"""template-library/1: the Template bases and their pure checks (library design section 9.2).

Every artifact section has a GENERIC template (the fixed layout of its artifact type: J2 keeps it as data, in
`templates/<type>/generic.json`, and this library holds no copy of it) and, per workflow, a SPECIALISED template the
engine generates from the workflow's context. This
module owns what a template IS and what makes one valid; the engine keeps the router, the library directory, codegen and
the prompts (it imports this module, never the other way round).

    FieldSpec, ObjectSpec, MadeBy, Context, Use     the parts
    GenericTemplate, SpecialisedTemplate            family "template", kinds generic and specialised (closed, frozen)
    shape_problems, rule_problems, resolve, keeps_problems, refusal      the checks: lists of reasons, never a raise
    build_model, transport, validate                the runtime class from a spec (pydantic.create_model), its draft-07
                                                    transport schema, and (data) -> (dict or None, errors)
    TemplateMeta, TemplateDecision, RunTemplate, TemplatesFile           the files of a run's own copy (J2 sync 33aeeda)
    RunTemplateBundle, RunTemplateWorkflow, RunTemplateUse, AutoReuse    J2 `run-template/1` (the bundle of a finished run, library/run-templates/<id>/template.json)
                                                                         and what templates.json says about the one a run started from (J2 1adb8ecd)
    run_tpl_rel, RUN_TEMPLATE_FILES                 where a run keeps its copy of a template version

Differences from J2, each on purpose: a template is frozen (a changed sha or version is `evolve`); `rules` are `RuleSpec`
objects, so a rule that cannot run is refused when the template is built, and a path outside the template is a `Template`
error (`resolve`); every string and list is bounded; the built runtime class is a strict `Value`, as the artifact models
are. The `sha` of a template is J2's (sha256 of `content()` with the rules in their J2 dict form), so templates stored by
J2 keep their shas. codegen (model.py) stays with the engine.
"""
import copy
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Annotated, Any, ClassVar, Literal, Optional, Self

from pydantic import Field, StringConstraints, create_model, model_validator

from .base import Record, Value
from .registry import REGISTRY, record, transport_schema
from .rules import RULE_TYPES, RuleSpec, spec_problems
from .types import ArtifactName, JsonObject

__all__ = [
    "SCHEMA", "VERSION", "MAX_FIELDS", "RUN_TEMPLATE_FILES", "TemplateArtifact", "FieldSpec", "ObjectSpec", "MadeBy",
    "Context", "Use", "Template", "GenericTemplate", "SpecialisedTemplate", "TemplateMeta", "TemplateCandidate",
    "TemplateDecision", "RunTemplate", "TemplatesFile", "RunTemplateBundle", "RunTemplateWorkflow", "RunTemplateUse", "AutoReuse",
    "AutoScore", "RUN_TEMPLATE_SCHEMA", "RUN_TEMPLATE_DIR", "MetaMadeBy", "Business", "CollectedFrom", "sha_of", "generic_ref", "shape_problems", "rule_problems",
    "resolve", "keeps_problems", "refusal", "spec_json", "slug", "errors_of", "normalise", "class_name", "build_model",
    "transport", "validate", "run_tpl_rel",
]

SCHEMA = "template-library/1"
RUN_TEMPLATE_SCHEMA = "run-template/1"          # J2 j2_template_lib.RUN_TEMPLATE_SCHEMA
RUN_TEMPLATE_DIR = "run-templates"              # library/run-templates/<id>/{template.json, schema.json}
VERSION = 1
TemplateArtifact = ArtifactName          # the name of an output type, by shape: the types are data
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


def slug(text) -> str:
    """J2's `slug` (j2_template_lib): lowercase, runs of anything else become one "-", "template" for nothing."""
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "template"


def errors_of(e):
    """The error lines of a pydantic error, in its own words ("where: message"), so a retry can quote them."""
    out = []
    for err in getattr(e, "errors", lambda: [])() or []:
        where = ".".join(str(x) for x in err.get("loc") or ()) or "section"
        out.append(f"{where}: {err.get('msg')}")
    return out or [str(e).splitlines()[0]]


def normalise(model, data: Any):
    """Enum values read case-insensitively and written back in the model's own casing, before validation. The enums are
    the model's `ENUMS` (a template's own enum fields, set by `build_model`)."""
    if not isinstance(data, dict):
        return data
    d = copy.deepcopy(data)
    enums = getattr(model, "ENUMS", None) or {}

    def walk(node):
        if isinstance(node, list):
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for k, v in list(node.items()):
                if k in enums and isinstance(v, str):
                    low = v.strip().lower()
                    node[k] = next((x for x in enums[k] if x.lower() == low), v)
                else:
                    walk(v)
    walk(d)
    return d


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
    """The generic layer: one per (artifact, section), as J2 keeps it in `templates/<type>/generic.json`."""

    kind: Literal["generic"] = "generic"


