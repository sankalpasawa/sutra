"""Ask, the read-only cited answer of the direct chat (DV-1, flag SUTRA_ASK_V1, D350 to D353), over HTTP.

Two halves. With the flag OFF the chat is what it was: a request that names `mode` is refused as an unknown field exactly like any other, no answer of the API has a new key, and a direct
chat without a mode sends the same system text and the same turn to the port, and stores the same rows, as before. With the flag ON an Ask turn is held to read access with the limits of a
function's question, its answer is followed by ONE card of sources whose labels come from code, a stopped or failed turn has no card, and a chat without a mode is still untouched.
The ports here are scripted (no model, no quota); the router's read cap is proved against the fake CLIs in tests/connectors/test_chat_ask_cap.py."""
from __future__ import annotations

import json

import pytest
from orchestrator.test_api_chat_v2 import H, error_code, rig, wait_for, world  # noqa: F401  (the fixtures of the chat v2 routes)
from orchestrator.test_api_live_chat import LivePort, live, started, text  # noqa: F401

from sutra_app.connectors.chat_models import ChatEvent
from sutra_app.connectors.errors import CrashedError
from sutra_app.connectors.workdir import Folder
from sutra_app.orchestrator import ask_mode, direct_running
from sutra_app.orchestrator.chat_ground import ASK_RULES, RULES, ground

CITED = "The program prints a greeting in [src/app.py:3-4]. It returns zero at [src/app.py:5 \"return 0\"]."
GOOD, BAD = "checked", "could not find"


class FakeRouter:
    """What `ground()` and the Ask mode read of a router: the owner's folder (read now) and a clock."""

    def __init__(self, folder, edit=False, now=1000.0):
        self.folder = Folder(str(folder), edit=edit) if folder else ""
        self._clock = lambda: now

    def chat_folder(self):
        return self.folder


class Port(LivePort):
    """The scripted live port that also keeps every system text it was given."""

    def __init__(self, *script, **kw):
        super().__init__(*script, **kw)
        self.systems = []

    def set_system(self, sid, text):
        self.systems.append(text)


class LegacyPort:
    """The port of the legacy turn (`SUTRA_LIVE_V1=0`): stream(sid, turn) with no stop token."""

    def __init__(self, answer, fail=None):
        self.answer, self.fail, self.systems, self.turns = answer, fail, [], []

    def stream(self, sid, turn):
        self.turns.append(turn)
        if self.fail is not None:
            raise self.fail
        yield ChatEvent(kind="turn_done", data={"text": self.answer, "provider": "claude", "model": None, "usd": None, "blocks": [], "switched": None})

    def set_system(self, sid, text):
        self.systems.append(text)

    def stop(self, sid):
        return False


