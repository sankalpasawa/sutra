"""template-library/1: the Template bases and their pure checks (library design section 9.2).

Every artifact section has a GENERIC template (the fixed layout of its artifact type, built from the section model and its
rules, never retyped) and, per workflow, a SPECIALISED template the engine generates from the workflow's context. This
module owns what a template IS and what makes one valid; the engine keeps the router, the library directory, codegen and
the prompts (it imports this module, never the other way round).

    FieldSpec, ObjectSpec, MadeBy, Context, Use     the parts
    GenericTemplate, SpecialisedTemplate            family "template", kinds generic and specialised (closed, frozen)
    shape_problems, rule_problems, resolve, keeps_problems, refusal      the checks: lists of reasons, never a raise
    generic, from_model, generic_file, write_generic, generic_drift      the generic layer, from the models and RULES
    build_model, transport, validate                the runtime class from a spec (pydantic.create_model), its draft-07
                                                    transport schema, and (data) -> (dict or None, errors)
    TemplateMeta, TemplateDecision, RunTemplate, TemplatesFile           the files of a run's own copy (J2 sync 33aeeda)
    run_tpl_rel, RUN_TEMPLATE_FILES                 where a run keeps its copy of a template version

Differences from J2, each on purpose: a template is frozen (a changed sha or version is `evolve`); `rules` are `RuleSpec`
objects, so a rule that cannot run is refused when the template is built, and a path outside the template is a `Template`
error (`resolve`); every string and list is bounded; the built runtime class is a strict `Value`, as the artifact models
are. The `sha` of a template is J2's (sha256 of `content()` with the rules in their J2 dict form), so templates stored by
J2 keep their shas. codegen (model.py) stays with the engine.
"""
import hashlib
import json
import os
import re
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal, Optional, Self, Union, get_args, get_origin

from pydantic import Field, StringConstraints, create_model, model_validator

from .artifacts import SECTION_MODELS, VERSION, slug
from .artifacts.models import OPTIONAL_FIELDS
from .artifacts.render import errors_of, normalise
from .artifacts.render import validate as validate_data
from .artifacts.rules import RULE_TYPES, RuleSpec, rules_for, spec_problems
from .base import Record, Value, unwrap_annotation
from .registry import REGISTRY, record, transport_schema
from .registry import schema_sha as sha_of_schema

__all__ = [
    "SCHEMA", "ARTIFACTS", "MAX_FIELDS", "RUN_TEMPLATE_FILES", "TemplateArtifact", "FieldSpec", "ObjectSpec", "MadeBy",
    "Context", "Use", "Template", "GenericTemplate", "SpecialisedTemplate", "TemplateMeta", "TemplateCandidate",
    "TemplateDecision", "RunTemplate", "TemplatesFile", "sha_of", "generic_ref", "shape_problems", "rule_problems",
    "resolve", "keeps_problems", "refusal", "from_model", "generic", "spec_json", "generic_file", "write_generic",
    "generic_drift", "templates_dir", "class_name", "build_model", "transport", "validate", "run_tpl_rel",
]

SCHEMA = "template-library/1"
ARTIFACTS = ("prd", "hld", "lld", "design", "website")
TemplateArtifact = Literal["prd", "hld", "lld", "design", "website"]
MAX_FIELDS = 25
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
OBJ_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
TYPE_RE = re.compile(r"^(?:string|integer|boolean|list\[string\]|list\[([A-Z][A-Za-z0-9]*)\]|([A-Z][A-Za-z0-9]*))$")
# a run keeps its copy of each template version it used as these four files (J2 33aeeda `FILES`)
RUN_TEMPLATE_FILES = ("spec.json", "model.py", "schema.json", "meta.json")
SAVED_PATTERN = r"^templates/[a-z0-9-]{1,40}/[a-z0-9-]{1,100}/[a-z0-9-]{1,200}@v[0-9]{1,6}$"

Hex64 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Sha = Annotated[str, StringConstraints(pattern=r"^([0-9a-f]{64})?$")]          # "" until the sha is computed
Line80 = Annotated[str, StringConstraints(max_length=80)]
Line200 = Annotated[str, StringConstraints(max_length=200)]
Name200 = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Text1000 = Annotated[str, StringConstraints(max_length=1000)]
Text2000 = Annotated[str, StringConstraints(max_length=2000)]


