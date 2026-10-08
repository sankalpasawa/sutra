"""Behavioral contract for the published J1 department-birth journey."""
import importlib
import json

import pytest


@pytest.fixture
def j1(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)

    import website_dept as W
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime as R

    for module in (E, W, org2_apply, founding, R):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, founding


def _root(j1, name="Acme Learning"):
    W, _, founding = j1
    root = founding.found_structure(name, owner="Sankalp")["root"]
    return W, root


def _children(W, root):
    return [d for d in W.list_depts() if d.get("parent") == root]


def test_j1_s3_s4_vague_words_ask_one_question_and_survive_reload(j1):
    """Removing persisted history or emitting two questions must break this test."""
    W, root = _root(j1)
    W.owner_ask(root, "Build me a website")
    W.run_until_idle(root, limit=200)

    assert _children(W, root) == []
    # The owner's words are the Request's version; Sutra's question is written by the converse step's covering onto
    # the durable conversation, and rides in the next version when the owner answers.
    filed = json.loads(W.read_files(root, "Request", W.latest(root, "Request")["v"])["request.json"])
    assert [m["text"] for m in filed["messages"] if m["actor"] == "user"] == ["Build me a website"]
    record = W._read(W.ddir(root) / "j1-state.json", None)
    assert [m["actor"] for m in record["messages"]] == ["user", "root"]
    assert record["status"] == "waiting"
    assert record["outstanding_question"]
    assert record["outstanding_question"].count("?") == 1
    said = [p for p in j1[1].board(root) if p["src"] == "Identity" and (p["payload"] or {}).get("word") == "question"]
    assert [p["payload"]["done"] for p in said] == [record["outstanding_question"]]

    importlib.reload(W)
    assert W._read(W.ddir(root) / "j1-state.json", None) == record

    W.owner_ask(root, "It teaches algebra to Class 8 students so that they practise every week")
    W.run_until_idle(root, limit=200)
    answered = json.loads(W.read_files(root, "Request", W.latest(root, "Request")["v"])["request.json"])
    assert [m["actor"] for m in answered["messages"]] == ["user", "root", "user"]
    assert len(_children(W, root)) == 1


def test_j1_s1_to_s7_clear_request_builds_once_without_default_stamp(j1):
    """Restoring the universal setup stamp or omitting handoff context must fail."""
    W, root = _root(j1)
    words = "Build a website that teaches algebra to Class 8 students"
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=200)

    children = _children(W, root)
    assert len(children) == 1, {"runs": [(r["engine"], r["status"], r.get("what")) for r in W.runs(root)], "asks": W.asks(root)}
    child = children[0]
    assert {s["name"] for s in W.map_view(child["ref"])["systems"]} == {
        "Identity", "Priority", "Coordination", "Adaptation", "Audit"
    }
    assert child["template_ref"] == {"id": "department/website", "version": 1}
    assert not child["founding"]["operation_id"].endswith(":latest")
    assert [m["text"] for m in child["initial_goal_context"]["messages"] if m["actor"] == "user"] == [words]
    assert not [a for a in W.asks(root) if a["kind"] == "setup" and a["status"] == "pending"]
    assert [e["kind"] for e in child["events"]] == ["j2_ready"]
    assert W.versions(child["ref"], "Site plan") == [], "J1 must not execute J2 business work"

    W.run_until_idle(root, limit=200)
    assert len(_children(W, root)) == 1
    assert [e["kind"] for e in W.dept(child["ref"])["events"]] == ["j2_ready"]


def test_j1_1_and_j1_2_answer_then_just_do_it_are_one_conversation(j1):
    """Starting a new Request for each answer or continuing after just-do-it is a bug."""
    W, root = _root(j1)
    W.owner_ask(root, "Build me a website")
    W.run_until_idle(root, limit=200)
    W.owner_ask(root, "For students")
    W.run_until_idle(root, limit=200)
    assert _children(W, root) == []

    W.owner_ask(root, "just do it")
    W.run_until_idle(root, limit=200)
    child = _children(W, root)[0]
    messages = child["initial_goal_context"]["messages"]
    assert [m["text"] for m in messages if m["actor"] == "user"] == [
        "Build me a website", "For students", "just do it"
    ]
    assert child["initial_goal_context"]["defaults_applied"]


