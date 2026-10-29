"""test_dept_list_api.py -- the cheap listing (dept_read), the two create-or-reuse routes (PRD A5.3.6) and the shadow flag on the
task's route. The model is stubbed (shadow_dept.CHOOSER)."""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import layer_schema as S
from test_shadow_dept import TASK, org, reply  # noqa: F401  (the fixture)
from test_shadow_dept_apply import ASK_RULE, NEW


@pytest.fixture
def client(org):
    import dept_list_api
    import interface_http
    import shadow_dept_api
    app = FastAPI()
    interface_http.install(app)
    app.include_router(dept_list_api.router)             # before any {ref} route, as app.py does
    app.include_router(shadow_dept_api.router)

    @app.get("/api/native/{ref}/x")
    def _ref_route(ref: str):                            # a route the listing must not be taken for
        return {"ref": ref}
    return TestClient(app)


def _cards(org):
    return {r["name"]: r for r in org.dr.rows(org.root)}


# ---- dept_read -------------------------------------------------------------------------------------------------------
def test_rows_read_the_three_small_files_and_nothing_else(org, monkeypatch):
    calls = []
    for name in ("status", "functions_view", "map_view"):
        if hasattr(org.W, name):
            monkeypatch.setattr(org.W, name, lambda *a, **k: calls.append(name))
    rows = _cards(org)
    assert set(rows) == {"Billing", "Gardening"} and calls == []
    b = rows["Billing"]
    assert b["root"] == org.root and b["kind"] == "default" and b["runtime"] == 2 and b["stopped"] is False
    assert b["goal"].startswith("Answer billing") and b["j2_url"] == "/j2ui/%s/" % b["ref"]
    assert S.validate("dept.listing", {"departments": list(rows.values()), "root_ref": org.root, "as_of": org.W.now()}) == []


def test_a_root_is_never_a_row_and_a_stopped_department_says_stopped(org):
    d = org.W.dept(org.kids["Billing"])
    d["stopped"] = True
    org.W.save_dept(org.kids["Billing"], d)
    rows = _cards(org)
    assert rows["Billing"]["state"] == "stopped" and org.root not in [r["ref"] for r in rows.values()]


def test_rows_are_cached_by_the_files_signature(org):
    first = org.dr.rows(org.root)
    d = org.W.dept(org.kids["Gardening"])
    d["goal"] = "Plan the orchard"
    time.sleep(0.01)
    org.W.save_dept(org.kids["Gardening"], d)
    assert {r["name"]: r["goal"] for r in org.dr.rows(org.root)}["Gardening"] == "Plan the orchard"
    assert first is not org.dr.rows(org.root)


def test_candidates_are_ordered_by_overlap_and_capped(org):
    c = org.dr.candidates(org.root, "answer the customer's billing questions about invoices", limit=8)
    assert [x["name"] for x in c] == ["Billing", "Gardening"] and c[0]["score"] > c[1]["score"] >= 0
    assert len(org.dr.candidates(org.root, "anything", limit=1)) == 1
    for card in c:
        assert S.validate("dept.candidate", card) == []


# ---- GET /api/native/_departments ------------------------------------------------------------------------------------
def test_the_listing_route_answers_dept_listing_and_is_not_taken_for_a_ref(client, org):
    r = client.get("/api/native/_departments", params={"root": org.root})
    assert r.status_code == 200
    body = r.json()
    assert body["root_ref"] == org.root and {d["name"] for d in body["departments"]} == {"Billing", "Gardening"}
    assert client.get("/api/native/abc/x").json() == {"ref": "abc"}


def test_the_listing_without_a_root_lists_every_department(client, org):
    assert len(client.get("/api/native/_departments").json()["departments"]) == 2


# ---- POST /api/native/{root}/departments ------------------------------------------------------------------------------
def test_a_post_decides_and_applies_for_any_caller(client, org):
    org.sd.CHOOSER["fn"] = lambda text: reply(**NEW)
    r = client.post("/api/native/%s/departments" % org.root, json={"words": TASK})
    assert r.status_code == 200
    d = r.json()
    assert (d["final_action"], d["held"], d["mode"]) == ("create", False, "link") and d["result_ref"]
    assert org.W.dept(d["result_ref"])["name"] == "Payroll"


def test_apply_false_only_previews(client, org):
    org.sd.CHOOSER["fn"] = lambda text: reply(**NEW)
    d = client.post("/api/native/%s/departments" % org.root, json={"words": TASK, "apply": False}).json()
    assert d["final_action"] == "create" and d["result_ref"] is None
    assert len([x for x in org.W.list_depts() if x.get("parent") == org.root]) == 2


def test_confirmed_true_is_the_owners_yes_to_a_held_create(client, org):
    d = org.W.dept(org.root)
    d["rules"] = list(d.get("rules") or []) + [dict(ASK_RULE)]
    org.W.save_dept(org.root, d)
    org.sd.CHOOSER["fn"] = lambda text: reply(**NEW)
    url = "/api/native/%s/departments" % org.root
    held = client.post(url, json={"words": TASK}).json()
    assert held["held"] is True and held["result_ref"] is None
    yes = client.post(url, json={"words": TASK, "confirmed": True}).json()
    assert yes["held"] is False and yes["result_ref"]


def test_an_unknown_root_is_404_and_a_department_that_is_not_a_root_is_409(client, org):
    assert client.post("/api/native/dref-nope/departments", json={"words": TASK}).status_code == 404
    assert client.post("/api/native/%s/departments" % org.kids["Billing"], json={"words": TASK}).status_code == 409


@pytest.mark.parametrize("body", [{}, {"words": ""}, {"words": "x", "surprise": 1}, {"words": "x", "mission_id": "m-1"},
                                  {"words": "x", "apply": "yes"}, [], "text"])
def test_a_body_that_does_not_fit_is_422_not_in_schema(client, org, body):
    with S.expect_refused("dept.request"):
        r = client.post("/api/native/%s/departments" % org.root, json=body)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "NOT_IN_SCHEMA"


# ---- POST /api/shadow/tasks/{mid}/department -----------------------------------------------------------------------------
def _task(org):
    import mission_engine
    return mission_engine.MissionStore().create(TASK, mission_engine.default_offer(), target_mode="new")


def test_the_task_route_decides_stores_and_returns_the_decision(client, org):
    m = _task(org)
    org.sd.CHOOSER["fn"] = lambda text: reply(action="use", ref=org.kids["Billing"], reason="Billing handles invoices")
    r = client.post("/api/shadow/tasks/%s/department" % m["id"], json={"words": TASK, "mission_id": m["id"]})
    assert r.status_code == 200 and r.json()["final_ref"] == org.kids["Billing"]
    import mission_engine
    assert mission_engine.MissionStore().load(m["id"])["department_ref"] == org.kids["Billing"]


def test_the_task_route_is_403_when_the_shadow_flag_is_off_before_anything_else(client, org, monkeypatch):
    import providers
    monkeypatch.setattr(providers, "shadow_enabled", lambda settings=None: False)
    r = client.post("/api/shadow/tasks/m-000000000000/department", json="not even a body")
    assert r.status_code == 403


def test_the_task_route_404_for_a_task_that_is_not_there_and_400_for_another_task(client, org):
    m = _task(org)
    assert client.post("/api/shadow/tasks/m-000000000000/department", json={"words": TASK}).status_code == 404
    other = client.post("/api/shadow/tasks/%s/department" % m["id"], json={"words": TASK, "mission_id": "m-000000000000"})
    assert other.status_code == 400
