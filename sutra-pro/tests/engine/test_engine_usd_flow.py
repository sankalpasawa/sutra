"""D256 (patch P26), the owner's flows with dollar mode on (NFR-6): whole Brew Lab runs of the vendored J2 in mock mode, where every call
is priced by the estimate rule (characters / 4 at the fallback rate, D255). A first probe run with a large limit measures what a run costs,
and each scenario sets its limit from it, so a change in prompt sizes moves the figures, not the tests.

  1. a run reaches its limit and asks the dollar question, with no "credit" anywhere the Requester reads
  2. "Add $N and keep going" raises the limit and the run goes on to its next pause or its end
  3. with Decide for me on, the run waits on the dollar question
  4. with ample dollars and few starting credits, code tops credits up and never asks a credit question
  5. with J2_USD_CAP the raise offered stops at the cap, and at the cap the continue option is gone"""
import re

import pytest

from test_engine_patches import BREW_LAB, fresh_j2, say

QUESTION = re.compile(r"^This run has used \$[\d.,]+ of \$[\d.,]+ \(API price\)\. Add \$[\d.,]+\? So far: \$[\d.,]+ approved\.")
PROBE = {}


@pytest.fixture(autouse=True)
def mock_mode(llm_reset):
    llm_reset.configure(mock=True)


def start(j2, tmp_path, name="j2-20261104-100001-7f3a"):
    run = j2.J2Run(run_dir=tmp_path / "runs" / name)
    say(run, BREW_LAB)
    return run


def cost(tmp_path):
    """What the whole mock Brew Lab run costs in dollar mode (measured once per session)."""
    if not PROBE:
        with fresh_j2(tmp_path / "probe", J2_USD_BUDGET="10000") as j2:
            run = start(j2, tmp_path / "probe")
            assert run.outcome.startswith("Done") and run.paused is None, run.outcome
            PROBE["total"] = run.usd_used
    return PROBE["total"]


def to_requester(run):
    return [m["text"] for m in run.chat if m.get("to_user") or m.get("audience") == "user"]


def limit_of(total, share):
    return f"{round(total * share, 2)}"      # cents: what a typed "$0.30" says


def test_run_reaches_its_limit_and_asks(tmp_path):
    limit = limit_of(cost(tmp_path), 0.5)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit) as j2:
        run = start(j2, tmp_path)
        p = run.paused
        assert p and p["kind"] == "limit" and p["handoff"].get("usd") is True, run.outcome
        assert QUESTION.match(p["questions"][0]["question"]), p["questions"][0]["question"]
        # asked because the dollars are used up, or because the work still to fund costs more than the dollars left buy
        reason = p["handoff"]["limit"]
        assert reason.startswith(("Dollar limit", "Out of budget")) or "can't pay for" in reason, reason
        assert not [t for t in to_requester(run) if re.search(r"credit", t, re.I)]
        assert not [q for q in p["questions"] for o in [q["question"], *q["options"]] if re.search(r"credit", o, re.I)]


def test_a_typed_raise_resumes_the_run(tmp_path):
    limit = limit_of(cost(tmp_path), 0.5)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit) as j2:
        run = start(j2, tmp_path)
        msg = run.paused["msg"]
        say(run, f"Add ${limit} and keep going")
        assert run.usd_limit == pytest.approx(2 * float(limit)) and len(run.usd_raises) == 1
        assert run.paused is None or run.paused["msg"] != msg                 # it left the pause: a new one, or the end
        if run.paused and run.paused["handoff"].get("usd"):
            assert " + " in run.paused["questions"][0]["question"].split("So far: ")[1]
        else:
            assert run.paused or run.outcome.startswith("Done"), run.outcome


def test_decide_for_me_does_not_answer(tmp_path):
    limit = limit_of(cost(tmp_path), 0.5)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit, J2_DECIDE_FOR_ME="1") as j2:
        run = start(j2, tmp_path)
        assert run.auto is True
        p = run.paused
        assert p and p["handoff"].get("usd") is True and run.snapshot()["paused"]["auto_waits"] is True
        assert run._auto_pick() is None and run.usd_raises == []


def test_code_tops_up_credits_without_asking(tmp_path, monkeypatch):
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET="10000") as j2:
        monkeypatch.setattr(j2, "BUDGET", 3)                               # starting credits below the cheapest part
        run = start(j2, tmp_path)
        assert run.outcome.startswith("Done"), run.outcome
        assert [r for r in run.raises if r.get("code")] and run.raises[0]["from"] == 3
        assert not [e for e in run.events if e["type"] == "pause" and e.get("pause") in ("limit", "approval", "ruling_budget")]


def test_cap_limits_the_raise(tmp_path):
    total = cost(tmp_path)
    limit, cap = round(total * 0.5, 2), round(total * 0.6, 2)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=f"{limit}", J2_USD_CAP=f"{cap}") as j2:
        run = start(j2, tmp_path)
        q = run.paused["questions"][0]
        offered = q["budget"][run.paused["handoff"]["choices"].index("continue")]
        assert 0 < offered <= round(cap - limit, 2) + 0.01
        say(run, "Option 1")
        assert run.usd_limit == pytest.approx(min(limit + offered, cap))
        run.usd_limit = cap                                                   # at the cap: no continue option
        run.usd_used = cap
        run._handoff("identity", kind="limit", usd=True, reason="Dollar limit")
        run.turn = "identity"
        run._identity_limit(run.handoff)
        assert "continue" not in run.paused["handoff"]["choices"]


def test_p26_limit_checked_between_turns(tmp_path, monkeypatch):
    """With credits to spare (a tiny USD_PER_CREDIT), the dollars themselves stop the run: between turns, once usd_used reaches
    the limit; the turn in progress may pass it (NFR-3)."""
    limit = limit_of(cost(tmp_path), 0.5)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit) as j2:
        monkeypatch.setattr(j2, "USD_PER_CREDIT", 0.00001)
        monkeypatch.setattr(j2, "BUDGET", 100_000)
        run = start(j2, tmp_path)
        p = run.paused
        assert p and p["handoff"]["limit"].startswith("Dollar limit") and run.usd_used >= float(limit)
        assert QUESTION.match(p["questions"][0]["question"])
        assert run.usd_used - float(limit) <= max(r["usd_counted"] for r in run.call_log) * 20      # at most one turn's calls past it
