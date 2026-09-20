# Live profile update validation — 2026-09-20

Base: user-supplied rednexus-current.zip, preserving the Windows lock and CLI timeout fixes.

- Linux / Python 3.12: `python -m pytest -q`: 100 passed, 7 skipped, 2 warnings (45.74s).
- `python -m ruff check .`: passed.
- New tests use HTTP MockTransport. They validate native endpoint mapping, risk conditions,
  context retention, read-only preflight and failure without demo fallback.
- Existing governance tests validate exact approval and conditional skipping.
- Windows PowerShell launchers were reviewed but not executed in this Linux environment.
- No access to the user's running services; no new live integration, Windows CI,
  RedPA chat completion or stable release claim is made.

Changes: shared START/WORKER ecosystem launcher; explicit default SQLite path;
RedPulse port 8002 in manifest/allowlists; preflight command; conditional live workflow;
honest RedWorld orchestration context; Persian installation/run guide.

Risk-to-world behavior: Nexus gates one world tick on failure_risk >= 0.5, then requires
human approval. RedWorld receives only its native steps parameter. The risk does not
alter the world's economic model. This is a demonstration orchestration policy.

Version remains 2.0.0rc1. Existing release evidence is not upgraded by these mock tests.