def sha_of(obj: Any) -> str:
    """J2's `sha_of`: sha256 of the object as sorted-key JSON."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- the parts
class FieldSpec(Value):
    """One field: a name, an allowed type, required or not, its description, and an enum when it is narrowed."""

    name: Line80
    type: Line80
    required: bool
    description: Text2000 = ""
    enum: Optional[Annotated[list[Annotated[str, StringConstraints(max_length=500)]], Field(max_length=300)]] = None
    nullable: bool = False      # Optional[...] in the model: the value may be null (google_fonts_url)


class ObjectSpec(Value):
    """An object type defined inside the spec, used as <Object> or list[<Object>]."""

    name: Line80
    fields: Annotated[list[FieldSpec], Field(max_length=60)]


class MadeBy(Value):
    run: Line200
    workflow: Line200
    atom: Line200
    agent: Line200


class Context(Value):
    business_type: Annotated[str, StringConstraints(max_length=300)]
    facts_used: Annotated[list[Annotated[str, StringConstraints(max_length=1000)]], Field(max_length=300)]
    fingerprint: Annotated[str, StringConstraints(max_length=128)]


class Use(Value):
    """One use of a template version: who asked for it, and whether it was reused, extended or created."""

    run: Optional[Line200] = None
    workflow: Optional[Line200] = None
    atom: Optional[Line200] = None
    action: Optional[Line80] = None


# ---------------------------------------------------------------- the Template classes
class Template(Record):
    """The base class: closed, frozen, and every write is checked (allowed types only, known rule types only, every rule
    path resolves to a field, identifier names without dunders, at most 25 fields)."""

    FAMILY = "template"
    ABSTRACT = True
    name: Name200
    artifact: TemplateArtifact
    section: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    version: Annotated[int, Field(ge=1, le=999_999)] = 1
    description: Text2000 = ""
    fields: Annotated[list[FieldSpec], Field(max_length=60)]
    objects: Annotated[list[ObjectSpec], Field(max_length=40)] = Field(default_factory=list)
    rules: Annotated[list[RuleSpec], Field(max_length=60)] = Field(default_factory=list)
    sha: Sha = ""

    @model_validator(mode="after")
    def _checked(self) -> Self:
        bad = shape_problems(self)
        if bad:
            raise ValueError("; ".join(bad))
        return self

    def content(self) -> dict[str, Any]:
        """What the sha covers: the template itself, not its version number or its provenance. Rules are in their J2
        dict form, so a template's sha is the one J2 gave it."""
        data = self.model_dump(exclude={"sha", "version", "made_by", "context", "used_by", "schema_version"})
        data["rules"] = [r.as_j2() for r in self.rules]
        return data

    def compute_sha(self) -> str:
        return sha_of(self.content())

    def ref(self) -> str:
        return f"{self.name}@{self.version}"


@record
class GenericTemplate(Template):
    """The generic layer: one per (artifact, section), built from the section model and RULES."""

    kind: Literal["generic"] = "generic"


@record
class SpecialisedTemplate(Template):
    """A workflow's own template: extends one generic and keeps every required field of it."""

    kind: Literal["specialised"] = "specialised"
    extends: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    made_by: MadeBy
    context: Context
    used_by: Annotated[list[Use], Field(max_length=5000)] = Field(default_factory=list)

    @model_validator(mode="after")
    def _keeps_generic(self) -> Self:
        want = generic_ref(self.artifact, self.section)
        if self.extends != want:
            raise ValueError(f"extends must be {want!r}, not {self.extends!r}")
        gen = generic(self.artifact, self.section)
        if gen is None:
            raise ValueError(f"there is no generic template for {self.artifact} {self.section!r}")
        bad = keeps_problems(gen, self)
        if bad:
            raise ValueError("; ".join(bad))
        return self


def generic_ref(artifact: str, section: str) -> str:
    return f"{artifact}/{slug(section)}@generic/{VERSION}"


# ---------------------------------------------------------------- the checks (one list of reasons, never a raise)
def _objs(t):
    return {o.name: o for o in t.objects}


def _parse_type(t):
    """(kind, object name) for an allowed type: ("string"|"integer"|"boolean"|"list_string"|"list_obj"|"obj", name)."""
    m = TYPE_RE.match(str(t or ""))
    if not m:
        return None, None
    if m.group(1):
        return "list_obj", m.group(1)
    if m.group(2):
        return "obj", m.group(2)
    return ("list_string" if t == "list[string]" else t), None


