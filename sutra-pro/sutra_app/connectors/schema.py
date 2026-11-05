"""JSON-schema helpers for the connectors (connectors design 3.6, D33).

    to_json_schema(schema)       a pydantic class -> its transport schema (library `transport_schema`: closed objects,
                                 `const` kept as a one-value enum, `anyOf` for unions); a dict -> a checked copy
    strict_schema(schema)        what Codex's `--output-schema` wants: every object closed (`additionalProperties:false`),
                                 every property required, optional ones nullable, `default`/`title`/`examples` removed,
                                 `oneOf` as `anyOf`, `const` as a one-value enum, `definitions`/`$defs` kept. Idempotent.
                                 UNVERIFIED against the real API (a 400 about the schema degrades to the prompted path)
    minimal_validate(v, schema)  [errors]: type, required keys, primitive property types, enum, anyOf. Not a full validator
    example_from_schema(schema)  the smallest value that fits (required fields; first enum value; "stub"; 0; False; []; nested)
    schema_text / schema_sha / fits_native   the 100,000-character gate for the native path and a stable name for a schema

A map with free keys (`additionalProperties` that is itself a schema) cannot be made strict; `strict_schema` leaves such
an object as it is and the prompted path serves it.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping, Optional

from pydantic import BaseModel

from sutra_app.library.registry import RegistryError, transport_schema

from .errors import InvalidRequestError

__all__ = [
    "NATIVE_SCHEMA_MAX_CHARS", "to_json_schema", "strict_schema", "minimal_validate", "example_from_schema", "schema_text",
    "schema_sha", "fits_native", "resolve_ref",
]

NATIVE_SCHEMA_MAX_CHARS = 100_000        # a larger schema goes to the CLI in the prompt, not as a flag or file (D33)
_DROPPED = ("default", "title", "examples", "discriminator")
_TYPES = {"string": str, "boolean": bool, "null": type(None), "object": dict, "array": list}


# ---- to_json_schema ----------------------------------------------------------------------------------------------------

def to_json_schema(schema: "type[BaseModel] | Mapping[str, Any]") -> dict:
    """The JSON schema of a request's `schema`. A class goes through the library's `transport_schema`; a dict is checked
    (JSON-native, an object at the root) and copied. InvalidRequestError when the schema cannot be used."""
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        try:
            return transport_schema(schema)
        except RegistryError as e:
            raise InvalidRequestError(f"the schema of {schema.__name__} cannot be sent to a model: {e}") from None
    if not isinstance(schema, Mapping):
        raise InvalidRequestError(f"a schema must be a pydantic class or a dict, not {type(schema).__name__}")
    try:
        text = json.dumps(schema, allow_nan=False)
    except (TypeError, ValueError) as e:
        raise InvalidRequestError(f"the schema is not JSON: {e}") from None
    out = json.loads(text)
    if out.get("type") != "object" and "properties" not in out and not any(k in out for k in ("anyOf", "$ref")):
        raise InvalidRequestError("the schema must describe a JSON object at its root")
    return out


def schema_text(schema: Mapping[str, Any]) -> str:
    """Compact JSON of a schema, as it goes into a file or a prompt."""
    return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


def schema_sha(schema: Mapping[str, Any]) -> str:
    """A stable name for a schema (key order does not matter): the router's `native_blocked` is keyed by it."""
    return hashlib.sha256(json.dumps(schema, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def fits_native(schema: Mapping[str, Any]) -> bool:
    """True when the schema is small enough to go natively (under 100,000 characters)."""
    return len(schema_text(schema)) < NATIVE_SCHEMA_MAX_CHARS


def resolve_ref(ref: Any, root: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """The node a local `$ref` ("#/definitions/X" or "#/$defs/X", any local path) points to, else None."""
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return None
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, Mapping) else None


# ---- strict_schema -----------------------------------------------------------------------------------------------------

def strict_schema(schema: Mapping[str, Any]) -> dict:
    """A copy of `schema` in the strict form Codex's `--output-schema` takes (see the module docstring)."""
    return _strict(copy.deepcopy(dict(schema)))


def _strict(node: Any) -> Any:
    if isinstance(node, list):
        return [_strict(n) for n in node]
    if not isinstance(node, dict):
        return node
    for key in _DROPPED:
        node.pop(key, None)
    if "const" in node:
        node["enum"] = [node.pop("const")]
    if "oneOf" in node:
        node.setdefault("anyOf", []).extend(node.pop("oneOf"))
    for key in ("definitions", "$defs"):
        if isinstance(node.get(key), dict):
            node[key] = {name: _strict(sub) for name, sub in node[key].items()}
    for key in ("anyOf", "allOf"):
        if isinstance(node.get(key), list):
            node[key] = [_strict(sub) for sub in node[key]]
    if isinstance(node.get("items"), (dict, list)):
        node["items"] = _strict(node["items"])
    if isinstance(node.get("additionalProperties"), dict):
        node["additionalProperties"] = _strict(node["additionalProperties"])
    props = node.get("properties")
    if isinstance(props, dict) or node.get("type") == "object":
        free_keys = isinstance(node.get("additionalProperties"), dict) or node.get("additionalProperties") is True
        if props is None and free_keys:
            return node                         # a map with free keys: cannot be strict (module docstring)
        props = props if isinstance(props, dict) else {}
        required = set(node.get("required") or ())
        new_props = {}
        for name, sub in props.items():
            sub = _strict(sub)
            new_props[name] = sub if name in required else _nullable(sub)
        node["properties"] = new_props
        node["required"] = list(new_props)
        node["additionalProperties"] = False
    return node


def _nullable(sub: Any) -> Any:
    """`sub` or null. Already-nullable schemas are returned as they are, so strict_schema is idempotent."""
    if not isinstance(sub, dict):
        return sub
    kind = sub.get("type")
    if isinstance(kind, str):
        if kind == "null":
            return sub
        sub["type"] = [kind, "null"]
    elif isinstance(kind, list):
        if "null" not in kind:
            sub["type"] = [*kind, "null"]
    elif "anyOf" in sub:
        if not any(isinstance(b, dict) and b.get("type") == "null" for b in sub["anyOf"]):
            sub["anyOf"] = [*sub["anyOf"], {"type": "null"}]
        return sub
    else:
        return {"anyOf": [sub, {"type": "null"}]}       # a $ref, an enum without type, or an untyped schema
    if isinstance(sub.get("enum"), list) and None not in sub["enum"]:
        sub["enum"] = [*sub["enum"], None]
    return sub


# ---- minimal_validate --------------------------------------------------------------------------------------------------

def minimal_validate(value: Any, schema: Mapping[str, Any]) -> list[str]:
    """Error lines "path: message" (empty when the value fits). Checks `type`, `required`, `enum` and `anyOf`, and walks
    `properties`, `items` and local `$ref`s. Anything else in the schema (formats, lengths, patterns) is not checked: the
    model's own class or the caller's rules do that."""
    errors: list[str] = []
    _check(value, schema, schema, "", errors, 0)
    return errors


def _kind_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "an object"
    return type(value).__name__


def _is_type(value: Any, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool) or (isinstance(value, float) and value.is_integer())
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name]) if name in _TYPES else True


