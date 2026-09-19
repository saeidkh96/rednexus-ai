import argparse
import asyncio
import getpass
import json
import os
import secrets
import signal
import sqlite3
import re
from contextlib import nullcontext
from pydantic import ValidationError
from pathlib import Path
from sqlalchemy import select
from .config import Settings
from .storage import Database, Membership, Workspace, User
from .contracts import UserInput
from .identity import Identity, Problem
from .adapters import Registry, Gateway
from .service import Platform
from .runtime import Worker
from .events import EventBus, emit


def stack():
    settings = Settings.from_env()
    db = Database(settings)
    registry = Registry(settings)
    return settings, db, registry, Platform(db, registry, settings)


def grants(registry):
    return (
        [f"tool:{name}" for name in registry.specs]
        + [f"review:{name}" for name in registry.specs]
        + ["memory:shared:read", "memory:shared:write", "events:ingest"]
    )


async def worker_loop(worker, bus=None, once=False, concurrency=1):
    from .operations import heartbeat
    from .storage import uid
    running = True
    worker_id = uid()

    def stop(*_):
        nonlocal running
        running = False

    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, stop)
    async def pulse():
        while True:
            heartbeat(worker.platform, worker_id, "running")
            await asyncio.sleep(5)

    monitor = asyncio.create_task(pulse())
    print(json.dumps({"event": "worker_started", "id": worker_id, "pid": os.getpid(),
                      "concurrency": concurrency}), flush=True)
    try:
        while running:
            results = await asyncio.gather(*(worker.tick() for _ in range(concurrency)))
            if any(results):
                print(json.dumps({"event": "worker_progress", "processed": sum(results)}), flush=True)
            if bus:
                try:
                    bus.publish()
                    bus.consume()
                except Exception as exc:
                    print(json.dumps({"event": "broker_unavailable", "error_type": type(exc).__name__}), flush=True)
            if once:
                break
            if not any(results):
                await asyncio.sleep(1)
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
        heartbeat(worker.platform, worker_id, "stopped")
        print(json.dumps({"event": "worker_stopped", "id": worker_id}), flush=True)


def demo():
    from tempfile import TemporaryDirectory
    from .api import create_app
    from fastapi.testclient import TestClient

    with TemporaryDirectory() as folder:
        settings = Settings(database_url=f"sqlite:///{Path(folder) / 'demo.db'}")
        db, registry = Database(settings), Registry(settings)
        db.migrate()
        identity = Identity(db, settings)
        operator_password = secrets.token_urlsafe(24)
        reviewer_password = secrets.token_urlsafe(24)
        identity.bootstrap(
            "demo",
            "Demo",
            UserInput(username="operator", password=operator_password, role="admin", grants=grants(registry)),
        )
        with db.session.begin() as s:
            identity.create_user(
                s,
                "demo",
                UserInput(username="reviewer", password=reviewer_password, role="reviewer", grants=grants(registry)),
            )
        app = create_app(settings, db, registry)
        with TestClient(app) as client:

            def auth(name, password):
                return {
                    "Authorization": "Bearer "
                    + client.post(
                        "/v1/auth/login", json={"username": name, "password": password, "workspace": "demo"}
                    ).json()["access_token"]
                }

            a, b = auth("operator", operator_password), auth("reviewer", reviewer_password)
            data = {
                "title": "Demonstration mission",
                "steps": [
                    {"capability": name, "input": {"objective": "Investigate a sample anomaly"}, "use_previous": i > 0}
                    for i, name in enumerate(registry.specs)
                ],
            }
            response = client.post("/v1/runs", json=data, headers={**a, "Idempotency-Key": "demo"})
            response.raise_for_status()
            run_id = response.json()["id"]
            worker = Worker(app.state.platform, Gateway(registry))
            for _ in range(20):
                asyncio.run(worker.tick())
                state = client.get("/v1/runs/" + run_id, headers=a).json()
                print(json.dumps({"run_id": run_id, "status": state["status"], "steps": state["cursor"]}))
                if state["status"] == "waiting_approval":
                    approval = client.get("/v1/approvals", headers=b).json()[0]
                    print("DEMO ONLY: authenticated test reviewer submits a scripted approval.")
                    review = client.post(
                        "/v1/approvals/" + approval["id"] + "/decision",
                        headers=b,
                        json={"allow": True, "digest": approval["action_digest"], "reason": "Scripted demonstration"},
                    )
                    review.raise_for_status()
                if state["status"] == "completed":
                    print(json.dumps(client.get("/v1/runs/" + run_id + "/evaluation", headers=a).json()))
                    break
            else:
                raise RuntimeError("demo did not complete")
        db.close()


