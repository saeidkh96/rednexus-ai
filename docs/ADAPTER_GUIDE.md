> Native ecosystem mappings are now available in `config/projects-ecosystem.json`. See ECOSYSTEM_SETUP_FA.md and INTEGRATION_STATUS.md. The generic Nexus envelope described below applies only to protocol `nexus`.

# Connecting an independent Red project

The default manifest contains explicit fixtures. The actual RedPA, RedPulse, RedGuard and RedForge APIs were not available for inspection; their schemas, endpoints and credentials still need verification. RedWorld v1.4.0 was inspected and its snapshot/advance mapping was tested against an isolated running instance; see REDWORLD_INTEGRATION.md and the alternative manifest.

## Contract

`config/projects.json` is an array of capability manifests. `contracts/CapabilitySpec.schema.json` is the exact schema. Names, versions, side-effect classification, approval requirement and input/output schemas are versioned contract elements. Any manifest change blocks already-queued runs that captured a different fingerprint.

HTTP gateways POST this envelope to the configured endpoint:

```json
{
  "contract_version": "1.0.0",
  "capability": "redpa.search",
  "input": {"objective": "Find relevant evidence"},
  "context": {
    "run_id": "generated-run-id",
    "workspace": "red",
    "actor": "verified-user-id",
    "step": 0,
    "idempotency_key": "generated-run-id:0",
    "deadline": 1800000000.0
  }
}
```

The endpoint returns JSON matching `output_schema`. Prefer `{summary, evidence, artifact references}` rather than raw large documents. Payload/response limit is 64 KiB. The default schemas are deliberately broad demo contracts; narrow them for each real domain integration.

If an existing project has another API shape, write a **domain-owned bridge** that maps this envelope to that project's existing API. Do not modify Nexus to import another repository's internal Python modules or read its database. `examples/reference_bridge.py` demonstrates authenticated envelope handling with an explicit fixture response.

## Configure an HTTP entry

1. Inspect the exact project release and API. Select a read-only operation first.
2. Replace its manifest entry's `mode` with `http`, set the real `endpoint`, and provide actual JSON schemas.
3. Set `credential_env` to the name of the server environment variable containing a project-scoped service credential.
4. Add the exact `scheme://host:port` origin to `NEXUS_ALLOWED_ORIGINS` in both API and worker environments.
5. Use HTTPS. `NEXUS_ALLOW_HTTP=true` is available for an explicitly chosen local development origin.
6. Restart API and worker so their manifests match. New workflow submissions snapshot the new contract.
7. Test successful response, unauthorized workspace, timeout, malformed output and duplicates against the real service.
8. Record the real project release and test evidence in the compatibility matrix before claiming it connected.

No redirects are followed. Proxy environment variables are ignored for tool calls. URL credentials, query strings and fragments are rejected. The operator-managed allowlist is a trust boundary; DNS/IP egress enforcement belongs at the deployment/network layer. A project must verify its service credential and delegated workspace itself; `X-Nexus-Workspace` is not authentication.

A side-effecting operation must declare `effect: write` or `propose` and `approval: true`. A bridge must not disguise an operation that changes data as `read`, because reads may retry. Idempotency keys are forwarded but their actual enforcement depends on the domain service. Unknown effectful outcomes require a domain status check and human reconciliation.

## Service discovery

The registry validates the manifest at startup and returns caller-visible capabilities. `demo`, `http` and `disabled` are configuration modes, not claims of health. No periodic domain health probing is implemented. Real failures become visible workflow errors. Independent deployment and release ownership remain with each project.

## Events from RedPulse or another producer

Create a service identity with the exact `events:ingest` grant in the intended workspace. Authenticate for a one-hour session. A human/operator creates an event rule bound to that service's user ID, event source and event type. POST events to `/v1/events/ingest` with stable event IDs. Duplicate IDs with changed data return conflict. Other producers cannot invoke that rule just by copying its source string.

The rule executes under its creator's current permissions. Therefore the rule is an explicit delegation to a specific producer and must be treated as such. Disable rules with DELETE `/v1/event-rules/{id}`.

## SDK example

```python
from rednexus.sdk import NexusClient

client = NexusClient("http://127.0.0.1:8000", token="your-session-token")
try:
    run = client.submit({
        "title": "Inspect evidence",
        "steps": [{"capability": "redpa.search", "input": {"objective": "Inspect the observation"}}]
    }, idempotency_key="my-stable-request-id")
    print(client.wait(run["id"]))
finally:
    client.close()
```

The client does not silently retry write requests and stops waiting when human approval is required.

## Compatibility matrix

| Project | Bridge contract defined | Fixture tested | Existing project endpoint verified |
|---|---|---|---|
| RedPA | Generic envelope, domain schema pending | Yes | No |
| RedPulse | Generic envelope, domain schema pending | Yes | No |
| RedGuard | Generic envelope, domain schema pending | Yes | No |
| RedForge | Generic envelope with approval | Yes | No |
| RedWorld | Native snapshot/advance mapping | Yes | Yes: v1.4.0, isolated local HTTP API; richer scenario APIs still pending |

Native protocol exception: `protocol: redworld_v140` uses the inspected RedWorld API rather than the generic POST envelope. It requires an explicit workspace binding. See REDWORLD_INTEGRATION.md for its security and recovery boundaries.
