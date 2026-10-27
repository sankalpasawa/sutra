"""Priority behind its interface (PRD A1, W1-PRIORITY: M5.8 and M5.3): layers/priority/v1 registers every name its recipe
uses, prices a proposal from what the engines have observably spent, answers it with the price, writes one price row per
answer, shows them in its view, and says by='priority' where it writes the record.

One test per done-check of P1 to P5. The contract's cases are layers/contract.py's; the fixtures are test_j2's: a
department born the way a person makes one, a model that is a function of the step id, the same board.
"""
import importlib
import re
from datetime import datetime, timedelta

import pytest

import layer_schema as S
import layers
import layers.contract as C
import layers.priority.v1 as V1

WEBSITE = "Build a website that teaches algebra to Class 8 students"
LINE = ["Plan", "Write", "Check", "Publish"]


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    return {"ref": C.fixture_department(tmp_path / "departments")}


@pytest.fixture
def j2(tmp_path, monkeypatch):
    """test_j2's fixture: a department is born the way a person makes one, on a records home of its own, with no model."""
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
    for module in (E, W, org2_apply, founding, R, J):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, J, founding


@pytest.fixture
def live(j2):
    """The department world with the registry's seam serving priority/v1's own bodies to the runtime (W1-CORE, K1): the
    bodies the runtime runs for Priority are the module's, not engine_runtime's old ones."""
    W, R, J, founding = j2
    for kind, mine in (("code", V1.CODE), ("prompt", V1.PROMPT), ("draft", V1.DRAFT), ("check", V1.CHECK)):
        legacy = {"code": R.CODE, "prompt": R.PROMPT, "draft": R.DRAFT, "check": R.CHECK}[kind]
        for name, fn in mine.items():
            if not hasattr(fn, "legacy"):
                assert layers.resolve(None, "Priority", kind, name, legacy) is fn, "%s %s is served from priority/v1" % (kind, name)
    return j2


def _born(j2, words=WEBSITE, org="Acme Learning", settle=True):
    """A department as a person makes one: found the organisation, say the words, Root sets it up."""
    W, _, _, founding = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    if settle:
        W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _actions(J, ref):
    return [e["action"] for e in J.events(ref)]


ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"
THREE = {"engines": [{"name": "Facts", "does": "finds the facts", "reads": "Brief", "writes": "Facts", "internet": True},
                     {"name": "Notes", "does": "sorts the facts", "reads": "Facts", "writes": "Notes", "internet": False},
                     {"name": "Summary", "does": "writes the summary", "reads": "Notes", "writes": "Summary", "internet": False}]}
#: the engines of a line shaped on the fly are not born when Priority prices it; what they cost is what they cost elsewhere:
#:   Facts   3 runs: calls 2, 3, 4 -> 3;  usd 0.05, 0.07, 0.09 -> 0.07
#:   Notes   2 runs: calls 1, 2 -> 1.5, a call is whole, so 2;  usd 0.03, 0.05 -> 0.04
#:   Summary none: priced as Do is, two model steps -> 2 calls, 0.08
SHAPED_HISTORY = {"Facts": [("ok", 2, 0.05), ("ok", 3, 0.07), ("ok", 4, 0.09)], "Notes": [("ok", 1, 0.03), ("ok", 2, 0.05)]}


def _model(monkeypatch, R, answers):
    """test_j2's model: a function of the step id. Every step it does not answer falls to its draft, as it does offline."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)

    def model(prompt, step):
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"
    monkeypatch.setattr(R, "MODEL", model)


def _stamp(ref, W):
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "conflict"]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)


#: finished runs of yesterday, by engine, oldest first: (status, calls, usd). Their medians, worked by hand, are the fixture:
#:   Plan   3 runs: calls 2, 4, 3 -> 3;  usd 0.06, 0.10, 0.08 -> 0.08                          (basis median, 3 runs)
#:   Write  4 runs: calls 5, 6, 9, 7 -> 6.5, a call is whole, so 7;  usd 0.20, 0.25, 0.50, 0.30 -> 0.275   (4 runs, the failed one counts)
#:   Check  none: the prior, one model step, one call, at 0.04 -> 1 call, 0.04
#:   Publish none: no model step -> 0 calls, 0.00
HISTORY = {"Plan": [("ok", 2, 0.06), ("ok", 4, 0.10), ("ok", 3, 0.08)],
           "Write": [("ok", 5, 0.20), ("ok", 6, 0.25), ("ok", 9, 0.50), ("failed", 7, 0.30)]}
MEDIANS = {"Plan": {"calls": 3, "usd": 0.08, "basis": "median", "runs": 3}, "Write": {"calls": 7, "usd": 0.275, "basis": "median", "runs": 4},
           "Check": {"calls": 1, "usd": 0.04, "basis": "prior", "runs": 0}, "Publish": {"calls": 0, "usd": 0.0, "basis": "prior", "runs": 0}}


def _run_row(engine, status, calls, usd, started, **more):
    row = {"id": "r-" + engine[:3].lower() + str(abs(hash((engine, status, calls, usd, started))) % 10 ** 6), "engine": engine,
           "system": False, "slot": None, "status": status, "started": started, "ended": started, "what": "history", "wrote": None,
           "chain": None, "spend": {"calls": calls, "usd": usd}, "retries": 0, "runtime": 2}
    row.update(more)
    return row


def _history(W, ref, history=HISTORY, noise=True):
    """Yesterday's finished runs in runs.json, and rows that are no finished run of an engine: skipped, one that waits for the
    owner, and a function's own row. They must not move a median. Slots are none, so no real slot looks done, and none is
    running, since a run that runs holds the motor."""
    yesterday = (datetime.now().astimezone() - timedelta(days=1)).isoformat(timespec="seconds")
    rows = list(W.runs(ref))
    for engine, runs in history.items():
        for i, (status, calls, usd) in enumerate(runs):
            rows.append(_run_row(engine, status, calls, usd, yesterday, wrote={"art": "Result", "v": i + 1}))
    if noise:
        rows += [_run_row("Plan", "skipped", 0, 0.0, yesterday), _run_row("Write", "asked", 50, 9.0, yesterday),
                 _run_row("Plan", "ok", 40, 8.0, yesterday, system=True)]
    W._write(W.ddir(ref) / "runs.json", rows)


def _envelopes(W, ref, **limits):
    for name, (calls, usd) in limits.items():
        W.set_envelope(ref, name, calls=calls, usd=usd)


def _prices(W, ref):
    return W.rows(ref, "prices.jsonl")


# ---- P1: priority/v1 by reference --------------------------------------------------------------------------------------
def test_p1_every_name_the_recipe_uses_is_registered_and_the_contract_passes(ctx):
    """A name the recipe uses that priority/v1 does not provide, or a case of the contract that fails, must fail."""
    recipe = C.recipe_of(V1)
    names = {k: sorted({s[k] for s in C._steps(recipe) if s.get(k)}) for k in ("code", "prompt", "draft", "check")}
    for kind, dict_ in (("code", V1.CODE), ("prompt", V1.PROMPT), ("draft", V1.DRAFT), ("check", V1.CHECK)):
        assert set(names[kind]) <= set(dict_), "%s: %s" % (kind, sorted(set(names[kind]) - set(dict_)))
    for number, what, case in C.cases():
        if number in (1, 2, 3, 4, 7):
            assert case(V1, ctx) == [], "case %d: %s" % (number, what)


def test_p1_a_name_still_by_reference_is_a_late_bound_delegate_to_engine_runtimes_own_body(ctx):
    """P1 moves nothing: until a body moves (P3), each name is a late-bound delegate to engine_runtime's own, so a
    reloaded runtime is the one that runs, and the registries are as they were. The count is reported, never gated."""
    import engine_runtime as R
    counts = C.by_reference(V1)
    everything = [(kind, name, fn) for kind, d in (("code", V1.CODE), ("prompt", V1.PROMPT), ("draft", V1.DRAFT), ("check", V1.CHECK))
                  for name, fn in d.items()]
    assert counts["by_reference"] + counts["own"] == len(everything)
    legacy = {"code": R.CODE, "prompt": R.PROMPT, "draft": R.DRAFT, "check": R.CHECK}
    for kind, name, fn in everything:
        if hasattr(fn, "legacy"):
            module, attr = fn.legacy
            assert module == "engine_runtime" and getattr(R, attr) is legacy[kind][name], "%s %s" % (kind, name)
    assert counts["by_reference"] >= 1
    importlib.reload(R)
    assert not hasattr(V1.CODE["priority_grant"], "legacy") and not hasattr(V1.CODE["priority_envelope"], "legacy"), \
        "priority_envelope moved in M5.4 and priority_grant in M9.2: their bodies are this module's"
    assert layers.recipes()["Priority"] == C.recipe_of(V1)


# ---- the interface rows Priority adds (A1 interface: priority:) and its covering ---------------------------------------
def _read(names, per, room, limit=6):
    """What priority.read hands the bargain, as far as the covering reads it."""
    return {"bag": {"priority.read": {"names": names, "limit": limit, "room": room, "estimate": {"calls": 0, "usd": 0, "per_engine": per}}}}


PER = {"Plan": {"calls": 2, "usd": 0.08}, "Write": {"calls": 4, "usd": 0.16}, "Check": {"calls": 1, "usd": 0.04}}


def test_p3_the_interface_names_the_estimate_and_what_remains_the_covering_and_the_prices_view():
    """The bargain line part gains estimate and remaining, the covering is listed with samples, and the view's prices are
    typed but not required, so a view written before them still validates."""
    line = S.PROMPTS["priority"]["bargain"]["line"]
    assert line["inputs"] == ("source", "engines", "calls", "usd", "room", "limit", "estimate", "remaining")
    assert "price_is_observed" in S.CHECKS["priority"] and "answer_has_its_price" in S.CHECKS["priority"]
    for out in S.CONTRACT_SAMPLES["price_is_observed"]["good"]:
        assert V1.CHECK["price_is_observed"](None, None, None, out)["ok"] is True, out
    for out in S.CONTRACT_SAMPLES["price_is_observed"]["bad"]:
        assert V1.CHECK["price_is_observed"](None, None, None, out)["ok"] is False, out
    view = S.DEFS["view.priority"]
    assert "prices" in view["properties"] and "prices" not in view["required"]
    assert S.validate("view.priority", {"bargains": [], "envelopes": []}) == []


def test_p3_the_covering_keeps_the_notes_of_the_covering_it_replaces_when_there_are_no_facts_to_hold_it_to():
    """With no facts the answer is held to its price alone, as engine_runtime's answer_has_its_price holds it (the notes are
    the same words), so the step keeps its name and the checks that pin it stay as they were."""
    import engine_runtime as R
    for out in ({"answer": "counter", "why": "room for two today", "keep": []}, {"answer": "maybe", "why": "unsure"},
                {"answer": "accept", "why": " "}, {"answer": "accept", "why": "fits today"},
                {"answer": "counter", "why": "room for two today", "keep": ["Plan", "Write"]}):
        assert V1.CHECK["answer_has_its_price"](None, None, None, out) == R.CHECK["answer_has_its_price"](None, None, None, out), out
    assert V1.CHECK["answer_has_its_price"] is V1.CHECK["price_is_observed"]


def test_p3_a_yes_or_an_ask_for_less_is_held_to_the_room_and_a_no_always_stands():
    """A yes that spends what is not there, an ask for less that keeps more than fits, and one that keeps what the
    proposal does not name must fail; a no, or a smaller yes, stands (approvals only tighten)."""
    check = V1.CHECK["price_is_observed"]
    names = ["Plan", "Write", "Check"]
    roomy, tight, none = ({"calls": 100, "usd": 5.0}, {"calls": 6, "usd": 0.24}, {"calls": 0, "usd": 0.0})
    assert check(_read(names, PER, roomy), None, None, {"answer": "accept", "why": "fits today"})["ok"]
    over = check(_read(names, PER, tight), None, None, {"answer": "accept", "why": "fits today"})
    assert not over["ok"] and over["notes"] == ["said yes to what costs more than the room holds: 7 calls and 0.28 USD go past the "
                                               "6 calls and 0.24 USD left today"]
    assert check(_read(names, PER, tight), None, None, {"answer": "counter", "why": "room for two", "keep": ["Plan", "Write"]})["ok"]
    too_many = check(_read(names, PER, tight), None, None, {"answer": "counter", "why": "x", "keep": ["Write", "Plan", "Check"]})
    assert not too_many["ok"] and "asked to keep what costs more than the room holds" in too_many["notes"][0]
    strange = check(_read(names, PER, roomy), None, None, {"answer": "counter", "why": "x", "keep": ["Plan", "Publish"]})
    assert strange["notes"] == ["an ask for less keeps Publish, which the proposal does not name"]
    assert check(_read(names, PER, none), None, None, {"answer": "reject", "why": "no room today"})["ok"]
    assert check(_read(names, PER, roomy), None, None, {"answer": "reject", "why": "no room"})["ok"], "a no stands over ample room"
    assert not check(_read(names, PER, roomy, limit=2), None, None, {"answer": "accept", "why": "fits"})["ok"], "past the limit of workflows"
    assert check(_read(names, PER, roomy), None, None, {"answer": "accept", "why": "fits today"})["notes"] == ["said yes, with its price: fits today"]


# ---- P2: Priority's words (M2.5) --------------------------------------------------------------------------------------------
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import layers.prompts as P  # noqa: E402
import test_function_prompts as TFP  # noqa: E402 -- the fixture department the M2.1a snapshot is rendered for


def test_p2_priority_holds_every_part_as_words_and_none_is_on_the_md_fallback(ctx):
    """A part of Priority still read from the .md bundle, or words that do not pass their field's type or compile, must fail
    (contract case 5): goal (does, skills) and bargain (line, engine, cost)."""
    parts = [(g, p) for g, ps in S.PROMPTS["priority"].items() for p in ps]
    assert [part for part in parts if part[0] != "goal" or part[1] not in S._ROLE_PARTS] == \
        [("goal", "does"), ("goal", "skills"), ("bargain", "line"), ("bargain", "engine"), ("bargain", "cost"),
         ("bargain", "round")], "the round part was added by W2-PRIORITY (M9.2); the role parts of the goal group by A3-FUNCTIONS"
    assert C.on_the_md_fallback(V1) == [] and C.case_5(V1, ctx) == []
    assert all(P._module(None, "priority", g, p) is V1 for g, p in parts), "the registry takes the WORDS path for every part"
    assert V1.WORDS["bargain"]["line"] == {} and set(V1.WORDS["bargain"]["engine"]) == {"task"}, "the line part has no field the owner may change"
    assert P.faults() == [], "and the definitions load holds the typed words to their interface"


def test_p2_each_part_compiled_from_its_words_is_the_md_part_byte_for_byte(ctx):
    """The migration changes no word: the words and the layout, with the sample inputs, are the bundle's part. (The estimate
    and remaining lines are the bundle's too since the snapshot commit before it.)"""
    for layer_group, ps in S.PROMPTS["priority"].items():
        for part in ps:
            if ("priority", layer_group, part) in S.ADDED_PARTS:
                continue                                  # an added part has no .md part to be the same as
            sample = P.sample_inputs("priority", layer_group, part)
            fallback = P.SLOT.sub(lambda m: sample[m.group(1)], P.md_part("priority", layer_group, part))
            assert P.prompt(None, "priority", layer_group, part, **sample) == fallback, "%s.%s" % (layer_group, part)