def _field_problems(where, fields, objs):
    out = []
    if len(fields) > MAX_FIELDS:
        out.append(f"{where} has {len(fields)} fields; at most {MAX_FIELDS} are allowed")
    seen = set()
    for f in fields:
        n = f.name
        if not NAME_RE.match(n) or "__" in n:
            out.append(f"{where}: field name {n!r} is not an identifier (letters, digits and _ only, no dunder)")
        if n in seen:
            out.append(f"{where}: field {n!r} appears twice")
        seen.add(n)
        kind, obj = _parse_type(f.type)
        if kind is None:
            out.append(f"{where}.{n}: type {f.type!r} is not allowed (string, integer, boolean, list[string], "
                       "list[<Object>] or <Object>)")
            continue
        if obj and obj not in objs:
            out.append(f"{where}.{n}: object type {obj!r} is not defined in the spec")
        if f.enum is not None:
            if kind not in ("string", "list_string"):
                out.append(f"{where}.{n}: an enum is allowed on string and list[string] only")
            elif not f.enum or any(not isinstance(v, str) or not v.strip() for v in f.enum):
                out.append(f"{where}.{n}: the enum must list non-empty strings")
            elif len(set(f.enum)) != len(f.enum):
                out.append(f"{where}.{n}: the enum repeats a value")
        if f.nullable and kind not in ("string", "obj"):
            out.append(f"{where}.{n}: only a string or an object may be nullable")
    return out


def _cycle(objs):
    """The name of an object that contains itself (the transport forbids recursion), or None."""
    def deps(name):
        return [_parse_type(f.type)[1] for f in objs[name].fields if _parse_type(f.type)[1]]
    state = {}

    def visit(n):
        if state.get(n) == 1:
            return n
        if state.get(n) == 2 or n not in objs:
            return None
        state[n] = 1
        for d in deps(n):
            hit = visit(d)
            if hit:
                return hit
        state[n] = 2
        return None
    for n in objs:
        hit = visit(n)
        if hit:
            return hit
    return None


def resolve(t, path):
    """None when a rule path resolves to a field of the template, else the reason. Paths: "a", "a.b" (a is an
    object), "a[].b" (a is a list of objects), "a[]", "a.*" (every value of the object a)."""
    objs = _objs(t)
    fields = {f.name: f for f in t.fields}
    parts = str(path or "").split(".")
    if not path or any(not p for p in parts):
        return f"rule path {path!r} is empty or malformed"
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if part == "*":
            return None if last and i > 0 else f"rule path {path!r}: * must come last, after an object"
        star = part.endswith("[]")
        key = part[:-2] if star else part
        if fields is None or key not in fields:
            return f"rule path {path!r}: {key!r} is not a field of the template"
        kind, obj = _parse_type(fields[key].type)
        if star:
            if kind not in ("list_obj", "list_string"):
                return f"rule path {path!r}: {key!r} is not a list"
            fields = {f.name: f for f in objs[obj].fields} if kind == "list_obj" and obj in objs else None
        elif kind == "obj" and obj in objs:
            fields = {f.name: f for f in objs[obj].fields}
        else:
            fields = None
            if not last and parts[i + 1] != "*":
                return f"rule path {path!r}: {key!r} has no fields under it"
            if not last and kind != "obj":
                return f"rule path {path!r}: {key!r} is not an object"
    return None


def rule_problems(t, rules):
    """What is wrong with a template's rules: each rule's own problems (`rules.spec_problems`, J2's wording) and every
    path that does not resolve to a field of `t`. `rules` holds `RuleSpec` objects or J2 dicts."""
    out = []
    for n, r in enumerate(rules, 1):
        rule = r.as_j2() if isinstance(r, RuleSpec) else r
        out += spec_problems(rule, n)
        if not isinstance(rule, Mapping) or not isinstance(rule.get("rule"), str) or rule["rule"] not in RULE_TYPES:
            continue
        for key in ("path", "anchor_path", "html_path"):
            v = rule.get(key)
            for p in (v if isinstance(v, list) else [v] if v else []):
                why = resolve(t, p) if isinstance(p, str) else f"rule path {p!r} is not a string"
                if why:
                    out.append(f"rule {n} ({rule['rule']}): {why}")
    return out


