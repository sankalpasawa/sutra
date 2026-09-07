"""brand/pack.py — what the brand pack looks like right now, for the UI.

summary() -> {files: [{name, exists, words, flags}], needs_review: [...]}, in build order. Flags are
counted by code from the files themselves, so the screen shows the truth on disk, not what a run
claimed: ⚠️ rows waiting for confirmation, ⚑ HUMAN DECISION lines, template tags and placeholders
left unfilled, byline questions the team has not answered.
"""
import json
import re

from . import _common as cm

# Every brand file, in build order, with the ORIGINAL's structure.
FILES = ["type-roles.json", "stats.md", "stories.md", "opinions.md", "page-shortlist.md", "brand-voice.md",
         "style-guide.md", "features.md", "cta-pages.md", "writing-examples.md", "persona.md", "voices.md",
         "writing-integrity.md", "writer-brief.md", "writer-brief-rulings.md", "brand-cards.json",
         "field-sources.md", "seo-aeo-geo-checklist.md"]

_PLACEHOLDER = re.compile(r"\[[A-Z][A-Z /·&-]{2,}\]")
_TAG = re.compile(r"\[(?:BLOGS|STANDARD|COMPANY)[^\]]*\]")


def _flags(name, text):
    flags = []
    n = cm.count_lines(text, "⚠️")
    if n and name in ("stats.md", "stories.md"):
        flags.append("%d ⚠️ %s to confirm" % (n, "rows" if name == "stats.md" else "entries"))
    n = cm.count_lines(text, "⚑ HUMAN DECISION")
    if n:
        flags.append("%d ⚑ HUMAN DECISION" % n)
    n = len(_TAG.findall(text))
    if n:
        flags.append("%d template tags unresolved" % n)
    if name in ("brand-voice.md", "features.md"):
        n = len({b for b in _PLACEHOLDER.findall(text) if b != "[BRACKET]"})
        if n:
            flags.append("%d placeholders unfilled" % n)
    if name == "voices.md":
        n = cm.count_lines(text, "*(ask")
        if n:
            flags.append("%d byline questions for the team" % n)
    if name == "opinions.md" and "*(none yet)*" in text:
        flags.append("interview unanswered")
    if name == "stories.md" and "*(none yet)*" in text:
        flags.append("no stories yet")
    if name == "style-guide.md":
        n = cm.count_lines(text, "confirm with marketing")
        if n:
            flags.append("%d lines to confirm with marketing" % n)
    if name == "writer-brief-rulings.md" and "[the decision, stated as an instruction]" in text:
        flags.append("no house decisions recorded (optional)")
    return flags


def summary():
    files, review = [], []
    for name in FILES:
        exists = cm.exists(name)
        text = ""
        if exists:
            v = cm.read(name)
            text = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v or "")
        flags = _flags(name, text) if exists else []
        files.append({"name": name, "exists": exists, "words": cm.words(text) if exists else 0, "flags": flags})
        for f in flags:
            if "optional" not in f and "no stories yet" not in f:
                review.append("%s: %s" % (name, f))
    for extra in ("_drafts/stats-new-candidates.md", "_drafts/stories-new-candidates.md"):
        if cm.exists(extra):
            review.append("%s: new candidates beside a confirmed file" % extra)
    return {"files": files, "needs_review": review}
