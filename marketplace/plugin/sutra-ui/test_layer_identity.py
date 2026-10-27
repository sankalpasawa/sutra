"""Identity behind its interface (PRD amendment A1, packages W1-IDENTITY: M3.8 and M3.9, and W2-IDENTITY: M5.4, M8.4, M8.5,
M9.3, M9.5 and M9.8), one section per step:

    I1  identity/v1 provides every code, prompt, draft and check name its recipe uses, by reference, and passes the
        contract cases that do not read words
    I2  Identity's words: every part of its prompts is served from WORDS and LAYOUT, byte for byte the .md part
    I3  identity/v1.view returns Identity's pane and it validates as view.identity in the four states of a cycle
    I4  Identity's writers say who they are: a save of Identity's keys names Identity, and no row says otherwise
    I5  Hear a doubt: Adaptation's one doubt is put to the owner as one question with no number in it, its answer goes
        back to Adaptation as a line request, and the bounds (one a line request, two a cycle) hold
    I6  the contract, every case, passes for identity/v1 with no part of its prompts on the .md fallback
    J1  a conflict that carries ways out reaches the owner as one ask with those options, each applied by the layer that owns it
    J2  Hear a reading: done is read from Audit's reading, by its id, and nothing else declares the goal reached
    J3  a reading is weighed three ways: a question, an ask, or the next move to Adaptation
    J4  File a granted round: the correction joins the Brief with no stamp unless a rule says ask
    J5  no silent ends: every end of the pursuit that is not done leaves a pending ask with options
    J6  a stamped change to the goal or to done-when starts the cycle again

The departments are born the way a person makes them, on the real board, as test_j2's are (its fixture and helpers are
copied here with the pane's module reloaded too). A test that meets a fault of the interface fails through conftest.py;
a deliberate one is wrapped in S.expect_refused().
"""
import importlib
import inspect
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
def j2(home, monkeypatch):
    """test_j2's fixture: the modules reloaded on a home of their own, the organisation's Root minted; the pane's module too.
    No test here may reach the live model (website_dept.model_json runs the `claude` CLI on the owner's plan: slow, billed, and
    different every time): it answers as offline and the test fails at its end if it was asked. A test that unsets
    SUTRA_WEBSITE_OFFLINE (_model) gives R.MODEL an answer for every step; one that sets R.MODEL to None turns it back on."""
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
    live = []
    monkeypatch.setattr(W, "model_json", lambda prompt, *a, **k: live.append(str(prompt)[:80]) or (None, 0.0, "offline"))
    yield W, R, J, founding, FV
    assert not live, "this test reached the live model %d time(s), first with: %s" % (len(live), live[0])


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


#: the bodies identity/v1 holds of its own: the handler Hear a doubt (I5) and the two steps that tell it the owner's answer, and
#: the wave 2 additions (J1 to J6)
OWN_CODE = {"identity_doubt", "identity_read", "identity_file", "identity_closed", "identity_apply", "identity_done",
            "identity_weigh_reading", "identity_finding", "identity_round", "identity_drop"}
OWN_CHECK = {"done_is_read"}
OWN = OWN_CODE | OWN_CHECK


def test_i1_each_name_the_recipe_uses_is_a_reference_to_the_body_engine_runtime_holds_but_the_versions_own(home):
    import engine_runtime as R
    legacy = {"code": R.CODE, "prompt": R.PROMPT, "draft": R.DRAFT, "check": R.CHECK}
    assert {n for n, f in V1.CODE.items() if not hasattr(f, "legacy")} == OWN_CODE
    assert {n for n, f in V1.CHECK.items() if not hasattr(f, "legacy")} == OWN_CHECK
    for kind, d in C._dicts(V1).items():
        for name, fn in d.items():
            if name in OWN:
                continue
            module, attr = fn.legacy
            assert module == "engine_runtime"
            assert getattr(R, attr) is legacy[kind][name], "%s %s points at %s, which is not the body the registry holds" % (kind, name, attr)


def test_i1_the_count_by_reference_is_reported(capsys):
    got = C.by_reference(V1)
    assert got == {"by_reference": sum(len(v) for v in _recipe_names().values()) - len(OWN), "own": len(OWN)}
    print("identity/v1: %(by_reference)d by reference, %(own)d own" % got)


@pytest.mark.parametrize("number", [1, 2, 3, 4, 7])
def test_i1_the_contract_cases_that_read_no_words_pass(number, ctx):
    fn = dict((n, f) for n, _, f in C.cases())[number]
    assert fn(V1, ctx) == []


# ---- I2: Identity's words --------------------------------------------------------------------------------------------
def _parts():
    return [(g, p) for g, parts in S.PROMPTS["identity"].items() for p in parts]


def test_i2_every_part_of_identitys_prompts_has_its_words_and_none_is_on_the_md_fallback(home):
    import layers.prompts as P
    assert C.on_the_md_fallback(V1) == []
    assert [(g, p) for g, parts in V1.WORDS.items() for p in parts] == _parts() == [(g, p) for g, parts in V1.LAYOUT.items() for p in parts]
    assert all(P._module(None, "identity", g, p) is V1 for g, p in _parts()), "the compiler takes the WORDS path for every part"
    assert C.case_5(V1, {}) == [] and P.faults() == []


def test_i2_each_part_compiles_back_to_the_md_part_byte_for_byte(home):
    import engine_runtime as R
    import layers.prompts as P
    for g, p in _parts():
        if ("identity", g, p) in S.ADDED_PARTS:                 # an added part has no .md part (A3-FUNCTIONS)
            continue
        inputs = {n: "<%s>" % n for n in S.PROMPTS["identity"][g][p]["inputs"]}
        md = P.SLOT.sub(lambda m: inputs[m.group(1)], P.md_part("identity", g, p))
        assert P.prompt(None, "identity", g, p, **inputs) == md, "%s.%s" % (g, p)
        assert S.PROMPTS["identity"][g][p]["returns"] is None or S.PROMPTS["identity"][g][p]["returns"] in md
    assert P.words(None, "identity", "goal", "does")["text"] == R._goal_of(None, "Identity")[0]


def test_i2_the_prompt_is_what_the_words_say_and_without_them_the_bundle_is_read(home, monkeypatch):
    """The words are what is served (the M2.1a snapshot, in test_function_prompts, passes unchanged on them): change one,
    and the prompt changes; set them aside, and the .md part, the same text, is read instead."""
    inputs = {n: "<%s>" % n for n in S.PROMPTS["identity"]["take"]["take"]["inputs"]}
    shipped = layers.prompt(None, "identity", "take", "take", **inputs)
    assert shipped.startswith("Judge one request from the owner.\nTHE GOAL: <goal>\n")
    monkeypatch.setitem(V1.WORDS["take"]["take"], "task", "Judge one request from the owner, kindly.")
    assert layers.prompt(None, "identity", "take", "take", **inputs) == shipped.replace("from the owner.", "from the owner, kindly.", 1)
    monkeypatch.undo()
    monkeypatch.setattr(V1, "WORDS", {})
    monkeypatch.setattr(V1, "LAYOUT", {})
    assert layers.prompt(None, "identity", "take", "take", **inputs) == shipped


def test_i2_the_owners_stamped_change_to_identitys_instructions_reaches_the_prompt_it_says_the_next_run_uses(j2):
    """Identity serves every part of its prompts from its words, and the owner's stamped change wins over them: Identity says
    'the next run uses it' and it does (a verifier found the words served and the change never sent). The live path, with no
    part of Identity's words set aside; W1-CORE K2's typed value is the same claim when it lands."""
    W, R, J, _, _ = j2
    ref, other = _born(j2), _born(j2, org="Other Co")
    assert C.on_the_md_fallback(V1) == [], "every part is served from the words"
    inputs = {n: "<%s>" % n for n in S.PROMPTS["identity"]["completeness"]["enough"]["inputs"]}
    shipped = layers.prompt(ref, "identity", "completeness", "enough", **inputs)
    assert "Be brief." not in shipped
    _an_instructions_ask(R, ref)
    assert layers.prompt(ref, "identity", "completeness", "enough", **inputs) == shipped, "nothing changes before the stamp"
    _stamp_the_pending(W, ref, ("instructions",))
    changed = layers.prompt(ref, "identity", "completeness", "enough", **inputs)
    assert "Be brief." in changed and S.PROMPTS["identity"]["completeness"]["enough"]["returns"] in changed, "the answer's shape is the app's"
    assert any("the next run uses it" in s for s in _said_by_identity(R, ref)), "the owner is told so, and it is so"
    assert layers.prompt(other, "identity", "completeness", "enough", **inputs) == shipped, "another department keeps the words"


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


def _items_met(prompt):
    """Audit's reader (M8.3), a function: it says every done-when item in the prompt is met, with its evidence."""
    items = json.loads(prompt.split("THE DONE-WHEN ITEMS:\n", 1)[1].split("\n\nWHAT CODE MEASURED:", 1)[0])
    return {"items": [{"id": i["id"], "verdict": "met", "claim": "it holds", "evidence": "the work shows it"} for i in items], "findings": []}


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
        # Audit read what went out, item by item, and found every done-when item met (S-30): Identity reads the reading and
        # says the goal is reached; "found nothing" without a reading clears nothing (PRD M8.3, M8.4)
        _model(monkeypatch, R, {"audit.judge": {"ok": True, "findings": []}, "audit.items": _items_met})
        ref = _born(j2, org=org)
        _stamp_the_pending(W, ref, ("publish",))
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
    """The owner's change to one of Identity's instruction files, filed as an ask for the stamp: the typed change of A1.16
    (a field of a part) once the app takes it, else M2.2's whole file."""
    if "group" in inspect.signature(R.instructions_ask).parameters:
        return R.instructions_ask(ref, "identity", "completeness", "enough", "task", layers.words(ref, "identity", "completeness", "enough")["task"] + " Be brief.")
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


# ---- I5: Hear a doubt ------------------------------------------------------------------------------------------------
BAKERY = "a site for my bakery in Pune"
DOUBT = "When someone pre-orders a cake, where should the order go, for example an email to the shop?"
FALLBACK_SAYS = "the form shows the order on screen for the customer to take to the shop, and sends nothing"
ANSWER = "Email it to hello@bakery.example"


def _doubts(R, ref, doubt=DOUBT, fallback=FALLBACK_SAYS, confidence=0.45, **more):
    """A stub Adaptation: it posts its one doubt about the plan it shaped (inform/doubt, M6.4). The interface lists no
    such send for Adaptation until W1-ADAPT adds its row, so the fault of that is expected here and only here."""
    with S.expect_refused():
        return R.post(ref, "Adaptation", "Identity", "inform",
                      dict({"word": "doubt", "engine": "Site", "doubt": doubt, "fallback": fallback, "confidence": confidence}, **more))


def _plan_asks(W, ref):
    return [a for a in W.asks(ref) if a["kind"] == "j2_identity" and a.get("missing") == "plan"]


def _line_requests(R, ref):
    return [q for q in R.board(ref) if q["src"] == "Identity" and q["dst"] == ["Adaptation"] and q["msg_type"] == "request"
            and q["payload"].get("word") == "line"]


def _doubting(j2, words=BAKERY, org="Bakery Co"):
    """A department that has its plan and runs, and Adaptation's doubt about a plan it shaped, heard."""
    W, R, J, _, _ = j2
    ref = _born(j2, words, org)
    _doubts(R, ref)
    W.run_until_idle(ref, limit=300)
    return ref


def _owner_says(j2, ref, how, text):
    W, _, J, _, _ = j2
    if how == "chat":
        W.owner_ask(ref, text)
    else:
        J.answer(ref, text)
    W.run_until_idle(ref, limit=300)


def test_i5_identitys_recipe_hears_a_doubt_and_the_interface_says_so(home):
    import engine_runtime as R
    row = next(r for r in S.hears("identity") if (r["act"], r["word"]) == ("inform", "doubt"))
    assert (row["from"], row["via"], row["payload"], row["handler"]) == (("Adaptation",), "board", "act.doubt", "Hear a doubt")
    handler = next(h for h in layers.recipes()["Identity"]["on"] if h["name"] == "Hear a doubt")
    assert handler["when"] == {"msg_type": "inform", "word": "doubt"}
    assert [(s["code"], s["born"], s["check"]) for s in handler["steps"]] == [("hear", "C2", "facts_are_closed"), ("identity_doubt", "C2", "said_what_it_did")]
    assert R.validate(R.defs()) == []
    assert S.validate("act.doubt", {"word": "doubt", "engine": "Site", "doubt": DOUBT, "fallback": FALLBACK_SAYS, "confidence": 0.45}) == []


def test_i5_the_interface_declares_the_fields_a_doubt_adds_to_the_line_request_and_the_ask():
    """The line request Identity posts carries answer, doubt, fallback and go_on; the ask that puts a doubt carries the doubt
    record. The interface types them (A1.13), so a wrong type is a fault, and Adaptation has a name to read go_on by."""
    props = S.DEFS["act.line_request"]["properties"]
    assert (props["go_on"], props["answer"]["maxLength"], props["doubt"]["maxLength"], props["fallback"]["maxLength"]) == ({"type": "boolean"}, 2000, 600, 600)
    assert set(S.DEFS["identity.ask"]["properties"]["doubt"]["properties"]) == {"engine", "doubt", "shown", "fallback", "line", "answered"}
    ok = {"word": "line", "words": "w", "answer": "Email it", "doubt": DOUBT, "fallback": FALLBACK_SAYS, "go_on": True}
    assert S.validate("act.line_request", ok) == [] and S.validate("act.line_request", {"word": "line"}) == [], "all of them are optional"
    for key, bad in (("go_on", "not a bool"), ("go_on", 1), ("answer", 123), ("answer", "x" * 2001), ("doubt", ["x"]), ("doubt", "x" * 601),
                     ("fallback", None), ("fallback", "x" * 601)):
        assert any(key in f for f in S.validate("act.line_request", dict(ok, **{key: bad}))), (key, bad)
    held = {"id": "a-1", "kind": "j2_identity", "status": "pending", "doubt": {"engine": "Site", "doubt": DOUBT, "shown": DOUBT, "fallback": FALLBACK_SAYS,
                                                                                  "line": 7, "answered": 9}}
    assert S.validate_record("identity", "ask", held) == []
    assert S.validate_record("identity", "ask", dict(held, doubt=dict(held["doubt"], line=None, answered=True))) == []
    for bad in ("not an object", dict(held["doubt"], line="seven"), dict(held["doubt"], answered="yes"), dict(held["doubt"], doubt=["x"]),
                dict(held["doubt"], fallback="x" * 601), dict(held["doubt"], engine="x" * 41)):
        assert S.validate_record("identity", "ask", dict(held, doubt=bad)), bad


def test_i5_a_line_request_or_an_ask_with_a_wrong_type_in_a_doubts_fields_is_a_fault_on_write(j2):
    W, R, J, _, _ = j2
    ref = _doubting(j2)
    with S.expect_refused() as met:
        with pytest.raises(S.SchemaFault):
            R.post(ref, "Identity", "Adaptation", "request", {"word": "line", "words": "w", "go_on": "not a bool", "answer": 123})
    assert any("go_on" in f for f in met) and any("answer" in f for f in met), met
    ask = _plan_asks(W, ref)[0]
    with S.expect_refused("identity.ask") as met:
        with pytest.raises(S.SchemaFault):
            W._put_ask(ref, dict(ask, doubt="not an object"))
    assert any("doubt" in f for f in met), met
    assert _plan_asks(W, ref)[0] == ask, "refuse mode: the ask stands as it was filed"


def test_i5_a_doubt_is_one_ask_with_no_number_in_it(j2):
    W, R, J, _, FV = j2
    ref = _doubting(j2)
    asks = _plan_asks(W, ref)
    assert len(asks) == 1 and asks[0]["status"] == "pending"
    name = W.dept(ref)["name"]
    # J2B-8, built by code from the doubt and its fallback
    assert asks[0]["text"] == 'Before I set up the work for %s: %s Unless you say, %s. Answer in your own words, or say "just do it".' % (name, DOUBT, FALLBACK_SAYS)
    assert not re.search(r"\d", asks[0]["text"].replace(name, ""))
    owner_sees = json.dumps([p for p in R.board(ref) if "Owner" in p["dst"]]) + json.dumps(asks[0]) + json.dumps(J.status(ref)["open_question"])
    assert "0.45" not in owner_sees and "confidence" not in owner_sees      # the number is Adaptation's to Identity, never the owner's
    assert not re.search(r"Adaptation|Priority|Coordination|confiden|J2|engine", asks[0]["text"])
    assert asks[0]["standard"] is False and asks[0]["points"] == ["plan"] and asks[0]["answer"] == "words"
    assert S.validate_record("identity", "ask", asks[0]) == []
    st = J.status(ref)
    assert (st["state"], st["step"]) == ("waiting", 2)
    assert st["open_question"]["id"] == asks[0]["id"] and st["open_question"]["missing"] == "plan" and st["open_question"]["standard"] is False
    assert J.waiting_on_owner(ref)
    # the pane carries it, and it is not a question on the standard
    pane = FV.function(ref, "identity")["j2"]
    assert pane["open_question"]["text"] == asks[0]["text"] and pane["standard"]["met"] is True
    assert S.validate_view("identity", pane) == []
    # Identity says it once, and the line names its card
    said = [p for p in R.board(ref) if p["src"] == "Identity" and p["dst"] == ["Owner"] and p["payload"].get("word") == "question"]
    assert len(said) == 1 and said[0]["payload"]["card"] == asks[0]["id"] and said[0]["payload"]["done"] == asks[0]["text"]
    assert [e["action"] for e in J.events(ref)][-1] == "identity.questioned" and J.events(ref)[-1]["step"] == 2


