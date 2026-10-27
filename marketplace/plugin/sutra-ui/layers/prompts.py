"""layers/prompts.py -- the typed prompt compiler (PRD amendment A1.16, W1-CORE).

A prompt part is three interface pieces and two implementation pieces. The interface (layer_schema.PROMPTS) names its
fields (what the owner may change, and their types), its inputs (the names code fills) and its returns (the answer
contract, verbatim, which the owner cannot change). A layer's implementation holds its WORDS (the default value of each
field) and its LAYOUT (the template that arranges them), in layers/<layer>/v<N>.py:

    WORDS[group][part]  = {field: value}
    LAYOUT[group][part] = a template. Its markers are {task}, {guidance}, {text}, {items} (rendered as lines '- x') and
                          {returns}, and {{name}} for an input. It is filled in one pass, and a value is never scanned
                          again, so nothing a value holds is read as a marker.

compile_layout() fills one; words() reads a part's fields as a department reads them now; prompt() is the words an agent
is sent. While a pinned implementation holds no WORDS for a part, prompt() and words() read the part from the .md bundle
(function-prompts/, and a department's own whole-file copy under M2.2), through the same split rule that the extractor
below applies, so the two ways give one text. faults() is the covering check of both. The bundle is read-only history
from here on: W3-PROOF deletes it.

THE BUNDLE IS THE REFERENCE for what the .md files hold (A1.16, 'Parts added by later steps'). A part a later step adds to
the interface has its words in its layer and no .md part: the extractor and the bundle check ask of the .md only the parts
the layer's default implementation does not hold as words (from_the_bundle()), and leave the rest to the words, which the
contract's case 5 holds to the interface. A part that neither holds is a fault.

THE OWNER'S VALUES (A1.16, W1-CORE K2): a field the owner changed is a typed value in {ref}/instructions.json, written on a
stamp. words() and prompt() overlay those values on the implementation's defaults, so a stamped value is the next run's
words and a value equal to the default is not kept (a later default reaches the department). A whole-file copy made under
M2.2 ({ref}/prompts/<fn>/<file>.md) is kept as the owner's note: no run reads it.

THE SPLIT RULE (A1.16), which turns a .md part into WORDS and LAYOUT; `python -m layers.prompts --extract <layer>` prints
the result for a layer:
  1. A file's first paragraph is its group's lead line, S.GROUPS[layer][group] (interface text).
  2. In a part, 'Return ONLY a JSON object: {...}.' is `returns`, wherever it stands in the part.
  3. `task` is the text before the first line that holds an input marker ({{...}}) or before `returns`, whichever comes first.
  4. `guidance` is the run of lines after `returns` that hold no input marker, up to a blank line.
  5. Everything else (input lines, labels such as 'THE RECORD:', blank lines, an input after the guidance) stays in LAYOUT as written.
  6. A `does` part is {text}; a `skills` part is {items}; a part with no `returns` (thin, refused) is {task} plus its input lines.
  7. Adaptation's decide file has no part a step reads: it becomes the part decide.note (field text, read by no step).
"""
import copy
import re
import sys

from layers import R, W, S  # noqa: F401 -- lazy proxies: tests reload the runtime

#: a marker of a layout: {{name}} (an input code fills) or one of the five field markers
MARKER = re.compile(r"\{\{([a-z_]+)\}\}|\{(task|guidance|text|items|returns)\}")
SLOT = re.compile(r"\{\{([a-z_]+)\}\}")
PART = re.compile(r"^## ([a-z][a-z0-9_-]*)[ \t]*$", re.M)
RETURNS = "Return ONLY a JSON object: "


def who(layer, group, part):
    """A part as the errors name it: Identity's take instructions, gate."""
    return "%s's %s instructions, %s" % (S.TITLE.get(layer) or str(layer).title(), group, part)


def held(layer, group, part):
    """Whether the layer's default implementation holds the part as WORDS and LAYOUT: the part its words serve, with no .md."""
    import layers
    module = layers.load(S.DEFAULT_PINS.get(layer))
    return part in ((getattr(module, "WORDS", None) or {}).get(group) or {}) and \
        part in ((getattr(module, "LAYOUT", None) or {}).get(group) or {})


