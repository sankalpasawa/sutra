"""The database layer and the DDL: migrations, pragmas, transactions and events, StoreContext, and every constraint of 4.1."""
import sqlite3
import threading

import anyio
import pytest

from sutra_app.library.gate import GATE
from sutra_app.library.org_chart import seed_chart
from sutra_app.orchestrator import db as dbmod
from sutra_app.orchestrator import schema
from sutra_app.orchestrator.db import Database, SchemaError, StoreContext, StoreContextError, run_blocking
from sutra_app.orchestrator.errors import StoreBusy

T = "tsk_aaaaaaaaaaaa"
T2 = "tsk_bbbbbbbbbbbb"


def sql(db, text, *args):
    return db.conn().execute(text, args)


def names(db, kind="table"):
    return {r[0] for r in sql(db, "SELECT name FROM sqlite_master WHERE type = ?", kind)}


def seed(db):
    """root and the department web with its three graph nodes, one session and one queued task."""
    sql(db, "INSERT INTO org_nodes(id, kind, name, created_rev, ts) VALUES ('root','root','Root',1,0),('web','department','Web',2,0)")
    sql(db, "INSERT INTO org_edges(parent_id, child_id) VALUES ('root','web')")
    sql(db, "INSERT INTO departments(id, home_dir, body, sha256, ts) VALUES ('web','departments/web','{}','x',0)")
    sql(db, "INSERT INTO tasks(id, dept_id, title, user_text, status, created_at) VALUES (?, 'web', 't', 'u', 'queued', 1)", T)
    for node_id, kind in (("root", "root"), ("web", "department"), ("web.identity", "identity")):
        sql(db, "INSERT INTO graph_nodes(id, kind, label, body, sha256, ts) VALUES (?,?,?,'{}','x',0)", node_id, kind, node_id)
    sql(db, "INSERT INTO graph_nodes(id, kind, label, task_id, step_ref, body, sha256, ts) VALUES ('s-1111111111','step','s',?, 'task','{}','x',0)", T)
    sql(db, "INSERT INTO chat_sessions(id, node_id, kind, title, created_at, updated_at) VALUES ('cs_org','root','org','Org',0,0)")


def atom(db, atom_id, schema_name="work-atom/0.3", state="open", display="open", attempt=1, node="web.identity"):
    sql(db, "INSERT INTO atoms(id, schema, node_id, state, display, attempt, goal, body, sha256, ts_open) VALUES (?,?,?,?,?,?,'g','{}','x',1)",
        atom_id, schema_name, node, state, display, attempt)


def usage(db, call_ref="r:1", task=T, provider="claude", **over):
    cols = {"at": 1, "provider": provider, "purpose": "p", "task_id": task, "call_ref": call_ref, **over}
    sql(db, f"INSERT INTO usage_ledger({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", *cols.values())


def change(db, id_="chg-0001", **over):
    cols = {"id": id_, "task_id": "req-1", "kind": "add", "actor": "chat_agent", "base_revision": 1, "status": "applied", "summary": "s",
            "body": "{}", "ts": 1, **over}
    sql(db, f"INSERT INTO chart_changes({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", *cols.values())


# ---- migrations and pragmas --------------------------------------------------------------------------------------

def test_migrate_creates_every_table_and_sets_the_version(db):
    assert db.version() == schema.SCHEMA_VERSION >= 3                      # not == 3: another package appends a migration too
    assert {n for n in names(db) if not n.startswith("chat_search")} - {"sqlite_sequence"} == set(schema.TABLES)      # chat_search is FTS5: it brings its shadow tables


def test_migrate_again_is_a_no_op(db):
    sql(db, "INSERT INTO meta VALUES ('k','v')")
    assert db.migrate() == schema.SCHEMA_VERSION
    assert sql(db, "SELECT count(*) FROM meta").fetchone()[0] == 1


def test_pragmas(db):
    one = lambda p: sql(db, f"PRAGMA {p}").fetchone()[0]          # noqa: E731
    assert (one("journal_mode"), one("synchronous"), one("foreign_keys"), one("busy_timeout")) == ("wal", 1, 1, 5000)


