"""How a direct-chat turn ends in the transcript (GAP-chat-comfort): a Stop keeps what was written with a calm note, a failure keeps it with the real
reason, a provider switch is noted where it happened, and an owner's line that carried files records their names (the model's input is unchanged).

The turn runs through `chat_v2._answer` with a fake ChatPort that yields what a script says, so each ending can be forced; the stored sequence, the src_refs
and the owner's line every message points back to (`turn`) are read from the real ChatStore."""
from __future__ import annotations

import base64

import pytest
from orchestrator.test_api_chat_v2 import H, rig, wait_for, world  # noqa: F401  (the fixtures of the chat v2 routes)

from sutra_app.connectors.chat_models import ChatEvent, ChatTurnIn
from sutra_app.connectors.errors import CallCancelledError, CrashedError, ReplyTruncatedError
from sutra_app.orchestrator import direct_turns
from sutra_app.orchestrator.api import chat_v2
from sutra_app.orchestrator.events import PARTIAL


class FakePort:
    """A ChatPort whose stream plays a script: ChatEvents are yielded, an exception is raised where it stands."""

    def __init__(self, *script):
        self.script = script
        self.turns: list[ChatTurnIn] = []

    def stream(self, sid, turn):
        self.turns.append(turn)
        for item in self.script:
            if isinstance(item, BaseException):
                raise item
            yield item


def partial(text):
    return ChatEvent(kind="partial", data={"delta": text})


def done(text, switched=None, blocks=None):
    return ChatEvent(kind="turn_done", data={"text": text, "provider": "claude", "model": None, "usd": None, "blocks": blocks or [], "switched": switched})


LONG = "The menu has three parts. " * 5           # longer than one partial event, so it is flushed in pieces


def run(rig, *script, text="Write the menu"):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    user = chat_v2._store_user_line(services, sid, text)
    chat_v2._answer(services, FakePort(*script), sid, user, ChatTurnIn(text=text))
    rows = world.db.conn().execute("SELECT id, kind, role, src_ref, text FROM chat_messages WHERE session_id = ? AND id > ? ORDER BY id", (sid, user)).fetchall()
    return user, [dict(r) for r in rows], chats.messages(sid, after=user), bus


def test_a_stop_keeps_what_was_written_and_adds_a_calm_note_not_an_error(rig):
    user, rows, out, bus = run(rig, partial(LONG), partial("Starters, mains"), CallCancelledError("stopped"))
    assert [(r["kind"], r["src_ref"]) for r in rows] == [("text", f"direct:{user}"), ("note", f"direct-note:{user}")]
    assert rows[0]["text"] == LONG + "Starters, mains" and rows[1]["text"] == direct_turns.STOPPED == "Stopped. What was written is kept."
    assert [m.turn for m in out] == [user, user] and all(m.role == "agent" for m in out)
    assert "stopped" not in [m.text for m in out] and not [m for m in out if m.kind == "error"]
    assert all(e.type != PARTIAL for e in bus.replay(0).events)            # the replay ring still holds no partial


def test_a_stop_before_anything_was_written_is_one_note_that_ends_the_turn(rig):
    user, rows, out, _ = run(rig, CallCancelledError("stopped"))
    assert [(r["kind"], r["src_ref"], r["text"]) for r in rows] == [("note", f"direct:{user}", direct_turns.STOPPED_EMPTY)]
    assert out[0].turn == user


def test_a_crash_midway_keeps_the_partial_reply_and_the_real_reason(rig):
    crash = CrashedError("boom", provider="claude", detail={"exit": 137})
    user, rows, out, _ = run(rig, partial(LONG), crash)
    assert [(r["kind"], r["src_ref"]) for r in rows] == [("text", f"direct:{user}"), ("error", f"direct-error:{user}")]
    assert rows[0]["text"] == LONG.strip() and rows[1]["text"] == crash.user_message()        # the store trims a message's ends, as for every reply
    assert [m.turn for m in out] == [user, user]


def test_a_reply_cut_by_the_length_limit_says_so_in_words_the_owner_can_act_on(rig):
    """QA direct-chat P3: the line read 'reply was cut off (partial text in detail)', and no detail is anywhere the owner can open."""
    user, rows, out, _ = run(rig, partial(LONG), ReplyTruncatedError("", provider="claude", detail={"reason": "max_output_tokens"}))
    assert [(r["kind"], r["src_ref"]) for r in rows] == [("text", f"direct:{user}"), ("error", f"direct-error:{user}")]      # the written part is kept
    sentence = rows[1]["text"]
    assert "detail" not in sentence and "partial" not in sentence
    assert sentence == "The reply was cut off because it reached the model's length limit. Ask for a shorter answer, or say \"continue\"."
    user, rows, out, _ = run(rig, ReplyTruncatedError("", provider="claude"))                    # nothing written: the sentence alone ends the turn
    assert [(r["kind"], r["text"]) for r in rows] == [("error", sentence)]