def from_the_bundle(layer, group, part):
    """Whether the .md bundle must hold the part: it is the bundle's to serve when the layer's default implementation does
    not hold it, unless a later step added it (S.ADDED_PARTS), which no .md ever held."""
    return (layer, group, part) not in S.ADDED_PARTS and not held(layer, group, part)


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


def _module(ref, layer, group, part):
    """The pinned implementation of a layer when it holds words and a layout for the part; else None."""
    import layers
    module = layers.impl(ref, layer)
    if module is not None and part in (getattr(module, "WORDS", None) or {}).get(group, {}) \
            and part in (getattr(module, "LAYOUT", None) or {}).get(group, {}):
        return module
    return None


def defaults(ref, layer, group, part):
    """A part's fields as the pinned implementation ships them: {field: value}. Its WORDS when it holds the part; else the
    bundle's .md part, split by the rule above. The owner's values are not in it (see words())."""
    module = _module(ref, layer, group, part)
    if module is not None:
        return copy.deepcopy(module.WORDS[group][part])
    return split(group, part, md_part(layer, group, part))[0]


def words(ref, layer, group, part):
    """A part's fields as the department reads them now: the defaults with the owner's stamped values laid over them."""
    out = defaults(ref, layer, group, part)
    for field, value in owner_values(ref, layer, group, part).items():
        if field in out:
            out[field] = copy.deepcopy(value)
    return out


def prompt(ref, layer, group, part, **inputs):
    """One part of a layer's instructions, compiled: the words its agent is sent. The pinned implementation's WORDS and
    LAYOUT when it holds the part, else the bundle's .md part through the same split; the owner's stamped values are laid
    over the defaults either way. A marker the code gives no value is an error, never a blank."""
    module = _module(ref, layer, group, part)
    name = who(layer, group, part)
    if module is not None:
        return compile_layout(module.LAYOUT[group][part], words(ref, layer, group, part), S.PROMPTS[layer][group][part]["returns"],
                              inputs, name)
    text = md_part(layer, group, part)
    span = returns_span(text)
    fields, layout = split(group, part, text)
    for field, value in owner_values(ref, layer, group, part).items():
        if field in fields:
            fields[field] = value
    return compile_layout(layout, fields, text[span[0]:span[1]] if span else None, inputs, name)


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


def faults():
    """The covering check of every function's words, at the definitions load: for each part its default implementation
    holds as WORDS and LAYOUT, that it serves (part_faults); for each .md file with a part no implementation holds yet,
    that the bundle has it, with its plain first line, the parts a step reads and only the slots the code fills.
    [] when every function has its words."""
    import layers
    out = []
    for layer in S.FUNCTION_LAYERS:
        module = layers.load(S.DEFAULT_PINS[layer])
        for group, parts in (getattr(module, "WORDS", None) or {}).items():
            for part, values in parts.items():
                out += ["%s: %s" % (who(layer, group, part), f) for f in
                        part_faults(layer, group, part, values, ((getattr(module, "LAYOUT", None) or {}).get(group) or {}).get(part))]
    return out + bundle_faults()


# ---- the owner's typed values (PRD A1.16, M2.6) ------------------------------------------------------------------------
#: where a department keeps them: {ref}/instructions.json, DEFS 'instructions', checked at the sink (website_dept._write)
VALUES_FILE = "instructions.json"


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
        return {"schema_version": S.SCHEMA_VERSION, "values": {}}
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


