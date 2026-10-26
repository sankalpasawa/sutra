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


# ---- M3.3 ------------------------------------------------------------------------------------------------------------
WHO = "Who are the site's visitors?"
FAMILIES = "families in Pune who order birthday cakes"


def _work(W, ref):
    return [r["engine"] for r in W.runs(ref) if not r.get("system")]


def _reader(reads, met="families"):
    """Identity's standard as an AI reads it: the goal names whom the site is for only once the words say families."""
    def enough(prompt):
        reads.append(prompt)
        if met in prompt.split("THE OWNER'S WORDS: ", 1)[1].split("WHAT ROOT ASKED", 1)[0].lower():
            return {"enough": True, "missing": [], "question": "", "why": "the goal names the bakery and whom it is for"}
        return {"enough": False, "missing": ["goal"], "question": WHO, "why": "the goal names no one the site is for"}
    return enough


def test_m3_3_words_the_standard_finds_thin_get_a_question_and_the_answer_is_read_again(j2, monkeypatch):
    """A department that starts on words its standard finds thin, or an answer taken without reading the standard again,
    must fail."""
    W, R, J, _, _ = j2
    reads = []
    _model(monkeypatch, R, {"identity.enough": _reader(reads)})
    ref = _born(j2)
    q = J.status(ref)["open_question"]
    assert (q["text"], q["standard"], q["points"], q["missing"]) == (WHO, True, ["goal"], "goal")
    assert q["why"] == "the goal names no one the site is for"
    assert len(reads) == 1 and BAKERY in reads[0] and "Identity's standard" in reads[0]     # read from its completeness file
    assert "proposal.requested" not in _actions(J, ref) and _work(W, ref) == []
    assert J.status(ref)["state"] == "waiting" and J.holding(ref)
    assert WHO in _said(R, ref)
    # the line names its card, and the chat leaves it to the card, which says the question once (M0.6)
    line = next(p for p in R.board(ref) if (p["payload"] or {}).get("done") == WHO)
    assert line["payload"]["card"] == q["id"]
    assert WHO not in [t["line"] for t in R.chat_view(ref)["turns"]]

    W.owner_ask(ref, FAMILIES)                                               # said in the chat: it answers the question
    W.run_until_idle(ref, limit=300)
    assert len(reads) == 2 and FAMILIES in reads[1] and BAKERY in reads[1]   # read again, the first words with it
    ask = next(a for a in W.asks(ref) if a["id"] == q["id"])
    assert (ask["status"], ask["answered"]) == ("stamped", FAMILIES)
    assert _actions(J, ref).count("ask.answered") == 1
    requested = next(e for e in J.events(ref) if e["action"] == "proposal.requested")
    assert requested["step"] == 2 and J.status(ref)["open_question"] is None
    assert FAMILIES in W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"])["brief.md"]
    assert "Thank you. The identity is clear now; the department starts." in _said(R, ref)


def test_m3_3_still_too_little_is_asked_again_through_the_answer_box(j2, monkeypatch):
    """FI1.1: an answer that still leaves the standard unmet, taken as met, must fail."""
    W, R, J, _, _ = j2
    reads = []
    _model(monkeypatch, R, {"identity.enough": _reader(reads)})
    ref = _born(j2)
    first = J.status(ref)["open_question"]["id"]
    client = _client()
    got = client.post("/api/dept/%s/j2/answer" % ref, json={"text": "nice people"})
    assert got.status_code == 200 and got.json()["open_question"] is None
    W.run_until_idle(ref, limit=300)
    second = J.status(ref)["open_question"]
    assert second and second["id"] != first and second["standard"] and len(reads) == 2
    assert _actions(J, ref).count("identity.questioned") == 2 and "proposal.requested" not in _actions(J, ref)
    client.post("/api/dept/%s/j2/answer" % ref, json={"text": FAMILIES})
    W.run_until_idle(ref, limit=300)
    assert len(reads) == 3 and next(e for e in J.events(ref) if e["action"] == "proposal.requested")["step"] == 2