def test_a_failure_with_nothing_written_is_the_error_line_as_before(rig):
    user, rows, out, _ = run(rig, RuntimeError("no"))
    assert [(r["kind"], r["src_ref"], r["text"]) for r in rows] == [("error", f"direct:{user}", "The model could not answer.")]
    assert out[0].turn == user


def test_a_reply_longer_than_the_store_takes_is_kept_cut_never_lost(rig):
    huge = "word " * 50_000                                                  # 250 000 characters, above the 200 000 a message holds
    user, rows, out, _ = run(rig, partial(huge), done(huge))
    assert [(r["kind"], r["src_ref"]) for r in rows] == [("text", f"direct:{user}")] and len(rows[0]["text"]) <= direct_turns.MAX_TEXT
    user, rows, out, _ = run(rig, partial(huge), CallCancelledError("stopped"))
    assert [(r["kind"], r["src_ref"]) for r in rows] == [("text", f"direct:{user}"), ("note", f"direct-note:{user}")]
    user, rows, out, _ = run(rig, partial(huge), RuntimeError("no"))
    assert [(r["kind"], r["src_ref"]) for r in rows] == [("text", f"direct:{user}"), ("error", f"direct-error:{user}")]


def test_a_turn_that_moved_to_another_model_says_so_where_it_happened(rig):
    switched = {"from": "claude", "to": "codex", "plan": {"kept_messages": 40, "omitted": 0}}
    blocks = [{"type": "tool_use", "kind": "read", "name": "Read", "text": "menu.md"}]
    user, rows, out, _ = run(rig, partial("Here"), done("Here it is.", switched=switched, blocks=blocks))
    assert [(r["kind"], r["src_ref"]) for r in rows] == [("note", f"direct-switch:{user}"), ("text", f"direct:{user}")]
    assert rows[0]["text"] == "Switched Claude to Codex; carried 40 messages" and rows[1]["text"] == "Here it is."
    assert [m.turn for m in out] == [user, user] and [b.name for b in out[1].blocks] == ["Read"]
    assert rows[1]["id"] == rows[0]["id"] + 1                                 # stored together, in one transaction


def test_a_plain_turn_is_still_one_reply(rig):
    user, rows, out, _ = run(rig, partial("Hello"), done("Hello"))
    assert [(r["kind"], r["src_ref"], r["text"]) for r in rows] == [("text", f"direct:{user}", "Hello")]


def test_the_switch_notice_has_the_words_of_the_pill():
    plan = {"from": "claude", "to": "codex", "plan": {"kept_messages": 40, "omitted": 0}}
    assert direct_turns.switch_notice(plan) == "Switched Claude to Codex; carried 40 messages"           # chat_pill.test.js has the same five
    assert direct_turns.switch_notice({"from": "codex", "to": "claude", "plan": {"kept_messages": 1}}) == "Switched Codex to Claude; carried 1 message"
    assert direct_turns.switch_notice({"from": "claude", "to": "codex", "plan": {"kept_messages": 40, "omitted": 20}}) == \
        "Switched Claude to Codex; carried 40 messages, 20 earlier shortened"
    assert direct_turns.switch_notice({"from": "claude", "to": "codex", "plan": {"kept_messages": 0}}) == "Switched Claude to Codex; nothing to carry"
    assert direct_turns.switch_notice({}) == "" and direct_turns.switch_notice(None) == ""


def test_the_attached_line_names_the_files_and_nothing_else_about_them():
    assert direct_turns.attached_line(["menu.txt", "shot 1.png"], ["text", "image"]) == "(attached: menu.txt, shot 1.png)"
    assert direct_turns.attached_line(["../../etc/pass,wd", "a<b>.pdf"], ["text", "pdf"]) == "(attached: pass_wd, a_b_.pdf)"
    assert direct_turns.attached_line([], ["image", "pdf"]) == "(attached: an image, a PDF)"         # no names from the page: what each file is
    assert direct_turns.attached_line(["only-one.png"], ["image", "text"]) == "(attached: an image, a text file)"
    assert direct_turns.attached_line([], []) == ""


