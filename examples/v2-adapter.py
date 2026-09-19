"""Independent adapter example. Set ADAPTER_TOKEN and run with Uvicorn.

Deliberately simulated. Add origin, register contract and grant tool permission
in Nexus; give Nexus the same token via NEXUS_EXAMPLE_TOKEN.
"""
import os
from rednexus.adapter_sdk import adapter_app

SPEC = {
    "name": "example.inspect", "project": "example", "version": "1.0.0",
    "description": "Independent adapter example", "mode": "http", "protocol": "nexus",
    "workspace_binding": "red", "effect": "read", "approval": False,
    "endpoint": "http://127.0.0.1:8120/execute", "health_endpoint": "http://127.0.0.1:8120/health",
    "credential_env": "NEXUS_EXAMPLE_TOKEN",
    "input_schema": {"type": "object", "properties": {"subject": {"type": "string"}},
                     "required": ["subject"], "additionalProperties": False},
    "output_schema": {"type": "object", "required": ["simulated", "result", "evidence"]},
}


def inspect_subject(payload, context):
    return {"simulated": True, "result": {"subject": payload["subject"]},
            "evidence": [{"source": "example-fixture"}]}


app = adapter_app([SPEC], {SPEC["name"]: inspect_subject}, os.environ["ADAPTER_TOKEN"],
                  os.getenv("ADAPTER_RECEIPT_DB", "./data/adapter-receipts.db"))