@record
class SpecialisedTemplate(Template):
    """A workflow's own template: extends one generic. That it keeps every required field of the generic is
    `keeps_problems(generic, template)`, checked by whoever holds the generic (J2's file); this library holds none."""

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


def spec_json(t) -> dict[str, Any]:
    """spec.json as J2 writes it: a generic without its empty keys, a specialised one without `used_by` (that lives in
    meta.json); rules as J2 dicts; no `schema_version` (the library's own, not part of J2's file)."""
    if t.kind == "generic":
        data = t.model_dump(exclude_none=True, exclude={"schema_version"})
    else:
        data = t.model_dump(exclude={"used_by", "schema_version"})
    data["rules"] = [r.as_j2() for r in t.rules]
    return data


# ---------------------------------------------------------------- runtime: the class is built from the spec
class TemplateBase(Value):
    TEMPLATE: ClassVar[str] = "template"
    SECTION: ClassVar[str] = ""
    ENUMS: ClassVar[dict] = {}

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


def _optional_names(t, reply_optional=(), generic=None):
    """The transport marks a field optional when the caller names it (`reply_optional`: what the type's generic.json says
    a reply may leave out, J2's own list; the library holds none) or when the template added it as not required. Which
    fields are the generic's own is the caller's `generic` (a template); without one, every field the template says is not
    required counts as added."""
    own = {f.name for f in generic.fields} | {f.name for o in generic.objects for f in o.fields} if generic is not None else set()
    added = {f.name for f in t.fields if not f.required and f.name not in own}
    added |= {f.name for o in t.objects for f in o.fields if not f.required and f.name not in own}
    return frozenset(added | set(reply_optional))


def _enums(t):
    """{field name: allowed values} of every string enum field of the template, for `normalise`."""
    out = {}
    for f in [*t.fields, *(f for o in t.objects for f in o.fields)]:
        if f.enum:
            out.setdefault(f.name, list(f.enum))
    return out


def build_model(t, reply_optional=(), generic=None):
    """The runtime class of a template, from its spec with pydantic.create_model (cached by the sha of its content). model.py is never
    imported for this. Every class carries the template's optional names as its `TRANSPORT_OPTIONAL` (see `_optional_names`)."""
    t = _as_template(t)
    optional = _optional_names(t, reply_optional, generic)
    key = (t.compute_sha(), t.version, t.name, optional)          # never the stored sha: a stale one must not find another class
    if key in _BUILT:
        return _BUILT[key]
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
    cls.ENUMS = _enums(t)
    cls.TRANSPORT_OPTIONAL = optional
    if len(_BUILT) >= _BUILT_MAX:
        _BUILT.pop(next(iter(_BUILT)))
    _BUILT[key] = cls
    return cls


def transport(t, reply_optional=(), generic=None):
    """schema.json: the draft-07 transport schema of a template (definitions, closed objects, nothing the transport
    forbids), from its runtime class. `reply_optional` and `generic`: see `_optional_names`."""
    return transport_schema(build_model(_as_template(t), reply_optional, generic))


def validate(t, data):
    """(dict or None, [errors]): the template's runtime class on the data, enum casing normalised first. Whatever the
    generic adds beyond fields (J2's `requires_one_of`) is J2's check, run by the engine on its own generic file."""
    t = _as_template(t)
    model = build_model(t)
    try:
        obj = model.model_validate(normalise(model, data))
    except Exception as e:
        return None, errors_of(e)
    return obj.model_dump(by_alias=True), []


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


class MetaMadeBy(MadeBy):
    """`made_by` of a library meta.json: the four keys of a spec's `made_by` and, since J2 sync 4, the time it was made."""

    date: Optional[Annotated[str, StringConstraints(max_length=40)]] = None


class Business(Value):
    """The business a template version was made for (provenance of a library version, J2 sync 4)."""

    name: Line200
    type: Line200


class CollectedFrom(Value):
    """Which run's copy a library version was collected from (the finish step, D142)."""

    run: Line200
    where: Line200


