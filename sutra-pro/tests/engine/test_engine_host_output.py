"""The host and the output type after J2 sync 5 (D165, D166): a pinned type must exist in the data, a run with no type leaves `J2_OUTPUT` unset,
and a follow-up whose earlier type is gone is left to the planner."""
import json
import os

from test_engine_host import BREW_LAB, QUIET, Running, chat, events, j2, trace   # noqa: F401  (fixtures and helpers)


def test_an_unknown_pinned_type_is_a_refused_start_that_lists_the_known_ones(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BREW_LAB, settings={**QUIET, "J2_OUTPUT": "no_such_type"})
    assert Running(run_dir, "--mock").wait(60) == 3
    ended = events(run_dir)[-1]
    assert ended["t"] == "run.ended" and ended["status"] == "crashed" and ended["code"] == "start_failed"
    assert ended["outcome"].startswith("could not start: unknown output type no_such_type (known: ")
    assert "project" in ended["outcome"] and "website" in ended["outcome"], "the data's names, a registered type included"
    lines = [m["text"] for m in chat(run_dir) if m["who"] == "system"]
    assert any(t.startswith("Could not start: unknown output type no_such_type") for t in lines)
    assert not (run_dir / "site").exists()


def test_with_no_type_chosen_the_host_leaves_j2_output_unset_and_says_so_in_the_records(j2, make_run_dir):
    run_dir = make_run_dir(user_text="a website for my cafe", settings=QUIET)
    running = Running(run_dir, "--mock")
    from test_engine_host import Answerer, VAGUE
    answerer = Answerer(run_dir, VAGUE[1:])
    assert running.wait(60) == 0
    answerer.stop()
    record = json.loads((run_dir / "output.json").read_text())
    assert (record["output"], record["rule"], record["choice"]) == (None, "planner", "auto")
    assert json.loads((run_dir / "settings.json").read_text())["output"] == "auto"
    assert os.environ.get("J2_OUTPUT") != "auto", "never the word auto: J2 reads the variable as a type name"
    assert trace(run_dir, "output.selected")[0]["data"]["output"] is None
