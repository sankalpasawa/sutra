"""D422 (patch P26), the owner's flows with dollar mode on (NFR-6): whole Brew Lab runs of the vendored J2 in mock mode, where every call
is priced by the estimate rule (characters / 4 at the fallback rate, D421). A first probe run with a large limit measures what a run costs,
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


# ---- review round 1 (R1-2 to R1-5, R1-11): every shortfall the Requester can meet asks in dollars, never in credits ----------------
CREDIT = re.compile(r"credit", re.I)
DESIGN_BRIEF = (BREW_LAB + " Write the design docs first. Users: coffee lovers and office staff. Problem: people can't see the menu or "
                "order ahead. Must-have features: see the menu with prices, pre-order a coffee, find the shop, read the opening "
                "hours. Constraints: one page only. Success: 30 pre-orders per week.")


def asked(run):
    """Every word of the open question the Requester reads: the question, its options, and Identity's message above them."""
    p = run.paused
    msg = next(m["text"] for m in run.chat if m["id"] == p["msg"])
    return [msg, *(t for q in p["questions"] for t in [q["question"], *q["options"]])]


def resume_at(run, to, handoff):
    """Point the paused run's next answer at `to` with `handoff`: the loop then takes that turn as it would after any answer."""
    run.paused = {**run.paused, "to": to, "handoff": handoff}


def test_a_big_raise_confirmed_from_the_card_applies_once(tmp_path):
    """R1-2: the re-asked card's button sends "Add $N and keep going" with the typed amount; that confirms it (once), never
    asks back again."""
    limit = limit_of(cost(tmp_path), 0.5)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit) as j2:
        run = start(j2, tmp_path)
        big = round(float(limit) * 6 + 1, 2)
        typed = f"Add ${big:g} and keep going"
        say(run, typed)
        assert run.paused and run.paused["msg"] and run.usd_raises == [], run.outcome       # asked back once
        assert asked(run)[0].count("more than 5 times"), asked(run)[0]
        say(run, typed)                                                                      # the card's button: same text
        assert [r["asked"] for r in run.usd_raises] == [big], run.usd_raises
        assert not (run.paused and "more than 5 times" in asked(run)[0]), "asked back again"


def test_add_zero_dollars_is_not_a_raise(tmp_path):
    """R1-11: a typed "Add $0" is asked again, never the option's own amount."""
    limit = limit_of(cost(tmp_path), 0.5)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit) as j2:
        run = start(j2, tmp_path)
        say(run, "Add $0 and keep going")
        assert run.usd_raises == [] and run.paused and run.paused["handoff"].get("reasked"), (run.usd_raises, run.outcome)


def test_approval_shortfall_asks_in_dollars(tmp_path):
    """R1-3 (approval): a workflow over its envelope that the dollars left can't fund: the dollar question, no credits."""
    limit = limit_of(cost(tmp_path), 0.5)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit) as j2:
        run = start(j2, tmp_path)
        run.usd_limit = round(run.usd_used + 0.5, 2)                     # some dollars left, far too few for the workflow
        w = next(w for w in run.workflows if not w.get("approval_asked"))
        w.update(cost=100_000, charged=False)
        resume_at(run, "priority", {"kind": "envelope", "wid": w["id"]})
        say(run, "Go on")
        assert any(e["type"] == "hold" for e in run.events), "the envelope check did not run"
        p = run.paused
        words = asked(run)
        assert not [t for t in words if CREDIT.search(t)], words
        assert p["handoff"].get("usd") is True and QUESTION.match(p["questions"][0]["question"]), p["questions"]
        say(run, "Option 1")
        assert len(run.usd_raises) == 1 and not [r for r in run.raises if not r.get("code") and r["cycle"] == run.cycle
                                                  and "over its envelope" in r["why"]], run.raises


