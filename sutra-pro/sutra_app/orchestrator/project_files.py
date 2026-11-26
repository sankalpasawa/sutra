"""The files of a project (D451): which stored files belong to which project, and their flags.

    files = ProjectFiles(db, AttachmentStore(data_dir), clock=..., limits=Limits())
    files.add("web", ref)                          # an `AttachmentRef` from the store -> FileOut (`already` when the same content is there); refused over a limit, in a sentence
    files.promote("web", attachment_id, name)      # a file stored for one chat or one request becomes a project file (the owner's act: "Add to project")
    files.list("web") / files.enabled("web")       # FilesOut (files, totals, mode, limits) / the rows a run or a turn is given
    files.patch("web", fid, enabled=, name=) / files.remove("web", fid) / files.remove_all("web")
    files.text_of(row)                             # the text of one file, read when a run or a turn needs it (the characters were counted once, at add)

The BYTES stay in the D440 store (`<data>/attachments/<sha256>.<ext>`, 0600, deduped); `project_files` (schema v10) is the list. A remove is soft (`removed_at`) so the row can be audited, and the
bytes go only when nothing else names them: another project's live row, a task's snapshot (`tasks.input_files_json`) or a chat line's files (`chat_messages.meta_json`). A deleted (hidden) project
keeps its files but takes no change (ReadOnly, D426). Writes use the one write transaction; the partial unique index (dept, sha) makes two adds of one file one row.
"""
from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from sutra_app.connectors import attachments as _attachments
from sutra_app.connectors.attachments import AttachmentStore, clean_name
from sutra_app.connectors.chat_models import AttachmentRef
from sutra_app.library.types import violation
from sutra_app.orchestrator import project_context as ctx
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.errors import NotFound, ReadOnly, validation_error
from sutra_app.orchestrator.ids import iso_z

__all__ = ["ProjectFiles", "Limits", "FileOut", "FilesOut", "FileRow", "LimitsOut", "TotalsOut", "kind_of_path"]

log = logging.getLogger(__name__)
_COLUMNS = "id, dept_id, sha, name, kind, size, chars, enabled, added_at"


@dataclass(frozen=True)
class Limits:
    max_files: int = ctx.MAX_FILES
    max_bytes: int = ctx.MAX_BYTES
    max_chars: int = ctx.MAX_TEXT_CHARS
    instructions_chars: int = ctx.INSTRUCTIONS_MAX


class LimitsOut(BaseModel):
    max_files: int
    max_bytes: int
    max_chars: int
    instructions_chars: int
    memory_entries: int = ctx.MEMORY_ENTRIES
    entry_chars: int = ctx.ENTRY_CHARS
    whole_chars: int = ctx.WHOLE_CHARS
    chat_block_chars: int = ctx.CHAT_BLOCK_CHARS
    run_block_chars: int = ctx.RUN_BLOCK_CHARS
    attached_chars: int = ctx.ATTACHED_CHARS


class FileOut(BaseModel):
    id: str
    name: str
    kind: str
    size: int
    chars: int
    enabled: bool
    added_at: str
    reference_only: bool
    already: bool = False


class TotalsOut(BaseModel):
    files: int
    bytes: int
    chars: int


class FilesOut(BaseModel):
    files: list[FileOut]
    totals: TotalsOut
    mode: str                        # "whole" | "excerpts" | "none": how the enabled files reach a chat (FR-10)
    limits: LimitsOut


@dataclass(frozen=True)
class FileRow:
    id: str
    dept_id: str
    sha: str
    name: str
    kind: str
    size: int
    chars: int
    enabled: bool
    added_at: int


def kind_of_path(path: Path) -> str:
    """The kind of a stored file from its name (the store names a file `<sha><ext>` by what its bytes are): pdf, image or text."""
    ext = path.suffix.lower()
    return "pdf" if ext == ".pdf" else "image" if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp") else "text"


def _human(size: int) -> str:
    return f"{size} bytes" if size < 1024 else f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size // (1024 * 1024)} MB"


def _row_of(r: Any) -> FileRow:
    return FileRow(id=r["id"], dept_id=r["dept_id"], sha=r["sha"], name=r["name"], kind=r["kind"], size=r["size"], chars=r["chars"], enabled=bool(r["enabled"]), added_at=r["added_at"])


def _out(row: FileRow, already: bool = False) -> FileOut:
    return FileOut(id=row.id, name=row.name, kind=row.kind, size=row.size, chars=row.chars, enabled=row.enabled, added_at=iso_z(row.added_at), reference_only=row.kind != "text", already=already)