def test_j1_4_no_fitting_template_uses_explicit_organic_route(j1):
    """Silently forcing an unrelated website/default template must fail."""
    W, root = _root(j1, "Northstar")
    W.owner_ask(root, "Create a bespoke climate-risk simulation laboratory for coastal cities")
    W.run_until_idle(root, limit=200)

    child = _children(W, root)[0]
    assert child["kind"] == "organic"
    assert child["template_ref"] is None
    assert child["engines"] == []
    assert child["events"] == [{"kind": "j2_ready", "route": "organic"}]


def test_j1_6_matching_ask_rule_waits_before_creating(j1):
    """Ignoring an explicit inherited birth rule must fail."""
    W, root = _root(j1)
    d = W.dept(root)
    d["rules"].append({"id": "rule-birth", "version": 3, "tag": "ask", "line": "Ask me before you make anything"})
    W.save_dept(root, d)

    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)

    assert _children(W, root) == []
    asks = [a for a in W.asks(root) if a["kind"] == "setup" and a["status"] == "pending"]
    assert len(asks) == 1
    assert asks[0]["rule"] == {"id": "rule-birth", "version": 3}

    W.decide_ask(root, asks[0]["id"], True)
    W.run_until_idle(root, limit=200)
    assert len(_children(W, root)) == 1

    # A retried approval decision is idempotent.
    W.decide_ask(root, asks[0]["id"], True)
    W.run_until_idle(root, limit=200)
    assert len(_children(W, root)) == 1


def test_j1_6_inherited_ask_rule_with_plain_wording_is_effective(j1):
    """An ancestor ask rule must not depend on birth keywords to govern Setup."""
    W, _, _ = j1
    _, root = _root(j1, "Inherited Rules")
    import placement_engine as E
    org = W.dept(root)["org"]["ref"]
    charter = E.charters_for(org)[0]
    sidecar = E.load_sidecar(charter["id"])
    sidecar["rules"] = [{"tag": "ask", "line": "Require my approval first"}]
    E.save_sidecar(charter["id"], sidecar)

    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)
    asks = [a for a in W.asks(root) if a["kind"] == "setup" and a["status"] == "pending"]
    assert len(asks) == 1
    assert asks[0]["rule"]["id"].startswith(charter["id"] + ":rule:")
    assert _children(W, root) == []
    W.decide_ask(root, asks[0]["id"], True)
    W.run_until_idle(root, limit=200)
    assert len(_children(W, root)) == 1


def test_j1_6_unrelated_ask_rule_does_not_gate_department_birth(j1):
    """A publish-only approval rule must not block department creation."""
    W, root = _root(j1)
    d = W.dept(root)
    d["rules"].append({
        "id": "rule-publish",
        "version": 1,
        "tag": "ask",
        "line": "Ask before publishing externally",
    })
    W.save_dept(root, d)

    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)

    assert len(_children(W, root)) == 1
    assert not [a for a in W.asks(root) if a["kind"] == "setup" and a["status"] == "pending"]


def test_j1_3_retry_message_and_compatible_repeat_do_not_duplicate(j1):
    """A transport retry or compatible repeated setup must keep one child."""
    W, root = _root(j1)
    words = "Build a website that teaches algebra to Class 8 students"
    W.owner_ask(root, words, message_id="msg-stable-1")
    W.owner_ask(root, words, message_id="msg-stable-1")
    W.run_until_idle(root, limit=200)
    first = _children(W, root)[0]

    W.owner_ask(root, "Start a department for a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)
    assert [d["ref"] for d in _children(W, root)] == [first["ref"]]


def test_j1_5_two_departments_create_only_first_and_leave_suggestion(j1):
    """Treating one turn as authority to create two children must fail."""
    W, root = _root(j1)
    W.owner_ask(root, "Build a website for tutors and a separate sales CRM for the team")
    W.run_until_idle(root, limit=200)

    children = _children(W, root)
    assert len(children) == 1
    assert children[0]["kind"] == "website"
    offer = {"label": "sales CRM for the team", "words": "Set up another department: sales CRM for the team"}
    assert children[0]["initial_goal_context"]["suggested_next"] == offer
    assert "sales CRM" not in children[0]["initial_goal_context"].get("goal", "")
    tells = [p["payload"] for p in j1[1].board(root) if (p["payload"] or {}).get("word") == "department"]
    assert len(tells) == 1 and tells[0]["offer"] == offer
    # The chip's words are a request for a department, not words for the first one.
    W.owner_ask(root, offer["words"])
    W.run_until_idle(root, limit=200)
    assert len(_children(W, root)) == 2


def test_j1_9_completed_request_state_survives_reload_without_rebirth(j1):
    """Losing the completion marker on restart must not replay founding."""
    W, root = _root(j1)
    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)
    child_ref = _children(W, root)[0]["ref"]

    importlib.reload(W)
    W.run_until_idle(root, limit=200)
    assert [d["ref"] for d in _children(W, root)] == [child_ref]


