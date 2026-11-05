"""GAP-DATA: `sutra-pro export chart | team | usage` (gaps G13). Read-only copies of the chart, a team's deliverables and the usage table.

The real data comes from the GAP-E2E harness (the Brew Lab scenario on the stub connector, stopped afterwards so the folder is still); the
edge cases (which run is the last finished one, which Atom log rows belong to a team) use a small migrated database made here.
"""
import csv
import hashlib
import io
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))
from harness import LiveApp, run_new_team                                            # noqa: E402

from sutra_app.config import Settings                                                # noqa: E402
from sutra_app.library.org_chart import ChartChange, OrgChart                        # noqa: E402
from sutra_app.ops import cli, exporter                                              # noqa: E402
from sutra_app.orchestrator.db import Database                                       # noqa: E402
from sutra_app.orchestrator.testing.scripted import ScriptedConnector                # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith(("SUTRA_", "J2_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("SUTRA_ENV_FILE", str(tmp_path / "none.env"))


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """The Brew Lab journey, finished; the app is stopped, the data folder stays. -> (Settings, task id, run id)."""
    root = tmp_path_factory.mktemp("export")
    live = LiveApp(root, connector=ScriptedConnector()).start()
    try:
        journey = run_new_team(live)
        run_id = journey.run_id
        assert live.task_status(journey.task) == "done"
    finally:
        live.stop()
        live.kill_engines()
    return live.settings, journey.task, run_id


