"""Prompt goldens (work package E5, engine design 9, ENG-01): in mock mode the engine asks the model for exactly the text J2 asks for.

`scripts/record_engine_golden.py` ran seven scenarios against J2, the folder `prototypes/j2` of this repository at the pinned commit
(`BASELINE` of the recorder; see `golden/prompts_*.json`): per scenario the outcome, the spend, the hash of the last page, of the
sections and of the workflows and, per model call in order, `[function, sha(system), sha(prompt)]`. The seventh, `agent_answer`, is the
`realization` run followed by one question to Adaptation through `j2_agent.answer` (a stub in place of the model): the one prompt J2's
agent view adds, recorded as the last call. Here the same scenarios run against the vendored engine, each in its own child process
(J2 reads its environment when it is imported), and the results must be equal. The runs take about two seconds each and run side by
side, so this file is part of every merge gate (it is not marked slow); the legacy J2 scripts are the slow part (test_engine_legacy.py).

The tests of the machinery make sure the comparison can fail: a changed role file, a changed digest, a changed length and a changed
outcome each show up as a difference.
"""
import importlib.util
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
GOLDEN = HERE / "golden"
NAMES = ("brewlab_fixes0", "brewlab_fixes1", "realization", "prd", "design_docs", "template_library", "agent_answer")