def test_j1_7_unanswered_question_stays_waiting_without_a_child(j1):
    """A timeout must not guess an answer or discard the Request."""
    W, root = _root(j1)
    W.owner_ask(root, "Build me a website")
    W.run_until_idle(root, limit=200)

    state = W._read(W.ddir(root) / "j1-state.json", {})
    assert state["status"] == "waiting"
    assert state["outstanding_question"]
    assert _children(W, root) == []


def test_j1_8_model_away_retries_three_times_then_retains_request(j1, monkeypatch):
    """Unbounded retry or loss of the Request after model failure must fail."""
    W, R, _ = j1
    _, root = _root(j1)
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    R.WAITS = (0, 0, 0)
    R.MODEL = lambda prompt, step: (None, 0.0, "away")

    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)

    attempts = [r for r in W.runs(root) if r["engine"] == "Setup" and r["status"] == "waiting"]
    assert len(attempts) == 3
    assert len([a for a in W.asks(root) if a["kind"] == "model" and a["status"] == "pending"]) == 1
    # The model never answered, so nothing was decided: the Request is kept as it was said, still open.
    state = W._read(W.ddir(root) / "j1-state.json", {})
    assert state["status"] == "collecting"
    assert [m["text"] for m in state["messages"]] == ["Build a website that teaches algebra to Class 8 students"]
    assert _children(W, root) == []


def test_j1_9_interrupted_founding_reconciles_the_same_child(j1, monkeypatch):
    """A crash after the child record is saved must not strand or duplicate it."""
    W, _, founding = j1
    _, root = _root(j1)
    real_give_goal = W.give_goal
    calls = {"n": 0}

    def fail_once(ref, goal):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated process loss")
        return real_give_goal(ref, goal)

    monkeypatch.setattr(W, "give_goal", fail_once)
    context = {"id": "j1-reconcile", "messages": [{"id": "m1", "actor": "user", "text": "Build a tutor website"}]}
    with pytest.raises(RuntimeError, match="simulated process loss"):
        founding.spawn(root, "Acme Website", "website", "Build a tutor website", goal_context=context,
                       template_ref={"id": "department/website", "version": 1})

    made = founding.spawn(root, "Acme Website", "website", "Build a tutor website", goal_context=context,
                          template_ref={"id": "department/website", "version": 1})
    assert made["created"] is True
    assert len(_children(W, root)) == 1
    child = W.dept(made["ref"])
    assert len([e for e in child["events"] if e["kind"] == "j2_ready"]) == 1
    assert W.requests(made["ref"])


def test_j1_feature_flag_restores_the_legacy_birth_gate(j1, monkeypatch):
    """The rollback switch must stop new automatic births without corrupting old records."""
    W, root = _root(j1, "Rollback Org")
    monkeypatch.setenv("J1_FLOW_V1", "0")
    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)
    assert _children(W, root) == []
    assert len([a for a in W.asks(root) if a["kind"] == "setup" and a["status"] == "pending"]) == 1


def test_j1_2_just_do_it_without_any_intent_still_asks_for_the_goal(j1):
    """Defaults may fill details, but they may not invent the department's purpose."""
    W, root = _root(j1, "Empty Intent")
    W.owner_ask(root, "just do it")
    W.run_until_idle(root, limit=200)
    assert _children(W, root) == []
    assert W._read(W.ddir(root) / "j1-state.json", {})["outstanding_question"]


def test_j1_9_crash_before_final_tell_replays_that_tell_once(j1, monkeypatch):
    """A child persisted before Root speaks must reconcile to one birth summary."""
    W, R, _ = j1
    _, root = _root(j1, "Tell Recovery")
    real_post = R.post
    failed = {"active": True}

    def lose_process(ref, src, dst, msg_type, payload=None, **kwargs):
        if (payload or {}).get("word") == "department" and failed["active"]:
            raise RuntimeError("simulated loss before final tell")
        return real_post(ref, src, dst, msg_type, payload, **kwargs)

    monkeypatch.setattr(R, "post", lose_process)
    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)
    assert len(_children(W, root)) == 1
    assert not [p for p in R.board(root) if (p.get("payload") or {}).get("word") == "department"]

    monkeypatch.setattr(R, "post", real_post)
    W.run_until_idle(root, limit=200)
    tells = [p for p in R.board(root) if (p.get("payload") or {}).get("word") == "department"]
    assert len(tells) == 1
    assert "final_tell" in W.dept(_children(W, root)[0]["ref"])["founding"]["checkpoints"]