@pytest.fixture
def folder(tmp_path):
    home = tmp_path / "proj"
    (home / "src").mkdir(parents=True)
    (home / "src" / "app.py").write_text("import os\n\ndef main():\n    print('hello world')\n    return 0\n", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("secret\n", encoding="utf-8")
    return home


@pytest.fixture
def ask(live, folder):
    """The live chat with the flag ON and the owner's folder set (read and change: the Ask turn must still be held to read)."""
    client, world, chats, bus, services = live
    services.settings = services.settings.model_copy(update={"ask_v1": True})
    services.connector_router = FakeRouter(folder, edit=True)
    return client, world, chats, bus, services


def card_of(message):
    """The card of a stored message as the wire shows it."""
    return message.card.model_dump(mode="json")


def say(client, sid, line="what does it print?", **extra):
    return client.post(f"/api/chats/{sid}/direct", json={"text": line, **extra}, headers=H)


def finish(chats, sid, count):
    return wait_for(lambda: len(chats.messages(sid)) >= count and not direct_running.answering(sid), 15)


# ---- the flag OFF: the chat is what it was ------------------------------------------------------------------------------------------------

def test_off_a_request_that_names_mode_is_refused_exactly_like_any_unknown_field(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.chat_port = Port(started(), text("ok"))
    asked = say(client, sid, mode="ask")
    other = say(client, sid, bogus="ask")
    assert asked.status_code == other.status_code == 422
    assert asked.json() == json.loads(json.dumps(other.json()).replace("bogus", "mode"))          # the same refusal, the name aside
    assert asked.json()["error"]["details"]["violations"][0]["code"] == "extra_forbidden"
    assert chats.messages(sid) == [] and services.chat_port.streams == [] and not direct_running.answering(sid)        # nothing stored, nothing started


def test_off_every_value_of_mode_is_refused_the_same_and_a_retry_names_no_mode_either(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    for value in ("ask", "do", "", None, 7, ["ask"], {"a": 1}):
        r = say(client, sid, mode=value)
        assert r.status_code == 422 and r.json()["error"]["details"]["violations"][0]["code"] == "extra_forbidden", value
    r = client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": 1, "mode": "ask"}, headers=H)
    plain = client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": 1, "bogus": "ask"}, headers=H)
    assert r.status_code == plain.status_code == 422 and r.json() == json.loads(json.dumps(plain.json()).replace("bogus", "mode"))
    assert chats.messages(sid) == []


def test_off_the_token_is_still_asked_for_first(live):
    client, world, *_ = live
    sid = world.session_of["web"]
    assert error_code(client.post(f"/api/chats/{sid}/direct", json={"text": "x", "mode": "ask"}), 401) == "bad_token"


def test_off_no_answer_of_the_api_has_a_new_key(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    pill = client.get(f"/api/chats/{sid}/providers").json()
    assert set(pill) == {"providers", "chosen", "kind", "agent", "own", "effective"} and "ask" not in pill
    assert "ask" not in services.settings.public() and "ask_v1" not in services.settings.public()


def test_off_and_on_a_chat_without_a_mode_sends_the_same_system_text_and_the_same_turn_and_stores_the_same_rows(live, folder):
    """The identity test: the flag flipped between two identical sends changes nothing the port, the store or the page can see."""
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.connector_router = FakeRouter(folder, edit=True)
    services.chat_port = port = Port(started(), text("It prints hello. [src/app.py:4]"))
    assert say(client, sid, "what does it print?").status_code == 202 and finish(chats, sid, 2)                   # flag off
    services.settings = services.settings.model_copy(update={"ask_v1": True})
    assert say(client, sid, "what does it print?").status_code == 202 and finish(chats, sid, 4)                    # flag on, no mode
    assert say(client, sid, "what does it print?", mode="do").status_code == 202 and finish(chats, sid, 6)         # flag on, mode do: the same
    assert port.systems[0] == port.systems[1] == port.systems[2] == ground(services, sid)                          # byte for byte, and no Ask rule in it
    assert ASK_RULES not in port.systems[0] and port.systems[0].endswith(RULES)
    turns = [t[1].model_dump(mode="json") for t in port.streams]
    assert turns[0] == turns[1] == turns[2] and turns[0]["tag"]["workspace"] == "none" and turns[0]["allowance"] is None
    rows = chats.messages(sid)
    assert [m.kind for m in rows] == ["text", "text"] * 3 and all(m.card is None for m in rows)                      # no card, with or without the flag
    assert [m.text for m in rows[1::2]] == [rows[1].text] * 3


def test_off_the_folder_text_of_a_plain_chat_still_says_the_owner_allowed_changes(live, folder):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.connector_router = FakeRouter(folder, edit=True)
    text_off = ground(services, sid)
    assert "create and change" in text_off and "read-only" not in text_off.split("How to answer:")[0]
    assert ground(services, sid, ask=False) == text_off


# ---- the flag ON: input and discovery -----------------------------------------------------------------------------------------------------

def test_on_the_pill_tells_the_page_that_ask_exists(ask):
    client, world, *_ = ask
    sid = world.session_of["web"]
    assert client.get(f"/api/chats/{sid}/providers").json()["ask"] is True
    assert client.get("/api/chats/cs_org/providers").json()["ask"] is True


def test_on_a_bad_mode_is_refused_in_words_after_the_token_and_nothing_starts(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), text("x"))
    for value in ("write", "ASK", "", None, 1, ["ask"], True):
        r = say(client, sid, mode=value)
        assert error_code(r, 422) == "validation" and r.json()["error"]["message"] == "mode is ask or do", value
        assert r.json()["error"]["details"]["violations"][0]["path"] == "mode"
    assert error_code(client.post(f"/api/chats/{sid}/direct", json={"text": "x", "mode": "write"}), 401) == "bad_token"     # no token: the token first, nothing about the body
    assert chats.messages(sid) == [] and services.chat_port.streams == []


def test_on_any_other_unknown_field_is_still_refused(ask):
    client, world, *_ = ask
    sid = world.session_of["web"]
    r = say(client, sid, bogus=1)
    assert r.status_code == 422 and r.json()["error"]["details"]["violations"][0]["code"] == "extra_forbidden"
    r = say(client, sid, mode="ask", bogus=1)                                  # mode is taken out; the other field is still caught by the closed model
    assert r.status_code == 422 and r.json()["error"]["details"]["violations"][0]["path"].endswith("bogus")


# ---- the flag ON: what an Ask turn is -----------------------------------------------------------------------------------------------------

def test_an_ask_turn_is_read_only_limited_and_grounded_in_the_ask_rules_even_when_the_owner_allowed_changes(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = port = Port(started(), text("It prints hello. [src/app.py:4]"))
    r = say(client, sid, mode="ask")
    assert r.status_code == 202 and set(r.json()) == {"message_id", "turn", "generation_id", "attempt_no", "client_id"}            # the same answer as any live send
    assert finish(chats, sid, 3)
    turn = port.streams[0][1]
    assert turn.tag.workspace == "read" and turn.tag.purpose == "agent_turn" and turn.text == "what does it print?"
    assert (turn.allowance.max_calls, turn.allowance.max_usd, turn.allowance.deadline) == (ask_mode.ASK_MAX_CALLS, ask_mode.ASK_MAX_USD, 1000.0 + ask_mode.ASK_TIMEOUT_S)
    assert (ask_mode.ASK_MAX_CALLS, ask_mode.ASK_MAX_USD, ask_mode.ASK_TIMEOUT_S) == (2, 0.25, 120.0)                              # the limits of a function's question
    system = port.systems[0]
    assert system.endswith(ASK_RULES) and "Working folder:" in system
    assert "create and change" not in system and "read-only" in system                      # the folder paragraph is the read-only one although the grant is "edit"
    assert chats.messages(sid)[0].text == "what does it print?"                              # the owner's line is stored as written, with no instruction added


def test_after_the_answer_one_card_lists_every_source_with_a_label_made_by_code(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    answer = ("It prints a greeting [src/app.py:3-4] and returns zero [src/app.py:5 \"return 0\"], "
              "it reads a settings file [src/config.py:1-9], quote [src/app.py:4 \"not in this file\"] and [../outside.txt:1]. Verified by Sutra: all checked.")
    services.chat_port = Port(started(), text(answer))
    assert say(client, sid, "what does it do?", mode="ask").status_code == 202 and finish(chats, sid, 3)
    user, reply, card = chats.messages(sid)
    assert (user.role, reply.kind, reply.turn, reply.text) == ("user", "text", user.id, answer)
    assert (card.kind, card.role, card.who, card.text, card.turn, card.attempt, card.superseded, card.id > reply.id) == ("card", "agent", "sutra", "", user.id, 1, False, True)
    body = card_of(card)
    assert body["type"] == "answer_sources" and body["question"] == "what does it do?"
    assert [(s["path"], s["start"], s["end"], s["label"]) for s in body["sources"]] == [
        ("src/app.py", 3, 4, GOOD), ("src/app.py", 5, 5, GOOD), ("src/config.py", 1, 9, BAD), ("src/app.py", 4, 4, BAD), ("../outside.txt", 1, 1, BAD)]
    assert [s.get("how") for s in body["sources"]] == ["lines", "quote", None, None, None]
    assert [s.get("reason") for s in body["sources"]][2:] == ["there is no such file", "the quoted words are not on those lines", "that path goes outside your folder"]
    assert (body["checked"], body["missing"], body["more"]) == (2, 3, 0)
    listed = client.get(f"/api/chats/{sid}/messages").json()["messages"]
    assert listed[-1]["card"] == body and listed[-1]["kind"] == "card" and "text" in listed[-1]          # the wire shape the page reads


def test_an_answer_with_no_source_gets_a_card_that_says_so(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), text("It prints hello and returns zero. I think."))
    assert say(client, sid, mode="ask").status_code == 202 and finish(chats, sid, 3)
    card = card_of(chats.messages(sid)[2])
    assert card == {"type": "answer_sources", "question": "what does it print?", "sources": [], "checked": 0, "missing": 0, "more": 0}


def test_an_answer_whose_every_source_is_wrong_is_reported_as_nothing_found(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), text("See [nope.py:1-2], [src/app.py:90-91] and [/etc/hosts:1]. All checked, I promise."))
    assert say(client, sid, mode="ask").status_code == 202 and finish(chats, sid, 3)
    card = card_of(chats.messages(sid)[2])
    assert [s["label"] for s in card["sources"]] == [BAD] * 3 and (card["checked"], card["missing"]) == (0, 3)
    assert [s["reason"] for s in card["sources"]] == ["there is no such file", "the file has only 5 lines", "that path is not inside your folder"]


def test_with_no_working_folder_every_source_says_so_and_the_turn_still_runs(live):
    client, world, chats, bus, services = live
    services.settings = services.settings.model_copy(update={"ask_v1": True})
    sid = world.session_of["web"]
    services.chat_port = port = Port(started(), text("Maybe [src/app.py:1]."))
    assert say(client, sid, mode="ask").status_code == 202 and finish(chats, sid, 3)
    card = card_of(chats.messages(sid)[2])
    assert card["sources"][0]["reason"] == "no working folder is set" and card["checked"] == 0
    assert port.streams[0][1].tag.workspace == "read"


def test_a_secret_in_a_source_is_scrubbed_before_the_card_is_stored(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), text('See [src/app.py:4 "key sk-abcdefgh12345678 here"] and [sk-abcdefgh12345678.py:1].'))
    assert say(client, sid, mode="ask").status_code == 202 and finish(chats, sid, 3)
    stored = json.dumps(card_of(chats.messages(sid)[2]))
    assert "sk-abcdefgh12345678" not in stored and "[redacted:openai-key]" in stored


def test_a_stopped_or_failed_ask_turn_has_no_card(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), text("Half an answer [src/app.py:1]"), CrashedError("the process died"))
    assert say(client, sid, mode="ask").status_code == 202 and finish(chats, sid, 3)
    kinds = [m.kind for m in chats.messages(sid)]
    assert kinds == ["text", "text", "error"] and "card" not in kinds


def test_the_owners_monthly_limit_does_not_hold_ask_back_while_a_plain_chat_still_works(ask):
    """Review m9: the read-only way must not be refused while the writing way works. A direct chat is not gated by the monthly limit today; Ask follows it."""
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    asked = []

    class Held:
        def gate(self, conn, now, dept):
            asked.append(dept)
            return "Waiting: the monthly limit is reached (about $10.10 of $10.00)"

    services.limits = Held()
    services.chat_port = port = Port(started(), text("It prints hello [src/app.py:4]."))
    assert say(client, sid, mode="ask").status_code == 202 and finish(chats, sid, 3)
    assert say(client, sid, "plain").status_code == 202 and finish(chats, sid, 5)
    assert asked == [] and port.streams[0][1].tag.workspace == "read" and [m.kind for m in chats.messages(sid)] == ["text", "text", "card", "text", "text"]


def test_a_retry_of_a_failed_ask_turn_names_its_mode_again_and_is_read_only_with_a_card_of_its_own(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = port = Port(started(), CrashedError("died"))
    first = say(client, sid, mode="ask")
    assert first.status_code == 202 and finish(chats, sid, 2)
    line = first.json()["message_id"]
    assert [m.kind for m in chats.messages(sid)] == ["text", "error"]
    services.chat_port = port2 = Port(started(), text("It prints hello [src/app.py:4]."))
    r = client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": line, "mode": "ask"}, headers=H)
    assert r.status_code == 202 and r.json()["attempt_no"] == 2 and finish(chats, sid, 4)
    assert port2.streams[0][1].tag.workspace == "read" and port2.streams[0][1].allowance.max_calls == 2 and port2.systems[0].endswith(ASK_RULES)
    rows = chats.messages(sid)
    card = rows[-1]
    assert card.kind == "card" and card.attempt == 2 and card.turn == line and card.superseded is False
    assert card_of(card)["sources"][0]["label"] == GOOD


def test_a_retry_with_a_bad_mode_is_refused_in_words_and_starts_nothing(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), CrashedError("died"))
    line = say(client, sid, mode="ask").json()["message_id"]
    assert finish(chats, sid, 2)
    services.chat_port = port2 = Port(started(), text("never"))
    r = client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": line, "mode": "write"}, headers=H)
    assert error_code(r, 422) == "validation" and r.json()["error"]["message"] == "mode is ask or do"
    assert port2.streams == [] and [m.kind for m in chats.messages(sid)] == ["text", "error"] and not direct_running.answering(sid)


def test_a_failed_ask_retried_with_no_mode_stays_read_only_with_its_card(ask):
    """Review M2: the mode is stored with the owner's line, so a page that forgot it (a reload, another tab) cannot widen the retry into a Do with the owner's write access."""
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), CrashedError("died"))
    line = say(client, sid, mode="ask").json()["message_id"]
    assert finish(chats, sid, 2)
    assert chats.messages(sid)[0].mode == "ask"                                              # stored with the line, in its own meta
    services.chat_port = port2 = Port(started(), text("Again [src/app.py:4]."))
    assert client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": line}, headers=H).status_code == 202 and finish(chats, sid, 4)
    turn = port2.streams[0][1]
    assert turn.tag.workspace == "read" and turn.allowance.max_calls == 2 and port2.systems[0].endswith(ASK_RULES)
    assert [m.kind for m in chats.messages(sid)] == ["text", "error", "text", "card"]
    assert card_of(chats.messages(sid)[3])["sources"][0]["label"] == GOOD


