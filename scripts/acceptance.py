"""Repeatable local verification; never starts live write missions or certifies stable release."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="Require configured Playwright browser tests")
    parser.add_argument("--output", default="artifacts/acceptance")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    import os

    env = os.environ.copy()
    # Product configuration must not contaminate isolated test databases/providers.
    for key in list(env):
        if key.startswith("NEXUS_") and not key.startswith("NEXUS_TEST_"):
            env.pop(key)
    if args.browser:
        env["NEXUS_TEST_BROWSER"] = "1"
    checks = []
    commands = [
        ("lint", [sys.executable, "-m", "ruff", "check", "rednexus", "tests", "scripts"]),
        ("tests", [sys.executable, "-m", "pytest", "-q", "--junitxml=" + str(output / "tests.xml")]),
        ("demo", [sys.executable, "-m", "rednexus.platform.cli", "demo"]),
    ]
    for name, command in commands:
        print(f"Running {name}...", flush=True)
        with (output / f"{name}.log").open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 124
        checks.append({"name": name, "exit_code": code, "log": name + ".log"})
    skipped = []
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    if (output / "tests.xml").exists():
        for case in ET.parse(output / "tests.xml").iter("testcase"):
            key = (
                "skipped"
                if case.find("skipped") is not None
                else "failed"
                if (case.find("failure") is not None or case.find("error") is not None)
                else "passed"
            )
            counts[key] += 1
            if key == "skipped":
                skipped.append({"test": case.attrib.get("name"), "reason": case.find("skipped").attrib.get("message")})
    files = sorted(
        p
        for folder in ("rednexus", "tests", "scripts", "config")
        for p in (ROOT / folder).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".js", ".json", ".html", ".css")
    )
    fingerprint = hashlib.sha256(
        "".join(f"{p.relative_to(ROOT)}:{hashlib.sha256(p.read_bytes()).hexdigest()}\n" for p in files).encode()
    ).hexdigest()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.system(),
        "checks": checks,
        "tests": counts,
        "skipped": skipped,
        "source_sha256": fingerprint,
        "local_checks_passed": all(c["exit_code"] == 0 for c in checks),
        "stable_release_certified": False,
        "scope": "Local automated checks. Skips are unverified; live services and Windows require separate evidence.",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["local_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