def test_m3_3_a_question_j1_already_answered_is_not_asked(j2, monkeypatch):
    """FI1.2: Identity asking what Root asked and the owner answered in J1 must fail."""
    W, R, J, _, _ = j2
    converse = []

    def ask_once(prompt):
        converse.append(1)
        return {"verdict": "ask", "question": WHO} if len(converse) == 1 else {"verdict": "clear", "question": ""}
    _model(monkeypatch, R, {"setup.converse": ask_once,
                            "identity.enough": {"enough": False, "missing": ["goal"], "question": WHO, "why": "the goal names no one"}})
    root = j2[3].found_structure("Bakery Co", owner="Sankalp")["root"]
    W.owner_ask(root, "A bakery site")
    W.run_until_idle(root, limit=300)
    W.owner_ask(root, FAMILIES)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    assert (WHO, FAMILIES) in R._j1_said(W.dept(ref))
    W.run_until_idle(ref, limit=300)
    assert not [a for a in W.asks(ref) if a["kind"] == "j2_identity"]
    assert "identity.questioned" not in _actions(J, ref)
    assert next(e for e in J.events(ref) if e["action"] == "proposal.requested")["step"] == 2


@pytest.mark.parametrize("via", ["chat", "answer box"])
def test_m3_3_just_do_it_starts_step_2_and_the_tell_names_the_defaults(j2, monkeypatch, via):
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"identity.enough": {"enough": False, "missing": ["goal", "items"], "question": WHO, "why": "the goal names no one"}})
    ref = _born(j2)
    assert J.status(ref)["open_question"]["standard"]
    if via == "chat":
        W.owner_ask(ref, "just do it")
    else:
        assert _client().post("/api/dept/%s/j2/answer" % ref, json={"text": "Just do it."}).status_code == 200
    W.run_until_idle(ref, limit=300)
    assert next(e for e in J.events(ref) if e["action"] == "proposal.requested")["step"] == 2
    tell = [s for s in _said(R, ref) if s.startswith("Just doing it.")]
    assert tell == ["Just doing it. Defaults used: the goal as you said it; the done-when items Root drafted. The department starts."]
    assert J.status(ref)["open_question"] is None
    assert "just do it" not in W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"])["brief.md"].lower()


def test_m3_3_just_do_it_fills_what_the_record_lacks_from_the_kind(j2):
    W, R, _, _, _ = j2
    W.create("dref-hurry", "Hurry Website", None)
    d = W.dept("dref-hurry")
    d.update({"goal": "", "done_items": [], "done": "", "rules": [{"tag": "go", "line": "Work inside the record"}, {"line": "untagged"}]})
    W.save_dept("dref-hurry", d)
    used = R._standard_defaults("dref-hurry", ["rules", "goal", "items", "invented"])
    d = W.dept("dref-hurry")
    assert used == ["the kind's goal: A live website for Hurry Website", "D1, the kind's done line: Every page checked and live",
                    "the kind's rules", "what nobody gave stays out, to be confirmed"]
    assert d["goal"] == "A live website for Hurry Website" and [i["id"] for i in d["done_items"]] == ["D1"]
    assert all(r.get("tag") in ("go", "ask", "refuse", "always") for r in d["rules"]) and len(d["rules"]) == 4    # kept, and the kind's
    assert d["identity_revision"] == 2 and R._standard_gaps(d) == []


