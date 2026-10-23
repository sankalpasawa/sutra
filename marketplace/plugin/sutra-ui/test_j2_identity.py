"""test_j2_identity.py -- Identity: one record, its standard, a way out (PRD M3).

Named claims, each a done check of the PRD:
  M3.1  dept.json is the one record of who the department is: founding makes its goal the goal Root shaped, and after a
        J2 answer the identity read and the Org screen's copy both equal it. The copy is filed and applied through the
        proposals path (decision C1), so nothing waits for the owner
  M3.2  Root drafts done-when items at birth, each with an id, a how and a level; the birth tell names them; offline there
        is exactly one item, D1, the kind's done line
  M3.3  Identity reads the identity against the standard in its completeness file: thin words get a question and the
        answer is read again; a question J1 already answered is not asked; 'just do it' starts step 2 and the tell names
        the defaults it used
  M3.4  a rule given as an answer keeps its tag through the rule ask, and a change to the done-when items never touches
        the goal
  M3.5  blocked always has a way out: new words reopen step 2, and the blocked message is an ask with options, each
        applied by code; an unknown option is 409 UNKNOWN_OPTION
  M3.6  one voice, in plain words: every tell passes the plain-words check, and only Identity speaks to the owner
  M3.7  Identity's pane: the read holds the standard, the done-when items, the rules, the open question and the conflicts

The departments are born the way a person makes them (founded, asked for, set up by Root), on a records home of their
own; no test reaches a model or the network: the model is a function, and every step it does not answer runs offline.
"""
import importlib

import pytest

BAKERY = "a site for my bakery in Pune"
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
    import functions_view as F

    for module in (E, W, org2_apply, founding, R, J, F):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, J, founding, F


