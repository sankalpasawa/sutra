"""What a turn produced (D157): the words and the reply a function atom carries in its body are stored as the layer wrote them, served by the
atom routes and by the node detail, and, in the app, put through the app's scrub and cut again before they are stored. An atom stored before
D157 has neither and is served as it was."""
import json

import pytest
from factories_atom import abandon, close_with
from orchestrator.test_atoms_usage import NODE, apply, atoms, chats, fn_event, opened, row, row_body, task, world  # noqa: F401  (fixtures and helpers)

from sutra_app.config import Settings
from sutra_app.connectors.egress import scrubbed
from sutra_app.library.atom import REPLY_TEXT_MAX, AtomReply, OutputItem, Seen
from sutra_app.orchestrator.atoms import AtomStore
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.wiring import build_services

MADE = OutputItem(verb="make", name="a proposal of 2 workflows: W-1 Build the page, Write the copy", form="proposal", ref="workflows.json")
SAID = OutputItem(verb="do", name="posted 1 message to Priority", form="message", ref="chat")
REPLY = json.dumps({"act": "PROPOSE", "say": "two workflows"}, indent=2)
SECRET = "env-secret-value-1234"
SHAPE = "sk-abcdefghijklmnop"


def body_of(world, atom_id):
    return json.loads(row_body(world, atom_id))


def scrubbing_store(db, chats, world):
    redactor = Redactor(None, environ={"SOME_API_KEY": SECRET})
    return AtomStore(db, chats=chats, graph=world.store, scrub=lambda text: scrubbed(text, redactor))


# ---- stored and served ------------------------------------------------------------------------------------------------------------

def test_the_words_and_the_reply_of_each_transition_are_stored_and_served_by_both_atom_routes_and_the_node_detail(db, world, atoms, task):
    t0 = opened()
    apply(db, atoms, fn_event(t0), task=task)
    assert atoms.get(t0.atom.id).body["reply"] is None and atoms.get(t0.atom.id).body["produced"] == []
    failed = close_with(t0.atom, 1, seen=Seen(produced=[SAID], reply=AtomReply(text="first")))
    apply(db, atoms, fn_event(failed), task=task)
    assert atoms.get(t0.atom.id).body["reply"] == {"text": "first", "clipped": False} and atoms.get(t0.atom.id).state == "open"
    closed = close_with(failed.atom, 0, seen=Seen(produced=[MADE, SAID], reply=AtomReply(text=REPLY, clipped=True)))
    result = apply(db, atoms, fn_event(closed), task=task)
    assert (result.status, result.display) == ("applied", "closed")
    served = atoms.get(t0.atom.id).body
    assert served["reply"] == {"text": REPLY, "clipped": True}
    assert [(i["verb"], i["name"], i["form"], i["ref"]) for i in served["produced"]] == [
        ("make", MADE.name, "proposal", "workflows.json"), ("do", SAID.name, "message", "chat")]
    assert atoms.find(node_id=NODE)[0].body == served and world.store.node(NODE).atoms[0].body == served        # the list route and the drawer's route
    assert body_of(world, t0.atom.id) == served                                                               # exactly what the row holds


def test_a_failed_atom_that_is_abandoned_keeps_the_last_reply_it_received(db, world, atoms, task):
    t = opened()
    apply(db, atoms, fn_event(t), task=task)
    last = t
    for n in (1, 2, 3):
        last = close_with(last.atom, 1, seen=Seen(produced=[SAID], reply=AtomReply(text=f"try {n}")))
        apply(db, atoms, fn_event(last), task=task)
    ended = abandon(last.atom, "verify failed: reply-valid: missing", code="verify_failed", seen=Seen(produced=[SAID], reply=AtomReply(text="try 3")))
    assert apply(db, atoms, fn_event(ended), task=task).display == "verify_failed"
    assert atoms.get(t.atom.id).body["reply"]["text"] == "try 3" and atoms.get(t.atom.id).state == "verify_failed"


def test_an_atom_stored_before_d157_is_served_as_it_was_with_neither_key(db, world, atoms):
    old = world.atom(NODE, "closed", n=7)                                                                    # a body written before the two keys
    assert atoms.get(old).body == {"n": 7} and world.store.node(NODE).atoms[0].body == {"n": 7}


