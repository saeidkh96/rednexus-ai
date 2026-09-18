import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import time
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from rednexus.platform.config import Settings
from rednexus.platform.storage import Database, Run, Approval, SessionToken, Memory, User
from rednexus.platform.contracts import UserInput, CapabilitySpec, AgentInput
from rednexus.platform.identity import Identity, Problem
from rednexus.platform.adapters import Registry, Gateway, AdapterFailure
from rednexus.platform.api import create_app
from rednexus.platform.runtime import Worker
from rednexus.platform.cli import grants
from rednexus.platform.agents import Planner

PASSWORD = "Test-only-Password-123!"


@pytest.fixture
def env(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    db, registry = Database(settings), Registry(settings)
    db.migrate()
    identity = Identity(db, settings)
    for workspace, name in [("alpha", "admin"), ("beta", "outsider")]:
        identity.bootstrap(
            workspace, workspace, UserInput(username=name, password=PASSWORD, role="admin", grants=grants(registry))
        )
    with db.session.begin() as s:
        for name, role, kind in [
            ("operator", "operator", "human"),
            ("reviewer", "reviewer", "human"),
            ("viewer", "viewer", "human"),
            ("service", "reviewer", "service"),
        ]:
            identity.create_user(
                s, "alpha", UserInput(username=name, password=PASSWORD, role=role, grants=grants(registry), kind=kind)
            )
    app = create_app(settings, db, registry)
    with TestClient(app) as client:
        tokens = {}
        for name in ["admin", "operator", "reviewer", "viewer", "service", "outsider"]:
            r = client.post(
                "/v1/auth/login",
                json={"username": name, "password": PASSWORD, "workspace": "beta" if name == "outsider" else "alpha"},
            )
            assert r.status_code == 200
            tokens[name] = {"Authorization": "Bearer " + r.json()["access_token"]}
        yield dict(
            settings=settings,
            db=db,
            registry=registry,
            identity=identity,
            app=app,
            client=client,
            tokens=tokens,
            worker=Worker(app.state.platform, Gateway(registry)),
        )
    db.close()


def request(e, method, path, user="operator", **kwargs):
    headers = {**e["tokens"][user], **kwargs.pop("headers", {})}
    return e["client"].request(method, "/v1" + path, headers=headers, **kwargs)


def submit(e, capability="redpa.search", key="case", user="operator", **kwargs):
    return request(
        e,
        "POST",
        "/runs",
        user,
        headers={"Idempotency-Key": key},
        json={
            "title": "Test mission",
            "steps": [{"capability": capability, "input": {"objective": "Analyze"}}],
            **kwargs,
        },
    )


def tick(e, count=1):
    for _ in range(count):
        asyncio.run(e["worker"].tick())


def state(e, run, user="operator"):
    return request(e, "GET", "/runs/" + run, user)


def approval(e):
    return request(e, "GET", "/approvals", "reviewer").json()[0]


def review(e, a, user="reviewer", allow=True, **kwargs):
    return request(
        e,
        "POST",
        "/approvals/" + a["id"] + "/decision",
        user,
        json={"allow": allow, "digest": a["action_digest"], "reason": "Test review", **kwargs},
    )


def test_unauthenticated(env):
    for p in ["/v1/runs", "/v1/users", "/v1/capabilities", "/v1/memory?namespace=shared", "/v1/metrics"]:
        assert env["client"].get(p).status_code == 401


def test_login_wrong_workspace_and_password(env):
    assert (
        env["client"]
        .post("/v1/auth/login", json={"username": "operator", "password": PASSWORD, "workspace": "beta"})
        .status_code
        == 401
    )
    assert (
        env["client"]
        .post("/v1/auth/login", json={"username": "operator", "password": "wrong", "workspace": "alpha"})
        .status_code
        == 401
    )


def test_rate_limit(env):
    for _ in range(10):
        assert (
            env["client"]
            .post("/v1/auth/login", json={"username": "absent", "password": "wrong", "workspace": "alpha"})
            .status_code
            == 401
        )
    assert (
        env["client"]
        .post("/v1/auth/login", json={"username": "absent", "password": "wrong", "workspace": "alpha"})
        .status_code
        == 429
    )


def test_logout_and_expiry(env):
    assert request(env, "POST", "/auth/logout").status_code == 200
    assert request(env, "GET", "/me").status_code == 401
    with env["db"].session.begin() as s:
        for row in s.scalars(select(SessionToken)):
            row.expires = time.time() - 1
    assert request(env, "GET", "/me", "admin").status_code == 401


def test_passwords_hashed(env):
    with env["db"].session() as s:
        for user in s.scalars(select(User)):
            assert PASSWORD not in user.password_hash and user.password_hash.startswith("scrypt$")


def test_viewer_and_unknown_tool(env):
    assert submit(env, user="viewer").status_code == 403
    assert submit(env, capability="unknown").status_code == 422
    assert submit(env, steps=[{"capability": "redpa.search", "input": {"objective": 42}}]).status_code == 422
    assert submit(env, steps=[{"capability": "redpa.search", "use_previous": True}]).status_code == 422


def test_body_limit(env):
    assert request(env, "POST", "/runs", content="x" * 300000).status_code == 413


def test_success_idempotency_journal(env):
    run = submit(env).json()["id"]
    assert submit(env).json()["id"] == run
    assert submit(env, title="Different").status_code == 409
    tick(env, 2)
    r = state(env, run).json()
    assert r["status"] == "completed" and r["tool_calls"] == 1 and len(r["events"]) == 4
    assert all(e["workspaceid"] == "alpha" for e in r["events"])


def test_workspace_and_owner_isolation(env):
    run = submit(env).json()["id"]
    assert state(env, run, "outsider").status_code == 404
    assert request(env, "GET", "/runs", "outsider").json() == []
    assert request(env, "POST", "/runs/" + run + "/cancel", "outsider").status_code == 404
    own = submit(env, user="admin").json()["id"]
    assert state(env, own).status_code == 404


def test_approval_binding_roles_and_replay(env):
    run = submit(env, capability="redforge.propose", user="admin").json()["id"]
    tick(env)
    a = approval(env)
    assert state(env, run, "admin").json()["tool_calls"] == 0
    assert review(env, a, user="admin").status_code == 403
    assert review(env, a, user="service").status_code == 403
    assert review(env, a, user="outsider").status_code == 404
    assert review(env, a, digest="0" * 64).status_code == 409
    assert review(env, a).status_code == 200
    assert review(env, a).status_code == 409
    tick(env)
    assert state(env, run, "admin").json()["status"] == "completed"


def test_rejection(env):
    run = submit(env, capability="redforge.propose").json()["id"]
    tick(env)
    assert review(env, approval(env), allow=False).status_code == 200
    tick(env)
    r = state(env, run).json()
    assert r["status"] == "rejected" and r["tool_calls"] == 0


def test_approval_expiry(env):
    run = submit(env, capability="redforge.propose").json()["id"]
    tick(env)
    with env["db"].session.begin() as s:
        s.scalar(select(Approval)).expires = time.time() - 1
    tick(env)
    assert state(env, run).json()["status"] == "expired"


def test_revoked_grants_and_disabled_identity(env):
    run = submit(env).json()["id"]
    u = request(env, "GET", "/me").json()
    assert (
        request(
            env, "PUT", "/users/" + u["id"] + "/access", "admin", json={"role": "operator", "grants": []}
        ).status_code
        == 200
    )
    tick(env)
    assert state(env, run).json()["status"] == "blocked"
    request(
        env, "PUT", "/users/" + u["id"] + "/access", "admin", json={"role": "operator", "grants": [], "enabled": False}
    )
    assert request(env, "GET", "/me").status_code == 401


def test_review_grant(env):
    submit(env, capability="redforge.propose")
    tick(env)
    a = approval(env)
    u = request(env, "GET", "/me", "reviewer").json()
    request(env, "PUT", "/users/" + u["id"] + "/access", "admin", json={"role": "reviewer", "grants": []})
    assert review(env, a).status_code == 403


def test_contract_drift(env):
    run = submit(env).json()["id"]
    spec = env["registry"].specs["redpa.search"]
    env["registry"].specs["redpa.search"] = spec.model_copy(update={"version": "2.0.0"})
    tick(env)
    assert state(env, run).json()["status"] == "blocked"


@pytest.mark.parametrize("changes", [{"budget_microunits": 0}, {"max_tool_calls": 1}])
def test_budget(env, changes):
    run = submit(env, steps=[{"capability": "redpa.search"}, {"capability": "redpa.search"}], **changes).json()["id"]
    tick(env, 3)
    r = state(env, run).json()
    assert r["status"] == "blocked" and r["tool_calls"] <= 1


def test_cancel(env):
    run = submit(env).json()["id"]
    assert request(env, "POST", "/runs/" + run + "/cancel").status_code == 200
    tick(env)
    r = state(env, run).json()
    assert r["status"] == "cancelled" and r["tool_calls"] == 0


def test_deadline(env):
    run = submit(env).json()["id"]
    with env["db"].session.begin() as s:
        s.get(Run, run).deadline = time.time() - 1
    tick(env)
    assert state(env, run).json()["status"] == "expired"


def test_read_recovery_and_fencing(env):
    run = submit(env).json()["id"]
    claim = env["worker"].claim()
    env["worker"].prepare(*claim)
    with env["db"].session.begin() as s:
        s.get(Run, run).lease_until = time.time() - 1
    env["worker"].recover()
    env["worker"].finish(*claim, output={"stale": True})
    tick(env)
    r = state(env, run).json()
    assert r["status"] == "completed" and r["tool_calls"] == 2 and "stale" not in r["outputs"][0]


def test_effectful_crash(env):
    run = submit(env, capability="redforge.propose").json()["id"]
    tick(env)
    review(env, approval(env))
    claim = env["worker"].claim()
    env["worker"].prepare(*claim)
    with env["db"].session.begin() as s:
        s.get(Run, run).lease_until = time.time() - 1
    tick(env)
    assert state(env, run).json()["status"] == "needs_reconciliation"


def test_concurrent_claims(env):
    submit(env)
    worker2 = Worker(env["app"].state.platform, Gateway(env["registry"]))
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(lambda w: w.claim(), [env["worker"], worker2]))
    assert sum(x is not None for x in results) == 1


