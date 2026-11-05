"""HealthBook (CN-6, connectors 3.6 "Health and quota before a call"): TTLs, cooldowns, quota, breaker, recovery."""
from __future__ import annotations

import pytest

from sutra_app.connectors.errors import (
    CliMissingError, CrashedError, FlagUnsupportedError, NotSignedInError, OverloadedError, ProviderError, QuotaError,
    RateLimitedError, ServerError,
)
from sutra_app.connectors.health import API_KEY_REFUSED, HealthBook
from sutra_app.connectors.models import AuthStatus, Quota

T0 = 1_000_000.0


class Clock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Probe:
    """A counted probe: how often the book really asked."""

    def __init__(self, value):
        self.value, self.calls = value, 0

    def __call__(self):
        self.calls += 1
        return self.value


def auth(provider="claude", signed_in=True, billing="subscription"):
    return AuthStatus(provider=provider, installed=True, signed_in=signed_in, billing=billing, checked_at=T0)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def book(clock):
    return HealthBook(clock=clock)


# ---- TTL caches ---------------------------------------------------------------------------------------------------------
def test_installed_is_cached_for_60_seconds(book, clock):
    probe = Probe(True)
    assert book.installed("claude", probe) is True and book.installed("claude", probe) is True
    assert probe.calls == 1
    clock.advance(59.9)
    book.installed("claude", probe)
    assert probe.calls == 1
    clock.advance(0.2)
    book.installed("claude", probe)
    assert probe.calls == 2


def test_auth_is_cached_for_30_seconds_and_refresh_forces(book, clock):
    probe = Probe(auth())
    book.auth("claude", probe)
    clock.advance(29.9)
    book.auth("claude", probe)
    assert probe.calls == 1
    assert book.peek_auth("claude") is probe.value
    book.auth("claude", probe, refresh=True)
    assert probe.calls == 2
    clock.advance(30.0)
    assert book.peek_auth("claude") is None                                    # stale: peek never probes
    book.auth("claude", probe)
    assert probe.calls == 3


def test_caches_are_per_provider(book):
    claude, codex = Probe(True), Probe(False)
    assert book.installed("claude", claude) and not book.installed("codex", codex)


def test_not_signed_in_error_drops_the_auth_cache(book):
    probe = Probe(auth(signed_in=True))
    book.auth("claude", probe)
    assert book.failed("claude", NotSignedInError(provider="claude")) is None
    book.auth("claude", probe)
    assert probe.calls == 2                                                    # asked again at once, not after 30 s


def test_cli_missing_error_marks_it_not_installed_at_once(book):
    probe = Probe(True)
    book.installed("claude", probe)
    book.failed("claude", CliMissingError(provider="claude"))
    assert book.installed("claude", probe) is False and probe.calls == 1
    book.forget_installed("claude")
    assert book.installed("claude", probe) is True


# ---- cooldowns, one test per error ----------------------------------------------------------------------------------------
def test_rate_limited_cools_down_60_seconds(book, clock):
    cd = book.failed("claude", RateLimitedError(provider="claude"))
    assert cd.kind == "rate_limited" and cd.until == T0 + 60
    clock.advance(59)
    assert book.cooldown("claude") is not None
    clock.advance(1)
    assert book.cooldown("claude") is None


def test_overloaded_cools_down_30_seconds(book):
    assert book.failed("codex", OverloadedError(provider="codex")).until == T0 + 30


def test_flag_error_cools_down_10_minutes(book):
    assert book.failed("claude", FlagUnsupportedError(provider="claude")).until == T0 + 600


def test_quota_cools_down_until_resets_at(book):
    cd = book.failed("claude", QuotaError(provider="claude", resets_at=T0 + 5000))
    assert (cd.kind, cd.until) == ("quota", T0 + 5000)


def test_quota_without_reset_time_uses_15_minutes_for_claude_and_30_for_codex(book):
    assert book.failed("claude", QuotaError(provider="claude")).until == T0 + 15 * 60
    assert book.failed("codex", QuotaError(provider="codex")).until == T0 + 30 * 60


