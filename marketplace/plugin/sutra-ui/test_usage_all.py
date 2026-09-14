"""test_usage_all.py -- GET /api/usage/all: one shape for three unrelated facts.

WHAT THIS PINS, in order of how much it would cost to get wrong:

  1. NO SECRET CROSSES THE BOUNDARY. The three underlying reads each hold a
     credential (an OAuth token, a ChatGPT session, an API key) and none of
     them may appear in this payload. There is a test that walks the whole
     serialised answer looking for one.
  2. Every failure is a STATE, never an exception and never a zero. A missing
     CLI, a signed-out account and a dead network are three different
     instructions to the client, and each has its own value.
  3. The plan label is CLEAN. `default_claude_max_20x` and `go` are internal
     ids; the screen shows "Max (20x)" and "Go".
  4. The existing routes are untouched.

EVERYTHING IS MOCKED. Nothing here reaches the operator's account, the network
or a subprocess -- the live shape was verified by hand once (see the report)
and re-verifying it in a unit test would mean spending the operator's quota on
every run.

Run: python -m pytest test_usage_all.py -q
"""
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import usage   # noqa: E402

CLAUDE_OK = {
    "available": True, "source": "cache", "fetched_at": 0.0,
    "limits": [
        {"label": "Session (5h)", "kind": "session", "group": "", "percent": 73.0,
         "severity": "normal", "active": True,
         "resets_at": "2026-09-14T13:20:00+00:00", "resets_epoch": 1789392000.0},
        {"label": "Weekly · all models", "kind": "weekly_all", "group": "",
         "percent": 16.0, "severity": "normal", "active": False,
         "resets_at": "2026-09-19T13:00:00+00:00", "resets_epoch": 1789822800.0},
    ],
    "extra_usage": None, "member_dashboard_available": False,
}

CODEX_PLAN = {
    "windows": [
        {"key": "primary", "used_percent": 42.0, "duration_mins": 300,
         "resets_at": 1790386506},
        {"key": "secondary", "used_percent": 7.5, "duration_mins": 10080,
         "resets_at": 1790900000},
    ],
    "plan_type": "go", "reached": None, "limit_id": "codex",
    "credits": None, "reset_credits": None,
}

DEEPSEEK_OK = {
    "available": True, "source": "live", "fetched_at": 0.0, "is_available": True,
    "balances": [{"currency": "USD", "total_balance": "1.87",
                  "granted_balance": "0.00", "topped_up_balance": "5.00"}],
}


class Scenario(unittest.TestCase):
    """Every probe replaced, so a run costs nothing and decides nothing."""

    def setUp(self):
        usage._reset_all_for_tests()
        self.stack = []

    def tearDown(self):
        for patcher in reversed(self.stack):
            patcher.stop()
        usage._reset_all_for_tests()

    def patch(self, target, **kw):
        p = mock.patch(target, **kw)
        p.start()
        self.stack.append(p)
        return p

    def run_with(self, bins=("claude", "codex", "deepseek"),
                 claude=None, codex_auth=None, codex_plan=None,
                 deepseek_auth=None, deepseek=None, profile=None):
        import providers
        self.patch("providers.provider_bin",
                   side_effect=lambda pid: ("/bin/%s" % pid) if pid in bins else None)
        self.patch("usage.snapshot", return_value=claude or CLAUDE_OK)
        self.patch("providers.codex_auth",
                   return_value=codex_auth or {"state": "chatgpt"})
        self.patch("codex_models.refresh_plan_if_stale",
                   return_value=CODEX_PLAN if codex_plan is None else codex_plan)
        self.patch("providers.deepseek_auth_state",
                   return_value=deepseek_auth
                   or {"signed_in": True, "mask": "sk-…abcd", "reason": None})
        self.patch("deepseek_usage.snapshot", return_value=deepseek or DEEPSEEK_OK)
        self.patch("claude_local.profile",
                   return_value=profile if profile is not None
                   else {"plan": "Claude Max (20x)", "email": "a@b.test"})
        self.patch("claude_local.account",
                   return_value={"email": "a@b.test", "display_name": "A"})
        del providers
        return {r["id"]: r for r in usage.all_providers()["providers"]}


