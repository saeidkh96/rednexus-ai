import time
from sqlalchemy import select, func, update, delete
from sqlalchemy.exc import IntegrityError
from .contracts import digest, RunInput
from .identity import Problem, actor_for
from .storage import Run, Approval, Event, Memory, Agent, Rule, Inbox, Membership, Workspace, MemoryVector
from .events import emit
from .adapters import validate_payload
from .workflows import validate_static


def run_view(row):
    return {
        k: getattr(row, k)
        for k in [
            "id",
            "title",
            "status",
            "cursor",
            "outputs",
            "created",
            "updated",
            "deadline",
            "error",
            "tool_calls",
            "cost",
            "budget",
            "cancel_requested",
            "plan",
            "owner",
        ]
    }


class Platform:
    def __init__(self, db, registry, settings):
        self.db, self.registry, self.settings = db, registry, settings
        registry.db = db

    def accessible_run(self, s, actor, run_id):
        row = s.get(Run, run_id)
        if not row or row.workspace != actor.workspace:
            raise Problem(404, "run not found")
        if row.owner != actor.id and actor.role not in ("admin", "reviewer"):
            raise Problem(404, "run not found")
        return row

    def snapshot(self, actor, workflow):
        self.registry.refresh()
        actor.require_role("admin", "operator")
        plan = []
        for index, step in enumerate(workflow.steps):
            spec = self.registry.get(step.capability)
            if spec.workspace_binding and spec.workspace_binding != actor.workspace:
                raise Problem(403, "capability is bound to a different workspace")
            actor.require(f"tool:{spec.name}")
            if step.use_previous and index == 0:
                raise Problem(422, "first step cannot consume a previous result")
            validate_static(spec.input_schema, step)
            plan.append(
                {
                    **step.model_dump(),
                    "contract": spec.model_dump(),
                    "fingerprint": self.registry.fingerprint(spec.name),
                }
            )
        return plan

    def submit_in(self, s, actor, workflow, request_key):
        if not request_key or len(request_key) > 200:
            raise Problem(422, "Idempotency-Key must contain 1..200 characters")
        request_digest = digest(workflow.model_dump())
        old = s.scalar(
            select(Run).where(Run.workspace == actor.workspace, Run.owner == actor.id, Run.request_key == request_key)
        )
        if old:
            if old.request_digest != request_digest:
                raise Problem(409, "idempotency key already used for different content")
            return old
        # Serialize admission per workspace so concurrent submits cannot exceed the cap.
        s.execute(update(Workspace).where(Workspace.id == actor.workspace).values(name=Workspace.name))
        active = s.scalar(
            select(func.count())
            .select_from(Run)
            .where(
                Run.workspace == actor.workspace,
                Run.status.in_(["queued", "running", "retry_wait", "waiting_approval"]),
            )
        )
        if active >= 100:
            raise Problem(429, "workspace active mission quota exhausted")
        plan = self.snapshot(actor, workflow)
        row = Run(
            workspace=actor.workspace,
            owner=actor.id,
            title=workflow.title,
            request_key=request_key,
            request_digest=request_digest,
            plan=plan,
            deadline=time.time() + workflow.deadline_seconds,
            max_tool_calls=workflow.max_tool_calls,
            budget=workflow.budget_microunits,
        )
        s.add(row)
        s.flush()
        emit(s, actor.workspace, "workflow.submitted", {"steps": len(plan), "actor": actor.id}, row.id)
        return row

    def submit(self, actor, workflow, request_key):
        try:
            with self.db.session.begin() as s:
                return run_view(self.submit_in(s, actor, workflow, request_key))
        except IntegrityError:
            # A concurrent request with the same key may have won the unique constraint.
            with self.db.session.begin() as s:
                return run_view(self.submit_in(s, actor, workflow, request_key))

    def runs(self, actor, limit=100):
        with self.db.session() as s:
            q = select(Run).where(Run.workspace == actor.workspace)
            if actor.role not in ("admin", "reviewer"):
                q = q.where(Run.owner == actor.id)
            return [run_view(r) for r in s.scalars(q.order_by(Run.created.desc()).limit(limit))]

    def inspect(self, actor, run_id):
        with self.db.session() as s:
            row = self.accessible_run(s, actor, run_id)
            events = [
                e.body for e in s.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.created, Event.id))
            ]
            return {**run_view(row), "events": events}

    def cancel(self, actor, run_id):
        actor.require_role("admin", "operator")
        with self.db.session.begin() as s:
            row = self.accessible_run(s, actor, run_id)
            # Atomic update cannot replace an active lease or resurrect a terminal run.
            result = s.execute(
                update(Run)
                .where(Run.id == row.id, Run.status.in_(["queued", "retry_wait", "waiting_approval", "running"]))
                .values(cancel_requested=True, updated=time.time())
            )
            if result.rowcount != 1:
                raise Problem(409, "run already terminal")
            s.execute(update(Run).where(Run.id == row.id, Run.status != "running").values(status="cancelled"))
            s.execute(
                update(Approval)
                .where(Approval.run_id == row.id, Approval.status == "pending")
                .values(status="cancelled")
            )
            emit(s, actor.workspace, "workflow.cancellation_requested", {"actor": actor.id}, row.id)
        return {"requested": True}

    def approvals(self, actor):
        actor.require_role("admin", "reviewer")
        with self.db.session() as s:
            rows = s.scalars(
                select(Approval)
                .where(Approval.workspace == actor.workspace, Approval.status == "pending")
                .order_by(Approval.expires)
            )
            return [
                {k: getattr(a, k) for k in ["id", "run_id", "step", "action_digest", "action", "expires", "status"]}
                for a in rows
            ]

    def review(self, actor, approval_id, decision):
        actor.require_role("admin", "reviewer")
        if actor.kind != "human":
            raise Problem(403, "service identities cannot supply human approval")
        with self.db.session.begin() as s:
            approval = s.get(Approval, approval_id)
            if not approval or approval.workspace != actor.workspace:
                raise Problem(404, "approval not found")
            row = s.get(Run, approval.run_id)
            if row.owner == actor.id:
                raise Problem(403, "requester cannot approve own workflow")
            if approval.action_digest != decision.digest:
                raise Problem(409, "action digest does not match")
            if approval.expires <= time.time():
                raise Problem(409, "approval expired; submit a new workflow")
            if row.status != "waiting_approval" or row.cancel_requested:
                raise Problem(409, "workflow is not awaiting this approval")
            spec = self.registry.get(row.plan[row.cursor]["capability"])
            actor.require(f"review:{spec.name}")
            result = s.execute(
                update(Approval)
                .where(Approval.id == approval_id, Approval.status == "pending")
                .values(status="approved" if decision.allow else "rejected", reviewer=actor.id, reason=decision.reason)
            )
            if result.rowcount != 1:
                raise Problem(409, "approval already decided")
            changed = s.execute(
                update(Run)
                .where(Run.id == row.id, Run.status == "waiting_approval", Run.cancel_requested.is_(False))
                .values(status="queued" if decision.allow else "rejected", updated=time.time())
            )
            if changed.rowcount != 1:
                raise Problem(409, "workflow changed during review")
            emit(
                s,
                actor.workspace,
                "approval.decided",
                {"reviewer": actor.id, "allow": decision.allow, "digest": decision.digest, "reason": decision.reason},
                row.id,
            )
        return {"status": "approved" if decision.allow else "rejected"}

    def remember(self, actor, data):
        actor.require(f"memory:{data.namespace}:write")
        with self.db.session.begin() as s:
            maximum = (
                s.scalar(
                    select(func.max(Memory.version)).where(
                        Memory.workspace == actor.workspace, Memory.namespace == data.namespace, Memory.key == data.key
                    )
                )
                or 0
            )
            row = Memory(
                workspace=actor.workspace,
                namespace=data.namespace,
                key=data.key,
                version=maximum + 1,
                text=data.text,
                source=data.source,
                author=actor.id,
                expires=time.time() + data.ttl_seconds,
            )
            s.add(row)
            s.flush()
            emit(
                s,
                actor.workspace,
                "memory.written",
                {"id": row.id, "namespace": row.namespace, "version": row.version, "actor": actor.id},
            )
            return {"id": row.id, "version": row.version}

    def search_memory(self, actor, namespace, query="", history=False):
        actor.require(f"memory:{namespace}:read")
        with self.db.session() as s:
            rows = list(
                s.scalars(
                    select(Memory)
                    .where(Memory.workspace == actor.workspace, Memory.namespace == namespace)
                    .order_by(Memory.created.desc(), Memory.version.desc())
                    .limit(1000)
                )
            )
            # Select latest version before expiry/deletion/query filtering: never resurface a stale version.
            if not history:
                latest = {}
                for row in rows:
                    if row.key not in latest:
                        latest[row.key] = row
                rows = list(latest.values())
            words = query.casefold().split()
            results = []
            for row in rows:
                if row.deleted or row.expires <= time.time():
                    continue
                score = sum(row.text.casefold().count(word) for word in words)
                if words and not score:
                    continue
                results.append(
                    {
                        k: getattr(row, k)
                        for k in ["id", "namespace", "key", "version", "text", "source", "author", "created", "expires"]
                    }
                    | {"score": score}
                )
            return sorted(results, key=lambda x: (x["score"], x["created"]), reverse=True)[:100]

    def delete_memory(self, actor, memory_id):
        with self.db.session.begin() as s:
            row = s.get(Memory, memory_id)
            if not row or row.workspace != actor.workspace:
                raise Problem(404, "memory not found")
            actor.require(f"memory:{row.namespace}:write")
            ids = select(Memory.id).where(Memory.workspace == actor.workspace, Memory.namespace == row.namespace,
                                         Memory.key == row.key)
            # Redact every version of this logical key; audit retains only record identifiers.
            s.execute(
                update(Memory)
                .where(Memory.workspace == actor.workspace, Memory.namespace == row.namespace, Memory.key == row.key)
                .values(deleted=True, text="", source="deleted")
            )
            s.execute(delete(MemoryVector).where(MemoryVector.memory_id.in_(ids)))
            emit(s, actor.workspace, "memory.deleted", {"namespace": row.namespace, "key": row.key, "actor": actor.id})
        return {"deleted": True}

    def create_agent(self, actor, data):
        actor.require_role("admin", "operator")
        for capability in data.capabilities:
            self.registry.get(capability)
            actor.require(f"tool:{capability}")
        with self.db.session.begin() as s:
            row = Agent(workspace=actor.workspace, owner=actor.id, definition=data.model_dump())
            s.add(row)
            s.flush()
            return {"id": row.id, **row.definition}

    def get_agent(self, actor, agent_id):
        with self.db.session() as s:
            row = s.get(Agent, agent_id)
            if not row or row.workspace != actor.workspace or row.owner != actor.id:
                raise Problem(404, "agent not found")
            return {"id": row.id, **row.definition}

    def create_rule(self, actor, data):
        actor.require_role("admin", "operator")
        self.snapshot(actor, data.workflow)
        with self.db.session.begin() as s:
            producer = s.get(Membership, (actor.workspace, data.producer_id))
            if not producer or not producer.enabled or "events:ingest" not in producer.grants:
                raise Problem(422, "producer requires active membership and events:ingest grant")
            row = Rule(
                workspace=actor.workspace,
                owner=actor.id,
                producer_id=data.producer_id,
                event_type=data.event_type,
                source=data.source,
                workflow=data.workflow.model_dump(),
            )
            s.add(row)
            s.flush()
            return {"id": row.id}

    def ingest(self, actor, event):
        actor.require("events:ingest")
        fingerprint = digest(event.model_dump())
        try:
            with self.db.session.begin() as s:
                old = s.scalar(
                    select(Inbox).where(
                        Inbox.workspace == actor.workspace, Inbox.source == event.source, Inbox.external_id == event.id
                    )
                )
                if old:
                    if old.digest != fingerprint:
                        raise Problem(409, "event ID reused with different data")
                    return {"duplicate": True, "run_ids": old.run_ids}
                record = Inbox(workspace=actor.workspace, source=event.source, external_id=event.id, digest=fingerprint)
                s.add(record)
                s.flush()
                rules = s.scalars(
                    select(Rule).where(
                        Rule.workspace == actor.workspace,
                        Rule.producer_id == actor.id,
                        Rule.source == event.source,
                        Rule.event_type == event.type,
                        Rule.enabled.is_(True),
                    )
                )
                run_ids = []
                for rule in rules:
                    owner = actor_for(s, rule.owner, actor.workspace)
                    definition = RunInput.model_validate(rule.workflow)
                    # Producer data goes into one named data field, never into permissions or plan structure.
                    definition.steps[0].input = {**definition.steps[0].input, "event": event.data}
                    row = self.submit_in(s, owner, definition, f"event:{record.id}:{rule.id}")
                    run_ids.append(row.id)
                record.run_ids = run_ids
                emit(
                    s,
                    actor.workspace,
                    "external_event.accepted",
                    {"event_id": event.id, "source": event.source, "producer": actor.id, "runs": run_ids},
                )
                return {"duplicate": False, "run_ids": run_ids}
        except IntegrityError:
            raise Problem(409, "event concurrently received; retry with same ID") from None

    def replay(self, actor, run_id):
        # Evidence replay never calls the gateway or resubmits a workflow.
        data = self.inspect(actor, run_id)
        return {"mode": "evidence_only", "run_id": run_id, "events": data["events"], "outputs": data["outputs"]}

    def evaluation(self, actor, run_id):
        data = self.inspect(actor, run_id)
        outputs = data["outputs"]
        return {
            "run_id": run_id,
            "completed": data["status"] == "completed",
            "steps_finished": len(outputs),
            "steps_total": len(data["plan"]),
            "within_reserved_budget": data["cost"] <= data["budget"],
            "simulated_outputs": sum(bool(x.get("simulated")) for x in outputs if isinstance(x, dict)),
            "outputs_with_evidence": sum(bool(x.get("evidence")) for x in outputs if isinstance(x, dict)),
            "quality_judgment": "structural checks only; domain quality needs domain-specific evaluators",
        }

    def reconcile(self, actor, run_id, data):
        actor.require_role("admin")
        if actor.kind != "human":
            raise Problem(403, "human reconciliation required")
        with self.db.session.begin() as s:
            row = self.accessible_run(s, actor, run_id)
            if row.owner == actor.id:
                raise Problem(403, "a different administrator must reconcile this run")
            changed = s.execute(
                update(Run).where(Run.id == run_id, Run.status == "needs_reconciliation").values(updated=time.time())
            )
            if changed.rowcount != 1:
                raise Problem(409, "run does not require reconciliation")
            s.refresh(row)
            step = row.plan[row.cursor]
            actor.require(f"review:{step['capability']}")
            if data.outcome == "confirmed_succeeded":
                validate_payload(step["contract"]["output_schema"], data.output)
                row.outputs = [*row.outputs, data.output]
                row.cursor += 1
                row.attempts = 0
                row.status = (
                    "cancelled" if row.cancel_requested else "completed" if row.cursor == len(row.plan) else "queued"
                )
            else:
                row.status = "failed" if data.outcome == "confirmed_failed" else "cancelled"
            row.error = None
            emit(
                s,
                actor.workspace,
                "step.reconciled",
                {"reviewer": actor.id, "outcome": data.outcome, "evidence": data.evidence},
                row.id,
            )
            return run_view(row)
