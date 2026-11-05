"""board/1: a shared message board so a blocked agent (A) can ask the one that knows (B). B answers by updating a
shared artifact or by saying what it recorded, A reads the answer and continues, and later agents reuse the same
entry instead of asking again (docs/j2-handoff.md).

Askers are the five functions (Identity, Adaptation, Priority, Coordination, Audit) and the workflow builders;
targets are a workflow (including a done one from an earlier cycle) or another function. asked_by_role says which
kind asked, answered_from where the answer came from.

Behind J2_BOARD=1 (default off): write and log_event are no-ops unless the flag is set, so the plain flow never
creates board.json or board.jsonl and plain_unchanged is unaffected. Everything else here is pure, no disk access.
"""
import json
import os
import re

SCHEMA = "board/1"
ROUTED = "routed to Identity"      # a question for the Requester: only Identity talks to them
STATUSES = ("open", "answered", "unanswered", "refused", ROUTED)
ROLES = ("function", "builder")
# Words the duplicate test drops before comparing two questions: they carry no subject of their own.
STOPWORDS = frozenset(
    "a about already an and any are as at be been being but by can could did do does doesnt for from get give got "
    "had has have her his how i if in into is it its me my no not of on one or our out over should so some that the "
    "their them then there these they this those to too us was we were what when where which who whom why will with "
    "would you your yours".split())
DUPLICATE_SHARE = 0.6      # 60% or more of a new question's content words already in an answered one: refused


def enabled():
    return os.environ.get("J2_BOARD") == "1"


def new_board():
    """An empty board/1 object."""
    return {"schema": SCHEMA, "entries": []}


def new_entry(entry_id, asked_by, atom, to, about, question, cycle, attempt, asked_by_role="builder"):
    """A board entry as it is first asked: status open, nothing answered yet, used_by empty. asked_by_role is
    "function" (one of the five) or "builder"; answered_from is filled in when the answer comes back."""
    return {"id": entry_id, "asked_by": asked_by, "atom": atom, "to": to, "about": about, "question": question,
            "answer": None, "answered_by": None, "status": "open", "artifact_update": None, "used_by": [],
            "cycle": cycle, "attempt": attempt, "asked_by_role": asked_by_role, "answered_from": None,
            # a change to a document: every atom the content edges reach, with what its re-check found
            "impact": []}


def content_words(text):
    """The words a question is about: lowercase, stopwords and single letters removed, in order."""
    return [w for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(w) > 1 and w not in STOPWORDS]


def duplicate_of(question, entries):
    """The id of the answered entry that already answers this question (DUPLICATE_SHARE or more of the new
    question's content words appear in that entry's question), or None. Code refuses a duplicate: the asker is
    pointed at the board instead."""
    words = content_words(question)
    if not words:
        return None
    for e in entries or []:
        if e.get("status") != "answered":
            continue
        have = set(content_words(e.get("question")))
        if sum(w in have for w in words) / len(words) >= DUPLICATE_SHARE:
            return e.get("id")
    return None


def write(run_dir, board):
    """board.json in the run folder. No-op unless J2_BOARD=1."""
    if not enabled():
        return
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "board.json"), "w", encoding="utf-8") as f:
        json.dump(board, f, indent=2, ensure_ascii=False)


def log_event(run_dir, event):
    """Appends one JSON line to board.jsonl. No-op unless J2_BOARD=1."""
    if not enabled():
        return
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "board.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
