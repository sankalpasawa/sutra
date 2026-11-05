"""The one write gate (library design 3.4).

Every store accepts only a `Checked` object, and only `Gate.check` makes one. `check` is the seven steps of the
design, in order:

    1  a model instance is dumped to JSON first, so `model_construct` cannot bypass validation; so is a Mapping of any
       kind (nested ones too), except that a tuple or a key that is not a string is refused: JSON has neither, and
       writing them as a list and a string would make the gate laxer than the class (stage `shape`, code `not_json`)
    2  an unknown family or version is refused (stage `unknown`); so is a payload over 1 MiB (stage `size`)
    3  a payload older than the latest `schema_version` runs the registered upgrade chain, or is refused
       (stage `shape`, code `schema_version`)
    4  strict validation through the family adapter, class validators included (stage `shape`)
    5  the cross rules for the family and kind, only when the caller passes a context (stage `cross`)
    6  canonical JSON and its sha256; then the JSON must read back to an equal model (stage `round_trip`)
    7  a `Checked` is returned; the gate writes nothing
"""
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from .base import Record, Value, canonical_json
from .registry import REGISTRY, ModelRegistry, RegistryError
from .types import Violation, clip, violation, violations_from_validation_error

__all__ = [
    "MAX_PAYLOAD_BYTES", "Stage", "GateError", "Checked", "GateContext", "CrossRule", "FunctionRule", "cross_rule",
    "SHIPPED_CROSS_RULES", "Gate", "GATE",
]

MAX_PAYLOAD_BYTES = 1_048_576
Stage = Literal["unknown", "size", "shape", "cross", "round_trip"]
T = TypeVar("T", bound=Value)


class GateError(Exception):
    """A payload the gate refused. Nothing was written. HTTP: 422 with the violations, 413 for stage `size`."""

    def __init__(self, family: str, stage: Stage, violations: Sequence[Violation]) -> None:
        self.family = family
        self.stage = stage
        self.violations = list(violations)
        first = self.violations[0] if self.violations else None
        summary = f"{first.path or '<root>'}: {first.message}" if first else "no detail"
        more = f" (+{len(self.violations) - 1} more)" if len(self.violations) > 1 else ""
        super().__init__(f"{stage} refused a {family!r} payload: {summary}{more}")


_TOKEN = object()


class Checked(Generic[T]):
    """A payload that passed the gate: the model, and the canonical JSON and sha256 a store writes. Immutable, and
    constructible only inside this module, so holding one is proof that `Gate.check` ran."""

    __slots__ = ("model", "family", "version", "kind", "json", "sha256")
    model: T
    family: str
    version: int
    kind: str
    json: str          # the canonical JSON of the model: the SQL `body`
    sha256: str        # of that text as UTF-8 bytes

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if len(args) != 7 or kwargs or args[0] is not _TOKEN:
            raise TypeError("Checked objects are made only by Gate.check; a store receives them, it never builds one")
        for name, value in zip(self.__slots__, args[1:]):
            object.__setattr__(self, name, value)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("Checked cannot be subclassed")

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("a Checked object is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("a Checked object is immutable")

    def __copy__(self) -> "Checked[T]":
        return self

    def __deepcopy__(self, memo: dict) -> "Checked[T]":
        return self

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, Checked) and (self.family, self.version, self.kind, self.sha256)
                == (other.family, other.version, other.kind, other.sha256))

    def __hash__(self) -> int:
        return hash((self.family, self.version, self.kind, self.sha256))

    def __repr__(self) -> str:       # never the body: it holds user text
        return f"Checked({self.family!r}, v{self.version}, kind={self.kind!r}, sha256={self.sha256[:12]}…)"


def _make_checked(model: Any, family: str, version: int, kind: str, text: str, sha256: str) -> Checked:
    return Checked(_TOKEN, model, family, version, kind, text, sha256)


class GateContext(Protocol):
    """What a cross rule may look at: the store's open transaction. `get` returns the stored model or None."""

    def get(self, family: str, id: str) -> Value | None: ...


