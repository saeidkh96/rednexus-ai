# RedNexus roadmap delivery — 2.0.0 RC2

This matrix describes shipped implementation and evidence, not a certification that every release gate passed.
The eight stages are themes, not eight completed stable releases.

| Stage | Shipped behavior | Verification / remaining gate |
|---|---|---|
| 1 Core | Durable runs, contract fingerprints, scoped identities, budgets, leases, worker lock, audit | Automated authorization, recovery, budget and migration tests; Windows execution must run in CI |
| 2 Connections | Native RedPA, RedPulse, RedGuard, RedForge and RedWorld mappings, allowlist, credential handling, preflight | Contract fixtures; supplied local user evidence confirms Pulse→World; other deployment configurations require independent health/auth validation |
| 3 Live workflow | Presets for high/low risk with reviewer-gated World advance; JSON import; evidence download | High-risk user run fc0bd205 completed; native HTTP fixtures cover both branches |
| 4 Reliability | Rejection/skip do not call writes; retry bounds; uncertain write reconciliation; expired-lease fencing; reviewer reauthorization | New native-adapter runtime tests; PostgreSQL replacement-worker gate added but not certified here |
| 5 Studio | New mission opens complete builder; recipes; import; preserved draft; existing-account grant editing; group progress; status-aware empty states | Browser regression expanded; local browser download failed; must pass browser CI before stable |
| 6 Semantic handoff | Pulse output bound into the actual RedPA chat content after exact-input human review | Mock HTTP verifies content survives dispatch; user's RedPA/model must pass live gate. World economic impact remains a separate RedWorld development task |
| 7 Agents and memory | Scoped agent profiles, model/team proposals, atomic group submission, progress lookup, namespace memory, provenance and embedding search | Existing parallel/scope/budget/memory tests plus team UI. Live model/embedding and Redis deployment gates remain |
| 8 Release operations | Reproducible acceptance runner, machine-readable results, source fingerprints, CI artifact logs, source-only package checksums, preservation-oriented upgrade | Linux checks recorded in RC2_VALIDATION.md. Windows, service, browser, model, telemetry gates cannot be inferred from unit tests |

## Domain boundary

`simulated: false` means the real service adapter was called; it does not mean a sensor observation was real or a score calibrated.
The supplied recipes contain **sample observations**. RedPulse's `failure_risk` is a score, not a certified probability.
World advance records prior output for provenance but does not apply motor failure to society/economy.
The explanation recipe instead binds the entire earlier result into a real RedPA API input. Use an existing dedicated conversation
instructed to explain the maintenance observation, distinguish estimates from facts, and avoid pretending a repair was performed.
RedPA chat stores messages: it is a write capability and requires separate review.

## Release gates

Use `python scripts/acceptance.py` for isolated local automated checks (no live writes).
Use `python scripts/acceptance.py --browser` only with Playwright Chromium installed.
Report and logs appear under `artifacts/acceptance/`. A skipped gate remains unverified.
Use `python scripts/check_release.py` for stable-release eligibility: **exit 2 is expected** until missing evidence is provided.
The runner does not rewrite stable gates or treat a demo as live validation.

CI includes Linux/Windows, Python 3.12/3.14, browser, PostgreSQL and Redis jobs.
CI configuration is not evidence of a successful CI run. Inspect actual job outcomes.

## Live acceptance sequence (test services only)

1. Keep one Nexus API and one SQLite worker; use identical manifest/database settings.
2. High risk: validate and queue; inspect Pulse output; review World write with another human account; observe completed 2/2.
3. Low risk: validate and queue; inspect actual risk < threshold; expect step.skipped, one tool call, no approval, no World write.
4. Reject: queue another high-risk draft and reject its exact World approval; expect rejected and no World write.
5. While waiting for review, stop worker normally, restart it, then review; completed read must not repeat.
6. For connection failures use isolated test instances. Do not kill a production worker during an effectful action.
7. Explanation: use configured RedPA credential and existing conversation, queue draft, inspect resolved chat content in review, approve,
   verify returned conversation ID and assistant message. Export evidence from the run.
8. Agent team: create scoped profiles, propose or explicitly fill assignments, inspect all budgets/inputs, Queue group, Check progress.
9. Memory: verify namespace write/read permissions, provenance, redaction; configure approved embedding origin/key before indexing.
10. Download evidence JSON. It can contain input/output business data; review before sharing. SHA256 is integrity metadata, not a signature.

No credential, grant, approval, production state or upstream world is changed by extracting this package.