def shape_problems(t):
    objs = _objs(t)
    out = _field_problems("fields", t.fields, objs)
    names = [o.name for o in t.objects]
    for o in t.objects:
        if not OBJ_RE.match(o.name):
            out.append(f"object name {o.name!r} must be a CapWord identifier")
        out += _field_problems(o.name, o.fields, objs)
    if len(set(names)) != len(names):
        out.append("an object is defined twice")
    hit = _cycle(objs)
    if hit:
        out.append(f"object {hit!r} contains itself; recursion is not allowed")
    if not out:
        out += rule_problems(t, t.rules)
    if not str(t.name or "").strip():
        out.append("the template needs a name")
    return out


def _keeps_obj(gen_objs, sp_objs, gname, sname, where):
    """Every required field of a generic object is still in the specialised one, with a compatible type."""
    out = []
    g, s = gen_objs.get(gname), sp_objs.get(sname)
    if g is None or s is None:
        return [f"{where}: object {sname!r} is missing"]
    have = {f.name: f for f in s.fields}
    for gf in g.fields:
        out += _keep_field(gf, have.get(gf.name), gen_objs, sp_objs, f"{where}.{gf.name}")
    return out


def _keep_field(gf, sf, gen_objs, sp_objs, where):
    if not gf.required:
        if sf is None:
            return []
    if sf is None:
        return [f"{where}: the generic's required field {gf.name!r} is dropped"]
    if gf.required and not sf.required:
        return [f"{where}: required in the generic, so it stays required"]
    gk, go = _parse_type(gf.type)
    sk, so = _parse_type(sf.type)
    if gk != sk:
        return [f"{where}: type {sf.type!r} doesn't keep the generic's {gf.type!r}"]
    if gf.enum and (not sf.enum or not set(sf.enum) <= set(gf.enum)):
        return [f"{where}: the enum may only narrow the generic's ({', '.join(gf.enum)})"]
    if go:
        return _keeps_obj(gen_objs, sp_objs, go, so, where)
    return []


def keeps_problems(gen, sp):
    """A specialised template keeps every required field of its generic (it may narrow a string to an enum, add
    fields and rewrite descriptions)."""
    have = {f.name: f for f in sp.fields}
    out = []
    for gf in gen.fields:
        out += _keep_field(gf, have.get(gf.name), _objs(gen), _objs(sp), gf.name)
    return out


def refusal(data):
    """The reasons a spec is refused ([] when it passes every check)."""
    try:
        SpecialisedTemplate.model_validate(data)
        return []
    except Exception as e:
        return [re.sub(r"^section: (?:Value error, )?", "", x) for x in errors_of(e)]


# ---------------------------------------------------------------- the generic layer, from the models (never retyped)
def _ann(annotation):
    """(type string, enum, nullable, object model or None) for a model field's annotation."""
    nullable = False
    annotation = unwrap_annotation(annotation)[0]
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType) and type(None) in args:      # Optional[X]
        nullable = True
        annotation = unwrap_annotation(next(a for a in args if a is not type(None)))[0]
        origin, args = get_origin(annotation), get_args(annotation)
    if origin is Literal:
        return "string", [str(a) for a in args], nullable, None
    if origin is list:
        inner = unwrap_annotation(args[0])[0]
        if get_origin(inner) is Literal:
            return "list[string]", [str(a) for a in get_args(inner)], nullable, None
        if inner is str:
            return "list[string]", None, nullable, None
        return f"list[{inner.__name__}]", None, nullable, inner
    if annotation is str:
        return "string", None, nullable, None
    if annotation is int:
        return "integer", None, nullable, None
    if annotation is bool:
        return "boolean", None, nullable, None
    return annotation.__name__, None, nullable, annotation


def from_model(model):
    """(fields, objects) of a pydantic section model, read from the model itself."""
    objects, order = {}, []

    def fields_of(m):
        out = []
        for name, f in m.model_fields.items():
            typ, enum, nullable, obj = _ann(f.annotation)
            if obj is not None and obj.__name__ not in objects:
                objects[obj.__name__] = None
                objects[obj.__name__] = fields_of(obj)
                order.append(obj.__name__)
            out.append(FieldSpec(name=f.alias or name, type=typ, required=f.is_required(),
                                 description=f.description or "", enum=enum, nullable=nullable))
        return out
    fields = fields_of(model)
    return fields, [ObjectSpec(name=n, fields=objects[n]) for n in order]


