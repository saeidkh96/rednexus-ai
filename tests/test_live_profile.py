import asyncio
import json
from pathlib import Path
import httpx
import pytest
from rednexus.platform.adapters import Registry, Gateway, AdapterFailure
from rednexus.platform.config import Settings
from rednexus.platform.contracts import RunInput
from rednexus.platform.preflight import inspect
from rednexus.platform.workflows import condition_matches, input_for

ROOT = Path(__file__).resolve().parents[1]


def settings():
    return Settings(manifest_path=str(ROOT / 'config/projects-ecosystem.json'), allow_http=True,
                    allowed_origins=tuple(f'http://127.0.0.1:{p}' for p in (8100, 8111, 8112, 8002, 8114)))


@pytest.mark.parametrize('risk,expected', [(0.7, True), (0.2, False)])
def test_live_adapter_chain_and_risk_condition(risk, expected):
    plan = RunInput.model_validate(json.loads((ROOT / 'examples/live-maintenance.json').read_text()))
    registry = Registry(settings())
    calls = []

    def upstream(req):
        calls.append(req)
        if req.url.port == 8002:
            assert json.loads(req.content)['machine_id'] == 'motor-07'
            return httpx.Response(200, json={'machine_id': 'motor-07', 'failure_risk': risk,
                'health_score': 30, 'confidence': 0.8, 'evidence': [], 'maintenance_priority': 'high'})
        assert req.method == 'POST' and req.url.path == '/api/v1/world/step'
        assert req.url.params['steps'] == '1'
        return httpx.Response(200, json={'stepped': 1,
            'world': {'version': '2.0.0', 'tick': 1, 'population': 50}})

    gateway = Gateway(registry, httpx.MockTransport(upstream))
    context = {'workspace': 'red', 'run_id': 'test', 'actor': 'test', 'idempotency_key': 'test:0'}
    first = plan.steps[0]
    result = asyncio.run(gateway.execute(registry.get(first.capability), first.input, context))
    second = plan.steps[1].model_dump()
    assert condition_matches(second['when'], [result]) is expected
    spec = registry.get(second['capability'])
    assert spec.effect == 'write' and spec.approval is True and spec.max_attempts == 1
    if expected:
        # Gateway mapping only; runtime approval enforcement is covered in test_v2.
        output = asyncio.run(gateway.execute(spec, input_for(second, [result]), context))
        assert output['orchestration_context']['previous'] == result
        assert output['orchestration_context']['applied_to_world_model'] is False
        assert output['simulated'] is False
    assert len(calls) == (2 if expected else 1)


def test_preflight_failure_and_read_only():
    def upstream(req):
        assert req.method == 'GET'
        return httpx.Response(503)
    result = inspect(settings(), httpx.MockTransport(upstream))
    assert result['ready'] is False and len(result['errors']) == 2


def test_preflight_success():
    def upstream(req):
        return httpx.Response(200, json={'status': 'healthy'} if req.url.port == 8002 else
                              {'version': '2.0.0', 'tick': 0, 'population': 50})
    assert inspect(settings(), httpx.MockTransport(upstream))['ready'] is True


def test_live_timeout_does_not_fall_back_to_demo():
    def upstream(req):
        raise httpx.ConnectTimeout('unavailable', request=req)
    registry = Registry(settings())
    with pytest.raises(AdapterFailure):
        asyncio.run(Gateway(registry, httpx.MockTransport(upstream)).execute(
            registry.get('redworld.snapshot'), {},
            {'workspace': 'red', 'run_id': 'r', 'actor': 'a', 'idempotency_key': 'r:0'}))
