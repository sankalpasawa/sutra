"""The chats of the agents (agent-sessions design 3.6, D130 to D132). Reads need no token; writes do (D81).

    GET  /api/teams/{dept}/agents?run=<run_id>   -> [{agent, label, kind: function|step, title, session_id, node_id, run_id, task_id, state, live, status, own,
                                                       run_pick, effective: {provider, model, effort, source}, usage: {calls, usd, tokens_in, tokens_out}, last_at}]
                                                    the team's five active function sessions plus every session stamped with `run` (builders, and the function
                                                    sessions a later run rolled); `run` defaults to the live run, else the latest (404 for a run of another team)

    POST /api/chats/{sid}/steer {text <= 2000}   -> {message_id, session_id, applies: "next_call"}   (token; only a function or step chat of a live run, else 409
                                                    `not_running`; the line is stored in the agent's session of this run with the marker `steer`, and the agent's entry of
                                                    <run>/node_context.json is rewritten, so the engine appends it to the agent's system prompt from its NEXT call)

The router reads `services.db`, `services.tasks` and, for the policy default of an agent, `services.chat_port` (a stand-in without one knows no default).
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path as FsPath
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import StringConstraints

from sutra_app import oslayer
from sutra_app.connectors.base import write_private_file
from sutra_app.connectors.egress import scan
from sutra_app.library.base import Value
from sutra_app.library.gate import GATE
from sutra_app.orchestrator.agent_sessions import CONTEXT_FILE, NOTE_CHARS, agent_of, compose_notes, team_agents
from sutra_app.orchestrator.api.chat import ID_PATTERN, respond
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.chats import STEER_REF
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.records import ChatMessage

__all__ = ["router", "build_router", "SteerIn"]


class SteerIn(Value):
    # the model bounds what could be stored; the cap of NOTE_CHARS is checked in the route, so that the refusal can say what it is
    text: Annotated[str, StringConstraints(min_length=1, max_length=20_000)]


def _need(request: Request, name: str):
    found = getattr(services_of(request), name, None)
    if found is None:
        raise AppError("internal", f"the {name} is not wired")
    return found


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["agent chats"])

    @router.get("/teams/{dept}/agents", summary="The chats of a team's agents for one run")
    async def agents(request: Request, dept: str = Path(pattern=ID_PATTERN), run: str | None = Query(None, pattern=ID_PATTERN)) -> RedactedJSONResponse:
        db, tasks = _need(request, "db"), _need(request, "tasks")
        port = getattr(services_of(request), "chat_port", None)
        default = getattr(port, "default_pick", None)
        found = await run_blocking(lambda: team_agents(db.conn(), tasks.store, dept, run, default if callable(default) else None))
        return respond(request, found)

    @router.post("/chats/{sid}/steer", summary="Write a note to an agent, read at its next call", dependencies=[Depends(require_token)])
    async def steer(request: Request, body: SteerIn, sid: str = Path(pattern=ID_PATTERN)) -> RedactedJSONResponse:
        services = services_of(request)
        db, tasks, chats = _need(request, "db"), _need(request, "tasks"), _need(request, "chats")
        text = body.text.strip()
        if not text:
            raise AppError("validation", "The note is empty.")
        if len(text) > NOTE_CHARS:
            raise AppError("validation", f"A note can be up to {NOTE_CHARS} characters; this one has {len(text)}.")
        text = scan(services.redact(text), replace=True)[0]            # a secret never lands in the chat store or in the agent's prompt

        def run() -> dict[str, Any]:
            with db.tx() as tx:
                conn = tx.conn
                ref = agent_of(conn, sid)
                if ref is None:
                    if conn.execute("SELECT 1 FROM chat_sessions WHERE id = ?", (sid,)).fetchone() is None:
                        raise AppError("not_found", "that chat was not found")
                    raise AppError("rules", "Only an agent's chat takes a note.")
                row = tasks.store.row_in(conn, ref.task_id) if ref.kind == "step" and ref.task_id else tasks.store.live_in(conn, ref.dept_id or "")
                if ref.status != "active" or row is None or not row.live or row.run_id is None:
                    raise AppError("not_running", "That run is over, so the agent can no longer read a note.")
                session_id = tasks.taskgraph.sessions.open(tx, row, ref.node_id) or sid          # a function agent's session of an earlier run rolls now, so the note lands in this run's
                posted = chats.post(tx, session_id, GATE.check("chat_message", ChatMessage(
                    kind="text", session_id=session_id, role="user", who="user", text=text, src_ref=f"{STEER_REF}{uuid.uuid4().hex[:16]}",
                    task_id=row.id, at=tx.now()), ctx=tx.ctx))
                _write_note(tasks.store.run_dir_of(row) / CONTEXT_FILE, ref.agent, text)
                return {"message_id": posted.id, "session_id": session_id, "applies": "next_call"}

        return respond(request, await run_blocking(run))

    return router


def _write_note(path: FsPath, agent: str, note: str) -> None:
    """Add the note to `<run>/node_context.json[agent]` (atomic, 0600). The engine re-reads the file on every call; the other agents' entries stay."""
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
        body = dict(body) if isinstance(body, dict) else {}
    except (OSError, ValueError):
        body = {}
    old = body.get(agent)
    body[agent] = compose_notes(old if isinstance(old, str) else "", note)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        write_private_file(tmp, json.dumps(body, ensure_ascii=False, indent=2) + "\n")
        oslayer.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


router = build_router()