def test_restart(env):
    run = submit(env, capability="redforge.propose").json()["id"]
    tick(env)
    review(env, approval(env))
    from rednexus.platform.service import Platform

    db = Database(env["settings"])
    asyncio.run(Worker(Platform(db, env["registry"], env["settings"]), Gateway(env["registry"])).tick())
    db.close()
    assert state(env, run).json()["status"] == "completed"


def test_memory_scope_version_delete(env):
    data = {"namespace": "shared", "key": "fact", "text": "first fact", "source": "doc:1"}
    first = request(env, "POST", "/memory", json=data).json()
    second = request(env, "POST", "/memory", json={**data, "text": "new fact"}).json()
    assert second["version"] == 2
    result = request(env, "GET", "/memory?namespace=shared&q=fact").json()
    assert len(result) == 1 and result[0]["version"] == 2
    assert request(env, "GET", "/memory?namespace=shared", "outsider").json() == []
    assert request(env, "DELETE", "/memory/" + first["id"], "outsider").status_code == 404
    assert request(env, "DELETE", "/memory/" + first["id"]).status_code == 200
    assert request(env, "GET", "/memory?namespace=shared&history=true").json() == []
    assert request(env, "GET", "/memory?namespace=secret").status_code == 403


def test_expired_memory_no_stale_resurfacing(env):
    data = {"namespace": "shared", "key": "fact", "text": "old", "source": "doc:1"}
    request(env, "POST", "/memory", json=data)
    last = request(env, "POST", "/memory", json={**data, "text": "new"}).json()
    with env["db"].session.begin() as s:
        s.get(Memory, last["id"]).expires = time.time() - 1
    assert request(env, "GET", "/memory?namespace=shared").json() == []


