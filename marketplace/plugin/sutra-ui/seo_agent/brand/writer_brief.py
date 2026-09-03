"""brand/writer_brief.py — builder 9: the one file a body writer reads before writing a section.

Port of 7-writer-brief/scripts/run_writer_brief.py.

Step 1 classify every section of every rule-carrying brand file (model per file, in parallel). The
       three questions are actionable / scope / kind; the KEEP-or-DROP verdict is derived IN CODE,
       in the recipe's order, never asked for.
Step 2 assemble the brief from everything kept, resolving the places the sources disagree (model;
       the template is lifted verbatim, the contradiction order lives in the prompt). Code then counts
       the concrete items it was given and reports how many survived, because losing a specific is the
       failure mode that matters. brand/writer-brief-rulings.md (hand-written house decisions) outranks
       the sources; it is instantiated from the template when missing.

Reads:  brand/brand-voice.md · brand/style-guide.md · brand/voices.md · brand/writing-integrity.md
Writes: brand/_work/writer-brief/{classified.json, dropped.md} · brand/writer-brief-rulings.md · brand/writer-brief.md
"""
import re

from .. import llm
from . import _common as cm

OUTPUT = "writer-brief.md"
RULINGS = "writer-brief-rulings.md"
WORK = "_work/writer-brief/"

# Only these are read. Each exclusion is a decision, not an oversight:
#   stats.md, stories.md  -> statistics and customer stories. Facts, not rules about writing.
#   features.md           -> a product catalogue. Not rules about writing.
#   persona.md            -> describes the reader, not the company's own voice.
#   writing-examples.md   -> five complete published articles. Whole finished pages, not rules.
#   opinions.md           -> an empty template with no opinions recorded in it.
SOURCE_FILES = ["brand-voice.md", "style-guide.md", "voices.md", "writing-integrity.md"]
WB_SECTION_CAP = 40000      # per source file into a classify prompt

DROP_REASONS = {
    "not-the-writers-job": "the writer cannot act on it",
    "a-fact": "a fact, not a rule about writing",
    "a-lookup-list": "a lookup list a human consults, not something applied while writing",
    "general-craft": "true for any company, so it is not this company's brief",
}
KINDS = {"rule", "fact", "reference"}


# ---- step 1 -----------------------------------------------------------------------------------

def verdict(sec):
    """Derived in code, never asked of the model: one answer cannot disagree with itself.
    Returns (keep|drop, reason). The order below is the recipe's order, word for word."""
    if not sec.get("actionable"):
        return "drop", "not-the-writers-job"
    if sec.get("kind") == "fact":
        return "drop", "a-fact"
    if sec.get("kind") == "reference":
        return "drop", "a-lookup-list"
    if sec.get("scope") == "universal":
        return "drop", "general-craft"
    return "keep", ""


def classify(co, say, redo=False):
    name = WORK + "classified.json"
    if cm.exists(name) and not redo:
        say("Reusing the classified sections", "brand/_work/writer-brief/classified.json")
        return cm.read(name)
    tpl = cm.prompt("classify-sections")
    present = [n for n in SOURCE_FILES if cm.exists(n)]
    for n in SOURCE_FILES:
        if n not in present:
            say("A source file is missing", "%s was skipped" % n)

    def one(fname):
        body = cm.read(fname)[:WB_SECTION_CAP]
        return llm.json_call(cm.fill(tpl, brand=co["brand"], niche=co.get("niche_definition") or "",
                                     filename=fname, content=body))

    sections = []
    for fname, r, err in cm.parallel(one, present, say, "Classifying source files", every=1):
        if err or not isinstance(r, dict):
            say("Could not classify a file", "%s: %s" % (fname, str(err)[:80] if err else "no sections returned"))
            continue
        got = [s for s in (r.get("sections") or []) if isinstance(s, dict)]
        for s in got:
            s["file"] = fname
            if s.get("kind") not in KINDS:                # verify, don't trust
                say("Unknown section kind", "%s: %r treated as 'reference'" % (fname, s.get("kind")))
                s["kind"] = "reference"
            s["verdict"], s["drop_reason"] = verdict(s)
        sections += got
        say("Classified %s" % fname, "%d sections" % len(got))
    cm.save(name, {"sections": sections})
    kept = sum(1 for s in sections if s["verdict"] == "keep")
    tally = {}
    for s in sections:
        if s["verdict"] == "drop":
            tally[s["drop_reason"]] = tally.get(s["drop_reason"], 0) + 1
    say("Sorted the brand pack", "%d sections: kept %d; dropped %s" % (len(sections), kept,
        " · ".join("%s=%d" % kv for kv in sorted(tally.items())) or "none"))
    return {"sections": sections}


# ---- step 2 -----------------------------------------------------------------------------------

def _kept_block(sections):
    out = []
    for s in sections:
        if s.get("verdict") == "keep" and str(s.get("carry") or "").strip():
            out.append("### %s — %s\n(%s)\n\n%s" % (s["file"], s.get("heading", ""), s.get("summary", ""), str(s["carry"]).strip()))
    return "\n\n".join(out)