class TheShape(Scenario):

    def test_every_provider_gets_exactly_one_row(self):
        rows = self.run_with()
        self.assertEqual(sorted(rows), ["claude", "codex", "deepseek", "gemini"])

    def test_every_row_has_every_key_present(self):
        """Present-and-null, never absent: the client reads row.plan on every
        row, and a key that exists only sometimes turns each read into a guard."""
        for row in self.run_with().values():
            self.assertEqual(sorted(row),
                             ["account", "balance", "error", "id", "name",
                              "plan", "state", "windows"])
            self.assertIsInstance(row["windows"], list)

    def test_every_state_is_one_of_the_five(self):
        for row in self.run_with().values():
            self.assertIn(row["state"],
                          ("ok", "not_installed", "signed_out", "unsupported",
                           "error"))

    def test_every_window_has_the_four_contract_fields(self):
        for row in self.run_with().values():
            for w in row["windows"]:
                for key in ("label", "percent", "resets_at", "kind"):
                    self.assertIn(key, w)


class TheHappyPath(Scenario):

    def test_claude_reports_its_windows_and_a_clean_plan(self):
        row = self.run_with()["claude"]
        self.assertEqual(row["state"], "ok")
        self.assertEqual(row["plan"], "Max (20x)",
                         "the product word is dropped -- the row is already "
                         "labelled Claude Code")
        self.assertEqual([w["label"] for w in row["windows"]],
                         ["Session (5h)", "Weekly · all models"])
        self.assertEqual(row["windows"][0]["percent"], 73.0)
        self.assertEqual(row["windows"][0]["kind"], "session")
        self.assertEqual(row["account"], "a@b.test")

    def test_codex_windows_are_labelled_from_their_duration(self):
        """Never hardcoded into the request: the measured account returns ONE
        43,200-minute window, so naming a duration in the protocol layer would
        have described it wrongly."""
        row = self.run_with()["codex"]
        self.assertEqual(row["state"], "ok")
        self.assertEqual(row["plan"], "Go")
        self.assertEqual([(w["label"], w["kind"]) for w in row["windows"]],
                         [("Session (5h)", "session"), ("Weekly", "weekly_all")])

    def test_a_codex_epoch_reset_becomes_an_iso_string(self):
        """Claude answers in ISO and codex in Unix seconds; the shared shape
        cannot carry both spellings under one name."""
        w = self.run_with()["codex"]["windows"][0]
        self.assertTrue(w["resets_at"].startswith("2026-"), w["resets_at"])
        self.assertEqual(w["resets_epoch"], 1790386506)

    def test_an_unknown_codex_duration_still_renders(self):
        plan = dict(CODEX_PLAN, windows=[
            {"key": "primary", "used_percent": 1.0, "duration_mins": 4320,
             "resets_at": None}])
        row = self.run_with(codex_plan=plan)["codex"]
        self.assertEqual(row["windows"][0]["label"], "3-day")

    def test_an_unknown_plan_type_is_titled_not_dropped(self):
        row = self.run_with(codex_plan=dict(CODEX_PLAN,
                                            plan_type="super_duper"))["codex"]
        self.assertEqual(row["plan"], "Super Duper")

    def test_deepseek_reports_a_balance_and_no_windows(self):
        """Measured: DeepSeek publishes no five-hour or weekly window, only a
        balance. An empty list is the fact, not a gap."""
        row = self.run_with()["deepseek"]
        self.assertEqual(row["state"], "ok")
        self.assertEqual(row["plan"], "Pay as you go")
        self.assertEqual(row["windows"], [])
        self.assertEqual(row["balance"]["amount"], "1.87")
        self.assertEqual(row["balance"]["currency"], "USD")

    def test_gemini_is_unsupported_not_an_error(self):
        row = self.run_with()["gemini"]
        self.assertEqual(row["state"], "unsupported")
        self.assertEqual(row["windows"], [])