def test_p2_the_words_are_the_ones_the_prompt_is_built_from_not_the_bundle(ctx, monkeypatch):
    """A prompt still read from the bundle, or a change of a word that does not reach the agent, must fail."""
    import engine_runtime as R
    monkeypatch.setitem(V1.WORDS["bargain"]["engine"], "task", "Adaptation offers an engine; say what it costs against what is left.")
    got = R._prompt("priority", "bargain", "engine", ctx["ref"], engine="Booking", does="d", needs="n", calls="240", usd="6.00", room="yes")
    assert got.startswith("Adaptation offers an engine; say what it costs against what is left.\nTHE ENGINE: Booking\n")
    assert R._goal_of(ctx["ref"], "Priority")[0] == V1.WORDS["goal"]["does"]["text"]


class TestPriorityIsServedFromItsWords(TFP.Fixture):
    def test_p2_the_snapshot_of_the_bargain_renders_unchanged_with_the_bundles_priority_files_gone(self):
        """The M2.1a snapshot, for Priority's prompts, from the registry's words alone: with the bundle's priority files
        emptied of every part, the same text is sent, and the definitions still load (a file whose every part a layer holds
        needs none)."""
        want = {k: v for k, v in json.loads(TFP.SNAP.read_text(encoding="utf-8")).items() if k.startswith("priority.")}
        assert sorted(want) == ["priority.bargain:engine:picked", "priority.bargain:engine:shaped", "priority.bargain:line:library",
                                "priority.bargain:line:over", "priority.bargain:line:shaped", "priority.bargain:rung"]
        tmp = Path(tempfile.mkdtemp(prefix="priority-bundle-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copytree(self.bundled, tmp / "b")
        for name in ("goal", "bargain"):
            (tmp / "b" / "priority" / (name + ".md")).write_text("Gone.\n", encoding="utf-8")
        self.R.PROMPTS_DIR = tmp / "b"
        self.R._DEFS.clear()
        self.assertEqual(self.R.bundle_faults(), [])
        got = {k: v for k, v in self.prompts().items() if k.startswith("priority.")}
        self.assertEqual(got, want)
        for text in got.values():
            self.assertIn("What Priority does: it grants each engine its envelope", text, "the card's goal is Priority's words too")


# ---- P3: observed spend and price rows (M5.3) --------------------------------------------------------------------------
def test_p3_the_estimate_of_an_engine_is_the_median_of_its_finished_runs_or_the_prior(j2):
    """An estimate that is a constant, or one a skipped, still-running or function row moves, must fail: it is the median
    of what the engine's finished runs spent, a call being whole, and with none, its model steps at call_usd."""
    W, R, J, _ = j2
    ref = _born(j2, settle=False)
    _history(W, ref)
    for name, want in MEDIANS.items():
        assert V1.price_of(ref, name) == want, name
    got = V1.estimate_of(ref, LINE, "line")
    assert (got["calls"], got["usd"], got["basis"], got["runs"]) == (11, 0.395, "line", 7)
    assert got["per_engine"] == MEDIANS
    assert S.validate("priority.estimate", got) == []
    assert V1.price_of(ref, "Facts") == {"calls": 2, "usd": 0.08, "basis": "prior", "runs": 0}, "an engine not born yet is priced as Do is"


def test_p3_the_prior_follows_call_usd_in_priority_v1s_template(j2, monkeypatch):
    """The price of a model call in the prior is the recipe's, not a constant of the code: 0.04 unless the template says."""
    W, R, J, _ = j2
    ref = _born(j2, settle=False)
    assert R.engine_def("Priority")["template"]["call_usd"] == 0.04
    assert V1.price_of(ref, "Check")["usd"] == 0.04
    monkeypatch.setitem(R.engine_def("Priority")["template"], "call_usd", 0.10)
    assert V1.price_of(ref, "Check") == {"calls": 1, "usd": 0.1, "basis": "prior", "runs": 0}
    monkeypatch.setitem(R.engine_def("Priority")["template"], "call_usd", "cheap")
    assert V1.price_of(ref, "Check")["usd"] == 0.04, "a template that names no price in numbers keeps the default"


def test_p3_room_is_the_sum_over_the_line_of_the_limit_less_todays_spend_and_remaining_is_room_less_the_estimate(j2):
    """A room that ignores today's spend, counts an engine past its limit as negative, or a remaining that is not the
    room less the estimate, must fail."""
    W, R, J, _ = j2
    ref = _born(j2, settle=False)
    _envelopes(W, ref, Plan=(10, 1.0), Write=(10, 1.0), Check=(10, 1.0), Publish=(10, 1.0))
    today = datetime.now().astimezone().isoformat(timespec="seconds")
    # what ran today has spent already, though a run that waits is no finished run to price from; Write is past its limit
    rows = W.runs(ref) + [_run_row("Plan", "asked", 4, 0.30, today), _run_row("Write", "asked", 25, 2.50, today)]
    W._write(W.ddir(ref) / "runs.json", rows)
    assert V1.room_of(ref, W.dept(ref), LINE) == {"calls": 6 + 0 + 10 + 10, "usd": 0.7 + 0.0 + 1.0 + 1.0}, "past its limit is no room, never less"
    _history(W, ref)
    ctx = {"ref": ref, "dept": W.dept(ref), "post": {"payload": {"word": "line", "engines": [{"name": n} for n in LINE]}, "thread": "x-1"}, "bag": {}}
    got = V1.priority_read(ctx, None, None)
    assert got["room"] == {"calls": 26, "usd": 2.7} and got["estimate"]["calls"] == 11
    assert got["remaining"] == {"calls": 26 - 11, "usd": round(2.7 - 0.395, 4)}
    assert got["fits"] == LINE and got["facts"] == {"word": "line", "room": True}


def test_p3_a_workflow_not_born_yet_brings_the_limit_of_a_work_engine(j2):
    """A line shaped on the fly names engines that hold no limit yet; their room is the one Priority will give each."""
    W, R, J, _ = j2
    ref = _born(j2, settle=False)
    t = R.priority_template()
    assert V1.room_of(ref, W.dept(ref), ["Facts", "Notes"]) == {"calls": 2 * t["work_calls"] * t["calls"], "usd": 2 * t["usd"]}


def test_p3_the_longest_prefix_that_fits_is_what_an_ask_for_less_keeps():
    """Fewer engines than the line, never a later one in place of an earlier one; and never more than the limit."""
    per = {n: {"calls": 3, "usd": 0.10} for n in "ABCDEFGH"}
    names = list("ABCDEFGH")
    room = lambda c, u: {"calls": c, "usd": u}
    assert V1.fits_of(names, per, room(9, 0.30), 6) == ["A", "B", "C"]
    assert V1.fits_of(names, per, room(9, 0.29), 6) == ["A", "B"], "money binds before calls"
    assert V1.fits_of(names, per, room(8, 9.0), 6) == ["A", "B"], "calls bind before money"
    assert V1.fits_of(names, per, room(2, 9.0), 6) == []
    assert V1.fits_of(names, per, room(900, 90.0), 6) == list("ABCDEF"), "the limit of workflows binds last"
    assert V1.fits_of(["A", "Z"], {"A": {"calls": 0, "usd": 0.0}, "Z": {"calls": 0, "usd": 0.0}}, room(0, 0.0), 6) == ["A", "Z"], "free work always fits"


def _priced(j2, limits, history=HISTORY, words=WEBSITE, org="Acme Learning", shaped=False):
    """A department born, its limits set and its history written before it proposes anything, then let run: the line goes to
    Priority and Priority prices it (offline, so the answer is the draft's: the arithmetic alone). `shaped`: the limits are
    written on the record for engines that are not born yet, as the model's line names them."""
    W, R, J, _ = j2
    ref = _born(j2, words, org, settle=False)
    if shaped:
        d = W.dept(ref)
        d["envelopes"].update({n: {"calls": c, "usd": u} for n, (c, u) in limits.items()})
        W.save_dept(ref, d)
    else:
        _envelopes(W, ref, **limits)
    _history(W, ref, history)
    W.run_until_idle(ref, limit=300)
    return ref


def test_p3_room_for_two_engines_gives_a_counter_keeping_two(live, monkeypatch):
    """Priority that says yes to what the room cannot hold, or no to what it can partly hold, or keeps a later engine in place
    of an earlier one, must fail: with room for Facts and Notes and none for Summary, the answer is an ask for less that
    keeps those two, and Adaptation takes it."""
    W, R, J, _ = live
    _model(monkeypatch, R, {"adapt.line": THREE})
    ref = _priced(live, {"Facts": (3, 0.07), "Notes": (2, 0.04), "Summary": (0, 0.0)}, SHAPED_HISTORY, ORGANIC, "Lab Co", shaped=True)
    acts = _actions(J, ref)
    assert acts[2:8] == ["proposal.created", "proposal.countered", "proposal.created", "proposal.granted", "workflow.validated", "workflow.registered"]
    assert W.dept(ref)["engines"] == ["Facts", "Notes"] and "conflict.raised" not in acts
    first, second = _prices(W, ref)
    assert first["answer"] == "counter" and first["keep"] == ["Facts", "Notes"] and first["proposal"] == "line"
    assert first["engines"] == ["Facts", "Notes", "Summary"]
    assert (first["estimate"]["calls"], first["estimate"]["usd"], first["estimate"]["basis"], first["estimate"]["runs"]) == (7, 0.19, "line", 5)
    assert first["estimate"]["per_engine"] == {"Facts": {"calls": 3, "usd": 0.07, "basis": "median", "runs": 3},
                                               "Notes": {"calls": 2, "usd": 0.04, "basis": "median", "runs": 2},
                                               "Summary": {"calls": 2, "usd": 0.08, "basis": "prior", "runs": 0}}
    assert first["room"] == {"calls": 5, "usd": 0.11} and first["remaining"] == {"calls": -2, "usd": -0.08}
    assert first["why"] == "room for 2 of 3 today: about 5 calls and 0.11 USD for these of the 5 calls and 0.11 USD left"
    assert first["indices"] == {"spend_per_run": {"Facts": 0.07, "Notes": 0.04, "Summary": 0.08},
                                "checks": {"Facts": "ok", "Notes": "ok", "Summary": "none"}}
    assert (second["answer"], second["keep"], second["engines"]) == ("accept", ["Facts", "Notes"], ["Facts", "Notes"]), "the ask is answered once, whole"
    assert second["remaining"] == {"calls": 0, "usd": 0.0}
    assert S.validate("priority.price", first) == [] and S.validate("priority.price", second) == []


def test_p3_no_room_gives_a_reject_a_conflict_and_step_4(live):
    """A no that ends in silence, or a bargain that never reaches Identity, must fail: with no room Priority says no, Adaptation
    raises the conflict, and Identity (step 4) is the one that asks the owner, once."""
    W, R, J, _ = live
    ref = _priced(live, {n: (0, 0.0) for n in LINE})
    acts = _actions(J, ref)
    assert acts[2:] == ["proposal.created", "proposal.refused", "conflict.raised", "identity.ruled", "ask.created"]
    assert next(e for e in J.events(ref) if e["action"] == "identity.ruled")["step"] == 4
    # Priority's no carries the ways out it priced, Adaptation passes them on in the conflict (W2-ADAPT, M5.4), and Identity puts the
    # owner one card that holds them (W2-IDENTITY): the question is still asked once, by Identity
    assert [a["kind"] for a in W.asks(ref) if a["status"] == "pending"] == ["blocked"]
    assert not [r for r in W.runs(ref) if not r.get("system") and r.get("what") != "history"], "the disputed work does not run"
    [row] = _prices(W, ref)
    assert row["answer"] == "reject" and row["keep"] == [] and row["room"] == {"calls": 0, "usd": 0.0}
    assert row["why"] == "no room today: even Plan costs about 3 calls and 0.08 USD against the 0 calls and 0.00 USD left"
    asked = next(a for a in W.asks(ref) if a["kind"] == "blocked")
    assert "Priority said no to the plan: no room today" in asked["text"]
    assert S.validate("priority.price", row) == []


def test_p3_enough_room_gives_a_yes(live):
    """Priority that asks for less, or says no, with room for the whole line, must fail."""
    W, R, J, _ = live
    ref = _priced(live, {"Plan": (50, 5.0), "Write": (50, 5.0), "Check": (50, 5.0), "Publish": (50, 5.0)})
    acts = _actions(J, ref)
    assert acts[2:5] == ["proposal.created", "proposal.granted", "workflow.validated"] and "conflict.raised" not in acts
    assert W.dept(ref)["workflows"][-1]["engines"] == LINE
    [row] = _prices(W, ref)
    assert row["answer"] == "accept" and row["keep"] == LINE and row["room"] == {"calls": 200, "usd": 20.0}
    assert row["remaining"] == {"calls": 189, "usd": round(20.0 - 0.395, 4)}
    assert row["why"].startswith("fits today: about 11 calls and 0.40 USD of the 200 calls and 20.00 USD left")
    assert S.validate("priority.price", row) == []


def test_p3_the_estimate_in_every_price_row_is_the_fixture_medians(live):
    """A row's estimate that is not what the engines' runs say must fail; each engine's price rides in per_engine."""
    W, R, J, _ = live
    ref = _priced(live, {"Plan": (50, 5.0), "Write": (50, 5.0), "Check": (50, 5.0), "Publish": (50, 5.0)})
    [row] = _prices(W, ref)
    assert row["estimate"]["per_engine"] == MEDIANS and row["estimate"]["runs"] == 7
    assert row["cycle_id"] and row["thread"] and row["round"] is None and row["schema_version"] == 1 and row["id"].startswith("pr-")


def test_p3_a_yes_the_room_cannot_hold_fails_its_step_and_nothing_is_granted(live, monkeypatch):
    """The covering that lets a model's yes through over a room that cannot hold the line must fail: the measured facts stand,
    the step fails, Adaptation is answered nothing, and no price is written for an answer that was never given."""
    W, R, J, _ = live
    _model(monkeypatch, R, {"priority.bargain": {"answer": "accept", "why": "fits today"}})
    ref = _priced(live, {n: (1, 0.01) for n in LINE})
    [step] = [r for r in R.step_rows(ref) if r["step"] == "priority.bargain"]
    assert step["status"] == "failed" and step["by"] == "model"
    assert "said yes to what costs more than the room holds: 11 calls and 0.40 USD go past the 4 calls and 0.04 USD left today" in step["why"]
    acts = _actions(J, ref)
    assert "proposal.granted" not in acts and "workflow.registered" not in acts and _prices(W, ref) == []


def test_p3_a_no_the_model_gives_over_ample_room_stands_because_approvals_only_tighten(live, monkeypatch):
    """A covering that turns a model's no into a failure would make Priority say yes against its own judgement."""
    W, R, J, _ = live
    _model(monkeypatch, R, {"priority.bargain": {"answer": "reject", "why": "no room in the envelope today"}})
    ref = _priced(live, {n: (50, 5.0) for n in LINE})
    assert "proposal.refused" in _actions(J, ref)
    [row] = _prices(W, ref)
    assert row["answer"] == "reject" and row["room"]["calls"] == 200 and row["why"] == "no room in the envelope today"
    assert S.validate("priority.price", row) == []


def test_p3_the_agent_is_told_what_the_line_is_likely_to_cost_and_what_remains(j2, monkeypatch):
    """The bargain line part gains two inputs: the estimate, each engine from what its runs spent, and what remains of the
    room. The engine and cost parts are sent what they were."""
    W, R, J, _ = j2
    ref = _born(j2, settle=False)
    _history(W, ref)
    sent = []
    monkeypatch.setattr(R, "_prompt", lambda fn, file, part, ref=None, **slots: sent.append((fn, file, part, slots)) or part)
    line = {"word": "line", "source": "library", "engines": [{"name": n, "does": "does " + n} for n in LINE]}
    c = {"ref": ref, "dept": W.dept(ref), "post": {"payload": line, "thread": "x-1"}, "bag": {}}
    c["bag"]["priority.read"] = V1.priority_read(c, None, None)
    assert V1.p_priority_bargain(c, None, None) == "line"
    (_, _, _, slots), = sent
    assert slots["estimate"] == ("11 calls and 0.40 USD (Plan: 3 calls and 0.08 USD, from 3 finished runs; Write: 7 calls and 0.28 USD, from 4 finished "
                                 "runs; Check: 1 call and 0.04 USD, a first guess; Publish: 0 calls and 0.00 USD, a first guess)")
    assert slots["remaining"] == "949 calls and 23.61 USD remain of the 960 calls and 24.00 USD left today"
    assert slots["room"] == "yes" and slots["limit"] == 6 and slots["source"] == "from the Library" and slots["calls"] == "240" and slots["usd"] == "6.00"
    assert set(slots) == {"source", "engines", "calls", "usd", "room", "limit", "estimate", "remaining"}, "the inputs S.PROMPTS names, no more"
    sent.clear()
    engine = {"word": "engine", "engine": "Booking", "offer": {"shape": {"name": "Booking", "does": "takes a booking", "needs": []}}}
    c["post"]["payload"] = engine
    c["bag"]["priority.read"] = V1.priority_read(c, None, None)
    V1.p_priority_bargain(c, None, None)
    assert set(sent[0][3]) == {"engine", "does", "needs", "calls", "usd", "room"}
    sent.clear()
    c["post"]["payload"] = {"word": "trial", "step": "write.page", "engine": "Write", "cost": "one more call a run, for 20 runs"}
    c["bag"]["priority.read"] = V1.priority_read(c, None, None)
    V1.p_priority_bargain(c, None, None)
    assert set(sent[0][3]) == {"word", "step", "cost", "room"}


def test_p3_an_engine_offer_is_priced_as_one_run_and_a_trial_as_what_it_adds(j2):
    """A trial priced as a whole run of the engine, or an offer as a constant, must fail: an engine offered is one run of it
    (Do's, when it is shaped on the fly); a trial is one more call a run for the runs it names, at call_usd."""
    W, R, J, _ = j2
    ref = _born(j2, settle=False)
    _history(W, ref)
    c = {"ref": ref, "dept": W.dept(ref), "bag": {}, "post": {"thread": "x-1", "payload": {"word": "engine", "engine": "Booking", "offer": {}}}}
    got = V1.priority_read(c, None, None)
    assert (got["names"], got["estimate"]["calls"], got["estimate"]["usd"], got["estimate"]["basis"]) == (["Booking"], 2, 0.08, "prior")
    assert got["room"] == {"calls": 240, "usd": 6.0} and got["facts"] == {"word": "engine", "room": True}
    c["post"]["payload"] = {"word": "trial", "step": "write.page", "engine": "Write", "cost": "one more call a run, for 20 runs"}
    got = V1.priority_read(c, None, None)
    assert (got["names"], got["estimate"]["calls"], got["estimate"]["usd"], got["estimate"]["basis"]) == (["Write"], 20, 0.8, "prior")
    assert got["estimate"]["per_engine"] == {"Write": {"calls": 20, "usd": 0.8, "basis": "prior", "runs": 0}}
    c["post"]["payload"] = {"word": "trial", "step": "write.page", "engine": "Write", "cost": "a trial"}
    assert V1.priority_read(c, None, None)["estimate"]["calls"] == 1, "a cost that names no runs is one call"
    for payload in ({"word": "engine", "engine": "Booking"}, {"word": "trial", "engine": "Write", "cost": "a call"}):
        c["post"]["payload"] = payload
        got = V1.priority_read(c, None, None)
        c["bag"] = {"priority.read": got}
        assert S.validate("priority.estimate", got["estimate"]) == []
        assert V1.d_priority_bargain(c, None, None)["answer"] == "accept"


def test_p3_an_offer_the_engines_room_cannot_hold_is_said_no_to_in_money_and_room(j2):
    """The offline answer to an engine offer when the engine's room is gone: no, and the why is only money and room."""
    W, R, J, _ = j2
    ref = _born(j2, settle=False)
    d = W.dept(ref)
    d["envelopes"]["Booking"] = {"calls": 1, "usd": 0.01}
    W.save_dept(ref, d)
    c = {"ref": ref, "dept": W.dept(ref), "bag": {}, "post": {"thread": "x-1", "payload": {"word": "engine", "engine": "Booking"}}}
    c["bag"]["priority.read"] = V1.priority_read(c, None, None)
    assert c["bag"]["priority.read"]["facts"] == {"word": "engine", "room": False}
    assert V1.d_priority_bargain(c, None, None) == {"answer": "reject", "why": "no room today: about 2 calls and 0.08 USD against the 1 call and 0.01 USD left"}


def test_p3_more_workflows_than_the_limit_is_an_ask_for_less_that_says_the_limit(j2):
    """The count a template allows still binds beside the money: eight workflows with ample room keep the first six."""
    W, R, J, _ = j2
    ref = _born(j2, settle=False)
    names = ["E%d" % i for i in range(8)]
    c = {"ref": ref, "dept": W.dept(ref), "bag": {}, "post": {"thread": "x-1", "payload": {"word": "line", "engines": [{"name": n} for n in names]}}}
    c["bag"]["priority.read"] = V1.priority_read(c, None, None)
    assert c["bag"]["priority.read"]["facts"]["room"] is False and c["bag"]["priority.read"]["fits"] == names[:6]
    got = V1.d_priority_bargain(c, None, None)
    assert got["answer"] == "counter" and got["keep"] == names[:6] and got["why"].endswith("(the limit is 6 workflows)")
    assert V1.CHECK["price_is_observed"](c, None, None, got)["ok"]
    assert not V1.CHECK["price_is_observed"](c, None, None, {"answer": "accept", "why": "fits"})["ok"]
    c["post"]["payload"]["engines"] = []
    c["bag"]["priority.read"] = V1.priority_read(c, None, None)
    assert V1.d_priority_bargain(c, None, None) == {"answer": "reject", "why": "the plan names no workflow"}


# ---- P4: Priority's view --------------------------------------------------------------------------------------------------
def _view(W, J, ref):
    """Priority's pane as the registry hands it out: the record, its cycle's events and its asks."""
    return V1.view(ref, W.dept(ref), J.events(ref), W.asks(ref))


def _price_row(**more):
    row = {"at": "2026-10-26T10:00:00+05:30", "proposal": "line", "estimate": {"calls": 3, "usd": 0.12, "basis": "prior", "runs": 0},
           "room": {"calls": 10, "usd": 1.0}, "answer": "accept", "why": "fits today"}
    row.update(more)
    return row


def test_p4_the_view_validates_empty_bargaining_limit_and_priced(live, monkeypatch):
    """A view that fails its interface, or one that shows a price from nowhere, must fail: the same pane in the four states a
    department is in when Priority is looked at."""
    W, R, J, _ = live
    empty = _born(live, org="Empty Co", settle=False)
    view = _view(W, J, empty)
    assert S.validate_view("priority", view) == [] and view["bargains"] == [] and view["prices"] == []
    assert [e["engine"] for e in view["envelopes"]][:4] == LINE and {e["share"] for e in view["envelopes"]} == {0.0}

    _model(monkeypatch, R, {"adapt.line": THREE})
    priced = _priced(live, {"Facts": (3, 0.07), "Notes": (2, 0.04), "Summary": (0, 0.0)}, SHAPED_HISTORY, ORGANIC, "Lab Co", shaped=True)
    view = _view(W, J, priced)
    assert S.validate_view("priority", view) == []
    assert [b["said"] for b in view["bargains"]] == ["asked for less", "said yes"], "the bargains, oldest first, as they were"
    assert [p["said"] for p in view["prices"]] == ["said yes", "asked for less"], "the prices, newest first"
    newest, oldest = view["prices"]
    assert (newest["answer"], newest["proposal"], newest["estimate"], newest["room"]) == ("accept", "line", {"calls": 5, "usd": 0.11}, {"calls": 5, "usd": 0.11})
    assert (oldest["answer"], oldest["estimate"], oldest["room"]) == ("counter", {"calls": 7, "usd": 0.19}, {"calls": 5, "usd": 0.11})
    assert oldest["why"] == "room for 2 of 3 today: about 5 calls and 0.11 USD for these of the 5 calls and 0.11 USD left"
    assert oldest["at"] and set(oldest) == {"at", "proposal", "answer", "said", "estimate", "room", "why"}

    limit = _born(live, org="Limit Co", settle=False)
    _envelopes(W, limit, Plan=(1, 0.05))
    today = datetime.now().astimezone().isoformat(timespec="seconds")
    W._write(W.ddir(limit) / "runs.json", W.runs(limit) + [_run_row("Plan", "asked", 1, 0.05, today)])
    view = _view(W, J, limit)
    assert S.validate_view("priority", view) == []
    assert next(e for e in view["envelopes"] if e["engine"] == "Plan")["share"] == 1.0 and view["prices"] == []


def test_p4_a_view_of_a_department_with_prices_validates_as_a_whole_through_the_contract(live, ctx):
    """Contract case 6 reads the fixture department's view; with prices on it, it still validates."""
    W, R, J, _ = live
    ref = ctx["ref"]
    W.append_row(ref, "prices.jsonl", _price_row())
    assert C.case_6(V1, ctx) == [] and _view(W, J, ref)["prices"][0]["said"] == "said yes"


def test_p4_the_prices_are_the_newest_few_newest_first_and_a_row_with_no_answer_is_not_shown(live, ctx, monkeypatch):
    monkeypatch.setattr(S, "MODE", "warn")      # the odd row has to be in the journal for the view to leave it out: warn mode keeps it
    W, R, J, _ = live
    ref = ctx["ref"]
    for i in range(14):
        W.append_row(ref, "prices.jsonl", _price_row(at="2026-10-26T10:%02d:00+05:30" % i, why="row %d" % i))
    with S.expect_refused() as met:
        try:
            W.append_row(ref, "prices.jsonl", {"at": "2026-10-26T11:00:00+05:30", "answer": "grant", "why": "a row that is no answer"})
        except S.SchemaFault:
            pass                       # in refuse mode the journal refuses the row; in warn mode it keeps it and reports
    assert met, "the journal checks every row it is given"
    view = _view(W, J, ref)
    assert [p["why"] for p in view["prices"]] == ["row %d" % i for i in range(13, 1, -1)], "twelve, newest first; the odd row is not one"
    assert S.validate_view("priority", view) == []


def test_p4_the_words_are_the_ones_the_pane_already_says_and_the_owners_not_the_insides(live, ctx):
    """said yes, asked for less, said no: the words of the bargains beside the prices, and of owner_words' phrase table; and
    a why that carries an inside word is said again in the owner's."""
    import owner_words
    W, R, J, _ = live
    assert V1.SAID == {"accept": "said yes", "counter": "asked for less", "reject": "said no"}
    table = dict(owner_words.BARGAIN_WORDS)
    assert table["Countered."].rstrip(".").lower() == V1.SAID["counter"] and table["Refused."].rstrip(".").lower() == V1.SAID["reject"]
    assert owner_words.plain("Granted within the envelope.") == "Said yes within the limit."
    ref = ctx["ref"]
    events = [{"action": a, "summary": "x", "occurred_at": "2026-10-26T10:00:00+05:30"} for a in ("proposal.granted", "proposal.countered", "proposal.refused")]
    pane = V1.view(ref, W.dept(ref), events, [])
    assert [b["said"] for b in pane["bargains"]] == list(V1.SAID.values()), "the pane's own bargains say the three words"
    W.append_row(ref, "prices.jsonl", _price_row(why="Priority countered (no room) and kept /Users/someone/secret/plan.md out"))
    assert V1.view(ref, W.dept(ref), [], [])["prices"][0]["why"] == "Priority asked for less (no room) and kept plan.md out", "names, never paths"


# ---- P5: Priority's writers say who they are --------------------------------------------------------------------------------
def _saves(monkeypatch, W):
    """Every save_dept call, with the function that made it and the `by` it passed; the real save still runs."""
    import sys
    calls, real = [], W.save_dept

    def spy(ref, d, by=None):
        calls.append((sys._getframe(1).f_code.co_name, by))
        return real(ref, d, by=by)
    monkeypatch.setattr(W, "save_dept", spy)
    return calls


def test_p5_set_envelope_says_it_is_priority_who_writes_and_leaves_no_ownership_row(live, monkeypatch):
    """A set_envelope that saves as nobody, or whose envelopes key reads as another layer's, must fail."""
    W, R, J, _ = live
    ref = _born(live, settle=False)
    saves, before = _saves(monkeypatch, W), S.REFUSED["count"]
    env = W.set_envelope(ref, "Plan", calls=7, usd=1.5, by="the owner")
    assert saves == [("set_envelope", "priority")] and env == {"calls": 7, "usd": 1.5}
    assert S.REFUSED["count"] == before, "no ownership row for a key that is Priority's"
    assert S.validate("envelope", W.dept(ref)["envelopes"]["Plan"]) == []
    assert any("set Plan's envelope" in r["what"] for r in W.runs(ref) if r.get("engine") == "Priority"), "the row still says who asked, in words"


def test_p5_priority_grant_says_it_is_priority_who_writes_and_every_envelope_it_gives_validates(live, monkeypatch):
    """A grant that saves as nobody must fail: the limits a registered plan is given are written by Priority, and are
    envelopes the interface accepts."""
    W, R, J, _ = live
    _model(monkeypatch, R, {"adapt.line": THREE})
    saves, before = _saves(monkeypatch, W), S.REFUSED["count"]
    ref = _born(live, ORGANIC, "Lab Co")
    given = [c for c in saves if c[0] == "priority_grant"]
    assert given == [("priority_grant", "priority")], saves
    envs = W.dept(ref)["envelopes"]
    assert {"Facts", "Notes", "Summary"} <= set(envs), "each engine the plan registered was given its limit"
    assert envs["Facts"] == {"calls": 240, "usd": 6.0}, "a work engine is given work_calls times the calls, from Priority's template"
    assert all(S.validate("envelope", env) == [] for env in envs.values())
    assert S.REFUSED["count"] == before, "no ownership row for envelopes across a whole department's birth"


def test_p5_a_save_that_names_its_layer_is_held_to_the_keys_that_layer_owns(live, ctx):
    """The point of saying who writes: with `by`, a key another layer owns is reported (a row), so a silent pass over the
    envelopes is a pass on the key's owner, not a check that was never made."""
    W, R, J, _ = live
    ref = ctx["ref"]
    d = W.dept(ref)
    d["envelopes"]["Plan"] = {"calls": 3, "usd": 0.5}
    with S.expect_refused() as met:
        W.save_dept(ref, dict(d, goal="a goal Priority has no business writing"), by="priority")
    assert met == ["$.goal: is Identity's, and Priority wrote it"]
    d2 = W.dept(ref)
    d2["envelopes"]["Plan"] = {"calls": 4, "usd": 0.5}
    before = S.REFUSED["count"]
    W.save_dept(ref, d2, by="priority")
    assert S.REFUSED["count"] == before


# ---- P6: the whole of it -----------------------------------------------------------------------------------------------------
def test_p6_the_contract_passes_for_priority_v1_with_no_part_on_the_fallback(ctx):
    """Any of the contract's eight cases failing for priority/v1, or a part read from the bundle, must fail."""
    for number, what, case in C.cases():
        assert case(V1, ctx) == [], "case %d: %s" % (number, what)
    assert C.on_the_md_fallback(V1) == []
    assert C.by_reference(V1) == {"by_reference": 3, "own": 9}, \
        "the three shared checks still delegate; the rest are this module's (priority_envelope moved in M5.4, priority_grant in M9.2)"


def test_p6_the_module_holds_no_state_besides_its_dicts_of_names():
    """A1.18: no module-level mutable state besides CODE, PROMPT, DRAFT, CHECK, WORDS and LAYOUT."""
    own = {"CODE", "PROMPT", "DRAFT", "CHECK", "WORDS", "LAYOUT"}
    held = {k: type(v).__name__ for k, v in vars(V1).items() if isinstance(v, (dict, list, set)) and not k.startswith("__")}
    assert set(held) == own, held


# ---- Q1: priced options on budget and bargain limits (M5.4) ------------------------------------------------------------------
# A limit reaches the owner as one question with up to three ways forward, built by code from the prices Priority holds: raise
# (add budget, up to RAISE_CAP times where it started), leave (give up the item the work was for) and stop. The envelope-held
# card carries them; a no carries them to Adaptation, which hands them on; a bargain at its limit has them asked for by thread.
ITEMS2 = [{"id": "D1", "text": "Every page checked and live", "how": "code", "level": "outcome"},
          {"id": "D2", "text": "The lessons for each topic are there", "how": "model", "level": "target"}]


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


def _held(live, plan_covers=True, items=True):
    """A department whose Plan is held at its limit (test_m0_4's way): Plan's limit is nought calls, two done-when items, and the
    registered plan says Plan alone is for D2 (the default gives every item to the last engine). The ask is filed again once
    the covers are as said, so the card is the one a department like that files."""
    W, R, J, _ = live
    ref = _born(live, settle=False)
    if items:
        W.put_done_items(ref, ITEMS2)
    W.set_envelope(ref, "Plan", calls=0)
    W.run_until_idle(ref, limit=300)
    if plan_covers:
        d = W.dept(ref)
        d["workflows"][-1]["covers"] = {"D1": ["Write", "Publish"], "D2": ["Plan"]}
        W.save_dept(ref, d)
        for a in [a for a in W.asks(ref) if a["kind"] == "envelope" and a["status"] == "pending"]:
            W._put_ask(ref, dict(a, status="replaced"))
        W.run_until_idle(ref, limit=5)
    return ref


def _envelope_ask(W, ref):
    [ask] = [a for a in W.asks(ref) if a["kind"] == "envelope" and a["status"] == "pending"]
    return ask


def test_j2_5_the_envelope_ask_names_the_limit_the_use_and_the_options(live):
    """A hold that files a card naming nothing, or one with no way forward, must fail (J2.5, BL-6): the card says the limit and
    what the engine has used, what happens next, and carries raise (up to twice the start), leave out and stop, each priced."""
    W, R, J, _ = live
    ref = _held(live)
    ask = _envelope_ask(W, ref)
    assert (ask["engine"], ask["escalated"], ask["chosen"]) == ("Plan", True, None)
    assert ask["text"] == ("Plan is out of today's envelope: it has used 0 of its 0 calls and 0.00 of its 6.00 USD. It waits until "
                           "tomorrow, unless you choose a way forward.")
    assert [o["id"] for o in ask["options"]] == ["raise:Plan", "leave:D2", "stop"]
    assert [o["kind"] for o in ask["options"]] == ["raise", "leave", "stop"]
    raise_, leave, stop = ask["options"]
    assert raise_["label"] == "Add budget for Plan"
    assert raise_["cost"] == "about 1 call more a day; Plan's limit becomes 1 call and 6.00 USD a day"
    assert raise_["params"] == {"what": "envelope", "engine": "Plan", "calls": 1, "usd": 6.0}
    assert (leave["label"], leave["cost"]) == ("Leave D2 out", "D2 is dropped from done-when (The lessons for each topic are there); nothing more is spent")
    assert (stop["label"], stop["cost"]) == ("Stop here", "the department stops where it is; you can start it again later")
    assert S.validate("identity.ask", ask) == [] and all(S.validate("option", o) == [] for o in ask["options"])
    held = [e for e in J.events(ref) if e["action"] == "envelope.held"]
    assert len(held) == 1 and held[0]["summary"] == "Plan is out of today's envelope", "the ledger says what it said"
    assert len([a for a in W.asks(ref) if a["kind"] == "envelope" and a["status"] == "pending"]) == 1, "one card, however often it is asked"
    for _ in range(5):
        W.run_until_idle(ref, limit=1)
    assert len([a for a in W.asks(ref) if a["kind"] == "envelope" and a["status"] == "pending"]) == 1


def _files_of(home):
    """Every file under a records home and the hash of its bytes."""
    import hashlib
    import os
    out = {}
    for root, _dirs, files in os.walk(home):
        for f in files:
            path = os.path.join(root, f)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, home)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def test_j2_5a_a_panel_read_never_files_the_envelope_card_and_the_tick_files_it_once(live):
    """Hard rule 4(g): the card an engine held at its limit files is the tick's. The gate is the module's own (it moved in M5.4, and the
    runtime's old body, which kept the guard, is no longer the one that runs), so a read of the department, which peeks, in every window
    before the tick files the card must write nothing: no ask, no ledger event, no row (found by a verifier 2026-10-27)."""
    W, R, J, _ = live
    ref = _born(live, settle=False)
    W.put_done_items(ref, ITEMS2)
    W.set_envelope(ref, "Plan", calls=0)
    slots, windows = 0, 0
    while True:
        before = _files_of(W.ddir(ref))
        R.next_due(ref, peek=True)
        W.status(ref)
        W.map_view(ref)
        after = _files_of(W.ddir(ref))
        assert sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)) == [], "a read before slot %d wrote" % slots
        assert [a for a in W.asks(ref) if a["kind"] == "envelope"] == []
        windows += 1
        if not W.run_until_idle(ref, limit=1):                      # nothing is due: the tick that asked is this one
            break
        slots += 1
        assert slots < 60
    assert windows >= 2, "the reads met the line before the tick that held Plan"
    ask = _envelope_ask(W, ref)
    assert ask["engine"] == "Plan" and [e["action"] for e in J.events(ref)].count("envelope.held") == 1, "the tick filed the card, and the ledger once"
    after = _files_of(W.ddir(ref))
    for _ in range(3):
        R.next_due(ref, peek=True)
        W.status(ref)
        W.map_view(ref)
    assert _files_of(W.ddir(ref)) == after, "and the reads after it write nothing"
    assert len([a for a in W.asks(ref) if a["kind"] == "envelope"]) == 1


