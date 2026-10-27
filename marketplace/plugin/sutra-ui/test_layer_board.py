"""Questions between engines, and Audit's spot checks (PRD M4.9 and M8.7, W3-BOARD): the board/1 format as charged runs, and the
sporadic, unannounced look at the engines' state.

  B1  with SUTRA_BOARD_QUESTIONS on, a work step's answer may carry a question {to, about, text}; question_is_bounded says no, with
      its reason, to a second question by the engine in the slot, a target not earlier in the line, a target that has not filed
      and an about already answered (that answer is reused); questions.json holds {schema: board/1, entries}, written only with the
      flag on: with it off no questions.json exists, and the step's answer is what it was
"""
import importlib
import json

import pytest

import layer_schema as S
import layers
import layers.contract as C
from layers.coordination import v1 as COORD

WEBSITE = "Build a website that teaches algebra to Class 8 students"
LINE = ["Plan", "Write", "Check", "Publish"]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    monkeypatch.delenv("SUTRA_BOARD_QUESTIONS", raising=False)
    return tmp_path


@pytest.fixture
def j2(home):
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


def _born(j2, org="Acme Learning"):
    """A department as a person makes one, settled: Plan, Write and Check ran, and Publish waits for the owner's stamp."""
    W, _, _, founding, _ = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, WEBSITE)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _model(monkeypatch, R, say, usd=0.01):
    """A model that is a function of (step id, prompt): what it says is a dict, or None to fall to the step's draft. Every call is
    kept: [(step id, prompt)]."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    calls = []

    def model(prompt, step):
        calls.append((step["id"], prompt))
        got = say(step["id"], prompt)
        return (None, 0.0, "offline") if got is None else (got, usd, "model")

    monkeypatch.setattr(R, "MODEL", model)
    return calls


def _write_again(W, R, ref, slot="Write@site-plan.v9"):
    """Write's run on the Site plan the department holds, in a slot of its own."""
    return R.run_engine(ref, "Write", dict(W.latest(ref, "Site plan")), slot)


def _page(prompt):
    words = " ".join("word%d" % i for i in range(80))
    return {"title": "A page", "body_html": "<h1>A page</h1><p>%s</p>" % words}


ASK = {"to": "Plan", "about": "the page list", "text": "Which pages does the site have?"}


def _asks_once(ask=None):
    """Write's page step asks Plan about the page list the first time it is asked, and never again (the rerun has the board)."""
    state = {"asked": False}

    def say(step, prompt):
        if step == "write.page":
            if not state["asked"]:
                state["asked"] = True
                return dict(_page(prompt), question=dict(ASK, **(ask or {})))
            return _page(prompt)
        if step == "coord.answer":
            return {"answer": "Home, About and Timetable"}
        return None
    return say


def _row(**more):
    return dict({"id": "Q-1", "asked_by": "Write", "slot": "Write@site-plan.v1", "to": "Plan", "about": "the page list", "status": "answered"}, **more)


# ---- B1: the question, bounded ---------------------------------------------------------------------------------------------
def test_b1_each_refusal_has_its_reason_and_a_question_in_bounds_has_none():
    bound = COORD.question_bounds
    assert bound([], LINE, ["Plan"], "Write", "Write@s.v1", "Plan", "the page list") == (True, None, None)
    assert bound([], LINE, ["Plan"], "Write", "Write@s.v1", "", "x")[:2] == (False, "it names no engine to ask")
    assert bound([_row(slot="Write@s.v1", status="refused")], LINE, ["Plan"], "Write", "Write@s.v1", "Plan", "the colours")[:2] == \
        (False, "a second question by Write in this slot")
    assert bound([_row(slot="Write@s.v0")], LINE, ["Plan"], "Write", "Write@s.v1", "Plan", "the colours")[0] is True, "another slot, another allowance"
    assert bound([], LINE, ["Plan", "Write"], "Write", "Write@s.v1", "Check", "x")[:2] == (False, "Check is not earlier in the line than Write")
    assert bound([], LINE, ["Plan", "Write"], "Write", "Write@s.v1", "Write", "x")[:2] == (False, "Write is not earlier in the line than Write")
    assert bound([], LINE, ["Plan"], "Write", "Write@s.v1", "Research", "x")[:2] == (False, "Research is not earlier in the line than Write")
    assert bound([], LINE, [], "Write", "Write@s.v1", "Plan", "x")[:2] == (False, "Plan has not filed anything yet")
    assert bound([_row()], LINE, ["Plan"], "Check", "Check@p.v1", "Plan", "The list of the pages")[:3] == \
        (False, "already answered in Q-1", "Q-1")
    assert bound([_row(status="unanswered")], LINE, ["Plan"], "Check", "Check@p.v1", "Plan", "the page list")[0] is True, "only an answer is reused"


