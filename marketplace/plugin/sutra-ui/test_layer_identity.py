"""Identity behind its interface (PRD amendment A1, package W1-IDENTITY: M3.8 and M3.9), one section per step:

    I1  identity/v1 provides every code, prompt, draft and check name its recipe uses, by reference, and passes the
        contract cases that do not read words
    I3  identity/v1.view returns Identity's pane and it validates as view.identity in the four states of a cycle
    I4  Identity's writers say who they are: a save of Identity's keys names Identity, and no row says otherwise
    I5  Hear a doubt: Adaptation's one doubt is put to the owner as one question with no number in it, its answer goes
        back to Adaptation as a line request, and the bounds (one a line request, two a cycle) hold

The departments are born the way a person makes them, on the real board, as test_j2's are (its fixture and helpers are
copied here with the pane's module reloaded too). A test that meets a fault of the interface fails through conftest.py;
a deliberate one is wrapped in S.expect_refused().
"""
import importlib
import json
import re

import pytest

import layer_schema as S
import layers
import layers.contract as C
import layers.identity.v1 as V1

WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A records home of the test's own, as test_j2's fixture makes one, with no model."""
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    return tmp_path


@pytest.fixture
def ctx(home):
    """The contract's fixture department, in a home of its own."""
    return {"ref": C.fixture_department(home / "departments")}


@pytest.fixture
def j2(home):
    """test_j2's fixture: the modules reloaded on a home of their own, the organisation's Root minted; the pane's module too."""
    import website_dept as W
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime as R
    import j2_runtime as J
    import functions_view as FV

    for module in (E, W, org2_apply, founding, R, J, FV):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, J, founding, FV


def _model(monkeypatch, R, answers):
    """test_j2's _model: a step id maps to what the model says (a dict, or a callable taking the prompt); every other
    step falls to its draft, as it does offline."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)

    def model(prompt, step):
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"

    monkeypatch.setattr(R, "MODEL", model)


def _born(j2, words=WEBSITE, org="Acme Learning", settle=True):
    """test_j2's _born: a department as a person makes one: found the organisation, say the words, Root sets it up."""
    W, _, _, founding, _ = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    if settle:
        W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _recipe_names():
    """Every code, prompt, draft and check name Identity's recipe uses, by kind."""
    out = {kind: set() for kind in ("code", "prompt", "draft", "check")}
    for s in C._steps(layers.recipes()["Identity"]):
        for kind in out:
            if s.get(kind):
                out[kind].add(s[kind])
    return out


# ---- I1: identity/v1 by reference ------------------------------------------------------------------------------------
def test_i1_every_name_the_recipe_uses_is_provided_and_nothing_else_is():
    names = _recipe_names()
    assert {k: set(d) for k, d in C._dicts(V1).items()} == names


def test_i1_each_name_the_recipe_uses_is_a_reference_to_the_body_engine_runtime_holds(home):
    import engine_runtime as R
    legacy = {"code": R.CODE, "prompt": R.PROMPT, "draft": R.DRAFT, "check": R.CHECK}
    for kind, d in C._dicts(V1).items():
        for name, fn in d.items():
            module, attr = fn.legacy
            assert module == "engine_runtime"
            assert getattr(R, attr) is legacy[kind][name], "%s %s points at %s, which is not the body the registry holds" % (kind, name, attr)


def test_i1_the_count_by_reference_is_reported(capsys):
    got = C.by_reference(V1)
    assert got == {"by_reference": sum(len(v) for v in _recipe_names().values()), "own": got["own"]}
    print("identity/v1: %(by_reference)d by reference, %(own)d own" % got)


@pytest.mark.parametrize("number", [1, 2, 3, 4, 7])
def test_i1_the_contract_cases_that_read_no_words_pass(number, ctx):
    fn = dict((n, f) for n, _, f in C.cases())[number]
    assert fn(V1, ctx) == []


# ---- I3: Identity's view ---------------------------------------------------------------------------------------------
#: test_j2_identity's three done-when items, one of them to confirm, and the reason Root's check sends a plan back
SHAPED = {"name": "Bakery Co Website", "kind": "website", "purpose": "the bakery's site", "second": "",
          "goal": "A phone-first website for Bakery Co, a bakery in Pune, where customers see every cake"}
ITEMS = [{"text": "Shoppers browse every cake by category", "how": "code", "level": "target", "confirm": ""},
         {"text": "An order reaches the bakery on WhatsApp", "how": "model", "level": "outcome", "confirm": ""},
         {"text": "Three reviews from customers", "how": "person", "level": "outcome", "confirm": "nobody gave the reviews"}]
FAULT = "the line reaches outside without a rule"
WHO = "Who are the site's visitors?"


