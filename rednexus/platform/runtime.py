import time
import asyncio
from sqlalchemy import select, update
from opentelemetry import trace
from .storage import Run, Approval, uid
from .identity import actor_for, Problem
from .contracts import digest
from .adapters import AdapterFailure, validate_payload
from .events import emit

TRACER = trace.get_tracer("rednexus.runtime")


class Worker:
    def __init__(self, platform, gateway):
        self.platform, self.gateway = platform, gateway
        self.db = platform.db

    def recover(self):
        now = time.time()
        with self.db.session.begin() as s:
            rows = list(s.scalars(select(Run).where(Run.status == "running", Run.lease_until < now)))
            for row in rows:
                step = row.plan[row.cursor]
                safe = step["contract"]["effect"] == "read"
                retry = safe and row.attempts < step["contract"]["max_attempts"]
                status = (
                    "needs_reconciliation"
                    if not safe
                    else "cancelled"
                    if row.cancel_requested
                    else "retry_wait"
                    if retry
                    else "failed"
                )
                result = s.execute(
                    update(Run)
                    .where(
                        Run.id == row.id,
                        Run.status == "running",
                        Run.lease_token == row.lease_token,
                        Run.lease_until < now,
                    )
                    .values(
                        status=status,
                        lease_token=None,
                        lease_until=None,
                        next_attempt=now,
                        error="worker_lease_expired",
                        updated=now,
                    )
                )
                if result.rowcount:
                    emit(s, row.workspace, "step.lease_expired", {"status": status}, row.id)
            expired = list(
                s.scalars(
                    select(Run).where(Run.status.in_(["queued", "retry_wait", "waiting_approval"]), Run.deadline < now)
                )
            )
            for row in expired:
                result = s.execute(
                    update(Run)
                    .where(
                        Run.id == row.id,
                        Run.status.in_(["queued", "retry_wait", "waiting_approval"]),
                        Run.deadline < now,
                    )
                    .values(status="expired", error="mission_deadline_exceeded", updated=now)
                )
                if result.rowcount:
                    s.execute(
                        update(Approval)
                        .where(Approval.run_id == row.id, Approval.status == "pending")
                        .values(status="expired")
                    )
                    emit(s, row.workspace, "workflow.expired", {}, row.id)
            pending = list(s.scalars(select(Approval).where(Approval.status == "pending", Approval.expires < now)))
            for approval in pending:
                changed = s.execute(
                    update(Approval)
                    .where(Approval.id == approval.id, Approval.status == "pending")
                    .values(status="expired")
                )
                if changed.rowcount:
                    s.execute(
                        update(Run)
                        .where(Run.id == approval.run_id, Run.status == "waiting_approval")
                        .values(status="expired", error="approval_expired", updated=now)
                    )

    def claim(self):
        now = time.time()
        with self.db.session() as s:
            ids = list(
                s.scalars(
                    select(Run.id)
                    .where(Run.status.in_(["queued", "retry_wait"]), Run.next_attempt <= now, Run.deadline > now)
                    .order_by(Run.created)
                    .limit(20)
                )
            )
        for run_id in ids:
            token = uid()
            with self.db.session.begin() as s:
                changed = s.execute(
                    update(Run)
                    .where(
                        Run.id == run_id,
                        Run.status.in_(["queued", "retry_wait"]),
                        Run.next_attempt <= now,
                        Run.cancel_requested.is_(False),
                    )
                    .values(
                        status="running",
                        lease_token=token,
                        lease_until=now + self.platform.settings.lease_seconds,
                        updated=now,
                    )
                )
                if changed.rowcount:
                    return run_id, token
        return None

    def prepare(self, run_id, token):
        with self.db.session.begin() as s:
            changed = s.execute(
                update(Run)
                .where(
                    Run.id == run_id, Run.status == "running", Run.lease_token == token, Run.lease_until > time.time()
                )
                .values(updated=time.time())
            )
            if not changed.rowcount:
                return None
            row = s.get(Run, run_id)
            try:
                actor = actor_for(s, row.owner, row.workspace)
                actor.require_role("admin", "operator")
                step = row.plan[row.cursor]
                actor.require(f"tool:{step['capability']}")
                spec = self.platform.registry.get(step["capability"])
                if self.platform.registry.fingerprint(spec.name) != step["fingerprint"]:
                    raise Problem(409, "capability_contract_changed")
                payload = dict(step["input"])
                if step["use_previous"]:
                    payload["previous"] = row.outputs[-1]
                validate_payload(spec.input_schema, payload)
                action = {
                    "run_id": row.id,
                    "step": row.cursor,
                    "capability": spec.name,
                    "fingerprint": step["fingerprint"],
                    "input": payload,
                    "estimated_cost_microunits": spec.estimated_cost_microunits,
                }
                action_digest = digest(action)
                if row.cancel_requested:
                    row.status = "cancelled"
                    row.lease_token = None
                    return None
                if spec.approval:
                    approval = s.scalar(select(Approval).where(Approval.run_id == run_id, Approval.step == row.cursor))
                    if approval is None:
                        s.add(
                            Approval(
                                workspace=row.workspace,
                                run_id=row.id,
                                step=row.cursor,
                                action_digest=action_digest,
                                action=action,
                                expires=min(row.deadline, time.time() + self.platform.settings.approval_seconds),
                            )
                        )
                        row.status, row.lease_token, row.lease_until = "waiting_approval", None, None
                        emit(
                            s,
                            row.workspace,
                            "approval.requested",
                            {"step": row.cursor, "digest": action_digest},
                            row.id,
                        )
                        return None
                    if (
                        approval.status != "approved"
                        or approval.action_digest != action_digest
                        or approval.expires < time.time()
                    ):
                        raise Problem(409, "approval_invalid_or_expired")
                    reviewer = actor_for(s, approval.reviewer, row.workspace)
                    reviewer.require_role("admin", "reviewer")
                    reviewer.require(f"review:{spec.name}")
                    if reviewer.kind != "human" or reviewer.id == actor.id:
                        raise Problem(403, "reviewer_identity_invalid")
                if row.tool_calls >= row.max_tool_calls or row.cost + spec.estimated_cost_microunits > row.budget:
                    raise Problem(409, "mission_budget_exhausted")
                row.tool_calls += 1
                row.attempts += 1
                row.cost += spec.estimated_cost_microunits
                emit(
                    s,
                    row.workspace,
                    "step.started",
                    {
                        "step": row.cursor,
                        "capability": spec.name,
                        "attempt": row.attempts,
                        "simulated": spec.mode == "demo",
                    },
                    row.id,
                )
                return (
                    spec,
                    payload,
                    {
                        "run_id": row.id,
                        "workspace": row.workspace,
                        "actor": row.owner,
                        "step": row.cursor,
                        "idempotency_key": f"{row.id}:{row.cursor}",
                        "deadline": min(row.deadline, time.time() + spec.timeout_seconds),
                    },
                )
            except Problem as exc:
                row.status, row.error, row.lease_token, row.lease_until = "blocked", exc.message, None, None
                emit(s, row.workspace, "step.blocked", {"reason": exc.message}, row.id)
                return None

    def finish(self, run_id, token, output=None, error=None):
        with self.db.session.begin() as s:
            # Lock/fence the run by a conditional UPDATE before reading mutable state.
            changed = s.execute(
                update(Run)
                .where(
                    Run.id == run_id, Run.status == "running", Run.lease_token == token, Run.lease_until > time.time()
                )
                .values(updated=time.time())
            )
            if not changed.rowcount:
                return
            row = s.get(Run, run_id)
            spec = row.plan[row.cursor]["contract"]
            row.lease_token, row.lease_until = None, None
            if error:
                retry = error.retryable and spec["effect"] == "read" and row.attempts < spec["max_attempts"]
                row.error = error.code
                row.status = (
                    "needs_reconciliation"
                    if spec["effect"] != "read"
                    else "cancelled"
                    if row.cancel_requested
                    else "retry_wait"
                    if retry
                    else "failed"
                )
                row.next_attempt = time.time() + min(30, 2**row.attempts)
                emit(s, row.workspace, "step.failed", {"code": error.code, "status": row.status}, row.id)
            else:
                row.outputs = [*row.outputs, output]
                row.cursor += 1
                row.attempts = 0
                row.error = None
                row.status = (
                    "cancelled" if row.cancel_requested else "completed" if row.cursor == len(row.plan) else "queued"
                )
                emit(s, row.workspace, "step.completed", {"step": row.cursor - 1}, row.id)
                if row.status == "completed":
                    emit(s, row.workspace, "workflow.completed", {"steps": row.cursor, "cost": row.cost}, row.id)

    async def tick(self):
        self.recover()
        claim = self.claim()
        if not claim:
            return False
        run_id, token = claim
        prepared = self.prepare(run_id, token)
        if prepared:
            spec, payload, context = prepared
            with TRACER.start_as_current_span("nexus.step") as span:
                span.set_attribute("nexus.run_id", run_id)
                span.set_attribute("nexus.capability", spec.name)
                try:
                    remaining = max(0.001, context["deadline"] - time.time())
                    async with asyncio.timeout(remaining):
                        output = await self.gateway.execute(spec, payload, context)
                    self.finish(run_id, token, output=output)
                except TimeoutError:
                    self.finish(run_id, token, error=AdapterFailure("mission_or_tool_timeout", True))
                except AdapterFailure as exc:
                    self.finish(run_id, token, error=exc)
                except Exception:
                    self.finish(run_id, token, error=AdapterFailure("internal_adapter_error"))
        return True