def test_event_dedup_producer_binding(env):
    me = request(env, "GET", "/me").json()
    rule = {
        "event_type": "anomaly.detected",
        "source": "redpulse",
        "producer_id": me["id"],
        "workflow": {"title": "From event", "steps": [{"capability": "redpa.search"}]},
    }
    assert request(env, "POST", "/event-rules", json=rule).status_code == 201
    event = {"id": "event-1", "source": "redpulse", "type": "anomaly.detected", "data": {"severity": "high"}}
    r = request(env, "POST", "/events/ingest", json=event)
    assert r.status_code == 200 and len(r.json()["run_ids"]) == 1
    assert request(env, "POST", "/events/ingest", json=event).json()["duplicate"]
    assert request(env, "POST", "/events/ingest", json={**event, "data": {}}).status_code == 409
    assert request(env, "POST", "/events/ingest", "admin", json={**event, "id": "event-2"}).json()["run_ids"] == []


def test_replay_no_execution(env):
    run = submit(env).json()["id"]
    tick(env)
    for suffix in ["replay", "evaluation"]:
        assert request(env, "GET", "/runs/" + run + "/" + suffix).status_code == 200
    assert state(env, run).json()["tool_calls"] == 1


def test_agent_plan_no_execution(env):
    a = request(
        env, "POST", "/agents", json={"name": "Analyst", "capabilities": ["redpa.search", "redpulse.analyze"]}
    ).json()
    r = request(env, "POST", "/agents/" + a["id"] + "/plan", json={"objective": "Analyze"}).json()
    assert not r["execution_started"] and len(r["workflow"]["steps"]) == 2
    assert request(env, "GET", "/runs").json() == []
    assert request(env, "POST", "/agents/" + a["id"] + "/plan", "outsider", json={"objective": "x"}).status_code == 404