def main():
    parser = argparse.ArgumentParser(prog="rednexus")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    boot = sub.add_parser("bootstrap")
    boot.add_argument("--workspace", default="red")
    boot.add_argument("--username", default="saeid")
    sync = sub.add_parser("sync-admin-grants", help="Local operator: add current manifest grants to an existing admin")
    sync.add_argument("--workspace", required=True)
    sync.add_argument("--username", required=True)
    member = sub.add_parser("add-membership")
    member.add_argument("--workspace", required=True)
    member.add_argument("--username", required=True)
    member.add_argument("--role", choices=["admin", "operator", "reviewer", "viewer"], default="viewer")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    work = sub.add_parser("worker")
    work.add_argument("--once", action="store_true")
    work.add_argument("--concurrency", type=int, choices=range(1, 9), default=1)
    work.add_argument("--distributed", action="store_true", help="Multiple workers; PostgreSQL required")
    sub.add_parser("doctor")
    sub.add_parser("purge-memory")
    workspace = sub.add_parser("create-workspace")
    workspace.add_argument("--workspace", required=True)
    workspace.add_argument("--username", required=True)
    secret = sub.add_parser("credential-set", help="Prompt for a token and store outside the repository")
    secret.add_argument("name", help="Uppercase credential variable, e.g. NEXUS_REDPA_TOKEN")
    redpa = sub.add_parser("redpa-login", help="Authenticate against the real RedPA OAuth form endpoint")
    redpa.add_argument("--url", default="http://127.0.0.1:8111/api/v1/auth/login")
    redpa.add_argument("--username", required=True)
    sub.add_parser("demo")
    launch_parser = sub.add_parser("launch", help="Start API and one worker together; Ctrl+C stops both")
    launch_parser.add_argument("--ecosystem", action="store_true")
    launch_parser.add_argument("--port", type=int, default=8000)
    launch_parser.add_argument("--concurrency", type=int, choices=range(1, 9), default=2)
    backup = sub.add_parser("backup")
    backup.add_argument("destination")
    restore = sub.add_parser("restore")
    restore.add_argument("source")
    args = parser.parse_args()
    if args.command == "demo":
        return demo()
    if args.command == "launch":
        from .launcher import launch
        raise SystemExit(launch(args.port, args.concurrency, args.ecosystem))
    settings, db, registry, platform = stack()
    try:
        if args.command == "migrate":
            db.migrate()
            print("Schema version 2 is ready (additive migration).")
        elif args.command == "bootstrap":
            db.migrate()
            password = os.getenv("NEXUS_BOOTSTRAP_PASSWORD") or getpass.getpass("New admin password (12+ characters): ")
            result = Identity(db, settings).bootstrap(
                args.workspace,
                args.workspace,
                UserInput(username=args.username, password=password, role="admin", grants=grants(registry)),
            )
            print(json.dumps(result))
        elif args.command == "sync-admin-grants":
            registry.refresh()
            with db.session.begin() as s:
                user = s.scalar(select(User).where(User.username == args.username))
                membership = s.get(Membership, (args.workspace, user.id)) if user else None
                if not user or not user.enabled or not membership or not membership.enabled or membership.role != "admin":
                    raise Problem(403, "an existing active administrator is required")
                names = [c.name for c in registry.specs.values() if c.mode != "disabled"
                         and (not c.workspace_binding or c.workspace_binding == args.workspace)]
                added = sorted({f"{kind}:{name}" for name in names for kind in ("tool", "review")} - set(membership.grants))
                membership.grants = sorted(set(membership.grants) | set(added))
                emit(s, args.workspace, "identity.local_admin_grants_synced",
                     {"actor": "local-operator-cli", "user": user.id, "added": added})
                print(json.dumps({"username": user.username, "added": added}))
        elif args.command == "add-membership":
            with db.session.begin() as s:
                user = s.scalar(select(User).where(User.username == args.username))
                if not user or not s.get(Workspace, args.workspace):
                    raise Problem(404, "user/workspace not found")
                if s.get(Membership, (args.workspace, user.id)):
                    raise Problem(409, "membership already exists")
                s.add(Membership(workspace=args.workspace, user_id=user.id, role=args.role, grants=[]))
                print("Membership created with no tool grants.")
        elif args.command == "serve":
            import uvicorn
            from .api import create_app
            from .telemetry import configure

            app = create_app(settings, db, registry)
            configure(app)
            uvicorn.run(app, host=args.host, port=args.port)
        elif args.command == "worker":
            from .telemetry import configure
            from .operations import WorkerLock

            configure()
            db.migrate()
            if args.distributed and not settings.database_url.startswith("postgresql"):
                raise Problem(422, "distributed workers require PostgreSQL; use --concurrency locally")
            bus = EventBus(db, settings.redis_url) if settings.redis_url else None
            with nullcontext() if args.distributed else WorkerLock(settings):
                asyncio.run(worker_loop(Worker(platform, Gateway(registry)), bus, args.once, args.concurrency))
        elif args.command == "doctor":
            from .operations import doctor
            print(json.dumps(doctor(platform), indent=2))
        elif args.command == "create-workspace":
            from .extensions import WorkspaceInput
            data = WorkspaceInput(id=args.workspace, name=args.workspace)
            with db.session.begin() as s:
                user = s.scalar(select(User).where(User.username == args.username, User.enabled.is_(True)))
                if not user:
                    raise Problem(404, "existing active user required")
                if s.get(Workspace, data.id):
                    raise Problem(409, "workspace already exists")
                s.add(Workspace(id=data.id, name=data.name))
                s.add(Membership(workspace=data.id, user_id=user.id, role="admin", grants=[]))
                emit(s, data.id, "workspace.created", {"actor": "local-operator-cli", "user": user.id})
            print("Workspace created with an administrator and no tool grants.")
        elif args.command == "purge-memory":
            from .memory import purge_expired
            print(json.dumps({"redacted_expired_records": purge_expired(db)}))
        elif args.command in ("credential-set", "redpa-login"):
            from .credentials import save_credential
            if args.command == "credential-set":
                if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,100}", args.name):
                    raise Problem(422, "credential name must be an uppercase environment variable name")
                name, value = args.name, getpass.getpass("Paste credential (hidden): ").strip()
            else:
                import httpx
                registry.check_endpoint(args.url)
                with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
                    response = client.post(args.url, data={"username": args.username,
                        "password": getpass.getpass("RedPA password (hidden): ")})
                if response.status_code != 200:
                    raise Problem(401, f"RedPA login returned HTTP {response.status_code}; verify URL and account")
                name, value = "NEXUS_REDPA_TOKEN", response.json().get("access_token", "")
            if not isinstance(value, str) or not value.strip():
                raise Problem(422, "empty credential")
            save_credential(name, value, settings.credential_file or None)
            print("Credential saved outside the repository; workers read it on the next call.")
        elif args.command in ("backup", "restore"):
            if not settings.database_url.startswith("sqlite:///"):
                raise Problem(400, "PostgreSQL: use pg_dump / pg_restore; see OPERATIONS.md")
            path = Path(settings.database_url.removeprefix("sqlite:///"))
            db.close()
            if args.command == "backup":
                destination = Path(args.destination)
                if destination.exists():
                    raise Problem(409, "backup destination already exists")
                with sqlite3.connect(path) as source, sqlite3.connect(destination) as target:
                    source.backup(target)
                print(f"Backup written: {destination}")
            else:
                source = Path(args.source)
                if path.exists():
                    raise Problem(409, "restore only into a new database path; stop services first")
                with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as original:
                    if original.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise Problem(422, "backup integrity check failed")
                    with sqlite3.connect(path) as target:
                        original.backup(target)
                print("Restored into new database.")
    except Problem as exc:
        parser.exit(1, f"{exc.message}\n")
    except ValidationError as exc:
        details = "; ".join(".".join(map(str, e["loc"])) + ": " + e["type"]
                            for e in exc.errors(include_input=False, include_url=False))
        parser.exit(1, "Invalid input: " + details + "\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