def _pane(j2, ref):
    """What the layer's view gives for the department as it stands, with the events of its cycle and its asks."""
    W, _, J, _, _ = j2
    return V1.view(ref, W.dept(ref), J.events(ref), W.asks(ref))


def _in_state(j2, monkeypatch, state, org="Acme Learning"):
    """A department in one state of its cycle, reached the way a person reaches it (an organisation of its own: the
    same name finds the department already made)."""
    W, R, J, _, FV = j2
    if state == "assessing":
        ref = _born(j2, org=org, settle=False)
    elif state == "waiting":
        _model(monkeypatch, R, {"identity.enough": {"enough": False, "missing": ["goal"], "question": WHO, "why": "the goal names no one"}})
        ref = _born(j2, org=org)
    elif state == "blocked":
        monkeypatch.setattr(R, "_root_check", lambda ref, d, engines, source: [FAULT])
        _model(monkeypatch, R, {"setup.shape": dict(SHAPED, done_items=[dict(i) for i in ITEMS])})
        ref = _born(j2, org=org)
    else:
        ref = _born(j2, org=org)
        assert J.audited(ref, 1, []) is True              # Audit read what went out and found nothing: done-when holds
    assert J.status(ref)["state"] == state, J.status(ref)
    return ref


@pytest.mark.parametrize("state", ["assessing", "waiting", "blocked", "done"])
def test_i3_the_view_validates_as_view_identity_in_each_state_of_a_cycle(j2, monkeypatch, state):
    W, R, J, _, FV = j2
    ref = _in_state(j2, monkeypatch, state)
    pane = _pane(j2, ref)
    assert S.validate_view("identity", pane) == []
    assert pane == FV._identity_part(ref, W.dept(ref), J.events(ref))        # by reference: the pane S5 renders, unchanged
    assert set(pane) == {"standard", "goal", "done", "done_items", "rules", "open_question", "conflicts"}
    assert (pane["open_question"] is not None) == (state == "waiting")
    assert pane["standard"]["met"] is (state != "waiting")


def test_i3_a_conflict_closed_is_typed_too(j2, monkeypatch):
    W, R, J, _, FV = j2
    _model(monkeypatch, R, {"priority.bargain": {"answer": "reject", "why": "no room"},
                            "identity.close": {"ruling": "run", "why": "the goal cannot be met without a site"}})
    ref = _born(j2)
    pane = _pane(j2, ref)
    assert [c["ruling"] for c in pane["conflicts"]] == ["run"] and S.validate_view("identity", pane) == []


def test_i3_the_contract_reads_the_view_of_the_fixture_department(ctx):
    assert C.case_6(V1, ctx) == []
    assert C.case_6(V1, {}) == ["identity/v1: the contract has no fixture department to read the view of"]


def test_i3_a_view_that_does_not_fit_is_found_by_the_interface(ctx, monkeypatch):
    monkeypatch.setattr(V1, "view", lambda ref, d, events, asks: {"goal": 7})
    got = C.case_6(V1, ctx)
    assert got and all(f.startswith("identity/v1: view ") for f in got)


# ---- I4: Identity's writers say who they are -------------------------------------------------------------------------
NEVER = "Never publish a page without asking me first"
DONE_WORDS = "From now on, the site is done when shoppers can order a cake on WhatsApp"
#: the functions that save the record on Identity's behalf, by the key they write (A1.6): the revision (every change to
#: who the department is), the host, the ladder's numbers and what Audit's holes were looked up for
IDENTITYS_WRITERS = {"bump_identity", "set_host", "decide_ask", "set_numbers", "identity_finding"}


def _spy(monkeypatch, W):
    """W.save_dept with a record of who called it and as whom, for the test to read."""
    import sys
    seen, real = [], W.save_dept

    def save_dept(ref, d, by=None):
        seen.append((sys._getframe(1).f_code.co_name, by))
        return real(ref, d, by=by)

    monkeypatch.setattr(W, "save_dept", save_dept)
    return seen


def _ownership_rows():
    return [r for r in S.REFUSED["rows"] if any("wrote it" in f for f in r["faults"])]


def _an_instructions_ask(R, ref):
    """The owner's change to one of Identity's instruction files, filed as an ask for the stamp (PRD M2.2)."""
    return R.instructions_ask(ref, "identity", "completeness", R._instruction("identity", "completeness", ref) + "\nBe brief.\n")


def _stamp_the_pending(W, ref, kinds):
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] in kinds]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)


def test_i4_identitys_standard_and_rule_tags_are_the_interfaces(j2):
    W, R, _, _, _ = j2
    assert R.STANDARD is S.STANDARD and W.RULE_TAGS is S.RULE_TAGS
    assert R.STANDARD == ("goal", "items", "rules", "owner", "budget", "invented") and W.RULE_TAGS == ("go", "ask", "refuse", "always")


