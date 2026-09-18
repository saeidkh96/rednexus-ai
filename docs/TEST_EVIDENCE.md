> RC1 historical reference. Current RC2 setup: [ECOSYSTEM_SETUP_FA.md](ECOSYSTEM_SETUP_FA.md); current integration evidence: [INTEGRATION_STATUS.md](INTEGRATION_STATUS.md).

# Validation evidence — 1.0.0-rc.1

Environment: Linux, Python 3.12.14. **61 passed, 2 skipped, 0 failed; 79.83% line coverage.** Current measured results are in `release-evidence.json` and `evidence/test-output.txt`; the JUnit and coverage files are included alongside them.

## Executed

- Lint: `python -m ruff check rednexus tests examples scripts`.
- Python source compilation and JavaScript syntax check (`node --check rednexus/static/app.js`).
- Full pytest suite with isolated temporary databases, real local HTTP, actual API/worker subprocesses, optional RedWorld source integration enabled, and coverage collection.
- Original v0.0.1 compatibility tests and original demo.
- New five-project fixture demo: authenticated identities, separate scripted test review, complete workflow and structural evaluation.
- RedWorld v1.4.0: actual supplied source, fresh local API process, snapshot/advance HTTP mapping, then a durable Nexus workflow with an authenticated test reviewer. Output ticks `[2, 3, 3]` after the initial two-step probe.
- CLI process path: migrate → bootstrap → start API → login → submit → worker process → completed state → backup → restore into a new database.

The RedWorld process used a new 50-citizen test world, not a user's existing live state. Its source is not vendored in this deliverable. The optional test uses `NEXUS_TEST_REDWORLD_SRC` to locate it.

## Important negative/recovery checks

Cross-workspace run, event and memory isolation; ownership restrictions; password hashing and login limit; expired/logout sessions; revoked identity/grants; separate human approval; action digest mismatch; rejected/expired review; reviewer permission revocation after approval; contract drift; read retry limit; tool/budget cap; cancelled and expired missions; concurrent worker claim; lease fencing; restart recovery; uncertain effectful action reconciliation; event deduplication and producer binding; outbox publish-after-crash duplication; memory version/expiry/deletion semantics; malformed/oversized HTTP output; HTTP absolute timeout; model proposal scope; replay without new tool calls.

## Not executed / skipped

Actual PostgreSQL and Redis service tests are skipped because those services were unavailable. Their explicit tests and CI service definitions are provided. An attempted local service installation could not run in this environment; no service execution success is claimed.

Browser visual/interaction validation did not run: a Chromium binary was unavailable and its download failed. HTML assets are served in the real API process and JavaScript syntax passes, but neither is a substitute for a browser test. PowerShell scripts and Windows/Python 3.14 were not executed here; CI definitions include those Python/OS gates.

No real RedPA, RedPulse, RedGuard or RedForge API was contacted. No live model endpoint, OTLP collector, production load test or independent security audit ran. Coverage is line coverage of pytest's process; CLI/server subprocess execution is verified behaviorally but not added to that process's coverage percentage.

The TestClient dependency chain emits deprecation warnings about httpx and AnyIO aliases. They do not fail the tests, and the warnings are retained in the evidence.

## Repeat locally

```powershell
.\.venv\Scripts\python.exe scripts/validate.py
```

Without optional services/source, their integration tests visibly skip. To repeat RedWorld verification, follow `REDWORLD_INTEGRATION.md`. To enable actual PostgreSQL/Redis tests, set `NEXUS_TEST_POSTGRES_URL` and `NEXUS_TEST_REDIS_URL` to dedicated test services; they create test data and must not point to production databases.
