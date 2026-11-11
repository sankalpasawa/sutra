"""artifact-schema/1: the SHAPE of every artifact J2 generates, as Pydantic 2 models built from data (J2_ARTIFACT_SCHEMA=1).

templates/<type>/generic.json is the hand-edited source of each output type's sections: their fields, types, which are
required, which enums they allow, the conditions they come from, the rules code holds them to and the lines their data
is rendered as. This file holds no section and no field. At load time it builds one model per section from that file
(model_for, section_models) and the whole-document model from the file's document-level template (doc_model), so
editing a field in generic.json changes the model, the schema the builder gets and the checks with no Python change.

The models say what fields an artifact's data has, their types, which are required and which enums they allow - and
nothing else. Every constraint (ids in order, references that point at an id that exists, hex colours, plain CSS, page
tags, anchors) is a rule, written as data beside the fields and run by j2_rules as its own layer. The one presence rule
that is shape is a template's "requires_one_of" (a page section must carry its markup or its head tags).

Two schemas per template, as the structured-output docs require:
  * the TRANSPORT schema, transport_schema(): what goes to the model. Draft-07 (2020-12 is refused by
    `claude --json-schema`), Pydantic's $defs rewritten to definitions, additionalProperties false on every object,
    every field required unless the brief may lack it (the template's "reply_optional"; the fields that are not
    required when it names none), no min/max, no length, no pattern, no format, no recursion.
  * the FULL rules, run by j2_rules on the validated data. Anything that needs another document (a component covering
    a requirement of an earlier document) is a ref_exists rule whose target names that document's type.

render_section() writes the markdown the existing parsers and conditions already read, from the template's "render"
lines, so nothing downstream changes: the agent sends data, code writes the document.

Python 3.9: Optional/List/Dict, never "X | None".
"""
import copy
import hashlib
import json
import keyword
import re
from functools import lru_cache
from typing import ClassVar, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

import j2_rules
import j2_types

SCHEMA = "artifact-schema/1"
VERSION = 1
DOCUMENT = j2_types.DOCUMENT      # the document-level template of a generic.json: the whole document, not a section
SEP = " · "                  # between a template's family and its section in its name
TYPE_RE = re.compile(r"^(?:string|integer|boolean|list\[string\]|list\[([A-Z][A-Za-z0-9]*)\]|([A-Z][A-Za-z0-9]*))$")


# ---------------------------------------------------------------- a template's fields, as data
class FieldSpec(BaseModel):
    """One field: a name, an allowed type, required or not, its description, and an enum when it is narrowed."""
    model_config = ConfigDict(extra="forbid")
    name: str
    type: str
    required: bool
    description: str = ""
    enum: Optional[List[str]] = None
    nullable: bool = False      # Optional[...] in the model: the value may be null


class ObjectSpec(BaseModel):
    """An object type defined inside the spec, used as <Object> or list[<Object>]."""
    model_config = ConfigDict(extra="forbid")
    name: str
    fields: List[FieldSpec]


def parse_type(t):
    """(kind, object name) for an allowed type: ("string"|"integer"|"boolean"|"list_string"|"list_obj"|"obj", name)."""
    m = TYPE_RE.match(str(t or ""))
    if not m:
        return None, None
    if m.group(1):
        return "list_obj", m.group(1)
    if m.group(2):
        return "obj", m.group(2)
    return ("list_string" if t == "list[string]" else t), None


def class_name(name, version=VERSION):
    """A class name made from a template's name and version ("Still Point classes", 2 -> StillPointClassesV2)."""
    base = "".join(w[:1].upper() + w[1:] for w in re.findall(r"[A-Za-z0-9]+", str(name or ""))) or "Template"
    if base[0].isdigit():
        base = "T" + base
    return f"{base}V{version}"


