"""What a run is given about files, instructions and earlier work (D451, T5).

    given = given_for(db, store, conn, dept_id, attached=[{id, name, kind, size, chars}], scrub=...)     # at a run's start, inside the transaction that makes its folder
    given.block                      # the composed project block and request digest (text for the system addendum, parts for the receipt)
    given.inputs                     # [InputFile]: the files to copy, the request's own under `attached`, the project's enabled ones under `knowledge`
    given.pointer                    # the short line the run's framing carries
    materialize(run_dir, inputs, store)                  # copies them into `<run>/inputs/<where>/`, 0600, before the engine process exists (raises `InputsError` naming the file)
    snapshot_of(refs, store)                             # what a send stores on its task: [{id, name, kind, size, chars}], each file looked up in the store (404 for one that is gone)
    write_context(run_dir, text)                         # `<run>/node_context.json` = {"*": text}: the engine host appends it to the system prompt of EVERY agent call (T2: the framing alone
                                                         # never reaches a builder in a real run)

The project's files are never written into the project's folder and never exported (FR-12, D428): they live under the run's own `inputs/`, which the export rules treat as a record folder.
Delivery is neutralised by `SUTRA_PROJECT_CONTEXT=0` for the project's part only; a file the owner sent with a request is always delivered (it is an explicit act, G4).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sutra_app import oslayer
from sutra_app.connectors import attachments as _attachments
from sutra_app.connectors.attachments import AttachmentStore, clean_name
from sutra_app.orchestrator import project_context as ctx
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.errors import NotFound
from sutra_app.orchestrator.models import InputFile
from sutra_app.orchestrator.owner_words import json_meta
from sutra_app.orchestrator.project_files import ProjectFiles, kind_of_path
from sutra_app.orchestrator.project_memory import INSTRUCTIONS_KEY, ProjectMemory

__all__ = ["Given", "InputsError", "given_for", "materialize", "snapshot_of", "write_context", "unique_names", "CONTEXT_FILE", "MAX_REQUEST_FILES"]

log = logging.getLogger(__name__)
CONTEXT_FILE = "node_context.json"
MAX_REQUEST_FILES = 10


class InputsError(Exception):
    """A file could not be put in the run folder. The message names the file: it is what the owner reads after "could not start:"."""


@dataclass
class Given:
    block: ctx.Block = field(default_factory=ctx.Block)
    inputs: list[InputFile] = field(default_factory=list)
    pointer: str = ""


def unique_names(names: Sequence[str]) -> list[str]:
    """The same names, each made unique inside one folder by ` (2)`, ` (3)` before the extension; the order is kept."""
    taken: set[str] = set()
    out = []
    for name in names:
        final, n = name, 2
        while final.lower() in taken:
            stem, dot, ext = name.rpartition(".")
            final = f"{stem[:70]} ({n}).{ext}" if dot and stem else f"{name[:70]} ({n})"
            n += 1
        taken.add(final.lower())
        out.append(final)
    return out


def snapshot_of(refs: Sequence[dict], store: AttachmentStore) -> list[dict]:
    """What a send keeps on its task for each file it carries: [{id, name, kind, size, chars}] in order. A file that is not in the store is a 404 `not_found` naming nothing else (the page
    says "attach it again"); more than MAX_REQUEST_FILES is refused by the caller's shape check."""
    out = []
    for ref in refs:
        path = store.path_of(str(ref.get("id") or ""))
        if path is None:
            raise NotFound("that attachment")
        kind = kind_of_path(path)
        chars = 0
        if kind == "text":
            try:
                chars = len(_attachments._text_of(path, str(ref.get("name") or "the file")))
            except Exception:                                                  # noqa: BLE001
                raise NotFound("that attachment") from None
        out.append({"id": str(ref["id"]), "name": clean_name(ref.get("name") or "") or path.name[:80], "kind": kind, "size": path.stat().st_size, "chars": chars})
    names = unique_names([o["name"] for o in out])
    return [{**o, "name": n} for o, n in zip(out, names)]


def _kfile(name: str, kind: str, size: int, text: str) -> ctx.KFile:
    return ctx.KFile(name=name, kind=kind, size=size, text=text)