def test_ruling_shortfall_asks_in_dollars(tmp_path):
    """R1-3 (ruling): Identity's ruling costs more than the dollars left fund: the question is in dollars and option 1
    raises the dollar limit, never credits."""
    limit = limit_of(cost(tmp_path), 0.5)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit) as j2:
        run = start(j2, tmp_path)
        run.usd_limit = round(run.usd_used + 0.5, 2)
        wf = {**run.workflows[0], "id": "W-90", "name": "Loyalty card", "cost": 100_000, "charged": False,
              "envelope": {**run.workflows[0]["envelope"], "money_limit": 100_000}}
        c = run._open_conflict("scope", ["adaptation", "priority"], "W-90", "the loyalty card")      # as a dispute opens one
        c.update(identity=[{"say": "The loyalty card is in the charter."}], pending_winner="adaptation", ruled_wfs=[wf])
        resume_at(run, "priority", {"kind": "ruling", "table": [wf], "conflict": c["id"]})
        say(run, "Go on")
        p = run.paused
        assert p and p["kind"] == "ruling_budget", run.outcome
        words = asked(run)
        assert not [t for t in words if CREDIT.search(t)], words
        assert p["questions"][0]["question"].startswith("This run has used $"), p["questions"][0]["question"]
        say(run, "Option 1")
        assert len(run.usd_raises) == 1 and not [r for r in run.raises if f"{c['id']} ruling" in r["why"]], (run.usd_raises, run.raises)


def test_document_chain_shortfall_asks_in_dollars(tmp_path):
    """R1-4: a chain of documents the dollars can't cover: code tops up first, then asks in dollars ("[adds $Z]")."""
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET="1") as j2:
        run = j2.J2Run(run_dir=tmp_path / "runs" / "j2-20261104-100002-7f3a")
        say(run, DESIGN_BRIEF)
        p = run.paused
        assert p and p["handoff"].get("kind") == "stage_decision", run.outcome
        words = asked(run)
        assert not [t for t in words if CREDIT.search(t)], words
        assert p["handoff"].get("usd") and QUESTION.match(p["questions"][0]["question"]), p["questions"][0]["question"]
        assert "[adds $" in words[0], words[0]
        say(run, "Option 1")
        assert len(run.usd_raises) == 1, (run.usd_raises, run.outcome)


def test_a_stated_need_the_dollars_cover_is_not_asked_for(tmp_path):
    """R1-5: a decision question that names the credits it needs: when the dollars left fund them, code tops up and the
    question offers no raise (no dollar question)."""
    limit = limit_of(cost(tmp_path), 0.5)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit) as j2:
        run = start(j2, tmp_path)
        run.usd_limit = round(run.usd_used + 50, 2)                      # plenty of dollars left
        resume_at(run, "identity", {"kind": "limit", "budget_needed": 40, "reason": "Adaptation asked: add the loyalty card?"})
        say(run, "Go on")
        p = run.paused
        assert p and p["kind"] == "limit" and not p["handoff"].get("usd"), p and p["handoff"]
        assert run.budget - run.spent >= 40 and not CREDIT.search(" ".join(asked(run)))


# ---- review round 2 (R2-1): an approved dollar raise funds the work it was priced for, in a run cheaper or dearer per credit than
# USD_PER_CREDIT ($0.0187): one rate prices the raise and turns the approved dollars into credits ------------------------------------
RUN_RATES = pytest.mark.parametrize("rate", [0.01, 0.03], ids=["cheap", "expensive"])


def priced_at(j2, run, rate, left=0.5):
    """Give the run a measured rate of `rate` dollars per credit (its dollars used become its credits spent times `rate`) and
    `left` dollars to spend, far too few for the work under test, and no credit beyond what is spent (code tops credits up from
    the dollars left). Its calls are already enough for its own rate to count (USD_RATE_MIN_CALLS, new with the fix: 8)."""
    assert run.spent and len(run.call_log) >= getattr(j2, "USD_RATE_MIN_CALLS", 8), (run.spent, len(run.call_log))
    run.usd_used = run.spent * rate
    run.usd_limit = round(run.usd_used + left, 2)
    run.budget = run.spent


def credits_after_raise(run):
    """The credits free right after each dollar raise is applied (before any of them is spent)."""
    seen, add = [], run._usd_add

    def recorded(*a, **k):
        out = add(*a, **k)
        seen.append(run.budget - run.spent)
        return out
    run._usd_add = recorded
    return seen


def funds_exactly(seen, need, rate):
    """One raise, and it bought the credits it was priced for: at least the need, and no more than the need plus what rounding
    the dollars up (to $1 at most) buys, so the dollars and the credits stay one rate (an over-grant spends dollars nobody priced)."""
    assert len(seen) == 1 and need <= seen[0] <= need + 2 / rate, (seen, need, rate)