class CrossRule(Protocol):
    """A rule that needs other stored records. `kind` None means every kind of the family."""

    name: str
    family: str
    kind: str | None

    def __call__(self, model: Any, ctx: GateContext) -> list[Violation]: ...


@dataclass(frozen=True)
class FunctionRule:
    """A CrossRule made from a function: `@cross_rule("atom.supersedes_abandoned", "atom")`."""

    name: str
    family: str
    kind: str | None
    fn: Callable[[Any, GateContext], list[Violation]]

    def __call__(self, model: Any, ctx: GateContext) -> list[Violation]:
        return list(self.fn(model, ctx))


def cross_rule(name: str, family: str, kind: str | None = None) -> Callable[[Callable], FunctionRule]:
    def decorate(fn: Callable[[Any, GateContext], list[Violation]]) -> FunctionRule:
        return FunctionRule(name=name, family=family, kind=kind, fn=fn)
    return decorate


# ---- the four rules that ship with the gate. They read plain attributes, so they work on the classes of the other
# library modules without importing them. -----------------------------------------------------------------------------

@cross_rule("atom.supersedes_abandoned", "atom")
def _atom_supersedes_abandoned(model: Any, ctx: GateContext) -> list[Violation]:
    """An atom may supersede only an atom that is abandoned (plugin bin/sutra-atom:237-241)."""
    target = getattr(model, "supersedes", None)
    if not target:
        return []
    other = ctx.get("atom", target)
    if other is None:
        return [violation("supersedes", "unknown_atom", f"supersedes target {target} is not found")]
    if getattr(other, "state", None) != "abandoned":
        return [violation("supersedes", "supersedes_not_abandoned",
                          f"supersedes target {target} is not abandoned: abandon it with a reason first")]
    return []


@cross_rule("edge.endpoints_exist", "edge")
def _edge_endpoints_exist(model: Any, ctx: GateContext) -> list[Violation]:
    """Both ends of an edge are stored nodes."""
    out: list[Violation] = []
    for field in ("from_id", "to_id"):
        node_id = getattr(model, field, None)
        if node_id and ctx.get("node", node_id) is None:
            out.append(violation(field, "unknown_node", f"{field} {clip(str(node_id), 80)!r} is not a stored node"))
    return out


@cross_rule("node.department_exists", "node")
def _node_department_exists(model: Any, ctx: GateContext) -> list[Violation]:
    """A node that names a department names a stored node of kind department (a department naming itself is fine)."""
    dept = getattr(model, "department_id", None)
    if not dept or dept == getattr(model, "id", None):
        return []
    found = ctx.get("node", dept)
    if found is None:
        return [violation("department_id", "unknown_department", f"department {clip(str(dept), 80)!r} is not a stored node")]
    if getattr(found, "kind", None) != "department":
        return [violation("department_id", "not_a_department", f"{clip(str(dept), 80)!r} is a {getattr(found, 'kind', '?')}, not a department")]
    return []


@cross_rule("department.in_chart", "department")
def _department_in_chart(model: Any, ctx: GateContext) -> list[Violation]:
    """A Department record exists only for a department the current org chart holds."""
    chart = ctx.get("org_chart", "chart")
    if chart is None:
        return [violation("id", "no_chart", "there is no org chart yet, so no department can exist")]
    mine = getattr(model, "id", None)
    if not any(getattr(n, "kind", None) == "department" and getattr(n, "id", None) == mine
               for n in getattr(chart, "nodes", ())):
        return [violation("id", "department_not_in_chart", f"the org chart holds no department {clip(str(mine), 80)!r}")]
    return []


SHIPPED_CROSS_RULES: tuple[CrossRule, ...] = (
    _atom_supersedes_abandoned, _edge_endpoints_exist, _node_department_exists, _department_in_chart,
)


# ---- the gate -----------------------------------------------------------------------------------------------------

class _NotJson(ValueError):
    """The payload holds something JSON does not have, at `path` (a list of keys and indexes, empty for the root)."""

    def __init__(self, path: list[Any], message: str) -> None:
        super().__init__(message)
        self.path = ".".join(str(part) for part in path)
        self.message = message


