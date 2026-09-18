# RedNexus AI

**One ecosystem. Independent intelligence. Governed execution.**

RedNexus AI is the central orchestration platform for the **Red ecosystem**. It connects specialized AI projects through versioned capabilities, shared workflow state, scoped memory, permissions, events, and human approval.

Each project retains its own repository, runtime, data, and release lifecycle. RedNexus coordinates their exposed capabilities through APIs and adapters; it does not merge their codebases or replace their internal systems.

> **Status: v1.0 release-candidate / integration preview.** Local live workflows have been exercised across all five current Red projects. This does not establish production readiness or completion of every stable-release gate. See [release status](docs/RELEASE_STATUS.md).

## The Red ecosystem

| Project | Domain | Current Nexus integration scope |
| --- | --- | --- |
| **RedPA AI** | Knowledge, RAG, and agentic AI | List accessible documents; send a message in an existing conversation |
| **RedGuard AI** | Computer vision and verification | Persist an inspection from supplied image-analysis scores, not raw images |
| **RedPulse AI** | Prediction and operations intelligence | Evaluate maintenance risk from baseline and current vectors |
| **RedForge AI** | Autonomous software engineering | Read an operator-bound repository's structure; no code execution or patch application |
| **RedWorld AI** | Society and world simulation | Read a world snapshot; advance the simulation after human approval |

These are bounded integration surfaces, not access to every feature of each project. Future Red projects can join through the same capability-and-adapter model.

## Platform capabilities

- **Identity and permissions:** workspace memberships, human/service identities, roles, and explicit capability grants.
- **Durable orchestration:** persisted plans and execution state, a SQL-backed queue, worker leases, deadlines, cancellation, and reconciliation.
- **Human approval:** review bound to the capability contract and exact resolved input, with expiry and permission revalidation.
- **Agent runtime:** agent definitions, deterministic or configured model planning, explicit proposal submission, and execution budgets.
- **Scoped memory:** namespace isolation, versions, provenance, TTL, lexical retrieval, and logical deletion/redaction.
- **Events:** authenticated inbound events, producer-bound workflow rules, inbox deduplication, and Redis Streams outbox delivery.
- **Capability contracts:** input/output validation, fixed-origin HTTP access, timeouts, response limits, and environment-based credentials.
- **Observability:** execution timelines, audit records, structural evaluations, evidence-only replay, metrics, and optional OpenTelemetry tracing.
- **Nexus Studio:** a web interface for missions, approvals, capabilities, agents, memory, and workspace management.

Shared identity and memory are Nexus-level controls. They do not automatically synchronize every project's user database or memory store.

## Architecture

The control layer accepts missions, resolves registered capabilities, validates inputs and permissions, and persists an immutable workflow plan. Workers claim work, enforce approval and budget checks, invoke project adapters, and record results and evidence.

| Layer | Responsibility |
| --- | --- |
| Studio, API, CLI, and Python SDK | Submit work and inspect execution |
| Nexus Core and Agent Runtime | Planning, authorization, approval, queueing, and lifecycle management |
| Persistence, Memory, and Events | Durable state, scoped knowledge, audit history, and event delivery |
| Capability Registry and Adapters | Versioned contracts and controlled access to independent services |
| Red project services | Domain-specific computation and project-owned data |

The implementation uses FastAPI, SQLAlchemy with SQLite/PostgreSQL support, Redis Streams, and a same-origin Studio with no JavaScript build step. Docker Compose and CI definitions are included.

Discovery currently relies on configured manifests. Automatic service discovery and health-aware routing remain roadmap items.

## Local integration evidence

These results were observed in the operator's Windows environment during September 2026. They are manual smoke-test evidence, not a fresh automated verification by this README update.

| Capability | Observed result |
| --- | --- |
| RedPulse maintenance evaluation | Mission completed |
| `redworld.snapshot` | Mission completed |
| `redworld.advance` | Waited for approval, then completed after a separate reviewer approved |
| RedGuard inspection | Mission completed |
| `redforge.scan` | Completed with a real repository listing and `simulated: false` |
| `redpa.documents` | Completed against the live API with `simulated: false`; returned an empty document list |
| `redpa.chat` | Registered; successful end-to-end execution has not yet been demonstrated |

An empty document list confirms a successful listing request, not document ingestion or RAG quality. Individual service tests do not establish a complete cross-project workflow.

## Quick start: demo mode

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m rednexus.platform.cli migrate
.\.venv\Scripts\python.exe -m rednexus.platform.cli bootstrap --workspace red --username nexus-admin
.\.venv\Scripts\python.exe -m rednexus.platform.cli serve
```

Choose your own password when prompted. There are no default credentials. Bootstrap creates the initial account; do not repeat it on every startup.

In a second PowerShell window, from the same directory:

```powershell
.\.venv\Scripts\python.exe -m rednexus.platform.cli worker
```

Open [Nexus Studio](http://127.0.0.1:8000). Sign in with workspace `red`, username `nexus-admin`, and your chosen password.

The default manifest uses explicitly labeled demo adapters. These direct Python commands do not require changing PowerShell script execution policy. The default database is `data/nexus-v1.db`.

For an isolated scripted demonstration:

```powershell
.\.venv\Scripts\python.exe -m rednexus.platform.cli demo
```

The demo uses temporary SQLite, fixture accounts, and a simulated reviewer. It is not evidence of a live project connection.

## Connect the live ecosystem

Follow [the ecosystem setup guide](docs/ECOSYSTEM_SETUP_FA.md) and configure `config/projects-ecosystem.json`. Start each live project separately with its own dependencies and environment.

The tested local setup uses:

| Service | Address |
| --- | --- |
| Nexus Studio / API | `http://127.0.0.1:8000` |
| RedPA backend | `http://127.0.0.1:8111` — Docker host port mapped to container port `8000` |
| RedPA frontend | `http://127.0.0.1:3001` |
| RedPulse backend | `http://127.0.0.1:8113` |

