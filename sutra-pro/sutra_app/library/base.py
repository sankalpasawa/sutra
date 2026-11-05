"""The closed base classes of the Interface library: `Value` and `Record` (library design section 3.1).

Three tiers, one rule set:

    Value    a closed object with no identity fields (the nested parts of everything else)
    Record   a Value that is stored or sent: it has a `kind` (the discriminator inside a family) and a `schema_version`
    Payload  a Value registered under (name, version), see `registry.ModelRegistry.register_payload`

Every class is strict (no coercion), frozen, `extra="forbid"` and made of JSON-native types only. `evolve()` is the
only way to change one, because `model_copy(update=...)` would skip validation. This module imports nothing from the
rest of the app; the other library modules build on it.
"""
import json
import keyword
import re
import types
from typing import Annotated, Any, ClassVar, Self, Union, get_args, get_origin

import pydantic
from pydantic import BaseModel, ConfigDict, model_validator

__all__ = [
    "Value", "Record", "canonical_json", "is_abstract", "require_pydantic",
    "unwrap_annotation", "union_members", "nested_models", "discriminator_of", "MIN_PYDANTIC",
    "unbounded_fields", "aliased_fields",
]

MIN_PYDANTIC = (2, 11)   # validate_by_name / serialize_by_alias (library design 3.1, rule 6)


def require_pydantic(version: str = pydantic.VERSION, minimum: tuple[int, int] = MIN_PYDANTIC) -> None:
    """Fail fast, with a clear message, when the installed pydantic is older than the library needs."""
    m = re.match(r"(\d+)\.(\d+)", version)
    if m is None or (int(m.group(1)), int(m.group(2))) < minimum:
        raise RuntimeError(f"the library needs pydantic >= {minimum[0]}.{minimum[1]} (found {version})")


require_pydantic()


def canonical_json(model: BaseModel) -> str:
    """The one text form of a model: dump(mode="json"), sorted keys, no spaces, no ASCII escaping.

    Equal models give equal text whatever order the keys arrived in, so a sha256 of it is a stable identity. NaN and
    infinity cannot occur (the config refuses them); `allow_nan=False` makes any that slipped in fail loudly."""
    data = model.model_dump(mode="json", by_alias=True, warnings=False)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _plain(value: Any) -> Any:
    """`value` as plain data: models become dicts (by field name), so evolve() validates everything afresh."""
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=False, warnings=False)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


class Value(BaseModel):
    """A closed, strict, frozen object. Subclass it for every nested part and every model-facing reply class."""

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, str_strip_whitespace=True,
        validate_by_name=True, validate_by_alias=True, serialize_by_alias=True,
        allow_inf_nan=False,   # canonical JSON must be valid JSON (design 3.1 rule 2: JSON-native types only)
    )

    # Property names that the model may leave out of a reply (design 3.5). Each class's set applies to that class's OWN
    # properties and to no other class's: a nested class lists its own, and a subclass inherits the set of its base
    # class (J2's global OPTIONAL_FIELDS becomes one set on the base class of the artifact models).
    TRANSPORT_OPTIONAL: ClassVar[frozenset[str]] = frozenset()

    def evolve(self, **changes: Any) -> Self:
        """A new instance with `changes` applied, checked from scratch. The ONLY update path.

        The current values are dumped to plain data, merged with `changes` (field names or aliases) and validated
        again, so a bad change raises ValidationError and an instance built with `model_construct` is re-checked."""
        cls = type(self)
        names: dict[str, str] = {}
        for name, info in cls.model_fields.items():
            for alias in (info.alias, info.validation_alias):
                if isinstance(alias, str):
                    names[alias] = name
        data = self.model_dump(by_alias=False, warnings=False)
        for key, value in changes.items():
            data[names.get(key, key)] = _plain(value)
        return cls.model_validate(data)

    def canonical_json(self) -> str:
        return canonical_json(self)


class Record(Value):
    """A Value that is stored or sent. `kind` picks the class inside a family (a concrete class narrows it to a
    Literal with a default); `schema_version` must equal the class's VERSION."""

    FAMILY: ClassVar[str]
    VERSION: ClassVar[int] = 1
    # Read from the class body only (see is_abstract): an inherited flag once silently unregistered every child.
    ABSTRACT: ClassVar[bool] = False

    kind: str
    schema_version: int = 1

    @model_validator(mode="after")
    def _schema_version_matches_class(self) -> Self:
        if self.schema_version != type(self).VERSION:
            raise ValueError(f"schema_version is {self.schema_version}, this class is version {type(self).VERSION}")
        return self


def is_abstract(cls: type) -> bool:
    """True only when `cls` itself says ABSTRACT = True in its body; a child of an abstract class is concrete."""
    return bool(cls.__dict__.get("ABSTRACT", False))


# ---- annotation helpers shared by the registry (transport schema) and the reply parser (tolerant reading) ---------

def unwrap_annotation(annotation: Any) -> tuple[Any, tuple[Any, ...]]:
    """(the annotation without its Annotated layers, the metadata those layers carried)."""
    meta: list[Any] = []
    while get_origin(annotation) is Annotated:
        args = get_args(annotation)
        annotation = args[0]
        meta.extend(args[1:])
    return annotation, tuple(meta)