def _jsonable(obj: Any, trail: list[Any], active: set[int]) -> Any:
    """`obj` as the plain data `json.dumps` writes: a Mapping of any kind becomes a dict, a nested model its JSON dump.
    What JSON does not have is refused rather than converted, so the gate is never laxer than the class (design 3.1
    rule 1, no coercion): strict validation refuses a tuple where a list belongs, and a key that is not a string would
    be written as one, so `{1: 10, "1": 20}` would lose a value. `trail` is the path to `obj`, kept for the message;
    `active` holds the containers being walked (json.dumps refused a payload that contains itself, and so does this)."""
    if obj is None or isinstance(obj, (str, int, float)):               # a bool is an int
        return obj
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", by_alias=True, warnings=False)
    if isinstance(obj, tuple):
        raise _NotJson(trail, "a tuple is not a list: send a list")
    if not isinstance(obj, (Mapping, list)):
        raise TypeError(f"{type(obj).__name__} is not JSON")
    if id(obj) in active:
        raise _NotJson(trail, "the payload contains itself")
    active.add(id(obj))
    if isinstance(obj, Mapping):
        out: dict[str, Any] = {}
        for key, item in obj.items():
            if not isinstance(key, str):
                raise _NotJson(trail, f"object keys must be strings, found {type(key).__name__} {clip(repr(key), 40)}")
            trail.append(key)
            out[key] = _jsonable(item, trail, active)
            trail.pop()
        result: Any = out
    else:
        items: list[Any] = []
        for index, item in enumerate(obj):
            trail.append(index)
            items.append(_jsonable(item, trail, active))
            trail.pop()
        result = items
    active.discard(id(obj))
    return result