def test_q1_raise_adds_the_budget_the_owner_chose_and_the_engine_runs_again(live):
    """A raise that is not applied, or one that lowers a limit, or one applied twice, must fail: the card's raise option sets
    Plan's limit to the one it names, by the owner's choice, and the held engine goes on."""
    W, R, J, _ = live
    ref = _held(live)
    ask = _envelope_ask(W, ref)
    assert W.limit_of(W.dept(ref), "Plan") == {"calls": 0, "usd": 6.0}
    got = W.choose_option(ref, ask["id"], "raise:Plan")
    assert got["status"] == "chosen" and got["chosen"]["id"] == "raise:Plan" and got["by"] == "the owner"
    assert W.dept(ref)["envelopes"]["Plan"] == {"calls": 1, "usd": 6.0}
    assert any(r["engine"] == "Priority" and "the owner's choice set Plan's envelope: 1 calls, 6.00 USD a day" in r["what"] for r in W.runs(ref))
    assert W.choose_option(ref, ask["id"], "raise:Plan")["status"] == "chosen", "the same choice again is the same answer"
    assert V1.apply_option(ref, got, got["options"][0])["raised"] is False, "a raise already made is not made again"
    assert V1.apply_option(ref, got, dict(got["options"][0], params={"what": "envelope", "engine": "Plan", "calls": 1, "usd": 1.0}))["raised"] is False, \
        "and a raise never lowers a limit"
    assert W.dept(ref)["envelopes"]["Plan"] == {"calls": 1, "usd": 6.0}
    W.run_until_idle(ref, limit=300)
    assert "Plan" in [r["engine"] for r in W.runs(ref) if not r.get("system")], "the engine the card held goes on"


