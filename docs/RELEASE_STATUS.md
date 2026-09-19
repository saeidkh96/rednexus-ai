> Historical v1 reference. Current release: **2.0.0 RC1**. See [V2_IMPLEMENTATION.md](V2_IMPLEMENTATION.md) and [release-evidence.json](release-evidence.json) for current scope and validation.

# Release status: 1.0.0-rc.1

This is a runnable platform candidate delivered toward the requested v1.0.0 scope. It is **not** a completed stable ecosystem integration. Version metadata deliberately uses `1.0.0rc1` to avoid treating missing release gates as passed.

## Roadmap accounting

| Requested milestone | Delivered implementation | Remaining boundary |
|---|---|---|
| v0.0.2 modular contracts | Modules, strict models, manifests, JSON schema exports, SDK | Domain-specific schemas require real projects |
| v0.1 core API | FastAPI, SQLAlchemy PostgreSQL/SQLite, initial migration, mission APIs | Real PostgreSQL execution not available here |
| v0.2 identity | Workspace memberships, users/services, roles, exact grants, revocable sessions | Native auth; no OIDC/MFA federation |
| v0.3 durable execution/events | Worker, atomic SQL queue, leases, retries, deadlines, outbox/Streams, inbox | Real Redis and PostgreSQL crash drills still need their environment |
| v0.4 first integrations | RedPA/RedPulse fixture workflows, configurable HTTP gateway, local TCP contract test | No actual RedPA/RedPulse endpoints verified |
| v0.5 Studio | Login, overview, missions, evidence, reviews, agents, memory, team | Browser visual/interaction gate could not run here |
| v0.6 agent runtime | Scoped ordered/model proposal, model selection, validation, call/cost reservation limits | Live model provider not called; no currency-billing reconciliation |
| v0.7 memory | Scope, provenance, versions, TTL, deletion, lexical search | Real semantic RAG delegated to unconnected RedPA; no vector index |
| v0.8 ecosystem integration | Five registry entries, HTTP SDK, verified native RedWorld v1.4.0 snapshot/advance mapping | RedPA, RedPulse, RedGuard and RedForge APIs remain unverified |
| v0.9 operations/evaluation | Audit, metrics, optional OTel, replay, structural eval, SQLite restore test | Real collector, PostgreSQL restore and load/security audits not performed |
| v1.0 stable release | Packaging, deployment files, CI gates, docs, compatibility evidence | Stable gate remains false until missing verification is completed |

## Explicitly not shipped

A verified live connection to RedPA, RedPulse, RedGuard or RedForge; a real LLM completion during validation; autonomous code execution or deployment; a distributed parallel DAG engine; vector-semantic memory; federation across identity providers; automatic database/stream retention; production performance/security certification; a published website or pushed repository.

## To turn this candidate into stable v1

1. Supply current source/OpenAPI, auth method and runnable test environment for RedPA, RedPulse, RedGuard and RedForge. RedWorld snapshot/advance has local-source integration evidence; confirm the target deployment and any richer scenario needs. Implement remaining domain bridges and contract tests.
2. Run actual PostgreSQL/Redis service tests and failure drills using the included CI/environment commands.
3. Run Studio browser and Windows/Python 3.14 validation. Prior v0.0.1 Windows results do not validate the expanded candidate.
4. Verify backup/restore and telemetry on the chosen deployment.
5. Review the intentionally limited semantics (sequential workflows, native auth, lexical local memory and structural evaluation) against the intended v1 acceptance criteria.
6. Record evidence, update the compatibility matrix and only then remove the RC suffix.

The user has authorized development of the whole requested scope. Missing external code/environments, not a request for another permission round, prevent honestly marking every integration gate complete.
