"""`handoff.json`: what a node leaves for the server when its run ended well (multi-agent nodes, D263, D265, D281; MAN-6).

    build(run_dir, node_id, status, outcome) -> dict        the document, `handoff/1`
    write(run_dir, document)                                 `<run folder>/handoff.json`, mode 0600, by temp file and rename

The host writes it from `finish.run_steps` (the step `handoff`), only when `task.json` has a `node` block, and only for a run that ended `done` or `done_with_open_items`: a stopped or
crashed run leaves none. The server (the Conductor's intake, `projects.py`) reads, checks and scrubs it; the node's words are DATA from here on and decide nothing:

    {"v": 1, "node_id": "nd_...", "status": "done" | "done_with_open_items" | "blocked",
     "summary": "<= 2000 characters, plain text",
     "files": [{"path": "relative/name", "sha256": "<64 hex>", "bytes": 1234}],           at most 200
     "claims": ["<= 200 characters"],                                                     at most 20
     "needs": [{"tier": 3, "why": "<= 200 characters"}]}                                  light nodes only: always empty here

The files come from the run folder itself (its top-level regular files, with their checksums), not from anything an agent said; `claims` is empty for an engine node, and `needs` too.
The summary is the run's own outcome sentence (what the owner reads on the done card). Nothing here fails a run: the caller traces an error and goes on.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any

from sutra_app import oslayer
from sutra_app.library.types import clip

__all__ = ["build", "write", "HANDOFF_FILE", "ACCEPTED_FILE", "SCHEMA_V", "MAX_FILES", "MAX_SUMMARY", "MAX_CLAIMS", "MAX_CLAIM", "MAX_BYTES", "NOT_HANDED_ON"]

HANDOFF_FILE = "handoff.json"
ACCEPTED_FILE = "handoff.accepted.json"          # written by the SERVER after it checked and scrubbed the hand-off: the one file of a node's run that dependants are given
SCHEMA_V = 1
MAX_FILES = 200
MAX_SUMMARY = 2000
MAX_CLAIMS = 20
MAX_CLAIM = 200
MAX_BYTES = 64 * 1024                            # the largest hand-off file the server reads
# the run folder's own plumbing and the hand-off files themselves are never part of what is handed on; `orchestrator.tasks.RUN_FOLDER_INTERNALS` is a subset (a test keeps them in step)
NOT_HANDED_ON = frozenset({
    "task.json", "inbox.jsonl", "events.jsonl", "trace.jsonl", "snapshot.json", "live.json", "settings.json", "run.stdout.log", "run.stderr.log", "choices.json", "agent_live.json",
    "deliverable.json", HANDOFF_FILE, ACCEPTED_FILE, "verdict.json", "needs.json", "chat.jsonl", "calls.jsonl", "summary.json", "status.json", "node_context.json",
})


def _digest(path: Path) -> tuple[str, int]:
    sha = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
            size += len(block)
    return sha.hexdigest(), size


def build(run_dir: str | os.PathLike[str], node_id: str, status: str, outcome: str, internals: frozenset[str] = NOT_HANDED_ON) -> dict[str, Any]:
    """The `handoff/1` document of the run in `run_dir`. `status` is the run's end (`done` or `done_with_open_items`). Files: the top-level regular files of the run folder (no link, no hidden
    name, none of the plumbing), at most 200, in name order, each with its sha256 and size."""
    root = Path(run_dir)
    files: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if len(files) >= MAX_FILES:
            break
        if entry.name in internals or entry.name.startswith(".") or entry.is_symlink() or not entry.is_file():
            continue
        try:
            sha, size = _digest(entry)
        except OSError:
            continue
        files.append({"path": entry.name, "sha256": sha, "bytes": size})
    return {"v": SCHEMA_V, "node_id": node_id, "status": status if status in ("done", "done_with_open_items") else "blocked",
            "summary": " ".join(str(outcome or "").split())[:MAX_SUMMARY] or "The run ended.", "files": files, "claims": [], "needs": []}


def write(run_dir: str | os.PathLike[str], document: dict[str, Any]) -> Path:
    """`<run folder>/handoff.json` by temp file and rename, mode 0600."""
    target = Path(run_dir) / HANDOFF_FILE
    temp = target.with_name(f".{HANDOFF_FILE}.{os.getpid()}.{secrets.token_hex(4)}.tmp")      # a name nobody else has, made with O_EXCL: a planted link or file under the old fixed name is never followed (Minor 4)
    fd = os.open(temp, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        oslayer.replace(temp, target)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
    return target


def _clip_for_trace(text: str) -> str:
    return clip(text, 200)
