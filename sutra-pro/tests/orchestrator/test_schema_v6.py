"""Migration v6 (multi-agent nodes, MAN-1): five new tables, `tasks.lane` and the swap of the one-live-task index. All of it is inert: a v5 file keeps its data, the new index
forbids exactly what the old one forbade for lane '', the audit and the messages are append-only, and no row exists until a later package writes one."""
import sqlite3

import pytest

from sutra_app.ops import backup
from sutra_app.orchestrator import schema
from sutra_app.orchestrator.db import Database

NEW_TABLES = {"projects", "agent_nodes", "node_messages", "node_audit", "approvals"}
LIVE = ("starting", "running", "waiting_user")


def sql(db, text, *args):
    return db.conn().execute(text, args)


def names(db, kind="table"):
    return {r[0] for r in sql(db, "SELECT name FROM sqlite_master WHERE type = ?", kind)}


def seed_team(db):
    """The team `web` and a second team `docs`, enough for a task row."""
    sql(db, "INSERT INTO org_nodes(id, kind, name, created_rev, ts) VALUES ('root','root','Root',1,0),('web','department','Web',2,0),('docs','department','Docs',2,0)")
    sql(db, "INSERT INTO org_edges(parent_id, child_id) VALUES ('root','web'),('root','docs')")
    sql(db, "INSERT INTO departments(id, home_dir, body, sha256, ts) VALUES ('web','departments/web','{}','x',0),('docs','departments/docs','{}','x',0)")


def add_task(db, n, dept="web", status="queued", **extra):
    cols = {"id": f"tsk_{n:012x}", "dept_id": dept, "title": "t", "user_text": "u", "status": status, "created_at": 1, **extra}
    sql(db, f"INSERT INTO tasks({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", *cols.values())
    return cols["id"]


def project(db, n=1, **over):
    cols = {"id": f"prj_{n:012x}", "created_at": 1, **over}
    sql(db, f"INSERT INTO projects({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", *cols.values())
    return cols["id"]


def audit(db, **over):
    cols = {"at": 1, "actor": "gatekeeper", "action": "grant.issued", **over}
    sql(db, f"INSERT INTO node_audit({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", *cols.values())


def message(db, project_id, seq, src_ref, kind="handoff"):
    sql(db, "INSERT INTO node_messages(project_id, seq, kind, src_ref, at) VALUES (?,?,?,?,1)", project_id, seq, kind, src_ref)


# ---- the migration -----------------------------------------------------------------------------------------------------------------

def test_the_nodes_migration_is_the_sixth_and_the_tables_are_registered():
    assert schema.MIGRATIONS[5] is schema.DDL_V6_NODES and schema.SCHEMA_VERSION >= 6          # later migrations (v7 work, v8 recipes) come after it, never before
    assert NEW_TABLES <= set(schema.TABLES)


def test_a_fresh_file_has_the_new_tables_empty_and_the_lane_column(db):
    assert NEW_TABLES <= names(db)
    for table in NEW_TABLES:
        assert sql(db, f"SELECT count(*) FROM {table}").fetchone()[0] == 0, table
    lane = next(r for r in sql(db, "PRAGMA table_info(tasks)") if r[1] == "lane")
    assert (lane[2], lane[3], lane[4]) == ("TEXT", 1, "''")            # TEXT, NOT NULL, default ''


def test_a_v5_database_migrates_with_every_row_intact_and_every_task_in_lane_empty(settings, events):
    old = Database(settings.data_dir / "v5.sqlite3", events)
    old.migrate(schema.MIGRATIONS[:5])
    seed_team(old)
    add_task(old, 1, "web", "running", pick_json='{"a":1}', settings_json='{"J2_BUDGET":"50"}')
    add_task(old, 2, "web", "queued", depends_on='["tsk_000000000001"]')
    add_task(old, 3, "docs", "done")
    sql(old, "INSERT INTO meta VALUES ('k','v')")
    sql(old, "INSERT INTO chat_sessions(id, node_id, kind, title, created_at, updated_at) VALUES ('cs_org','root','org','Org',0,0)")
    sql(old, "INSERT INTO chat_messages(session_id, role, who, text, at) VALUES ('cs_org','user','user','hello there',1)")
    columns = "id, dept_id, status, depends_on, settings_json, pick_json, created_at"
    before = [tuple(r) for r in sql(old, f"SELECT {columns} FROM tasks ORDER BY id")]
    assert old.version() == 5 and NEW_TABLES.isdisjoint(names(old))
    assert old.migrate() == schema.SCHEMA_VERSION >= 6
    assert [tuple(r) for r in sql(old, f"SELECT {columns} FROM tasks ORDER BY id")] == before
    assert [r[0] for r in sql(old, "SELECT lane FROM tasks")] == ["", "", ""]
    assert sql(old, "SELECT value FROM meta WHERE key = 'k'").fetchone()[0] == "v"
    assert sql(old, "SELECT text FROM chat_messages").fetchone()[0] == "hello there"
    assert NEW_TABLES <= names(old)
    assert old.migrate() == schema.SCHEMA_VERSION                      # again: a no-op
    old.close()