def test_a_database_from_a_newer_app_is_refused(db, settings, events):
    sql(db, "PRAGMA user_version = 9")
    with pytest.raises(SchemaError, match="newer"):
        Database(settings.db_path, events).migrate()


def test_a_failing_migration_leaves_the_file_untouched(settings, events):
    fresh = Database(settings.data_dir / "other.sqlite3", events)
    with pytest.raises(sqlite3.OperationalError):
        fresh.migrate([("CREATE TABLE a (x)", "CREATE TABLE a (y)")])        # the second statement fails
    assert fresh.version() == 0 and names(fresh) == set()
    fresh.migrate([("CREATE TABLE a (x)",), lambda conn: conn.execute("CREATE TABLE b (y)")])
    assert fresh.version() == 2 and {"a", "b"} <= names(fresh)
    fresh.close()


def test_a_database_at_version_two_gets_the_recurring_tables_and_keeps_its_rows(settings, events):
    old = Database(settings.data_dir / "v2.sqlite3", events)
    old.migrate(schema.MIGRATIONS[:2])
    sql(old, "INSERT INTO meta VALUES ('k','v')")
    assert old.version() == 2 and not {"recurring", "recurring_runs"} & names(old)
    assert old.migrate() == schema.SCHEMA_VERSION >= 3
    assert {"recurring", "recurring_runs"} <= names(old) and sql(old, "SELECT count(*) FROM meta").fetchone()[0] == 1
    old.close()


def test_a_due_time_is_unique_per_schedule_and_runs_go_with_their_schedule(db):
    seed(db)
    sql(db, "INSERT INTO recurring(id, dept_id, text, schedule_json, cursor_at, created_at, updated_at) VALUES ('rec_aaaaaaaaaaaa','web','t','{}',1,1,1)")
    sql(db, "INSERT INTO recurring_runs(recurring_id, due_at, at, trigger, outcome) VALUES ('rec_aaaaaaaaaaaa', 100, 100, 'schedule', 'skipped')")
    with pytest.raises(sqlite3.IntegrityError):
        sql(db, "INSERT INTO recurring_runs(recurring_id, due_at, at, trigger, outcome) VALUES ('rec_aaaaaaaaaaaa', 100, 101, 'catch_up', 'started')")
    with pytest.raises(sqlite3.IntegrityError):
        sql(db, "INSERT INTO recurring_runs(recurring_id, due_at, at, trigger, outcome) VALUES ('rec_aaaaaaaaaaaa', 200, 200, 'nope', 'started')")
    sql(db, "DELETE FROM recurring WHERE id = 'rec_aaaaaaaaaaaa'")
    assert sql(db, "SELECT count(*) FROM recurring_runs").fetchone()[0] == 0


def test_ddl_statements_are_complete_and_carry_the_settled_additions(db):
    assert all(sqlite3.complete_statement(s + ";") for s in schema.DDL_V1)
    cols = lambda t: {r[1]: r for r in sql(db, f"PRAGMA table_info({t})")}      # noqa: E731
    assert {"task_title", "result_json"} <= set(cols("chart_changes"))
    assert cols("chart_changes")["result_json"][4] == "'{}'" and cols("chart_changes")["task_title"][4] == "''"
    assert "display" in cols("atoms") and "filed_under" in cols("chat_sessions")
    assert {"step", "atom_id", "detail_json"} <= set(cols("usage_ledger"))
    assert {"atoms_node_display", "one_open_atom_per_node", "usage_call", "chat_sessions_active"} <= names(db, "index")
    assert {"atom_ledger_no_update", "atom_ledger_no_delete"} <= names(db, "trigger")


# ---- every constraint of 4.1 ------------------------------------------------------------------------------------------

