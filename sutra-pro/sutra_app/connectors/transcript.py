"""The carry-over of a chat transcript to a new provider session (connectors design 3.6 "Chat sessions", D32).

The provider's session is a cache of the app's own transcript. When the Router has to start a new provider session (the
provider changed, the provider forgot the session, or `session.json` is gone) the first prompt starts with this block, so the
new model knows the conversation. It is deterministic text: no model writes a summary (cost, and a new failure mode).

    messages whose rendered lines fit in 60,000 characters (J2 `CHAT_FULL_CHARS`, j2.py:93)     all of them, in full
    more than that                                                                            the last 40 messages (J2
        `CHAT_TAIL`, j2.py:94) in full, plus ONE line of at most 120 characters for each older message, the lines together
        capped at 8,000 characters

`render_carry_over([])` is the empty string: a brand-new conversation carries nothing.
"""
from __future__ import annotations

from typing import Optional, Sequence

from .models import Message

__all__ = ["render_carry_over", "FULL_CHARS", "TAIL_MESSAGES", "DIGEST_LINE_CHARS", "DIGEST_CAP_CHARS", "ROLE_LABELS"]

FULL_CHARS = 60_000          # J2 CHAT_FULL_CHARS
TAIL_MESSAGES = 40           # J2 CHAT_TAIL
DIGEST_LINE_CHARS = 120      # one shortened line per older message
DIGEST_CAP_CHARS = 8_000     # all shortened lines together
ROLE_LABELS = {"user": "User", "assistant": "Assistant", "system": "System"}


def _line(m: Message) -> str:
    return f"{ROLE_LABELS[m.role]}: {m.text}"


def _short(m: Message) -> str:
    """The message on one line of at most 120 characters (whitespace collapsed, cut with an ellipsis)."""
    flat = " ".join(_line(m).split())
    return flat if len(flat) <= DIGEST_LINE_CHARS else flat[:DIGEST_LINE_CHARS - 1].rstrip() + "…"


def _header(from_provider: Optional[str], to_provider: Optional[str], omitted: int) -> str:
    if from_provider and to_provider and from_provider == to_provider:
        why = f"the provider session was lost ({to_provider})"
    elif from_provider and to_provider:
        why = f"the provider changed ({from_provider} → {to_provider})"
    else:
        why = "the provider changed"
    head = f"Earlier messages of this conversation, carried over because {why}"
    if omitted:
        head += f"; [{omitted} earlier message{'s' if omitted != 1 else ''} omitted]"
    return head


def render_carry_over(messages: Sequence[Message], *, from_provider: Optional[str] = None, to_provider: Optional[str] = None,
                      full_chars: int = FULL_CHARS, tail: int = TAIL_MESSAGES, digest_cap: int = DIGEST_CAP_CHARS) -> str:
    """The block a new provider session starts with. `from_provider` / `to_provider` only fill the header. The three limits are
    parameters for tests; the defaults are J2's."""
    msgs = list(messages)
    if not msgs:
        return ""
    lines = [_line(m) for m in msgs]
    if len("\n".join(lines)) <= full_chars or len(msgs) <= tail:
        return _header(from_provider, to_provider, 0) + ":\n\n" + "\n".join(lines)
    older, recent = msgs[:-tail], lines[-tail:]
    shown: list[str] = []
    used = 0
    for m in older:
        short = _short(m)
        if used + len(short) + 1 > digest_cap:
            break
        shown.append(short)
        used += len(short) + 1
    rest = len(older) - len(shown)
    digest = "\n".join(shown)
    if rest:
        digest += f"\n[{rest} more not listed]"
    return (_header(from_provider, to_provider, len(older)) + ":\n\nShortened earlier messages:\n" + digest
            + "\n\nRecent messages in full:\n" + "\n".join(recent))
