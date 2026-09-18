# v0.0.1 — 2026-09-17

## Delivered

Product vision, architecture, integration model, core/runtime/memory/events/security design, repository structure and gated roadmap. Runnable standard-library Python core and five simulated adapters. No existing project repository was changed.

## Validation evidence

Environment: Linux, Python 3.12.14.

`python -m unittest discover -s tests -v`: 13 tests passed.

Coverage: completed-run replay protection; submission idempotency conflict; approval wait and nonduplicated request event; rejection; self/cross-tenant review rejection; cross-tenant run/event denial; execution-time permission recheck; memory isolation/provenance; handler failure; cancellation; contract drift; restart while awaiting approval; uncertain-step replay blocking.

`python -m rednexus.demo`: completed five mock steps, paused before RedForge proposal, recorded a distinct simulated reviewer decision, emitted 14 journal events, and saved scoped memory.

Initial test discovery from the parent directory failed because the package was outside the import path. Running from the repository root, as documented, passed. PowerShell wrapper and Python 3.14 compatibility have not been executed in this environment.

## Limits

Local trusted prototype; injected principals are not authentication. Single worker only, without concurrency locks/leases. Registry is in memory and must be re-registered on restart. No real HTTP adapters, schemas for domain data, LLM, autonomous planning, network API, OIDC, broker, background worker, OTel export, sandbox, quotas, deadlines or UI.

Inputs/results are limited to 64 KiB per plan/result, but accumulated memory and database growth are not bounded. Handlers are trusted synchronous code. Approval binds to the stored run/step and immutable plan, but there is no cryptographic artifact binding or expiry. Do not connect real side-effecting operations until durable execution, identity and reconciliation are implemented.

The event journal and audit data can be edited by anyone with database access. Generic handler exceptions expose only exception class in events. Memory supports scoped key-value lookup, not semantic search or automatic knowledge sharing.

## Next release

v0.0.2: actual project API inventory, explicit schemas, module separation and first read-only live adapter with contract tests.
