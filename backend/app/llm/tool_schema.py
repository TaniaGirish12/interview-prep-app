"""Pydantic model → JSON Schema for a strict tool's input_schema.

Strict tool schemas accept only a subset of JSON Schema. Length, count and numeric
bounds are removed from the copy sent to the API; Pydantic still enforces them when
the result is validated, and a violation triggers the one validation retry.
"""

from typing import Any

from pydantic import BaseModel

UNSUPPORTED = {
    "minLength", "maxLength", "maxItems", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "default", "title",
}


def _strip(node: Any) -> Any:
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in UNSUPPORTED:
                continue
            if k == "minItems" and isinstance(v, int) and v > 1:
                out[k] = 1
                continue
            if k == "properties":  # keys here are field names, not keywords
                out[k] = {name: _strip(sub) for name, sub in v.items()}
                continue
            out[k] = _strip(v)
        return out
    if isinstance(node, list):
        return [_strip(v) for v in node]
    return node


def input_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = _strip(model.model_json_schema())
    schema.setdefault("additionalProperties", False)
    return schema


def tool_definition(model: type[BaseModel], name: str, description: str) -> dict[str, Any]:
    return {"name": name, "description": description, "input_schema": input_schema(model), "strict": True}