class TemplateMeta(_TemplateDoc):
    """meta.json of one template version (a library version or a run's copy). A generic copy says `kind: "generic"` and
    has `used_by: []`; a specialised one has no `kind` key in J2, and carries the class name, the creation time and the
    fingerprints of the needs it answered. The keys after `used_by` are provenance: `made_by`, `business`, `mock` and
    `collected_from` (a library version, J2 sync 4; a run's copy of one carries them too) and, from J2 1adb8ecd,
    `renamed_from` ("name@N", the family and number a moved version had) and `adapted_from` ("name@N", the template an
    auto-reuse adaptation started from)."""

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
    made_by: Optional[MetaMadeBy] = None
    business: Optional[Business] = None
    mock: Optional[bool] = None
    collected_from: Optional[CollectedFrom] = None
    renamed_from: Optional[Line200] = None
    adapted_from: Optional[Line200] = None


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
    # J2 1adb8ecd, on the paths that use a run template, auto-reuse or the content door
    run_template: Optional[Annotated[str, StringConstraints(max_length=80)]] = None      # the run template this run follows (id)
    from_template: Optional[bool] = None                                                  # the template has a workflow for this section
    template_workflow: Optional[Line80] = None                                            # which one ("W-3")
    adapted_from: Optional[Line200] = None                                                # "name@N": the template this one was made over from
    new_family: Optional[bool] = None                                                     # adapted for another business: a family of its own
    first_refused: Optional[Text2000] = None                                              # why the run template's own section template was not adapted
    nearest: Optional[JsonObject] = None                                                  # the nearest template by fields (auto-reuse)
    nearest_refused: Optional[Text2000] = None                                            # why the nearest template was not adapted
    door: Optional[Literal["reuse", "adapt", "build", "unknown"]] = None                  # the content door's decision for this section


class RunTemplate(TemplateDecision):
    """A row of GET /api/run-templates: the decision plus where its template can be read from now."""

    source: Literal["from this run", "from library", "not recorded"]


class RunTemplateUse(Value):
    """`run_template` of templates.json: the run template this run follows, chosen by the Requester (`set_run_template`) or by
    auto-reuse (`auto`, `match`). `plans` and `workflows` are per-workflow state J2 keeps while the run goes (bounded open JSON)."""

    id: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    name: Name200
    selected: Annotated[list[Annotated[str, StringConstraints(max_length=40)]], Field(max_length=500)]
    added: Annotated[list[Annotated[str, StringConstraints(max_length=40)]], Field(max_length=500)] = Field(default_factory=list)
    of: Annotated[int, Field(ge=0, le=500)]
    plans: JsonObject = Field(default_factory=dict)
    workflows: Annotated[list[JsonObject], Field(max_length=500)] = Field(default_factory=list)
    added_stages: Optional[Annotated[list[Annotated[str, StringConstraints(max_length=40)]], Field(max_length=40)]] = None
    auto: Optional[bool] = None
    match: Optional[float] = None


class AutoScore(Value):
    """One run template scored against a run (J2 `match_run_templates`): the score and its three parts, and whether this run could
    take it (`eligible`; `why_not` says why not). `mock` is true, false or "not recorded"."""

    id: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    name: Name200
    score: float
    stages: float
    business: float
    covers: float
    template_stages: Annotated[list[Annotated[str, StringConstraints(max_length=40)]], Field(max_length=40)]
    business_type: Line200
    mock: bool | Literal["not recorded"]
    eligible: bool
    why_not: Optional[Text1000] = None


class AutoReuse(Value):
    """`auto_reuse` of templates.json (J2_AUTO_REUSE=1): the threshold and weights used, the stages asked for, the pick (an id, or
    null when no template reached the threshold) and every score."""

    threshold: float
    weights: dict[Line80, float]
    asked_stages: Annotated[list[Annotated[str, StringConstraints(max_length=40)]], Field(max_length=40)]
    picked: Optional[Annotated[str, StringConstraints(max_length=80)]] = None
    match: Optional[float] = None
    scores: Annotated[list[AutoScore], Field(max_length=500)] = Field(default_factory=list)


class TemplatesFile(_TemplateDoc):
    """templates.json of a run. `run_template` and `auto_reuse` appear only when a run template or auto-reuse was in play."""

    library: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    decisions: Annotated[list[TemplateDecision], Field(max_length=2000)] = Field(default_factory=list)
    run_template: Optional[RunTemplateUse] = None
    auto_reuse: Optional[AutoReuse] = None


# ---------------------------------------------------------------- run-template/1: the bundle of a finished run (J2 1adb8ecd)
NOT_RECORDED = "not recorded"
KEY_RE = re.compile(r"^W-[0-9]+$")
SLOT_RE = re.compile(r"<([a-z][a-z ]*)>")
ID_SLOTS = ("requirement ids", "component ids", "goal ids", "section ids")        # J2 `ID_SLOTS`: slots that are never facts
Key = Annotated[str, StringConstraints(pattern=r"^W-[0-9]+$", max_length=40)]
Stage = Annotated[str, StringConstraints(min_length=1, max_length=40)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80)]