def test_quota_with_a_reset_time_in_the_past_falls_back_to_the_default(book):
    assert book.failed("claude", QuotaError(provider="claude", resets_at=T0 - 5)).until == T0 + 15 * 60


def test_other_errors_set_no_cooldown(book):
    for err in (ServerError(provider="claude"), ProviderError(provider="claude")):
        assert book.failed("claude", err) is None
    assert book.cooldown("claude") is None


def test_a_shorter_block_never_shortens_a_longer_one_of_the_same_kind(book):
    book.failed("claude", QuotaError(provider="claude", resets_at=T0 + 5000))
    book.failed("claude", QuotaError(provider="claude", resets_at=T0 + 100))
    assert book.cooldown("claude").until == T0 + 5000


def test_cooldown_reports_the_block_that_ends_last(book):
    book.failed("claude", RateLimitedError(provider="claude"))
    book.failed("claude", FlagUnsupportedError(provider="claude"))
    assert book.cooldown("claude").kind == "flag"


def test_cooldown_of_one_provider_leaves_the_other_free(book):
    book.failed("claude", RateLimitedError(provider="claude"))
    assert book.cooldown("codex") is None


# ---- quota snapshots ----------------------------------------------------------------------------------------------------
def test_rejected_quota_skips_until_resets_at(book, clock):
    book.set_quota("claude", Quota(status="exhausted", window="five_hour", resets_at=T0 + 3600, source="rate_limit_event"))
    assert book.cooldown("claude").until == T0 + 3600
    clock.advance(3599)
    assert book.cooldown("claude") is not None
    clock.advance(2)
    assert book.cooldown("claude") is None                                     # back after the reset time


def test_exhausted_quota_without_a_reset_time_blocks_for_the_default_from_when_seen(book, clock):
    book.set_quota("codex", Quota(status="exhausted", source="rollout"))
    clock.advance(30 * 60 - 1)
    assert book.cooldown("codex") is not None
    clock.advance(2)
    assert book.cooldown("codex") is None


def test_a_later_ok_snapshot_lifts_a_quota_block(book):
    book.failed("claude", QuotaError(provider="claude", resets_at=T0 + 5000))
    book.set_quota("claude", Quota(status="warning", used=0.9, source="rate_limit_event"))
    assert book.cooldown("claude") is None
    assert book.quota("claude").status == "warning"


def test_a_snapshot_does_not_lift_other_blocks(book):
    book.failed("claude", RateLimitedError(provider="claude"))
    book.set_quota("claude", Quota(status="ok", source="rate_limit_event"))
    assert book.cooldown("claude").kind == "rate_limited"


def test_quota_snapshot_is_kept_per_provider(book):
    assert book.quota("claude") is None
    book.set_quota("claude", Quota(status="ok", used=0.1, window="five_hour", source="rate_limit_event"))
    assert book.quota("claude").used == 0.1 and book.quota("codex") is None


# ---- breaker -------------------------------------------------------------------------------------------------------------
def test_three_crashes_within_a_minute_open_the_breaker_for_a_minute(book, clock):
    assert book.failed("claude", CrashedError(provider="claude")) is None
    clock.advance(20)
    assert book.failed("claude", CrashedError(provider="claude")) is None
    clock.advance(20)
    cd = book.failed("claude", CrashedError(provider="claude"))
    assert (cd.kind, cd.until) == ("breaker", clock.now + 60)
    assert book.state("claude").state == "breaker"
    clock.advance(60)
    assert book.cooldown("claude") is None and book.state("claude").state == "ok"


def test_crashes_older_than_a_minute_do_not_count(book, clock):
    book.failed("claude", CrashedError(provider="claude"))
    book.failed("claude", CrashedError(provider="claude"))
    clock.advance(61)
    assert book.failed("claude", CrashedError(provider="claude")) is None
    assert book.cooldown("claude") is None


def test_a_success_forgets_the_crash_history(book):
    book.failed("claude", CrashedError(provider="claude"))
    book.failed("claude", CrashedError(provider="claude"))
    book.ok("claude")
    assert book.failed("claude", CrashedError(provider="claude")) is None


