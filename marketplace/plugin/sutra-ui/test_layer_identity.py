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


#: the bodies identity/v1 holds of its own: the handler Hear a doubt (I5) and the two steps that tell it the owner's answer
OWN = {"identity_doubt", "identity_read", "identity_file"}


def test_i1_each_name_the_recipe_uses_is_a_reference_to_the_body_engine_runtime_holds_but_the_versions_own(home):
    import engine_runtime as R
    legacy = {"code": R.CODE, "prompt": R.PROMPT, "draft": R.DRAFT, "check": R.CHECK}
    assert {n for n, f in V1.CODE.items() if not hasattr(f, "legacy")} == OWN
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
    assert "Unless you say, %s. Answer" % v1.FALLBACK in ask["text"] and "email to the shop?" in ask["text"]
    # a doubt a model wrote in the bargain's words is put right, or said in the plainest words that still ask it
    ref = _born(j2, BAKERY, "Plain Co")
    _doubts(R, ref, doubt="Should Priority grant the cake counter its own page?", fallback="the cake counter shares the home page")
    W.run_until_idle(ref, limit=300)
    ask = _plan_asks(W, ref)[0]
    assert not re.search(r"\b(?:grant|counter)", ask["text"], re.I) and v1.SOMETHING in ask["text"] and "Unless you say, %s." % v1.FALLBACK in ask["text"]
    assert "just do it" in ask["text"] and R.plain_faults(ask["text"], R._owners_words(ref, {})) == []


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
