"""How a direct-chat turn ends in the transcript (GAP-chat-comfort): what is stored when the reply is done, stopped or failed, and the line
that records the owner's attachments.

    finished(user_id, done)            the stored reply, preceded by a note when the turn moved the chat to another provider
    stopped(user_id, shown)            what was written so far (kept as the reply) and a calm note; never an error
    failed(user_id, shown, sentence)   what was written so far (kept as the reply) and the error line with the real reason
    switch_notice(switched)            "Switched Claude to Codex; carried 40 messages" (the words of ChatPill.switchNotice)
    attached_line(names, kinds)        "(attached: a.png, b.pdf)", the last line of an owner's line that carried files

Every message of one turn is stored in ONE transaction (`chat_v2._post_all`), so a page never sees half an ending, and each carries a src_ref
that names the owner's line (`direct:<id>` for the reply, or for the first message when there is no reply; `direct-note:<id>`,
`direct-error:<id>`, `direct-switch:<id>` for the others), because `ChatStore.post` refuses a repeated src_ref and `chats._turn_of` reads
the owner's line back from all of them. Notes and errors are not carried over to the next model (`ChatTranscripts` takes text and questions
only); a kept partial reply is, because the model did write it. Nothing here touches a store: these are values in, values out.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, StringConstraints

from sutra_app.library.base import Value

__all__ = ["Ending", "finished", "stopped", "failed", "switch_notice", "attached_line", "clean_name",
           "STOPPED", "STOPPED_EMPTY", "NO_REPLY", "MAX_TEXT"]

STOPPED = "Stopped. What was written is kept."
STOPPED_EMPTY = "Stopped before the model wrote anything."
NO_REPLY = "(no reply)"
MAX_TEXT = 200_000                       # the store's cap on a message (chat_v2._post cuts there too): a longer reply is kept cut, never lost
_NAMES = {"claude": "Claude", "codex": "Codex"}
_KIND_WORDS = {"image": "an image", "pdf": "a PDF", "text": "a text file"}


class Ending(Value):
    """One message the end of a turn stores: always role agent, who sutra (a note is drawn calm by its kind, an error red). The text is kept
    as the model wrote it (no stripping)."""

    model_config = ConfigDict(str_strip_whitespace=False)
    kind: Literal["text", "note", "error"]
    text: Annotated[str, StringConstraints(min_length=1, max_length=MAX_TEXT)]
    src_ref: Annotated[str, StringConstraints(pattern=r"^direct(-(note|error|switch))?:[1-9][0-9]{0,15}$")]
    blocks: list[dict[str, Any]] = []


def _ref(user_id: int, tail: str = "") -> str:
    return f"direct{'-' + tail if tail else ''}:{int(user_id)}"


def _label(name: Any) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(name or "")).strip()
    return _NAMES.get(text, text)


def switch_notice(switched: Any) -> str:
    """The sentence of a provider switch, or "" when `switched` names no target. Same words as ChatPill.switchNotice."""
    if not isinstance(switched, dict) or not _label(switched.get("to")):
        return ""
    plan = switched.get("plan") if isinstance(switched.get("plan"), dict) else {}
    kept = plan.get("kept_messages") if isinstance(plan.get("kept_messages"), int) else 0
    omitted = plan.get("omitted") if isinstance(plan.get("omitted"), int) else 0
    to = _label(switched.get("to"))
    head = f"Switched {_label(switched.get('from'))} to {to}" if _label(switched.get("from")) else f"Switched to {to}"
    carried = "nothing to carry" if kept == 0 else f"carried {kept} message{'' if kept == 1 else 's'}"
    return head + "; " + carried + (f", {omitted} earlier shortened" if omitted > 0 else "")


def finished(user_id: int, done: dict) -> list[Ending]:
    blocks = [b for b in done.get("blocks", []) if isinstance(b, dict) and (b.get("type") != "text" or b.get("text"))]
    out = []
    notice = switch_notice(done.get("switched"))
    if notice:
        out.append(Ending(kind="note", text=notice, src_ref=_ref(user_id, "switch")))
    out.append(Ending(kind="text", text=(str(done.get("text") or "") or NO_REPLY)[:MAX_TEXT], src_ref=_ref(user_id), blocks=blocks))
    return out


def stopped(user_id: int, shown: str) -> list[Ending]:
    if not shown.strip():
        return [Ending(kind="note", text=STOPPED_EMPTY, src_ref=_ref(user_id))]
    return [Ending(kind="text", text=shown[:MAX_TEXT], src_ref=_ref(user_id)), Ending(kind="note", text=STOPPED, src_ref=_ref(user_id, "note"))]


def failed(user_id: int, shown: str, sentence: str) -> list[Ending]:
    reason = sentence.strip()[:MAX_TEXT] or "The model could not answer."
    if not shown.strip():
        return [Ending(kind="error", text=reason, src_ref=_ref(user_id))]
    return [Ending(kind="text", text=shown[:MAX_TEXT], src_ref=_ref(user_id)), Ending(kind="error", text=reason, src_ref=_ref(user_id, "error"))]


def clean_name(name: Any) -> str:
    """A file name as the attachment store cleans it (letters, digits, space . _ ( ) -; at most 80), so a name never breaks the list."""
    base = re.split(r"[\\/]", str(name or "").strip())[-1]
    return re.sub(r"[^A-Za-z0-9 ._()-]", "_", base).strip()[:80]


def attached_line(names: list[str], kinds: list[str]) -> str:
    """The record of what went with an owner's line: the owner's names when the page sent one per file, else what each file is."""
    if not kinds:
        return ""
    cleaned = [clean_name(n) for n in names] if len(names) == len(kinds) else []
    shown = [c if c else _KIND_WORDS.get(k, "a file") for c, k in zip(cleaned or [""] * len(kinds), kinds)]
    return "(attached: " + ", ".join(shown) + ")"