BAD = {
    "second root": ("INSERT INTO org_nodes(id, kind, name, created_rev, ts) VALUES ('r2','root','R',1,0)",),
    "org kind word": ("INSERT INTO org_nodes(id, kind, name, created_rev, ts) VALUES ('x','team','X',1,0)",),
    "org state word": ("INSERT INTO org_nodes(id, kind, name, state, created_rev, ts) VALUES ('x','division','X','gone',1,0)",),
    "task status word": ("INSERT INTO tasks(id, dept_id, title, user_text, status, created_at) VALUES ('t9','web','t','u','archived',1)",),
    "task without department": ("INSERT INTO tasks(id, dept_id, title, user_text, status, created_at) VALUES ('t9','nope','t','u','queued',1)",),
    "node kind word": ("INSERT INTO graph_nodes(id, kind, label, body, sha256, ts) VALUES ('n1','function','f','{}','x',0)",),
    "node state word": ("INSERT INTO graph_nodes(id, kind, label, state, body, sha256, ts) VALUES ('n1','division','f','archived','{}','x',0)",),
    "step without task": ("INSERT INTO graph_nodes(id, kind, label, body, sha256, ts) VALUES ('s-2','step','f','{}','x',0)",),
    "non-step with task": ("INSERT INTO graph_nodes(id, kind, label, task_id, step_ref, body, sha256, ts) VALUES ('n1','division','f','tsk_aaaaaaaaaaaa','task','{}','x',0)",),
    "duplicate step": ("INSERT INTO graph_nodes(id, kind, label, task_id, step_ref, body, sha256, ts) VALUES ('s-2222222222','step','f','tsk_aaaaaaaaaaaa','task','{}','x',0)",),
    "stored contains edge": ("INSERT INTO graph_edges(id, kind, from_id, to_id, body) VALUES ('contains:root>web','contains','root','web','{}')",),
    "edge to itself": ("INSERT INTO graph_edges(id, kind, from_id, to_id, body) VALUES ('step:web>web','step','web','web','{}')",),
    "edge to nothing": ("INSERT INTO graph_edges(id, kind, from_id, to_id, body) VALUES ('step:web>zzz','step','web','zzz','{}')",),
    "two active sessions per node": ("INSERT INTO chat_sessions(id, node_id, kind, title, created_at, updated_at) VALUES ('cs_2','root','org','Org',0,0)",),
    "session kind word": ("INSERT INTO chat_sessions(id, node_id, kind, title, created_at, updated_at) VALUES ('cs_2','web','group','x',0,0)",),
    "session writable 2": ("INSERT INTO chat_sessions(id, node_id, kind, title, writable, created_at, updated_at) VALUES ('cs_2','web','department','x',2,0,0)",),
    "message role word": ("INSERT INTO chat_messages(session_id, role, who, text, at) VALUES ('cs_org','bot','x','t',1)",),
    "message kind word": ("INSERT INTO chat_messages(session_id, role, who, kind, text, at) VALUES ('cs_org','user','user','shout','t',1)",),
    "message state word": ("INSERT INTO chat_messages(session_id, role, who, text, state, at) VALUES ('cs_org','user','user','t','lost',1)",),
    "message in no session": ("INSERT INTO chat_messages(session_id, role, who, text, at) VALUES ('cs_zzz','user','user','t',1)",),
    "atom schema word": ("INSERT INTO atoms(id, schema, node_id, state, display, attempt, goal, body, sha256, ts_open) VALUES ('a1','work-atom/0.2','web.identity','open','open',1,'g','{}','x',1)",),
    "plugin atom verify_failed": ("INSERT INTO atoms(id, schema, node_id, state, display, attempt, goal, body, sha256, ts_open) VALUES ('a1','work-atom/0.3','web.identity','verify_failed','verify_failed',1,'g','{}','x',1)",),
    "atom/1 refused": ("INSERT INTO atoms(id, schema, node_id, state, display, attempt, goal, body, sha256, ts_open) VALUES ('a1','atom/1','web.identity','refused','refused',1,'g','{}','x',1)",),
    "display word": ("INSERT INTO atoms(id, schema, node_id, state, display, attempt, goal, body, sha256, ts_open) VALUES ('a1','atom/1','web.identity','open','failed',1,'g','{}','x',1)",),
    "attempt 4": ("INSERT INTO atoms(id, schema, node_id, state, display, attempt, goal, body, sha256, ts_open) VALUES ('a1','atom/1','web.identity','open','open',4,'g','{}','x',1)",),
    "atom on no node": ("INSERT INTO atoms(id, schema, node_id, state, display, attempt, goal, body, sha256, ts_open) VALUES ('a1','atom/1','zzz','open','open',1,'g','{}','x',1)",),
    "ledger status word": ("INSERT INTO atom_ledger(atom_id, node_id, status, body, ts) VALUES ('a1','web.identity','open','{}',1)",),
    "usage provider word": ("INSERT INTO usage_ledger(at, provider, purpose) VALUES (1,'gpt','p')",),
    "negative usd": ("INSERT INTO usage_ledger(at, provider, purpose, usd) VALUES (1,'claude','p',-0.01)",),
    "negative tokens": ("INSERT INTO usage_ledger(at, provider, purpose, tokens_in) VALUES (1,'claude','p',-1)",),
    "usage ok 2": ("INSERT INTO usage_ledger(at, provider, purpose, ok) VALUES (1,'claude','p',2)",),
    "change kind word": ("INSERT INTO chart_changes(id, task_id, kind, actor, base_revision, status, summary, body, ts) VALUES ('c','r','merge','user',1,'applied','s','{}',1)",),
    "change actor word": ("INSERT INTO chart_changes(id, task_id, kind, actor, base_revision, status, summary, body, ts) VALUES ('c','r','add','bot',1,'applied','s','{}',1)",),
    "change status word": ("INSERT INTO chart_changes(id, task_id, kind, actor, base_revision, status, summary, body, ts) VALUES ('c','r','add','user',1,'maybe','s','{}',1)",),
}


