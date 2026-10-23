"""The J2 ledger appends without reading itself (PRD-FIVE-FUNCTIONS M0.2, SM-10).

The ledger was one JSON document, read whole and written whole on every event, and counted by reading it whole on
every 2.5 s poll. It is now a journal (j2-events.jsonl) with an index beside it (j2-index.json). These tests hold it to
that: an append is one line, the index alone answers idempotency and causation, a ledger from before reads the same
after its conversion, and the two cursors of /j2/events never repeat or skip a row.
"""
import importlib
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

WEBSITE = "Build a website that teaches algebra to Class 8 students"


@pytest.fixture
def j2(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)

    import website_dept as W
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime as R
    import j2_runtime as J

    for module in (E, W, org2_apply, founding, R, J):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, J, founding


def _cycle(j2, ref="dref-ledger"):
    """A department with a cycle, waiting on Identity's first question: the ledger is open and nothing else writes."""
    W, _, J, _ = j2
    d, _ = W.create(ref, "Ledger", "A goal", kind="website")
    d.update({"done": "", "events": [{"kind": "j2_ready", "route": "template"}]})
    W.save_dept(ref, d)
    J.start(ref)
    return ref


def _born(j2, words=WEBSITE, org="Acme Learning"):
    W, _, _, founding = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _forget(J):
    """What this process holds of every index goes, as when the app starts again."""
    J._IDX.clear()


def test_ten_thousand_appends_each_grow_the_journal_by_one_line_and_p95_is_recorded(j2, record_property):
    """An append that rewrites the ledger, or writes anything but its own one line, must fail. The p95 is SM-10's
    figure: recorded, never a gate."""
    W, _, J, _ = j2
    ref = _cycle(j2)
    path = W.ddir(ref) / J.LEDGER
    size, took = path.stat().st_size, []
    for i in range(10000):
        t0 = time.perf_counter()
        J.note(ref, 6, "Plan", "Coordination", "run.step_recorded", "recorded", "Step %d." % i, "bench-%d" % i)
        took.append(time.perf_counter() - t0)
        grown = path.stat().st_size
        with open(path, "rb") as f:
            f.seek(size)
            added = f.read()
        assert added.count(b"\n") == 1 and added.endswith(b"\n"), (i, added[:80])
        assert json.loads(added)["summary"] == "Step %d." % i
        size = grown
    took.sort()
    p95 = took[int(len(took) * 0.95)] * 1000
    record_property("sm10_append_p95_ms", round(p95, 3))
    print("SM-10: p95 append %.2f ms at 10,000 events" % p95)
    idx = json.loads((W.ddir(ref) / J.INDEX).read_text())
    assert idx["count"] == len(J.events(ref)) == 10001 and idx["bytes"] == path.stat().st_size
    assert J.status(ref)["event_count"] == 10001


def test_the_index_alone_answers_idempotency_and_causation(j2, monkeypatch):
    """Reading the journal to append to it must fail: the journal is not read while an event is appended."""
    W, _, J, _ = j2
    ref = _cycle(j2)
    first = J.note(ref, 6, "Plan", "Coordination", "run.started", "running", "Plan started.", "k-1")
    monkeypatch.setattr(J, "events", lambda ref: (_ for _ in ()).throw(AssertionError("the journal was read")))
    monkeypatch.setattr(J.record, "lines", lambda p: (_ for _ in ()).throw(AssertionError("the journal was read")))
    second = J.note(ref, 6, "Plan", "Coordination", "run.completed", "complete", "Plan finished.", "k-2")
    assert second["causation_id"] == first["event_id"] and second["seq"] == first["seq"] + 1
    again = J.note(ref, 6, "Plan", "Coordination", "run.started", "running", "Plan started.", "k-1")
    assert again["event_id"] == first["event_id"]                      # the same key is the same event, once
    assert J.status(ref)["event_count"] == second["seq"]                # the count is the state's, not the journal's
    state = json.loads((W.ddir(ref) / "j2-state.json").read_text())
    assert state["event_count"] == second["seq"]


def test_an_old_ledger_reads_the_same_after_its_one_conversion(j2):
    """A conversion that loses, reorders or rewrites a row, or that runs twice, must fail."""
    W, _, J, _ = j2
    ref = _born(j2)
    rows = J.events(ref)
    assert len(rows) > 10
    for r in rows[:3]:
        r.pop("seq", None)                                             # a ledger from before seq existed
    folder = W.ddir(ref)
    (folder / J.LEDGER).unlink()
    (folder / J.INDEX).unlink()
    (folder / J.OLD_LEDGER).write_text(json.dumps(rows, indent=1))
    _forget(J)

    assert J.events(ref) == rows                                         # the same rows, in the same order
    assert (folder / (J.OLD_LEDGER + ".bak")).exists() and not (folder / J.OLD_LEDGER).exists()
    assert [r["seq"] for r in J.activity(ref) if not r["id"].startswith("board-")] == list(range(1, len(rows) + 1))
    added = J.note(ref, 6, "Plan", "Coordination", "run.step_recorded", "recorded", "After.", "after-conversion")
    assert added["seq"] == len(rows) + 1
    assert added["causation_id"] == [r for r in rows if r["cycle_id"] == added["cycle_id"]][-1]["event_id"]
    assert J.note(ref, *[rows[-1][k] for k in ("step", "actor", "recipient", "action", "state", "summary")],
                  rows[-1]["idempotency_key"].rsplit("/", 1)[1])["event_id"] == rows[-1]["event_id"]
    # once: a second read converts nothing, and the backup is the old document as it was
    (folder / (J.OLD_LEDGER + ".bak")).rename(folder / "kept.bak")
    assert J.events(ref)[:len(rows)] == rows and not (folder / J.OLD_LEDGER).exists()
    assert json.loads((folder / "kept.bak").read_text()) == rows


