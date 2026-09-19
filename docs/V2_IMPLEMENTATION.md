# Implementation and acceptance matrix — 2.0.0 RC1

This supersedes the older roadmap. Milestones are delivered together as one
candidate, not as separately certified stable releases.

| Milestone | Implemented | Remaining acceptance / boundary |
|---|---|---|
| 1.0 hardening | Hidden-input validation, OAuth CLI, external credentials, worker lock/status, diagnostics | Windows DPAPI, live RedPA chat; license remains owner decision |
| 1.1 data flow | Earlier-step JSON Pointer bindings, scalar/existence conditions, final schema checks | Sequential steps; no arbitrary expressions or loops |
| 1.2 catalog | Persistent registration, scope, origin allowlist, version/fingerprint checks, health probes | Point-in-time health only; no arbitrary network scanning |
| 1.3 memory | Provenance, embeddings, cosine search, versioning, expiry, redaction | 500 current records per namespace; explicit indexing; no large ANN backend |
| 1.4 agents | Ordered/model plans, team proposals, scoped assignments, parallel runs, group budget, replan proposals | User-owned scoped agent profiles; explicit submission; no unbounded autonomous replanning or provider billing enforcement |
| 1.5 operations | Launcher, status, failed-run inbox, read resubmission, event correlation, SQLite backup/restore, secrets | Real PostgreSQL/Redis/OTel and capacity validation required; uncertain writes need evidence |
| 2.0 extensibility | Adapter SDK with receipts, templates, v2 APIs, workspaces, PostgreSQL worker mode | No public plugin marketplace/arbitrary code loading; multi-node validation still required |

## Execution guarantees

- Plan and contract fingerprint freeze on submission. Bindings resolve from
  committed earlier outputs; missing sources block execution.
- Approval binds the resolved input, contract, run, step and reserved cost.
  Actor/reviewer grants are rechecked before execution.
- Templates, groups and memory are workspace-scoped. Tenant administrators cannot
  grant themselves platform-wide permissions through the HTTP API.
- The OS worker lock is local to one machine. PostgreSQL mode explicitly permits
  multiple workers; database leases and fencing arbitrate claims.
- Adapter receipts persist `started` before calling a handler. Crashes leave
  uncertainty instead of replaying a write. This is not exactly-once execution;
  handlers still need service transactions, idempotency or outboxes.
- Replanning proposes a new workflow, never resets a failed run or reuses its
  approval. Group allocations commit together and fit the group budget.
- Tool costs are estimated reservations, not externally measured provider bills.

## Upgrade and rollback

Existing `/v1` routes remain. Schema version 2 adds tables without deleting v1
accounts or records. Expanded contracts change fingerprints: drain/cancel pending
v1 work first. Never manually alter a stored approval or fingerprint to resume.

Rollback requires stopping v2 and restoring **both** pre-upgrade source and DB.
Do not run old code against v2-modified state. Restoring Nexus cannot reverse
effects already made in external projects. The upgrade script backs up only the
default SQLite DB; custom paths/PostgreSQL require an operator backup.

## Credentials and registration

The credential file defaults to the OS user's home. Unix files are owner-only,
not encrypted; Windows uses DPAPI tied to the current Windows user. DPAPI files
are not portable backups. Containers should use injected environment variables
or an owner-readable mounted file, never image-baked credentials.

Registrations refresh before submission and worker ticks, and survive restarts.
Changed contracts require a new version and invalidate existing plan fingerprints.
Health probes use explicit health URLs without sending service credentials.
Protected health endpoints can therefore report authorization errors even when
execution works. Origin changes are local settings requiring restart. Registration
never grants execution access. All worker nodes need the same origin/secret policy.

## Validation

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check rednexus tests
python -m rednexus.platform.cli demo
python scripts/export_contracts.py
python scripts/check_release.py
```

Optional service tests use `NEXUS_TEST_POSTGRES_URL` and `NEXUS_TEST_REDIS_URL`.
Use isolated test services only. Native tests use `NEXUS_TEST_ECOSYSTEM_ROOT`,
`NEXUS_TEST_REDWORLD_SRC` and, for RedForge, a Python 3.14 interpreter via
`NEXUS_TEST_REDFORGE_PYTHON`. Source-router, source-app and protocol-fixture tests
have different scopes; none certify domain-model quality.

Before stable 2.0.0: validate Windows/DPAPI/upgrade/rollback, all seven native
capabilities (including reviewed RedPA chat), actual embedding/model providers,
PostgreSQL multi-worker recovery, Redis duplicate/dead-letter handling, browser
flows and an OTel collector. Record actual evidence; skipped tests do not pass a
gate. No automatic GitHub push/tag occurs. No throughput or SLO claim is made.
