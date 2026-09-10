"""brand/pack.py — what the brand pack looks like right now, for the screen that shows it.

summary() -> {files: [{name, exists, words}]}, in build order. Nothing more.

It used to count flags off every file — drafted rows waiting for confirmation, ⚑ HUMAN DECISION
lines, template tags, unanswered byline questions — and hand the screen a list of chores. Dropped
2026-09-09: the owner opened his own brand pack and was met by a tally of things he had not asked
to be told about. The flags themselves are still IN the documents, where they are honest and where
the quality gates read them; they are simply no longer counted at him.

The second half of the file answers one question the Knowledge screen asks: which files is the
writer brief actually built from? Derived, never typed out, so it cannot drift from the builder.
"""
import json

from . import _common as cm
from . import writer_brief

# Every brand file, in build order, with the ORIGINAL's structure. This order is the pack's own
# build order, so anything that wants "in the order these come into existence" reads it from here.
# pricing.md is the one INPUT in this list rather than an output: nothing builds it, a person types
# it, and brand/features.py fills features.md from it. It sits where it is read, immediately before
# features.md, and it is here so the screen gives it a door — a file that is not listed cannot be
# opened, which is exactly how the old seed file stayed empty for good (finding 8.21).
FILES = ["type-roles.json", "stats.md", "stories.md", "page-shortlist.md", "brand-voice.md",
         "style-guide.md", "pricing.md", "features.md", "cta-pages.md", "writing-examples.md", "persona.md",
         "writing-integrity.md", "writer-brief.md", "writer-brief-rulings.md", "brand-cards.json",
         "field-sources.md", "seo-aeo-geo-checklist.md"]


def _text(name):
    v = cm.read(name)
    return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v or "")


def summary():
    files = []
    for name in FILES:
        exists = cm.exists(name)
        text = _text(name) if exists else ""
        files.append({"name": name, "exists": exists, "words": cm.words(text) if exists else 0})
    return {"files": files}


# ---- what the writer brief is built from -------------------------------------------------------
# The one page a body writer reads is assembled from a handful of the others. The screen shows that
# chain, so a person can see where a rule in the brief came from.

# Files a writer really uses that the BRIEF is not built from. features.md is the one that matters:
# writer_brief.py excludes it by name and says why ("a product catalogue. Not rules about writing"),
# but write/wrapper.py reads it directly for the product claims and the close. So it is used, and it
# belongs beside the brief rather than inside the list of the brief's own sources.
#
# voices.md used to be listed under "how this was built", as one of the brief's four classified
# sources. The whole byline feature was deleted on 2026-09-09 ("remove completely everything about
# the byline questions, everything from Sutra for now"), so the file, its builder and its two setup
# questions are gone and the brief is built from three sources, not four.
EXTRAS = ["features.md"]

# Plain names and one line each, for a screen where "writing-integrity.md" means nothing to anybody.
LABELS = {
    "brand-voice.md": ("Brand voice", "How the company sounds, learned from its own best pages."),
    "style-guide.md": ("Style guide", "Capitalisation, numbers, punctuation, house spelling."),
    "features.md": ("Product facts", "What the company sells, and the proof behind each claim."),
    "writing-integrity.md": ("Writing integrity", "The honesty rules: no invented customers, no hype."),
    "writer-brief-rulings.md": ("Your rulings", "Decisions made by hand. These outrank everything else."),
    "persona.md": ("Readers", "Who each article is written to. Never named in the article itself."),
    "pricing.md": ("Prices and hidden facts",
                   "Anything your site draws with JavaScript, so a crawler cannot see it. Prices, "
                   "plans, trial length. Type it here and it beats anything we read off the site."),
}


def _row(name):
    label, note = LABELS.get(name, (name, ""))
    exists = cm.exists(name)
    return {"name": name, "label": label, "note": note, "exists": exists,
            "words": cm.words(_text(name)) if exists else 0}


def built_from_names():
    """EXACTLY the files the writer brief is built from, in the pack's own build order.

    Derived from the builder itself, never typed out as a list here, so a change in writer_brief.py
    shows up on this screen instead of quietly disagreeing with it. Three sources, three mechanisms:
    SOURCE_FILES is what the classifier reads, RULINGS is folded in by assemble() and outranks the
    rest, and persona.md is appended by _with_readers() as the "Who we write to" table.

    Corrected 2026-09-09. The first version put features.md in this list on my say-so. It is not a
    source: writer_brief.py excludes it BY NAME, with a comment giving the reason. The owner asked
    that this door show "only the actual files which were used", so what the builder does wins over
    what I assumed, and features.md moved to EXTRAS.
    """
    want = set(writer_brief.SOURCE_FILES) | {writer_brief.RULINGS, "persona.md"}
    return [n for n in FILES if n in want]


# The files a PERSON fills in, which a builder then reads. Not outputs, and not sources of the
# brief either, so they belong in neither list above. One so far.
#
# DERIVED, never typed out again: brand/_common.INPUTS is where the class is decided (it maps each
# one to the blank form that stands in for it), and FILES is where the order is decided. A second
# hand-written list here would be a second thing to keep in step with both.
INPUTS = [n for n in FILES if cm.is_input(n)]


def inputs():
    """The typed-in files, for the screen.

    `filled` is the difference between the blank form and a file somebody has actually written in,
    and `words` cannot tell them apart: the blank form is real text on disk, so it has a word count
    of its own. The screen needs the difference because the known failure mode of a typed-in file is
    that it ships blank, reads as something not built yet, and stays blank for months. That is
    exactly what happened to the seed file this one replaces (finding 8.21).

    A FILE THAT IS NOT ON DISK IS THE BLANK FORM, NOT AN ABSENCE. The form only reaches disk when
    the brand-pack builder runs, so a pack built before it existed has no copy -- and this screen
    still offered a door to it, which answered 404 (the owner, 2026-09-10). cm.read() stands the
    template in, so `exists` here means "there is a form to open", `words` counts the text the
    person will actually be shown, and `filled` is still the only word for "has anybody typed in
    it". The two states the screen draws -- the blank form, and a file somebody wrote -- are the
    two states there are; "on disk but untouched" and "not created yet" are not a difference a
    person can see, and pretending they are is what put a door in front of a missing file.
    """
    from . import features
    rows = []
    for n in INPUTS:
        label, note = LABELS.get(n, (n, ""))
        text = _text(n)
        rows.append({"name": n, "label": label, "note": note,
                     "exists": bool(str(text).strip()), "words": cm.words(text),
                     "filled": not features.untouched(text, n)})
    return rows


def brief():
    """writer-brief.md itself: does it exist, how long is it, and its text verbatim."""
    text = cm.read(writer_brief.OUTPUT) if cm.exists(writer_brief.OUTPUT) else ""
    return {"exists": bool(text.strip()), "words": cm.words(text), "text": text}


def built_from():
    return [_row(n) for n in built_from_names()]


def extras():
    """Used by a writer, but not sources of the brief. `in_use` is the truth, not a placeholder:
    features.md is read by write/wrapper.py on every article."""
    return [dict(_row(n), in_use=True) for n in EXTRAS]
