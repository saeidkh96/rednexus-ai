import asyncio
from dataclasses import replace
import json
import time
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from test_platform import env as _environment, request, submit, tick, state, approval, review
from rednexus.platform.contracts import RunInput, MemoryInput, CapabilitySpec
from rednexus.platform.storage import Memory, MemoryVector, Membership, Run, SchemaVersion
from rednexus.platform.identity import Problem
from rednexus.platform.workflows import pointer
from rednexus.platform.memory import SemanticMemory, SemanticQuery, purge_expired
from rednexus.platform.operations import WorkerLock
from rednexus.platform.credentials import save_credential, credential
from rednexus.adapter_sdk import adapter_app

env = _environment


def v2(e, method, path, user="operator", **kwargs):
    return e["client"].request(method, "/v2" + path,
        headers={**e["tokens"][user], **kwargs.pop("headers", {})}, **kwargs)


def actor(e, user="operator"):
    return e["identity"].authenticate(e["tokens"][user]["Authorization"].removeprefix("Bearer "))


def workflow(**kw):
    return {"title": "Connected", "steps": [{"capability": "redpa.search", "input": {"objective": "hello"}}], **kw}


def test_bindings_resolve_before_exact_human_approval(env):
    r = submit(env, steps=[{"capability": "redpa.search", "input": {"objective": "A"}},
        {"capability": "redforge.propose", "bindings": {"objective": {"step": 0, "pointer": "/received/objective"}}}])
    assert r.status_code == 201, r.text
    tick(env, 2)
    a = approval(env)
    assert a["action"]["input"] == {"objective": "A"}
    assert review(env, a).status_code == 200
    tick(env)
    assert state(env, r.json()["id"]).json()["status"] == "completed"


def test_missing_binding_fails_without_tool_call(env):
    r = submit(env, steps=[{"capability": "redpa.search"},
        {"capability": "redpa.search", "bindings": {"objective": {"step": 0, "pointer": "/absent"}}}])
    tick(env, 2)
    record = state(env, r.json()["id"]).json()
    assert record["status"] == "blocked"
    assert record["error"] == "binding_source_missing"
    assert record["tool_calls"] == 1


def test_condition_skips_effect_without_approval_or_cost(env):
    r = submit(env, steps=[{"capability": "redpa.search"}, {"capability": "redforge.propose",
        "when": {"step": 0, "pointer": "/project", "op": "eq", "value": "other"}}])
    tick(env, 2)
    record = state(env, r.json()["id"]).json()
    assert record["status"] == "completed"
    assert record["outputs"][1]["skipped"] is True
    assert record["tool_calls"] == 1
    assert request(env, "GET", "/approvals", "reviewer").json() == []


@pytest.mark.parametrize("ref", [0, 1, 19])
def test_forward_and_self_references_rejected(ref):
    with pytest.raises(ValueError):
        RunInput.model_validate(workflow(steps=[{"capability": "redpa.search",
            "bindings": {"objective": {"step": ref}}}]))


def test_json_pointer_escaping_and_array():
    assert pointer({"a/b": {"~": [42]}}, "/a~1b/~0/0") == 42
    with pytest.raises(KeyError):
        pointer([1], "/01")


def test_templates_version_scope_and_revocation(env):
    data = {"name": "test", "workflow": workflow()}
    one = v2(env, "POST", "/templates", json=data).json()
    two = v2(env, "POST", "/templates", json=data).json()
    assert one["version"] == 1 and two["version"] == 2
    assert v2(env, "GET", "/templates", "outsider").json() == []
    with env["db"].session.begin() as s:
        s.get(Membership, ("alpha", actor(env).id)).grants = []
    r = v2(env, "POST", f'/templates/{one["id"]}/runs', headers={"Idempotency-Key": "template"})
    assert r.status_code == 403


def test_registration_persists_and_requires_version_and_scope(env):
    spec = {"name": "rednew.read", "project": "rednew", "version": "1.0.0", "description": "test",
            "mode": "demo", "workspace_binding": "alpha"}
    assert v2(env, "POST", "/capabilities", "operator", json=spec).status_code == 403
    assert v2(env, "POST", "/capabilities", "admin", json=spec).status_code == 201
    assert v2(env, "POST", "/capabilities", "admin", json={**spec, "description": "changed"}).status_code == 409
    assert v2(env, "POST", "/capabilities", "outsider", json={**spec, "workspace_binding": "beta"}).status_code == 409
    from rednexus.platform.adapters import Registry
    fresh = Registry(env["settings"])
    fresh.db = env["db"]
    fresh.refresh()
    assert fresh.get("rednew.read").workspace_binding == "alpha"
    assert submit(env, capability="rednew.read", user="admin").status_code == 403


def test_discovery_distinguishes_demo_from_live(env):
    result = v2(env, "GET", "/discovery").json()
    assert result and all(x["status"] == "demo" for x in result)


