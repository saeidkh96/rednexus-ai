# Implemented architecture — 1.0.0-rc.1

The platform is a modular control plane and separate worker process. It does not merge domain repositories. The independent domain service owns its data and actions. The inspected native RedWorld API lacks authentication; its adapter is therefore bound to one workspace and requires a private instance, as documented in REDWORLD_INTEGRATION.md.

## Modules and boundaries

| Module | Responsibility |
|---|---|
| contracts | Strict request models, capability manifest and JSON schema validation |
| storage | PostgreSQL/SQLite tables, SQLAlchemy sessions, initial migration marker |
| identity | Scrypt hashes, opaque expiring sessions, current membership/grants |
| service | Missions, approvals, memory, inbound event rules, audit and evaluation |
| runtime | SQL queue claim, lease fencing, retries, recovery and cancellation |
| adapters | Demo fixtures and bounded HTTP calls to fixed operator-configured endpoints |
| events | Transactional outbox, Redis Streams publishing, receipt deduplication |
| agents | Scoped deterministic or model-based workflow proposal |
| api | Authenticated HTTP API, request bounds, Studio assets |
| telemetry | Optional OpenTelemetry export/instrumentation |
| sdk | HTTP client for external integrations |

The legacy `rednexus/core.py` and demo remain available for compatibility. They are not the authenticated platform and must not be exposed as a network API.

## Identity and permissions

A user can have multiple workspace memberships. Each token resolves its user and workspace from a hashed database record; request bodies cannot select another tenant after login. Membership and enabled state are checked on every authenticated request. Session lifetime is one hour by default, with explicit logout/revocation. Passwords use random salts and scrypt. Login limits are account-scoped, database-backed; deploy edge/IP controls for a public service.

Roles: admin manages workspace identities and reads workspace audit; operator creates workflows/agents/event rules; reviewer reviews authorized actions and can inspect workspace missions; viewer has no execution privilege. Admin and reviewer have workspace-wide mission visibility. Operator/viewer mission visibility is restricted to ownership. Exact `tool:<capability>`, `review:<capability>`, `memory:<namespace>:read/write` and `events:ingest` grants are separate from roles. Admin is intentionally not a tool wildcard.

Native shared identity is implemented. OIDC federation, MFA, password recovery and refresh-token flows are not implemented. Service identities authenticate through the same expiring login sessions and cannot approve; production credential lifecycle automation is future work.

## Execution correctness

Submission validates capabilities, grants, JSON inputs and bounded plan size. Plans snapshot the entire capability contract and a digest. Idempotency keys are scoped to workspace and owner; changed content with the same key is rejected. Each workspace permits at most 100 active missions.

The SQL queue uses conditional updates for atomic claim. A worker has a 120-second lease, while individual gateway calls are bounded to at most 60 seconds and the remaining mission deadline. Finishing requires the same unexpired lease token. Completed results and transition events commit in one transaction.

Read operations may retry with bounded exponential delay. A lost lease or error after an effectful call is treated as uncertain and requires reconciliation. No exactly-once external write guarantee is claimed. Cancellation stops queued work; an already-started call may complete. An unknown write outcome stays in reconciliation even if cancellation was requested.

A separate human admin with the review grant can reconcile using domain evidence and a verified result, record confirmed failure, or abandon. Reconciliation never retries the side effect. This is an audited human assertion; Nexus cannot independently prove an external service's result without its status API.

Execution is sequential, bounded to 20 steps. Parallel DAGs, distributed scheduler fairness and dynamically spawning agent swarms are not included. Multiple workers are supported through SQL claims; actual PostgreSQL concurrency still needs its service gate. SQLite is intended for local/small deployments, not a high-write multi-node cluster.

## Approval semantics

Approval binds the run, step, contract fingerprint and **resolved payload including the prior step's result**. It expires after one hour or at mission deadline, whichever comes first. The owner cannot approve the same workflow. Service accounts cannot supply human approval. A reviewer requires the exact review grant. Current owner and reviewer permissions are rechecked before dispatch. Contract drift blocks execution and requires a new workflow.

## Memory

Memory records have workspace, namespace, logical key, version, source, author and expiry. Retrieval authorizes namespace first and selects the newest version before applying TTL, deletion and query filters. Logical deletion redacts text and source across all versions of a key. Audit retains identifiers, not deleted content. Backups still contain historical bytes and need their own retention policy.

Search is lexical, not vector-semantic. It inspects up to 1,000 recent rows per namespace and returns at most 100 results; this is a documented local-scale bound. Domain semantic retrieval belongs to a configured RedPA capability, executed as a governed workflow. No full RedPA RAG stack is duplicated in Nexus. Embeddings, per-record ACLs, encryption-at-rest and automatic retention cleanup are not implemented; logical TTL prevents retrieval but does not automatically erase expired database rows.

## Events

Every domain transition emits a CloudEvents-shaped record in the same database transaction. Redis publication is asynchronous and at least once. A crash after publishing but before marking an outbox row can produce duplicates. Consumer receipts deduplicate event IDs; acknowledgements follow receipt commit. Stale pending Redis messages are reclaimed. Malformed envelopes go to a dead-letter stream without exposing the original payload.

The included Redis consumer records delivery receipts; it does not infer new tool calls from events. External project events enter through authenticated `/v1/events/ingest`. Explicit rules bind event type, source and producer identity to an owner's prevalidated workflow. Inbox deduplication and triggered workflow creation share one transaction. Producer payload can populate a named `event` data field, never permissions or workflow structure.

Streams and database audit are not auto-trimmed. Configure retention after consumer lag and recovery requirements are known.

## Agent runtime and cost

Agents have owner, workspace, allowed capability list, strategy and tool budget. Ordered strategy proposes the listed capabilities. Model strategy supports a configured chat-completions-compatible HTTP endpoint with bounded output tokens and five planning requests per user/workspace per five minutes. The configured model endpoint must pass the same fixed-origin allowlist. Model output is validated and cannot invent tools outside scope.

Plans do not execute automatically. The user submits the proposal as a normal immutable workflow. There are no self-issued grants or agent-created credentials. Token usage reported by the provider is recorded in a planning event. Tool costs are declared **estimated/reserved micro-units**, not actual monetary billing. Hard per-mission tool-call and reservation caps are enforced; provider billing reconciliation and a shared currency ledger are not included.

## Observability and evaluation

Run-correlated audit records, workspace status/outbox metrics, evidence-only replay and structural evaluation are implemented. Replay returns stored data and never calls tools. Evaluation checks completion, presence of evidence, simulated results and reserved budget; it is not a correctness judgment about a forecast, visual verification or simulation.

Optional OTel instrumentation exports API traces and worker spans; HTTP adapters propagate trace headers. Run IDs correlate the persisted queue boundary. The queue does not persist a full parent OTel span context, so API and worker traces are not a single continuous trace unless extended later. No public production SLO or load capacity is claimed.

## Reviewed primary references

- FastAPI security primitives: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/ (Nexus uses opaque server-side sessions rather than JWTs).
- SQLAlchemy core constructs: https://docs.sqlalchemy.org/en/20/core/selectable.html .
- HTTPX timeouts: https://www.python-httpx.org/advanced/timeouts/ . Absolute async deadlines additionally bound the complete call.
- Redis pending-entry recovery: https://redis.io/docs/latest/commands/xautoclaim/ .
- CloudEvents metadata: https://cloudevents.io/ .
- OpenTelemetry scope: https://opentelemetry.io/docs/what-is-opentelemetry/ .
