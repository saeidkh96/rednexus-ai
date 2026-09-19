import time
from uuid import uuid4
from sqlalchemy import (
    create_engine,
    event,
    Column,
    String,
    Integer,
    BigInteger,
    Float,
    Boolean,
    JSON,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class SchemaVersion(Base):
    __tablename__ = "nx_schema_version"
    version = Column(Integer, primary_key=True)


class Workspace(Base):
    __tablename__ = "nx_workspaces"
    id = Column(String(80), primary_key=True)
    name = Column(String(120), nullable=False)


class User(Base):
    __tablename__ = "nx_users"
    id = Column(String(36), primary_key=True, default=uid)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    kind = Column(String(20), nullable=False, default="human")
    enabled = Column(Boolean, nullable=False, default=True)


class Membership(Base):
    __tablename__ = "nx_memberships"
    workspace = Column(String(80), primary_key=True)
    user_id = Column(String(36), primary_key=True)
    role = Column(String(20), nullable=False)
    grants = Column(JSON, nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True)


class SessionToken(Base):
    __tablename__ = "nx_sessions"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(String(36), nullable=False)
    workspace = Column(String(80), nullable=False)
    expires = Column(Float, nullable=False)


class LoginAttempt(Base):
    __tablename__ = "nx_login_attempts"
    key = Column(String(64), primary_key=True)
    count = Column(Integer, nullable=False, default=0)
    window = Column(Float, nullable=False)


class Run(Base):
    __tablename__ = "nx_runs"
    __table_args__ = (UniqueConstraint("workspace", "owner", "request_key"),)
    id = Column(String(36), primary_key=True, default=uid)
    workspace = Column(String(80), nullable=False, index=True)
    owner = Column(String(36), nullable=False)
    title = Column(String(200), nullable=False)
    request_key = Column(String(200), nullable=False)
    request_digest = Column(String(64), nullable=False)
    plan = Column(JSON, nullable=False)
    status = Column(String(40), nullable=False, default="queued", index=True)
    cursor = Column(Integer, nullable=False, default=0)
    outputs = Column(JSON, nullable=False, default=list)
    created = Column(Float, nullable=False, default=time.time)
    deadline = Column(Float, nullable=False)
    updated = Column(Float, nullable=False, default=time.time)
    next_attempt = Column(Float, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    tool_calls = Column(Integer, nullable=False, default=0)
    max_tool_calls = Column(Integer, nullable=False)
    cost = Column(BigInteger, nullable=False, default=0)
    budget = Column(BigInteger, nullable=False)
    lease_token = Column(String(36), nullable=True)
    lease_until = Column(Float, nullable=True)
    error = Column(String(200), nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)


class Approval(Base):
    __tablename__ = "nx_approvals"
    __table_args__ = (UniqueConstraint("run_id", "step"),)
    id = Column(String(36), primary_key=True, default=uid)
    workspace = Column(String(80), nullable=False, index=True)
    run_id = Column(String(36), nullable=False)
    step = Column(Integer, nullable=False)
    action_digest = Column(String(64), nullable=False)
    action = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    expires = Column(Float, nullable=False)
    reviewer = Column(String(36), nullable=True)
    reason = Column(Text, nullable=True)


class Event(Base):
    __tablename__ = "nx_events"
    id = Column(String(36), primary_key=True, default=uid)
    workspace = Column(String(80), nullable=False, index=True)
    run_id = Column(String(36), nullable=True, index=True)
    kind = Column(String(200), nullable=False)
    body = Column(JSON, nullable=False)
    created = Column(Float, nullable=False, default=time.time)
    published = Column(Boolean, nullable=False, default=False, index=True)


class Inbox(Base):
    __tablename__ = "nx_inbox"
    __table_args__ = (UniqueConstraint("workspace", "source", "external_id"),)
    id = Column(String(36), primary_key=True, default=uid)
    workspace = Column(String(80), nullable=False)
    source = Column(String(200), nullable=False)
    external_id = Column(String(100), nullable=False)
    digest = Column(String(64), nullable=False)
    run_ids = Column(JSON, nullable=False, default=list)


class Memory(Base):
    __tablename__ = "nx_memory"
    __table_args__ = (UniqueConstraint("workspace", "namespace", "key", "version"),)
    id = Column(String(36), primary_key=True, default=uid)
    workspace = Column(String(80), nullable=False, index=True)
    namespace = Column(String(60), nullable=False)
    key = Column(String(100), nullable=False)
    version = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    source = Column(Text, nullable=False)
    author = Column(String(36), nullable=False)
    created = Column(Float, nullable=False, default=time.time)
    expires = Column(Float, nullable=False)
    deleted = Column(Boolean, nullable=False, default=False)


class Agent(Base):
    __tablename__ = "nx_agents"
    id = Column(String(36), primary_key=True, default=uid)
    workspace = Column(String(80), nullable=False)
    owner = Column(String(36), nullable=False)
    definition = Column(JSON, nullable=False)


class Rule(Base):
    __tablename__ = "nx_rules"
    id = Column(String(36), primary_key=True, default=uid)
    workspace = Column(String(80), nullable=False)
    owner = Column(String(36), nullable=False)
    producer_id = Column(String(36), nullable=False)
    event_type = Column(String(200), nullable=False)
    source = Column(String(200), nullable=False)
    workflow = Column(JSON, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)


class BusReceipt(Base):
    __tablename__ = "nx_bus_receipts"
    id = Column(String(36), primary_key=True)
    workspace = Column(String(80), nullable=False)
    received = Column(Float, nullable=False, default=time.time)


class Database:
    def __init__(self, settings):
        settings.prepare()
        kwargs = {"pool_pre_ping": True}
        if settings.database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
            if ":memory:" in settings.database_url:
                kwargs["poolclass"] = StaticPool
        self.engine = create_engine(settings.database_url, **kwargs)
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def sqlite_config(dbapi, _):
                dbapi.execute("PRAGMA foreign_keys=ON")
                dbapi.execute("PRAGMA journal_mode=WAL")

        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def migrate(self):
        # Initial additive migration; nx_ names never overwrite legacy v0 tables.
        Base.metadata.create_all(self.engine)
        with self.session.begin() as s:
            versions = s.query(SchemaVersion).all()
            if any(v.version not in (1, 2) for v in versions):
                raise RuntimeError("unsupported schema version")
            if not any(v.version == 2 for v in versions):
                s.add(SchemaVersion(version=2))

    def health(self):
        with self.engine.connect() as c:
            c.execute(text("SELECT 1"))

    def close(self):
        self.engine.dispose()


class RateBucket(Base):
    __tablename__ = "nx_rate_buckets"
    key = Column(String(200), primary_key=True)
    count = Column(Integer, nullable=False, default=0)
    window = Column(Float, nullable=False)


class Template(Base):
    __tablename__ = "nx_templates"
    __table_args__ = (UniqueConstraint("workspace", "name", "version"),)
    id = Column(String(36), primary_key=True, default=uid)
    workspace = Column(String(80), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    version = Column(Integer, nullable=False)
    workflow = Column(JSON, nullable=False)
    owner = Column(String(36), nullable=False)
    created = Column(Float, nullable=False, default=time.time)


class CapabilityRegistration(Base):
    __tablename__ = "nx_capability_registrations"
    __table_args__ = (UniqueConstraint("name"),)
    workspace = Column(String(80), primary_key=True)
    name = Column(String(100), primary_key=True)
    spec = Column(JSON, nullable=False)
    updated = Column(Float, nullable=False, default=time.time)


class WorkerHeartbeat(Base):
    __tablename__ = "nx_worker_heartbeats"
    id = Column(String(100), primary_key=True)
    updated = Column(Float, nullable=False, default=time.time)
    status = Column(String(20), nullable=False)
    host = Column(String(200), nullable=False)
    pid = Column(Integer, nullable=False)
    credentials = Column(JSON, nullable=False, default=list)


class MemoryVector(Base):
    __tablename__ = "nx_memory_vectors"
    memory_id = Column(String(36), primary_key=True)
    model = Column(String(200), nullable=False)
    vector = Column(JSON, nullable=False)


class MissionGroup(Base):
    __tablename__ = "nx_mission_groups"
    __table_args__ = (UniqueConstraint("workspace", "owner", "request_key"),)
    id = Column(String(36), primary_key=True, default=uid)
    workspace = Column(String(80), nullable=False, index=True)
    owner = Column(String(36), nullable=False)
    request_key = Column(String(200), nullable=False)
    request_digest = Column(String(64), nullable=False)
    title = Column(String(200), nullable=False)
    runs = Column(JSON, nullable=False)
    budget = Column(BigInteger, nullable=False)
    created = Column(Float, nullable=False, default=time.time)
