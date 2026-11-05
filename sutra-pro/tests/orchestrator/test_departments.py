"""DepartmentStore (ORCH-5): the rows `Services.department` returns, the wire shapes, invariant I4, department.json and the orphan sweep."""
import json

import pytest
from factories_org import dept_op, rename_op
from orchestrator.test_chart_store import Env

from sutra_app.engine.spec import DEPT_ID_RE
from sutra_app.orchestrator.departments import ENGINE_OWNED, MIRROR_NAME, DepartmentStore
from sutra_app.orchestrator.errors import NotFound
from sutra_app.orchestrator.models import DeptRow


@pytest.fixture
def built(db, settings, clock, events):
    return Env(db, settings, clock, events).build()


@pytest.fixture
def store(built, settings) -> DepartmentStore:
    return built.chart.departments


def folder(settings, dept: str):
    return settings.data_dir / "departments" / dept


def add_task(env, n: int, dept: str, status: str, *, run: str | None = None, created: int | None = None, started=None, ended=None, pid=None):
    env.sql("INSERT INTO tasks(id, dept_id, title, user_text, status, run_id, created_at, started_at, ended_at, pid) VALUES (?,?,?,?,?,?,?,?,?,?)",
            f"tsk_{n:012x}", dept, f"Task {n}", "u", status, run, created if created is not None else n, started, ended, pid)
    return f"tsk_{n:012x}"


# ---- row (Services.department) ------------------------------------------------------------------------------------------------

def test_row_gives_the_id_and_the_chart_name_and_a_department_is_never_archived(store):
    assert store.row("web") == DeptRow(id="web", name="Web", archived=False, merged_into_name="")


def test_row_follows_a_rename(built, store):
    built.apply(rename_op("web", name="Web Studio"))
    assert store.row("web").name == "Web Studio"


@pytest.mark.parametrize("dept_id", ["nope", "menu", "root", "", "Web", "web.identity", "../web", None, 7])
def test_row_is_none_for_an_unknown_id_a_division_the_root_or_a_malformed_id(store, dept_id):
    assert store.row(dept_id) is None


def test_row_refuses_an_id_that_breaks_the_url_and_folder_rule_even_when_a_row_exists(built, store):
    built.sql("PRAGMA foreign_keys = OFF")
    built.sql("INSERT INTO org_nodes(id, kind, name, created_rev, ts) VALUES ('under_score', 'department', 'Odd', 1, 0)")
    built.sql("INSERT INTO departments(id, home_dir, body, sha256, ts) VALUES ('under_score', 'departments/under_score', '{}', 'x', 0)")
    assert store.row("under_score") is None


def test_department_ids_made_from_any_name_obey_the_url_and_folder_rule(built):
    import re
    for name in ("Café Ünïcode", "3D printing", "A", "Ops & Support!!", "x" * 80, "日本語"):
        result = built.apply(dept_op("$d", name))
        assert re.fullmatch(DEPT_ID_RE, result.added[0]), (name, result.added)
    assert len({r["id"] for r in built.sql("SELECT id FROM departments")}) == 8


# ---- the wire shapes -----------------------------------------------------------------------------------------------------------

def test_a_department_out_has_name_purpose_state_session_and_five_function_chips_in_order(built, store):
    built.apply(rename_op("web", purpose="Sites"))
    out = store.get("web")
    assert (out.id, out.name, out.purpose, out.node_status, out.live_task_id) == ("web", "Web", "Sites", "idle", None)
    assert out.session_id == built.session_of("web")
    assert [(c.id, c.fn, c.status) for c in out.functions] == [(f"web.{fn}", fn, "idle") for fn in ("identity", "adaptation", "priority", "coordination", "audit")]
    assert [c.chat_session_id for c in out.functions] == [built.session_of(f"web.{fn}") for fn in ("identity", "adaptation", "priority", "coordination", "audit")]


def test_the_live_task_and_the_node_status_show_up(built, store):
    add_task(built, 1, "web", "done", run="j2-20261104-100001-aaaa")
    live = add_task(built, 2, "web", "waiting_user", run="j2-20261104-100002-aaaa")
    add_task(built, 3, "web", "queued")
    with built.db.tx() as tx:
        built.graph.aggregate(tx)
    out = store.get("web")
    assert (out.live_task_id, out.node_status) == (live, "waiting_on_you")
    assert store.get("sales").live_task_id is None


def test_the_list_is_in_chart_order_and_an_unknown_department_is_not_found(built, store):
    assert [d.id for d in store.listing()] == ["sales", "web"]
    built.apply(dept_op("$s", "Support"))
    assert [d.id for d in store.listing()] == ["sales", "web", "support"]
    with pytest.raises(NotFound):
        store.get("ghost")
    with pytest.raises(NotFound):
        store.get("menu")


