"""`sutra-pro prune [--older-than 90d] [--dry-run] [--yes]`: remove the bulky evidence of old FINISHED runs (gaps G13, decisions D60, D93).

    sutra-pro prune                    a dry run: lists what would go and how much space it frees (the default)
    sutra-pro prune --older-than 30d --yes

Only files of runs whose task is over (done, done_with_open_items, stopped, crashed, cancelled) and ended more than the age ago:
screenshots (`site/shots/**`, `screenshots/**`, `*.png` in the run folder), `trace.jsonl`, `events.jsonl` (only when the task's
`events_offset` equals the file's size, that is when the server has projected every byte of it), `run.stdout.log`, `run.stderr.log`.
Plus the automatic backups beyond the newest 7 in `<data>/backups/` (the `pre-upgrade-*.sqlite3` copies are kept).

Never touched: `summary.json`, `goal.json`, site versions, documents, `chat.jsonl`, `calls.jsonl`, anything of a run that is still open or
that the database does not list, links, and every database row. The Atom log and the usage table are append-only (D60) and stay (D93);
the command prints their row counts and sizes. `VACUUM` runs only on `--yes`, only when the instance lock is free, and it holds
that lock while it works, so no server starts in the middle.
"""
import argparse
import os
import re
import sqlite3
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sutra_app.config import Settings
from sutra_app.engine.spec import is_dept_id, is_run_id
from sutra_app.ops import backup, cli, lock

__all__ = ["parse_age", "plan", "apply", "Plan", "Candidate", "table_stats", "register", "DEFAULT_AGE", "FINISHED"]

DEFAULT_AGE = "90d"
FINISHED = ("done", "done_with_open_items", "stopped", "crashed", "cancelled")
ALWAYS = ("trace.jsonl", "run.stdout.log", "run.stderr.log")
SHOT_DIRS = (("site", "shots"), ("screenshots",))
LEDGER_TABLES = ("atom_ledger", "usage_ledger")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}


@dataclass(frozen=True)
class Candidate:
    path: Path
    size: int
    dept_id: str
    run_id: str
    what: str                        # screenshot | trace | events | log


@dataclass
class Plan:
    older_than_s: float
    candidates: list[Candidate] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)                 # one line per file left alone on purpose (events not fully projected)
    runs: int = 0                                                  # finished runs old enough to look at
    backups: list[Path] = field(default_factory=list)             # old automatic backups beyond the newest 7
    backup_bytes: int = 0
    tables: dict[str, dict[str, int | None]] = field(default_factory=dict)

    @property
    def bytes(self) -> int:
        return sum(c.size for c in self.candidates) + self.backup_bytes


