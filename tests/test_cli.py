"""Exercise the user's actual process entrypoints, outside FastAPI TestClient."""

import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def test_cli_migrate_bootstrap_api_worker_and_backup(tmp_path):
    env = os.environ.copy()
    env["NEXUS_DATABASE_URL"] = f"sqlite:///{tmp_path / 'runtime.db'}"
    env["NEXUS_BOOTSTRAP_PASSWORD"] = "Process-test-password-123!"
    env["NEXUS_MANIFEST"] = str(ROOT / "config/projects.json")

    def cli(*args, extra=None):
        result = subprocess.run(
            [sys.executable, "-m", "rednexus.platform.cli", *args],
            cwd=ROOT,
            env={**env, **(extra or {})},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    cli("migrate")
    cli("bootstrap", "--workspace", "process-test", "--username", "process-admin")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    log = tmp_path / "api.log"
    with log.open("w") as output:
        api = subprocess.Popen(
            [sys.executable, "-m", "rednexus.platform.cli", "serve", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2, trust_env=False) as client:
                for _ in range(100):
                    if api.poll() is not None:
                        raise AssertionError(log.read_text())
                    try:
                        if client.get("/health/ready").status_code == 200:
                            break
                    except (httpx.ConnectError, httpx.ConnectTimeout):
                        pass
                    time.sleep(0.1)
                else:
                    raise AssertionError("API failed readiness: " + log.read_text())
                auth = client.post(
                    "/v1/auth/login",
                    json={
                        "workspace": "process-test",
                        "username": "process-admin",
                        "password": env["NEXUS_BOOTSTRAP_PASSWORD"],
                    },
                )
                auth.raise_for_status()
                client.headers["Authorization"] = "Bearer " + auth.json()["access_token"]
                run = client.post(
                    "/v1/runs",
                    headers={"Idempotency-Key": "process-test"},
                    json={"title": "Real process test", "steps": [{"capability": "redpa.search", "input": {}}]},
                )
                run.raise_for_status()
                run_id = run.json()["id"]
                cli("worker", "--once")
                status = client.get("/v1/runs/" + run_id).json()
                assert status["status"] == "completed"
                assert client.get("/").status_code == 200
        finally:
            api.terminate()
            try:
                api.wait(timeout=10)
            except subprocess.TimeoutExpired:
                api.kill()
                api.wait()
    backup = tmp_path / "backup.db"
    cli("backup", str(backup))
    restored = tmp_path / "restored.db"
    cli("restore", str(backup), extra={"NEXUS_DATABASE_URL": f"sqlite:///{restored}"})
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT status FROM nx_runs WHERE id=?", (run_id,)).fetchone()[0] == "completed"


def test_manifest_grant_upgrade_is_scoped_and_audited(tmp_path):
    import json
    env = {**os.environ, 'NEXUS_DATABASE_URL': f"sqlite:///{tmp_path / 'upgrade.db'}",
           'NEXUS_BOOTSTRAP_PASSWORD': 'Upgrade-test-password-123!',
           'NEXUS_MANIFEST': str(ROOT / 'config/projects.json')}

    def call(*args):
        return subprocess.run([sys.executable, '-m', 'rednexus.platform.cli', *args], cwd=ROOT,
                              env=env, capture_output=True, text=True, timeout=30)

    assert call('bootstrap', '--workspace', 'red', '--username', 'admin').returncode == 0
    env.update(NEXUS_MANIFEST=str(ROOT / 'config/projects-ecosystem.json'), NEXUS_ALLOW_HTTP='true',
               NEXUS_ALLOWED_ORIGINS=','.join(f'http://127.0.0.1:{p}' for p in [8100, 8111, 8112, 8113, 8114]))
    first = call('sync-admin-grants', '--workspace', 'red', '--username', 'admin')
    assert first.returncode == 0, first.stderr
    assert 'tool:redforge.scan' in json.loads(first.stdout)['added']
    again = call('sync-admin-grants', '--workspace', 'red', '--username', 'admin')
    assert json.loads(again.stdout)['added'] == []
    assert call('sync-admin-grants', '--workspace', 'other', '--username', 'admin').returncode != 0
    with sqlite3.connect(tmp_path / 'upgrade.db') as db:
        assert db.execute("SELECT count(*) FROM nx_events WHERE kind LIKE '%local_admin_grants_synced%'").fetchone()[0] == 2


def test_launcher_starts_api_worker_and_reports_duplicate_worker(tmp_path):
    import signal
    import pytest
    if os.name == "nt":
        pytest.skip("POSIX signal-based launcher smoke; Windows launcher is a target gate")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "NEXUS_DATABASE_URL": f"sqlite:///{tmp_path / 'launch.db'}",
           "NEXUS_MANIFEST": str(ROOT / 'config/projects.json')}
    base = [sys.executable, '-m', 'rednexus.platform.cli']
    with (tmp_path / 'launcher.log').open('w') as log:
        process = subprocess.Popen(base + ['launch', '--port', str(port)], cwd=ROOT, env=env,
                                   stdout=log, stderr=log)
        try:
            with httpx.Client(timeout=1, trust_env=False) as client:
                for _ in range(100):
                    try:
                        if client.get(f'http://127.0.0.1:{port}/health/ready').status_code == 200:
                            break
                    except (httpx.ConnectError, httpx.ConnectTimeout):
                        pass
                    time.sleep(.1)
                else:
                    raise AssertionError('launcher API did not start')
            # Allow the concurrently started worker to acquire its lock.
            for _ in range(100):
                if 'worker_started' in (tmp_path / 'launcher.log').read_text():
                    break
                time.sleep(.1)
            duplicate = subprocess.run(base + ['worker', '--once'], cwd=ROOT, env=env,
                                       capture_output=True, text=True, timeout=10)
            assert duplicate.returncode != 0
            assert 'already owns' in duplicate.stderr
        finally:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=20)
    with sqlite3.connect(tmp_path / 'launch.db') as db:
        assert db.execute("SELECT count(*) FROM nx_worker_heartbeats WHERE status='running'").fetchone()[0] == 0
