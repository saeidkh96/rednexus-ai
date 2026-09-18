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
from rednexus.platform.adapters import Registry, Gateway, AdapterFailure
from rednexus.platform.config import Settings
from rednexus.platform.contracts import CapabilitySpec

ROOT = Path(__file__).resolve().parents[1]


def specs(endpoint="http://127.0.0.1:8100/api/v1/world"):
    raw = json.loads((ROOT / "config/projects-redworld-v140.json").read_text())
    selected = [x for x in raw if x.get("protocol") == "redworld_v140"]
    for item in selected:
        item["endpoint"] = endpoint
    return selected


def test_redworld_workspace_and_effect_binding():
    spec = specs()[0]
    registry = Registry(Settings(allow_http=True, allowed_origins=("http://127.0.0.1:8100",)), [spec])
    with pytest.raises(AdapterFailure, match="workspace_binding"):
        asyncio.run(
            Gateway(registry).execute(
                registry.get("redworld.snapshot"),
                {},
                {"workspace": "other", "run_id": "r", "actor": "a", "idempotency_key": "r:0"},
            )
        )
    with pytest.raises(ValueError):
        CapabilitySpec.model_validate({**spec, "workspace_binding": None})
    with pytest.raises(ValueError):
        CapabilitySpec.model_validate({**spec, "name": "redworld.advance", "effect": "read"})


def test_redworld_mapping_and_version_validation():
    registry = Registry(Settings(allow_http=True, allowed_origins=("http://127.0.0.1:8100",)), specs())

    def upstream(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/world/step"
        assert request.url.params["steps"] == "2"
        return httpx.Response(200, json={"stepped": 2, "world": {"version": "1.4.0", "tick": 2, "population": 50}})

    context = {"workspace": "red", "run_id": "r", "actor": "a", "idempotency_key": "r:0"}
    result = asyncio.run(
        Gateway(registry, httpx.MockTransport(upstream)).execute(
            registry.get("redworld.advance"), {"steps": 2}, context
        )
    )
    assert result["advanced_steps"] == 2 and result["simulated"] is False
    bad = httpx.MockTransport(lambda _: httpx.Response(200, json={"version": "9.0.0", "tick": 0, "population": 50}))
    with pytest.raises(AdapterFailure, match="version_or_contract"):
        asyncio.run(Gateway(registry, bad).execute(registry.get("redworld.snapshot"), {}, context))


@pytest.mark.integration
def test_real_redworld_api(tmp_path):
    source = os.getenv("NEXUS_TEST_REDWORLD_SRC")
    if not source:
        pytest.skip("NEXUS_TEST_REDWORLD_SRC is not configured")
    # Source must be an explicitly provided RedWorld src directory. Not vendored in Nexus.
    if not (Path(source) / "redworld/api/main.py").is_file():
        pytest.fail("RedWorld source directory does not contain redworld/api/main.py")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "PYTHONPATH": source, "REDWORLD_DEFAULT_POPULATION": "50"}
    log = tmp_path / "redworld.log"
    with log.open("w") as output:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "redworld.api.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=tmp_path,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            origin = f"http://127.0.0.1:{port}"
            with httpx.Client(timeout=10, trust_env=False) as client:
                for _ in range(150):
                    if process.poll() is not None:
                        pytest.fail(log.read_text())
                    try:
                        if client.get(origin + "/api/v1/world").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.1)
                else:
                    pytest.fail("RedWorld did not become ready: " + log.read_text())
            selected = specs(origin + "/api/v1/world")
            if os.getenv("NEXUS_TEST_REDWORLD_VERSION", "1.4.0") == "2.0.0":
                for item in selected:
                    item["protocol"] = "redworld_v200"
                    item["output_schema"]["properties"]["project_version"] = {"const": "2.0.0"}
            registry = Registry(Settings(allow_http=True, allowed_origins=(origin,)), selected)
            gateway = Gateway(registry)
            context = {"workspace": "red", "run_id": "r", "actor": "a", "idempotency_key": "r:0"}
            before = asyncio.run(gateway.execute(registry.get("redworld.snapshot"), {}, context))
            assert before["world"]["population"] == 50 and before["world"]["tick"] == 0
            after = asyncio.run(gateway.execute(registry.get("redworld.advance"), {"steps": 2}, context))
            assert after["world"]["tick"] == 2 and after["advanced_steps"] == 2
            final = asyncio.run(gateway.execute(registry.get("redworld.snapshot"), {}, context))
            assert final["world"]["tick"] == 2
            assert final["evidence"][0]["kind"] == "live_project_api"
            # Exercise the real API through the durable, reviewed Nexus workflow too.
            from rednexus.platform.storage import Database, Approval
            from rednexus.platform.service import Platform
            from rednexus.platform.identity import Identity
            from rednexus.platform.contracts import UserInput, LoginInput, RunInput, ReviewInput
            from rednexus.platform.runtime import Worker
            from rednexus.platform.cli import grants
            from sqlalchemy import select

            settings = Settings(
                database_url=f"sqlite:///{tmp_path / 'nexus.db'}", allow_http=True, allowed_origins=(origin,)
            )
            db = Database(settings)
            db.migrate()
            identity = Identity(db, settings)
            password = "Redworld-integration-test-123!"
            identity.bootstrap(
                "red", "Red", UserInput(username="operator", password=password, role="admin", grants=grants(registry))
            )
            with db.session.begin() as session:
                identity.create_user(
                    session,
                    "red",
                    UserInput(
                        username="reviewer", password=password, role="reviewer", grants=["review:redworld.advance"]
                    ),
                )

            def actor(name):
                token = identity.login(LoginInput(username=name, password=password, workspace="red"), "local")
                return identity.authenticate(token["access_token"])

            operator, reviewer = actor("operator"), actor("reviewer")
            platform = Platform(db, registry, settings)
            worker = Worker(platform, gateway)
            mission = platform.submit(
                operator,
                RunInput(
                    title="Real RedWorld mission",
                    steps=[
                        {"capability": "redworld.snapshot"},
                        {"capability": "redworld.advance", "input": {"steps": 1}},
                        {"capability": "redworld.snapshot"},
                    ],
                ),
                "real-redworld",
            )
            asyncio.run(worker.tick())
            asyncio.run(worker.tick())
            assert platform.inspect(operator, mission["id"])["status"] == "waiting_approval"
            with db.session() as session:
                approval = session.scalar(select(Approval))
                platform.review(
                    reviewer,
                    approval.id,
                    ReviewInput(
                        allow=True,
                        digest=approval.action_digest,
                        reason="Scripted integration test on isolated test world",
                    ),
                )
            asyncio.run(worker.tick())
            asyncio.run(worker.tick())
            finished = platform.inspect(operator, mission["id"])
            assert finished["status"] == "completed"
            assert [r["world"]["tick"] for r in finished["outputs"]] == [2, 3, 3]
            db.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