def test_a_retry_that_names_ask_for_a_stored_ask_is_the_same_and_one_that_names_do_is_refused(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), CrashedError("died"))
    line = say(client, sid, mode="ask").json()["message_id"]
    assert finish(chats, sid, 2)
    services.chat_port = port2 = Port(started(), text("never"))
    refused = client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": line, "mode": "do"}, headers=H)
    assert error_code(refused, 422) == "validation" and "read only" in refused.json()["error"]["message"]
    assert port2.streams == [] and [m.kind for m in chats.messages(sid)] == ["text", "error"] and not direct_running.answering(sid)
    services.chat_port = port3 = Port(started(), text("ok [src/app.py:1]"))
    assert client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": line, "mode": "ask"}, headers=H).status_code == 202 and finish(chats, sid, 4)
    assert port3.streams[0][1].tag.workspace == "read"


def test_a_retry_of_a_do_line_stays_a_do_unless_the_body_narrows_it_to_ask(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), CrashedError("died"))
    line = say(client, sid).json()["message_id"]
    assert finish(chats, sid, 2) and chats.messages(sid)[0].mode is None
    services.chat_port = port2 = Port(started(), text("Again [src/app.py:4]."))
    assert client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": line}, headers=H).status_code == 202 and finish(chats, sid, 3)
    assert port2.streams[0][1].tag.workspace == "none" and port2.streams[0][1].allowance is None and ASK_RULES not in port2.systems[0]
    assert [m.kind for m in chats.messages(sid)] == ["text", "error", "text"]               # no card: a Do
    services.chat_port = Port(started(), CrashedError("died"))
    line2 = say(client, sid, "second").json()["message_id"]
    assert finish(chats, sid, 5)
    services.chat_port = port3 = Port(started(), text("Narrowed [src/app.py:4]."))
    assert client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": line2, "mode": "ask"}, headers=H).status_code == 202 and finish(chats, sid, 7)
    assert port3.streams[0][1].tag.workspace == "read" and chats.messages(sid)[-1].kind == "card"       # a Do may be asked again as an Ask