def _check(value: Any, node: Any, root: Mapping[str, Any], path: str, errors: list[str], depth: int) -> None:
    if not isinstance(node, Mapping) or depth > 24:
        return
    where = path or "reply"
    if "$ref" in node:
        target = resolve_ref(node["$ref"], root)
        if target is not None:
            _check(value, target, root, path, errors, depth + 1)
        return
    for key in ("anyOf", "oneOf"):
        if isinstance(node.get(key), list):
            branches = [b for b in node[key] if isinstance(b, Mapping)]
            if branches and not any(not _errors_of(value, b, root, path, depth) for b in branches):
                errors.append(f"{where}: does not match any of the allowed shapes")
            return
    if isinstance(node.get("allOf"), list):
        for sub in node["allOf"]:
            _check(value, sub, root, path, errors, depth + 1)
    if "const" in node and value != node["const"]:
        errors.append(f"{where}: must be {node['const']!r}")
        return
    if isinstance(node.get("enum"), list) and value not in node["enum"]:
        errors.append(f"{where}: must be one of {node['enum']!r}")
        return
    kind = node.get("type")
    if kind is not None:
        names = [kind] if isinstance(kind, str) else [k for k in kind if isinstance(k, str)]
        if names and not any(_is_type(value, n) for n in names):
            errors.append(f"{where}: must be {' or '.join(names)}, got {_kind_name(value)}")
            return
    if isinstance(value, dict):
        for name in node.get("required") or ():
            if name not in value:
                errors.append(f"{path + '.' if path else ''}{name}: is required")
        props = node.get("properties")
        if isinstance(props, Mapping):
            for name, sub in props.items():
                if name in value:
                    _check(value[name], sub, root, f"{path + '.' if path else ''}{name}", errors, depth + 1)
    elif isinstance(value, list) and isinstance(node.get("items"), Mapping):
        for i, item in enumerate(value):
            _check(item, node["items"], root, f"{path + '.' if path else ''}{i}", errors, depth + 1)