class TheUnhappyPaths(Scenario):

    def test_a_missing_cli_is_not_installed(self):
        rows = self.run_with(bins=("claude",))
        self.assertEqual(rows["codex"]["state"], "not_installed")
        self.assertEqual(rows["claude"]["state"], "ok")

    def test_no_claude_credentials_reads_as_signed_out(self):
        """A sign-in state, not a failure -- the difference decides whether the
        client offers a sign-in button or an error."""
        row = self.run_with(claude={
            "available": False,
            "reason": "no Claude Code credentials on this machine",
            "limits": [], "extra_usage": None})["claude"]
        self.assertEqual(row["state"], "signed_out")

    def test_a_dead_network_is_an_error_with_the_reason(self):
        row = self.run_with(claude={
            "available": False,
            "reason": "could not reach the usage endpoint (URLError)",
            "limits": [], "extra_usage": None})["claude"]
        self.assertEqual(row["state"], "error")
        self.assertIn("could not reach", row["error"])
        self.assertEqual(row["windows"], [], "an error must show no figure")

    def test_a_logged_out_codex_is_signed_out(self):
        row = self.run_with(codex_auth={"state": "logged_out"})["codex"]
        self.assertEqual(row["state"], "signed_out")

    def test_a_codex_api_key_is_usable_with_no_allowance(self):
        """An API key has no plan, so it has no allowance to be a percentage
        of. ok with no windows says "usable, nothing metered", which is true."""
        row = self.run_with(codex_auth={"state": "api_key"})["codex"]
        self.assertEqual(row["state"], "ok")
        self.assertEqual(row["plan"], "Pay as you go")
        self.assertEqual(row["windows"], [])

    def test_an_unrecognised_codex_status_is_an_error_not_a_guess(self):
        row = self.run_with(codex_auth={"state": "unknown",
                                        "detail": "answered oddly"})["codex"]
        self.assertEqual(row["state"], "error")
        self.assertEqual(row["error"], "answered oddly")

    def test_no_deepseek_key_is_signed_out_with_its_own_reason(self):
        row = self.run_with(deepseek_auth={"signed_in": False,
                                           "reason": "no API key."})["deepseek"]
        self.assertEqual(row["state"], "signed_out")
        self.assertEqual(row["error"], "no API key.")

    def test_one_broken_provider_costs_one_row(self):
        self.run_with()
        # A real exception out of one arm, with everything else still mocked.
        with mock.patch("providers.deepseek_auth_state",
                        side_effect=RuntimeError("boom")):
            usage._reset_all_for_tests()
            rows = {r["id"]: r for r in usage.all_providers()["providers"]}
        self.assertEqual(rows["deepseek"]["state"], "error")
        self.assertEqual(rows["claude"]["state"], "ok",
                         "one broken CLI must not take the screen down")

    def test_a_zero_is_never_invented_for_a_missing_balance(self):
        """"no credits here" and "your balance is zero" are opposite claims."""
        row = self.run_with(deepseek={"available": True, "is_available": True,
                                      "balances": []})["deepseek"]
        self.assertIsNone(row["balance"])


class NoSecretCrossesTheBoundary(Scenario):

    def test_nothing_that_looks_like_a_credential_is_serialised(self):
        blob = json.dumps(self.run_with()).lower()
        for needle in ("accesstoken", "refreshtoken", "authorization",
                       "bearer ", "sk-proj-", "apikey", "api_key",
                       "credential", "secret"):
            self.assertNotIn(needle, blob, "%r reached the payload" % needle)

    def test_deepseeks_account_is_the_mask_the_store_already_publishes(self):
        row = self.run_with()["deepseek"]
        self.assertEqual(row["account"], "sk-…abcd")


class TheCache(Scenario):

    def test_a_second_call_inside_the_ttl_does_not_re_probe(self):
        self.run_with()
        import providers
        with mock.patch("providers.codex_auth",
                        side_effect=AssertionError("re-probed")) as spy:
            out = usage.all_providers()
        self.assertEqual(out["source"], "cache")
        self.assertEqual(spy.call_count, 0)
        del providers

    def test_refresh_false_spawns_nothing_even_with_a_cold_cache(self):
        usage._reset_all_for_tests()
        with mock.patch("providers.codex_auth",
                        side_effect=AssertionError("spawned")), \
             mock.patch("codex_models.refresh_plan_if_stale",
                        side_effect=AssertionError("spawned")), \
             mock.patch("providers.provider_bin", return_value="/bin/x"), \
             mock.patch("usage.snapshot", return_value=CLAUDE_OK), \
             mock.patch("providers.deepseek_auth_state",
                        return_value={"signed_in": False, "reason": "none"}), \
             mock.patch("codex_models.plan_cached", return_value=None):
            out = usage.all_providers(refresh=False)
        self.assertEqual(len(out["providers"]), 4)


class TheOldRoutesAreUntouched(unittest.TestCase):

    def test_snapshot_still_answers_its_own_shape(self):
        with mock.patch("usage._cached", return_value=None), \
             mock.patch("usage._fetch", return_value=(None, "no creds")):
            snap = usage.snapshot()
        self.assertEqual(sorted(snap),
                         ["available", "extra_usage", "limits", "reason"])
        self.assertFalse(snap["available"])

    def test_account_still_answers_its_own_shape(self):
        out = usage.account()
        self.assertIn("available", out)
        self.assertIn("profile", out)
        self.assertIn("subscription", out)


if __name__ == "__main__":
    unittest.main()