def test_the_mode_is_on_the_wire_only_for_the_line_of_an_ask(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), text("A [src/app.py:1]."))
    assert say(client, sid, "first", mode="ask").status_code == 202 and finish(chats, sid, 3)
    assert say(client, sid, "second").status_code == 202 and finish(chats, sid, 5)
    wire = client.get(f"/api/chats/{sid}/messages").json()["messages"]
    assert [(m["role"], m.get("mode")) for m in wire] == [("user", "ask"), ("agent", None), ("agent", None), ("user", None), ("agent", None)]
    assert all("mode" not in m for m in wire if m.get("mode") is None)


def test_a_chat_with_no_ask_in_it_has_no_mode_key_on_any_message(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    services.chat_port = Port(started(), text("plain"))
    assert say(client, sid).status_code == 202 and finish(chats, sid, 2)
    assert all("mode" not in m for m in client.get(f"/api/chats/{sid}/messages").json()["messages"])


def test_one_ask_turn_and_one_plain_turn_in_the_same_chat_do_not_leak_into_each_other(ask):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = port = Port(started(), text("A [src/app.py:1]."))
    assert say(client, sid, "first", mode="ask").status_code == 202 and finish(chats, sid, 3)
    assert say(client, sid, "second").status_code == 202 and finish(chats, sid, 5)
    assert port.streams[0][1].tag.workspace == "read" and port.streams[1][1].tag.workspace == "none" and port.streams[1][1].allowance is None
    assert port.systems[0].endswith(ASK_RULES) and ASK_RULES not in port.systems[1]
    assert [m.kind for m in chats.messages(sid)] == ["text", "text", "card", "text", "text"]


def test_the_org_chat_can_be_asked_too(ask):
    client, world, chats, bus, services = ask
    services.chat_port = Port(started(), text("Yes [src/app.py:1]."))
    assert say(client, "cs_org", mode="ask").status_code == 202 and finish(chats, "cs_org", 3)
    assert card_of(chats.messages("cs_org")[2])["type"] == "answer_sources"


# ---- the legacy turn (SUTRA_LIVE_V1=0) ------------------------------------------------------------------------------------------------------

def test_on_the_legacy_turn_ask_works_the_same_way(rig, folder):
    client, world, chats, bus, services = rig
    services.settings = services.settings.model_copy(update={"ask_v1": True})
    services.connector_router = FakeRouter(folder, edit=True)
    sid = world.session_of["web"]
    services.chat_port = port = LegacyPort("It prints hello [src/app.py:4] and [gone.py:2].")
    r = say(client, sid, mode="ask")
    assert r.status_code == 202 and set(r.json()) == {"message_id", "turn"}
    assert wait_for(lambda: len(chats.messages(sid)) == 3 and sid not in __import__("sutra_app.orchestrator.api.chat_v2", fromlist=["_running"])._running)
    assert port.turns[0].tag.workspace == "read" and port.systems[0].endswith(ASK_RULES)
    card = chats.messages(sid)[2]
    assert card.kind == "card" and [s["label"] for s in card_of(card)["sources"]] == [GOOD, BAD]


def test_on_the_legacy_turn_a_chat_without_a_mode_is_unchanged(rig, folder):
    client, world, chats, bus, services = rig
    services.settings = services.settings.model_copy(update={"ask_v1": True})
    services.connector_router = FakeRouter(folder, edit=True)
    sid = world.session_of["web"]
    services.chat_port = port = LegacyPort("plain [src/app.py:4]")
    assert say(client, sid).status_code == 202
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and not direct_running.answering(sid))
    assert port.turns[0].tag.workspace == "none" and ASK_RULES not in port.systems[0] and [m.kind for m in chats.messages(sid)] == ["text", "text"]


