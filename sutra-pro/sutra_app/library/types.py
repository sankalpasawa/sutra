"""Scalars, id patterns, the function names, `Violation`, `DomainEvent` and the id helpers (library design 3.2).

This is the one place that knows how ids are written:

    chart node      sales                 (NodeId)
    function node   sales.identity        function_node_id(dept_id, function)
    function atom   a-3f9a1c2b7d-01       function_atom_id(atom_sid(run_id, node_id), n)
    J2 atom         W-1.a2                (a J2 workflow atom, built by J2, never here)
    overhead key    a-<sid>-01            overhead_atom_id(owner_ref): the accounting key of a call made outside any
                                          function turn; it has no `atoms` row and is not a third id scheme

Patterns are written with `[0-9]` (never `\\d`, which also matches non-ASCII digits) and checked with `fullmatch`.
"""
import hashlib
import math
import re
from types import MappingProxyType
from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, Field, JsonValue, StringConstraints, ValidationError, model_validator

from .base import Value

__all__ = [
    "Ts", "ArtifactName", "ARTIFACT_NAME_PATTERN", "ARTIFACT_NAME_RE", "NodeId", "FunctionName", "WorkflowId", "AtomId", "ChangeId", "Ref", "Target", "FindingId", "EdgeId",
    "JsonObject", "FUNCTIONS", "NODE_ID_RE", "WORKFLOW_ID_RE", "ATOM_ID_RE", "CHANGE_ID_RE", "REF_RE", "TARGET_RE",
    "FINDING_ID_RE", "EDGE_ID_RE", "NODE_ID_PATTERN", "WORKFLOW_ID_PATTERN", "ATOM_ID_PATTERN", "CHANGE_ID_PATTERN",
    "REF_PATTERN", "TARGET_PATTERN", "FINDING_ID_PATTERN", "EDGE_ID_PATTERN", "IdError", "function_node_id",
    "atom_sid", "function_atom_id", "overhead_atom_id", "Violation", "DomainEvent", "violation", "clip",
    "violations_from_validation_error", "MAX_VIOLATIONS", "EVENT_DATA_KEYS",
]

FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")      # J2:100, the order J2 lists them
FunctionName = Literal["identity", "adaptation", "priority", "coordination", "audit"]

# No dot in a NodeId: the dot belongs to function node ids "<dept>.<function>".
NODE_ID_PATTERN = r"^[a-z][a-z0-9_-]{1,39}$"
WORKFLOW_ID_PATTERN = r"^W-[0-9]+$"
# a-<sid>-<nn> is a function-node atom (plugin SA:253); W-<n>.a<k> is a J2 workflow atom (J2:6679)
ATOM_ID_PATTERN = r"^(a-[a-z0-9]{1,16}-[0-9]{2,6}|W-[0-9]+\.a[0-9]+)$"
CHANGE_ID_PATTERN = r"^chg-[0-9]{4,9}$"
REF_PATTERN = r"^\$[a-z][a-z0-9_]{0,15}$"
TARGET_PATTERN = r"^(\$[a-z][a-z0-9_]{0,15}|[a-z][a-z0-9_-]{1,39})$"       # an existing NodeId or a Ref
# An output type's name, by shape only (J2's own NAME_RE): the names themselves are data (`artifacts/types.json` and the
# user's local types), never listed in code.
ARTIFACT_NAME_PATTERN = r"^[a-z][a-z0-9_]{1,40}$"
FINDING_ID_PATTERN = r"^F-[A-Za-z0-9-]{1,20}$"
EDGE_ID_PATTERN = r"^[a-z_]{1,20}:[^>\s]{1,80}>[^>\s]{1,80}$"                 # "<kind>:<from_id>><to_id>"

