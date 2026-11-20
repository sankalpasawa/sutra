"""The approvals rows (MAN-2, guardrails 5; D270): who is asked what, the answer, who answered, when it ends. Tier 6 is never asked or allowed, "allow for this project" stops at tier 4,
an answer given twice is stored once, and an approval that ran out means denied."""
import sqlite3

import pytest

from sutra_app.orchestrator.errors import AlreadyDecided, AppError, NotFound
from sutra_app.orchestrator.nodes_store import NodeStore
from sutra_app.orchestrator.redact import Redactor

PROJECT = "prj_" + "1" * 12
OTHER = "prj_" + "3" * 12
NODE = "nd_" + "2" * 12
SECRET = "the-launch-token-0123456789"


@pytest.fixture
def store(db, ids):
    for pid in (PROJECT, OTHER):
        db.conn().execute("INSERT INTO projects(id, created_at) VALUES (?, 1)", (pid,))
    return NodeStore(db, ids=ids, redact=Redactor(extra=[SECRET], environ={}))


def ask(store, tier=4, *, project=PROJECT, expires=10**10, client_id=None, request=None):
    with store.db.tx() as tx:
        return store.open_approval(tx, project_id=project, node_id=NODE, tier=tier, request=request if request is not None else {"why": "read GitHub"}, expires_at=expires,
                                   client_id=client_id)


def answer(store, approval_id, decision, by="owner"):
    with store.db.tx() as tx:
        return store.decide(tx, approval_id, decision, decided_by=by)


def test_a_question_is_stored_open_with_who_what_and_when_it_ends(store):
    row = ask(store, 4, expires=5_000_000_000, request={"why": "read GitHub", "step": "a1", "count": 2, "paths": ["a/", "b/"], "flag": True})
    assert row.id.startswith("ap_") and (row.project_id, row.node_id, row.tier, row.status, row.decided_by, row.decided_at) == (PROJECT, NODE, 4, "open", "", None)
    assert row.open and not row.allowed and row.expires_at == 5_000_000_000 and not row.duplicate and row.created_at > 0
    assert row.request == {"why": "read GitHub", "step": "a1", "count": 2, "paths": ["a/", "b/"], "flag": True}
    assert store.get_approval(row.id) == row and store.get_approval("ap_" + "0" * 12) is None


def test_tier_6_is_never_asked_and_neither_is_tier_0(store):
    for tier in (6, 0, 7, -1, True, "4", None):
        with pytest.raises(ValueError):
            ask(store, tier)
    assert store.approvals(PROJECT) == []
    assert ask(store, 5).tier == 5                                    # a raise of the budget is asked, per raise


def test_the_same_client_id_in_a_project_is_stored_once_and_another_project_may_use_it(store):
    first = ask(store, 4, client_id="c1")
    again = ask(store, 4, client_id="c1")
    assert again.id == first.id and again.duplicate and not first.duplicate
    assert ask(store, 4, project=OTHER, client_id="c1").id != first.id
    assert len(store.approvals(PROJECT)) == 1


def test_the_request_is_names_and_short_text_scrubbed_and_clipped(store):
    row = ask(store, 4, request={"why": "use " + SECRET + " now", "note": "n" * 300, "tokenish": "sk-ABCDEFGHIJKLMNOP1234"})
    assert SECRET not in str(row.request) and len(row.request["note"]) == 200 and "sk-ABCDEFGHIJ" not in str(row.request)
    for bad in ({"why": {"nested": "no"}}, {"Why": "x"}, {"why": 1.5}, {"why": None}, {f"k{i}": "x" for i in range(21)}, {"why": [1]}, {"why": ["x"] * 21}, {"": "x"}, "text"):
        with pytest.raises(ValueError):
            ask(store, 4, request=bad)


@pytest.mark.parametrize("decision,status", [("allow_once", "allowed_once"), ("allow_project", "allowed_project"), ("deny", "denied")])
def test_the_owners_answers_and_the_status_each_one_stores(store, decision, status):
    row = answer(store, ask(store, 4).id, decision)
    assert row.status == status and row.decided_by == "owner" and row.decided_at is not None and row.allowed == (decision != "deny") and not row.open


def test_the_same_answer_again_is_a_no_op_and_a_different_one_is_refused(store):
    first = answer(store, ask(store, 4).id, "allow_project")
    again = answer(store, first.id, "allow_project", by="rule:decide_for_me")
    assert again.duplicate and again.status == "allowed_project" and again.decided_by == "owner" and again.decided_at == first.decided_at
    for other in ("deny", "allow_once"):
        with pytest.raises(AlreadyDecided):
            answer(store, first.id, other)
    assert store.get_approval(first.id).status == "allowed_project"


