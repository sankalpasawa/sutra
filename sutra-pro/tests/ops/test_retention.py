"""GAP-DATA: `sutra-pro prune` removes only the bulky evidence of old FINISHED runs (gaps G13, decisions D60, D93)."""
import json
import os
import sqlite3
import time
from pathlib import Path

import pytest

from sutra_app.config import Settings
from sutra_app.ops import backup, cli, retention
from sutra_app.ops.lock import InstanceLock
from sutra_app.orchestrator.db import Database

DAY = 86400
BULKY = {"trace.jsonl": "t" * 100, "run.stdout.log": "o" * 50, "run.stderr.log": "e" * 50, "events.jsonl": "ev\n" * 10,
         "site/shots/v1.png": "p" * 200, "screenshots/home.png": "q" * 20, "final.png": "r" * 10}
KEPT = {"summary.json": "{}", "goal.json": "{}", "goal.v2.json": "{}", "site/index.html": "<html>", "site/v1.html": "<html>", "site/logo.png": "logo",
        "site/doc-v1.md": "# doc", "documents.json": "{}", "chat.jsonl": "c\n", "calls.jsonl": "k\n", "atoms.json": "[]"}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith(("SUTRA_", "J2_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("SUTRA_ENV_FILE", str(tmp_path / "none.env"))


class Folder:
    """A data folder with a real migrated database and helpers that add finished runs of a given age."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir()
        db = Database(root / "db.sqlite3", lambda events: None)
        db.migrate()
        db.close()
        self.settings = Settings.load({}, data_dir=root, env_file=root.parent / "none.env")
        self.n = 0
        self.now = time.time()

    def sql(self, query: str, *args):
        conn = sqlite3.connect(self.settings.db_path, isolation_level=None)
        try:
            return conn.execute(query, args).fetchall()
        finally:
            conn.close()

    def run(self, dept: str = "web", *, status: str = "done", days: float = 120, offset: int | str | None = "full", files: dict | None = None,
            ended: bool = True) -> Path:
        self.n += 1
        run_id = f"j2-2026-{self.n:04d}"
        folder = self.root / "departments" / dept / "runs" / run_id
        for name, body in {**BULKY, **KEPT, **(files or {})}.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        size = (folder / "events.jsonl").stat().st_size
        at = int(self.now - days * DAY)
        self.sql("INSERT INTO tasks(id, dept_id, title, user_text, status, run_id, events_offset, created_at, ended_at)"
                 " VALUES (?,?,?,?,?,?,?,?,?)", f"tsk_{self.n}", dept, "t", "u", status, run_id, size if offset == "full" else (offset or 0),
                 at - 60, at if ended else None)
        return folder

    def tables(self) -> dict[str, list]:
        return {t: self.sql(f"SELECT * FROM {t} ORDER BY rowid") for t in ("tasks", "atom_ledger", "usage_ledger", "chat_messages", "org_charts")}


@pytest.fixture
def folder(tmp_path) -> Folder:
    return Folder(tmp_path / "data")


def files_under(run: Path) -> set[str]:
    return {p.relative_to(run).as_posix() for p in run.rglob("*") if p.is_file()}


def prune(folder: Folder, *flags: str, capsys=None) -> tuple[int, str]:
    code = cli.main(["prune", "--data-dir", str(folder.root), *flags])
    out = capsys.readouterr() if capsys is not None else None
    return code, (out.out + out.err) if out is not None else ""


# ============================================================ the age ========================================================

@pytest.mark.parametrize("text, seconds", [("90d", 90 * DAY), ("36h", 36 * 3600), ("2w", 14 * DAY), ("45m", 2700), ("600s", 600), ("30", 30 * DAY), (" 1.5d ", 1.5 * DAY)])
def test_parse_age(text, seconds):
    assert retention.parse_age(text) == seconds


@pytest.mark.parametrize("text", ["", "abc", "-1d", "0d", "5y", "d"])
def test_parse_age_refuses_nonsense(text):
    with pytest.raises(ValueError, match="age"):
        retention.parse_age(text)


def test_bad_age_and_contradicting_flags_are_usage_errors(folder, capsys):
    assert prune(folder, "--older-than", "soon", capsys=capsys)[0] == 2
    code, out = prune(folder, "--dry-run", "--yes", capsys=capsys)
    assert code == 2 and "contradict" in out


def test_the_default_age_is_90_days(folder, capsys):
    young, old = folder.run(days=60), folder.run(days=100)
    code, out = prune(folder, "--yes", capsys=capsys)
    assert code == 0 and "trace.jsonl" in files_under(young) and "trace.jsonl" not in files_under(old)


# ============================================================ dry run and apply ==============================================

def test_dry_run_is_the_default_lists_the_files_and_deletes_nothing(folder, capsys):
    run = folder.run()
    before = files_under(run)
    code, out = prune(folder, capsys=capsys)
    assert code == 0 and files_under(run) == before
    assert "Dry run" in out and "trace.jsonl" in out and "Nothing was deleted" in out and "--yes" in out
    code, out = prune(folder, "--dry-run", capsys=capsys)
    assert code == 0 and files_under(run) == before


def test_yes_removes_exactly_the_bulky_evidence_and_keeps_every_deliverable(folder, capsys):
    run = folder.run()
    code, out = prune(folder, "--yes", capsys=capsys)
    assert code == 0 and "Removed 7 of 7" in out
    assert files_under(run) == set(KEPT)
    assert retention.plan(folder.settings, 90 * DAY).candidates == []


def test_apply_changes_no_database_row(folder, capsys):
    folder.run()
    folder.sql("INSERT INTO chat_sessions(id, node_id, kind, title, created_at, updated_at) VALUES ('cs_x','n','org','t',1,1)")
    folder.sql("INSERT INTO atom_ledger(atom_id, node_id, status, body, ts) VALUES ('a1','n','closed','{}',1)")
    folder.sql("INSERT INTO usage_ledger(at, provider, purpose, usd) VALUES (1,'stub','p',0)")
    before = folder.tables()
    prune(folder, "--yes", capsys=capsys)
    assert folder.tables() == before


def test_a_second_apply_has_nothing_left_to_do(folder, capsys):
    folder.run()
    prune(folder, "--yes", capsys=capsys)
    code, out = prune(folder, "--yes", "--json", capsys=capsys)
    payload = json.loads(out)
    assert code == 0 and payload["files"] == 0 and payload["removed"] == 0 and payload["applied"] is True


# ============================================================ which runs ======================================================

@pytest.mark.parametrize("status", ["done", "done_with_open_items", "stopped", "crashed", "cancelled"])
def test_every_finished_status_is_pruned(folder, status):
    run = folder.run(status=status)
    retention.apply(folder.settings, retention.plan(folder.settings, 90 * DAY))
    assert files_under(run) == set(KEPT)


@pytest.mark.parametrize("status", ["blocked", "queued", "starting", "running", "waiting_user"])
def test_a_run_that_is_not_over_is_never_touched(folder, status):
    run = folder.run(dept=f"team-{status.replace('_', '-')}", status=status)
    before = files_under(run)
    retention.apply(folder.settings, retention.plan(folder.settings, 1))
    assert files_under(run) == before


def test_a_run_younger_than_the_age_is_kept_and_the_age_is_the_end_time(folder):
    young = folder.run(days=5)
    old = folder.run(days=40)
    found = retention.plan(folder.settings, 30 * DAY)
    assert {c.run_id for c in found.candidates} == {old.name} and found.runs == 1
    assert files_under(young) == set(BULKY) | set(KEPT)


def test_a_run_with_no_end_time_is_aged_by_its_creation(folder):
    run = folder.run(ended=False, days=100)
    retention.apply(folder.settings, retention.plan(folder.settings, 90 * DAY))
    assert "trace.jsonl" not in files_under(run)


def test_a_run_folder_the_database_does_not_list_is_left_alone(folder):
    stray = folder.root / "departments" / "web" / "runs" / "j2-2026-9999"
    (stray).mkdir(parents=True)
    (stray / "trace.jsonl").write_text("t")
    retention.apply(folder.settings, retention.plan(folder.settings, 1))
    assert (stray / "trace.jsonl").exists()


def test_events_are_pruned_only_when_the_server_has_projected_every_byte(folder, capsys):
    behind = folder.run(offset=5)
    done = folder.run()
    code, out = prune(folder, "--yes", capsys=capsys)
    assert (behind / "events.jsonl").exists() and not (done / "events.jsonl").exists()
    assert "events.jsonl kept" in out and "projected 5 of its 30 bytes" in out
    assert "trace.jsonl" not in files_under(behind)                                       # the rest of that run still goes


def test_ids_in_the_database_that_could_leave_the_runs_folder_are_ignored(folder, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "trace.jsonl").write_text("precious")
    folder.sql("INSERT INTO tasks(id, dept_id, title, user_text, status, run_id, created_at, ended_at) VALUES ('tsk_bad','..','t','u','done','../../outside',1,1)")
    folder.sql("INSERT INTO tasks(id, dept_id, title, user_text, status, run_id, created_at, ended_at) VALUES ('tsk_bad2','web','t','u','done','../../../outside',1,1)")
    retention.apply(folder.settings, retention.plan(folder.settings, 1))
    assert (outside / "trace.jsonl").read_text() == "precious"


def test_links_are_not_followed_and_not_deleted(folder, tmp_path):
    run = folder.run()
    secret = tmp_path / "secret.txt"
    secret.write_text("keep me")
    (run / "trace.jsonl").unlink()
    (run / "trace.jsonl").symlink_to(secret)
    (run / "site" / "shots" / "v1.png").unlink()
    (run / "site" / "shots" / "v1.png").symlink_to(secret)
    retention.apply(folder.settings, retention.plan(folder.settings, 90 * DAY))
    assert secret.read_text() == "keep me" and (run / "trace.jsonl").is_symlink() and (run / "site" / "shots" / "v1.png").is_symlink()


# ============================================================ backups =========================================================

def test_automatic_backups_beyond_the_newest_7_go_and_pre_upgrade_copies_stay(folder, capsys):
    backups = folder.root / "backups"
    backups.mkdir()
    for i in range(9):
        path = backups / f"sutra-pro-backup-2026010{i + 1}T000000Z.tar.gz"
        path.write_text("b" * 10)
        os.utime(path, (1_700_000_000 + i, 1_700_000_000 + i))
    (backups / "pre-upgrade-v0-to-v1.sqlite3").write_text("keep")
    (backups / "notes.txt").write_text("keep")
    code, out = prune(folder, capsys=capsys)
    assert "old backup sutra-pro-backup-20260101T000000Z.tar.gz" in out and len(list(backups.glob("sutra-pro-backup-*"))) == 9
    prune(folder, "--yes", capsys=capsys)
    assert sorted(p.name for p in backups.glob("sutra-pro-backup-*")) == [f"sutra-pro-backup-2026010{i}T000000Z.tar.gz" for i in range(3, 10)]
    assert (backups / "pre-upgrade-v0-to-v1.sqlite3").exists() and (backups / "notes.txt").exists()


def test_prune_and_backup_agree_on_how_many_to_keep():
    assert retention.backup.KEEP_AUTOMATIC == 7 == backup.KEEP_AUTOMATIC


# ============================================================ the append-only tables and VACUUM ================================

def bloat(folder: Folder) -> int:
    """Make the file big and then free the pages so that a VACUUM has something to give back."""
    conn = sqlite3.connect(folder.settings.db_path, isolation_level=None)
    for i in range(300):
        conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", (f"b{i}", "x" * 4000))
    conn.execute("DELETE FROM meta")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return folder.settings.db_path.stat().st_size


def test_row_counts_and_sizes_of_the_append_only_tables_are_printed(folder, capsys):
    folder.sql("INSERT INTO atom_ledger(atom_id, node_id, status, body, ts) VALUES ('a1','n','closed','{}',1), ('a2','n','closed','{}',2)")
    folder.sql("INSERT INTO usage_ledger(at, provider, purpose) VALUES (1,'stub','p'), (2,'stub','p'), (3,'stub','p')")
    code, out = prune(folder, capsys=capsys)
    assert "atom_ledger: 2 rows" in out and "usage_ledger: 3 rows" in out and "append-only, kept" in out and "D93" in out
    stats = retention.table_stats(sqlite3.connect(folder.settings.db_path))
    assert stats["atom_ledger"]["rows"] == 2 and stats["usage_ledger"]["rows"] == 3 and stats["atom_ledger"]["bytes"] != 0


def test_vacuum_runs_only_with_yes_and_only_when_the_server_is_not_running(folder, capsys):
    big = bloat(folder)
    prune(folder, capsys=capsys)
    assert folder.settings.db_path.stat().st_size == big                                    # a dry run never vacuums
    holder = InstanceLock(folder.root)
    assert holder.acquire()
    try:
        code, out = prune(folder, "--yes", capsys=capsys)
        assert code == 0 and "VACUUM: skipped" in out and "server is running" in out
        assert folder.settings.db_path.stat().st_size == big
    finally:
        holder.release()
    code, out = prune(folder, "--yes", "--json", capsys=capsys)
    payload = json.loads(out)
    assert payload["vacuum"]["done"] is True and folder.settings.db_path.stat().st_size < big


def test_a_dry_run_says_when_the_server_is_running(folder, capsys):
    holder = InstanceLock(folder.root)
    assert holder.acquire()
    try:
        assert "The server is running now" in prune(folder, capsys=capsys)[1]
    finally:
        holder.release()


def test_prune_works_while_the_server_runs_for_files_and_never_waits_for_it(folder, capsys):
    run = folder.run()
    holder = InstanceLock(folder.root)
    assert holder.acquire()
    try:
        code, _ = prune(folder, "--yes", capsys=capsys)
    finally:
        holder.release()
    assert code == 0 and files_under(run) == set(KEPT)


def test_prune_without_a_database_is_not_a_crash(tmp_path, capsys):
    (tmp_path / "d").mkdir()
    code = cli.main(["prune", "--data-dir", str(tmp_path / "d")])
    assert code == 0 and "0 run(s)" in capsys.readouterr().out
    cli.build_parser()
    assert "prune" in cli.COMMANDS
