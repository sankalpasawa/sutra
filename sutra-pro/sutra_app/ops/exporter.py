"""`sutra-pro export chart | team | usage`: read-only copies of what the owner may want to keep or hand on (gaps G13).

    sutra-pro export chart [--out FILE]          the head org chart and the whole change log, one JSON file (default ./sutra-pro-chart-<UTC>.json)
    sutra-pro export team DEPT [--out DIR]       the team's last finished run: charter, site, documents, summary, and its Atom log rows
    sutra-pro export usage --csv [--out FILE]    every usage_ledger row as CSV (default ./sutra-pro-usage-<UTC>.csv)

`--out -` writes a chart or usage export to standard output. An existing output file or a non-empty output folder is never overwritten.
Nothing in the data folder is changed: the database is opened read-only and files are only read.

Chart file: `{export, export_version, schemas: {org_chart, chart_change}, exported, head, head_sha256, changes: [...]}`. `head` is the library
`OrgChart` and each change carries the library `ChartChange` (`change`; the bootstrap row 1 has `change` null and the seed `OrgChart` in `seed_chart`) beside the log columns (status, actor, shas, summary, times). Both models
are validated on the way out, so a damaged row stops the export instead of landing in a file.

Team folder: `goal.json` (and `goal.v<N>.json`), `summary.json`, `documents.json`, `artifacts.json`, `artifacts/`, `site/` (the page versions and
documents, without `site/shots/`), `atom-ledger.jsonl` (one `atom_ledger` row per line, body parsed) and `EXPORT.json` (what, from which run, the files).
"""
import argparse
import csv
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from sutra_app import __version__
from sutra_app.config import Settings
from sutra_app.engine.spec import is_dept_id, is_run_id
from sutra_app.library.org_chart import ChartChange, OrgChart
from sutra_app.ops import backup, cli

__all__ = ["ExportError", "export_chart", "export_team", "export_usage", "register", "CHART_EXPORT_VERSION", "USAGE_COLUMNS"]

CHART_EXPORT_VERSION = 1
GOOD_END = ("done", "done_with_open_items")
USAGE_COLUMNS = ("id", "at", "provider", "model", "purpose", "session_id", "node_id", "task_id", "dept_id", "fn", "step", "atom_id", "usd",
                 "tokens_in", "tokens_out", "seconds", "ok", "how", "call_ref")
GOAL_FILE = re.compile(r"goal(\.v[0-9]+)?\.json")
TEAM_FILES = ("summary.json", "documents.json", "artifacts.json")


class ExportError(RuntimeError):
    """An export could not be made; the message says why."""


def _open_db(settings: Settings) -> sqlite3.Connection:
    try:
        return backup.connect_readonly(settings.db_path)
    except FileNotFoundError:
        raise ExportError(f"there is no database at {settings.db_path}; start Sutra Pro once, or check --data-dir") from None
    except sqlite3.Error as exc:
        raise ExportError(f"the database {settings.db_path} cannot be opened ({exc})") from None


def _refuse_existing(path: Path) -> None:
    if path.exists():
        raise ExportError(f"{path} already exists and is not overwritten; pick another --out or move it away")