def test_q1_leave_gives_up_the_item_the_held_engine_was_for(live):
    """A leave that changes nothing, or drops more than the item it names, must fail: the card has no thread for Identity's step,
    so the choice is put in place with the card: done-when keeps D1 and loses D2, and the goal is as it was."""
    W, R, J, _ = live
    ref = _held(live)
    ask, goal = _envelope_ask(W, ref), W.dept(ref)["goal"]
    W.choose_option(ref, ask["id"], "leave:D2")
    d = W.dept(ref)
    assert [i["id"] for i in d["done_items"]] == ["D1"] and d["goal"] == goal
    assert next(a for a in W.asks(ref) if a["id"] == ask["id"])["chosen"]["id"] == "leave:D2"
    assert W.dept(ref)["envelopes"]["Plan"]["calls"] == 0, "nothing is spent or raised by leaving something out"


def test_q1_stop_stops_the_department_where_it_is(live):
    """A stop that leaves the department running must fail: it is the owner's Stop, so the cycle says stopped and no engine
    starts."""
    W, R, J, _ = live
    ref = _held(live)
    ask = _envelope_ask(W, ref)
    W.choose_option(ref, ask["id"], "stop")
    assert W.dept(ref)["stopped"] is True and J.status(ref)["state"] == "stopped"
    before = len([r for r in W.runs(ref) if not r.get("system")])
    W.run_until_idle(ref, limit=20)
    assert len([r for r in W.runs(ref) if not r.get("system")]) == before


