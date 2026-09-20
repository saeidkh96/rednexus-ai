"""Version 2 control-plane APIs, sharing v1 identities, grants and execution fences."""
import asyncio
import time
import httpx
from fastapi import Depends, Header, Query
from pydantic import Field
from sqlalchemy import select, func, update
from .contracts import Contract, RunInput, CapabilitySpec, digest
from .identity import Problem, actor_for
from .storage import (Template, CapabilityRegistration, WorkerHeartbeat, Run, Event,
                      MissionGroup, Workspace, Membership)
from .events import emit
from .adapters import Registry
from .credentials import credential


class TemplateInput(Contract):
    name: str = Field(min_length=1, max_length=100)
    workflow: RunInput


class Assignment(Contract):
    agent_id: str
    workflow: RunInput


class GroupInput(Contract):
    title: str = Field(min_length=1, max_length=200)
    assignments: list[Assignment] = Field(min_length=1, max_length=10)
    budget_microunits: int = Field(default=1000000, ge=0, le=1000000000)


class ReplanInput(Contract):
    agent_id: str
    objective: str = Field(min_length=1, max_length=3000)


class TeamObjective(Contract):
    agent_id: str
    objective: str = Field(min_length=1, max_length=3000)


class TeamPlanInput(Contract):
    title: str = Field(min_length=1, max_length=200)
    objectives: list[TeamObjective] = Field(min_length=1, max_length=5)
    budget_microunits: int = Field(default=1000000, ge=0, le=1000000000)


class WorkspaceInput(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,60}$")
    name: str = Field(min_length=1, max_length=120)


def workflow_from_run(row):
    return RunInput(title=row.title, steps=[{key: value for key, value in step.items()
                    if key not in ("contract", "fingerprint")} for step in row.plan],
                    budget_microunits=row.budget, max_tool_calls=row.max_tool_calls)