def test_m3_3_the_standards_covering_holds_the_shape_and_what_code_can_read(j2):
    W, R, _, _, _ = j2
    W.create("dref-std", "Std Website", None)
    _, s = R.step_def("identity.enough")
    c = R.CHECK[s["check"]]
    ctx = {"dept": W.dept("dref-std")}
    assert c(ctx, s, None, {"enough": True, "missing": [], "question": ""})["ok"]
    assert c(ctx, s, None, {"enough": False, "missing": ["goal"], "question": WHO})["ok"]
    assert not c(ctx, s, None, {"enough": False, "missing": ["goal"], "question": ""})["ok"]
    assert not c(ctx, s, None, {"enough": False, "missing": [], "question": WHO})["ok"]
    assert not c(ctx, s, None, {"enough": False, "missing": ["vibes"], "question": WHO})["ok"]
    assert not c(ctx, s, None, {"enough": "yes", "missing": []})["ok"]
    gap = dict(W.dept("dref-std"), owner="", rules=[{"line": "no tag here"}])
    got = c({"dept": gap}, s, None, {"enough": True, "missing": [], "question": ""})
    assert not got["ok"] and got["notes"] == ["read as enough, but the record has a rule with no tag, no owner"]
    # the draft under the AI is today's presence check, read by code
    assert R.d_identity_enough({"dept": gap}, s, None)["missing"] == ["rules", "owner"]
    assert R.d_identity_enough(ctx, s, None) == {"enough": True, "missing": [], "question": "", "why": "read by code: every point is on the record"}


def test_m3_3_the_standard_is_read_only_inside_the_cycle(j2, monkeypatch):
    """Identity's standard read for a department outside its J2 cycle (the AI called for nothing) must fail."""
    W, R, J, _, _ = j2
    reads = []
    _model(monkeypatch, R, {"identity.enough": _reader(reads)})
    monkeypatch.setenv("J2_FLOW_V1", "0")
    ref = _born(j2)
    assert reads == [] and not [a for a in W.asks(ref) if a["kind"] == "j2_identity"]
    rows = [r for r in R.step_rows(ref) if r["step"] == "identity.enough"]
    assert rows and all(r["by"] == R.SKIPPED for r in rows)


# ---- M3.4 ------------------------------------------------------------------------------------------------------------
NEVER = "Never publish without asking me"


def _rules_gap(j2, words=None):
    """A department whose rule says no tag: Identity's question is on the rules. With `words`, its first words are filed
    first, so later words said in the chat answer the question."""
    W, R, J, _, _ = j2
    d, _ = W.create("dref-rules", "Rules Website", None)
    d.update({"events": [{"kind": "j2_ready", "route": "template"}], "rules": [{"id": "r1", "line": "Work inside the record"}]})
    W.save_dept("dref-rules", d)
    J.start("dref-rules")
    if words:
        W.give_goal("dref-rules", words)
        W.run_until_idle("dref-rules", limit=300)
    q = J.status("dref-rules")["open_question"]
    assert q and q["missing"] == "rules"
    return "dref-rules", q


def _rule_asks(W, ref):
    return [a for a in W.asks(ref) if a["kind"] == "rule"]


@pytest.mark.parametrize("via", ["answer box", "chat"])
def test_m3_4_a_rule_given_as_an_answer_keeps_its_tag_through_the_rule_ask(j2, via):
    """The answer written straight into the rules tagged go, or a rule that waits for no stamp, must fail."""
    W, R, J, _, _ = j2
    ref, q = _rules_gap(j2, words=None if via == "answer box" else BAKERY)
    before = W.dept(ref)
    if via == "answer box":
        assert _client().post("/api/dept/%s/j2/answer" % ref, json={"text": NEVER}).status_code == 200
    else:
        W.owner_ask(ref, NEVER)
    W.run_until_idle(ref, limit=300)
    asks = _rule_asks(W, ref)
    assert len(asks) == 1 and asks[0]["status"] == "pending"
    assert (asks[0]["tag"], asks[0]["line"], asks[0]["scope"], asks[0]["answers"]) == ("ask", NEVER, "standing", q["id"])
    assert asks[0]["text"] == "A rule, as understood (it asks you first, from now on): " + NEVER     # its tag and scope restated
    assert W.dept(ref)["rules"] == before["rules"]                                   # nothing is written before the stamp
    assert next(a for a in W.asks(ref) if a["id"] == q["id"])["status"] == "stamped" and J.status(ref)["open_question"] is None
    assert asks[0]["text"] in _said(R, ref)

    W.decide_ask(ref, asks[0]["id"], True)
    W.run_until_idle(ref, limit=300)
    d = W.dept(ref)
    assert [(r["tag"], r["line"]) for r in d["rules"]] == [("ask", NEVER)]               # the untagged rule gave way to it
    assert d["identity_revision"] == int(before.get("identity_revision") or 1) + 1
    assert R._standard_gaps(d) == [] and J.status(ref)["open_question"] is None
    if via == "chat":
        # the first words were filed: with nothing missing now, the department starts (step 2)
        assert next(e for e in J.events(ref) if e["action"] == "proposal.requested")["step"] == 2