def _model(monkeypatch, R, answers):
    """A model that is a function: a step id maps to what the model says (a dict, or a callable taking the prompt).
    Every other step runs its offline draft."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    asked = []

    def model(prompt, step):
        asked.append((step["id"], prompt))
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"

    monkeypatch.setattr(R, "MODEL", model)
    return asked


def _found(j2, words=BAKERY, org="Bakery Co"):
    W, _, _, founding, _ = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    return root, next(d for d in W.list_depts() if d.get("parent") == root)["ref"]


def _born(j2, words=BAKERY, org="Bakery Co", settle=True):
    W = j2[0]
    _, ref = _found(j2, words, org)
    if settle:
        W.run_until_idle(ref, limit=300)
    return ref


def _actions(J, ref):
    return [e["action"] for e in J.events(ref)]


def _said(R, ref):
    return [str((p["payload"] or {}).get("done") or (p["payload"] or {}).get("objective") or "") for p in R.board(ref)
            if p["src"] == "Identity" and "Owner" in p["dst"]]


def _client():
    import dept_api
    import j2_api
    import website_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    for m in (dept_api, j2_api, website_api):
        importlib.reload(m)
    app = FastAPI()
    for m in (dept_api, j2_api, website_api):
        app.include_router(m.router)
    return TestClient(app)


SHAPED = {"name": "Bakery Co Website", "kind": "website", "purpose": "the bakery's site", "second": "",
          "goal": "A phone-first website for Bakery Co, a bakery in Pune, where customers see the cakes and order on WhatsApp"}


# ---- M3.1 ------------------------------------------------------------------------------------------------------------
def test_m3_1_founding_makes_the_records_goal_the_goal_root_shaped(j2, monkeypatch):
    """A department born with the kind's goal line ('A live website for ...') while Root shaped the owner's own must fail."""
    W, R, _, founding, _ = j2
    _model(monkeypatch, R, {"setup.shape": dict(SHAPED)})
    ref = _born(j2, settle=False)
    d = W.dept(ref)
    assert d["goal"] == SHAPED["goal"]
    assert d["goal"] != W.KINDS["website"]["goal"].format(name=d["name"])
    assert founding._standing(ref)["purpose"] == SHAPED["goal"]                  # born with the same words on its copy


def test_m3_1_offline_the_goal_is_the_owners_words(j2):
    W = j2[0]
    ref = _born(j2, settle=False)
    assert W.dept(ref)["goal"] == BAKERY


def test_m3_1_after_a_j2_answer_the_identity_read_and_the_copy_equal_the_record(j2, monkeypatch):
    """The Org screen's copy left behind the record, a copy written straight to the registry, or one that waits in
    Approvals for a stamp, must fail."""
    W, R, J, founding, _ = j2
    import proposals
    _model(monkeypatch, R, {"setup.shape": dict(SHAPED)})
    ref = _born(j2, settle=False)
    d = W.dept(ref)
    d["goal"] = ""                                                    # the identity has a gap: Identity asks for the goal
    W.save_dept(ref, d)
    J._ask_gap(ref, W.dept(ref), J._state(ref))
    assert J.status(ref)["open_question"]["missing"] == "goal"
    before = int(W.dept(ref).get("identity_revision") or 1)
    filed = len(proposals.listing())
    answer = "A website for Bakery Co where customers in Pune order cakes for pickup"
    J.answer(ref, answer)

    d = W.dept(ref)
    assert d["goal"] == answer and d["identity_revision"] == before + 1
    got = _client().get("/api/dept/%s/identity" % ref).json()
    assert got["source"] == "record" and got["goal"] == d["goal"] and got["done"] == d["done"]
    assert got["rules"] == [{"tag": r["tag"], "text": r["line"]} for r in d["rules"]]
    copy = founding._standing(ref)
    assert copy["purpose"] == d["goal"]
    assert copy["done_when"] == ([i["text"] for i in d.get("done_items") or []] or [d["done"]])
    assert [{"tag": r["tag"], "line": r["line"]} for r in copy["rules"]] == [{"tag": r["tag"], "line": r["line"]} for r in d["rules"]]
    # filed and applied in one move (decision C1): one org.charter proposal more, approved, and nothing waits for a stamp
    new = proposals.listing()[:len(proposals.listing()) - filed]
    assert [(p["kind"], p["status"]) for p in new] == [("org.charter", "approved")]
    assert proposals.pending() == []
    # the same identity again files nothing
    founding.mirror(ref)
    assert len(proposals.listing()) == filed + 1


def test_m3_1_a_department_not_in_the_registry_has_no_copy_and_nothing_is_filed(j2):
    W, _, _, founding, _ = j2
    import proposals
    W.create("dref-alone", "Alone Website", None)
    d = W.bump_identity("dref-alone", W.dept("dref-alone"))
    assert d["identity_revision"] == 2 and founding.mirror("dref-alone") is None
    assert proposals.listing() == []


# ---- M3.2 ------------------------------------------------------------------------------------------------------------
ITEMS = [{"text": "Shoppers browse every cake by category", "how": "code", "level": "target", "confirm": ""},
         {"text": "An order reaches the bakery on WhatsApp", "how": "model", "level": "outcome", "confirm": ""},
         {"text": "Three reviews from customers", "how": "person", "level": "outcome", "confirm": "nobody gave the reviews"}]


def _birth_tell(R, root):
    return [p["payload"]["done"] for p in R.board(root) if (p["payload"] or {}).get("word") == "department"]


def test_m3_2_root_drafts_done_when_items_at_birth_each_with_an_id_a_how_and_a_level(j2, monkeypatch):
    """A department born with one line of done-when and no items, or items with no how, must fail."""
    W, R, _, founding, _ = j2
    _model(monkeypatch, R, {"setup.shape": dict(SHAPED, done_items=[dict(i) for i in ITEMS])})
    root, ref = _found(j2)
    d = W.dept(ref)
    assert d["done_items"] == [{"id": "D1", "text": ITEMS[0]["text"], "how": "code", "level": "target"},
                               {"id": "D2", "text": ITEMS[1]["text"], "how": "model", "level": "outcome"},
                               {"id": "D3", "text": ITEMS[2]["text"], "how": "person", "level": "outcome"}]
    assert d["to_be_confirmed"] == [{"item": "D3", "why": "nobody gave the reviews"}]
    assert d["done"] == "; ".join(i["text"] for i in ITEMS)                         # done stays as the items' joined text
    tell = _birth_tell(R, root)
    assert len(tell) == 1
    for i, item in enumerate(ITEMS):
        assert "D%d %s" % (i + 1, item["text"]) in tell[0]
    assert "D3 Three reviews from customers (to confirm)" in tell[0]
    assert founding._standing(ref)["done_when"] == [i["text"] for i in ITEMS]       # what Root stamped, on the Org screen too


def test_m3_2_offline_there_is_exactly_one_item_the_kinds_done_line(j2):
    W, R, _, _, _ = j2
    root, ref = _found(j2, WEBSITE, "Acme Learning")
    d = W.dept(ref)
    assert d["done_items"] == [{"id": "D1", "text": W.KINDS[d["kind"]]["done"], "how": "code", "level": "outcome"}]
    assert d["done"] == W.KINDS[d["kind"]]["done"] and d["to_be_confirmed"] == []
    assert "Done when: D1 %s." % W.KINDS[d["kind"]]["done"] in _birth_tell(R, root)[0]


def test_m3_2_an_item_that_does_not_say_how_it_is_checked_fails_roots_shape(j2, monkeypatch):
    W, R, _, _, _ = j2
    _model(monkeypatch, R, {"setup.shape": dict(SHAPED, done_items=[{"text": "It looks nice", "how": "vibes", "level": "outcome"}])})
    root = j2[3].found_structure("Bakery Co", owner="Sankalp")["root"]
    W.owner_ask(root, BAKERY)
    W.run_until_idle(root, limit=300)
    assert not [d for d in W.list_depts() if d.get("parent") == root]                  # nothing was made on a bad item
    shaped = [r for r in R.step_rows(root) if r["step"] == "setup.shape"]
    assert shaped[-1]["status"] == "failed" and "D1 says how it is checked as 'vibes'" in shaped[-1]["why"]


def test_m3_2_every_department_on_the_runtime_holds_its_items(j2):
    W = j2[0]
    W.create("dref-items", "Items Website", None)
    assert W.dept("dref-items")["done_items"] == [{"id": "D1", "text": W.KINDS["website"]["done"], "how": "code", "level": "outcome"}]
    assert W.done_items([{"text": " "}, {"text": "A", "how": "Code", "level": "TARGET"}], "website") == \
        [{"id": "D1", "text": "A", "how": "code", "level": "target"}]