def generic(artifact, section):
    """The GenericTemplate of one section, built from its model and its rules (None when there is no model)."""
    model = (SECTION_MODELS.get(artifact) or {}).get(section)
    if model is None:
        return None
    fields, objects = from_model(model)
    t = GenericTemplate(name=model.template(), artifact=artifact, section=section, version=VERSION,
                        description=f"The generic {model.template()} template: the fixed layout of every "
                                    f"{artifact.upper() if artifact in ('prd', 'hld', 'lld') else artifact} "
                                    f"{section} section, whatever the business",
                        fields=fields, objects=objects, rules=rules_for(artifact, section))
    return t.evolve(sha=t.compute_sha())


def spec_json(t) -> dict[str, Any]:
    """spec.json as J2 writes it: a generic without its empty keys, a specialised one without `used_by` (that lives in
    meta.json); rules as J2 dicts; no `schema_version` (the library's own, not part of J2's file)."""
    if t.kind == "generic":
        data = t.model_dump(exclude_none=True, exclude={"schema_version"})
    else:
        data = t.model_dump(exclude={"used_by", "schema_version"})
    data["rules"] = [r.as_j2() for r in t.rules]
    return data


def generic_file(artifact):
    """templates/<artifact>/generic.json as it must be: every section of the artifact, in the models' order."""
    ts = [generic(artifact, s) for s in SECTION_MODELS[artifact]]
    return {"schema": SCHEMA, "artifact": artifact, "kind": "generic", "version": VERSION,
            "from": "sutra_app.library.artifacts (SECTION_MODELS and RULES; generated by write_generic)",
            "templates": [{**spec_json(t), "schema_sha": sha_of_schema(transport_schema(SECTION_MODELS[artifact][t.section]))}
                          for t in ts]}


def templates_dir(explicit=None) -> Path:
    """Where the generated generic.json files go: the argument, else SUTRA_TEMPLATES_DIR, else docs/schemas/templates of
    the checkout. They are documentation and a drift guard; nothing reads them at run time."""
    chosen = explicit or os.environ.get("SUTRA_TEMPLATES_DIR")
    return Path(chosen) if chosen else Path(__file__).resolve().parents[2] / "docs" / "schemas" / "templates"


def write_generic(root=None):
    out = []
    for a in ARTIFACTS:
        p = templates_dir(root) / a / "generic.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(generic_file(a), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        out.append(str(p))
    return out


def generic_drift(root=None):
    """Every disagreement between the generic.json files under `root` and the models + RULES ([] when none)."""
    out = []
    for a in ARTIFACTS:
        p = templates_dir(root) / a / "generic.json"
        if not p.exists():
            out.append(f"{p} is missing")
            continue
        try:
            have = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            out.append(f"{p} is not JSON")
            continue
        want = generic_file(a)
        if have != want:
            hs = {t.get("section"): t for t in have.get("templates") or [] if isinstance(t, dict)}
            before = len(out)
            for t in want["templates"]:
                h = hs.get(t["section"])
                if h != t:
                    keys = sorted(k for k in set(t) | set(h or {}) if (h or {}).get(k) != t.get(k))
                    out.append(f"{a}/{t['section']}: generic.json differs from the models/RULES in {', '.join(keys)}")
            if len(out) == before:
                out.append(f"{a}: generic.json differs from the models/RULES")
    return out


# ---------------------------------------------------------------- runtime: the class is built from the spec
class TemplateBase(Value):
    TEMPLATE: ClassVar[str] = "template"
    SECTION: ClassVar[str] = ""

    @classmethod
    def template(cls) -> str:
        return cls.TEMPLATE


_BUILT: dict[tuple, type] = {}
_BUILT_MAX = 256


def _attr(name):
    import keyword
    return name + "_" if keyword.iskeyword(name) else name


def class_name(t):
    base = "".join(w[:1].upper() + w[1:] for w in re.findall(r"[A-Za-z0-9]+", t.name)) or "Template"
    if base[0].isdigit():
        base = "T" + base
    return f"{base}V{t.version}"


def _py_type(f, classes):
    kind, obj = _parse_type(f.type)
    if kind == "string":
        tp = Literal[tuple(f.enum)] if f.enum else str
    elif kind == "integer":
        tp = int
    elif kind == "boolean":
        tp = bool
    elif kind == "list_string":
        tp = list[Literal[tuple(f.enum)]] if f.enum else list[str]
    elif kind == "list_obj":
        tp = list[classes[obj]]
    else:
        tp = classes[obj]
    if f.nullable or (kind == "obj" and not f.required):
        tp = Optional[tp]
    return tp


