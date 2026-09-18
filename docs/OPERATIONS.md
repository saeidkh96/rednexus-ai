# Operations runbook

## Local process model

Run from the repository root. `python -m rednexus.platform.cli migrate` creates the initial schema. Start API and worker separately. API defaults to loopback only. `health/live` checks the process; `health/ready` verifies database connectivity and schema access. It does not assert project or broker availability.

The manifest is read at startup. Restart both API and worker after a controlled configuration change. Configuration drift between their processes blocks affected runs rather than silently changing what executes. No default password is installed. Bootstrap requires a chosen password; `NEXUS_BOOTSTRAP_PASSWORD` can supply it in an automated trusted environment. Remove that variable after provisioning.

Native session tokens are one hour. Login again after expiry. Studio holds the token in memory, not localStorage; a full page reload intentionally requires login. API sessions are not sent as ambient cookies, and the app does not enable cross-origin API access.

## PostgreSQL and Redis with Docker Compose

1. Copy `.env.example` to `.env` and set a long random URL-safe `POSTGRES_PASSWORD`. Do not commit it.
2. Run `docker compose up --build -d`.
3. Run `docker compose exec api python -m rednexus.platform.cli bootstrap --workspace red --username saeid` and choose an admin password.
4. Open `http://127.0.0.1:8000`.
5. Inspect `docker compose logs api worker` if queued work does not advance.

PostgreSQL and Redis do not publish host ports. API publishes loopback port 8000. The application container runs as an unprivileged user. Compose persists PostgreSQL and Redis data in named volumes. `docker compose down` stops containers; do not add `-v` unless deleting those databases is explicitly intended.

This environment could not run Docker, PostgreSQL or Redis, so these definitions are supplied but unverified here. The CI service gate exercises actual PostgreSQL and Redis when run on a capable host. Do not mark those release gates passed before it succeeds.

For real HTTP adapters, add service origins and credential environment variables to **both** API and worker environment definitions. The sample Compose does not auto-forward every host variable. Do not put actual credentials in the manifest. The image does not contain `.env` or your database files.

## Backups and recovery

SQLite online backup uses SQLite's backup API:

```powershell
.\.venv\Scripts\python.exe -m rednexus.platform.cli backup C:\backups\nexus-backup.db
```

Choose a path whose parent directory exists. Existing backup paths are rejected. To restore, stop API/worker, choose a new database file and set `NEXUS_DATABASE_URL` to that destination before running:

```powershell
$env:NEXUS_DATABASE_URL = 'sqlite:///./data/restored-nexus.db'
.\.venv\Scripts\python.exe -m rednexus.platform.cli restore C:\backups\nexus-backup.db
.\.venv\Scripts\python.exe -m rednexus.platform.cli migrate
```

Restore refuses to overwrite an existing database. Validate integrity and review accounts before resuming work. Pending writes may have happened outside Nexus after the backup was taken: inspect domain operation IDs before starting the restored worker. Backups contain credentials hashes, sessions and data; apply your normal access and retention controls.

For PostgreSQL use `pg_dump --format=custom` and `pg_restore` into a new database. Take consistent infrastructure backups and retain the corresponding manifest version. PostgreSQL restore was not executed in this environment.

## Failure states

| State | Operator action |
|---|---|
| queued | Ensure worker uses the same database and manifest; check deadline |
| waiting_approval | Review exact payload with another authorized human |
| retry_wait | Bounded retry scheduled for a read; inspect dependency if repeated |
| blocked | Inspect missing grant, contract drift or budget; submit a corrected new workflow |
| failed | Inspect audit; fix cause; submit new workflow if appropriate |
| expired | Create a fresh mission and fresh approval; do not reuse stale approval |
| needs_reconciliation | Check actual domain operation using run/step idempotency key; independent admin records verified outcome |
| cancelled | No further dispatch; already-completed external work is not rolled back |

Reconcile through `POST /v1/runs/{id}/reconcile`, supplying `outcome`, `evidence` and, for success, schema-valid `output`. Allowed outcomes: `confirmed_succeeded`, `confirmed_failed`, `abandon`. The endpoint requires a different human admin with `review:<capability>`. This is not exposed as a one-click destructive Studio control.

## Event delivery and retention

Without `NEXUS_REDIS_URL`, local workflow execution still works; events remain in the transactional journal/outbox. With Redis configured, worker publishes pending events and consumes receipts. Broker outages are reported and do not delete pending events. Redis is not the canonical workflow queue: SQL owns execution state.

Malformed Redis envelopes go to `rednexus:deadletters:v1`. Pending entries can be reclaimed after 30 seconds. Keep one publisher/receipt loop initially; multiple publishers may create duplicate stream messages, which receipts deduplicate. No automatic stream/database retention is implemented. Plan trimming around consumer offsets, backups and recovery windows.

## Observability

`GET /v1/metrics` requires a workspace admin session and returns current run-status counts and outbox backlog. `GET /v1/audit` returns 200 recent events for that admin's workspace. Mission pages show their event timelines. Metrics are database-derived and survive process restart; they are not a full monitoring suite.

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to a trusted OTLP HTTP collector to enable API instrumentation, worker spans and outgoing trace headers. Secrets, model prompts and memory content are not added as span attributes by Nexus. Collector availability and exported traces have not been validated here. Secure and filter telemetry destinations as part of the chosen deployment.

## Configuration and capacity

`NEXUS_DATABASE_URL`, `NEXUS_MANIFEST`, `NEXUS_REDIS_URL`, `NEXUS_ALLOWED_ORIGINS`, `NEXUS_ALLOW_HTTP`, `NEXUS_MODEL_URL`, `NEXUS_MODEL_NAME`, `NEXUS_MODEL_API_KEY` are read by the CLI. `.env` is loaded by Compose, not the native Python CLI.

Limits: 20 steps per workflow; 64 KiB plan/result; 256 KiB HTTP request; maximum 80 tool calls; 100 active missions per workspace; configured HTTP timeout at most 60 seconds; 120-second worker lease; at most 4 attempts on reads; one-hour default session/approval; five model plans per five minutes per user/workspace. Exact run budgets are caller supplied within server model bounds. Estimated tool costs are reservations, not measured bills.

No autoscaling or high-availability guarantee is made. Before external hosting add TLS termination, trusted proxy configuration, IP/edge abuse controls, identity recovery/MFA as needed, backup schedules, network egress policy, dependency scanning and representative load tests. These are deployment work, not claims that this release has passed a production security audit.