def test_the_pre_upgrade_backup_still_runs_for_a_v5_file(settings, events):
    old = Database(settings.db_path, events)
    old.migrate(schema.MIGRATIONS[:5])
    sql(old, "INSERT INTO meta VALUES ('marker','five')")
    old.close()
    path = backup.before_upgrade(settings)
    assert path is not None and path.name == f"pre-upgrade-v5-to-v{schema.SCHEMA_VERSION}.sqlite3"
    check = sqlite3.connect(path)
    assert check.execute("PRAGMA user_version").fetchone()[0] == 5 and check.execute("SELECT value FROM meta WHERE key = 'marker'").fetchone()[0] == "five"
    check.close()


def test_a_failing_v6_leaves_the_v5_file_as_it_was(settings, events):
    old = Database(settings.data_dir / "v5b.sqlite3", events)
    old.migrate(schema.MIGRATIONS[:5])
    broken = (*schema.DDL_V6_NODES, "CREATE TABLE projects (x)")          # the last statement fails: the table exists already
    with pytest.raises(sqlite3.OperationalError):
        old.migrate([*schema.MIGRATIONS[:5], broken])
    assert old.version() == 5 and NEW_TABLES.isdisjoint(names(old)) and "tasks_one_live_per_dept" in names(old, "index")
    assert "lane" not in {r[1] for r in sql(old, "PRAGMA table_info(tasks)")}
    old.close()


# ---- the index swap: the same rule for lane '' --------------------------------------------------------------------------------------

def one_live_rule_outcomes(db):
    """What the database does with a fixed run of task moves: one True (accepted) or False (refused) per move."""
    seed_team(db)
    results = []

    def attempt(fn):
        try:
            fn()
            results.append(True)
        except sqlite3.IntegrityError:
            results.append(False)

    attempt(lambda: add_task(db, 1, "web", "running"))
    attempt(lambda: add_task(db, 2, "web", "running"))              # a second live task of the team: refused
    attempt(lambda: add_task(db, 3, "web", "starting"))             # refused
    attempt(lambda: add_task(db, 4, "web", "waiting_user"))         # refused
    attempt(lambda: add_task(db, 5, "web", "queued"))               # not live: fine
    attempt(lambda: add_task(db, 6, "web", "blocked"))              # fine
    attempt(lambda: add_task(db, 7, "web", "done"))                 # fine
    attempt(lambda: add_task(db, 8, "docs", "running"))             # another team: fine
    attempt(lambda: sql(db, "UPDATE tasks SET status = 'running' WHERE id = ?", "tsk_000000000005"))     # queued to running while one runs: refused
    attempt(lambda: sql(db, "UPDATE tasks SET status = 'done' WHERE id = ?", "tsk_000000000001"))        # the live one ends: fine
    attempt(lambda: sql(db, "UPDATE tasks SET status = 'running' WHERE id = ?", "tsk_000000000005"))     # now the queued one may start: fine
    attempt(lambda: sql(db, "UPDATE tasks SET status = 'waiting_user' WHERE id = ?", "tsk_000000000006"))     # a second live one again: refused
    return results


def test_the_new_index_forbids_exactly_what_the_old_one_forbade_for_lane_empty(settings, events):
    old = Database(settings.data_dir / "old.sqlite3", events)
    old.migrate(schema.MIGRATIONS[:5])
    new = Database(settings.data_dir / "new.sqlite3", events)
    new.migrate()
    expected = [True, False, False, False, True, True, True, True, False, True, True, False]
    assert one_live_rule_outcomes(old) == expected                      # the table of moves is right: this is what the old index did
    assert one_live_rule_outcomes(new) == expected                      # and the new one does the same
    old.close()
    new.close()


def test_the_old_index_is_gone_and_the_new_one_is_partial_on_the_live_statuses(db):
    assert "tasks_one_live_per_dept" not in names(db, "index") and "tasks_one_live_per_dept_lane" in names(db, "index")
    definition = sql(db, "SELECT sql FROM sqlite_master WHERE name = 'tasks_one_live_per_dept_lane'").fetchone()[0]
    assert "(dept_id, lane)" in definition and all(f"'{status}'" in definition for status in LIVE)


def test_a_second_lane_is_the_only_way_past_the_rule_and_nothing_uses_it_yet(db):
    """The lane is what MAN-10 will use for same-team workers; with the column in place the index allows one live task per (team, lane), and nothing but lane '' is written today."""
    seed_team(db)
    add_task(db, 1, "web", "running")
    add_task(db, 2, "web", "running", lane="nd_aaaaaaaaaaaa")           # another lane: allowed
    with pytest.raises(sqlite3.IntegrityError):
        add_task(db, 3, "web", "running", lane="nd_aaaaaaaaaaaa")       # the same lane: refused
    with pytest.raises(sqlite3.IntegrityError):
        add_task(db, 4, "web", "running")                               # lane '' again: refused
    assert sql(db, "SELECT count(*) FROM tasks WHERE lane <> ''").fetchone()[0] == 1


# ---- the new tables ---------------------------------------------------------------------------------------------------------------