def parse_age(text: str) -> float:
    """`90d`, `36h`, `2w`, `45m`, `600s`; a bare number is days. Raises ValueError with a message fit for the user."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhdw]?)\s*", str(text).lower())
    if match is None:
        raise ValueError(f"cannot read the age {str(text)[:30]!r}; write it like 90d, 36h or 2w")
    seconds = float(match.group(1)) * _UNITS[match.group(2) or "d"]
    if seconds <= 0:
        raise ValueError("the age must be more than zero")
    return seconds


def table_stats(conn: sqlite3.Connection) -> dict[str, dict[str, int | None]]:
    """Row count and bytes of the two append-only tables (their indexes included when SQLite offers `dbstat`, else the payload size)."""
    stats: dict[str, dict[str, int | None]] = {}
    for table in LEDGER_TABLES:
        try:
            rows = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except sqlite3.Error:
            stats[table] = {"rows": 0, "bytes": None}
            continue
        size: int | None
        try:
            names = [table] + [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name = ?", (table,))]
            marks = ",".join("?" for _ in names)
            size = conn.execute(f"SELECT SUM(pgsize) FROM dbstat WHERE name IN ({marks})", names).fetchone()[0]
            size = int(size) if size is not None else None
        except sqlite3.Error:
            size = None
        stats[table] = {"rows": rows, "bytes": size}
    return stats


def _finished_runs(conn: sqlite3.Connection, cutoff: float) -> list[sqlite3.Row]:
    marks = ",".join("?" for _ in FINISHED)
    return conn.execute(
        f"SELECT id, dept_id, run_id, events_offset, COALESCE(ended_at, last_event_at, created_at) AS finished FROM tasks"
        f" WHERE run_id IS NOT NULL AND status IN ({marks}) AND COALESCE(ended_at, last_event_at, created_at) < ? ORDER BY finished, id",
        (*FINISHED, cutoff)).fetchall()


def _plain_files(folder: Path):
    if folder.is_symlink() or not folder.is_dir():
        return
    for root, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
        for name in names:
            path = Path(root) / name
            if not path.is_symlink() and path.is_file():
                yield path


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def plan(settings: Settings, older_than_s: float, *, now: Callable[[], float] = time.time) -> Plan:
    """What `prune` would remove. Reads the database and the file system; changes nothing."""
    result = Plan(older_than_s=older_than_s)
    cutoff = now() - older_than_s
    try:
        conn = backup.connect_readonly(settings.db_path)
    except FileNotFoundError:
        conn = None
    except sqlite3.Error:
        conn = None
    if conn is not None:
        try:
            result.tables = table_stats(conn)
            for row in _finished_runs(conn, cutoff):
                if not is_dept_id(row["dept_id"]) or not is_run_id(row["run_id"]):
                    continue
                run_dir = settings.departments_dir / row["dept_id"] / "runs" / row["run_id"]
                if run_dir.is_symlink() or not run_dir.is_dir():
                    continue
                result.runs += 1
                _plan_run(result, run_dir, row)
        finally:
            conn.close()
    stale = backups_beyond(settings)
    result.backups = stale
    result.backup_bytes = sum(_size_of(p) for p in stale)
    return result


def _plan_run(result: Plan, run_dir: Path, row: sqlite3.Row) -> None:
    dept, run = row["dept_id"], row["run_id"]

    def add(path: Path, what: str) -> None:
        result.candidates.append(Candidate(path=path, size=_size_of(path), dept_id=dept, run_id=run, what=what))

    for name in ALWAYS:
        path = run_dir / name
        if path.is_file() and not path.is_symlink():
            add(path, "trace" if name == "trace.jsonl" else "log")
    events = run_dir / "events.jsonl"
    if events.is_file() and not events.is_symlink():
        size = _size_of(events)
        if size == row["events_offset"]:
            add(events, "events")
        else:
            result.kept.append(f"{dept}/{run}: events.jsonl kept (the server has projected {row['events_offset']} of its {size} bytes)")
    for png in run_dir.glob("*.png"):
        if png.is_file() and not png.is_symlink():
            add(png, "screenshot")
    for parts in SHOT_DIRS:
        for path in _plain_files(run_dir.joinpath(*parts)):
            add(path, "screenshot")


def backups_beyond(settings: Settings, keep: int = backup.KEEP_AUTOMATIC) -> list[Path]:
    """The automatic backups (not the pre-upgrade copies) older than the newest `keep`."""
    folder = backup.backups_dir(settings)
    if not folder.is_dir():
        return []
    entries = [p for p in folder.glob(backup.BACKUP_GLOB) if p.is_file() and not p.is_symlink()]
    entries.sort(key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
    return entries[keep:]


def apply(settings: Settings, found: Plan) -> tuple[int, int]:
    """Delete what `plan` found. Returns (files removed, bytes freed). A file that is already gone is not an error."""
    removed = freed = 0
    for path, size in [(c.path, c.size) for c in found.candidates] + [(p, _size_of(p)) for p in found.backups]:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            continue
        removed += 1
        freed += size
    return removed, freed


def vacuum(settings: Settings) -> tuple[bool, str]:
    """VACUUM while holding the instance lock. (done, why not or the size change)."""
    if not settings.db_path.is_file():
        return False, "there is no database"
    held = lock.InstanceLock(settings.data_dir)
    if not held.acquire():
        return False, "the server is running (VACUUM needs the database to itself); run it again after `sutra-pro stop`"
    try:
        before = settings.db_path.stat().st_size
        conn = sqlite3.connect(str(settings.db_path), isolation_level=None, timeout=5.0)
        try:
            conn.execute("VACUUM")
        finally:
            conn.close()
        return True, f"{backup.size_text(before)} -> {backup.size_text(settings.db_path.stat().st_size)}"
    except sqlite3.Error as exc:
        return False, f"VACUUM failed ({exc})"
    finally:
        held.release()


def _label(table: str, info: dict[str, int | None]) -> str:
    size = "size unknown" if info["bytes"] is None else backup.size_text(int(info["bytes"]))
    return f"  {table}: {info['rows']} rows, {size} (append-only, kept)"


def cmd_prune(args: argparse.Namespace) -> int:
    if args.yes and args.dry_run:
        print("sutra-pro: --dry-run and --yes contradict each other; leave out --dry-run to apply, or leave out --yes to look", file=sys.stderr)
        return 2
    try:
        age = parse_age(args.older_than)
    except ValueError as exc:
        print(f"sutra-pro: {exc}", file=sys.stderr)
        return 2
    settings = cli.load_settings(args)
    if settings is None:
        return 2
    try:
        found = plan(settings, age)
    except sqlite3.Error as exc:
        print(f"sutra-pro: the database could not be read ({exc})", file=sys.stderr)
        return 1
    apply_now = bool(args.yes)
    removed = freed = 0
    if apply_now:
        removed, freed = apply(settings, found)
    lines = [f"{'Pruning' if apply_now else 'Dry run:'} finished runs older than {args.older_than} ({found.runs} run(s) looked at)."]
    by_run: dict[tuple[str, str], list[Candidate]] = {}
    for item in found.candidates:
        by_run.setdefault((item.dept_id, item.run_id), []).append(item)
    for (dept, run), items in by_run.items():
        parts = ", ".join(f"{item.path.name} {backup.size_text(item.size)}" for item in items[:4]) + (f", +{len(items) - 4} more" if len(items) > 4 else "")
        lines.append(f"  {dept}/{run}: {parts}")
    lines += [f"  {note}" for note in found.kept]
    for path in found.backups:
        lines.append(f"  old backup {path.name} {backup.size_text(_size_of(path))}")
    total = len(found.candidates) + len(found.backups)
    if apply_now:
        lines.append(f"Removed {removed} of {total} file(s), freed {backup.size_text(freed)}.")
    else:
        lines.append(f"Would remove {total} file(s) and free {backup.size_text(found.bytes)}. Nothing was deleted; add --yes to do it.")
    lines.append("Kept in the database (append-only, D60; no row retention in version 1, D93):")
    lines += [_label(table, info) for table, info in found.tables.items()]
    vacuumed: dict[str, Any] = {"done": False, "note": ""}
    if apply_now:
        done, note = vacuum(settings)
        vacuumed = {"done": done, "note": note}
        lines.append(f"VACUUM: {'done, ' if done else 'skipped, '}{note}")
    else:
        lines.append("VACUUM runs only with --yes and only while the server is stopped." + (" (The server is running now.)" if lock.is_locked(settings.data_dir) else ""))
    cli.emit(args, {"applied": apply_now, "older_than": args.older_than, "runs": found.runs, "files": total, "bytes": found.bytes,
                    "removed": removed, "freed": freed, "kept": found.kept, "backups": [str(p) for p in found.backups],
                    "tables": found.tables, "vacuum": vacuumed,
                    "candidates": [{"path": str(c.path), "size": c.size, "what": c.what, "dept": c.dept_id, "run": c.run_id} for c in found.candidates]}, lines)
    return 0


def register(sub: Any) -> None:
    """Add `prune` to the CLI's subparsers (the `register(sub)` contract of ops.cli)."""
    p = sub.add_parser("prune", parents=[cli.common_parser()], help="remove screenshots, traces, event files and logs of old finished runs (dry run unless --yes)")
    p.add_argument("--older-than", default=DEFAULT_AGE, metavar="AGE", help=f"how long ago the run ended: 90d, 36h, 2w (default {DEFAULT_AGE})")
    p.add_argument("--dry-run", action="store_true", help="only list what would go (this is the default)")
    p.add_argument("--yes", action="store_true", help="really delete")
    p.set_defaults(func=cmd_prune)