def _field_args(f):
    kind, _ = _parse_type(f.type)
    args = {"description": f.description}
    if f.name != _attr(f.name):
        args["alias"] = f.name
    if f.required:
        return args
    if kind in ("list_string", "list_obj"):
        args["default_factory"] = list
    elif f.nullable or kind == "obj":
        args["default"] = None
    elif kind == "integer":
        args["default"] = 0
    elif kind == "boolean":
        args["default"] = False
    else:
        args["default"] = f.enum[0] if f.enum else ""
    return args


def _obj_order(t):
    objs, done, out = _objs(t), set(), []

    def visit(n):
        if n in done or n not in objs:
            return
        done.add(n)
        for f in objs[n].fields:
            o = _parse_type(f.type)[1]
            if o:
                visit(o)
        out.append(n)
    for o in t.objects:
        visit(o.name)
    return out


def _as_template(t):
    if isinstance(t, Template):
        return t
    cls = SpecialisedTemplate if isinstance(t, Mapping) and t.get("kind") == "specialised" else GenericTemplate
    return cls.model_validate(t)


def _optional_names(t):
    """The transport marks a field optional when the generic's transport does (OPTIONAL_FIELDS), or when the template
    added it as not required."""
    gen = generic(t.artifact, t.section)
    gnames = {f.name for f in gen.fields} | {f.name for o in gen.objects for f in o.fields} if gen else set()
    added = {f.name for f in t.fields if not f.required and f.name not in gnames}
    added |= {f.name for o in t.objects for f in o.fields if not f.required and f.name not in gnames}
    return frozenset(OPTIONAL_FIELDS | added)


def build_model(t):
    """The runtime class of a template, from its spec with pydantic.create_model (cached by the sha of its content). model.py is never
    imported for this. Every class carries the template's optional names as its `TRANSPORT_OPTIONAL`."""
    t = _as_template(t)
    key = (t.compute_sha(), t.version, t.name)          # never the stored sha: a stale one must not find another class
    if key in _BUILT:
        return _BUILT[key]
    optional = _optional_names(t)
    classes, objs = {}, _objs(t)
    for n in _obj_order(t):
        classes[n] = create_model(n, __base__=TemplateBase,
                                  **{_attr(f.name): (_py_type(f, classes), Field(**_field_args(f)))
                                     for f in objs[n].fields})
        classes[n].TRANSPORT_OPTIONAL = optional
    cls = create_model(class_name(t), __base__=TemplateBase,
                       **{_attr(f.name): (_py_type(f, classes), Field(**_field_args(f))) for f in t.fields})
    cls.TEMPLATE = f"{t.name} v{t.version}"
    cls.SECTION = t.section
    cls.TRANSPORT_OPTIONAL = optional
    if len(_BUILT) >= _BUILT_MAX:
        _BUILT.pop(next(iter(_BUILT)))
    _BUILT[key] = cls
    return cls


def transport(t):
    """schema.json: the draft-07 transport schema of a template (definitions, closed objects, nothing the transport
    forbids), from its runtime class."""
    return transport_schema(build_model(_as_template(t)))


def validate(t, data):
    """(dict or None, [errors]): the template's runtime class, then the generic model on the generic fields (so the
    generic's shape - the website section's html-or-head - still holds)."""
    t = _as_template(t)
    model = build_model(t)
    obj, errs = validate_data(model, normalise(model, data))
    if errs:
        return None, errs
    got = obj.model_dump(by_alias=True)
    gmodel = (SECTION_MODELS.get(t.artifact) or {}).get(t.section)
    if gmodel is not None:
        gnames = {(f.alias or n) for n, f in gmodel.model_fields.items()}
        _, gerrs = validate_data(gmodel, normalise(gmodel, {k: v for k, v in got.items() if k in gnames}))
        if gerrs:
            return None, gerrs
    return got, []


# ---------------------------------------------------------------- a run's own copy of the templates it used (J2 33aeeda)
def run_tpl_rel(rec) -> str:
    """Where a run keeps its copy of one decision's template: templates/<artifact>/<section-slug>/<slug>@v<N>/, holding
    spec.json, model.py, schema.json and meta.json. `rec` is a decision (`TemplateDecision` or its J2 dict)."""
    get = rec.get if isinstance(rec, Mapping) else lambda k: getattr(rec, k)
    return f"templates/{get('artifact')}/{slug(get('section'))}/{slug(get('template'))}@v{get('version')}"


