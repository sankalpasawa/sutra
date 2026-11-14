"""How a direct-chat turn ends in the transcript (GAP-chat-comfort): what is stored when the reply is done, stopped or failed, and the line
that records the owner's attachments.

    finished(user_id, done)            the stored reply, preceded by a note when the turn moved the chat to another provider
    stopped(user_id, shown)            what was written so far (kept as the reply) and a calm note; never an error
    failed(user_id, shown, sentence)   what was written so far (kept as the reply) and the error line with the real reason
                                       (each takes `attempt=N`: the retry's refs; `finished` also `ordered=True`: the blocks are the turn in order, D212)
    ref_of(user_id, tail, attempt)     the src_ref of one of them
    owner_ref(client_id)               the src_ref of the owner's line (`direct-ask:<client_id>`)
    switch_notice(switched)            "Switched Claude to Codex; carried 40 messages" (the words of ChatPill.switchNotice)
    attached_line(names, kinds)        "(attached: a.png, b.pdf)", the last line of an owner's line that carried files

Every message of one turn is stored in ONE transaction (`chat_v2._post_all`), so a page never sees half an ending, and each carries a src_ref
that names the owner's line (`direct:<id>` for the reply, or for the first message when there is no reply; `direct-note:<id>`,
`direct-error:<id>`, `direct-switch:<id>` for the others), because `ChatStore.post` refuses a repeated src_ref and `chats._turn_of` reads
the owner's line back from all of them. A retry of the same owner line is attempt N >= 2 and adds `.N` to each ref (`direct:<id>.2`), because the
first attempt's rows are stored for good (D216); attempt 1 keeps the historical shape, so every stored row is still read the same. Notes and errors are not carried over to the next model (`ChatTranscripts` takes text and questions
only); a kept partial reply is, because the model did write it. Nothing here touches a store: these are values in, values out.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, StringConstraints

from sutra_app.connectors.attachments import clean_name as _clean_file_name
from sutra_app.library.base import Value

__all__ = ["Ending", "finished", "stopped", "failed", "switch_notice", "earlier_note", "attached_line", "clean_name", "ref_of", "owner_ref", "valid_client_id",
           "STOPPED", "STOPPED_EMPTY", "NO_REPLY", "MAX_TEXT", "MAX_ATTEMPT", "DIRECT_ASK", "CLIENT_ID_RE"]

STOPPED = "Stopped. What was written is kept."
STOPPED_EMPTY = "Stopped before the model wrote anything."
NO_REPLY = "(no reply)"
MAX_TEXT = 200_000                       # the store's cap on a message (chat_v2._post cuts there too): a longer reply is kept cut, never lost
MAX_ATTEMPT = 99                         # the ref shape allows `.2` to `.99`: a chat that was retried that often is told so instead of failing to store
DIRECT_ASK = "direct-ask:"               # the src_ref prefix of the owner's line that starts a direct turn (a random tail, or the page's `client_id`)
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_NAMES = {"claude": "Claude", "codex": "Codex"}
_KIND_WORDS = {"image": "an image", "pdf": "a PDF", "text": "a text file"}


class Ending(Value):
    """One message the end of a turn stores: always role agent, who sutra (a note is drawn calm by its kind, an error red). The text is kept
    as the model wrote it (no stripping)."""

    model_config = ConfigDict(str_strip_whitespace=False)
    kind: Literal["text", "note", "error"]
    text: Annotated[str, StringConstraints(min_length=1, max_length=MAX_TEXT)]
    src_ref: Annotated[str, StringConstraints(pattern=r"^direct(-(note|error|switch))?:[1-9][0-9]{0,15}(\.([2-9]|[1-9][0-9]))?$")]
    blocks: list[dict[str, Any]] = []
    ordered: bool = False                    # `blocks` is the whole turn in order, text included (D212): stored as a sibling key of the meta, read back as `ChatMessageOut.ordered`


def ref_of(user_id: int, tail: str = "", attempt: int = 1) -> str:
    """`direct[-tail]:<owner id>` for attempt 1 (the shape of every row stored before retries had their own), plus `.N` from attempt 2."""
    if not isinstance(attempt, int) or isinstance(attempt, bool) or not 1 <= attempt <= MAX_ATTEMPT:
        raise ValueError(f"an attempt is a number from 1 to {MAX_ATTEMPT}")
    return f"direct{'-' + tail if tail else ''}:{int(user_id)}" + (f".{attempt}" if attempt > 1 else "")


_ref = ref_of


def owner_ref(client_id: str) -> str:
    if not valid_client_id(client_id):
        raise ValueError("a client id is 8 to 64 characters of letters, digits, '_' or '-'")
    return DIRECT_ASK + client_id


def valid_client_id(value: Any) -> bool:
    return isinstance(value, str) and CLIENT_ID_RE.match(value) is not None


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


def earlier_note(earlier: Any, *, bare: bool = False) -> str:
    """One line for each earlier try of this turn that ran tools ("Earlier try (claude, failed: Claude had a server error) ran: Reading a.py, Editing b.py"), at most 20 lines, so
    that a try that may have changed files stays visible after a reload, as text. `earlier` is `BlockAccumulator.earlier_attempts()`; a try with no tool line adds nothing,
    unless `bare` (a turn that failed: every earlier try is said, with its reason, so a reload tells who failed before the last error as the live page did)."""
    lines: list[str] = []
    for item in earlier if isinstance(earlier, list) else []:
        if not isinstance(item, dict) or not (item.get("lines") or (bare and str(item.get("reason") or "").strip())):
            continue
        if not item.get("lines"):
            lines.append(f"Earlier try ({_label(item.get('provider')) or 'the model'}) failed: {str(item.get('reason')).strip()}"[:600])
            continue
        reason = str(item.get("reason") or "").strip()
        head = f"Earlier try ({_label(item.get('provider')) or 'the model'}{', failed: ' + reason if reason else ''}) ran: "
        ran = ", ".join(str(x) for x in item["lines"][:20])
        lines.append((head + ran + ("." if not ran.endswith(".") else "") + (" It may have changed files." if item.get("after_side_effects") else ""))[:600])
    return "\n".join(lines[:20])


def _notes(user_id: int, attempt: int, switched: Any, earlier: Any, *, bare: bool = False) -> list["Ending"]:
    text = "\n".join(part for part in (switch_notice(switched), earlier_note(earlier, bare=bare)) if part)
    return [Ending(kind="note", text=text, src_ref=ref_of(user_id, "switch", attempt))] if text else []


def finished(user_id: int, done: dict, attempt: int = 1, *, ordered: bool = False, earlier: Any = None) -> list[Ending]:
    """`ordered=True` keeps text blocks (the turn's blocks are the whole turn in order) and marks the reply so; the default drops text blocks that carry no text
    and is what every turn stored before the live view looks like."""
    blocks = [b for b in done.get("blocks", []) if isinstance(b, dict) and (b.get("type") != "text" or b.get("text"))]
    out = _notes(user_id, attempt, done.get("switched"), earlier)
    out.append(Ending(kind="text", text=(str(done.get("text") or "") or NO_REPLY)[:MAX_TEXT], src_ref=ref_of(user_id, "", attempt), blocks=blocks,
                      ordered=bool(ordered and blocks)))
    return out


def stopped(user_id: int, shown: str, attempt: int = 1, *, blocks: list[dict] | None = None, ordered: bool = False, earlier: Any = None) -> list[Ending]:
    notes = _notes(user_id, attempt, None, earlier)
    if not shown.strip():            # nothing was written; the tools that ran stay visible on the calm note (a note may carry blocks)
        return notes + [Ending(kind="note", text=STOPPED_EMPTY, src_ref=ref_of(user_id, "", attempt), blocks=blocks or [], ordered=bool(ordered and blocks))]
    return notes + [Ending(kind="text", text=shown[:MAX_TEXT], src_ref=ref_of(user_id, "", attempt), blocks=blocks or [], ordered=bool(ordered and blocks)),
                    Ending(kind="note", text=STOPPED, src_ref=ref_of(user_id, "note", attempt))]


def failed(user_id: int, shown: str, sentence: str, attempt: int = 1, *, blocks: list[dict] | None = None, ordered: bool = False, earlier: Any = None) -> list[Ending]:
    reason = sentence.strip()[:MAX_TEXT] or "The model could not answer."
    notes = _notes(user_id, attempt, None, earlier, bare=True)
    if not shown.strip():
        return notes + [Ending(kind="error", text=reason, src_ref=ref_of(user_id, "", attempt), blocks=blocks or [], ordered=bool(ordered and blocks))]
    return notes + [Ending(kind="text", text=shown[:MAX_TEXT], src_ref=ref_of(user_id, "", attempt), blocks=blocks or [], ordered=bool(ordered and blocks)),
                    Ending(kind="error", text=reason, src_ref=ref_of(user_id, "error", attempt))]


def clean_name(name: Any) -> str:
    """A file name as the attachment store cleans it (`connectors.attachments.clean_name`: letters, digits and accents of any script, emoji, space
    . _ ( ) -; at most 80), so a name never breaks the list or a line."""
    return _clean_file_name(name)


def attached_line(names: list[str], kinds: list[str]) -> str:
    """The record of what went with an owner's line: the owner's names when the page sent one per file, else what each file is."""
    if not kinds:
        return ""
    cleaned = [clean_name(n) for n in names] if len(names) == len(kinds) else []
    shown = [c if c else _KIND_WORDS.get(k, "a file") for c, k in zip(cleaned or [""] * len(kinds), kinds)]
    return "(attached: " + ", ".join(shown) + ")"