#: the interface's faults for a field, in words the owner reads (the path is '$' for the value, '$[2]' for the third item)
_FAULT_SAYS = (
    (re.compile(r"^shorter than 1$"), "is empty"),
    (re.compile(r"^shorter than (\d+)$"), r"is shorter than \1 characters"),
    (re.compile(r"^longer than (\d+)$"), r"is longer than \1 characters"),
    (re.compile(r"^holds '\{\{' or '\}\}'"), "cannot hold '{{' or '}}', which only the app writes"),
    (re.compile(r"^holds 'Return ONLY'"), "cannot hold 'Return ONLY': the shape of the answer belongs to the app"),
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
        doc["schema_version"] = S.SCHEMA_VERSION
        bad = S.validate_instructions(doc)
        if bad:
            raise ValueError("; ".join(plain_faults(field, bad)))
        if result != "same":
            if doc["values"] or doc.get("kept"):
                W._write(values_path(ref), doc)
            elif values_path(ref).exists():
                values_path(ref).unlink()
        return result


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
            doc["schema_version"] = S.SCHEMA_VERSION
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


# ---- the .md fallback: the bundle, and a department's own whole-file copy (PRD M2) ----------------------------------------
def parts_of(text):
    """An instruction file, read: its lead, the plain words before the first part that say what the file is for (no
    agent is sent them), and its parts, each under a heading of its own name, its words exactly as written between
    the blank lines that set it off."""
    text = str(text or "").replace("\r\n", "\n")
    heads = list(PART.finditer(text))
    parts = {}
    for i, m in enumerate(heads):
        if m.group(1) in parts:
            raise ValueError("the part %s is written twice" % m.group(1))
        parts[m.group(1)] = text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)].strip("\n")
    return (text[:heads[0].start()] if heads else text).strip(), parts


def own(ref, fn, file):
    """Where a department keeps its own copy of one instruction file: in its records home, which an update of the app
    never replaces (PRD M2.2, J7 step 3). Written only on the owner's stamped ask."""
    return W.ddir(ref) / "prompts" / fn / (file + ".md")


def instruction(fn, file, ref=None):
    """The text of one of a function's instruction files: the department's own copy when the owner stamped one, else
    the bundle's."""
    if ref:
        mine = own(ref, fn, file)
        if mine.is_file():
            return mine.read_text(encoding="utf-8")
    return (R.PROMPTS_DIR / fn / (file + ".md")).read_text(encoding="utf-8")


def file_parts(fn, file, ref=None):
    """The parts of one instruction file as the app names them: its headed parts, or, for a file that has none and whose
    group the interface gives a note (Adaptation's decide, with any part a later step adds beside it), the words after its
    lead as the part `note`."""
    text = instruction(fn, file, ref)
    lead, parts = parts_of(text)
    note = next((p for p, spec in ((S.PROMPTS.get(fn) or {}).get(file) or {}).items() if "field.note" in spec["fields"].values()), None)
    if not parts and note:
        parts = {note: lead.split("\n\n", 1)[1].strip("\n") if "\n\n" in lead else ""}
    return parts


def md_part(fn, file, part, ref=None):
    """One part of an instruction file: the department's own copy wins; a part it does not hold (one a later bundle
    added) is the bundle's."""
    parts = file_parts(fn, file, ref)
    if part not in parts and ref:
        parts = file_parts(fn, file)
    if part not in parts:
        raise ValueError("%s's %s instructions have no part %s" % (fn.title(), file, part))
    return parts[part]


def instruction_faults(fn, file, text):
    """What keeps one instruction file from serving its function: no line that says what it is for, a part the bundle must
    hold gone, a part no step reads, or a slot the code does not fill in a part it serves. [] when it serves. The covering
    check of every file an agent's words come from: the bundle's at the definitions load. Only the parts the bundle must hold
    are asked of the text (from_the_bundle): a part the layer's words hold, or a later step added, is not."""
    named = (R.INSTRUCTIONS.get(fn) or {}).get(file)
    if named is None:
        return ["%s has no instructions named %s" % (str(fn).title(), file)]
    try:
        lead, parts = parts_of(text)
    except ValueError as exc:
        return [str(exc)]
    faults = [] if lead else ["%s does not say first, in a line, what it is for" % file]
    for part, slots in named.items():
        if part not in parts:
            if from_the_bundle(fn, file, part):
                faults.append("%s has no part %s" % (file, part))
            continue
        unknown = sorted(set(SLOT.findall(parts[part])) - set(slots)) if from_the_bundle(fn, file, part) else []
        if unknown:
            faults.append("%s, %s: the app fills no %s" % (file, part, ", ".join("{{%s}}" % s for s in unknown)))
    return faults + ["%s, %s: no step reads this part" % (file, p) for p in parts if p not in named]