@pytest.mark.parametrize("what", sorted(BAD))
def test_constraint_fires(db, what):
    seed(db)
    with pytest.raises(sqlite3.IntegrityError):
        sql(db, *BAD[what])


def test_one_parent_each(db):
    seed(db)
    sql(db, "INSERT INTO org_nodes(id, kind, name, created_rev, ts) VALUES ('sub','division','Sub',2,0)")
    sql(db, "INSERT INTO org_edges(parent_id, child_id) VALUES ('web','sub')")
    with pytest.raises(sqlite3.IntegrityError):
        sql(db, "INSERT INTO org_edges(parent_id, child_id) VALUES ('root','sub')")
    with pytest.raises(sqlite3.IntegrityError):
        sql(db, "INSERT INTO org_edges(parent_id, child_id) VALUES ('sub','sub')")


def test_one_live_task_per_department_but_any_number_queued(db):
    seed(db)
    for n in range(3):
        sql(db, "INSERT INTO tasks(id, dept_id, title, user_text, status, created_at) VALUES (?, 'web', 't', 'u', 'queued', 1)", f"q{n}")
    sql(db, "UPDATE tasks SET status = 'running', run_id = 'j2-1' WHERE id = ?", T)
    for live in ("starting", "waiting_user"):
        with pytest.raises(sqlite3.IntegrityError):
            sql(db, "UPDATE tasks SET status = ? WHERE id = 'q0'", live)
    sql(db, "UPDATE tasks SET status = 'done', ended_at = 2 WHERE id = ?", T)
    sql(db, "UPDATE tasks SET status = 'running' WHERE id = 'q0'")              # the slot is free again


def test_run_id_is_unique(db):
    seed(db)
    sql(db, "UPDATE tasks SET run_id = 'j2-1' WHERE id = ?", T)
    sql(db, "INSERT INTO tasks(id, dept_id, title, user_text, status, created_at) VALUES ('t2','web','t','u','queued',1)")
    with pytest.raises(sqlite3.IntegrityError):
        sql(db, "UPDATE tasks SET run_id = 'j2-1' WHERE id = 't2'")


def test_archived_sessions_may_share_a_node_with_the_active_one(db):
    seed(db)
    for n in range(2):
        sql(db, "INSERT INTO chat_sessions(id, node_id, kind, title, status, created_at, updated_at) VALUES (?, 'root', 'org', 'old', 'archived', 0, 0)", f"cs_a{n}")
    assert sql(db, "SELECT count(*) FROM chat_sessions WHERE node_id = 'root'").fetchone()[0] == 3


