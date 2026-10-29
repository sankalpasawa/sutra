"""layers/prompts.py -- the typed prompt compiler (PRD amendment A1.16, W1-CORE; retired the .md bundle, W3-PROOF X1).

A prompt part is three interface pieces and two implementation pieces. The interface (layer_schema.PROMPTS) names its
fields (what the owner may change, and their types), its inputs (the names code fills) and its returns (the answer
contract, verbatim, which the owner cannot change). A layer's implementation holds its WORDS (the default value of each
field) and its LAYOUT (the template that arranges them), in layers/<layer>/v<N>.py:

    WORDS[group][part]  = {field: value}
    LAYOUT[group][part] = a template. Its markers are {task}, {guidance}, {text}, {items} (rendered as lines '- x') and
                          {returns}, and {{name}} for an input. It is filled in one pass, and a value is never scanned
                          again, so nothing a value holds is read as a marker.

compile_layout() fills one; words() reads a part's fields as a department reads them now; prompt() is the words an agent
is sent. Every part is served by the words and the layout of a version: the one a department pins, else the layer's default
version (a version that extends another holds its parent's through layers.inherit, so the pinned one always does). There is
no other source: the .md files that held the words before they moved into the layers and their reader
are deleted, and a part no version holds words for is a fault (faults()), never a blank.

THE OWNER'S VALUES (A1.16, W1-CORE K2): a field the owner changed is a typed value in {ref}/instructions.json, written on a
stamp. words() and prompt() overlay those values on the implementation's defaults, so a stamped value is the next run's
words and a value equal to the default is not kept (a later default reaches the department). A whole-file copy made under
M2.2 ({ref}/prompts/<fn>/<file>.md) is kept as the owner's note: no run reads it, and it is the one .md path that stays.
"""
import copy
import re

from layers import W, S  # lazy proxies: tests reload the runtime

#: a marker of a layout: {{name}} (an input code fills) or one of the five field markers
MARKER = re.compile(r"\{\{([a-z_]+)\}\}|\{(task|guidance|text|items|returns)\}")
SLOT = re.compile(r"\{\{([a-z_]+)\}\}")


def who(layer, group, part):
    """A part as the errors name it: Identity's take instructions, gate."""
    return "%s's %s instructions, %s" % (S.TITLE.get(layer) or str(layer).title(), group, part)


# ---- the compiler ----------------------------------------------------------------------------------------------------
def compile_layout(layout, values, returns, inputs, part=None):
    """A layout filled, in one pass: {task}, {guidance} and {text} with their values, {items} as lines '- x', {returns}
    with the answer contract, and {{name}} with the input code gave. A value is never scanned again. A marker with no
    value is an error, never a blank: ValueError naming `part` (see who())."""
    part = part or "a prompt"

    def fill(m):
        if m.group(1):
            if m.group(1) not in inputs:
                raise ValueError("%s: the app fills no {{%s}}" % (part, m.group(1)))
            return str(inputs[m.group(1)])
        name = m.group(2)
        if name == "returns":
            if returns is None:
                raise ValueError("%s: the part has no answer contract to put at {returns}" % part)
            return returns
        if name not in values:
            raise ValueError("%s: no %s to put at {%s}" % (part, name, name))
        value = values[name]
        return "\n".join("- %s" % x for x in value) if name == "items" and isinstance(value, (list, tuple)) else str(value)
    return MARKER.sub(fill, layout)


def _holds(module, group, part):
    return module is not None and part in (getattr(module, "WORDS", None) or {}).get(group, {}) \
        and part in (getattr(module, "LAYOUT", None) or {}).get(group, {})


def _module(ref, layer, group, part):
    """The implementation that serves a part: the one the department pins when it holds words and a layout for the part, else
    the layer's default version when it does; None when neither does."""
    import layers
    module = layers.impl(ref, layer)
    if _holds(module, group, part):
        return module
    default = layers.load(S.DEFAULT_PINS.get(layer))
    return default if _holds(default, group, part) else None


def _serving(ref, layer, group, part):
    """The module that serves a part, or the error that names why none does: the interface names no such part, or no version
    holds words for it (never a blank, never another source)."""
    if ((S.PROMPTS.get(layer) or {}).get(group) or {}).get(part) is None:
        raise ValueError("%s's %s instructions have no part %s" % (str(layer).title(), group, part))
    module = _module(ref, layer, group, part)
    if module is None:
        raise ValueError("%s: no version holds words for this part" % who(layer, group, part))
    return module