@RUN_RATES
def test_approval_raise_funds_the_workflow(tmp_path, rate):
    limit = limit_of(cost(tmp_path), 0.5)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit) as j2:
        run = start(j2, tmp_path)
        priced_at(j2, run, rate)
        w = next(w for w in run.workflows if not w.get("approval_asked"))
        w.update(cost=100_000, charged=False)
        resume_at(run, "priority", {"kind": "envelope", "wid": w["id"]})
        say(run, "Go on")
        assert run.paused and run.paused["handoff"].get("usd") is True, run.outcome
        seen = credits_after_raise(run)
        say(run, "Option 1")
        funds_exactly(seen, 100_000, rate)
        assert w.get("status") != "unfunded" and w.get("charged"), ({k: w.get(k) for k in ("status", "charged")}, run.outcome)


def priced_ruling(j2, run, credits=2000):
    """A ruled workflow the validator can price and register: W-1's fields, with rate-card parts worth about `credits`."""
    w0 = run.workflows[0]
    k = (w0.get("parts") or [next(iter(j2.RATES))])[0]
    n = -(-credits // j2.RATES[k])
    c = n * j2.RATES[k]
    return {**w0, "id": "W-90", "name": "Loyalty card", "parts": [k] * n, "cost": c, "charged": False,
            "envelope": {**w0["envelope"], "money_limit": c}}


@RUN_RATES
def test_ruling_raise_funds_the_ruling(tmp_path, rate):
    limit = limit_of(cost(tmp_path), 0.5)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit) as j2:
        run = start(j2, tmp_path)
        priced_at(j2, run, rate)
        wf = priced_ruling(j2, run)
        c = run._open_conflict("scope", ["adaptation", "priority"], "W-90", "the loyalty card")
        c.update(identity=[{"say": "The loyalty card is in the charter."}], pending_winner="adaptation", ruled_wfs=[wf])
        resume_at(run, "priority", {"kind": "ruling", "table": [wf], "conflict": c["id"]})
        say(run, "Go on")
        assert run.paused and run.paused["kind"] == "ruling_budget", run.outcome
        seen = credits_after_raise(run)
        say(run, "Option 1")
        funds_exactly(seen, wf["cost"], rate)
        w = next((x for x in run.workflows if x["name"] == "Loyalty card"), None)
        assert w and w.get("status") != "unfunded" and w.get("charged"), (w and {k: w.get(k) for k in ("status", "charged")}, run.outcome)


@RUN_RATES
def test_chain_raise_funds_the_documents(tmp_path, rate):
    """The first document fits; before the second, the dollars left are cut to a cent at `rate`, so the chain's gate asks."""
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET="8") as j2:
        run = j2.J2Run(run_dir=tmp_path / "runs" / "j2-20261104-100002-7f3a")
        advance, asked_at = run._advance, {}

        def cut(i):
            if i == 1 and not asked_at:
                priced_at(j2, run, rate, left=0.01)
                asked_at.update(need=sum(run._stage_cost(k) for k in run.stages[i:]), stages=list(run.stages))
            return advance(i)
        run._advance = cut
        say(run, DESIGN_BRIEF)
        h = run.paused and run.paused["handoff"]
        assert asked_at and h and h.get("kind") == "stage_decision" and h["stage_i"] == 1, run.outcome
        seen = credits_after_raise(run)
        say(run, "Option 1")
        funds_exactly(seen, asked_at["need"], rate)
        assert run.stages == asked_at["stages"] and not (run.paused and run.paused["handoff"].get("kind") == "stage_decision"), run.outcome


def test_the_envelope_check_tops_up_before_a_hold(tmp_path):
    """R2-1 probe, second half: after a raise the envelope check ran again with approval already asked, and Priority held the
    workflow unfunded although the dollars left funded it. Code tops up at the check itself, so it runs."""
    limit = limit_of(cost(tmp_path), 0.5)
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit) as j2:
        run = start(j2, tmp_path)
        priced_at(j2, run, 0.01, left=0.5)      # $0.50 at $0.01 buys 50 credits
        w = run.workflows[-1]
        w.update(cost=40, charged=False, approval_asked=True, status="waiting")
        resume_at(run, "priority", {"kind": "envelope", "wid": w["id"]})
        say(run, "Go on")
        assert w.get("charged") and w.get("status") != "unfunded", ({k: w.get(k) for k in ("status", "charged")}, run.outcome)