ARTIFACT_NAME_RE = re.compile(ARTIFACT_NAME_PATTERN)
NODE_ID_RE = re.compile(NODE_ID_PATTERN)
WORKFLOW_ID_RE = re.compile(WORKFLOW_ID_PATTERN)
ATOM_ID_RE = re.compile(ATOM_ID_PATTERN)
CHANGE_ID_RE = re.compile(CHANGE_ID_PATTERN)
REF_RE = re.compile(REF_PATTERN)
TARGET_RE = re.compile(TARGET_PATTERN)
FINDING_ID_RE = re.compile(FINDING_ID_PATTERN)
EDGE_ID_RE = re.compile(EDGE_ID_PATTERN)

Ts = Annotated[int, Field(ge=0)]                                              # epoch seconds
# Every pattern bounds its own length except the two with a digit run (`[0-9]+`), which carry a max_length (rule 3).
ArtifactName = Annotated[str, StringConstraints(pattern=ARTIFACT_NAME_PATTERN)]
NodeId = Annotated[str, StringConstraints(pattern=NODE_ID_PATTERN)]
WorkflowId = Annotated[str, StringConstraints(pattern=WORKFLOW_ID_PATTERN, max_length=12)]
AtomId = Annotated[str, StringConstraints(pattern=ATOM_ID_PATTERN, max_length=40)]
ChangeId = Annotated[str, StringConstraints(pattern=CHANGE_ID_PATTERN)]
Ref = Annotated[str, StringConstraints(pattern=REF_PATTERN)]
Target = Annotated[str, StringConstraints(pattern=TARGET_PATTERN)]
FindingId = Annotated[str, StringConstraints(pattern=FINDING_ID_PATTERN)]
EdgeId = Annotated[str, StringConstraints(pattern=EDGE_ID_PATTERN)]

_JSON_DEPTH = 32
_JSON_KEYS = 500


def _check_json_object(value: dict[str, Any]) -> dict[str, Any]:
    """A JsonObject is bounded: at most 500 keys at the top, 32 levels deep, and every number finite."""
    if len(value) > _JSON_KEYS:
        raise ValueError(f"a JSON object may have at most {_JSON_KEYS} keys, this one has {len(value)}")

    def walk(item: Any, depth: int) -> None:
        if depth > _JSON_DEPTH:
            raise ValueError(f"JSON nested deeper than {_JSON_DEPTH} levels")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("JSON numbers must be finite")
        if isinstance(item, list):
            for sub in item:
                walk(sub, depth + 1)
        elif isinstance(item, dict):
            for sub in item.values():
                walk(sub, depth + 1)

    walk(value, 1)
    return value


JsonObject = Annotated[dict[str, JsonValue], AfterValidator(_check_json_object)]


# ---- ids --------------------------------------------------------------------------------------------------------

class IdError(ValueError):
    """An id helper was given something that cannot make a valid id. A programming error, not a data error."""


def _sha1_hex(text: str, digits: int) -> str:
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise IdError("an id part must be valid text") from exc
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:digits]


def _need_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise IdError(f"{name} must be a non-empty string")
    return value


def function_node_id(dept_id: str, function: str) -> str:
    """"<dept_id>.<function>": the ONE place that knows the scheme. FunctionIds, FunctionNode and check_graph call it,
    so another scheme is a one-line change."""
    if not isinstance(dept_id, str) or not NODE_ID_RE.fullmatch(dept_id):
        raise IdError(f"a department id is a NodeId (lowercase letters, digits, - and _), not {clip(str(dept_id), 60)!r}")
    if function not in FUNCTIONS:
        raise IdError(f"function must be one of {', '.join(FUNCTIONS)}, not {clip(str(function), 60)!r}")
    return f"{dept_id}.{function}"


def atom_sid(run_id: str, node_id: str) -> str:
    """The first 10 hex digits of sha1("<run_id>:<node_id>"): the `sid` of a function atom (and Atom.session_id)."""
    return _sha1_hex(f"{_need_text('run_id', run_id)}:{_need_text('node_id', node_id)}", 10)


