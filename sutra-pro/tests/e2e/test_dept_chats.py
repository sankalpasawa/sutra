"""Each team the org chat creates has its own chat, over the REAL app (GAP3 dept-chats, docs/notes/GAP3-dept-chats.md).

Two teams are asked for in ONE message to the org chat. Test one runs the app with the stub connector (the chat agent's model scripted, the engine
a real process in J2's mock mode) and reads what the owner's page reads: the sessions, who holds which message, the pointers in the org chat, the
needs-you list and the event stream. Test two runs the REAL connector router over the fake `claude` and proves the provider sessions: one per chat,
a team's first turn starts a fresh one and carries nothing of the org chat, and its second turn resumes its own."""
import json

import pytest
from harness import ANSWER, ORG, FakeCliBin, LiveApp, add_dept, assignments, change_reply, decide, draft

ASK = "I need a flyer printed and my lease reviewed"                       # vague on purpose: each team's Identity asks the owner a question
ORG_MARK = "ZEBRA-ORG-MARK"
PRINT_MARK = "OTTER-PRINT-MARK"
LEGAL_MARK = "HERON-LEGAL-MARK"


def two_team_script() -> list[dict]:
    return [decide(change="add", reuse=(), why="no team prints or reviews"),
            change_reply(add_dept("$print", "Print", "Flyers and print jobs"), add_dept("$legal", "Legal", "Lease and contract reviews")),
            assignments(draft("a1", "print", title="Flyer", brief="Print the flyer."), draft("a2", "legal", title="Lease review", brief="Review the lease."))]


def stop(live: LiveApp) -> None:
    try:
        live.stop()
    finally:
        live.kill_engines()


def test_two_teams_from_one_org_message_each_get_their_own_chat_end_to_end(tmp_path):
    from sutra_app.orchestrator.testing.scripted import ScriptedConnector
    live = LiveApp(tmp_path, connector=ScriptedConnector()).start()
    try:
        mid = live.say(ASK, *two_team_script())
        print_sid, legal_sid = live.session_of("print"), live.session_of("legal")
        # (a) the sessions: one each, titled by the team, writable, listed by the API next to the org chat
        listed = {s["id"]: s for s in live.get("/api/chats")}
        assert {print_sid, legal_sid, ORG} <= set(listed) and len({print_sid, legal_sid, ORG}) == 3
        assert [(listed[s]["kind"], listed[s]["title"], listed[s]["writable"], listed[s]["node_id"]) for s in (print_sid, legal_sid)] == [
            ("department", "Print", True, "print"), ("department", "Legal", True, "legal")]
        # (c) the owner's words are the first user line of each team's chat, marked as passed on, and the task started there
        for sid, node in ((print_sid, "print"), (legal_sid, "legal")):
            first = [m for m in live.messages(sid) if m["role"] == "user"][0]
            assert (first["text"], first["passed_on"], first["task_id"]) == (ASK, mid, live.one("SELECT id FROM tasks WHERE dept_id = ?", node))
        assert "passed_on" not in [m for m in live.messages(ORG) if m["id"] == mid][0]
        # the org chat says "Started <team>" with a pointer to each team's own chat
        started = [c for c in live.cards("team_chat") if c["about"] == "started"]
        assert [(c["node_id"], c["name"], c["session_id"]) for c in started] == [("print", "Print", print_sid), ("legal", "Legal", legal_sid)]
        # (d) both Identities ask: the questions stay in their own team's chat, and the needs-you list says which chat each belongs to
        live.until("both questions", lambda: len(live.get("/api/needs-you")) == 2)
        needs = {n["dept_id"]: n for n in live.get("/api/needs-you")}
        assert (needs["print"]["session_id"], needs["print"]["dept_name"]) == (print_sid, "Print")
        assert (needs["legal"]["session_id"], needs["legal"]["dept_name"]) == (legal_sid, "Legal")
        for sid in (print_sid, legal_sid):
            assert [m["kind"] for m in live.messages(sid) if m["who"] == "identity"] == ["question"]
        org_json = json.dumps(live.messages(ORG))
        for n in needs.values():
            assert n["text"] not in org_json and "Before we start" not in org_json                  # none of the team's words reached the org chat
        pointers = {c["node_id"]: c for c in live.cards("team_chat") if c["about"] == "question"}
        assert {k: (v["session_id"], v["question_message_id"]) for k, v in pointers.items()} == {k: (v["session_id"], v["message_id"]) for k, v in needs.items()}
        assert live.cards("needs_you") == []
        # the owner answers in ONE team's chat: that run goes on, the other still waits, the org chat gets no line of it
        before_org = len(live.messages(ORG))
        task = live.one("SELECT id FROM tasks WHERE dept_id = 'print'")
        response = live.write(print_sid, ANSWER)
        assert response.status_code == 200 and response.json()["task_id"] == task and response.json()["delivered"] == "answer"
        live.settled(task)
        assert [n["dept_id"] for n in live.get("/api/needs-you")] == ["legal"]
        assert live.one("SELECT status FROM tasks WHERE dept_id = 'legal'") == "waiting_user"
        # nothing a team wrote or was asked is in the org chat: only Sutra's own lines and cards, the owner's, and a done card per finished task
        assert {m["who"] for m in live.messages(ORG)} == {"sutra", "user"}
        assert [m["card"]["type"] for m in live.messages(ORG)[before_org:]] == ["done"]
        assert not [m for m in live.messages(ORG) if m["kind"] in ("question", "note", "error")]
        # the event stream: every message event of the engine's lines went to the team's own session, never to cs_org
        team_say = [f["data"] for f in live.sse.of("chat.message") if f["data"]["message"]["who"] in ("identity", "adaptation", "priority", "coordination", "audit")
                    and f["data"]["message"]["kind"] != "card"]
        assert team_say and all(d["session_id"] not in (ORG,) for d in team_say)
        assert all(d["session_id"] == d["message"]["session_id"] for d in (f["data"] for f in live.sse.of("chat.message")))
        assert live.one("SELECT count(*) FROM chat_messages WHERE session_id = ? AND who IN ('identity', 'validator')", ORG) == 0
    finally:
        stop(live)


