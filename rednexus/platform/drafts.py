"""Reviewed workflow recipes. Creating a draft never executes a capability."""

from typing import Literal
from uuid import UUID
from pydantic import Field
from .contracts import Contract, RunInput
from .identity import Problem


class DraftInput(Contract):
    recipe: Literal["maintenance-high", "maintenance-low", "maintenance-explanation"]
    machine_id: str = Field(default="motor-07", min_length=1, max_length=200)
    conversation_id: UUID | None = None
    threshold: float = Field(default=0.5, ge=0, le=1)
    world_steps: int = Field(default=1, ge=1, le=10)


def build_draft(data: DraftInput):
    low = data.recipe == "maintenance-low"
    observation = {
        "machine_id": data.machine_id,
        "baseline": [0.18, 0.21, 0.19, 0.22],
        "current": [0.18, 0.21, 0.19, 0.22] if low else [0.62, 0.69, 0.66, 0.71],
        "drift_score": 0.0 if low else 0.72,
        "trajectory_match": 0.0 if low else 0.81,
        "uncertainty": 0.12,
    }
    steps = [{"capability": "redpulse.analyze", "input": observation}]
    if data.recipe == "maintenance-explanation":
        if not data.conversation_id:
            raise Problem(422, "An existing RedPA conversation UUID is required")
        steps.append(
            {
                "capability": "redpa.chat",
                "input": {"conversation_id": str(data.conversation_id)},
                "bindings": {"content": {"step": 0, "pointer": "", "format": "json"}},
            }
        )
        notes = [
            "The complete RedPulse output becomes the RedPA chat message after review.",
            "Use a dedicated conversation with a maintenance-analysis instruction.",
            "Model replies are not validated engineering advice. No world mutation occurs.",
        ]
    else:
        steps.append(
            {
                "capability": "redworld.advance",
                "input": {"steps": data.world_steps},
                "use_previous": True,
                "when": {"step": 0, "pointer": "/result/failure_risk", "op": "gte", "value": data.threshold},
            }
        )
        notes = [
            "World advance requires a different human reviewer.",
            "Risk controls the branch; it is not injected into the world economy.",
            "Low-risk fixtures still use the actual upstream score; inspect the result.",
        ]
    workflow = RunInput(title=f"{data.recipe}: {data.machine_id}", steps=steps)
    return {"workflow": workflow.model_dump(), "execution_started": False, "sample_observation": True, "notes": notes}