# ---- R2-2: the ruling's dollar question takes a typed amount, as the other dollar questions do ----------------------------------------
def at_ruling(j2, run, credits=2000):
    """The ruling's dollar question, at $0.01 per credit with $0.50 (50 credits) left: a ruling worth about `credits`."""
    priced_at(j2, run, 0.01)
    wf = priced_ruling(j2, run, credits)
    c = run._open_conflict("scope", ["adaptation", "priority"], "W-90", "the loyalty card")
    c.update(identity=[{"say": "The loyalty card is in the charter."}], pending_winner="adaptation", ruled_wfs=[wf])
    resume_at(run, "priority", {"kind": "ruling", "table": [wf], "conflict": c["id"]})
    say(run, "Go on")
    assert run.paused and run.paused["kind"] == "ruling_budget", run.outcome
    return wf, c


def test_the_ruling_question_takes_a_typed_amount(tmp_path):
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit_of(cost(tmp_path), 0.5)) as j2:
        run = start(j2, tmp_path)
        wf, _ = at_ruling(j2, run, credits=100)      # about $1 of work, $0.50 left: the shortfall is under BIG_RAISE times the limit
        assert "[adds $" in next(m["text"] for m in run.chat if m["id"] == run.paused["msg"])      # the cards read the amount from it
        old, typed = run.usd_limit, 2.0
        assert typed != run.paused["handoff"]["usd"]
        say(run, f"Add ${typed:g} and keep going")
        assert run.usd_limit == pytest.approx(old + typed), (old, typed, run.usd_limit)
        assert run.usd_raises[-1]["asked"] == pytest.approx(typed)
        assert next(x for x in run.workflows if x["name"] == wf["name"]).get("charged"), run.outcome


def test_a_typed_amount_in_a_refusal_raises_nothing(tmp_path):
    """Review of R2-2: "No, don't add $3" names a dollar amount but declines; only the model's choice 1 or the card's own raise text
    makes a typed amount the raise."""
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit_of(cost(tmp_path), 0.5)) as j2:
        run = start(j2, tmp_path)
        at_ruling(j2, run, credits=100)
        old, call = run.usd_limit, run.call

        def declined(fn, fmt, task, mock, *a, **k):      # the model reads the refusal as choice 2, as a real one would
            if fn == "identity" and task.startswith("YOU ASKED THE REQUESTER"):
                mock = lambda: '{"say": "The Requester kept Priority\'s final answer.", "choice": 2}'
            return call(fn, fmt, task, mock, *a, **k)
        run.call = declined
        say(run, "No, don't add $3, go with Priority's final answer")
        assert run.usd_limit == old and not run.usd_raises, (old, run.usd_limit, run.usd_raises)


def test_a_typed_amount_short_of_the_ruling_is_asked_again(tmp_path):
    """Review of R2-2: an amount that funds less than the ruling is asked again with the amount offered, never registered "in full"."""
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit_of(cost(tmp_path), 0.5)) as j2:
        run = start(j2, tmp_path)
        _, c = at_ruling(j2, run)
        old, offer, asked = run.usd_limit, run.paused["handoff"]["usd"], dict(c["user_question"])
        say(run, "Add $1 and keep going")
        p = run.paused
        assert p and p["kind"] == "ruling_budget" and run.usd_limit == old and p["handoff"]["usd"] == offer, run.outcome
        assert c["user_question"] == asked
        say(run, "Yes, approve it.")
        assert run.usd_limit == pytest.approx(old + offer)


def test_the_ruling_question_asks_again_for_zero_and_confirms_a_big_amount(tmp_path):
    with fresh_j2(tmp_path / "env", J2_USD_BUDGET=limit_of(cost(tmp_path), 0.5)) as j2:
        run = start(j2, tmp_path)
        _, c = at_ruling(j2, run)
        old, asked = run.usd_limit, dict(c["user_question"])
        say(run, "Add $0")
        assert run.paused and run.paused["kind"] == "ruling_budget" and run.usd_limit == old, run.outcome
        big = round(max(old * 6 + 1, run.paused["handoff"]["usd"] + 1), 2)
        say(run, f"Add ${big:g} and keep going")
        p = run.paused
        assert p and p["kind"] == "ruling_budget" and run.usd_limit == old, run.outcome
        assert p["questions"][0]["options"][0].startswith(f"Add {run_fmt(j2, big)} ") and p["handoff"]["usd"] == big
        assert c["user_question"] == asked      # the stored question stays the first one
        say(run, "Yes, approve it.")
        assert run.usd_limit == pytest.approx(old + big), (old, big, run.usd_limit)


def run_fmt(j2, x):
    return j2.fmt_usd(x)
