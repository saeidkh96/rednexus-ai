import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from opentelemetry.propagate import inject
from jsonschema import Draft202012Validator, ValidationError
from .contracts import CapabilitySpec, canonical, digest
from .identity import Problem


class AdapterFailure(Exception):
    def __init__(self, code, retryable=False):
        self.code, self.retryable = code, retryable
        super().__init__(code)


def validate_payload(schema, value):
    try:
        Draft202012Validator(schema).validate(value)
        if len(canonical(value).encode()) > 65536:
            raise ValueError()
    except (ValidationError, ValueError, TypeError):
        raise Problem(422, "payload does not satisfy capability schema or size limit") from None


class Registry:
    def __init__(self, settings, specs=None):
        self.settings = settings
        raw = json.loads(Path(settings.manifest_path).read_text()) if specs is None else specs
        self.specs = {}
        for item in raw:
            spec = CapabilitySpec.model_validate(item)
            if spec.name in self.specs:
                raise ValueError("duplicate capability name")
            if spec.mode == "http":
                self.check_endpoint(spec.endpoint)
            self.specs[spec.name] = spec

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
            c.model_dump(exclude={"credential_env", "endpoint"})
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
                        raise AdapterFailure("upstream_temporarily_unavailable", True)
                    if not 200 <= response.status_code < 300:
                        raise AdapterFailure("upstream_rejected_request")
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
                credential = os.getenv(spec.credential_env)
                if not credential:
                    raise AdapterFailure("missing_service_credential")
                headers["Authorization"] = f"Bearer {credential}"
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
