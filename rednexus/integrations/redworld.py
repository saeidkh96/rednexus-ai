"""HTTP mapping verified against the supplied RedWorld v1.4.0 source archive.

RedWorld's native API has one mutable world and no authentication/tenant checks.
Keep that service private and bind this capability to one Nexus workspace.
"""

from rednexus.platform.adapters import AdapterFailure, bounded_request


async def execute_redworld(spec, payload, context, headers, transport=None):
    expected_version = "2.0.0" if spec.protocol == "redworld_v200" else "1.4.0"
    if context["workspace"] != spec.workspace_binding:
        raise AdapterFailure("redworld_workspace_binding_mismatch")
    if spec.name == "redworld.snapshot":
        data = await bounded_request("GET", spec.endpoint, None, headers, spec.timeout_seconds, transport)
        world = data
        advanced = 0
    elif spec.name == "redworld.advance":
        steps = payload.get("steps", 1)
        if type(steps) is not int or not 1 <= steps <= 10:
            raise AdapterFailure("redworld_steps_out_of_bounds")
        data = await bounded_request(
            "POST",
            spec.endpoint.rstrip("/") + "/step",
            None,
            headers,
            spec.timeout_seconds,
            transport,
            params={"steps": steps},
        )
        world = data.get("world") if isinstance(data, dict) else None
        advanced = data.get("stepped") if isinstance(data, dict) else None
        if advanced != steps:
            raise AdapterFailure("redworld_step_result_mismatch")
    else:
        raise AdapterFailure("redworld_unsupported_capability")
    if not isinstance(world, dict) or world.get("version") != expected_version or type(world.get("tick")) is not int:
        raise AdapterFailure("redworld_version_or_contract_mismatch")
    return {
        "simulated": False,
        "domain": "simulation",
        "project": "redworld",
        "project_version": expected_version,
        "summary": f"RedWorld at tick {world['tick']}; advanced {advanced} steps",
        "world": world,
        "advanced_steps": advanced,
        "orchestration_context": {
            "previous": payload.get("previous"),
            "objective": payload.get("objective"),
            "applied_to_world_model": False,
        },
        "evidence": [{"source": spec.endpoint, "world_tick": world["tick"], "kind": "live_project_api"}],
    }
