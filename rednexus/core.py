"""Trusted-local reference runtime, not a network security boundary.

One process/worker only. Handlers must be side-effect-free in this release.
A crashed running step is blocked for manual reconciliation, never auto-retried.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from typing import Callable
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant: str
    grants: frozenset[str]


@dataclass(frozen=True)
class Capability:
    name: str
    project: str
    version: str
    requires_approval: bool = False


class Nexus:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.registry: dict[str, tuple[Capability, Callable]] = {}
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, tenant TEXT NOT NULL, subject TEXT NOT NULL,
          request_key TEXT NOT NULL, plan TEXT NOT NULL, status TEXT NOT NULL,
          cursor INTEGER NOT NULL DEFAULT 0, outputs TEXT NOT NULL DEFAULT '[]',
          UNIQUE(tenant, subject, request_key));
        CREATE TABLE IF NOT EXISTS approvals (
          run_id TEXT NOT NULL, step INTEGER NOT NULL, reviewer TEXT NOT NULL,
          decision INTEGER NOT NULL, PRIMARY KEY(run_id, step));
        CREATE TABLE IF NOT EXISTS events (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL,
          run_id TEXT NOT NULL, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS memory (
          tenant TEXT NOT NULL, namespace TEXT NOT NULL, key TEXT NOT NULL,
          value TEXT NOT NULL, source TEXT NOT NULL, updated TEXT NOT NULL,
          PRIMARY KEY(tenant, namespace, key));
        """)

    def close(self):
        self.db.close()

    def register(self, capability, handler):
        if capability.name in self.registry:
            raise ValueError("duplicate capability")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self.registry[capability.name] = capability, handler

    def discover(self):
        return [vars(cap) for cap, _ in self.registry.values()]

    @staticmethod
    def require(principal, grant):
        if grant not in principal.grants:
            raise PermissionError(f"missing grant: {grant}")

    def _run(self, principal, run_id, owner=True):
        row = self.db.execute("SELECT * FROM runs WHERE id=? AND tenant=?", (run_id, principal.tenant)).fetchone()
        if row is None or (owner and row["subject"] != principal.subject):
            raise PermissionError("run unavailable")
        return row

    def _event(self, row, kind, data):
        event = dict(
            specversion="1.0",
            id=str(uuid4()),
            source="/rednexus/core",
            type=f"ai.rednexus.{kind}.v1",
            time=now(),
            subject=row["id"],
            datacontenttype="application/json",
            tenantid=row["tenant"],
            correlationid=row["id"],
            data=data,
        )
        self.db.execute(
            "INSERT INTO events(tenant,run_id,body) VALUES(?,?,?)", (row["tenant"], row["id"], encode(event))
        )

    def submit(self, principal, steps, request_key):
        self.require(principal, "workflow:run")
        if not request_key or not steps or len(steps) > 20:
            raise ValueError("request key and 1..20 steps required")
        # Snapshot capability version and approval policy into immutable plan.
        plan = []
        for step in steps:
            if set(step) != {"capability", "input"} or not isinstance(step["input"], dict):
                raise ValueError("step requires capability and object input")
            cap, _ = self.registry[step["capability"]]
            self.require(principal, f"tool:{cap.name}")
            plan.append(
                dict(capability=cap.name, version=cap.version, approval=cap.requires_approval, input=step["input"])
            )
        serialized = encode(plan)
        if len(serialized.encode()) > 65536:
            raise ValueError("plan exceeds 64 KiB")
        old = self.db.execute(
            "SELECT * FROM runs WHERE tenant=? AND subject=? AND request_key=?",
            (principal.tenant, principal.subject, request_key),
        ).fetchone()
        if old:
            if old["plan"] != serialized:
                raise ValueError("idempotency key reused with different plan")
            return old["id"]
        run_id = str(uuid4())
        with self.db:
            self.db.execute(
                "INSERT INTO runs(id,tenant,subject,request_key,plan,status) VALUES(?,?,?,?,?,?)",
                (run_id, principal.tenant, principal.subject, request_key, serialized, "queued"),
            )
            self._event(self._run(principal, run_id), "workflow.submitted", {"steps": len(plan)})
        return run_id

    def inspect(self, principal, run_id):
        row = self._run(principal, run_id)
        return dict(id=row["id"], status=row["status"], cursor=row["cursor"], outputs=json.loads(row["outputs"]))

    def advance(self, principal, run_id):
        self.require(principal, "workflow:run")
        row = self._run(principal, run_id)
        if row["status"] in {"completed", "failed", "rejected", "cancelled"}:
            return self.inspect(principal, run_id)
        if row["status"] == "running":
            raise RuntimeError("uncertain step: manual reconciliation required")
        plan = json.loads(row["plan"])
        step = plan[row["cursor"]]
        self.require(principal, f"tool:{step['capability']}")
        cap, handler = self.registry[step["capability"]]
        if cap.version != step["version"] or cap.requires_approval != step["approval"]:
            raise RuntimeError("capability contract changed; submit a new workflow")
        approval = self.db.execute(
            "SELECT decision FROM approvals WHERE run_id=? AND step=?", (run_id, row["cursor"])
        ).fetchone()
        if step["approval"] and approval is None:
            if row["status"] != "waiting_approval":
                with self.db:
                    self.db.execute("UPDATE runs SET status='waiting_approval' WHERE id=?", (run_id,))
                    self._event(row, "approval.requested", {"step": row["cursor"], "capability": cap.name})
            return self.inspect(principal, run_id)
        if approval is not None and not approval["decision"]:
            raise RuntimeError("rejected approval")
        with self.db:
            self.db.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))
            self._event(row, "step.started", {"step": row["cursor"], "capability": cap.name})
        try:
            # Handlers receive copies, not database state or credentials.
            output = handler(step["input"], json.loads(row["outputs"]))
            serialized = encode(output)
            if len(serialized.encode()) > 65536:
                raise ValueError("output exceeds 64 KiB")
        except Exception as exc:
            with self.db:
                self.db.execute("UPDATE runs SET status='failed' WHERE id=?", (run_id,))
                self._event(row, "step.failed", {"step": row["cursor"], "error_type": type(exc).__name__})
            return self.inspect(principal, run_id)
        outputs = json.loads(row["outputs"]) + [output]
        cursor = row["cursor"] + 1
        status = "completed" if cursor == len(plan) else "queued"
        with self.db:
            self.db.execute(
                "UPDATE runs SET cursor=?,outputs=?,status=? WHERE id=?", (cursor, encode(outputs), status, run_id)
            )
            self._event(row, "step.completed", {"step": row["cursor"]})
            if status == "completed":
                self._event(row, "workflow.completed", {"steps": cursor})
        return self.inspect(principal, run_id)

    def review(self, reviewer, run_id, allow):
        self.require(reviewer, "approval:review")
        if type(allow) is not bool:
            raise ValueError("decision must be boolean")
        row = self._run(reviewer, run_id, owner=False)
        if row["subject"] == reviewer.subject:
            raise PermissionError("requester cannot approve own run")
        if row["status"] != "waiting_approval":
            raise ValueError("run is not waiting for approval")
        with self.db:
            self.db.execute(
                "INSERT INTO approvals VALUES(?,?,?,?)", (run_id, row["cursor"], reviewer.subject, int(allow))
            )
            self.db.execute("UPDATE runs SET status=? WHERE id=?", ("queued" if allow else "rejected", run_id))
            self._event(
                row, "approval.decided", {"step": row["cursor"], "reviewer": reviewer.subject, "allowed": allow}
            )

    def cancel(self, principal, run_id):
        self.require(principal, "workflow:run")
        row = self._run(principal, run_id)
        if row["status"] not in {"queued", "waiting_approval"}:
            raise ValueError("only queued or waiting runs can be cancelled")
        with self.db:
            self.db.execute("UPDATE runs SET status='cancelled' WHERE id=?", (run_id,))
            self._event(row, "workflow.cancelled", {})

    def events(self, principal, run_id):
        self._run(principal, run_id)
        return [
            json.loads(r[0])
            for r in self.db.execute(
                "SELECT body FROM events WHERE run_id=? AND tenant=? ORDER BY seq", (run_id, principal.tenant)
            )
        ]

    def remember(self, principal, namespace, key, value, source):
        self.require(principal, f"memory:{namespace}:write")
        if not source:
            raise ValueError("memory requires provenance")
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO memory VALUES(?,?,?,?,?,?)",
                (principal.tenant, namespace, key, encode(value), source, now()),
            )

    def recall(self, principal, namespace, key):
        self.require(principal, f"memory:{namespace}:read")
        row = self.db.execute(
            "SELECT value,source,updated FROM memory WHERE tenant=? AND namespace=? AND key=?",
            (principal.tenant, namespace, key),
        ).fetchone()
        return (
            None if row is None else dict(value=json.loads(row["value"]), source=row["source"], updated=row["updated"])
        )