def test_a_mode_taken_out_of_the_body_does_not_change_a_body_without_one(ask):
    """The route class reads the body only to look for `mode`: a body without it reaches the model exactly as sent (also with attachments and a client id)."""
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), text("ok"))
    assert say(client, sid, "plain words", client_id="client-aaaa1111").status_code == 202 and finish(chats, sid, 2)
    assert chats.messages(sid)[0].text == "plain words" and chats.messages(sid)[0].client_id == "client-aaaa1111"


# ---- a body nobody can encode or parse must not be a 500, and must not be heard before the token (review m1) --------------------------------------------------------------------

def raw(client, path, body, token=True):
    return client.post(path, content=body, headers={"Content-Type": "application/json", **(H if token else {})})


@pytest.mark.parametrize("route, body", [
    ("direct", b'{"text": "x\\ud800", "mode": "ask"}'),
    ("direct", b'{"mode": "ask", "text": "\\udfff and \\ud83d"}'),
    ("direct/retry", b'{"message_id": 1, "mode": "ask", "client_id": "client-\\ud800"}'),
])
def test_on_a_lone_surrogate_in_a_body_that_names_mode_is_a_clean_refusal_and_the_token_is_asked_for_first(ask, route, body):
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), text("x"))
    nobody = raw(client, f"/api/chats/{sid}/{route}", body, token=False)
    assert nobody.status_code == 401 and nobody.json()["error"]["code"] == "bad_token"            # it was a 500 before the fix
    someone = raw(client, f"/api/chats/{sid}/{route}", body)
    assert someone.status_code == 422, someone.text
    assert chats.messages(sid) == [] and services.chat_port.streams == []