class _TemplateDoc(Value):
    """A J2 file that carries `"schema": "template-library/1"`. The key is checked and not stored (a field named `schema`
    would need an alias that is not a Python keyword, which design rule 7 allows only for AtomView); `to_json()` puts it
    back first."""

    @model_validator(mode="before")
    @classmethod
    def _schema_key(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and "schema" in data:
            if data["schema"] != SCHEMA:
                raise ValueError(f"schema must be {SCHEMA!r}, not {data['schema']!r}")
            data = {k: v for k, v in data.items() if k != "schema"}
        return data

    def to_json(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **self.model_dump(by_alias=True, mode="json", exclude_none=True)}


class TemplateMeta(_TemplateDoc):
    """meta.json of one template version (a library version or a run's copy). A generic copy says `kind: "generic"` and
    has `used_by: []`; a specialised one has no `kind` key in J2, and carries the class name, the creation time and the
    fingerprints of the needs it answered."""

    name: Name200
    version: Annotated[int, Field(ge=1, le=999_999)]
    kind: Optional[Literal["generic", "specialised"]] = None
    sha: Hex64
    schema_sha: Hex64
    model_sha: Hex64
    class_: Optional[Line200] = Field(default=None, alias="class")
    created: Optional[Annotated[str, StringConstraints(max_length=40)]] = None
    fingerprints: Optional[Annotated[list[Annotated[str, StringConstraints(max_length=128)]], Field(max_length=500)]] = None
    used_by: Annotated[list[Use], Field(max_length=5000)] = Field(default_factory=list)


class TemplateCandidate(Value):
    name: Name200
    version: Annotated[int, Field(ge=1, le=999_999)]
    score: float
    fingerprint_match: bool
    has_fields: bool


class TemplateDecision(Value):
    """One routing decision of templates.json. `saved` (J2 33aeeda) is the path of the run's own copy of the template,
    relative to the run folder (`run_tpl_rel`), or null when the copy could not be made; absent on older runs. The keys
    after `reason` are those the router adds on some paths only."""

    run: Optional[Line200] = None
    t: Optional[Annotated[str, StringConstraints(max_length=40)]] = None
    workflow: Optional[Line200] = None
    atom: Optional[Line200] = None
    artifact: TemplateArtifact
    section: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    action: Literal["reused", "extended", "created", "generic"]
    template: Name200
    version: Optional[Annotated[int, Field(ge=1, le=999_999)]] = None
    kind: Literal["generic", "specialised"]
    score: Optional[float] = None
    reason: Text2000
    rule: Optional[Annotated[str, StringConstraints(max_length=8)]] = None
    fingerprint: Optional[Annotated[str, StringConstraints(max_length=128)]] = None
    facts: Optional[Annotated[int, Field(ge=0)]] = None
    fields: Optional[Annotated[int, Field(ge=0)]] = None
    needed_fields: Annotated[list[Line80], Field(max_length=100)] = Field(default_factory=list)
    needed_enums: dict[Line80, Annotated[list[Annotated[str, StringConstraints(max_length=500)]], Field(max_length=300)]] = Field(
        default_factory=dict)
    candidates: Annotated[list[TemplateCandidate], Field(max_length=10)] = Field(default_factory=list)
    covers: Optional[Text1000] = None
    schema_sha: Optional[Hex64] = None
    attempts: Optional[Annotated[int, Field(ge=1, le=10)]] = None
    refused: Optional[Annotated[list[Optional[Text2000]], Field(max_length=10)]] = None
    saved: Optional[Annotated[str, StringConstraints(pattern=SAVED_PATTERN)]] = None


class RunTemplate(TemplateDecision):
    """A row of GET /api/run-templates: the decision plus where its template can be read from now."""

    source: Literal["from this run", "from library", "not recorded"]


class TemplatesFile(_TemplateDoc):
    """templates.json of a run."""

    library: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    decisions: Annotated[list[TemplateDecision], Field(max_length=2000)] = Field(default_factory=list)


for _name, _cls in (("template.meta", TemplateMeta), ("template.decision", TemplateDecision),
                    ("template.run", RunTemplate), ("template.file", TemplatesFile)):
    REGISTRY.register_payload(_name, 1, _cls)