_PUNCT = re.compile(r"[*`_\"'“”‘’.,;:!?()\[\]]+")


def _norm(s):
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", s)).strip().lower()


def atoms(text):
    """The CONCRETE items the source gave us: table cells and the head of each list item. Losing one
    of these is the failure mode that matters, so they are counted rather than trusted.

    An atom is only ever the thing that must SURVIVE, so an arrow pair keeps its left side: the
    source's 'clients -> not customers' becomes 'clients', which then matches however the brief
    formats it."""
    out = set()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):        # a table rule row
                continue
            pieces = cells
        elif re.match(r"^([-*·]|\d+\.)\s+", line):
            head = re.sub(r"^([-*·]|\d+\.)\s+", "", line)
            pieces = [re.split(r"[:—(]", head)[0]]
        else:
            continue
        for p in pieces:
            p = re.split(r"→|->|\bnot\b", p)[0]                  # keep the side that must survive
            # A cell often lists alternatives ("same-day / next-day"). Each is its own item, and the
            # brief may re-join them with a comma, so compare them separately.
            for part in re.split(r"\s*/\s*|\s*·\s*", p):
                part = _norm(part)
                if 2 < len(part) < 60:
                    out.add(part)
    return out


def rulings(co, say):
    if not cm.exists(RULINGS):
        cm.save(RULINGS, cm.template("writer-brief-rulings").replace("[Company]", co["brand"]))
        say("Instantiated the house-decisions file", "brand/writer-brief-rulings.md (optional, hand-written; blank rows outrank nothing)")
    text = cm.read(RULINGS).strip()
    # A file still carrying the template's placeholder row has no decisions in it yet.
    return text if text and "[the decision, stated as an instruction]" not in text else "*(none — nothing has been overridden by hand)*"


def assemble(co, sections, say):
    kept = _kept_block(sections)
    draft = cm.strip_fence(llm.text(cm.fill(cm.prompt("assemble-brief"), brand=co["brand"],
                                             niche=co.get("niche_definition") or "", kept=kept,
                                             rulings=rulings(co, say), template=cm.template("writer-brief")), timeout=llm.LONG_TIMEOUT))
    cm.save(OUTPUT, draft)
    # Search the WHOLE normalised brief, not a set of output atoms: the brief is allowed to reformat a
    # bullet into a table cell, and an atom-to-atom compare called every such reformat a loss.
    want, blob = atoms(kept), _norm(draft)
    missing = sorted(a for a in want if a not in blob)
    say("Assembled the writer brief", "%d words" % cm.words(draft))
    say("Concrete items carried through", "%d of %d%s" % (len(want) - len(missing), len(want),
        ("; missing e.g. %s" % ", ".join(missing[:8])) if missing else ""))
    return draft, want, missing


def dropped(co, sections):
    """A record of what did not make the brief, and why, so nothing is silently lost. The
    general-craft group is written out IN FULL: good writing rules that simply are not brand."""
    by = {}
    for s in sections:
        if s.get("verdict") == "keep":
            continue
        by.setdefault(s.get("drop_reason", "?"), []).append(s)
    lines = ["# What did not make the writer brief — %s" % co["brand"], "",
             "A record. Nothing here was deleted from any source file.", ""]
    for reason in sorted(by):
        group = by[reason]
        lines.append("## %s — %s  (%d)" % (reason, DROP_REASONS.get(reason, ""), len(group)))
        lines.append("")
        if reason == "general-craft":
            lines.append("Good writing rules that are true for any company. Kept in full, because this "
                         "group is the one worth reusing elsewhere.")
            lines.append("")
            for s in group:
                lines += ["### %s — %s" % (s["file"], s.get("heading", "")), "*%s*" % s.get("why", ""), "",
                          str(s.get("carry") or "*(no text captured)*").strip(), ""]
        else:
            for s in group:
                lines.append("- **%s — %s** · %s" % (s["file"], s.get("heading", ""), s.get("why", "")))
            lines.append("")
    cm.save(WORK + "dropped.md", "\n".join(lines) + "\n")
    return len(by.get("general-craft", []))


# ---- the builder ------------------------------------------------------------------------------

def run(co, say, redo=False):
    if cm.exists(OUTPUT) and not redo:
        say("Kept writer-brief.md", "already built; ask for a redo to rebuild it")
        return {"files": [OUTPUT, RULINGS], "needs_review": []}
    if not any(cm.exists(n) for n in SOURCE_FILES):
        raise RuntimeError("None of the source files exist yet (%s); build the voice, style guide and voices first." % ", ".join(SOURCE_FILES))
    data = classify(co, say, redo=redo)
    sections = data.get("sections") or []
    _draft, want, missing = assemble(co, sections, say)
    n_craft = dropped(co, sections)
    say("Recorded what was dropped", "brand/_work/writer-brief/dropped.md (%d general-craft rules kept in full)" % n_craft)
    notes = []
    if missing:
        notes.append("writer-brief.md: %d of %d concrete items did not survive the assembly (see the run log)" % (len(missing), len(want)))
    return {"files": [OUTPUT, RULINGS], "needs_review": notes}