# ---- recovery and update -------------------------------------------------------------------------------------------------
def test_ok_lifts_cooldowns_and_an_exhausted_snapshot(book):
    book.failed("claude", RateLimitedError(provider="claude"))
    book.set_quota("claude", Quota(status="exhausted", resets_at=T0 + 9999, source="rate_limit_event"))
    book.ok("claude")
    assert book.cooldown("claude") is None and book.quota("claude") is None


def test_update_applies_the_outcome_and_then_the_snapshot_that_came_with_it(book):
    book.failed("claude", RateLimitedError(provider="claude"))
    book.update("claude", quota=Quota(status="ok", source="rate_limit_event"))                 # success clears, snapshot kept
    assert book.cooldown("claude") is None and book.quota("claude").status == "ok"
    book.update("claude", quota=Quota(status="exhausted", resets_at=T0 + 700, source="rate_limit_event"))
    assert book.cooldown("claude").until == T0 + 700                                              # a success that used up the quota
    book.update("codex", error=OverloadedError(provider="codex"))
    assert book.cooldown("codex").kind == "overloaded"


# ---- state and skip_reason -----------------------------------------------------------------------------------------------
def test_state_names(book, clock):
    assert book.state("claude").state == "ok"                                  # never probed: ok
    book.failed("claude", RateLimitedError(provider="claude"))
    got = book.state("claude")
    assert (got.state, got.until, got.reason) == ("cooldown", T0 + 60, "rate limited")
    book.failed("codex", QuotaError(provider="codex", resets_at=T0 + 99))
    assert book.state("codex").state == "quota"
    book.installed("stub", Probe(False))
    assert book.state("stub").state == "missing"
    book.auth("claude", Probe(auth(signed_in=False)))
    book.ok("claude")
    assert book.state("claude").state == "signed_out"
    clock.advance(31)
    assert book.state("claude").state == "ok"                                  # a stale answer is not trusted
    assert set(book.snapshot()) == {"claude", "codex", "stub"}


def test_skip_reason_none_when_everything_is_fine(book):
    assert book.skip_reason("claude", installed_probe=Probe(True), auth_probe=Probe(auth())) is None


def test_skip_reason_not_installed_stops_before_asking_for_auth(book):
    a = Probe(auth())
    assert book.skip_reason("codex", installed_probe=Probe(False), auth_probe=a) == "Codex CLI is not installed"
    assert a.calls == 0


def test_skip_reason_signed_out_but_unknown_is_allowed(book):
    assert book.skip_reason("claude", installed_probe=Probe(True), auth_probe=Probe(auth(signed_in=False))) == "Claude is not signed in"
    assert book.skip_reason("codex", installed_probe=Probe(True), auth_probe=Probe(auth("codex", signed_in=None))) is None


def test_api_key_login_is_refused_with_no_override_but_unknown_billing_passes(book):
    got = book.skip_reason("codex", installed_probe=Probe(True), auth_probe=Probe(auth("codex", billing="api_key")))
    assert got == API_KEY_REFUSED == "API-key login refused (D7): sign in with your subscription"
    assert book.skip_reason("claude", installed_probe=Probe(True), auth_probe=Probe(auth(billing="unknown"))) is None


def test_skip_reason_names_the_block_and_clears_after_it(book, clock):
    book.failed("claude", QuotaError(provider="claude", resets_at=T0 + 120))
    reason = book.skip_reason("claude", installed_probe=Probe(True), auth_probe=Probe(auth()))
    assert reason.startswith("usage limit reached, retry after ")
    clock.advance(121)
    assert book.skip_reason("claude", installed_probe=Probe(True), auth_probe=Probe(auth())) is None


def test_skip_reason_without_an_auth_probe_checks_installed_and_blocks_only(book):
    assert book.skip_reason("claude", installed_probe=Probe(True)) is None
    book.failed("claude", OverloadedError(provider="claude"))
    assert "overloaded" in book.skip_reason("claude", installed_probe=Probe(True))
