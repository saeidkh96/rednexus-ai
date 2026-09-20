# RC2 validation — 2026-09-20

Executed on Linux / Python 3.12.3 against the delivered Nexus source.

- Full suite: **115 passed, 7 skipped, 0 failed**; two dependency deprecation warnings.
- Ruff (`rednexus tests scripts`): passed.
- CLI isolated API/worker/database backup test: included and passed.
- Demo: passed; this is explicitly demo evidence.
- JavaScript syntax: app.js, v2.js, roadmap.js passed Node syntax checks.
- OpenAPI and contract files regenerated successfully.
- Source ZIP integrity and per-file hashes verified by package_release.py.

## Added acceptance

Native HTTP transport fixtures plus actual worker/database/auth/reviewer code verify:
low-risk skip without a write/approval; high-risk waiting then approved completion;
review rejection without a write; exact earlier output becomes reviewed RedPA chat content;
bounded read retries; uncertain write stops without retry; worker recreation resumes approved work;
expired write lease fences late results; revoked reviewer blocks the write;
workflow drafts execute nothing and do not grant access; evidence export respects workspace access;
non-object Redis envelopes are dead-lettered instead of crashing the consumer.

These are not calls to the user's deployed upstream services.

## User-reported live evidence (separate from automated results)

The supplied local execution `fc0bd205` completed 2/2:
RedPulse at port 8002 returned risk 0.7673901451, followed by a reviewed RedWorld advance at port 8100 to tick 1.
The prior Pulse output was preserved; `applied_to_world_model` was false.
This happened before RC2 and does not certify every new UI path or the RedPA semantic recipe.

## Unverified gates

Seven suite skips: three supplied-source native integrations (Pulse/Guard/Forge),
one RedWorld source integration, PostgreSQL, Redis, and browser.
Chromium installation was attempted but failed with HTTP 502/timeouts, so no rendered-browser pass is claimed.
The expanded browser regression is included in CI; Windows, DPAPI and PowerShell upgrade require target validation.
PostgreSQL replacement-worker/fencing checks are included but were not run locally.
Live RedPA explanation/model, embedding provider and OTel collector were not available.
No production readiness, domain-model accuracy or throughput guarantee is made.

See acceptance-report.json for automated machine-readable results and release-evidence.json for stable gates.