class ProjectFiles:
    def __init__(self, db: Database, store: AttachmentStore, *, clock: Any = None, limits: Limits | None = None) -> None:
        self.db = db
        self.store = store
        self.clock = clock
        self.limits = limits or Limits()

    # ---- reads -----------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def _team(conn: Any, dept_id: str) -> Any:
        found = conn.execute("SELECT d.hidden_at FROM departments d JOIN org_nodes o ON o.id = d.id WHERE d.id = ? AND o.state = 'active'", (dept_id,)).fetchone()
        if found is None:
            raise NotFound("that project")
        return found

    def _writable(self, conn: Any, dept_id: str) -> None:
        if self._team(conn, dept_id)["hidden_at"] is not None:
            raise ReadOnly("This project was deleted.")

    def _live(self, conn: Any, dept_id: str) -> list[FileRow]:
        return [_row_of(r) for r in conn.execute(f"SELECT {_COLUMNS} FROM project_files WHERE dept_id = ? AND removed_at IS NULL ORDER BY added_at, rowid", (dept_id,))]

    def list(self, dept_id: str) -> FilesOut:
        conn = self.db.conn()
        self._team(conn, dept_id)
        rows = self._live(conn, dept_id)
        used = [r for r in rows if r.enabled and r.kind == "text"]
        total = sum(r.chars for r in used)
        mode = "none" if not [r for r in rows if r.enabled] else "whole" if total <= ctx.WHOLE_CHARS else "excerpts"
        return FilesOut(files=[_out(r) for r in rows], totals=TotalsOut(files=len(rows), bytes=sum(r.size for r in rows), chars=sum(r.chars for r in rows)), mode=mode,
                        limits=LimitsOut(max_files=self.limits.max_files, max_bytes=self.limits.max_bytes, max_chars=self.limits.max_chars, instructions_chars=self.limits.instructions_chars))

    def enabled(self, dept_id: str) -> list[FileRow]:
        """The files a run and a chat of the project are given, in the order they were added. [] for a team that is gone (a delivery never fails for it)."""
        try:
            conn = self.db.conn()
            return [r for r in self._live(conn, dept_id) if r.enabled]
        except Exception:                                                  # noqa: BLE001  (a project's files must never keep a team from starting or answering)
            log.exception("the files of %s could not be read", dept_id)
            return []

    def text_of(self, row: FileRow) -> str:
        """The text of a text file, read from the store now; "" for an image, a PDF, or a file that is gone or cannot be read."""
        if row.kind != "text":
            return ""
        path = self.store.path_of(row.sha)
        if path is None:
            return ""
        try:
            return _attachments._text_of(path, row.name)
        except Exception:                                                  # noqa: BLE001
            log.warning("a project file could not be read: %s", row.name)
            return ""

    # ---- writes ----------------------------------------------------------------------------------------------------------------------

    def add(self, dept_id: str, ref: AttachmentRef, *, name: str | None = None) -> FileOut:
        """Keep a stored file with the project. The same content twice is one row (`already`). Over a limit is a 422 in one sentence, and nothing is kept."""
        path = self.store.path_of(ref.id)
        if path is None:
            raise NotFound("that file")
        shown = clean_name(name or ref.name) or "file"
        conn = self.db.conn()
        self._writable(conn, dept_id)
        same = conn.execute(f"SELECT {_COLUMNS} FROM project_files WHERE dept_id = ? AND sha = ? AND removed_at IS NULL", (dept_id, ref.id)).fetchone()
        if same is not None:
            return _out(_row_of(same), already=True)
        kind = ref.kind if ref.kind in ("text", "image", "pdf") else kind_of_path(path)
        size = path.stat().st_size
        chars = 0
        if kind == "text":
            try:
                chars = len(_attachments._text_of(path, shown))               # read ONCE, here: a run or a turn never re-extracts to count (NFR-5)
            except Exception:                                                  # noqa: BLE001
                raise validation_error([violation("file", "unreadable", f"{shown} could not be read")], f"{shown} could not be read") from None
        with self.db.tx() as tx:
            self._writable(tx.conn, dept_id)
            same = tx.conn.execute(f"SELECT {_COLUMNS} FROM project_files WHERE dept_id = ? AND sha = ? AND removed_at IS NULL", (dept_id, ref.id)).fetchone()
            if same is not None:                                               # another thread won the race: one row
                return _out(_row_of(same), already=True)
            rows = self._live(tx.conn, dept_id)
            self._check(rows, size, chars)
            taken = {r.name.lower() for r in rows}
            final = shown
            n = 2
            while final.lower() in taken:
                stem, dot, ext = shown.rpartition(".")
                final = (f"{stem[:70]} ({n}).{ext}" if dot and stem else f"{shown[:70]} ({n})")
                n += 1
            row_id = "pf_" + secrets.token_hex(6)
            now = tx.now()
            tx.conn.execute("INSERT INTO project_files(id, dept_id, sha, name, kind, size, chars, enabled, added_at) VALUES (?,?,?,?,?,?,?,1,?)", (row_id, dept_id, ref.id, final, kind, size, chars, now))
            return _out(FileRow(row_id, dept_id, ref.id, final, kind, size, chars, True, now))

    def _check(self, rows: list[FileRow], size: int, chars: int) -> None:
        said = None
        if len(rows) >= self.limits.max_files:
            said = f"This project holds {self.limits.max_files} files. Remove one to add another."
        elif sum(r.size for r in rows) + size > self.limits.max_bytes:
            said = f"This project is at its size limit ({_human(self.limits.max_bytes)} of files). Remove a file to add another."
        elif sum(r.chars for r in rows) + chars > self.limits.max_chars:
            said = f"This project is at its text limit ({self.limits.max_chars:,} characters of text in all). Remove a file to add another."
        if said:
            raise validation_error([violation("file", "project_limit", said)], said)

    def promote(self, dept_id: str, attachment_id: str, name: str | None = None) -> FileOut:
        """A file that is stored already (one a chat or a request carried) becomes a project file: the owner's explicit act."""
        path = self.store.path_of(attachment_id)
        if path is None:
            raise NotFound("that file")
        ref = AttachmentRef(id=attachment_id, name=clean_name(name or "") or path.name[:80], kind=kind_of_path(path), size=path.stat().st_size)    # type: ignore[arg-type]
        return self.add(dept_id, ref)

    def _mine(self, conn: Any, dept_id: str, file_id: str) -> FileRow:
        found = conn.execute(f"SELECT {_COLUMNS} FROM project_files WHERE id = ? AND dept_id = ? AND removed_at IS NULL", (file_id, dept_id)).fetchone()
        if found is None:
            raise NotFound("that file")
        return _row_of(found)

    def patch(self, dept_id: str, file_id: str, *, enabled: bool | None = None, name: str | None = None) -> FileOut:
        with self.db.tx() as tx:
            self._writable(tx.conn, dept_id)
            row = self._mine(tx.conn, dept_id, file_id)
            if enabled is not None:
                tx.conn.execute("UPDATE project_files SET enabled = ? WHERE id = ?", (1 if enabled else 0, file_id))
            if name is not None:
                clean = clean_name(name)
                if not clean:
                    raise validation_error([violation("name", "empty", "A file needs a name.")], "A file needs a name.")
                clash = tx.conn.execute("SELECT 1 FROM project_files WHERE dept_id = ? AND removed_at IS NULL AND id <> ? AND lower(name) = lower(?)", (dept_id, file_id, clean)).fetchone()
                if clash is not None:
                    said = f"Another file in this project is already called {clean}."
                    raise validation_error([violation("name", "taken", said)], said)
                tx.conn.execute("UPDATE project_files SET name = ? WHERE id = ?", (clean, file_id))
            return _out(self._mine(tx.conn, dept_id, file_id))

    def remove(self, dept_id: str, file_id: str) -> None:
        with self.db.tx() as tx:
            self._writable(tx.conn, dept_id)
            row = self._mine(tx.conn, dept_id, file_id)
            tx.conn.execute("UPDATE project_files SET removed_at = ? WHERE id = ?", (tx.now(), file_id))
        self._release([row.sha])

    def remove_all(self, dept_id: str) -> int:
        with self.db.tx() as tx:
            self._writable(tx.conn, dept_id)
            rows = self._live(tx.conn, dept_id)
            tx.conn.execute("UPDATE project_files SET removed_at = ? WHERE dept_id = ? AND removed_at IS NULL", (tx.now(), dept_id))
        self._release([r.sha for r in rows])
        return len(rows)

    # ---- the bytes -------------------------------------------------------------------------------------------------------------------

    def _release(self, shas: list[str]) -> None:
        """Delete the stored bytes of each id that nothing names any more: another project's live row, a task's snapshot, a chat line's files."""
        conn = self.db.conn()
        for sha in dict.fromkeys(shas):
            if not re.fullmatch(r"[0-9a-f]{64}", sha):
                continue
            used = (conn.execute("SELECT 1 FROM project_files WHERE sha = ? AND removed_at IS NULL LIMIT 1", (sha,)).fetchone()
                    or conn.execute("SELECT 1 FROM tasks WHERE input_files_json LIKE ? LIMIT 1", (f"%{sha}%",)).fetchone()
                    or conn.execute("SELECT 1 FROM chat_messages WHERE meta_json LIKE ? LIMIT 1", (f"%{sha}%",)).fetchone())
            if used is not None:
                continue
            path = self.store.path_of(sha)
            if path is not None:
                try:
                    path.unlink()
                except OSError:
                    log.warning("a stored file could not be removed (%s)", path.name)