# ---- the AI inside the converse and shape steps (S-24, and what a live model answered on 2026-10-07) ----------------
def _model(monkeypatch, R, answers):
    """A model that is a function: `answers` maps a step id to what the model says for it (a dict, or a callable taking
    the prompt). Every other step falls to its draft, as it does offline."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    seen = []

    def model(prompt, step):
        seen.append((step["id"], prompt))
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"

    monkeypatch.setattr(R, "MODEL", model)
    return seen


LIVE_SHAPE = {"name": "Acme Learning Algebra Website", "kind": "website",
              "goal": "Build a website that teaches algebra to Class 8 students.",
              "purpose": "A live website that teaches algebra to Class 8 students.",
              "route": "template", "template_ref": {"id": "website", "version": "1"}}


def test_j1_s5_the_shape_a_live_model_gave_makes_the_department(j1, monkeypatch):
    """Checking the model's own template reference again must fail: on 2026-10-07 this exact answer made nothing."""
    W, R, _ = j1
    _, root = _root(j1)
    _model(monkeypatch, R, {"setup.converse": {"verdict": "clear", "question": ""}, "setup.shape": dict(LIVE_SHAPE)})
    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)

    children = _children(W, root)
    assert [c["name"] for c in children] == ["Acme Learning Algebra Website"]
    assert children[0]["kind"] == "website"
    assert children[0]["template_ref"] == {"id": "department/website", "version": 1}
    assert W._read(W.ddir(root) / "j1-state.json", {})["status"] == "completed"


def test_j1_s3_the_questions_are_the_models_not_a_list_in_code(j1, monkeypatch):
    """Putting the questions back in code, or asking when the model says clear, must fail."""
    W, R, _ = j1
    _, root = _root(j1)
    asked = iter(["Who are the students, and what should they be able to do after a week?", "Should it be free to use?"])
    turns = {"n": 0}

    def converse(prompt):
        turns["n"] += 1
        if turns["n"] <= 2:
            return {"verdict": "ask", "question": next(asked)}
        return {"verdict": "clear", "question": ""}

    seen = _model(monkeypatch, R, {"setup.converse": converse, "setup.shape": dict(LIVE_SHAPE)})
    # Words the plain offline test would call clear: the model still decides, and it asks.
    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)
    state = W._read(W.ddir(root) / "j1-state.json", {})
    assert state["outstanding_question"] == "Who are the students, and what should they be able to do after a week?"
    assert _children(W, root) == []

    W.owner_ask(root, "Class 8, and they should solve linear equations")
    W.run_until_idle(root, limit=200)
    assert W._read(W.ddir(root) / "j1-state.json", {})["outstanding_question"] == "Should it be free to use?"
    assert _children(W, root) == []

    W.owner_ask(root, "yes, free")
    W.run_until_idle(root, limit=200)
    assert len(_children(W, root)) == 1
    prompts = [p for sid, p in seen if sid == "setup.converse"]
    assert len(prompts) == 3
    # The third prompt carries the whole conversation, Sutra's own questions included.
    assert "SUTRA: Should it be free to use?" in prompts[2] and "OWNER: yes, free" in prompts[2]
    questions = [p["payload"]["done"] for p in R.board(root) if (p["payload"] or {}).get("word") == "question"]
    assert questions == ["Who are the students, and what should they be able to do after a week?", "Should it be free to use?"]


def test_j1_2_just_do_it_overrules_a_model_that_keeps_asking(j1, monkeypatch):
    """Letting the model ask after the owner said just do it must fail."""
    W, R, _ = j1
    _, root = _root(j1)
    _model(monkeypatch, R, {"setup.converse": {"verdict": "ask", "question": "And for whom?"}, "setup.shape": dict(LIVE_SHAPE)})
    W.owner_ask(root, "A website about algebra")
    W.run_until_idle(root, limit=200)
    assert _children(W, root) == []
    W.owner_ask(root, "just do it")
    W.run_until_idle(root, limit=200)
    assert len(_children(W, root)) == 1
    tell = [p["payload"]["done"] for p in R.board(root) if (p["payload"] or {}).get("word") == "department"]
    assert len(tell) == 1 and "Defaults used:" in tell[0]