def run_cli(capsys, *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def tree_digest(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def db_rows(settings: Settings, sql: str, *args):
    conn = sqlite3.connect(f"file:{settings.db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


# ============================================================ chart ===========================================================

def test_chart_export_has_the_head_chart_the_whole_log_and_the_schema_versions(real, tmp_path, capsys):
    settings, _, _ = real
    out = tmp_path / "chart.json"
    code, text, _ = run_cli(capsys, "export", "chart", "--data-dir", str(settings.data_dir), "--out", str(out))
    assert code == 0 and "revision 2" in text and "2 change(s)" in text
    doc = json.loads(out.read_text())
    assert doc["export"] == "sutra-pro-chart" and doc["export_version"] == 1 and doc["schemas"] == {"org_chart": 1, "chart_change": 1}
    assert doc["exported"].endswith("Z") and doc["app_version"]
    head = OrgChart.model_validate(doc["head"])
    [stored] = db_rows(settings, "SELECT revision, sha256 FROM org_charts ORDER BY revision DESC LIMIT 1")
    assert head.revision == stored["revision"] == 2 and doc["head_sha256"] == stored["sha256"]
    assert {n.id for n in head.nodes} == {"root", "web"}
    rows = db_rows(settings, "SELECT * FROM chart_changes ORDER BY seq")
    assert [c["seq"] for c in doc["changes"]] == [r["seq"] for r in rows] == [1, 2]
    seed, add = doc["changes"]
    assert seed["change"] is None and OrgChart.model_validate(seed["seed_chart"]).revision == 1
    assert add["seed_chart"] is None and ChartChange.model_validate(add["change"]).kind == "add"
    assert (add["id"], add["status"], add["actor"], add["before_sha"], add["after_sha"]) == ("chg-0002", "applied", "chat_agent", rows[1]["before_sha"], rows[1]["after_sha"])
    assert add["before_sha"] == seed["after_sha"] and add["summary"] == rows[1]["summary"] and add["task_id"] == rows[1]["task_id"]


def test_chart_export_defaults_to_a_stamped_file_in_the_current_folder(real, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, text, _ = run_cli(capsys, "export", "chart", "--data-dir", str(real[0].data_dir), "--json")
    payload = json.loads(text)
    [made] = list(tmp_path.glob("sutra-pro-chart-*Z.json"))
    assert code == 0 and Path(payload["path"]) == made and payload["revision"] == 2 and payload["changes"] == 2
    assert made.stat().st_mode & 0o777 == 0o600


def test_chart_export_to_standard_output(real, capsys):
    code, text, _ = run_cli(capsys, "export", "chart", "--data-dir", str(real[0].data_dir), "--out", "-")
    assert code == 0 and json.loads(text)["head"]["revision"] == 2


def test_an_existing_output_file_is_never_overwritten(real, tmp_path, capsys):
    out = tmp_path / "mine.json"
    out.write_text("precious")
    code, _, err = run_cli(capsys, "export", "chart", "--data-dir", str(real[0].data_dir), "--out", str(out))
    assert code == 1 and "already exists" in err and out.read_text() == "precious"


def test_export_is_read_only(real, tmp_path, capsys):
    settings, _, _ = real
    before = tree_digest(settings.data_dir)
    run_cli(capsys, "export", "chart", "--data-dir", str(settings.data_dir), "--out", str(tmp_path / "c.json"))
    run_cli(capsys, "export", "team", "web", "--data-dir", str(settings.data_dir), "--out", str(tmp_path / "team"))
    run_cli(capsys, "export", "usage", "--csv", "--data-dir", str(settings.data_dir), "--out", str(tmp_path / "u.csv"))
    assert tree_digest(settings.data_dir) == before


def test_chart_export_stops_on_a_record_that_no_longer_matches_the_models(tmp_path, capsys):
    settings = make_folder(tmp_path)
    seed_chart(settings)
    conn = sqlite3.connect(settings.db_path)
    conn.execute("UPDATE chart_changes SET body = '{\"kind\": \"add\"}' WHERE id = 'chg-0002'")
    conn.commit()
    conn.close()
    code, _, err = run_cli(capsys, "export", "chart", "--data-dir", str(settings.data_dir), "--out", str(tmp_path / "c.json"))
    assert code == 1 and "no longer matches the library models" in err and not (tmp_path / "c.json").exists()


def test_exports_say_so_when_there_is_no_database(tmp_path, capsys):
    (tmp_path / "d").mkdir()
    for argv in (("chart",), ("team", "web"), ("usage", "--csv")):
        code, _, err = run_cli(capsys, "export", *argv, "--data-dir", str(tmp_path / "d"))
        assert code == 1 and "no database" in err
    assert not (tmp_path / "d" / "db.sqlite3").exists()                                 # reading never creates one


# ============================================================ team ============================================================

def test_team_export_copies_charter_site_summary_and_the_atom_log_rows(real, tmp_path, capsys):
    settings, task, run_id = real
    run = settings.departments_dir / "web" / "runs" / run_id
    (run / "site" / "shots").mkdir(exist_ok=True)
    (run / "site" / "shots" / "v1.png").write_bytes(b"png")
    (run / "documents.json").write_text('{"d": 1}')
    out = tmp_path / "team"
    code, text, _ = run_cli(capsys, "export", "team", "web", "--data-dir", str(settings.data_dir), "--out", str(out))
    assert code == 0 and run_id in text
    info = json.loads((out / "EXPORT.json").read_text())
    assert (info["dept"], info["task_id"], info["run_id"], info["status"]) == ("web", task, run_id, "done")
    for name in ("goal.json", "summary.json", "documents.json", "site/index.html", "site/v1.html", "artifacts.json"):
        assert (out / name).read_bytes() == (run / name).read_bytes(), name
    assert not (out / "site" / "shots").exists() and "site/shots/v1.png" not in info["files"]
    assert {"goal.json", "summary.json", "atom-ledger.jsonl", "site/index.html"} <= set(info["files"]) and "EXPORT.json" not in info["files"]
    lines = [json.loads(line) for line in (out / "atom-ledger.jsonl").read_text().splitlines()]
    want = db_rows(settings, "SELECT l.seq, l.atom_id, l.status FROM atom_ledger l JOIN graph_nodes n ON n.id = l.node_id WHERE n.department_id = 'web' ORDER BY l.seq")
    assert len(lines) == len(want) == info["ledger_rows"] > 5
    assert [(x["seq"], x["atom_id"], x["status"]) for x in lines] == [tuple(w) for w in want]
    assert all(isinstance(x["body"], dict) and x["body"] for x in lines)


def test_team_export_default_folder_and_json(real, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, text, _ = run_cli(capsys, "export", "team", "web", "--data-dir", str(real[0].data_dir), "--json")
    [made] = list(tmp_path.glob("sutra-pro-team-web-*Z"))
    assert code == 0 and Path(json.loads(text)["path"]) == made and (made / "summary.json").is_file()


def test_team_export_refuses_a_folder_that_is_not_empty_and_uses_an_empty_one(real, tmp_path, capsys):
    full = tmp_path / "full"
    full.mkdir()
    (full / "x").write_text("x")
    code, _, err = run_cli(capsys, "export", "team", "web", "--data-dir", str(real[0].data_dir), "--out", str(full))
    assert code == 1 and "not empty" in err and sorted(p.name for p in full.iterdir()) == ["x"]
    empty = tmp_path / "empty"
    empty.mkdir()
    assert run_cli(capsys, "export", "team", "web", "--data-dir", str(real[0].data_dir), "--out", str(empty))[0] == 0


@pytest.mark.parametrize("dept, message", [("nope", "no team 'nope'"), ("../etc", "not a team id"), ("Web", "not a team id")])
def test_team_export_refuses_an_unknown_or_unsafe_team(real, tmp_path, capsys, dept, message):
    code, _, err = run_cli(capsys, "export", "team", dept, "--data-dir", str(real[0].data_dir), "--out", str(tmp_path / "o"))
    assert code == 1 and message in err and not (tmp_path / "o").exists()


# ---- which run, which rows (a small database) -------------------------------------------------------------------------------

def make_folder(tmp_path: Path) -> Settings:
    root = tmp_path / "small"
    root.mkdir()
    db = Database(root / "db.sqlite3", lambda events: None)
    db.migrate()
    db.close()
    return Settings.load({}, data_dir=root, env_file=tmp_path / "none.env")


def sql(settings: Settings, query: str, *args) -> None:
    conn = sqlite3.connect(settings.db_path)
    conn.execute(query, args)
    conn.commit()
    conn.close()


def seed_chart(settings: Settings) -> None:
    """Chart rows made by the library: the seed (change 1) and a department add (change 2), as the chart store writes them."""
    from sutra_app.library.org_chart import AddOp, NewNode, seed_chart as library_seed
    seed = library_seed("root", 1)
    change = ChartChange(kind="add", id="chg-0002", task_id="req-2", base_revision=1, reason="a team", ops=[AddOp(node=NewNode(kind="department", name="Web", purpose="p", parent="root", ref="$web"))], ts=2)
    sql(settings, "INSERT INTO org_charts(revision, body, sha256, ts) VALUES (1, ?, 'sha1', 1)", seed.model_dump_json())
    sql(settings, "INSERT INTO chart_changes(seq, id, task_id, kind, actor, base_revision, result_revision, status, summary, body, before_sha, after_sha, ts)"
                  " VALUES (1,'chg-0001','boot','add','system',0,1,'applied','seed',?, '', 'sha1', 1)", seed.model_dump_json())
    sql(settings, "INSERT INTO chart_changes(seq, id, task_id, kind, actor, base_revision, result_revision, status, summary, body, before_sha, after_sha, ts)"
                  " VALUES (2,'chg-0002','req-2','add','chat_agent',1,2,'applied','add Web',?, 'sha1', 'sha2', 2)", change.model_dump_json())


def add_team(settings: Settings, dept: str) -> None:
    sql(settings, "INSERT INTO departments(id, home_dir, body, sha256, ts) VALUES (?, ?, '{}', 'x', 1)", dept, f"departments/{dept}")


def add_task(settings: Settings, n: int, dept: str, status: str, ended: int | None, run_id: str | None, summary: str = "") -> Path | None:
    sql(settings, "INSERT INTO tasks(id, dept_id, title, user_text, status, run_id, created_at, ended_at) VALUES (?,?,?,?,?,?,?,?)",
        f"tsk_{n}", dept, f"task {n}", "u", status, run_id, 100 + n, ended)
    if run_id is None:
        return None
    run = settings.departments_dir / dept / "runs" / run_id
    run.mkdir(parents=True)
    (run / "summary.json").write_text(summary or f'{{"n": {n}}}')
    (run / "goal.json").write_text(f'{{"goal": {n}}}')
    return run


def test_the_last_finished_run_is_the_newest_good_end_not_a_failed_or_running_one(tmp_path, capsys):
    s = make_folder(tmp_path)
    add_team(s, "web")
    add_task(s, 1, "web", "done", 1000, "j2-old")
    add_task(s, 2, "web", "done_with_open_items", 3000, "j2-new")
    add_task(s, 3, "web", "crashed", 5000, "j2-crashed")
    add_task(s, 4, "web", "running", None, "j2-live")
    add_task(s, 5, "web", "done", 2000, "j2-middle")
    folder, info = exporter.export_team(s, "web", tmp_path / "o")
    assert info["run_id"] == "j2-new" and info["status"] == "done_with_open_items" and json.loads((folder / "summary.json").read_text()) == {"n": 2}


def test_goal_versions_are_copied_beside_the_charter_and_other_files_are_not(tmp_path):
    s = make_folder(tmp_path)
    add_team(s, "web")
    run = add_task(s, 1, "web", "done", 1000, "j2-a")
    (run / "goal.v2.json").write_text("{}")
    (run / "goal.bak").write_text("no")
    (run / "goalpost.json").write_text("no")
    (run / "trace.jsonl").write_text("bulky")
    folder, info = exporter.export_team(s, "web", tmp_path / "o")
    assert {"goal.json", "goal.v2.json"} <= set(info["files"]) and not [f for f in info["files"] if f in ("goal.bak", "goalpost.json", "trace.jsonl")]


def test_a_team_with_no_finished_run_or_a_missing_run_folder_is_refused(tmp_path):
    s = make_folder(tmp_path)
    add_team(s, "web")
    add_team(s, "ops")
    add_task(s, 1, "web", "running", None, "j2-a")
    add_task(s, 2, "ops", "done", 10, "j2-gone")
    import shutil
    shutil.rmtree(s.departments_dir / "ops" / "runs" / "j2-gone")
    with pytest.raises(exporter.ExportError, match="no finished run"):
        exporter.export_team(s, "web", tmp_path / "a")
    with pytest.raises(exporter.ExportError, match="run folder .* is missing"):
        exporter.export_team(s, "ops", tmp_path / "b")


def test_links_in_the_run_folder_are_not_followed(tmp_path):
    s = make_folder(tmp_path)
    add_team(s, "web")
    run = add_task(s, 1, "web", "done", 10, "j2-a")
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    (run / "site").mkdir()
    (run / "site" / "index.html").write_text("ok")
    (run / "site" / "leak.txt").symlink_to(secret)
    (run / "documents.json").symlink_to(secret)
    folder, _ = exporter.export_team(s, "web", tmp_path / "o")
    assert (folder / "site" / "index.html").is_file() and not (folder / "site" / "leak.txt").exists() and not (folder / "documents.json").exists()


def test_atom_log_rows_are_the_teams_own_through_node_or_atom_in_seq_order(tmp_path):
    s = make_folder(tmp_path)
    for dept in ("web", "ops"):
        add_team(s, dept)
        sql(s, "INSERT INTO graph_nodes(id, kind, department_id, label, body, sha256, ts) VALUES (?, 'identity', ?, 'l', '{}', 'x', 1)", f"{dept}.identity", dept)
    add_task(s, 1, "web", "done", 10, "j2-a")
    for atom, node in (("a1", "web.identity"), ("a2", "ops.identity"), ("a3", "web.identity"), ("a4", "step.of.web")):
        sql(s, "INSERT INTO atom_ledger(atom_id, node_id, status, body, ts) VALUES (?, ?, 'closed', ?, 1)", atom, node, json.dumps({"atom_id": atom}))
    sql(s, "INSERT INTO atoms(id, schema, node_id, department_id, state, display, attempt, goal, body, sha256, ts_open)"
           " VALUES ('a4','atom/1','step.of.web','web','closed','closed',0,'g','{}','x',1)")
    _, info = exporter.export_team(s, "web", tmp_path / "o")
    lines = [json.loads(x) for x in (tmp_path / "o" / "atom-ledger.jsonl").read_text().splitlines()]
    assert [x["atom_id"] for x in lines] == ["a1", "a3", "a4"] and info["ledger_rows"] == 3 and [x["seq"] for x in lines] == sorted(x["seq"] for x in lines)
    assert lines[0]["body"] == {"atom_id": "a1"}


# ============================================================ usage ===========================================================

def test_usage_csv_has_every_row_with_times_in_utc_and_empty_cells_for_null(real, tmp_path, capsys):
    settings, _, _ = real
    out = tmp_path / "usage.csv"
    code, text, _ = run_cli(capsys, "export", "usage", "--csv", "--data-dir", str(settings.data_dir), "--out", str(out), "--json")
    rows = list(csv.DictReader(io.StringIO(out.read_text())))
    stored = db_rows(settings, "SELECT * FROM usage_ledger ORDER BY id")
    assert code == 0 and json.loads(text)["rows"] == len(rows) == len(stored) > 5
    assert list(rows[0]) == list(exporter.USAGE_COLUMNS)
    assert [int(r["id"]) for r in rows] == [r["id"] for r in stored]
    first, source = rows[0], stored[0]
    assert first["at"] == datetime.fromtimestamp(source["at"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert first["provider"] == source["provider"] and first["atom_id"] == source["atom_id"] and int(first["tokens_in"]) == source["tokens_in"]
    assert float(first["usd"]) == source["usd"] and first["ok"] == "1"


def test_usage_needs_csv_and_goes_to_stdout_or_a_stamped_file(real, tmp_path, monkeypatch, capsys):
    data = str(real[0].data_dir)
    assert run_cli(capsys, "export", "usage", "--data-dir", data)[0] == 2
    code, text, _ = run_cli(capsys, "export", "usage", "--csv", "--data-dir", data, "--out", "-")
    assert code == 0 and text.splitlines()[0].startswith("id,at,provider")
    monkeypatch.chdir(tmp_path)
    assert run_cli(capsys, "export", "usage", "--csv", "--data-dir", data)[0] == 0
    [made] = list(tmp_path.glob("sutra-pro-usage-*Z.csv"))
    code, _, err = run_cli(capsys, "export", "usage", "--csv", "--data-dir", data, "--out", str(made))
    assert code == 1 and "already exists" in err


def test_usage_csv_of_an_empty_table_is_just_the_header(tmp_path):
    s = make_folder(tmp_path)
    assert exporter.export_usage(s) == ",".join(exporter.USAGE_COLUMNS) + "\n"


def test_null_cells_and_commas_survive_the_csv_round_trip(tmp_path):
    s = make_folder(tmp_path)
    sql(s, "INSERT INTO usage_ledger(at, provider, model, purpose, usd, how) VALUES (1800000000, 'claude', 'm,odel \"x\"', 'agent_turn', NULL, 'cli')")
    [row] = list(csv.DictReader(io.StringIO(exporter.export_usage(s))))
    assert row["model"] == 'm,odel "x"' and row["usd"] == "" and row["at"] == "2027-01-15T08:00:00Z" and row["atom_id"] == ""


def test_the_export_command_is_registered_and_needs_a_subcommand(capsys):
    cli.build_parser()
    assert "export" in cli.COMMANDS
    with pytest.raises(SystemExit) as caught:
        cli.main(["export"])
    assert caught.value.code == 2
