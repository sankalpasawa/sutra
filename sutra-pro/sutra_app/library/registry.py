"""The model registry and the transport schema (library design 3.3 and 3.5).

`ModelRegistry` keys every class by (family, version, kind): `kind` is the discriminator inside a family, a breaking
change is a new class with VERSION+1 and an `upgrade` function, and the whole registry is exported to JSON Schema by
`export.py`. The module also holds the schema a model is asked to answer in (`transport_schema`), its checker
(`is_transport_safe`) and the reply wrapper (`reply_schema`).
"""
import copy
import hashlib
import json
import re
import threading
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Callable, Literal, Union, get_args, get_origin

from pydantic import BaseModel, Field, TypeAdapter
from pydantic.json_schema import GenerateJsonSchema

from .base import Record, Value, is_abstract, unwrap_annotation
from .types import Violation, violation

__all__ = [
    "RegistryError", "ModelRegistry", "REGISTRY", "record", "transport_schema", "reply_schema", "is_transport_safe",
    "schema_sha", "TRANSPORT_DRAFT",
]

TRANSPORT_DRAFT = "http://json-schema.org/draft-07/schema#"   # 2020-12 is refused by `claude --json-schema`
_FAMILY_RE = re.compile(r"[a-z][a-z0-9_.-]{0,79}")             # safe in file names and URLs: no path separator


