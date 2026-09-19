"""Report actual release gates. Exit nonzero while live integration evidence is absent."""

import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "config/projects-ecosystem.json").read_text())
evidence_path = root / "docs/release-evidence.json"
evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
required_projects = {"redpa", "redpulse", "redguard", "redforge", "redworld"}
configured = {c["project"] for c in manifest if c["mode"] == "http"}
verified = set(evidence.get("verified_live_projects", []))
gates = {
    "core_tests_passed": evidence.get("core_tests_passed", False),
    "five_http_projects_configured": required_projects <= configured,
    "five_live_projects_verified": required_projects <= verified,
    "postgres_verified": evidence.get("postgres_verified", False),
    "redis_verified": evidence.get("redis_verified", False),
    "browser_verified": evidence.get("browser_verified", False),
    "windows_verified": evidence.get("windows_verified", False),
    "redpa_chat_live_verified": evidence.get("redpa_chat_live_verified", False),
    "semantic_provider_verified": evidence.get("semantic_provider_verified", False),
    "distributed_recovery_verified": evidence.get("distributed_recovery_verified", False),
    "live_model_verified": evidence.get("live_model_verified", False),
    "otel_collector_verified": evidence.get("otel_collector_verified", False),
}
ready = all(gates.values())
print(json.dumps({"version": "2.0.0-rc.1", "stable_v2_ready": ready, "gates": gates}, indent=2))
raise SystemExit(0 if ready else 2)
