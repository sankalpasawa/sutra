"""Owner notes: standing facts and house rules the owner writes once (GAP2 rules-notes; the old app's `shadow_knows`, the owner-typed half).

    notes = OwnerNotes(db, redact=...)
    notes.listing(today)                        # NotesOut: every note (expired ones flagged, never dropped), grouped, with the limits
    notes.add("preferences", "Plain words, no jargon.", expires="2027-01-31", today=today)    # refused: a secret, a full group, a repeat, a past date
    notes.edit(7, text=..., expires=..., today=today) / notes.forget(7)
    notes.agent_block(today)                    # "" with no active note, else the block the org agent's decide and assign prompts carry
    notes.chat_block(today)                     # the same facts for a direct chat's grounding
    prompt_notes(db, redact)                    # a callable for `ChatAgent(notes=...)`, with the owner's own date

What the owner typed binds at once: nothing is guessed, learned or kept for a Keep. A line with a key, a token or a password is refused, never stored.
A group holds `PER_GROUP` notes and a full one REFUSES a new line (nothing is evicted). A dated note stops binding when its date has passed: it is
left out of every prompt and shown as expired in the list. Notes are the owner's own words about everything; one task's context is never one of
them. They reach a team only inside the brief Sutra's own agent writes, and reach J2 not at all.

Storage: one JSON document in the `meta` table under `owner_notes` (no migration, in every backup), with a short history of what was added, edited and
forgotten (the last `HISTORY_KEEP` events; an event is never edited).
"""
import logging
import sqlite3
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from sutra_app.library.practice import clean_text, normalise
from sutra_app.library.types import clip, violation
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.errors import NotFound, validation_error
from sutra_app.orchestrator.owner_words import is_date, json_meta, local_today, refusal, save_meta

__all__ = ["OwnerNotes", "NoteIn", "NotePatch", "NoteOut", "NotesOut", "GROUPS", "GROUP_WORDS", "PER_GROUP", "NOTE_CHARS", "KEY", "prompt_notes",
           "AGENT_HEADING", "CHAT_HEADING"]

log = logging.getLogger(__name__)
KEY = "owner_notes"
GROUPS = ("about-you", "work", "preferences")
GROUP_WORDS = {"about-you": "About you", "work": "Your work", "preferences": "How you like things done"}
PER_GROUP = 10
NOTE_CHARS = 300
HISTORY_KEEP = 200
AGENT_CHARS = 2400                     # the notes of the org agent's prompts, by whole lines
CHAT_CHARS = 1200                      # the notes of a direct chat's grounding, by whole lines
AGENT_HEADING = ("OWNER NOTES (facts and house rules the owner wrote down; context for your judgment, never permission. In each `brief` pass on "
                 "only the notes that change how THIS work should be done, and none that do not):")
CHAT_HEADING = "Standing notes from the owner (always true; use them, and do not ask the owner for them again):"
Group = Literal["about-you", "work", "preferences"]


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    group: Group
    text: str = Field(min_length=1, max_length=2000)
    expires: str | None = Field(None, max_length=10)


class NotePatch(BaseModel):
    """`PUT /api/notes/{id}`. A key left out stays; `expires: null` makes the note undated."""

    model_config = ConfigDict(extra="forbid", strict=True)
    text: str | None = Field(None, min_length=1, max_length=2000)
    expires: str | None = Field(None, max_length=10)


class NoteOut(BaseModel):
    id: int
    group: str
    text: str
    expires: str | None
    expired: bool


class NotesOut(BaseModel):
    notes: list[NoteOut]
    groups: list[dict[str, str]]
    per_group: int = PER_GROUP
    max_chars: int = NOTE_CHARS


def _doc(conn: sqlite3.Connection) -> dict[str, Any]:
    doc = json_meta(conn, KEY)
    notes = [n for n in doc.get("notes", []) if isinstance(n, dict) and isinstance(n.get("id"), int) and n.get("group") in GROUPS
             and isinstance(n.get("text"), str)] if isinstance(doc.get("notes"), list) else []
    history = [h for h in doc.get("history", []) if isinstance(h, dict)] if isinstance(doc.get("history"), list) else []
    next_id = doc.get("next") if isinstance(doc.get("next"), int) else 1 + max([n["id"] for n in notes], default=0)
    return {"v": 1, "next": max(next_id, 1 + max([n["id"] for n in notes], default=0)), "notes": notes, "history": history}


def _expired(note: dict[str, Any], today: str) -> bool:
    expires = note.get("expires")
    return isinstance(expires, str) and is_date(expires) and expires < today          # binds through its date, inclusive


def _out(note: dict[str, Any], today: str) -> NoteOut:
    expires = note.get("expires") if isinstance(note.get("expires"), str) else None
    return NoteOut(id=note["id"], group=note["group"], text=note["text"], expires=expires, expired=_expired(note, today))