@pytest.fixture
def cli(tmp_path) -> FakeCliBin:
    return FakeCliBin(tmp_path)


def direct(live: LiveApp, sid: str, text: str) -> None:
    from sutra_app.orchestrator.api import chat_v2
    seen = len(live.get(f"/api/chats/{sid}/messages")["messages"])
    response = live.post(f"/api/chats/{sid}/direct", {"text": text})
    assert response.status_code == 202, response.text
    live.until("the reply to be stored", lambda: len(live.get(f"/api/chats/{sid}/messages")["messages"]) >= seen + 2)
    live.until("the turn to end", lambda: sid not in chat_v2._running)


def chat_calls(cli: FakeCliBin) -> list[dict]:
    """The `claude -p` calls of the direct chats (the chat agent's are the ones that carry a JSON schema)."""
    return [c for c in cli.calls("claude") if "--json-schema" not in c["argv"]]


def opt(call: dict, flag: str) -> str | None:
    argv = call["argv"]
    return argv[argv.index(flag) + 1] if flag in argv else None


def test_a_teams_first_turn_starts_its_own_provider_session_and_carries_nothing_of_the_org_chat(tmp_path, cli):
    cli.push("claude", *two_team_script())
    live = LiveApp(tmp_path, cli=cli, connector_name="auto", offline=False).start()
    try:
        mid = live.say(ASK)
        print_sid, legal_sid = live.session_of("print"), live.session_of("legal")
        agent_calls = [c for c in cli.calls("claude") if "--json-schema" in c["argv"]]
        assert len(agent_calls) == 3 and not chat_calls(cli)                                      # the planning is three one-shot calls: no chat session yet
        assert {(r["session_id"], r["node_id"]) for r in live.rows("SELECT session_id, node_id FROM usage_ledger WHERE purpose = 'chat_plan'")} == {(ORG, "root")}

        direct(live, ORG, f"how are my teams doing? {ORG_MARK}")
        direct(live, print_sid, f"what is the paper size? {PRINT_MARK}")
        direct(live, legal_sid, f"which clause worries you? {LEGAL_MARK}")
        org_call, print_call, legal_call = chat_calls(cli)
        # one provider session per chat: three different ones, all new (a `--session-id`), none resumed
        ids = [c["session_id"] for c in (org_call, print_call, legal_call)]
        assert all(ids) and len(set(ids)) == 3
        for call in (org_call, print_call, legal_call):
            assert opt(call, "--session-id") and opt(call, "--resume") is None, call["argv"]
        # each runs in the work folder of its OWN chat session
        assert [call["cwd"].rstrip("/").rsplit("/", 1)[-1] for call in (org_call, print_call, legal_call)] == [ORG, print_sid, legal_sid]
        # what the model was given: the org chat's turn carries the org chat; a team's first turn carries ITS OWN chat (the request passed on to it)
        # and nothing of the org chat or of the other team
        assert ORG_MARK in org_call["stdin"] and PRINT_MARK not in org_call["stdin"] and LEGAL_MARK not in org_call["stdin"]
        assert PRINT_MARK in print_call["stdin"] and ASK in print_call["stdin"]
        assert ORG_MARK not in print_call["stdin"] and LEGAL_MARK not in print_call["stdin"] and "I set up a Print team" not in print_call["stdin"]
        assert LEGAL_MARK in legal_call["stdin"] and ASK in legal_call["stdin"]
        assert ORG_MARK not in legal_call["stdin"] and PRINT_MARK not in legal_call["stdin"] and "I set up a Legal team" not in legal_call["stdin"]
        # the store agrees: each chat remembers its own provider session
        remembered = {r["id"]: r["provider_session_id"] for r in live.rows("SELECT id, provider_session_id FROM chat_sessions WHERE id IN (?, ?, ?)", ORG, print_sid, legal_sid)}
        assert set(remembered) == {ORG, print_sid, legal_sid} and len(set(remembered.values())) == 3 and None not in remembered.values()
        assert remembered[print_sid] == print_call["session_id"] and remembered[legal_sid] == legal_call["session_id"]

        # a team's SECOND turn resumes its own provider session, and still not the org chat's
        direct(live, print_sid, f"and the stock? {PRINT_MARK}-2")
        again = chat_calls(cli)[-1]
        assert opt(again, "--resume") == print_call["session_id"] != org_call["session_id"] and opt(again, "--session-id") is None
        assert ORG_MARK not in again["stdin"]
        # the org chat holds none of the teams' direct lines, and the teams hold none of the org chat's
        org_text = json.dumps(live.messages(ORG))
        assert PRINT_MARK not in org_text and LEGAL_MARK not in org_text
        assert ORG_MARK not in json.dumps(live.messages(print_sid)) + json.dumps(live.messages(legal_sid))
        assert mid in [m["passed_on"] for m in live.messages(print_sid) if "passed_on" in m]
    finally:
        stop(live)
