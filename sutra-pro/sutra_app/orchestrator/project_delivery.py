"""What a project's rows become for a model (D451): the one place that reads a project's files, instructions and memory and composes them, for a direct chat and for the preview.

    chat_block(db, store, redact, clock, dept_id, message)    -> ChatBlock | None   the stable system text and this message's excerpts (None: nothing to say, or SUTRA_PROJECT_CONTEXT=0)
    preview(db, store, redact, clock, dept_id, message)       -> dict               the exact text a chat and a run would be given now, with sizes and sources (GET /api/teams/{dept}/context)

A run's own delivery is `run_inputs.given_for` (it needs the open transaction of the run's start); the preview calls it too, so the owner reads what a run would get. Reading never raises for a
file that cannot be read: it is left out and the preview says so.
"""
from __future__ import annotations

from typing import Any, Callable

from sutra_app.connectors.egress import scan
from sutra_app.orchestrator import project_context as ctx
from sutra_app.orchestrator.owner_words import json_meta
from sutra_app.orchestrator.project_files import ProjectFiles
from sutra_app.orchestrator.project_memory import INSTRUCTIONS_KEY, ProjectMemory

__all__ = ["chat_block", "preview"]


def _scrub(redact: Callable[[str], str] | None) -> Callable[[str], str]:
    return lambda text: scan(redact(text) if redact is not None else text, replace=True)[0]


def chat_block(db: Any, store: Any, redact: Callable[[str], str] | None, clock: Any, dept_id: str, message: str) -> "ctx.ChatBlock | None":
    if ctx.switched_off():
        return None
    pf = ProjectFiles(db, store)
    files = [ctx.KFile(name=r.name, kind=r.kind, size=r.size, text=pf.text_of(r)) for r in pf.enabled(dept_id)]
    memory = ProjectMemory(db, redact, clock=clock).deliverable(dept_id, ctx.CHAT_MEMORY_CHARS)
    instructions = str(json_meta(db.conn(), INSTRUCTIONS_KEY.format(dept_id)).get("text") or "")
    block = ctx.compose_chat_block(instructions=instructions, memory=memory, files=files, message=message, scrub=_scrub(redact))
    return block if block.stable or block.context else None


def preview(db: Any, store: Any, redact: Callable[[str], str] | None, clock: Any, dept_id: str, message: str = "") -> dict:
    """The exact text a direct chat and a run of the project would be given now. `chat_stable` is the project block in the system text, `chat_context` this message's excerpts (only when the
    files are too long to paste whole), `run_block` what a run's agents are told. Nothing is sent by asking."""
    from sutra_app.orchestrator.run_inputs import given_for
    off = ctx.switched_off()
    block = chat_block(db, store, redact, clock, dept_id, message)
    conn = db.conn()
    given = given_for(db, store, conn, dept_id, [], scrub=_scrub(redact)) if not conn.in_transaction else None
    pm = ProjectMemory(db, redact, clock=clock)
    files = ProjectFiles(db, store).list(dept_id)
    return {"off": off, "mode": block.mode if block is not None else "none", "sig": block.sig if block is not None else "",
            "chat_stable": block.stable if block is not None else "", "chat_context": block.context if block is not None else "",
            "run_block": given.block.text if given is not None else "", "parts": ctx.receipt(block) if block is not None else [],
            "files_used": [f.name for f in files.files if f.enabled], "files_total": len(files.files), "memory_on": pm.memory(dept_id).enabled,
            "sizes": {"chat_stable": len(block.stable) if block is not None else 0, "chat_context": len(block.context) if block is not None else 0,
                      "run_block": len(given.block.text) if given is not None else 0}}