# ---------------------------------------------------------------- the model of a template, built from its fields
class Artifact(BaseModel):
    """Base of every artifact model: strict (no extra keys), and it carries the template name the records show."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)

    TEMPLATE: ClassVar[str] = "artifact/1"
    SECTION: ClassVar[str] = ""
    LABEL: ClassVar[str] = ""
    REPLY_OPTIONAL: ClassVar[frozenset] = frozenset()      # the field names a reply may leave out (transport_schema)
    ENUMS: ClassVar[dict] = {}                             # field name -> its allowed values (normalise)

    @classmethod
    def template(cls):
        return cls.LABEL or cls.TEMPLATE


_BUILT = {}


def attr(name):
    """The attribute a field is held in: its name, or name_ when the name is a Python keyword (the alias keeps it)."""
    return name + "_" if keyword.iskeyword(name) else name


def py_type(f, classes):
    kind, obj = parse_type(f.type)
    if kind == "string":
        tp = Literal[tuple(f.enum)] if f.enum else str
    elif kind == "integer":
        tp = int
    elif kind == "boolean":
        tp = bool
    elif kind == "list_string":
        tp = List[Literal[tuple(f.enum)]] if f.enum else List[str]
    elif kind == "list_obj":
        tp = List[classes[obj]]
    else:
        tp = classes[obj]
    if f.nullable or (kind == "obj" and not f.required):
        tp = Optional[tp]
    return tp


def field_args(f, blank=True):
    """What Field() gets for one field. blank=False leaves an empty description out of the schema, as a field written
    without one has none."""
    kind, _ = parse_type(f.type)
    args = {"description": f.description} if f.description or blank else {}
    if f.name != attr(f.name):
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


def obj_order(objects):
    """The object names, each after the objects its fields use (the order their classes are built in)."""
    objs, done, out = {o.name: o for o in objects}, set(), []

    def visit(n):
        if n in done or n not in objs:
            return
        done.add(n)
        for f in objs[n].fields:
            o = parse_type(f.type)[1]
            if o:
                visit(o)
        out.append(n)
    for o in objects:
        visit(o.name)
    return out


def _one_of(names, message):
    """Shape, not a constraint: the data must carry at least one of these fields (a page section's markup or its head
    tags). Everything else about the values is a rule."""
    def check(self):
        got = [getattr(self, attr(n), None) for n in names]
        if not any(v.strip() if isinstance(v, str) else v for v in got):
            raise ValueError(message)
        return self
    return model_validator(mode="after")(check)


def build_class(name, label, section, fields, objects=(), requires=(), optional=None, template=None, blank=True):
    """The Pydantic class of one template, from its fields and objects with pydantic.create_model (kept by content, so
    the same template gives the same class). name is the class name, label what the records call the template, and
    optional the field names a reply may leave out (None: the fields that are not required). blank=False keeps an
    empty description out of the schema (a generic template's schema has none for a field that says nothing)."""
    fields = [f if isinstance(f, FieldSpec) else FieldSpec.model_validate(f) for f in fields]
    objects = [o if isinstance(o, ObjectSpec) else ObjectSpec.model_validate(o) for o in objects]
    every = fields + [f for o in objects for f in o.fields]
    if optional is None:
        optional = [f.name for f in every if not f.required]
    requires = [{"fields": list(r["fields"]), "message": str(r["message"])} for r in requires or ()]
    key = schema_sha([name, label, section, template, [f.model_dump() for f in fields], [o.model_dump() for o in objects],
                      requires, sorted(optional), blank])
    if key in _BUILT:
        return _BUILT[key]
    classes, objs = {}, {o.name: o for o in objects}
    for n in obj_order(objects):
        classes[n] = create_model(n, __base__=Artifact, **{attr(f.name): (py_type(f, classes), Field(**field_args(f, blank)))
                                                           for f in objs[n].fields})
    checks = {f"_requires_{i}": _one_of(r["fields"], r["message"]) for i, r in enumerate(requires)}
    cls = create_model(name, __base__=Artifact, __validators__=checks or None,
                       **{attr(f.name): (py_type(f, classes), Field(**field_args(f, blank))) for f in fields})
    cls.LABEL = label
    cls.TEMPLATE = template or label.split(SEP)[0]
    cls.SECTION = section
    cls.REPLY_OPTIONAL = frozenset(optional)
    cls.ENUMS = {f.name: list(f.enum) for f in every if f.enum and parse_type(f.type)[0] == "string"}
    _BUILT[key] = cls
    return cls


# ---------------------------------------------------------------- the registry: generic.json -> one model per section
_GENERIC = {}      # id of a template entry -> (the entry, its class): an entry is rebuilt only when its file changed


def model_name(entry):
    """The class name of a generic template: its own "model", else one made from its name."""
    return entry.get("model") or class_name(entry.get("name"), entry.get("version") or VERSION)


def document_objects(kind, fields):
    """The objects a document-level template's fields use, taken from the type's own sections (an object a section
    defines, or a whole section by its model name), so the document never repeats them."""
    pool = {}
    for t in j2_types.template(kind):
        for o in t.get("objects") or []:
            pool.setdefault(o["name"], o["fields"])
    for t in j2_types.template(kind):
        pool.setdefault(model_name(t), t["fields"])
    done, out = set(), []

    def visit(n):
        if n in done or n not in pool:
            return
        done.add(n)
        for f in pool[n]:
            o = parse_type(f.get("type"))[1]
            if o:
                visit(o)
        out.append(ObjectSpec.model_validate({"name": n, "fields": pool[n]}))
    for f in fields:
        o = parse_type(f.type)[1]
        if o:
            visit(o)
    return out


def entry_spec(kind, entry):
    """(fields, objects) of one generic.json template, as FieldSpec and ObjectSpec."""
    fields = [FieldSpec.model_validate(f) for f in entry.get("fields") or []]
    if entry.get("section") == DOCUMENT and "objects" not in entry:
        return fields, document_objects(kind, fields)
    return fields, [ObjectSpec.model_validate(o) for o in entry.get("objects") or []]


def entry_label(kind, entry):
    """What the records call a generic template: its name (the document-level one without its closing "Document")."""
    label = str(entry.get("name") or kind)
    if entry.get("section") == DOCUMENT and label.endswith(SEP + DOCUMENT):
        label = label[:-len(SEP + DOCUMENT)]
    return label


def _entry_class(kind, entry):
    hit = _GENERIC.get(id(entry))
    if hit is not None and hit[0] is entry:
        return hit[1]
    fields, objects = entry_spec(kind, entry)
    cls = build_class(model_name(entry), entry_label(kind, entry), "" if entry.get("section") == DOCUMENT else entry["section"],
                      fields, objects, entry.get("requires_one_of") or (), entry.get("reply_optional"), blank=False)
    _GENERIC[id(entry)] = (entry, cls)
    return cls


def kinds():
    """Every artifact that has a template: the output types of artifacts/types.json and the style guide a form names."""
    return j2_types.templated()


def section_models(kind):
    """{section: model} of one artifact, in its template's order ({} when it has no template)."""
    return {t["section"]: _entry_class(kind, t) for t in j2_types.template(str(kind or ""))}


def model_for(kind, section):
    """The model one workflow writes, by output kind and section name (None when there is none). An artifact with one
    template has one model, whatever the section is called."""
    by = section_models(kind)
    if section in by:
        return by[section]
    want = re.sub(r"[^a-z0-9]+", " ", str(section or "").lower()).strip()
    for name, m in by.items():
        if re.sub(r"[^a-z0-9]+", " ", name.lower()).strip() == want:
            return m
    return next(iter(by.values())) if len(by) == 1 else None


def doc_model(kind):
    """The whole artifact as one model: the document-level template of its generic.json, or its one section's model
    when it has a single template (None otherwise)."""
    d = j2_types.document(str(kind or ""))
    if d is not None:
        return _entry_class(kind, d)
    by = section_models(kind)
    return next(iter(by.values())) if len(by) == 1 else None


def reply_optional(kind):
    """Every field name a reply may leave out in any section of one artifact: what a specialised template, which may
    carry the fields of several of its artifact's sections, starts from."""
    return frozenset(n for m in section_models(kind).values() for n in m.REPLY_OPTIONAL)


def section_conditions(kind, section):
    """Which conditions a section's rules come from, for the records (the conditions themselves stay in conditions/)."""
    return list((j2_types.section_template(str(kind or ""), section) or {}).get("conditions") or [])


# ---------------------------------------------------------------- the transport schema
_STRIP = ("minLength", "maxLength", "minItems", "maxItems", "pattern", "format", "exclusiveMinimum",
          "exclusiveMaximum", "minimum", "maximum", "multipleOf", "default", "title", "examples", "const")


def _clean(node, optional=frozenset()):
    """One schema node as the transport allows it: no length, pattern, format or default, anyOf [X, null] folded into
    a type list, objects closed, and every property required unless its name is in optional."""
    if not isinstance(node, dict):
        return node
    out = {k: v for k, v in node.items() if k not in _STRIP}
    if "anyOf" in out:      # Optional[X] -> {"type": [x, "null"]}
        parts = [_clean(x, optional) for x in out.pop("anyOf")]
        nullable = any(p.get("type") == "null" for p in parts)
        real = [p for p in parts if p.get("type") != "null"]
        if len(real) == 1 and isinstance(real[0].get("type"), str):
            out.update(real[0])
            out["type"] = [real[0]["type"], "null"] if nullable else real[0]["type"]
        elif real:
            out["anyOf"] = real
    for key in ("properties", "definitions", "$defs"):
        if isinstance(out.get(key), dict):
            out[key] = {k: _clean(v, optional) for k, v in out[key].items()}
    if isinstance(out.get("items"), dict):
        out["items"] = _clean(out["items"], optional)
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        props = list((out.get("properties") or {}).keys())
        out["required"] = [p for p in props if p not in optional] or props
    return out


def transport_schema(model):
    """The draft-07 schema sent to the model: generated from the model, so the two can never drift. Pydantic's $defs
    become definitions (2020-12 is refused by `claude --json-schema`), reason comes first, and nothing the transport
    forbids is left in."""
    raw = json.loads(json.dumps(model.model_json_schema(by_alias=True)).replace("#/$defs/", "#/definitions/"))
    raw.pop("$schema", None)
    if "$defs" in raw:
        raw["definitions"] = raw.pop("$defs")
    out = _clean(copy.deepcopy(raw), getattr(model, "REPLY_OPTIONAL", frozenset()))
    out = {"$schema": "http://json-schema.org/draft-07/schema#", **out}
    return out


def inline_definitions(schema):
    """schema with its own definitions written in place of every $ref to them, and no definitions block: a schema
    that sits inside another schema's property can't keep them (`claude --json-schema` resolves #/definitions/X from
    the root only; the first page builder's reply schema carried Design's as a nested block and the CLI refused it
    before any model call, runs/j2-20261103-184249 W-24 to W-35). A reference to itself stays a $ref."""
    defs = schema.get("definitions") or {}

    def walk(x, stack):
        if isinstance(x, list):
            return [walk(v, stack) for v in x]
        if not isinstance(x, dict):
            return x
        name = str(x.get("$ref") or "")[len("#/definitions/"):] if str(x.get("$ref") or "").startswith("#/definitions/") else None
        if name in defs and name not in stack:
            return walk({**defs[name], **{k: v for k, v in x.items() if k != "$ref"}}, stack + (name,))
        return {k: walk(v, stack) for k, v in x.items() if k != "definitions"}
    return walk(schema, ())


def reply_schema(model, extra_fields):
    """The whole reply as one object: the fields a builder already returns (reason first), plus "section", its own
    section model. extra_fields is {name: schema} for the optional board, spec and design fields; each is written
    with its definitions in place (inline_definitions), so the reply's only definitions are the section's."""
    sec = transport_schema(model)
    defs = sec.pop("definitions", None)
    sec.pop("$schema", None)
    props = {"reason": {"type": "string", "description": "one short sentence: why you decided this"},
             "say": {"type": "string", "description": "one short line reporting to @Coordination: what you changed; "
                                                      "code runs your checks and reports them, so don't claim they "
                                                      "pass"},
             "human_output": {"type": "string", "description": "1 to 3 plain sentences telling a person what you "
                                                               "built"},
             "atom_human_output": {"type": "string", "description": "1 or 2 plain sentences telling the Requester "
                                                                    "what this part created, in everyday words"},
             "next": {"type": "string", "description": "Coordination"},
             "section": sec}
    props.update({k: inline_definitions(v) for k, v in (extra_fields or {}).items()})
    out = {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object", "additionalProperties": False,
           "properties": props,
           "required": ["reason", "say", "human_output", "atom_human_output", "next", "section"]}
    if defs:
        out["definitions"] = defs
    return out


def schema_sha(schema):
    return hashlib.sha256(json.dumps(schema, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def schema_name(model):
    return model.template()


def validate(model, data):
    """(object or None, [error lines]) for one section's data, with the full rules. The errors are Pydantic's own
    words, so a retry can quote them."""
    try:
        return model.model_validate(data), []
    except Exception as e:
        return None, errors_of(e)


def errors_of(e):
    out = []
    for err in getattr(e, "errors", lambda: [])() or []:
        where = ".".join(str(x) for x in err.get("loc") or ()) or "section"
        out.append(f"{where}: {err.get('msg')}")
    return out or [str(e).splitlines()[0]]


def normalise(model, data):
    """Enum values read case-insensitively and written back in the model's own casing, before validation."""
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


# ---------------------------------------------------------------- rendering: code writes the document, not the agent
# A section's template says how its data is written ("render" in generic.json): a list of blocks, each one
#   {"text": "<line>"}                          one line from the section's own fields
#   {"each": "<list field>", "line": "<line>"}  one line per item ("head": lines always written first; "join": what
#                                               sits between the lines, a new line unless given; "unless": leave out
#                                               the items that have this field)
# joined by a new line ("gap": true puts an empty line before the block), with the blocks marked "after_body" added
# after the body, one per line. In a line, {field} is a value (a list is joined with ", "; {#} is the item's number,
# {_} the item itself, {a.b} a field of an object), {field|words} uses the words when the value is empty, {field:nodot}
# drops a closing full stop, {field:cap} starts with a capital, {field:yesno} writes yes or no, and [ ... ] is written
# only when every value inside it is given. The agent sends data; no agent writes a heading.
FILTERS = ("nodot", "cap", "yesno")


@lru_cache(maxsize=None)
def line_parts(text):
    """A render line read once: (("text", str) | ("value", spec) | ("maybe", parts), ...). ValueError on an open { or [."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "{[":
            j = text.find("}" if c == "{" else "]", i)
            if j < 0:
                raise ValueError(f"render line {text!r}: {c} is never closed")
            inner = text[i + 1:j]
            out.append(("value", inner) if c == "{" else ("maybe", line_parts(inner)))
            i = j + 1
        else:
            j = min([x for x in (text.find("{", i), text.find("[", i)) if x >= 0] or [n])
            out.append(("text", text[i:j]))
            i = j
    return tuple(out)


def value_spec(spec):
    """(path, filter, default words) of one {value}: "needs|uses the page" -> ("needs", "", "uses the page")."""
    body, _, default = spec.partition("|")
    path, _, how = body.partition(":")
    return path, how, default


def _value(spec, item, index):
    """(the value as given, the words written for it) for one {value} of a line."""
    path, how, default = value_spec(spec)
    if path == "#":
        v = index
    elif path == "_":
        v = item
    else:
        v = item
        for key in path.split("."):
            v = v.get(key) if isinstance(v, dict) else None
    if how == "yesno":
        s = "yes" if v else "no"
    elif isinstance(v, list):
        s = ", ".join(str(x) for x in v)
    else:
        s = "" if v is None else str(v)
    if how == "nodot":
        s = s.rstrip(".")
    elif how == "cap":
        s = s[:1].upper() + s[1:]
    return v, (s or default)


def _line(parts, item, index):
    out = []
    for kind, x in parts:
        if kind == "text":
            out.append(x)
        elif kind == "value":
            out.append(_value(x, item, index)[1])
        elif all(_value(y, item, index)[0] for k, y in x if k == "value"):
            out.append(_line(x, item, index))
    return "".join(out)


def _block_lines(block, data):
    if "text" in block:
        return [_line(line_parts(block["text"]), data, 0)]
    items = data.get(block.get("each")) or []
    if block.get("unless"):
        items = [x for x in items if not (isinstance(x, dict) and x.get(block["unless"]))]
    return [_line(line_parts(block["line"]), x, i) for i, x in enumerate(items, 1)]


def render_section(kind, section, data):
    """The markdown of one section, from its validated data: "## <Section>" and the body, in the shape the readers
    expect, written from the section template's render lines. Returns None when the template has none (or there is no
    such section)."""
    blocks = (j2_types.section_template(str(kind or ""), section) or {}).get("render")
    if blocks is None:
        return None
    d = dict(data or {})
    body, after = "", ""
    for b in blocks:
        lines = _block_lines(b, d)
        if b.get("after_body"):
            after += "".join(f"\n{x}" for x in lines)
            continue
        text = str(b.get("join", "\n")).join(lines)
        if b.get("head"):
            text = f"{b['head']}\n{text}"
        if text:
            body += (("\n\n" if b.get("gap") else "\n") if body else "") + text
    return f"## {section}\n\n{body.strip()}{after}\n"


def style_from_design(data):
    """The style guide's data as the style guide the rest of the code already uses (style_css, style.json): the fields
    of the style guide's template, in its order, so nothing downstream changes."""
    d = dict(data or {})
    t = next(iter(j2_types.template(j2_types.style_guide() or "")), None) or {}
    objs = {o["name"]: o["fields"] for o in t.get("objects") or []}
    out = {}
    for f in t.get("fields") or []:
        kind, obj = parse_type(f["type"])
        v = d.get(f["name"])
        if kind == "obj":
            out[f["name"]] = {g["name"]: (v or {}).get(g["name"]) for g in objs.get(obj) or []}
        else:
            out[f["name"]] = (v or "") if kind == "string" and not f.get("required") and not f.get("nullable") else v
    return out


# ---------------------------------------------------------------- the rules layer (code, every attempt)
# The rules themselves are data in each template; these are here so the callers keep one import.
rule_names = j2_rules.rule_names
rules_count = j2_rules.rules_count
run_rules = j2_rules.run_rules