def test_q1_a_raise_past_twice_where_it_started_is_409_over_cap_through_the_asks_route(live):
    """A raise the cap does not hold must fail: past RAISE_CAP times where Plan's limit started the choice is 409 OVER_CAP,
    the card is as it was and the limit is untouched; at the cap it is applied. set_envelope holds it too when called for an
    option, and the box on the card (by the owner) sets any limit the owner types."""
    W, R, J, _ = live
    ref = _held(live)
    ask = _envelope_ask(W, ref)
    start = R.engine_limit("Plan")
    assert start == {"calls": 240, "usd": 6.0} and S.RAISE_CAP == 2.0
    stale = dict(ask["options"][0], params={"what": "envelope", "engine": "Plan", "calls": 481, "usd": 6.0})
    W._put_ask(ref, dict(ask, options=[stale] + ask["options"][1:]))
    api = _client()
    url = "/api/native/%s/asks/%s" % (ref, ask["id"])
    over = api.post(url, json={"option": "raise:Plan"})
    assert (over.status_code, over.json()["detail"]) == (409, {"code": "OVER_CAP"})
    assert next(a for a in W.asks(ref) if a["id"] == ask["id"])["status"] == "pending", "the card waits as it was"
    assert W.dept(ref)["envelopes"]["Plan"] == {"calls": 0, "usd": 6.0}
    money = dict(stale, params={"what": "envelope", "engine": "Plan", "calls": 480, "usd": 12.01})
    W._put_ask(ref, dict(ask, options=[money] + ask["options"][1:]))
    assert api.post(url, json={"option": "raise:Plan"}).status_code == 409
    at_cap = dict(stale, params={"what": "envelope", "engine": "Plan", "calls": 480, "usd": 12.0})
    W._put_ask(ref, dict(ask, options=[at_cap] + ask["options"][1:]))
    ok = api.post(url, json={"option": "raise:Plan"})
    assert ok.status_code == 200 and W.dept(ref)["envelopes"]["Plan"] == {"calls": 480, "usd": 12.0}
    with pytest.raises(W.AskError) as exc:
        W.set_envelope(ref, "Plan", calls=481, by="option")
    assert exc.value.code == "OVER_CAP"
    assert W.set_envelope(ref, "Plan", calls=481, by="the owner")["calls"] == 481, "the owner's own box is not held to the cap"


def test_q1_no_raise_is_offered_past_the_cap(live):
    """A card that offers a raise it would refuse must fail: at twice where it started there is no raise, only leave and stop."""
    W, R, J, _ = live
    ref = _held(live)
    W.set_envelope(ref, "Plan", calls=480, usd=12.0)
    today = datetime.now().astimezone().isoformat(timespec="seconds")
    W._write(W.ddir(ref) / "runs.json", W.runs(ref) + [_run_row("Plan", "ok", 480, 0.5, today)])
    for a in [a for a in W.asks(ref) if a["kind"] == "envelope" and a["status"] == "pending"]:
        W._put_ask(ref, dict(a, status="replaced"))
    W.run_until_idle(ref, limit=5)
    assert [o["id"] for o in _envelope_ask(W, ref)["options"]] == ["leave:D2", "stop"]


def _rejected(live, limits=None, items=True):
    """A department whose plan Priority says no to by the arithmetic alone (no room in any limit), with two done-when items."""
    W, R, J, _ = live
    ref = _born(live, settle=False)
    if items:
        W.put_done_items(ref, ITEMS2)
    _envelopes(W, ref, **(limits or {n: (0, 0.0) for n in LINE}))
    _history(W, ref)
    W.run_until_idle(ref, limit=300)
    return ref


def _priority_posts(R, ref, act):
    return [p for p in R.board(ref) if p["src"] == "Priority" and p["msg_type"] == act]


def test_q1_a_no_carries_raise_leave_and_stop_priced_from_what_the_line_costs(live):
    """A no that carries no way forward, or one priced from a constant, must fail: with no room the line costs 11 calls and
    0.40 USD (the medians of the fixture), so the first engine the room does not reach is offered that much more."""
    W, R, J, _ = live
    ref = _rejected(live)
    [no] = _priority_posts(R, ref, "reject-proposal")
    assert no["payload"]["word"] == "line" and no["payload"]["why"].startswith("no room today: even Plan costs about 3 calls and 0.08 USD")
    opts = no["payload"]["options"]
    assert [o["id"] for o in opts] == ["raise:Plan", "leave:D2", "stop"] and [o["kind"] for o in opts] == ["raise", "leave", "stop"]
    assert opts[0]["params"] == {"what": "envelope", "engine": "Plan", "calls": 11, "usd": 0.395}
    assert opts[0]["cost"] == "about 11 calls and 0.40 USD more a day; Plan's limit becomes 11 calls and 0.40 USD a day"
    assert opts[1]["label"] == "Leave D2 out" and opts[2]["id"] == "stop"
    assert all(S.validate("option", o) == [] for o in opts) and len(opts) <= S.OPTIONS_MAX
    assert S.validate("act.any", no["payload"]) == [], "the payload is the interface's"
    [row] = _prices(W, ref)
    assert row["answer"] == "reject" and "options" not in row, "the price row is the price, not the card"


def test_q1_a_counter_and_a_yes_carry_no_options(live, monkeypatch):
    """Options on an answer that is not a no must fail: they are the ways out of a limit, and a yes or an ask for less
    is no limit."""
    W, R, J, _ = live
    _model(monkeypatch, R, {"adapt.line": THREE})
    ref = _priced(live, {"Facts": (3, 0.07), "Notes": (2, 0.04), "Summary": (0, 0.0)}, SHAPED_HISTORY, ORGANIC, "Lab Co", shaped=True)
    answers = _priority_posts(R, ref, "propose") + _priority_posts(R, ref, "accept-proposal")
    assert len(answers) == 2 and all("options" not in p["payload"] for p in answers)


def test_q1_a_raise_is_the_shortfall_from_where_the_engine_stands_today(live):
    """A raise bigger than the shortfall, one that forgets what the engine spent today, or one that leaves the line short, must
    fail: with Plan's limit 2 calls and 0.04 USD, one call and a cent spent today, and the other limits at nought, the line
    (11 calls, 0.395 USD) is short of 10 calls and 0.365 USD, so Plan is raised from where it stands, and then the room holds
    the line."""
    W, R, J, _ = live
    ref = _born(live, settle=False)
    _envelopes(W, ref, Plan=(2, 0.04), Write=(0, 0.0), Check=(0, 0.0), Publish=(0, 0.0))
    _history(W, ref)
    today = datetime.now().astimezone().isoformat(timespec="seconds")
    W._write(W.ddir(ref) / "runs.json", W.runs(ref) + [_run_row("Plan", "asked", 1, 0.01, today)])
    W.run_until_idle(ref, limit=300)
    [no] = _priority_posts(R, ref, "reject-proposal")
    assert no["payload"]["why"] == "no room today: even Plan costs about 3 calls and 0.08 USD against the 1 call and 0.03 USD left"
    raise_ = no["payload"]["options"][0]
    assert raise_["params"] == {"what": "envelope", "engine": "Plan", "calls": 12, "usd": 0.405}
    assert raise_["cost"] == "about 10 calls and 0.36 USD more a day; Plan's limit becomes 12 calls and 0.41 USD a day"
    assert V1.apply_option(ref, {}, raise_)["raised"] is True
    room = V1.room_of(ref, W.dept(ref), LINE)
    assert room == {"calls": 11, "usd": 0.395}, "the line costs 11 calls and 0.395 USD, and the room holds exactly that"


def test_q1_a_line_of_more_workflows_than_the_limit_is_offered_no_raise(live):
    """A raise offered for what no money mends must fail: eight workflows against a limit of six are not a matter of budget."""
    W, R, J, _ = live
    ref = _born(live, settle=False)
    names = ["E%d" % i for i in range(8)]
    d = W.dept(ref)
    est = {"calls": 99, "usd": 5.0}
    got = V1.line_options(ref, d, names, {}, est, {"calls": 0, "usd": 0.0}, [], 6)
    assert [o["id"] for o in got] == ["stop"], "no raise, and no item to leave out of a line that covers none"
    one = V1.line_options(ref, d, ["Plan"], {}, est, {"calls": 0, "usd": 0.0}, [], 6)
    assert [o["id"] for o in one] == ["raise:Plan", "stop"]


def test_q1_a_bargain_at_its_limit_has_its_options_asked_for_by_thread(live, monkeypatch):
    """A limit with no way forward must fail: when the bargain reaches its hops the conflict goes to Identity, and the ways
    forward for the line it was about are Priority's to give, by thread, priced and built by code."""
    W, R, J, _ = live
    monkeypatch.setattr(R, "BOUNDS", {"hops": 1, "seconds": 900, "usd": 0.5})
    ref = _born(live, settle=False)
    W.put_done_items(ref, ITEMS2)
    W.run_until_idle(ref, limit=300)
    raised = next(e for e in J.events(ref) if e["action"] == "conflict.raised")
    assert raised["payload"]["bound"] == "hops"
    thread = next(p["thread"] for p in R.board(ref) if p["msg_type"] == "propose" and (p["payload"] or {}).get("word") == "line")
    opts = layers.call(ref, "priority", "limit_options", ref, thread)
    assert [o["id"] for o in opts] == ["leave:D2", "stop"], "the room is ample, so money is not what the line is short of"
    assert all(S.validate("option", o) == [] for o in opts)
    assert layers.call(ref, "priority", "limit_options", ref, None) == [] and layers.call(ref, "priority", "limit_options", ref, "x-none") == []


def test_q1_no_option_is_worded_by_a_model(live, monkeypatch):
    """An option whose words a model wrote must fail: building them calls no model, and what a model says as its reason
    reaches no label and no cost."""
    W, R, J, _ = live
    calls = []
    _model(monkeypatch, R, {"priority.bargain": {"answer": "reject", "why": "MODELWORDS-zz"}})
    inner = R.MODEL
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: calls.append(step["id"]) or inner(prompt, step))
    ref = _rejected(live)
    [no] = _priority_posts(R, ref, "reject-proposal")
    assert no["payload"]["why"] == "MODELWORDS-zz" and "priority.bargain" in calls
    assert all("MODELWORDS" not in o["label"] + o["cost"] for o in no["payload"]["options"])
    calls.clear()
    d = W.dept(ref)
    V1.line_options(ref, d, LINE, {"D2": ["Publish"]}, {"calls": 11, "usd": 0.4}, {"calls": 0, "usd": 0.0}, [], 6)
    V1.hold_options(ref, d, "Plan", 0, 0.0, {"calls": 0, "usd": 6.0})
    V1.limit_options(ref, None)
    assert calls == [], "the options are built by code"


def test_q1_priority_applies_only_the_raise_and_a_raise_names_what_it_raises(live):
    """An option that names nothing to raise must be refused before it is recorded, and the module hands a card with a thread
    only the raise to apply."""
    W, R, J, _ = live
    ref = _held(live)
    with pytest.raises(ValueError):
        V1.check_raise(ref, {"id": "raise:x", "params": {"what": "weather"}})
    with pytest.raises(ValueError):
        V1.check_raise(ref, {"id": "raise:x", "params": {"what": "envelope", "engine": "Nobody", "calls": 1, "usd": 1.0}})
    threaded = dict(_envelope_ask(W, ref), thread="x-1")
    assert V1.apply_choice(ref, threaded, W.option("stop", "Stop here", "x")) == {}
    assert W.dept(ref).get("stopped") is not True


# ---- Q2: the goal's ceiling (M9.2) --------------------------------------------------------------------------------------------
# Priority holds one ceiling for the whole goal beside its engines' daily limits: dept.ceiling, written once at the first
# registration (rounds, and the calls and money of that many runs of the line), raised only by the owner's choice up to RAISE_CAP
# times where it started. A round Adaptation proposes is answered by code against it: yes with a why in money and room, or no with
# [raise ceiling (+2 rounds), leave, stop].
@pytest.fixture
def rounds_sendable(monkeypatch):
    """Adaptation's propose/round to Priority is W2-ADAPT's row of the interface; until it is merged a test that posts a round
    adds it, so the act is judged as the interface will judge it."""
    if not any(r["act"] == "propose" and "round" in r["words"] for r in S.SENDS["Adaptation"]):
        monkeypatch.setitem(S.SENDS, "Adaptation", list(S.SENDS["Adaptation"]) +
                            [{"act": "propose", "words": ("round",), "to": ("Priority",), "payload": "act.round"}])


def _propose_round(live, ref, n, correction="put D2 right", covers=("D2",), thread=None):
    """What Adaptation posts to Priority for a round (act.round), and the department let run until Priority has answered."""
    W, R, J, _ = live
    row = R.post(ref, "Adaptation", "Priority", "propose", {"word": "round", "round": n, "correction": correction, "covers": list(covers)},
                 thread=thread)
    W.run_until_idle(ref, limit=100)
    return row


def _round_answers(R, ref, n=None):
    return [p for p in R.board(ref) if p["src"] == "Priority" and (p["payload"] or {}).get("word") == "round"
            and (n is None or p["payload"].get("round") == n)]


