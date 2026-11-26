"""D451, T13 and T14: a project's instructions and its earlier-context memory (`orchestrator/project_memory.py`).

FR-13/14 one free-text field with a revision check, FR-15 a run that ends and a chat that is archived each leave one entry (no model is called), FR-17 read, edit, add, delete, disable,
FR-18 an existing project is seeded once from its stored history, FR-19 an entry holds the owner's request and the outcome sentence only, scrubbed. Real database and real store (`tenv`).
"""
from __future__ import annotations

import pytest
from orchestrator.test_chat_store import msg
from orchestrator.test_tasks import tenv  # noqa: F401  (a fixture)

from sutra_app.orchestrator.chat_v2 import ChatArchive
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.project_memory import MAX_ENTRIES, ENTRY_CHARS, ProjectMemory
from sutra_app.orchestrator.redact import Redactor

SECRET = "sk-aaaaaaaa11111111"


def memory_of(t) -> ProjectMemory:
    return ProjectMemory(t.db, Redactor(None, environ={}), clock=t.clock)


def ended(t, text: str, status: str = "done", outcome: str = "Made the page", dept: str = "web") -> str:
    task = t.new(dept, text)
    t.sql("UPDATE tasks SET status = 'running' WHERE id = ?", task.id)
    t.projector.mark_ended(task.id, status, outcome)
    return task.id


def session_of(t, dept: str = "web") -> str:
    return t.one("SELECT chat_session_id FROM graph_nodes WHERE id = ?", dept)


def say(t, sid: str, text: str, who: str = "user") -> None:
    with t.db.tx() as tx:
        t.chats.post(tx, sid, msg(sid, text, who=who))


def archive(t, sid: str) -> None:
    with t.db.tx() as tx:
        ChatArchive(t.db, t.graph).archive(tx, sid)


def texts(pm: ProjectMemory, dept: str = "web") -> list[str]:
    return [e.text for e in pm.memory(dept).entries]


# ---- instructions (FR-13, FR-14) --------------------------------------------------------------------------------------------------------

def test_a_project_has_no_instructions_until_the_owner_writes_some(tenv):
    pm = memory_of(tenv)
    got = pm.instructions("web")
    assert got.text == "" and got.rev and got.max_chars == 4000


def test_instructions_are_stored_per_project_and_read_back(tenv):
    pm = memory_of(tenv)
    first = pm.instructions("web")
    saved = pm.put_instructions("web", "  Always answer in plain words.\nNever promise a date.  ", first.rev)
    assert saved.text == "Always answer in plain words.\nNever promise a date." and saved.rev != first.rev
    assert pm.instructions("web") == saved and pm.instructions("sales").text == ""
    assert tenv.one("SELECT count(*) FROM meta WHERE key = 'pinstr:web'") == 1


def test_two_saves_from_one_revision_the_second_is_refused_and_nothing_is_overwritten(tenv):
    pm = memory_of(tenv)
    rev = pm.instructions("web").rev
    pm.put_instructions("web", "from window one", rev)
    with pytest.raises(AppError) as caught:
        pm.put_instructions("web", "from window two", rev)
    assert caught.value.status == 409 and caught.value.details.get("stale") is True
    assert pm.instructions("web").text == "from window one"


def test_instructions_that_hold_a_key_or_are_too_long_are_refused_in_a_sentence(tenv):
    pm = memory_of(tenv)
    rev = pm.instructions("web").rev
    with pytest.raises(AppError) as secret:
        pm.put_instructions("web", f"use the key {SECRET} for the api", rev)
    assert secret.value.status == 422 and "key" in secret.value.message and SECRET not in secret.value.message
    with pytest.raises(AppError) as long:
        pm.put_instructions("web", "x" * 4001, rev)
    assert long.value.status == 422 and "4000" in long.value.message
    assert pm.instructions("web").text == ""


def test_an_unknown_project_is_not_found(tenv):
    pm = memory_of(tenv)
    with pytest.raises(NotFound):
        pm.instructions("nowhere")
    with pytest.raises(NotFound):
        pm.memory("nowhere")


# ---- what the app writes (FR-15, FR-19) -------------------------------------------------------------------------------------------------