class RegistryError(Exception):
    """A programming error in how classes are registered or schemas are asked for (never a data error).
    `code` is one of: frozen, duplicate, not_record, not_payload, bad_family, bad_version, kind_not_literal,
    family_conflict, unknown_family, unknown_version, unknown_kind, kind_required, duplicate_upgrade, bad_upgrade,
    no_upgrade, dangling_upgrade, not_model, transport_dict, transport_recursion, bad_schema_version, specs_unbound,
    specs_empty, arity_unbound."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _name(obj: Any) -> str:
    return getattr(obj, "__qualname__", repr(obj))


class _Family:
    """Everything registered under one family name."""

    def __init__(self, name: str, payload: bool) -> None:
        self.name = name
        self.payload = payload
        self.versions: dict[int, dict[str, type]] = {}                 # version -> kind -> class
        self.upgrades: dict[int, Callable[[dict], dict]] = {}          # from_version -> fn(payload) -> payload
        self.rules: dict[int, tuple[Any, ...]] = {}                    # payload rules per version


class ModelRegistry:
    """One registry keyed (family, version, kind). The module-level `REGISTRY` is the app's; tests build their own."""

    def __init__(self) -> None:
        self._families: dict[str, _Family] = {}
        self._frozen = False
        self._lock = threading.RLock()
        self._adapters: dict[tuple[str, int], TypeAdapter] = {}
        self._transport: dict[type, dict] = {}                          # a class -> its transport schema
        self._spec_source: Any = None
        self._check_arity: Callable[[str], tuple[int, int] | None] | None = None

    # ---- registering -------------------------------------------------------------------------------------------

    def register(self, cls: type[Record]) -> type[Record]:
        """Register a Record class: one entry per kind in its `kind` Literal. A class that says ABSTRACT = True in its
        own body is skipped. Usable as a decorator (`record`)."""
        with self._lock:
            self._require_open("register")
            if not (isinstance(cls, type) and issubclass(cls, Record)):
                raise RegistryError("not_record", f"{_name(cls)} is not a Record subclass")
            if is_abstract(cls):
                return cls
            family = getattr(cls, "FAMILY", None)
            version = getattr(cls, "VERSION", None)
            self._check_name(family, cls)
            self._check_version(version, cls)
            kinds = self._kinds_of(cls)
            self._check_schema_version(version, cls)
            fam = self._families.get(family)
            if fam is not None and fam.payload:
                raise RegistryError("family_conflict", f"{family!r} is already registered as a payload")
            taken = fam.versions.get(version, {}) if fam is not None else {}
            for kind in kinds:
                other = taken.get(kind)
                if other is not None and other is not cls:
                    raise RegistryError(
                        "duplicate", f"({family!r}, v{version}, {kind!r}) is already registered by {_name(other)}")
            if fam is None:
                fam = self._families[family] = _Family(family, payload=False)
            slot = fam.versions.setdefault(version, {})
            for kind in kinds:
                slot[kind] = cls
            self._forget(family)
            return cls

    def register_payload(self, name: str, version: int, cls: type[Value], *, rules: Sequence[Any] = ()) -> type[Value]:
        """Register a Value (no identity fields) under (name, version): a J2 artifact section, a J2 wire document.
        `rules` (a list of RuleSpec, owned by the artifacts package) are attached and read back with `rules()`."""
        with self._lock:
            self._require_open("register_payload")
            if not (isinstance(cls, type) and issubclass(cls, Value)) or issubclass(cls, Record):
                raise RegistryError("not_payload", f"{_name(cls)} must be a Value that is not a Record")
            self._check_name(name, cls)
            self._check_version(version, cls)
            attached = tuple(rules)
            fam = self._families.get(name)
            if fam is not None and not fam.payload:
                raise RegistryError("family_conflict", f"{name!r} is already registered as a record family")
            if fam is not None:
                other = fam.versions.get(version, {}).get(name)
                if other is not None and (other is not cls or fam.rules.get(version, ()) != attached):
                    raise RegistryError("duplicate", f"payload ({name!r}, v{version}) is already registered by {_name(other)}")
            else:
                fam = self._families[name] = _Family(name, payload=True)
            fam.versions.setdefault(version, {})[name] = cls     # a payload is a family with one pseudo-kind: its name
            fam.rules[version] = attached                        # (no cached adapter can be stale: (name, version) is one class)
            return cls

    def upgrade(self, family: str, from_version: int) -> Callable[[Callable[[dict], dict]], Callable[[dict], dict]]:
        """Decorator: `fn(payload: dict) -> dict` turns a payload of `from_version` into one of `from_version + 1`.
        The gate chains these when it is given an older payload."""
        def decorate(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
            with self._lock:
                self._require_open("upgrade")
                fam = self._families.get(family)
                if fam is None:
                    raise RegistryError("unknown_family", f"register the {family!r} classes before their upgrades")
                if isinstance(from_version, bool) or not isinstance(from_version, int) or from_version < 0:
                    raise RegistryError("bad_version", f"from_version must be an integer >= 0, not {from_version!r}")
                if not callable(fn):
                    raise RegistryError("bad_upgrade", "an upgrade must be a function")
                if from_version in fam.upgrades:
                    raise RegistryError("duplicate_upgrade", f"{family!r} already upgrades from v{from_version}")
                fam.upgrades[from_version] = fn
            return fn
        return decorate

    def freeze(self) -> None:
        """Call after the imports: further register, register_payload and upgrade raise RegistryError("frozen")."""
        with self._lock:
            if self._frozen:
                return
            for fam in self._families.values():
                for start in fam.upgrades:
                    if start + 1 not in fam.versions:
                        raise RegistryError(
                            "dangling_upgrade", f"{fam.name!r} upgrades from v{start} but v{start + 1} is not registered")
            self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    # ---- looking up --------------------------------------------------------------------------------------------

    def families(self) -> list[str]:
        with self._lock:
            return sorted(self._families)

    def is_payload(self, family: str) -> bool:
        return self._family(family).payload

    def versions(self, family: str) -> list[int]:
        return sorted(self._family(family).versions)

    def kinds(self, family: str, version: int | None = None) -> dict[str, type]:
        """kind -> class for one version (the latest by default). A payload family has one kind: its own name."""
        fam = self._family(family)
        return dict(fam.versions[self._version(fam, version)])

    def rules(self, family: str, version: int | None = None) -> tuple[Any, ...]:
        fam = self._family(family)
        return fam.rules.get(self._version(fam, version), ())

    def adapter(self, family: str, version: int | None = None) -> TypeAdapter:
        """One class: a TypeAdapter of that class. Several: a union discriminated by `kind`. Built once, cached."""
        with self._lock:
            fam = self._family(family)
            v = self._version(fam, version)
            cached = self._adapters.get((family, v))
            if cached is None:
                classes = tuple(dict.fromkeys(fam.versions[v].values()))
                if len(classes) == 1:
                    cached = TypeAdapter(classes[0])
                else:
                    cached = TypeAdapter(Annotated[Union[classes], Field(discriminator="kind")])
                self._adapters[(family, v)] = cached
            return cached

    def json_schema(self, family: str, version: int | None = None) -> dict:
        """The JSON Schema (2020-12) of a family; several classes give `oneOf` plus a `discriminator`."""
        return self.adapter(family, version).json_schema(by_alias=True)

    def transport_schema(self, family: str, kind: str | None = None, version: int | None = None) -> dict:
        """The draft-07 schema a model is asked to answer in, for ONE concrete class. A family with several classes
        needs `kind`; a family is never sent whole."""
        with self._lock:
            fam = self._family(family)
            v = self._version(fam, version)
            classes = fam.versions[v]
            if kind is None:
                distinct = tuple(dict.fromkeys(classes.values()))
                if len(distinct) != 1:
                    raise RegistryError("kind_required", f"{family!r} has {len(distinct)} classes: name a kind of {sorted(classes)}")
                kind = next(iter(classes))
            elif kind not in classes:
                raise RegistryError("unknown_kind", f"{family!r} v{v} has no kind {kind!r} (it has {sorted(classes)})")
            cls = classes[kind]
            if cls not in self._transport:
                self._transport[cls] = transport_schema(cls)
            return copy.deepcopy(self._transport[cls])

    # ---- upgrades ----------------------------------------------------------------------------------------------

    def can_upgrade(self, family: str, from_version: int, to_version: int) -> bool:
        """True when every step from `from_version` up to `to_version` has an upgrade function."""
        fam = self._family(family)
        return all(step in fam.upgrades for step in range(from_version, to_version))

    def upgrade_payload(self, family: str, payload: Mapping[str, Any], from_version: int,
                        to_version: int | None = None) -> dict:
        """Run the upgrade chain on a deep copy of `payload`. Each step must return a dict; the registry sets its
        `schema_version` to the step's target, so an upgrade function need not."""
        fam = self._family(family)
        end = self._version(fam, to_version)
        data = copy.deepcopy(dict(payload))
        for step in range(from_version, end):
            fn = fam.upgrades.get(step)
            if fn is None:
                raise RegistryError("no_upgrade", f"{family!r} has no upgrade from v{step}")
            data = fn(data)
            if not isinstance(data, dict):
                raise RegistryError("bad_upgrade", f"the {family!r} upgrade from v{step} must return a dict")
            if not fam.payload:
                data["schema_version"] = step + 1
        return data

    # ---- references the library cannot check alone -------------------------------------------------------------

    def bind_function_specs(self, source: Any) -> None:
        """Say where `verify_refs()` finds the FunctionSpecs: the specs object, or a function returning it. The
        function-node module (WP L6) calls this; the registry itself imports neither."""
        self._spec_source = source

    def bind_check_arity(self, arity: Callable[[str], tuple[int, int] | None] | None) -> None:
        """`arity(name)` gives the (min, max) argument count of a named check, or None for an unknown name."""
        self._check_arity = arity

    def verify_refs(self, specs: Any = None, *,
                    check_arity: Callable[[str], tuple[int, int] | None] | None = None) -> list[Violation]:
        """Check what the FunctionSpecs point at: every task kind's reply family and each "|" alternative of its
        reply kind is registered (latest version), and every template check is a known name with a matching argument
        count. `specs` is a FunctionSpecs (its `.specs` mapping), a mapping of FunctionSpec, or an iterable of them;
        omitted, the bound source is used (`bind_function_specs`); the arity function is `check_arity`, else the bound
        one (`bind_check_arity`).

        A check that cannot run is an error, never a quiet pass: an empty list returned means at least one spec was
        looked at and every reference it holds resolved. Raises RegistryError `specs_unbound` (nothing given or bound,
        or the bound loader returned None), `specs_empty` (the set holds no spec) and `arity_unbound` (a spec holds
        checks and no arity function is known). To look at the reply references of specs with checks and nothing
        else, say so with `check_arity=lambda name: (0, 99)`."""
        if specs is None:
            specs = self._spec_source() if callable(self._spec_source) else self._spec_source
        if specs is None:
            raise RegistryError(
                "specs_unbound", "there are no FunctionSpecs to verify: pass them, or call bind_function_specs(...) first")
        arity = check_arity or self._check_arity
        inner = getattr(specs, "specs", specs)
        items = list(inner.values()) if isinstance(inner, Mapping) else list(inner)
        if not items:
            raise RegistryError("specs_empty", "the FunctionSpecs hold no spec, so nothing was verified")
        found: list[Violation] = []
        for spec in items:
            function = str(getattr(spec, "function", "?"))
            for task_kind in getattr(spec, "task_kinds", None) or ():
                base = f"{function}.task_kinds.{getattr(task_kind, 'kind', '?')}"
                self._verify_reply_ref(base, str(getattr(task_kind, "reply_family", "") or ""),
                                       str(getattr(task_kind, "reply_kind", "") or ""), found)
            for template in getattr(spec, "atom_templates", None) or ():
                for index, ref in enumerate(getattr(template, "checks", None) or ()):
                    where = f"{function}.atom_templates.{getattr(template, 'name', '?')}.checks.{index}"
                    if arity is None:
                        raise RegistryError(
                            "arity_unbound",
                            f"{where} is a check but no arity function is known to verify it: pass check_arity=..., or call bind_check_arity(...)")
                    self._verify_check_ref(where, ref, arity, found)
        return found

    def _verify_reply_ref(self, base: str, family: str, kind_text: str, found: list[Violation]) -> None:
        if not family and not kind_text:
            return
        if not family or not kind_text:
            found.append(violation(base, "incomplete_reply_ref", "reply_family and reply_kind go together"))
            return
        if family not in self._families:
            found.append(violation(f"{base}.reply_family", "unknown_reply_family", f"{family!r} is not a registered family"))
            return
        known = self.kinds(family)
        for alternative in (part.strip() for part in kind_text.split("|")):
            if alternative not in known:
                found.append(violation(f"{base}.reply_kind", "unknown_reply_kind",
                                       f"{alternative!r} is not a kind of {family!r} (it has {', '.join(sorted(known))})"))

    @staticmethod
    def _verify_check_ref(where: str, ref: Any, arity: Callable[[str], tuple[int, int] | None],
                          found: list[Violation]) -> None:
        name = str(getattr(ref, "name", ""))
        count = len(getattr(ref, "args", None) or ())
        limits = arity(name)
        if limits is None:
            found.append(violation(f"{where}.name", "unknown_check", f"{name!r} is not a known check name"))
        elif not limits[0] <= count <= limits[1]:
            wanted = str(limits[0]) if limits[0] == limits[1] else f"{limits[0]} to {limits[1]}"
            found.append(violation(f"{where}.args", "bad_check_args", f"{name!r} takes {wanted} arguments, got {count}"))

    # ---- internals ---------------------------------------------------------------------------------------------

    def _require_open(self, action: str) -> None:
        if self._frozen:
            raise RegistryError("frozen", f"the registry is frozen: {action} is refused")

    @staticmethod
    def _check_name(name: Any, cls: Any) -> None:
        if not isinstance(name, str) or not _FAMILY_RE.fullmatch(name):
            raise RegistryError(
                "bad_family", f"{_name(cls)}: a family name is lowercase letters, digits, . _ - (1 to 80), not {name!r}")

    @staticmethod
    def _check_version(version: Any, cls: Any) -> None:
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise RegistryError("bad_version", f"{_name(cls)}: VERSION must be an integer >= 1, not {version!r}")

    @staticmethod
    def _check_schema_version(version: int, cls: type[Record]) -> None:
        """A Record's `schema_version` defaults to 1 (Record) and the class refuses any other value than its VERSION. A
        VERSION+1 class that does not redeclare `schema_version: int = N` would register and then fail at its first
        write ("schema_version is 1, this class is version 2"); this is where both numbers are known."""
        info = cls.model_fields.get("schema_version")
        default = info.default if info is not None else None
        if type(default) is not int or default != version:
            shown = default if type(default) is int else "no usable default"
            raise RegistryError(
                "bad_schema_version",
                f"{_name(cls)}: VERSION is {version} but schema_version defaults to {shown}: declare `schema_version: int = {version}`")

    @staticmethod
    def _kinds_of(cls: type[Record]) -> tuple[str, ...]:
        info = cls.model_fields.get("kind")
        annotation = unwrap_annotation(info.annotation)[0] if info is not None else None
        values = get_args(annotation) if get_origin(annotation) is Literal else ()
        if not values or not all(isinstance(v, str) and v for v in values):
            raise RegistryError("kind_not_literal", f"{_name(cls)}: `kind` must be a Literal of strings, e.g. Literal['atom']")
        return tuple(dict.fromkeys(values))

    def _family(self, family: str) -> _Family:
        fam = self._families.get(family) if isinstance(family, str) else None
        if fam is None:
            raise RegistryError("unknown_family", f"no family {str(family)[:80]!r}")
        return fam

    @staticmethod
    def _version(fam: _Family, version: int | None) -> int:
        if version is None:
            return max(fam.versions)
        if version not in fam.versions:
            raise RegistryError("unknown_version", f"{fam.name!r} has no version {version!r} (it has {sorted(fam.versions)})")
        return version

    def _forget(self, family: str) -> None:
        """A new class changes the union of its family, so the cached adapters go. A cached transport schema never
        goes stale: it belongs to one class and a registered class cannot be replaced."""
        for key in [k for k in self._adapters if k[0] == family]:
            del self._adapters[key]

    def __repr__(self) -> str:
        return f"<ModelRegistry {len(self._families)} families{' frozen' if self._frozen else ''}>"


REGISTRY = ModelRegistry()
record = REGISTRY.register


# ---- the transport schema (design 3.5; a port of J2's j2_artifact_models.transport_schema) ------------------------

# What the transport forbids and the cleaner removes. `const` (kept as a one-value enum) and `discriminator` (dropped
# with `oneOf`) are handled apart from this list.
_STRIP = frozenset((
    "minLength", "maxLength", "minItems", "maxItems", "pattern", "format", "exclusiveMinimum",
    "exclusiveMaximum", "minimum", "maximum", "multipleOf", "default", "title", "examples",
))
# What is_transport_safe reports when it finds it anywhere in a schema.
_FORBIDDEN = _STRIP | frozenset((
    "const", "oneOf", "discriminator", "allOf", "not", "if", "then", "else", "$defs", "prefixItems",
    "uniqueItems", "patternProperties", "propertyNames", "minProperties", "maxProperties",
))


_OPTIONAL_KEY = "x-sutra-transport-optional"     # carried from the generator to the cleaner; never in the output


class _TransportSchemaGenerator(GenerateJsonSchema):
    """pydantic's JSON Schema generator with one addition: the schema of every model says which of ITS OWN properties
    its class lists in `TRANSPORT_OPTIONAL`. The cleaner reads that on the same node, so a class's set reaches its own
    properties and no other class's (the first version took the union over the whole tree by property name, and a reply
    class that marked `reason` optional made the required `reason` of every class nested in it optional too). Nothing
    is looked up by definition name, which pydantic changes when two classes share a name."""

    def model_schema(self, schema: Any) -> Any:
        json_schema = super().model_schema(schema)
        optional = getattr(schema["cls"], "TRANSPORT_OPTIONAL", None)
        if optional:
            json_schema[_OPTIONAL_KEY] = sorted(optional)
        return json_schema


def _rewrite_refs(node: Any) -> Any:
    """`#/$defs/X` becomes `#/definitions/X` (draft-07), in `$ref` values only."""
    if isinstance(node, dict):
        return {k: (v.replace("#/$defs/", "#/definitions/", 1) if k == "$ref" and isinstance(v, str)
                    else _rewrite_refs(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [_rewrite_refs(v) for v in node]
    return node


def _clean(node: Any, where: str) -> Any:
    """One schema node as the transport allows it: no length, pattern, format or default, `const` as a one-value
    enum, a union as `anyOf`, `anyOf [X, null]` folded into a type list, objects closed, and every property required
    unless the class of that object lists it as optional (its own `TRANSPORT_OPTIONAL`, carried on the node)."""
    if not isinstance(node, dict):
        return node
    out = {k: v for k, v in node.items() if k not in _STRIP and k not in ("const", "discriminator", _OPTIONAL_KEY)}
    if "const" in node and "enum" not in out:
        out["enum"] = [node["const"]]                                  # J2 dropped const and lost the constraint
    if "oneOf" in out:
        out["anyOf"] = [*out.get("anyOf", ()), *out.pop("oneOf")]      # distinguishable members: a one-value enum each
    if "anyOf" in out:
        parts = [_clean(x, f"{where}/anyOf") for x in out.pop("anyOf")]
        nullable = any(isinstance(p, dict) and p.get("type") == "null" for p in parts)
        real = [p for p in parts if not (isinstance(p, dict) and p.get("type") == "null")]
        if len(real) == 1 and isinstance(real[0], dict) and isinstance(real[0].get("type"), str):
            out.update(real[0])
            out["type"] = [real[0]["type"], "null"] if nullable else real[0]["type"]
            if nullable and "enum" in out and None not in out["enum"]:
                out["enum"] = [*out["enum"], None]                      # the type allows null, so the enum must too
        elif real:
            if len(real) == 1 and isinstance(real[0], dict) and set(real[0]) == {"anyOf"}:
                real = real[0]["anyOf"]                                 # Optional[union]: no anyOf inside an anyOf
            out["anyOf"] = real
    for key in ("properties", "definitions", "$defs"):
        if isinstance(out.get(key), dict):
            out[key] = {k: _clean(v, f"{where}/{key}/{k}") for k, v in out[key].items()}
    if isinstance(out.get("items"), dict):
        out["items"] = _clean(out["items"], f"{where}/items")
    if out.get("type") == "object" or "properties" in out:
        if "properties" not in out:
            raise RegistryError(
                "transport_dict",
                f"{where}: a dict with free keys becomes an object that accepts no key; use a list of pairs instead")
        out["additionalProperties"] = False
        props = list(out["properties"])
        optional = node.get(_OPTIONAL_KEY) or ()
        out["required"] = [p for p in props if p not in optional] or props
    return out


def _refs_in(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_refs_in(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_refs_in(item))
    return found


def _find_cycle(schema: dict) -> list[str] | None:
    """A `$ref` cycle among the definitions reachable from the root, as the names along it, or None."""
    prefix = "#/definitions/"
    defs = schema.get("definitions") if isinstance(schema.get("definitions"), dict) else {}
    state: dict[str, int] = {}
    trail: list[str] = []

    def visit(name: str) -> list[str] | None:
        if state.get(name) == 1:
            return [*trail[trail.index(name):], name]
        if state.get(name) == 2 or name not in defs:
            return None
        state[name] = 1
        trail.append(name)
        for ref in _refs_in(defs[name]):
            if ref.startswith(prefix):
                hit = visit(ref[len(prefix):])
                if hit:
                    return hit
        trail.pop()
        state[name] = 2
        return None

    for ref in _refs_in({k: v for k, v in schema.items() if k != "definitions"}):
        if ref.startswith(prefix):
            hit = visit(ref[len(prefix):])
            if hit:
                return hit
    return None


def transport_schema(model: type[BaseModel]) -> dict:
    """The draft-07 schema sent to the model, generated from the model so the two cannot drift.

    `$defs` become `definitions`; every object is closed and has every property required except the names in ITS
    class's `TRANSPORT_OPTIONAL` (each class's own set, for its own properties only; a subclass inherits the set of
    its base class); no length, pattern, format, default or title is left in; `const` stays as a
    one-value `enum`; a union is `anyOf` (no `oneOf`, no `discriminator`); a recursive class and a dict with free keys
    raise RegistryError (`transport_recursion`, `transport_dict`)."""
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise RegistryError("not_model", f"{_name(model)} is not a pydantic model class")
    raw = _rewrite_refs(model.model_json_schema(by_alias=True, schema_generator=_TransportSchemaGenerator))
    if "$defs" in raw:
        raw["definitions"] = raw.pop("$defs")
    raw.pop("$schema", None)
    out = {"$schema": TRANSPORT_DRAFT, **_clean(raw, _name(model))}
    cycle = _find_cycle(out)
    if cycle:
        raise RegistryError("transport_recursion", f"{_name(model)} refers to itself: {' -> '.join(cycle)}")
    return out


def reply_schema(model: type[BaseModel], extra_fields: Mapping[str, Any] | None) -> dict:
    """A builder's whole reply as one object (ported as is from J2): the fields a builder already returns, `reason`
    first, plus "section", the transport schema of its own section model. `extra_fields` is {name: schema} for the
    optional fields; they are not in `required`."""
    section = transport_schema(model)
    definitions = section.pop("definitions", None)
    section.pop("$schema", None)
    props: dict[str, Any] = {
        "reason": {"type": "string", "description": "one short sentence: why you decided this"},
        "say": {"type": "string", "description": "one short line reporting to @Coordination: what you changed; "
                                                 "code runs your checks and reports them, so don't claim they pass"},
        "human_output": {"type": "string", "description": "1 to 3 plain sentences telling a person what you built"},
        "atom_human_output": {"type": "string", "description": "1 or 2 plain sentences telling the Requester what "
                                                               "this part created, in everyday words"},
        "next": {"type": "string", "description": "Coordination"},
        "section": section,
    }
    props.update(extra_fields or {})
    out: dict[str, Any] = {
        "$schema": TRANSPORT_DRAFT, "type": "object", "additionalProperties": False, "properties": props,
        "required": ["reason", "say", "human_output", "atom_human_output", "next", "section"],
    }
    if definitions:
        out["definitions"] = definitions
    return out


def schema_sha(schema: Any) -> str:
    """J2's schema_sha: sha256 of the schema as sorted-key JSON. The router remembers a schema by it."""
    return hashlib.sha256(json.dumps(schema, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def is_transport_safe(schema: Any) -> list[str]:
    """What is wrong with a transport schema, one line each as "<json pointer>: <code>: <text>"; [] when it is safe.

    Safe means: draft-07; no keyword the transport refuses (`oneOf`, `discriminator`, `const`, lengths, patterns,
    defaults, titles ...); every object closed (`additionalProperties` false) and, if it has `required`, naming only
    its properties; an object without `properties` is a free-key dict (`transport_dict`); `$ref` only into
    `#/definitions/` and no cycle (`transport_recursion`); an enum that allows null when its type does."""
    problems: list[str] = []
    if not isinstance(schema, dict):
        return ["#: not_a_schema: a schema is an object"]
    if schema.get("$schema") != TRANSPORT_DRAFT:
        problems.append(f"#: draft: $schema must be {TRANSPORT_DRAFT}")
    definitions = schema.get("definitions") if isinstance(schema.get("definitions"), dict) else {}

    def walk(node: Any, path: str) -> None:
        if not isinstance(node, dict):
            return
        for key in node:
            if key in _FORBIDDEN:
                problems.append(f"{path}: keyword_not_allowed: {key!r} is not allowed in a transport schema")
        ref = node.get("$ref")
        if isinstance(ref, str) and not (ref.startswith("#/definitions/") and ref[len("#/definitions/"):] in definitions):
            problems.append(f"{path}: bad_ref: {ref!r} does not point into #/definitions/")
        if node.get("type") == "object" or "properties" in node:
            if "properties" not in node:
                problems.append(f"{path}: transport_dict: an object without properties accepts no key (a dict with free keys?)")
            if node.get("additionalProperties") is not False:
                problems.append(f"{path}: not_closed: additionalProperties must be false")
            props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
            for name in node.get("required") or ():
                if name not in props:
                    problems.append(f"{path}: bad_required: {name!r} is required but is not a property")
        kind = node.get("type")
        if isinstance(node.get("enum"), list) and isinstance(kind, list) and "null" in kind and None not in node["enum"]:
            problems.append(f"{path}: enum_null: the type allows null but the enum does not")
        for key in ("properties", "definitions"):
            if isinstance(node.get(key), dict):
                for name, sub in node[key].items():
                    walk(sub, f"{path}/{key}/{name}")
        if isinstance(node.get("items"), dict):
            walk(node["items"], f"{path}/items")
        if isinstance(node.get("anyOf"), list):
            for index, sub in enumerate(node["anyOf"]):
                walk(sub, f"{path}/anyOf/{index}")

    walk(schema, "#")
    cycle = _find_cycle(schema)
    if cycle:
        problems.append(f"#: transport_recursion: definitions refer to themselves: {' -> '.join(cycle)}")
    return problems