def _spend_runs(W, ref, calls, usd):
    """What each work run of the department spent, written to runs.json: offline a run spends nothing, and a ceiling is of money."""
    rows = W.runs(ref)
    for r in rows:
        if not r.get("system"):
            r["spend"] = {"calls": calls, "usd": usd}
    W._write(W.ddir(ref) / "runs.json", rows)


def _settled(live, items=True, org="Acme Learning"):
    """A department as a person makes one, run until it waits on the owner's first publish, with two done-when items."""
    W, R, J, _ = live
    ref = _born(live, org=org, settle=False)
    if items:
        W.put_done_items(ref, ITEMS2)
    W.run_until_idle(ref, limit=300)
    return ref


def test_q2_the_ceiling_is_written_once_at_the_first_registration_and_validates(live, monkeypatch):
    """A goal with no ceiling, one written by anyone but Priority, or one that is rewritten by a second registration, must fail:
    ROUNDS_DEFAULT rounds, and for the calls and the money that many runs of the line at its estimate, start the same."""
    W, R, J, _ = live
    saves, before = _saves(monkeypatch, W), S.REFUSED["count"]
    ref = _born(live, settle=False)
    assert "ceiling" not in W.dept(ref)
    prior = V1.estimate_of(ref, LINE, "line")
    W.run_until_idle(ref, limit=300)
    c = W.dept(ref)["ceiling"]
    assert S.ROUNDS_DEFAULT == 6 and c["rounds"] == 6
    assert (c["calls"], c["usd"]) == (6 * prior["calls"], round(6 * prior["usd"], 4)) and c["calls"] > 0
    assert c["start"] == {"rounds": 6, "calls": c["calls"], "usd": c["usd"]} and c["at"] and "raised" not in c
    assert S.validate("priority.ceiling", c) == [] and S.validate("department", W.dept(ref)) == []
    assert ("ensure_ceiling", "priority") in saves and S.REFUSED["count"] == before, "Priority's key, written by Priority"
    ledger = [e for e in J.events(ref) if e["action"] == "envelope.granted"]
    assert len(ledger) == 4, "and the limits are given as they were"
    # one that exists is never rewritten: not by the same plan again, not by a born word on the board
    mine = dict(c, rounds=9, calls=c["calls"] + 5)
    d = W.dept(ref)
    d["ceiling"] = mine
    W.save_dept(ref, d, by="priority")
    assert V1.ensure_ceiling(ref, LINE) == (mine, False)
    R.post(ref, "Identity", ["Priority"], "inform", {"word": "born", "version": 1, "engines": LINE})
    W.run_until_idle(ref, limit=50)
    assert W.dept(ref)["ceiling"] == mine


def test_q2_a_department_of_each_kind_is_given_its_ceiling_at_its_first_registration(live, monkeypatch):
    """The default kind (one Do engine) and an organic line, as well as a website, are given a ceiling: the same rule for every
    kind."""
    W, R, J, _ = live
    d, _ = W.create("dref-answers", "Answers", None, kind="default")
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    W.save_dept(d["ref"], d)
    J.start(d["ref"])
    W.give_goal(d["ref"], "Answer what the science team asks about the lab rota")
    prior = V1.estimate_of(d["ref"], ["Do"], "line")
    W.run_until_idle(d["ref"], limit=300)
    assert W.dept(d["ref"])["ceiling"]["calls"] == 6 * prior["calls"] and W.dept(d["ref"])["ceiling"]["rounds"] == 6
    _model(monkeypatch, R, {"adapt.line": THREE})
    organic = _born(live, ORGANIC, "Lab Co")
    c = W.dept(organic)["ceiling"]
    names = W.dept(organic)["workflows"][-1]["engines"]
    assert names == ["Facts", "Notes", "Summary"] and S.validate("priority.ceiling", c) == []
    assert c["rounds"] == 6 and c["start"]["calls"] == c["calls"]


def test_q2_a_round_inside_the_ceiling_is_said_yes_with_its_why_in_money_and_room(live, rounds_sendable):
    """A round the ceiling holds that is refused, or an answer that names no money, must fail: round 2 of 6 is yes, and the
    price row says the round."""
    W, R, J, _ = live
    ref = _settled(live)
    _spend_runs(W, ref, 2, 0.1)
    c = W.dept(ref)["ceiling"]
    spent, est = V1.spent_of(ref), V1.estimate_of(ref, LINE, "line")
    assert spent == {"calls": 6, "usd": 0.3} and est["calls"] == 6, "three runs of two calls; Publish has not run"
    _propose_round(live, ref, 2)
    [yes] = _round_answers(R, ref)
    assert yes["msg_type"] == "accept-proposal" and "options" not in yes["payload"] and yes["payload"]["round"] == 2
    assert yes["payload"]["why"] == "inside the ceiling: round 2 of 6, about %s of the %s left" % (
        V1._say_cost(est["calls"], est["usd"]), V1._say_cost(c["calls"] - spent["calls"], c["usd"] - spent["usd"]))
    [row] = [r for r in _prices(W, ref) if r["proposal"] == "round"]
    assert (row["answer"], row["round"], row["keep"], row["engines"]) == ("accept", 2, LINE, LINE) and row["why"] == yes["payload"]["why"]
    assert row["room"] == {"calls": c["calls"] - 6, "usd": round(c["usd"] - 0.3, 4)}
    assert row["remaining"] == {"calls": c["calls"] - 6 - est["calls"], "usd": round(c["usd"] - 0.3 - est["usd"], 4)}
    assert S.validate("priority.price", row) == [] and row["thread"] == yes["thread"]
    assert [p["msg_type"] for p in R.board(ref) if p["thread"] == yes["thread"]] == ["propose", "accept-proposal"]
    assert S.validate("act.any", yes["payload"]) == []


def test_q2_a_stub_round_7_of_6_is_refused_with_three_typed_options(live, rounds_sendable):
    """A round past the ceiling that is funded, or one refused with no way forward, must fail (M9.2): round 7 of 6 is said no
    to in rounds, and carries [raise the ceiling by two rounds, leave out the item, stop], each typed and priced."""
    W, R, J, _ = live
    ref = _settled(live)
    c = W.dept(ref)["ceiling"]
    _propose_round(live, ref, 7)
    [no] = _round_answers(R, ref)
    assert no["msg_type"] == "reject-proposal" and no["payload"]["round"] == 7
    assert no["payload"]["why"] == "no room in the ceiling: round 7 against a ceiling of 6 rounds"
    opts = no["payload"]["options"]
    assert [o["id"] for o in opts] == ["raise:ceiling", "leave:D2", "stop"] and [o["kind"] for o in opts] == ["raise", "leave", "stop"]
    assert opts[0]["label"] == "Add 2 more rounds"
    assert opts[0]["params"] == {"what": "ceiling", "rounds": 8, "calls": c["calls"], "usd": c["usd"]}
    assert opts[0]["cost"].endswith("the goal's ceiling becomes 8 rounds, %s" % V1._say_cost(c["calls"], c["usd"]))
    assert opts[1]["cost"] == "D2 is dropped from done-when (The lessons for each topic are there); nothing more is spent"
    assert all(S.validate("option", o) == [] for o in opts) and S.validate("act.any", no["payload"]) == []
    [row] = [r for r in _prices(W, ref) if r["proposal"] == "round"]
    assert (row["answer"], row["round"], row["keep"]) == ("reject", 7, []) and row["why"] == no["payload"]["why"]
    assert S.validate("priority.price", row) == []
    assert W.dept(ref)["ceiling"] == c, "a no changes nothing"


def test_q2_a_raise_of_the_ceiling_is_applied_by_code_two_rounds_at_a_time_up_to_the_cap(live, rounds_sendable):
    """A raise that is not applied, one that goes past twice where the ceiling started, or one still offered at the cap, must
    fail: rounds 8, 10, 12 are the owner's, the money follows (the runs the added rounds cost, held to twice its start), the
    start never moves, and at twelve there is no raise left to offer."""
    W, R, J, _ = live
    ref = _settled(live)
    _spend_runs(W, ref, 2, 0.1)
    start = dict(W.dept(ref)["ceiling"]["start"])
    est = V1.estimate_of(ref, LINE, "line")
    for n, rounds in ((7, 8), (9, 10), (11, 12)):
        _propose_round(live, ref, n)
        no = _round_answers(R, ref, n)[-1]
        raise_ = no["payload"]["options"][0]
        assert raise_["id"] == "raise:ceiling" and raise_["params"]["rounds"] == rounds
        ask = W.options_ask("blocked", "The round is past the ceiling.", no["payload"]["options"], who="Identity")
        W._put_ask(ref, ask)
        got = W.choose_option(ref, ask["id"], "raise:ceiling")
        assert got["status"] == "chosen" and got["chosen"]["id"] == "raise:ceiling"
        c = W.dept(ref)["ceiling"]
        assert c["rounds"] == rounds and c["start"] == start and S.validate("priority.ceiling", c) == []
        assert (c["calls"], c["usd"]) == (raise_["params"]["calls"], raise_["params"]["usd"])
        assert c["calls"] <= 2 * start["calls"] and c["usd"] <= round(2 * start["usd"], 4)
        assert c["raised"][-1]["by"] == "the owner" and c["raised"][-1]["to"] == {"rounds": rounds, "calls": c["calls"], "usd": c["usd"]}
    assert len(c["raised"]) == 3 and c["rounds"] == 2 * start["rounds"] == 12
    assert any("the owner's choice raised the goal's ceiling: 12 rounds" in r["what"] for r in W.runs(ref) if r.get("engine") == "Priority")
    _propose_round(live, ref, 13)
    last = _round_answers(R, ref, 13)[-1]
    assert [o["id"] for o in last["payload"]["options"]] == ["leave:D2", "stop"], "at the cap there is no raise to offer"
    again = V1.apply_option(ref, {}, raise_)
    assert again["raised"] is False and W.dept(ref)["ceiling"]["rounds"] == 12, "a raise already made is not made again"


def test_q2_a_raise_past_the_cap_is_409_over_cap_and_the_ceiling_stays(live, rounds_sendable):
    """A raise of the ceiling past twice where it started that is taken, must fail: through POST /asks/{aid} it is 409 OVER_CAP,
    the card waits as it was and the ceiling is untouched; in any one of rounds, calls or money."""
    W, R, J, _ = live
    ref = _settled(live)
    c = W.dept(ref)["ceiling"]
    api = _client()
    for params in ({"rounds": 13, "calls": c["calls"], "usd": c["usd"]}, {"rounds": 8, "calls": 2 * c["calls"] + 1, "usd": c["usd"]},
                   {"rounds": 8, "calls": c["calls"], "usd": 2 * c["usd"] + 0.01}):
        stale = W.option("raise:ceiling", "Add 2 more rounds", "about a lot more", dict(params, what="ceiling"))
        ask = W.options_ask("blocked", "The round is past the ceiling.", [stale, W.option("stop", "Stop here", "x")])
        W._put_ask(ref, ask)
        got = api.post("/api/native/%s/asks/%s" % (ref, ask["id"]), json={"option": "raise:ceiling"})
        assert (got.status_code, got.json()["detail"]) == (409, {"code": "OVER_CAP"}), params
        assert next(a for a in W.asks(ref) if a["id"] == ask["id"])["status"] == "pending"
        assert W.dept(ref)["ceiling"] == c
    ok = W.option("raise:ceiling", "Add 2 more rounds", "x", {"what": "ceiling", "rounds": 12, "calls": 2 * c["calls"], "usd": round(2 * c["usd"], 4)})
    ask = W.options_ask("blocked", "The round is past the ceiling.", [ok])
    W._put_ask(ref, ask)
    assert api.post("/api/native/%s/asks/%s" % (ref, ask["id"]), json={"option": "raise:ceiling"}).status_code == 200
    assert W.dept(ref)["ceiling"]["rounds"] == 12


def test_q2_a_round_past_the_calls_or_the_money_is_said_no_to_in_money_and_the_raise_is_held_to_the_cap(live, rounds_sendable):
    """A round funded though the goal has spent what the ceiling holds must fail: with 12 calls and 0.60 USD spent, a line
    estimated at the same again, and a ceiling of 20 calls, round 2 is over by calls, and the raise offered is the most the cap
    allows, said so."""
    W, R, J, _ = live
    ref = _settled(live)
    _spend_runs(W, ref, 4, 0.2)
    d = W.dept(ref)
    d["ceiling"] = {"rounds": 6, "calls": 20, "usd": 5.0, "start": {"rounds": 6, "calls": 20, "usd": 5.0}, "at": W.now()}
    W.save_dept(ref, d, by="priority")
    assert V1.spent_of(ref) == {"calls": 12, "usd": 0.6} and V1.estimate_of(ref, LINE, "line")["calls"] == 12
    _propose_round(live, ref, 2)
    [no] = _round_answers(R, ref)
    assert no["payload"]["why"] == "no room in the ceiling: about 12 calls and 0.60 USD against the 8 calls and 4.40 USD left"
    raise_ = no["payload"]["options"][0]
    assert raise_["params"] == {"what": "ceiling", "rounds": 8, "calls": 40, "usd": 5.0 + 2 * 0.6}, "twice the 20 calls it started at, no more"
    assert raise_["cost"] == "about 20 calls and 1.20 USD more; the goal's ceiling becomes 8 rounds, 40 calls and 6.20 USD (the most allowed)"
    [row] = [r for r in _prices(W, ref) if r["proposal"] == "round"]
    assert row["room"] == {"calls": 8, "usd": 4.4} and row["remaining"] == {"calls": -4, "usd": 3.8}


