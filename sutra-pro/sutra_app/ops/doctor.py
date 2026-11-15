"""`sutra-pro doctor`: fourteen checks of the machine, the data folder and the setup, each with a fix hint (gaps G08, D34, D92, D94).

    report = run(settings, offline=False)          # starts no server, makes no model call, writes nothing but a probe file
    print("\\n".join(report.lines()));  exit(0 if report.ok else 1)

A check is `ok`, `warn` (the app runs, something is worth fixing), `fail` (the app cannot do its job) or `skip` (not looked at: offline,
or optional). The report is `ok` when nothing failed. The checks, in order:

    python, data_dir, disk, database, env_file, claude, codex, gh, chrome, port, instance, library, browser, settings

`claude` and `codex` are judged together: when one of them is unusable the other still lets the app work, so the broken one is a
warning; when neither works both fail. The CLI checks reuse the connector layer's own status probes (`build_router(...).status()`:
`<cli> --version`, `claude auth status`, `codex login status`; no model call). An API-key login is refused (D34).
`offline` skips the three CLI checks and the two browser checks.
"""
import contextlib
import copy
import hashlib
import json
import logging
import os
import re
import stat
import time
from sutra_app import oslayer
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sutra_app.config import Settings, read_env_file
from sutra_app.ops import browser, lock
from sutra_app.ops.envfile import SMTP_VARS, mode_problem

__all__ = ["Check", "Report", "run", "CHECK_IDS", "MIN_FREE_BYTES", "PORT_RANGE", "seed_dir", "missing_seed_templates", "missing_seed_versions",
           "missing_seed_run_templates",
           "sync_seed_library", "sync_seed_once", "SeedSyncError", "LibraryBusy", "LibraryUnreadable", "LOCK_WAIT_S", "SEED_MARKER"]

MIN_FREE_BYTES = 1024 ** 3
MIN_PYTHON = (3, 11)
PORT_RANGE = range(8780, 8800)
GH_TIMEOUT_S = 10
CHECK_IDS = ("python", "data_dir", "disk", "database", "env_file", "claude", "codex", "gh", "chrome", "port", "instance", "library",
             "browser", "settings")
_LOGIN = {"claude": "claude auth login", "codex": "codex login"}


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    status: str                 # ok | warn | fail | skip
    detail: str
    fix: str = ""

    def line(self) -> str:
        tag = {"ok": "[ ok ]", "warn": "[WARN]", "fail": "[FAIL]", "skip": "[skip]"}[self.status]
        text = f"{tag} {self.title}: {self.detail}"
        return text + (f"  -> fix: {self.fix}" if self.fix and self.status in ("warn", "fail") else "")

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "title": self.title, "status": self.status, "detail": self.detail, "fix": self.fix}


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures()

    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == "fail"]

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for c in self.checks if c.status == s) for s in ("ok", "warn", "fail", "skip")}

    def lines(self) -> list[str]:
        counts = self.counts()
        return [c.line() for c in self.checks] + [
            f"{counts['ok']} ok, {counts['warn']} warning(s), {counts['fail']} failed, {counts['skip']} skipped"]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "summary": self.counts(), "checks": [c.to_dict() for c in self.checks]}


# ---- the seed library ---------------------------------------------------------------------------------------------------------
# D144. The app ships a seed template library (`engine/seed/library`). An install's `<data>/library` began as a copy of it and its runs
# have added to it since. A newer seed brings new templates, new versions of templates the install has, the provenance of the versions it
# has (who made one, when, for which business, live or mock) and the runs those came from. `sync_seed_library` gives an existing library
# exactly that and nothing else: it only adds. It never changes a value, never renumbers a version, and writes every file by a temp file
# and `oslayer.replace`, under the `<library>/.lock` that the runtime's `store` and `mark_used` take (the engine's patch P10).
# D185 (J2 sync 6) adds the run templates (`run_templates` of the index and the folders `run-templates/<id>/`) and the two provenance keys
# `renamed_from` and `adapted_from`; nothing is moved or renamed on disk, so a family J2 renamed is added beside the old one.

log = logging.getLogger(__name__)
LOCK_WAIT_S = 30.0                      # the most a sync waits for the library lock (the wait P10 gives a run)
SEED_MARKER = ".seed-sync"              # `<library>/.seed-sync`: the sha256 of the seed's index.json that the library was last synced with


class SeedSyncError(OSError):
    """The seed could not be synced into the library. Nothing was changed: the library is as it was."""


class LibraryBusy(SeedSyncError):
    """Another process held `<library>/.lock` for `LOCK_WAIT_S` seconds (a run storing a template, or another sync)."""


class LibraryUnreadable(SeedSyncError):
    """`<library>/index.json` exists and is not a template library index. It is never replaced: it lists the owner's templates."""


def seed_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "engine" / "seed" / "library"


def _entries(index_path: Path) -> list[dict[str, Any]]:
    try:
        doc = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = doc.get("templates") if isinstance(doc, dict) else None
    return [t for t in items if isinstance(t, dict)] if isinstance(items, list) else []


def _key(entry: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(entry.get("artifact")), str(entry.get("section_slug")), str(entry.get("slug")))


def missing_seed_templates(data_dir: str | os.PathLike[str], seed: Path | None = None) -> list[str] | None:
    """The seed templates (`artifact/section/slug`) that `<data>/library` lacks, as folder or as index entry. None when there is no
    library folder yet (the engine seeds it whole at the first run)."""
    library = Path(data_dir) / "library"
    if not library.is_dir():
        return None
    have = {_key(e) for e in _entries(library / "index.json")}
    wanted = sorted(_key(e) for e in _entries((seed or seed_dir()) / "index.json"))
    return ["/".join(key) for key in wanted if key not in have or not library.joinpath(*key).is_dir()]


