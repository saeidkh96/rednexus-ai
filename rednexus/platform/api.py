from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from fastapi import FastAPI, Depends, Header, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from .config import Settings
from .storage import Database, Membership, User, Run, Event, Agent, Rule
from .contracts import (
    LoginInput,
    UserInput,
    AccessInput,
    RunInput,
    ReviewInput,
    MemoryInput,
    AgentInput,
    PlanInput,
    EventInput,
    RuleInput,
    ReconcileInput,
)
from .identity import Identity, Problem
from .adapters import Registry
from .service import Platform
from .agents import Planner
from .events import emit

STATIC = Path(__file__).resolve().parent.parent / "static"
security = HTTPBearer(auto_error=False)


class RequestLimits:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        # Bound streamed request size too, not only Content-Length.
        chunks, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > 262144:
                response = JSONResponse({"detail": "request exceeds 256 KiB"}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body", False):
                break

        async def replay_receive():
            if chunks:
                return chunks.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)


def create_app(settings=None, db=None, registry=None):
    settings = settings or Settings.from_env()
    db = db or Database(settings)
    registry = registry or Registry(settings)
    platform, identity = Platform(db, registry, settings), Identity(db, settings)

    @asynccontextmanager
    async def lifespan(app):
        db.health()
        yield

    app = FastAPI(title="RedNexus AI", version="2.0.0-rc.2", lifespan=lifespan)
    app.add_middleware(RequestLimits)
    app.state.platform, app.state.identity, app.state.db = platform, identity, db

    @app.exception_handler(Problem)
    async def problem_handler(request, exc):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.exception_handler(IntegrityError)
    async def conflict_handler(request, exc):
        return JSONResponse({"detail": "concurrent update or duplicate record; reload and retry"}, status_code=409)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        # Pydantic errors otherwise echo submitted passwords/tokens in `input`.
        return JSONResponse({"detail": [{k: e[k] for k in ("loc", "msg", "type")}
                                        for e in exc.errors()]}, status_code=422)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path == "/" or request.url.path.startswith("/static"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
            )
        return response

    def token(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
        if not credentials or credentials.scheme.lower() != "bearer":
            raise Problem(401, "bearer session required")
        return credentials.credentials

    def actor(value=Depends(token)):
        return identity.authenticate(value)

    @app.get("/health/live")
    def live():
        return {"status": "ok", "version": "2.0.0-rc.2"}

    @app.get("/health/ready")
    def ready():
        try:
            db.health()
            with db.session() as s:
                s.execute(select(Membership).limit(1))
        except Exception:
            raise Problem(503, "database unavailable or migration required") from None
        return {"database": "ok", "capabilities": len(registry.specs)}

    @app.post("/v1/auth/login")
    def login(data: LoginInput, request: Request):
        return identity.login(data, request.client.host if request.client else "")

    @app.post("/v1/auth/logout")
    def logout(value=Depends(token), current=Depends(actor)):
        identity.logout(value)
        return {"logged_out": True}

    @app.get("/v1/me")
    def me(current=Depends(actor)):
        return {**asdict(current), "grants": sorted(current.grants)}

    @app.get("/v1/users")
    def users(current=Depends(actor)):
        current.require_role("admin")
        with db.session() as s:
            records = s.execute(
                select(User, Membership)
                .join(Membership, User.id == Membership.user_id)
                .where(Membership.workspace == current.workspace)
            ).all()
            return [
                {
                    "id": u.id,
                    "username": u.username,
                    "kind": u.kind,
                    "role": m.role,
                    "enabled": m.enabled,
                    "grants": m.grants,
                }
                for u, m in records
            ]

    @app.post("/v1/users", status_code=201)
    def user_create(data: UserInput, current=Depends(actor)):
        current.require_role("admin")
        if any(g.startswith("platform:") for g in data.grants):
            raise Problem(403, "platform grants can only be assigned by the local operator")
        with db.session.begin() as s:
            result = identity.create_user(s, current.workspace, data)
            emit(s, current.workspace, "identity.created", {"actor": current.id, "user": result["id"]})
            return result

    @app.put("/v1/users/{user_id}/access")
    def user_access(user_id: str, data: AccessInput, current=Depends(actor)):
        current.require_role("admin")
        if any(g.startswith("platform:") for g in data.grants):
            raise Problem(403, "platform grants can only be assigned by the local operator")
        if user_id == current.id:
            raise Problem(409, "use a different administrator to change your own access")
        with db.session.begin() as s:
            m = s.get(Membership, (current.workspace, user_id))
            if not m:
                raise Problem(404, "membership not found")
            m.role, m.grants, m.enabled = data.role, data.grants, data.enabled
            emit(s, current.workspace, "identity.access_changed", {"actor": current.id, "user": user_id})
        return {"updated": True}

    @app.get("/v1/capabilities")
    def capabilities(current=Depends(actor)):
        registry.refresh()
        return registry.visible(current)

    @app.post("/v1/runs", status_code=201)
    def submit(data: RunInput, idempotency_key: str = Header(...), current=Depends(actor)):
        return platform.submit(current, data, idempotency_key)

    @app.get("/v1/runs")
    def runs(current=Depends(actor)):
        return platform.runs(current)

    @app.get("/v1/runs/{run_id}")
    def inspect(run_id: str, current=Depends(actor)):
        return platform.inspect(current, run_id)

    @app.post("/v1/runs/{run_id}/cancel")
    def cancel(run_id: str, current=Depends(actor)):
        return platform.cancel(current, run_id)

    @app.post("/v1/runs/{run_id}/reconcile")
    def reconcile(run_id: str, data: ReconcileInput, current=Depends(actor)):
        return platform.reconcile(current, run_id, data)

    @app.get("/v1/runs/{run_id}/replay")
    def replay(run_id: str, current=Depends(actor)):
        return platform.replay(current, run_id)

    @app.get("/v1/runs/{run_id}/evaluation")
    def evaluate(run_id: str, current=Depends(actor)):
        return platform.evaluation(current, run_id)

    @app.get("/v1/approvals")
    def approvals(current=Depends(actor)):
        return platform.approvals(current)

    @app.post("/v1/approvals/{approval_id}/decision")
    def decide(approval_id: str, data: ReviewInput, current=Depends(actor)):
        return platform.review(current, approval_id, data)

    @app.post("/v1/memory", status_code=201)
    def remember(data: MemoryInput, current=Depends(actor)):
        return platform.remember(current, data)

    @app.get("/v1/memory")
    def search(namespace: str, q: str = "", history: bool = False, current=Depends(actor)):
        return platform.search_memory(current, namespace, q, history)

    @app.delete("/v1/memory/{memory_id}")
    def forget(memory_id: str, current=Depends(actor)):
        return platform.delete_memory(current, memory_id)

    @app.post("/v1/agents", status_code=201)
    def create_agent(data: AgentInput, current=Depends(actor)):
        return platform.create_agent(current, data)

    @app.get("/v1/agents")
    def agents(current=Depends(actor)):
        with db.session() as s:
            return [
                {"id": a.id, **a.definition}
                for a in s.scalars(select(Agent).where(Agent.workspace == current.workspace, Agent.owner == current.id))
            ]

    @app.post("/v1/agents/{agent_id}/plan")
    async def plan(agent_id: str, data: PlanInput, current=Depends(actor)):
        return await Planner(platform).plan(current, agent_id, data.objective)

    @app.post("/v1/event-rules", status_code=201)
    def rule_create(data: RuleInput, current=Depends(actor)):
        return platform.create_rule(current, data)

    @app.delete("/v1/event-rules/{rule_id}")
    def disable_rule(rule_id: str, current=Depends(actor)):
        current.require_role("admin", "operator")
        with db.session.begin() as s:
            rule = s.get(Rule, rule_id)
            if (
                not rule
                or rule.workspace != current.workspace
                or (rule.owner != current.id and current.role != "admin")
            ):
                raise Problem(404, "rule not found")
            rule.enabled = False
        return {"disabled": True}

    @app.post("/v1/events/ingest")
    def ingest(data: EventInput, current=Depends(actor)):
        return platform.ingest(current, data)

    @app.get("/v1/audit")
    def audit(current=Depends(actor)):
        current.require_role("admin")
        with db.session() as s:
            return [
                row.body
                for row in s.scalars(
                    select(Event).where(Event.workspace == current.workspace).order_by(Event.created.desc()).limit(200)
                )
            ]

    @app.get("/v1/metrics", response_class=PlainTextResponse)
    def metrics(current=Depends(actor)):
        current.require_role("admin")
        with db.session() as s:
            states = s.execute(
                select(Run.status, func.count()).where(Run.workspace == current.workspace).group_by(Run.status)
            ).all()
            pending = s.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.workspace == current.workspace, Event.published.is_(False))
            )
            lines = ["# TYPE nexus_runs gauge"]
            lines.extend(f'nexus_runs{{status="{status}"}} {count}' for status, count in states)
            lines.extend(["# TYPE nexus_outbox_pending gauge", f"nexus_outbox_pending {pending}"])
            return "\n".join(lines) + "\n"

    from .extensions import install
    install(app, platform, actor)
    from .memory import install as install_memory
    install_memory(app, platform, actor)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def studio():
        return FileResponse(STATIC / "index.html")

    return app