def test_an_index_behind_its_journal_is_read_forward_and_a_torn_line_stays_out(j2):
    """An index left behind by a closed app, or a torn last line, that loses or merges an event must fail."""
    W, _, J, _ = j2
    ref = _cycle(j2)
    folder = W.ddir(ref)
    a = J.note(ref, 6, "Plan", "Coordination", "run.started", "running", "A.", "a")
    stale = (folder / J.INDEX).read_text()
    b = J.note(ref, 6, "Plan", "Coordination", "run.completed", "complete", "B.", "b")
    (folder / J.INDEX).write_text(stale)                                 # the app closed between the line and the index
    _forget(J)
    assert J.note(ref, 6, "Plan", "Coordination", "run.completed", "complete", "B.", "b")["event_id"] == b["event_id"]
    c = J.note(ref, 6, "Plan", "Coordination", "run.step_recorded", "recorded", "C.", "c")
    assert c["causation_id"] == b["event_id"] and c["seq"] == b["seq"] + 1
    with open(folder / J.LEDGER, "ab") as f:
        f.write(b'{"idempotency_key": "torn", "summ')                    # a line the app never finished
    d = J.note(ref, 6, "Plan", "Coordination", "run.step_recorded", "recorded", "D.", "d")
    assert [e["summary"] for e in J.events(ref)][-4:] == ["A.", "B.", "C.", "D."]
    assert d["seq"] == c["seq"] + 1 and a["seq"] < b["seq"]
    (folder / J.INDEX).unlink()                                          # no index at all: built from the journal
    _forget(J)
    assert J.event_count(ref) == len(J.events(ref)) and J.events_after(ref, c["seq"]) == [d]


def test_two_cursors_never_repeat_or_skip_a_row_while_both_sources_grow(j2):
    """The old single cursor was a place in a list merged by time: a row written into an earlier second moved every
    later row along, and the screen showed one twice or never. Paging by the two cursors must give each row once."""
    W, R, J, _ = j2
    ref = _cycle(j2)
    seen, cur = [], {"after_seq": 0, "after_board": 0}

    def read():
        page = J.activity_page(ref, cur["after_seq"], cur["after_board"])
        seen.extend(r["id"] for r in page["events"])
        cur.update(after_seq=page["after_seq"], after_board=page["after_board"])

    for i in range(700):                                               # more than two marks of the index
        if i % 3 == 0:
            R.post(ref, "Identity", R.OWNER, "inform", {"word": "said", "done": "Line %d." % i})
        J.note(ref, 6, "Plan", "Coordination", "run.step_recorded", "recorded", "Event %d." % i, "e-%d" % i)
        if i % 7 == 0:
            read()
    read()
    read()                                                             # a read with nothing new adds nothing
    every = [r["id"] for r in J.activity(ref)]
    assert len(seen) == len(set(seen))                                 # never twice
    assert sorted(seen) == sorted(every)                               # never skipped
    assert cur["after_seq"] == J.event_count(ref) and cur["after_board"] == len(R.board(ref))


def test_the_events_route_takes_both_cursors_and_the_old_one(j2):
    W, R, J, _ = j2
    import j2_api
    importlib.reload(j2_api)
    app = FastAPI()
    app.include_router(j2_api.router)
    client = TestClient(app)
    ref = _cycle(j2)
    url = "/api/dept/%s/j2/events" % ref
    whole = client.get(url).json()
    assert whole["cursor"] == len(whole["events"]) and whole["after_seq"] == J.event_count(ref)
    assert client.get(url, params={"after": whole["cursor"]}).json()["events"] == []
    J.note(ref, 6, "Plan", "Coordination", "run.step_recorded", "recorded", "New.", "new")
    page = client.get(url, params={"after_seq": whole["after_seq"], "after_board": whole["after_board"]}).json()
    assert [r["summary"] for r in page["events"]] == ["New."]
    assert page["after_seq"] == whole["after_seq"] + 1 and page["after_board"] == whole["after_board"]
    assert client.get(url, params={"after_seq": page["after_seq"], "after_board": page["after_board"]}).json()["events"] == []
