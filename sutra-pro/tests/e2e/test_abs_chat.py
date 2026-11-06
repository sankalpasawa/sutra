"""End to end for the absorbed chat (work package ABS-13): a team chat answered through ChatPort over the fake `claude` and `codex` (real processes), the
per-chat provider choice, the carry-over with a scrubbed credential, a second chat that stays on Claude, archive and search, the import of old chats and a
team's run that follows its chat's choice. The engine plays J2's mock; nothing here reaches a real model."""
from __future__ import annotations

import json

import pytest
from harness import FakeCliBin, LiveApp

from sutra_app.ops import import_old
from sutra_app.orchestrator.redact import Redactor

SECRET = "sk-abcdefgh12345678"


@pytest.fixture
def cli(tmp_path) -> FakeCliBin:
    return FakeCliBin(tmp_path)


def session_of(live: LiveApp, dept: str) -> str:
    return live.one("SELECT chat_session_id FROM graph_nodes WHERE id = ?", dept)


def direct(live: LiveApp, sid: str, text: str, expect_messages: int) -> list[dict]:
    response = live.post(f"/api/chats/{sid}/direct", {"text": text})
    assert response.status_code == 202, response.text
    live.until("the reply to be stored", lambda: len(live.get(f"/api/chats/{sid}/messages")["messages"]) >= expect_messages)
    live.until("the turn to end", lambda: not _running(sid))
    return live.get(f"/api/chats/{sid}/messages")["messages"]


def _running(sid: str) -> bool:
    from sutra_app.orchestrator.api import chat_v2
    return sid in chat_v2._running


def test_the_chat_improvements_end_to_end(tmp_path, cli):
    live = LiveApp(tmp_path, cli=cli, connector_name="auto", offline=False).start()
    try:
        live.add_department("web", "Web", "Websites")
        live.add_department("menu", "Menu", "Menus")
        web, menu = session_of(live, "web"), session_of(live, "menu")

        # both providers can run, and nothing is chosen yet
        pill = live.get(f"/api/chats/{web}/providers")
        assert [(p["name"], p["ready"]) for p in pill["providers"]] == [("claude", True), ("codex", True)] and pill["chosen"] is None

        # a first turn on Claude (the policy default) with a credential in the owner's words
        messages = direct(live, web, f"my key is {SECRET}, remember it", 2)
        assert [m["role"] for m in messages] == ["user", "agent"] and len(cli.calls("claude")) == 1 and not cli.calls("codex")

        # choose Codex for THIS chat only; the next turn goes there with the carry-over, and the credential shape is scrubbed in it
        assert live.http.put(f"/api/chats/{web}/choice", json={"provider": "codex"}).json()["provider"] == "codex"
        messages = direct(live, web, "and what is my plan?", 4)
        codex = cli.calls("codex")
        assert len(codex) == 1
        prompt = codex[0]["stdin"]
        assert "Earlier messages of this conversation, carried over because the provider changed" in prompt
        assert SECRET not in prompt and "[redacted:openai-key]" in prompt and "and what is my plan?" in prompt
        egress = [json.loads(x) for x in (live.settings.data_dir / "connectors" / "egress.jsonl").read_text().splitlines()]
        assert any(r["session"] == web and r["mode"] == "replace" for r in egress)
        # the credential was scrubbed before the line was stored (so it is never in the chat store or a carry-over)
        assert SECRET not in json.dumps(live.get(f"/api/chats/{web}/messages")) and "[redacted:openai-key]" in messages[0]["text"]
        assert SECRET not in json.dumps(egress)

        # a second chat is still on Claude; the global default was never touched
        direct(live, menu, "hello menu", 2)
        assert len(cli.calls("claude")) == 2 and len(cli.calls("codex")) == 1
        assert live.get(f"/api/chats/{menu}/providers")["chosen"] is None

        # a team's J2 run started after the choice carries it
        task = live.give_task("web", "Build the cafe page")
        spec = json.loads((live.run_dir(task) / "task.json").read_text())
        assert spec["connector"] == "codex"
        task2 = live.give_task("menu", "Build the menu page")
        assert json.loads((live.run_dir(task2) / "task.json").read_text())["connector"] == "auto"

        # search finds the chat, archive hides it until asked, and it is found again with archived included
        assert [r["session_id"] for r in live.get("/api/chats/search", q="plan", scope="node:web")["results"]] == [web]
        assert live.post(f"/api/chats/{web}/archive").json() == {"session_id": web, "archived": True}
        assert live.get("/api/chats/search", q="plan", scope="node:web")["results"] == []
        found = live.get("/api/chats/search", q="plan", scope="node:web", include="archived")["results"]
        assert [(r["session_id"], r["archived"]) for r in found] == [(web, True)]
        assert live.get(f"/api/chats/{web}")["status"] == "archived"

        # old chats arrive archived and read only, are found by search and are not written to
        old = tmp_path / "old-chats"
        old.mkdir()
        (old / ("e" * 32 + ".json")).write_text(json.dumps({
            "sutra_id": "e" * 32, "title": "Old cafe notes", "cwd": "/w/cafe", "created": "2026-09-01T00:00:00Z", "updated": "2026-09-01T00:00:00Z",
            "provider_history": [{"provider": "claude", "native_id": "n", "from_turn": 0}],
            "messages": [{"role": "user", "ts": "2026-09-01T00:00:00Z", "blocks": [{"type": "text", "text": "zebra pricing question"}]}]}))
        chats, bad = import_old.read_chats(old)
        done = import_old.import_chats(live.services.db, chats, Redactor(None, environ={}))
        assert done["chats_added"] == 1 and done["messages_added"] == 1 and not bad
        older = live.get("/api/chats/search", q="zebra", include="archived")["results"]
        assert [(r["session_id"], r["archived"]) for r in older] == [("cs_old_" + "e" * 12, True)]
        assert live.get("/api/chats/search", q="zebra")["results"] == []
        refused = live.post(f"/api/chats/cs_old_{'e' * 12}/direct", {"text": "hi"})
        assert refused.status_code == 403
        assert live.post(f"/api/chats/cs_old_{'e' * 12}/unarchive").status_code == 422
    finally:
        try:
            live.stop()
        finally:
            live.kill_engines()