def test_i4_every_save_of_identitys_keys_names_identity_and_no_row_says_otherwise(j2, monkeypatch):
    W, R, J, _, _ = j2
    seen = _spy(monkeypatch, W)
    _model(monkeypatch, R, {"identity.recognise": {"journey": "directive", "why": "a standing rule"},
                            "identity.rule": {"tag": "ask", "line": NEVER, "scope": "standing"}})
    ref = _born(j2)
    # a rule the owner gives, stamped; a goal the owner changes, stamped; done-when changed, stamped (bump_identity)
    W.owner_ask(ref, NEVER)
    W.run_until_idle(ref, limit=300)
    _stamp_the_pending(W, ref, ("rule",))
    assert [(r["tag"], r["line"]) for r in W.dept(ref)["rules"]][-1] == ("ask", NEVER)
    W.put_done_items(ref, W.items_of(W.dept(ref)) + [{"text": "Shoppers can order a cake", "how": "model", "level": "outcome"}])
    R._standard_defaults(ref, ["goal", "rules", "owner"])                                     # 'just do it' fills from the kind
    # where the site is served from, asked at the first publish and said by the owner (set_host, decide_ask)
    W.set_host(ref, "bakery.example.org")
    d = W.dept(ref)
    d["host"] = ""
    W.save_dept(ref, d)
    W._put_ask(ref, {"id": "a-publish1", "kind": "publish", "engine": "Identity", "text": "Publish?", "status": "pending", "created": W.now()})
    W.decide_ask(ref, "a-publish1", True)
    # the owner's ladder numbers, and a hole Audit found that the department's own engine looks up
    R.set_numbers(ref, "Plan", {"runs": 41})
    monkeypatch.setattr(R, "_web_engine", lambda d: "Plan")
    R.post(ref, "Audit", "Identity", "inform", {"word": "finding", "claim": "opening hours", "severity": "low", "where": "Home",
                                                "findings": [{"kind": "hole", "claim": "opening hours"}]})
    W.run_until_idle(ref, limit=300)
    assert W.dept(ref)["looked_up"] == ["opening hours"]

    mine = [(who, by) for who, by in seen if who in IDENTITYS_WRITERS]
    assert {who for who, _ in mine} == IDENTITYS_WRITERS, "every one of Identity's writers was run"
    assert all(by == "identity" for _, by in mine), mine
    assert _ownership_rows() == []                       # no row says a layer wrote what another's key holds


def test_i4_a_save_that_does_name_identity_for_a_key_another_owns_is_a_row(j2):
    """The detection is real: the same save, changing Root's name, is one row, which only this test may meet."""
    W, _, _, _, _ = j2
    ref = _born(j2)
    d = W.dept(ref)
    d["name"] = "Another name"
    with S.expect_refused("department") as met:
        W.save_dept(ref, d, by="identity")
    assert met == ["$.name: is Root's, and Identity wrote it"]


def test_i4_every_ask_identity_files_validates_as_identity_ask(j2, monkeypatch):
    W, R, J, _, _ = j2
    kinds = {}

    def take(ref):
        for a in W.asks(ref):
            kinds.setdefault(a["kind"], []).append(a)

    _model(monkeypatch, R, {"identity.recognise": {"journey": "directive", "why": "a standing rule"},
                            "identity.rule": {"tag": "ask", "line": NEVER, "scope": "standing"}})
    ref = _born(j2)
    W.owner_ask(ref, NEVER)
    W.run_until_idle(ref, limit=300)                                                          # a rule ask
    take(ref)
    _stamp_the_pending(W, ref, ("rule",))
    _model(monkeypatch, R, {"identity.recognise": {"journey": "directive", "why": "it says when the site is done"},
                            "identity.rule": {"tag": "goal", "line": DONE_WORDS[len("From now on, "):], "scope": "standing"}})
    W.owner_ask(ref, DONE_WORDS)
    W.run_until_idle(ref, limit=300)                                                          # a done_items ask
    instructions = _an_instructions_ask(R, ref)
    take(ref)
    waiting = _in_state(j2, monkeypatch, "waiting", "Waiting Co")                                # Identity's question: a j2_identity ask
    take(waiting)
    blocked = _in_state(j2, monkeypatch, "blocked", "Blocked Co")                                # a blocked plan: an ask with options
    take(blocked)
    assert {"rule", "done_items", "instructions", "j2_identity", "blocked"} <= set(kinds)
    assert instructions["id"] in [a["id"] for a in kinds["instructions"]]
    for kind in ("rule", "done_items", "instructions", "j2_identity", "blocked"):
        for a in kinds[kind]:
            assert S.validate_record("identity", "ask", a) == [], (kind, a)
    assert all(o["id"] in ("words", "stop") or o["id"].startswith("leave:") for a in kinds["blocked"] for o in a["options"])
    assert all(S.validate("option", o) == [] for a in kinds["blocked"] for o in a["options"])