@pytest.mark.parametrize("body", [b"[" * 200_000, b'{"mode": ' + b"[" * 100_000 + b"}", b"\xff\xfe not json", b'{"text": "x", "mode": "ask"'])
def test_a_body_that_is_not_json_is_refused_the_same_with_the_flag_on_and_off(live, body):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    results = {}
    for flag in (False, True):
        services.settings = services.settings.model_copy(update={"ask_v1": flag})
        results[flag] = [(r.status_code, r.json()) for r in (raw(client, f"/api/chats/{sid}/direct", body), raw(client, f"/api/chats/{sid}/direct", body, token=False))]
    assert results[False] == results[True] and all(code < 500 for code, _ in results[True])
    assert chats.messages(sid) == []


def test_on_a_lone_surrogate_in_the_text_is_refused_like_with_the_flag_off(live):
    client, world, chats, bus, services = live
    sid = world.session_of["web"]
    body = b'{"text": "x\\ud800"}'
    off = raw(client, f"/api/chats/{sid}/direct", body)
    services.settings = services.settings.model_copy(update={"ask_v1": True})
    on_plain = raw(client, f"/api/chats/{sid}/direct", body)
    on_mode = raw(client, f"/api/chats/{sid}/direct", b'{"text": "x\\ud800", "mode": "ask"}')
    assert off.status_code == on_plain.status_code == on_mode.status_code == 422 and off.json() == on_plain.json() == on_mode.json()


