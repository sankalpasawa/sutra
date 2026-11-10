"""Reading what a run left for the owner (D135): the file the engine host wrote at the end of the run and the report it names.

    read_deliverable(run_dir) -> Deliverable | None

The host writes `<run>/deliverable.json` before `run.ended` for an output that leaves a file the owner reads (today: project work), whatever the end was:

    {"schema": "deliverable/1", "output": "project", "label": "Project work report", "file": "project.md",
     "changes": {"files": [{"path": "README.md", "status": "modified"}], "more": 0}}

`changes` is there only when the host could read git at both ends of the run in the owner's working folder (git, never an agent); an empty list says git
looked and nothing changed. The Projector reads the file when it applies `run.ended` (`Projector._finish`) and posts ONE card to the team's chat with
the report, the list and the link to the whole report; the done card in the org chat gets the link too.

Everything read here came from a run folder the app made, but the report is text a model wrote, so it is bounded and cleaned the way any such text is:
a plain file name (never a path), a plain file (never a link), at most DELIVERABLE_TEXT_MAX characters cut at a line end, control characters dropped.
A missing, torn or odd file is no deliverable: nothing is posted and nothing fails.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sutra_app.orchestrator.models import DELIVERABLE_FILES_MAX, DELIVERABLE_TEXT_MAX, ChangedFile, DeliverableChanges

__all__ = ["Deliverable", "read_deliverable", "RECORD_NAME", "RECORD_MAX_BYTES"]

RECORD_NAME = "deliverable.json"
RECORD_MAX_BYTES = 400_000                  # the record names at most a hundred files: anything bigger is not ours
_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,60}\.md")
_STATUS = ("new", "modified", "deleted", "reverted")


@dataclass(frozen=True)
class Deliverable:
    """`text` is the report (markdown, maybe cut: `cut`), "" when the run ended before it was written; `changes` is None when git could not say."""

    label: str
    file: str
    text: str
    cut: bool
    changes: Optional[DeliverableChanges]

    @property
    def has_report(self) -> bool:
        return self.text != ""


def _plain_file(folder: Path, name: str) -> Optional[Path]:
    try:
        path = folder / name
        return path if not folder.is_symlink() and path.is_file() and not path.is_symlink() else None
    except OSError:
        return None


def _clean(text: str) -> str:
    """The text without control characters (a line break and a tab stay; a carriage return goes, so a Windows line end is a plain one)."""
    return "".join(c for c in text if c in "\n\t" or (ord(c) >= 32 and ord(c) != 127)).strip()


def _report(run_dir: Path, name: str) -> tuple[str, bool]:
    """`(text, cut)` of the report file: the first DELIVERABLE_TEXT_MAX characters, cut at a line end; `("", False)` when there is none."""
    path = _plain_file(run_dir, name) if _FILE.fullmatch(name) else None
    if path is None:
        return "", False
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            raw = handle.read(DELIVERABLE_TEXT_MAX + 1)
    except OSError:
        return "", False
    text = _clean(raw)
    if len(text) > DELIVERABLE_TEXT_MAX:
        return text[:DELIVERABLE_TEXT_MAX].rsplit("\n", 1)[0].rstrip(), True
    return text, False


def _changes(value: object) -> Optional[DeliverableChanges]:
    """The record's `changes`, or None when it is not there or not in shape. Rows that are not `{path, status}` are dropped, not guessed at."""
    if not isinstance(value, dict) or not isinstance(value.get("files"), list):
        return None
    files = []
    for row in value["files"]:
        if isinstance(row, dict) and isinstance(row.get("path"), str) and row["path"].strip() and row.get("status") in _STATUS:
            files.append(ChangedFile(path=_clean(row["path"])[:400] or "?", status=row["status"]))
    more = value.get("more")
    extra = max(0, more) if isinstance(more, int) and not isinstance(more, bool) else 0
    kept = files[:DELIVERABLE_FILES_MAX]
    return DeliverableChanges(files=kept, more=extra + len(files) - len(kept))


def read_deliverable(run_dir: Path) -> Optional[Deliverable]:
    """What the run left, or None when it left nothing to show: no record, a record that is not ours, or neither a report nor a changed file."""
    folder = Path(run_dir)
    record = _plain_file(folder, RECORD_NAME)
    if record is None:
        return None
    try:
        if record.stat().st_size > RECORD_MAX_BYTES:
            return None
        body = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict) or body.get("schema") != "deliverable/1":
        return None
    label = " ".join(_clean(str(body.get("label") or "")).split())[:200] or "Report"
    file = body.get("file") if isinstance(body.get("file"), str) else ""
    text, cut = _report(folder, file)
    changes = _changes(body.get("changes"))
    if not text and not (changes is not None and (changes.files or changes.more)):
        return None
    return Deliverable(label=label, file=file if text else "", text=text, cut=cut, changes=changes)