def test_j1_s4_an_answer_reaches_the_open_question_when_a_department_already_exists(j1):
    """Routing an answer to the only child must fail: it is Sutra's question that is open."""
    W, R, _ = j1
    _, root = _root(j1)
    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)
    first = _children(W, root)
    assert len(first) == 1

    W.owner_ask(root, "Set up another department")
    W.run_until_idle(root, limit=200)
    assert W._read(W.ddir(root) / "j1-state.json", {})["status"] == "waiting"
    before = len(W.requests(first[0]["ref"]))

    W.owner_ask(root, "It is a system to track the chemical inventory for the science team so that nothing runs out")
    W.run_until_idle(root, limit=200)
    assert len(W.requests(first[0]["ref"])) == before          # the answer was not handed to the first department
    assert len(_children(W, root)) == 2


def test_j1_s5_a_shape_the_library_cannot_build_tells_the_owner_and_closes_the_request(j1, monkeypatch):
    """A failed Setup that leaves the chat on 'shaping the department' must fail."""
    W, R, _ = j1
    _, root = _root(j1)
    _model(monkeypatch, R, {"setup.converse": {"verdict": "clear", "question": ""},
                            "setup.shape": {"name": "Acme Thing", "kind": "spaceship", "goal": "Fly"}})
    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)

    assert _children(W, root) == []
    assert W._read(W.ddir(root) / "j1-state.json", {})["status"] == "failed"
    told = [p for p in R.board(root) if p["src"] == "Identity" and "could not set the department up" in str((p["payload"] or {}).get("done"))]
    assert len(told) == 1
    # The next words start a new Request; they are not appended to the failed one.
    monkeypatch.setattr(R, "MODEL", None)
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    W.owner_ask(root, "Build a website that teaches algebra to Class 8 students")
    W.run_until_idle(root, limit=200)
    state = W._read(W.ddir(root) / "j1-state.json", {})
    assert len([m for m in state["messages"] if m["actor"] == "user"]) == 1
    assert len(_children(W, root)) == 1


def test_j1_6_a_refused_preview_closes_the_request(j1):
    """Appending the next words to a refused Request must fail: its preview showed the words twice."""
    W, root = _root(j1)
    d = W.dept(root)
    d["rules"].append({"id": "rule-birth", "version": 3, "tag": "ask", "line": "Ask me before you make anything"})
    W.save_dept(root, d)
    words = "Build a website that teaches algebra to Class 8 students"
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=200)
    ask = [a for a in W.asks(root) if a["kind"] == "setup" and a["status"] == "pending"][0]
    W.decide_ask(root, ask["id"], False)
    W.run_until_idle(root, limit=200)
    assert _children(W, root) == []
    assert W._read(W.ddir(root) / "j1-state.json", {})["status"] == "refused"

    W.owner_ask(root, words)
    W.run_until_idle(root, limit=200)
    state = W._read(W.ddir(root) / "j1-state.json", {})
    assert [m["text"] for m in state["messages"] if m["actor"] == "user"] == [words]
    fresh = [a for a in W.asks(root) if a["kind"] == "setup" and a["status"] == "pending"]
    assert len(fresh) == 1 and fresh[0]["text"].count(words) == 1


def test_j1_7_the_birth_is_told_once_when_setup_the_sweep_and_the_next_due_read_race(j1):
    """Looking at the board and posting outside one lock must fail (2 of 13 foundings told the birth twice)."""
    import threading
    W, R, founding = j1
    _, root = _root(j1)
    made = founding.spawn(root, "Acme Learning Website", "website", "Teach algebra", template_ref={"id": "department/website", "version": 1})
    child = W.dept(made["ref"])
    child["pending_final_tell"] = {"word": "department", "done": "Acme Learning Website is set up.", "dept": made["ref"],
                                   "from": "Acme Learning Website", "operation": made["operation_id"]}
    W.save_dept(made["ref"], child)
    start = threading.Barrier(8)

    def go():
        start.wait()
        R._reconcile_j1_tells(root)

    threads = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len([p for p in R.board(root) if (p.get("payload") or {}).get("word") == "department"]) == 1