# ---- the document the chat routes publish is the one that was published before DV-1, byte for byte (review m2) ----------------------------------------------------------------

def test_the_openapi_document_of_the_chat_routes_is_byte_for_byte_what_it_was_before_ask():
    """`tests/fixtures/openapi/chat_routes_before_ask.json` was written from the code of the commit before DV-1 (22bbbf0a) with the same few lines as below. The flag is off (the
    default): the two direct routes are registered in the old place with the same request models, so the paths come in the same order and no `mode` or card appears."""
    import warnings
    from pathlib import Path

    from fastapi import FastAPI

    from sutra_app.orchestrator.api import chat as chat_api
    from sutra_app.orchestrator.api import chat_v2 as chat_v2_api
    app = FastAPI()
    for module in (chat_v2_api, chat_api):
        app.include_router(module.build_router())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        now = json.dumps(app.openapi(), indent=1) + "\n"
    before = (Path(__file__).resolve().parents[1] / "fixtures" / "openapi" / "chat_routes_before_ask.json").read_text(encoding="utf-8")
    assert now == before
    assert '"mode"' not in now and "AnswerCard" not in now and "answer_sources" not in now


def test_the_ask_setup_reads_the_folder_off_the_event_loop(ask, monkeypatch):
    """Review m8: `ask_mode.begin` reads a setting file; on the loop it would stall every other request. It runs in the worker pool, for a send and for a retry."""
    import threading
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    seen = {}
    real_begin, real_turn = ask_mode.begin, direct_running.begin_turn

    def begin(*a, **k):
        seen.setdefault("begin", []).append(threading.get_ident())
        return real_begin(*a, **k)

    def begin_turn(*a, **k):
        seen.setdefault("loop", []).append(threading.get_ident())                   # called on the event loop's own thread
        return real_turn(*a, **k)
    monkeypatch.setattr(ask_mode, "begin", begin)
    monkeypatch.setattr(direct_running, "begin_turn", begin_turn)
    services.chat_port = Port(started(), CrashedError("died"))
    line = say(client, sid, mode="ask").json()["message_id"]
    assert finish(chats, sid, 2)
    services.chat_port = Port(started(), text("ok [src/app.py:1]"))
    assert client.post(f"/api/chats/{sid}/direct/retry", json={"message_id": line}, headers=H).status_code == 202 and finish(chats, sid, 4)
    assert len(seen["begin"]) == 2 and len(seen["loop"]) == 2
    assert set(seen["begin"]).isdisjoint(seen["loop"])