def test_m3_4_a_refused_rule_answer_asks_the_question_again(j2):
    W, R, J, _, _ = j2
    ref, q = _rules_gap(j2)
    J.answer(ref, NEVER)
    W.run_until_idle(ref, limit=300)
    W.decide_ask(ref, _rule_asks(W, ref)[0]["id"], False)
    W.run_until_idle(ref, limit=300)
    again = J.status(ref)["open_question"]
    assert again and again["missing"] == "rules" and again["id"] != q["id"]
    assert W.dept(ref)["rules"] == [{"id": "r1", "line": "Work inside the record"}]


DONE_WORDS = "From now on, the site is done when shoppers can order a cake on WhatsApp"


def test_m3_4_a_stamped_change_to_the_items_leaves_the_goal_as_it_was(j2, monkeypatch):
    """A done-when change filed under the goal's tag, which a stamp writes over the goal, must fail."""
    W, R, J, _, _ = j2
    ref = _born(j2)
    _model(monkeypatch, R, {"identity.recognise": {"journey": "directive", "why": "it says when the site is done"},
                            "identity.rule": {"tag": "goal", "line": DONE_WORDS[len("From now on, "):], "scope": "standing"}})
    goal, items = W.dept(ref)["goal"], W.dept(ref)["done_items"]
    rev = int(W.dept(ref).get("identity_revision") or 1)
    W.owner_ask(ref, DONE_WORDS)
    W.run_until_idle(ref, limit=300)
    assert not [a for a in _rule_asks(W, ref) if a["status"] == "pending"]           # not a goal ask
    ask = next(a for a in W.asks(ref) if a["kind"] == "done_items")
    assert ask["status"] == "pending" and [i["id"] for i in ask["items"]] == ["D1", "D2"]
    assert ask["items"][1] == {"id": "D2", "text": "Shoppers can order a cake on WhatsApp", "how": "model", "level": "outcome"}
    assert ask["text"] == "Done when, as understood: add D2 Shoppers can order a cake on WhatsApp, read by an AI. The goal stays as it is"
    assert W.dept(ref)["done_items"] == items                                        # nothing changes before the stamp

    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=300)
    d = W.dept(ref)
    assert d["goal"] == goal and not d.get("goals")                                  # the goal is as it was
    assert d["done_items"] == items + [{"id": "D2", "text": "Shoppers can order a cake on WhatsApp", "how": "model", "level": "outcome"}]
    assert d["done"] == W.done_line(d["done_items"]) and d["identity_revision"] == rev + 1
    assert "Done when is now: D1 %s; D2 Shoppers can order a cake on WhatsApp." % items[0]["text"] in _said(R, ref)


def test_m3_4_the_done_items_ask_is_one_shape_and_keeps_what_is_to_confirm(j2):
    W = j2[0]
    W.create("dref-items4", "Items Website", None)
    d = W.dept("dref-items4")
    d.update({"done_items": [{"id": "D1", "text": "A", "how": "code", "level": "target"}, {"id": "D2", "text": "B", "how": "person", "level": "outcome"},
                             {"id": "D3", "text": "C", "how": "model", "level": "outcome"}],
              "to_be_confirmed": [{"item": "D3", "why": "nobody gave it"}]})
    W.save_dept("dref-items4", d)
    items = [i for i in W.items_of(d) if i["id"] != "D2"]                            # leave D2 out
    ask = W.done_items_ask("Leave D2 out", items, "the owner asked for less")
    assert (ask["kind"], ask["status"], [i["id"] for i in ask["items"]]) == ("done_items", "pending", ["D1", "D2"])
    assert ask["items"][1] == {"id": "D2", "text": "C", "how": "model", "level": "outcome", "confirm": "nobody gave it"}
    goal = W.dept("dref-items4")["goal"]
    out = W.apply_done_items("dref-items4", ask)
    assert out["goal"] == goal and out["done"] == "A; C" and out["to_be_confirmed"] == [{"item": "D2", "why": "nobody gave it"}]
    assert out["done_items"] == [{"id": "D1", "text": "A", "how": "code", "level": "target"}, {"id": "D2", "text": "C", "how": "model", "level": "outcome"}]