def bundle_faults():
    """The bundle's files against the list: each one there, each serving. A file none of whose parts the bundle must hold
    (the default implementation holds each as words, or a later step added it) needs none, and a file with some such parts
    is asked for the others only. [] when every function has its files."""
    out = []
    for fn, files in R.INSTRUCTIONS.items():
        for file, parts in files.items():
            if parts and not any(from_the_bundle(fn, file, p) for p in parts):
                continue
            p = R.PROMPTS_DIR / fn / (file + ".md")
            if not p.is_file():
                out.append("%s's %s instructions are missing from the bundle" % (fn.title(), file))
                continue
            out += ["%s's instructions: %s" % (fn.title(), f) for f in instruction_faults(fn, file, p.read_text(encoding="utf-8"))]
    return out


# ---- the split rule, and the extractor ---------------------------------------------------------------------------------
def returns_span(text):
    """(start, end) of the answer contract in a part: 'Return ONLY a JSON object: ' and its braces, balanced, and the
    full stop that closes the sentence; None when the part has none."""
    start = text.find(RETURNS)
    if start < 0:
        return None
    i, depth = text.find("{", start), 0
    if i < 0:
        return None
    for j in range(i, len(text)):
        depth += (text[j] == "{") - (text[j] == "}")
        if depth == 0:
            return start, j + 1 + (text[j + 1:j + 2] == ".")
    return None


def split(group, part, text):
    """One .md part by the split rule: (words, layout), words being {field: value}. The layout compiled with the words,
    the part's returns and its inputs is the part, byte for byte."""
    text = str(text)
    if part == "does" or (group == "decide" and part == "note"):
        return {"text": text}, "{text}"
    if part == "skills":
        return {"items": [ln.strip()[2:].strip() if ln.strip().startswith("- ") else ln.strip() for ln in text.split("\n") if ln.strip()]}, "{items}"
    span = returns_span(text)
    marked = next((m.start() for m in re.finditer(r"^.*\{\{.*$", text, re.M)), len(text))   # the first line holding an input
    fields, cuts = {}, []                                    # cuts: (start, end, marker) spans of the text the fields stand for
    end = min(marked, span[0] if span else len(text))
    task = text[:end].rstrip()
    if task:
        fields["task"] = task
        cuts.append((0, len(task), "{task}"))
    if span:
        cuts.append((span[0], span[1], "{returns}"))
        pieces = text[span[1]:].split("\n")
        run = []
        for i, piece in enumerate(pieces):
            if "{{" in piece or (i and not piece.strip()):
                break
            run.append(piece)
        raw = "\n".join(run)
        guidance = raw.strip()
        if guidance:
            at = span[1] + len(raw) - len(raw.lstrip())
            fields["guidance"] = guidance
            cuts.append((at, at + len(guidance), "{guidance}"))
    layout, at = "", 0
    for start, stop, marker in sorted(cuts):
        layout += text[at:start] + marker
        at = stop
    return fields, layout + text[at:]


def inputs_of(text):
    """The names a part's text asks code to fill, in the order they first appear."""
    return list(dict.fromkeys(SLOT.findall(text)))


