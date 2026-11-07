"""`sutra-pro backup | restore` and the automatic backup before a schema upgrade (gaps G13, decisions D5, D88, D93, D94).

    sutra-pro backup [--to DIR] [--no-runs]     one `sutra-pro-backup-<UTC>.tar.gz` (mode 0600), default <data>/backups/
    sutra-pro restore FILE                      verify, stage, swap; the old folder is moved aside, never deleted
    before_upgrade(settings)                    called by `serve` before the app is built (cli.before_start)

What a backup holds, all relative to the data folder: `db.sqlite3` (a consistent copy made with `sqlite3.Connection.backup()`, so it is
WAL-safe and works while the server runs), `departments/**` (the run logs `run.stdout.log` / `run.stderr.log` only when younger than
7 days; `--no-runs` leaves every `runs/` folder out), `library/`, `agents/`, `connectors/policy.json`, `engine.json`, the owner's limits and
quiet hours (`limits.json`, `attention.json`), and last a
`MANIFEST.json` (format, app version, `user_version`, UTC time, every file with size and sha256). NEVER `.env`, `app.lock`, `app.pid`
or `logs/`: a backup is meant to be kept and copied around, and the override key and SMTP password live in `.env`
(`--include-env` is refused with that reason). Only regular files go in; links are skipped.

A file is copied to a scratch file first and hashed and archived from the copy, so a log that grows while the server runs cannot
make the manifest disagree with the archive.

Rotation: a backup written to the default folder keeps only the newest 7 `sutra-pro-backup-*.tar.gz` there (`prune_backups`); a backup
written with `--to` is the owner's own copy and is never rotated. The `pre-upgrade-*.sqlite3` files are never rotated.

Restore order (each step refuses before anything is touched): the instance lock must be free (it is held for the whole swap); the
manifest must be known and its `user_version` no newer than this build; every member must be a regular file named in the manifest
and every sha256 and size must match; the files go into a staging folder next to the data folder, the staged database must pass
`PRAGMA integrity_check`; then the data folder is renamed to `<data>.before-restore-<UTC>`, the staging folder takes its place, and
`.env` and `backups/` are carried over from the old folder (they are never in an archive). An older `user_version` is fine: the
server migrates it, after its own pre-upgrade backup.
"""
import argparse
import contextlib
import hashlib
import json
import os
from sutra_app import oslayer
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from sutra_app import __version__
from sutra_app.config import DB_FILENAME, Settings
from sutra_app.ops import cli, lock
from sutra_app.orchestrator import schema

__all__ = ["BackupError", "RestoreError", "BackupResult", "RestoreResult", "create_backup", "restore_backup", "before_upgrade",
           "prune_backups", "size_text", "snapshot_database", "connect_readonly", "collect_files", "register", "utc_stamp", "backups_dir",
           "MANIFEST_NAME", "FORMAT", "KEEP_AUTOMATIC", "LOG_MAX_AGE_S", "ENV_REFUSAL"]

FORMAT = 1
MANIFEST_NAME = "MANIFEST.json"
KEEP_AUTOMATIC = 7
LOG_MAX_AGE_S = 7 * 86400
BACKUP_GLOB = "sutra-pro-backup-*.tar.gz"
RUN_LOGS = ("run.stdout.log", "run.stderr.log")
ENV_REFUSAL = ("--include-env is refused: .env holds the owner override key and the SMTP password, and a backup is a file that gets copied, "
               "synced and mailed. Keep .env apart (config init writes a new one) or copy it by hand.")
_DIR_MODE = 0o700
_FILE_MODE = 0o600
_ROOT_FILES = ("engine.json", "connectors/policy.json", "limits.json", "attention.json")       # the owner's own choices: limits, quiet hours
_ROOT_TREES = ("departments", "library", "agents")


class BackupError(RuntimeError):
    """A backup could not be made. The message says why and what to do."""


class RestoreError(RuntimeError):
    """A restore was refused or failed. Nothing of the current data folder was changed unless the message says so."""


@dataclass(frozen=True)
class BackupResult:
    path: Path
    files: int
    size: int
    user_version: int
    rotated: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class RestoreResult:
    data_dir: Path
    moved_to: Path | None
    files: int
    user_version: int


# ---- small helpers ------------------------------------------------------------------------------------------------------------