def test_q2_a_model_cannot_fund_a_round_the_ceiling_does_not_hold_and_its_no_stands(live, rounds_sendable, monkeypatch):
    """A covering that lets a model's yes through over a ceiling that is gone must fail, and one that turns the model's no into a
    failure would make Priority say yes against its judgement: the model is sent the round part, round 7 of 6 said yes to fails
    the step and posts nothing, and round 2 said no to stands."""
    W, R, J, _ = live
    ref = _settled(live)
    sent = []

    def model(prompt):
        sent.append(prompt)
        return {"answer": "accept", "why": "fits"} if len(sent) == 1 else {"answer": "reject", "why": "no room in the ceiling today"}
    _model(monkeypatch, R, {"priority.bargain": model})
    _propose_round(live, ref, 7, correction="put D2 right: the lessons for fractions")
    asked = sent[0]
    assert "Adaptation proposes another round on the line" in asked and "THE ROUND: round 7\n" in asked
    assert "WHAT IT PUTS RIGHT: put D2 right: the lessons for fractions\n" in asked and "ROOM IN THE CEILING: no\n" in asked
    assert "THE GOAL'S CEILING: 6 rounds, " in asked and "WHAT REMAINS OF THE CEILING AFTER IT: " in asked
    assert asked.rstrip().endswith('Return ONLY a JSON object: {"answer": "accept" | "reject", "why": "one line, in money and room only"}.')
    [step] = [r for r in R.step_rows(ref) if r["step"] == "priority.bargain" and r["facts"] == {"word": "round", "room": False}]
    assert step["status"] == "failed" and step["by"] == "model"
    assert "said yes to a round the ceiling does not hold: round 7 against a ceiling of 6 rounds" in step["why"]
    assert _round_answers(R, ref) == [] and [r for r in _prices(W, ref) if r["proposal"] == "round"] == []
    _propose_round(live, ref, 2)
    [no] = _round_answers(R, ref)
    assert no["msg_type"] == "reject-proposal" and no["payload"]["why"] == "no room in the ceiling today"
    assert [o["id"] for o in no["payload"]["options"]] == ["leave:D2", "stop"], "the ceiling holds the round, so no raise would mend a no"
    assert "ROOM IN THE CEILING: yes\n" in sent[1]


def test_q2_a_round_has_no_ask_for_less(live, rounds_sendable, monkeypatch):
    """A counter to a round that is posted as one must fail: a round is held or it is not."""
    W, R, J, _ = live
    ref = _settled(live)
    _model(monkeypatch, R, {"priority.bargain": {"answer": "counter", "why": "room for two rounds", "keep": ["Plan"]}})
    _propose_round(live, ref, 2)
    [step] = [r for r in R.step_rows(ref) if r["step"] == "priority.bargain" and r["facts"] == {"word": "round", "room": True}]
    assert step["status"] == "failed" and "not an answer to a round: 'counter'" in step["why"]
    assert _round_answers(R, ref) == []


def test_q2_the_round_is_held_to_the_ceiling_at_its_edges(live):
    """A boundary read wrong must fail: the last round is held, the one after it is not; the room is exactly enough or one
    short; a round of nought is no round."""
    W, R, J, _ = live
    est = {"calls": 6, "usd": 0.3}
    c = {"rounds": 6, "calls": 66, "usd": 3.0, "start": {"rounds": 6, "calls": 66, "usd": 3.0}}

    def read(n, spent_calls, spent_usd):
        room = {"calls": 66 - spent_calls, "usd": round(3.0 - spent_usd, 4)}
        return {"word": "round", "round": n, "ceiling": c, "estimate": est, "room": room, "spent": {"calls": spent_calls, "usd": spent_usd}}
    assert V1.round_within_ceiling(read(6, 60, 2.7))["answer"] == "accept", "the room is exactly enough, and so is round 6 of 6"
    assert V1.round_within_ceiling(read(6, 61, 2.7))["answer"] == "reject"
    assert V1.round_within_ceiling(read(6, 60, 2.71))["answer"] == "reject"
    assert V1.round_within_ceiling(read(7, 0, 0.0))["over"] == ["round 7 against a ceiling of 6 rounds"]
    assert V1.round_within_ceiling(read(0, 0, 0.0))["answer"] == "reject"
    both = V1.round_within_ceiling(read(7, 66, 3.0))
    assert both["why"] == "no room in the ceiling: round 7 against a ceiling of 6 rounds; about 6 calls and 0.30 USD against the 0 calls and 0.00 USD left"
    ok = V1.CHECK["round_within_ceiling"]
    ctx = {"bag": {"priority.read": read(7, 0, 0.0)}}
    assert ok(ctx, None, None, {"answer": "reject", "why": "no room"})["ok"] and not ok(ctx, None, None, {"answer": "accept", "why": "fits"})["ok"]
    assert ok({"bag": {"priority.read": read(2, 0, 0.0)}}, None, None, {"answer": "accept", "why": "fits"})["ok"]
    assert V1.CHECK["price_is_observed"](ctx, None, None, {"answer": "accept", "why": "fits"})["ok"] is False, "the step's covering reads a round"
    for out in S.CONTRACT_SAMPLES["round_within_ceiling"]["good"]:
        assert ok(None, None, None, out)["ok"] is True, out
    for out in S.CONTRACT_SAMPLES["round_within_ceiling"]["bad"]:
        assert ok(None, None, None, out)["ok"] is False, out


def test_q2_the_interface_names_the_round_part_its_covering_and_the_ceiling_in_the_view():
    """A round part the interface does not name, a covering it does not list, or a view that cannot carry the ceiling, must fail."""
    part = S.PROMPTS["priority"]["bargain"]["round"]
    assert part["inputs"] == ("round", "correction", "estimate", "room", "ceiling", "remaining") and part["read_by"] == "priority.bargain"
    assert part["returns"] == 'Return ONLY a JSON object: {"answer": "accept" | "reject", "why": "one line, in money and room only"}.'
    assert ("priority", "bargain", "round") in S.ADDED_PARTS and "round_within_ceiling" in S.CHECKS["priority"]
    view = S.DEFS["view.priority"]
    assert "ceiling" in view["properties"] and "ceiling" not in view["required"]
    assert S.validate("view.priority", {"bargains": [], "envelopes": [], "ceiling": None}) == []
    assert S.validate("view.priority", {"bargains": [], "envelopes": [], "ceiling": {"rounds": 6, "calls": 66, "usd": 3.0,
                                                                                    "start": {"rounds": 6, "calls": 66, "usd": 3.0}}}) == []
    assert S.validate("view.priority", {"bargains": [], "envelopes": [], "ceiling": {"rounds": 6}}) != []
    import engine_runtime as R
    assert R.INSTRUCTIONS["priority"]["bargain"]["round"] == part["inputs"], "the owner's screen names the same slots"
    assert all(n in R.INPUT_SAYS for n in part["inputs"])


def test_q2_priority_never_orders_in_the_words_it_sends_or_says(live, rounds_sendable):
    """A word of ordering in Priority's round part, its answers or its options must fail (S-05): Priority prices and holds."""
    W, R, J, _ = live
    forbidden = re.compile(r"order|what runs next", re.I)
    assert not forbidden.search(json.dumps(V1.WORDS["bargain"]["round"]) + V1.LAYOUT["bargain"]["round"])
    ref = _settled(live)
    for n in (2, 7):
        _propose_round(live, ref, n)
    said = json.dumps([p["payload"] for p in _round_answers(R, ref)])
    assert len(_round_answers(R, ref)) == 2 and not forbidden.search(said)


def test_q2_the_view_carries_the_ceiling_and_the_map_and_the_cycle_read_it(live, rounds_sendable):
    """A pane or a Map that still reads the ceiling from envelopes._goal must fail: the view holds dept.ceiling, the cycle's
    ceiling is the record's, and the budget bar is the goal's spend against it, not the day's."""
    import functions_view as F
    W, R, J, _ = live
    empty = _born(live, org="Empty Co", settle=False)
    assert _view(W, J, empty)["ceiling"] is None and F.functions(empty)["cycle"]["ceiling"] is None
    assert F.functions(empty)["budget"]["of"] == "today's limits"
    ref = _settled(live)
    _spend_runs(W, ref, 2, 0.1)
    c = W.dept(ref)["ceiling"]
    view = _view(W, J, ref)
    assert view["ceiling"] == c and S.validate_view("priority", view) == []
    got = F.functions(ref)
    assert got["cycle"]["ceiling"] == c
    bar = got["budget"]
    assert (bar["of"], bar["calls"], bar["usd"], bar["calls_limit"], bar["usd_limit"]) == ("the goal", 6, 0.3, c["calls"], round(c["usd"], 3))
    assert bar["share"] == round(max(6 / c["calls"], 0.3 / c["usd"]), 3)
    d = W.dept(ref)
    d["envelopes"]["_goal"] = {"calls": 1, "usd": 1.0}            # the old, unwritten place is not read
    W.save_dept(ref, d)
    assert F.functions(ref)["budget"]["calls_limit"] == c["calls"]
    del d["ceiling"]
    W.save_dept(ref, d)
    assert F.functions(ref)["budget"]["of"] == "today's limits" and F.functions(ref)["cycle"]["ceiling"] is None


# ---- Q3: scenario tests for the rare branches of the bargain (M5.5) ----------------------------------------------------------
# Seven branches, each on a website, a default department (one Do engine) and an organic line (shaped on the fly): Priority asks
# for less, Priority says no, the bargain reaches its limit by hops, by time and by spend, Identity drops the plan, Identity asks.
# The model is a function of the step id (test_j2's way); the clock is the system clock, ticked by R.sweep; the limit by time and by
# spend are reached with a model that is away, so that the bargain stays open while the clock runs.
KINDS3 = ("website", "default", "organic")
LAST3 = {"website": "Publish", "default": "Do", "organic": "Summary"}
KEEP3 = {"website": ["Plan", "Write", "Check"], "default": ["Do"], "organic": ["Facts", "Notes"]}
FIRST3 = {"website": "Plan", "default": "Do", "organic": "Facts"}
NO = {"answer": "reject", "why": "no room in the envelope today"}


def _work(W, ref):
    """The work engines that ran, in order (test_j2's reading)."""
    return [r["engine"] for r in W.runs(ref) if not r.get("system") and r.get("what") != "history"]


def _said(R, ref):
    """What Identity said to the owner on the board (test_j2's reading)."""
    return [str((p["payload"] or {}).get("done") or (p["payload"] or {}).get("objective") or "") for p in R.board(ref)
            if p["src"] == "Identity" and "Owner" in p["dst"]]


def _scenario(monkeypatch, R, kind, bargain=None, more=None, away=None, cost=0.0, bounds=None):
    """The model of a scenario, per step id: Adaptation's line for the organic kind, Priority's bargain, and whatever else is
    named. `away`: Priority's bargain waits for the model (it costs `cost`), so the bargain stays open."""
    answers = {"adapt.line": THREE} if kind == "organic" else {}
    if bargain is not None:
        answers["priority.bargain"] = bargain
    answers.update(more or {})
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)

    def model(prompt, step):
        if away and step["id"] == "priority.bargain":
            return None, cost, "away"
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"
    monkeypatch.setattr(R, "MODEL", model)
    if bounds:
        monkeypatch.setattr(R, "BOUNDS", dict({"hops": 4, "seconds": 900, "usd": 0.5}, **bounds))


def _scenario_dept(live, kind):
    """A department of the kind, made the way a person makes one, with two done-when items, and run until it waits."""
    W, R, J, _ = live
    if kind == "default":
        d, _ = W.create("dref-answers", "Answers", None, kind="default")
        d["events"] = [{"kind": "j2_ready", "route": "template"}]
        W.save_dept(d["ref"], d)
        J.start(d["ref"])
        W.give_goal(d["ref"], "Answer what the science team asks about the lab rota")
        ref = d["ref"]
    else:
        ref = _born(live, ORGANIC if kind == "organic" else WEBSITE, "Lab Co" if kind == "organic" else "Acme Learning", settle=False)
    W.put_done_items(ref, ITEMS2)
    W.run_until_idle(ref, limit=300)
    return ref


def _counter3(kind):
    def bargain(prompt):
        if "- %s:" % LAST3[kind] in prompt:
            return {"answer": "counter", "why": "room for some of it today", "keep": KEEP3[kind]}
        return {"answer": "accept", "why": "the envelope has room"}
    return bargain


def _line_thread(R, ref):
    return next(p["thread"] for p in R.board(ref) if p["src"] == "Adaptation" and p["msg_type"] == "propose" and (p["payload"] or {}).get("word") == "line")


def _one_conflict_ask(W, ref):
    asks = [a for a in W.asks(ref) if a["status"] == "pending"]
    assert [a["kind"] for a in asks] == ["conflict"], asks
    return asks[0]


def _one_way_out_card(W, ref):
    """A conflict that carries Priority's ways out reaches the owner as one blocked card that holds them (M5.4), never as the stamp
    that can only run or drop the plan."""
    asks = [a for a in W.asks(ref) if a["status"] == "pending"]
    assert [a["kind"] for a in asks] == ["blocked"], asks
    return asks[0]


def _no_ways_out(monkeypatch, R):
    """Priority's no as it was before it priced ways out: the answer carries none, so the conflict is the stamp that runs or drops
    the plan. Priority sends them now and Adaptation passes them on, so a row that tests the stamp takes them off."""
    real = R.post

    def post(ref, src, dst, msg_type, payload=None, *a, **kw):
        if src == "Priority" and isinstance(payload, dict) and "options" in payload:
            payload = {k: v for k, v in payload.items() if k != "options"}
        return real(ref, src, dst, msg_type, payload, *a, **kw)
    monkeypatch.setattr(R, "post", post)


