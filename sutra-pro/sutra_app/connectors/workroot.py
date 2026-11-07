"""The default work root of ONE data folder (connectors design CD9, QA direct-chat bug 1).

The work root holds every chat's `session.json` (the provider session id it resumes) and `system.txt` (its grounding). Session ids repeat from one
data folder to the next (`cs_org` is the org chat of all of them), so a root that every data folder of the machine shared let a brand-new folder resume
another instance's provider session, and let two instances overwrite each other's files. The root now belongs to the folder:

    <tempdir>/sutra-app-<uid>/work-<key>        key = first 16 hex of sha256(realpath(data folder) + "\\n" + the folder's id)

`<data>/connectors/work-id` is that id: random, written once (mode 0600) when the data folder exists and has none (or a damaged one). It makes a folder
that was deleted and made again at the same path a new folder (its old provider sessions are never resumed), and the realpath makes a copy of a folder
another one. A folder that cannot be written to (read-only, not there yet) is keyed by its path alone. The root stays under the OS temp root, outside any
checkout: a data folder inside a repo must not make the CLIs read that repo's CLAUDE.md or AGENTS.md (CD9).

A root that changes (the first run after this change, a folder moved to another path) only costs a new provider session with the carry-over of the app's
own transcript; the transcript is the app's, the provider session is its cache.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from pathlib import Path

from sutra_app import oslayer

__all__ = ["ID_FILE", "folder_id", "default_work_root"]

ID_FILE = "work-id"
_VALID = re.compile(r"[0-9a-f]{32}")
_PRIVATE_FILE = 0o600
_PRIVATE_DIR = 0o700


def _read(path: Path) -> str:
    try:
        found = path.read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return ""
    return found if _VALID.fullmatch(found) else ""


def folder_id(data_dir: "str | os.PathLike[str]") -> str:
    """The id of this data folder, made on first use; "" when there is none and none can be made (the folder is missing or cannot be written)."""
    folder = Path(data_dir)
    mark = folder / "connectors" / ID_FILE
    found = _read(mark)
    if found or not folder.is_dir():
        return found
    fresh = uuid.uuid4().hex
    tmp = mark.with_name(f".{ID_FILE}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        mark.parent.mkdir(exist_ok=True, mode=_PRIVATE_DIR)
        fd = os.open(str(tmp), os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_EXCL, _PRIVATE_FILE)
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(fresh + "\n")
        oslayer.replace(tmp, mark)
    except OSError:
        return ""
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return _read(mark) or fresh               # two starts at once: whichever file stayed is the id both use


def default_work_root(data_dir: "str | os.PathLike[str]") -> Path:
    """`<tempdir>/sutra-app-<uid>/work-<key>` for this data folder (not yet resolved through realpath; `ConnectorConfig.resolved_work_root` does that)."""
    ident = folder_id(data_dir)
    key = hashlib.sha256(f"{os.path.realpath(data_dir)}\n{ident}".encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"sutra-app-{oslayer.user_token()}" / f"work-{key}"
