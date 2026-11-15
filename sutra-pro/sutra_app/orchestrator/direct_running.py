"""Which chats have a direct turn answering right now, in this process (QA direct-chat bugs 3 and 4).

    begin(sid)               claim the chat for a direct turn: False when one is already answering (the route answers 409 `busy`)
    begin_turn(sid, client_id)  the same claim, with the turn's stop token (D215): `Started(token)` or `Busy(client_id)` (the one that holds it)
    token_of(sid)            the stop token of the turn that is answering, or None
    bind(sid, live) / live_of(sid)  the `LiveTurn` of the turn (D204), once the route has built it
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
from dataclasses import dataclass
from typing import Any

from sutra_app.connectors.cancel import CancelToken

__all__ = ["RUNNING", "LOCK", "begin", "begin_turn", "attach", "end", "answering", "turn_of", "token_of", "client_of", "bind", "live_of",
           "Started", "Busy"]

RUNNING: set[str] = set()
LOCK = threading.Lock()
_TURNS: dict[str, int] = {}
_TOKENS: dict[str, CancelToken] = {}
_CLIENTS: dict[str, str | None] = {}
_LIVE: dict[str, Any] = {}


@dataclass(frozen=True)
class Started:
    token: CancelToken


@dataclass(frozen=True)
class Busy:
    client_id: str | None = None          # the `client_id` of the turn that holds the chat (None when it was started without one)


def begin_turn(session_id: str, client_id: str | None = None) -> Started | Busy:
    """Claims the chat for one direct turn and creates its stop token. `Busy` carries the holder's `client_id`, so a repeated send of the same turn can be
    told apart from a different one (D220)."""
    with LOCK:
        if session_id in RUNNING:
            return Busy(_CLIENTS.get(session_id))
        RUNNING.add(session_id)
        token = CancelToken()
        _TOKENS[session_id] = token
        _CLIENTS[session_id] = client_id
        return Started(token)


def begin(session_id: str) -> bool:
    return isinstance(begin_turn(session_id), Started)


def attach(session_id: str, message_id: int) -> None:
    with LOCK:
        if session_id in RUNNING:
            _TURNS[session_id] = int(message_id)


def end(session_id: str) -> None:
    with LOCK:
        RUNNING.discard(session_id)
        _TURNS.pop(session_id, None)
        _TOKENS.pop(session_id, None)
        _CLIENTS.pop(session_id, None)
        _LIVE.pop(session_id, None)


def answering(session_id: str) -> bool:
    with LOCK:
        return session_id in RUNNING


def turn_of(session_id: str) -> int | None:
    with LOCK:
        return _TURNS.get(session_id) if session_id in RUNNING else None


def token_of(session_id: str) -> CancelToken | None:
    with LOCK:
        return _TOKENS.get(session_id) if session_id in RUNNING else None


def client_of(session_id: str) -> str | None:
    with LOCK:
        return _CLIENTS.get(session_id) if session_id in RUNNING else None


def bind(session_id: str, live: Any) -> None:
    """Remember the `LiveTurn` of the turn that is answering (dropped by `end`)."""
    with LOCK:
        if session_id in RUNNING:
            _LIVE[session_id] = live


def live_of(session_id: str) -> Any:
    with LOCK:
        return _LIVE.get(session_id) if session_id in RUNNING else None