def test_allow_for_the_project_stops_at_tier_4_and_tier_5_is_allowed_once_per_raise(store):
    five = ask(store, 5)
    with pytest.raises(AppError) as refused:
        answer(store, five.id, "allow_project")
    assert refused.value.code == "validation" and store.get_approval(five.id).open
    assert answer(store, five.id, "allow_once").status == "allowed_once"
    assert answer(store, ask(store, 5).id, "deny").status == "denied"


def test_tier_6_cannot_be_allowed_even_if_a_row_for_it_got_in_by_hand(store, db):
    db.conn().execute("INSERT INTO approvals(id, project_id, tier, expires_at, created_at) VALUES ('ap_" + "6" * 12 + "', ?, 6, 10000000000, 1)", (PROJECT,))
    for decision in ("allow_once", "allow_project"):
        with pytest.raises(AppError):
            answer(store, "ap_" + "6" * 12, decision)
    assert answer(store, "ap_" + "6" * 12, "deny").status == "denied"                 # a refusal of it is always fine


def test_a_bad_answer_or_a_bad_answerer_or_an_unknown_approval_is_refused(store):
    row = ask(store, 4)
    with pytest.raises(AppError) as bad:
        answer(store, row.id, "yes")
    assert bad.value.code == "validation"
    for by in ("model", "", "rule:", "rule:Bad Name", "owner ", "OWNER", None):
        with pytest.raises(ValueError):
            answer(store, row.id, "deny", by=by)
    with pytest.raises(NotFound):
        answer(store, "ap_" + "0" * 12, "deny")
    assert store.get_approval(row.id).open
    assert answer(store, row.id, "allow_once", by="rule:decide_for_me").decided_by == "rule:decide_for_me"


def test_an_approval_that_ran_out_is_expired_which_means_denied(store, clock):
    soon = ask(store, 4, expires=clock.peek + 100)
    later = ask(store, 4, expires=clock.peek + 100_000)
    clock.advance(1000)
    with store.db.tx() as tx:
        changed = store.expire_due(tx)
    assert [row.id for row in changed] == [soon.id] and changed[0].status == "expired" and changed[0].decided_by == "system" and not changed[0].allowed
    assert store.get_approval(later.id).open and store.approvals(PROJECT, status="open") == [store.get_approval(later.id)]
    with store.db.tx() as tx:
        assert store.expire_due(tx) == []                                                         # nothing left to expire
    with pytest.raises(AlreadyDecided):
        answer(store, soon.id, "allow_once")                                                      # it is decided: expired


def test_an_answer_that_comes_after_the_expiry_does_not_count(store, clock):
    row = ask(store, 4, expires=clock.peek + 50)
    clock.advance(500)
    late = answer(store, row.id, "allow_project")
    assert late.status == "expired" and late.decided_by == "system" and not late.allowed


def test_expiry_can_be_limited_to_one_project(store, clock):
    a = ask(store, 4, expires=clock.peek + 10)
    b = ask(store, 4, project=OTHER, expires=clock.peek + 10)
    clock.advance(100)
    with store.db.tx() as tx:
        assert [row.id for row in store.expire_due(tx, project_id=OTHER)] == [b.id]
    assert store.get_approval(a.id).open


def test_approvals_list_oldest_first_and_by_status(store):
    first, second, third = ask(store, 4), ask(store, 4), ask(store, 5)
    answer(store, second.id, "deny")
    assert [row.id for row in store.approvals(PROJECT)] == [first.id, second.id, third.id]
    assert [row.id for row in store.approvals(PROJECT, status="open")] == [first.id, third.id] and [row.id for row in store.approvals(PROJECT, status="denied")] == [second.id]
    assert store.approvals(OTHER) == []


def test_the_table_still_refuses_what_the_store_would_not_store(store, db):
    with pytest.raises(sqlite3.IntegrityError):
        db.conn().execute("INSERT INTO approvals(id, project_id, tier, expires_at, created_at) VALUES ('ap_" + "7" * 12 + "', ?, 9, 1, 1)", (PROJECT,))
    with pytest.raises(sqlite3.IntegrityError):
        db.conn().execute("INSERT INTO approvals(id, project_id, tier, expires_at, created_at) VALUES ('ap_" + "8" * 12 + "', 'prj_" + "f" * 12 + "', 4, 1, 1)")      # no such project
