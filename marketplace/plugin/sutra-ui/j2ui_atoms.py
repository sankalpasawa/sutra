"""j2ui_atoms.py -- a work atom for each slot step of an engine, in the J2 prototype's shape (UI port, package j2ui-work).

The page the app shows for a website department (the J2 prototype's j2_ui.html, copied byte for byte) draws a workflow as a
row, and under it one card for each of its work atoms: a goal, who builds it, what must exist, the check that proves it,
what the check found. Sutra has no such atom stored. What it has is an engine, its steps, and one row in steps.jsonl each
time a step ran, so an atom here is a step read as the page reads an atom. This module only reads: it writes nothing, makes
no model call, and invents nothing. Where the record holds no value the page's own empty form is used (an empty list, no
status, no output).

The small readers below (plain, sentence, epoch, hhmmss, memoised) are shared by j2ui_work.py and j2ui_audit.py, the three
modules of this package, so that no string they emit says an inside word: a check's id (brief_is_text) is never a sentence.
"""
import re
from datetime import datetime

import owner_words

ID_LIKE = re.compile(r"^[a-z]+(_[a-z]+)+$")                  # brief_is_text: a check's id, never a sentence


# ---- the small readers all three modules share ---------------------------------------------------------------------
def plain(text):
    """One line in the owner's words; '' for nothing. A check's id is not a line (an inside word) and reads as nothing."""
    text = " ".join(str(owner_words.plain(text) if text is not None else "").split())
    return "" if ID_LIKE.match(text) else text


def cut(text, n=300):
    """A line cut at a word boundary, never inside a word."""
    text = str(text or "")
    if len(text) <= n:
        return text
    head = text[:n]
    sp = head.rfind(" ")
    return (head[:sp] if sp > 0 and text[n] != " " else head).rstrip() + "…"


def sentence(name, notes):
    """A step's check as a sentence: its name, then what the latest row's check noted first ('Read the brief: the brief has
    words'), never the check's id. The step's name alone when the check noted nothing."""
    name = plain(name)
    note = next((plain(n) for n in notes or [] if plain(n)), "")
    return "%s: %s" % (name, note) if name and note else name or note


def epoch(iso):
    """Seconds since the epoch of a recorded time, or None."""
    try:
        return datetime.fromisoformat(str(iso)).timestamp()
    except (TypeError, ValueError):
        return None


def hhmmss(iso):
    """The clock part of a recorded time, as the chat prints it: 'HH:MM:SS'; '' when the record has none."""
    s = str(iso or "")
    return s[11:19] if len(s) >= 19 and s[10] in "T " else ""


def memoised(ctx, key, build, empty, label):
    """build(ctx) once for this read of the department (its memo), or `empty()` with a reason on ctx.reasons when it
    fails: a builder never raises, and a failure empties its own keys and nothing else."""
    memo = getattr(ctx, "memo", None)
    if isinstance(memo, dict) and key in memo:
        return memo[key]
    try:
        out = build(ctx)
    except Exception as e:  # noqa: BLE001 -- a wrong shape blanks the page, so a builder gives its empty one instead
        reasons = getattr(ctx, "reasons", None)
        if isinstance(reasons, list):
            reasons.append("%s: %s %s" % (label, type(e).__name__, cut(e, 120)))
        out = empty()
    if isinstance(memo, dict):
        memo[key] = out
    return out