def make_agent(e):
    response = request(e, "POST", "/agents", json={"name": "Research", "capabilities": ["redpa.search"]})
    return response.json()["id"]


def test_parallel_group_budget_idempotency_and_isolation(env):
    agent_id = make_agent(env)
    data = {"title": "Parallel", "budget_microunits": 200,
        "assignments": [{"agent_id": agent_id, "workflow": workflow(budget_microunits=100)} for _ in range(2)]}
    response = v2(env, "POST", "/mission-groups", headers={"Idempotency-Key": "team"}, json=data)
    assert response.status_code == 201, response.text
    assert response.json() == v2(env, "POST", "/mission-groups", headers={"Idempotency-Key": "team"}, json=data).json()
    async def execute():
        from rednexus.platform.adapters import Gateway
        started = []
        both = asyncio.Event()
        class SlowGateway(Gateway):
            async def execute(self, spec, payload, context):
                started.append(context["run_id"])
                if len(started) == 2:
                    both.set()
                await asyncio.wait_for(both.wait(), 2)
                return await super().execute(spec, payload, context)
        env["worker"].gateway = SlowGateway(env["registry"])
        await asyncio.gather(env["worker"].tick(), env["worker"].tick())
        assert len(set(started)) == 2
    asyncio.run(execute())
    group_id = response.json()["id"]
    result = v2(env, "GET", "/mission-groups/" + group_id)
    assert result.json()["completed"] is True
    assert v2(env, "GET", "/mission-groups/" + group_id, "outsider").status_code == 404
    data["budget_microunits"] = 1
    assert v2(env, "POST", "/mission-groups", headers={"Idempotency-Key": "bad"}, json=data).status_code == 422


def test_group_agent_scope_is_enforced(env):
    data = {"title": "Denied", "assignments": [{"agent_id": make_agent(env),
        "workflow": workflow(steps=[{"capability": "redforge.propose"}])}]}
    assert v2(env, "POST", "/mission-groups", headers={"Idempotency-Key": "bad"}, json=data).status_code == 403
    assert request(env, "GET", "/runs").json() == []


def test_operations_and_dead_letters_are_scoped(env):
    r = submit(env)
    with env["db"].session.begin() as s:
        s.get(Run, r.json()["id"]).status = "failed"
    assert v2(env, "GET", "/operations").status_code == 403
    assert v2(env, "GET", "/operations", "admin").json()["runs"]["failed"] == 1
    assert v2(env, "GET", "/dead-letters", "outsider").json() == []
    retried = v2(env, "POST", f'/runs/{r.json()["id"]}/retry-read', headers={"Idempotency-Key": "retry"})
    assert retried.status_code == 201
    assert retried.json()["id"] != r.json()["id"]


def test_uncertain_writes_cannot_auto_retry(env):
    r = submit(env, capability="redforge.propose")
    with env["db"].session.begin() as s:
        s.get(Run, r.json()["id"]).status = "needs_reconciliation"
    assert v2(env, "POST", f'/runs/{r.json()["id"]}/retry-read', headers={"Idempotency-Key": "retry"}).status_code == 409


def test_invalid_password_response_does_not_echo_secret(env):
    response = request(env, "POST", "/users", "admin", json={"username": "test", "password": "SECRET", "role": "viewer"})
    assert response.status_code == 422
    assert "SECRET" not in response.text


def test_platform_grants_cannot_be_self_assigned(env):
    response = request(env, "POST", "/users", "admin", json={"username": "test", "password": "Long-test-only-123",
        "role": "admin", "grants": ["platform:workspaces:create"]})
    assert response.status_code == 403
    assert v2(env, "POST", "/workspaces", "admin", json={"id": "third", "name": "Third"}).status_code == 403


def test_local_worker_lock_releases(env):
    with WorkerLock(env["settings"]):
        with pytest.raises(Problem):
            with WorkerLock(env["settings"]):
                pass
    with WorkerLock(env["settings"]):
        pass


def test_credentials_file_and_env_precedence(env, tmp_path, monkeypatch):
    path = tmp_path / "secrets.json"
    save_credential("NEXUS_REDPA_TOKEN", "test-token", path)
    settings = replace(env["settings"], credential_file=str(path))
    assert credential(settings, "NEXUS_REDPA_TOKEN") == "test-token"
    monkeypatch.setenv("NEXUS_REDPA_TOKEN", "override")
    assert credential(settings, "NEXUS_REDPA_TOKEN") == "override"


