# Historical roadmap — v0/v1

For the current implementation and remaining release gates, see [V2_IMPLEMENTATION.md](V2_IMPLEMENTATION.md).

The first six weeks are an indicative foundation sprint for one developer, subject to actual repository/API compatibility. They do not represent a promise to finish the entire platform in six weeks.

| Window / milestone | Deliverable | Exit gate |
|---|---|---|
| Now: v0.0.1 | Local core, mock adapters, SQLite state, policy and approval semantics, blueprint | Unit tests and five-interface demo pass; limitations documented |
| Week 1: v0.0.2 | Inspect project APIs; split core modules; schemas and manifest validation; pick first real RedPA read-only adapter | Real request returns cited evidence; contract and negative input tests pass |
| Week 2: v0.1.0 | FastAPI boundary, verified user identity, PostgreSQL migrations, workspace membership | No cross-tenant read/write; invalid tokens denied; restart preserves state |
| Week 3: v0.2.0 | RedPulse → Nexus → RedPA live read-only mission | Real event reaches explanation; unavailable services fail visibly; duplicate event does not duplicate mission |
| Week 4: v0.3.0 | Event outbox, broker transport, inbox deduplication, durable execution proof | Injected crashes/redelivery do not lose committed events or repeat completed writes |
| Week 5: v0.4.0 | Real reviewer inbox and constrained RedForge proposal workflow | Exact diff/evidence reviewed; changed plan invalidates approval; no deployment capability yet |
| Week 6: v0.5.0 | Minimal Studio, trace propagation, quotas, replay/evaluation fixtures | One mission inspectable end to end; budget exhaustion stops work; recorded replay cannot issue writes |
| Next: v0.6–0.8 | RedGuard and relevant RedWorld scenario adapters; scoped semantic memory | Real visual evidence and validated scenario outputs retain provenance and access controls |
| v0.9 | Failure drills, migration/backup/restore, isolated execution, adversarial tests | Restore and tenancy/security/recovery gates pass on chosen environment |
| v1.0 | Stable SDK/contracts, supported adapter matrix, documented operations | Repeatable real end-to-end workflows; explicit SLO evidence; no critical unresolved isolation defects |
| Beyond v1 | Multi-node capacity, federation, capability catalog, advanced evaluations | Demand-driven scale tests and independent onboarding without core edits |

## First live workflow

Start with two projects: RedPulse publishes a permitted operational signal; RedPA supplies an evidence-based explanation. Add visual verification only when visual input exists. Add simulation only when the model is relevant. RedForge initially prepares a plan/diff in isolation; merge/deployment remain separate capabilities and approval steps.

## v0.0.2 backlog

1. Obtain exact current OpenAPI/specification files for RedPA and RedPulse.
2. Inventory auth, health, error, async job and idempotency behavior without altering them.
3. Write versioned command/result schemas and manifest validator.
4. Separate repository/storage and runtime interfaces behind tested ports.
5. Implement a timeout-bounded, allowlisted read-only HTTP adapter.
6. Add contract tests with recorded fixtures plus an explicitly configured integration test.
7. Make environment configuration explicit; never commit credentials.
8. Record evidence that the adapter calls the real project before labeling it connected.

## Release discipline

Each version records scope, changes, evidence and limitations. No placeholder counts as a working service. Integration, security, reliability and performance are separate gates. A green unit suite does not establish production readiness.