class Gate:
    """Validates payloads of registered families. One per registry; the app's is `GATE`."""

    def __init__(self, registry: ModelRegistry = REGISTRY, cross_rules: Sequence[CrossRule] = ()) -> None:
        self._registry = registry
        self._rules = tuple(cross_rules)
        names = [rule.name for rule in self._rules]
        for name in names:
            if names.count(name) > 1:
                raise RegistryError("duplicate", f"cross rule {name!r} is given twice")

    @property
    def registry(self) -> ModelRegistry:
        return self._registry

    @property
    def cross_rules(self) -> tuple[CrossRule, ...]:
        return self._rules

    def check(self, family: str, payload: Mapping[str, Any] | str | bytes | Value, *,
              version: int | None = None, ctx: GateContext | None = None) -> Checked:
        shown = clip(str(family), 80)
        reg = self._registry
        # 2. unknown family or version (before any work on the payload)
        try:
            versions = reg.versions(family)
        except RegistryError:
            raise GateError(shown, "unknown", [violation("", "unknown_family", f"no family {shown!r} is registered")]) from None
        if version is None:
            target = versions[-1]
        elif not isinstance(version, bool) and isinstance(version, int) and version in versions:
            target = version
        else:
            raise GateError(shown, "unknown", [violation(
                "", "unknown_version", f"family {shown!r} has no version {clip(str(version), 20)} (it has {versions})")])
        # 1 and 2. the payload as JSON text, within the size limit
        text = self._text_of(shown, payload)
        # 3. an older payload is upgraded, or refused
        if not reg.is_payload(family):
            text = self._upgraded(shown, family, text, target)
        # 4. strict validation
        adapter = reg.adapter(family, target)
        try:
            model = adapter.validate_json(text)
        except ValidationError as exc:
            raise GateError(shown, "shape", violations_from_validation_error(exc)) from None
        except RecursionError:
            raise GateError(shown, "shape", [violation("", "too_deep", "the payload is nested too deeply")]) from None
        kind = model.kind if isinstance(model, Record) else family       # a payload's one kind is its own name
        # 5. cross rules, only with a context
        if ctx is not None:
            found: list[Violation] = []
            for rule in self._rules:
                if rule.family == family and (rule.kind is None or rule.kind == kind):
                    found.extend(rule(model, ctx))
            if found:
                raise GateError(shown, "cross", found)
        # 6. canonical JSON, sha256, and the round trip
        try:
            canon = canonical_json(model)
            digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()
        except (ValueError, UnicodeError):
            raise GateError(shown, "shape", [violation("", "not_json", "the payload holds a value JSON cannot carry (a non-finite number or invalid text)")]) from None
        try:
            again = adapter.validate_json(canon)
        except ValidationError as exc:
            raise GateError(shown, "round_trip", violations_from_validation_error(exc)) from None
        if again != model:
            raise GateError(shown, "round_trip", [violation(
                "", "round_trip_mismatch", "the model read back from its canonical JSON differs from the model checked")])
        # 7.
        return _make_checked(model, family, target, kind, canon, digest)

    # ---- steps ------------------------------------------------------------------------------------------------

    @staticmethod
    def _text_of(shown: str, payload: Any) -> str:
        """Steps 1 and 2: the payload as JSON text, refused when it is not JSON or is over the limit."""
        if isinstance(payload, (bytes, bytearray, memoryview)) and len(payload) > MAX_PAYLOAD_BYTES:
            raise GateError(shown, "size", [violation("", "payload_too_large", f"payload is {len(payload)} bytes, the limit is {MAX_PAYLOAD_BYTES}")])
        if isinstance(payload, str) and len(payload) > MAX_PAYLOAD_BYTES:
            raise GateError(shown, "size", [violation("", "payload_too_large", f"payload is over {MAX_PAYLOAD_BYTES} bytes")])
        try:
            if isinstance(payload, Value):
                text = payload.model_dump_json(by_alias=True, warnings=False)
            elif isinstance(payload, Mapping):
                text = json.dumps(_jsonable(payload, [], set()), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            elif isinstance(payload, str):
                text = payload
            elif isinstance(payload, (bytes, bytearray, memoryview)):
                text = bytes(payload).decode("utf-8")
            else:
                raise GateError(shown, "shape", [violation(
                    "", "payload_type", f"a payload is a model, a dict, JSON text or bytes, not {type(payload).__name__}")])
            size = len(text.encode("utf-8"))
        except GateError:
            raise
        except _NotJson as exc:
            raise GateError(shown, "shape", [violation(exc.path, "not_json", exc.message)]) from None
        except UnicodeError:
            raise GateError(shown, "shape", [violation("", "bad_unicode", "the payload is not valid UTF-8 text")]) from None
        except RecursionError:
            raise GateError(shown, "shape", [violation("", "too_deep", "the payload is nested too deeply")]) from None
        except (TypeError, ValueError, OverflowError) as exc:
            raise GateError(shown, "shape", [violation("", "not_json", f"the payload cannot be written as JSON: {clip(str(exc), 120)}")]) from None
        if size > MAX_PAYLOAD_BYTES:
            raise GateError(shown, "size", [violation("", "payload_too_large", f"payload is {size} bytes, the limit is {MAX_PAYLOAD_BYTES}")])
        return text

    def _upgraded(self, shown: str, family: str, text: str, target: int) -> str:
        """Step 3: run the upgrade chain when the payload says it is older than `target`."""
        try:
            data = json.loads(text)
        except (ValueError, RecursionError):
            return text                                           # step 4 reports the bad JSON in pydantic's words
        found = data.get("schema_version") if isinstance(data, dict) else None
        if isinstance(found, bool) or not isinstance(found, int) or found >= target:
            return text                                           # absent, malformed (step 4 says so) or current
        if not self._registry.can_upgrade(family, found, target):
            raise GateError(shown, "shape", [violation(
                "schema_version", "schema_version",
                f"payload is version {found}, the latest is {target}, and no upgrade is registered from {found}")])
        try:                                      # a RegistryError (a bad upgrade function) is a bug and propagates
            data = self._registry.upgrade_payload(family, data, found, target)
            upgraded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            size = len(upgraded.encode("utf-8"))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise GateError(shown, "shape", [violation(
                "schema_version", "upgrade_failed", f"upgrading from version {found} failed: {type(exc).__name__}")]) from None
        if size > MAX_PAYLOAD_BYTES:
            raise GateError(shown, "size", [violation("", "payload_too_large", f"the upgraded payload is {size} bytes, the limit is {MAX_PAYLOAD_BYTES}")])
        return upgraded


GATE = Gate(REGISTRY, SHIPPED_CROSS_RULES)
