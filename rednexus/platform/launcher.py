"""Keep API and one worker together; exiting stops both child processes."""
import os
from pathlib import Path
import subprocess
import sys
import time


def launch(port=8000, concurrency=2, ecosystem=False):
    root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    if ecosystem:
        environment["NEXUS_MANIFEST"] = str(root / "config/projects-ecosystem.json")
        environment.setdefault("NEXUS_ALLOW_HTTP", "true")
        environment.setdefault("NEXUS_ALLOWED_ORIGINS", ",".join(
            f"http://127.0.0.1:{p}" for p in (8100, 8111, 8112, 8002, 8114)))
    base = [sys.executable, "-m", "rednexus.platform.cli"]
    check = subprocess.run(base + ["migrate"], cwd=root, env=environment)
    if check.returncode:
        return check.returncode
    children = []
    try:
        children.append(subprocess.Popen(base + ["serve", "--port", str(port)], cwd=root, env=environment))
        children.append(subprocess.Popen(base + ["worker", "--concurrency", str(concurrency)], cwd=root, env=environment))
        print(f"Nexus Studio: http://127.0.0.1:{port} — Ctrl+C stops API and worker.", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        return next((child.returncode for child in children if child.returncode is not None), 1)
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(launch(ecosystem=True))