def test_semantic_memory_versions_and_redaction(env):
    platform = env["app"].state.platform
    platform.settings = replace(platform.settings, embedding_url="https://emb.test/v1/embeddings", embedding_model="test")
    platform.registry.settings = replace(platform.settings, allowed_origins=("https://emb.test",))
    calls = []
    def provider(request):
        inputs = json.loads(request.content)["input"]
        calls.extend(inputs)
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [1.0, 0.0] if "motor" in t else [0.0, 1.0]}
                                                   for i, t in enumerate(inputs)]})
    engine = SemanticMemory(platform, httpx.MockTransport(provider))
    current = actor(env)
    first = platform.remember(current, MemoryInput(namespace="shared", key="motor", text="motor bearing", source="run:1"))
    platform.remember(current, MemoryInput(namespace="shared", key="other", text="garden", source="run:2"))
    assert asyncio.run(engine.index(current, "shared"))["indexed"] == 2
    result = asyncio.run(engine.search(current, SemanticQuery(namespace="shared", query="motor")))
    assert result["results"][0]["key"] == "motor"
    platform.remember(current, MemoryInput(namespace="shared", key="motor", text="new motor", source="run:3"))
    result = asyncio.run(engine.search(current, SemanticQuery(namespace="shared", query="motor")))
    assert result["unindexed"] == 1
    assert all(x["key"] != "motor" for x in result["results"])
    platform.delete_memory(current, first["id"])
    with env["db"].session() as s:
        assert s.get(MemoryVector, first["id"]) is None
    previous = len(calls)
    with pytest.raises(Problem):
        asyncio.run(engine.search(current, SemanticQuery(namespace="private", query="motor")))
    assert len(calls) == previous


def test_memory_retention_redacts_vectors(env):
    platform = env["app"].state.platform
    row = platform.remember(actor(env), MemoryInput(namespace="shared", key="old", text="private", source="run:1"))
    with env["db"].session.begin() as s:
        s.execute(update(Memory).where(Memory.id == row["id"]).values(expires=time.time()-1))
        s.add(MemoryVector(memory_id=row["id"], model="test", vector=[1]))
    assert purge_expired(env["db"]) == 1
    with env["db"].session() as s:
        assert s.get(Memory, row["id"]).text == ""
        assert s.get(MemoryVector, row["id"]) is None


def test_additive_schema_upgrade_is_repeatable(env):
    with env["db"].session.begin() as s:
        for row in s.scalars(select(SchemaVersion)):
            s.delete(row)
        s.add(SchemaVersion(version=1))
    env["db"].migrate()
    env["db"].migrate()
    with env["db"].session() as s:
        assert {x.version for x in s.scalars(select(SchemaVersion))} == {1, 2}


def test_adapter_receipts_prevent_write_replay_and_scope_leak(tmp_path):
    spec = CapabilitySpec(name="example.write", project="example", version="1.0.0", description="test",
                          workspace_binding="alpha", effect="write", approval=True, mode="http",
                          endpoint="https://example.test/execute")
    calls = []
    def handle(payload, context):
        calls.append(payload)
        return {"ok": True}
    secret = "test-only-token-" + "x" * 24
    app = adapter_app([spec.model_dump()], {spec.name: handle}, secret, tmp_path / "receipts.db")
    payload = {"contract_version": "1.0.0", "capability": spec.name, "input": {},
               "context": {"workspace": "alpha", "idempotency_key": "one", "deadline": time.time()+60}}
    headers = {"Authorization": "Bearer " + secret, "Idempotency-Key": "one"}
    with TestClient(app) as client:
        assert client.post("/execute", json=payload, headers=headers).status_code == 200
        assert client.post("/execute", json=payload, headers=headers).status_code == 200
        assert len(calls) == 1
        payload["input"] = {"different": True}
        assert client.post("/execute", json=payload, headers=headers).status_code == 409
        payload["context"]["workspace"] = "beta"
        assert client.post("/execute", json=payload, headers=headers).status_code == 403


def test_sdk_uncertain_write_is_not_replayed_after_restart(tmp_path):
    spec = CapabilitySpec(name="example.write", project="example", version="1.0.0", description="test",
        workspace_binding="alpha", effect="write", approval=True, mode="http", endpoint="https://example.test/execute")
    calls = []
    def fail(payload, context):
        calls.append(1)
        raise RuntimeError("private provider detail")
    token = "test-only-long-adapter-secret-123"
    path = tmp_path / "receipts.db"
    envelope = {"contract_version": "1.0.0", "capability": spec.name, "input": {},
        "context": {"workspace": "alpha", "idempotency_key": "key", "deadline": time.time()+60}}
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": "key"}
    for expected in (502, 409):
        with TestClient(adapter_app([spec.model_dump()], {spec.name: fail}, token, path)) as client:
            response = client.post("/execute", json=envelope, headers=headers)
            assert response.status_code == expected
            assert "private provider detail" not in response.text
    assert len(calls) == 1


def test_team_planning_proposes_without_execution(env):
    agent = make_agent(env)
    response = v2(env, "POST", "/agent-teams/plan", json={"title": "Team plan", "objectives": [
        {"agent_id": agent, "objective": "Inspect sample"}]})
    assert response.status_code == 200, response.text
    assert response.json()["execution_started"] is False
    assert response.json()["group"]["assignments"][0]["agent_id"] == agent
    assert request(env, "GET", "/runs").json() == []