def extract(layer):
    """What the split rule makes of one function layer's .md files: (WORDS, LAYOUT, faults). Each part the .md holds has its
    fields, returns and inputs checked against the interface (S.PROMPTS), each group's lead against S.GROUPS, and the part
    compiled back from its words is checked to be the .md part, byte for byte. A part the interface names that no .md holds
    (one a later step added) is printed from nothing and is no fault while the layer holds its words (from_the_bundle). The
    faults are [] when the split holds."""
    out_words, out_layout, bad = {}, {}, []
    for group, parts in (S.PROMPTS.get(layer) or {}).items():
        path = R.PROMPTS_DIR / layer / (group + ".md")
        if not path.is_file():
            bad.append("%s: the bundle has no file %s" % (S.TITLE[layer], group))
            continue
        text = path.read_text(encoding="utf-8")
        lead, found = parts_of(text)
        if lead.split("\n\n")[0] != S.GROUPS[layer][group]:
            bad.append("%s: the lead of %s is not the interface's" % (S.TITLE[layer], group))
        found = file_parts(layer, group)
        # the bundle is the reference: it holds the parts it holds, the interface's, in the interface's order. A part the
        # interface names that it lacks (one a later step added) is the layer's words to serve, and a fault when they do not
        if list(found) != [part for part in parts if part in found]:
            bad.append("%s: %s holds the parts %s, and the interface %s" % (S.TITLE[layer], group, list(found), list(parts)))
        bad += ["%s: the bundle has no such part and the layer holds no words for it" % who(layer, group, part)
                for part in parts if part not in found and from_the_bundle(layer, group, part)]
        for part, spec in parts.items():
            if part not in found:
                continue
            fields, layout = split(group, part, found[part])
            span = returns_span(found[part])
            returns = found[part][span[0]:span[1]] if span else None
            name = who(layer, group, part)
            if set(fields) != set(spec["fields"]):
                bad.append("%s: the split finds the fields %s, and the interface %s" % (name, sorted(fields), sorted(spec["fields"])))
            if returns != spec["returns"]:
                bad.append("%s: the split finds returns %r, and the interface %r" % (name, returns, spec["returns"]))
            if inputs_of(found[part]) != list(spec["inputs"]):
                bad.append("%s: the part asks for the inputs %s, and the interface %s" % (name, inputs_of(found[part]), list(spec["inputs"])))
            sample = {n: "<%s>" % n for n in inputs_of(found[part])}
            try:
                if compile_layout(layout, fields, returns, sample, name) != SLOT.sub(lambda m: sample[m.group(1)], found[part]):
                    bad.append("%s: compiled from its words it is not the .md part" % name)
            except ValueError as exc:
                bad.append(str(exc))
            out_words.setdefault(group, {})[part] = fields
            out_layout.setdefault(group, {})[part] = layout
    return out_words, out_layout, bad


def _string(s, indent):
    """A string as source: one literal for a short line, and for a long or many-line one, pieces in parentheses that
    join to it (a line break ends a piece; so does a space once a piece is long)."""
    if len(repr(s)) <= 100 and "\n" not in s:
        return repr(s)
    pieces = []
    for line in s.split("\n") if s.count("\n") == 0 else re.findall(r"[^\n]*\n|[^\n]+$", s):
        buf = ""
        for word in re.findall(r"\S+\s*|\s+", line):
            if buf and len(repr(buf + word)) > 100:
                pieces.append(buf)
                buf = ""
            buf += word
        pieces.append(buf)
    return "(\n" + "".join("%s    %r\n" % (" " * indent, p) for p in pieces) + " " * indent + ")"


def literal(value, indent=0):
    """A dict, list or string as Python source that evaluates to it (ast.literal_eval reads what this prints)."""
    pad = " " * indent
    if isinstance(value, dict):
        return "{}" if not value else "{\n" + "".join("%s    %r: %s,\n" % (pad, k, literal(v, indent + 4)) for k, v in value.items()) + pad + "}"
    if isinstance(value, (list, tuple)):
        return "[]" if not value else "[\n" + "".join("%s    %s,\n" % (pad, literal(v, indent + 4)) for v in value) + pad + "]"
    return _string(value, indent)


def main(argv=None, out=None, err=None):
    """python -m layers.prompts --extract <layer>: print WORDS and LAYOUT for that layer's .md files, as literals ready
    to paste into layers/<layer>/v<N>.py. Exit 1 when the split does not hold against the interface, 2 when it cannot run."""
    argv, out, err = list(sys.argv[1:] if argv is None else argv), out or sys.stdout, err or sys.stderr
    if len(argv) != 2 or argv[0] != "--extract" or argv[1] not in S.FUNCTION_LAYERS:
        err.write("usage: python -m layers.prompts --extract <%s>\n" % "|".join(S.FUNCTION_LAYERS))
        return 2
    layer = argv[1]
    words_, layout, bad = extract(layer)
    out.write("# %s: WORDS and LAYOUT by the split rule of A1.16, from function-prompts/%s/*.md\nWORDS = %s\nLAYOUT = %s\n"
              % (S.TITLE[layer], layer, literal(words_), literal(layout)))
    for line in bad:
        err.write(line + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