def _read_json(path: Path) -> Any:
    """What `path` holds as JSON; None when it is absent or not JSON."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, obj: Any) -> None:
    """A library file written as J2 writes one (indent 2, readable text, a newline), by a temp file beside it and `oslayer.replace`; an
    existing file keeps its permission bits. Always `\\n`, whatever the system."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write((json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        with contextlib.suppress(OSError):
            os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
        oslayer.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _copy_folder(source: Path, target: Path) -> None:
    """Copy a seed folder to a place that does not exist yet: into a temp folder beside it, then one rename, so that a crash cannot leave
    a half-copied version folder that looks present."""
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(dir=target.parent, prefix=".sync-"))
    try:
        part = scratch / "copy"
        shutil.copytree(source, part)
        oslayer.replace(part, target)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


@contextlib.contextmanager
def _library_lock(library: Path) -> Iterator[None]:
    """An exclusive lock on `<library>/.lock`, the file and the calls the runtime's `store` and `mark_used` use (P10), so that a sync and a
    run never write the index together. Waits `LOCK_WAIT_S`, then raises `LibraryBusy`."""
    fd = os.open(library / ".lock", os.O_RDWR | oslayer.O_BINARY | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + LOCK_WAIT_S
        while not oslayer.try_lock(fd):
            if time.monotonic() >= deadline:
                raise LibraryBusy(f"the template library is locked by another process (waited {LOCK_WAIT_S:g} s)") from None
            time.sleep(0.05)
        try:
            yield
        finally:
            oslayer.unlock(fd)
    finally:
        os.close(fd)


def _library_doc(library: Path) -> dict[str, Any]:
    """The library's index as J2 reads it: a library with no index file has an empty one. A file that is there and is not an index is
    `LibraryUnreadable`: the sync never replaces it."""
    path = library / "index.json"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"schema": "template-library/1", "templates": []}
    except OSError as exc:
        raise LibraryUnreadable(f"{path} cannot be read ({exc.strerror or exc})") from exc
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise LibraryUnreadable(f"{path} is not valid JSON ({exc})") from exc
    if doc == {}:
        return {"schema": "template-library/1", "templates": []}
    if not isinstance(doc, dict) or not isinstance(doc.get("templates"), list):
        raise LibraryUnreadable(f"{path} is not a template library index (it has no list of templates)")
    return doc


def _safe_key(key: tuple[str, str, str]) -> bool:
    """A seed template's folder names are used to make folders under the library: only plain names pass."""
    return all(part not in ("", ".", "..", "None") and "/" not in part and "\\" not in part for part in key)


def _disk_sha(folder: Path) -> str | None:
    """The spec sha a version folder's own meta.json holds."""
    meta = _read_json(folder / "meta.json")
    sha = meta.get("sha") if isinstance(meta, dict) else None
    return sha if isinstance(sha, str) else None


def _seed_doc(seed: Path) -> dict[str, Any]:
    doc = _read_json(seed / "index.json")
    return doc if isinstance(doc, dict) else {}


def _template_order(entry: Any) -> tuple[str, str, str]:
    """J2's own order of the index's templates (`_save_index`)."""
    return (str(entry.get("artifact")), str(entry.get("section")), str(entry.get("slug"))) if isinstance(entry, dict) else ("", "", "")


def _version_of(row: Any) -> int:
    return row["version"] if isinstance(row, dict) and isinstance(row.get("version"), int) else 0


RUN_TEMPLATES_KEY = "run_templates"     # the index key of J2's run templates (J2 1adb8ecd)
RUN_TEMPLATES_DIR = "run-templates"     # `<library>/run-templates/<id>/{template.json, schema.json}`
RUN_TEMPLATE_FILES = ("template.json", "schema.json")
_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")          # J2's `slug`: a run template's id is also its folder name
PROVENANCE_ONLY_IF_LACKING = ("business", "mock", "collected_from", "renamed_from", "adapted_from")


def _safe_id(value: Any) -> bool:
    return isinstance(value, str) and len(value) <= 120 and bool(_ID_RE.match(value))


