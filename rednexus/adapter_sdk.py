"""Build an independent HTTP adapter; no project source is imported into Nexus."""
import asyncio
import inspect
import json
import secrets
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import Field
from .platform.contracts import Contract, CapabilitySpec, digest, canonical
from .platform.adapters import validate_payload
from .platform.identity import Problem


class ExecutionEnvelope(Contract):
    contract_version: str
    capability: str
    input: dict = Field(default_factory=dict)
    context: dict


def adapter_app(specs, handlers, token, receipt_database):
    """Handlers accept (input, context). For writes, use service transactions/outboxes.

    A started receipt is never re-executed, including after a crash. The operator
    must reconcile uncertain writes. This does not claim exactly-once side effects.
    """
    if not token or len(token) < 24:
        raise ValueError("adapter token must contain at least 24 characters")
    catalog = {s.name: s for s in (CapabilitySpec.model_validate(item) for item in specs)}
    if any(not s.workspace_binding or s.protocol != "nexus" or s.mode != "http" for s in catalog.values()):
        raise ValueError("SDK adapters require workspace binding, HTTP mode and nexus protocol")
    if set(catalog) != set(handlers):
        raise ValueError("handlers must match capability names")
    path = Path(receipt_database)
    path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect():
        conn = sqlite3.connect(path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS receipts (key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, "
                   "status TEXT NOT NULL, output TEXT)")
    app = FastAPI(title="RedNexus project adapter", version="2.0.0-rc.1")
    from .platform.api import RequestLimits
    app.add_middleware(RequestLimits)

    @app.exception_handler(Problem)
    async def problem(_, exc):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.get("/health")
    def health():
        with connect() as db:
            db.execute("SELECT 1")
        return {"status": "ok", "capabilities": len(catalog)}

    @app.post("/execute")
    async def execute(data: ExecutionEnvelope, authorization: str = Header(default=""),
                      idempotency_key: str = Header(...)):
        if not secrets.compare_digest(authorization, "Bearer " + token):
            raise Problem(401, "invalid adapter credential")
        spec = catalog.get(data.capability)
        if not spec or spec.version != data.contract_version:
            raise Problem(409, "unknown capability or version")
        if data.context.get("workspace") != spec.workspace_binding:
            raise Problem(403, "workspace mismatch")
        if not 1 <= len(idempotency_key) <= 200 or data.context.get("idempotency_key") != idempotency_key:
            raise Problem(422, "invalid idempotency key")
        deadline = data.context.get("deadline")
        if type(deadline) not in (int, float) or deadline <= time.time():
            raise Problem(422, "expired execution deadline")
        validate_payload(spec.input_schema, data.input)
        # Deadline may differ after retry; identity, capability and input may not.
        fingerprint = digest({"capability": data.capability, "version": data.contract_version,
                              "input": data.input, "workspace": data.context["workspace"],
                              "actor": data.context.get("actor"), "run_id": data.context.get("run_id")})
        key = digest({"workspace": spec.workspace_binding, "key": idempotency_key})
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT fingerprint,status,output FROM receipts WHERE key=?", (key,)).fetchone()
            if old:
                if old[0] != fingerprint:
                    raise Problem(409, "idempotency conflict")
                if old[1] == "completed":
                    return json.loads(old[2])
                raise Problem(409, "execution uncertain; reconciliation required")
            db.execute("INSERT INTO receipts VALUES (?,?,?,NULL)", (key, fingerprint, "started"))
        try:
            handler = handlers[spec.name]
            if inspect.iscoroutinefunction(handler):
                result = await handler(data.input, data.context)
            else:
                result = await asyncio.to_thread(handler, data.input, data.context)
            validate_payload(spec.output_schema, result)
            with connect() as db:
                db.execute("UPDATE receipts SET status='completed',output=? WHERE key=?", (canonical(result), key))
            return result
        except Exception:
            # Never include handler error strings, inputs or credentials in a response.
            raise Problem(502, "adapter execution uncertain; inspect service evidence") from None

    return app