def defaults(ref, layer, group, part):
    """A part's fields as the implementation that serves it ships them: {field: value}, its WORDS. The owner's values are not
    in it (see words())."""
    return copy.deepcopy(_serving(ref, layer, group, part).WORDS[group][part])


def words(ref, layer, group, part):
    """A part's fields as the department reads them now: the defaults with the owner's stamped values laid over them."""
    out = defaults(ref, layer, group, part)
    for field, value in owner_values(ref, layer, group, part).items():
        if field in out:
            out[field] = copy.deepcopy(value)
    return out


def prompt(ref, layer, group, part, **inputs):
    """One part of a layer's instructions, compiled: the words its agent is sent. The serving implementation's WORDS and
    LAYOUT, with the owner's stamped values laid over the defaults. A marker the code gives no value is an error, never a
    blank."""
    module = _serving(ref, layer, group, part)
    return compile_layout(module.LAYOUT[group][part], words(ref, layer, group, part), S.PROMPTS[layer][group][part]["returns"],
                          inputs, who(layer, group, part))


def sample_inputs(layer, group, part):
    """Inputs for a compile that stands for no department: each name, as its own sample word."""
    return {name: "<%s>" % name for name in S.PROMPTS[layer][group][part]["inputs"]}


def part_faults(layer, group, part, values, layout):
    """What keeps one typed part from serving: a part the interface does not name, a value that is not its field's type
    (S.validate_field), and whatever layout_faults finds. [] when it serves."""
    if ((S.PROMPTS.get(layer) or {}).get(group) or {}).get(part) is None:
        return ["%s has no part %s.%s" % (S.TITLE.get(layer, layer), group, part)]
    return ["%s: %s" % (field, f[3:] if f.startswith("$: ") else f) for field in (values or {})
            for f in S.validate_field(layer, group, part, field, values[field])] + layout_faults(layer, group, part, values, layout)


def layout_faults(layer, group, part, values, layout):
    """What keeps one layout from arranging its part: a marker the app cannot fill ({{name}} that is no input, a field
    marker the part has no field for or that WORDS holds no value of), a field the layout never reads (an owner's change
    that would do nothing), an answer contract the layout leaves out, and a compile with sample inputs that does not hold
    the returns verbatim or leaves a marker. [] when it arranges."""
    spec = ((S.PROMPTS.get(layer) or {}).get(group) or {}).get(part)
    if spec is None:
        return ["%s has no part %s.%s" % (S.TITLE.get(layer, layer), group, part)]
    out, named = [], set()
    for m in MARKER.finditer(layout or ""):
        if m.group(1):
            if m.group(1) not in spec["inputs"]:
                out.append("the layout holds {{%s}} and the app fills no such input" % m.group(1))
        elif m.group(2) == "returns":
            named.add("returns")
            if spec["returns"] is None:
                out.append("the layout holds {returns} and the part has no answer contract")
        else:
            named.add(m.group(2))
            if m.group(2) not in spec["fields"]:
                out.append("the layout holds {%s} and the part has no field %s" % (m.group(2), m.group(2)))
            elif m.group(2) not in (values or {}):
                out.append("the layout holds {%s} and WORDS holds no %s" % (m.group(2), m.group(2)))
    out += ["the layout never reads the field %s" % f for f in spec["fields"] if f not in named]
    if spec["returns"] is not None and "returns" not in named:
        out.append("the layout leaves out the answer contract")
    if out:
        return out
    try:
        got = compile_layout(layout, values, spec["returns"], sample_inputs(layer, group, part), who(layer, group, part))
    except ValueError as exc:
        return [str(exc)]
    if spec["returns"] is not None and spec["returns"] not in got:
        out.append("the compiled part does not hold the answer contract verbatim")
    left = re.findall(r"\{\{[^{}]*\}\}|\{(?:task|guidance|text|items|returns)\}", got)
    return out + (["the compiled part still holds %s" % ", ".join(sorted(set(left)))] if left else [])


def unserved(layer, module):
    """The parts of a layer's prompts a version holds no WORDS for, as 'group.part', in the interface's order: what keeps an
    agent from being sent them. [] when it holds every part (an added part, S.ADDED_PARTS, among them: it has no other source)."""
    words_ = getattr(module, "WORDS", None) or {}
    return ["%s.%s" % (group, part) for group, parts in (S.PROMPTS.get(layer) or {}).items() for part in parts
            if part not in (words_.get(group) or {})]


