import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
import pytest
from rednexus.platform.adapters import AdapterFailure, Gateway, Registry
from rednexus.platform.config import Settings
from rednexus.platform.contracts import CapabilitySpec
from rednexus.platform.identity import Problem

ROOT = Path(__file__).resolve().parents[1]
SPECS = json.loads((ROOT / 'config/projects-ecosystem.json').read_text())
INPUTS = json.loads((ROOT / 'config/ecosystem-inputs.json').read_text())
CONTEXT = dict(workspace='red', run_id='run', actor='operator', idempotency_key='run:0')


def registry(spec):
    origin = str(httpx.URL(spec['endpoint']).copy_with(path='')).rstrip('/')
    return Registry(Settings(allow_http=True, allowed_origins=(origin,)), [spec])


@pytest.mark.parametrize('raw', [s for s in SPECS if not s['protocol'].startswith('redworld_')])
def test_native_bindings_are_mandatory(raw):
    for changes in [{'workspace_binding': None}, {'endpoint': raw['endpoint'] + '/other'}]:
        with pytest.raises(ValueError):
            CapabilitySpec.model_validate({**raw, **changes})
    reg = registry(raw)
    with pytest.raises(AdapterFailure, match='workspace_binding'):
        asyncio.run(Gateway(reg).execute(reg.get(raw['name']), INPUTS[raw['name']], {**CONTEXT, 'workspace': 'other'}))
    if raw['effect'] != 'read':
        for changes in [{'approval': False}, {'effect': 'read'}]:
            with pytest.raises(ValueError):
                CapabilitySpec.model_validate({**raw, **changes})


@pytest.mark.parametrize('name', ['redpa.documents', 'redpa.chat'])
def test_redpa_native_authenticated_mapping(name, monkeypatch):
    raw = next(s for s in SPECS if s['name'] == name)
    reg = registry(raw)
    monkeypatch.delenv('NEXUS_REDPA_TOKEN', raising=False)
    with pytest.raises(AdapterFailure, match='missing_service_credential'):
        asyncio.run(Gateway(reg).execute(reg.get(name), INPUTS[name], CONTEXT))
    monkeypatch.setenv('NEXUS_REDPA_TOKEN', 'test-account-token')

    def upstream(request):
        assert request.headers['Authorization'] == 'Bearer test-account-token'
        assert request.headers['X-Nexus-Workspace'] == 'red'
        assert request.url.path == httpx.URL(raw['endpoint']).path
        if name == 'redpa.documents':
            assert request.method == 'GET' and request.content == b''
            return httpx.Response(200, json=[dict(id='doc', filename='sample.txt', status='ready')])
        assert request.method == 'POST' and json.loads(request.content) == INPUTS[name]
        return httpx.Response(200, json=dict(conversation_id=INPUTS[name]['conversation_id'],
            user_message={}, assistant_message={'content': 'Protocol fixture, not actual RAG'}, model='fixture'))

    result = asyncio.run(Gateway(reg, httpx.MockTransport(upstream)).execute(reg.get(name), INPUTS[name], CONTEXT))
    assert result['project'] == 'redpa'
    for response, error in [(httpx.Response(401), 'upstream_rejected_request'), (httpx.Response(200, json={}), 'contract_violation')]:
        with pytest.raises(AdapterFailure, match=error):
            asyncio.run(Gateway(reg, httpx.MockTransport(lambda _: response)).execute(reg.get(name), INPUTS[name], CONTEXT))


def test_native_contract_cannot_be_weakened():
    raw = next(s for s in SPECS if s['name'] == 'redforge.scan')
    reg = registry({**raw, 'input_schema': {'type': 'object'}})
    with pytest.raises(Problem):
        asyncio.run(Gateway(reg).execute(reg.get(raw['name']), {'path': '/unauthorized'}, CONTEXT))
    with pytest.raises(ValueError):
        CapabilitySpec.model_validate({**raw, 'resource_binding': None})
    raw = next(s for s in SPECS if s['name'] == 'redpulse.analyze')
    reg = registry(raw)
    with pytest.raises(AdapterFailure, match='dimensions'):
        asyncio.run(Gateway(reg).execute(reg.get(raw['name']), {**INPUTS[raw['name']], 'baseline': [0]}, CONTEXT))


