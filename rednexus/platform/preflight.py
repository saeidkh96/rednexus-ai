"""Read-only live profile check; no writes, credentials or response bodies printed."""
import json
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from .adapters import Registry
from .config import Settings


def inspect(settings, transport=None):
    registry = Registry(settings)
    capabilities = [{"name": s.name, "mode": s.mode,
                     "fingerprint": registry.fingerprint(s.name)}
                    for s in registry.specs.values() if s.mode != "disabled"]
    errors = []
    if any(s.mode != "http" for s in registry.specs.values()):
        errors.append("live_profile_required")
    with httpx.Client(timeout=5, trust_env=False, transport=transport) as client:
        for name, path in (("redpulse.analyze", "/api/v1/health"),
                           ("redworld.snapshot", "/api/v1/world")):
            spec = registry.specs.get(name)
            if spec is None or spec.mode != "http":
                errors.append(name + ": missing_http_capability")
                continue
            parts = urlsplit(spec.endpoint)
            url = f"{parts.scheme}://{parts.netloc}{path}"
            registry.check_endpoint(url)
            try:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
                if name == "redpulse.analyze":
                    valid = isinstance(data, dict) and data.get("status") == "healthy"
                else:
                    valid = (isinstance(data, dict) and data.get("version") == "2.0.0"
                             and type(data.get("tick")) is int and "population" in data)
                if not valid:
                    errors.append(name + ": unexpected_health_contract")
            except (httpx.HTTPError, ValueError):
                errors.append(name + ": health_request_failed")
    return {"ready": not errors, "manifest": str(Path(settings.manifest_path).resolve()),
            "capabilities": capabilities, "errors": errors,
            "scope": "RedPulse/RedWorld read-only preflight; not live workflow evidence"}


def main():
    result = inspect(Settings.from_env())
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ready"] else 1)


if __name__ == "__main__":
    main()