def faults():
    """The covering check of every function's words, at the definitions load: for each part its default implementation
    holds as WORDS and LAYOUT, that it serves (part_faults), and for each part of the interface it holds none for, that fault.
    [] when every function has its words."""
    import layers
    out = []
    for layer in S.FUNCTION_LAYERS:
        module = layers.load(S.DEFAULT_PINS[layer])
        for group, parts in (getattr(module, "WORDS", None) or {}).items():
            for part, values in parts.items():
                out += ["%s: %s" % (who(layer, group, part), f) for f in
                        part_faults(layer, group, part, values, ((getattr(module, "LAYOUT", None) or {}).get(group) or {}).get(part))]
        out += ["%s: the version holds no words for it" % who(layer, *name.split(".")) for name in unserved(layer, module)]
    return out


# ---- the owner's typed values (PRD A1.16, M2.6) ------------------------------------------------------------------------
#: where a department keeps them: {ref}/instructions.json, DEFS 'instructions', checked at the sink (website_dept._write)
VALUES_FILE = "instructions.json"
#: the version of instructions.json itself (the `instructions` definition holds `schema_version` at 1): it is not the interface's version
VALUES_VERSION = 1


def values_path(ref):
    return W.ddir(ref) / VALUES_FILE


def owner_doc(ref):
    """{ref}/instructions.json as it is stored: {schema_version, values, ...}. An empty document when the department has
    none, or none that can be read."""
    try:
        doc = W._read(values_path(ref), None) if ref else None
    except ValueError:                                       # not a department ref: it holds nothing of the owner's
        doc = None
    if not isinstance(doc, dict) or not isinstance(doc.get("values"), dict):
        return {"schema_version": VALUES_VERSION, "values": {}}
    return doc


def owner_values(ref, layer, group, part):
    """The owner's stamped values for one part, {field: value}: those that still pass the interface (a value the
    interface no longer takes is not used, and the default stands)."""
    entries = ((((owner_doc(ref).get("values") or {}).get(layer) or {}).get(group) or {}).get(part)) or {}
    return {field: e["value"] for field, e in entries.items()
            if isinstance(e, dict) and "value" in e and not S.validate_field(layer, group, part, field, e["value"])}


def owner_entry(ref, layer, group, part, field):
    """One stamped value as stored, {value, at, ask}; None when the owner has not changed that field."""
    e = (((((owner_doc(ref).get("values") or {}).get(layer) or {}).get(group) or {}).get(part)) or {}).get(field)
    return e if isinstance(e, dict) and "value" in e else None


#: the interface's faults for a field, in words the owner reads (the path is '$' for the value, '$[2]' for the third item).
#: Each pattern takes the interface's whole message, so none of its own words stay behind the owner's sentence (the two
#: markers' messages go on with a clause of their own, which the owner's sentence already says)
_FAULT_SAYS = (
    (re.compile(r"^shorter than 1$"), "is empty"),
    (re.compile(r"^shorter than (\d+)$"), r"is shorter than \1 characters"),
    (re.compile(r"^longer than (\d+)$"), r"is longer than \1 characters"),
    (re.compile(r"^holds '\{\{' or '\}\}'.*$"), "cannot hold '{{' or '}}', which only the app writes"),
    (re.compile(r"^holds 'Return ONLY'.*$"), "cannot hold 'Return ONLY': the shape of the answer belongs to the app"),
    (re.compile(r"^holds a control character$"), "holds a character that cannot be shown"),
    (re.compile(r"^holds a line break$"), "must be one line"),
    (re.compile(r"^fewer than (\d+) items?$"), r"needs at least \1 of them"),
    (re.compile(r"^more than (\d+) items$"), r"can hold at most \1 of them"),
    (re.compile(r"^is not a string$"), "has to be words"),
    (re.compile(r"^is not a list$"), "has to be a list"),
)


def plain_faults(label, faults):
    """The interface's faults for one field, in plain words: 'the task is longer than 1200 characters'. `label` is how the
    owner calls the field ('the task'). A fault this does not know is said as the interface says it."""
    out = []
    for f in faults:
        where, _, what = f.partition(": ")
        n = re.search(r"\[(\d+)\]", where)
        said = next((rx.sub(then, what) for rx, then in _FAULT_SAYS if rx.search(what)), what)
        out.append("%s%s %s" % (label, " (item %d)" % (int(n.group(1)) + 1) if n else "", said))
    return out