def test_a_run_that_ends_leaves_one_entry_with_the_request_and_the_outcome(tenv):
    pm = memory_of(tenv)
    assert pm.memory("web").entries == []
    task_id = ended(tenv, "Build a landing page for my cafe " + "x" * 200, outcome="Made the cafe page with a menu and opening hours " + "y" * 300)
    (entry,) = pm.memory("web").entries
    assert entry.source == "run" and entry.ref == task_id and entry.on is True
    assert "asked 'Build a landing page for my cafe " in entry.text and "Result: Made the cafe page" in entry.text
    assert "x" * 200 not in entry.text and len(entry.text) <= ENTRY_CHARS                              # the request is cut at 120 characters, the outcome at 160


@pytest.mark.parametrize("status,kept", [("done", True), ("done_with_open_items", True), ("stopped", True), ("crashed", False), ("cancelled", False)])
def test_only_a_run_that_finished_or_was_stopped_is_remembered(tenv, status, kept):
    ended(tenv, "Write the quote", status=status, outcome="whatever")
    assert len(memory_of(tenv).memory("web").entries) == (1 if kept else 0)


def test_an_archived_chat_leaves_one_entry_with_its_first_owner_line_and_its_last_reply(tenv):
    pm = memory_of(tenv)
    sid = session_of(tenv)
    say(tenv, sid, "Let us plan the pricing page")
    say(tenv, sid, "We settled on three tiers: starter, team and business", who="identity")
    archive(tenv, sid)
    (entry,) = pm.memory("web").entries
    assert entry.source == "chat" and entry.ref == sid
    assert "chat 'Let us plan the pricing page'" in entry.text and "Last: We settled on three tiers" in entry.text


def test_a_chat_with_no_owner_line_leaves_nothing(tenv):
    sid = session_of(tenv)
    say(tenv, sid, "a note from the team", who="identity")
    archive(tenv, sid)
    assert memory_of(tenv).memory("web").entries == []


def test_newest_first_and_a_credential_shape_in_the_request_is_replaced(tenv):
    pm = memory_of(tenv)
    ended(tenv, "first request", outcome="first outcome")
    ended(tenv, f"use {SECRET} to log in", outcome=f"logged in with {SECRET}")
    got = texts(pm)
    assert "asked 'use " in got[0] and SECRET not in "".join(got)                                     # FR-19: the shape never reaches the entry
    assert "first request" in got[1]                                                                  # newest first


def test_entries_copy_no_file_content_and_no_reasoning(tenv):
    ended(tenv, "Summarise the attached spec", outcome="Done: see the report")
    (entry,) = memory_of(tenv).memory("web").entries
    assert set(vars(entry)) >= {"n", "text", "source", "at", "ref", "on"} and "reason" not in entry.text.lower()


def test_the_thirty_first_automatic_entry_drops_the_oldest_automatic_one_never_an_owner_entry(tenv):
    pm = memory_of(tenv)
    pm.add_entry("web", "Owner fact: the brand colour is teal")
    for n in range(MAX_ENTRIES + 3):
        ended(tenv, f"request {n}", outcome=f"outcome {n}")
    got = pm.memory("web").entries
    assert len(got) == MAX_ENTRIES and any(e.source == "owner" for e in got)
    assert "request 0" not in " ".join(e.text for e in got) and f"request {MAX_ENTRIES + 2}" in got[0].text


# ---- the owner's hand (FR-17) ----------------------------------------------------------------------------------------------------------

def test_the_owner_can_add_edit_disable_and_delete_entries(tenv):
    pm = memory_of(tenv)
    ended(tenv, "plan the menu", outcome="menu planned")
    added = pm.add_entry("web", "The owner prefers short pages")
    assert added.source == "owner" and added.on is True
    got = pm.memory("web")
    edited = [{"n": e.n, "text": ("Edited: " + e.text) if e.source == "run" else e.text, "on": e.on} for e in got.entries]
    after = pm.put_memory("web", edited, got.rev)
    assert any(e.text.startswith("Edited: ") for e in after.entries)
    off = [{"n": e.n, "text": e.text, "on": e.source != "run"} for e in after.entries]
    pm.put_memory("web", off, after.rev)
    assert [t for t in pm.deliverable("web", 3000)] == ["The owner prefers short pages"]                # a disabled entry is kept but never sent
    victim = pm.memory("web").entries[-1].n
    pm.delete_entry("web", victim)
    assert all(e.n != victim for e in pm.memory("web").entries)
    with pytest.raises(NotFound):
        pm.delete_entry("web", 9999)


