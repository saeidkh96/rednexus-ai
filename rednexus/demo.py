"""All adapters in this demo are simulated; no external calls are made."""

import json
from .core import Capability, Nexus, Principal


def setup(nexus):
    capabilities = [
        ("redpulse.analyze", "redpulse", False),
        ("redpa.explain", "redpa", False),
        ("redguard.verify", "redguard", False),
        ("redworld.simulate", "redworld", False),
        ("redforge.propose_change", "redforge", True),
    ]
    for name, project, approval in capabilities:

        def mock(payload, previous, name=name):
            return {
                "adapter": name,
                "simulated": True,
                "input": payload,
                "previous_results": len(previous),
                "result": "demo evidence only",
            }

        nexus.register(Capability(name, project, "1.0.0", approval), mock)
    return capabilities


def main():
    nexus = Nexus()
    capabilities = setup(nexus)
    operator = Principal(
        "operator",
        "red",
        frozenset(
            ["workflow:run", "memory:workflow:write", "memory:workflow:read"]
            + [f"tool:{name}" for name, _, _ in capabilities]
        ),
    )
    reviewer = Principal("reviewer", "red", frozenset(["approval:review"]))
    steps = [{"capability": name, "input": {"scenario": "operations anomaly"}} for name, _, _ in capabilities]
    run_id = nexus.submit(operator, steps, "demo-001")
    while True:
        state = nexus.advance(operator, run_id)
        print(json.dumps({"run_id": run_id, "status": state["status"], "finished_steps": state["cursor"]}))
        if state["status"] == "waiting_approval":
            print("DEMO: a distinct simulated reviewer approves this exact step.")
            nexus.review(reviewer, run_id, True)
        elif state["status"] in {"completed", "failed", "rejected"}:
            break
    nexus.remember(operator, "workflow", run_id, state, f"run:{run_id}")
    print(
        json.dumps(
            {
                "registered_projects": len(nexus.discover()),
                "events": len(nexus.events(operator, run_id)),
                "memory_saved": nexus.recall(operator, "workflow", run_id) is not None,
            }
        )
    )
    nexus.close()


if __name__ == "__main__":
    main()
