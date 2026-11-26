"""D451, T2 (spike, no production change): which of J2's calls see the host's "Context from the team lead" line?

A recorded fact, not a feature: `docs/ai/project-files-context/channel-spike.md` reads the answer out of this file. The framing of a run reaches J2 only as one `system` chat line, and J2 puts
the chat in the prompt of the five function agents but NOT in the prompt of a builder in a real run (`J2_SLIM` on, the default: `context()` gives a builder `builder_state`, which holds the brief and
the Requester's answers and no chat). So a project block that travels in the framing would never reach a builder. The characterisation below is what T5 builds on: the block goes through the
host's `system_addendum` path (the node-context file), which `call()` appends to the system prompt of EVERY agent call.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from test_engine_host import BREW_LAB, QUIET, Running, fresh_j2, j2, jsonl  # noqa: F401  (j2 is a fixture)

from sutra_app.engine import llm

LINE = "PROJECT-LINE-XYZ"
FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")


def calls_of(run_dir: Path) -> list[dict]:
    return jsonl(Path(run_dir) / "calls.jsonl")


def test_a_hosted_mock_run_shows_the_framing_in_the_prompts_of_the_function_agents(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET, framing=LINE)
    assert Running(run_dir, "--mock").wait() == 0
    rows = calls_of(run_dir)
    seen = {r["fn"] for r in rows if LINE in (r.get("prompt") or "")}
    assert set(FUNCTIONS) & seen, "no function agent saw the framing line"
    assert not any(LINE in (r.get("system") or "") for r in rows)                      # it is never in a system prompt: the chat is the only way it travels


def test_a_builders_context_in_a_real_run_holds_no_chat_so_the_framing_line_never_reaches_it(j2, tmp_path, monkeypatch):
    folder = tmp_path / "runs" / "j2-20261104-100001-7f3a"
    folder.mkdir(parents=True)
    run = j2.J2Run(run_dir=folder)
    run.post("system", f"Context from the team lead: {LINE}")
    for fn in FUNCTIONS:
        assert LINE in run.context(fn), fn                                              # a function agent reads the chat
    monkeypatch.setattr(llm, "MOCK", False)                                             # a real run: J2_SLIM is on unless it is 0
    assert LINE not in run.context("W-1") and "requester_brief" in run.context("W-1")
    monkeypatch.setenv("J2_SLIM", "0")                                                  # the old path, prompt for prompt: a builder reads the chat again
    assert LINE in run.context("W-1")


def test_a_long_chat_summarises_the_framing_line_away_even_for_a_function_agent(j2, tmp_path, monkeypatch):
    folder = tmp_path / "runs" / "j2-20261104-100002-7f3a"
    folder.mkdir(parents=True)
    run = j2.J2Run(run_dir=folder)
    run.post("system", f"Context from the team lead: {LINE}")
    monkeypatch.setattr(j2, "CHAT_FULL_CHARS", 200)
    for n in range(60):
        run.post("identity", f"message number {n} " + "padding " * 10)
    assert LINE not in run.chat_view()                                                  # messages 1..N are a model's summary; the first line is the first to go
