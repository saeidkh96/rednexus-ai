"""Real service gates are explicit and skipped when their test URLs are absent."""

import asyncio
import os
from uuid import uuid4
import pytest
from rednexus.platform.config import Settings
from rednexus.platform.storage import Database, Event, BusReceipt
from rednexus.platform.adapters import Registry, Gateway
from rednexus.platform.identity import Identity
from rednexus.platform.contracts import UserInput, LoginInput, RunInput
from rednexus.platform.cli import grants
from rednexus.platform.service import Platform
from rednexus.platform.runtime import Worker
from rednexus.platform.events import EventBus, emit
from sqlalchemy import select, func


@pytest.mark.integration
def test_real_postgresql_migration_and_worker():
    url = os.getenv("NEXUS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("NEXUS_TEST_POSTGRES_URL is not configured")
    settings = Settings(database_url=url)
    db = Database(settings)
    db.migrate()
    registry = Registry(settings)
    unique = "test-" + uuid4().hex[:12]
    identity = Identity(db, settings)
    password = "CI-only-password-123!"
    identity.bootstrap(
        unique, unique, UserInput(username=unique, password=password, role="admin", grants=grants(registry))
    )
    auth = identity.login(LoginInput(username=unique, password=password, workspace=unique), "local")
    actor = identity.authenticate(auth["access_token"])
    platform = Platform(db, registry, settings)
    run = platform.submit(actor, RunInput(title="PostgreSQL gate", steps=[{"capability": "redpa.search"}]), "1")
    asyncio.run(Worker(platform, Gateway(registry)).tick())
    assert platform.inspect(actor, run["id"])["status"] == "completed"
    db.close()


@pytest.mark.integration
def test_real_redis_stream_outbox_receipts(tmp_path):
    url = os.getenv("NEXUS_TEST_REDIS_URL")
    if not url:
        pytest.skip("NEXUS_TEST_REDIS_URL is not configured")
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'redis.db'}")
    db = Database(settings)
    db.migrate()
    bus = EventBus(db, url)
    unique = uuid4().hex
    bus.stream = "nexus:test:" + unique
    bus.group = "test-" + unique
    try:
        with db.session.begin() as s:
            emit(s, "test", "example", {"fixture": True})
        assert bus.publish() == 1
        assert bus.consume() == 1
        assert bus.publish() == 0
        with db.session() as s:
            assert s.scalar(select(func.count()).select_from(BusReceipt)) == 1
            assert s.scalar(select(Event)).published
    finally:
        bus.client.delete(bus.stream)
        db.close()