@pytest.mark.parametrize("how", ["chat", "answer box"])
def test_i5_the_answer_posts_a_line_request_that_carries_it(j2, how):
    W, R, J, _, _ = j2
    ref = _doubting(j2)
    before = len(_line_requests(R, ref))
    ask = _plan_asks(W, ref)[0]
    _owner_says(j2, ref, how, ANSWER)
    sent = _line_requests(R, ref)[before:]
    assert len(sent) == 1, "one line request, whichever way the owner answered"
    pl = sent[0]["payload"]
    assert (pl["word"], pl["answer"], pl["doubt"]) == ("line", ANSWER, DOUBT) and ANSWER in pl["words"]
    assert not pl.get("go_on") and pl["faults"] == [] and S.validate("act.line_request", pl) == []
    closed = next(a for a in W.asks(ref) if a["id"] == ask["id"])
    assert (closed["status"], closed["answered"]) == ("stamped", ANSWER) and closed["doubt"]["answered"]
    assert ANSWER in " ".join(W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"]).values())      # it joins the Brief with its question
    assert J.status(ref)["open_question"] is None
    acts = [e["action"] for e in J.events(ref)]
    assert acts[acts.index("ask.answered", acts.index("identity.questioned")):].count("proposal.requested") == 1
    assert any("Adaptation shapes the plan afresh with your answer" in s for s in _said_by_identity(R, ref))
    assert J.status(ref)["state"] in ("adapting", "running")                  # the cycle went back to Adaptation and runs on


def _said_by_identity(R, ref):
    return [str(p["payload"].get("done") or p["payload"].get("objective") or "") for p in R.board(ref) if p["src"] == "Identity" and "Owner" in p["dst"]]


@pytest.mark.parametrize("how", ["chat", "answer box"])
def test_i5_just_do_it_takes_the_fallback_and_the_tell_names_it(j2, how):
    W, R, J, _, _ = j2
    ref = _doubting(j2)
    before = len(_line_requests(R, ref))
    _owner_says(j2, ref, how, "just do it")
    sent = _line_requests(R, ref)[before:]
    assert len(sent) == 1
    assert sent[0]["payload"]["answer"] == "going with this: " + FALLBACK_SAYS and sent[0]["payload"]["doubt"] == DOUBT
    assert any("Just doing it: %s." % FALLBACK_SAYS in s for s in _said_by_identity(R, ref))
    assert "going with this: " + FALLBACK_SAYS in " ".join(W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"]).values())
    assert not R.JUST_DO_IT.search(sent[0]["payload"]["answer"])


def test_i5_one_question_a_line_request_two_a_cycle_and_a_third_files_no_ask(j2):
    W, R, J, _, _ = j2
    ref = _doubting(j2)
    assert len(_plan_asks(W, ref)) == 1
    _doubts(R, ref)                                                              # the same line request doubts again: asked already
    W.run_until_idle(ref, limit=300)
    assert len(_plan_asks(W, ref)) == 1 and not [q for q in _line_requests(R, ref) if q["payload"].get("go_on")]
    _owner_says(j2, ref, "chat", ANSWER)
    _doubts(R, ref, doubt="Which days is the shop closed?", fallback="the page says nothing of the days")           # the new line request: its one
    W.run_until_idle(ref, limit=300)
    asks = _plan_asks(W, ref)
    assert len(asks) == 2 and asks[1]["status"] == "pending" and "Which days is the shop closed?" in asks[1]["text"]
    _owner_says(j2, ref, "answer box", "Closed on Mondays")
    sent_before = len(_line_requests(R, ref))
    _doubts(R, ref, doubt="Should the page say who the baker is?", fallback="the page names no one")              # the third in the cycle
    W.run_until_idle(ref, limit=300)
    assert len(_plan_asks(W, ref)) == 2, "a third doubt in the cycle files no ask"
    sent = _line_requests(R, ref)[sent_before:]
    assert len(sent) == 1 and sent[0]["payload"]["go_on"] is True
    assert sent[0]["payload"]["doubt"] == "Should the page say who the baker is?" and sent[0]["payload"]["fallback"] == "the page names no one"
    assert S.validate("act.line_request", sent[0]["payload"]) == []
    told = [s for s in _said_by_identity(R, ref) if "the plan goes on as it stands" in s]
    assert len(told) == 1 and "Should the page say who the baker is?" in told[0] and "Unless you say otherwise, the page names no one." in told[0]
    assert J.status(ref)["open_question"] is None


def test_i5_a_doubt_that_comes_back_after_adaptation_was_told_to_go_on_is_a_blocked_plan_never_a_loop(j2):
    W, R, J, _, _ = j2
    ref = _doubting(j2)
    for said in ("A first answer", "A second answer"):
        _owner_says(j2, ref, "chat", said)
        _doubts(R, ref)
        W.run_until_idle(ref, limit=300)
    assert len(_plan_asks(W, ref)) == 2
    went_on = [q for q in _line_requests(R, ref) if q["payload"].get("go_on")]
    assert len(went_on) == 1                                                    # the third doubt: told to go on
    sent = len(_line_requests(R, ref))
    _doubts(R, ref)                                                             # Adaptation doubts again, ignoring it
    W.run_until_idle(ref, limit=300)
    assert len(_line_requests(R, ref)) == sent and len(_plan_asks(W, ref)) == 2   # no further request, no further question
    assert J.status(ref)["state"] == "blocked"
    card = next(a for a in W.asks(ref) if a["kind"] == "blocked" and a["status"] == "pending")
    assert [o["id"] for o in card["options"]][0] == "words" and card["options"][-1]["id"] == "stop"
    assert DOUBT in card["text"] and card["why"] == DOUBT


def test_i5_with_another_question_open_the_doubt_waits_for_the_plan_to_be_shaped_again(j2):
    W, R, J, _, _ = j2
    ref = _born(j2, BAKERY)
    J.asked(ref, "Who are the site's visitors?", ["goal"], "the goal names no one")           # Identity's own question on the standard
    open_now = J.status(ref)["open_question"]["id"]
    sent = len(_line_requests(R, ref))
    _doubts(R, ref)
    W.run_until_idle(ref, limit=300)
    assert _plan_asks(W, ref) == [] and len(_line_requests(R, ref)) == sent
    assert J.status(ref)["open_question"]["id"] == open_now, "the question the owner is on is the one that stays"


def test_i5_outside_a_cycle_a_doubt_asks_nothing_and_adaptation_goes_on(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2, BAKERY)
    monkeypatch.setenv("J2_FLOW_V1", "0")
    before = len(_line_requests(R, ref))
    _doubts(R, ref)
    W.run_until_idle(ref, limit=300)
    assert _plan_asks(W, ref) == [] and len(_line_requests(R, ref)) == before + 1 and _line_requests(R, ref)[-1]["payload"]["go_on"] is True


def test_i5_the_fallback_never_reaches_outside_and_is_in_plain_words(j2):
    W, R, J, _, _ = j2
    ref = _born(j2, BAKERY)
    _doubts(R, ref, fallback="the form sends the order by email to the shop")
    W.run_until_idle(ref, limit=300)
    ask = _plan_asks(W, ref)[0]
    import layers.identity.v1 as v1
    assert "Unless you say, %s. Answer" % v1.fallback_default(W.dept(ref)) in ask["text"] and "email to the shop?" in ask["text"]
    # a doubt a model wrote in the bargain's words is put right, or said in the plainest words that still ask it
    ref = _born(j2, BAKERY, "Plain Co")
    _doubts(R, ref, doubt="Should Priority grant the cake counter its own page?", fallback="the cake counter shares the home page")
    W.run_until_idle(ref, limit=300)
    ask = _plan_asks(W, ref)[0]
    assert not re.search(r"\b(?:grant|counter)", ask["text"], re.I) and v1.SOMETHING in ask["text"] and "Unless you say, %s." % v1.fallback_default(W.dept(ref)) in ask["text"]
    assert "just do it" in ask["text"] and R.plain_faults(ask["text"], R._owners_words(ref, {})) == []


#: what a model may write that the owner may not read (J2B-8: no number, no part of the app): the confidence as a figure and as
#: a word, a part by name, the app's words for its insides
SHOWS_THE_INSIDE = [
    ("Adaptation is unsure, at confidence 0.45, whether the Check engine should read the order form; Root may review it.",
     "Coordination runs Check after the Site engine"),
    ("I am only 45% sure the shop wants 3 pages, and the charter says Priority must refuse orders over the engine limit (confidence 0.45)",
     "Priority holds the envelope at 70 percent"),
    ("Should the page say who the baker is? My confidence is low.", "the Check engine goes on without it")]
#: what the owner may not read, as the oracle of these tests says it (apart from V1.INSIDE, which is what is under test). The
#: owner's page says workflow in its headers and on its map (j2ui_assets/j2_ui.html), so the word is not one of them.
INSIDE_WORDS = re.compile(r"confiden|\b0?\.\d+\b|%|per ?cent|Adaptation|Priority|Coordination|Audit|engine|envelope|charter|refus", re.I)


def _the_card_the_owner_reads(R, ref, ask):
    """Every word of a doubt's question the owner reads: the card's text and why, and the line that names it in the chat."""
    said = [p["payload"].get("done") for p in R.board(ref) if p["src"] == "Identity" and "Owner" in p["dst"] and p["payload"].get("card") == ask["id"]]
    return [ask["text"], ask["why"]] + said


@pytest.mark.parametrize("doubt,fallback", SHOWS_THE_INSIDE)
def test_i5_a_doubt_or_fallback_that_shows_the_confidence_or_a_part_of_the_app_is_put_in_the_stock_words(j2, doubt, fallback):
    W, R, J, _, _ = j2
    ref = _born(j2, BAKERY)
    _doubts(R, ref, doubt=doubt, fallback=fallback)
    W.run_until_idle(ref, limit=300)
    ask = _plan_asks(W, ref)[0]
    name = W.dept(ref)["name"]
    assert ask["text"] == 'Before I set up the work for %s: %s Unless you say, %s. Answer in your own words, or say "just do it".' % (name, V1.SOMETHING, V1.fallback_default(W.dept(ref)))
    seen = _the_card_the_owner_reads(R, ref, ask)
    assert len(seen) == 3 and all(INSIDE_WORDS.search(s.replace(name, "")) is None for s in seen), seen
    assert V1.inside(doubt) and V1.inside(fallback), "the guard sees what the test says is in them"
    # Adaptation's own words stay Adaptation's: the ask holds the doubt as it was posted, and what the owner was shown
    assert ask["doubt"]["doubt"] == V1._said(doubt, 600) and ask["doubt"]["shown"] == V1.SOMETHING and ask["doubt"]["fallback"] == V1.fallback_default(W.dept(ref))
    assert S.validate_record("identity", "ask", ask) == []
    # the answer is filed in the Brief under the question as the owner read it, and goes to Adaptation with the doubt as it was
    _owner_says(j2, ref, "answer box", ANSWER)
    brief = " ".join(W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"]).values())
    assert "To Identity's question (%s): %s" % (V1.SOMETHING.rstrip("."), ANSWER) in brief and INSIDE_WORDS.search(brief.split("To Identity's question")[1]) is None
    assert _line_requests(R, ref)[-1]["payload"]["doubt"] == V1._said(doubt, 600)


def test_i5_the_doubt_that_is_left_open_is_told_and_blocked_in_the_stock_words_too(j2):
    W, R, J, _, _ = j2
    doubt, fallback = SHOWS_THE_INSIDE[1]
    ref = _doubting(j2)
    for said in ("A first answer", "A second answer"):
        _owner_says(j2, ref, "chat", said)
        _doubts(R, ref, doubt=doubt, fallback=fallback)
        W.run_until_idle(ref, limit=300)
    told = [s for s in _said_by_identity(R, ref) if "the plan goes on as it stands" in s]
    assert len(told) == 1 and V1.SOMETHING in told[0] and "Unless you say otherwise, %s." % V1.fallback_default(W.dept(ref)) in told[0]
    assert INSIDE_WORDS.search(told[0].replace("Priority and Root check it before anything runs.", "")) is None, told[0]
    went_on = [q for q in _line_requests(R, ref) if q["payload"].get("go_on")]
    assert went_on[-1]["payload"]["doubt"] == doubt[:600] and went_on[-1]["payload"]["fallback"] == V1.fallback_default(W.dept(ref)), "Adaptation is sent the doubt as it was"
    _doubts(R, ref, doubt=doubt, fallback=fallback)                                    # it comes back: a blocked plan
    W.run_until_idle(ref, limit=300)
    card = next(a for a in W.asks(ref) if a["kind"] == "blocked" and a["status"] == "pending")
    assert V1.SOMETHING in card["text"] and card["why"] == V1.SOMETHING
    assert all(INSIDE_WORDS.search(s) is None for s in (card["text"].replace("Priority and Root check it before anything runs.", ""), card["why"]))


def test_i5_figures_and_words_of_the_owners_own_work_are_not_taken_for_the_inside(j2):
    W, R, J, _, _ = j2
    doubt, fallback = "Should the cake page show 3 sizes, and be easy to find on a search engine?", "the page shows one size"
    ref = _born(j2, BAKERY)
    _doubts(R, ref, doubt=doubt, fallback=fallback)
    W.run_until_idle(ref, limit=300)
    ask = _plan_asks(W, ref)[0]
    assert doubt in ask["text"] and "Unless you say, %s." % fallback in ask["text"] and ask["doubt"]["shown"] == doubt
    assert V1.inside("Class 8.5, v2.1, 12 pm, 3 pages, a search engine") == [] and V1.inside("at .45") == [".45"]


#: the confidence in the shapes a verifier found past the guard (2026-10-27): a decimal that ends a sentence, a percentage in
#: words, and odds said as a ratio
ENDS_ON_A_FIGURE = [
    "I give this 0.6.",
    "Which pages does the shop want? 0.45.",
    "Which pages does the shop want? I put it at 0.45.",
    "Is it 0.45? Is it (0.45)! Is it 0.45...",
    "I am about sixty percent sure",
    "Call it sixty per cent.",
    "It is a 1 in 3 chance.",
    "Maybe a one in three chance the shop wants it.",
    "I put it at 2 out of 5.",
    "Call it zero point four five."]
#: a figure or a word of the owner's own work, which is theirs: a time, a class, a version, a layout, a count of what they sell
THE_OWNERS_OWN = [
    "Open from 9.30.", "Class 8.5.", "It needs v2.1.3.", "Version 0.45.3 of the font.", "Show 3 in 4 columns.",
    "Do 2 out of 3 customers want it on a phone?", "The workflow for the cake page lists the sizes.", "A search engine finds it.",
    "Show 12 pages in 3 rows."]


@pytest.mark.parametrize("text", ENDS_ON_A_FIGURE)
def test_i5_inside_finds_the_confidence_when_it_ends_a_sentence_or_is_spelled_out(text):
    assert V1.inside(text), text


@pytest.mark.parametrize("text", THE_OWNERS_OWN)
def test_i5_inside_leaves_the_owners_own_figures_and_the_word_workflow_alone(text):
    assert V1.inside(text) == [], text


def test_i5_inside_names_the_figure_it_found():
    assert V1.inside("I give this 0.6.") == ["0.6"] and V1.inside("(0.45)") == ["0.45"] and V1.inside("about 45 percent") == ["45 percent"]
    assert V1.inside("Call it sixty per cent.") == ["per cent"] and V1.inside("a 1 in 3 chance") == ["1 in 3"]


@pytest.mark.parametrize("doubt", ["Which pages does the shop want? " + said for said in (
    "I put it at 0.45.", "0.45.", "I am about sixty percent sure.", "Call it sixty per cent.", "It is a 1 in 3 chance.", "I put it at one in three.")])
def test_i5_a_doubt_that_ends_on_a_figure_or_spells_it_out_is_put_in_the_stock_words(j2, doubt):
    """Found by a verifier: 'Which pages does the shop want? I put it at 0.45.' reached the card and the chat line as written."""
    W, R, J, _, _ = j2
    ref = _born(j2, BAKERY)
    _doubts(R, ref, doubt=doubt, fallback="the page shows one size")
    W.run_until_idle(ref, limit=300)
    ask = _plan_asks(W, ref)[0]
    name = W.dept(ref)["name"]
    assert ask["text"] == 'Before I set up the work for %s: %s Unless you say, the page shows one size. Answer in your own words, or say "just do it".' % (name, V1.SOMETHING)
    seen = _the_card_the_owner_reads(R, ref, ask)
    assert len(seen) == 3 and all(not re.search(r"\d|per ?cent|sixty|in three|zero point", s.replace(name, ""), re.I) for s in seen), seen
    assert ask["doubt"]["doubt"] == V1._said(doubt, 600) and ask["doubt"]["shown"] == V1.SOMETHING and S.validate_record("identity", "ask", ask) == []


def test_i5_a_doubt_that_names_a_workflow_keeps_its_words(j2):
    """The owner's page says workflow where it lists the work and on its map, so a doubt that names one is asked as it is:
    the owner is asked what was doubted, not that something was (found by a verifier)."""
    W, R, J, _, _ = j2
    doubt, fallback = "Should the workflow that builds the cake page also list the sizes?", "the workflow lists one size"
    ref = _born(j2, BAKERY)
    _doubts(R, ref, doubt=doubt, fallback=fallback)
    W.run_until_idle(ref, limit=300)
    ask = _plan_asks(W, ref)[0]
    assert ask["text"] == 'Before I set up the work for %s: %s Unless you say, %s. Answer in your own words, or say "just do it".' % (W.dept(ref)["name"], doubt, fallback)
    assert ask["doubt"]["shown"] == doubt and ask["doubt"]["fallback"] == fallback and V1.SOMETHING not in ask["text"]
    assert S.validate_record("identity", "ask", ask) == []


def test_i5_the_default_fallback_says_the_department_unless_it_is_a_website(j2):
    """A website is the owner's site; any other kind of department is the department (engine_runtime.identity_file says it so):
    the question, the go-on line and 'just do it' never say a site for a laboratory."""
    W, R, J, _, _ = j2
    ref = _born(j2, ORGANIC, "Lab Co")
    d = W.dept(ref)
    assert d["kind"] != "website"
    stock = "I go ahead with the plan as it stands, and nothing in it reaches outside the department"
    assert V1.fallback_default(d) == stock and V1.fallback_default({"kind": "website"}) == V1.FALLBACK == stock.replace("department", "site")
    site = _born(j2, "a website for my bakery in Pune", "Bakery Web Co")
    assert W.dept(site)["kind"] == "website"
    _doubts(R, site, doubt="Which cakes need a note?", fallback="")
    W.run_until_idle(site, limit=300)
    assert _plan_asks(W, site)[0]["text"].endswith('Unless you say, %s. Answer in your own words, or say "just do it".' % V1.FALLBACK), "a website is a site"
    _doubts(R, ref, doubt="Which chemicals need a safety note?", fallback="")
    W.run_until_idle(ref, limit=300)
    ask = _plan_asks(W, ref)[0]
    assert ask["text"] == 'Before I set up the work for %s: Which chemicals need a safety note? Unless you say, %s. Answer in your own words, or say "just do it".' % (d["name"], stock)
    assert ask["doubt"]["fallback"] == stock and S.validate_record("identity", "ask", ask) == []
    assert all(not re.search(r"\bsite\b", s, re.I) for s in _the_card_the_owner_reads(R, ref, ask))
    # 'just do it' takes it, and says it; so does an unplain fallback the doubt came with
    _owner_says(j2, ref, "chat", "just do it")
    assert any("Just doing it: %s." % stock in s for s in _said_by_identity(R, ref))
    assert _line_requests(R, ref)[-1]["payload"]["answer"] == "going with this: " + stock
    # past the bound, the go-on line says it too
    _owner_says(j2, ref, "chat", "Only the acids")
    _doubts(R, ref, doubt="Which shelf holds the acids?", fallback="Coordination moves them to another engine")
    W.run_until_idle(ref, limit=300)
    _owner_says(j2, ref, "chat", "The top shelf")
    _doubts(R, ref, doubt="Who signs the inventory?", fallback="")
    W.run_until_idle(ref, limit=300)
    told = [s for s in _said_by_identity(R, ref) if "the plan goes on as it stands" in s]
    assert len(told) == 1 and "Unless you say otherwise, %s." % stock in told[0] and not re.search(r"\bsite\b", told[0], re.I), told
    assert [q["payload"]["fallback"] for q in _line_requests(R, ref) if q["payload"].get("go_on")] == [stock]


def test_i5_words_after_the_doubt_is_answered_are_no_answer_to_it(j2):
    W, R, J, _, _ = j2
    ref = _doubting(j2)
    _owner_says(j2, ref, "chat", ANSWER)
    asked = len(_plan_asks(W, ref))
    sent = len(_line_requests(R, ref))
    W.owner_ask(ref, "Make the heading on the home page bigger")
    W.run_until_idle(ref, limit=300)
    assert len(_plan_asks(W, ref)) == asked
    assert not [q for q in _line_requests(R, ref)[sent:] if q["payload"].get("answer")]


# ---- I6: the contract, whole ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("case", C.cases(), ids=lambda c: "case %d" % c[0])
def test_i6_the_contract_passes_for_identity_v1_with_no_part_on_the_fallback(case, ctx):
    _, what, fn = case
    assert fn(V1, ctx) == [], what
    assert C.on_the_md_fallback(V1) == []


# ---- J1: the conflict ask carries the ways out (M5.4) ----------------------------------------------------------------------
ENGINES = [{"name": "Plan", "reads": "Brief", "writes": "Site plan"}, {"name": "Write", "reads": "Site plan", "writes": "Pages"}]


def _ways(items):
    """Priority's three ways out at a limit: raise it, leave the last item out, stop (act.conflict options)."""
    last = items[-1]["id"]
    return [{"id": "raise", "label": "Raise the limit", "cost": "adds budget, up to twice where it started", "kind": "raise",
             "params": {"what": "ceiling", "rounds": 12}},
            {"id": "leave:" + last, "label": "Leave %s out" % last, "cost": "%s is dropped from done-when; nothing more is spent" % last, "kind": "leave"},
            {"id": "stop", "label": "Stop here", "cost": "the department stops where it is; you can start it again later", "kind": "stop"}]


def _conflict(R, ref, engines, options, why="Priority said no to the plan: there is no room", **more):
    """A stub Adaptation (or Coordination): it tells Identity a bargain did not close, with the ways out it knows."""
    return R.post(ref, "Adaptation", "Identity", "inform",
                  dict({"word": "conflict", "engines": engines, "source": "library", "words": "w", "why": why, "bound": None, "for": "x-j1",
                        "options": options}, **more))


def _cards(W, ref, kinds=("blocked", "conflict")):
    return [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] in kinds]


def test_j1_a_conflict_with_raise_leave_and_stop_reaches_the_owner_as_one_ask_with_those_options(j2):
    W, R, J, _, _ = j2
    ref = _born(j2)
    ways = _ways(W.items_of(W.dept(ref)))
    assert S.validate("act.conflict", {"word": "conflict", "options": ways}) == []
    _conflict(R, ref, ENGINES, ways)
    W.run_until_idle(ref, limit=300)
    cards = _cards(W, ref)
    assert len(cards) == 1 and cards[0]["kind"] == "blocked", "one ask, and not the stamp that only runs or drops"
    ask = cards[0]
    assert [o["id"] for o in ask["options"]] == [w["id"] for w in ways] and [o["kind"] for o in ask["options"]] == ["raise", "leave", "stop"]
    assert [o["params"] for o in ask["options"] if "params" in o] == [{"what": "ceiling", "rounds": 12}]
    assert all(S.validate("option", o) == [] for o in ask["options"]) and S.validate_record("identity", "ask", ask) == []
    assert ask["for"] == "x-j1" and J.status(ref)["state"] == "blocked"
    seen = _the_card_the_owner_reads(R, ref, ask)
    assert not [w for s in seen for w in re.findall(r"\b(?:grant|counter|refuse|charter)\w*", s, re.I)], seen
    # said again, the same conflict is the same card: one ask however often it is heard
    _conflict(R, ref, ENGINES, ways, **{"for": "x-j1"})
    W.run_until_idle(ref, limit=300)
    assert [a["id"] for a in _cards(W, ref)] == [ask["id"]]


def test_j1_a_conflict_with_no_ways_out_is_put_to_the_owner_as_it_was(j2):
    W, R, J, _, _ = j2
    ref = _born(j2)
    R.post(ref, "Adaptation", "Identity", "inform", {"word": "conflict", "engines": ENGINES, "source": "library", "words": "w", "why": "no room", "for": "x-j1"})
    W.run_until_idle(ref, limit=300)
    cards = _cards(W, ref)
    assert [a["kind"] for a in cards] == ["conflict"] and "options" not in cards[0]


def test_j1_a_conflict_that_cannot_make_a_plan_carries_its_ways_out_on_the_blocked_card(j2):
    W, R, J, _, _ = j2
    ref = _born(j2)
    ways = [{"id": "root_setup", "label": "Set it up again, done its own way", "cost": "Root sets this up again for your stamp", "kind": "root_setup",
             "params": {"words": "A bakery site, done our way"}}] + _ways(W.items_of(W.dept(ref)))[1:]
    _conflict(R, ref, [], ways, why="Check cannot serve D1: nothing it makes shows it")
    W.run_until_idle(ref, limit=300)
    ask = _cards(W, ref)[0]
    assert ask["kind"] == "blocked" and [o["id"] for o in ask["options"]][0] == "root_setup" and len(ask["options"]) == 3
    assert ask["options"][0]["params"] == {"words": "A bakery site, done our way"}


def test_j1_a_conflict_about_a_round_is_a_card_about_the_next_round_and_never_about_a_plan(j2):
    """A round's limit put to the owner under the title of a plan that cannot be made (found by a verifier 2026-10-27): the plan is
    registered and runs, and what needs the owner's word is the next round. The card says so, and says whose it is: Priority's when
    a round was proposed and did not go on, Adaptation's when it had no new way to put the work right."""
    W, R, J, _, _ = j2
    ref = _born(j2)
    ways = _ways(W.items_of(W.dept(ref)))
    assert S.validate("act.conflict", {"word": "conflict", "round": 2, "correction": "Put the phone line on the doctors page"}) == []
    assert S.validate("act.conflict", {"word": "conflict", "round": 0}) and S.validate("act.conflict", {"word": "conflict", "round": "two"})
    _conflict(R, ref, [], ways, why="Priority said no to round 2: no room in the ceiling", round=2, correction="Put the phone line on the doctors page",
              **{"for": "x-r2"})
    W.run_until_idle(ref, limit=300)
    [ask] = _cards(W, ref)
    assert (ask["title"], ask["who"]) == ("The next round needs your word.", "Priority, pricing the round")
    assert ask["text"] == "Priority said no to round 2: no room in the ceiling. Say how to put it right, or choose a way forward on this card."
    assert [o["id"] for o in ask["options"]] == [w["id"] for w in ways] and J.status(ref)["state"] == "blocked"
    _conflict(R, ref, [], ways, why="Adaptation has no new way to put D2 right: its only idea is the approach that already failed in round 1",
              round=2, **{"for": "x-r2b"})
    W.run_until_idle(ref, limit=300)
    [again] = _cards(W, ref)
    assert (again["title"], again["who"]) == ("The next round needs your word.", "Adaptation, correcting the work")
    for card in (ask, again):
        assert not re.search(r"\bplan\b|Say what to correct|\b(?:grant|counter|refus)\w*", " ".join((card["title"], card["who"], card["text"])), re.I), card
    # a conflict that is about no round keeps the words of a plan that cannot be made
    _conflict(R, ref, [], ways, why="Check cannot serve D1: nothing it makes shows it", **{"for": "x-np"})
    W.run_until_idle(ref, limit=300)
    [plan] = _cards(W, ref)
    assert (plan["title"], plan["who"]) == ("No plan can be made as it stands.", "Adaptation, shaping the plan")
    assert V1.round_words({"word": "conflict", "round": True}) is None and V1.round_words({"word": "conflict"}) is None and V1.round_words(None) is None


def test_j1_the_ways_out_are_checked_as_the_interface_types_them_and_are_at_most_three():
    good = [{"id": "raise", "label": "Raise it", "cost": "more", "kind": "raise", "params": {"what": "ceiling"}},
            {"id": "leave:D2", "label": "Leave D2 out", "cost": "less"}, {"id": "stop", "label": "Stop", "cost": "nothing"}]
    bad = [{"id": "Not A Way", "label": "x", "cost": "y"}, {"id": "teleport", "label": "Teleport", "cost": "z"},
           {"id": "raise", "label": "", "cost": "y"}, {"id": "words", "cost": "y"}, "not an option", None, {"id": "raise", "label": "r", "cost": "c", "params": "no"}]
    got = V1.conflict_options({"options": bad[:2] + good + bad[2:]})
    assert [o["id"] for o in got] == ["raise", "leave:D2", "stop"] and all(S.validate("option", o) == [] for o in got)
    assert [o["kind"] for o in got] == ["raise", "leave", "stop"], "the kind is the part of the id before the colon"
    assert len(V1.conflict_options({"options": good * 2})) == S.OPTIONS_MAX == 3
    assert V1.conflict_options({}) == V1.conflict_options({"options": None}) == V1.conflict_options(None) == []
    assert V1.conflict_options({"options": bad}) == []


def test_j1_a_way_out_is_applied_by_the_layer_the_interface_names(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2)
    ways = _ways(W.items_of(W.dept(ref)))
    _conflict(R, ref, ENGINES, ways)
    W.run_until_idle(ref, limit=300)
    ask = _cards(W, ref)[0]
    assert S.OPTION_KINDS["raise"]["layer"] == "priority"
    seen = []
    prio = layers.load("priority/v1")
    # choose_option has Priority apply a raise on the click (apply_choice, M5.4); stood in for here, so that what is seen is
    # Identity's own step reaching the layer the interface names (the pair together is the next test)
    monkeypatch.setattr(prio, "apply_choice", lambda r, a, o: {}, raising=False)
    monkeypatch.setattr(prio, "apply_option", lambda r, a, o: seen.append((r, a["id"], o["id"], o.get("params"))) or {"raised": True}, raising=False)
    W.choose_option(ref, ask["id"], "raise")
    W.run_until_idle(ref, limit=300)
    assert seen == [(ref, ask["id"], "raise", {"what": "ceiling", "rounds": 12})], "Priority applied it, with the option as the card held it"
    done = next(a for a in W.asks(ref) if a["id"] == ask["id"])
    assert done["status"] == "chosen" and done["chosen"]["id"] == "raise", "the card is answered, once"


def test_j1_a_way_out_no_layer_can_apply_leaves_the_card_waiting_and_says_why(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2)
    _conflict(R, ref, ENGINES, _ways(W.items_of(W.dept(ref))))
    W.run_until_idle(ref, limit=300)
    ask = _cards(W, ref)[0]
    prio = layers.load("priority/v1")
    monkeypatch.setattr(prio, "apply_choice", lambda r, a, o: {}, raising=False)     # Identity's step is what is tried here, not the click's
    monkeypatch.delattr(prio, "apply_option", raising=False)
    W.choose_option(ref, ask["id"], "raise")
    W.run_until_idle(ref, limit=300)
    again = _cards(W, ref)
    assert [a["id"] for a in again] == [ask["id"]] and again[0]["chosen"] is None and again[0]["thread"] != ask["thread"], "the same card, waiting again"
    assert any("Priority cannot do that yet. Nothing changed; choose again on the card." in s for s in _said_by_identity(R, ref))
    # a layer that refuses it (past its cap, say) leaves the card waiting too, and says what it said
    def refuse(r, a, o):
        raise ValueError("That is more than twice where it started")
    monkeypatch.setattr(layers.load("priority/v1"), "apply_option", refuse, raising=False)
    W.choose_option(ref, ask["id"], "raise")
    W.run_until_idle(ref, limit=300)
    assert _cards(W, ref)[0]["id"] == ask["id"] and any("That is more than twice where it started. Nothing changed" in s for s in _said_by_identity(R, ref))


def test_j1_a_raise_chosen_on_the_card_is_made_once_and_identitys_step_after_it_changes_nothing(j2):
    """Priority applies a raise on the click (apply_choice) and Identity's stamp step applies it again through apply_option: the
    second finds the limit already as high (a raise already made is not made again), so the ceiling is raised once."""
    W, R, J, _, _ = j2
    ref = _born(j2)
    _conflict(R, ref, ENGINES, _ways(W.items_of(W.dept(ref))))
    W.run_until_idle(ref, limit=300)
    ask = _cards(W, ref)[0]
    prio = layers.load("priority/v1")
    before = (W.dept(ref).get("ceiling") or {}).get("raised") or []
    W.choose_option(ref, ask["id"], "raise")
    W.run_until_idle(ref, limit=300)
    ceiling = W.dept(ref)["ceiling"]
    assert ceiling["rounds"] == 12 and len(ceiling["raised"]) == len(before) + 1, "raised once, though two paths applied it"
    assert prio.apply_option(ref, ask, {"id": "raise", "kind": "raise", "params": {"what": "ceiling", "rounds": 12}})["raised"] is False
    done = next(a for a in W.asks(ref) if a["id"] == ask["id"])
    assert done["status"] == "chosen" and done["chosen"]["id"] == "raise"


def test_j1_set_it_up_again_is_applied_by_root_as_one_request_for_the_owners_stamp(j2):
    W, R, J, _, _ = j2
    ref = _born(j2)
    root = W.dept(ref)["root"]
    ways = [{"id": "root_setup", "label": "Set it up again, done its own way", "cost": "Root sets this up again for your stamp", "kind": "root_setup",
             "params": {"words": "A bakery site"}}] + _ways(W.items_of(W.dept(ref)))[1:]
    _conflict(R, ref, [], ways, why="Check cannot serve D1: nothing it makes shows it")
    W.run_until_idle(ref, limit=300)
    ask = _cards(W, ref)[0]
    before = len([p for p in R.board(root) if p["src"] == "Owner"])
    W.choose_option(ref, ask["id"], "root_setup")
    W.run_until_idle(ref, limit=300)
    asked = [p for p in R.board(root)[before:] if p["src"] == "Owner" and "done its own way" in str(p["payload"].get("words"))]
    assert len(asked) == 1 and asked[0]["payload"]["words"] == "A bakery site, done its own way"
    assert next(a for a in W.asks(ref) if a["id"] == ask["id"])["status"] == "chosen"


def _two_items(W, ref):
    """The default website's done-when is one item; a second, read by an AI, so one can be left out."""
    W.put_done_items(ref, W.items_of(W.dept(ref)) + [{"text": "Shoppers can order a cake on WhatsApp", "how": "model", "level": "outcome"}])
    return W.items_of(W.dept(ref))


def test_j1_leave_and_stop_are_still_applied_by_identity(j2):
    W, R, J, _, _ = j2
    ref = _born(j2)
    items = _two_items(W, ref)
    assert [i["id"] for i in items] == ["D1", "D2"]
    _conflict(R, ref, ENGINES, _ways(items))
    W.run_until_idle(ref, limit=300)
    ask = _cards(W, ref)[0]
    W.choose_option(ref, ask["id"], "leave:" + items[-1]["id"])
    W.run_until_idle(ref, limit=300)
    assert [i["id"] for i in W.items_of(W.dept(ref))] == [i["id"] for i in items[:-1]], "the item is out of done-when"


# ---- J2: Hear a reading (M8.4) ---------------------------------------------------------------------------------------------
#: the severity Audit gives a verdict (engine_runtime.ITEM_SEVERITY)
SEVERITY = {"met": "low", "to_confirm": "medium", "not_met": "high"}


def _actions(J, ref):
    return [e["action"] for e in J.events(ref)]


def _reached(W, J, ref):
    return [e for e in J.events(ref) if e["action"] == "goal.reached"]


def _a_running_department(j2, org="Acme Learning", words=WEBSITE, items=2):
    """A website with its plan at work and its first version live, and `items` done-when items: what Audit reads."""
    W, R, J, _, _ = j2
    ref = _born(j2, words, org)
    _stamp_the_pending(W, ref, ("publish",))
    if items > 1:
        _two_items(W, ref)
    assert W.latest(ref, "Live site") and J.status(ref)["step"] >= 6
    return ref


def _file_reading(j2, ref, verdicts, findings=(), read=True, v=None, cycle="current", artifact=None, method="model"):
    """What Audit files of one version, as the audit step files it (readings.jsonl, checked as the interface types it)."""
    import hashlib
    W, R, J, _, _ = j2
    art = artifact or S.deliverable(W.dept(ref))
    v = v or W.latest(ref, art)["v"]
    n = len(W.rows(ref, "readings.jsonl"))
    text = {i["id"]: i["text"] for i in W.items_of(W.dept(ref))}
    items = [{"id": i, "subject": text.get(i, "an item"), "claim": "what is so of it", "evidence": "what shows it", "method": method,
              "verdict": verdict, "severity": SEVERITY[verdict]} for i, verdict in verdicts.items()] if read else []
    row = {"schema_version": 1, "id": "r-" + hashlib.sha1(("%s%s%s" % (ref, v, n)).encode()).hexdigest()[:8], "v": v, "artifact": art,
           "cycle_id": J.status(ref)["cycle_id"] if cycle == "current" else cycle, "round": None, "read": read,
           "why_not_read": None if read else "no model was there to read it", "items": items,
           "findings": [dict({"id": "F%d" % (k + 1), "severity": "high", "claim": "A reader could be misled", "where": "Home", "item": None,
                              "went_to": "Identity", "at": W.now()}, **f) for k, f in enumerate(findings)], "at": W.now()}
    return W.append_row(ref, "readings.jsonl", row)


def _tell_reading(j2, ref, row):
    """Audit tells Identity the reading it filed (inform/reading), and the department runs until it is idle."""
    W, R, J, _, _ = j2
    post = R.audit_tell(ref, row)
    assert post is not None, "Identity's recipe hears a reading, so Audit posts it"
    W.run_until_idle(ref, limit=300)
    return post


def _hear(j2, ref, verdicts, **kw):
    return _tell_reading(j2, ref, _file_reading(j2, ref, verdicts, **kw))


def sm1_faults(W, J, ref):
    """SM-1: every goal.reached of the ledger cites a reading of the version it names, read, with every done-when item met."""
    rows = {r["id"]: r for r in W.rows(ref, "readings.jsonl")}
    bad = []
    for e in J.events(ref):
        if e["action"] != "goal.reached":
            continue
        cited = next((x for x in e["evidence_refs"] if isinstance(x, dict) and x.get("reading")), None)
        row = rows.get((cited or {}).get("reading"))
        met = {i["id"] for i in (row or {}).get("items") or [] if i["verdict"] == "met"}
        if not (row and row["read"] and row["v"] == cited["version"] and row["artifact"] == cited["artifact"]
                and {i["id"] for i in W.items_of(W.dept(ref))} <= met):
            bad.append(e["event_id"])
    return bad


def test_j2_identitys_recipe_hears_a_reading_and_the_interface_says_so(home):
    import engine_runtime as R
    row = next(r for r in S.hears("identity") if (r["act"], r["word"]) == ("inform", "reading"))
    assert (row["from"], row["via"], row["payload"], row["handler"]) == (("Audit",), "board", "act.reading", "Hear a reading")
    handler = next(h for h in layers.recipes()["Identity"]["on"] if h["name"] == "Hear a reading")
    assert handler["when"] == {"msg_type": "inform", "word": "reading"}
    assert [(s["id"], s["code"], s["born"], s["check"]) for s in handler["steps"]] == \
        [("identity.hear_reading", "hear", "C2", "facts_are_closed"), ("identity.done", "identity_done", "C2", "done_is_read"),
         ("identity.weigh_reading", "identity_weigh_reading", "C2", "said_what_it_did")]
    assert "done_is_read" in S.CHECKS["identity"] and "done_is_read" in S.CONTRACT_SAMPLES and "done_is_read" in V1.CHECK
    assert R.validate(R.defs()) == []
    assert R._handler(R.engine_def("Identity"), {"msg_type": "inform", "payload": {"word": "reading"}}) is not None
    assert any(r["act"] == "inform" and "reading" in r["words"] and r["to"] == ("Identity",) for r in S.SENDS["Audit"])


def test_j2_no_findings_but_d2_not_met_is_not_done(j2):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _hear(j2, ref, {"D1": "met", "D2": "not_met"}, findings=[])
    assert _reached(W, J, ref) == [] and J.status(ref)["goal_reached"] is False and J.status(ref)["state"] != "done"
    steps = [r for r in R.step_rows(ref) if r["step"] == "identity.done"]
    assert steps and steps[-1]["status"] == "ok" and "D2 not met" in steps[-1]["out_hash"] or "D2 not met" in json.dumps(steps[-1]), steps[-1]


def test_j2_every_item_met_is_goal_reached_citing_the_reading_id(j2):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    row = _file_reading(j2, ref, {"D1": "met", "D2": "met"})
    _tell_reading(j2, ref, row)
    (reached,) = _reached(W, J, ref)
    assert reached["actor"] == "Identity" and reached["recipient"] == "User" and reached["step"] == 8
    assert reached["evidence_refs"] == [{"artifact": "Live site", "version": row["v"], "reading": row["id"]}] and reached["payload"]["reading"] == row["id"]
    st = J.status(ref)
    assert (st["state"], st["step"], st["goal_reached"]) == ("done", 8, True)
    acts = _actions(J, ref)
    assert acts[-2:] == ["audit.finding_filed", "goal.reached"], "the clean reading stands before the goal it led to"
    said = [s for s in _said_by_identity(R, ref) if s.startswith("The goal is reached:")]
    assert len(said) == 1 and "Audit read Live site v%d and found nothing to put right." % row["v"] in said[0]
    assert sm1_faults(W, J, ref) == []


def test_j2_an_item_to_confirm_is_not_done(j2):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _hear(j2, ref, {"D1": "met", "D2": "to_confirm"})
    assert _reached(W, J, ref) == [] and J.status(ref)["state"] != "done"
    # a fact still to be confirmed on the record blocks done too, whatever the reader said of the item
    d = W.dept(ref)
    items = W.items_of(d)
    items[1]["confirm"] = "nobody gave the price list"
    W.put_done_items(ref, items)
    _hear(j2, ref, {"D1": "met", "D2": "met"})
    assert _reached(W, J, ref) == [] and J.status(ref)["state"] != "done"


def test_j2_a_high_finding_open_is_not_done(j2):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _hear(j2, ref, {"D1": "met", "D2": "met"}, findings=[{"severity": "high", "claim": "The fees are invented"}])
    assert _reached(W, J, ref) == [] and J.status(ref)["state"] != "done"
    # a finding that is not high does not block it, and the owner is told it was noted
    _hear(j2, ref, {"D1": "met", "D2": "met"}, findings=[{"severity": "low", "claim": "A heading could be shorter"}])
    assert len(_reached(W, J, ref)) == 1
    assert any("noted something that does not block" in s for s in _said_by_identity(R, ref))


def test_j2_a_version_nobody_read_and_an_item_nobody_read_are_not_done(j2):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _hear(j2, ref, {}, read=False, findings=[{"severity": "low", "claim": "x"}])
    _hear(j2, ref, {"D1": "met"})                                                  # D2 has no reading at all
    assert _reached(W, J, ref) == [] and J.status(ref)["state"] != "done"


def test_j2_a_reading_of_an_older_version_or_an_earlier_cycle_is_not_done(j2):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _hear(j2, ref, {"D1": "met", "D2": "met"}, cycle="cycle-before")
    assert _reached(W, J, ref) == [], "a reading of an earlier cycle"
    old = _file_reading(j2, ref, {"D1": "met", "D2": "met"})
    W.add_version(ref, "Live site", {"index.html": "<p>newer</p>"}, [], "r-x", {"ok": True, "notes": []})
    _tell_reading(j2, ref, old)
    assert _reached(W, J, ref) == [] and J.status(ref)["state"] != "done", "a newer version is out: its reading decides"


def test_j2_the_goal_is_reached_once_and_said_once_however_often_the_reading_is_heard(j2):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    row = _file_reading(j2, ref, {"D1": "met", "D2": "met"})
    _tell_reading(j2, ref, row)
    _tell_reading(j2, ref, row)
    assert len(_reached(W, J, ref)) == 1
    assert len([s for s in _said_by_identity(R, ref) if s.startswith("The goal is reached:")]) == 1


def test_j2_the_covering_refuses_a_claim_the_reading_does_not_bear(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    d = W.dept(ref)
    full = {"done": True, "reading": "r-1a2b3c4d", "read": True, "met": ["D1", "D2"], "not_met": [], "to_confirm": [], "unread": [], "high": False}
    assert V1.c_done_is_read({"dept": d}, None, None, full)["ok"] is True, "a claim that holds together, off the record"
    for lie in (dict(full, met=["D1"]), dict(full, not_met=["D2"]), dict(full, to_confirm=["D2"]), dict(full, high=True), dict(full, read=False),
                dict(full, reading=None), dict(full, unread=["D2"]), dict(full, done="yes")):
        assert V1.c_done_is_read({"dept": d}, None, None, lie)["ok"] is False, lie
    # a claim of done the reading does not bear is not written, whatever claims it
    _file_reading(j2, ref, {"D1": "met", "D2": "not_met"})
    true, calls = V1.done_claim, []

    def lying(dept, row):                     # the first reading of the reading lies; the covering reads the record again
        calls.append(1)
        return dict(full, artifact="Live site", v=row["v"], reading=row["id"], why="every item is met") if len(calls) == 1 else true(dept, row)
    monkeypatch.setattr(V1, "done_claim", lying)
    _tell_reading(j2, ref, W.rows(ref, "readings.jsonl")[-1])
    assert len(calls) >= 2, "the covering read the record again"
    assert _reached(W, J, ref) == [] and J.status(ref)["state"] != "done"


def test_j2_the_goal_is_reached_by_the_real_flow_from_a_reading_and_sm_1_is_zero(j2, monkeypatch):
    """Audit's reader says every item is met; Identity hears the reading Audit filed and says the goal is reached, citing it:
    SM-1 (a 'goal reached' with no reading of every item for that version) is 0 here, and 'found nothing' alone reaches none."""
    W, R, J, _, _ = j2
    ref = _in_state(j2, monkeypatch, "done")
    (reading,) = [r for r in W.rows(ref, "readings.jsonl") if r["read"]]
    (reached,) = _reached(W, J, ref)
    assert reached["evidence_refs"][0]["reading"] == reading["id"] and sm1_faults(W, J, ref) == []
    assert [e["actor"] for e in J.events(ref) if e["action"] == "goal.reached"] == ["Identity"]
    # the offline department: the version was not read, so there is no 'goal reached' to match (M0.3)
    monkeypatch.setattr(R, "MODEL", None)
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    offline = _born(j2, org="Offline Co")
    _stamp_the_pending(W, offline, ("publish",))
    assert _reached(W, J, offline) == [] and sm1_faults(W, J, offline) == []
    # and SM-1 sees a goal reached on no reading
    J.note(offline, 8, "Identity", "User", "goal.reached", "done", "Done-when holds.", "goal-reached-vX", {}, evidence_refs=[{"artifact": "Live site", "version": 1}])
    assert len(sm1_faults(W, J, offline)) == 1


# ---- J3: a reading is weighed three ways (M8.5) ------------------------------------------------------------------------
def _adaptation_hears_next(monkeypatch, R):
    """Adaptation's recipe has a handler for request/next once W2-ADAPT is merged (M9.1); until then a stub with no steps stands
    in, so that what Identity posts has a receiver (A1-14). Returns True when the recipe is the stub."""
    e = R.engine_def("Adaptation")
    if R._handler(e, {"msg_type": "request", "payload": {"word": "next"}}) is not None:
        return False
    monkeypatch.setitem(e, "on", list(e["on"]) + [{"name": "Propose the next round", "when": {"msg_type": "request", "word": "next"}, "steps": []}])
    return True


def _next_requests(R, ref):
    return [q for q in R.board(ref) if q["src"] == "Identity" and q["dst"] == ["Adaptation"] and q["msg_type"] == "request"
            and (q["payload"] or {}).get("word") == "next"]


def _asks_of(W, ref, kind, status="pending"):
    return [a for a in W.asks(ref) if a["kind"] == kind and a["status"] == status]


def _four_items(W, ref):
    """D1 to D4, the last read by an AI, each worth a verdict of its own."""
    d = W.dept(ref)
    W.put_done_items(ref, W.items_of(d)[:1] + [{"text": text, "how": "model", "level": "outcome"} for text in (
        "Prices are on the page", "Every page names its fees", "Subscribers get the offer by email")])
    return W.items_of(W.dept(ref))


def test_j2_g_a_reading_is_weighed_three_ways(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, items=1)
    assert len(_four_items(W, ref)) == 4
    stub = _adaptation_hears_next(monkeypatch, R)
    row = _file_reading(j2, ref, {"D1": "met", "D2": "to_confirm", "D3": "not_met", "D4": "not_met"},
                        findings=[{"id": "F1", "severity": "high", "claim": "The fees are not on any page", "item": "D3"},
                                  {"id": "F2", "severity": "medium", "claim": "The offer is not sent to subscribers by email", "item": "D4"}])
    _tell_reading(j2, ref, row)
    # a fact only the owner knows: one question, missing 'fact', about the item it could not confirm
    (q,) = _asks_of(W, ref, "j2_identity")
    assert (q["missing"], q["points"], q["standard"], q["reading"]) == ("fact", ["D2"], False, row["id"])
    assert "D2" in q["text"] and "Prices are on the page" in q["text"] and S.validate_record("identity", "ask", q) == []
    assert J.status(ref)["open_question"]["id"] == q["id"]
    if stub:
        assert J.waiting_on_owner(ref), "nothing else moves: the cycle waits on the owner"
    else:
        # With Adaptation's own recipe the round for D3 is proposed, priced and filed, and the line builds again while the question
        # stays open: the cycle goes on and does not wait on the owner, whose question is still theirs to answer
        folded = {r["round"]: r for r in W.rows(ref, "rounds.jsonl")}
        assert [(n, r["status"], r["covers"]) for n, r in folded.items()] == [(1, "filed", ["D3"])], "one round, for D3, filed in the Brief"
        assert W.latest(ref, "Live site")["v"] == 2, "and the line built again on it"
        assert not J.waiting_on_owner(ref) and J.status(ref)["state"] != "waiting"
        assert [a["id"] for a in _asks_of(W, ref, "j2_identity")] == [q["id"]], "while the question on D2 is still the owner's, open"
    # a finding the owner must say yes to (a rule says ask: it reaches outside the department): an ask, and its item goes no further
    (f,) = _asks_of(W, ref, "finding")
    assert f["claim"] == "The offer is not sent to subscribers by email" and f["reading"] == row["id"] and f["thread"] and "Stamp to have it put right" in f["text"]
    assert f["rule"] and S.validate_record("identity", "ask", f) == []
    # every other item not met: the next move, to Adaptation, once
    (nxt,) = _next_requests(R, ref)
    assert nxt["payload"]["items"] == ["D3"] and nxt["payload"]["reading"] == row["id"] and nxt["payload"]["findings"] == ["F1"]
    assert S.validate("act.next", nxt["payload"]) == []
    # a met item goes nowhere, and nothing is asked twice if the reading is heard again
    _tell_reading(j2, ref, row)
    assert len(_asks_of(W, ref, "j2_identity")) == 1 and len(_asks_of(W, ref, "finding")) == 1 and len(_next_requests(R, ref)) == 1


def test_j2_g_an_item_to_confirm_is_one_question_whatever_their_number(j2):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, items=1)
    _four_items(W, ref)
    _hear(j2, ref, {"D1": "met", "D2": "to_confirm", "D3": "to_confirm", "D4": "met"})
    (q,) = _asks_of(W, ref, "j2_identity")
    assert q["points"] == ["D2", "D3"] and q["text"].count("D2") == 1 and q["text"].count("D3") == 1
    assert J.waiting_on_owner(ref) and J.status(ref)["open_question"]["id"] == q["id"], "no round is moving, so the cycle waits on the owner"
    said = [p for p in R.board(ref) if p["src"] == "Identity" and "Owner" in p["dst"] and p["payload"].get("card") == q["id"]]
    assert len(said) == 1, "the line names its card, so the chat says the question once, on the card"
    assert not re.search(r"\b(?:grant|counter|refuse|charter|Priority|Coordination)\b", q["text"], re.I)


@pytest.mark.parametrize("how", ["chat", "answer box"])
def test_j2_g_the_owners_answer_to_the_question_on_a_fact_is_filed_and_the_line_builds_again(j2, how):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    items = W.items_of(W.dept(ref))
    items[1]["confirm"] = "nobody gave the price list"
    W.put_done_items(ref, items)
    _hear(j2, ref, {"D1": "met", "D2": "to_confirm"})
    (q,) = _asks_of(W, ref, "j2_identity")
    briefs = len(W.versions(ref, "Brief"))
    _owner_says(j2, ref, how, "The price list is 500 rupees a month")
    done = next(a for a in W.asks(ref) if a["id"] == q["id"])
    assert (done["status"], done["answered"]) == ("stamped", "The price list is 500 rupees a month")
    assert len(W.versions(ref, "Brief")) > briefs and "The price list is 500 rupees a month" in W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"])["brief.md"]
    assert W.dept(ref)["to_be_confirmed"] == [] and "confirm" not in W.items_of(W.dept(ref))[1]
    assert J.status(ref)["open_question"] is None and J.status(ref)["state"] != "waiting"
    assert len(_asks_of(W, ref, "j2_identity")) == 0 and not _reached(W, J, ref)
    assert not [a for a in _asks_of(W, ref, "blocked")]


def test_j2_g_just_do_it_to_a_fact_the_owner_does_not_give_leaves_the_ways_out_never_a_silent_end(j2):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _hear(j2, ref, {"D1": "met", "D2": "to_confirm"})
    (q,) = _asks_of(W, ref, "j2_identity")
    _owner_says(j2, ref, "chat", "just do it")
    (card,) = _asks_of(W, ref, "blocked")
    assert [o["id"] for o in card["options"]] == ["words", "leave:D2", "stop"] and J.status(ref)["state"] == "blocked"
    assert next(a for a in W.asks(ref) if a["id"] == q["id"])["status"] == "stamped"


def test_j2_g_a_finding_a_rule_says_ask_about_is_an_ask_and_its_stamp_puts_it_right(j2):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    row = _file_reading(j2, ref, {"D1": "met", "D2": "not_met"}, findings=[{"id": "F1", "severity": "medium", "claim": "Send the offer by email to every subscriber", "item": "D2"}])
    _tell_reading(j2, ref, row)
    (ask,) = _asks_of(W, ref, "finding")
    assert ask["rule"] == "Ask the owner before anything reaches outside" or ask["rule"], "the rule that says to ask is named"
    briefs = len(W.versions(ref, "Brief"))
    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=300)
    assert "Correct this: Send the offer by email to every subscriber" in W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"])["brief.md"]
    assert len(W.versions(ref, "Brief")) == briefs + 1


def test_j2_g_every_other_not_met_item_is_the_next_move_and_is_posted_only_when_adaptation_hears_one(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    real = R._handler
    monkeypatch.setattr(R, "_handler", lambda e, p: None if (p.get("payload") or {}).get("word") == "next" else real(e, p))
    assert V1.next_is_heard() is False
    _hear(j2, ref, {"D1": "met", "D2": "not_met"}, findings=[{"id": "F1", "severity": "medium", "claim": "Every page names its fees", "item": "D2"}])
    assert _next_requests(R, ref) == [], "Adaptation has no handler yet: nothing is posted (A1-14)"
    monkeypatch.setattr(R, "_handler", real)
    stub = _adaptation_hears_next(monkeypatch, R)
    assert V1.next_is_heard() is True
    _hear(j2, ref, {"D1": "met", "D2": "not_met"}, findings=[{"id": "F1", "severity": "medium", "claim": "Every page names its fees", "item": "D2"}])
    (nxt,) = _next_requests(R, ref)
    assert (nxt["payload"]["items"], nxt["payload"]["findings"]) == (["D2"], ["F1"])
    runs = [r["what"] for r in W.runs(ref) if r["engine"] == "Adaptation"]
    assert ("Propose the next round" in runs) or not stub
    assert J.status(ref)["state"] == "pursuing" and J.status(ref)["step"] == 8


def test_j2_g_a_not_met_item_always_leaves_a_next_move_even_before_anyone_takes_a_round(j2, monkeypatch):
    """SM-6 with Pursue off: no handler for request/next, so the item goes the way it went before rounds, to the owner, on a stamp."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    real = R._handler
    monkeypatch.setattr(R, "_handler", lambda e, p: None if (p.get("payload") or {}).get("word") == "next" else real(e, p))
    _hear(j2, ref, {"D1": "met", "D2": "not_met"}, findings=[{"id": "F1", "severity": "low", "claim": "Every page names its fees", "item": "D2"}])
    assert _next_requests(R, ref) == []
    (ask,) = _asks_of(W, ref, "finding")
    assert "D2" in ask["found"] and ask["reading"] and S.validate_record("identity", "ask", ask) == []


#: the finding a rule says to ask about, which comes back on the reading after the owner answered it (found by a verifier: the
#: department then sat in 'pursuing' with nothing pending and no next move)
AGAIN = "Send the offer by email to every subscriber"


def _a_next_move_for(R, W, ref, reading):
    """SM-6: what a not-met item leaves after a reading: a next round asked of Adaptation about that reading, or a question waiting
    on the owner. Returns what it is, or None for a silent end."""
    if [q for q in _next_requests(R, ref) if q["payload"].get("reading") == reading]:
        return "next"
    pending = [a for a in W.asks(ref) if a["status"] == "pending"]
    return pending[0]["kind"] if pending else None


def _the_same_finding_comes_back(j2, monkeypatch, org, answer, heard=True):
    """A reading with D2 not met and a finding a rule says to ask about: the owner answers the ask it makes (yes: stamped; no: refused,
    and then 'Change the plan in my words'), the line is built again, and the next reading finds D2 still not met with the same
    finding. Returns (department, the reading that came back)."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org=org)
    if heard:
        _adaptation_hears_next(monkeypatch, R)
    else:
        real = R._handler
        monkeypatch.setattr(R, "_handler", lambda e, p: None if (p.get("payload") or {}).get("word") == "next" else real(e, p))
    finding = [{"id": "F1", "severity": "medium", "claim": AGAIN, "item": "D2"}]
    first = _file_reading(j2, ref, {"D1": "met", "D2": "not_met"}, findings=finding)
    _tell_reading(j2, ref, first)
    (ask,) = [a for a in _asks_of(W, ref, "finding") if not a.get("round")]
    assert ask["claim"] == AGAIN and ask["reading"] == first["id"], "the rule's ask is the first reading's move"
    if answer == "yes":
        W.decide_ask(ref, ask["id"], True)
    else:
        W.decide_ask(ref, ask["id"], False)
        W.run_until_idle(ref, limit=300)
        W.choose_option(ref, _the_card(W, ref)["id"], "words", "Tell people about the offer on the page instead")
    W.run_until_idle(ref, limit=300)
    assert next(a for a in W.asks(ref) if a["id"] == ask["id"])["status"] == ("stamped" if answer == "yes" else "refused")
    assert J.status(ref)["state"] != "done" and W.latest(ref, "Live site")["v"] >= 2, "the line was built again"
    again = _file_reading(j2, ref, {"D1": "met", "D2": "not_met"}, findings=finding)
    assert again["id"] != first["id"] and again["v"] == W.latest(ref, "Live site")["v"]
    _tell_reading(j2, ref, again)
    return ref, again


@pytest.mark.parametrize("heard", [True, False], ids=["adaptation hears next", "nobody hears next"])
@pytest.mark.parametrize("answer", ["yes", "no"])
def test_j2_g_a_finding_the_owner_already_answered_that_comes_back_leaves_a_next_move(j2, monkeypatch, answer, heard):
    """SM-6 on the repeat: the owner answered the ask for a finding (said yes, or said no and changed the plan), the line was built
    again, and the next reading has the same item not met with the same finding. The answered ask covers nothing now: the item goes
    on as every other item not met, the next round asked of Adaptation, or, when nobody takes one, a question for the owner. It is
    never 'pursuing' with nothing pending and no next move, and the finding is not put to the owner a second time as it was."""
    W, R, J, _, _ = j2
    ref, again = _the_same_finding_comes_back(j2, monkeypatch, "Again %s %s Co" % (answer, "Heard" if heard else "Silent"), answer, heard)
    move = _a_next_move_for(R, W, ref, again["id"])
    assert move is not None, ("a silent end", J.status(ref)["state"], [(a["kind"], a["status"]) for a in W.asks(ref)])
    assert [a for a in _asks_of(W, ref, "finding") if a["claim"] == AGAIN] == [], "the answered finding is not asked a second time"
    if heard:
        assert move == "next", "Adaptation hears a next round, so the item is its next move"
        (nxt,) = [q for q in _next_requests(R, ref) if q["payload"].get("reading") == again["id"]]
        assert nxt["payload"]["items"] == ["D2"] and S.validate("act.next", nxt["payload"]) == []
    else:
        (ask,) = _asks_of(W, ref, "finding")
        assert "D2" in ask["found"] and ask["reading"] == again["id"] and S.validate_record("identity", "ask", ask) == []


def test_j2_g_a_finding_whose_ask_is_still_waiting_covers_its_item_on_the_next_reading_too(j2, monkeypatch):
    """The ask is the item's move only while the owner has not answered it: a second reading that comes while it waits files
    nothing more (not the ask again, not a next round beside it)."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org="Waiting Again Co")
    _adaptation_hears_next(monkeypatch, R)
    finding = [{"id": "F1", "severity": "medium", "claim": AGAIN, "item": "D2"}]
    _tell_reading(j2, ref, _file_reading(j2, ref, {"D1": "met", "D2": "not_met"}, findings=finding))
    (ask,) = _asks_of(W, ref, "finding")
    nexts = len(_next_requests(R, ref))
    again = _file_reading(j2, ref, {"D1": "met", "D2": "not_met"}, findings=finding)
    _tell_reading(j2, ref, again)
    assert [a["id"] for a in _asks_of(W, ref, "finding")] == [ask["id"]] and len(_next_requests(R, ref)) == nexts
    assert _a_next_move_for(R, W, ref, again["id"]) == "finding", "the waiting ask is the move"


def test_j2_g_a_high_finding_the_next_round_carries_is_not_also_put_to_the_owner(j2, monkeypatch):
    """Once Adaptation hears a next round the finding ask is swapped for the round (PRD risk P1): a high finding of a reading
    with an item not met reaches Adaptation as the next move, and the owner is not also asked to stamp the same correction."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _adaptation_hears_next(monkeypatch, R)
    row = _file_reading(j2, ref, {"D1": "met", "D2": "not_met"}, findings=[{"id": "F1", "severity": "high", "claim": "Every page names its fees", "item": "D2"}])
    R.post(ref, "Audit", "Identity", "inform", {"word": "finding", "claim": "Every page names its fees", "severity": "high", "reading": row["id"],
                                               "findings": [{"page": "index", "claim": "Every page names its fees", "severity": "high", "item": "D2"}]})
    R.audit_tell(ref, row)
    W.run_until_idle(ref, limit=300)
    # (with Adaptation's own recipe the round reaches Identity, and a correction that reaches outside is put to the owner once, as
    # the round's own ask; the finding itself is not put as well)
    assert [a for a in _asks_of(W, ref, "finding") if not a.get("round")] == [] and len(_next_requests(R, ref)) == 1
    # a hole is the owner's to fill in, rounds or not
    R.post(ref, "Audit", "Identity", "inform", {"word": "finding", "claim": "opening hours", "severity": "low", "reading": row["id"],
                                               "findings": [{"kind": "hole", "claim": "opening hours"}]})
    W.run_until_idle(ref, limit=300)
    assert any("does not know" in s for s in _said_by_identity(R, ref))


def test_j2_g_a_reading_of_an_earlier_cycle_is_weighed_by_nobody(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _adaptation_hears_next(monkeypatch, R)
    _hear(j2, ref, {"D1": "met", "D2": "not_met"}, cycle="cycle-before", findings=[{"id": "F1", "severity": "low", "claim": "x", "item": "D2"}])
    assert _next_requests(R, ref) == [] and _asks_of(W, ref, "finding") == []


def test_j2_g_nothing_is_weighed_of_a_version_nobody_read_or_a_department_that_is_done(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _adaptation_hears_next(monkeypatch, R)
    _hear(j2, ref, {}, read=False)
    assert _next_requests(R, ref) == [] and _asks_of(W, ref, "j2_identity") == []
    _hear(j2, ref, {"D1": "met", "D2": "met"})
    assert len(_reached(W, J, ref)) == 1
    _hear(j2, ref, {"D1": "met", "D2": "not_met"}, findings=[{"id": "F1", "severity": "low", "claim": "x", "item": "D2"}])
    assert _next_requests(R, ref) == [], "a department that is done takes tasks through the Brief (J3 4a), not rounds"


def test_j2_g_a_measured_failure_that_waits_on_facts_the_owner_was_asked_for_is_not_also_a_next_round(j2, monkeypatch):
    """The site said it does not know some facts and the owner was asked for them: what code measured as not holding waits on
    those facts, which are never made up, so asking the line to correct it would be asking it to invent them."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _adaptation_hears_next(monkeypatch, R)
    row = _file_reading(j2, ref, {"D1": "not_met", "D2": "met"}, method="code", findings=[{"id": "F1", "severity": "high", "claim": "opening hours", "item": None}])
    R._tell(ref, W.dept(ref), {"src": R.OWNER}, "inform", {"word": "facts", "done": "The site says it does not know opening hours.", "holes": 1, "about_version": row["v"]})
    _tell_reading(j2, ref, row)
    assert _next_requests(R, ref) == [] and _asks_of(W, ref, "finding") == [], "the facts question is the next move"
    other = _file_reading(j2, ref, {"D1": "not_met", "D2": "met"}, method="code", v=row["v"] + 1, artifact="Live site",
                          findings=[{"id": "F1", "severity": "high", "claim": "a link goes nowhere", "item": None}])
    W.add_version(ref, "Live site", {"index.html": "<p>again</p>"}, [], "r-y", {"ok": True, "notes": []})
    _tell_reading(j2, ref, other)
    assert len(_next_requests(R, ref)) == 1, "with no facts asked for, it is the next round's"


# ---- J4: File a granted round (M9.3) -----------------------------------------------------------------------------------------
def _adaptation_may_tell_a_round(monkeypatch):
    """Adaptation's SENDS row for inform/round is W2-ADAPT's (M9.1); the stub round of these tests brings it when it is not yet in."""
    if not any(r["act"] == "inform" and "round" in r["words"] and "Identity" in r["to"] for r in S.SENDS["Adaptation"]):
        monkeypatch.setitem(S.SENDS, "Adaptation", list(S.SENDS["Adaptation"]) +
                            [{"act": "inform", "words": ("round",), "to": ("Identity",), "payload": "act.round"}])


def _grant_round(R, W, J, monkeypatch, ref, n=2, correction="Name the fees on every page", covers=("D2",), rows=("proposed", "granted"),
                 cycle=None, **more):
    """A stub Adaptation: it proposed round n, Priority priced it inside the ceiling, and it tells Identity the round is granted
    (inform/round). Its rounds.jsonl rows are its own (W2-ADAPT); the stub writes the ones it would: the statuses in `rows`, in the
    cycle now at work unless `cycle` names another. A test of a round nobody granted gives fewer rows and still tells Identity."""
    _adaptation_may_tell_a_round(monkeypatch)
    base = {"schema_version": 1, "round": n, "at": W.now(), "cycle_id": cycle or J.status(ref)["cycle_id"], "correction": correction, "fixes": ["F1"],
            "covers": list(covers), "estimate": {"calls": 4, "usd": 0.08}, "reading": "r-0a0a0a0a"}
    for status in rows:
        W.append_row(ref, "rounds.jsonl", dict(base, status=status, **({"brief_v": 3} if status in ("filed", "read") else {})))
    return R.post(ref, "Adaptation", "Identity", "inform",
                  dict({"word": "round", "round": n, "correction": correction, "fixes": ["F1"], "covers": list(covers),
                        "estimate": {"calls": 4, "usd": 0.08}, "why": "it fits the room"}, **more))


def _identity_hears(R, ref, post):
    """Only Identity runs, on this post: what its handler files, and nothing the line does after."""
    return R.run_engine(ref, "Identity", {"post": post, "v": post["n"]}, "Identity@board.n%d" % post["n"])


def _versions(W, ref):
    return {a: len(W.versions(ref, a)) for a in list(W.artifacts_of(W.dept(ref))) + ["Brief"]}


def test_j4_identitys_recipe_files_a_granted_round_and_the_interface_says_so(home):
    import engine_runtime as R
    row = next(r for r in S.hears("identity") if (r["act"], r["word"]) == ("inform", "round"))
    assert (row["from"], row["via"], row["payload"], row["handler"]) == (("Adaptation",), "board", "act.round", "File a granted round")
    handler = next(h for h in layers.recipes()["Identity"]["on"] if h["name"] == "File a granted round")
    assert handler["when"] == {"msg_type": "inform", "word": "round"}
    assert [(s["id"], s["code"], s["born"], s["check"]) for s in handler["steps"]] == \
        [("identity.hear_round", "hear", "C2", "facts_are_closed"), ("identity.round", "identity_round", "C2", "said_what_it_did")]
    assert R.validate(R.defs()) == []


def test_j4_a_stub_granted_round_files_brief_v3_and_nothing_else(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    R._file_words(ref, W.dept(ref), "Make the heading on the home page bigger", "the owner's ask")
    assert len(W.versions(ref, "Brief")) == 2
    before, asks = _versions(W, ref), [a["id"] for a in W.asks(ref)]
    told = len([p for p in R.board(ref) if p["src"] == "Identity" and "Owner" in p["dst"]])
    post = _grant_round(R, W, J, monkeypatch, ref)
    row = _identity_hears(R, ref, post)
    assert row["status"] == "ok", row
    after = _versions(W, ref)
    assert after["Brief"] == 3 and {a: n for a, n in after.items() if a != "Brief"} == {a: n for a, n in before.items() if a != "Brief"}, "Brief v3, and no other artifact"
    brief = W.read_files(ref, "Brief", 3)["brief.md"]
    assert brief.rstrip().endswith("- Correct this: Name the fees on every page")
    assert [a["id"] for a in W.asks(ref)] == asks, "no stamp: nothing is asked of the owner"
    assert [p["payload"]["done"] for p in R.board(ref)[-1:] if p["src"] == "Identity"] and \
        len([p for p in R.board(ref) if p["src"] == "Identity" and "Owner" in p["dst"]]) == told + 1, "the owner is told once"
    assert next(p for p in reversed(R.board(ref)) if p["src"] == "Identity")["payload"]["done"] == \
        "Round 2: I sent the line back to put right: Name the fees on every page. It is filed in the Brief as v3."
    made = W.versions(ref, "Brief")[-1]["made_from"]
    assert made[-1]["round"] == 2 and made[-1]["ask"] == "Correct this: Name the fees on every page"


def test_j4_a_status_change_is_a_row_appended_never_a_row_rewritten(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    post = _grant_round(R, W, J, monkeypatch, ref)
    raw = (W.ddir(ref) / "rounds.jsonl").read_text(encoding="utf-8")
    _identity_hears(R, ref, post)
    now = (W.ddir(ref) / "rounds.jsonl").read_text(encoding="utf-8")
    assert now.startswith(raw), "the rows that were there are the same bytes"
    rows = W.rows(ref, "rounds.jsonl")
    assert [r["status"] for r in rows] == ["proposed", "granted", "filed"] and rows[-1]["brief_v"] == len(W.versions(ref, "Brief"))
    assert all(S.validate_record("adaptation", "round", r) == [] for r in rows)
    assert (rows[-1]["round"], rows[-1]["correction"], rows[-1]["covers"], rows[-1]["reading"]) == (2, "Name the fees on every page", ["D2"], "r-0a0a0a0a")


@pytest.mark.parametrize("rows,cycle,why", [
    (("proposed",), None, "Priority has not answered: the last row is proposed"),
    ((), None, "no row at all: nobody proposed it"),
    (("proposed", "granted"), "cycle-before", "granted in an earlier cycle, not this one"),
    (("proposed", "granted", "filed", "read"), "cycle-before", "filed and read in an earlier cycle: rounds are numbered again in each cycle"),
])
def test_j4_a_round_priority_did_not_grant_is_not_filed(j2, monkeypatch, rows, cycle, why):
    """Every proposal passes Priority first (rule 10): Identity files 'Correct this' only for a round whose last row, in the cycle
    now at work, says granted. The sender (Adaptation) is no proof of it."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    before, state = _versions(W, ref), {k: J.status(ref)[k] for k in ("state", "step", "round", "cycle_id")}
    told = len([p for p in R.board(ref) if p["src"] == "Identity" and "Owner" in p["dst"]])
    for correction in ("Name the fees on every page", "Email every subscriber the new fees"):      # and the one a rule says to ask about
        post = _grant_round(R, W, J, monkeypatch, ref, correction=correction, rows=rows, cycle=cycle)
        written = (W.ddir(ref) / "rounds.jsonl").read_text(encoding="utf-8") if (W.ddir(ref) / "rounds.jsonl").exists() else ""
        row = _identity_hears(R, ref, post)
        assert row["status"] == "ok", (why, row)
        assert "round 2 has no yes from Priority; nothing is filed" in json.dumps(row), (why, row)
        assert _versions(W, ref) == before, (why, "no version of the Brief or of anything else")
        now = (W.ddir(ref) / "rounds.jsonl").read_text(encoding="utf-8") if (W.ddir(ref) / "rounds.jsonl").exists() else ""
        assert now == written, (why, "no row of the round is written")
        assert _asks_of(W, ref, "finding") == [], (why, "and nothing is asked of the owner")
        assert {k: J.status(ref)[k] for k in state} == state and len([p for p in R.board(ref) if p["src"] == "Identity" and "Owner" in p["dst"]]) == told


def test_j4_a_round_numbered_again_in_a_new_cycle_is_filed_on_its_own_yes(j2, monkeypatch):
    """Rounds are numbered again in each cycle: round 2 filed and read in an earlier cycle is no word on round 2 of this one."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _grant_round(R, W, J, monkeypatch, ref, rows=("proposed", "granted", "filed", "read"), cycle="cycle-before")
    post = _grant_round(R, W, J, monkeypatch, ref)
    briefs = len(W.versions(ref, "Brief"))
    _identity_hears(R, ref, post)
    assert len(W.versions(ref, "Brief")) == briefs + 1 and J.status(ref)["round"] == 2
    mine = [r["status"] for r in W.rows(ref, "rounds.jsonl") if r["cycle_id"] == J.status(ref)["cycle_id"]]
    assert mine == ["proposed", "granted", "filed"]


def test_j4_a_round_heard_twice_is_filed_once(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    post = _grant_round(R, W, J, monkeypatch, ref)
    _identity_hears(R, ref, post)
    again = R.post(ref, "Adaptation", "Identity", "inform", dict(post["payload"]))
    _identity_hears(R, ref, again)
    assert len(W.versions(ref, "Brief")) == 2 and [r["status"] for r in W.rows(ref, "rounds.jsonl")].count("filed") == 1
    assert W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"])["brief.md"].count("Correct this: Name the fees on every page") == 1


def test_j4_the_next_reading_marks_the_filed_round_read_once(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _identity_hears(R, ref, _grant_round(R, W, J, monkeypatch, ref))
    assert [r["status"] for r in W.rows(ref, "rounds.jsonl")] == ["proposed", "granted", "filed"]
    row = _file_reading(j2, ref, {"D1": "met", "D2": "met"})
    _tell_reading(j2, ref, row)
    rows = W.rows(ref, "rounds.jsonl")
    assert [r["status"] for r in rows] == ["proposed", "granted", "filed", "read"] and rows[-1]["brief_v"] == rows[-2]["brief_v"]
    assert all(S.validate_record("adaptation", "round", r) == [] for r in rows)
    _tell_reading(j2, ref, row)
    assert [r["status"] for r in W.rows(ref, "rounds.jsonl")].count("read") == 1, "read once"


def test_j4_the_cycle_runs_the_registered_line_again_on_the_round(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    registered = set(W.dept(ref)["workflows"][-1]["engines"])
    runs = len(W.runs(ref))
    post = _grant_round(R, W, J, monkeypatch, ref)
    _identity_hears(R, ref, post)
    st = J.status(ref)
    assert (st["state"], st["step"], st["round"]) == ("running", 6, 2)
    W.run_until_idle(ref, limit=300)
    ran = [r["engine"] for r in W.runs(ref)[runs:] if not r.get("system")]
    assert ran and set(ran) <= registered, "only registered engines run (SM-3): %s" % ran


def test_j4_after_the_goal_is_reached_no_round_is_filed(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _hear(j2, ref, {"D1": "met", "D2": "met"})
    assert J.status(ref)["state"] == "done"
    briefs = len(W.versions(ref, "Brief"))
    row = _identity_hears(R, ref, _grant_round(R, W, J, monkeypatch, ref))
    assert row["status"] == "ok" and len(W.versions(ref, "Brief")) == briefs and J.status(ref)["state"] == "done"


def test_j4_a_rule_that_says_ask_makes_the_correction_an_ask_and_the_stamp_files_the_round(j2, monkeypatch):
    """S-18: no stamp unless a rule says ask. The department's born rule asks before anything reaches outside."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    post = _grant_round(R, W, J, monkeypatch, ref, correction="Email every subscriber the new fees")
    briefs = len(W.versions(ref, "Brief"))
    _identity_hears(R, ref, post)
    (ask,) = _asks_of(W, ref, "finding")
    assert ask["round"] == 2 and ask["rule"] and len(W.versions(ref, "Brief")) == briefs and W.rows(ref, "rounds.jsonl")[-1]["status"] == "granted"
    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=1)
    assert len(W.versions(ref, "Brief")) == briefs + 1
    assert "Correct this: Email every subscriber the new fees" in W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"])["brief.md"]
    filed = W.rows(ref, "rounds.jsonl")[-1]
    assert (filed["status"], filed["round"], filed["brief_v"]) == ("filed", 2, briefs + 1) and J.status(ref)["round"] == 2


def test_j4_a_rule_that_says_ask_and_a_no_ends_the_round_and_leaves_the_ways_out(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2)
    _identity_hears(R, ref, _grant_round(R, W, J, monkeypatch, ref, correction="Email every subscriber the new fees"))
    (ask,) = _asks_of(W, ref, "finding")
    briefs = len(W.versions(ref, "Brief"))
    W.decide_ask(ref, ask["id"], False)
    W.run_until_idle(ref, limit=1)
    assert len(W.versions(ref, "Brief")) == briefs and W.rows(ref, "rounds.jsonl")[-1]["status"] == "refused"
    (card,) = _asks_of(W, ref, "blocked")
    assert [o["id"] for o in card["options"]] == ["words", "leave:D2", "stop"] and J.status(ref)["state"] == "blocked"


# ---- J5: no silent ends (M9.5) -----------------------------------------------------------------------------------------------
RULE = "Every page ends with: Call 108."


def _a_rule_the_build_breaks(j2, monkeypatch, org="Rule Co"):
    """A website whose owner stamped a rule its pages cannot meet, so Check fails every build: after two rewrites the line stops."""
    W, R, J, _, _ = j2
    ref = _born(j2, WEBSITE, org)
    _stamp_the_pending(W, ref, ("publish",))
    _model(monkeypatch, R, {"identity.recognise": {"journey": "directive", "why": "a standing rule"},
                            "identity.rule": {"tag": "always", "line": RULE, "scope": "standing"}})
    W.owner_ask(ref, "From now on, every page ends with: Call 108.")
    W.run_until_idle(ref, limit=300)
    _stamp_the_pending(W, ref, ("rule",))
    W.run_until_idle(ref, limit=600)
    return ref


def test_j2_7_the_second_send_back_files_an_options_ask(j2, monkeypatch):
    """A build that breaks a stamped rule goes back to the line twice; when two rewrites did not mend it the owner is told so and
    given the ways out as one ask, never a tell only: say it another way, leave this rule out, stop."""
    W, R, J, _, _ = j2
    ref = _a_rule_the_build_breaks(j2, monkeypatch)
    brief = W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"])["brief.md"]
    assert brief.count(R.SEND_BACK) == 2, "the finding went to the line twice, and no more"
    told = [s for s in _said_by_identity(R, ref) if "two rewrites did not mend it" in s]
    assert len(told) == 1 and "Say the rule another way, or drop it." in told[0], "the tell stays"
    (card,) = _asks_of(W, ref, "blocked")
    rule = next(r for r in W.dept(ref)["rules"] if r["line"] == RULE)
    assert [o["id"] for o in card["options"]] == ["words", "leave:" + rule["id"], "stop"]
    assert [o["label"] for o in card["options"]] == ["Say the rule another way", "Leave this rule out", "Stop here"]
    assert S.validate_record("identity", "ask", card) == [] and card["thread"] and RULE.rstrip(".") in card["text"]
    assert J.status(ref)["state"] == "blocked"
    assert not re.search(r"\b(?:grant|counter|refus|charter)", " ".join([card["text"], card["title"], card["why"]]), re.I)
    # the chat says it once on the card: the card's line is not a turn of its own
    assert len([t for t in R.chat_view(ref)["turns"] if t.get("word") == "blocked"]) == 0


def test_j5_leaving_the_rule_out_drops_it_and_the_line_builds_again_without_it(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_rule_the_build_breaks(j2, monkeypatch)
    (card,) = _asks_of(W, ref, "blocked")
    rule = next(r for r in W.dept(ref)["rules"] if r["line"] == RULE)
    live, revision = len(W.versions(ref, "Live site")), W.dept(ref)["identity_revision"]
    monkeypatch.setattr(R, "MODEL", None)                                # the owner's words are still what the line is held to
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")                     # and no model is there: the drafts build the pages (as in test_j2_the_goal_is_reached_by_the_real_flow)
    W.choose_option(ref, card["id"], "leave:" + rule["id"])
    W.run_until_idle(ref, limit=600)
    d = W.dept(ref)
    assert RULE not in [r["line"] for r in d["rules"]] and d["identity_revision"] == revision + 1, "the rule is off the record, a revision"
    assert next(a for a in W.asks(ref) if a["id"] == card["id"])["status"] == "chosen"
    assert "A rule is left out: %s" % RULE.rstrip(".") in W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"])["brief.md"]
    assert len(W.versions(ref, "Live site")) > live, "with the rule gone the build passes and goes live"
    assert not _asks_of(W, ref, "blocked") and J.status(ref)["state"] != "blocked"


def test_j5_saying_it_another_way_and_stopping_are_still_applied(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_rule_the_build_breaks(j2, monkeypatch)
    (card,) = _asks_of(W, ref, "blocked")
    W.choose_option(ref, card["id"], "stop")
    W.run_until_idle(ref, limit=100)
    assert W.dept(ref)["stopped"] is True
    (again,) = _asks_of(W, ref, "blocked")
    assert again["id"] == card["id"] and [o["id"] for o in again["options"]][0] == "words", "stopped, its way out stays open"


def _verdicts(W, ref, last):
    """Every done-when item met but the last, which has the verdict `last`: D1 met and D2 not met for two items, D1 alone for one."""
    ids = [i["id"] for i in W.items_of(W.dept(ref))]
    return dict({i: "met" for i in ids[:-1]}, **{ids[-1]: last})


def _stalled_department(j2, monkeypatch, rounds=2, org="Stall Co", items=2):
    """A department whose rounds met nothing new: a reading with the last item not met, then `rounds` rounds filed, each read with
    it still not met (D2 of two items, D1 of one)."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org=org, items=items)
    last = W.items_of(W.dept(ref))[-1]["id"]
    _adaptation_hears_next(monkeypatch, R)
    finding = [{"id": "F1", "severity": "high", "claim": "Every page names its fees", "item": last}]
    _hear(j2, ref, _verdicts(W, ref, "not_met"), findings=finding)
    for n in range(2, 2 + rounds):
        W.append_row(ref, "rounds.jsonl", {"schema_version": 1, "round": n, "at": W.now(), "cycle_id": J.status(ref)["cycle_id"], "correction": "Name the fees",
                                           "fixes": ["F1"], "covers": [last], "status": "filed", "brief_v": n + 1, "reading": "r-0a0a0a0a"})
        _hear(j2, ref, _verdicts(W, ref, "not_met"), v=n, findings=finding)
    return ref


def test_j5_two_rounds_with_no_newly_met_item_give_an_options_ask_and_ask_the_line_for_no_more(j2, monkeypatch):
    W, R, J, _, _ = j2
    one = _stalled_department(j2, monkeypatch, rounds=1, org="One Round Co")
    assert len(_next_requests(R, one)) == 2 and _asks_of(W, one, "blocked") == [], "one round with nothing new met is not yet a stall"
    ref = _stalled_department(j2, monkeypatch, rounds=2)
    (card,) = _asks_of(W, ref, "blocked")
    assert [o["id"] for o in card["options"]] == ["words", "leave:D2", "stop"] and J.status(ref)["state"] == "blocked"
    assert "D2" in card["text"] and card["reading"] == W.rows(ref, "readings.jsonl")[-1]["id"] and S.validate_record("identity", "ask", card) == []
    assert len(_next_requests(R, ref)) == 2, "no further round is asked of the line (the reading after round 3 files none)"
    _tell_reading(j2, ref, W.rows(ref, "readings.jsonl")[-1])
    assert len(_asks_of(W, ref, "blocked")) == 1, "the same reading, heard again, is the same card"


def test_j5_a_round_that_met_something_new_is_progress(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org="Progress Co")
    _four_items(W, ref)
    _adaptation_hears_next(monkeypatch, R)
    cycle = J.status(ref)["cycle_id"]
    finding = [{"id": "F1", "severity": "high", "claim": "x", "item": "D2"}]
    _hear(j2, ref, {"D1": "met", "D2": "not_met", "D3": "not_met", "D4": "met"}, findings=finding)
    for n, verdicts in ((2, {"D1": "met", "D2": "met", "D3": "not_met", "D4": "met"}), (3, {"D1": "met", "D2": "met", "D3": "not_met", "D4": "met"})):
        W.append_row(ref, "rounds.jsonl", {"schema_version": 1, "round": n, "at": W.now(), "cycle_id": cycle, "correction": "c", "covers": ["D2"],
                                           "status": "filed", "brief_v": n + 1})
        _hear(j2, ref, verdicts, v=n, findings=[])
    assert _asks_of(W, ref, "blocked") == [], "the first round met D2: only the second met nothing new"
    W.append_row(ref, "rounds.jsonl", {"schema_version": 1, "round": 4, "at": W.now(), "cycle_id": cycle, "correction": "c", "covers": ["D3"],
                                       "status": "filed", "brief_v": 5})
    _hear(j2, ref, {"D1": "met", "D2": "met", "D3": "not_met", "D4": "met"}, v=4, findings=[])
    assert len(_asks_of(W, ref, "blocked")) == 1, "now two rounds in a row met nothing new"


#: what the screen never says (the owner's rulings: said yes, asked for less, said no; no charter, no internal system; no orders)
SCREEN_BANNED = re.compile(r"\b(?:grant|counter|refus|orders\b|charter|internal system)", re.I)


def test_j5_the_words_the_owner_reads_in_the_pursuit_keep_the_screen_rules(j2, monkeypatch):
    """Every line Identity says to the owner in these flows, every card and every way out on it, in the owner's words: no grant,
    counter, refuse, orders, charter or internal system, no code of the machine, and no function addressing another."""
    W, R, J, _, _ = j2
    seen, notes = [], []
    states = list(_end_states(j2, monkeypatch))
    # and a department whose round was filed with no stamp: the Brief version that round makes carries a note the owner reads
    ref = _a_running_department(j2, org="Filed Round Co")
    _identity_hears(R, ref, _grant_round(R, W, J, monkeypatch, ref))
    assert len(W.versions(ref, "Brief")) == 2
    states.append(("a round filed with no stamp", ref))
    for what, ref in states:
        for p in R.board(ref):
            if p["src"] == "Identity" and "Owner" in p["dst"]:
                seen += [(what, str(p["payload"].get(k))) for k in ("done", "objective") if p["payload"].get(k)]
        for a in W.asks(ref):
            seen += [(what, str(a.get(k))) for k in ("text", "title", "why") if a.get(k)]
            seen += [(what, str(o.get(k))) for o in a.get("options") or [] for k in ("label", "cost")]
        # the Versions pane prints every version's note and every check note of it (22-website.js), and the artifact read returns them
        for art in list(W.artifacts_of(W.dept(ref))) + ["Brief"]:
            for v in W.versions(ref, art):
                notes += [(what, str(x)) for x in [v.get("note")] + list((v.get("check") or {}).get("notes") or []) if x]
    assert len(seen) > 40 and any("round 2" in text for _, text in notes), "the filed round's note was scanned"
    for what, text in notes:
        assert not SCREEN_BANNED.search(text), (what, "a version note", text)
    from engine_runtime import PLAIN_FAULTS
    for what, text in seen:
        assert not SCREEN_BANNED.search(text), (what, text)
        assert not [name for name, rx in PLAIN_FAULTS if rx.search(text)], (what, text)


def test_j4_the_brief_version_a_filed_round_makes_names_who_said_yes_in_the_owners_words(j2, monkeypatch):
    """The Versions pane and the work item's card print a version's note and its check notes. The version a filed round makes
    says who agreed to it as the screen says it: Priority said yes, never 'granted'."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org="Note Co")
    _identity_hears(R, ref, _grant_round(R, W, J, monkeypatch, ref))
    made = W.versions(ref, "Brief")[-1]
    assert made["made_from"][-1]["round"] == 2
    assert made["check"]["notes"][0] == "round 2, Priority said yes"
    import website_api
    shown = next(v for v in website_api.artifact(ref, "brief")["versions"] if v["v"] == made["v"])
    assert shown["check"]["notes"][0] == "round 2, Priority said yes" and not SCREEN_BANNED.search(" ".join(map(str, shown["check"]["notes"] + [shown.get("note") or ""])))


def _end_states(j2, monkeypatch):
    """Every end the pursuit can come to that is not done, each in a department of its own: (what it is, the department)."""
    W, R, J, _, _ = j2
    out = []
    # (first: a model that reads every word as a rule, which the next state installs, would read the owner's words so)
    # the same finding comes back on the next reading after the owner turned it down and changed the plan: the item is the next move
    # again (a round asked of Adaptation, or a question for the owner when nobody takes one), and the owner's second no ends in the card
    for org, heard in (("Again No Co", True), ("Again Silent Co", False)):
        with monkeypatch.context() as m:
            ref, _ = _the_same_finding_comes_back(j2, m, org, "no", heard)
            _owner_says_no(W, ref, _asks_of(W, ref, "finding")[0])
        out.append(("a finding that came back after it was turned down, turned down again" + ("" if heard else " (nobody takes a next round)"), ref))
    ref = _born(j2, WEBSITE, "Conflict Co")
    _two_items(W, ref)
    _conflict(R, ref, ENGINES, _ways(W.items_of(W.dept(ref))))
    W.run_until_idle(ref, limit=300)
    out.append(("a conflict with ways out", ref))
    out.append(("a rule the build still breaks after two rewrites", _a_rule_the_build_breaks(j2, monkeypatch, "Send Back Co")))
    out.append(("two rounds that met nothing new", _stalled_department(j2, monkeypatch, org="No Progress Co")))
    ref = _a_running_department(j2, org="Fact Co")
    _hear(j2, ref, {"D1": "met", "D2": "to_confirm"})
    _owner_says(j2, ref, "chat", "just do it")
    out.append(("a fact the owner does not give", ref))
    ref = _a_running_department(j2, org="No Co")
    _identity_hears(R, ref, _grant_round(R, W, J, monkeypatch, ref, correction="Email every subscriber the new fees"))
    W.decide_ask(ref, _asks_of(W, ref, "finding")[0]["id"], False)
    W.run_until_idle(ref, limit=1)
    out.append(("a correction the owner turned down", ref))
    # a finding that is not a round's, turned down: a high finding on a reading that met every item, a finding a rule says to ask
    # about, and a not-met item's finding ask while nobody takes a next round (the owner's no must never end in silence)
    ref = _a_running_department(j2, org="High Co")
    _high_finding_on_a_met_reading(R, W, j2, ref)
    _owner_says_no(W, ref, _asks_of(W, ref, "finding")[0])
    out.append(("a high finding on a reading that met every item, turned down", ref))
    ref = _a_running_department(j2, org="Ask Co")
    _tell_reading(j2, ref, _file_reading(j2, ref, {"D1": "met", "D2": "not_met"},
                                         findings=[{"id": "F1", "severity": "medium", "claim": "Send the offer by email to every subscriber", "item": "D2"}]))
    _owner_says_no(W, ref, _asks_of(W, ref, "finding")[0])
    out.append(("a finding a rule says to ask about, turned down", ref))
    ref = _a_running_department(j2, org="Interim Co")
    with monkeypatch.context() as m:
        real = R._handler
        m.setattr(R, "_handler", lambda e, p: None if (p.get("payload") or {}).get("word") == "next" else real(e, p))
        _hear(j2, ref, {"D1": "met", "D2": "not_met"}, findings=[{"id": "F1", "severity": "low", "claim": "Every page names its fees", "item": "D2"}])
        _owner_says_no(W, ref, _asks_of(W, ref, "finding")[0])
    out.append(("a not-met item's finding turned down", ref))
    return out


def _high_finding_on_a_met_reading(R, W, j2, ref, claim="The fees are invented"):
    """Audit read the version, found every item met and one high finding, and said both: the finding is put to the owner."""
    row = _file_reading(j2, ref, {"D1": "met", "D2": "met"}, findings=[{"id": "F1", "severity": "high", "claim": claim, "item": None}])
    R.post(ref, "Audit", "Identity", "inform", {"word": "finding", "claim": claim, "severity": "high", "reading": row["id"],
                                               "findings": [{"page": "index.html", "claim": claim, "severity": "high"}]})
    R.audit_tell(ref, row)
    W.run_until_idle(ref, limit=300)
    return row


def _owner_says_no(W, ref, ask):
    W.decide_ask(ref, ask["id"], False)
    W.run_until_idle(ref, limit=300)


def test_j5_every_end_that_is_not_done_has_a_pending_ask_with_options(j2, monkeypatch):
    """SM-6: the scenario suite's ends of the pursuit. None is done, none is silent: a pending ask, and in it ways out the owner
    can choose, each of a kind the interface names."""
    W, R, J, _, _ = j2
    for what, ref in _end_states(j2, monkeypatch):
        assert J.status(ref)["state"] != "done", what
        pending = [a for a in W.asks(ref) if a["status"] == "pending" and a.get("options")]
        assert len(pending) == 1, (what, [(a["kind"], a["status"]) for a in W.asks(ref)])
        card = pending[0]
        assert card["kind"] == "blocked" and 2 <= len(card["options"]) <= S.OPTIONS_MAX, what
        assert all(S.validate("option", o) == [] and o["kind"] in S.OPTION_KINDS for o in card["options"]), what
        assert "stop" in [o["id"] for o in card["options"]], (what, "a way to stop is always there")
        assert S.validate_record("identity", "ask", card) == [], what
        assert card["thread"], "the card is on a thread, so a choice reaches Identity"
        assert _leave_it_names(card) <= {o["id"] for o in card["options"]}, (what, "the card names a way out its buttons do not offer", card["text"])


def _leave_it_names(card):
    """The ways out that leave an item out which the words of a card name, as option ids: 'leave D2 out of done-when' is leave:D2."""
    return {"leave:" + i for i in re.findall(r"leave (D\d+) out", card["text"])}


def _the_card(W, ref):
    (card,) = _asks_of(W, ref, "blocked")
    return card


def test_j5_a_no_to_a_finding_that_is_not_a_rounds_leaves_the_ways_out_never_a_silent_end(j2, monkeypatch):
    """M9.5: the owner's no to a finding ask ends that correction, and what follows is one card with the ways out: whatever put the
    finding to the owner (a high finding on a reading that met every item, a not-met item's finding while nobody takes a next
    round, a finding a rule says to ask about) and not only a round's correction."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org="High No Co")
    row = _high_finding_on_a_met_reading(R, W, j2, ref)
    (ask,) = _asks_of(W, ref, "finding")
    assert J.status(ref)["state"] != "blocked" and not _asks_of(W, ref, "blocked")
    briefs, rounds = len(W.versions(ref, "Brief")), len(W.rows(ref, "rounds.jsonl"))
    _owner_says_no(W, ref, ask)
    card = _the_card(W, ref)
    assert next(a for a in W.asks(ref) if a["id"] == ask["id"])["status"] == "refused"
    # D1 and D2 are both met and the finding names no item: there is no item to leave out of done-when, so the card offers the two ways
    # that lead somewhere (dropping a met item would not lift a high finding, and the same finding would come back: a loop)
    assert [o["id"] for o in card["options"]] == ["words", "stop"] and J.status(ref)["state"] == "blocked"
    assert card["text"].startswith("You said no to the correction: ") and "fees are invented" in card["text"] and S.validate_record("identity", "ask", card) == []
    assert card["text"].endswith("Say what to change, or stop here.") and "leave" not in card["text"] and not _leave_it_names(card)
    assert len(W.versions(ref, "Brief")) == briefs and len(W.rows(ref, "rounds.jsonl")) == rounds, "nothing is filed, and no round is refused: it is no round's"
    assert not _reached(W, J, ref) and row["id"]
    # the same flow with an item not met, while nobody takes a next round: the item the finding names is the one that can be left out
    ref = _a_running_department(j2, org="Interim No Co")
    _four_items(W, ref)
    real = R._handler
    monkeypatch.setattr(R, "_handler", lambda e, p: None if (p.get("payload") or {}).get("word") == "next" else real(e, p))
    _hear(j2, ref, {"D1": "met", "D2": "met", "D3": "not_met", "D4": "met"}, findings=[{"id": "F1", "severity": "low", "claim": "Every page names its fees", "item": "D3"}])
    _owner_says_no(W, ref, _asks_of(W, ref, "finding")[0])
    card = _the_card(W, ref)
    assert [o["id"] for o in card["options"]] == ["words", "leave:D3", "stop"] and "leave D3 out of done-when" in card["text"] and "D3 not met" in card["why"]
    # a finding a rule says to ask about, with no item named: the reading's last item that is not met
    # (the stub stays: with nobody taking a next round, the rule's ask is the only finding ask; a round filed for real adds its own)
    ref = _a_running_department(j2, org="Rule No Co")
    _four_items(W, ref)
    _tell_reading(j2, ref, _file_reading(j2, ref, {"D1": "met", "D2": "not_met", "D3": "met", "D4": "not_met"},
                                         findings=[{"id": "F1", "severity": "medium", "claim": "Send the offer by email to every subscriber", "item": None}]))
    (ask,) = _asks_of(W, ref, "finding")
    _owner_says_no(W, ref, ask)
    card = _the_card(W, ref)
    assert [o["id"] for o in card["options"]] == ["words", "leave:D4", "stop"] and "D2, D4 not met" in card["why"]


def test_j5_a_met_item_is_no_way_out_of_a_high_finding_it_has_nothing_to_do_with(j2):
    """A high finding on a reading that met D1 and D2 names no item. Leaving D2 out would not lift it (done_claim keeps a high finding
    open whatever the items say) and the same finding would come back as a new ask on the next reading: a way out that loops. So the
    card offers no such button, a choice of it is refused, and the owner's goal keeps both items."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org="Met Item Co")
    _high_finding_on_a_met_reading(R, W, j2, ref)
    _owner_says_no(W, ref, _asks_of(W, ref, "finding")[0])
    card = _the_card(W, ref)
    assert [o["id"] for o in card["options"]] == ["words", "stop"] and [o["label"] for o in card["options"]] == ["Change the plan in my words", "Stop here"]
    assert "D2" not in card["text"] and "D2" not in card["why"] and card["why"] == "a finding is still open"
    with pytest.raises(W.AskError) as refused:
        W.choose_option(ref, card["id"], "leave:D2")
    assert refused.value.code == "UNKNOWN_OPTION"
    assert [i["id"] for i in W.items_of(W.dept(ref))] == ["D1", "D2"], "no met item was dropped from the owner's goal"
    assert _the_card(W, ref)["id"] == card["id"] and J.status(ref)["state"] == "blocked", "the card waits as it was"
    # the two ways that are there are applied as ever: stop stops the department where it is
    W.choose_option(ref, card["id"], "stop")
    W.run_until_idle(ref, limit=100)
    assert W.dept(ref)["stopped"] is True


def test_j5_the_real_flow_a_reader_that_says_every_item_is_met_but_one_high_finding_and_a_no_ends_with_the_ways_out(j2, monkeypatch):
    """The reader says every done-when item is met and reports one high finding: the goal is not reached (M8.4), the finding is
    put to the owner, and their no leaves the department with a card, not a pursuit that stands still with nothing pending."""
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"audit.judge": {"ok": False, "findings": [{"page": "index.html", "claim": "The fees are invented", "severity": "high"}]},
                            "audit.items": _items_met})
    ref = _born(j2, org="Real No Co")
    _stamp_the_pending(W, ref, ("publish",))
    (ask,) = _asks_of(W, ref, "finding")
    assert not _reached(W, J, ref) and J.status(ref)["state"] != "done"
    _owner_says_no(W, ref, ask)
    card = _the_card(W, ref)
    assert J.status(ref)["state"] == "blocked" and "stop" in [o["id"] for o in card["options"]] and S.validate_record("identity", "ask", card) == []
    assert not [a for a in W.asks(ref) if a["status"] == "pending" and a["id"] != card["id"]], "the card is all that waits for the owner"
    W.choose_option(ref, card["id"], "stop")                      # and the way out can be taken
    W.run_until_idle(ref, limit=100)
    assert W.dept(ref)["stopped"] is True


def test_j5_a_no_to_a_finding_after_the_goal_is_reached_asks_nothing_more(j2):
    """After done a finding is a task for the Brief (J3 4a): a no to it ends it, and the department stays done."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org="Done No Co")
    _hear(j2, ref, {"D1": "met", "D2": "met"})
    assert J.status(ref)["state"] == "done"
    R.post(ref, "Audit", "Identity", "inform", {"word": "finding", "claim": "The fees are invented", "severity": "high", "findings": [{"page": "index.html", "claim": "The fees are invented", "severity": "high"}]})
    W.run_until_idle(ref, limit=300)
    (ask,) = _asks_of(W, ref, "finding")
    _owner_says_no(W, ref, ask)
    assert J.status(ref)["state"] == "done" and _asks_of(W, ref, "blocked") == []


def test_j5_a_no_while_the_department_is_stopped_is_taken_on_start_and_leaves_the_card(j2):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org="Stop No Co")
    _high_finding_on_a_met_reading(R, W, j2, ref)
    (ask,) = _asks_of(W, ref, "finding")
    J.stop(ref)
    _owner_says_no(W, ref, ask)
    assert J.status(ref)["state"] == "stopped" and _asks_of(W, ref, "blocked") == [], "Identity applies the no on Start"
    J.resume(ref)
    W.run_until_idle(ref, limit=300)
    assert J.status(ref)["state"] == "blocked" and len(_asks_of(W, ref, "blocked")) == 1


@pytest.mark.parametrize("items", [1, 2])
def test_j3_j5_a_card_names_the_way_that_leaves_an_item_out_only_when_it_offers_it(j2, monkeypatch, items):
    """done-when is never left empty, so with one item a card offers 'Change the plan in my words' and 'Stop here' and its text
    says so (found by a verifier: it read 'leave D1 out of done-when' above buttons that did not leave anything out)."""
    W, R, J, _, _ = j2
    cards = {}
    cards["two rounds that met nothing new"] = _the_card(W, ref := _stalled_department(j2, monkeypatch, org="Stall %d Co" % items, items=items))
    ref = _a_running_department(j2, org="Fact %d Co" % items, items=items)
    _hear(j2, ref, _verdicts(W, ref, "to_confirm"))
    _owner_says(j2, ref, "chat", "just do it")
    cards["a fact the owner does not give"] = _the_card(W, ref)
    ref = _a_running_department(j2, org="Round %d Co" % items, items=items)
    last = W.items_of(W.dept(ref))[-1]["id"]
    _identity_hears(R, ref, _grant_round(R, W, J, monkeypatch, ref, correction="Email every subscriber the new fees", covers=(last,)))
    _owner_says_no(W, ref, _asks_of(W, ref, "finding")[0])
    cards["a correction the owner turned down"] = _the_card(W, ref)
    ref = _a_running_department(j2, org="Finding %d Co" % items, items=items)
    _high_finding_on_a_met_reading(R, W, j2, ref)
    _owner_says_no(W, ref, _asks_of(W, ref, "finding")[0])
    cards["a finding the owner turned down"] = _the_card(W, ref)
    for what, card in cards.items():
        ids = [o["id"] for o in card["options"]]
        if items == 1:
            assert ids == ["words", "stop"] and not _leave_it_names(card) and "leave" not in card["text"], (what, card["text"], ids)
            assert card["text"].endswith(", or stop here."), (what, card["text"])
        elif what == "a finding the owner turned down":
            # a high finding on a reading that met every item names no item: nothing is left out for it, with two items as with one
            assert ids == ["words", "stop"] and not _leave_it_names(card) and "leave" not in card["text"], (what, card["text"], ids)
            assert card["text"].endswith("Say what to change, or stop here."), (what, card["text"])
        else:
            assert ids == ["words", "leave:D2", "stop"] and _leave_it_names(card) == {"leave:D2"}, (what, card["text"], ids)
            assert "leave D2 out of done-when, or stop here." in card["text"], (what, card["text"])
        assert S.validate_record("identity", "ask", card) == [], what


# ---- J6: a goal change reopens the cycle (M9.8) ------------------------------------------------------------------------------
NEW_GOAL = "A phone-first website that teaches algebra and geometry to Class 8 students"


def _rev(W, ref):
    return int(W.dept(ref).get("identity_revision") or 1)


def _says_a_directive(R, monkeypatch, tag, line, audit=True):
    """The model reads the owner's next words as a directive (and Audit's reader keeps saying every item is met)."""
    answers = {"identity.recognise": {"journey": "directive", "why": "a standing change"},
               "identity.rule": {"tag": tag, "line": line, "scope": "standing"}}
    if audit:
        answers.update({"audit.judge": {"ok": True, "findings": []}, "audit.items": _items_met})
    _model(monkeypatch, R, answers)


def test_j2_8_a_stamped_goal_rule_reopens_the_cycle_at_step_1(j2, monkeypatch):
    """J2.8, Q7: Identity takes the owner's words as a goal rule they stamp, and a stamped goal rule starts a new cycle at step 1,
    the record kept, with a goal.revised event that carries the identity's revision before and after."""
    W, R, J, _, _ = j2
    ref = _in_state(j2, monkeypatch, "done")
    old_cycle, old_revision = J.status(ref)["cycle_id"], _rev(W, ref)
    old_goal, kept = W.dept(ref)["goal"], len(J.events(ref))
    assert J.status(ref)["state"] == "done"
    _says_a_directive(R, monkeypatch, "goal", NEW_GOAL)
    W.owner_ask(ref, "From now on, the goal is " + NEW_GOAL)
    W.run_until_idle(ref, limit=300)
    assert J.status(ref)["cycle_id"] == old_cycle and J.status(ref)["state"] == "done", "nothing changes before the stamp"
    _stamp_the_pending(W, ref, ("rule",))
    st = J.status(ref)
    d = W.dept(ref)
    assert d["goal"] == NEW_GOAL and _rev(W, ref) == old_revision + 1
    assert st["cycle_id"] != old_cycle and st["state"] != "done" and st["goal_reached"] is False
    events = J.events(ref)
    assert events[:kept] == events[:kept] and [e for e in events[:kept] if e["action"] == "goal.reached"], "the record is kept: the old goal.reached stands"
    mine = [e for e in events if e["cycle_id"] == st["cycle_id"]]
    assert mine[0]["action"] == "goal.revised" and mine[0]["step"] == 1 and mine[0]["actor"] == "Identity", "a step-1 event opens the new cycle"
    assert mine[0]["payload"]["identity_revision"] == {"from": old_revision, "to": old_revision + 1}
    assert mine[0]["payload"]["goal"] == {"from": old_goal, "to": NEW_GOAL} and mine[0]["payload"]["previous_cycle"] == old_cycle
    assert mine[0]["identity_revision"] == old_revision + 1
    assert [e["step"] for e in mine][:2] == [1, 1] or len(mine) >= 1
    said = [s for s in _said_by_identity(R, ref) if s.startswith("The goal changed from")]
    assert said == ["The goal changed from “%s” to “%s”. The department starts its work again from the top." % (old_goal.rstrip("."), NEW_GOAL)]
    assert _reached(W, J, ref) == [e for e in events[:kept] if e["action"] == "goal.reached"], "no goal is reached on the old goal's reading"


def test_j2_8_the_new_cycle_holds_admissions_until_its_plan_is_registered_and_runs_it_afresh(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _in_state(j2, monkeypatch, "done")
    d = W.dept(ref)
    before = dict(goal=d["goal"], done=d["done"], revision=_rev(W, ref))
    d["goal"] = NEW_GOAL
    W.bump_identity(ref, d)
    assert J.holding(ref) is None, "a done department holds nothing"
    state = J.reopen(ref, was=before)
    assert (state["step"], state["state"], state["previous"]) == (1, "assessing", J.events(ref)[0]["cycle_id"]) and state["revision"] == before["revision"] + 1
    assert J.holding(ref), "nothing is admitted while the new cycle is below step 6"
    assert J.active(ref) and J.status(ref)["round"] is None
    # the department goes on to register a plan under the new cycle, and runs it
    R._j2_went_on(ref, "test")
    W.run_until_idle(ref, limit=400)
    new = [e["action"] for e in J.events(ref) if e["cycle_id"] == state["cycle_id"]]
    assert new[0] == "goal.revised" and "proposal.requested" in new and "workflow.registered" in new, new
    assert J.holding(ref) is None and J.status(ref)["step"] >= 6
    assert len(W.dept(ref)["workflows"]) == 2, "the registered line is kept, and the new plan is registered beside it"


def test_j2_8_a_stamped_change_to_done_when_reopens_it_too(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _in_state(j2, monkeypatch, "done")
    old_cycle, revision = J.status(ref)["cycle_id"], _rev(W, ref)
    _says_a_directive(R, monkeypatch, "goal", DONE_WORDS[len("From now on, "):])
    W.owner_ask(ref, DONE_WORDS)
    W.run_until_idle(ref, limit=300)
    assert J.status(ref)["cycle_id"] == old_cycle, "the ask is not the change"
    _stamp_the_pending(W, ref, ("done_items",))
    st = J.status(ref)
    assert st["cycle_id"] != old_cycle and len(W.items_of(W.dept(ref))) == 2
    first = next(e for e in J.events(ref) if e["cycle_id"] == st["cycle_id"])
    assert first["action"] == "goal.revised" and first["payload"]["identity_revision"]["from"] == revision
    assert "done" in first["payload"] and "Done-when changed" in first["summary"]
    assert any(s.startswith("Done-when changed from") for s in _said_by_identity(R, ref))


def test_j2_8_after_done_a_task_is_the_briefs_and_starts_no_cycle(j2, monkeypatch):
    """Q8: keep J3 4a. The owner's task after done is filed in the Brief and the registered line runs it; no new cycle."""
    W, R, J, _, _ = j2
    ref = _in_state(j2, monkeypatch, "done")
    cycle, briefs = J.status(ref)["cycle_id"], len(W.versions(ref, "Brief"))
    W.owner_ask(ref, "Add a page on parking.")
    W.run_until_idle(ref, limit=300)
    assert J.status(ref)["cycle_id"] == cycle and J.status(ref)["state"] == "done"
    assert len(W.versions(ref, "Brief")) == briefs + 1 and "Add a page on parking." in W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"])["brief.md"]
    assert not [e for e in J.events(ref) if e["action"] == "goal.revised"]


def test_j2_8_a_rule_that_is_not_about_the_goal_and_an_answer_to_a_question_reopen_nothing(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org="Rules Co")
    cycle = J.status(ref)["cycle_id"]
    _says_a_directive(R, monkeypatch, "ask", NEVER, audit=False)
    W.owner_ask(ref, NEVER)
    W.run_until_idle(ref, limit=300)
    _stamp_the_pending(W, ref, ("rule",))
    assert any(r["line"] == NEVER for r in W.dept(ref)["rules"]) and J.status(ref)["cycle_id"] == cycle
    assert not [e for e in J.events(ref) if e["action"] == "goal.revised"]
    # a department still at its first step, asking: the stamp that answers its question goes on with that cycle
    waiting = _in_state(j2, monkeypatch, "waiting", "Waiting Again Co")
    first = J.status(waiting)["cycle_id"]
    _stamp_the_pending(W, waiting, ("rule", "done_items"))
    assert J.status(waiting)["cycle_id"] == first


def test_j2_8_a_goal_stamped_while_stopped_changes_the_cycle_when_the_department_starts_again(j2, monkeypatch):
    """A stopped department's card can still be answered (S10), and Identity applies the stamp on Start: the cycle that begins
    then is the new one, and nothing started while it was stopped."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org="Stopped Co")
    old = J.status(ref)["cycle_id"]
    _says_a_directive(R, monkeypatch, "goal", NEW_GOAL, audit=False)
    W.owner_ask(ref, "From now on, the goal is " + NEW_GOAL)
    W.run_until_idle(ref, limit=300)
    J.stop(ref)
    (ask,) = _asks_of(W, ref, "rule")
    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=300)
    assert J.status(ref)["cycle_id"] == old and J.status(ref)["state"] == "stopped", "Identity applies the stamp on Start"
    J.resume(ref)
    W.run_until_idle(ref, limit=400)
    st = J.status(ref)
    assert st["cycle_id"] != old and W.dept(ref)["goal"] == NEW_GOAL
    new = [e["action"] for e in J.events(ref) if e["cycle_id"] == st["cycle_id"]]
    assert new[0] == "goal.revised" and "proposal.requested" in new, new


def test_j2_8_a_cycle_reopened_while_stopped_stays_stopped_and_begins_on_start(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org="Stopped Again Co")
    old = J.status(ref)["cycle_id"]
    J.stop(ref)
    d = W.dept(ref)
    before = dict(goal=d["goal"], done=d["done"], revision=_rev(W, ref))
    d["goal"] = NEW_GOAL
    W.bump_identity(ref, d)
    st = J.reopen(ref, was=before)
    assert st["cycle_id"] != old and (st["state"], st["step"], st["was"]) == ("stopped", 1, "assessing")
    W.run_until_idle(ref, limit=300)
    assert [e["action"] for e in J.events(ref) if e["cycle_id"] == st["cycle_id"]] == ["goal.revised"], "nothing starts while it is stopped"
    J.resume(ref)
    W.run_until_idle(ref, limit=400)
    assert "proposal.requested" in [e["action"] for e in J.events(ref) if e["cycle_id"] == st["cycle_id"]]


def _a_goal_stamped_while_questions_are_open(j2, monkeypatch, org):
    """The owner's goal rule waits for the stamp; Audit's reading then leaves a fact only the owner has, and Identity asks about it;
    the owner stamps the goal rule with that question open. Returns the department, the question, and the cycle it was asked in."""
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org=org)
    _says_a_directive(R, monkeypatch, "goal", NEW_GOAL, audit=False)
    W.owner_ask(ref, "From now on, the goal is " + NEW_GOAL)
    W.run_until_idle(ref, limit=300)
    _hear(j2, ref, {"D1": "met", "D2": "to_confirm"})
    (q,) = _asks_of(W, ref, "j2_identity")
    old = J.status(ref)["cycle_id"]
    assert (q["missing"], q["cycle_id"], J.status(ref)["open_question"]["id"], len(_asks_of(W, ref, "rule"))) == ("fact", old, q["id"], 1)
    _stamp_the_pending(W, ref, ("rule",))
    assert J.status(ref)["cycle_id"] != old, "the stamped goal rule started a new cycle"
    return ref, q, old


def _cycle_now(J, ref):
    st = J.status(ref)
    return {k: st[k] for k in ("cycle_id", "step", "state", "round")}


def test_j6_a_reopen_retires_the_question_of_the_cycle_it_ends(j2, monkeypatch):
    """J6: what Identity asked under the old goal is moot under the new one. A question on a fact that was open when the goal rule
    was stamped is closed as replaced, the new cycle does not wait on it, and an answer that comes later moves nothing."""
    W, R, J, _, _ = j2
    ref, q, old = _a_goal_stamped_while_questions_are_open(j2, monkeypatch, "Reopen Question Co")
    assert next(a for a in W.asks(ref) if a["id"] == q["id"])["status"] == "replaced"
    assert J.status(ref)["open_question"] is None and not J.waiting_on_owner(ref) and J.status(ref)["cycle_id"] != old
    before, briefs = _cycle_now(J, ref), len(W.versions(ref, "Brief"))
    R.request(ref, "The price list is 500 rupees a month", answers=q["id"])
    W.run_until_idle(ref, limit=300)
    assert _cycle_now(J, ref) == before and len(W.versions(ref, "Brief")) == briefs, "the old question's answer moves nothing and files nothing"
    assert next(a for a in W.asks(ref) if a["id"] == q["id"])["status"] == "replaced"
    assert any(s.startswith("That question belonged to the goal before it changed") for s in _said_by_identity(R, ref)), "and the owner is told"


def test_j6_an_answer_to_a_question_of_an_earlier_cycle_moves_nothing_whatever_the_ask_says(j2, monkeypatch):
    """Whatever left a question of the old cycle open (an ask written before this fix), fact_answered closes it and moves nothing:
    it used to set the new cycle to 'pursuing', step 8, on the old goal's question."""
    W, R, J, _, _ = j2
    ref, q, old = _a_goal_stamped_while_questions_are_open(j2, monkeypatch, "Reopen Stale Co")
    W._put_ask(ref, dict(next(a for a in W.asks(ref) if a["id"] == q["id"]), status="pending", decided=None))
    before, briefs = _cycle_now(J, ref), len(W.versions(ref, "Brief"))
    assert before["step"] != 8 or before["state"] != "pursuing", before
    R.request(ref, "The price list is 500 rupees a month", answers=q["id"])
    W.run_until_idle(ref, limit=300)
    assert _cycle_now(J, ref) == before and len(W.versions(ref, "Brief")) == briefs
    assert next(a for a in W.asks(ref) if a["id"] == q["id"])["status"] == "replaced"


def test_j6_an_answer_to_a_doubt_of_an_earlier_cycle_asks_adaptation_nothing(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref, q, old = _a_goal_stamped_while_questions_are_open(j2, monkeypatch, "Reopen Doubt Co")
    doubt = dict(W.j2_identity_ask("Where should the order go?", old, "plan", "the plan rests on something only you can say", ["plan"], False),
                 doubt={"engine": "Site", "doubt": DOUBT, "shown": DOUBT, "fallback": FALLBACK_SAYS, "line": None})
    W._put_ask(ref, doubt)
    before, briefs, lines = _cycle_now(J, ref), len(W.versions(ref, "Brief")), len(_line_requests(R, ref))
    R.request(ref, ANSWER, answers=doubt["id"])
    W.run_until_idle(ref, limit=300)
    assert _cycle_now(J, ref) == before and len(W.versions(ref, "Brief")) == briefs and len(_line_requests(R, ref)) == lines
    assert next(a for a in W.asks(ref) if a["id"] == doubt["id"])["status"] == "replaced"


def test_j6_a_finding_ask_and_a_blocked_card_of_the_old_cycle_are_retired_too(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _a_running_department(j2, org="Reopen Cards Co")
    _high_finding_on_a_met_reading(R, W, j2, ref)
    (finding,) = _asks_of(W, ref, "finding")
    _owner_says_no(W, ref, finding)
    (card,) = _asks_of(W, ref, "blocked")
    _high_finding_on_a_met_reading(R, W, j2, ref, claim="A price is wrong")
    (second,) = _asks_of(W, ref, "finding")
    R.post(ref, "Adaptation", "Identity", "inform", {"word": "conflict", "engines": ENGINES, "source": "library", "words": "w", "why": "no room", "for": "x-old"})
    W.run_until_idle(ref, limit=300)
    (conflict,) = _asks_of(W, ref, "conflict")
    old = J.status(ref)["cycle_id"]
    _says_a_directive(R, monkeypatch, "goal", NEW_GOAL, audit=False)
    W.owner_ask(ref, "From now on, the goal is " + NEW_GOAL)
    W.run_until_idle(ref, limit=300)
    _stamp_the_pending(W, ref, ("rule",))
    assert J.status(ref)["cycle_id"] != old
    status = {a["id"]: a["status"] for a in W.asks(ref)}
    assert (status[finding["id"]], status[card["id"]], status[second["id"]], status[conflict["id"]]) == ("refused", "replaced", "replaced", "replaced")
    # what is not Identity's question of the old cycle stands: a publish ask, and the new cycle's own asks
    assert all(a["status"] != "replaced" for a in W.asks(ref) if a["kind"] in ("publish", "rule", "engine", "done_items"))
