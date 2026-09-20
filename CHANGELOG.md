# 2.0.0 RC2

- Workflow recipes and import in Studio; primary New mission opens full builder.
- Existing identity access editor, team proposals/status, scoped evidence exports.
- Semantic Pulse-to-RedPA handoff recipe with exact-input review.
- Native HTTP fixture acceptance for skip, rejection, timeout, revocation and recovery.
- Local acceptance runner, expanded browser/PostgreSQL CI checks, preserved configuration upgrade.
- Still a release candidate: see current gate matrix.

# Changelog

## 2.0.0-rc.1 — 2026-09-19

- Add deterministic earlier-step bindings and conditional skipping; validate final
  inputs before human approval or tool execution.
- Add immutable template versions and SQL-backed capability registration.
- Add explicit health discovery and credential readiness diagnostics.
- Add optional provider-backed semantic memory with namespace authorization,
  version-aware retrieval, redaction and retention cleanup.
- Add scoped agent group submissions, concurrent workers, team planning proposals
  and explicit terminal-run replanning.
- Add operations and failed-run views, safe read-only resubmission and HTTP status
  evidence without storing upstream response bodies or credentials.
- Add worker lock, heartbeat, one-command launcher and external credential store.
- Add RedPA form-login CLI; redact credential input from validation errors.
- Add adapter SDK with durable execution receipts and client SDK extensions.
- Add Studio panels, v2 contracts, tests and Persian upgrade guide.
- Preserve existing v1 API and accounts through additive schema version 2.

This is a candidate. See docs/release-evidence.json for actual tests and pending
target gates; no stable-release certification is implied.
