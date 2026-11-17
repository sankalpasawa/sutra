"""Sidebar sections: the owner's own named groups of projects ("Clients", "Internal"), kept on the server so they survive a restart and a new port.

    store = SectionsStore(data_dir)
    store.load()                                # the document; a missing or damaged file reads as the empty default (a damaged one is logged)
    store.save(doc)                             # checks and cleans `doc`, writes it, returns what was written (422 `validation`, each refusal named)
    clean_doc(doc)                              # the check alone: the cleaned document, or AppError 422 with every violation

The document is small and the page replaces it whole:

    {"version": 1, "sections": [{"id": "sec_ab12cd", "name": "Clients", "teams": ["web-development", "prd"], "collapsed": false}]}

A team (a department id, `DEPT_ID_RE`) is in at most one section; a team in none shows under "All projects". A team that does not exist (yet, or any
more) is kept as long as its id is a valid one. A name is trimmed and loses its control characters, then must be 1 to `NAME_CHARS` long. At most
`MAX_SECTIONS` sections, each with a unique `SECTION_ID_RE` id.

Storage: `<data_dir>/ui/sections.json`, written whole to a temp file in the same folder and swapped in with `oslayer.replace`, so a crash leaves the
old file or the new one, never half of one. Browser storage is not used: it is per port, and the app's port can change.
"""
import json
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from sutra_app import oslayer
from sutra_app.engine.spec import is_dept_id
from sutra_app.library.types import Violation, violation
from sutra_app.orchestrator.errors import validation_error

__all__ = ["SectionsStore", "clean_doc", "empty_doc", "VERSION", "MAX_SECTIONS", "NAME_CHARS", "SECTION_ID_RE", "FILE_PARTS"]

log = logging.getLogger(__name__)
VERSION = 1
MAX_SECTIONS = 30
NAME_CHARS = 40
MAX_TEAMS = 500                         # per section; far above any real org, it only bounds a hostile body
SECTION_ID_RE = r"^sec_[a-z0-9]{4,16}$"
FILE_PARTS = ("ui", "sections.json")    # under the data folder
SECTION_KEYS = {"id", "name", "teams", "collapsed"}
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_LOCK = threading.Lock()                # one writer at a time for every store of this process (the page saves rarely)


def empty_doc() -> dict[str, Any]:
    return {"version": VERSION, "sections": []}


def clean_name(value: object) -> str:
    """The name as it is kept: control characters dropped, then trimmed. A non-string is ""."""
    return _CONTROL.sub("", value).strip() if isinstance(value, str) else ""


def _check(doc: object) -> tuple[dict[str, Any], list[Violation]]:
    found: list[Violation] = []
    if not isinstance(doc, dict):
        return empty_doc(), [violation("", "not_object", "The sections must be a JSON object")]
    for key in sorted(set(doc) - {"version", "sections"}):
        found.append(violation(str(key), "extra", f"Unknown field {str(key)[:40]!r}"))
    if doc.get("version") != VERSION or isinstance(doc.get("version"), bool):
        found.append(violation("version", "bad_version", f"version must be {VERSION}"))
    sections = doc.get("sections")
    if not isinstance(sections, list):
        return empty_doc(), found + [violation("sections", "not_list", "sections must be a list")]
    if len(sections) > MAX_SECTIONS:
        return empty_doc(), found + [violation("sections", "too_many", f"At most {MAX_SECTIONS} sections")]
    out: list[dict[str, Any]] = []
    ids: set[str] = set()
    placed: dict[str, int] = {}                         # team -> the section index it was first seen in
    for i, raw in enumerate(sections):
        at = f"sections.{i}"
        if not isinstance(raw, dict):
            found.append(violation(at, "not_object", "A section must be an object"))
            continue
        for key in sorted(set(raw) - SECTION_KEYS):
            found.append(violation(f"{at}.{key}", "extra", f"Unknown field {str(key)[:40]!r}"))
        sid = raw.get("id")
        if not isinstance(sid, str) or re.fullmatch(SECTION_ID_RE, sid) is None:
            found.append(violation(f"{at}.id", "bad_id", "A section id looks like sec_ab12cd"))
        elif sid in ids:
            found.append(violation(f"{at}.id", "repeat_id", f"Two sections share the id {sid}"))
        else:
            ids.add(sid)
        name = clean_name(raw.get("name"))
        if not name:
            found.append(violation(f"{at}.name", "empty_name", "A section needs a name"))
        elif len(name) > NAME_CHARS:
            found.append(violation(f"{at}.name", "long_name", f"A section name is at most {NAME_CHARS} characters"))
        teams = raw.get("teams", [])
        if not isinstance(teams, list) or len(teams) > MAX_TEAMS:
            found.append(violation(f"{at}.teams", "not_list", f"teams must be a list of at most {MAX_TEAMS} project ids"))
            teams = []
        for j, team in enumerate(teams):
            if not is_dept_id(team):
                found.append(violation(f"{at}.teams.{j}", "bad_team", "Not a project id"))
            elif team in placed:
                where = "this section" if placed[team] == i else f"section {placed[team] + 1}"
                found.append(violation(f"{at}.teams.{j}", "repeat_team", f"{team} is already in {where}: a project sits in one section only"))
            else:
                placed[team] = i
        collapsed = raw.get("collapsed", False)
        if not isinstance(collapsed, bool):
            found.append(violation(f"{at}.collapsed", "not_bool", "collapsed must be true or false"))
        out.append({"id": sid, "name": name, "teams": list(teams), "collapsed": collapsed is True})
    return {"version": VERSION, "sections": out}, found


def clean_doc(doc: object) -> dict[str, Any]:
    """The document as it is kept, or AppError 422 `validation` naming every refusal (the first 50)."""
    cleaned, found = _check(doc)
    if found:
        raise validation_error(found[:50], "The sections were refused")
    return cleaned


class SectionsStore:
    """The one sections file of a data folder. Holds no state but its path, so a route builds one per call."""

    def __init__(self, data_dir: str | os.PathLike[str]) -> None:
        self.path = Path(data_dir).joinpath(*FILE_PARTS)

    def load(self) -> dict[str, Any]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return empty_doc()
        except OSError as exc:
            log.warning("sections: cannot read %s (%s); showing no sections", self.path, exc)
            return empty_doc()
        try:
            cleaned, found = _check(json.loads(text))
        except ValueError:
            found, cleaned = [violation("", "bad_json", "not JSON")], empty_doc()
        if found:
            log.warning("sections: %s is damaged (%s); showing no sections until the next save", self.path, found[0].message)
            return empty_doc()
        return cleaned

    def save(self, doc: object) -> dict[str, Any]:
        cleaned = clean_doc(doc)
        with _LOCK:
            self._write(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n")
        return cleaned

    def _write(self, text: str) -> None:
        folder = self.path.parent
        folder.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{self.path.name}.", suffix=".tmp")      # the same folder: the swap is atomic
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            oslayer.replace(tmp, self.path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