def test_b1_with_the_flag_off_no_questions_file_exists_and_the_prompt_is_as_it_was(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2)
    seen = _model(monkeypatch, R, _asks_once())
    row = _write_again(W, R, ref)
    assert row["status"] == "ok" and not (W.ddir(ref) / "questions.json").exists()
    assert not any("THE BOARD" in p or "BOARD (answered" in p for _, p in seen)
    assert COORD.entries(ref) == [] and not [r for r in R.board(ref) if (r.get("payload") or {}).get("word") == "question"]
    assert COORD.board_on({"dept": W.dept(ref)}) is False


def test_b1_a_root_and_a_department_off_the_runtime_ask_nothing(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2)
    monkeypatch.setenv("SUTRA_BOARD_QUESTIONS", "1")
    assert COORD.board_on({"dept": W.dept(ref)}) is True and COORD.board_on({"dept": W.dept(ref)}, {"id": "coord.answer"}) is False
    assert COORD.board_on({"dept": W.dept(W.dept(ref)["root"])}) is False and COORD.board_on({"dept": dict(W.dept(ref), runtime=1)}) is False


def test_b1_with_the_flag_on_a_question_is_filed_in_questions_json_as_board_1(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2)
    monkeypatch.setenv("SUTRA_BOARD_QUESTIONS", "1")
    seen = _model(monkeypatch, R, _asks_once())
    assert _write_again(W, R, ref)["status"] == "ok"
    doc = json.loads((W.ddir(ref) / "questions.json").read_text(encoding="utf-8"))
    assert doc["schema"] == "board/1" and len(doc["entries"]) == 1
    e = doc["entries"][0]
    assert S.validate("coordination.question", e) == []
    assert (e["id"], e["asked_by"], e["to"], e["about"], e["question"], e["status"]) == \
        ("Q-1", "Write", "Plan", "the page list", "Which pages does the site have?", "open")
    assert e["slot"] == "Write@site-plan.v9" and e["used_by"] == []
    prompts = [p for s, p in seen if s == "write.page"]
    assert prompts and all("THE BOARD" in p and "ENGINES YOU MAY ASK: Plan" in p for p in prompts), "the format is in the step's prompt"
    assert "question" not in json.dumps(W.read_files(ref, "Pages", W.latest(ref, "Pages")["v"])), "the question is not part of the work"


@pytest.mark.parametrize("ask,why", [
    ({"to": "Check", "about": "the colours", "text": "Which colours?"}, "Check is not earlier in the line than Write"),
    ({"to": "Research", "about": "the colours", "text": "Which colours?"}, "Research is not earlier in the line than Write"),
    ({"to": "Write", "about": "the colours", "text": "Which colours?"}, "Write is not earlier in the line than Write"),
])
def test_b1_a_question_for_an_engine_that_is_not_before_the_asker_is_said_no_to_with_its_reason(j2, monkeypatch, ask, why):
    W, R, J, _, _ = j2
    ref = _born(j2)
    monkeypatch.setenv("SUTRA_BOARD_QUESTIONS", "1")
    _model(monkeypatch, R, _asks_once(ask))
    assert _write_again(W, R, ref)["status"] == "ok", "the asker takes its normal path"
    rows = COORD.entries(ref)
    assert len(rows) == 1 and rows[0]["status"] == "refused" and rows[0]["reason"] == why
    assert S.validate("coordination.question", rows[0]) == []


def test_b1_a_question_that_names_nobody_is_not_filed_as_asked_of_anybody(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2)
    monkeypatch.setenv("SUTRA_BOARD_QUESTIONS", "1")
    _model(monkeypatch, R, _asks_once({"to": ""}))
    assert _write_again(W, R, ref)["status"] == "ok"
    assert COORD.entries(ref) == [], "no engine named: it is no question"


def test_b1_a_target_that_has_not_filed_is_said_no_to(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2)
    monkeypatch.setenv("SUTRA_BOARD_QUESTIONS", "1")
    monkeypatch.setattr(COORD, "_filed", lambda r, line: [])
    _model(monkeypatch, R, _asks_once())
    assert _write_again(W, R, ref)["status"] == "ok"
    assert [(e["status"], e["reason"]) for e in COORD.entries(ref)] == [("refused", "Plan has not filed anything yet")]


def test_b1_a_second_question_by_the_engine_in_the_slot_is_said_no_to_whatever_its_pages_ask(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2)
    monkeypatch.setenv("SUTRA_BOARD_QUESTIONS", "1")
    n = {"pages": 0}

    def say(step, prompt):
        if step == "write.page":
            n["pages"] += 1
            return dict(_page(prompt), question={"to": "Plan", "about": "colour %d" % n["pages"], "text": "Which colour?"})
        return None
    _model(monkeypatch, R, say)
    assert _write_again(W, R, ref)["status"] == "ok"
    rows = COORD.entries(ref)
    assert len(rows) > 1 and rows[0]["status"] == "open", "the first is let through, as it is within its bounds"
    assert all(e["status"] == "refused" and e["reason"] == "a second question by Write in this slot" for e in rows[1:])
    assert len({e["id"] for e in rows}) == len(rows)