def _errors_of(value: Any, node: Mapping[str, Any], root: Mapping[str, Any], path: str, depth: int) -> list[str]:
    out: list[str] = []
    _check(value, node, root, path, out, depth + 1)
    return out


# ---- example_from_schema -----------------------------------------------------------------------------------------------

def example_from_schema(schema: "type[BaseModel] | Mapping[str, Any]") -> Any:
    """The smallest value that fits `schema` (a class: its own JSON schema, so only required fields appear). Strings are
    "stub" (padded or cut to the length limits), numbers 0 (moved into their bounds), booleans False, lists [] (or as long
    as `minItems` asks), enums their first value, `const` its value, unions their first non-null branch. For a class the
    result validates against it unless a pattern or a custom validator says otherwise."""
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        schema = schema.model_json_schema()
    if not isinstance(schema, Mapping):
        raise InvalidRequestError(f"a schema must be a pydantic class or a dict, not {type(schema).__name__}")
    return _example(schema, schema, 0)


def _example(node: Any, root: Mapping[str, Any], depth: int) -> Any:
    if not isinstance(node, Mapping) or depth > 12:
        return None
    if "$ref" in node:
        return _example(resolve_ref(node["$ref"], root), root, depth + 1)
    if "const" in node:
        return copy.deepcopy(node["const"])
    if isinstance(node.get("enum"), list) and node["enum"]:
        return copy.deepcopy(node["enum"][0])
    for key in ("anyOf", "oneOf"):
        if isinstance(node.get(key), list) and node[key]:
            options = [b for b in node[key] if isinstance(b, Mapping)]
            real = [b for b in options if b.get("type") != "null"] or options
            return _example(real[0], root, depth + 1)
    if isinstance(node.get("allOf"), list) and node["allOf"]:
        return _example(node["allOf"][0], root, depth + 1)
    kind = node.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), kind[0] if kind else None)
    if kind is None:
        kind = "object" if "properties" in node else ("array" if "items" in node else None)
    if kind == "object":
        props = node.get("properties") or {}
        return {name: _example(props[name], root, depth + 1) for name in node.get("required") or () if name in props}
    if kind == "array":
        count = int(node.get("minItems") or 0)
        return [_example(node.get("items"), root, depth + 1) for _ in range(count)]
    if kind == "string":
        text = "stub"
        low, high = node.get("minLength"), node.get("maxLength")
        if isinstance(low, int) and len(text) < low:
            text = text + "x" * (low - len(text))
        if isinstance(high, int) and len(text) > high:
            text = text[:high]
        return text
    if kind in ("integer", "number"):
        return _number(node, kind)
    if kind == "boolean":
        return False
    return None


def _number(node: Mapping[str, Any], kind: str) -> Any:
    number: float = 0
    low = node.get("minimum")
    if low is None and "exclusiveMinimum" in node:
        low = node["exclusiveMinimum"] + 1
    high = node.get("maximum")
    if high is None and "exclusiveMaximum" in node:
        high = node["exclusiveMaximum"] - 1
    if isinstance(low, (int, float)) and number < low:
        number = low
    if isinstance(high, (int, float)) and number > high:
        number = high
    return int(number) if kind == "integer" else number
