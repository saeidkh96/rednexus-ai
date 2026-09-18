"""Native endpoint contracts inspected in the user-supplied ecosystem sources.

Private services and dedicated RedPA accounts are bound to one Nexus workspace.
These mappings do not imply that an upstream implements Nexus identity delegation.
"""
from jsonschema import Draft202012Validator


def obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required,
            "additionalProperties": False}


TEXT = {"type": "string", "minLength": 1, "maxLength": 200}
SCORE = {"type": "number", "minimum": 0, "maximum": 1}
VECTOR = {"type": "array", "items": {"type": "number"}, "minItems": 1, "maxItems": 512}
# name -> (protocol, project, effect, method, path, input, required output fields)
OPERATIONS = {
    "redpulse.analyze": ("redpulse_v400", "redpulse", "read", "POST", "/api/v1/platform/v40/intelligence/evaluate",
        obj({"machine_id": TEXT, "baseline": VECTOR, "current": VECTOR, "drift_score": SCORE,
             "trajectory_match": SCORE, "uncertainty": SCORE},
            ["machine_id", "baseline", "current", "drift_score", "trajectory_match"]),
        {"machine_id": TEXT, "failure_risk": SCORE, "health_score": {"type": "number", "minimum": 0, "maximum": 100},
         "confidence": SCORE, "evidence": {"type": "array"}, "maintenance_priority": TEXT}),
    "redguard.inspect": ("redguard_v100", "redguard", "write", "POST", "/api/v1/inspections",
        obj({"component_id": TEXT, "component_type": TEXT, **{key: SCORE for key in
            ("change_score", "fingerprint_similarity", "anomaly_score", "edge_difference", "texture_difference", "reference_consensus")}}),
        {"inspection_id": TEXT, "component_id": TEXT, "decision": TEXT, "severity": TEXT,
         "risk_score": {"type": "number"}, "confidence": SCORE, "evidence": {"type": "array"}}),
    "redforge.scan": ("redforge_v161", "redforge", "read", "POST", "/api/v1/repository/scan", obj({}),
        {"root": TEXT, "name": TEXT, "total_files": {"type": "integer", "minimum": 0}, "files": {"type": "array"}}),
    "redpa.documents": ("redpa_v191", "redpa", "read", "GET", "/api/v1/documents", obj({}), None),
    "redpa.chat": ("redpa_v191", "redpa", "write", "POST", "/api/v1/chat",
        obj({"conversation_id": {"type": "string", "pattern": "^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$"},
             "content": {"type": "string", "minLength": 1, "maxLength": 16000, "pattern": "\\S"}}),
        {"conversation_id": TEXT, "user_message": {"type": "object"},
         "assistant_message": {"type": "object", "required": ["content"], "properties": {"content": {"type": "string"}}}, "model": TEXT}),
}


def validate_native_spec(spec):
    from urllib.parse import urlsplit
    if spec.name not in OPERATIONS:
        raise ValueError("unsupported native capability")
    protocol, project, effect, _, path, _, _ = OPERATIONS[spec.name]
    if (spec.protocol, spec.project, spec.effect) != (protocol, project, effect) or not spec.workspace_binding:
        raise ValueError("native capability requires matching protocol, project, effect and workspace binding")
    if spec.mode == "http" and urlsplit(spec.endpoint).path != path:
        raise ValueError("native endpoint path mismatch")
    if project == "redpa" and not spec.credential_env:
        raise ValueError("RedPA requires a dedicated account credential")
    if project == "redforge" and not spec.resource_binding:
        raise ValueError("RedForge requires an operator-configured repository path")


async def execute_native(spec, payload, context, headers, transport=None):
    from rednexus.platform.adapters import AdapterFailure, bounded_request, validate_payload
    _, project, _, method, _, schema, fields = OPERATIONS[spec.name]
    validate_payload(schema, payload)  # Cannot be weakened by changing the manifest.
    if project == "redpulse" and len(payload["baseline"]) != len(payload["current"]):
        raise AdapterFailure("redpulse_vector_dimensions_mismatch")
    body = {"path": spec.resource_binding} if project == "redforge" else payload
    data = await bounded_request(method, spec.endpoint, body if method == "POST" else None,
                                 headers, spec.timeout_seconds, transport, max_bytes=1048576 if project == "redforge" else 65536)
    output = ({"type": "object", "required": list(fields), "properties": fields} if fields else
              {"type": "array", "items": {"type": "object", "required": ["id", "filename", "status"]}})
    if not Draft202012Validator(output).is_valid(data):
        raise AdapterFailure("native_upstream_contract_violation")
    if project == "redforge":
        # Full source inventory can exceed the workflow result limit. Keep a bounded,
        # explicitly partial file preview, with the original total counts.
        files = [{"path": str(item.get("path", ""))[:500], "language": str(item.get("language", ""))[:80]}
                 for item in data["files"][:50] if isinstance(item, dict)]
        data = {key: data[key] for key in ("root", "name", "total_files")}
        data.update(files=files, files_preview_truncated=data["total_files"] > len(files))
    if spec.name == "redpa.chat" and data["conversation_id"].lower() != payload["conversation_id"].lower():
        raise AdapterFailure("redpa_conversation_mismatch")
    if project == "redpulse" and data["machine_id"] != payload["machine_id"]:
        raise AdapterFailure("redpulse_machine_mismatch")
    if project == "redguard" and data["component_id"] != payload["component_id"]:
        raise AdapterFailure("redguard_component_mismatch")
    return {"simulated": False, "project": project, "summary": f"Native {spec.name} completed",
            "result": data, "evidence": [{"source": spec.endpoint, "kind": "live_project_api"}]}
