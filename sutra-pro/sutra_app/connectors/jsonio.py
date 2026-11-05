"""Reading a model's JSON reply: parse, validate, repair prompt, prune_nulls (connectors design 3.6, JSON strategy).

`extract_json` and `close_json` are NOT defined here: they are the library's objects (`sutra_app.library.replies`), the
one copy of J2's code (llm.py:268-295), imported so that `jsonio.extract_json is replies.extract_json` (S2-models-12,
S1-contracts-18). What this module adds is the connector's own part:

    parse_reply(text)               fence / brace slice / cut-off reply -> dict, else InvalidJsonError
    validate_reply(value, schema)   a pydantic class -> the instance; a dict schema -> `minimal_validate`; else InvalidJsonError
    parse_and_validate(text, schema)
    format_errors(exc)              "loc: msg; loc: msg" (J2's "Pydantic's own words", j2_artifact_models.errors_of)
    repair_prompt(prompt, errors, last_reply)   the stateless repair call's prompt (J2's pattern, j2.py:7086)
    prune_nulls(value, schema)      drop the nulls a strict (Codex) schema forced into optional fields

Business rules are never checked here: callers use `ReplyParser` and their own retries (library design F4).
"""
from __future__ import annotations

import copy
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ValidationError

from sutra_app.library.replies import close_json, extract_json

from .errors import InvalidJsonError
from .schema import minimal_validate, resolve_ref

__all__ = [
    "extract_json", "close_json", "parse_reply", "validate_reply", "parse_and_validate", "format_errors", "repair_prompt",
    "prune_nulls", "MAX_ERRORS_CHARS", "MAX_LAST_REPLY_CHARS", "MAX_ERROR_DETAIL",
]

MAX_ERRORS_CHARS = 1500        # the errors quoted in a repair prompt
MAX_LAST_REPLY_CHARS = 3000    # the rejected reply quoted in a repair prompt
MAX_ERROR_DETAIL = 500         # InvalidJsonError keeps the first 500 characters of the errors


def format_errors(exc: BaseException) -> str:
    """Pydantic's own words as "loc: msg; loc: msg"; a location-less error says "reply"."""
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors():
            where = ".".join(str(x) for x in err.get("loc") or ()) or "reply"
            parts.append(f"{where}: {err.get('msg')}")
        return "; ".join(parts) or "reply: not valid"
    return (str(exc).splitlines() or ["reply: not valid"])[0]


def parse_reply(text: str) -> dict:
    """The JSON object in a model's reply (fenced, sliced from the first `{` to the last `}`, or closed when the reply was
    cut off). InvalidJsonError when there is none or it cannot be read."""
    try:
        found = extract_json(text or "")
    except ValueError as e:                  # includes json.JSONDecodeError
        raise InvalidJsonError(f"reply: not one JSON object ({str(e).splitlines()[0][:200]})") from None
    if not isinstance(found, dict):
        raise InvalidJsonError("reply: the JSON is not an object")
    return found


def validate_reply(value: Any, schema: "type[BaseModel] | dict | None") -> Any:
    """`schema` a pydantic class: the validated instance. A dict schema: `value` itself after `minimal_validate`.
    None: `value` unchanged. Errors raise InvalidJsonError with the first 500 characters of "loc: msg; ..."."""
    if schema is None:
        return value
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        try:
            return schema.model_validate(value)
        except ValidationError as e:
            raise InvalidJsonError(format_errors(e)[:MAX_ERROR_DETAIL]) from None
    if isinstance(schema, Mapping):
        errors = minimal_validate(value, schema)
        if errors:
            raise InvalidJsonError("; ".join(errors)[:MAX_ERROR_DETAIL])
        return value
    raise TypeError(f"schema must be a pydantic class, a dict or None, not {type(schema).__name__}")


def parse_and_validate(text: str, schema: "type[BaseModel] | dict | None" = None) -> Any:
    return validate_reply(parse_reply(text), schema)


def repair_prompt(prompt: str, errors: str, last_reply: str) -> str:
    """The prompt of a stateless repair call: the original prompt, why the last reply was rejected (1,500 characters at
    most), the last reply (3,000 at most) and the instruction to answer again with one JSON object."""
    return (f"{prompt}\nYOUR LAST REPLY WAS REJECTED: {(errors or '')[:MAX_ERRORS_CHARS]}\n"
            f"YOUR LAST REPLY WAS:\n{(last_reply or '')[:MAX_LAST_REPLY_CHARS]}\n"
            "Reply again with one JSON object only.")


# ---- prune_nulls -------------------------------------------------------------------------------------------------------

def prune_nulls(value: Any, schema: "type[BaseModel] | dict | None" = None) -> Any:
    """A copy of `value` without the nulls a strict schema forced in.

    Codex's strict schema (`schema.strict_schema`) makes every optional property required and nullable, so the model
    answers `null` for what it would have left out, and a `null` defeats the field's default. With the ORIGINAL schema
    (the class, or the dict before `strict_schema`) only a null at a property that is NOT required is dropped; a required
    property keeps its null, so validation still sees it. Without a schema every null dict value is dropped. Where the
    schema cannot be followed (an unresolvable `$ref`, a union with no matching branch) that level is left as it is."""
    if schema is None:
        return _prune_all(copy.deepcopy(value))
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        schema = schema.model_json_schema()
    root = schema
    return _prune(copy.deepcopy(value), schema, root, 0)


def _prune_all(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _prune_all(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_prune_all(v) for v in value]
    return value


def _branch(node: Mapping[str, Any], value: Any, root: Mapping[str, Any], depth: int) -> Optional[Mapping[str, Any]]:
    """The schema node that describes `value`: `$ref` followed, `allOf` taken as its first member, a union resolved to the
    first branch whose properties include every key of a dict value. None when it cannot be told."""
    if depth > 12:
        return None
    if "$ref" in node:
        target = resolve_ref(node["$ref"], root)
        return _branch(target, value, root, depth + 1) if target is not None else None
    if "allOf" in node and node["allOf"]:
        return _branch(node["allOf"][0], value, root, depth + 1)
    for key in ("anyOf", "oneOf"):
        if key in node:
            for option in node[key]:
                got = _branch(option, value, root, depth + 1)
                if got is None:
                    continue
                if isinstance(value, dict):
                    props = got.get("properties")
                    if isinstance(props, Mapping) and all(k in props for k in value):
                        return got
                elif isinstance(value, list) and (got.get("type") == "array" or "items" in got):
                    return got
            return None
    return node


def _prune(value: Any, node: Mapping[str, Any], root: Mapping[str, Any], depth: int) -> Any:
    if depth > 24 or not isinstance(node, Mapping):
        return value
    node = _branch(node, value, root, 0)
    if node is None:
        return value
    if isinstance(value, dict):
        props = node.get("properties") or {}
        required = set(node.get("required") or ())
        out = {}
        for key, item in value.items():
            if item is None and key in props and key not in required:
                continue
            out[key] = _prune(item, props[key], root, depth + 1) if key in props else item
        return out
    if isinstance(value, list):
        items = node.get("items")
        if isinstance(items, Mapping):
            return [_prune(v, items, root, depth + 1) for v in value]
    return value