def _write_text(path: Path, text: str) -> None:
    _refuse_existing(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _stamp(now: Callable[[], float]) -> str:
    return backup.utc_stamp(now())


# ---- chart --------------------------------------------------------------------------------------------------------------------

def export_chart(settings: Settings, *, now: Callable[[], float] = time.time) -> dict[str, Any]:
    """The chart export document (a plain dict, ready for json.dumps)."""
    conn = _open_db(settings)
    try:
        head = conn.execute("SELECT revision, body, sha256, ts FROM org_charts ORDER BY revision DESC LIMIT 1").fetchone()
        if head is None:
            raise ExportError("the org chart has no revision yet; start Sutra Pro once so it writes the root chart")
        rows = conn.execute("SELECT * FROM chart_changes ORDER BY seq").fetchall()
    except sqlite3.Error as exc:
        raise ExportError(f"the chart could not be read ({exc})") from None
    finally:
        conn.close()
    try:
        chart = OrgChart.model_validate_json(head["body"])
        changes = []
        for row in rows:
            seed = '"kind":"org_chart"' in row["body"].replace(" ", "")      # change 1 stores the seed chart itself, not a request
            changes.append({
                "seq": row["seq"], "id": row["id"], "task_id": row["task_id"], "task_title": row["task_title"], "kind": row["kind"],
                "actor": row["actor"], "status": row["status"], "base_revision": row["base_revision"], "result_revision": row["result_revision"],
                "summary": row["summary"], "reason": row["reason"], "before_sha": row["before_sha"], "after_sha": row["after_sha"], "ts": row["ts"],
                "change": None if seed else ChartChange.model_validate_json(row["body"]).model_dump(mode="json"),
                "seed_chart": OrgChart.model_validate_json(row["body"]).model_dump(mode="json") if seed else None})
    except ValidationError as exc:
        raise ExportError(f"a stored chart record no longer matches the library models ({exc.error_count()} problem(s), "
                          f"first at {'.'.join(str(p) for p in exc.errors()[0]['loc'])}); nothing was exported") from None
    return {"export": "sutra-pro-chart", "export_version": CHART_EXPORT_VERSION, "app_version": __version__,
            "schemas": {"org_chart": OrgChart.VERSION, "chart_change": ChartChange.VERSION},
            "exported": datetime.fromtimestamp(now(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "head": chart.model_dump(mode="json"), "head_sha256": head["sha256"], "changes": changes}


def cmd_chart(args: argparse.Namespace) -> int:
    settings = cli.load_settings(args)
    if settings is None:
        return 2
    try:
        document = export_chart(settings)
        text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        if args.out is not None and str(args.out) == "-":
            sys.stdout.write(text)
            return 0
        out = args.out or Path.cwd() / f"sutra-pro-chart-{_stamp(time.time)}.json"
        _write_text(out, text)
    except ExportError as exc:
        print(f"sutra-pro: {exc}", file=sys.stderr)
        return 1
    cli.emit(args, {"path": str(out), "revision": document["head"]["revision"], "changes": len(document["changes"])},
             [f"Wrote {out}: org chart revision {document['head']['revision']} and {len(document['changes'])} change(s)."])
    return 0


# ---- team ---------------------------------------------------------------------------------------------------------------------

def _last_finished_run(conn: sqlite3.Connection, dept: str) -> sqlite3.Row | None:
    marks = ",".join("?" for _ in GOOD_END)
    return conn.execute(
        f"SELECT id, run_id, status, title, COALESCE(ended_at, last_event_at, created_at) AS finished FROM tasks"
        f" WHERE dept_id = ? AND run_id IS NOT NULL AND status IN ({marks}) ORDER BY finished DESC, created_at DESC, id DESC LIMIT 1",
        (dept, *GOOD_END)).fetchone()


def _ledger_rows(conn: sqlite3.Connection, dept: str) -> Iterator[dict[str, Any]]:
    cursor = conn.execute(
        "SELECT l.seq, l.atom_id, l.node_id, l.status, l.body, l.ts FROM atom_ledger l"
        " LEFT JOIN graph_nodes n ON n.id = l.node_id LEFT JOIN atoms a ON a.id = l.atom_id"
        " WHERE n.department_id = ? OR a.department_id = ? ORDER BY l.seq", (dept, dept))
    for row in cursor:
        try:
            body: Any = json.loads(row["body"])
        except ValueError:
            body = row["body"]
        yield {"seq": row["seq"], "atom_id": row["atom_id"], "node_id": row["node_id"], "status": row["status"], "ts": row["ts"], "body": body}


def _copy_tree(src: Path, dest: Path, skip: tuple[str, ...] = ()) -> list[str]:
    copied: list[str] = []
    for root, dirs, names in os.walk(src, followlinks=False):
        rootp = Path(root)
        dirs[:] = [d for d in dirs if not (rootp / d).is_symlink() and (rootp / d).relative_to(src).as_posix() not in skip]
        for name in names:
            path = rootp / name
            if path.is_symlink() or not path.is_file():
                continue
            target = dest / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            copied.append(target.relative_to(dest).as_posix())
    return copied


def export_team(settings: Settings, dept: str, out: Path | None = None, *, now: Callable[[], float] = time.time) -> tuple[Path, dict[str, Any]]:
    """Copy a team's last finished run into a new folder. Returns (folder, EXPORT.json document)."""
    if not is_dept_id(dept):
        raise ExportError(f"{dept[:40]!r} is not a team id (lowercase letters, digits and dashes)")
    conn = _open_db(settings)
    try:
        if conn.execute("SELECT 1 FROM departments WHERE id = ?", (dept,)).fetchone() is None:
            raise ExportError(f"there is no team {dept!r}; `sutra-pro export chart` lists the teams of the chart")
        task = _last_finished_run(conn, dept)
        if task is None:
            raise ExportError(f"team {dept!r} has no finished run yet; there is nothing to export")
        ledger = list(_ledger_rows(conn, dept))
    except sqlite3.Error as exc:
        raise ExportError(f"the database could not be read ({exc})") from None
    finally:
        conn.close()
    if not is_run_id(task["run_id"]):
        raise ExportError(f"the run id {str(task['run_id'])[:40]!r} of team {dept!r} is not a run folder name")
    run_dir = settings.departments_dir / dept / "runs" / task["run_id"]
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise ExportError(f"the run folder {run_dir} is missing, so team {dept!r} cannot be exported (was it moved or restored without runs?)")
    folder = Path(out).expanduser() if out is not None else Path.cwd() / f"sutra-pro-team-{dept}-{_stamp(now)}"
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise ExportError(f"{folder} exists and is not empty; pick another --out or move it away")
    folder.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    try:
        names = sorted(p.name for p in run_dir.glob("goal*.json") if GOAL_FILE.fullmatch(p.name) and p.is_file() and not p.is_symlink())
        for name in [*names, *TEAM_FILES]:
            path = run_dir / name
            if path.is_file() and not path.is_symlink():
                shutil.copyfile(path, folder / name)
                files.append(name)
        for tree, skip in (("site", ("shots",)), ("artifacts", ())):
            if (run_dir / tree).is_dir() and not (run_dir / tree).is_symlink():
                files += [f"{tree}/{name}" for name in _copy_tree(run_dir / tree, folder / tree, skip)]
        lines = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ledger)
        (folder / "atom-ledger.jsonl").write_text(lines, encoding="utf-8")
        files.append("atom-ledger.jsonl")
        info = {"export": "sutra-pro-team", "export_version": 1, "app_version": __version__, "dept": dept, "task_id": task["id"],
                "run_id": task["run_id"], "status": task["status"], "title": task["title"], "ledger_rows": len(ledger),
                "exported": datetime.fromtimestamp(now(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "files": sorted(files)}
        (folder / "EXPORT.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"the export into {folder} failed ({exc.strerror or exc}); the folder may hold part of it") from None
    return folder, info


def cmd_team(args: argparse.Namespace) -> int:
    settings = cli.load_settings(args)
    if settings is None:
        return 2
    try:
        folder, info = export_team(settings, args.dept, args.out)
    except ExportError as exc:
        print(f"sutra-pro: {exc}", file=sys.stderr)
        return 1
    cli.emit(args, {"path": str(folder), **info},
             [f"Exported team {args.dept} (run {info['run_id']}) to {folder}: {len(info['files'])} file(s), {info['ledger_rows']} Atom log row(s)."])
    return 0


# ---- usage --------------------------------------------------------------------------------------------------------------------

def export_usage(settings: Settings) -> str:
    """Every `usage_ledger` row as CSV text (header first, ids ascending, `at` as UTC ISO time)."""
    conn = _open_db(settings)
    try:
        rows = conn.execute(f"SELECT {', '.join(USAGE_COLUMNS)} FROM usage_ledger ORDER BY id").fetchall()
    except sqlite3.Error as exc:
        raise ExportError(f"the usage table could not be read ({exc})") from None
    finally:
        conn.close()
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(USAGE_COLUMNS)
    for row in rows:
        cells = []
        for column in USAGE_COLUMNS:
            value = row[column]
            if column == "at" and isinstance(value, int):
                value = datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            cells.append("" if value is None else value)
        writer.writerow(cells)
    return buffer.getvalue()


def cmd_usage(args: argparse.Namespace) -> int:
    settings = cli.load_settings(args)
    if settings is None:
        return 2
    if not args.csv:
        print("sutra-pro: export usage writes CSV; add --csv", file=sys.stderr)
        return 2
    try:
        text = export_usage(settings)
        if args.out is not None and str(args.out) == "-":
            sys.stdout.write(text)
            return 0
        out = args.out or Path.cwd() / f"sutra-pro-usage-{_stamp(time.time)}.csv"
        _write_text(out, text)
    except ExportError as exc:
        print(f"sutra-pro: {exc}", file=sys.stderr)
        return 1
    rows = max(0, text.count("\n") - 1)
    cli.emit(args, {"path": str(out), "rows": rows}, [f"Wrote {out}: {rows} usage row(s)."])
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    return {"chart": cmd_chart, "team": cmd_team, "usage": cmd_usage}[args.export_cmd](args)


def register(sub: Any) -> None:
    """Add `export` (chart | team | usage) to the CLI's subparsers (the `register(sub)` contract of ops.cli)."""
    common = [cli.common_parser()]
    p = sub.add_parser("export", help="read-only copies: the org chart and its change log, a team's deliverables, the usage table")
    what = p.add_subparsers(dest="export_cmd", metavar="chart|team|usage", required=True)
    q = what.add_parser("chart", parents=common, help="the head org chart and the change log as JSON")
    q.add_argument("--out", type=Path, metavar="FILE", help="the file to write (default ./sutra-pro-chart-<UTC>.json; - is standard output)")
    q = what.add_parser("team", parents=common, help="a team's charter, site, documents, summary and Atom log rows")
    q.add_argument("dept", help="the team id, e.g. web")
    q.add_argument("--out", type=Path, metavar="DIR", help="the new folder to write (default ./sutra-pro-team-<id>-<UTC>)")
    q = what.add_parser("usage", parents=common, help="every usage row as CSV")
    q.add_argument("--csv", action="store_true", help="write CSV (the only format)")
    q.add_argument("--out", type=Path, metavar="FILE", help="the file to write (default ./sutra-pro-usage-<UTC>.csv; - is standard output)")
    p.set_defaults(func=cmd_export)
