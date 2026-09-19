import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from opentelemetry.propagate import inject
from jsonschema import Draft202012Validator, ValidationError
from .contracts import CapabilitySpec, canonical, digest
from .identity import Problem
from .credentials import credential


class AdapterFailure(Exception):
    def __init__(self, code, retryable=False, http_status=None):
        self.code, self.retryable, self.http_status = code, retryable, http_status
        super().__init__(code)


def validate_payload(schema, value):
    try:
        Draft202012Validator(schema).validate(value)
        if len(canonical(value).encode()) > 65536:
            raise ValueError()
    except ValidationError as exc:
        path = "/" + "/".join(str(p) for p in exc.absolute_path)
        raise Problem(422, f"input contract violation at {path}: {exc.validator}") from None
    except (ValueError, TypeError):
        raise Problem(422, "payload does not satisfy capability schema or size limit") from None


class Registry:
    def __init__(self, settings, specs=None):
        self.settings = settings
        raw = json.loads(Path(settings.manifest_path).read_text(encoding="utf-8-sig")) if specs is None else specs
        self.base_specs = raw
        self.db = None
        self.specs = {}
        for item in raw:
            spec = CapabilitySpec.model_validate(item)
            if spec.name in self.specs:
                raise ValueError("duplicate capability name")
            if spec.mode == "http":
                self.check_endpoint(spec.endpoint)
            if spec.health_endpoint:
                self.check_endpoint(spec.health_endpoint)
            self.specs[spec.name] = spec

    def refresh(self):
        if self.db is None:
            return
        from sqlalchemy import select
        from .storage import CapabilityRegistration
        with self.db.session() as session:
            additions = [row.spec for row in session.scalars(select(CapabilityRegistration))]
        merged = {name: spec.model_dump() for name, spec in self.specs.items()}
        for item in additions:
            merged[item["name"]] = item
        fresh = Registry(self.settings, list(merged.values()))
        self.specs = fresh.specs

    def check_endpoint(self, endpoint):
        parsed = urlsplit(endpoint)
        if parsed.username or parsed.password or parsed.fragment or parsed.query:
            raise ValueError("endpoint cannot contain credentials, query or fragment")
        if parsed.scheme != "https" and not (self.settings.allow_http and parsed.scheme == "http"):
            raise ValueError("HTTPS required unless operator explicitly enables HTTP")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.settings.allowed_origins:
            raise ValueError("endpoint origin not in operator allowlist")

    def get(self, name):
        if name not in self.specs:
            raise Problem(422, "unknown capability")
        spec = self.specs[name]
        if spec.mode == "disabled":
            raise Problem(409, "capability is disabled")
        return spec

    def fingerprint(self, name):
        return digest(self.get(name).model_dump())

    def visible(self, actor):
        return [
            c.model_dump(exclude={"credential_env", "endpoint", "health_endpoint"})
            for c in self.specs.values()
            if (f"tool:{c.name}" in actor.grants or actor.role == "admin")
            and (not c.workspace_binding or c.workspace_binding == actor.workspace)
        ]


async def bounded_request(method, url, body, headers, timeout, transport=None, params=None, max_bytes=65536):
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout), follow_redirects=False, trust_env=False, transport=transport
            ) as client:
                async with client.stream(method, url, json=body, headers=headers, params=params) as response:
                    if response.status_code in (429, 502, 503, 504):
                        raise AdapterFailure("upstream_temporarily_unavailable", True, response.status_code)
                    if not 200 <= response.status_code < 300:
                        raise AdapterFailure("upstream_rejected_request", http_status=response.status_code)
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > max_bytes:
                            raise AdapterFailure("upstream_response_too_large")
                    return json.loads(data)
    except (TimeoutError, httpx.TimeoutException, httpx.NetworkError):
        raise AdapterFailure("upstream_timeout_or_network", True) from None
    except (ValueError, httpx.HTTPError):
        raise AdapterFailure("upstream_invalid_response") from None


async def bounded_post(url, body, headers, timeout, transport=None):
    return await bounded_request("POST", url, body, headers, timeout, transport)


class Gateway:
    def __init__(self, registry, transport=None):
        self.registry, self.transport = registry, transport

    async def execute(self, spec, payload, context):
        validate_payload(spec.input_schema, payload)
        if spec.workspace_binding and spec.workspace_binding != context["workspace"]:
            raise AdapterFailure("capability_workspace_binding_mismatch")
        if spec.mode == "demo":
            # A visible fixture, never represented as a domain prediction or live result.
            result = {
                "simulated": True,
                "project": spec.project,
                "summary": f"Demonstration response from {spec.project}",
                "evidence": [{"source": "demo-fixture", "verified": False}],
                "received": payload,
            }
        elif spec.mode == "http":
            self.registry.check_endpoint(spec.endpoint)
            headers = {
                "X-Nexus-Run": context["run_id"],
                "X-Nexus-Workspace": context["workspace"],
                "Idempotency-Key": context["idempotency_key"],
                "X-Nexus-Actor": context["actor"],
            }
            if spec.credential_env:
                try:
                    secret = credential(self.registry.settings, spec.credential_env)
                except (OSError, ValueError):
                    raise AdapterFailure("credential_store_unavailable") from None
                if not secret:
                    raise AdapterFailure("missing_service_credential")
                headers["Authorization"] = f"Bearer {secret}"
            inject(headers)
            # Domain service must verify the credential and delegated workspace itself.
            if spec.protocol in ("redworld_v140", "redworld_v200"):
                from rednexus.integrations.redworld import execute_redworld

                result = await execute_redworld(spec, payload, context, headers, self.transport)
            elif spec.protocol != "nexus":
                from rednexus.integrations.native import execute_native

                result = await execute_native(spec, payload, context, headers, self.transport)
            else:
                result = await bounded_post(
                    spec.endpoint,
                    {"contract_version": spec.version, "capability": spec.name, "input": payload, "context": context},
                    headers,
                    spec.timeout_seconds,
                    self.transport,
                )
        else:
            raise AdapterFailure("capability_disabled")
        try:
            validate_payload(spec.output_schema, result)
        except Problem:
            raise AdapterFailure("upstream_contract_violation") from None
        return result