def test_a_projected_line_is_stored_once_per_session(db):
    seed(db)
    msg = "INSERT INTO chat_messages(session_id, role, who, text, src_ref, at) VALUES ('cs_org','agent','sutra','t',?,1)"
    sql(db, msg, "run#chat:1")
    with pytest.raises(sqlite3.IntegrityError):
        sql(db, msg, "run#chat:1")
    sql(db, msg, "run#chat:2")
    sql(db, "INSERT INTO chat_messages(session_id, role, who, text, at) VALUES ('cs_org','user','user','a',1),('cs_org','user','user','b',2)")   # no ref, no limit


def test_one_open_plugin_atom_per_node_but_several_open_workflow_atoms(db):
    seed(db)
    atom(db, "a-1", display="open")
    with pytest.raises(sqlite3.IntegrityError):
        atom(db, "a-2", display="open")
    atom(db, "a-3", state="closed", display="closed")                           # a closed one beside it is fine
    atom(db, "run1:W-1.a1", "atom/1")
    atom(db, "run1:W-1.a2", "atom/1")


@pytest.mark.parametrize("schema_name,state,display", [("work-atom/0.3", "abandoned", "verify_failed"), ("work-atom/0.3", "refused", "refused"),
                                                       ("atom/1", "verify_failed", "verify_failed")])
def test_each_schema_keeps_its_own_state_words(db, schema_name, state, display):
    seed(db)
    atom(db, "a-x", schema_name, state, display)


def test_usage_call_is_idempotent_by_task_and_call_ref(db):
    seed(db)
    usage(db, "run:1")
    with pytest.raises(sqlite3.IntegrityError):
        usage(db, "run:1")
    cur = sql(db, "INSERT INTO usage_ledger(at, provider, purpose, task_id, call_ref) VALUES (1,'claude','p',?,'run:1') "
                  "ON CONFLICT(task_id, call_ref) WHERE call_ref IS NOT NULL DO NOTHING", T)
    assert cur.rowcount == 0 and sql(db, "SELECT count(*) FROM usage_ledger").fetchone()[0] == 1
    usage(db, "run:1", task=None)                                                 # no task: nothing to collide with
    usage(db, "run:1", task=None)
    usage(db, None); usage(db, None)                                              # no call ref: never a collision
    usage(db, "run:2", provider="stub", atom_id="a-0123456789-01", step="W-1", detail_json="{}")


def test_duplicate_change_id_is_refused_and_defaults_are_filled(db):
    change(db)
    with pytest.raises(sqlite3.IntegrityError):
        change(db)
    row = sql(db, "SELECT seq, task_title, result_json, reason FROM chart_changes").fetchone()
    assert tuple(row) == (1, "", "{}", "")


def test_org_charts_keep_every_revision(db):
    for rev in (1, 2):
        sql(db, "INSERT INTO org_charts(revision, body, sha256, ts) VALUES (?, '{}', 'x', 0)", rev)
    with pytest.raises(sqlite3.IntegrityError):
        sql(db, "INSERT INTO org_charts(revision, body, sha256, ts) VALUES (2, '{}', 'x', 0)")