def test_runs_are_the_tasks_with_a_run_folder_newest_first(built, store):
    add_task(built, 1, "web", "done", run="j2-20261104-100001-aaaa", created=1, started=100, ended=200)
    add_task(built, 2, "web", "running", run="j2-20261104-100002-aaaa", created=2, started=300, pid=4242)
    add_task(built, 3, "web", "queued", created=3)
    add_task(built, 4, "sales", "done", run="j2-20261104-100004-aaaa", created=4, started=1, ended=2)
    runs = store.runs("web")
    assert [(r.run_id, r.status, r.pid, r.dir) for r in runs] == [
        ("j2-20261104-100002-aaaa", "running", 4242, "departments/web/runs/j2-20261104-100002-aaaa"),
        ("j2-20261104-100001-aaaa", "done", None, "departments/web/runs/j2-20261104-100001-aaaa")]
    assert runs[1].started_at == "1970-01-01T00:01:40Z" and runs[1].ended_at == "1970-01-01T00:03:20Z" and runs[0].ended_at is None
    assert runs[0].task_id == "tsk_000000000002" and runs[0].dept_id == "web"
    with pytest.raises(NotFound):
        store.runs("ghost")
    assert store.runs("sales")[0].task_id == "tsk_000000000004"


# ---- I4 ------------------------------------------------------------------------------------------------------------------------

def test_a_healthy_chart_has_no_department_problems(store):
    assert store.problems() == []


def test_a_missing_home_folder_a_missing_function_node_and_a_missing_row_are_reported(built, store, settings):
    import shutil
    shutil.rmtree(folder(settings, "web"))
    built.sql("PRAGMA foreign_keys = OFF")
    built.sql("DELETE FROM graph_nodes WHERE id = 'sales.audit'")
    built.sql("DELETE FROM departments WHERE id = 'sales'")
    built.sql("PRAGMA foreign_keys = ON")
    assert store.problems() == ["sales: no departments row", "web: the home folder departments/web does not exist"]
    built.sql("INSERT INTO departments SELECT * FROM (SELECT 'sales', 'departments/sales', body, sha256, ts FROM departments WHERE id = 'web')")
    assert store.problems() == ["sales: no function node audit", "web: the home folder departments/web does not exist"]


# ---- department.json -------------------------------------------------------------------------------------------------------------

def test_a_new_department_gets_its_mirror_after_the_commit(built, settings):
    body = json.loads((folder(settings, "web") / MIRROR_NAME).read_text())
    assert body["id"] == "web" and body["name"] == "Web" and body["home_dir"] == "departments/web" and body["created"].endswith("Z")
    assert oct((folder(settings, "web") / "runs").stat().st_mode & 0o777) == "0o700"


def test_the_mirror_follows_a_rename_and_never_blocks_a_failed_write(built, store, settings):
    built.apply(rename_op("web", name="Web Studio", purpose="Sites"))
    body = json.loads((folder(settings, "web") / MIRROR_NAME).read_text())
    assert (body["name"], body["purpose"]) == ("Web Studio", "Sites")
    assert store.write_mirror("ghost") is False
    (folder(settings, "web") / MIRROR_NAME).unlink()
    (folder(settings, "web") / MIRROR_NAME).mkdir()                            # a directory where the file goes: the write fails
    assert store.write_mirror("web") is False


# ---- the orphan sweep -----------------------------------------------------------------------------------------------------------

def test_sweep_removes_empty_orphan_folders_and_only_those(built, store, settings):
    base = settings.data_dir / "departments"
    (base / "ghost" / "runs").mkdir(parents=True)
    (base / "empty").mkdir()
    (base / "with-file").mkdir()
    (base / "with-file" / "notes.txt").write_text("x")
    (base / "Not_A_Dept").mkdir()
    (base / "stray.txt").write_text("x")
    assert store.sweep() == 2
    assert not (base / "ghost").exists() and not (base / "empty").exists()
    assert (base / "with-file").is_dir() and (base / "Not_A_Dept").is_dir() and (base / "stray.txt").is_file()
    assert (base / "web" / "runs").is_dir() and (base / "sales").is_dir()                  # known departments are never touched
    assert store.sweep() == 0


@pytest.mark.parametrize("entry", ENGINE_OWNED)
def test_sweep_keeps_a_folder_that_holds_an_engine_owned_entry(built, store, settings, entry):
    held = settings.data_dir / "departments" / "kept"
    held.mkdir(parents=True)
    if entry == "memory":
        (held / entry).mkdir()
    else:
        (held / entry).write_text("{}")
    assert store.sweep() == 0 and held.is_dir()


def test_sweep_keeps_a_symlink_and_survives_a_missing_departments_folder(built, store, settings, tmp_path):
    base = settings.data_dir / "departments"
    (base / "linked").symlink_to(tmp_path)
    assert store.sweep() == 0 and (base / "linked").is_symlink()
    assert DepartmentStore(built.db, tmp_path / "nowhere").sweep() == 0
