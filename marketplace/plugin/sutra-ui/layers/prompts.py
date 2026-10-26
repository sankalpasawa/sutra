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


def words(ref, layer, group, part):
    """A part's fields as the department reads them now: {field: value}. The pinned implementation's WORDS when it holds
    the part; else the .md part, split by the rule above."""
    module = _module(ref, layer, group, part)
    if module is not None:
        return copy.deepcopy(module.WORDS[group][part])
    return split(group, part, md_part(layer, group, part, ref))[0]


def prompt(ref, layer, group, part, **inputs):
    """One part of a layer's instructions, compiled: the words its agent is sent. The pinned implementation's WORDS and
    LAYOUT when it holds the part, else the .md part (the department's own copy wins; a part it does not hold is the
    bundle's). A marker the code gives no value is an error, never a blank."""
    module = _module(ref, layer, group, part)
    if module is not None:
        spec = S.PROMPTS[layer][group][part]
        return compile_layout(module.LAYOUT[group][part], words(ref, layer, group, part), spec["returns"], inputs, who(layer, group, part))

    def fill(m):
        if m.group(1) not in inputs:
            raise ValueError("%s: the app fills no {{%s}}" % (who(layer, group, part), m.group(1)))
        return str(inputs[m.group(1)])
    return SLOT.sub(fill, md_part(layer, group, part, ref))


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
    group the interface gives only a note (Adaptation's decide), the words after its lead as the part `note`."""
    text = instruction(fn, file, ref)
    lead, parts = parts_of(text)
    if not parts and list(((S.PROMPTS.get(fn) or {}).get(file) or {})) == ["note"]:
        parts = {"note": lead.split("\n\n", 1)[1].strip("\n") if "\n\n" in lead else ""}
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
    """What keeps one instruction file from serving its function: no line that says what it is for, a part a step
    reads gone, a part no step reads, or a slot the code does not fill. [] when it serves. The covering check of every
    file an agent's words come from: the bundle's at the definitions load."""
    want = (R.INSTRUCTIONS.get(fn) or {}).get(file)
    if want is None:
        return ["%s has no instructions named %s" % (str(fn).title(), file)]
    try:
        lead, parts = parts_of(text)
    except ValueError as exc:
        return [str(exc)]
    faults = [] if lead else ["%s does not say first, in a line, what it is for" % file]
    for part, slots in want.items():
        if part not in parts:
            faults.append("%s has no part %s" % (file, part))
            continue
        unknown = sorted(set(SLOT.findall(parts[part])) - set(slots))
        if unknown:
            faults.append("%s, %s: the app fills no %s" % (file, part, ", ".join("{{%s}}" % s for s in unknown)))
    return faults + ["%s, %s: no step reads this part" % (file, p) for p in parts if p not in want]


def bundle_faults():
    """The bundle's files against the list: each one there, each serving. A file every part of which the default
    implementation holds as words needs none. [] when every function has its files."""
    import layers
    out = []
    for fn, files in R.INSTRUCTIONS.items():
        module = layers.load(S.DEFAULT_PINS.get(fn))
        for file, parts in files.items():
            if parts and all(p in ((getattr(module, "WORDS", None) or {}).get(file) or {}) and
                             p in ((getattr(module, "LAYOUT", None) or {}).get(file) or {}) for p in parts):
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
    """What the split rule makes of one function layer's .md files: (WORDS, LAYOUT, faults). Each part's fields,
    returns and inputs are checked against the interface (S.PROMPTS), each group's lead against S.GROUPS, and the part
    compiled back from its words is checked to be the .md part, byte for byte. The faults are [] when the split holds."""
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
        if list(found) != list(parts):
            bad.append("%s: %s holds the parts %s, and the interface %s" % (S.TITLE[layer], group, list(found), list(parts)))
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