def test_b1_an_about_already_answered_is_said_no_to_and_its_answer_is_the_one_used(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2)
    monkeypatch.setenv("SUTRA_BOARD_QUESTIONS", "1")
    seed = _row(about="The page list", answer="Home and About", answered_by="Plan", used_by=[], schema="board/1", question="Which pages?",
                cycle=None, attempt=1, run=None, artifact_update=None, reason=None)
    COORD._save(ref, [seed])
    seen = _model(monkeypatch, R, lambda s, p: dict(_page(p), question=dict(ASK)) if s == "write.page" and "Q-2" not in p and
                  "BOARD (answered" in p else (_page(p) if s == "write.page" else None))
    assert _write_again(W, R, ref)["status"] == "ok"
    rows = COORD.entries(ref)
    assert [e["status"] for e in rows][:2] == ["answered", "refused"] and rows[1]["reason"] == "already answered in Q-1"
    assert rows[0]["used_by"] == ["Write"], "the answer was used by the engine that asked it again"
    pages = [p for s, p in seen if s == "write.page"]
    assert all("Home and About" in p for p in pages), "every call held the answer"


def test_b1_the_covering_reads_the_entry_over_the_board_as_it_stood_before_it(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2)
    monkeypatch.setenv("SUTRA_BOARD_QUESTIONS", "1")
    _model(monkeypatch, R, _asks_once({"to": "Check"}))
    _write_again(W, R, ref)
    e = COORD.entries(ref)[0]
    check = COORD.question_is_bounded
    assert check({"ref": ref}, None, None, {"entry": e})["ok"] is True, "refused, and rightly"
    assert check({"ref": ref}, None, None, dict(entry=dict(e, status="open")))["ok"] is False, "let through past its bounds"
    assert check({"ref": ref}, None, None, dict(entry=dict(e, reason="")))["ok"] is False, "a no gives its reason"
    good = dict(e, to="Plan", about="the page list", status="refused", reason="no reason, but it was in bounds")
    assert check({"ref": ref}, None, None, {"entry": good})["ok"] is False, "a question within its bounds was said no to"
    assert check(None, None, None, {"entry": e})["ok"] is False, "no department to read"
    steps = [r for r in R.step_rows(ref) if r["step"] == "coord.question"]
    assert steps and all(r["engine"] == "Coordination" and r["status"] == "ok" and r["check"]["ok"] for r in steps)


def test_b1_the_board_is_heard_from_the_boards_post_and_a_question_the_asker_left_open_is_unanswered(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2)
    monkeypatch.setenv("SUTRA_BOARD_QUESTIONS", "1")
    _model(monkeypatch, R, _asks_once())
    _write_again(W, R, ref)
    assert [e["status"] for e in COORD.entries(ref)] == ["open"]
    W.run_until_idle(ref, limit=50)                      # Coordination hears the asker's post
    heard = [r for r in W.runs(ref) if r["engine"] == "Coordination" and "@board.n" in str(r.get("slot"))]
    assert heard and heard[-1]["status"] == "ok"
    assert [(e["status"], e["reason"]) for e in COORD.entries(ref)] == [("unanswered", "the asker had moved on")]


def test_b1_a_department_whose_table_is_older_learns_the_engine_edges(j2):
    W, R, J, _, _ = j2
    ref = _born(j2)
    t = W._read(W.ddir(ref) / "coordination.json", {})
    t["edges"].pop("Engine", None)
    t["edges"]["Coordination"] = {"request": ["Identity", "Priority"], "inform": ["Identity"]}
    W._write(W.ddir(ref) / "coordination.json", t)
    got = R.coordination(ref)["edges"]
    assert got["Engine"] == {"request": ["Coordination"]} and got["Coordination"]["request"][-1] == "Engine" and got["Coordination"]["inform"][-1] == "Engine"
    assert R.may_post("Write", ["Coordination"], "request", ref) and R.may_post("Coordination", ["Plan"], "request", ref)
    assert R.may_post("Coordination", ["Write"], "inform", ref)
    assert not R.may_post("Write", ["Identity"], "request", ref) and not R.may_post("Write", ["Plan"], "request", ref)
    assert not R.may_post("Coordination", ["Nobody"], "request", ref), "a name that is no engine is no Engine"
    assert R.may_post("Owner", ["Identity"], "request", ref) and not R.may_post("Plan", ["Identity"], "inform", ref)
