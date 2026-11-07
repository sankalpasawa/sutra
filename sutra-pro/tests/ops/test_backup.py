"""GAP-DATA: `sutra-pro backup`, `restore` and the automatic backup before an upgrade (gaps G13).

Most tests use a small data folder made here (a real migrated database plus a few files); the last test starts the REAL app (stub
connector, Brew Lab scenario of GAP-E2E), backs it up while it is live, restores into a new folder, starts a second app on it and compares.
"""
import errno
import hashlib
import io
import json
import os
import sqlite3
import sys
import tarfile
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))
from harness import LiveApp, run_new_team                                            # noqa: E402

from sutra_app import __version__, oslayer                                           # noqa: E402
from sutra_app.config import Settings                                                # noqa: E402
from sutra_app.ops import backup, cli, lock                                          # noqa: E402
from sutra_app.ops.lock import InstanceLock                                          # noqa: E402
from sutra_app.orchestrator import schema                                            # noqa: E402
from sutra_app.orchestrator.db import Database                                       # noqa: E402
from sutra_app.orchestrator.testing.scripted import ScriptedConnector                # noqa: E402

RUN = "j2-20261101-100000-abcd"
DAY = 86400


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith(("SUTRA_", "J2_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("SUTRA_ENV_FILE", str(tmp_path / "none.env"))


def settings_for(root: Path) -> Settings:
    return Settings.load({}, data_dir=root, env_file=root.parent / "none.env")


def write(path: Path, text: str = "x", age_days: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if age_days:
        stamp = time.time() - age_days * DAY
        os.utime(path, (stamp, stamp))
    return path


@pytest.fixture
def data(tmp_path) -> Settings:
    """A data folder with a real migrated database (one extra row in `meta`) and one of each kind of file."""
    root = tmp_path / "data"
    root.mkdir()
    db = Database(root / "db.sqlite3", lambda events: None)
    db.migrate()
    db.conn().execute("INSERT INTO meta(key, value) VALUES ('marker', 'one')")
    db.close()
    run = root / "departments" / "web" / "runs" / RUN
    write(root / "departments" / "web" / "department.json", '{"id": "web"}')
    write(run / "summary.json", '{"status": "done"}')
    write(run / "events.jsonl", "e\n")
    write(run / "run.stdout.log", "old out", age_days=9)
    write(run / "run.stderr.log", "new err", age_days=1)
    write(run / "site" / "index.html", "<html></html>")
    write(root / "library" / "index.json", "{}")
    write(root / "agents" / "j2" / "role.md", "role")
    write(root / "connectors" / "policy.json", "{}")
    write(root / "connectors" / "other.json", "not listed")
    write(root / "engine.json", "{}")
    write(root / "limits.json", '{"version": 1}')
    write(root / "attention.json", '{"version": 1}')
    write(root / ".env", "J2_OVERRIDE_KEY=secret-value")
    write(root / "app.lock", "")
    write(root / "app.pid", "1 2")
    write(root / "logs" / "server.log", "log line")
    return settings_for(root)


def names_of(archive: Path) -> set[str]:
    with tarfile.open(archive) as tar:
        return {m.name for m in tar.getmembers()}


def contents(archive: Path) -> dict[str, bytes]:
    with tarfile.open(archive) as tar:
        return {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isreg()}


def build_archive(dest: Path, files: dict[str, bytes], *, manifest: dict | None = None, user_version: int | None = None,
                  extra: list[tarfile.TarInfo] = (), skip_manifest: bool = False) -> Path:
    """A hand-made backup: `files` plus a manifest computed from them (override with `manifest`)."""
    if manifest is None:
        version = schema.SCHEMA_VERSION if user_version is None else user_version
        manifest = {"format": 1, "app": "sutra-pro", "app_version": "x", "user_version": version, "created": "2026-11-04T00:00:00Z",
                    "files": [{"path": n, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for n, b in files.items()]}
    with tarfile.open(dest, "w:gz") as tar:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
        for info in extra:
            tar.addfile(info, io.BytesIO(b"") if info.isreg() else None)
        if not skip_manifest:
            body = json.dumps(manifest).encode()
            info = tarfile.TarInfo("MANIFEST.json")
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return dest


@pytest.fixture
def good(data, tmp_path) -> tuple[Path, dict[str, bytes]]:
    result = backup.create_backup(data, to=tmp_path / "bk")
    items = contents(result.path)
    items.pop("MANIFEST.json")
    return result.path, items


# ============================================================ backup ==========================================================

def test_backup_holds_the_listed_files_and_never_secrets_or_locks_or_logs(data):
    result = backup.create_backup(data)
    assert result.path.parent == data.data_dir / "backups" and result.path.name.startswith("sutra-pro-backup-")
    assert result.path.name.endswith("Z.tar.gz")
    names = names_of(result.path)
    assert names == {"db.sqlite3", "MANIFEST.json", "engine.json", "connectors/policy.json", "limits.json", "attention.json", "library/index.json", "agents/j2/role.md",
                     "departments/web/department.json", f"departments/web/runs/{RUN}/summary.json", f"departments/web/runs/{RUN}/events.jsonl",
                     f"departments/web/runs/{RUN}/run.stderr.log", f"departments/web/runs/{RUN}/site/index.html"}
    assert "secret-value" not in b"".join(contents(result.path).values()).decode("latin-1")


def test_backup_file_is_mode_0600_and_the_backups_folder_0700(data):
    result = backup.create_backup(data)
    assert result.path.stat().st_mode & 0o777 == 0o600
    assert result.path.parent.stat().st_mode & 0o777 == 0o700
    assert not list(result.path.parent.glob(".*part")) and not [p for p in result.path.parent.iterdir() if p.is_dir()]


def test_manifest_has_version_user_version_time_and_a_true_sha256_for_every_file(data):
    result = backup.create_backup(data)
    items = contents(result.path)
    manifest = json.loads(items.pop("MANIFEST.json"))
    assert manifest["format"] == 1 and manifest["app_version"] == __version__ and manifest["user_version"] == schema.SCHEMA_VERSION == result.user_version
    assert manifest["created"].endswith("Z") and manifest["runs_included"] is True
    assert {f["path"] for f in manifest["files"]} == set(items)
    for entry in manifest["files"]:
        assert hashlib.sha256(items[entry["path"]]).hexdigest() == entry["sha256"] and len(items[entry["path"]]) == entry["size"]


def test_run_logs_older_than_7_days_are_left_out_younger_ones_kept(data):
    names = names_of(backup.create_backup(data).path)
    assert f"departments/web/runs/{RUN}/run.stdout.log" not in names and f"departments/web/runs/{RUN}/run.stderr.log" in names


def test_no_runs_leaves_every_runs_folder_out_but_keeps_the_team_files(data):
    result = backup.create_backup(data, include_runs=False)
    names = names_of(result.path)
    assert "departments/web/department.json" in names and not [n for n in names if "/runs/" in n]
    assert json.loads(contents(result.path)["MANIFEST.json"])["runs_included"] is False


def test_the_database_copy_is_consistent_and_holds_rows_still_in_the_wal(data):
    """A writer with an open connection keeps rows in the -wal file; the copy must hold them (online backup, not a file copy)."""
    writer = sqlite3.connect(data.db_path, isolation_level=None)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    for i in range(50):
        writer.execute("INSERT INTO meta(key, value) VALUES (?, 'wal')", (f"w{i}",))
    assert (data.data_dir / "db.sqlite3-wal").stat().st_size > 0
    try:
        result = backup.create_backup(data)
    finally:
        writer.close()
    copy = result.path.parent / "copy.sqlite3"
    copy.write_bytes(contents(result.path)["db.sqlite3"])
    check = sqlite3.connect(copy)
    assert check.execute("SELECT count(*) FROM meta WHERE value = 'wal'").fetchone()[0] == 50
    assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    check.close()


def test_a_backup_during_steady_writes_is_a_whole_snapshot(data):
    stop = threading.Event()

    def churn():
        conn = sqlite3.connect(data.db_path, isolation_level=None, timeout=10)
        n = 0
        while not stop.is_set():
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO meta(key, value) VALUES (?, 'pair')", (f"a{n}",))
            conn.execute("INSERT INTO meta(key, value) VALUES (?, 'pair')", (f"b{n}",))
            conn.execute("COMMIT")
            n += 1
        conn.close()

    thread = threading.Thread(target=churn)
    thread.start()
    try:
        time.sleep(0.05)
        result = backup.create_backup(data)
    finally:
        stop.set()
        thread.join()
    copy = result.path.parent / "copy.sqlite3"
    copy.write_bytes(contents(result.path)["db.sqlite3"])
    check = sqlite3.connect(copy)
    assert check.execute("SELECT count(*) FROM meta WHERE key LIKE 'a%'").fetchone()[0] == check.execute("SELECT count(*) FROM meta WHERE key LIKE 'b%'").fetchone()[0]
    check.close()


def test_a_missing_database_is_refused_and_no_archive_is_left(tmp_path):
    empty = settings_for(tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    with pytest.raises(backup.BackupError, match="no database"):
        backup.create_backup(empty)
    assert not list((tmp_path / "empty" / "backups").glob("*"))


def test_default_folder_keeps_the_newest_7_backups_and_never_touches_pre_upgrade_copies(data):
    folder = data.data_dir / "backups"
    for i in range(8):
        write(folder / f"sutra-pro-backup-2026010{i + 1}T000000Z.tar.gz", "old", age_days=100 - i)
    keeper = write(folder / "pre-upgrade-v0-to-v1.sqlite3", "keep", age_days=500)
    result = backup.create_backup(data)
    left = sorted(p.name for p in folder.glob("sutra-pro-backup-*.tar.gz"))
    assert len(left) == 7 and result.path.name in left
    assert "sutra-pro-backup-20260101T000000Z.tar.gz" not in left and "sutra-pro-backup-20260102T000000Z.tar.gz" not in left
    assert "sutra-pro-backup-20260103T000000Z.tar.gz" in left and keeper.exists() and len(result.rotated) == 2


def test_a_backup_with_to_is_never_rotated(data, tmp_path):
    target = tmp_path / "mine"
    for i in range(9):
        write(target / f"sutra-pro-backup-2026010{i + 1}T000000Z.tar.gz", "old", age_days=100 - i)
    result = backup.create_backup(data, to=target)
    assert len(list(target.glob("sutra-pro-backup-*.tar.gz"))) == 10 and result.rotated == []


def test_two_backups_in_one_second_get_two_files(data):
    first = backup.create_backup(data, now=lambda: 1_800_000_000.0)
    second = backup.create_backup(data, now=lambda: 1_800_000_000.0)
    assert first.path != second.path and first.path.exists() and second.path.exists()


# ============================================================ the commands ====================================================

def test_include_env_is_refused_with_the_reason_and_writes_nothing(data, capsys):
    code = cli.main(["backup", "--data-dir", str(data.data_dir), "--include-env"])
    assert code == 2
    err = capsys.readouterr().err
    assert "--include-env is refused" in err and "override key" in err and "SMTP" in err
    assert not (data.data_dir / "backups").exists()


def test_backup_command_prints_where_and_what_and_json(data, capsys):
    assert cli.main(["backup", "--data-dir", str(data.data_dir), "--json", "--no-runs"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert Path(payload["path"]).is_file() and payload["user_version"] == schema.SCHEMA_VERSION and payload["server_running"] is False
    assert cli.main(["backup", "--data-dir", str(data.data_dir)]) == 0
    out = capsys.readouterr().out
    assert "Backup written:" in out and ".env" in out


def test_backup_command_exits_1_without_a_database(tmp_path, capsys):
    (tmp_path / "d").mkdir()
    assert cli.main(["backup", "--data-dir", str(tmp_path / "d")]) == 1
    assert "no database" in capsys.readouterr().err


def damage(settings: Settings) -> None:
    """Overwrite a few stretches of the database with 0xFF, past its first page: the file still opens, but `PRAGMA integrity_check` fails."""
    conn = sqlite3.connect(settings.db_path, isolation_level=None)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    with open(settings.db_path, "r+b") as handle:
        for n in range(6):
            handle.seek(8192 + n * 3000)
            handle.write(b"\xff" * 200)
    conn = sqlite3.connect(settings.db_path, isolation_level=None)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok", "the test's damage did not damage the database"
    finally:
        conn.close()


@pytest.mark.parametrize("target", [None, "elsewhere"])
def test_a_damaged_database_is_refused_with_the_reason_and_no_archive_or_scratch_is_left(data, tmp_path, target):
    damage(data)
    folder = tmp_path / "elsewhere" if target else data.data_dir / "backups"
    with pytest.raises(backup.BackupError) as caught:
        backup.create_backup(data, to=folder if target else None)
    text = str(caught.value)
    assert "integrity check" in text and "no backup was written" in text and "sutra-pro restore" in text and "\n" not in text
    assert list(folder.iterdir()) == []                               # no archive, no .part file, no scratch folder


def test_a_damaged_database_never_pushes_the_good_backups_out_of_the_rotation(data, tmp_path):
    folder = data.data_dir / "backups"
    good_ones = [backup.create_backup(data, now=lambda i=i: 1_800_000_000.0 + i).path for i in range(backup.KEEP_AUTOMATIC)]
    damage(data)
    for _ in range(backup.KEEP_AUTOMATIC + 1):
        with pytest.raises(backup.BackupError, match="integrity check"):
            backup.create_backup(data)
    assert sorted(p.name for p in folder.glob("sutra-pro-backup-*.tar.gz")) == sorted(p.name for p in good_ones)
    restored = backup.restore_backup(settings_for(tmp_path / "back"), max(good_ones))               # the newest kept backup still restores
    assert restored.files >= 1 and sqlite3.connect(tmp_path / "back" / "db.sqlite3").execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_integrity_problem_is_none_for_a_sound_file_one_line_for_a_damaged_one_and_raises_for_other_errors(data):
    conn = sqlite3.connect(data.db_path, isolation_level=None)
    assert backup.integrity_problem(conn) is None
    conn.close()
    damage(data)
    conn = sqlite3.connect(data.db_path, isolation_level=None)
    text = backup.integrity_problem(conn)
    assert text and "\n" not in text and len(text) <= 160
    conn.close()
    with pytest.raises(sqlite3.ProgrammingError):                       # a closed connection is not a damaged file
        backup.integrity_problem(conn)


def test_backup_command_says_why_and_exits_1_for_a_damaged_database(data, capsys):
    damage(data)
    assert cli.main(["backup", "--data-dir", str(data.data_dir)]) == 1
    captured = capsys.readouterr()
    assert "Backup written" not in captured.out and "integrity check" in captured.err and "sutra-pro restore" in captured.err
    assert not list((data.data_dir / "backups").glob("*.tar.gz"))


def test_the_commands_are_registered_in_cli_commands():
    cli.build_parser()
    assert {"backup", "restore"} <= set(cli.COMMANDS)


# ============================================================ before an upgrade ===============================================

def set_version(settings: Settings, version: int) -> None:
    conn = sqlite3.connect(settings.db_path, isolation_level=None)
    conn.execute(f"PRAGMA user_version={version}")
    conn.close()


def test_before_upgrade_copies_the_database_when_it_is_older_than_this_build(data):
    set_version(data, 0)
    path = backup.before_upgrade(data)
    assert path == data.data_dir / "backups" / f"pre-upgrade-v0-to-v{schema.SCHEMA_VERSION}.sqlite3" and path.is_file()
    assert path.stat().st_mode & 0o777 == 0o600
    check = sqlite3.connect(path)
    assert check.execute("SELECT value FROM meta WHERE key = 'marker'").fetchone()[0] == "one" and check.execute("PRAGMA user_version").fetchone()[0] == 0
    check.close()


def test_before_upgrade_names_both_versions(data, monkeypatch):
    current = schema.SCHEMA_VERSION                                              # the data fixture is migrated to this build's version
    monkeypatch.setattr(schema, "SCHEMA_VERSION", current + 2)
    assert backup.before_upgrade(data).name == f"pre-upgrade-v{current}-to-v{current + 2}.sqlite3"


def test_before_upgrade_replaces_an_older_copy_of_the_same_name(data):
    set_version(data, 0)
    path = backup.before_upgrade(data)
    path.write_bytes(b"stale")
    backup.before_upgrade(data)
    assert path.read_bytes() != b"stale" and sqlite3.connect(path).execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize("version", [schema.SCHEMA_VERSION, schema.SCHEMA_VERSION + 3])
def test_before_upgrade_does_nothing_for_a_current_or_newer_database(data, version):
    set_version(data, version)
    assert backup.before_upgrade(data) is None and not (data.data_dir / "backups").exists()


def test_before_upgrade_does_nothing_without_a_database_or_with_an_unreadable_one(tmp_path):
    root = tmp_path / "fresh"
    assert backup.before_upgrade(settings_for(root)) is None and not root.exists()
    root.mkdir()
    (root / "db.sqlite3").write_bytes(b"this is not a database" * 50)
    assert backup.before_upgrade(settings_for(root)) is None


def test_a_failed_pre_upgrade_backup_stops_the_start_with_a_doctor_style_message(data):
    set_version(data, 0)
    (data.data_dir / "backups").write_text("a file where the folder should be")
    with pytest.raises(backup.BackupError) as caught:
        cli.before_start(data)
    text = str(caught.value)
    assert text.startswith("[FAIL]") and "-> fix:" in text and "version 0" in text and "nothing was changed" in text


# ============================================================ restore =========================================================

def restore_into(root: Path, archive: Path):
    return backup.restore_backup(settings_for(root), archive)


def test_restore_into_a_new_folder_brings_back_every_file_with_no_before_restore_folder(good, tmp_path):
    archive, items = good
    target = tmp_path / "new" / "data"
    result = restore_into(target, archive)
    assert result.moved_to is None and result.files == len(items) and not list((tmp_path / "new").glob("*before-restore*"))
    for name, body in items.items():
        assert (target / name).read_bytes() == body
    assert sorted(p.name for p in (tmp_path / "new").iterdir()) == ["data"]             # no staging folder left
    assert sqlite3.connect(target / "db.sqlite3").execute("SELECT value FROM meta WHERE key = 'marker'").fetchone()[0] == "one"


def test_restore_over_an_existing_folder_moves_it_aside_and_carries_env_and_backups(good, data):
    archive, _ = good
    write(data.data_dir / "marker.txt", "mine")
    result = backup.restore_backup(data, archive, now=lambda: 1_800_000_000.0)
    aside = data.data_dir.parent / "data.before-restore-20270115T080000Z"
    assert result.moved_to == aside and (aside / "marker.txt").read_text() == "mine" and (aside / "db.sqlite3").is_file()
    assert not (data.data_dir / "marker.txt").exists() and (data.data_dir / "db.sqlite3").is_file()
    assert (data.data_dir / ".env").read_text() == "J2_OVERRIDE_KEY=secret-value" and (aside / ".env").is_file()
    assert not (data.data_dir / "logs").exists() and (aside / "logs" / "server.log").is_file()


def watch_the_folder_rename(monkeypatch, data, *, refuse_open_files: bool, really_rename: bool) -> list[bool]:
    """Wrap os.rename: note whether the instance lock (an open file inside the data folder) is held when the data folder itself is renamed.
    `refuse_open_files` makes the wrapper answer as Windows does (a folder with a file open in it is "Access is denied"); without
    `really_rename` the folder is never moved, the wrapper fails it, so the test needs no working rename."""
    seen: list[bool] = []
    real = os.rename

    def rename(src, dst, *args, **kwargs):
        if Path(src) == data.data_dir:
            seen.append(lock.is_locked(data.data_dir))
            if (refuse_open_files and seen[-1]) or not really_rename:
                raise PermissionError(errno.EACCES, "Access is denied")
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "rename", rename)
    return seen


@pytest.mark.parametrize("windows", [True, False])
def test_the_instance_lock_is_dropped_before_the_data_folder_is_renamed_on_windows_and_held_through_it_elsewhere(good, data, monkeypatch, windows):
    # Windows cannot rename a folder that has a file open in it, this process's own app.lock included; elsewhere an open lock follows the
    # folder and keeps a server from starting on it halfway through the swap
    archive, _ = good
    monkeypatch.setattr(oslayer, "IS_WINDOWS", windows)
    seen = watch_the_folder_rename(monkeypatch, data, refuse_open_files=False, really_rename=False)
    with pytest.raises(backup.RestoreError, match="could not be put in place"):
        backup.restore_backup(data, archive)
    assert seen == [not windows]
    assert (data.data_dir / "engine.json").is_file() and not list(data.data_dir.parent.glob("*.restore-*")) and not lock.is_locked(data.data_dir)


@pytest.mark.skipif(oslayer.IS_WINDOWS, reason="the real folder rename is what the Windows leg skips for the other restore-over-a-folder tests")
def test_restore_over_an_existing_folder_completes_when_the_system_refuses_to_rename_a_folder_with_an_open_file(good, data, monkeypatch):
    archive, _ = good
    write(data.data_dir / "marker.txt", "mine")
    monkeypatch.setattr(oslayer, "IS_WINDOWS", True)
    seen = watch_the_folder_rename(monkeypatch, data, refuse_open_files=True, really_rename=True)
    result = backup.restore_backup(data, archive, now=lambda: 1_800_000_000.0)
    assert seen == [False] and result.moved_to is not None and (result.moved_to / "marker.txt").read_text() == "mine"
    assert (data.data_dir / "db.sqlite3").is_file() and not (data.data_dir / "marker.txt").exists()
    assert (data.data_dir / ".env").read_text() == "J2_OVERRIDE_KEY=secret-value" and not lock.is_locked(data.data_dir)


def test_restore_moves_the_backups_folder_into_the_new_data_folder(data):
    result = backup.create_backup(data)
    backup.restore_backup(data, result.path)
    assert (data.data_dir / "backups" / result.path.name).is_file()


def test_restore_refuses_while_the_instance_lock_is_held_and_changes_nothing(good, data):
    archive, _ = good
    holder = InstanceLock(data.data_dir, version="t")
    assert holder.acquire()
    try:
        with pytest.raises(backup.RestoreError, match="running"):
            backup.restore_backup(data, archive)
        assert cli.main(["restore", "--data-dir", str(data.data_dir), str(archive)]) == 1
    finally:
        holder.release()
    assert (data.data_dir / "engine.json").is_file() and not list(data.data_dir.parent.glob("*before-restore*"))


def test_restore_refuses_a_backup_from_a_newer_build(good, tmp_path):
    _, items = good
    archive = build_archive(tmp_path / "newer.tar.gz", items, user_version=schema.SCHEMA_VERSION + 1)
    with pytest.raises(backup.RestoreError, match="newer Sutra Pro"):
        restore_into(tmp_path / "t", archive)
    assert not (tmp_path / "t").exists()


def test_restore_accepts_an_older_database_version(data, tmp_path):
    set_version(data, 0)
    result = backup.create_backup(data)
    assert backup.restore_backup(settings_for(tmp_path / "t"), result.path).user_version == 0


def test_restore_refuses_a_changed_file_and_leaves_no_staging_folder(good, data, tmp_path):
    _, items = good
    manifest = {"format": 1, "user_version": 1, "files": [{"path": n, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for n, b in items.items()]}
    archive = build_archive(tmp_path / "bad.tar.gz", {**items, "library/index.json": b"{tampered}"}, manifest=manifest)
    with pytest.raises(backup.RestoreError, match="checksum"):
        backup.restore_backup(data, archive)
    assert (data.data_dir / "engine.json").is_file()
    assert sorted(p.name for p in data.data_dir.parent.iterdir() if p.name.startswith("data")) == ["data"]


def test_restore_refuses_a_file_the_manifest_does_not_list(good, tmp_path):
    _, items = good
    plus = build_archive(tmp_path / "plus.tar.gz", {**items, "sneaky.txt": b"x"}, manifest={
        "format": 1, "user_version": 1, "files": [{"path": n, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for n, b in items.items()]})
    with pytest.raises(backup.RestoreError, match="does not list"):
        restore_into(tmp_path / "t", plus)


def test_restore_refuses_a_listed_file_that_is_missing(good, tmp_path):
    _, items = good
    manifest = {"format": 1, "user_version": 1, "files": [{"path": n, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for n, b in items.items()]}
    manifest["files"].append({"path": "library/gone.json", "size": 1, "sha256": "0" * 64})
    archive = build_archive(tmp_path / "short.tar.gz", items, manifest=manifest)
    with pytest.raises(backup.RestoreError, match="lacks 1 file"):
        restore_into(tmp_path / "t", archive)
    assert not (tmp_path / "t").exists()


@pytest.mark.parametrize("bad", ["../evil.txt", "/abs/evil.txt", "a/../../evil.txt", "a\\b"])
def test_restore_refuses_unsafe_paths_in_the_manifest(good, tmp_path, bad):
    _, items = good
    manifest = {"format": 1, "user_version": 1, "files": [{"path": n, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for n, b in items.items()]}
    manifest["files"].append({"path": bad, "size": 1, "sha256": "0" * 64})
    with pytest.raises(backup.RestoreError, match="unsafe"):
        restore_into(tmp_path / "t", build_archive(tmp_path / "x.tar.gz", items, manifest=manifest))
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.parametrize("name", [
    ".env", "connectors/bins.json", "connectors/other.json", "connectors/policy.json.bak", "Connectors/policy.json", ".ENV", "app.lock", "app.pid",
    "logs/server.log", "backups/old.tar.gz", "departments", "library", "sneaky.txt", "db.sqlite3-wal",
])
def test_restore_refuses_a_file_a_backup_never_writes_even_when_its_manifest_lists_it_with_a_true_checksum(good, tmp_path, name):
    """The manifest comes from the archive, so it cannot be the allow-list: a crafted one planted `.env` (the override key) and
    `connectors/bins.json` ({"claude": "/bin/sh"}) in a data folder."""
    _, items = good
    crafted = build_archive(tmp_path / "evil.tar.gz", {**items, name: b"SUTRA_OVERRIDE_KEY=planted"})
    with pytest.raises(backup.RestoreError, match="never holds"):
        restore_into(tmp_path / "t", crafted)
    assert not (tmp_path / "t").exists() and sorted(p.name for p in tmp_path.iterdir() if "restore" in p.name) == []


def test_restore_over_a_folder_with_a_crafted_archive_changes_nothing(good, data, tmp_path):
    _, items = good
    crafted = build_archive(tmp_path / "evil.tar.gz", {**items, ".env": b"SUTRA_OVERRIDE_KEY=planted"})
    before = (data.data_dir / ".env").read_text()
    with pytest.raises(backup.RestoreError, match="never holds"):
        backup.restore_backup(data, crafted)
    assert (data.data_dir / ".env").read_text() == before and sorted(p.name for p in data.data_dir.parent.iterdir() if p.name.startswith("data")) == ["data"]


def test_restore_refuses_a_link_member(good, tmp_path):
    _, items = good
    link = tarfile.TarInfo("library/link")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    manifest = {"format": 1, "user_version": 1, "files": [{"path": n, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for n, b in items.items()]}
    with pytest.raises(backup.RestoreError, match="not a plain file"):
        restore_into(tmp_path / "t", build_archive(tmp_path / "x.tar.gz", items, manifest=manifest, extra=[link]))


@pytest.mark.parametrize("what", ["no manifest", "not an archive", "wrong format", "no database", "bad version"])
def test_restore_refuses_files_that_are_not_backups(good, tmp_path, what):
    _, items = good
    path = tmp_path / "x.tar.gz"
    if what == "no manifest":
        build_archive(path, items, skip_manifest=True)
    elif what == "not an archive":
        path.write_bytes(b"hello")
    elif what == "wrong format":
        build_archive(path, items, manifest={"format": 9, "user_version": 1, "files": []})
    elif what == "no database":
        trimmed = {n: b for n, b in items.items() if n != "db.sqlite3"}
        build_archive(path, trimmed)
    else:
        build_archive(path, items, manifest={"format": 1, "user_version": "1", "files": []})
    with pytest.raises(backup.RestoreError):
        restore_into(tmp_path / "t", path)
    assert not (tmp_path / "t").exists()


def test_restore_refuses_a_database_that_is_not_what_the_manifest_says(good, tmp_path):
    _, items = good
    archive = build_archive(tmp_path / "x.tar.gz", items, user_version=0)               # the file says 1, the manifest 0
    with pytest.raises(backup.RestoreError, match="manifest says 0"):
        restore_into(tmp_path / "t", archive)
    broken = {**items, "db.sqlite3": b"garbage" * 100}
    with pytest.raises(backup.RestoreError, match="database"):
        restore_into(tmp_path / "t", build_archive(tmp_path / "y.tar.gz", broken))
    assert not (tmp_path / "t").exists()


def test_restore_command_reports_the_old_folder_and_json(good, data, tmp_path, capsys):
    archive, _ = good
    assert cli.main(["restore", "--data-dir", str(data.data_dir), str(archive)]) == 0
    out = capsys.readouterr().out
    assert "before-restore" in out and "kept at" in out
    assert cli.main(["restore", "--data-dir", str(tmp_path / "t2"), "--json", str(archive)]) == 0
    assert json.loads(capsys.readouterr().out)["moved_to"] is None
    assert cli.main(["restore", "--data-dir", str(tmp_path / "t3"), str(tmp_path / "missing.tar.gz")]) == 1
    assert "no backup file" in capsys.readouterr().err


# ============================================================ the real app ====================================================

TABLES = ("org_charts", "chart_changes", "org_nodes", "org_edges", "departments", "tasks", "graph_nodes", "graph_edges", "chat_sessions",
          "chat_messages", "atoms", "atom_ledger", "usage_ledger")


def table_rows(path: Path, table: str) -> list[tuple]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
    finally:
        conn.close()


def test_backup_of_a_live_app_restores_into_a_new_folder_and_a_second_app_shows_the_same_work(tmp_path, capsys):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    first = LiveApp(tmp_path / "one", connector=ScriptedConnector()).start()
    try:
        journey = run_new_team(first)
        assert first.task_status(journey.task) == "done"
        # the server is up (the real lifespan, uvicorn and an engine that has just ended): back it up now
        capsys.readouterr()                                                       # the harness prints the server banner
        assert cli.main(["backup", "--data-dir", str(first.settings.data_dir), "--json"]) == 0
        archive = Path(json.loads(capsys.readouterr().out)["path"])
        want = {
            "graph": first.get("/api/graph"), "chart": first.get("/api/chart"), "changes": first.get("/api/chart/changes"),
            "atom_log": first.get("/api/atoms/log", limit=500), "org_chat": first.messages(),
            "team_chat": first.messages(first.session_of("web")), "usage": first.get("/api/usage", limit=500, include_stub="true")["rows"],
            "tables": {t: table_rows(first.settings.db_path, t) for t in TABLES}}
        assert want["atom_log"] and want["usage"] and len(want["tables"]["chat_messages"]) > 3
    finally:
        first.stop()
        first.kill_engines()
    assert cli.main(["restore", "--data-dir", str(tmp_path / "two" / "data"), str(archive)]) == 0
    capsys.readouterr()
    restored = tmp_path / "two" / "data"
    for table in TABLES:
        assert table_rows(restored / "db.sqlite3", table) == want["tables"][table], table           # row by row
    run = tmp_path / "two" / "data" / "departments" / "web" / "runs" / first.task_row(journey.task)["run_id"]
    assert json.loads((run / "summary.json").read_text())["run"] and (run / "site" / "index.html").is_file()
    second = LiveApp(tmp_path / "two", connector=ScriptedConnector()).start()
    try:
        assert second.get("/api/graph") == want["graph"]
        assert second.get("/api/chart") == want["chart"] and second.get("/api/chart/changes") == want["changes"]
        assert second.get("/api/atoms/log", limit=500) == want["atom_log"]
        assert second.messages() == want["org_chat"] and second.messages(second.session_of("web")) == want["team_chat"]
        assert second.get("/api/usage", limit=500, include_stub="true")["rows"] == want["usage"]
    finally:
        second.stop()
        second.kill_engines()