@pytest.mark.parametrize("kind", KINDS3)
def test_q3_priority_asks_for_less_and_adaptation_takes_it(live, monkeypatch, kind):
    """A counter treated as a no, a cut engine that runs, or a line that cannot be cut and is cut all the same, must fail: on a
    website and an organic line the engines Priority kept are registered and run, the one it cut never does; a default
    department has one engine, so asking to keep all of it is a yes."""
    W, R, J, _ = live
    _scenario(monkeypatch, R, kind, _counter3(kind))
    ref = _scenario_dept(live, kind)
    acts = _actions(J, ref)
    assert "conflict.raised" not in acts and "workflow.registered" in acts
    prices = _prices(W, ref)
    if kind == "default":
        assert "proposal.countered" not in acts and [(p["answer"], p["keep"]) for p in prices] == [("accept", ["Do"])]
        assert W.dept(ref)["workflows"][-1]["engines"] == ["Do"]
    else:
        i = acts.index("proposal.countered")
        assert acts[i:i + 4] == ["proposal.countered", "proposal.created", "proposal.granted", "workflow.validated"]
        assert [(p["answer"], p["keep"]) for p in prices] == [("counter", KEEP3[kind]), ("accept", KEEP3[kind])]
        assert W.dept(ref)["workflows"][-1]["engines"] == KEEP3[kind]
        assert LAST3[kind] not in [r["engine"] for r in W.runs(ref)], "the engine Priority asked to leave out never ran"
        assert not [o for p in _priority_posts(R, ref, "propose") for o in p["payload"].get("options") or []], "an ask for less is no limit"
    assert _work(W, ref) == (KEEP3[kind] if kind != "default" else ["Do"])[:len(_work(W, ref))] and _work(W, ref)[0] == FIRST3[kind]
    assert all(S.validate("priority.price", p) == [] for p in prices)


@pytest.mark.parametrize("kind", KINDS3)
def test_q3_priority_says_no_and_the_conflict_reaches_identity_with_the_ways_forward(live, monkeypatch, kind):
    """A no that ends in silence, an ask put twice, or a no with no way forward, must fail: Identity is the one that asks, once,
    nothing runs, and Priority's post carries what the owner may do, priced by code."""
    W, R, J, _ = live
    _scenario(monkeypatch, R, kind, NO)
    ref = _scenario_dept(live, kind)
    assert _actions(J, ref)[-5:] == ["proposal.created", "proposal.refused", "conflict.raised", "identity.ruled", "ask.created"]
    ask = _one_way_out_card(W, ref)
    assert "Priority said no to the plan: no room in the envelope today" in ask["text"] and _work(W, ref) == []
    [no] = _priority_posts(R, ref, "reject-proposal")
    assert [o["id"] for o in no["payload"]["options"]] == ["leave:D2", "stop"], "the room was ample, so no raise would mend it"
    assert all(S.validate("option", o) == [] for o in no["payload"]["options"])
    assert not [o for o in no["payload"]["options"] if re.search(r"order|MODEL", o["label"] + o["cost"])]
    assert [o["id"] for o in ask["options"]] == ["leave:D2", "stop"], "the card holds the ways Priority priced, passed on by Adaptation"
    [row] = _prices(W, ref)
    assert (row["answer"], row["keep"], row["proposal"]) == ("reject", [], "line") and S.validate("priority.price", row) == []
    W.run_until_idle(ref, limit=100)
    assert len([a for a in W.asks(ref) if a["kind"] in ("blocked", "conflict")]) == 1


def _limit_scenario(live, monkeypatch, kind, bound):
    """A bargain that reaches its limit: by hops (one hop, so Priority's answer is the second), by time (a bargain open for five
    seconds, the model away, the clock ticked) and by spend (the model away having cost more than the thread may spend)."""
    W, R, J, _ = live
    if bound == "hops":
        _scenario(monkeypatch, R, kind, bounds={"hops": 1})
    else:
        _scenario(monkeypatch, R, kind, away=True, cost=0.6 if bound == "usd" else 0.0, bounds={"seconds": 5} if bound == "seconds" else {})
    ref = _scenario_dept(live, kind)
    if bound != "hops":
        for _ in range(3):
            R.sweep(ref)
        W.run_until_idle(ref, limit=100)
    return ref


@pytest.mark.parametrize("kind", KINDS3)
@pytest.mark.parametrize("bound,label", (("hops", "hops"), ("seconds", "time"), ("usd", "spend")))
def test_q3_a_bargain_that_reaches_its_limit_goes_to_identity_and_priority_has_the_ways_forward(live, monkeypatch, kind, bound, label):
    """A limit that stops the bargain in silence, a conflict raised twice, or a limit with no way forward, must fail (J2.2): the
    bargain stops where it is, Coordination raises the conflict, Identity asks once, nothing runs, and Priority gives the options
    for the line the bargain was about."""
    W, R, J, _ = live
    ref = _limit_scenario(live, monkeypatch, kind, bound)
    raised = [e for e in J.events(ref) if e["action"] == "conflict.raised"]
    assert len(raised) == 1 and raised[0]["actor"] == "Coordination" and raised[0]["payload"]["bound"] == bound
    _one_conflict_ask(W, ref)
    assert _work(W, ref) == [] and [e for e in J.events(ref) if e["action"] == "workflow.registered"] == []
    th = next(t for t in R.threads(ref) if t["id"] == _line_thread(R, ref))
    assert (th["state"], th["outcome"]["which"]) == ("canceled", bound)
    if bound == "hops":
        assert _priority_posts(R, ref, "reject-proposal") == [] and _prices(W, ref) == [], "Priority's answer was past the limit"
    else:
        [step] = [r for r in R.step_rows(ref) if r["step"] == "priority.bargain"]
        assert step["status"] == "waiting", "Priority was waiting for the model when the clock ran out"
    opts = layers.call(ref, "priority", "limit_options", ref, th["id"])
    assert [o["id"] for o in opts] == ["leave:D2", "stop"] and all(S.validate("option", o) == [] for o in opts)
    assert opts[0]["cost"].startswith("D2 is dropped from done-when") and opts[1]["cost"].startswith("the department stops")


@pytest.mark.parametrize("kind", KINDS3)
def test_q3_identity_drops_the_plan_and_nothing_runs(live, monkeypatch, kind):
    """A drop that leaves the cycle running, or leaves the owner with no way out, must fail: Identity rules from the rules, the
    cycle is blocked, nothing runs, and the blocked card is the owner's way out."""
    W, R, J, _ = live
    _scenario(monkeypatch, R, kind, NO, {"identity.close": {"ruling": "drop", "why": "the rules say so"}})
    ref = _scenario_dept(live, kind)
    ruled = next(e for e in J.events(ref) if e["action"] == "identity.ruled")
    assert ruled["state"] == "drop" and J.status(ref)["state"] == "blocked" and _work(W, ref) == []
    assert any("is dropped: the rules say so" in s for s in _said(R, ref))
    card = [a for a in W.asks(ref) if a["status"] == "pending"]
    assert [a["kind"] for a in card] == ["blocked"] and "stop" in [o["id"] for o in card[0]["options"]]
    assert "workflow.registered" not in _actions(J, ref)


@pytest.mark.parametrize("kind", KINDS3)
def test_q3_identity_asks_the_owner_and_the_owners_stamp_runs_the_plan(live, monkeypatch, kind):
    """An ask Identity puts twice, or a stamp that does not resume the same cycle, must fail: one ask, in the owner's words, and
    the stamp registers the plan and the first engine runs."""
    W, R, J, _ = live
    _no_ways_out(monkeypatch, R)
    _scenario(monkeypatch, R, kind, NO, {"identity.close": {"ruling": "ask", "why": "the goal and the rules do not settle it"}})
    ref = _scenario_dept(live, kind)
    ruled = next(e for e in J.events(ref) if e["action"] == "identity.ruled")
    assert ruled["state"] == "ask" and J.status(ref)["state"] == "waiting" and _work(W, ref) == []
    ask = _one_conflict_ask(W, ref)
    assert "Priority said no to the plan: no room in the envelope today" in ask["text"]
    W.run_until_idle(ref, limit=100)
    assert len([a for a in W.asks(ref) if a["kind"] == "conflict"]) == 1
    cycle = {e["cycle_id"] for e in J.events(ref)}
    _stamp(ref, W)
    assert "workflow.registered" in _actions(J, ref) and _work(W, ref)[:1] == [FIRST3[kind]]
    assert {e["cycle_id"] for e in J.events(ref)} == cycle, "one answer resumes the same cycle"


# ---- Q4: spend by round (M9.6, Priority's part) ---------------------------------------------------------------------------------
# view.priority.spend_by_round [{round, calls, usd}]: the spend of the runs the ledger links by run_ref, summed by the round whose
# Brief version each run descends from (a round files its correction as a Brief version: rounds.jsonl, brief_v).
def _two_rounds(live):
    """A department with two rounds on its record. Round 1: Plan, Write and Check on Brief v1, two calls and 0.10 USD each. The
    owner's correction is filed as Brief v2 (J3's way), and round 2 runs the line again: three calls and 0.25 USD each. Adaptation's
    row for the round (rounds.jsonl) names Brief v2."""
    W, R, J, _ = live
    ref = _settled(live)
    _spend_runs(W, ref, 2, 0.1)
    W.owner_ask(ref, "Add a page for the timetable of the algebra classes")
    W.run_until_idle(ref, limit=300)
    rows = W.runs(ref)
    for r in rows:
        if r.get("chain") == "brief.v2":
            r["spend"] = {"calls": 3, "usd": 0.25}
    W._write(W.ddir(ref) / "runs.json", rows)
    W.append_row(ref, "rounds.jsonl", {"schema_version": 1, "round": 2, "at": W.now(), "cycle_id": J._state(ref)["cycle_id"],
                                       "correction": "Add a page for the timetable of the algebra classes", "fixes": [], "covers": ["D2"],
                                       "status": "filed", "brief_v": 2})
    return ref


def test_q4_the_spend_of_each_round_is_the_sum_of_its_runs_in_runs_json(live):
    """A sum that is not runs.json's, a run counted in the wrong round, or a run counted twice, must fail: in a two-round fixture
    each round's calls and money are the runs.json rows of the Brief version it filed, added up here independently."""
    W, R, J, _ = live
    ref = _two_rounds(live)
    work = [r for r in W.runs(ref) if not r.get("system")]
    assert sorted({r["chain"] for r in work}) == ["brief.v1", "brief.v2"] and len(work) == 6
    want = []
    for rn, chain in ((1, "brief.v1"), (2, "brief.v2")):
        mine = [r for r in work if r["chain"] == chain]
        want.append({"round": rn, "calls": sum(r["spend"]["calls"] for r in mine), "usd": round(sum(r["spend"]["usd"] for r in mine), 4)})
    assert want == [{"round": 1, "calls": 6, "usd": 0.3}, {"round": 2, "calls": 9, "usd": 0.75}]
    assert V1.spend_by_round(ref) == want
    assert V1.spent_of(ref) == {"calls": 15, "usd": 1.05} and sum(x["calls"] for x in want) == V1.spent_of(ref)["calls"]
    view = _view(W, J, ref)
    assert view["spend_by_round"] == want and S.validate_view("priority", view) == []
    assert S.validate("view.priority", {"bargains": [], "envelopes": [], "spend_by_round": [{"round": 1, "calls": 6, "usd": 0.3}]}) == []
    assert S.validate("view.priority", {"bargains": [], "envelopes": [], "spend_by_round": [{"round": 0, "calls": 6}]}) != []


def test_q4_before_a_second_round_every_run_is_the_first_and_with_no_run_there_is_none(live):
    W, R, J, _ = live
    empty = _born(live, org="Empty Co", settle=False)
    assert V1.spend_by_round(empty) == [] and _view(W, J, empty)["spend_by_round"] == []
    ref = _settled(live)
    _spend_runs(W, ref, 2, 0.1)
    assert V1.spend_by_round(ref) == [{"round": 1, "calls": 6, "usd": 0.3}]


def test_q4_only_the_runs_the_ledger_links_count_and_a_round_that_has_begun_shows_before_it_has_run(live):
    """A run the ledger never saw, a function's own run, or a round that disappears until it spends, must fail."""
    W, R, J, _ = live
    ref = _two_rounds(live)
    before = V1.spend_by_round(ref)
    today = datetime.now().astimezone().isoformat(timespec="seconds")
    W._write(W.ddir(ref) / "runs.json", W.runs(ref) + [_run_row("Write", "ok", 40, 4.0, today, chain="brief.v2"),
                                                       _run_row("Priority", "ok", 40, 4.0, today, system=True, chain="brief.v2")])
    assert V1.spend_by_round(ref) == before, "a run with no event on the ledger is no run of this goal, and a function's run is no work"
    W.append_row(ref, "rounds.jsonl", {"schema_version": 1, "round": 3, "at": W.now(), "cycle_id": None, "correction": "Fix the timetable page",
                                       "fixes": [], "covers": ["D2"], "status": "granted"})
    assert V1.spend_by_round(ref) == before, "a round whose correction is not filed yet names no Brief version, and has not begun to spend"
    W.append_row(ref, "rounds.jsonl", {"schema_version": 1, "round": 3, "at": W.now(), "cycle_id": None, "correction": "Fix the timetable page",
                                       "fixes": [], "covers": ["D2"], "status": "filed", "brief_v": 3})
    assert V1.spend_by_round(ref) == before + [{"round": 3, "calls": 0, "usd": 0.0}]


def test_q4_a_run_that_names_no_brief_version_belongs_to_the_round_that_had_begun(live):
    """A run with no chain that is counted nowhere, or always in the first round, must fail: it is the round that had begun
    when the run started."""
    W, R, J, _ = live
    ref = _two_rounds(live)
    rows = W.runs(ref)
    late = next(r for r in rows if r.get("chain") == "brief.v2" and r["engine"] == "Check")
    early = next(r for r in rows if r.get("chain") == "brief.v1" and r["engine"] == "Plan")
    late["chain"], early["chain"] = None, None
    late["started"] = (datetime.now().astimezone() + timedelta(minutes=5)).isoformat(timespec="seconds")
    early["started"] = (datetime.now().astimezone() - timedelta(days=1)).isoformat(timespec="seconds")
    W._write(W.ddir(ref) / "runs.json", rows)
    assert V1.spend_by_round(ref) == [{"round": 1, "calls": 6, "usd": 0.3}, {"round": 2, "calls": 9, "usd": 0.75}]