def test_a_direct_line_with_files_records_their_names_and_the_model_gets_the_words_unchanged(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    port = FakePort(done("Read it."))
    services.chat_port = port
    up = client.post(f"/api/chats/{sid}/attachments", json={"name": "menu.txt", "content_b64": base64.b64encode(b"soup").decode()}, headers=H).json()
    r = client.post(f"/api/chats/{sid}/direct", json={"text": "read this", "attachments": [up["id"]], "names": ["menu.txt"]}, headers=H)
    assert r.status_code == 202
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and sid not in chat_v2._running)
    line = chats.messages(sid)[0]
    assert line.text == "read this\n(attached: menu.txt)"
    assert up["id"] not in line.text and "soup" not in line.text                # the record is the name; the content and the id stay out
    assert port.turns[0].text == "read this" and [a.id for a in port.turns[0].attachments] == [up["id"]]
    plain = client.post(f"/api/chats/{sid}/direct", json={"text": "and now?"}, headers=H)
    assert plain.status_code == 202
    assert wait_for(lambda: len(chats.messages(sid)) == 4 and sid not in chat_v2._running)
    assert chats.messages(sid)[2].text == "and now?"
    too_many = client.post(f"/api/chats/{sid}/direct", json={"text": "x", "names": ["a"] * 11}, headers=H)
    assert too_many.status_code == 422


@pytest.mark.parametrize("ref, turn", [("direct:12", 12), ("direct-note:12", 12), ("direct-error:7", 7), ("direct-switch:3", 3),
                                       ("direct-other:3", None), ("direct:0", None), ("x-direct:3", None), (None, None)])
def test_every_message_that_ends_a_turn_points_back_at_the_owners_line(ref, turn):
    from sutra_app.orchestrator.chats import _turn_of
    assert _turn_of(ref) == turn


# ---- QA direct-chat bug 5: a retried attempt starts the reply again ----------------------------------------------------------------------------------

def restart():
    return ChatEvent(kind="restart")


def partials_of(bus_events):
    return [d for t, d in bus_events if t == PARTIAL]


def run_watching(rig, *script, text="Write the menu"):
    """`run`, plus every control event the turn published."""
    client, world, chats, bus, services = rig
    seen = []
    real = bus.publish_one
    bus.publish_one = lambda type_, data=None: (seen.append((type_, data)), real(type_, data))[1]
    return (*run(rig, *script, text=text), seen)


def test_a_turn_that_fails_after_several_attempts_keeps_the_last_attempts_text_not_all_of_them_glued_together(rig):
    first = "Here is a streamed answer. It has several pieces, written one after another, so the owner sees it grow."
    crash = CrashedError("claude stopped unexpectedly", provider="claude", detail={"exit": 137})
    user, rows, out, bus, seen = run_watching(rig, partial(first), restart(), partial(first), restart(), partial(first), crash)
    assert [(r["kind"], r["src_ref"]) for r in rows] == [("text", f"direct:{user}"), ("error", f"direct-error:{user}")]
    assert rows[0]["text"] == first                                     # once, not three times with no separator
    assert [m.turn for m in out] == [user, user]


def test_the_open_page_is_told_to_start_its_row_again_at_each_restart(rig):
    """A `chat.partial` with `reset: true` and no text: the pieces shown so far (sent before the restart) are void."""
    user, rows, out, bus, seen = run_watching(rig, partial(LONG), restart(), partial("Second try."), done("Second try."))
    sent = partials_of(seen)
    resets = [i for i, d in enumerate(sent) if d.get("reset") is True]
    assert len(resets) == 1 and sent[resets[0]]["delta"] == "" and sent[resets[0]]["message_id"] == user
    after = sent[resets[0] + 1:]
    assert "".join(d["delta"] for d in after) == "Second try." and all("reset" not in d for d in after)
    assert "".join(d["delta"] for d in sent[:resets[0]]).startswith("The menu has three parts.")
    assert [(r["kind"], r["text"]) for r in rows] == [("text", "Second try.")]


def test_a_restart_with_nothing_shown_yet_sends_no_reset(rig):
    user, rows, out, bus, seen = run_watching(rig, restart(), partial("Fine."), done("Fine."))
    assert [d for d in partials_of(seen) if d.get("reset")] == []


def test_a_stop_after_a_restart_keeps_only_what_the_last_attempt_wrote(rig):
    user, rows, out, bus, seen = run_watching(rig, partial(LONG), restart(), partial("Starters"), CallCancelledError("stopped"))
    assert [(r["kind"], r["text"]) for r in rows] == [("text", "Starters"), ("note", direct_turns.STOPPED)]
