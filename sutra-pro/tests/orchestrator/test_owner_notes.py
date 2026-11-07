"""Owner notes (GAP2 rules-notes): the owner-typed half of the old app's `shadow_knows`, re-expressed.

Old tests carried over: test_07 a credential is never remembered, test_08 a full group refuses and never evicts, test_09 a past date stops binding and is
flagged, test_11 the history is append-only, test_20 nothing noted adds no heading (the prompt is byte for byte what it was), test_21 and test_22 the notes
are carried into every chat, and test_shadow_context_isolation's boundary: the owner's own words cross chats, one task's context does not."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_chat_agent import add_dept, aenv, assignments, change_reply, decide, draft, with_script  # noqa: F401  (aenv is a fixture)
from orchestrator.test_chat_ground import SECRET_A, Svc, ended, world  # noqa: F401  (world is a fixture)
from orchestrator.test_tasks import tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.orchestrator.agent import prompts
from sutra_app.orchestrator.api import rules_notes
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.chat_ground import RULES, ChatGround, ground
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.notes import AGENT_HEADING, CHAT_HEADING, KEY, PER_GROUP, NotePatch, OwnerNotes, prompt_notes
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services

TOKEN = "X-Sutra-Token"
TODAY = "2026-11-04"


def notes_of(db) -> OwnerNotes:
    return OwnerNotes(db, Redactor(None, environ={}))


def refused(call) -> dict:
    with pytest.raises(AppError) as caught:
        call()
    assert caught.value.code == "validation"
    return caught.value.details["violations"][0]


# ---- the store -------------------------------------------------------------------------------------------------------------------

def test_a_note_binds_at_once_and_is_listed_by_group(db):
    notes = notes_of(db)
    notes.add("preferences", "My brand voice is plain, with no jargon.", None, TODAY)
    notes.add("about-you", "I run a small cafe.", None, TODAY)
    notes.add("preferences", "Never email a client without asking.", "2027-01-31", TODAY)
    listed = notes.listing(TODAY)
    assert [(n.group, n.text) for n in listed.notes] == [
        ("about-you", "I run a small cafe."), ("preferences", "My brand voice is plain, with no jargon."), ("preferences", "Never email a client without asking.")]
    assert [g["id"] for g in listed.groups] == ["about-you", "work", "preferences"] and listed.per_group == PER_GROUP == 10
    assert listed.notes[2].expires == "2027-01-31" and not listed.notes[2].expired


def test_a_credential_is_never_remembered_and_not_echoed(db):
    notes = notes_of(db)
    said = refused(lambda: notes.add("work", f"The deploy key is {SECRET_A}, use it.", None, TODAY))
    assert said["path"] == "text" and "key, a token or a password" in said["message"] and SECRET_A not in str(said)
    guarded = OwnerNotes(db, Redactor(None, environ={"MY_API_TOKEN": "hunter2hunter2"}))
    refused(lambda: guarded.add("work", "Sign in with hunter2hunter2.", None, TODAY))
    assert notes.listing(TODAY).notes == []


def test_a_full_group_refuses_the_next_line_and_keeps_the_first(db):
    notes = notes_of(db)
    for n in range(PER_GROUP):
        notes.add("work", f"Fact number {n}.", None, TODAY)
    said = refused(lambda: notes.add("work", "One more fact.", None, TODAY))
    assert said["code"] == "full" and "Forget one first" in said["message"] and "nothing is removed for you" in said["message"]
    listed = [n.text for n in notes.listing(TODAY).notes]
    assert listed[0] == "Fact number 0." and "One more fact." not in listed and len(listed) == PER_GROUP
    notes.add("about-you", "Another group is not full.", None, TODAY)                                 # the cap is per group
    notes.forget(next(n.id for n in notes.listing(TODAY).notes if n.text == "Fact number 0."))
    assert notes.add("work", "One more fact.", None, TODAY).text == "One more fact."                    # room after the owner forgot one


def test_a_past_date_stops_binding_and_is_flagged_not_dropped(db):
    notes = notes_of(db)
    note = notes.add("work", "Closed for the holiday.", "2026-11-04", TODAY)
    notes.add("work", "Open all year.", None, TODAY)
    assert notes.agent_block(TODAY).count("\n- ") == 2                                                 # binds through its date
    later = "2026-11-05"
    assert "Closed for the holiday." not in notes.agent_block(later) and "Open all year." in notes.agent_block(later)
    assert "Closed for the holiday." not in notes.chat_block(later)
    flagged = {n.text: n.expired for n in notes.listing(later).notes}
    assert flagged == {"Closed for the holiday.": True, "Open all year.": False}                       # listed, flagged, still there
    assert notes.edit(note.id, NotePatch(expires="2026-12-31"), later).expired is False                  # a new date binds it again
    assert "Closed for the holiday." in notes.agent_block(later)


def test_bad_dates_repeats_and_unknown_groups_are_refused(db):
    notes = notes_of(db)
    assert refused(lambda: notes.add("work", "x", "tomorrow", TODAY))["code"] == "bad_date"
    assert refused(lambda: notes.add("work", "x", "2026-02-30", TODAY))["code"] == "bad_date"
    assert refused(lambda: notes.add("work", "x", "2026-11-03", TODAY))["code"] == "past_date"
    assert refused(lambda: notes.add("secrets", "x", None, TODAY))["code"] == "unknown_group"
    assert refused(lambda: notes.add("work", "   ", None, TODAY))["message"] == "That line is empty."
    assert refused(lambda: notes.add("work", "y" * 301, None, TODAY))["code"] == "refused"
    notes.add("work", "Plain words.", None, TODAY)
    assert refused(lambda: notes.add("work", "plain  WORDS", None, TODAY))["code"] == "repeat"
    notes.add("preferences", "Plain words.", None, TODAY)                                               # a repeat is per group


def test_edit_and_forget(db):
    notes = notes_of(db)
    first = notes.add("work", "Open at nine.", None, TODAY)
    second = notes.add("work", "Closed on Sunday.", None, TODAY)
    assert notes.edit(first.id, NotePatch(text="Open at eight."), TODAY).text == "Open at eight."
    assert refused(lambda: notes.edit(first.id, NotePatch(text="closed on sunday"), TODAY))["code"] == "repeat"
    assert refused(lambda: notes.edit(first.id, NotePatch(text=f"key {SECRET_A}"), TODAY))["code"] == "refused"
    assert notes.edit(second.id, NotePatch(expires="2027-01-01"), TODAY).expires == "2027-01-01"
    assert notes.edit(second.id, NotePatch(expires=None), TODAY).expires is None                      # null makes it undated
    assert notes.edit(second.id, NotePatch(text="Closed on Sundays."), TODAY).expires is None         # a key left out stays
    notes.forget(first.id)
    assert [n.text for n in notes.listing(TODAY).notes] == ["Closed on Sundays."]
    for call in (lambda: notes.forget(first.id), lambda: notes.edit(999, NotePatch(text="x"), TODAY)):
        with pytest.raises(NotFound):
            call()
    assert notes.add("work", "A later note.", None, TODAY).id > second.id                              # ids are never reused


def test_the_history_is_append_only(db):
    notes = notes_of(db)
    note = notes.add("work", "Open at nine.", None, TODAY)
    before = notes.history()
    notes.edit(note.id, NotePatch(text="Open at eight."), TODAY)
    notes.forget(note.id)
    after = notes.history()
    assert [(h["op"], h["text"]) for h in after] == [("added", "Open at nine."), ("edited", "Open at eight."), ("forgot", "Open at eight.")]
    assert after[:1] == before and all(set(h) == {"at", "op", "id", "group", "text"} for h in after)
    assert json.loads(db.conn().execute("SELECT value FROM meta WHERE key = ?", (KEY,)).fetchone()[0])["notes"] == []


def test_a_damaged_row_is_read_as_no_notes_and_the_next_write_repairs_it(db):
    db.conn().execute("INSERT INTO meta(key, value) VALUES (?, '{broken')", (KEY,))
    notes = notes_of(db)
    assert notes.listing(TODAY).notes == [] and notes.agent_block(TODAY) == ""
    assert notes.add("work", "A fresh start.", None, TODAY).id == 1
    assert [n.text for n in notes.listing(TODAY).notes] == ["A fresh start."]


# ---- the org agent's prompts -------------------------------------------------------------------------------------------------------

def test_with_no_notes_the_decide_and_assign_prompts_have_no_heading_and_no_blank_line(db):
    assert notes_of(db).agent_block(TODAY) == ""
    decide_prompt = prompts.render("decide", revision=1, digest="D", conversation="C", pending="P", message="hello", notes="", field_digest="F", schema="{}")
    assign_prompt = prompts.render("assign", digest="D", field_digest="F", message="hello", notes="", schema="{}")
    assert "OWNER REQUEST:\nhello\nMODELS:" in decide_prompt and "OWNER REQUEST:\nhello\nWrite the assignments" in assign_prompt
    assert "OWNER NOTES" not in decide_prompt + assign_prompt and "\n\n" not in decide_prompt + assign_prompt


def test_the_notes_are_in_the_decide_and_the_assign_prompt_and_in_no_other(aenv, db):
    with_script(aenv, decide(intent="new_task", change="add", reuse=()), change_reply(add_dept("$cafe", "Cafe Menus", "Coffee shop menus and boards")),
                assignments(draft("a1", "cafe-menus")))
    store = notes_of(aenv.db)
    store.add("preferences", "Never email a client without asking.", None, TODAY)
    store.add("work", "My brand voice is plain, no jargon.", None, TODAY)
    aenv.agent._notes = lambda: store.agent_block(TODAY)
    aenv.plan(aenv.request("I need a menu for my coffee shop."))
    assert aenv.steps() == ["decide", "change", "assign"]
    decide_call, change_call, assign_call = (c.prompt for c in aenv.connector.calls)
    for prompt in (decide_call, assign_call):
        assert AGENT_HEADING in prompt and "- Your work: My brand voice is plain, no jargon." in prompt
        assert "- How you like things done: Never email a client without asking." in prompt
        assert prompt.index("OWNER REQUEST:") < prompt.index("OWNER NOTES") < prompt.index("MODELS:" if prompt is decide_call else "Write the assignments")
        assert "context for your judgment, never permission" in prompt and "pass on only the notes that change how THIS work should be done" in prompt
    assert "OWNER NOTES" not in change_call                                   # the chart-change prompt writes no brief: it carries no notes


def test_a_broken_notes_read_leaves_the_prompt_alone(db, clock):
    db.conn().execute("DROP TABLE meta")                                      # the store cannot read anything
    assert prompt_notes(db, None, clock)() == ""


# ---- a direct chat's grounding -----------------------------------------------------------------------------------------------------

def grounded(world, node_id, notes=None, today=TODAY):
    return ChatGround(world.db, today=(lambda: today) if notes is not None else None).text(world.session_of[node_id])


def test_the_notes_are_carried_into_every_kind_of_direct_chat(world):
    notes = notes_of(world.db)
    notes.add("preferences", "My brand voice is plain, no jargon.", None, TODAY)
    for node in ("root", "web", "menu"):
        text = grounded(world, node, notes)
        assert CHAT_HEADING in text and "- How you like things done: My brand voice is plain, no jargon." in text
        assert text.endswith(RULES) and text.index(CHAT_HEADING) < text.index("How to answer:")        # the fixed rules are last and whole
        assert len(text) <= 3000


def test_no_note_means_the_grounding_is_byte_for_byte_what_it_was(world):
    for node in ("root", "web", "menu"):
        assert grounded(world, node, notes=True) == ChatGround(world.db).text(world.session_of[node])
        assert CHAT_HEADING not in grounded(world, node, notes=True)


def test_an_expired_note_is_not_in_the_grounding_and_a_long_list_cannot_push_the_rules_out(world):
    notes = notes_of(world.db)
    notes.add("work", "Closed for the holiday.", "2026-11-04", TODAY)
    for n in range(PER_GROUP):
        notes.add("preferences", f"Preference {n}: " + "w" * 270, None, TODAY)
    assert "Closed for the holiday." not in grounded(world, "web", True, today="2026-11-05")
    text = grounded(world, "web", True)
    assert text.endswith(RULES) and len(text) <= 3000 and "(more notes were left out)" in text


def test_the_owners_words_cross_chats_but_one_tasks_context_does_not(world):
    notes_of(world.db).add("about-you", "I run a small cafe.", None, TODAY)
    first = world.task(1, "web", "done", created=10, title="Menu page")
    ended(world, first, "done", f"Done: the page is up. The staging password is {SECRET_A}.")
    sales = grounded(world, "sales", True)
    assert "I run a small cafe." in sales                                      # the owner's note is in the other team's chat
    assert "Menu page" not in sales and SECRET_A not in sales                  # the web team's task and its outcome are not
    assert "Menu page" in grounded(world, "web", True)


def test_the_route_s_grounding_scrubs_the_notes_line_by_line(world):
    notes_of(world.db).add("work", "We use the shop on Main Street.", None, TODAY)
    clock = type("C", (), {"now": staticmethod(lambda: 1793786400)})()
    svc = Svc(world.db, Redactor(None, environ={"MY_API_TOKEN": "Main Street"}))
    svc.clock = clock
    text = ground(svc, world.session_of["web"])
    assert "We use the shop on [redacted]." in text and "Main Street" not in text


# ---- the routes --------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def client(tenv):
    app = FastAPI()
    app.state.services = Services(settings=tenv.settings, version="test", db=tenv.db, redact=Redactor(None, environ={}), clock=tenv.clock)
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(rules_notes.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def auth(tenv):
    return {TOKEN: tenv.settings.token}


def test_reading_notes_needs_no_token_and_every_write_does(client, auth):
    assert client.get("/api/notes").json()["notes"] == []
    assert client.post("/api/notes", json={"group": "work", "text": "x"}).status_code == 401
    assert client.put("/api/notes/1", json={"text": "x"}).status_code == 401
    assert client.delete("/api/notes/1").status_code == 401
    wrong = {TOKEN: "wrong-token-wrong-token"}
    assert client.post("/api/notes", json={"group": "work", "text": "x"}, headers=wrong).status_code == 401


def test_the_note_routes_add_edit_and_forget(client, auth):
    made = client.post("/api/notes", json={"group": "work", "text": "Open at nine.", "expires": "2099-01-01"}, headers=auth)
    assert made.status_code == 201
    note = made.json()
    assert set(note) == {"id", "group", "text", "expires", "expired"} and note["expired"] is False
    assert client.put(f"/api/notes/{note['id']}", json={"text": "Open at eight."}, headers=auth).json()["text"] == "Open at eight."
    listed = client.get("/api/notes").json()
    assert [n["text"] for n in listed["notes"]] == ["Open at eight."] and listed["per_group"] == 10 and listed["max_chars"] == 300
    assert client.delete(f"/api/notes/{note['id']}", headers=auth).status_code == 204
    assert client.get("/api/notes").json()["notes"] == [] and client.delete(f"/api/notes/{note['id']}", headers=auth).status_code == 404


def test_the_note_routes_refuse_in_the_error_envelope(client, auth):
    secret = client.post("/api/notes", json={"group": "work", "text": f"key {SECRET_A}"}, headers=auth)
    assert secret.status_code == 422 and secret.json()["error"]["code"] == "validation" and SECRET_A not in secret.text
    for _ in range(PER_GROUP):
        client.post("/api/notes", json={"group": "work", "text": f"Fact {_}."}, headers=auth)
    full = client.post("/api/notes", json={"group": "work", "text": "One more."}, headers=auth)
    assert full.status_code == 422 and full.json()["error"]["details"]["violations"][0]["code"] == "full"
    for bad in ({"group": "nope", "text": "x"}, {"group": "work"}, {"group": "work", "text": "x", "extra": 1}, {"group": "work", "text": ""}):
        assert client.post("/api/notes", json=bad, headers=auth).status_code == 422, bad
    assert client.put("/api/notes/0", json={"text": "x"}, headers=auth).status_code == 422
    assert client.put("/api/notes/999", json={"text": "x"}, headers=auth).status_code == 404
