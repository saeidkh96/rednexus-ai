"""Small client SDK for the versioned Nexus API. No hidden retries of writes."""

import time
from uuid import uuid4
import httpx


class NexusClient:
    def __init__(self, base_url, token, timeout=20):
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=False,
        )

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def validate(self, workflow):
        return self.request("POST", "/v2/validate", json=workflow)

    def discovery(self):
        return self.request("GET", "/v2/discovery")

    def save_template(self, name, workflow):
        return self.request("POST", "/v2/templates", json={"name": name, "workflow": workflow})

    def submit_group(self, group, idempotency_key=None):
        return self.request("POST", "/v2/mission-groups", json=group,
                            headers={"Idempotency-Key": idempotency_key or str(uuid4())})

    def semantic_search(self, namespace, query, limit=10):
        return self.request("POST", "/v2/memory/search", json={"namespace": namespace, "query": query, "limit": limit})

    def request(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def capabilities(self):
        return self.request("GET", "/v1/capabilities")

    def submit(self, workflow, idempotency_key=None):
        return self.request(
            "POST", "/v1/runs", json=workflow, headers={"Idempotency-Key": idempotency_key or str(uuid4())}
        )

    def inspect(self, run_id):
        return self.request("GET", f"/v1/runs/{run_id}")

    def emit(self, event):
        return self.request("POST", "/v1/events/ingest", json=event)

    def wait(self, run_id, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.inspect(run_id)
            if state["status"] not in {"queued", "running", "retry_wait"}:
                return state  # Returns pending approval; never approves automatically.
            time.sleep(0.5)
        raise TimeoutError("workflow wait deadline exceeded")
