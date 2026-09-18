# RedNexus AI

**One mission. Multiple specialized systems. A traceable outcome.**

RedNexus coordinates the independent RedPA, RedGuard, RedPulse, RedForge and RedWorld projects through versioned capabilities, shared identity, scoped memory, durable workflows, events and human review.

## Release status

**1.0.0-rc.1 — executable platform release candidate. Not a verified stable v1.0.0.**

The API, Studio, database-backed worker, approval gates, memory, event transport code, client SDK and deployment files are implemented. The default five-project manifest uses explicitly labeled **demo** adapters. RedWorld v1.4.0 was subsequently verified against its actual source in an isolated local HTTP process; use the alternative manifest described in [RedWorld integration](docs/REDWORLD_INTEGRATION.md). The other four projects remain unverified fixtures. PostgreSQL/Redis service gates and browser/Windows execution also require their target environments. See [release status](docs/RELEASE_STATUS.md).

## Windows quick start

Extract the archive. Open PowerShell in the directory containing this README:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m rednexus.platform.cli migrate
.\.venv\Scripts\python.exe -m rednexus.platform.cli bootstrap --workspace red --username saeid
.\.venv\Scripts\python.exe -m rednexus.platform.cli serve
```

Choose your own password when prompted. There are no default credentials.

Open a second PowerShell in the same directory:

```powershell
.\.venv\Scripts\python.exe -m rednexus.platform.cli worker
```

Open [Nexus Studio](http://127.0.0.1:8000). Sign in with workspace `red`, username `saeid`, and your chosen password.

Use Workspace team to create a separate reviewer. Grant `review:redforge.propose` for the default approval-required capability. An admin still needs explicit tool/review grants. The bootstrap account receives the current manifest's grants. Model planning is optional; ordered planning and the five demo adapters work without an API key.

PowerShell wrappers: `SETUP.ps1`, `BOOTSTRAP.ps1`, `START.ps1`, `WORKER.ps1`, `VALIDATE.ps1`. The direct commands above work without changing PowerShell script execution policy.

## Upgrade from v0.0.1

Stop running processes. Extract into a separate directory and use `scripts/UPGRADE.ps1 -Target <existing-project-directory>`, or back up your old source and copy the new archive's contents over it. Preserve `.env`, `.venv`, `.git`, database files and `data/`.

The `rednexus.core` and `rednexus.demo` modules and 13 original tests remain compatible. The new platform defaults to `data/nexus-v1.db` and separate `nx_` tables. Legacy run records are not automatically imported. Reinstall dependencies and run migration before starting the new platform. Full Persian instructions: [UPGRADE_AND_RUN_FA.md](docs/UPGRADE_AND_RUN_FA.md).

## Validate

```powershell
.\.venv\Scripts\python.exe scripts/validate.py
.\.venv\Scripts\python.exe scripts/check_release.py
```

The first command tests the local implementation. The second intentionally exits `2` while stable release gates are missing. Passing unit tests is not proof of real Red-project integrations.

Cross-platform demo:

```bash
python -m rednexus.platform.cli demo
```

The demo uses temporary SQLite, fixture accounts and a scripted reviewer. Its output identifies every project response as simulated. Studio workflows require an actual separate reviewer login.

## Implemented platform

- FastAPI API and OpenAPI contracts; same-origin Studio with no JavaScript build step.
- Scrypt password storage, expiring/revocable opaque sessions, workspace memberships, roles and exact grants; service identities cannot approve.
- PostgreSQL/SQLite SQLAlchemy persistence; initial versioned schema migration.
- Durable SQL queue, atomic claim, lease fencing, bounded read retries, deadlines, cancellation and manual reconciliation.
- Immutable plans; approval binds to capability contract and exact resolved input; expiry and reviewer revalidation.
- Redis Streams outbox publisher, deduplicating consumer receipts, dead-letter handling for malformed envelopes.
- Authenticated inbound events with producer-bound workflow rules and inbox deduplication.
- Validated HTTP capability gateway, fixed origin allowlist, timeouts, response limits and environment-based service credentials. Native RedWorld snapshot/advance mappings are verified against v1.4.0.
- Agent definitions, deterministic or configured model planning, explicit proposal submission, tool-call/estimated-cost caps and planning rate limits.
- Tenant/namespace memory with versions, provenance, TTL, lexical retrieval and logical deletion/redaction.
- Evidence-only replay, structural evaluations, workspace audit, Prometheus-style metrics and optional OpenTelemetry tracing.
- CLI, Python client SDK, Docker Compose, Windows/Linux CI definitions and operational runbooks.

## Documentation

Start at [docs/README.md](docs/README.md). Exact API/manifest schemas live in `contracts/`. A fixture bridge is in `examples/reference_bridge.py`; it is not an implementation of any existing project's API.

No automatic deployment, GitHub publication or changes to another Red repository occurred. Licensing remains an explicit owner decision; this package does not copy another project's license.
