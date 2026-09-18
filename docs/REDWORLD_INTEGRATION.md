> RC1 historical reference. Current RC2 setup: [ECOSYSTEM_SETUP_FA.md](ECOSYSTEM_SETUP_FA.md); current integration evidence: [INTEGRATION_STATUS.md](INTEGRATION_STATUS.md).

# Real RedWorld v1.4.0 integration

The user's `redworld-ai-v1.4.0.zip` was inspected and its actual application was started in an isolated local process. Nexus's adapter was tested against that HTTP API, not a fixture. The independent RedWorld source was not modified or bundled into Nexus.

## Verified endpoints

| Nexus capability | Native RedWorld API | Effect |
|---|---|---|
| `redworld.snapshot` | GET `/api/v1/world` | Read current world summary |
| `redworld.advance` | POST `/api/v1/world/step?steps=N` | Advance the existing mutable world; requires approval |

Nexus bounds the step count to 1–10 (the native API allows more). This is not a branchable counterfactual-scenario API. The adapter verifies `world.version == "1.4.0"` and checks the tick/step result. The archive's package `__version__` still says `1.0.0`; its project metadata and world summary say `1.4.0`. Nexus checks the world summary contract.

`simulated: false` in the adapter response means the response came from the real project rather than a mock. Its `domain: simulation` field makes clear that the underlying world is still a simulation, not a prediction about reality.

## Executed verification

A fresh RedWorld instance with 50 citizens was started using the supplied source. Direct adapter reads showed tick 0; an explicit two-step call produced tick 2; a subsequent read confirmed tick 2. Then a Nexus mission ran snapshot → advance one step → snapshot. It paused for a separate authenticated test reviewer and completed with output ticks `[2, 3, 3]`.

This proves compatibility with the inspected source in an isolated local test. It does not change or verify a previously running world on the user's machine. No full RedWorld regression suite was run as part of this Nexus integration test.

## Activate locally

In the separate RedWorld project, use its own environment to start its existing API on loopback port 8100:

```powershell
# Run in your RedWorld project, with that project's dependencies installed:
python -m uvicorn redworld.api.main:app --app-dir src --host 127.0.0.1 --port 8100
```

In **both** Nexus API and worker terminals, set:

```powershell
$env:NEXUS_MANIFEST = 'config/projects-redworld-v140.json'
$env:NEXUS_ALLOWED_ORIGINS = 'http://127.0.0.1:8100'
$env:NEXUS_ALLOW_HTTP = 'true'
```

Then start Nexus API and worker normally. If you bootstrapped before switching the manifest, add `tool:redworld.snapshot` and `tool:redworld.advance` to the operator's workspace membership, and `review:redworld.advance` to a different human reviewer. Use a different workspace admin to change the original admin's grants, or bootstrap a dedicated new workspace with an appropriately bound manifest. Bootstrap never silently alters existing permissions.

For a new install, choose the RedWorld manifest **before** bootstrap so the first admin receives its capability grants. The manifest binds the native world to workspace `red`; change that explicit field if using a different workspace. A different workspace cannot see or execute the bound capability.

A one-step API submission looks like:

```json
{
  "title": "Read RedWorld",
  "steps": [{"capability": "redworld.snapshot", "input": {}}]
}
```

To advance, submit `redworld.advance` with input `{"steps": 1}`. Studio's basic builder can dispatch the default one step; custom step counts use the API or an edited workflow payload.

## Native limitations that the adapter does not hide

The inspected RedWorld API has no authentication or tenant separation and stores one mutable world in memory. Keep it on loopback or a private trusted network. This native mapping is explicitly bound to one Nexus workspace; it does not make RedWorld itself multi-tenant. It cannot protect a RedWorld endpoint that is independently exposed to other callers.

The native step endpoint does not implement idempotency or operation status lookup. Nexus therefore never retries its effectful call automatically. A lost response can leave an uncertain outcome requiring human review. The web viewer's live connection can also advance the world, so a tick difference alone is not definitive proof that one particular command ran when other clients are active. Prefer an isolated world instance for controlled Nexus workflows.

## Repeat the integration test

Install the optional integration dependencies in the Nexus test environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-integration.txt
$env:NEXUS_TEST_REDWORLD_SRC = 'C:\path\to\redworld-ai\src'
.\.venv\Scripts\python.exe -m pytest -q tests/test_redworld_adapter.py
```

The test starts a fresh local RedWorld process. It does not connect to the configured running world or touch its state. Without the explicit source path, this live test is skipped.