@pytest.mark.integration
@pytest.mark.parametrize('project,name', [('redpulse', 'redpulse.analyze'), ('redguard', 'redguard.inspect'), ('redforge', 'redforge.scan')])
def test_supplied_source_native_endpoint(project, name, tmp_path):
    """Original source router for Pulse; original complete apps for Guard and Forge.

    Does not certify a full RedPulse database deployment.
    """
    source = os.getenv('NEXUS_TEST_ECOSYSTEM_ROOT')
    if not source:
        pytest.skip('NEXUS_TEST_ECOSYSTEM_ROOT is not configured')
    backend = Path(source) / (project + '-ai') / ('src' if project == 'redguard' else 'backend')
    assert backend.is_dir()
    code = {
        'redpulse': 'from fastapi import FastAPI\nfrom app.api.v1.v40_platform import router\napp=FastAPI()\napp.include_router(router,prefix="/api/v1")\n',
        'redforge': 'from redforge.main import app\n',
        'redguard': 'from redguard.api.app import app\n',
    }[project]
    (tmp_path / 'source_app.py').write_text(code)
    repo = tmp_path / 'fixture-repository'
    repo.mkdir()
    (repo / 'main.py').write_text('def greeting():\n    return "hello"\n')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    env = {**os.environ, 'PYTHONPATH': str(backend), 'REDFORGE_WORKSPACE_ROOT': str(repo)}
    interpreter = os.getenv('NEXUS_TEST_REDFORGE_PYTHON', sys.executable) if project == 'redforge' else sys.executable
    if project == 'redforge' and interpreter == sys.executable and sys.version_info < (3, 14):
        pytest.skip('RedForge source requires Python 3.14; set NEXUS_TEST_REDFORGE_PYTHON')
    log = tmp_path / 'source.log'
    with log.open('w') as stream:
        process = subprocess.Popen([interpreter, '-m', 'uvicorn', 'source_app:app', '--host', '127.0.0.1', '--port', str(port)],
                                   cwd=tmp_path, env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            with httpx.Client(timeout=2, trust_env=False) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        pytest.fail(log.read_text())
                    try:
                        if client.get(origin + '/openapi.json').status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(.1)
                else:
                    pytest.fail('Source endpoint did not start')
            raw = dict(next(s for s in SPECS if s['name'] == name))
            raw['endpoint'] = origin + httpx.URL(raw['endpoint']).path
            if project == 'redforge':
                raw['resource_binding'] = str(repo)
            reg = registry(raw)
            output = asyncio.run(Gateway(reg).execute(reg.get(name), INPUTS[name], CONTEXT))
            result = output['result']
            assert output['simulated'] is False
            if project == 'redpulse':
                assert result['machine_id'] == 'motor-1' and 0 <= result['failure_risk'] <= 1
            elif project == 'redforge':
                assert result['total_files'] == 1 and result['files'][0]['path'] == 'main.py'
            else:
                assert result['component_id'] == 'part-1'
                with httpx.Client(trust_env=False) as client:
                    saved = client.get(origin + '/api/v1/inspections/' + result['inspection_id'])
                    assert saved.status_code == 200 and saved.json()['inspection_id'] == result['inspection_id']
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def test_large_repository_response_is_explicitly_summarized():
    raw = next(s for s in SPECS if s['name'] == 'redforge.scan')
    reg = registry(raw)
    data = dict(root='/repository', name='repo', total_files=200,
                files=[{'path': f'file-{i}.py', 'language': 'Python'} for i in range(200)],
                symbols={'details': 'x' * 80000})

    def upstream(request):
        assert json.loads(request.content) == {'path': raw['resource_binding']}
        return httpx.Response(200, json=data)

    result = asyncio.run(Gateway(reg, httpx.MockTransport(upstream)).execute(reg.get(raw['name']), {}, CONTEXT))['result']
    assert result['total_files'] == 200 and len(result['files']) == 50 and result['files_preview_truncated']
