# Native integration evidence — 1.0.0-rc.2

Source: user-supplied `red-ecosystem-source.zip`. Projects remain separate repos.

| Project | Capability | Validation performed | Not established |
|---|---|---|---|
| RedPA | documents, chat | Request/response contract inspected in source; bearer-token, missing-token, rejected-request and malformed-response adapter tests | Full authenticated database + model/RAG execution |
| RedPulse 4.0.0 | analyze | Original v40 router and its real maintenance engine served over HTTP in an isolated FastAPI app | Full application with its database and other routers |
| RedGuard 1.0.0 | inspect | Original full app served over HTTP; scoring, artifact creation, persistence and lookup verified | Raw-image inference, model accuracy, multi-process persistence |
| RedForge 1.6.1 | scan | Original full app served over HTTP under Python 3.14.7; actual fixture repository scanned | Patch generation/application, command execution, autonomous delivery |
| RedWorld API 2.0.0 | snapshot, advance | Original full app; real local world; reviewed durable workflow completed | Large-population load or long-running simulation |

The existing RedWorld 1.4.0 manifest and contract tests remain supported. The new ecosystem manifest pins the uploaded API's 2.0.0 contract. The source package's own version strings are inconsistent; the adapter checks the world response version, not its package `__init__` string.

The native protocol names describe inspected source contracts. Only RedWorld reports an exact version in every operation response; the other mappings validate response shape and relevant request/result identifiers, not an independently proven deployment version.

No mock response is counted as live project verification. The RedPA protocol fixtures are intentionally listed separately. The integrated apps run in temporary directories and do not touch the user's stores or accounts.

## Changes

- Seven real HTTP capabilities with strict native mappings and workspace bindings.
- RedPA dedicated service credential; fixed operator repository path for RedForge.
- Human approval for all exposed native writes; no automatic replay of uncertain writes.
- Bounded source responses; explicit partial preview for repository scans.
- Mission editor accepts independent JSON inputs and displays input contracts.
- Local audited command upgrades an existing admin's manifest grants without resetting credentials.
- ECOSYSTEM.ps1 selects the same live manifest for the API and worker.

An ordered agent cannot infer domain input values from a free-text objective. It now returns an actionable error for native capabilities. Use explicit mission inputs, or configure the model planner and review its proposed inputs.

Cross-project execution uses explicit ordered steps. There is no invented conversion from maintenance risk to image scores, and there are no installed outbound event producers in the five source repos. Generic Nexus event ingestion, rules and durable workflows remain available for explicitly implemented producers.

## Reproduction

Install Nexus dev requirements in its own Python 3.12+ environment. For external-source tests, additionally install `pydantic-settings`, `numpy`, and `opencv-python-headless`. The original RedForge app must run in a separate Python 3.14+ environment with its API dependencies.

Set the following environment variables to local source directories/interpreters:

```text
NEXUS_TEST_ECOSYSTEM_ROOT=<directory containing redpa-ai, redguard-ai, redpulse-ai, redforge-ai, redworld-ai>
NEXUS_TEST_REDFORGE_PYTHON=<Python 3.14 environment executable>
NEXUS_TEST_REDWORLD_SRC=<ecosystem directory>/redworld-ai/src
NEXUS_TEST_REDWORLD_VERSION=2.0.0
```

Then run `python -m pytest -q`. External source projects are not vendored in this distribution. Without these variables, corresponding integration tests are skipped explicitly. PostgreSQL and Redis tests require their own configured test URLs.

## Release status

This is a release candidate, not a claim that the complete stable-v1 roadmap has passed acceptance. Remaining gates include full RedPA execution, full RedPulse deployment, PostgreSQL/Redis, browser and Windows validation. Model-provider and OTel collector integrations are also unverified. See `release-evidence.json` for current machine-readable evidence.
