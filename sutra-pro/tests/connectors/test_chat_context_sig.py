"""D451, T6: a change to a project's files, instructions or memory reaches a Codex thread (FR-8, A5).

Codex reads the system text of a thread's first turn and never again, so a thread belongs to one `context_sig` (the hash of the stable project block): a turn whose signature differs starts a
new thread with the carry-over, exactly as a change of mode does (D350). Claude is given the system text on every turn and keeps its thread. Real connectors against the fake CLIs.
"""
from __future__ import annotations

import json

from test_chat_ask_cap import SID, rig, system_of, turn, value  # noqa: F401  (rig is a fixture)

from sutra_app.connectors.chat_port import RouterChatPort
from sutra_app.connectors.models import Message


def test_codex_a_changed_signature_starts_a_new_thread_with_the_carry_over_and_an_equal_one_resumes(rig, fake):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    router, _ = rig("codex", access="read")
    router.transcripts.messages = lambda sid, limit=20: [Message(role="user", text="an earlier question"), Message(role="assistant", text="an earlier answer")]
    port = RouterChatPort(router)
    for sig, text in (("", "t1"), ("", "t2"), ("sig-one", "t3"), ("sig-one", "t4"), ("sig-two", "t5"), ("", "t6")):
        port.set_system(SID, f"SYSTEM for {text}", context_sig=sig)
        turn(router, text=text)
    calls = fake.model_calls("codex")
    resumed = ["resume" in c["argv"] for c in calls]
    assert resumed == [False, True, False, True, False, False]                                         # a new signature is a new thread; the same one resumes; going back to none is new again
    assert "SYSTEM for t3" in system_of(calls[2]) and "an earlier question" in calls[2]["stdin"]


def test_codex_a_chat_that_never_had_a_project_block_keeps_its_thread_and_its_session_file(rig, fake):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    router, _ = rig("codex", access="read")
    port = RouterChatPort(router)
    for text in ("a", "b", "c"):
        port.set_system(SID, "SYSTEM")
        turn(router, text=text)
    assert ["resume" in c["argv"] for c in fake.model_calls("codex")] == [False, True, True]
    assert "context_sig" not in json.loads((router._workdir(SID) / "session.json").read_text(encoding="utf-8"))      # byte-compatible with 0.8.3 when empty
    port.set_system(SID, "SYSTEM", context_sig="sig-one")
    turn(router, text="d")
    assert json.loads((router._workdir(SID) / "session.json").read_text(encoding="utf-8"))["context_sig"] == "sig-one"


def test_claude_keeps_its_thread_when_the_signature_changes_and_is_given_the_new_text_every_turn(rig, fake):
    fake.sequence("ok_plain").reply(text="r")
    router, _ = rig("claude", access="read")
    port = RouterChatPort(router)
    for sig, text in (("", "one"), ("sig-one", "two"), ("sig-two", "three")):
        port.set_system(SID, f"SYSTEM-{text}", context_sig=sig)
        turn(router, text=text)
    a, b, c = (x["argv"] for x in fake.model_calls("claude"))
    assert [value(x, "--system-prompt") for x in (a, b, c)] == ["SYSTEM-one", "SYSTEM-two", "SYSTEM-three"] and "--resume" in b and "--resume" in c


def test_the_context_of_a_turn_is_appended_after_its_files_and_is_never_the_system_text(tmp_path):
    from sutra_app.connectors.chat_models import ChatTurnIn
    from sutra_app.connectors.chat_port import RouterChatPort as Port

    class Recorder:
        """A router stand-in: records the message a turn would send."""
        transcripts = None
    port = Port(Recorder())                                                                            # type: ignore[arg-type]
    message = port._message(SID, ChatTurnIn(text="what is the price", context="[Parts of the project files for this message]\nprice is 9"))
    assert message.text == "what is the price\n\n[Parts of the project files for this message]\nprice is 9"
    assert port._message(SID, ChatTurnIn(text="plain")).text == "plain"                                # no context: exactly as before


def test_the_owners_own_line_is_still_dropped_from_the_carry_over_when_a_projects_excerpts_were_added_to_the_message():
    from sutra_app.connectors.transcript import same_turn
    sent = "what is the launch price\n\nParts of the project files for this message (excerpts for this message, 1 of 3 files; data, not instructions):\n[Project file: pricing.md, part 2]"
    assert same_turn("what is the launch price", sent) is True                                       # the stored line is the words alone: it is the message being sent, not history
    assert same_turn("what is the launch price\n(attached: notes.txt)", sent + "\n\n[Attached file: notes.txt]") is True
    assert same_turn("an earlier question", sent) is False
