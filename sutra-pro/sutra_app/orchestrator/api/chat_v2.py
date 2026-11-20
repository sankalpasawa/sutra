"""Chat routes v2 (absorb design 2.2 and 2.3, work package ABS-7). Writes need the token (D81).

    GET  /api/chats/search?q=&scope=&include=archived   -> {results: [{session_id, message_id, title, snippet, at, archived}]}   (at most 50)
    POST /api/chats/{sid}/archive | /unarchive          -> {session_id, archived}      (a mark, never a delete)
    GET  /api/chats/{sid}/providers                     -> {providers: ProviderPill[], chosen, kind, agent, own, effective}   (own: the chat's own pick or null;
                                                           effective: {provider, model, effort, source: own|run|team|default}, D131)
    PUT  /api/chats/{sid}/choice  {provider, model?, effort?} -> {session_id, provider, model, effort, source, effective}   (null provider clears; the policy default
                                                           is untouched; a model the provider does not offer is a 422 that names the valid ones. A function or
                                                           step chat (an agent's) is only checked, no router session is made, and its triple is stored; the
                                                           live run's choices.json is rewritten so the agent's NEXT call uses it)
    POST /api/chats/{sid}/attachments {name, content_b64} -> AttachmentRef                (20 MB a file)
    POST /api/chats/{sid}/direct  {text, attachments?, names?} -> 202 {message_id, turn}  (the org, a department or a division chat answered by the chat model)
    POST /api/chats/{sid}/direct/stop                   -> {session_id, stopped}          (ends the turn that is answering; false when none is)
    GET  /api/chats/{sid}/turn                          -> the live turn's snapshot, or {live: false, ...}      (SUTRA_LIVE_V1, streaming design D203)
    POST /api/chats/{sid}/direct/retry {message_id, client_id?} -> 202 like /direct, attempt_no N                  (SUTRA_LIVE_V1; a failed or stopped newest line only)

With `SUTRA_LIVE_V1=1` the direct chat is a live turn (orchestrator/live_turn.py): `/direct` takes the page's `client_id` (a repeated one answers 200 `{duplicate: true}`, never a
second turn), answers 202 with the generation id, and every event of the turn travels as `chat.live` (see events.py); Stop answers at once and the process is stopped in the
background; the reply is stored once with its blocks in order. With the flag off nothing below `_answer_legacy` is reached and every payload is what it was.

`/direct` stores the owner's line, writes the session's grounding (the node's own record and the rules, `orchestrator/chat_ground.py`, through
`ChatPort.set_system`), then answers through `ChatPort.stream`. The pieces of the reply travel as `chat.partial` events
({session_id, message_id, delta}); they are NOT stored and NOT in the replay ring, so a client that reconnects mid-turn gets the stored
message only. When the router retries the turn, the port says `restart` and the pieces shown so far are void: one more `chat.partial` with
`reset: true` and an empty delta tells the page to start its row again (and the kept partial reply of a failed turn is the last attempt's). The agent's message is written once, at `turn_done` (with its typed blocks); a stopped turn keeps what was written and adds a
calm note, a failed one keeps it and adds the `error` line, a provider switch is noted (orchestrator/direct_turns.py, GAP-chat-comfort).
The org chat's staged agent path (`POST /api/chats/cs_org/messages`) is unchanged, and so is a team chat's plain message route; `/direct` on cs_org\nis the owner's opt-in "ask directly" (D115), never the default.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import ConfigDict, Field, StringConstraints

from sutra_app.connectors.chat_blocks import join_text
from sutra_app.connectors.attachments import MAX_BYTES, MAX_PER_MESSAGE, clean_name
from sutra_app.connectors.chat_models import AttachmentRef, ChatTurnIn
from sutra_app.connectors.egress import scan
from sutra_app.connectors.errors import CallCancelledError, ConnectorError, ReplyTruncatedError
from sutra_app.library.base import Value
from sutra_app.library.gate import GATE
from sutra_app.library.types import violation
from sutra_app.orchestrator.api.chat import ID_PATTERN, respond
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator import ask_mode, direct_running
from sutra_app.orchestrator.agent_sessions import agent_of, effective, pick_dict
from sutra_app.orchestrator.chat_ground import ground
from sutra_app.orchestrator import live_checkpoint
from sutra_app.orchestrator.chat_v2 import (DIRECT_ASK, MAX_RESULTS, SCOPE_RE, ChatArchive, ChatChoices, ChatSearch, attempts_stored, find_owner_line, last_outcome, newest_owner_line,
                                            next_attempt)
from sutra_app.orchestrator.live_turn import LiveConfig, LiveTurn
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator import direct_turns
from sutra_app.orchestrator.direct_turns import MAX_TEXT, Ending, attached_line, failed, finished, stopped
from sutra_app.orchestrator.errors import AppError, Busy, NotFound, ReadOnly, validation_error
from sutra_app.orchestrator.events import PARTIAL
from sutra_app.orchestrator.records import ChatMessage

__all__ = ["router", "build_router", "ChoiceIn", "UploadIn", "DirectIn", "RetryIn"]

log = logging.getLogger(__name__)
PARTIAL_EVERY_CHARS = 60
MAX_CHARS = 8000                                                      # the longest message the owner can send (the page's box says the same: chat_composer.js)
_running = direct_running.RUNNING                                   # the chats with a direct turn answering: one at a time (a Busy for the next), shared with the team route
_running_lock = direct_running.LOCK
_background: set[Any] = set()                                       # the tasks that stop a process in the background (kept so none is collected before it ends)


class ChoiceIn(Value):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider: Annotated[str, StringConstraints(pattern=r"^(claude|codex)$")] | None = None
    model: Annotated[str, StringConstraints(max_length=100)] | None = None
    effort: Annotated[str, StringConstraints(pattern=r"^(low|medium|high|xhigh|max)$")] | None = None


class UploadIn(Value):
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    content_b64: Annotated[str, StringConstraints(min_length=1, max_length=MAX_BYTES * 4 // 3 + 8)]


class DirectIn(Value):
    # the model only bounds what the store could hold; the cap of MAX_CHARS is checked in the route so that the refusal can say what it is (a pydantic
    # refusal is the generic "The request was refused")
    text: Annotated[str, StringConstraints(min_length=1, max_length=MAX_TEXT)]
    attachments: Annotated[list[Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]], Field(max_length=MAX_PER_MESSAGE)] = []
    # the owner's names of the attachments, in order: only for the record on the owner's line (GAP-chat-comfort); the model's input is unchanged
    names: Annotated[list[Annotated[str, StringConstraints(max_length=200)]], Field(max_length=MAX_PER_MESSAGE)] = []
    # the page's id of this send (8 to 64 characters of letters, digits, `_`, `-`): a repeated send with it is the same send (D220). Only read when the live chat is on
    client_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{8,64}$")] | None = None


class RetryIn(Value):
    model_config = ConfigDict(extra="forbid", strict=True)
    message_id: Annotated[int, Field(ge=1)]
    client_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{8,64}$")] | None = None


def _need(request: Request, name: str) -> Any:
    found = getattr(services_of(request), name, None)
    if found is None:
        raise AppError("internal", f"the {name} is not wired")
    return found


def _default_of(port: Any) -> Any:
    """The policy default for an agent, from the chat port (a port without one, as a test's stand-in, knows nothing: all fields empty)."""
    found = getattr(port, "default_pick", None)
    return found if callable(found) else None


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
        session = await run_blocking(chats.session, sid)

        def read() -> dict[str, Any]:
            pills = port.providers(sid)
            conn = db.conn()
            own = ChatChoices(db).pick(sid)
            ref = agent_of(conn, sid)
            out = []
            for pill in pills:
                shown = pill.model_dump(mode="json") | {"chosen": pill.name == own.provider}
                if pill.name == own.provider:                  # the database has the model and effort when the chat's session.json is gone (a temp folder)
                    shown["chat_model"] = shown.get("chat_model") or own.model
                    shown["chat_effort"] = shown.get("chat_effort") or own.effort
                out.append(shown)
            shown = {"providers": out, "chosen": own.provider or None, "kind": session.kind, "agent": ref.agent if ref is not None else None,
                     "own": pick_dict(own), "effective": effective(conn, sid, _default_of(port))}
            if ask_mode.ask_on(services_of(request)):          # DV-1: the page learns here that Ask exists; with the flag off the answer has no such key
                shown["ask"] = True
            return shown

        return respond(request, await run_blocking(read))

    @router.put("/chats/{sid}/choice", summary="Choose the provider, model and effort of this chat", dependencies=[Depends(require_token)])
    async def choose(request: Request, body: ChoiceIn, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        chats, db, port = _need(request, "chats"), _need(request, "db"), _need(request, "chat_port")
        tasks = getattr(services_of(request), "tasks", None)
        session = await run_blocking(chats.session, sid)

        def run() -> Any:
            ref = agent_of(db.conn(), sid)
            own = ChatChoices(db).pick(sid)
            kept = body.provider is not None and own.provider == body.provider             # the pill changes one select at a time: the other stays while the provider does
            model = body.model if body.model is not None else (own.model if kept else None)
            effort = body.effort if body.effort is not None else (own.effort if kept else None)
            if ref is not None:
                if session.status != "active":
                    raise AppError("busy", "That chat belongs to a run that is over. Its choice can no longer change.")
                choice = port.check_choice(body.provider, body.model, body.effort)      # an agent's calls are one-shot: only checked, no router session
                if body.effort is None and body.model is not None and effort is not None:
                    try:
                        port.check_choice(body.provider, model, effort)                  # the kept effort must suit the new model; if it does not, the model's default applies
                    except ConnectorError:
                        effort = None
            else:
                choice = port.choose(sid, body.provider, body.model, body.effort)       # refuses a provider that cannot run, an unknown model or effort (422 below)
            with db.tx() as tx:
                ChatChoices(db).set_pick(tx, sid, body.provider, model, effort)
                shown = effective(tx.conn, sid, _default_of(port))
                tx.emit("chat.choice", {"session_id": sid, "provider": shown["provider"], "model": shown["model"], "effort": shown["effort"],
                                        "source": shown["source"]})
            dept = ref.dept_id if ref is not None else (session.node_id if session.kind == "department" else None)
            if tasks is not None and dept is not None:
                tasks.refresh_choices(dept_id=dept)                # a live run's agents hear of it from their next call (D131)
            return choice, shown

        try:
            choice, shown = await run_blocking(run)
        except ConnectorError as exc:
            raise AppError("validation", exc.user_message()) from None
        return respond(request, {"session_id": sid, "provider": choice.provider, "model": choice.model, "effort": choice.effort,
                                 "source": shown["source"], "effective": shown})

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

    async def direct(request: Request, body: DirectIn, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        services = services_of(request)
        chats, port, attachments = _need(request, "chats"), _need(request, "chat_port"), _need(request, "attachments")
        session = await run_blocking(chats.session, sid)
        if session.status != "active":                    # a page that did not hear of the archive (another tab) is told the cause
            raise ReadOnly("This chat was archived. Open the team's current chat to write.")
        if not session.writable or session.kind not in ("org", "department", "division"):
            raise ReadOnly("This chat cannot be asked directly")
        if len(body.text) > MAX_CHARS:
            sentence = f"Messages can be up to {MAX_CHARS} characters; this one has {len(body.text)}."
            raise validation_error([violation("text", "string_too_long", sentence)], sentence)
        refs = []
        owner_names = list(body.names) if len(body.names) == len(body.attachments) else []          # the page sends one per file or none (as attached_line reads them)
        for n, ref_id in enumerate(body.attachments):
            path = attachments.get(ref_id)
            if path is None:
                raise NotFound("that attachment")
            # the model is told the owner's file name (cleaned), never the content hash the store keeps the file under
            named = clean_name(owner_names[n]) if owner_names else ""
            refs.append(AttachmentRef(id=ref_id, name=named or f"attachment-{n + 1}{path.suffix}", kind=_kind_of(path.name), size=path.stat().st_size))
        # DV-1: the Ask mode, only when the flag is on and the request named `ask` (a request without a mode never gets here, and the flag off never reads one)
        asking = ask_mode.begin(services, port, session, _clean(services, body.text), lambda value: _clean(services, value)) if ask_mode.requested(request) == "ask" else None
        if _live_on(services):
            return await _start_live(request, services, port, sid, said=_clean(services, body.text),
                                     attached=_clean(services, attached_line(list(body.names), [r.kind for r in refs])), refs=refs, client_id=body.client_id, ask=asking)
        if not direct_running.begin(sid):
            raise Busy("This chat is already answering")
        try:
            said = _clean(services, body.text)          # stored and sent without credential shapes: a secret never lands in the chat store
            attached = _clean(services, attached_line(list(body.names), [r.kind for r in refs]))
            message_id = await run_blocking(_store_user_line, services, sid, said, attached)
            direct_running.attach(sid, message_id)       # from here any page can read which line is being answered (GET /api/chats/{sid}: direct_turn)
            await run_blocking(_ground, services, port, sid, asking is not None)
        except BaseException:
            direct_running.end(sid)
            raise
        asyncio.get_running_loop().create_task(run_blocking(_answer, services, port, sid, message_id, ChatTurnIn(text=said, attachments=refs) if asking is None else asking.turn_in(said, refs), 1, asking))
        return RedactedJSONResponse(status_code=202, content={"message_id": message_id, "turn": "started"})

    @router.post("/chats/{sid}/direct/stop", summary="Stop the turn that is answering", dependencies=[Depends(require_token)])
    async def stop(request: Request, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        services = services_of(request)
        chats, port = _need(request, "chats"), _need(request, "chat_port")
        await run_blocking(chats.session, sid)
        if not _live_on(services):
            stopped = await run_blocking(port.stop, sid)
            return respond(request, {"session_id": sid, "stopped": bool(stopped)})
        return respond(request, _stop_live(port, sid))

    @router.get("/chats/{sid}/turn", summary="Where the live turn of this chat is")
    async def turn(request: Request, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        services = services_of(request)
        chats = _need(request, "chats")
        await run_blocking(chats.session, sid)
        live = direct_running.live_of(sid) if _live_on(services) else None
        if live is not None:
            return respond(request, await run_blocking(live.snapshot))
        return respond(request, await run_blocking(_last_turn, services, sid))

    async def retry(request: Request, body: RetryIn, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        services = services_of(request)
        chats, port = _need(request, "chats"), _need(request, "chat_port")
        session = await run_blocking(chats.session, sid)
        if not _live_on(services):
            raise NotFound("that route")
        if session.status != "active":
            raise ReadOnly("This chat was archived. Open the team's current chat to write.")
        if not session.writable or session.kind not in ("org", "department", "division"):
            raise ReadOnly("This chat cannot be asked directly")
        return await _retry_live(request, services, port, sid, body, session)

    # the two routes that take the Ask mode: the same routes as ever; `AskRoute` is inert while the flag is off (orchestrator/ask_mode.py)
    router.add_api_route("/chats/{sid}/direct", direct, methods=["POST"], summary="Ask the chat model directly", dependencies=[Depends(require_token)],
                         route_class_override=ask_mode.AskRoute)
    router.add_api_route("/chats/{sid}/direct/retry", retry, methods=["POST"], status_code=202, summary="Answer the owner's last line again",
                         dependencies=[Depends(require_token)], route_class_override=ask_mode.AskRoute)
    return router


def _kind_of(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return "pdf" if ext == "pdf" else "image" if ext in ("png", "jpg", "gif", "webp") else "text"


def _post(services: Any, sid: str, *, role: str, who: str, kind: str, text: str, blocks: list | None = None,
          src_ref: str | None = None) -> int | None:
    """The stored message's id, or None when a message with this `src_ref` is stored already (`ChatStore.post` refuses a repeated ref: a replayed line is
    not an error, and the caller looks the stored one up)."""
    redact = services.redact
    with services.db.tx() as tx:
        out = services.chats.post(tx, sid, GATE.check("chat_message", ChatMessage(
            kind=kind, session_id=sid, role=role, who=who, text=redact(text)[:200_000], blocks=blocks or [], src_ref=src_ref, at=tx.now()), ctx=tx.ctx))
    return None if out is None else out.id


def _clean(services: Any, text: str) -> str:
    """The app's secret values and the egress credential shapes replaced (connectors.egress), so the stored line, the line the model gets and
    any later carry-over are the same text."""
    return scan(services.redact(text), replace=True)[0]


def _post_all(services: Any, sid: str, endings: list[Ending], drop_generation: str | None = None) -> dict[str, int | None]:
    """The messages that end one turn, in ONE transaction: a page never reads half an ending. `drop_generation` is the live turn whose checkpoint is deleted in the same
    transaction (D211): the partial copy and the final reply are never both there, and never neither. -> the id stored for each `src_ref` (None for a replayed one)."""
    redact = services.redact
    ids: dict[str, int | None] = {}
    with services.db.tx() as tx:
        for e in endings:
            out = services.chats.post(tx, sid, GATE.check("chat_message", ChatMessage(
                kind=e.kind, session_id=sid, role="agent", who="sutra", text=redact(e.text)[:200_000], blocks=e.blocks, ordered=e.ordered, via=e.via,
                src_ref=e.src_ref, at=tx.now(), **({"card": e.card} if isinstance(e, direct_turns.CardEnding) else {})), ctx=tx.ctx))
            ids[e.src_ref] = None if out is None else out.id
        if drop_generation:
            live_checkpoint.drop(tx, drop_generation)
    return ids


def _store_user_line(services: Any, sid: str, text: str, attached: str = "", client_id: str | None = None) -> int:
    """The owner's line; with files, a last line records what went with it (the model gets the files and `text` itself). Its src_ref marks it as the
    start of a direct turn, so that a start after a crash can find the ones that never got an ending (`chat_v2.recover_interrupted`). The page's
    `client_id` is the tail of the ref when it sent one (D220): a replayed line is found again, never stored twice."""
    ref = DIRECT_ASK + (client_id or uuid.uuid4().hex[:16])
    stored = _post(services, sid, role="user", who="user", kind="text", text=text + ("\n" + attached if attached else ""), src_ref=ref)
    if stored is None:                                      # the ref was stored already: this is the same line
        found = find_owner_line(services.db.conn(), sid, client_id or "")
        if found is None:
            raise AppError("internal", "the owner's line could not be stored")
        return found
    return stored


def _ground(services: Any, port: Any, sid: str, ask: bool = False) -> None:
    """The session's system text for this turn: the node's own record and the rules (`orchestrator/chat_ground.py`), rebuilt every turn so it
    is current. A grounding that cannot be built or written is logged and the turn runs without a new one; it never fails the turn. `ask` (DV-1) adds the Ask mode's words."""
    try:
        port.set_system(sid, ground(services, sid, ask=True) if ask else ground(services, sid))
    except Exception:
        log.warning("could not ground the direct chat %s", sid, exc_info=True)


def _answer(services: Any, port: Any, sid: str, user_message_id: int, turn: ChatTurnIn, attempt: int = 1, ask: "ask_mode.AskTurn | None" = None) -> None:
    """The turn, on a worker thread: partials out as control events, the stored reply once at the end. A stop keeps what was written
    with a calm note; a failure keeps it with the real reason (direct_turns). `attempt` is the try of the owner's line (1; N for a retry): it names the refs
    the endings are stored under (D216)."""
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
            elif event.kind == "restart":                            # the router tried again: the earlier attempt's text is void, on the page and in the store
                seen_any = shown != ""
                buffered, shown = "", ""
                if seen_any and bus is not None:
                    bus.publish_one(PARTIAL, {"session_id": sid, "message_id": user_message_id, "delta": "", "reset": True})
            elif event.kind == "turn_done":
                done = event.data
        flush()
        if done is None:
            raise RuntimeError("the turn ended without a result")
        endings = finished(user_message_id, done, attempt)
        if ask is not None:                                          # DV-1: the card of the answer's sources, in the same transaction as the answer
            endings = ask.with_card(endings, user_message_id, attempt, str(done.get("text") or ""))
        _post_all(services, sid, endings)
    except Exception as exc:                                         # a failed turn is a message, not a lost line
        flush()
        log.warning("direct chat turn failed for %s: %s", sid, type(exc).__name__)
        if isinstance(exc, CallCancelledError):                      # the owner's Stop is not an error: what was written stays
            endings = stopped(user_message_id, shown, attempt)
        else:
            message = exc.user_message() if isinstance(exc, ConnectorError) else (exc.message if isinstance(exc, AppError) else "The model could not answer.")
            if isinstance(exc, ReplyTruncatedError):                 # the part that was written is kept above; say what the owner can do next
                message += " Ask for a shorter answer, or say \"continue\"."
            endings = failed(user_message_id, shown, message, attempt)
        try:
            _post_all(services, sid, endings)
        except Exception:
            log.exception("could not store the failed turn of %s", sid)
    finally:
        direct_running.end(sid)


# ---- the live turn (SUTRA_LIVE_V1, streaming design D201 to D222) ------------------------------------------------------------------------------------

def _live_on(services: Any) -> bool:
    return bool(getattr(getattr(services, "settings", None), "live_v1", False))


def _duplicate(sid: str, services: Any, client_id: str, message_id: int | None, running: bool) -> RedactedJSONResponse:
    """200 `{duplicate: true}` for a send whose `client_id` was already taken: nothing is started, the page matches the first send by `client_id`."""
    live = direct_running.live_of(sid) if running else None
    return RedactedJSONResponse(status_code=200, content={
        "duplicate": True, "turn": "started" if running else "done", "message_id": message_id, "client_id": client_id,
        "generation_id": live.generation_id if live is not None else None})


async def _start_live(request: Request, services: Any, port: Any, sid: str, *, said: str, attached: str, refs: list, client_id: str | None,
                      ask: "ask_mode.AskTurn | None" = None) -> RedactedJSONResponse:
    """One send as a live turn. The order matters (D220): look the `client_id` up, claim the chat (which also creates the stop token), store the owner's line, ground the chat,
    build and bind the live turn, publish `turn.accepted` (seq 1), and only then return the 202."""
    if client_id:
        found = await run_blocking(lambda: find_owner_line(services.db.conn(), sid, client_id))
        if found is not None:
            return _duplicate(sid, services, client_id, found, direct_running.answering(sid) and direct_running.client_of(sid) == client_id)
    claim = direct_running.begin_turn(sid, client_id)
    if isinstance(claim, direct_running.Busy):
        if client_id and claim.client_id == client_id:               # the same send, caught while its first request is still storing the line
            found = await run_blocking(lambda: find_owner_line(services.db.conn(), sid, client_id))
            return _duplicate(sid, services, client_id, found, True)
        raise Busy("This chat is already answering")
    generation = uuid.uuid4().hex
    live: LiveTurn | None = None
    try:
        message_id = await run_blocking(_store_user_line, services, sid, said, attached, client_id)
        direct_running.attach(sid, message_id)
        await run_blocking(_ground, services, port, sid, ask is not None)
        live = _new_live(services, sid, message_id, generation, client_id, 1, claim.token)
        direct_running.bind(sid, live)
        live.start()
        live.accepted()
        if claim.token.requested:                                      # a Stop that arrived while the line was being stored
            live.request_stop()
    except BaseException:
        if live is not None:
            live.close()
        direct_running.end(sid)
        raise
    turn = ChatTurnIn(text=said, attachments=refs) if ask is None else ask.turn_in(said, refs)
    asyncio.get_running_loop().create_task(run_blocking(_answer_live, services, port, sid, message_id, turn, live, 1, ask))
    return RedactedJSONResponse(status_code=202, content={"message_id": message_id, "turn": "started", "generation_id": generation, "attempt_no": 1,
                                                          "client_id": client_id or _client_of_line(services, sid, message_id)})


def _client_of_line(services: Any, sid: str, message_id: int) -> str | None:
    row = services.db.conn().execute("SELECT src_ref FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
    ref = row["src_ref"] if row is not None else ""
    return ref[len(DIRECT_ASK):] if ref.startswith(DIRECT_ASK) else None


def _new_live(services: Any, sid: str, message_id: int, generation: str, client_id: str | None, attempt_no: int, token: Any) -> LiveTurn:
    return LiveTurn(session_id=sid, message_id=message_id, generation_id=generation, client_id=client_id, attempt_no=attempt_no, token=token, bus=services.bus,
                    db=services.db, redact=services.redact, config=LiveConfig.from_settings(services.settings))


async def _retry_live(request: Request, services: Any, port: Any, sid: str, body: RetryIn, session: Any = None) -> RedactedJSONResponse:
    """Answer the owner's newest line again: the same owner line, a new generation, attempt-scoped refs (D216). Only a failed or stopped try can be retried."""
    def check() -> tuple[str, int]:
        conn = services.db.conn()
        row = conn.execute("SELECT id, role, text, src_ref FROM chat_messages WHERE id = ? AND session_id = ?", (body.message_id, sid)).fetchone()
        if row is None or row["role"] != "user" or not str(row["src_ref"] or "").startswith(DIRECT_ASK):
            raise NotFound("that line")
        if newest_owner_line(conn, sid) != body.message_id:
            raise AppError("not_retryable", "Only the last question of a chat can be answered again.")
        if last_outcome(conn, sid, body.message_id) == "done":
            raise AppError("not_retryable", "That question was answered. Ask it again as a new message.")
        return str(row["text"]), next_attempt(conn, sid, body.message_id)
    text, attempt = await run_blocking(check)
    said = re.sub(r"\n\(attached: [^\n]*\)$", "", text)          # the files of the first send cannot be sent again: the question can
    asking = ask_mode.begin(services, port, session, said, lambda value: _clean(services, value)) if ask_mode.requested(request) == "ask" else None     # DV-1: a retry names its mode again
    claim = direct_running.begin_turn(sid, body.client_id)
    if isinstance(claim, direct_running.Busy):
        raise Busy("This chat is already answering")
    generation = uuid.uuid4().hex
    live: LiveTurn | None = None
    try:
        if attempt > direct_turns.MAX_ATTEMPT:
            raise AppError("not_retryable", "That question was already answered again as often as the chat allows.")
        direct_running.attach(sid, body.message_id)
        await run_blocking(_ground, services, port, sid, asking is not None)
        live = _new_live(services, sid, body.message_id, generation, body.client_id, attempt, claim.token)
        direct_running.bind(sid, live)
        live.start()
        live.accepted()
        if claim.token.requested:
            live.request_stop()
    except BaseException:
        if live is not None:
            live.close()
        direct_running.end(sid)
        raise
    turn = ChatTurnIn(text=said) if asking is None else asking.turn_in(said, [])
    asyncio.get_running_loop().create_task(run_blocking(_answer_live, services, port, sid, body.message_id, turn, live, attempt, asking))
    return RedactedJSONResponse(status_code=202, content={"message_id": body.message_id, "turn": "started", "generation_id": generation, "attempt_no": attempt,
                                                          "client_id": body.client_id})


def _stop_live(port: Any, sid: str) -> dict[str, Any]:
    """Stop, as a live chat does it: say so to the live turn (it stops sending and freezes what was written), ask the process to end on a background task, and answer at once.
    `stopped: true` means a turn was running and Stop is now requested; `false` means none is (the page resyncs from the snapshot, it never decides by itself)."""
    live = direct_running.live_of(sid)
    token = direct_running.token_of(sid)
    running = direct_running.answering(sid)
    if live is not None:
        live.request_stop()
    elif token is not None:
        token.request()                                              # the turn is being set up: it stops before its process starts, and the live turn is frozen when it is built
    if running:
        task = asyncio.get_running_loop().create_task(run_blocking(port.stop, sid))      # the cancel ladder can take 12 s: never wait for it here
        _background.add(task)
        task.add_done_callback(_background.discard)
    return {"session_id": sid, "stopped": bool(running), "state": live.state if live is not None else ("stopping" if running else "none")}


def _last_turn(services: Any, sid: str) -> dict[str, Any]:
    """`{live: false}` and what the page needs to fetch the stored reply: the newest reply of a direct turn and which try it was."""
    row = services.db.conn().execute(
        "SELECT id, src_ref FROM chat_messages WHERE session_id = ? AND src_ref LIKE 'direct:%' ORDER BY id DESC LIMIT 1", (sid,)).fetchone()
    out: dict[str, Any] = {"live": False}
    if row is not None:
        ref = str(row["src_ref"])
        out["last_reply_id"] = int(row["id"])
        out["last_attempt_no"] = int(ref.rsplit(".", 1)[-1]) if "." in ref else 1
    return out


def _failure_text(exc: BaseException) -> str:
    message = exc.user_message() if isinstance(exc, ConnectorError) else (exc.message if isinstance(exc, AppError) else "The model could not answer.")
    if isinstance(exc, ReplyTruncatedError):                 # the part that was written is kept above; say what the owner can do next
        message += " Ask for a shorter answer, or say \"continue\"."
    return message


def _answer_live(services: Any, port: Any, sid: str, user_message_id: int, turn: ChatTurnIn, live: LiveTurn, attempt: int, ask: "ask_mode.AskTurn | None" = None) -> None:
    """The turn, on a worker thread, as a live turn: the port's events go to the live turn, which publishes them; the reply is stored once at the end, in one transaction with the
    deletion of its checkpoint, and only then does `turn.done` go out (so a page that hears it can fetch the stored message). A Stop keeps what was written (and the tools that
    ran, ended `interrupted`) with a calm note; a failure keeps it with the real reason. `live.close()` and `direct_running.end` run whatever happens."""
    try:
        done = None
        for event in port.stream(sid, turn, cancel=live.token, acc=live.acc):
            live.on_event(event)
            if event.kind == "turn_done":
                done = event.data
        if done is None:
            raise RuntimeError("the turn ended without a result")
        if live.stopping or (live.token is not None and live.token.requested):
            # Stop won, even though the provider still returned a result (it had already finished when the cancel ladder ran): every tab saw the text freeze, so the stored
            # ending is the stopped one, built from what was shown, never the provider's full text
            raise CallCancelledError("stopped")
        stored = {**done, "blocks": done.get("blocks_ordered") or done.get("blocks") or []}
        plain = "".join(str(b.get("text") or "") for b in stored["blocks"] if isinstance(b, dict) and b.get("type") == "text")
        if str(done.get("text") or "") == plain and plain:            # the provider's text is the blocks' text run together: store it as the page draws it, paragraphs apart
            stored["text"] = join_text((b.get("type") == "text", str(b.get("text") or "")) for b in stored["blocks"] if isinstance(b, dict))
        endings = finished(user_message_id, stored, attempt, ordered=True, earlier=done.get("earlier"), via=live.via())
        if ask is not None:                                          # DV-1: the card of the answer's sources, in the same transaction as the answer
            endings = ask.with_card(endings, user_message_id, attempt, str(stored["text"]))
        ids = _post_all(services, sid, endings, drop_generation=live.generation_id)
        live.finish(ids.get(direct_turns.ref_of(user_message_id, "", attempt)) or 0, {**done, "text": stored["text"]})
    except Exception as exc:                                         # a failed turn is a message, not a lost line
        log.warning("live direct chat turn failed for %s: %s", sid, type(exc).__name__)
        try:
            if isinstance(exc, CallCancelledError):                  # the owner's Stop is not an error: what was written stays
                live.request_stop()
            live.settle_blocks("interrupted")
            shown, blocks, earlier = live.shown_text(), live.acc.stored_blocks(ordered=True), live.earlier_tries()
            if isinstance(exc, CallCancelledError):
                endings = stopped(user_message_id, shown, attempt, blocks=blocks, ordered=True, earlier=earlier, via=live.via())
            else:
                endings = failed(user_message_id, shown, _failure_text(exc), attempt, blocks=blocks, ordered=True, earlier=earlier, via=live.via())
            ids = _post_all(services, sid, endings, drop_generation=live.generation_id)
            reply = ids.get(direct_turns.ref_of(user_message_id, "", attempt)) or 0
            if isinstance(exc, CallCancelledError):
                live.stopped(reply)
            else:
                live.failed(_failure_text(exc), getattr(exc, "code", "failed") if isinstance(exc, ConnectorError) else "failed", reply)
        except Exception:
            log.exception("could not store the failed turn of %s", sid)
    finally:
        direct_running.end(sid)          # first: the reply is stored and the end sent, so the chat is free now; closing joins threads and can wait on a slow checkpoint write
        live.close()


router = build_router()
