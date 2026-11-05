"""render_carry_over: the block a new provider session starts with (connectors design 3.6, work package CN-7)."""
from __future__ import annotations

from sutra_app.connectors.models import Message
from sutra_app.connectors.transcript import (
    DIGEST_CAP_CHARS, DIGEST_LINE_CHARS, FULL_CHARS, TAIL_MESSAGES, render_carry_over,
)


def conversation(n, size=10):
    return [Message(role="user" if i % 2 == 0 else "assistant", text=f"m{i} " + "x" * size) for i in range(n)]


def test_constants_are_j2s_numbers():
    assert (FULL_CHARS, TAIL_MESSAGES, DIGEST_LINE_CHARS, DIGEST_CAP_CHARS) == (60_000, 40, 120, 8_000)


def test_empty_conversation_carries_nothing():
    assert render_carry_over([]) == ""


def test_under_the_limit_every_message_is_whole_and_in_order():
    msgs = [Message(role="user", text="hello"), Message(role="assistant", text="hi there"), Message(role="system", text="note")]
    text = render_carry_over(msgs, from_provider="claude", to_provider="codex")
    lines = text.split("\n\n", 1)[1].split("\n")
    assert lines == ["User: hello", "Assistant: hi there", "System: note"]
    assert "omitted" not in text


def test_header_names_both_providers():
    text = render_carry_over(conversation(2), from_provider="claude", to_provider="codex")
    assert text.startswith("Earlier messages of this conversation, carried over because the provider changed (claude → codex):")


def test_header_for_a_lost_session_on_the_same_provider():
    text = render_carry_over(conversation(2), from_provider="claude", to_provider="claude")
    assert "because the provider session was lost (claude)" in text.splitlines()[0]


def test_header_without_provider_names():
    assert render_carry_over(conversation(1)).startswith("Earlier messages of this conversation, carried over because the provider changed:")


def test_over_the_limit_keeps_the_last_forty_whole_and_shortens_the_rest():
    msgs = conversation(60, size=2000)                     # 60 x ~2000 characters is over 60,000
    text = render_carry_over(msgs, from_provider="claude", to_provider="codex")
    assert "[20 earlier messages omitted]" in text.splitlines()[0]
    digest, recent = text.split("Shortened earlier messages:\n")[1].split("\n\nRecent messages in full:\n")
    short = digest.split("\n")
    assert len(short) == 20 and all(len(line) <= DIGEST_LINE_CHARS for line in short)
    assert short[0].startswith("User: m0 xxx") and short[0].endswith("…")
    full = recent.split("\n")
    assert len(full) == 40 and full[0].startswith("User: m20 ") and len(full[0]) > 1500 and full[-1].startswith("Assistant: m59 ")
    assert "m19 " in digest and "m20 " not in digest        # the split is exactly after the 20th


def test_a_short_older_message_is_not_cut():
    msgs = [Message(role="user", text="small")] + conversation(45, size=2000)
    digest = render_carry_over(msgs).split("Shortened earlier messages:\n")[1].split("\n\n")[0]
    assert digest.split("\n")[0] == "User: small"


def test_one_omitted_message_is_singular():
    msgs = conversation(41, size=2000)
    assert "[1 earlier message omitted]" in render_carry_over(msgs, full_chars=100).splitlines()[0]


def test_whitespace_in_an_older_message_collapses_to_one_line():
    msgs = [Message(role="assistant", text="a\n\nb\tc")] + conversation(41, size=2000)
    digest = render_carry_over(msgs, full_chars=100).split("Shortened earlier messages:\n")[1]
    assert digest.split("\n")[0] == "Assistant: a b c"


def test_digest_is_capped_and_says_how_many_are_not_listed():
    msgs = conversation(500, size=300)
    text = render_carry_over(msgs, digest_cap=1000)
    digest = text.split("Shortened earlier messages:\n")[1].split("\n\nRecent messages in full:\n")[0]
    lines = digest.split("\n")
    assert sum(len(line) + 1 for line in lines[:-1]) <= 1000
    listed = len(lines) - 1
    assert lines[-1] == f"[{460 - listed} more not listed]"
    assert "[460 earlier messages omitted]" in text.splitlines()[0]


def test_many_small_messages_under_the_character_limit_stay_whole():
    msgs = conversation(200, size=5)                       # more than 40 messages, but far under 60,000 characters
    text = render_carry_over(msgs)
    assert "omitted" not in text and text.count("\n") >= 200


def test_oversize_but_not_more_than_the_tail_is_whole():
    msgs = conversation(10, size=20_000)
    text = render_carry_over(msgs)
    assert "Shortened" not in text and text.count("m9 ") == 1


def test_same_input_same_output():
    msgs = conversation(70, size=1500)
    assert render_carry_over(msgs, from_provider="a", to_provider="b") == render_carry_over(list(msgs), from_provider="a", to_provider="b")
