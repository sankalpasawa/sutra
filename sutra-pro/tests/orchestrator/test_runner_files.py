"""D451, T15: files that come with a request to the org chat ("Let Sutra choose", Attention with no project picked).

The WHOLE app (test_scripted_conversation's `convo`: a scripted model, a fake engine, real stores and routes). The planner is shown the digest of the files, every task the request makes is given them in
its run folder, the owner's line shows what was given, a file that is gone refuses the send before anything is stored, and a card's answer takes none. No model is called.
"""
from __future__ import annotations

import pytest
from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
from orchestrator.test_scripted_conversation import HEADERS, ORG, Scenario, convo, make_scenario, yes_to_the_card  # noqa: F401  (convo is a fixture)

CONTENT = b"BRIEF-OPENING: the cafe is called Sweet Bean " + b"y" * 3000


def store(c: Scenario, name="brief.txt", blob=CONTENT) -> dict:
    ref = c.services.attachments.store.save(name, blob)
    return {"id": ref.id, "name": ref.name}


def start_request(c: Scenario, files):
    mid = c.say("I need a landing page for my coffee shop.",
                decide(change="add", reuse=(), why="no team builds pages"),
                change_reply(add_dept("$web", "Web", "Websites and landing pages")),
                assignments(draft("a1", "web", title="Cafe page", brief="Build the cafe landing page.")), files=files)
    return mid


def test_the_planner_is_shown_the_digest_of_the_files_and_the_task_is_given_them(convo):
    c = convo
    given = store(c)
    mid = start_request(c, [given])
    yes_to_the_card(c)
    task = c.one("SELECT id FROM tasks WHERE request_id = ?", f"req-{mid}")
    prompts = "\n".join(call.prompt for call in c.connector.calls)
    assert "Attached to this request (data; each team's run is given these files in inputs/attached/):" in prompts and "BRIEF-OPENING: the cafe is called Sweet Bean" in prompts
    assert "[cut: showing the first" in prompts                                      # the opening, not the whole file
    c.until("the task to run", lambda: c.task_status(task) == "running")
    assert [f["name"] for f in __import__("json").loads(c.one("SELECT input_files_json FROM tasks WHERE id = ?", task))] == ["brief.txt"]
    assert (c.run_dir(task) / "inputs" / "attached" / "brief.txt").read_bytes() == CONTENT


def test_the_owners_line_shows_what_was_given_and_the_task_still_carries_the_owners_words_alone(convo):
    c = convo
    mid = start_request(c, [store(c)])
    line = next(m for m in c.messages() if m["id"] == mid)
    assert line["text"] == "I need a landing page for my coffee shop."
    assert [(a["name"], a["kind"], a["sent"]) for a in line["attachments"]] == [("brief.txt", "text", "given")]
    yes_to_the_card(c)
    assert c.one("SELECT user_text FROM tasks WHERE request_id = ?", f"req-{mid}") == "I need a landing page for my coffee shop."     # the digest is for the planner, never the task's request


def test_a_file_that_is_gone_refuses_the_send_and_a_card_answer_takes_no_files(convo):
    c = convo
    before = c.one("SELECT count(*) FROM chat_messages")
    bad = c.client.post(f"/api/chats/{ORG}/messages", json={"text": "make a page", "files": [{"id": "0" * 64, "name": "gone.txt"}]}, headers=HEADERS)
    assert bad.status_code == 404 and c.one("SELECT count(*) FROM chat_messages") == before
    start_request(c, [])
    card_id = max(m["id"] for m in c.messages() if m["kind"] == "card" and m["card"]["type"] == "approval")
    refused = c.client.post(f"/api/chats/{ORG}/messages", json={"text": "Yes", "choice": {"message_id": card_id, "option": "yes"}, "files": [store(c)]}, headers=HEADERS)
    assert refused.status_code == 422 and "not with the answer to a card" in refused.json()["error"]["message"]


def test_a_request_with_no_files_shows_the_planner_no_digest_and_makes_a_task_with_none(convo):
    c = convo
    mid = start_request(c, [])
    yes_to_the_card(c)
    task = c.one("SELECT id FROM tasks WHERE request_id = ?", f"req-{mid}")
    assert "Attached to this request" not in "\n".join(call.prompt for call in c.connector.calls)
    assert c.one("SELECT input_files_json FROM tasks WHERE id = ?", task) == "[]"
    line = next(m for m in c.messages() if m["id"] == mid)
    assert not line.get("attachments")