def utc_stamp(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def backups_dir(settings: Settings) -> Path:
    return settings.data_dir / "backups"


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    """A connection that cannot write (also used by the exporter and prune). Raises FileNotFoundError for a missing file: sqlite would make one."""
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5.0, isolation_level=None)
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()
    except sqlite3.OperationalError:
        conn = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
        conn.execute("PRAGMA query_only=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def snapshot_database(src: Path, dest: Path) -> int:
    """Copy `src` to the new file `dest` with SQLite's online backup API (consistent even while a server writes; the WAL is folded in).
    Returns the copy's `user_version`. Raises BackupError."""
    try:
        source = connect_readonly(src)
    except FileNotFoundError:
        raise BackupError(f"there is no database at {src}; nothing to back up") from None
    except sqlite3.Error as exc:
        raise BackupError(f"the database {src} cannot be opened ({exc}); is it a Sutra database?") from None
    try:
        target = sqlite3.connect(str(dest), isolation_level=None)
        try:
            source.backup(target)
            return _user_version(target)
        finally:
            target.close()
    except sqlite3.Error as exc:
        raise BackupError(f"the database {src} could not be copied ({exc})") from None
    finally:
        source.close()


def _sha256_copy(src: Path, dest: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with open(src, "rb") as reader, open(dest, "wb") as writer:
        while chunk := reader.read(1 << 20):
            digest.update(chunk)
            writer.write(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _is_old_log(path: Path, now: float) -> bool:
    return path.name in RUN_LOGS and now - path.stat().st_mtime > LOG_MAX_AGE_S


def collect_files(data_dir: Path, *, include_runs: bool = True, now: float | None = None) -> list[tuple[str, Path]]:
    """(archive name, path) of every file a backup holds besides the database and the manifest, sorted by name."""
    when = time.time() if now is None else now
    found: dict[str, Path] = {}
    for rel in _ROOT_FILES:
        path = data_dir / rel
        if path.is_file() and not path.is_symlink():
            found[rel] = path
    for tree in _ROOT_TREES:
        top = data_dir / tree
        if not top.is_dir() or top.is_symlink():
            continue
        for root, dirs, names in os.walk(top, followlinks=False):
            rootp = Path(root)
            if tree == "departments" and not include_runs:
                dirs[:] = [d for d in dirs if not (d == "runs" and rootp.parent == top)]
            for name in names:
                path = rootp / name
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    if include_runs and _is_old_log(path, when):
                        continue
                except OSError:
                    continue
                found[path.relative_to(data_dir).as_posix()] = path
    return sorted(found.items())


def prune_backups(directory: Path, keep: int = KEEP_AUTOMATIC) -> list[Path]:
    """Delete the oldest `sutra-pro-backup-*.tar.gz` of `directory` beyond the newest `keep`; returns what it deleted."""
    if not directory.is_dir():
        return []
    entries = [p for p in directory.glob(BACKUP_GLOB) if p.is_file() and not p.is_symlink()]
    entries.sort(key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
    gone: list[Path] = []
    for path in entries[keep:]:
        with contextlib.suppress(OSError):
            path.unlink()
            gone.append(path)
    return gone


def _unique(directory: Path, stem: str, suffix: str) -> Path:
    path = directory / f"{stem}{suffix}"
    n = 1
    while path.exists():
        n += 1
        path = directory / f"{stem}-{n}{suffix}"
    return path


# ---- backup -------------------------------------------------------------------------------------------------------------------

def create_backup(settings: Settings, *, to: Path | None = None, include_runs: bool = True, now: Callable[[], float] = time.time) -> BackupResult:
    """Write one backup archive and (for the default folder) rotate. Raises BackupError."""
    data_dir = settings.data_dir
    started = now()
    target_dir = Path(to).expanduser() if to is not None else backups_dir(settings)
    try:
        target_dir.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(f"cannot create {target_dir}: {exc.strerror or exc}") from None
    final = _unique(target_dir, f"sutra-pro-backup-{utc_stamp(started)}", ".tar.gz")
    part = target_dir / f".{final.name}.part"
    entries: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="sutra-backup-", dir=target_dir) as scratch_name:
            scratch = Path(scratch_name)
            db_copy = scratch / DB_FILENAME
            user_version = snapshot_database(settings.db_path, db_copy)
            fd = os.open(part, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
            with os.fdopen(fd, "wb") as raw, tarfile.open(fileobj=raw, mode="w:gz") as tar:
                def add(arcname: str, source: Path, mtime: float) -> None:
                    copy = scratch / "file.tmp"
                    sha, size = _sha256_copy(source, copy)
                    info = tarfile.TarInfo(arcname)
                    info.size, info.mtime, info.mode = size, int(mtime), _FILE_MODE
                    with open(copy, "rb") as handle:
                        tar.addfile(info, handle)
                    copy.unlink()
                    entries.append({"path": arcname, "size": size, "sha256": sha})

                add(DB_FILENAME, db_copy, started)
                for arcname, path in collect_files(data_dir, include_runs=include_runs, now=started):
                    try:
                        add(arcname, path, path.stat().st_mtime)
                    except FileNotFoundError:
                        continue                                  # a live server removed it between the walk and the copy
                manifest = {"format": FORMAT, "app": "sutra-pro", "app_version": __version__, "user_version": user_version,
                            "created": _iso(started), "runs_included": include_runs, "files": entries}
                body = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
                info = tarfile.TarInfo(MANIFEST_NAME)
                info.size, info.mtime, info.mode = len(body), int(started), _FILE_MODE
                scratch_manifest = scratch / MANIFEST_NAME
                scratch_manifest.write_bytes(body)
                with open(scratch_manifest, "rb") as handle:
                    tar.addfile(info, handle)
        oslayer.replace(part, final)
    except BackupError:
        with contextlib.suppress(OSError):
            part.unlink()
        raise
    except OSError as exc:
        with contextlib.suppress(OSError):
            part.unlink()
        raise BackupError(f"the backup could not be written to {target_dir}: {exc.strerror or exc}") from None
    rotated = prune_backups(target_dir) if to is None else []
    return BackupResult(path=final, files=len(entries), size=final.stat().st_size, user_version=user_version, rotated=rotated)


def before_upgrade(settings: Settings) -> Path | None:
    """Called by `serve` before `create_app`. If the database exists and its `user_version` is lower than this build's migrations, write
    `<data>/backups/pre-upgrade-v<old>-to-v<new>.sqlite3` (database only; an older file of that name is replaced). Returns the path, or None
    when nothing needed doing. A failure raises BackupError with a doctor-style line: the start stops (a migration without a copy is not allowed)."""
    db_path = settings.db_path
    if not db_path.is_file():
        return None
    try:
        conn = connect_readonly(db_path)
        try:
            old = _user_version(conn)
        finally:
            conn.close()
    except (sqlite3.Error, FileNotFoundError):
        return None                       # unreadable: the app's own start-up reports it (SchemaError), the doctor says what to do
    new = schema.SCHEMA_VERSION
    if old >= new:
        return None
    from sutra_app.ops.doctor import Check
    target_dir = backups_dir(settings)
    final = target_dir / f"pre-upgrade-v{old}-to-v{new}.sqlite3"
    part = target_dir / f".{final.name}.part"
    try:
        target_dir.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
        with contextlib.suppress(FileNotFoundError):
            part.unlink()
        snapshot_database(db_path, part)
        os.chmod(part, _FILE_MODE)
        oslayer.replace(part, final)
    except (BackupError, OSError) as exc:
        with contextlib.suppress(OSError):
            part.unlink()
        why = str(exc) if isinstance(exc, BackupError) else (exc.strerror or str(exc))
        raise BackupError(Check("backup", "backup before the upgrade", "fail",
                                f"the database is at version {old} and this build needs {new}, but its copy could not be written to {final}: {why}",
                                f"free disk space or make {target_dir} writable, then start again; nothing was changed").line()) from None
    return final


# ---- restore ------------------------------------------------------------------------------------------------------------------

def _read_manifest(archive: Path) -> dict[str, Any]:
    try:
        with tarfile.open(archive, "r:gz") as tar:
            try:
                member = tar.getmember(MANIFEST_NAME)
            except KeyError:
                raise RestoreError(f"{archive} has no {MANIFEST_NAME}; it is not a Sutra Pro backup") from None
            handle = tar.extractfile(member)
            if handle is None or member.size > 64 * 1024 * 1024:
                raise RestoreError(f"{MANIFEST_NAME} in {archive} is not a regular file of a sane size")
            manifest = json.loads(handle.read().decode("utf-8"))
    except (tarfile.TarError, OSError, EOFError, UnicodeDecodeError, ValueError) as exc:
        raise RestoreError(f"{archive} cannot be read as a backup ({type(exc).__name__}: {str(exc)[:120]})") from None
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT or not isinstance(manifest.get("files"), list):
        raise RestoreError(f"{MANIFEST_NAME} in {archive} has an unknown format (this build reads format {FORMAT})")
    version = manifest.get("user_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise RestoreError(f"{MANIFEST_NAME} in {archive} has no usable user_version")
    return manifest


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "." not in path.parts and "\\" not in name and "\x00" not in name


def _manifest_files(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for item in manifest["files"]:
        if (not isinstance(item, dict) or not isinstance(item.get("path"), str) or not _safe_name(item["path"])
                or not isinstance(item.get("sha256"), str) or isinstance(item.get("size"), bool) or not isinstance(item.get("size"), int)):
            raise RestoreError(f"{MANIFEST_NAME} lists a file entry that is malformed or unsafe: {str(item)[:80]}")
        if item["path"] in files:
            raise RestoreError(f"{MANIFEST_NAME} lists {item['path']} twice")
        files[item["path"]] = item
    if DB_FILENAME not in files:
        raise RestoreError(f"{MANIFEST_NAME} does not list {DB_FILENAME}; the backup has no database")
    return files


def _stage(archive: Path, files: dict[str, dict[str, Any]], staging: Path) -> None:
    """Extract every listed file into `staging`, checking size and sha256; refuse anything not listed or not a plain file."""
    seen: set[str] = set()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if member.name == MANIFEST_NAME:
                continue
            if not member.isreg():
                raise RestoreError(f"{archive} holds {member.name!r}, which is not a plain file; refusing to unpack it")
            entry = files.get(member.name)
            if entry is None:
                raise RestoreError(f"{archive} holds {member.name!r}, which {MANIFEST_NAME} does not list; refusing to unpack it")
            if member.name in seen:
                raise RestoreError(f"{archive} holds {member.name!r} twice")
            seen.add(member.name)
            source = tar.extractfile(member)
            if source is None:
                raise RestoreError(f"{member.name} cannot be read from {archive}")
            dest = staging / member.name
            dest.parent.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
            digest, size = hashlib.sha256(), 0
            fd = os.open(dest, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
            with os.fdopen(fd, "wb") as out:
                while chunk := source.read(1 << 20):
                    digest.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
            if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                raise RestoreError(f"{member.name} does not match its checksum in {MANIFEST_NAME}; the backup is damaged. Nothing was changed")
    missing = sorted(set(files) - seen)
    if missing:
        raise RestoreError(f"the backup lacks {len(missing)} file(s) its manifest lists (first: {missing[0]}); it is incomplete. Nothing was changed")


def _check_staged_database(path: Path, manifest_version: int) -> None:
    try:
        conn = sqlite3.connect(str(path), isolation_level=None)
        try:
            verdict = conn.execute("PRAGMA integrity_check").fetchone()[0]
            actual = _user_version(conn)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise RestoreError(f"the database in the backup cannot be opened ({exc}). Nothing was changed") from None
    if verdict != "ok":
        raise RestoreError(f"the database in the backup failed its integrity check ({str(verdict)[:100]}). Nothing was changed")
    if actual != manifest_version:
        raise RestoreError(f"the database in the backup is at version {actual} but the manifest says {manifest_version}. Nothing was changed")


def restore_backup(settings: Settings, archive: Path, *, now: Callable[[], float] = time.time) -> RestoreResult:
    """Restore `archive` into `settings.data_dir`. Raises RestoreError (the current folder is untouched, or restored, when it does)."""
    data_dir = settings.data_dir
    archive = Path(archive).expanduser()
    if not archive.is_file():
        raise RestoreError(f"there is no backup file {archive}")
    held = None
    if data_dir.exists():
        held = lock.InstanceLock(data_dir)
        if not held.acquire():
            holder = lock.read_holder(data_dir)
            where = f" on http://127.0.0.1:{holder.port}/ (pid {holder.pid})" if holder is not None and holder.port else ""
            raise RestoreError(f"Sutra Pro is running{where} on {data_dir}; stop it first (`sutra-pro stop`). Nothing was changed")
    try:
        manifest = _read_manifest(archive)
        if manifest["user_version"] > schema.SCHEMA_VERSION:
            raise RestoreError(f"this backup was made by a newer Sutra Pro (database version {manifest['user_version']}, this build reads up to "
                               f"{schema.SCHEMA_VERSION}); update the app first. Nothing was changed")
        files = _manifest_files(manifest)
        stamp = utc_stamp(now())
        staging = _unique(data_dir.parent, f"{data_dir.name}.restore-{stamp}", "")
        try:
            data_dir.parent.mkdir(parents=True, exist_ok=True)
            staging.mkdir(mode=_DIR_MODE)
            _stage(archive, files, staging)
            _check_staged_database(staging / DB_FILENAME, manifest["user_version"])
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)         # our own half-built folder, never the owner's data
            raise
        moved = None
        try:
            if data_dir.exists():
                moved = _unique(data_dir.parent, f"{data_dir.name}.before-restore-{stamp}", "")
                os.rename(data_dir, moved)
            try:
                os.rename(staging, data_dir)
            except OSError:
                if moved is not None:
                    os.rename(moved, data_dir)
                raise
        except OSError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise RestoreError(f"the restored folder could not be put in place ({exc.strerror or exc}); the current data was left as it was") from None
        if moved is not None:
            _carry_over(moved, data_dir)
        return RestoreResult(data_dir=data_dir, moved_to=moved, files=len(files), user_version=manifest["user_version"])
    finally:
        if held is not None:
            held.release()


def _carry_over(old: Path, new: Path) -> None:
    """What an archive never holds but the owner still needs: `backups/` (moved: it can be large) and `.env` (copied)."""
    with contextlib.suppress(OSError):
        if (old / "backups").is_dir() and not (new / "backups").exists():
            os.rename(old / "backups", new / "backups")
    with contextlib.suppress(OSError):
        env = old / ".env"
        if env.is_file() and not env.is_symlink() and not (new / ".env").exists():
            shutil.copy2(env, new / ".env")


# ---- the commands -------------------------------------------------------------------------------------------------------------

def size_text(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def cmd_backup(args: argparse.Namespace) -> int:
    if args.include_env:
        print(f"sutra-pro: {ENV_REFUSAL}", file=sys.stderr)
        return 2
    settings = cli.load_settings(args)
    if settings is None:
        return 2
    try:
        result = create_backup(settings, to=args.to, include_runs=not args.no_runs)
    except BackupError as exc:
        print(f"sutra-pro: {exc}", file=sys.stderr)
        return 1
    live = lock.is_locked(settings.data_dir)
    lines = [f"Backup written: {result.path} ({size_text(result.size)}, {result.files} files, database version {result.user_version}"
             + (", server running: the database copy is consistent" if live else "") + ").",
             "Not in it: .env, logs and the instance lock files." + (" Run logs older than 7 days and every runs/ folder were left out (--no-runs)."
                                                                       if args.no_runs else " Run logs older than 7 days were left out.")]
    if result.rotated:
        lines.append(f"Removed {len(result.rotated)} older backup(s); the newest {KEEP_AUTOMATIC} are kept.")
    cli.emit(args, {"path": str(result.path), "size": result.size, "files": result.files, "user_version": result.user_version,
                    "rotated": [str(p) for p in result.rotated], "server_running": live}, lines)
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    settings = cli.load_settings(args)
    if settings is None:
        return 2
    try:
        result = restore_backup(settings, args.file)
    except RestoreError as exc:
        print(f"sutra-pro: {exc}", file=sys.stderr)
        return 1
    lines = [f"Restored {result.files} files (database version {result.user_version}) into {result.data_dir}."]
    if result.moved_to is not None:
        lines.append(f"The previous folder is kept at {result.moved_to}; delete it yourself when you are sure.")
    lines.append("Start Sutra Pro again; it migrates an older database after its own backup.")
    cli.emit(args, {"data_dir": str(result.data_dir), "moved_to": str(result.moved_to) if result.moved_to else None, "files": result.files,
                    "user_version": result.user_version}, lines)
    return 0


def register(sub: Any) -> None:
    """Add `backup` and `restore` to the CLI's subparsers (the `register(sub)` contract of ops.cli)."""
    common = [cli.common_parser()]
    p = sub.add_parser("backup", parents=common, help="write a backup archive (database, teams, library); works while the server runs")
    p.add_argument("--to", type=Path, metavar="DIR", help="write into DIR instead of <data>/backups (older backups there are then not rotated)")
    p.add_argument("--no-runs", action="store_true", help="leave every team's runs/ folder out (much smaller; the chart, chats and atom log stay in the database)")
    p.add_argument("--include-env", action="store_true", help="refused: .env holds secrets and is never put in a backup")
    p.set_defaults(func=cmd_backup)
    p = sub.add_parser("restore", parents=common, help="restore a backup into the data folder (the old folder is moved aside, never deleted)")
    p.add_argument("file", type=Path, help="a sutra-pro-backup-*.tar.gz")
    p.set_defaults(func=cmd_restore)