def test_a_stale_revision_or_a_too_long_entry_or_too_many_entries_are_refused(tenv):
    pm = memory_of(tenv)
    pm.add_entry("web", "one")
    got = pm.memory("web")
    pm.add_entry("web", "two")                                                                          # the list moved on
    with pytest.raises(AppError) as stale:
        pm.put_memory("web", [], got.rev)
    assert stale.value.status == 409
    with pytest.raises(AppError) as long:
        pm.add_entry("web", "x" * (ENTRY_CHARS + 1))
    assert long.value.status == 422
    with pytest.raises(AppError) as secret:
        pm.add_entry("web", f"the key is {SECRET}")
    assert secret.value.status == 422


def test_memory_switched_off_sends_nothing_and_appends_nothing(tenv):
    pm = memory_of(tenv)
    ended(tenv, "before it was switched off", outcome="ok")
    assert pm.deliverable("web", 3000)
    assert pm.set_enabled("web", False).enabled is False
    assert pm.deliverable("web", 3000) == []
    ended(tenv, "while off", outcome="ok")
    sid = session_of(tenv)
    say(tenv, sid, "a chat while memory is off")
    archive(tenv, sid)
    assert len(pm.memory("web").entries) == 1                                                           # only the one from before
    pm.set_enabled("web", True)
    assert len(pm.deliverable("web", 3000)) == 1


def test_delivery_is_newest_first_and_stops_at_the_budget(tenv):
    pm = memory_of(tenv)
    for n in range(10):
        ended(tenv, f"request {n}", outcome="o" * 150)
    got = pm.deliverable("web", 700)
    assert 1 <= len(got) <= 4 and "request 9" in got[0] and sum(len(t) for t in got) <= 700


# ---- FR-18: an existing project is seeded once from its stored history -------------------------------------------------------------------

def old_history(t) -> None:
    """What a project of version 9 has: finished runs and an archived chat, and no memory document (nothing ever wrote one)."""
    for n in range(12):
        task = t.new("web", f"old request {n}")
        t.sql("UPDATE tasks SET status = 'done', outcome = ?, ended_at = ?, started_at = ? WHERE id = ?", f"old outcome {n}", 1793700000 + n * 100, 1793700000 + n * 100, task.id)
    t.sql("DELETE FROM meta WHERE key LIKE 'pmem:%'")


def test_an_existing_project_gets_its_last_ten_runs_and_last_five_chats_once_marked_from_history(tenv):
    old_history(tenv)
    for n in range(7):
        sid = session_of(tenv)
        say(tenv, sid, f"old chat {n}")
        say(tenv, sid, f"old reply {n}", who="identity")
        with tenv.db.tx() as tx:
            ChatArchive(tenv.db, tenv.graph).archive(tx, sid)
    tenv.sql("DELETE FROM meta WHERE key LIKE 'pmem:%'")                                                # forget what archiving just wrote: this is the state of a project from before D451
    pm = memory_of(tenv)
    got = pm.memory("web")
    history = [e for e in got.entries if e.source == "history"]
    assert len([e for e in history if "old request" in e.text]) == 10 and len([e for e in history if "old chat" in e.text]) == 5
    assert all("old request 0 " not in e.text and "old request 1 " not in e.text for e in history)         # only the last ten
    assert len(got.entries) <= MAX_ENTRIES and got.enabled is True
    again = pm.memory("web")
    assert [e.n for e in again.entries] == [e.n for e in got.entries]                                   # seeded once


def test_an_entry_the_owner_deleted_from_the_seed_does_not_come_back(tenv):
    old_history(tenv)
    pm = memory_of(tenv)
    first = pm.memory("web").entries
    pm.delete_entry("web", first[0].n)
    assert len(pm.memory("web").entries) == len(first) - 1
    assert pm.deliverable("web", 3000)                                                                  # and delivery works from the seeded list


def test_a_project_with_no_history_starts_with_memory_on_and_empty(tenv):
    got = memory_of(tenv).memory("sales")
    assert got.enabled is True and got.entries == []
