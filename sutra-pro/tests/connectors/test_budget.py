"""Per-model window budget for the carry-over (work package ABS-3; the old app's test_budget cases re-expressed)."""
from __future__ import annotations

import pytest

from sutra_app.connectors import budget
from sutra_app.connectors.models import Message
from sutra_app.connectors.transcript import DIGEST_CAP_CHARS, FULL_CHARS, render_carry_over


def test_haiku_is_not_given_its_siblings_window():
    assert budget.window_for("claude", "haiku")["tokens"] == 200_000 < budget.window_for("claude", "sonnet")["tokens"]


def test_haiku_budget_is_five_times_smaller():
    assert budget.for_target("claude", "sonnet")["budget_chars"] > 4 * budget.for_target("claude", "haiku")["budget_chars"]


def test_unknown_model_assumes_the_floor_and_says_so():
    w = budget.window_for("claude", "")
    assert w["source"] == "assumed-floor" and w["tokens"] == budget.FLOOR_WINDOW
    assert budget.window_for("claude", "some-new-model")["source"] == "assumed-floor"
    assert budget.window_for("nobody", "x")["source"] == "assumed-floor"


def test_codex_uses_what_it_enforces_not_the_floor():
    w = budget.window_for("codex", "")
    assert (w["tokens"], w["source"]) == (258_400, "provider-default")


def test_floor_is_the_smallest_declared_window():
    assert budget.FLOOR_WINDOW == min(w for t in budget.WINDOWS.values() for w in t.values())


def test_reply_room_is_reserved_and_usable_is_discounted():
    info = budget.for_target("claude", "sonnet")
    assert info["usable_tokens"] == int((1_000_000 - budget.REPLY_RESERVE_TOKENS) * budget.USABLE_FRACTION)
    assert info["estimate"] is True and info["chars_per_token"] == 3.0


def test_token_estimate_is_conservative_and_rounds_up():
    assert budget.estimate_tokens(3) == 1 and budget.estimate_tokens(4) == 2 and budget.estimate_tokens(0) == 0


def test_fits_reports_both_ways():
    assert budget.fits(1000, "claude", "sonnet") and not budget.fits(10_000_000, "claude", "haiku")


@pytest.mark.parametrize("target,model", [(t, m) for t, ms in budget.WINDOWS.items() for m in [*ms, "", "unknown"]] + [("codex", "gpt-5.6")])
def test_the_carry_over_limits_never_exceed_the_j2_caps(target, model):
    c = budget.carry_chars(target, model)
    assert c["full_chars"] <= FULL_CHARS and c["digest_cap"] <= DIGEST_CAP_CHARS


def msgs(n, size):
    return [Message(role="user" if i % 2 == 0 else "assistant", text=("m%d " % i) + "x" * size) for i in range(n)]


def test_no_budget_is_exactly_j2():
    m = msgs(60, 2000)
    assert render_carry_over(m, from_provider="claude", to_provider="codex") == render_carry_over(m, from_provider="claude", to_provider="codex", budget=None)


def test_a_big_budget_never_enlarges_the_carry_over():
    m = msgs(60, 2000)
    assert render_carry_over(m, budget=10**9) == render_carry_over(m)


def test_a_small_budget_shrinks_a_whole_chat_to_the_digest_tier():
    m = msgs(50, 800)                                      # about 41,000 characters: whole under J2's rule
    assert "Shortened earlier messages" not in render_carry_over(m)
    small = render_carry_over(m, budget=20_000)
    assert "Shortened earlier messages" in small and "[10 earlier messages omitted]" in small
    assert len(small) < len(render_carry_over(m))