def test_model_plan_scope(env):
    p = env["app"].state.platform
    p.settings = replace(
        p.settings, model_url="https://model.test/chat", model_name="test", allowed_origins=("https://model.test",)
    )
    p.registry.settings = p.settings
    actor = env["identity"].authenticate(env["tokens"]["operator"]["Authorization"].split()[1])
    agent = p.create_agent(actor, AgentInput(name="Test", capabilities=["redpa.search"], strategy="model"))
    content = {"title": "Bad", "steps": [{"capability": "redforge.propose", "input": {}}]}
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})
    )
    with pytest.raises(Problem) as failure:
        asyncio.run(Planner(p, transport).plan(actor, agent["id"], "Analyze"))
    assert failure.value.status == 403


def test_admin_and_studio(env):
    assert request(env, "GET", "/users").status_code == 403
    me = request(env, "GET", "/me", "admin").json()
    assert (
        request(
            env, "PUT", "/users/" + me["id"] + "/access", "admin", json={"role": "viewer", "grants": []}
        ).status_code
        == 409
    )
    r = env["client"].get("/")
    assert r.status_code == 200 and "RedNexus" in r.text
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert env["client"].get("/static/app.js").status_code == 200


def test_manifest_guards():
    base = {"name": "tool.test", "project": "test", "version": "1.0.0", "description": "test"}
    with pytest.raises(ValueError):
        CapabilitySpec(**base, effect="write", approval=False)
    with pytest.raises(ValueError):
        CapabilitySpec(**base, input_schema={"$ref": "https://evil.test/schema"})
    with pytest.raises(ValueError):
        Registry(Settings(), [{**base, "mode": "http", "endpoint": "http://127.0.0.1/private"}])
    with pytest.raises(ValueError):
        Registry(
            Settings(allowed_origins=("https://safe.test",)),
            [{**base, "mode": "http", "endpoint": "https://safe.test/x?token=secret"}],
        )


