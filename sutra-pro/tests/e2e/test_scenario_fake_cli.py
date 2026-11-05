"""Scenario 2 (GAP-E2E, G05): the same first message, but the chat agent talks to the REAL connector router over the fake `claude`
and `codex` of tests/fakes (draw.io step 3: `claude cli + python models`).

What runs for real: `AsyncConnector` -> `Router` (policy, health book, usage sink, event hook) -> `ClaudeConnector` / `CodexConnector`
-> a child process (the queue-fed wrapper of `FakeCliBin`, which runs tests/fakes/fake_cli.py) -> the python models that read the
reply. The engine of the run still plays J2's mock (`SUTRA_MOCK=1`), so nothing here can reach a real model.
"""
import json

import pytest
from harness import FIRST_MESSAGE, ORG, FakeCliBin, LiveApp, decide, new_team_script, run_new_team

from sutra_app.connectors.orchestrator_port import AsyncConnector
from sutra_app.connectors.router import Router
from sutra_app.library.types import overhead_atom_id
from sutra_app.orchestrator.agent import planner


@pytest.fixture
def cli(tmp_path) -> FakeCliBin:
    return FakeCliBin(tmp_path)


def connector_frames(live: LiveApp, prefix: str = "connector.") -> list[dict]:
    """The `connector.*` events the stream holds (replayed from the ring, so the ones from before the page connected are in too)."""
    text = live.http.get("/api/events", params={"after": 0, "once": 1}).text
    found = []
    for block in text.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if fields.get("event", "").startswith(prefix):
            found.append({"type": fields["event"], "data": json.loads(fields["data"])})
    return found


def test_step3_claude_cli_and_python_models_plan_the_new_team_through_the_router(tmp_path, cli):
    cli.push("claude", *new_team_script())
    live = LiveApp(tmp_path, cli=cli, connector_name="auto", offline=False).start()
    try:
        assert isinstance(live.services.connector, AsyncConnector) and isinstance(live.services.connector_router, Router)
        health = live.get("/api/health")["connectors"]
        assert health["claude"]["signed_in"] and health["codex"]["signed_in"] and health["claude"]["method"] == "claude.ai"
        journey = run_new_team(live, script=[])
        # --- the three stages reached the fake `claude -p` as real process calls
        calls = cli.calls("claude")
        assert len(calls) == 3 and not cli.calls("codex") and all(c["op"] == "print" for c in calls)
        for call, stage in zip(calls, ("decide", "change", "assign"), strict=True):
            assert call["argv"][0] == "-p" and "stream-json" in call["argv"] and "--json-schema" in call["argv"], stage
            assert call["argv"][call["argv"].index("--model") + 1] == "sonnet"
            assert "OWNER REQUEST:\n" + FIRST_MESSAGE in call["stdin"]                         # the prompt travelled on stdin
        assert journey.digest0 in calls[0]["stdin"]                                          # step 1: the chart digest
        schema_arg = calls[0]["argv"][calls[0]["argv"].index("--json-schema") + 1]
        assert json.loads(schema_arg)["properties"]["intent"] and "SCHEMA:" in calls[0]["stdin"]       # step 2: the models library schema
        # --- the python models read the replies: the chart changed and the team got its task
        assert [r["status"] for r in live.rows("SELECT status FROM chart_changes ORDER BY seq")] == ["applied", "applied"]
        assert live.one("SELECT name FROM org_nodes WHERE id = 'web'") == "Web"
        # --- the router's usage sink wrote one row per call, all on the request's overhead key
        rows = live.rows("SELECT * FROM usage_ledger WHERE purpose = 'chat_plan' ORDER BY id")
        assert len(rows) == 3
        assert {(r["provider"], r["model"], r["fn"], r["session_id"], r["node_id"], r["task_id"], r["ok"]) for r in rows} == \
            {("claude", "claude-sonnet-5-5", "chat_agent", ORG, "root", None, 1)}
        assert {r["atom_id"] for r in rows} == {overhead_atom_id(f"req-{journey.message_id}")}
        assert [(r["usd"], r["tokens_in"], r["tokens_out"]) for r in rows] == [(0.01, 120, 30)] * 3
        # --- the router's own events, and the chat session that remembers the provider
        modes = connector_frames(live, "connector.mode")
        assert modes and modes[0]["data"]["mode"] == "live"
        session = live.get("/api/chats/" + ORG)
        assert (session["connector"], session["model"]) == ("claude", "claude-sonnet-5-5")
        assert live.get("/api/connectors/status")["providers"][0]["today"]["calls"] == 3
        # --- the engine did not call any model: it played J2's mock, and the run is Done
        assert live.events_of(journey.task)[0]["mock"] is True and live.task_status(journey.task) == "done"
        assert len(cli.calls("claude")) == 3
        assert live.rows("SELECT count(*) FROM usage_ledger WHERE provider != 'stub' AND task_id IS NOT NULL")[0][0] == 0
    finally:
        try:
            live.stop()
        finally:
            live.kill_engines()


def test_step3_when_claude_reports_quota_the_turn_falls_back_to_codex(tmp_path, cli):
    cli.sequence["claude"] = "quota"                                                         # every claude call: usage limit reached
    cli.push("codex", decide("smalltalk", "none", reuse=()))
    live = LiveApp(tmp_path, cli=cli, connector_name="auto", offline=False).start()
    try:
        mid = live.say("Thanks a lot")
        assert [(c["cli"], c["op"], c["scenario"]) for c in cli.calls()] == [("claude", "print", "quota"), ("codex", "exec", "ok")]
        # the owner sees a normal answer, the ledger says who gave it, the stream says what happened to claude
        assert [(m["who"], m["state"]) for m in live.messages()][-2:] == [("user", "ok"), ("sutra", "ok")]
        assert live.messages()[-1]["text"] == planner.LINES["smalltalk"]
        rows = live.rows("SELECT provider, model, ok, purpose, atom_id FROM usage_ledger")
        assert [(r["provider"], r["ok"], r["purpose"], r["atom_id"]) for r in rows] == [("codex", 1, "chat_plan", overhead_atom_id(f"req-{mid}"))]
        health = [f["data"] for f in live.sse.of("connector.health")]
        assert [(h["provider"], h["state"], h["reason"]) for h in health] == [("claude", "quota", "usage limit reached")]
        status = {p["name"]: p for p in live.get("/api/connectors/status")["providers"]}
        assert status["claude"]["health"]["state"] == "quota" and status["codex"]["health"]["state"] == "ok"
        assert live.get("/api/chats/" + ORG)["connector"] == "codex"
        assert live.one("SELECT count(*) FROM chart_changes") == 1 and live.one("SELECT count(*) FROM tasks") == 0
        # the next turn does not try claude again while it is cooling down
        cli.push("codex", decide("smalltalk", "none", reuse=()))
        live.say("Thanks again")
        assert [c["cli"] for c in cli.calls()] == ["claude", "codex", "codex"]
    finally:
        try:
            live.stop()
        finally:
            live.kill_engines()
