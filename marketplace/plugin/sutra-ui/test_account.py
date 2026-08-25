"""test_account.py -- the Account card's data: what it reads, what it refuses.

Two modules feed Settings > Usage > Account:

  claude_local.profile()   ~/.claude.json oauthAccount, allow-listed
  usage.subscription()     the NON-secret half of the credential record
  usage.account()          the two composed, failing open

The property worth pinning is not the happy path -- it is that a credential
record containing tokens can be handed to these functions and NO token
survives into anything a route would serialise. And that an unknown plan
renders as its raw values, never as a familiar name it does not deserve.

Run: python -m pytest test_account.py -q
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import claude_local  # noqa: E402
import usage  # noqa: E402

FULL_OAUTH_ACCOUNT = {
    "accountUuid": "246c49aa-1111-2222-3333-444444444444",
    "emailAddress": "ada@example.com",
    "organizationUuid": "396f91bb-5555-6666-7777-888888888888",
    "hasExtraUsageEnabled": False,
    "billingType": "stripe_subscription",
    "accountCreatedAt": "2026-07-22T14:41:05.344213Z",
    "subscriptionCreatedAt": "2026-07-22T15:56:22.012622Z",
    "displayName": "Ada (AE)",
    "fullName": "Ada Lovelace",
    "profileFetchedAt": 1787638099467,
    "organizationRole": "admin",
    "workspaceRole": None,
    "organizationName": "Analytical Engines",
    "organizationType": "claude_max",
    "organizationRateLimitTier": "default_claude_max_20x",
    "userRateLimitTier": None,
    "seatTier": None,
    "claudeCodeTrialEndsAt": None,
}

CREDENTIALS_WITH_TOKENS = {
    "accessToken": "sk-ant-oat01-SECRET-ACCESS",
    "refreshToken": "sk-ant-ort01-SECRET-REFRESH",
    "expiresAt": 1787666896293,
    "refreshTokenExpiresAt": 1790000000000,
    "scopes": ["user:inference", "user:profile"],
    "subscriptionType": "max",
    "rateLimitTier": "default_claude_max_20x",
}


def _claude_json(payload):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(payload, fh)
    return path


class PlanLabel(unittest.TestCase):
    def test_exact_mapping_gets_a_friendly_name(self):
        self.assertEqual(claude_local.plan_label("claude_max", "default_claude_max_20x"),
                         "Claude Max (20x)")
        self.assertEqual(claude_local.plan_label("claude_pro", "default_claude_pro"),
                         "Claude Pro")

    def test_unknown_product_is_not_guessed(self):
        """A type this build has not met yields None, so the panel shows the raw
        values -- a familiar name over an unfamiliar tier is the convincing-wrong
        answer ADR-035 forbids."""
        self.assertIsNone(claude_local.plan_label("claude_galaxy", "default_claude_galaxy_5x"))
        self.assertIsNone(claude_local.plan_label(None, "default_claude_max_20x"))


class Profile(unittest.TestCase):
    def test_projects_the_allow_list(self):
        path = _claude_json({"oauthAccount": FULL_OAUTH_ACCOUNT})
        self.addCleanup(os.unlink, path)
        with mock.patch.object(claude_local, "CLAUDE_JSON", path):
            p = claude_local.profile()
        self.assertEqual(p["email"], "ada@example.com")
        self.assertEqual(p["display_name"], "Ada (AE)")
        self.assertEqual(p["full_name"], "Ada Lovelace")
        self.assertEqual(p["plan"], "Claude Max (20x)")
        self.assertEqual(p["organization_type"], "claude_max")
        self.assertEqual(p["rate_limit_tier"], "default_claude_max_20x")
        self.assertEqual(p["billing_type"], "stripe_subscription")
        self.assertEqual(p["organization"], "Analytical Engines")
        self.assertEqual(p["organization_role"], "admin")
        self.assertIs(p["extra_usage_enabled"], False)
        # Short ids, seconds not milliseconds.
        self.assertEqual(p["account_id"], "246c49aa")
        self.assertEqual(p["organization_id"], "396f91bb")
        self.assertAlmostEqual(p["profile_fetched_at"], 1787638099.467, places=2)
        # Access-control knobs are NOT account facts and are not forwarded.
        for absent in ("userRateLimitTier", "seatTier", "workspaceRole",
                       "user_rate_limit_tier", "seat_tier", "workspace_role"):
            self.assertNotIn(absent, p)

    def test_unknown_plan_keeps_raw_values(self):
        oa = dict(FULL_OAUTH_ACCOUNT, organizationType="claude_galaxy",
                  organizationRateLimitTier="default_claude_galaxy_5x")
        path = _claude_json({"oauthAccount": oa})
        self.addCleanup(os.unlink, path)
        with mock.patch.object(claude_local, "CLAUDE_JSON", path):
            p = claude_local.profile()
        self.assertIsNone(p["plan"])
        self.assertEqual(p["organization_type"], "claude_galaxy")
        self.assertEqual(p["rate_limit_tier"], "default_claude_galaxy_5x")

    def test_absent_config_is_unknown_not_an_error(self):
        with mock.patch.object(claude_local, "CLAUDE_JSON", "/nonexistent/x.json"):
            self.assertIsNone(claude_local.profile())


class Subscription(unittest.TestCase):
    def test_only_the_non_secret_fields_come_through(self):
        with mock.patch.object(usage, "_credentials", lambda: dict(CREDENTIALS_WITH_TOKENS)):
            s = usage.subscription()
        self.assertEqual(s, {"subscription_type": "max",
                             "rate_limit_tier": "default_claude_max_20x"})

    def test_no_credentials_is_none(self):
        with mock.patch.object(usage, "_credentials", lambda: None):
            self.assertIsNone(usage.subscription())

    def test_token_still_reads_through_the_shared_record(self):
        """The refactor that introduced _credentials() must not have changed
        what the usage fetch gets: the access token, from the same record."""
        with mock.patch.object(usage, "_credentials", lambda: dict(CREDENTIALS_WITH_TOKENS)):
            self.assertEqual(usage._token(), "sk-ant-oat01-SECRET-ACCESS")


class AccountComposed(unittest.TestCase):
    def test_secrets_never_reach_the_serialised_payload(self):
        """The regression that matters: hand the composer a credential record
        FULL of tokens and assert the JSON a route would return has none of
        them -- not by key, not by value."""
        path = _claude_json({"oauthAccount": FULL_OAUTH_ACCOUNT})
        self.addCleanup(os.unlink, path)
        with mock.patch.object(claude_local, "CLAUDE_JSON", path), \
             mock.patch.object(usage, "_credentials", lambda: dict(CREDENTIALS_WITH_TOKENS)):
            out = usage.account()
        self.assertTrue(out["available"])
        text = json.dumps(out)
        for needle in ("sk-ant", "SECRET", "accessToken", "refreshToken",
                       "access_token", "refresh_token", "expiresAt", "scopes"):
            self.assertNotIn(needle, text)
        self.assertEqual(out["profile"]["email"], "ada@example.com")
        self.assertEqual(out["subscription"]["subscription_type"], "max")

    def test_profile_absent_but_subscription_present_is_still_available(self):
        """A machine whose ~/.claude.json has no oauthAccount but whose Keychain
        does hold credentials renders the card with the profile rows 'not
        reported' -- the fold is not suppressed."""
        with mock.patch.object(claude_local, "CLAUDE_JSON", "/nonexistent/x.json"), \
             mock.patch.object(usage, "_credentials", lambda: dict(CREDENTIALS_WITH_TOKENS)):
            out = usage.account()
        self.assertTrue(out["available"])
        self.assertIsNone(out["profile"])
        self.assertEqual(out["subscription"]["subscription_type"], "max")

    def test_nothing_signed_in_fails_open(self):
        with mock.patch.object(claude_local, "CLAUDE_JSON", "/nonexistent/x.json"), \
             mock.patch.object(usage, "_credentials", lambda: None):
            out = usage.account()
        self.assertFalse(out["available"])
        self.assertIn("signed in", out["reason"])
        self.assertIsNone(out["profile"])


if __name__ == "__main__":
    unittest.main()