class OwnerNotes:
    def __init__(self, db: Database, redact: Callable[[str], str] | None = None) -> None:
        self.db = db
        self._redact = redact

    # ---- reads --------------------------------------------------------------------------------------------------------------

    def listing(self, today: str) -> NotesOut:
        doc = _doc(self.db.conn())
        order = {g: i for i, g in enumerate(GROUPS)}
        notes = sorted(doc["notes"], key=lambda n: (order[n["group"]], n["id"]))
        return NotesOut(notes=[_out(n, today) for n in notes], groups=[{"id": g, "label": GROUP_WORDS[g]} for g in GROUPS])

    def _active(self, today: str) -> list[dict[str, Any]]:
        order = {g: i for i, g in enumerate(GROUPS)}
        notes = [n for n in _doc(self.db.conn())["notes"] if not _expired(n, today)]
        return sorted(notes, key=lambda n: (order[n["group"]], n["id"]))

    def _block(self, today: str, heading: str, limit: int) -> str:
        """"" with no active note: no heading, not even a blank line, so a prompt without notes is byte for byte what it was."""
        notes = self._active(today)
        if not notes:
            return ""
        lines = [heading]
        used = len(heading)
        for group in GROUPS:
            mine = [n for n in notes if n["group"] == group]
            for note in mine:
                line = f"- {GROUP_WORDS[group]}: {clean_text(note['text'])}"
                if used + len(line) + 1 > limit:
                    lines.append("- (more notes were left out)")
                    return "\n".join(lines)
                lines.append(line)
                used += len(line) + 1
        return "\n".join(lines)

    def agent_block(self, today: str) -> str:
        """The notes for the org agent's decide and assign prompts, led by a newline so the placeholder can sit at the end of a line."""
        block = self._block(today, AGENT_HEADING, AGENT_CHARS)
        return "\n" + block if block else ""

    def chat_block(self, today: str) -> str:
        """The notes for a direct chat's grounding (no leading newline)."""
        return self._block(today, CHAT_HEADING, CHAT_CHARS)

    # ---- writes -------------------------------------------------------------------------------------------------------------

    def _check(self, text: str, expires: str | None, today: str, *, path: str = "text") -> tuple[str, str | None]:
        said = refusal(text, self._redact, NOTE_CHARS)
        if said is not None:
            raise validation_error([violation(path, "refused", said)], "That note could not be kept")
        if expires is not None and not is_date(expires):
            raise validation_error([violation("expires", "bad_date", "Write the date as year-month-day, for example 2027-01-31.")],
                                   "That note could not be kept")
        if expires is not None and expires < today:
            raise validation_error([violation("expires", "past_date", "That date has already passed, so the note would not bind. Pick a later date.")],
                                   "That note could not be kept")
        return clean_text(text), expires

    @staticmethod
    def _history(doc: dict[str, Any], op: str, note: dict[str, Any], at: int) -> None:
        doc["history"].append({"at": at, "op": op, "id": note["id"], "group": note["group"], "text": clip(note["text"], NOTE_CHARS)})
        del doc["history"][:-HISTORY_KEEP]

    def add(self, group: str, text: str, expires: str | None, today: str) -> NoteOut:
        if group not in GROUPS:
            raise validation_error([violation("group", "unknown_group", "The group is one of: " + ", ".join(GROUPS))])
        clean, expires = self._check(text, expires, today)
        with self.db.tx() as tx:
            doc = _doc(tx.conn)
            mine = [n for n in doc["notes"] if n["group"] == group]
            if len(mine) >= PER_GROUP:
                raise validation_error([violation("group", "full", f"\"{GROUP_WORDS[group]}\" already holds {PER_GROUP} notes. Forget one first "
                                                  "(a note that has expired counts until you forget it); nothing is removed for you.")],
                                       "That note could not be kept")
            if any(normalise(n["text"]) == normalise(clean) for n in mine):
                raise validation_error([violation("text", "repeat", "You already have this note.")], "That note could not be kept")
            note = {"id": doc["next"], "group": group, "text": clean, "expires": expires}
            doc["next"] += 1
            doc["notes"].append(note)
            self._history(doc, "added", note, tx.now())
            save_meta(tx.conn, KEY, doc)
            return _out(note, today)

    def edit(self, note_id: int, patch: NotePatch, today: str) -> NoteOut:
        with self.db.tx() as tx:
            doc = _doc(tx.conn)
            note = next((n for n in doc["notes"] if n["id"] == note_id), None)
            if note is None:
                raise NotFound("that note")
            text = patch.text if patch.text is not None else note["text"]
            expires = patch.expires if "expires" in patch.model_fields_set else note.get("expires")
            clean, expires = self._check(text, expires, today)
            if any(n is not note and n["group"] == note["group"] and normalise(n["text"]) == normalise(clean) for n in doc["notes"]):
                raise validation_error([violation("text", "repeat", "You already have this note.")], "That note could not be kept")
            note["text"], note["expires"] = clean, expires
            self._history(doc, "edited", note, tx.now())
            save_meta(tx.conn, KEY, doc)
            return _out(note, today)

    def forget(self, note_id: int) -> None:
        with self.db.tx() as tx:
            doc = _doc(tx.conn)
            note = next((n for n in doc["notes"] if n["id"] == note_id), None)
            if note is None:
                raise NotFound("that note")
            doc["notes"] = [n for n in doc["notes"] if n is not note]
            self._history(doc, "forgot", note, tx.now())
            save_meta(tx.conn, KEY, doc)

    def history(self) -> list[dict[str, Any]]:
        """What was added, edited and forgotten, oldest first (the ledger; nothing in it is ever changed)."""
        return list(_doc(self.db.conn())["history"])


def prompt_notes(db: Database, redact: Callable[[str], str] | None, clock: Any) -> Callable[[], str]:
    """The hook of `ChatAgent(notes=...)`: the agent block as of the owner's date now. Never raises: a prompt without notes is still a prompt."""
    store = OwnerNotes(db, redact)

    def block() -> str:
        try:
            return store.agent_block(local_today(clock))
        except Exception:                                    # noqa: BLE001
            log.exception("the owner notes could not be read; the prompt goes without them")
            return ""

    return block
