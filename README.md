# RedNexus AI

**Independent projects. Shared workflows, memory and human review.**

RedNexus coordinates RedPA, RedGuard, RedPulse, RedForge, RedWorld and future
projects through versioned APIs. Each project keeps its own repository/runtime.

**Package: 2.0.0-rc.1 — release candidate, not a certified stable deployment.**
See [implementation scope](docs/V2_IMPLEMENTATION.md) and
[test evidence](docs/release-evidence.json). Earlier manual Windows smoke tests
are historical evidence, not fresh v2 validation.

Existing Windows installation? Start with **[START_HERE_FA.md](START_HERE_FA.md)**.

## What's new

| Area | Implemented behavior |
|---|---|
| Workflows | Earlier-step JSON Pointer bindings, conditional steps, final schema validation before approval |
| Templates | Immutable workspace-scoped versions, permissions rechecked on execution |
| Onboarding | Persistent capability registration, origin allowlist, version/fingerprint checks, health probes |
| Memory | Scoped provenance, versioning, retention, optional embeddings and cosine search |
| Agent teams | Scoped assignments, parallel independent workflows, aggregate reserved budget, team plan proposals |
| Operations | Worker lock/status, concurrency, launcher, HTTP diagnostic codes, failed-run inbox |
| Credentials | Environment or external store; Windows DPAPI, owner-only Unix files, RedPA login CLI |
| SDK | Independent HTTP adapter factory with durable idempotency receipts; Python client |
| Compatibility | Existing `/v1` API plus `/v2` routes and additive database migration |

Uncertain writes are never silently replayed. Model proposals cannot bypass
grants or human approval. Estimated tool reservations are not provider invoices.

## Upgrade on Windows

Finish/cancel old pending work, stop old API/workers and extract this ZIP into
a separate folder. From that folder:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\UPGRADE.ps1 -Target C:\Users\saeed\Desktop\rednexus-ai
cd C:\Users\saeed\Desktop\rednexus-ai
.\SETUP.ps1
.\ECOSYSTEM.ps1 -Action doctor
.\START_ECOSYSTEM.cmd
```

Upgrade preserves config, accounts, data, .env, .git and .venv. It backs up the
default SQLite database and old source. Back up custom databases/PostgreSQL
separately. **Do not bootstrap an existing workspace again.** Expanded contract
fingerprints intentionally block old pending plans; submit a newly reviewed plan.

The launcher starts Nexus API and one worker (concurrency 2), not the independent
Red services. Nexus uses **8000**; RedPA remains **8111 → container 8000**.
Keep the terminal open. Stop an existing Nexus instance before launching.

## Fresh demo installation

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m rednexus.platform.cli migrate
.\.venv\Scripts\python.exe -m rednexus.platform.cli bootstrap --workspace red --username saeid
.\.venv\Scripts\python.exe -m rednexus.platform.cli launch
```

Open http://127.0.0.1:8000. `config/projects.json` is explicitly simulated;
`launch --ecosystem` selects the native HTTP manifest. A distinct human reviewer
needs exact review grants; even administrators need tool/review grants.

## RedPA credentials

With RedPA running on 8111:

```powershell
.\ECOSYSTEM.ps1 -Action redpa-login -Username saeed@example.com
```

Password is prompted privately. The real RedPA OAuth form endpoint is
`/api/v1/auth/login`; Nexus's JSON login endpoint is a different service.
The token is stored outside the repo in `%USERPROFILE%\.rednexus\credentials.json`,
protected by DPAPI on Windows. Workers read it on their next call. Expired token?
Run login again. No database password changes or token minting are necessary.
An old `NEXUS_REDPA_TOKEN` environment variable overrides the file; remove that
variable before starting the worker if you want the stored token.

To save an existing token: `ECOSYSTEM.ps1 -Action credential-set`.
`redpa.documents` takes `{}`. `redpa.chat` takes a real conversation UUID and
`content`, and pauses for review. It may invoke a paid model.

## Workflows and APIs

Studio adds Workflow builder, Templates, Service status, Agent teams, Semantic
memory and Operations. `/docs` contains the API specification.

- `POST /v2/validate`, `/v2/templates`, `/v2/templates/{id}/runs`
- `POST /v2/capabilities`; `GET /v2/discovery`
- `POST /v2/agent-teams/plan`, `/v2/mission-groups`; `GET /v2/mission-groups/{id}`
- `POST /v2/runs/{id}/replan`, `/v2/runs/{id}/retry-read`
- `POST /v2/memory/index/{namespace}`, `/v2/memory/search`
- `GET /v2/operations`, `/v2/dead-letters`

[examples/v2-bindings.json](examples/v2-bindings.json) runs with the demo manifest.
Bindings use zero-based source steps and JSON pointers. A typical field binding:

```json
{"content": {"step": 0, "pointer": "/result", "format": "json"}}
```

Only earlier steps can be referenced. Missing sources block execution. A false
condition records a skipped output without a tool call or approval. Final bound
inputs are validated against the full contract before review/execution.

Registering a capability requires a workspace administrator, explicit workspace
binding and a pre-approved endpoint origin. Names are globally unique. Grant
`tool:<name>` and `review:<name>` separately. Native validators remain enforced.

## Semantic memory

Configure `NEXUS_EMBEDDING_URL`, `NEXUS_EMBEDDING_MODEL`, optional
`NEXUS_EMBEDDING_API_KEY`, and add the provider origin to `NEXUS_ALLOWED_ORIGINS`.
The endpoint must support OpenAI-compatible embeddings. Restart after changing
settings. Indexing explicitly sends authorized namespace text to this provider.

Search returns provenance, version and cosine score. Changed provider/model
requires reindexing; missing vectors are reported. Limit: **500 current records
per namespace**, 4096 dimensions and 50 search results. This is not a large ANN
database. `purge-memory` physically redacts expired text/vectors; expired records
cannot be retrieved even before purging.

## Adapters and distributed workers

See [examples/v2-adapter.py](examples/v2-adapter.py). The adapter SDK stores a
receipt before handler execution; uncertain receipts are not automatically
replayed. Domain handlers still need transactions/outboxes/idempotency.
Registering a contract never loads arbitrary Python into the Nexus process.

Local: `worker --concurrency 2`. Distributed: PostgreSQL and
`worker --distributed --concurrency 4` per node with identical manifest, allowlist
and secrets. SQL leases arbitrate jobs; Redis is optional event transport.
Parallelism is across independent workflows, not within a run's steps.

## Validation

```powershell
.\.venv\Scripts\python.exe scripts\validate.py
.\.venv\Scripts\python.exe scripts\export_contracts.py
.\.venv\Scripts\python.exe scripts\check_release.py
```

The release gate intentionally exits 2 until target validations are recorded.
Skipped optional tests are not passing gates. See docs for scope and limits.

## License

License selection remains the owner's decision. This archive does not grant an
open-source license or copy another project's license. An existing repository
LICENSE remains applicable and is preserved during upgrade.