def test_an_ask_stopped_by_its_own_limit_says_so_in_plain_words_and_a_plain_chat_keeps_the_connectors_words(ask):
    """Review m7: "the envelope allows no more calls, money or time" is a developer's sentence and must not reach the owner from the chat box."""
    from sutra_app.connectors.errors import EnvelopeExceededError
    client, world, chats, bus, services = ask
    sid = world.session_of["web"]
    services.chat_port = Port(started(), EnvelopeExceededError("limit", detail={"limit": "max_usd"}))
    assert say(client, sid, mode="ask").status_code == 202 and finish(chats, sid, 2)
    error = chats.messages(sid)[1]
    assert error.kind == "error" and error.text == ask_mode.LIMIT_WORDS
    assert "envelope" not in error.text and "$0.25" in error.text and "2 minutes" in error.text
    services.chat_port = Port(started(), EnvelopeExceededError("limit", detail={"limit": "max_usd"}))
    assert say(client, sid, "plain").status_code == 202 and finish(chats, sid, 4)
    assert chats.messages(sid)[3].text == "the envelope allows no more calls, money or time"        # the chat as it was


def test_no_reason_on_a_card_uses_a_developers_word():
    from sutra_app.orchestrator import citations as c
    reasons = set()
    for path in ("", "a\\b", "C:x", "//h/s", "~x", "..", "src/../x", "con", "x ", "a*b", "x" * 400, "/etc/passwd"):
        reasons.add(c.check_mark(c.Mark(path or "p", 1, 1), "/some/folder").reason)
    reasons.add(c.check_mark(c.Mark("a.py", 1, 900), "/some/folder").reason)
    reasons.add(c.check_mark(c.Mark("a.py", 0, 1), "/some/folder").reason)
    for reason in reasons:
        assert reason and len(reason) <= 70 and not any(w in reason for w in ("envelope", "realpath", "spelling", "regex", "device name", "path inside the folder (use"))
