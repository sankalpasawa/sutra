"""Messages between nodes (MAN-6, D264, D297): `seq` is 1, 2, 3 ... per project with no gap, a repeated source is stored once and takes no number, a rolled-back post gives its number back, and the
page's `after=` catch-up gets k+1 first. Append-only, scrubbed, written by the server in the caller's one transaction."""
import json
import threading

import pytest

from sutra_app.orchestrator.nodes_store import NodeStore
from sutra_app.orchestrator.redact import Redactor

A, B = "prj_" + "a" * 12, "prj_" + "b" * 12
SECRET = "the-launch-token-0123456789"


@pytest.fixture
def store(db, ids):
    for pid in (A, B):
        db.conn().execute("INSERT INTO projects(id, created_at) VALUES (?, 1)", (pid,))
    return NodeStore(db, ids=ids, redact=Redactor(extra=[SECRET], environ={}))


def post(store, project, n, kind="handoff", body=None, **kw):
    with store.db.tx() as tx:
        return store.post(tx, project_id=project, kind=kind, src_ref=kw.pop("src_ref", f"m:{n}"), body=body if body is not None else {"n": n}, **kw)


def seqs(store, project):
    return [m.seq for m in store.messages(project, limit=500)]


def test_two_projects_posting_in_turn_each_get_one_to_n_with_no_hole(store):
    for n in range(1, 9):
        post(store, A, n)
        post(store, B, n) if n % 2 == 0 else None
        post(store, A, 100 + n)
    assert seqs(store, A) == list(range(1, 17)) and seqs(store, B) == [1, 2, 3, 4]
    assert store.last_seq(A) == 16 and store.last_seq(B) == 4 and store.last_seq("prj_" + "c" * 12) == 0


def test_a_repeated_source_is_stored_once_returns_the_same_row_and_takes_no_number(store):
    first = post(store, A, 1, src_ref="handoff:nd_1:1")
    again = post(store, A, 2, src_ref="handoff:nd_1:1", body={"different": "body"})
    assert again.duplicate and again.seq == first.seq == 1 and not first.duplicate and json.loads(again.body) == {"n": 1}
    third = post(store, A, 3)
    assert third.seq == 2 and seqs(store, A) == [1, 2]                                     # the repeat did not use number 2
    assert post(store, B, 4, src_ref="handoff:nd_1:1").seq == 1                            # the same source in another project is another message


def test_a_rolled_back_post_gives_its_number_back(store):
    post(store, A, 1)
    with pytest.raises(RuntimeError):
        with store.db.tx() as tx:
            assert store.post(tx, project_id=A, kind="status", src_ref="x", body={"a": 1}).seq == 2
            raise RuntimeError("the caller's work failed")
    assert seqs(store, A) == [1] and post(store, A, 3).seq == 2


def test_two_posts_in_one_transaction_take_consecutive_numbers(store):
    with store.db.tx() as tx:
        one = store.post(tx, project_id=A, kind="status", src_ref="a", body="x")
        two = store.post(tx, project_id=A, kind="status", src_ref="b", body="y")
    assert (one.seq, two.seq) == (1, 2)


def test_fifty_posts_read_back_as_one_to_fifty_and_the_catch_up_returns_k_plus_one_first(store):
    for n in range(1, 51):
        post(store, A, n)
    assert seqs(store, A) == list(range(1, 51))
    for k in (0, 1, 17, 49):
        got = [m.seq for m in store.messages(A, after=k, limit=500)]
        assert got[:1] == [k + 1] and got == list(range(k + 1, 51))
    assert store.messages(A, after=50) == [] and [m.seq for m in store.messages(A, after=10, limit=5)] == [11, 12, 13, 14, 15]
    assert [m.seq for m in store.messages(A, after=-5, limit=2)] == [1, 2]


def test_posts_from_several_threads_never_leave_a_hole_or_a_repeat(db, store):
    errors = []

    def work(offset):
        try:
            for n in range(10):
                post(store, A, offset * 100 + n)
        except Exception as exc:                                                            # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and seqs(store, A) == list(range(1, 41))


def test_the_body_is_scrubbed_hashed_and_a_big_one_becomes_a_reference(store):
    posted = post(store, A, 1, body={"summary": f"use {SECRET} and sk-ABCDEFGHIJKLMNOP1234", "nested": [{"k": "token: abcdefghij1234567890"}]})
    assert SECRET not in posted.body and "sk-ABCDEFGHIJ" not in posted.body and "abcdefghij1234567890" not in posted.body and "[redacted" in posted.body
    import hashlib
    assert posted.body_sha256 == hashlib.sha256(posted.body.encode()).hexdigest()
    big = post(store, A, 2, body={"text": "x" * 40_000}, file="handoff.accepted.json")
    ref = json.loads(big.body)
    assert ref["file"] == "handoff.accepted.json" and ref["bytes"] > 40_000 and len(ref["sha256"]) == 64 and len(big.body) < 200


def test_the_wire_shape_and_the_closed_kinds(store):
    posted = post(store, A, 1, from_node="nd_" + "1" * 12, to_node="project")
    wire = posted.as_dict()
    assert wire["v"] == 1 and wire["seq"] == 1 and wire["from"] == {"node_id": "nd_" + "1" * 12} and wire["kind"] == "handoff" and wire["body"] == {"n": 1} and wire["at"].endswith("Z")
    for kind in ("chat", "", "HANDOFF"):
        with pytest.raises(ValueError):
            post(store, A, 2, kind=kind)
    with pytest.raises(ValueError):
        post(store, A, 2, src_ref="")
    with pytest.raises(Exception):
        post(store, "prj_" + "f" * 12, 3)                                                    # no such project


def test_a_message_is_append_only_even_for_the_store_and_the_event_follows_the_commit(store, db):
    post(store, A, 1)
    with pytest.raises(Exception, match="append-only"):
        db.conn().execute("UPDATE node_messages SET body = 'x'")
    batches = []
    original = db._publish
    db._publish = lambda events: (batches.append([e.type for e in events]), original(events))
    post(store, A, 2)
    assert batches[-1] == ["project.message"]
