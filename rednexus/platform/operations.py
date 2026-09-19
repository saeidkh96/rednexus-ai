import hashlib
import os
import socket
import tempfile
import time
from pathlib import Path
from .storage import WorkerHeartbeat
from .identity import Problem
from .credentials import credential


class WorkerLock:
    """One default CLI worker per local database; OS releases the lock on crashes."""
    def __init__(self, settings):
        key = settings.database_url
        if key.startswith("sqlite:///"):
            key = str(Path(key.removeprefix("sqlite:///")).resolve())
        name = hashlib.sha256(key.encode()).hexdigest()[:24]
        self.path = Path(tempfile.gettempdir()) / ("rednexus-worker-" + name + ".lock")
        self.file = None

    def __enter__(self):
        self.file = open(self.path, "a+b")
        if self.path.stat().st_size == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise Problem(409, "a local worker already owns this database; keep its terminal open") from None
        return self

    def __exit__(self, *_):
        if os.name == "nt":
            import msvcrt
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        self.file.close()


def heartbeat(platform, worker_id, status):
    with platform.db.session.begin() as s:
        row = s.get(WorkerHeartbeat, worker_id)
        if not row:
            row = WorkerHeartbeat(id=worker_id, host=socket.gethostname(), pid=os.getpid())
            s.add(row)
        row.updated, row.status = time.time(), status


def doctor(platform):
    platform.db.health()
    platform.registry.refresh()
    items = []
    for spec in platform.registry.specs.values():
        try:
            ready = not spec.credential_env or bool(credential(platform.settings, spec.credential_env))
        except (OSError, ValueError):
            ready = False
        items.append({"name": spec.name, "mode": spec.mode, "credential_ready": ready,
                      "health_configured": bool(spec.health_endpoint)})
    return {"database": "ok", "capabilities": items, "credentials_in_output": False}