@pytest.mark.parametrize(
    "status,code",
    [(302, "upstream_rejected_request"), (503, "upstream_temporarily_unavailable"), (401, "upstream_rejected_request")],
)
def test_http_errors(status, code):
    spec = CapabilitySpec(
        name="test.call",
        project="test",
        version="1.0.0",
        description="Test",
        mode="http",
        endpoint="https://safe.test/tool",
    )
    registry = Registry(Settings(allowed_origins=("https://safe.test",)), [spec.model_dump()])
    gateway = Gateway(registry, httpx.MockTransport(lambda _: httpx.Response(status, json={})))
    with pytest.raises(AdapterFailure) as error:
        asyncio.run(gateway.execute(spec, {}, dict(run_id="r", workspace="w", actor="a", idempotency_key="k")))
    assert error.value.code == code


def test_http_contract_context_and_size():
    spec = CapabilitySpec(
        name="test.call",
        project="test",
        version="1.0.0",
        description="Test",
        mode="http",
        endpoint="https://safe.test/tool",
        output_schema={"type": "object", "required": ["answer"]},
    )
    registry = Registry(Settings(allowed_origins=("https://safe.test",)), [spec.model_dump()])

    def response(req):
        assert req.headers["Idempotency-Key"] == "run:0"
        assert json.loads(req.content)["context"]["workspace"] == "alpha"
        return httpx.Response(200, json={"answer": "Transport fixture"})

    context = dict(run_id="run", workspace="alpha", actor="a", idempotency_key="run:0")
    assert asyncio.run(Gateway(registry, httpx.MockTransport(response)).execute(spec, {}, context))["answer"]
    for content in [b"x" * 70000, b"{}"]:
        with pytest.raises(AdapterFailure):
            asyncio.run(
                Gateway(registry, httpx.MockTransport(lambda _: httpx.Response(200, content=content))).execute(
                    spec, {}, context
                )
            )


def test_read_retry_limit(env):
    class FailGateway:
        async def execute(self, *args):
            raise AdapterFailure("temporary", True)

    env["worker"].gateway = FailGateway()
    run = submit(env).json()["id"]
    tick(env)
    assert state(env, run).json()["status"] == "retry_wait"
    with env["db"].session.begin() as s:
        s.get(Run, run).next_attempt = 0
    tick(env)
    assert state(env, run).json()["status"] == "failed"


def test_cancel_uncertain_effect_still_requires_reconciliation(env):
    run = submit(env, capability="redforge.propose").json()["id"]
    tick(env)
    review(env, approval(env))
    claim = env["worker"].claim()
    env["worker"].prepare(*claim)
    request(env, "POST", "/runs/" + run + "/cancel")
    with env["db"].session.begin() as s:
        s.get(Run, run).lease_until = time.time() - 1
    tick(env)
    assert state(env, run).json()["status"] == "needs_reconciliation"
    result = request(
        env,
        "POST",
        "/runs/" + run + "/reconcile",
        "admin",
        json={
            "outcome": "confirmed_succeeded",
            "evidence": "Checked domain operation ID: fixture-123",
            "output": {"confirmed": True},
        },
    )
    assert result.status_code == 200 and result.json()["status"] == "cancelled"
    assert result.json()["outputs"] == [{"confirmed": True}]
    assert (
        request(
            env,
            "POST",
            "/runs/" + run + "/reconcile",
            "admin",
            json={"outcome": "abandon", "evidence": "Repeated reconciliation attempt"},
        ).status_code
        == 409
    )


def test_reviewer_revocation_after_approval(env):
    run = submit(env, capability="redforge.propose").json()["id"]
    tick(env)
    review(env, approval(env))
    u = request(env, "GET", "/me", "reviewer").json()
    request(env, "PUT", "/users/" + u["id"] + "/access", "admin", json={"role": "reviewer", "grants": []})
    tick(env)
    assert state(env, run).json()["status"] == "blocked"


def test_previous_output_and_exact_approval_payload(env):
    run = submit(
        env, steps=[{"capability": "redpa.search"}, {"capability": "redforge.propose", "use_previous": True}]
    ).json()["id"]
    tick(env, 2)
    a = approval(env)
    assert a["action"]["input"]["previous"]["project"] == "redpa"
    review(env, a)
    tick(env)
    assert state(env, run).json()["status"] == "completed"
