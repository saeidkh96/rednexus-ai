"""Acceptance against native HTTP fixtures, real database and real worker/reviewer flow."""

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import time
import httpx
import pytest
from sqlalchemy import select
from test_platform import env as env_fixture, request, tick, state, approval, review
from test_v2 import v2
from rednexus.platform.adapters import Registry, Gateway
from rednexus.platform.contracts import digest
from rednexus.platform.drafts import DraftInput, build_draft
from rednexus.platform.runtime import Worker
from rednexus.platform.storage import Membership, Run

env = env_fixture
ROOT = Path(__file__).resolve().parents[1]


def native(e, monkeypatch, risk=0.8, fail=None):
    specs = json.loads((ROOT / "config/projects-ecosystem.json").read_text())
    for spec in specs:
        spec["workspace_binding"] = "alpha"
    settings = replace(
        e["settings"],
        allow_http=True,
        allowed_origins=tuple(f"http://127.0.0.1:{p}" for p in (8002, 8100, 8111, 8112, 8114)),
    )
    registry = Registry(settings, specs)
    platform = e["app"].state.platform
    platform.registry = registry
    # Endpoints capture registry at installation; all test-time registry objects agree.
    e["registry"].specs = registry.specs
    e["registry"].settings = settings
    with e["db"].session.begin() as s:
        for member in s.scalars(select(Membership).where(Membership.workspace == "alpha")):
            member.grants = [f"{prefix}:{spec['name']}" for spec in specs for prefix in ("tool", "review")]
    monkeypatch.setenv("NEXUS_REDPA_TOKEN", "fixture-only")
    # Use the actual configured key, without depending on its name.
    for spec in specs:
        if spec.get("credential_env"):
            monkeypatch.setenv(spec["credential_env"], "fixture-only")
    calls = []

    def handler(req):
        calls.append(req)
        if (fail == "read" and req.url.port == 8002) or (fail == "write" and req.url.port == 8100):
            raise httpx.ConnectTimeout("fixture timeout", request=req)
        if req.url.port == 8002:
            return httpx.Response(
                200,
                json={
                    "machine_id": "motor-07",
                    "failure_risk": risk,
                    "health_score": 20,
                    "confidence": 0.88,
                    "evidence": [],
                    "maintenance_priority": "high",
                },
            )
        if req.url.port == 8111:
            data = json.loads(req.content)
            assert json.loads(data["content"])["result"]["failure_risk"] == risk
            return httpx.Response(
                200,
                json={
                    "conversation_id": data["conversation_id"],
                    "user_message": {},
                    "assistant_message": {"content": "Fixture explanation"},
                    "model": "fixture",
                },
            )
        assert req.url.path == "/api/v1/world/step"
        return httpx.Response(200, json={"stepped": 1, "world": {"version": "2.0.0", "tick": 1, "population": 1500}})

    e["worker"] = Worker(platform, Gateway(registry, httpx.MockTransport(handler)))
    return calls


def queue(e, recipe="maintenance-high", **kwargs):
    draft = build_draft(DraftInput(recipe=recipe, **kwargs))["workflow"]
    r = request(e, "POST", "/runs", headers={"Idempotency-Key": "acceptance"}, json=draft)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.parametrize(
    "risk,decision,expected", [(0.1, None, "completed"), (0.8, True, "completed"), (0.8, False, "rejected")]
)
def test_native_branch_and_reviewer_gate(env, monkeypatch, risk, decision, expected):
    calls = native(env, monkeypatch, risk)
    run = queue(env)
    tick(env, 2)
    if decision is None:
        assert request(env, "GET", "/approvals", "reviewer").json() == []
        assert state(env, run).json()["outputs"][1]["skipped"] is True
    else:
        assert state(env, run).json()["status"] == "waiting_approval"
        assert len(calls) == 1
        a = approval(env)
        assert review(env, a, user="operator").status_code == 403
        assert review(env, a, allow=decision).status_code == 200
        tick(env)
    record = state(env, run).json()
    assert record["status"] == expected
    assert len(calls) == (2 if decision is True else 1)


