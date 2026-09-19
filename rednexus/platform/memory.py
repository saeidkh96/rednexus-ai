"""Opt-in semantic memory with namespace authorization and immutable version vectors."""
import math
import time
from fastapi import Depends
from pydantic import Field
from sqlalchemy import select, func, delete, update
from .contracts import Contract, digest
from .storage import Memory, MemoryVector
from .identity import Problem, actor_for, consume_quota
from .adapters import bounded_request, AdapterFailure
from .credentials import credential
from .events import emit


class SemanticQuery(Contract):
    namespace: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,60}$")
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=10, ge=1, le=50)


def latest_query(workspace, namespace):
    latest = select(Memory.key, func.max(Memory.version).label("version")).where(
        Memory.workspace == workspace, Memory.namespace == namespace).group_by(Memory.key).subquery()
    return select(Memory).join(latest, (Memory.key == latest.c.key) & (Memory.version == latest.c.version)).where(
        Memory.workspace == workspace, Memory.namespace == namespace, Memory.deleted.is_(False),
        Memory.expires > time.time()).order_by(Memory.created.desc())


def unit_vector(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 4096:
        raise Problem(502, "invalid embedding dimensions")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise Problem(502, "invalid embedding values")
    norm = math.sqrt(sum(v * v for v in value))
    if not math.isfinite(norm) or norm == 0:
        raise Problem(502, "invalid embedding norm")
    return [v / norm for v in value]


class SemanticMemory:
    def __init__(self, platform, transport=None):
        self.platform, self.transport = platform, transport

    async def embed(self, texts):
        settings = self.platform.settings
        if not settings.embedding_url or not settings.embedding_model:
            raise Problem(409, "semantic memory requires an embedding endpoint and model")
        self.platform.registry.check_endpoint(settings.embedding_url)
        headers = {}
        key = credential(settings, settings.embedding_key_env)
        if key:
            headers["Authorization"] = "Bearer " + key
        try:
            response = await bounded_request("POST", settings.embedding_url,
                {"model": settings.embedding_model, "input": texts}, headers, 30, self.transport, max_bytes=1048576)
            records = sorted(response["data"], key=lambda r: r["index"])
            if [r["index"] for r in records] != list(range(len(texts))):
                raise ValueError()
            vectors = [unit_vector(r["embedding"]) for r in records]
            if len({len(v) for v in vectors}) != 1:
                raise ValueError()
            return vectors
        except (AdapterFailure, KeyError, TypeError, ValueError):
            raise Problem(502, "embedding provider failed or returned an invalid response") from None

    @property
    def model_id(self):
        settings = self.platform.settings
        return digest({"url": settings.embedding_url, "model": settings.embedding_model})

    async def index(self, actor, namespace):
        actor.require(f"memory:{namespace}:write")
        actor.require(f"memory:{namespace}:read")
        consume_quota(self.platform.db, f"embeddings:{actor.workspace}:{actor.id}", 20, 300)
        with self.platform.db.session() as s:
            rows = list(s.scalars(latest_query(actor.workspace, namespace).limit(501)))
            if len(rows) > 500:
                raise Problem(409, "namespace exceeds 500-record semantic index limit")
            pending = [r for r in rows if not (v := s.get(MemoryVector, r.id)) or v.model != self.model_id]
        # Small batches bound provider requests and response memory. Partial indexing is resumable.
        count = 0
        for offset in range(0, len(pending), 4):
            batch = pending[offset:offset + 4]
            vectors = await self.embed([r.text for r in batch])
            with self.platform.db.session.begin() as s:
                fresh = actor_for(s, actor.id, actor.workspace)
                fresh.require(f"memory:{namespace}:write")
                fresh.require(f"memory:{namespace}:read")
                for row, vector in zip(batch, vectors):
                    # Serialize against concurrent deletion/retention before writing a vector.
                    alive = s.execute(update(Memory).where(Memory.id == row.id, Memory.deleted.is_(False),
                        Memory.expires > time.time()).values(expires=Memory.expires)).rowcount
                    if not alive:
                        continue
                    stored = s.get(MemoryVector, row.id)
                    if stored:
                        stored.model, stored.vector = self.model_id, vector
                    else:
                        s.add(MemoryVector(memory_id=row.id, model=self.model_id, vector=vector))
                    count += 1
        with self.platform.db.session.begin() as s:
            emit(s, actor.workspace, "memory.indexed", {"namespace": namespace, "records": count,
                                                       "model": self.model_id, "actor": actor.id})
        return {"indexed": count, "model": self.model_id}

    async def search(self, actor, data):
        actor.require(f"memory:{data.namespace}:read")
        consume_quota(self.platform.db, f"embeddings:{actor.workspace}:{actor.id}", 20, 300)
        query = (await self.embed([data.query]))[0]
        with self.platform.db.session() as s:
            actor_for(s, actor.id, actor.workspace).require(f"memory:{data.namespace}:read")
            rows = list(s.scalars(latest_query(actor.workspace, data.namespace).limit(501)))
            if len(rows) > 500:
                raise Problem(409, "namespace exceeds 500-record semantic search limit")
            results, missing = [], 0
            for row in rows:
                stored = s.get(MemoryVector, row.id)
                if not stored or stored.model != self.model_id or len(stored.vector) != len(query):
                    missing += 1
                    continue
                score = sum(a * b for a, b in zip(query, unit_vector(stored.vector)))
                results.append({k: getattr(row, k) for k in ("id", "key", "version", "namespace", "text", "source", "author", "expires")}
                               | {"score": score})
        return {"results": sorted(results, key=lambda r: r["score"], reverse=True)[:data.limit],
                "unindexed": missing, "model": self.model_id}


def purge_expired(db):
    with db.session.begin() as s:
        ids = select(Memory.id).where((Memory.expires <= time.time()) | Memory.deleted.is_(True))
        count = s.execute(update(Memory).where(Memory.expires <= time.time(), Memory.deleted.is_(False))
                          .values(text="", source="expired", deleted=True)).rowcount
        s.execute(delete(MemoryVector).where(MemoryVector.memory_id.in_(ids)))
    return count


def install(app, platform, actor):
    engine = SemanticMemory(platform)

    @app.post("/v2/memory/index/{namespace}")
    async def index(namespace: str, current=Depends(actor)):
        return await engine.index(current, namespace)

    @app.post("/v2/memory/search")
    async def search(data: SemanticQuery, current=Depends(actor)):
        return await engine.search(current, data)
