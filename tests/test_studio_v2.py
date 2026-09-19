"""Opt-in real browser gate: NEXUS_TEST_BROWSER=1, requirements-browser.txt."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
import pytest


@pytest.mark.browser
def test_studio_v2_workflow_template_and_operations(tmp_path):
    if os.getenv("NEXUS_TEST_BROWSER") != "1":
        pytest.skip("NEXUS_TEST_BROWSER is not enabled")
    playwright = pytest.importorskip("playwright.sync_api")
    root = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "NEXUS_DATABASE_URL": f"sqlite:///{tmp_path / 'browser.db'}",
                   "NEXUS_MANIFEST": str(root / "config/projects.json"),
                   "NEXUS_BOOTSTRAP_PASSWORD": "Browser-test-only-123!"}
    subprocess.run([sys.executable, "-m", "rednexus.platform.cli", "bootstrap", "--workspace", "red",
                    "--username", "browser-admin"], cwd=root, env=environment, check=True, capture_output=True)
    with socket.socket() as socket_probe:
        socket_probe.bind(("127.0.0.1", 0))
        port = socket_probe.getsockname()[1]
    with (tmp_path / "server.log").open("w") as log:
        server = subprocess.Popen([sys.executable, "-m", "rednexus.platform.cli", "serve", "--port", str(port)],
                                  cwd=root, env=environment, stdout=log, stderr=log)
        try:
            origin = f"http://127.0.0.1:{port}"
            with httpx.Client(timeout=1, trust_env=False) as client:
                for _ in range(100):
                    try:
                        if client.get(origin + "/health/ready").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.1)
                else:
                    raise AssertionError("browser fixture did not start")
            with playwright.sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(origin)
                page.locator('[name="username"]').fill("browser-admin")
                page.locator('[name="password"]').fill(environment["NEXUS_BOOTSTRAP_PASSWORD"])
                page.locator('#login-form button').click()
                page.locator('#shell').wait_for(state="visible")
                page.locator('[data-page="workflow"]').click()
                page.locator('[data-v2="validate"]').click()
                playwright.expect(page.locator('#v2-result')).to_contain_text('"valid": true')
                page.locator('#template-name').fill("Browser template")
                page.locator('[data-v2="save-template"]').click()
                playwright.expect(page.locator('#v2-result')).to_contain_text('"version": 1')
                page.locator('[data-page="templates"]').click()
                playwright.expect(page.locator('#content')).to_contain_text('Browser template')
                page.locator('[data-page="discovery"]').click()
                playwright.expect(page.locator('#content')).to_contain_text('Credential available')
                page.locator('[data-page="operations"]').click()
                playwright.expect(page.locator('#content')).to_contain_text('Workers alive')
                assert errors == []
                browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
