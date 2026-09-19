"""Record this build's JUnit/coverage results without inventing live-service gates."""
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
import sys
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
tree = ET.parse(sys.argv[1])
cases = tree.findall(".//testcase")
skipped = [c for c in cases if c.find("skipped") is not None]
failed = [c for c in cases if c.find("failure") is not None or c.find("error") is not None]
passed = [c for c in cases if c not in skipped and c not in failed]
passed_names = {c.attrib["name"] for c in passed}
lint = subprocess.run([sys.executable, "-m", "ruff", "check", "rednexus", "tests"], cwd=root, capture_output=True)
coverage = json.loads(Path(sys.argv[2]).read_text())
result = {
    "version": "2.0.0-rc.1", "generated_at": datetime.now(timezone.utc).isoformat(),
    "python": platform.python_version(), "platform": platform.system(),
    "core_tests_passed": bool(passed) and not failed, "passed_tests": len(passed), "skipped_tests": len(skipped),
    "failed_tests": len(failed), "line_coverage_percent": round(coverage["totals"]["percent_covered"], 2),
    "skipped": [{"test": c.attrib["name"], "reason": c.find("skipped").attrib.get("message", "")} for c in skipped],
    "source_app_verified_projects": [project for project, test in {
        "redguard": "test_supplied_source_native_endpoint[redguard-redguard.inspect]",
        "redforge": "test_supplied_source_native_endpoint[redforge-redforge.scan]",
        "redworld": "test_real_redworld_api"}.items() if test in passed_names],
    "source_router_verified_projects": ["redpulse"] if "test_supplied_source_native_endpoint[redpulse-redpulse.analyze]" in passed_names else [],
    "verified_live_projects": [],
    "live_scope_note": "Source applications/router ran in isolated temporary HTTP processes; user's deployed services were not accessed.",
    "sqlite_backup_restore_passed": "test_sqlite_backup_restore" in passed_names,
    "api_worker_process_smoke_passed": "test_cli_migrate_bootstrap_api_worker_and_backup" in passed_names,
    "launcher_duplicate_worker_test_passed": "test_launcher_starts_api_worker_and_reports_duplicate_worker" in passed_names,
    "lint_passed": lint.returncode == 0,
    "browser_verified": False, "windows_verified": False, "postgres_verified": False,
    "redis_verified": False, "redpa_chat_live_verified": False, "semantic_provider_verified": False,
    "distributed_recovery_verified": False, "live_model_verified": False, "otel_collector_verified": False,
    "stable_v2_ready": False,
    "environment_limits": ["PostgreSQL/Redis binaries unavailable; package installation failed under container OS permissions",
        "Playwright browser download failed (timeouts/502); JavaScript syntax checked but no browser execution",
        "RedForge source requires unavailable Python 3.14 interpreter; protocol tests passed",
        "Windows DPAPI, PowerShell upgrade and live model providers require target validation"],
}
(root / "docs/release-evidence.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: result[k] for k in ("passed_tests", "skipped_tests", "failed_tests", "line_coverage_percent")}))
