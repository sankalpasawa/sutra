"""digit_guard.py — every figure in the finished draft traces back to something the research bought.

THE GUARD, AND WHERE IT COMES FROM. The write phase runs a digit guard at every step that lets a
model touch already-written prose: `coherence.py` blocks the whole edit when "a number that exists
NOWHERE in the original" appears in the rewrite, `slop_pass.py` and `sentence_pass.py` throw a block
away when its number signature changes, `readable.py` puts "No invented figures" on its receipt.
Sutra carries all of those. What it never carried is the one at the END, over the finished article,
against the EVIDENCE rather than against the previous draft: every step-level guard only proves that
this step invented nothing, and a figure that entered at the first write — or in a section a person
edited by hand afterwards — passes all of them and ships.

So this asks the question the step guards cannot: does this number exist in any card the research
actually paid for? A figure in the draft that is in no card, no brand file and no measured number is
either invented or mangled (a digit dropped from 4,700, a 51% written as 15%), and both are the same
fault to a reader who checks it.

CODE COUNTS, THE MODEL JUDGES — and here the count IS the judgment, so there is no model call at all.
Set membership over text already on disk is not an opinion, which is why this can say `fail` under
the rule in checks/__init__.py while everything statistical stays at `warn`.

WHAT IS NOT A STATISTIC (write-body.md rule 3, his list, kept word for word in spirit):
    · a number that is part of a name or a label — "the DS14", "Type 2", "a 401(k)"
    · a year or a date — "published in 2022"
    · a small incidental number in passing — "two of the three studies", "the first step"
    · a number inside a formula you are explaining
    · a count of the things you just listed
  "None of those is a statistic. They are ordinary writing that happens to contain a digit."
Those are skipped, because flagging them would bury the one figure that matters under forty that do
not, and a guard nobody reads is a guard that is off.
"""
import re

from . import artifact, item, result

# The figure pattern, taken from coherence.py with its bug fix intact: digits, optional thousand
# separators, optional decimal part, but NEVER a trailing "." or ",". The greedy version captured
# "5." and "4," as separate numbers, so a sentence rewritten to end on a figure looked like
# fabrication ("third guard bug of the day", 2026-08).
FIGURE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")

# A figure only counts as a STATISTIC when it is shaped like one: a percentage, an amount of money, a
# multiplier, a thousands-separated count, or a decimal. Everything else is a bare small integer and
# is skipped as ordinary writing (his "small incidental number in passing").
STATISTIC = re.compile(
    r"(?:[$£€]\s?\d+(?:,\d{3})*(?:\.\d+)?"          # money: $4,700
    r"|\d+(?:,\d{3})*(?:\.\d+)?\s?%"                 # percentage: 51%, 4.5 %
    r"|\d+(?:,\d{3})*(?:\.\d+)?\s?(?:x|times)\b"     # multiplier: 3x, 2.5 times
    r"|\d{1,3}(?:,\d{3})+"                           # a counted thing big enough to carry a comma
    r"|\d+\.\d+)")                                   # any decimal

# A four-digit number in this range reads as a year, not a measurement.
YEAR = re.compile(r"^(?:1[89]|20)\d{2}$")

MAX_SHOWN = 12          # offending figures listed; past this the point is already made

# Where a legitimate figure can have come from. cards.json is the evidence the research bought;
# blueprint.json and research.json carry the measured numbers (volumes, difficulty, the word band);
# the brand files carry the company's own stats, which the writer is told to name in the prose.
BRAND_FILES = ("stats.md", "features.md", "stories.md", "writer-brief.md", "brand-facts.md")


def _norm(fig):
    """Compare figures the way a reader would: "$4,700" and "4700" are the same number.

    Normalising is for COMPARING ONLY. The shape test below reads the raw text, because the comma in
    "47,000" is the very thing that says it is a measurement rather than a page number, and stripping
    it first threw away the signal the test needed.
    """
    return re.sub(r"(\d),(\d)", r"\1\2", str(fig or ""))


def _figures(text):
    """Every figure in the text, exactly as written, in order of appearance."""
    return [m.group(0) for m in FIGURE.finditer(text or "")]


def _is_statistic(sentence, figure):
    """Is this figure one the argument leans on, or ordinary writing that happens to carry a digit?

    Deliberately narrow. A percentage spelled out in words ("51 percent") does not count, and neither
    does a bare small integer, because the cost of a false alarm here is a person learning to ignore
    the guard.
    """
    if YEAR.match(figure):
        return False                                # "published in 2022"
    if "," in figure or "." in figure:              # 4,700 / 0.51 are measurements wherever they sit
        return True
    for m in STATISTIC.finditer(sentence or ""):
        if figure in m.group(0):
            return True
    return False


def _corpus(ctx):
    """Everything the article's figures are allowed to have come from, as one lump of text.

    Returns "" when there is nothing on file, which is the signal to warn rather than fail: a check
    that cannot see the evidence must never call the writer a fabricator.
    """
    parts = []
    cards = artifact(ctx, "cards.json")
    for c in (cards if isinstance(cards, list) else []):
        if isinstance(c, dict):
            parts += [str(c.get("verbatim") or ""), str(c.get("gloss") or "")]
    if not parts:
        return ""
    for name in ("blueprint.json", "research.json"):
        got = artifact(ctx, name)
        if got is not None:
            parts.append(_dump(got))
    parts.append(_brand_text(ctx))
    return "\n".join(parts)


def _dump(obj):
    import json
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(obj)


def _brand_text(ctx):
    """The company's own material — its stats and product facts are figures the writer is told to
    name in the prose. A test hands it straight in under 'brand_text'."""
    ctx = ctx or {}
    if isinstance(ctx.get("brand_text"), str):
        return ctx["brand_text"]
    from .. import store
    out = []
    for name in BRAND_FILES:
        got = store.knowledge("brand/" + name)
        if isinstance(got, str):
            out.append(got)
    return "\n".join(out)


def check(md, ctx=None):
    """Every statistic in the draft, against the evidence the research bought."""
    from . import draft_checks as dc            # deferred: draft_checks imports this module
    corpus = _corpus(ctx or {})
    if not corpus:
        return result("figures_trace_to_evidence", "warn",
                      "No evidence cards on file for this run, so the draft's figures cannot be "
                      "traced. Run the research first, or check every number by hand.")

    known = {_norm(f) for f in _figures(corpus)}
    traced, seen, loose = 0, set(), []
    for i, block in enumerate(dc.blocks(md)):
        if dc.HEADING.match(block.strip()):
            continue
        for sentence in dc.sentences(dc.prose(block)):
            for fig in _figures(sentence):
                if not _is_statistic(sentence, fig):
                    continue
                if _norm(fig) in known:
                    traced += 1
                    continue
                if _norm(fig) in seen:
                    continue                      # one figure, one finding, however often it repeats
                seen.add(_norm(fig))
                loose.append(item("paragraph %d" % (i + 1), sentence.strip()[:140],
                                  "%s is in no card the research bought. Cite the source it came "
                                  "from, correct it against the card, or cut it." % fig))
    if loose:
        return result("figures_trace_to_evidence", "fail",
                      "%d figure(s) in the draft appear in no evidence card. A number nobody can "
                      "check is either invented or mistyped, and both read the same to a reader."
                      % len(loose), loose[:MAX_SHOWN])
    return result("figures_trace_to_evidence", "pass",
                  "Every statistic in the draft traces back to a card the research bought (%d checked)."
                  % traced)
