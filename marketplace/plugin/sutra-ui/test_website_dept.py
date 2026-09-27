"""test_website_dept.py -- the website department's record, engines and motor,
offline (no model), each test on its own temp record.

Named claims (holding/website/native/system/first-build.html, R1-R14):
  - a department with no goal does nothing; given a goal it plans, writes and
    checks on its own, then asks before the first publish (R2, R7)
  - after one stamp it publishes, and an owner's ask grows the live site with
    no second stamp (R5, R7)
  - a slot never runs twice; an interrupted run's slot runs again once (R9)
  - stop halts, resume continues (R10)
  - a failed check is never published (R4, R7)
  - put back republishes an earlier version as a new one (R8)
  - the trace of the live site reaches the owner's words (R12)
  - founding an org gives it a root department and, under the root, a website
    department with the Library's templates picked (R1)
"""
import importlib
import json

import pytest

REF = "dref-test0001"
GOAL = ("A website for City Care Hospital, a 200-bed multi-speciality hospital in Pune: "
        "cardiology, orthopaedics, maternity, a 24-hour emergency line.")


@pytest.fixture
def W(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "native"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    import website_dept
    importlib.reload(website_dept)
    return website_dept


def _live(W, ref=REF):
    W.create(ref, "City Care Hospital Website", None)
    W.give_goal(ref, GOAL)
    assert W.run_until_idle(ref) == 3
    ask = W.status(ref)["asks"][0]
    W.decide_ask(ref, ask["id"], True)
    assert W.run_until_idle(ref) == 1
    return ask


def test_no_goal_no_work_then_the_line_runs_to_the_first_publish_ask(W):
    W.create(REF, "City Care Hospital Website", None)
    assert W.due(REF)[2] == "nothing due"
    W.give_goal(REF, GOAL)
    assert W.run_until_idle(REF) == 3
    engines = [r["engine"] for r in W.runs(REF) if not r.get("system")]
    assert engines == ["Plan", "Write", "Check"]
    assert W.latest(REF, "Build")["check"]["ok"] is True
    st = W.status(REF)
    assert [a["kind"] for a in st["asks"]] == ["publish"]
    assert W.versions(REF, "Live site") == []
    assert W.due(REF)[2] == "waits for the stamp"


def test_one_stamp_publishes_and_an_ask_grows_the_site_with_no_second_stamp(W):
    _live(W)
    assert (W.live_dir(REF) / "index.html").is_file()
    W.owner_ask(REF, "Add a Careers page for nurses and doctors")
    assert W.run_until_idle(REF) == 4
    assert (W.live_dir(REF) / "careers.html").is_file()
    assert len(W.versions(REF, "Live site")) == 2
    assert W.status(REF)["asks"] == []


def test_a_slot_never_runs_twice_and_an_interrupted_slot_runs_once_more(W):
    _live(W)
    assert W.run_until_idle(REF) == 0
    slots = [r["slot"] for r in W.runs(REF) if r.get("slot") and r["status"] in ("ok", "failed")]
    assert len(slots) == len(set(slots))
    health = {c["name"]: c["state"] for c in W.health(REF)["checks"]}
    assert health["Slots"] == "ok" and health["Versions"] == "ok"
    W.owner_ask(REF, "Add a Visiting hours page")
    name, inp, slot = W.due(REF)
    W._put_run(REF, {"id": "r-crash", "engine": name, "system": False, "slot": slot, "status": "running",
                     "started": W.now(), "ended": None, "what": "reading", "wrote": None, "chain": None,
                     "spend": {"calls": 0, "usd": 0.0}, "retries": 0})
    assert W.due(REF)[2] == "running"
    W.recover()
    assert W.due(REF)[2] == slot
    W.run_until_idle(REF)
    reran = [r for r in W.runs(REF) if r.get("slot") == slot]
    assert [r["status"] for r in reran] == ["interrupted", "ok"] and reran[1]["retries"] == 1


def test_only_one_motor_ticks_a_record_and_the_next_takes_over(W):
    W.create(REF, "City Care Hospital Website", None)
    W.give_goal(REF, GOAL)
    name, inp, slot = W.due(REF)
    W._put_run(REF, {"id": "r-live", "engine": name, "system": False, "slot": slot, "status": "running",
                     "started": W.now(), "ended": None, "what": "reading", "wrote": None, "chain": None,
                     "spend": {"calls": 0, "usd": 0.0}, "retries": 0})
    assert W.hold_motor() is True                      # the first app: it is the motor, and it recovers
    assert [r["status"] for r in W.runs(REF) if r["id"] == "r-live"] == ["interrupted"]
    W._put_run(REF, dict(W.runs(REF)[-1], id="r-live2", status="running"))
    first = W._LOCK["fd"]
    W._LOCK["fd"] = None                               # a second app opens on the same record
    assert W.hold_motor() is False                     # it may not tick ...
    assert [r["status"] for r in W.runs(REF) if r["id"] == "r-live2"] == ["running"]   # ... nor cut a live run
    W._LOCK["fd"] = first
    W.stop_motor()                                     # the first app closes
    assert W.hold_motor() is True                      # and the next one takes over
    W.stop_motor()


def test_stop_halts_and_resume_continues(W):
    _live(W)
    W.set_stopped(REF, True)
    W.owner_ask(REF, "Add a Blog page")
    assert W.run_until_idle(REF) == 0 and W.due(REF)[2] == "stopped"
    W.set_stopped(REF, False)
    assert W.run_until_idle(REF) == 4


def test_a_failed_check_is_never_published(W, monkeypatch):
    W.create(REF, "City Care Hospital Website", None)
    W.give_goal(REF, GOAL)
    real = W.engine_write

    def broken(ref, d, inp):
        files, check, spend = real(ref, d, inp)
        page = json.loads(files["index.html"])
        page["body_html"] += '<a href="nowhere.html">a dead link</a>'
        files["index.html"] = json.dumps(page)
        return files, check, spend
    monkeypatch.setitem(W.ENGINE_FN, "Write", broken)
    W.run_until_idle(REF)
    assert W.latest(REF, "Build")["check"]["ok"] is False
    assert W.status(REF)["asks"] == [] and W.versions(REF, "Live site") == []


def test_put_back_republishes_an_earlier_version(W):
    _live(W)
    first = (W.live_dir(REF) / "index.html").read_text()
    W.owner_ask(REF, "Add a Careers page")
    W.run_until_idle(REF)
    assert (W.live_dir(REF) / "careers.html").is_file()
    row = W.put_back(REF, "Live site", 1)
    assert row["v"] == 3 and row["made_from"] == [{"art": "Live site", "v": 1}]
    assert (W.live_dir(REF) / "index.html").read_text() == first
    assert not (W.live_dir(REF) / "careers.html").exists()


def test_the_trace_of_the_live_site_reaches_the_owners_words(W):
    _live(W)
    chain = W.trace(REF, "Live site", 1)
    kinds = [c["kind"] for c in chain]
    assert kinds[0] == "version" and kinds[-1] == "ask"
    assert [c["art"] for c in chain if c["kind"] == "version"] == ["Live site", "Build", "Pages", "Site plan", "Brief"]
    assert chain[-1]["text"].startswith("A website for City Care Hospital")


def test_found_gives_an_org_a_root_and_a_website_department_with_library_templates(W, tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    import sys
    from pathlib import Path
    lib = str(Path(__file__).resolve().parents[1] / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import placement_engine as E
    importlib.reload(E)
    import org2_apply
    importlib.reload(org2_apply)
    import website_api
    importlib.reload(website_api)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    app = FastAPI()
    app.include_router(website_api.router)
    c = TestClient(app)
    out = c.post("/api/native/found", json={"org": "City Care Hospital", "owner": "Sankalp"}).json()
    domains = E.load_domains()
    assert domains[out["org"]]["name"] == "City Care Hospital"
    assert domains[out["root"]]["name"] == "Root" and domains[out["root"]]["parent_ref"] == out["org"]
    assert domains[out["ref"]]["parent_ref"] == out["root"]
    import function_templates as FT
    assert set(FT.picked(out["ref"]).values()) == {f + "/product-build" for f in FT.FUNCTIONS}
    m = c.get("/api/native/%s/map" % out["ref"]).json()
    assert m["has_goal"] is False and len(m["systems"]) == 5 and len(m["engines"]) == 4
    again = c.post("/api/native/found", json={"org": "City Care Hospital"}).json()
    assert again["ref"] == out["ref"] and again["created"] is False
    assert c.post("/api/native/%s/goal" % out["ref"], json={"text": GOAL}).json()["ok"] is True
    assert W.run_until_idle(out["ref"]) == 3
    assert c.get("/api/native/%s/preview/build/1/index.html" % out["ref"]).status_code == 200


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
