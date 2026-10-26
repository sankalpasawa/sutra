"""Priority behind its interface (PRD A1, W1-PRIORITY: M5.8 and M5.3): layers/priority/v1 registers every name its recipe
uses, prices a proposal from what the engines have observably spent, answers it with the price, writes one price row per
answer, shows them in its view, and says by='priority' where it writes the record.

One test per done-check of P1 to P5. The contract's cases are layers/contract.py's; the fixtures are test_j2's: a
department born the way a person makes one, a model that is a function of the step id, the same board.
"""
import importlib
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
    assert V1.CODE["priority_envelope"].legacy == ("engine_runtime", "priority_envelope")
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
    assert parts == [("goal", "does"), ("goal", "skills"), ("bargain", "line"), ("bargain", "engine"), ("bargain", "cost")]
    assert C.on_the_md_fallback(V1) == [] and C.case_5(V1, ctx) == []
    assert all(P._module(None, "priority", g, p) is V1 for g, p in parts), "the registry takes the WORDS path for every part"
    assert V1.WORDS["bargain"]["line"] == {} and set(V1.WORDS["bargain"]["engine"]) == {"task"}, "the line part has no field the owner may change"
    assert P.faults() == [], "and the definitions load holds the typed words to their interface"


def test_p2_each_part_compiled_from_its_words_is_the_md_part_byte_for_byte(ctx):
    """The migration changes no word: the words and the layout, with the sample inputs, are the bundle's part. (The estimate
    and remaining lines are the bundle's too since the snapshot commit before it.)"""
    for layer_group, ps in S.PROMPTS["priority"].items():
        for part in ps:
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
    assert [a["kind"] for a in W.asks(ref) if a["status"] == "pending"] == ["conflict"]
    assert not [r for r in W.runs(ref) if not r.get("system") and r.get("what") != "history"], "the disputed work does not run"
    [row] = _prices(W, ref)
    assert row["answer"] == "reject" and row["keep"] == [] and row["room"] == {"calls": 0, "usd": 0.0}
    assert row["why"] == "no room today: even Plan costs about 3 calls and 0.08 USD against the 0 calls and 0.00 USD left"
    asked = next(a for a in W.asks(ref) if a["kind"] == "conflict")
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


def test_p4_the_prices_are_the_newest_few_newest_first_and_a_row_with_no_answer_is_not_shown(live, ctx):
    W, R, J, _ = live
    ref = ctx["ref"]
    for i in range(14):
        W.append_row(ref, "prices.jsonl", _price_row(at="2026-10-26T10:%02d:00+05:30" % i, why="row %d" % i))
    with S.expect_refused() as met:
        W.append_row(ref, "prices.jsonl", {"at": "2026-10-26T11:00:00+05:30", "answer": "grant", "why": "a row that is no answer"})
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


def test_p4_the_view_does_not_come_back_through_the_part_that_reads_the_views(live, ctx, monkeypatch):
    """A view that builds its pane by calling functions_view._j2_part must fail once _j2_part hands the pane to layers.view
    (A1.17, K2's C9): the two would call each other without end. _j2_part is made to do exactly that here, with no guard
    of its own; the view builds its pane from the record and never asks for it."""
    import functions_view
    W, R, J, _ = live
    ref = ctx["ref"]
    W.append_row(ref, "prices.jsonl", _price_row())
    asked = []

    def hands_to_the_views(ref_, d_, fn, events, ak):
        asked.append(fn)
        return layers.view(ref_, layers.layer_of(fn), d_, events, ak)
    monkeypatch.setattr(functions_view, "_j2_part", hands_to_the_views)
    events = [{"action": "proposal.countered", "summary": "Priority countered the line", "occurred_at": "2026-10-26T10:00:00+05:30"}]
    pane = V1.view(ref, W.dept(ref), events, [])
    assert asked == [], "the view reads the record, not the part that reads the views"
    assert S.validate_view("priority", pane) == []
    assert [(b["said"], b["summary"]) for b in pane["bargains"]] == [("asked for less", "Priority asked for less on the line")]
    assert [p["said"] for p in pane["prices"]] == ["said yes"] and [e["engine"] for e in pane["envelopes"]][:4] == LINE
    # and through the registry, which is how the pane is served: the same pane, validated, with the part never asked
    served = layers.view(ref, "priority", W.dept(ref), events, [])
    assert served == pane and S.validate_view("priority", served) == [] and asked == []


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
    assert C.by_reference(V1) == {"by_reference": 5, "own": 6}, \
        "priority_envelope and priority_grant, and the three shared checks, still delegate; the rest are this module's"


def test_p6_the_module_holds_no_state_besides_its_dicts_of_names():
    """A1.18: no module-level mutable state besides CODE, PROMPT, DRAFT, CHECK, WORDS and LAYOUT."""
    own = {"CODE", "PROMPT", "DRAFT", "CHECK", "WORDS", "LAYOUT"}
    held = {k: type(v).__name__ for k, v in vars(V1).items() if isinstance(v, (dict, list, set)) and not k.startswith("__")}
    assert set(held) == own, held
