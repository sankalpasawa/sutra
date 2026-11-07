"""Chat routes v2 (absorb design 2.2 and 2.3, work package ABS-7). Writes need the token (D81).

    GET  /api/chats/search?q=&scope=&include=archived   -> {results: [{session_id, message_id, title, snippet, at, archived}]}   (at most 50)
    POST /api/chats/{sid}/archive | /unarchive          -> {session_id, archived}      (a mark, never a delete)
    GET  /api/chats/{sid}/providers                     -> {providers: ProviderPill[], chosen}
    PUT  /api/chats/{sid}/choice  {provider, model?, effort?} -> {session_id, provider, model, effort}   (null provider clears; the policy default is untouched;
                                                           a model the provider does not offer is a 422 that names the valid ones)
    POST /api/chats/{sid}/attachments {name, content_b64} -> AttachmentRef                (20 MB a file)
    POST /api/chats/{sid}/direct  {text, attachments?, names?} -> 202 {message_id, turn}  (the org, a department or a division chat answered by the chat model)
    POST /api/chats/{sid}/direct/stop                   -> {session_id, stopped}          (ends the turn that is answering; false when none is)

`/direct` stores the owner's line, writes the session's grounding (the node's own record and the rules, `orchestrator/chat_ground.py`, through
`ChatPort.set_system`), then answers through `ChatPort.stream`. The pieces of the reply travel as `chat.partial` events
({session_id, message_id, delta}); they are NOT stored and NOT in the replay ring, so a client that reconnects mid-turn gets the stored
message only. The agent's message is written once, at `turn_done` (with its typed blocks); a stopped turn keeps what was written and adds a
calm note, a failed one keeps it and adds the `error` line, a provider switch is noted (orchestrator/direct_turns.py, GAP-chat-comfort).
The org chat's staged agent path (`POST /api/chats/cs_org/messages`) is unchanged, and so is a team chat's plain message route; `/direct` on cs_org\nis the owner's opt-in "ask directly" (D115), never the default.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import ConfigDict, Field, StringConstraints

from sutra_app.connectors.attachments import MAX_BYTES, MAX_PER_MESSAGE
from sutra_app.connectors.chat_models import AttachmentRef, ChatTurnIn
from sutra_app.connectors.egress import scan
from sutra_app.connectors.errors import CallCancelledError, ConnectorError
from sutra_app.library.base import Value
from sutra_app.library.gate import GATE
from sutra_app.orchestrator.api.chat import ID_PATTERN, respond
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.chat_ground import ground
from sutra_app.orchestrator.chat_v2 import MAX_RESULTS, SCOPE_RE, ChatArchive, ChatChoices, ChatSearch
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.direct_turns import Ending, attached_line, failed, finished, stopped
from sutra_app.orchestrator.errors import AppError, Busy, NotFound, ReadOnly
from sutra_app.orchestrator.events import PARTIAL
from sutra_app.orchestrator.records import ChatMessage

__all__ = ["router", "build_router", "ChoiceIn", "UploadIn", "DirectIn"]

log = logging.getLogger(__name__)
PARTIAL_EVERY_CHARS = 60
_running: set[str] = set()
_running_lock = threading.Lock()


class ChoiceIn(Value):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider: Annotated[str, StringConstraints(pattern=r"^(claude|codex)$")] | None = None
    model: Annotated[str, StringConstraints(max_length=100)] | None = None
    effort: Annotated[str, StringConstraints(pattern=r"^(low|medium|high|xhigh|max)$")] | None = None


class UploadIn(Value):
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    content_b64: Annotated[str, StringConstraints(min_length=1, max_length=MAX_BYTES * 4 // 3 + 8)]


class DirectIn(Value):
    text: Annotated[str, StringConstraints(min_length=1, max_length=8000)]
    attachments: Annotated[list[Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]], Field(max_length=MAX_PER_MESSAGE)] = []
    # the owner's names of the attachments, in order: only for the record on the owner's line (GAP-chat-comfort); the model's input is unchanged
    names: Annotated[list[Annotated[str, StringConstraints(max_length=200)]], Field(max_length=MAX_PER_MESSAGE)] = []


def _need(request: Request, name: str) -> Any:
    found = getattr(services_of(request), name, None)
    if found is None:
        raise AppError("internal", f"the {name} is not wired")
    return found


def _provider_error(exc: ConnectorError) -> AppError:
    return AppError("provider_unavailable", exc.user_message())


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["chats v2"])

    @router.get("/chats/search", summary="Search the chats")
    async def search(request: Request, q: str = Query("", max_length=200), scope: str = Query("all", max_length=80),
                     include: str | None = Query(None, pattern="^archived$")) -> RedactedJSONResponse:
        if SCOPE_RE.match(scope) is None:
            raise AppError("validation", "scope is all, node:<id> or dept:<id>")
        db = _need(request, "db")
        found = await run_blocking(lambda: ChatSearch(db).search(q, scope=scope, include_archived=include == "archived", limit=MAX_RESULTS))
        return respond(request, {"results": found})

    @router.post("/chats/{sid}/archive", summary="Archive a chat (a mark)", dependencies=[Depends(require_token)])
    async def archive(request: Request, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        db, graph = _need(request, "db"), getattr(services_of(request), "graph", None)

        def run() -> None:
            with db.tx() as tx:
                ChatArchive(db, graph).archive(tx, sid)
        await run_blocking(run)
        return respond(request, {"session_id": sid, "archived": True})

    @router.post("/chats/{sid}/unarchive", summary="Bring an archived chat back", dependencies=[Depends(require_token)])
    async def unarchive(request: Request, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        db, graph = _need(request, "db"), getattr(services_of(request), "graph", None)

        def run() -> None:
            with db.tx() as tx:
                ChatArchive(db, graph).unarchive(tx, sid)
        await run_blocking(run)
        return respond(request, {"session_id": sid, "archived": False})

    @router.get("/chats/{sid}/providers", summary="The provider pill of a chat")
    async def providers(request: Request, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        chats, db, port = _need(request, "chats"), _need(request, "db"), _need(request, "chat_port")
        await run_blocking(chats.session, sid)
        pills = await run_blocking(lambda: port.providers(sid))
        chosen = await run_blocking(lambda: ChatChoices(db).get(sid))
        return respond(request, {"providers": [p.model_dump(mode="json") | {"chosen": p.name == chosen} for p in pills], "chosen": chosen or None})

    @router.put("/chats/{sid}/choice", summary="Choose the provider of this chat", dependencies=[Depends(require_token)])
    async def choose(request: Request, body: ChoiceIn, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        chats, db, port = _need(request, "chats"), _need(request, "db"), _need(request, "chat_port")
        await run_blocking(chats.session, sid)

        def run() -> Any:
            choice = port.choose(sid, body.provider, body.model, body.effort)          # refuses a provider that cannot run, an unknown model or effort (422 below)
            with db.tx() as tx:
                ChatChoices(db).set(tx, sid, body.provider)
            return choice

        try:
            choice = await run_blocking(run)
        except ConnectorError as exc:
            raise AppError("validation", exc.user_message()) from None
        return respond(request, {"session_id": sid, "provider": choice.provider, "model": choice.model, "effort": choice.effort})

    @router.post("/chats/{sid}/attachments", summary="Attach a file", dependencies=[Depends(require_token)])
    async def attach(request: Request, body: UploadIn, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        chats, store = _need(request, "chats"), _need(request, "attachments")
        await run_blocking(chats.session, sid)
        try:
            blob = base64.b64decode(body.content_b64, validate=True)
        except (ValueError, binascii.Error):
            raise AppError("validation", "that file could not be read") from None
        try:
            ref = await run_blocking(store.upload, body.name, blob)
        except ConnectorError as exc:
            raise AppError("validation", exc.user_message()) from None
        return respond(request, ref.model_dump(mode="json"))

    @router.post("/chats/{sid}/direct", summary="Ask the chat model directly", dependencies=[Depends(require_token)])
    async def direct(request: Request, body: DirectIn, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        services = services_of(request)
        chats, port, attachments = _need(request, "chats"), _need(request, "chat_port"), _need(request, "attachments")
        session = await run_blocking(chats.session, sid)
        if session.status != "active" or not session.writable or session.kind not in ("org", "department", "division"):
            raise ReadOnly("This chat cannot be asked directly")
        refs = []
        for ref_id in body.attachments:
            path = attachments.get(ref_id)
            if path is None:
                raise NotFound("that attachment")
            refs.append(AttachmentRef(id=ref_id, name=path.name, kind=_kind_of(path.name), size=path.stat().st_size))
        with _running_lock:
            if sid in _running:
                raise Busy("This chat is already answering")
            _running.add(sid)
        try:
            said = _clean(services, body.text)          # stored and sent without credential shapes: a secret never lands in the chat store
            attached = _clean(services, attached_line(list(body.names), [r.kind for r in refs]))
            message_id = await run_blocking(_store_user_line, services, sid, said, attached)
            await run_blocking(_ground, services, port, sid)
        except BaseException:
            _running.discard(sid)
            raise
        asyncio.get_running_loop().create_task(run_blocking(_answer, services, port, sid, message_id, ChatTurnIn(text=said, attachments=refs)))
        return RedactedJSONResponse(status_code=202, content={"message_id": message_id, "turn": "started"})

    @router.post("/chats/{sid}/direct/stop", summary="Stop the turn that is answering", dependencies=[Depends(require_token)])
    async def stop(request: Request, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        chats, port = _need(request, "chats"), _need(request, "chat_port")
        await run_blocking(chats.session, sid)
        stopped = await run_blocking(port.stop, sid)
        return respond(request, {"session_id": sid, "stopped": bool(stopped)})

    return router


def _kind_of(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return "pdf" if ext == "pdf" else "image" if ext in ("png", "jpg", "gif", "webp") else "text"


def _post(services: Any, sid: str, *, role: str, who: str, kind: str, text: str, blocks: list | None = None,
          src_ref: str | None = None) -> int:
    redact = services.redact
    with services.db.tx() as tx:
        out = services.chats.post(tx, sid, GATE.check("chat_message", ChatMessage(
            kind=kind, session_id=sid, role=role, who=who, text=redact(text)[:200_000], blocks=blocks or [], src_ref=src_ref, at=tx.now()), ctx=tx.ctx))
    return out.id


def _clean(services: Any, text: str) -> str:
    """The app's secret values and the egress credential shapes replaced (connectors.egress), so the stored line, the line the model gets and
    any later carry-over are the same text."""
    return scan(services.redact(text), replace=True)[0]


def _post_all(services: Any, sid: str, endings: list[Ending]) -> None:
    """The messages that end one turn, in ONE transaction: a page never reads half an ending."""
    redact = services.redact
    with services.db.tx() as tx:
        for e in endings:
            services.chats.post(tx, sid, GATE.check("chat_message", ChatMessage(
                kind=e.kind, session_id=sid, role="agent", who="sutra", text=redact(e.text)[:200_000], blocks=e.blocks, src_ref=e.src_ref,
                at=tx.now()), ctx=tx.ctx))


def _store_user_line(services: Any, sid: str, text: str, attached: str = "") -> int:
    """The owner's line; with files, a last line records what went with it (the model gets the files and `text` itself)."""
    return _post(services, sid, role="user", who="user", kind="text", text=text + ("\n" + attached if attached else ""))