def test_the_atom_log_is_append_only_with_one_row_per_atom(db):
    seed(db)
    ins = "INSERT INTO atom_ledger(atom_id, node_id, status, body, ts) VALUES (?, 'web.identity', ?, '{}', 1)"
    sql(db, ins, "a-1", "closed")
    for status in ("closed", "verify_failed", "abandoned", "refused"):
        sql(db, ins, f"a-{status}", status)
    with pytest.raises(sqlite3.IntegrityError):
        sql(db, ins, "a-1", "closed")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        sql(db, "UPDATE atom_ledger SET status = 'abandoned' WHERE atom_id = 'a-1'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        sql(db, "DELETE FROM atom_ledger WHERE atom_id = 'a-1'")
    assert [r[0] for r in sql(db, "SELECT seq FROM atom_ledger ORDER BY seq")] == [1, 2, 3, 4, 5]


# ---- transactions and events -------------------------------------------------------------------------------------

def test_commit_publishes_after_the_data_is_visible(db, settings, events):
    seen = []
    other = Database(settings.db_path, lambda batch: seen.append(sql(other, "SELECT count(*) FROM meta").fetchone()[0]))
    with other.tx() as tx:
        tx.conn.execute("INSERT INTO meta VALUES ('a','1')")
        tx.emit("graph.updated", {"version": 1})
        tx.emit("chat.message", {"n": 2})
        assert seen == []                                                            # nothing before COMMIT
    assert seen == [1]
    other.close()
    # the db fixture's own bus gets one batch per transaction, in order, with seq 0 and an ISO time
    with db.tx() as tx:
        tx.emit("a.b", {"x": [1]})
        tx.emit("c.d", {})
    assert [e.type for e in events.batches[-1]] == ["a.b", "c.d"] and events.batches[-1][0].seq == 0
    assert events.batches[-1][0].at.endswith("Z")


def test_rollback_drops_events_and_data(db, events):
    before = len(events.batches)
    with pytest.raises(ZeroDivisionError):
        with db.tx() as tx:
            tx.conn.execute("INSERT INTO meta VALUES ('a','1')")
            tx.emit("x.y", {})
            1 / 0
    assert len(events.batches) == before and sql(db, "SELECT count(*) FROM meta").fetchone()[0] == 0
    assert sql(db, "SELECT 1").fetchone()[0] == 1                                    # the connection is usable again
    with db.tx():
        pass                                                                          # and a new transaction can start


def test_an_error_at_commit_time_rolls_back(db, events):
    sql(db, "PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        with db.tx() as tx:
            tx.conn.execute("PRAGMA defer_foreign_keys = ON")
            tx.conn.execute("INSERT INTO org_edges(parent_id, child_id) VALUES ('nope','nada')")        # checked at COMMIT
            tx.emit("never.seen", {})
    assert "never.seen" not in [e.type for e in events.events]
    with db.tx():
        pass


def test_transactions_do_not_nest(db):
    with db.tx():
        with pytest.raises(RuntimeError, match="nest"):
            with db.tx():
                pass
    with db.read():
        with pytest.raises(RuntimeError, match="nest"):
            with db.tx():
                pass


def test_emit_after_the_block_is_refused_and_data_is_copied(db, events):
    payload = {"list": [1]}
    with db.tx() as tx:
        tx.emit("a.b", payload)
        payload["list"].append(2)
    assert events.events[-1].data == {"list": [1]}
    with pytest.raises(RuntimeError, match="closed"):
        tx.emit("late", {})


def test_a_failing_subscriber_does_not_undo_the_commit(settings):
    def boom(batch):
        raise ValueError("subscriber bug")
    loud = Database(settings.data_dir / "loud.sqlite3", boom)
    loud.migrate()
    with loud.tx() as tx:
        tx.conn.execute("INSERT INTO meta VALUES ('a','1')")
        tx.emit("x.y", {})
    assert sql(loud, "SELECT value FROM meta").fetchone()[0] == "1"
    loud.close()


def test_each_thread_has_its_own_connection(db):
    mine = db.conn()
    found = []
    t = threading.Thread(target=lambda: found.append(db.conn()))
    t.start(); t.join()
    assert found[0] is not mine and db.conn() is mine


def test_a_locked_database_is_store_busy(settings, events, monkeypatch):
    monkeypatch.setattr(dbmod, "BUSY_TIMEOUT_MS", 50)
    first = Database(settings.data_dir / "busy.sqlite3", events)
    first.migrate()
    second = Database(settings.data_dir / "busy.sqlite3", events)
    with first.tx():
        with pytest.raises(StoreBusy) as err:
            with second.tx():
                pass
    assert err.value.code == "store_busy" and err.value.status == 503
    with second.tx():                                                                 # free again
        pass
    first.close(); second.close()


def test_read_gives_a_snapshot_and_close_ends_use(db, settings, events):
    writer = Database(settings.db_path, events)
    with db.read() as conn:
        before = conn.execute("SELECT count(*) FROM meta").fetchone()[0]
        with writer.tx() as tx:
            tx.conn.execute("INSERT INTO meta VALUES ('a','1')")
        assert conn.execute("SELECT count(*) FROM meta").fetchone()[0] == before          # same snapshot
    assert sql(db, "SELECT count(*) FROM meta").fetchone()[0] == before + 1
    db.checkpoint()
    writer.close()
    db.close(); db.close()
    with pytest.raises(SchemaError, match="closed"):
        db.conn()


def test_run_blocking_runs_on_a_worker_thread(db):
    async def go():
        return await run_blocking(lambda: (threading.current_thread() is threading.main_thread(), sql(db, "SELECT 41 + 1").fetchone()[0]))
    assert anyio.run(go) == (False, 42)


# ---- StoreContext --------------------------------------------------------------------------------------------------

def test_store_context_reads_each_family_through_the_open_transaction(db):
    from factories_atom import opened
    from sutra_app.library.department import Department
    from sutra_app.library.node import StructuralNode
    chart = GATE.check("org_chart", seed_chart(ts=5))
    node = GATE.check("node", StructuralNode(kind="department", id="web", label="Web", department_id="web"))
    dept = GATE.check("department", Department(id="web", home_dir="departments/web", ts_created=1))
    plugin_atom = GATE.check("atom", opened())
    with db.tx() as tx:
        ctx = tx.ctx
        assert isinstance(ctx, StoreContext)
        assert ctx.get("org_chart", "chart") is None and ctx.get("node", "web") is None and ctx.get("atom", plugin_atom.model.id) is None
        tx.conn.execute("INSERT INTO org_charts VALUES (1, ?, ?, 5)", (chart.json, chart.sha256))
        tx.conn.execute("INSERT INTO org_nodes(id, kind, name, created_rev, ts) VALUES ('web','department','Web',1,0)")
        tx.conn.execute("INSERT INTO departments VALUES ('web', 'departments/web', ?, ?, 1)", (dept.json, dept.sha256))
        tx.conn.execute("INSERT INTO graph_nodes(id, kind, label, department_id, body, sha256, ts) VALUES ('web','department','Web','web',?,?,0)", (node.json, node.sha256))
        tx.conn.execute("INSERT INTO graph_nodes(id, kind, label, body, sha256, ts) VALUES (?, 'identity', 'x', '{}', 'x', 0)", (plugin_atom.model.node_id,))
        tx.conn.execute("INSERT INTO atoms(id, schema, node_id, state, display, attempt, goal, body, sha256, ts_open) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (plugin_atom.model.id, "work-atom/0.3", plugin_atom.model.node_id, "open", "open", 0, "g", plugin_atom.json, plugin_atom.sha256, 1))
        assert ctx.get("org_chart", "chart") == chart.model == ctx.get("org_chart", "head") == ctx.get("org_chart", "1")
        assert ctx.get("org_chart", "2") is None and ctx.get("org_chart", "nope") is None
        assert ctx.get("node", "web") == node.model and ctx.get("department", "web") == dept.model and ctx.get("department", "zzz") is None
        assert ctx.get("atom", plugin_atom.model.id) == plugin_atom.model
        tx.conn.execute("INSERT INTO atoms(id, schema, node_id, state, display, attempt, goal, body, sha256, ts_open) VALUES ('run1:W-1.a1','atom/1',?,'open','open',1,'g','{}','x',1)",
                        (plugin_atom.model.node_id,))
        assert ctx.get("atom", "run1:W-1.a1") is None                                 # a J2 atom/1 row is not a library Atom
        with pytest.raises(StoreContextError, match="usage"):
            ctx.get("usage", "1")


def test_a_cross_rule_sees_the_context(db):
    """The gate's `department.in_chart` rule reads the chart the transaction holds."""
    from sutra_app.library.department import Department
    from sutra_app.library.gate import GateError
    with db.tx() as tx:
        with pytest.raises(GateError, match="no org chart"):
            GATE.check("department", Department(id="web", home_dir="departments/web", ts_created=1), ctx=tx.ctx)