def function_atom_id(sid: str, n: int) -> str:
    """"a-<sid>-<nn>" with at least two digits. The only code that builds a function atom id. `n` counts per run and
    node from 1, and every open attempt consumes a number, so gaps are normal."""
    if not isinstance(sid, str) or not re.fullmatch(r"[a-z0-9]{1,16}", sid):
        raise IdError("sid must be 1 to 16 lowercase letters or digits (use atom_sid)")
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 999_999:
        raise IdError("n must be an integer from 1 to 999999")
    return f"a-{sid}-{n:02d}"


def overhead_atom_id(owner_ref: str) -> str:
    """The accounting key of a model call made outside any function turn: the run id for engine calls, "req-<id>" for
    the chat agent. The same owner always gets the same key; it names no `atoms` row and no card."""
    return function_atom_id(atom_sid(_need_text("owner_ref", owner_ref), "overhead"), 1)


# ---- violations and events ----------------------------------------------------------------------------------------

def clip(text: str, limit: int) -> str:
    """`text` cut to `limit` characters, with an ellipsis when something was cut."""
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


class Violation(Value):
    """One reason a payload was refused. `path` is the pydantic loc joined by ".", union tag first."""

    path: Annotated[str, Field(max_length=500)]
    code: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    message: Annotated[str, StringConstraints(min_length=1, max_length=300)]


def violation(path: str, code: str, message: str) -> Violation:
    """A Violation that always fits its bounds (long text is clipped, an empty message falls back to the code)."""
    text = clip(str(message).strip(), 300) or str(code)
    return Violation(path=clip(str(path), 500), code=clip(str(code), 80) or "invalid", message=text)


MAX_VIOLATIONS = 50   # a payload with thousands of errors reports the first 50 and says how many it left out
_PREFIXES = {"value_error": "Value error, ", "assertion_error": "Assertion failed, "}


def violations_from_validation_error(exc: ValidationError) -> list[Violation]:
    """pydantic's errors as Violations: path = loc joined by ".", code = the error type, message = its text without
    the "Value error, " prefix. Echoed input is cut to 100 characters (a Violation message never carries more)."""
    errors = exc.errors(include_url=False, include_context=True, include_input=False)
    out: list[Violation] = []
    for err in errors[:MAX_VIOLATIONS]:
        code = str(err["type"])
        message = str(err["msg"])
        prefix = _PREFIXES.get(code)
        if prefix and message.startswith(prefix):
            message = message[len(prefix):]
        tag = (err.get("ctx") or {}).get("tag")
        if isinstance(tag, str) and len(tag) > 100:
            message = message.replace(tag, tag[:100] + "…")
        out.append(violation(".".join(str(part) for part in err["loc"]), code, message))
    if len(errors) > MAX_VIOLATIONS:
        out.append(violation("", "more_errors", f"{len(errors) - MAX_VIOLATIONS} more violations are not shown"))
    return out


# The keys the `data` of each event type must hold (design section 13). Other keys are allowed: the orchestrator adds
# version, summary and archived to chart.changed.
EVENT_DATA_KEYS: MappingProxyType[str, tuple[str, ...]] = MappingProxyType({
    "chart.changed": ("revision", "change_id", "kind", "added", "moved", "merged"),
    "atom.transitioned": ("atom_id", "node_id", "outcome", "state"),
    "node.state": ("node_id", "state"),
})


class DomainEvent(Value):
    """What the stores publish after a commit (design section 13): chart.changed, atom.transitioned, node.state. The
    `data` of each type holds the keys of `EVENT_DATA_KEYS` (so a misspelt key is refused where the event is made, not
    found by the SSE mapping); more keys are allowed."""

    type: Literal["chart.changed", "atom.transitioned", "node.state"]
    subject_id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    data: JsonObject
    ts: Ts

    @model_validator(mode="after")
    def _data_holds_the_keys_of_its_type(self) -> Self:
        missing = [key for key in EVENT_DATA_KEYS[self.type] if key not in self.data]
        if missing:
            have = sorted(self.data)
            shown = ", ".join(clip(key, 40) for key in have[:8]) + (", ..." if len(have) > 8 else "")
            raise ValueError(f"the data of a {self.type} event lacks {', '.join(missing)} (it has {shown or 'no keys'})")
        return self