class RunTemplateWorkflow(Value):
    """One workflow of a run template. `section_template` is "name@version" as the library holds it (the generic layout's own
    name when the run's builder filled the generic one); `covers` are done-when texts with slots, never facts."""

    key: Key
    name: Name200
    stage: Stage
    artifact: TemplateArtifact
    section: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    section_template: Name200
    section_template_kind: Literal["generic", "specialised", "not recorded"] = NOT_RECORDED
    depends_on: Annotated[list[Key], Field(max_length=500)] = Field(default_factory=list)
    covers: Annotated[list[Annotated[str, StringConstraints(max_length=2000)]], Field(max_length=300)] = Field(default_factory=list)
    made_from: Annotated[str, StringConstraints(max_length=40)] = ""        # the workflow's id in the run it was made from
    fix: bool = False                                                       # it fixed an Audit finding of that run


class RunTemplateBundle(Value):
    """`run-template/1`: all the workflows of one finished run, as `library/run-templates/<id>/template.json` (family payload
    `run_template.bundle`). Closed, and checked as J2 checks it at every write: workflow keys run W-1.. in order, each once;
    `depends_on` names earlier keys; every workflow's stage is one of `stages`, and the workflows are grouped by stage in that
    order; no slot is used that `facts_slots` does not list; `outputs` name a stage and the files inside its folder. The
    `schema` key is checked and written back by `to_json()`. Not a row of `GET /api/run-templates` (that is `RunTemplate`)."""

    id: Slug
    name: Name200
    description: Text2000 = ""
    business_type: Line200 = NOT_RECORDED
    made_from_run: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    mock: bool | Literal["not recorded"] = NOT_RECORDED
    stages: Annotated[list[Stage], Field(min_length=1, max_length=40)]
    workflows: Annotated[list[RunTemplateWorkflow], Field(min_length=1, max_length=500)]
    facts_slots: Annotated[list[Annotated[str, StringConstraints(max_length=200)]], Field(max_length=300)] = Field(default_factory=list)
    outputs: dict[Stage, JsonObject] = Field(default_factory=dict)
    made_by: JsonObject = Field(default_factory=dict)
    used_by: Annotated[list[JsonObject], Field(max_length=5000)] = Field(default_factory=list)
    created: Annotated[str, StringConstraints(max_length=40)] = ""

    @model_validator(mode="before")
    @classmethod
    def _schema_key(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and "schema" in data:
            if data["schema"] != RUN_TEMPLATE_SCHEMA:
                raise ValueError(f"schema must be {RUN_TEMPLATE_SCHEMA!r}, not {data['schema']!r}")
            data = {k: v for k, v in data.items() if k != "schema"}
        return data

    @model_validator(mode="after")
    def _checked(self) -> Self:
        bad: list[str] = []
        for stage, out in self.outputs.items():
            files = out.get("files")
            if stage not in self.stages or not isinstance(files, list) or not files or any(
                    not isinstance(f, str) or not f or f.startswith(("/", "..")) or "/../" in f for f in files):
                bad.append(f"outputs[{stage!r}] must name a stage and list its files, as paths inside its folder")
        if not self.name.strip():
            bad.append("id must be a slug and name must be given")
        keys = [w.key for w in self.workflows]
        if keys != [f"W-{i}" for i in range(1, len(keys) + 1)]:
            bad.append("workflow keys must run W-1, W-2, ... in order")
        for i, w in enumerate(self.workflows):
            if w.stage not in self.stages:
                bad.append(f"{w.key}: stage {w.stage!r} is not one of the template's stages")
            late = [d for d in w.depends_on if d not in keys[:i]]
            if late:
                bad.append(f"{w.key}: depends_on {late} names no earlier workflow")
        order = [w.stage for w in self.workflows]
        if [s for i, s in enumerate(order) if i == 0 or order[i - 1] != s] != self.stages:
            bad.append("the workflows must be grouped by stage, in the order of stages")
        used = {m for w in self.workflows for t in [w.name, *w.covers] for m in SLOT_RE.findall(t)}
        extra = sorted(used - set(self.facts_slots) - set(ID_SLOTS))
        if extra:
            bad.append(f"slots used but not listed in facts_slots: {extra}")
        if bad:
            raise ValueError("; ".join(bad))
        return self

    def to_json(self) -> dict[str, Any]:
        return {"schema": RUN_TEMPLATE_SCHEMA, **self.model_dump(by_alias=True, mode="json")}


for _name, _cls in (("template.meta", TemplateMeta), ("template.decision", TemplateDecision),
                    ("template.run", RunTemplate), ("template.file", TemplatesFile),
                    ("run_template.bundle", RunTemplateBundle)):
    REGISTRY.register_payload(_name, 1, _cls)
