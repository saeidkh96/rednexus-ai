"""Contract fixture only. Replace fixture handler with a domain-owned implementation.

Run: NEXUS_BRIDGE_TOKEN=<secret> python -m uvicorn examples.reference_bridge:app --port 8100
Windows: set $env:NEXUS_BRIDGE_TOKEN in PowerShell first.
"""

import hmac
import os
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

app = FastAPI(title="Nexus reference bridge — fixture, not a Red project")


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: str
    capability: str
    input: dict
    context: dict


@app.post("/execute")
def execute(command: Command, authorization: str = Header(default="")):
    secret = os.getenv("NEXUS_BRIDGE_TOKEN")
    if not secret or not hmac.compare_digest(authorization, "Bearer " + secret):
        raise HTTPException(401, "invalid service credential")
    if command.context.get("workspace") != os.getenv("NEXUS_BRIDGE_WORKSPACE", "red"):
        raise HTTPException(403, "workspace not permitted by this bridge")
    if command.capability != "reference.echo" or command.contract_version != "1.0.0":
        raise HTTPException(422, "unsupported capability or contract")
    return {
        "simulated": True,
        "evidence": [{"source": "reference-bridge-fixture"}],
        "received": command.input,
        "summary": "Authenticated contract fixture; no real project called.",
    }