def test_a_replayed_line_of_an_atom_with_a_reply_is_unchanged(db, world, chats, task):
    store = scrubbing_store(db, chats, world)
    t = close_with(opened().atom, 0, seen=Seen(produced=[SAID], reply=AtomReply(text=f'{{"k": "{SECRET} {SHAPE}"}}')))
    apply(db, store, fn_event(opened()), task=task)
    event = fn_event(t)
    assert apply(db, store, event, task=task).status == "applied"
    assert apply(db, store, event, task=task).status == "unchanged"                                          # the scrub gives the same text twice: the sha agrees


# ---- the scrub ---------------------------------------------------------------------------------------------------------------------

def test_a_store_without_a_scrub_keeps_what_it_is_given(db, world, atoms, task):
    t0 = opened()
    apply(db, atoms, fn_event(t0), task=task)
    apply(db, atoms, fn_event(close_with(t0.atom, 0, seen=Seen(produced=[SAID], reply=AtomReply(text=f"{SECRET} {SHAPE}")))), task=task)
    assert body_of(world, t0.atom.id)["reply"]["text"] == f"{SECRET} {SHAPE}"


def test_a_store_with_a_scrub_replaces_secret_values_and_credential_shapes_in_the_reply_the_words_and_their_refs(db, world, chats, task):
    store = scrubbing_store(db, chats, world)
    t0 = opened()
    apply(db, store, fn_event(t0), task=task)
    item = OutputItem(verb="do", name=f"said: use {SHAPE}", form="reply", ref=f"the reply of {SECRET}")
    closed = close_with(t0.atom, 0, seen=Seen(produced=[item, SAID], reply=AtomReply(text=f'{{"say": "{SECRET} and {SHAPE}"}}')))
    assert apply(db, store, fn_event(closed), task=task).status == "applied"
    stored = row_body(world, t0.atom.id)
    assert SECRET not in stored and SHAPE not in stored
    body = json.loads(stored)
    assert body["reply"] == {"text": '{"say": "[redacted] and [redacted:openai-key]"}', "clipped": False}
    assert [(i["name"], i["ref"]) for i in body["produced"]] == [("said: use [redacted:openai-key]", "the reply of [redacted]"), (SAID.name, "chat")]
    assert SECRET not in json.dumps(store.get(t0.atom.id).model_dump(mode="json"))


def test_a_text_that_grows_when_a_secret_is_replaced_is_cut_again_to_4000_characters_and_says_so(db, world, chats, task):
    store = scrubbing_store(db, chats, world)
    t0 = opened()
    apply(db, store, fn_event(t0), task=task)
    text = ("sk-12345678 " * 400)[:REPLY_TEXT_MAX]                                                             # 4,000 characters; each key grows to 21
    closed = close_with(t0.atom, 0, seen=Seen(reply=AtomReply(text=text)))
    assert apply(db, store, fn_event(closed), task=task).status == "applied"
    reply = body_of(world, t0.atom.id)["reply"]
    assert len(reply["text"]) == REPLY_TEXT_MAX and reply["clipped"] is True and "sk-12345678" not in reply["text"] and reply["text"].endswith("…")


def test_a_short_reply_and_the_flag_the_layer_set_are_left_as_they_were(db, world, chats, task):
    store = scrubbing_store(db, chats, world)
    t0 = opened()
    apply(db, store, fn_event(t0), task=task)
    apply(db, store, fn_event(close_with(t0.atom, 0, seen=Seen(reply=AtomReply(text="plain words", clipped=True)))), task=task)
    assert body_of(world, t0.atom.id)["reply"] == {"text": "plain words", "clipped": True}


@pytest.mark.parametrize("reply,produced", [(None, []), ({"text": 5}, [{"name": 5}]), ("text", ["x"])])
def test_a_body_whose_output_is_not_the_shape_the_library_expects_is_left_for_the_gate(db, world, chats, task, reply, produced):
    """The scrub reads defensively: a malformed part is not touched, and the library gate then decides (a refusal, never an error)."""
    store = scrubbing_store(db, chats, world)
    t0 = opened()
    result = apply(db, store, fn_event(t0, body={"reply": reply, "produced": produced}), task=task)
    assert result.status in ("applied", "rejected")
    if result.status == "rejected":
        assert "refused" in result.reason


def test_the_apps_wiring_gives_the_store_the_apps_scrub(tmp_path, monkeypatch):
    monkeypatch.setenv("SOME_API_KEY", SECRET)
    settings = Settings.load({}, data_dir=tmp_path / "data", token="t" * 24, env_file=tmp_path / "none.env", engine="fake")
    services = build_services(settings)
    try:
        assert services.atoms.scrub(f"{SECRET} {SHAPE}") == "[redacted] [redacted:openai-key]"
    finally:
        services.db.close()