def install(app, platform, actor):
    db, registry, settings = platform.db, platform.registry, platform.settings

    from .drafts import DraftInput, build_draft

    @app.post("/v2/workflow-drafts")
    def workflow_draft(data: DraftInput, current=Depends(actor)):
        current.require_role("admin", "operator")
        result = build_draft(data)
        registry.refresh()
        names = [s["capability"] for s in result["workflow"]["steps"]]
        result["missing_grants"] = [f"tool:{name}" for name in names if f"tool:{name}" not in current.grants]
        result["unavailable_capabilities"] = [name for name in names if name not in registry.specs or
            registry.specs[name].mode == "disabled" or registry.specs[name].workspace_binding not in (None, current.workspace)]
        result["review_grants"] = [f"review:{name}" for name in names if name in registry.specs and
                                  registry.specs[name].approval]
        return result

    @app.get("/v2/runs/{run_id}/evidence")
    def run_evidence(run_id: str, current=Depends(actor)):
        record = platform.inspect(current, run_id)
        bundle = {"schema_version": "1.0", "scope": "recorded execution; no tools invoked",
                  "run": record}
        # Integrity checksum, not a signature or independent verification of upstream claims.
        return {**bundle, "sha256": digest(bundle)}

    @app.get("/v2/mission-groups")
    def list_groups(current=Depends(actor)):
        with db.session() as s:
            query = select(MissionGroup).where(MissionGroup.workspace == current.workspace)
            if current.role not in ("admin", "reviewer"):
                query = query.where(MissionGroup.owner == current.id)
            return [{"id": g.id, "title": g.title} for g in s.scalars(query.limit(100))]

    @app.post("/v2/workspaces", status_code=201)
    def create_workspace(data: WorkspaceInput, current=Depends(actor)):
        # Workspace creation is an explicit global grant, never implied by tenant admin.
        current.require_role("admin")
        current.require("platform:workspaces:create")
        with db.session.begin() as s:
            s.add(Workspace(id=data.id, name=data.name))
            s.add(Membership(workspace=data.id, user_id=current.id, role="admin", grants=[]))
            emit(s, current.workspace, "workspace.created", {"workspace": data.id, "actor": current.id})
        return {"id": data.id, "name": data.name, "grants": []}

    @app.post("/v2/templates", status_code=201)
    def save_template(data: TemplateInput, current=Depends(actor)):
        platform.snapshot(current, data.workflow)
        with db.session.begin() as s:
            s.execute(update(Workspace).where(Workspace.id == current.workspace).values(name=Workspace.name))
            version = (s.scalar(select(func.max(Template.version)).where(
                Template.workspace == current.workspace, Template.name == data.name)) or 0) + 1
            row = Template(workspace=current.workspace, name=data.name, version=version,
                           workflow=data.workflow.model_dump(), owner=current.id)
            s.add(row)
            s.flush()
            emit(s, current.workspace, "template.created", {"id": row.id, "version": version, "actor": current.id})
            return {"id": row.id, "version": version}

    @app.get("/v2/templates")
    def templates(current=Depends(actor)):
        with db.session() as s:
            rows = s.scalars(select(Template).where(Template.workspace == current.workspace)
                             .order_by(Template.created.desc()).limit(100))
            return [{k: getattr(r, k) for k in ("id", "name", "version", "workflow", "created")} for r in rows]

    @app.post("/v2/templates/{template_id}/runs", status_code=201)
    def template_run(template_id: str, idempotency_key: str = Header(...), current=Depends(actor)):
        with db.session() as s:
            row = s.get(Template, template_id)
            if not row or row.workspace != current.workspace:
                raise Problem(404, "template not found")
            workflow = RunInput.model_validate(row.workflow)
        # Re-authorize and snapshot today's contracts; saving a template grants no authority.
        return platform.submit(current, workflow, idempotency_key)

    @app.post("/v2/capabilities", status_code=201)
    def register(data: CapabilitySpec, current=Depends(actor)):
        current.require_role("admin")
        if data.workspace_binding != current.workspace:
            raise Problem(422, "registration must be bound to this workspace")
        Registry(settings, [data.model_dump()])
        registry.refresh()
        existing = registry.specs.get(data.name)
        if existing and existing.workspace_binding != current.workspace:
            raise Problem(409, "capability name reserved by another scope")
        with db.session.begin() as s:
            row = s.get(CapabilityRegistration, (current.workspace, data.name))
            if existing and existing.version == data.version and digest(existing.model_dump()) != digest(data.model_dump()):
                raise Problem(409, "changed contracts require a new version")
            if row:
                row.spec, row.updated = data.model_dump(), time.time()
            else:
                s.add(CapabilityRegistration(workspace=current.workspace, name=data.name, spec=data.model_dump()))
            emit(s, current.workspace, "capability.registered", {"name": data.name, "version": data.version,
                                                               "actor": current.id})
        registry.refresh()
        return {"name": data.name, "version": data.version, "fingerprint": registry.fingerprint(data.name)
                if data.mode != "disabled" else digest(data.model_dump())}

    @app.get("/v2/discovery")
    async def discovery(current=Depends(actor)):
        registry.refresh()
        visible = registry.visible(current)
        semaphore = asyncio.Semaphore(8)

        async def probe(item):
            spec = registry.specs[item["name"]]
            result = {"name": spec.name, "project": spec.project, "version": spec.version,
                      "mode": spec.mode, "status": "unconfigured", "checked_at": time.time()}
            try:
                result["credential_ready"] = not spec.credential_env or bool(credential(settings, spec.credential_env))
            except (OSError, ValueError):
                result["credential_ready"] = False
            if spec.mode != "http":
                result["status"] = spec.mode
                return result
            if not spec.health_endpoint:
                return result
            registry.check_endpoint(spec.health_endpoint)
            async with semaphore:
                try:
                    async with httpx.AsyncClient(timeout=3, follow_redirects=False, trust_env=False) as client:
                        async with client.stream("GET", spec.health_endpoint) as response:
                            result["status"] = "online" if 200 <= response.status_code < 300 else "unhealthy"
                            result["http_status"] = response.status_code
                except httpx.HTTPError:
                    result["status"] = "offline"
            return result

        return await asyncio.gather(*(probe(item) for item in visible))

    @app.post("/v2/mission-groups", status_code=201)
    def submit_group(data: GroupInput, idempotency_key: str = Header(...), current=Depends(actor)):
        current.require_role("admin", "operator")
        if not 1 <= len(idempotency_key) <= 160:
            raise Problem(422, "group idempotency key must contain 1..160 characters")
        if sum(a.workflow.budget_microunits for a in data.assignments) > data.budget_microunits:
            raise Problem(422, "assigned budgets exceed mission group budget")
        fingerprint = digest(data.model_dump())
        with db.session.begin() as s:
            s.execute(update(Workspace).where(Workspace.id == current.workspace).values(name=Workspace.name))
            old = s.scalar(select(MissionGroup).where(MissionGroup.workspace == current.workspace,
                           MissionGroup.owner == current.id, MissionGroup.request_key == idempotency_key))
            if old:
                if old.request_digest != fingerprint:
                    raise Problem(409, "group idempotency key conflict")
                return {"id": old.id, "runs": old.runs}
            run_ids = []
            for index, assignment in enumerate(data.assignments):
                agent = platform.get_agent(current, assignment.agent_id)
                if assignment.workflow.budget_microunits > agent["budget_microunits"]:
                    raise Problem(422, "assignment exceeds agent budget")
                if any(step.capability not in agent["capabilities"] for step in assignment.workflow.steps):
                    raise Problem(403, "assignment exceeds agent capability scope")
                row = platform.submit_in(s, current, assignment.workflow, f"group:{idempotency_key}:{index}")
                run_ids.append({"agent_id": assignment.agent_id, "run_id": row.id})
            group = MissionGroup(workspace=current.workspace, owner=current.id, request_key=idempotency_key,
                                 request_digest=fingerprint, title=data.title, runs=run_ids, budget=data.budget_microunits)
            s.add(group)
            s.flush()
            emit(s, current.workspace, "mission_group.submitted", {"id": group.id, "runs": run_ids})
            return {"id": group.id, "runs": run_ids}

    @app.post("/v2/agent-teams/plan")
    async def team_plan(data: TeamPlanInput, current=Depends(actor)):
        from .agents import Planner
        current.require_role("admin", "operator")
        profiles = [platform.get_agent(current, item.agent_id) for item in data.objectives]
        if sum(profile["budget_microunits"] for profile in profiles) > data.budget_microunits:
            raise Problem(422, "agent budgets exceed team budget; reduce agent budgets first")
        # Each planner independently validates its scope. Nothing is queued until explicit submission.
        proposals = await asyncio.gather(*(Planner(platform).plan(current, item.agent_id, item.objective)
                                           for item in data.objectives))
        return {"execution_started": False, "group": {"title": data.title,
            "budget_microunits": data.budget_microunits,
            "assignments": [{"agent_id": item.agent_id, "workflow": proposal["workflow"]}
                            for item, proposal in zip(data.objectives, proposals)]},
            "usage": [p["usage"] for p in proposals]}

    @app.get("/v2/mission-groups/{group_id}")
    def group_status(group_id: str, current=Depends(actor)):
        with db.session() as s:
            row = s.get(MissionGroup, group_id)
            if not row or row.workspace != current.workspace or (row.owner != current.id and current.role not in ("admin", "reviewer")):
                raise Problem(404, "mission group not found")
            states = [platform.accessible_run(s, current, item["run_id"]) for item in row.runs]
            return {"id": row.id, "title": row.title, "budget": row.budget,
                    "cost": sum(r.cost for r in states),
                    "completed": all(r.status == "completed" for r in states),
                    "runs": [{"id": r.id, "status": r.status, "cost": r.cost} for r in states]}

    @app.post("/v2/runs/{run_id}/replan")
    async def replan(run_id: str, data: ReplanInput, current=Depends(actor)):
        from .agents import Planner
        with db.session() as s:
            row = platform.accessible_run(s, current, run_id)
            if row.status not in ("failed", "blocked", "cancelled", "expired", "reconciled_failed"):
                raise Problem(409, "resolve active or uncertain execution before replanning")
            # Do not silently replay successful effects or send sensitive output to a model.
            context = f"Previous run status: {row.status}; finished steps: {row.cursor}; error code: {row.error}. "
        proposal = await Planner(platform).plan(current, data.agent_id, context + data.objective)
        return {**proposal, "supersedes": run_id, "requires_new_submission": True}

    @app.get("/v2/operations")
    def operations(current=Depends(actor)):
        current.require_role("admin")
        with db.session() as s:
            counts = dict(s.execute(select(Run.status, func.count()).where(Run.workspace == current.workspace)
                                   .group_by(Run.status)).all())
            cost = s.scalar(select(func.sum(Run.cost)).where(Run.workspace == current.workspace)) or 0
            workers = list(s.scalars(select(WorkerHeartbeat)))
            pending = s.scalar(select(func.count()).select_from(Event).where(Event.workspace == current.workspace,
                                                                                  Event.published.is_(False)))
            # Worker credentials/host/process details stay local, not exposed across workspaces.
            return {"runs": counts, "reserved_cost_microunits": cost, "outbox_pending": pending,
                    "broker_enabled": bool(settings.redis_url),
                    "workers_alive": sum(w.status == "running" and w.updated > time.time() - 30 for w in workers),
                    "workers_stale": sum(w.status == "running" and w.updated <= time.time() - 30 for w in workers)}

    @app.get("/v2/dead-letters")
    def dead_letters(limit: int = Query(default=100, ge=1, le=100), current=Depends(actor)):
        current.require_role("admin", "operator")
        from .service import run_view
        with db.session() as s:
            query = select(Run).where(Run.workspace == current.workspace,
                Run.status.in_(("failed", "blocked", "needs_reconciliation", "expired")))
            if current.role != "admin":
                query = query.where(Run.owner == current.id)
            return [run_view(r) for r in s.scalars(query.order_by(Run.updated.desc()).limit(limit))]

    @app.post("/v2/runs/{run_id}/retry-read", status_code=201)
    def retry_read(run_id: str, idempotency_key: str = Header(...), current=Depends(actor)):
        with db.session() as s:
            row = platform.accessible_run(s, current, run_id)
            if row.status not in ("failed", "blocked", "expired"):
                raise Problem(409, "only failed terminal reads can be resubmitted")
            if any(step["contract"]["effect"] != "read" for step in row.plan):
                raise Problem(409, "effectful workflows require explicit reconciliation and a new plan")
            workflow = workflow_from_run(row)
        result = platform.submit(current, workflow, idempotency_key)
        return {**result, "retried_from": run_id}

    @app.post("/v2/validate")
    def validate_workflow(data: RunInput, current=Depends(actor)):
        plan = platform.snapshot(current, data)
        return {"valid": True, "steps": len(plan), "execution_started": False,
                "dynamic_inputs_checked_at_execution": any(s.bindings or s.use_previous for s in data.steps)}

    @app.get("/v2/access-check")
    def access_check(current=Depends(actor)):
        with db.session() as s:
            fresh = actor_for(s, current.id, current.workspace)
        return {"workspace": fresh.workspace, "role": fresh.role, "grants": sorted(fresh.grants)}
