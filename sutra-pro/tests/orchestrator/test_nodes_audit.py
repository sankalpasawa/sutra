"""The audit store (MAN-2, guardrails 8; D280): append only, names and shapes only, reasons clipped and redacted, and the rows that belong to the caller's transaction."""
import sqlite3

import pytest

from sutra_app.orchestrator.nodes_store import NodeStore
from sutra_app.orchestrator.redact import Redactor

PROJECT = "prj_" + "1" * 12
NODE = "nd_" + "2" * 12
SECRET = "the-launch-token-0123456789"


@pytest.fixture
def store(db, ids):
    return NodeStore(db, ids=ids, redact=Redactor(extra=[SECRET], environ={}))


def write(store, **over):
    fields = {"actor": "gatekeeper", "action": "grant.issued", "project_id": PROJECT, "node_id": NODE, "role": "worker", "tier": 2, "decision": "allow", "reason": "the role table", **over}
    with store.db.tx() as tx:
        return store.audit(tx, **fields)


def rows(store, **kw):
    return store.audit_rows(**kw)


def test_a_row_is_stored_with_the_time_the_names_and_the_tier(store, clock):
    seq = write(store, target="site/pricing/", ref="j2-run", hash="a" * 64)
    [row] = rows(store)
    assert row["seq"] == seq == 1 and row["actor"] == "gatekeeper" and row["action"] == "grant.issued" and row["tier"] == 2 and row["decision"] == "allow"
    assert (row["project_id"], row["node_id"], row["role"], row["target"], row["ref"], row["hash"], row["reason"]) == (PROJECT, NODE, "worker", "site/pricing/", "j2-run", "a" * 64, "the role table")
    assert row["at"].endswith("Z") and row["at"].startswith("2026-")


def test_the_table_has_no_column_for_a_payload_and_the_call_has_no_argument_for_one(store, db):
    columns = [r[1] for r in db.conn().execute("PRAGMA table_info(node_audit)")]
    assert columns == ["seq", "at", "project_id", "node_id", "role", "actor", "action", "tier", "target", "decision", "reason", "ref", "hash"]
    for payload in ("payload", "body", "prompt", "content", "text", "data", "detail", "message"):
        with pytest.raises(TypeError):
            with db.tx() as tx:
                store.audit(tx, actor="node", action="handoff.accepted", **{payload: "a whole hand-off"})
    assert rows(store) == []