def store(ref, layer, group, part, field, value, ask=None):
    """The owner's value for one field, stamped: {ref}/instructions.json written whole and atomically, through the sink.
    A value equal to the implementation's default is removed, so a later default reaches the department; a document left
    with nothing in it goes. Checked again here, whatever checked it when it was asked: ValueError, in plain words, and
    nothing written, when the field or the whole document does not fit the interface. Returns 'set', 'removed' or 'same'."""
    faults = S.validate_field(layer, group, part, field, value)
    if faults:
        raise ValueError("; ".join(plain_faults(field, faults)))
    with W._lock(ref):
        doc = copy.deepcopy(owner_doc(ref))
        fields = defaults(ref, layer, group, part)
        part_values = doc["values"].setdefault(layer, {}).setdefault(group, {}).setdefault(part, {})
        before = part_values.get(field)
        if field in fields and value == fields[field]:
            part_values.pop(field, None)
            result = "removed" if before else "same"
        elif before and before.get("value") == value:
            result = "same"
        else:
            part_values[field] = dict({"value": value, "at": W.now()}, **({"ask": str(ask)[:40]} if ask else {}))
            result = "set"
        for tier in (doc["values"][layer][group], doc["values"][layer], doc["values"]):   # no empty shell is kept
            for k in [k for k, v in tier.items() if not v]:
                del tier[k]
        doc["schema_version"] = VALUES_VERSION
        bad = S.validate_instructions(doc)
        if bad:
            raise ValueError("; ".join(plain_faults(field, bad)))
        if result != "same":
            if doc["values"] or doc.get("kept"):
                W._write(values_path(ref), doc)
            elif values_path(ref).exists():
                values_path(ref).unlink()
        return result


# ---- a department's earlier whole-file change, kept as the owner's note (PRD M2.2) ------------------------------------
def own(ref, fn, file):
    """Where a department keeps its own copy of one instruction file: in its records home, which an update of the app
    never replaces (PRD M2.2, J7 step 3). It is the owner's note (kept_as_notes): no run reads it."""
    return W.ddir(ref) / "prompts" / fn / (file + ".md")


def own_files(ref, layer):
    """The whole-file copies a department made under M2.2 for a layer: {ref}/prompts/<layer>/<file>.md, by file name."""
    try:
        return sorted(p.stem for p in own(ref, layer, "x").parent.glob("*.md"))
    except (OSError, ValueError):
        return []


def kept_as_notes(ref, layer):
    """The M2.2 copies of a layer that this read is the first to find: recorded as the owner's notes in instructions.json
    ('kept', by layer/file), and returned for Identity to tell the owner once. Nothing reads a copy any more (A1-7: it is
    not decompiled into fields); the owner changes the field again to use the words. [] when each is recorded already."""
    files = own_files(ref, layer)
    if not files:
        return []
    with W._lock(ref):
        doc = copy.deepcopy(owner_doc(ref))
        kept = doc.setdefault("kept", {})
        new = [f for f in files if "%s/%s" % (layer, f) not in kept]
        if new:
            for f in new:
                kept["%s/%s" % (layer, f)] = {"at": W.now()}
            doc["schema_version"] = VALUES_VERSION
            W._write(values_path(ref), doc)
        return new


def kept_note(ref, layer, group):
    """When a group's earlier whole-file change was kept as a note ({at}), else None."""
    return ((owner_doc(ref).get("kept") or {}).get("%s/%s" % (layer, group))) or None


def answer_keys(returns):
    """The keys of the JSON object a part's contract asks for, in order: 'Return ONLY a JSON object: {"verdict": ..., "why":
    ...}.' -> ['verdict', 'why']. Only the object's own keys, never those of an object inside it. [] for no contract."""
    if not returns or "{" not in returns:
        return []
    out, depth, i, text = [], 0, returns.index("{"), returns
    while i < len(text):
        c = text[i]
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                break
        elif c == '"':
            j = text.index('"', i + 1) if '"' in text[i + 1:] else len(text) - 1
            if depth == 1 and text[j + 1:j + 2] == ":":
                out.append(text[i + 1:j])
            i = j
        i += 1
    return out