These are local setup values, not universal defaults. Other endpoints and repository bindings are defined in the manifests and integration guides. Inside Docker, `127.0.0.1` refers to the current container, not the host or another service.

For an already configured ecosystem installation, use separate PowerShell windows:

```powershell
# Window 1: API and Studio
.\ECOSYSTEM.ps1 -Action serve
```

```powershell
# Window 2: worker
.\ECOSYSTEM.ps1 -Action worker
```

Review scripts before running them and follow your machine's execution policy. Do not start another API process on the same port. For local troubleshooting, keep one worker running so an older worker cannot claim jobs with stale configuration or missing credentials.

### Credentials and approvals

- RedPA capabilities require `NEXUS_REDPA_TOKEN` in the environment of the executing worker. Setting it in another terminal does not update an existing worker.
- Use the target service's supported authentication flow, preferably with a dedicated least-privilege account. Browser sessions and tokens from another authentication surface are not necessarily interchangeable.
- Tokens can expire; a successful setup test does not guarantee later requests will remain authenticated.
- Keep passwords, tokens, private keys, runtime databases, and local data out of commits and diagnostic screenshots. `.env.example` must contain placeholders only.
- Create a separate reviewer with the required `review:<capability>` grant. An administrator role alone does not replace explicit tool/review permissions.
- Registered capabilities are configuration, not proof of availability. Test each connection before composing a larger workflow.

## Validation

```powershell
.\.venv\Scripts\python.exe scripts/validate.py
.\.venv\Scripts\python.exe scripts/check_release.py
```

The validator checks the local implementation. The release checker is designed to exit with code `2` while required stable-release gates are missing. Passing unit tests alone does not establish live integration correctness or production safety.

The original foundation remains available:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m rednexus.demo
```

## Repository layout

| Path | Contents |
| --- | --- |
| `rednexus/platform/` | API, identity, orchestration, agents, storage, events, and telemetry |
| `rednexus/integrations/` | Project-specific API mappings and adapters |
| `rednexus/static/` | Nexus Studio interface |
| `rednexus/sdk.py` | Python client SDK |
| `config/` | Capability manifests and example inputs |
| `contracts/` | JSON schemas and exported OpenAPI contract |
| `tests/` | Automated tests |
| `scripts/` | Validation, release checks, upgrades, and contract export |
| `examples/` | Example missions, manifests, and a fixture bridge |
| `docs/` | Architecture, operations, integration guides, and release evidence |

## Limitations and next milestones

Current boundaries:

- This is an integration preview, not a verified stable v1.0.0 release.
- PostgreSQL/Redis service gates and deployment-specific checks still need evidence from their target environments.
- Memory retrieval is lexical; a shared semantic/vector memory layer is not implied.
- Evidence replay inspects recorded execution rather than repeating external side effects.
- RedForge integration scans repositories; it does not expose the full issue-to-PR engineering pipeline.
- Secrets remain environment-based; managed service credentials and renewal need further work.

Next milestones:

1. Harden service authentication, credential renewal, and startup diagnostics.
2. Validate `redpa.chat` with a real conversation and its human-approval path.
3. Verify a cross-project workflow with explicit data mappings and approval boundaries.
4. Add health-aware discovery and clearer service/worker diagnostics in Studio.
5. Complete infrastructure, security, recovery, and release gates before declaring a stable release.

See the [roadmap](docs/ROADMAP.md) and [integration checklist](docs/INTEGRATION_CHECKLIST.md).

## Upgrading from v0.0.1

Stop running processes and back up the installation. Preserve `.env`, `.venv`, `.git`, database files, and `data/`.

The legacy `rednexus.core` and `rednexus.demo` modules remain available. The platform uses separate `nx_` tables; legacy run records are not automatically imported. Reinstall dependencies and run migration before restarting.

See [the upgrade guide](docs/UPGRADE_AND_RUN_FA.md) for the full procedure.

## Documentation

- [Documentation index](docs/README.md)
- [Architecture blueprint](docs/BLUEPRINT.md)
- [Adapter guide](docs/ADAPTER_GUIDE.md)
- [Operations](docs/OPERATIONS.md)
- [Ecosystem setup — فارسی](docs/ECOSYSTEM_SETUP_FA.md)
- [RedWorld integration](docs/REDWORLD_INTEGRATION.md)
- [Release status](docs/RELEASE_STATUS.md)

`examples/reference_bridge.py` is a fixture bridge, not a replacement implementation of any Red project.

## License

License selection is pending. This README does not grant a license or declare the project open source. A separate `LICENSE` file will define the project's terms once finalized by the owner.

---

Created by **Saeid Khalilian** — RedNexus AI, the orchestration core of the Red ecosystem.
