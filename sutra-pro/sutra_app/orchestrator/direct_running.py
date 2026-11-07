"""Which chats have a direct turn answering right now, in this process (QA direct-chat bugs 3 and 4).

    begin(sid)               claim the chat for a direct turn: False when one is already answering (the route answers 409 `busy`)
    attach(sid, message_id)  the owner's line the turn answers, once it is stored
    end(sid)                 the turn is over (always, whatever way it ended)
    answering(sid)           a direct turn is answering
    turn_of(sid)             the owner's line it answers, or None (not answering, or the line is not stored yet)

One turn at a time per chat is the rule of `POST /api/chats/{sid}/direct`; the same registry now also (a) refuses a team-route message while a direct turn runs
(`POST /api/chats/{sid}/messages`: the two answers would interleave in one chat) and (b) lets a page that did not start the turn, a reload or a second tab,
learn that the chat is answering (`ChatSessionOut.direct_turn`) and offer Stop. It is memory only: a process that dies takes its turns with it, which is why
the next start marks the owner lines left without an answer (`chat_v2.recover_interrupted`).

`RUNNING` is the set the route has always used (`api.chat_v2._running` is this very object, so a test or a caller that adds to it is seen here too)."""
from __future__ import annotations

import threading

__all__ = ["RUNNING", "LOCK", "begin", "attach", "end", "answering", "turn_of"]

RUNNING: set[str] = set()
LOCK = threading.Lock()
_TURNS: dict[str, int] = {}


def begin(session_id: str) -> bool:
    with LOCK:
        if session_id in RUNNING:
            return False
        RUNNING.add(session_id)
        return True


def attach(session_id: str, message_id: int) -> None:
    with LOCK:
        if session_id in RUNNING:
            _TURNS[session_id] = int(message_id)


def end(session_id: str) -> None:
    with LOCK:
        RUNNING.discard(session_id)
        _TURNS.pop(session_id, None)


def answering(session_id: str) -> bool:
    with LOCK:
        return session_id in RUNNING


def turn_of(session_id: str) -> int | None:
    with LOCK:
        return _TURNS.get(session_id) if session_id in RUNNING else None