def _read(store: AttachmentStore, sha: str, name: str, kind: str) -> str:
    """The text of a stored text file, "" for anything else or a file that cannot be read now (the copy at the start names it)."""
    if kind != "text":
        return ""
    path = store.path_of(sha)
    if path is None:
        return ""
    try:
        return _attachments._text_of(path, name)
    except Exception:                                                          # noqa: BLE001
        return ""


def given_for(db: Database, store: AttachmentStore, conn: sqlite3.Connection, dept_id: str, attached: Sequence[dict], scrub: Callable[[str], str] | None = None) -> Given:
    """The project's block and the request's own files for a run of `dept_id`, read now. Nothing at all (an empty `Given`) for a run with no file, no instructions and nothing remembered:
    its prompts, `task.json` and folder are what they were."""
    off = ctx.switched_off()
    files = ProjectFiles(db, store)
    rows = [] if off else files.enabled(dept_id)
    instructions = "" if off else str(json_meta(conn, INSTRUCTIONS_KEY.format(dept_id)).get("text") or "")
    memory: list[str] = []
    if not off:
        try:
            memory = ProjectMemory.texts_of(ProjectMemory(db).read_in(conn, dept_id), ctx.RUN_MEMORY_CHARS)
        except Exception:                                                      # noqa: BLE001  (a memory that cannot be read must never keep a team from starting)
            log.exception("the memory of %s could not be read for a run", dept_id)
    knowledge = [_kfile(r.name, r.kind, r.size, _read(store, r.sha, r.name, r.kind)) for r in rows]
    came = [_kfile(a["name"], a["kind"], a["size"], _read(store, a["id"], a["name"], a["kind"])) for a in attached]
    if not (knowledge or came or instructions.strip() or memory):
        return Given()
    block = ctx.compose_run_block(instructions=instructions, memory=memory, files=knowledge, attached=came, scrub=scrub)
    inputs = [InputFile(id=r.sha, name=r.name, kind=r.kind, size=r.size, chars=r.chars, where="knowledge") for r in rows]       # type: ignore[arg-type]
    inputs += [InputFile(id=a["id"], name=a["name"], kind=a["kind"], size=a["size"], chars=a.get("chars", 0), where="attached") for a in attached]    # type: ignore[arg-type]
    return Given(block=block, inputs=inputs, pointer=ctx.run_pointer(knowledge, came))


def _copy(src: Path, dst: Path) -> None:
    fd = os.open(dst, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out, open(src, "rb") as source:
        shutil.copyfileobj(source, out)


def materialize(run_dir: Path, inputs: Sequence[InputFile], store: AttachmentStore) -> None:
    """Copy each file into `<run_dir>/inputs/<where>/<name>` (the folder 0700, each file 0600) and, for a Word file, its text beside it as `<name>.txt`. A file that is gone, a link, or a name that would
    leave the folder raises `InputsError` naming the file, and whatever was made is removed: a run never starts with a file silently missing."""
    if not inputs:
        return
    root = Path(run_dir) / "inputs"
    try:
        for f in inputs:
            folder = root / f.where
            os.makedirs(folder, mode=0o700, exist_ok=True)
            src = store.path_of(f.id)
            name = clean_name(f.name)
            if src is None or src.is_symlink() or not name or name != f.name:
                raise InputsError(f"{f.name} could not be copied")
            dst = folder / name
            if dst.parent.resolve() != folder.resolve():
                raise InputsError(f"{f.name} could not be copied")
            try:
                _copy(src, dst)
                if f.kind == "text" and src.suffix.lower() == ".docx":
                    text = _attachments._text_of(src, f.name)
                    fd = os.open(folder / (name + ".txt"), os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "wb") as out:
                        out.write(text.encode("utf-8"))
            except InputsError:
                raise
            except Exception as exc:                                           # noqa: BLE001  (disk full, a vanished file, a bad Word file: all one sentence naming the file)
                raise InputsError(f"{f.name} could not be copied") from exc
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise


def write_context(run_dir: Path, text: str) -> None:
    """`<run>/node_context.json` = {"*": text} (0600, by temp file and rename). The engine host's `system_addendum` appends the "*" entry, under its own heading, to every agent call."""
    path = Path(run_dir) / CONTEXT_FILE
    tmp = path.with_name(f".{CONTEXT_FILE}.{uuid.uuid4().hex[:8]}.tmp")
    fd = os.open(tmp, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"*": text}, ensure_ascii=False, indent=2) + "\n")
        oslayer.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