# ---- M3.5 ------------------------------------------------------------------------------------------------------------
FAULT = "the line reaches outside without a rule"


def _blocked_dept(j2, monkeypatch, items=True):
    """Root's check refuses the plan three times, so it is blocked: a department born with three done-when items."""
    W, R, J, _, _ = j2
    monkeypatch.setattr(R, "_root_check", lambda ref, d, engines, source: [FAULT])
    shaped = dict(SHAPED, goal="A phone-first website for Bakery Co, a bakery in Pune, where customers see every cake")
    _model(monkeypatch, R, {"setup.shape": dict(shaped, done_items=[dict(i) for i in ITEMS]) if items else shaped})
    ref = _born(j2)
    assert J.status(ref)["state"] == "blocked"
    assert _actions(J, ref).count("workflow.blocked") == J.REPAIRS + 1
    return ref


def _card(W, ref):
    return next(a for a in W.asks(ref) if a["kind"] == "blocked" and a["status"] == "pending")


def test_m3_5_a_blocked_plan_is_an_ask_with_options(j2, monkeypatch):
    """A blocked plan told in a line with nothing to press (a dead end) must fail."""
    W, R, J, _, _ = j2
    ref = _blocked_dept(j2, monkeypatch)
    card = _card(W, ref)
    assert [o["id"] for o in card["options"]] == ["words", "leave:D3", "stop"]
    assert all(set(o) == {"id", "label", "cost"} and o["label"] and o["cost"] for o in card["options"])
    assert [o["label"] for o in card["options"]] == ["Change the plan in my words", "Leave D3 out", "Stop here"]
    assert (card["title"], card["who"], card["why"], card["chosen"]) == ("The plan could not be approved.", "Root, at its review", FAULT, None)
    assert card["if_nothing"] and card["thread"]
    assert any("refused the plan 3 times" in s for s in _said(R, ref))                  # what Identity said is the card's text
    turns = [t["line"] for t in R.chat_view(ref)["turns"]]
    assert not [t for t in turns if "refused the plan 3 times" in t]                   # said once, on its card
    assert [a["id"] for a in R.chat_view(ref)["asks"] if a["kind"] == "blocked"] == [card["id"]]
    # a department with one item has nothing to leave out: done-when is never left empty
    assert R._left_out({"done_items": [{"id": "D1", "text": "x"}]}, "") is None


def test_m3_5_from_blocked_new_words_reopen_step_2(j2, monkeypatch):
    """New words that leave the cycle blocked, or reopen it with Root's repairs used up, must fail."""
    W, R, J, _, _ = j2
    ref = _blocked_dept(j2, monkeypatch)
    card = _card(W, ref)
    monkeypatch.setattr(R, "_root_check", lambda ref, d, engines, source: [])           # Root's check holds from now on
    seen = len(J.events(ref))
    W.owner_ask(ref, "Make it a simple one-page site that shows the cakes")
    W.run_until_idle(ref, limit=300)
    after = J.events(ref)[seen:]
    requested = next(e for e in after if e["action"] == "proposal.requested")
    assert requested["step"] == 2
    assert "workflow.registered" in [e["action"] for e in after] and J.status(ref)["state"] == "running"
    shut = next(a for a in W.asks(ref) if a["id"] == card["id"])
    assert shut["status"] == "chosen" and shut["chosen"]["id"] == "words"               # the card goes quiet