def _run_template_rows(doc: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = doc.get(RUN_TEMPLATES_KEY)
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _run_template_name(row: Mapping[str, Any]) -> str:
    return str(row.get("name") or row.get("id") or "").lower()


def _fill(target: dict[str, Any], *sources: Any) -> list[str]:
    """Give `target` the provenance keys it lacks (`business`, `mock`, `collected_from`, `renamed_from`, `adapted_from`, `made_by` and its
    `date`), each taken from the first of `sources` that has it. A key that is there is never changed; of a `made_by` that is there only a
    missing `date` is added. Returns the keys added, by the names D144 and D185 use."""
    found_in = tuple(s for s in sources if isinstance(s, Mapping))
    added: list[str] = []
    for name in PROVENANCE_ONLY_IF_LACKING:
        if name not in target:
            donor = next((s for s in found_in if name in s), None)
            if donor is not None:
                target[name] = copy.deepcopy(donor[name])
                added.append(name)
    made = target.get("made_by")
    if "made_by" not in target:
        donor = next((s for s in found_in if "made_by" in s), None)
        if donor is not None:
            target["made_by"] = copy.deepcopy(donor["made_by"])
            added.append("made_by.date" if isinstance(donor["made_by"], Mapping) and "date" in donor["made_by"] else "made_by")
    elif isinstance(made, dict) and "date" not in made:
        donor = next((s["made_by"] for s in found_in if isinstance(s.get("made_by"), Mapping) and "date" in s["made_by"]), None)
        if donor is not None:
            made["date"] = donor["date"]
            added.append("made_by.date")
    return added


def _apply_seed(library: Path, seed: Path, doc: dict[str, Any], *, apply: bool) -> dict[str, Any]:
    """The rule of D144 over the library's index `doc`, which it edits in place; the caller writes the index when it changed.

    For each seed template and each of its versions (the library's state decides, the seed's number is never changed):
      * the library has a row with the same spec sha (at any number): present. Provenance keys it lacks are added to its row and to its
        meta.json. A row whose folder is gone, at the seed's own number, gets its folder back from the seed;
      * else a row at that number (another spec): left alone, reported `skipped`;
      * else a folder at that number with no row: its own meta.json decides: the same sha gets its row (the index lost it), any other
        is left alone and reported `skipped`;
      * else the number is free: the seed's folder is copied and its row appended.
    A template the library lacks (no index entry, or no folder) is the same rule over all its versions; it is reported as a template,
    its versions are not listed one by one. The seed's `runs` rows whose id is absent are appended. D185: the seed's `run_templates` follow
    the same four states per id (`_apply_run_templates`), and a version the seed says was renamed (`renamed_from`) that is added here,
    under the family name the seed gives it, is also listed in `renamed` (the old family stays where it is: nothing is moved).

    `apply` False writes nothing (`doc` is still edited: pass a copy); the report says what would be done. The report:
    `templates`, `versions` (`artifact/section/slug@vN`), `filled` (version -> provenance keys added), `skipped`, `runs`,
    `run_templates` (ids added or restored) and `renamed` (version -> the name@N it was renamed from)."""
    report: dict[str, Any] = {"templates": [], "versions": [], "filled": {}, "skipped": [], "runs": [], "run_templates": [], "renamed": {}}
    seed_doc = _seed_doc(seed)
    held = {_key(e): e for e in doc["templates"] if isinstance(e, dict)}
    new_entries: list[dict[str, Any]] = []

    def skip(template: str, version: Any, why: str) -> None:
        report["skipped"].append({"template": template, "version": version, "why": why})

    for seed_entry in seed_doc.get("templates") or []:
        if not isinstance(seed_entry, dict) or not _safe_key(_key(seed_entry)):
            continue
        key = _key(seed_entry)
        name = "/".join(key)
        folder, source = library.joinpath(*key), seed.joinpath(*key)
        entry = held.get(key)
        if entry is not None and not isinstance(entry.get("versions"), list):
            skip(name, None, "its entry in the library index has no list of versions")
            continue
        rows: list[Any] = entry["versions"] if entry is not None else []
        lacking = entry is None or not folder.is_dir()
        done: list[str] = []
        appended = False
        seed_rows = sorted((r for r in seed_entry.get("versions") or [] if isinstance(r, dict) and isinstance(r.get("version"), int)),
                           key=_version_of)
        for seed_row in seed_rows:
            n = seed_row["version"]
            sha = seed_row.get("sha") if isinstance(seed_row.get("sha"), str) else None
            seed_folder = source / f"v{n}"
            same = next((r for r in rows if sha and isinstance(r, dict) and r.get("sha") == sha), None)
            if same is not None:                                              # the same spec is here, at its number
                m = same.get("version")
                here = folder / f"v{m}"
                if here.is_dir():
                    state = "present"
                elif m == n and seed_folder.is_dir():
                    state = "restore"
                else:
                    skip(name, n, f"its folder v{m} is missing here and the seed's v{n} is not copied under another number")
                    continue
            else:
                m, here = n, folder / f"v{n}"
                if any(isinstance(r, dict) and r.get("version") == n for r in rows):
                    skip(name, n, f"v{n} is already taken here by a version with another spec; yours is kept and the seed's is not renumbered")
                    continue
                if here.exists():
                    if here.is_dir() and sha is not None and _disk_sha(here) == sha:
                        state = "adopt"
                    else:
                        skip(name, n, f"a folder v{n} exists here with another spec and no index row; it is left alone")
                        continue
                elif seed_folder.is_dir():
                    state = "add"
                else:
                    skip(name, n, "the seed has no folder for it")
                    continue
            label = f"{name}@v{m}"
            keys: list[str] = []
            if state in ("add", "restore") and apply:
                _copy_folder(seed_folder, here)
            if state in ("add", "adopt"):
                row = copy.deepcopy(seed_row)
                rows.append(row)
                appended = True
                done.append(label)
                if isinstance(seed_row.get("renamed_from"), str) and seed_row["renamed_from"]:
                    report["renamed"][label] = seed_row["renamed_from"]
            elif state == "restore":
                done.append(label)
            if state in ("present", "restore"):                               # the library's own row gains the seed row's provenance
                keys += _fill(same, seed_row)
            if state in ("present", "adopt"):                                 # the folder was there before the sync: its meta.json too
                meta_path = here / "meta.json"
                meta = _read_json(meta_path)
                if isinstance(meta, dict) and sha is not None and meta.get("sha") == sha:
                    got = _fill(meta, _read_json(seed_folder / "meta.json"), seed_row)
                    if got and apply:
                        _write_json(meta_path, meta)
                    keys += got
                elif isinstance(meta, dict) and _fill(copy.deepcopy(meta), _read_json(seed_folder / "meta.json"), seed_row):
                    skip(name, m, "its meta.json does not hold this spec's sha; provenance was not added to it")
                elif meta is None and meta_path.exists():
                    skip(name, m, "its meta.json is not valid JSON; provenance was not added to it")
            if keys:
                report["filled"][label] = sorted(set(keys))
        if appended and entry is not None:
            rows.sort(key=_version_of)
        if entry is None:
            if rows:                                                          # versions were added or adopted: the template is new here
                new_entries.append({k: sorted(rows, key=_version_of) if k == "versions" else copy.deepcopy(v) for k, v in seed_entry.items()})
                report["templates"].append(name)
        elif done:
            if lacking:
                report["templates"].append(name)
            else:
                report["versions"].extend(done)
    doc["templates"].extend(new_entries)
    seed_runs = seed_doc.get("runs")
    if isinstance(seed_runs, dict) and seed_runs:
        mine = doc.get("runs")
        if mine is None:
            mine = {}
        if isinstance(mine, dict):
            fresh = {rid: row for rid, row in seed_runs.items() if rid not in mine}
            if fresh:
                mine.update(copy.deepcopy(fresh))
                doc["runs"] = mine
                report["runs"] = list(fresh)
        else:
            skip("index.json", None, "`runs` is not an object; the seed's runs were not added")
    _apply_run_templates(library, seed, seed_doc, doc, report, apply=apply, skip=skip)
    return report


def _apply_run_templates(library: Path, seed: Path, seed_doc: Mapping[str, Any], doc: dict[str, Any], report: dict[str, Any], *,
                         apply: bool, skip: Callable[[str, Any, str], None]) -> None:
    """D185: J2's run templates (`run_templates` of the index, `run-templates/<id>/{template.json, schema.json}`), per seed id and by the
    states of a version: the library has the row and the folder (present: left alone, its `used_by` is the library's own); the row but not
    the folder (restore: the seed's folder is copied back); the folder but not the row (adopt: the row is appended when the folder's
    template.json is the seed's run template, else the folder is left alone and reported); neither (add: folder copied, row appended). An
    id the library holds under another spec is never touched. The rows are kept in J2's order (by name, case-insensitive)."""
    seed_rows = _run_template_rows(seed_doc)
    if not seed_rows:
        return
    if doc.get(RUN_TEMPLATES_KEY) is not None and not isinstance(doc[RUN_TEMPLATES_KEY], list):
        skip("index.json", None, "`run_templates` is not a list; the seed's run templates were not added")
        return
    rows: list[Any] = doc.get(RUN_TEMPLATES_KEY) or []                              # the key is written only when a row is added
    held = {r.get("id"): r for r in rows if isinstance(r, dict)}
    appended = False
    for seed_row in seed_rows:
        rid = seed_row.get("id")
        name = f"{RUN_TEMPLATES_DIR}/{rid}"
        if not _safe_id(rid):
            continue
        source, here = seed / RUN_TEMPLATES_DIR / rid, library / RUN_TEMPLATES_DIR / rid
        has_source = source.is_dir() and all((source / f).is_file() for f in RUN_TEMPLATE_FILES)
        row = held.get(rid)
        if row is not None:
            if here.is_dir():
                continue                                                          # present
            if not has_source:
                skip(name, None, "its folder is missing here and the seed has none to restore it from")
                continue
            if apply:
                _copy_folder(source, here)                                        # restore
            report["run_templates"].append(rid)
            continue
        if here.exists():
            same = _read_json(here / "template.json") if here.is_dir() else None
            if isinstance(same, dict) and same.get("id") == rid and same.get("made_from_run") == seed_row.get("made_from_run"):
                state = "adopt"
            else:
                skip(name, None, "a folder of this name exists here with another run template and no index row; it is left alone")
                continue
        elif has_source:
            state = "add"
        else:
            skip(name, None, "the seed has no folder for it")
            continue
        if state == "add" and apply:
            _copy_folder(source, here)
        rows.append(copy.deepcopy(seed_row))
        held[rid] = rows[-1]
        appended = True
        report["run_templates"].append(rid)
    if appended:
        rows.sort(key=lambda r: _run_template_name(r) if isinstance(r, dict) else "")
        doc[RUN_TEMPLATES_KEY] = rows


def _seed_whole(library: Path, seed: Path) -> bool:
    """A data folder without a library gets the whole seed, as the engine does at a first run: copied beside it, then one rename decides
    between processes that start together. False when another process made the library first (the locked path then adds what it lacks)."""
    library.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch = library.with_name(f".library.sync-{os.getpid()}")
    shutil.rmtree(scratch, ignore_errors=True)
    shutil.copytree(seed, scratch)
    try:
        oslayer.replace(scratch, library)
    except OSError:
        shutil.rmtree(scratch, ignore_errors=True)
        if not library.exists():
            raise
        return False
    return True


def sync_seed_library(data_dir: str | os.PathLike[str], seed: Path | None = None, *, report: dict[str, Any] | None = None) -> list[str]:
    """Give `<data>/library` what the seed has and it lacks (D144: only adds, never overwrites; `_apply_seed` has the rule). Returns the
    templates added (`artifact/section/slug`) and the versions added to templates it had (`artifact/section/slug@vN`). `report`, when
    given, is filled with `templates`, `versions`, `filled`, `skipped`, `runs`, `run_templates` and `renamed` (`_apply_seed` says what each is).

    A data folder without a library gets the whole seed. Otherwise the sync runs under the library lock (waits `LOCK_WAIT_S`, then
    raises `LibraryBusy`) and writes the index once, at the end; an index that is not an index raises `LibraryUnreadable` and nothing is
    touched. Both are `OSError`s, and the library is as it was. Run twice, the second changes nothing."""
    seed = seed or seed_dir()
    library = Path(data_dir) / "library"
    found: dict[str, Any] | None = None
    if not library.exists() and _seed_whole(library, seed):
        seed_runs = _seed_doc(seed).get("runs")
        found = {"templates": ["/".join(_key(e)) for e in _entries(seed / "index.json")], "versions": [], "filled": {}, "skipped": [],
                 "runs": list(seed_runs) if isinstance(seed_runs, dict) else [], "renamed": {},
                 "run_templates": [r["id"] for r in _run_template_rows(_seed_doc(seed)) if isinstance(r.get("id"), str)]}
    if found is None:
        with _library_lock(library):
            doc = _library_doc(library)
            before = copy.deepcopy(doc)
            found = _apply_seed(library, seed, doc, apply=True)
            if doc != before:
                doc["templates"].sort(key=_template_order)
                _write_json(library / "index.json", doc)
    if report is not None:
        report.update(found)
    return sorted(found["templates"]) + sorted(found["versions"])


def missing_seed_versions(data_dir: str | os.PathLike[str], seed: Path | None = None) -> list[str]:
    """The seed versions (`artifact/section/slug@vN`) of templates the library has that it lacks and could receive: what `sync_seed_library`
    would add or restore. Not the versions of a template it lacks as a whole (`missing_seed_templates` lists those) and not a version whose
    number is taken by another spec (the sync leaves that one alone). Nothing is written and no lock is taken. [] when there is no library
    or its index is not an index."""
    library = Path(data_dir) / "library"
    if not library.is_dir():
        return []
    try:
        doc = _library_doc(library)
    except LibraryUnreadable:
        return []
    return sorted(_apply_seed(library, seed or seed_dir(), doc, apply=False)["versions"])


def missing_seed_run_templates(data_dir: str | os.PathLike[str], seed: Path | None = None) -> list[str]:
    """The ids of the seed's run templates that `sync_seed_library` would add or restore (D185): the library lacks the row or the folder.
    Nothing is written and no lock is taken. [] when there is no library or its index is not an index."""
    library = Path(data_dir) / "library"
    if not library.is_dir():
        return []
    try:
        doc = _library_doc(library)
    except LibraryUnreadable:
        return []
    return sorted(_apply_seed(library, seed or seed_dir(), doc, apply=False)["run_templates"])


def _seed_sha(seed: Path) -> str | None:
    try:
        return hashlib.sha256((seed / "index.json").read_bytes()).hexdigest()
    except OSError:
        return None


def sync_seed_once(data_dir: str | os.PathLike[str], seed: Path | None = None) -> dict[str, Any] | None:
    """The server's start-up sync: `sync_seed_library`, once per seed. `<library>/.seed-sync` holds the sha256 of the seed's index.json the
    library was last synced with; when it is the current one nothing is done. A data folder without a library gets the whole seed, as the
    engine does at a first run (`host/loop._seed_library` stays for a run that starts without the server). Never raises: a failure (the
    lock held, an index that is not an index, a disk error) is a warning in the log, the marker is not written, and the next start tries
    again. Returns the report when it synced, else None."""
    try:
        seed = seed or seed_dir()
        library = Path(data_dir) / "library"
        wanted = _seed_sha(seed)
        if wanted is None:
            return None
        marker = library / SEED_MARKER
        try:
            if marker.read_text(encoding="utf-8").strip() == wanted:
                return None
        except OSError:
            pass
        report: dict[str, Any] = {}
        sync_seed_library(data_dir, seed, report=report)
    except Exception as exc:                                                    # noqa: BLE001 - a library problem never stops the app from starting
        log.warning("the template library was not synced with the seed (%s: %s); the next start tries again", type(exc).__name__, exc)
        return None
    try:
        tmp = marker.with_name(f"{SEED_MARKER}.{os.getpid()}.tmp")
        tmp.write_text(wanted + "\n", encoding="utf-8")
        oslayer.replace(tmp, marker)
    except OSError as exc:
        log.warning("the template library was synced, but %s could not be written (%s); the next start syncs again", SEED_MARKER, exc.strerror or exc)
    added = len(report["templates"]) + len(report["versions"]) + len(report["filled"]) + len(report["runs"]) + len(report["run_templates"])
    if added:
        log.info("template library synced with the seed: %d template(s), %d version(s), provenance on %d version(s), %d run(s), %d run template(s)",
                 len(report["templates"]), len(report["versions"]), len(report["filled"]), len(report["runs"]), len(report["run_templates"]))
    if report["skipped"]:
        log.warning("template library: %d seed version(s) were left alone (their number is taken here by another spec, or their files differ): %s",
                    len(report["skipped"]), ", ".join(f"{s['template']}@v{s['version']}" if s["version"] is not None else s["template"] for s in report["skipped"][:5]))
    return report


# ---- the checks ---------------------------------------------------------------------------------------------------------------

def _nearest_existing(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return Path("/")


def _check_python(version: Sequence[int]) -> Check:
    text = ".".join(str(n) for n in tuple(version)[:3])
    if tuple(version)[:2] >= MIN_PYTHON:
        return Check("python", "Python", "ok", text)
    return Check("python", "Python", "fail", f"{text} is older than {MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
                 f"install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer (for example `uv venv --python 3.11`)")


def _check_data_dir(data_dir: Path) -> Check:
    title = "Data folder"
    if data_dir.exists() and not data_dir.is_dir():
        return Check("data_dir", title, "fail", f"{data_dir} exists and is not a folder", "move it away or set SUTRA_DATA_DIR")
    anchor = data_dir if data_dir.exists() else _nearest_existing(data_dir)
    try:
        with tempfile.NamedTemporaryFile(dir=anchor, prefix=".sutra-doctor-"):
            pass
    except OSError as exc:
        return Check("data_dir", title, "fail", f"{anchor} is not writable ({exc.strerror or exc})",
                     f"fix the permissions (`chmod u+rwx {anchor}`) or set SUTRA_DATA_DIR to another folder")
    if not data_dir.exists():
        return Check("data_dir", title, "ok", f"{data_dir} will be created at the first start")
    if oslayer.IS_WINDOWS:
        return Check("data_dir", title, "ok", f"{data_dir} (writable; Windows keeps a profile folder private to its user)")
    mode = data_dir.stat().st_mode & 0o777
    if mode & 0o077:
        return Check("data_dir", title, "warn", f"{data_dir} is mode {mode:03o}; it holds your work and should be private",
                     f"chmod 700 {data_dir}")
    return Check("data_dir", title, "ok", f"{data_dir} (writable, mode {mode:03o})")


def _check_disk(data_dir: Path, minimum: int) -> Check:
    anchor = _nearest_existing(data_dir)
    try:
        free = shutil.disk_usage(anchor).free
    except OSError as exc:
        return Check("disk", "Free space", "warn", f"could not read the free space of {anchor}: {exc}", "check the disk by hand")
    gb = free / 1024 ** 3
    if free < minimum:
        return Check("disk", "Free space", "fail", f"{gb:.2f} GB free on the disk of {anchor}; at least {minimum / 1024 ** 3:.0f} GB is needed",
                     "free some space (runs write screenshots and logs)")
    return Check("disk", "Free space", "ok", f"{gb:.1f} GB free")


def _check_database(settings: Settings) -> Check:
    from sutra_app.ops.backup import integrity_problem
    from sutra_app.orchestrator.schema import SCHEMA_VERSION
    path = settings.db_path
    if not path.exists():
        return Check("database", "Database", "ok", "none yet; it is created at the first start")
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        try:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
            problem = integrity_problem(conn)            # reading the version proves little: a damaged file still opens and reads its first page
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return Check("database", "Database", "fail", f"{path.name} cannot be opened ({exc})",
                     "if it is not a Sutra database move it away; otherwise restore a backup")
    if problem is not None:
        return Check("database", "Database", "fail", f"{path.name} fails SQLite's integrity check ({problem})",
                     "stop Sutra Pro and restore the newest good backup (`sutra-pro restore FILE`, backups are in the data folder's backups/); "
                     "a backup of this file cannot be restored, so none is made")
    if version > SCHEMA_VERSION:
        return Check("database", "Database", "fail", f"schema version {version} is newer than this app's {SCHEMA_VERSION}",
                     "update the app (a newer version wrote this file); do not open it with an older one")
    note = "" if version == SCHEMA_VERSION else f"; it will be upgraded to {SCHEMA_VERSION} at the next start"
    return Check("database", "Database", "ok", f"schema version {version}{note}")


def _check_env_file(settings: Settings) -> Check:
    path = settings.env_file
    if not path.exists():
        return Check("env_file", ".env file", "ok",
                     f"none at {path} (optional: the owner override key and live email need one; `sutra-pro config init` writes a template)")
    problem = mode_problem(path)
    if problem:
        return Check("env_file", ".env file", "warn", f"{path}: {problem}", f"chmod 600 {path}")
    return Check("env_file", ".env file", "ok", f"{path} (mode 600)")


def _provider_statuses(settings: Settings, cfg: Any) -> dict[str, Any]:
    from sutra_app.connectors.factory import build_router
    router = build_router(settings.model_copy(update={"connector": "auto", "offline": False}), config=cfg)
    try:
        return {p.name: p for p in router.status().providers}
    finally:
        router.close()


def _judge(name: str, status: Any, desktop: bool = False) -> tuple[str, str, str]:
    """('ok' | 'warn' | 'bad', detail, fix) for one CLI. `desktop`: Claude Desktop is installed, which is not Claude Code (GAP-providers)."""
    from sutra_app.connectors.factory import TESTED_VERSIONS
    login = _LOGIN[name]
    if (status is None or not status.installed) and name == "claude" and desktop:
        return "bad", "Claude Desktop is installed, but Sutra needs Claude Code, a separate command-line tool", \
            f"install Claude Code (claude.com/claude-code), or choose its file in Settings, Connectors; then run `{login}`"
    if status is None or not status.installed:
        return "bad", "not found on PATH or in the usual install folders", \
            f"install the {name} CLI (or choose its file in Settings, Connectors), then run `{login}`"
    version = status.version or "unknown version"
    if status.billing == "api_key":
        return "bad", f"{version}: signed in with an API key, which is refused", f"sign out, then `{login}` with your subscription account"
    if status.signed_in is False:
        return "bad", f"{version}: not signed in", f"run `{login}`"
    if status.signed_in is None:
        return "bad", f"{version}: could not tell whether it is signed in ({(status.detail or '')[:120]})", f"run `{name} --version` and `{login}` by hand"
    how = f", {status.method}" if status.method else ""
    tested = TESTED_VERSIONS.get(name)
    if tested and status.version and status.version != tested:
        return "warn", f"{version} signed in{how}; the app was tested with {tested}", f"if calls fail, install {name} {tested}"
    return "ok", f"{version} signed in{how}", ""


def _cli_checks(settings: Settings, cfg: Any, offline: bool) -> list[Check]:
    if offline:
        return [Check(n, n, "skip", "not checked (offline)") for n in ("claude", "codex")]
    try:
        statuses = _provider_statuses(settings, cfg)
    except Exception as exc:                                                # noqa: BLE001
        return [Check(n, n, "fail", f"could not probe the CLI ({type(exc).__name__}: {str(exc)[:150]})", "run `sutra-pro doctor --offline` and report this")
                for n in ("claude", "codex")]
    judged = {name: _judge(name, statuses.get(name), bool(getattr(cfg, "claude_desktop", False))) for name in ("claude", "codex")}
    any_usable = any(level in ("ok", "warn") for level, _, _ in judged.values())
    out = []
    for name, (level, detail, fix) in judged.items():
        if level == "bad":
            level = "warn" if any_usable else "fail"
            if level == "warn":
                detail += " (the other CLI can serve)"
        out.append(Check(name, name, {"ok": "ok", "warn": "warn", "fail": "fail"}[level], detail, fix))
    return out


def _check_gh(cfg: Any, offline: bool, env: Mapping[str, str], which: Callable[[str], str | None]) -> Check:
    if offline:
        return Check("gh", "gh", "skip", "not checked (offline)")
    exe = cfg.gh_exe
    if not which(exe):
        return Check("gh", "gh", "skip", "not installed (optional: only the GitHub tool uses it)")
    child_env = {**env, **dict(cfg.extra_env)}
    try:
        done = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=GH_TIMEOUT_S, env=child_env,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return Check("gh", "gh", "warn", f"installed, `gh auth status` did not run ({type(exc).__name__})", "run `gh auth status` by hand")
    if done.returncode == 0:
        return Check("gh", "gh", "ok", "installed and signed in")
    return Check("gh", "gh", "warn", "installed, not signed in (optional)", "run `gh auth login` if you want the GitHub tool")


def _check_chrome(effective_chrome: str, offline: bool, which: Callable[[str], str | None], exists: Callable[[str], bool]) -> Check:
    if offline:
        return Check("chrome", "Chrome", "skip", "not checked (offline)")
    named = os.path.expanduser((effective_chrome or "").strip())
    if named and exists(named):
        return Check("chrome", "Chrome", "ok", named)
    found = browser.find_chrome({}, exists=exists, which=which)          # the standard places (the named one was tried above)
    if found and not named:
        return Check("chrome", "Chrome", "ok", found)
    if found:
        return Check("chrome", "Chrome", "warn", f"J2_CHROME points to {named}, which does not exist (Chrome is at {found})",
                     f"`sutra-pro config set chrome '{found}'`, or unset J2_CHROME")
    why = f"J2_CHROME points to {named}, which does not exist; " if named else "not found; "
    return Check("chrome", "Chrome", "warn", why + "Audit will judge from code only (no screenshots)",
                 "install Google Chrome, or set its path: `sutra-pro config set chrome /path/to/chrome`")


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _check_port(env: Mapping[str, str], ports: Sequence[int]) -> Check:
    explicit = (env.get("SUTRA_PORT") or "").strip()
    if explicit:
        if explicit.isdigit() and _port_free(int(explicit)):
            return Check("port", "Port", "ok", f"{explicit} (SUTRA_PORT) is free")
        return Check("port", "Port", "warn", f"SUTRA_PORT={explicit} is busy or not a port; the server will refuse to start on it",
                     "unset SUTRA_PORT, or stop whatever uses it")
    free = [p for p in ports if _port_free(p)]
    if free:
        return Check("port", "Port", "ok", f"{free[0]} is free (range {ports[0]} to {ports[-1]})")
    return Check("port", "Port", "fail", f"every port from {ports[0]} to {ports[-1]} is busy", "stop the programs that use them, or set SUTRA_PORT")


def _check_instance(data_dir: Path) -> Check:
    if not lock.is_locked(data_dir):
        return Check("instance", "Second instance", "ok", "no other Sutra Pro runs on this data folder")
    holder = lock.read_holder(data_dir)
    if holder is not None and holder.pid == os.getpid():
        return Check("instance", "Second instance", "ok", "this process holds the data folder")
    where = f" on {holder.url} (pid {holder.pid})" if holder is not None and holder.url else ""
    return Check("instance", "Second instance", "warn", f"Sutra Pro already runs{where}; a second launch only opens it",
                 "`sutra-pro stop` to stop it, or use `sutra-pro open`")


def _check_library(data_dir: Path, seed: Path | None) -> Check:
    title = "Template library"
    missing = missing_seed_templates(data_dir, seed)
    if missing is None:
        return Check("library", title, "ok", "not created yet; the first run seeds it")
    library = data_dir / "library"
    try:
        _library_doc(library)
    except LibraryUnreadable as exc:
        return Check("library", title, "warn", f"{exc}; the seed cannot be synced into it",
                     "restore library/index.json from a backup (`sutra-pro config sync-library` leaves an index it cannot read alone)")
    versions = missing_seed_versions(data_dir, seed)
    run_templates = missing_seed_run_templates(data_dir, seed)
    if missing or versions or run_templates:
        names = [*missing, *versions, *run_templates]
        what = " and ".join(part for part in (f"{len(missing)} seed template(s)" if missing else "", f"{len(versions)} seed version(s)" if versions else "",
                                              f"{len(run_templates)} seed run template(s)" if run_templates else "") if part)
        return Check("library", title, "warn", f"{what} are missing from {library}: " + ", ".join(names[:3]) + (" ..." if len(names) > 3 else ""),
                     "run `sutra-pro config sync-library` (adds only what is missing, never overwrites)")
    return Check("library", title, "ok", "all seed templates, versions and run templates are present")


def _check_browser(offline: bool, platform: str | None, plist_path: Any, chrome_known: bool) -> Check:
    if offline:
        return Check("browser", "Default browser", "skip", "not checked (offline)")
    found = browser.default_browser(platform=platform, plist_path=plist_path)
    if found is None:
        return Check("browser", "Default browser", "skip", "not checked on this system")
    if found.chromium:
        return Check("browser", "Default browser", "ok", f"{found.name} (Chrome-based)")
    if chrome_known:
        return Check("browser", "Default browser", "ok", f"{found.name}; Sutra Pro opens Chrome instead (D92)")
    return Check("browser", "Default browser", "warn", f"{found.name}; only Chrome is measured, other browsers are not verified",
                 "install Google Chrome (Sutra Pro opens it), or open the page in Chrome yourself")


def _check_settings(settings: Settings, env: Mapping[str, str]) -> tuple[Check, str]:
    """The engine's setting layers must be valid, and `send_mode=live` needs the SMTP login. Returns the check and the effective `chrome`."""
    from sutra_app.engine.spec import EngineSettings, SettingsError, read_settings_file
    title = "Locked settings"
    effective = ""
    try:
        global_file = read_settings_file(settings.data_dir / "engine.json")
        layers = {"engine.json": EngineSettings.layered(env, global_file, None, {})}
        effective = layers["engine.json"].chrome
        departments = settings.departments_dir
        for path in sorted(departments.glob("*/engine.json")) if departments.is_dir() else []:
            layers[f"departments/{path.parent.name}/engine.json"] = EngineSettings.layered(env, global_file, read_settings_file(path), {})
    except (SettingsError, OSError) as exc:
        return Check("settings", title, "fail", str(exc)[:300], "correct the file, or set the field again with `sutra-pro config set <field> <value>`"), effective
    live = [name for name, eff in layers.items() if eff.send_mode == "live"]
    if live:
        have = {**read_env_file(settings.env_file), **{k: v for k, v in env.items() if k in SMTP_VARS}}
        missing = [v for v in SMTP_VARS if not (have.get(v) or "").strip()]
        if missing:
            return Check("settings", title, "fail", f"send_mode is live ({', '.join(live)}) but {', '.join(missing)} is not set",
                         f"put the J2_SMTP_* lines in {settings.env_file} (`sutra-pro config init` writes a template), or `sutra-pro config set send_mode dry-run`"), effective
        return Check("settings", title, "ok", "send_mode is live and the SMTP login is present"), effective
    return Check("settings", title, "ok", "valid (send_mode is not live)"), effective


# ---- the run ------------------------------------------------------------------------------------------------------------------

def run(settings: Settings, *, offline: bool = False, environ: Mapping[str, str] | None = None, config: Any = None,
        platform: str | None = None, ports: Sequence[int] = PORT_RANGE, python_version: Sequence[int] | None = None,
        plist_path: Any = None, seed: Path | None = None, min_free: int = MIN_FREE_BYTES,
        which: Callable[[str], str | None] = shutil.which, exists: Callable[[str], bool] = os.path.exists) -> Report:
    """All fourteen checks, in `CHECK_IDS` order. A check that raises becomes a failed check, never an exception."""
    env = os.environ if environ is None else environ
    version = tuple(python_version) if python_version is not None else tuple(sys.version_info[:3])
    data_dir = settings.data_dir
    if config is None:
        from sutra_app.connectors.discover import connector_config         # the CLIs where installers put them, as the app finds them
        config = connector_config(data_dir, environ=env)
    try:
        settings_check, chrome_path = _check_settings(settings, env)
    except Exception as exc:                                                # noqa: BLE001
        settings_check, chrome_path = Check("settings", "Locked settings", "fail", f"the check crashed: {type(exc).__name__}: {str(exc)[:200]}",
                                            "report this"), ""
    chrome = _check_chrome(chrome_path, offline, which, exists)
    claude_codex = _cli_checks(settings, config, offline)
    steps: list[tuple[str, Callable[[], Check]]] = [
        ("python", lambda: _check_python(version)),
        ("data_dir", lambda: _check_data_dir(data_dir)),
        ("disk", lambda: _check_disk(data_dir, min_free)),
        ("database", lambda: _check_database(settings)),
        ("env_file", lambda: _check_env_file(settings)),
        ("claude", lambda: claude_codex[0]),
        ("codex", lambda: claude_codex[1]),
        ("gh", lambda: _check_gh(config, offline, env, which)),
        ("chrome", lambda: chrome),
        ("port", lambda: _check_port(env, ports)),
        ("instance", lambda: _check_instance(data_dir)),
        ("library", lambda: _check_library(data_dir, seed)),
        ("browser", lambda: _check_browser(offline, platform, plist_path, chrome.status == "ok")),
        ("settings", lambda: settings_check),
    ]
    report = Report()
    for check_id, step in steps:
        try:
            report.checks.append(step())
        except Exception as exc:                                            # noqa: BLE001
            report.checks.append(Check(check_id, check_id, "fail", f"the check crashed: {type(exc).__name__}: {str(exc)[:200]}",
                                       "report this; the rest of the report is still valid"))
    return report
