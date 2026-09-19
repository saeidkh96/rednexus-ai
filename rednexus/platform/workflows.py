"""Deterministic data flow. No expressions, code evaluation or network resolution."""
import copy
import operator
from .contracts import canonical
from .identity import Problem
from .adapters import validate_payload


def pointer(value, path):
    if path == "":
        return value
    for token in path[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            value = value[token]
        elif isinstance(value, list) and token.isdecimal() and (token == "0" or not token.startswith("0")):
            value = value[int(token)]
        else:
            raise KeyError(path)
    return value


def resolve(ref, outputs):
    try:
        value = pointer(outputs[ref["step"]], ref.get("pointer", ""))
        return canonical(value) if ref.get("format") == "json" else copy.deepcopy(value)
    except (KeyError, IndexError, TypeError, ValueError):
        raise Problem(422, "binding_source_missing") from None


def condition_matches(condition, outputs):
    if not condition:
        return True
    try:
        actual = resolve(condition, outputs)
    except Problem:
        if condition["op"] == "exists":
            return False
        raise
    op = condition["op"]
    if op == "exists":
        return True
    expected = condition.get("value")
    if op in ("gt", "gte", "lt", "lte"):
        if type(actual) not in (int, float) or type(expected) not in (int, float):
            raise Problem(422, "condition_requires_numbers")
    operations = {"eq": operator.eq, "ne": operator.ne, "gt": operator.gt,
                  "gte": operator.ge, "lt": operator.lt, "lte": operator.le}
    return operations[op](actual, expected)


def input_for(step, outputs):
    payload = copy.deepcopy(step["input"])
    if step.get("use_previous"):
        payload["previous"] = copy.deepcopy(outputs[-1])
    for field, ref in step.get("bindings", {}).items():
        payload[field] = resolve(ref, outputs)
    return payload


def validate_static(schema, step):
    """Defer dynamic field validation, but validate constants immediately.

    Complex cross-field schemas are validated after binding, before approval/call.
    The full immutable contract is always kept in the plan.
    """
    dynamic = set(step.bindings)
    if step.use_previous:
        dynamic.add("previous")
    if not dynamic:
        return validate_payload(schema, step.input)
    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False and dynamic - set(properties):
        raise Problem(422, "binding targets unknown input fields")
    required = set(schema.get("required", [])) - dynamic
    if required - set(step.input):
        raise Problem(422, "required constant input field missing")
    for key, value in step.input.items():
        if key in properties:
            validate_payload(properties[key], value)
        elif schema.get("additionalProperties") is False:
            raise Problem(422, "unknown constant input field")