def test_semantic_handoff_uses_actual_previous_output_after_review(env, monkeypatch):
    calls = native(env, monkeypatch)
    run = queue(env, "maintenance-explanation", conversation_id="11111111-1111-4111-8111-111111111111")
    tick(env, 2)
    a = approval(env)
    assert json.loads(a["action"]["input"]["content"])["result"]["failure_risk"] == 0.8
    assert len(calls) == 1
    review(env, a)
    tick(env)
    assert state(env, run).json()["status"] == "completed"
    assert len(calls) == 2


@pytest.mark.parametrize("failure,expected", [("read", "retry_wait"), ("write", "needs_reconciliation")])
def test_native_timeouts_do_not_repeat_uncertain_effects(env, monkeypatch, failure, expected):
    calls = native(env, monkeypatch, fail=failure)
    run = queue(env)
    tick(env, 2)
    if failure == "write":
        review(env, approval(env))
        tick(env)
    assert state(env, run).json()["status"] == expected
    before = len(calls)
    if failure == "write":
        tick(env, 3)
        assert len(calls) == before
    else:
        with env["db"].session.begin() as s:
            s.get(Run, run).next_attempt = time.time() - 1
        tick(env)
        assert state(env, run).json()["status"] == "failed"
        assert len(calls) == 2


def test_worker_recreation_preserves_approval_and_does_not_replay_read(env, monkeypatch):
    calls = native(env, monkeypatch)
    run = queue(env)
    tick(env, 2)
    old = env["worker"]
    env["worker"] = Worker(old.platform, old.gateway)
    tick(env)
    assert len(calls) == 1
    review(env, approval(env))
    tick(env)
    assert state(env, run).json()["status"] == "completed"
    assert len(calls) == 2


def test_expired_write_lease_is_fenced_after_worker_recreation(env, monkeypatch):
    calls = native(env, monkeypatch)
    run = queue(env)
    tick(env, 2)
    review(env, approval(env))
    worker = env["worker"]
    run_id, token = worker.claim()
    assert worker.prepare(run_id, token) is not None
    with env["db"].session.begin() as s:
        s.get(Run, run).lease_until = time.time() - 1
    replacement = Worker(worker.platform, worker.gateway)
    asyncio.run(replacement.tick())
    worker.finish(run_id, token, output={"late": True})
    assert state(env, run).json()["status"] == "needs_reconciliation"
    assert len(calls) == 1


def test_revoked_reviewer_is_rechecked_before_write(env, monkeypatch):
    calls = native(env, monkeypatch)
    run = queue(env)
    tick(env, 2)
    review(env, approval(env))
    with env["db"].session.begin() as s:
        reviewer = env["identity"].authenticate(env["tokens"]["reviewer"]["Authorization"][7:])
        s.get(Membership, ("alpha", reviewer.id)).grants = []
    tick(env)
    assert state(env, run).json()["status"] == "blocked"
    assert len(calls) == 1


def test_draft_permissions_and_missing_grants_are_not_auto_granted(env):
    data = {"recipe": "maintenance-high"}
    assert v2(env, "POST", "/workflow-drafts", "viewer", json=data).status_code == 403
    r = v2(env, "POST", "/workflow-drafts", json=data)
    assert r.status_code == 200, r.text
    assert r.json()["execution_started"] is False
    assert "redworld.advance" in r.json()["unavailable_capabilities"]
    assert request(env, "GET", "/runs").json() == []
    assert v2(env, "POST", "/workflow-drafts", json={"recipe": "maintenance-explanation"}).status_code == 422


def test_evidence_export_is_scoped_checksummed_and_read_only(env):
    from test_platform import submit

    run = submit(env).json()["id"]
    tick(env)
    result = v2(env, "GET", f"/runs/{run}/evidence").json()
    checksum = result.pop("sha256")
    assert digest(result) == checksum
    assert result["run"]["status"] == "completed"
    assert v2(env, "GET", f"/runs/{run}/evidence", "outsider").status_code == 404
    assert v2(env, "GET", "/mission-groups", "outsider").json() == []


@pytest.mark.parametrize('body', ['[]', 'null', '42', '"text"'])
def test_non_object_bus_envelopes_go_to_deadletters(env, body):
    from test_operations import StreamFixture
    from rednexus.platform.events import EventBus
    stream = StreamFixture()
    stream.items = [('message-1', {'event': body})]
    bus = EventBus(env['db'], '', client=stream)
    assert bus.consume() == 0
    assert 'message-1' in stream.acked
    assert stream.items[-1][1]['reason'] == 'invalid_envelope'