def _load_recorder():
    spec = importlib.util.spec_from_file_location("record_engine_golden", REPO / "scripts" / "record_engine_golden.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["record_engine_golden"] = mod
    spec.loader.exec_module(mod)
    return mod


rec = _load_recorder()


def golden(name: str) -> dict:
    return json.loads((GOLDEN / f"prompts_{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def engine_results() -> dict:
    """The vendored engine's run of every scenario (seven child processes at once)."""
    with ThreadPoolExecutor(len(NAMES)) as pool:
        return dict(zip(NAMES, pool.map(rec.engine_result, NAMES)))


# ---- the goldens themselves -----------------------------------------------------------------------------------------------
def test_there_are_seven_goldens_and_they_are_the_scenarios():
    files = sorted(p.name for p in GOLDEN.glob("prompts_*.json"))
    assert files == sorted(f"prompts_{n}.json" for n in NAMES)
    assert sorted(rec.SCENARIOS) == sorted(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_golden_file_shape(name):
    g = golden(name)
    assert g["schema"] == rec.SCHEMA and g["scenario"] == name
    assert g["j2_commit"] == rec.BASELINE                                # one extraction, one pin for all seven (docs/design/j2-sync-4.md)
    assert g["outcome"].startswith("Done") and g["spent"] > 0
    assert len(g["calls"]) >= 10 and all(len(c) == 3 and all(isinstance(x, str) and x for x in c) for c in g["calls"])
    assert all(len(c[1]) == 12 and len(c[2]) == 12 for c in g["calls"])
    assert g["env"]["STUDIO_MOCK"] == "1" and g["env"] == {**rec.COMMON_ENV, **rec.SCENARIOS[name]["env"]}
    assert (GOLDEN / f"prompts_{name}.json").read_text(encoding="utf-8") == rec.dump(g)      # the file is in the recorder's format


def test_scenarios_differ_where_their_flags_differ():
    calls = {n: golden(n)["calls"] for n in NAMES}
    assert calls["brewlab_fixes0"] != calls["brewlab_fixes1"] and calls["brewlab_fixes0"] != calls["realization"]
    assert sum(c[0] == "priority" for c in calls["brewlab_fixes1"]) == sum(c[0] == "priority" for c in calls["brewlab_fixes0"]) + 1
    assert len(calls["design_docs"]) > 60 > len(calls["prd"])                             # three documents and a site, against one document
    assert golden("prd")["env"]["J2_OUTPUT"] == "prd" and golden("realization")["env"]["J2_REALIZATION"] == "1"
    assert golden("template_library")["env"]["J2_TEMPLATE_LIBRARY"] == "1" and golden("design_docs")["budget"] == 900


# ---- the seventh scenario: a question to a function (j2_agent.answer, the one prompt the agent view adds) -------------------
def test_the_answer_scenario_is_the_realization_run_and_one_question_to_adaptation():
    ans, real = golden("agent_answer"), golden("realization")
    assert rec.SCENARIOS["agent_answer"]["ask"] == {"who": "adaptation", "q": "Why was W-3 scored below the gate?"}
    assert [n for n in NAMES if "ask" in rec.SCENARIOS[n]] == ["agent_answer"]
    keys = ("env", "brief_sha", "budget", "outcome", "spent", "site", "sections", "workflows")
    assert {k: ans[k] for k in keys} == {k: real[k] for k in keys}
    assert ans["calls"][:-1] == real["calls"], "fixing J2's time-of-day stamp changes no prompt of the run itself"
    assert len(ans["calls"]) == len(real["calls"]) + 1 and ans["calls"][-1][0] == "adaptation"
    assert ans["calls"][-1] not in real["calls"], "the answer is a prompt of its own, not one the run already asked"


def test_a_changed_answer_prompt_is_seen():
    g = golden("agent_answer")
    n = len(g["calls"])
    for column, what in ((1, "system"), (2, "prompt")):
        other = json.loads(json.dumps(g))
        other["calls"][-1][column] = "000000000000"
        assert rec.differences(g, other) == [f"call {n} (adaptation): {what} differ"]


def test_feed_digest_ignores_the_wall_clock_seconds_and_nothing_else():
    feed = ("[12:00:00] AI call 7 · step 2 · cycle 1 · 0.0 s — Scripted mock reply\n"
            "[12:00:00] Plan confidence 0.95 · 8 workflows — 5 AI calls · 0 s")
    slower = feed.replace("· 0.0 s", "· 0.1 s").replace("· 0 s", "· 2 s")
    assert rec.feed_digest(feed) == rec.feed_digest(slower) != rec.digest(feed)
    assert rec.feed_digest(feed) != rec.feed_digest(feed.replace("AI call 7", "AI call 8")), "a changed record is seen"
    assert rec.feed_digest(feed) != rec.feed_digest(feed.replace("[12:00:00]", "[12:00:01]")), "so is a stamp (the child fixes it instead)"
    assert rec.feed_digest("3 stages, 2 steps, 8 s") == rec.feed_digest("3 stages, 2 steps, 9 s")
    assert rec.feed_digest("3 stages, 2 steps") == rec.digest("3 stages, 2 steps"), "only `N s` is touched, not `N stages`"


def test_freeze_time_of_day_fixes_that_one_format_only(monkeypatch):
    monkeypatch.setattr(time, "strftime", time.strftime)          # the real one is put back when the test ends
    rec.freeze_time_of_day()
    assert time.strftime("%H:%M:%S") == "12:00:00"
    assert rec.TIME_RE.fullmatch(time.strftime("%Y-%m-%dT%H:%M:%S")) and len(time.strftime("%Y%m%d-%H%M%S")) == 15
    assert time.strftime("%Y", time.gmtime(0)) == "1970"


def test_the_source_must_be_an_extraction_of_prototypes_j2(tmp_path):
    with pytest.raises(SystemExit, match="holds no j2.py"):
        rec.checkout_of(tmp_path, "abc")
    (tmp_path / "j2.py").write_text("", encoding="utf-8")
    assert rec.checkout_of(tmp_path, "abc") == (tmp_path.resolve(), None, "abc")


# ---- the engine against the goldens ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", NAMES)
def test_engine_asks_the_model_what_j2_asked(name, engine_results):
    assert rec.differences(golden(name), engine_results[name]) == []


def test_engine_run_is_the_same_on_a_rerun():
    assert rec.engine_result("brewlab_fixes0") == rec.engine_result("brewlab_fixes0")


def test_a_changed_role_file_is_seen(tmp_path):
    """The comparison is not vacuous: one extra word in identity.md changes Identity's system prompt and nothing else."""
    agents = tmp_path / "agents"
    shutil.copytree(REPO / "sutra_app" / "engine" / "agents" / "j2", agents)
    role = agents / "identity.md"
    role.write_text(role.read_text(encoding="utf-8") + "\nExtra sentence.\n", encoding="utf-8")
    got = rec.run_child("engine", REPO, "brewlab_fixes0", extra_env={"J2_AGENTS_DIR": str(agents)})
    diff = rec.differences(golden("brewlab_fixes0"), got)
    assert len(diff) == 1 and diff[0].startswith("call 1 (identity): system differ"), diff


# ---- the comparison and the recorder's helpers ------------------------------------------------------------------------------
def test_differences_name_the_first_changed_call_and_what_changed():
    g = golden("prd")
    same = json.loads(json.dumps(g))
    assert rec.differences(g, same) == []
    prompt = json.loads(json.dumps(g))
    prompt["calls"][3][2] = "000000000000"
    system = json.loads(json.dumps(g))
    system["calls"][5][1] = "000000000000"
    fn = json.loads(json.dumps(g))
    fn["calls"][1][0] = "other"
    assert rec.differences(g, prompt) == [f"call 4 ({g['calls'][3][0]}): prompt differ"]
    assert rec.differences(g, system) == [f"call 6 ({g['calls'][5][0]}): system differ"]
    assert rec.differences(g, fn) == [f"call 2 ({g['calls'][1][0]}): function differ"]


def test_differences_see_length_outcome_spend_and_hashes():
    g = golden("prd")
    short = {**g, "calls": g["calls"][:-1]}
    assert rec.differences(g, short) == [f"calls: golden {len(g['calls'])}, got {len(g['calls']) - 1}"]
    got = {**g, "outcome": "Paused: x", "spent": g["spent"] + 1, "site": "x", "sections": "y", "workflows": "z", "scenario": "q"}
    assert [d.split(":")[0] for d in rec.differences(g, got)] == ["scenario", "outcome", "spent", "site", "sections", "workflows"]
    assert rec.differences({**g, "j2_commit": "a"}, {**g, "j2_commit": "b"}) == []       # the commit is provenance, not behaviour


def test_digest_ignores_timestamps_only():
    assert rec.digest("at 2026-11-04T10:00:01 ok") == rec.digest("at 2025-01-01T00:00:00 ok")
    assert rec.digest("at 2026-11-04 ok") != rec.digest("at 2026-11-05 ok")
    assert rec.digest("a") != rec.digest("b") and len(rec.digest("a")) == 12


def test_dump_is_one_call_per_line_and_round_trips():
    g = golden("brewlab_fixes0")
    text = rec.dump(g)
    assert json.loads(text) == g and text.endswith("}\n")
    assert sum(1 for line in text.splitlines() if line.startswith('  ["')) == len(g["calls"])


def test_recorder_writes_checks_and_refuses_without_a_source(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    assert rec.main(["--engine", "--scenario", "prd", "--out-dir", str(out)]) == 0
    written = json.loads((out / "prompts_prd.json").read_text(encoding="utf-8"))
    assert rec.differences(golden("prd"), written) == []
    assert rec.main(["--engine", "--scenario", "prd", "--out-dir", str(out), "--check"]) == 0
    (out / "prompts_prd.json").write_text(rec.dump({**written, "spent": 1}), encoding="utf-8")
    assert rec.main(["--engine", "--scenario", "prd", "--out-dir", str(out), "--check"]) == 1
    assert "DIFFERENT" in capsys.readouterr().out
    monkeypatch.delenv("SUTRA_J2_CHECKOUT", raising=False)
    with pytest.raises(SystemExit) as stop:
        rec.main(["--scenario", "prd"])
    assert stop.value.code == 2


@pytest.mark.slow
@pytest.mark.skipif(not os.environ.get("SUTRA_J2_CHECKOUT"), reason="needs SUTRA_J2_CHECKOUT (an extraction of prototypes/j2 at the pinned commit)")
@pytest.mark.parametrize("name", ("brewlab_fixes0", "prd", "agent_answer"))
def test_goldens_are_what_j2_does_at_the_baseline(name):
    """Re-record three scenarios from J2 itself: the stored goldens are not stale."""
    got = rec.record(os.environ["SUTRA_J2_CHECKOUT"], rec.BASELINE, [name])[name]
    assert got["j2_commit"] == golden(name)["j2_commit"] and rec.differences(golden(name), got) == []