def _ground(services: Any, port: Any, sid: str) -> None:
    """The session's system text for this turn: the node's own record and the rules (`orchestrator/chat_ground.py`), rebuilt every turn so it
    is current. A grounding that cannot be built or written is logged and the turn runs without a new one; it never fails the turn."""
    try:
        port.set_system(sid, ground(services, sid))
    except Exception:
        log.warning("could not ground the direct chat %s", sid, exc_info=True)


def _answer(services: Any, port: Any, sid: str, user_message_id: int, turn: ChatTurnIn) -> None:
    """The turn, on a worker thread: partials out as control events, the stored reply once at the end. A stop keeps what was written
    with a calm note; a failure keeps it with the real reason (direct_turns)."""
    bus = services.bus
    buffered = ""
    shown = ""                                                       # what the owner has seen stream in, redacted as it was sent

    def flush() -> None:
        nonlocal buffered, shown
        if buffered:
            piece = services.redact(buffered)
            shown += piece
            if bus is not None:
                bus.publish_one(PARTIAL, {"session_id": sid, "message_id": user_message_id, "delta": piece})
        buffered = ""

    try:
        done = None
        for event in port.stream(sid, turn):
            if event.kind == "partial":
                buffered += event.data.get("delta", "")
                if len(buffered) >= PARTIAL_EVERY_CHARS:
                    flush()
            elif event.kind == "turn_done":
                done = event.data
        flush()
        if done is None:
            raise RuntimeError("the turn ended without a result")
        _post_all(services, sid, finished(user_message_id, done))
    except Exception as exc:                                         # a failed turn is a message, not a lost line
        flush()
        log.warning("direct chat turn failed for %s: %s", sid, type(exc).__name__)
        if isinstance(exc, CallCancelledError):                      # the owner's Stop is not an error: what was written stays
            endings = stopped(user_message_id, shown)
        else:
            message = exc.user_message() if isinstance(exc, ConnectorError) else (exc.message if isinstance(exc, AppError) else "The model could not answer.")
            endings = failed(user_message_id, shown, message)
        try:
            _post_all(services, sid, endings)
        except Exception:
            log.exception("could not store the failed turn of %s", sid)
    finally:
        with _running_lock:
            _running.discard(sid)


router = build_router()