def union_members(annotation: Any) -> tuple[Any, ...] | None:
    """The members of a Union / Optional / `A | B` annotation, or None when it is not one."""
    core, _ = unwrap_annotation(annotation)
    if get_origin(core) in (Union, types.UnionType):
        return get_args(core)
    return None


def discriminator_of(meta: tuple[Any, ...]) -> str | None:
    """The discriminator field name that Annotated metadata declares (`Field(discriminator=...)` or `Discriminator`)."""
    for item in meta:
        found = getattr(item, "discriminator", None)          # FieldInfo and pydantic.Discriminator both have one
        if isinstance(found, str):
            return found
    return None


def nested_models(annotation: Any) -> list[type[BaseModel]]:
    """Every BaseModel class that appears anywhere inside `annotation` (lists, dicts, unions, Annotated), in order."""
    found: list[type[BaseModel]] = []

    def walk(ann: Any) -> None:
        core, _ = unwrap_annotation(ann)
        if isinstance(core, type) and issubclass(core, BaseModel):
            if core not in found:
                found.append(core)
            return
        for arg in get_args(core):
            walk(arg)

    walk(annotation)
    return found


# ---- the design rules a class can be checked against (library design 3.1, rules 3 and 7) ----------------------------
# Not enforced when a class is declared (a toy class in a test may be loose); a test runs them over the classes it owns
# (L1: those of types.py; L8: every class of the full REGISTRY), so a field without a bound or a stray alias cannot
# ship unnoticed.

def _pattern_bounds_length(pattern: str) -> bool:
    """True when `pattern` is anchored at both ends and cannot match more than some fixed number of characters.
    pydantic applies a pattern as a search, so an unanchored one bounds nothing. This reads Python's own regex parser;
    anything it cannot read counts as unbounded, so the check errs towards asking for a `max_length`."""
    try:
        parsed = re._parser.parse(pattern)                                      # type: ignore[attr-defined]
        first, last = parsed.data[0], parsed.data[-1]
        anchored = (str(first[0]), str(first[1])) == ("AT", "AT_BEGINNING") and (str(last[0]), str(last[1])) == ("AT", "AT_END")
        return anchored and parsed.getwidth()[1] < re._constants.MAXREPEAT      # type: ignore[attr-defined]
    except Exception:
        return False


def _string_is_bounded(node: dict[str, Any]) -> bool:
    return any(key in node for key in ("maxLength", "enum", "const")) or (
        isinstance(node.get("pattern"), str) and _pattern_bounds_length(node["pattern"]))


def unbounded_fields(cls: type[BaseModel]) -> list[str]:
    """Rule 3: every `str` and every `list` is bounded. Returns `Class.field` for each field of `cls`, and of each class
    nested in it, that holds a `str` or a `list` with no bound; `[]` after the name stands for the items of a list and
    `{}` for the values of a dict (`Doc.tags[]` is a list of strings whose items have no `max_length`).

    A string is bounded by `max_length`, by being a `Literal`, or by a pattern that is anchored at both ends and
    cannot match more than a fixed length (the id types); a list by `max_length`. A `JsonObject` is bounded by its own
    validator (500 keys, 32 levels) and is not looked into; dict keys are not looked at."""
    schema = cls.model_json_schema(by_alias=False)
    found: list[str] = []

    def add(where: str) -> None:
        if where not in found:
            found.append(where)

    def visit(node: Any, where: str) -> None:
        if not isinstance(node, dict) or "$ref" in node:         # a nested class is checked as a definition of its own
            return
        for key in ("anyOf", "allOf", "oneOf"):
            for sub in node.get(key) or ():
                visit(sub, where)
        kind = node.get("type")
        if kind == "string":
            if not _string_is_bounded(node):
                add(where)
        elif kind == "array":
            if "maxItems" not in node:
                add(where)
            visit(node.get("items"), f"{where}[]")
            for index, sub in enumerate(node.get("prefixItems") or ()):
                visit(sub, f"{where}[{index}]")
        elif kind == "object":
            visit(node.get("additionalProperties"), f"{where}{{}}")

    def visit_class(name: str, node: dict[str, Any]) -> None:
        for field, sub in (node.get("properties") or {}).items():
            visit(sub, f"{name}.{field}")

    visit_class(cls.__name__, schema)
    for name, node in (schema.get("$defs") or {}).items():
        visit_class(name, node)
    return found


def aliased_fields(cls: type[BaseModel]) -> list[tuple[str, str]]:
    """Rule 7: a field alias is allowed only where J2's wire key is a Python keyword (`pass`, `from`). Returns
    `(class name, alias)` for each alias on a field of `cls`, and of each class nested in it, that is NOT a keyword; a
    test holds the few that are allowed on purpose (`AtomView.schema`) and expects nothing else. An alias that is not a
    plain string (`AliasChoices`, `AliasPath`) is reported by its repr."""
    found: list[tuple[str, str]] = []
    seen: set[type] = set()
    queue: list[type[BaseModel]] = [cls]
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        for info in current.model_fields.values():
            for alias in (info.alias, info.validation_alias, info.serialization_alias):
                if alias is None:
                    continue
                shown = alias if isinstance(alias, str) else repr(alias)
                if not (isinstance(alias, str) and keyword.iskeyword(alias)) and (current.__name__, shown) not in found:
                    found.append((current.__name__, shown))
            queue.extend(nested_models(info.annotation))
    return found