def test_m3_5_each_option_is_applied_by_code_and_an_unknown_one_is_409(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _blocked_dept(j2, monkeypatch)
    client = _client()
    card = _card(W, ref)
    url = "/api/native/%s/asks/%s" % (ref, card["id"])
    got = client.post(url, json={"option": "raise"})
    assert got.status_code == 409 and got.json()["detail"]["code"] == "UNKNOWN_OPTION"
    assert client.post(url, json={"approve": True}).status_code == 400                   # it takes an option, never a stamp
    got = client.post(url, json={"option": "words", "text": "  "})
    assert got.status_code == 400 and got.json()["detail"]["code"] == "EMPTY_ANSWER"
    assert _card(W, ref)["status"] == "pending"

    # leave an item out: a done_items ask, stamped by that one click; the goal is as it was; step 2 again
    goal, seen = W.dept(ref)["goal"], len(J.events(ref))
    assert client.post(url, json={"option": "leave:D3"}).status_code == 200
    assert client.post(url, json={"option": "leave:D3"}).status_code == 200              # the same choice again is the same answer
    got = client.post(url, json={"option": "stop"})
    assert got.status_code == 409 and got.json()["detail"]["code"] == "ALREADY_HANDLED"
    W.run_until_idle(ref, limit=300)
    d = W.dept(ref)
    assert [i["id"] for i in d["done_items"]] == ["D1", "D2"] and d["goal"] == goal and d["to_be_confirmed"] == []
    left = next(a for a in W.asks(ref) if a["kind"] == "done_items")
    assert (left["status"], left["answers"]) == ("stamped", card["id"])
    after = J.events(ref)[seen:]
    assert "The owner chose: Leave D3 out." in [e["summary"] for e in after]
    assert next(e for e in after if e["action"] == "proposal.requested")["step"] == 2

    # blocked again (Root still refuses): the words option takes the owner's words; stop stops the department
    W.run_until_idle(ref, limit=300)
    card = _card(W, ref)
    assert [o["id"] for o in card["options"]] == ["words", "leave:D2", "stop"]
    seen = len(J.events(ref))
    assert client.post("/api/native/%s/asks/%s" % (ref, card["id"]), json={"option": "words", "text": "Only the cakes page"}).status_code == 200
    W.run_until_idle(ref, limit=300)
    assert next(e for e in J.events(ref)[seen:] if e["action"] == "proposal.requested")["step"] == 2
    assert "Only the cakes page" in W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"])["brief.md"]
    card = _card(W, ref)
    assert client.post("/api/native/%s/asks/%s" % (ref, card["id"]), json={"option": "stop"}).status_code == 200
    W.run_until_idle(ref, limit=300)
    assert W.dept(ref)["stopped"] is True and J.status(ref)["state"] == "stopped"


def test_m3_5_an_options_ask_is_one_shape(j2):
    W = j2[0]
    a = W.options_ask("blocked", "Stuck", [W.option("a", "A", "costs a"), W.option("b", "B", "costs b"), W.option("c", "C", "c"),
                                           W.option("d", "D", "d")], why="because")
    assert [o["id"] for o in a["options"]] == ["a", "b", "c"] and a["chosen"] is None and a["status"] == "pending"
    assert a["why"] == "because" and a["kind"] == "blocked"


# ---- M3.6 ------------------------------------------------------------------------------------------------------------
def test_m3_6_the_plain_words_check(j2):
    _, R, _, _, _ = j2
    assert R.plain_faults("The plan is set: Plan -> Write. Priority said yes to it.") == []
    assert R.plain_faults("Priority granted it and it passed Root's check") == ["grant or counter"]
    assert R.plain_faults("Priority countered the plan") == ["grant or counter"]
    assert R.plain_faults("Step J2.b is open; see FI1") == ["a J2 code"]
    assert R.plain_faults("Priority: say yes to the plan") == ["a function addressing another"]
    assert R.plain_faults("Your cakes are ready at the counter", owners="pick them up at the counter") == []   # the owner's own word
    assert R.plain_faults("D2 and Live site v3 in Round 2") == []                                          # names, never codes
    W = j2[0]
    W.create("dref-plain", "Plain Website", None)
    out = R._plainly("dref-plain", {"word": "line", "done": "The plan is set: Plan. Priority granted it and it passed Root's check."})
    assert out["done"] == "The plan is set: Plan. Priority said yes to it and it passed Root's check."
    assert out["plain"] == [{"key": "done", "faults": ["grant or counter"], "by": "said again"}]
    out = R._plainly("dref-plain", {"word": "answer", "answer": "Adaptation: J2.b says so", "done": "Adaptation: J2.b says so"})
    assert out["answer"] == R.PLAIN_TEMPLATE["answer"] and out["done"] == R.PLAIN_TEMPLATE[""]
    assert [f["by"] for f in out["plain"]] == ["template", "template"]
    assert R._plainly("dref-plain", {"word": "request", "done": "Filed in the Brief."}) == {"word": "request", "done": "Filed in the Brief."}


def _scenarios(j2, monkeypatch):
    """The J2 scenarios, each a department: born and run offline; Priority says no and Identity rules it runs; Priority
    says no and Identity puts the plan to the owner; Root's check refuses the plan until it is blocked; Identity's
    standard asks; a rule given as an answer."""
    W, R, J, _, _ = j2
    refs = [_born(j2)]
    _model(monkeypatch, R, {"priority.bargain": {"answer": "reject", "why": "no room"},
                            "identity.close": {"ruling": "run", "why": "the goal cannot be met without a site"}})
    refs.append(_born(j2, org="Ruled Co"))
    _model(monkeypatch, R, {"priority.bargain": {"answer": "reject", "why": "no room in the envelope today"}})
    refs.append(_born(j2, org="Asked Co"))
    real = R._root_check
    monkeypatch.setattr(R, "_root_check", lambda ref, d, engines, source: [FAULT])
    _model(monkeypatch, R, {"setup.shape": dict(SHAPED, goal="A website for Blocked Co where customers see every cake",
                                                done_items=[dict(i) for i in ITEMS])})
    refs.append(_born(j2, org="Blocked Co"))
    monkeypatch.setattr(R, "_root_check", real)
    _model(monkeypatch, R, {"identity.enough": {"enough": False, "missing": ["goal"], "question": WHO, "why": "the goal names no one"}})
    refs.append(_born(j2, org="Standard Co"))
    ref, _ = _rules_gap(j2, words=BAKERY)
    W.owner_ask(ref, NEVER)
    W.run_until_idle(ref, limit=300)
    refs.append(ref)
    return refs


def test_m3_6_one_voice_in_plain_words_on_every_board(j2, monkeypatch):
    """A post to the owner from any function but Identity (SM-4), or a tell that carries grant, counter, a J2 code or
    one function addressing another, must fail."""
    W, R, J, _, _ = j2
    refs = _scenarios(j2, monkeypatch)
    assert any(a["kind"] == "conflict" for a in W.asks(refs[2])) and J.status(refs[3])["state"] == "blocked"
    boards = set(refs) | {W.dept(r).get("root") for r in refs if W.dept(r).get("root")}
    told = 0
    for b in boards:
        for p in R.board(b):
            if "Owner" not in p["dst"]:
                continue
            assert p["src"] == "Identity", "%s spoke to the owner on %s: %s" % (p["src"], b, p["payload"])
            pl = p["payload"] or {}
            owners = R._owners_words(b, pl)
            for k in R.PLAIN_KEYS:
                if isinstance(pl.get(k), str):
                    assert R.plain_faults(pl[k], owners) == [], "%s on %s: %s" % (k, b, pl[k])
                    told += 1
    assert told > 20
    said = [s for r in refs for s in _said(R, r)]
    assert any("Priority said yes to it and it passed Root's check" in s for s in said)        # said again, plainly
    assert any("did not say yes to the plan" in s for s in said)
    assert not [a for r in refs for a in W.asks(r) if R.plain_faults(a.get("text"), R._owners_words(r, a))]  # the asks' words too


def test_m3_6_a_functions_chat_box_says_the_words_go_to_identity(j2):
    import pathlib
    src = (pathlib.Path(__file__).parent / "static" / "js" / "22-website.js").read_text(encoding="utf-8")
    assert '"Say it to Identity about " + name' in src and '"Say it to Identity"' in src


# ---- M3.7 ------------------------------------------------------------------------------------------------------------
def test_m3_7_identitys_pane_reads_its_one_record(j2, monkeypatch):
    """A pane that reads the standard from somewhere other than the record, drops the items' how and level, or shows a
    rule without where it came from, must fail."""
    import json
    W, R, J, _, F = j2
    _model(monkeypatch, R, {"setup.shape": dict(SHAPED, goal="A website for Bakery Co where customers see every cake",
                                                done_items=[dict(i) for i in ITEMS]),
                            "priority.bargain": {"answer": "reject", "why": "no room"},
                            "identity.close": {"ruling": "run", "why": "the goal cannot be met without a site"}})
    ref = _born(j2)
    j = F.function(ref, "identity")["j2"]
    assert [r["id"] for r in j["standard"]["rows"]] == ["goal", "items", "rules", "owner_budget", "invented"]
    assert [r["says"] for r in j["standard"]["rows"]] == [s for _, s, _ in R.STANDARD_POINTS]
    assert [r["state"] for r in j["standard"]["rows"]] == ["met", "met", "met", "met", "to_confirm"]
    assert j["standard"]["rows"][4]["note"] == "to confirm with you: D3, nobody gave the reviews"
    assert j["goal"] == W.dept(ref)["goal"]
    assert j["done_items"] == [{"id": "D1", "text": ITEMS[0]["text"], "how": "code", "level": "target", "confirm": None},
                               {"id": "D2", "text": ITEMS[1]["text"], "how": "model", "level": "outcome", "confirm": None},
                               {"id": "D3", "text": ITEMS[2]["text"], "how": "person", "level": "outcome", "confirm": "nobody gave the reviews"}]
    assert [(r["tag"], r["by"]) for r in j["rules"]] == [(r["tag"], "the template") for r in W.KINDS["website"]["rules"]]
    assert j["open_question"] is None
    assert len(j["conflicts"]) == 1
    c = j["conflicts"][0]
    assert (c["who"], c["ruling"], c["ruled"], c["asked_you"]) == ("Adaptation and Priority did not agree", "run", "it runs", False)
    assert c["plan"] and "the goal cannot be met without a site" in c["why"]
    assert "charter" not in json.dumps(j).lower()
    # a rule the owner gave says it is theirs, and when
    d = W.dept(ref)
    d["rules"].append(W.rule_row("refuse", "Never show a price that is not in my list", "never show a price that is not in my list"))
    W.save_dept(ref, d)
    mine = F.function(ref, "identity")["j2"]["rules"][-1]
    assert (mine["tag"], mine["by"]) == ("refuse", "yours") and mine["since"]


def test_m3_7_an_open_question_on_the_standard_is_on_the_pane(j2, monkeypatch):
    W, R, J, _, F = j2
    _model(monkeypatch, R, {"identity.enough": {"enough": False, "missing": ["goal"], "question": WHO, "why": "the goal names no one"}})
    ref = _born(j2)
    j = F.function(ref, "identity")["j2"]
    assert (j["open_question"]["text"], j["open_question"]["standard"], j["open_question"]["points"]) == (WHO, True, ["goal"])
    assert j["standard"]["rows"][0] == {"id": "goal", "says": "The goal names what and for whom", "state": "not_met", "note": "Identity asks you"}
    assert j["standard"]["met"] is False
    # the record's own gap is read by code, in the owner's words
    d = W.dept(ref)
    d["owner"] = ""
    W.save_dept(ref, d)
    row = F.function(ref, "identity")["j2"]["standard"]["rows"][3]
    assert (row["state"], row["note"]) == ("not_met", "the record has no owner")
