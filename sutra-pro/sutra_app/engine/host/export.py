"""A finished run's results into its project's folder (named projects, R1.12 and R1.14, D428): the `export` finish step.

    export.step(host)                                   # finish.STEPS: only a run that ended done / done_with_open_items gets here
    export.export_run(run_dir, folder, run_id, rows)    # ExportResult(new, updated, unchanged, outside, failed)

The run's deliverables (each deliverable row's file, the `.docx` beside a document, every file of a folder output) are copied into the team's
OWN folder (`departments/<id>/workdir.json`, never the app-wide fallback: results never land in another project's folder) under the same
relative paths. Sutra's records stay in the run: `*.json`, `*.jsonl`, `site/`, `out/`, dotfiles. A Read only folder gets nothing (the owner
capped what Sutra may do there).

`<folder>/.sutra/manifest.json` = {"version": 1, "run_id", "files": {path: sha256}} is what Sutra last wrote there. A target that exists and is
not in it (a file Sutra never wrote), or whose bytes differ from it (the owner changed it since), is never touched: the chat names it. Each
file is written through a temp file in its own folder and an atomic replace; one that cannot be written (open in another program on Windows)
is named and the rest still go. `<run>/export.json` records what happened, for the run history and the PRD's metrics.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from sutra_app import oslayer

from .finish import Skip

__all__ = ["ExportResult", "Manifest", "deliverable_files", "export_run", "import_from_folder", "lines", "step", "MANIFEST_PARTS", "RECORD"]

log = logging.getLogger(__name__)
MANIFEST_PARTS = (".sutra", "manifest.json")
RECORD = "export.json"
NAMED = 10                                         # files named one by one in the chat; the rest are counted
_RECORD_SUFFIXES = (".json", ".jsonl")
_RECORD_TOPS = ("site", "out")


@dataclass(frozen=True)
class ExportResult:
    new: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    outside: list[str] = field(default_factory=list)       # there, and not Sutra's to write (never written, or changed since)
    failed: list[str] = field(default_factory=list)


def _sha(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _is_record(rel: str) -> bool:
    parts = rel.split("/")
    return (rel.endswith(_RECORD_SUFFIXES) or parts[0] in _RECORD_TOPS or any(p.startswith(".") for p in parts) or ".." in parts)


def _walk(run_dir: Path, top: str) -> set[str]:
    """Every file of a folder output, at any depth, with `/`: a built app keeps its configs (`package.json`, `config/*.json`). Dotfiles and
    dot-folders (an app's `.env`, `.git`) and links are left out."""
    found: set[str] = set()
    base = run_dir / top
    if not base.is_dir() or base.is_symlink():
        return found
    for here, dirs, files in os.walk(base, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith(".") and not os.path.islink(os.path.join(here, d))]
        for name in files:
            path = Path(here) / name
            if name.startswith(".") or path.is_symlink():
                continue
            found.add(path.relative_to(run_dir).as_posix())
    return found


def deliverable_files(run_dir: Path, rows: list[dict]) -> list[str]:
    """The run's deliverables as relative paths with `/`, sorted: each row's file that is not a record, the `.docx` beside a document, and
    the whole folder of a folder output (form `agent`). The record rules (`*.json`, `site/`, `out/`) are the run's top level only: inside an
    app's folder a JSON file is the app's."""
    run_dir = Path(run_dir)
    out: set[str] = set()
    for row in rows or []:
        rel = str((row or {}).get("file") or "").replace("\\", "/").lstrip("/")
        if (row or {}).get("form") == "agent":
            top = rel.split("/")[0]
            if top and not top.startswith(".") and top not in _RECORD_TOPS and ".." not in rel.split("/") and ":" not in top:
                out |= _walk(run_dir, top)
            continue
        if not rel or _is_record(rel):
            continue
        src = run_dir / rel
        if src.is_file() and not src.is_symlink():
            out.add(rel)
        if rel.endswith(".md"):
            docx = rel[:-3] + ".docx"
            if (run_dir / docx).is_file() and not (run_dir / docx).is_symlink():
                out.add(docx)
    return sorted(out)


class Manifest:
    """What Sutra last wrote into a project folder. A missing or damaged file is an empty manifest: then nothing there is Sutra's."""

    def __init__(self, files: Optional[dict[str, str]] = None, run_id: str = "") -> None:
        self.files = dict(files or {})
        self.run_id = run_id

    @staticmethod
    def path(folder: Path) -> Path:
        return Path(folder).joinpath(*MANIFEST_PARTS)

    @classmethod
    def load(cls, folder: Path) -> "Manifest":
        try:
            body = json.loads(cls.path(folder).read_text(encoding="utf-8"))
            files = body.get("files") if isinstance(body, dict) else None
            if isinstance(files, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
                return cls(files, str(body.get("run_id") or ""))
        except (OSError, ValueError):
            pass
        return cls()

    def save(self, folder: Path) -> None:
        target = self.path(folder)
        _write_bytes(target, (json.dumps({"version": 1, "run_id": self.run_id, "files": dict(sorted(self.files.items()))}, indent=2) + "\n").encode("utf-8"))


def _write_bytes(target: Path, data: bytes) -> None:
    """Write through a temp file in the target's own folder and an atomic replace; the temp never stays behind."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
        oslayer.replace(tmp, target)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _inside(folder: Path, rel: str) -> Optional[Path]:
    """The target of `rel` in `folder`, or None when it would leave the folder."""
    root = Path(os.path.realpath(folder))
    target = Path(os.path.realpath(root / rel))
    try:
        return target if os.path.commonpath([str(root), str(target)]) == str(root) and target != root else None
    except ValueError:                                        # another drive on Windows
        return None


def export_run(run_dir: Path, folder: Path, run_id: str, rows: list[dict]) -> ExportResult:
    """Copy the run's deliverables into `folder` (see the module text); the manifest is rewritten once, after every file."""
    run_dir, folder = Path(run_dir), Path(folder)
    manifest = Manifest.load(folder)
    result = ExportResult()
    for rel in deliverable_files(run_dir, rows):
        target = _inside(folder, rel)
        if target is None:
            continue
        try:
            data = (run_dir / rel).read_bytes()
        except OSError:
            result.failed.append(rel)
            continue
        fresh = hashlib.sha256(data).hexdigest()
        if target.exists():
            on_disk = _sha(target)
            if rel not in manifest.files or on_disk != manifest.files[rel]:
                result.outside.append(rel)                     # the owner's file, or one the owner changed since Sutra wrote it
                continue
            if on_disk == fresh:
                result.unchanged.append(rel)
                continue
            bucket = result.updated
        else:
            bucket = result.new
        try:
            _write_bytes(target, data)
        except OSError as exc:
            log.info("could not write %s into the project folder: %s", rel, exc)
            result.failed.append(rel)
            continue
        manifest.files[rel] = fresh
        bucket.append(rel)
    manifest.run_id = run_id
    if result.new or result.updated or not Manifest.path(folder).exists():
        manifest.save(folder)
    return result


def import_from_folder(folder: Path, run_dir: Path, *, rebase: bool) -> list[str]:
    """Phase 2 (R2.2, R2.4): before a follow-up starts, the files Sutra wrote into the project folder (the manifest's paths, nothing else)
    are copied from the folder into the new run, so an edit the owner made by hand is what the team starts from. Returns the paths whose
    bytes differed from the run's copy (the owner's edits), sorted. With `rebase` (the team may change the folder) the manifest takes the
    folder's bytes as Sutra's: the follow-up's changes can then be written back over the owner's edit it started from."""
    folder, run_dir = Path(folder), Path(run_dir)
    manifest = Manifest.load(folder)
    edited: list[str] = []
    changed = False
    for rel in sorted(manifest.files):
        source = _inside(folder, rel)
        target = _inside(run_dir, rel)
        if source is None or target is None or not source.is_file() or source.is_symlink():
            continue
        try:
            data = source.read_bytes()
        except OSError:
            continue
        fresh = hashlib.sha256(data).hexdigest()
        if _sha(target) != fresh:
            try:
                _write_bytes(target, data)
            except OSError:
                log.info("could not bring %s back from the project folder", rel)
                continue
            if target.exists():
                edited.append(rel)
        if rebase and manifest.files.get(rel) != fresh:
            manifest.files[rel] = fresh
            changed = True
    if changed:
        try:
            manifest.save(folder)
        except OSError:
            log.warning("could not update the project folder's manifest", exc_info=True)
    return edited


def _rows(run_dir: Path, own: Optional[str] = None) -> list[dict]:
    """What the run made for the owner: the Artifacts tab's deliverable rows, every file of a folder output (form `agent`, the app a team
    built), and the run's own result (`own`, from the run's output; else the one `deliverable.json` names): a single-output run such as
    project work has no deliverable row for it. J2 is imported here, after the host set its environment."""
    from .. import j2_artifacts
    listed = j2_artifacts.listing(str(run_dir))
    rows = list(listed.get("deliverables") or []) + [r for r in listed.get("records") or [] if r.get("form") == "agent"]
    try:                                          # a folder output whose files all sit in subfolders has no row: find it from its type
        types = j2_artifacts.load_types(str(run_dir))["types"]
    except Exception:  # noqa: BLE001 - the types list is a courtesy here; the rows above still go
        types = []
    for t in types:
        pattern = str(t.get("file") or "")
        if t.get("form") == "agent" and pattern.endswith("/*") and (Path(run_dir) / pattern[:-2]).is_dir():
            rows.append({"file": pattern[:-2], "form": "agent"})
    if not own:
        try:
            own = json.loads((Path(run_dir) / "deliverable.json").read_text(encoding="utf-8")).get("file")
        except (OSError, ValueError, AttributeError):
            own = None
    if isinstance(own, str) and own:
        rows.append({"file": own, "form": "document"})
    return rows


def _post(host: Any, text: str) -> None:
    run = getattr(host, "run", None)
    if run is not None and hasattr(run, "post"):
        try:
            run.post("system", text)
        except Exception:  # noqa: BLE001 - a chat line never fails the end of a run
            log.warning("could not post %r", text, exc_info=True)


def lines(folder: str, result: ExportResult, name: str = "") -> list[str]:
    """The run chat's lines about the save (R1.12, R1.14) and, for a follow-up, which files it changed (R2.6)."""
    out = []
    saved = len(result.new) + len(result.updated)
    if saved:
        out.append(f"Saved to {folder}: {saved} file{'s' if saved != 1 else ''} ({len(result.new)} new, {len(result.updated)} updated).")
    if result.updated:
        shown = ", ".join(result.updated[:NAMED]) + (f" and {len(result.updated) - NAMED} more" if len(result.updated) > NAMED else "")
        out.append(f"Changed in {name or folder}: {shown}")
    out += [f"Not updated: {rel} was changed outside Sutra" for rel in result.outside[:NAMED]]
    if len(result.outside) > NAMED:
        out.append(f"and {len(result.outside) - NAMED} more not updated")
    out += [f"Not saved: {rel} could not be written" for rel in result.failed[:NAMED]]
    return out


def step(host: Any) -> dict:
    """The `export` finish step (finish.STEPS)."""
    from sutra_app.connectors.workdir import WorkFolder
    dept = str(getattr(getattr(host, "task", None), "dept_id", "") or "")
    if not dept:
        raise Skip("no project folder")
    store = WorkFolder(host.paths.data_dir, dept_id=dept)
    stored = store.stored()
    if stored is None:
        raise Skip("no project folder")
    if not os.path.isdir(stored):
        _post(host, f"Not saved: {stored} is not there any more")
        raise Skip("the project folder is not there")
    grant = store.grant()
    if grant is None:
        raise Skip(store.problem() or "the project folder cannot be used")
    if not getattr(grant, "edit", False):
        raise Skip("the project may only read its folder")
    run_dir = Path(host.paths.run_dir)
    run_id = str(getattr(host.paths, "run_id", "") or getattr(host.task, "run_id", ""))
    out = getattr(getattr(host, "run", None), "out", None)
    own = out.get("file") if isinstance(out, dict) and out.get("deliver") and isinstance(out.get("file"), str) else None
    result = export_run(run_dir, Path(str(grant)), run_id, _rows(run_dir, own))
    record = {"folder": str(grant), **asdict(result)}
    try:
        _write_bytes(run_dir / RECORD, (json.dumps(record, indent=2) + "\n").encode("utf-8"))
    except OSError:
        log.warning("could not write %s", RECORD, exc_info=True)
    for text in lines(str(grant), result, str(getattr(getattr(host, "task", None), "dept_label", "") or "")):
        _post(host, text)
    return {key: len(value) for key, value in asdict(result).items()}