def test_the_audit_is_append_only(db):
    audit(db, project_id="prj_000000000001", node_id="nd_000000000001", role="worker", tier=2, decision="allow", reason="role table")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        sql(db, "UPDATE node_audit SET decision = 'deny'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        sql(db, "DELETE FROM node_audit")
    assert sql(db, "SELECT count(*) FROM node_audit").fetchone()[0] == 1


def test_the_audit_refuses_a_tier_above_six_an_unknown_actor_or_decision_and_a_long_reason(db):
    audit(db, tier=6, decision="deny")                                  # tier 6 may be recorded (a refusal), never more
    audit(db, tier=None)
    for bad in ({"tier": 7}, {"tier": -1}, {"actor": "model"}, {"decision": "maybe"}, {"reason": "x" * 201}, {"action": ""}):
        with pytest.raises(sqlite3.IntegrityError):
            audit(db, **bad)
    audit(db, reason="x" * 200)


def test_a_message_is_stored_once_per_source_and_its_seq_is_per_project(db):
    first, second = project(db, 1), project(db, 2)
    message(db, first, 1, "handoff:nd_000000000001:1")
    message(db, first, 2, "handoff:nd_000000000002:1")
    message(db, second, 1, "handoff:nd_000000000001:1")                  # the same source in another project: fine, and its seq starts at 1 again
    with pytest.raises(sqlite3.IntegrityError):
        message(db, first, 3, "handoff:nd_000000000001:1")               # a repeat of a source: stored once
    with pytest.raises(sqlite3.IntegrityError):
        message(db, first, 2, "other")                                   # a seq is used once in a project
    with pytest.raises(sqlite3.IntegrityError):
        message(db, first, 0, "zero")                                    # and starts at 1
    with pytest.raises(sqlite3.IntegrityError):
        message(db, first, 3, "x", kind="chat")
    assert [r[0] for r in sql(db, "SELECT seq FROM node_messages WHERE project_id = ? ORDER BY seq", first)] == [1, 2]


def test_messages_are_append_only(db):
    first = project(db)
    message(db, first, 1, "handoff:nd_000000000001:1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        sql(db, "UPDATE node_messages SET body = 'changed'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        sql(db, "DELETE FROM node_messages")


def test_a_message_needs_its_project(db):
    with pytest.raises(sqlite3.IntegrityError):
        message(db, "prj_00000000ffff", 1, "x")


def test_a_project_row_has_closed_choices_and_one_row_per_request_and_client(db):
    project(db, 1, request_id="req-1", client_id="c1")
    for bad in ({"status": "paused"}, {"failure_policy": "ignore"}, {"decide_for_me": 2}, {"budget_credits": -1}):
        with pytest.raises(sqlite3.IntegrityError):
            project(db, 9, **bad)
    with pytest.raises(sqlite3.IntegrityError):
        project(db, 2, request_id="req-1")
    with pytest.raises(sqlite3.IntegrityError):
        project(db, 3, client_id="c1")
    row = sql(db, "SELECT status, failure_policy, decide_for_me, paused, review_loops, caps_json FROM projects WHERE id = ?", "prj_000000000001").fetchone()
    assert tuple(row) == ("planning", "stop_branch", 0, 0, 0, "{}")


def test_a_node_row_has_closed_roles_runtimes_and_states_and_one_node_per_task(db):
    seed_team(db)
    prj = project(db)
    task = add_task(db, 1)

    def node(n, **over):
        cols = {"id": f"nd_{n:012x}", "project_id": prj, "role": "worker", "runtime": "engine", "created_at": 1, **over}
        sql(db, f"INSERT INTO agent_nodes({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", *cols.values())

    node(1, task_id=task)
    for i, state in enumerate(("planned", "awaiting_approval", "awaiting_system", "ready", "queued", "leased", "running", "handing_off", "done", "failed", "cancelled", "expired")):
        node(0x100 + i, state=state)
    for bad in ({"role": "conductor"}, {"runtime": "thread"}, {"state": "paused"}, {"attempt": 0}, {"project_id": "prj_00000000ffff"}):
        with pytest.raises(sqlite3.IntegrityError):
            node(2, **bad)
    with pytest.raises(sqlite3.IntegrityError):
        node(3, task_id=task)                                            # a task belongs to one node


def test_an_approval_has_closed_choices_and_a_client_answer_is_stored_once(db):
    prj = project(db)

    def approval(n, **over):
        cols = {"id": f"ap_{n:012x}", "project_id": prj, "tier": 4, "expires_at": 10, "created_at": 1, **over}
        sql(db, f"INSERT INTO approvals({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", *cols.values())

    approval(1, client_id="c1")
    approval(2)                                                          # no client id: several are fine
    approval(3)
    with pytest.raises(sqlite3.IntegrityError):
        approval(4, client_id="c1")                                      # the same answer twice in a project: stored once
    for bad in ({"tier": 7}, {"status": "maybe"}):
        with pytest.raises(sqlite3.IntegrityError):
            approval(5, **bad)
    assert sql(db, "SELECT status FROM approvals WHERE id = 'ap_000000000001'").fetchone()[0] == "open"