def test_a_row_cannot_be_changed_or_deleted_by_the_store_or_by_hand(store, db):
    write(store)
    for statement in ("UPDATE node_audit SET decision = 'deny'", "DELETE FROM node_audit", "UPDATE node_audit SET reason = ''"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.conn().execute(statement)
    assert len(rows(store)) == 1
    assert not [name for name in dir(store) if name.startswith(("update", "delete", "remove", "edit"))]


def test_a_reason_is_redacted_first_and_clipped_to_200_characters_after(store):
    write(store, reason="a" * 195 + SECRET + " tail")
    [row] = rows(store)
    assert len(row["reason"]) == 200 and SECRET not in row["reason"] and SECRET[:8] not in row["reason"] and row["reason"].startswith("a" * 195 + "[reda")
    write(store, reason="exactly " + "z" * 192)
    assert len(rows(store)[-1]["reason"]) == 200


def test_credential_shapes_are_replaced_even_when_the_app_does_not_know_the_value(store):
    write(store, reason="the key sk-ABCDEFGHIJKLMNOP1234 was in the file", target="token: abcdefghij1234567890")
    [row] = rows(store)
    assert "sk-ABCDEFGHIJ" not in row["reason"] and "[redacted:openai-key]" in row["reason"]
    assert "abcdefghij1234567890" not in row["target"] and "[redacted" in row["target"]


def test_target_and_ref_are_scrubbed_and_clipped_too_and_every_text_is_one_line(store):
    write(store, target="x" * 500, ref=SECRET, reason="line one\nline two\r\n\tindented    gap")
    [row] = rows(store)
    assert len(row["target"]) == 200 and SECRET not in row["ref"] and row["reason"] == "line one line two indented gap"


@pytest.mark.parametrize("over", [
    {"actor": "model"}, {"actor": ""}, {"decision": "maybe"}, {"action": ""}, {"action": "Grant Issued"}, {"action": "grant."}, {"action": "x" * 81}, {"action": "grant.issued; DROP"},
    {"tier": 7}, {"tier": -1}, {"tier": True}, {"tier": "2"}, {"hash": "nothex"}, {"hash": "A" * 64}, {"hash": "a" * 63}, {"role": "owner"}, {"project_id": "prj_x"}, {"node_id": "tsk_" + "a" * 12},
    {"reason": None}, {"reason": 5}, {"target": ["a"]},
])
def test_a_name_outside_the_closed_lists_is_refused_and_nothing_is_written(store, over):
    with pytest.raises(ValueError):
        write(store, **over)
    assert rows(store) == []


def test_tier_6_can_be_recorded_as_a_refusal_and_a_row_may_have_no_tier_project_or_node(store):
    write(store, tier=6, decision="deny", action="grant.denied", reason="publishing outside is never available")
    write(store, tier=None, project_id=None, node_id=None, role="", actor="owner", action="kill", decision="n/a", reason="kill all")
    assert [(r["tier"], r["project_id"], r["action"]) for r in rows(store)] == [(6, PROJECT, "grant.denied"), (None, None, "kill")]


def test_a_row_commits_and_rolls_back_with_the_callers_transaction(store, db):
    with pytest.raises(RuntimeError):
        with db.tx() as tx:
            store.audit(tx, actor="conductor", action="node.spawned", project_id=PROJECT)
            raise RuntimeError("the caller's work failed")
    assert rows(store) == []
    with db.tx() as tx:
        store.audit(tx, actor="conductor", action="node.spawned", project_id=PROJECT)
        store.audit(tx, actor="conductor", action="node.leased", project_id=PROJECT)
    assert [r["action"] for r in rows(store)] == ["node.spawned", "node.leased"]


def test_the_rows_read_back_in_order_by_project_node_after_and_limit(store):
    other = "prj_" + "9" * 12
    for n in range(5):
        write(store, action=f"step.n{n}", project_id=PROJECT if n % 2 == 0 else other, node_id=NODE if n < 3 else None)
    assert [r["action"] for r in rows(store)] == [f"step.n{n}" for n in range(5)]
    assert [r["action"] for r in rows(store, project_id=PROJECT)] == ["step.n0", "step.n2", "step.n4"]
    assert [r["action"] for r in rows(store, node_id=NODE)] == ["step.n0", "step.n1", "step.n2"]
    assert [r["seq"] for r in rows(store, after=2)] == [3, 4, 5] and [r["seq"] for r in rows(store, after=2, limit=2)] == [3, 4]
    assert len(rows(store, limit=0)) == 1 and len(rows(store, limit=10_000)) == 5


def test_a_text_that_is_not_a_string_is_a_value_error_not_a_stored_object(store):
    with pytest.raises(ValueError):
        write(store, target={"path": "x"})


def test_the_names_for_a_closed_laptop_are_in_place_and_fit_the_audit(store):
    from sutra_app.orchestrator import nodes_store as ns
    assert ns.GATE_REFUSED_SLEEP == "the computer went to sleep before you answered" and ns.GATE_REFUSED_CLOSED == "Sutra was closed before you answered"
    write(store, actor="system", action=ns.GATE_REFUSED_ACTION, decision="deny", reason=ns.GATE_REFUSED_SLEEP)
    write(store, actor="system", action=ns.PROJECT_STOPPED_ACTION, decision="n/a", reason=ns.GATE_REFUSED_CLOSED)
    assert [(r["action"], r["decision"], r["reason"]) for r in rows(store)] == [("gate.refused", "deny", ns.GATE_REFUSED_SLEEP), ("project.stopped", "n/a", ns.GATE_REFUSED_CLOSED)]


def test_no_code_replaces_a_row_of_the_append_only_tables():
    """`INSERT OR REPLACE` / `REPLACE INTO` deletes the conflicting old row and the append-only triggers do not see it: node_audit and node_messages are only ever inserted with a plain
    INSERT (ON CONFLICT DO NOTHING where a conflict is possible). This fails the day somebody writes the other spelling (m1)."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "sutra_app"
    bad = re.compile(r"(?is)(INSERT\s+OR\s+REPLACE\s+INTO|REPLACE\s+INTO)\s+node_(audit|messages)\b|node_(audit|messages)[^;]{0,200}ON\s+CONFLICT[^;]{0,120}DO\s+UPDATE")
    found = [str(path.relative_to(root)) for path in root.rglob("*.py") if bad.search(path.read_text(encoding="utf-8"))]
    assert found == []
    assert bad.search("INSERT OR REPLACE INTO node_audit(x) VALUES (1)") and bad.search("insert or replace into node_messages values (1)") and not bad.search("INSERT INTO node_audit(x) VALUES (1) ON CONFLICT DO NOTHING")


def test_a_replace_would_silently_remove_a_message_which_is_why_the_spelling_is_forbidden(db):
    db.conn().execute("INSERT INTO projects(id, created_at) VALUES ('prj_" + "1" * 12 + "', 1)")
    db.conn().execute("INSERT INTO node_messages(project_id, seq, kind, src_ref, at) VALUES ('prj_" + "1" * 12 + "', 1, 'handoff', 'r', 1)")
    db.conn().execute("INSERT OR REPLACE INTO node_messages(project_id, seq, kind, src_ref, body, at) VALUES ('prj_" + "1" * 12 + "', 2, 'handoff', 'r', 'changed', 1)")
    assert db.conn().execute("SELECT seq, body FROM node_messages").fetchall()[0]["body"] == "changed"        # the trigger did not fire: the old row is gone and the new one has another seq
