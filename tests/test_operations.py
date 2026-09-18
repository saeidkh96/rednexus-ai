import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sqlite3
import threading
import time
import httpx
import pytest
from sqlalchemy import select, func
from rednexus.platform.adapters import Registry, Gateway
from rednexus.platform.config import Settings
from rednexus.platform.contracts import CapabilitySpec
from rednexus.platform.storage import Database, Event, BusReceipt
from rednexus.platform.events import EventBus, emit
from rednexus.platform.identity import consume_quota, Problem


def test_real_http_transport_to_local_contract_fixture():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps({"result": "local contract fixture", "simulated": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    except OSError as exc:
        pytest.skip(f"Local listening socket unavailable: {exc}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    spec = CapabilitySpec(
        name="fixture.test",
        project="fixture",
        version="1.0.0",
        description="TCP fixture",
        mode="http",
        endpoint=origin + "/execute",
    )
    registry = Registry(Settings(allowed_origins=(origin,), allow_http=True), [spec.model_dump()])
    try:
        result = asyncio.run(
            Gateway(registry).execute(
                spec, {"question": "test"}, dict(run_id="r", workspace="w", actor="a", idempotency_key="r:0")
            )
        )
        assert result["result"] == "local contract fixture"
        assert received[0]["input"] == {"question": "test"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_absolute_http_timeout():
    from rednexus.platform.adapters import bounded_post, AdapterFailure

    async def slow(request):
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={})

    started = time.monotonic()
    with pytest.raises(AdapterFailure, match="timeout"):
        asyncio.run(bounded_post("https://fixture.test", {}, {}, 0.01, httpx.MockTransport(slow)))
    assert time.monotonic() - started < 1


class StreamFixture:
    def __init__(self):
        self.items = []
        self.acked = []
        self.fail = False

    def xadd(self, stream, value):
        self.items.append((f"{len(self.items)}-0", value))
        if self.fail:
            raise ConnectionError("simulated disconnect after publish")

    def xgroup_create(self, *args, **kwargs):
        pass

    def xautoclaim(self, *args, **kwargs):
        return ["0-0", [], []]

    def xreadgroup(self, *args, **kwargs):
        return [("stream", [x for x in self.items if x[0] not in self.acked])]

    def xack(self, stream, group, mid):
        self.acked.append(mid)


def test_outbox_duplicate_after_crash_is_deduplicated(tmp_path):
    db = Database(Settings(database_url=f"sqlite:///{tmp_path / 'bus.db'}"))
    db.migrate()
    fake = StreamFixture()
    bus = EventBus(db, "", client=fake)
    with db.session.begin() as s:
        emit(s, "a", "test", {})
    fake.fail = True
    with pytest.raises(ConnectionError):
        bus.publish()
    with db.session() as s:
        assert not s.scalar(select(Event)).published
    fake.fail = False
    assert bus.publish() == 1
    assert bus.consume() == 2
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(BusReceipt)) == 1
    db.close()


def test_sqlite_backup_restore(tmp_path):
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    target = tmp_path / "restore.db"
    db = Database(Settings(database_url=f"sqlite:///{source}"))
    db.migrate()
    with db.session.begin() as s:
        emit(s, "a", "backup_test", {"data": "survives"})
    with sqlite3.connect(source) as original, sqlite3.connect(backup) as dest:
        original.backup(dest)
    db.close()
    with sqlite3.connect(backup) as original, sqlite3.connect(target) as dest:
        original.backup(dest)
    restored = Database(Settings(database_url=f"sqlite:///{target}"))
    with restored.session() as s:
        assert s.scalar(select(Event)).body["data"]["data"] == "survives"
    restored.close()


def test_model_request_quota(tmp_path):
    db = Database(Settings(database_url=f"sqlite:///{tmp_path / 'quota.db'}"))
    db.migrate()
    for _ in range(5):
        consume_quota(db, "actor-model", 5, 300)
    with pytest.raises(Problem) as failure:
        consume_quota(db, "actor-model", 5, 300)
    assert failure.value.status == 429
    db.close()
