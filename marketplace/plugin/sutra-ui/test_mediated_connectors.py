"""The Google tile reports a connection Sutra does not own.

Every test here exists because the honest answer and the convenient answer
differ. The convenient answer is always "not connected" -- it is what you get
from an empty list, a missing binary, a timeout, and a logged-out user alike.
These tests are what stop that from being rendered as fact.
"""

import ast
import json
import os
import subprocess
import threading
import unittest
from pathlib import Path

import mediated_connectors as mc

HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures" / "claude-mcp-list.txt"

# The literal sentinel the CLI prints when it has no server list -- offline,
# signed out, or genuinely empty. Exit status is 0 in all four cases.
EMPTY_OUT = "No MCP servers configured. Use `claude mcp add` to add a server.\n"


class ParseRealOutput(unittest.TestCase):
    """Against a byte-for-byte capture, never a retyped string. A hand-copied
    fixture would silently normalise the sentinel glyphs, which is exactly the
    detail the parser has to get right."""

    def test_fixture_exists_and_is_real(self):
        self.assertTrue(FIXTURE.exists(), "capture fixture missing: %s" % FIXTURE)
        self.assertIn("claude.ai ", FIXTURE.read_text())

    def test_parses_every_row_of_the_capture(self):
        saw, by_host, _un = mc.parse(FIXTURE.read_text())
        self.assertTrue(saw)
        self.assertIn("gmailmcp.googleapis.com", by_host)
        self.assertIn("drivemcp.googleapis.com", by_host)
        # The Atlassian row is a claude.ai row too and must parse, even though
        # no Google service claims it -- if it did not, a future format change
        # affecting only that row would go unnoticed.
        self.assertIn("mcp.atlassian.com", by_host)

    def test_both_sentinel_glyphs_classify(self):
        """`✔` and `!` both prefix status text. startswith("connected") fails
        on both, which would send every row on a healthy machine to UNKNOWN."""
        self.assertEqual(mc.classify("✔ Connected"), "connected")
        self.assertEqual(mc.classify("! Needs authentication"), "needs_auth")
        self.assertEqual(mc.classify("✔ Connected · tools fetch failed"), "degraded")
        self.assertEqual(mc.classify("⏸ Pending approval"), "pending_approval")
        self.assertEqual(mc.classify("✗ Failed to connect"), "probe_failed")
        self.assertEqual(mc.classify("something new in v3"), "unknown")

    def test_status_text_is_uniform_after_cleaning(self):
        """One field must not read '! Needs authentication' on one row and
        'Connected' on the next purely because one glyph is ASCII."""
        _, by, _un = mc.parse(
            "claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - ✔ Connected\n"
            "claude.ai Google Drive: https://drivemcp.googleapis.com/mcp/v1 - ! Needs authentication\n")
        for rows in by.values():
            for r in rows:
                self.assertFalse(r["raw_status"].startswith(("!", "✔")),
                                 "sentinel survived into display: %r" % r["raw_status"])


class NeverGuess(unittest.TestCase):
    """The core promise: an absent answer renders as unknown, never as absent."""

    def test_offline_sentinel_is_unreadable_not_not_added(self):
        saw, by, _un = mc.parse(EMPTY_OUT)
        self.assertFalse(saw, "the empty sentinel must not count as proof of fetch")
        p = mc._build("unreadable", EMPTY_OUT, saw=saw, by_host=by)
        for svc in p["services"]:
            self.assertEqual(svc["membership"], "unknown",
                             "offline must never render as 'not added'")

    def test_not_added_requires_proof_the_list_arrived(self):
        """Only assertable when some claude.ai row was seen.

        Scoped to CATALOGUED entries: the Atlassian row itself now comes back as
        a passthrough service, and it is legitimately "added" -- it is in the
        list, which is the fact."""
        saw, by, _un = mc.parse(
            "claude.ai Atlassian Rovo: https://mcp.atlassian.com/v1/mcp - ! Needs authentication\n")
        p = mc._build("ok", saw=saw, by_host=by)
        catalogued = [s for s in p["services"] if s["catalogued"]]
        self.assertEqual(len(catalogued), len(mc.CATALOGUE))
        for svc in catalogued:
            self.assertEqual(svc["membership"], "not_added", svc["name"])

    def test_a_connector_sutra_has_no_entry_for_is_surfaced_not_dropped(self):
        """The operator HAS an Atlassian Rovo connector. A catalogue that only
        knows Google would silently drop it, which tells them a connector they
        can see in Claude does not exist."""
        saw, by, _un = mc.parse(
            "claude.ai Atlassian Rovo: https://mcp.atlassian.com/v1/mcp - ! Needs authentication\n")
        p = mc._build("ok", saw=saw, by_host=by)
        extra = [s for s in p["services"] if not s["catalogued"]]
        self.assertEqual([s["name"] for s in extra], ["Atlassian Rovo"])
        self.assertEqual(extra[0]["membership"], "added")
        self.assertEqual(extra[0]["observation"], "needs_auth")

    def test_proof_of_fetch_survives_a_format_change(self):
        """If proof-of-fetch came from the strict row regex, a cosmetic CLI
        change would make the tile announce 'no claude.ai connectors' -- false,
        since the CLI listed three."""
        saw, by, _un = mc.parse(
            "claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 (HTTP) - ✔ Connected\n")
        self.assertTrue(saw)
        self.assertIn("gmailmcp.googleapis.com", by,
                      "optional transport tag must not break row parsing")

    def test_unrecognised_row_shape_still_proves_fetch(self):
        saw, by, _un = mc.parse("claude.ai Gmail >>> totally new layout\n")
        self.assertTrue(saw, "a claude.ai line proves the list arrived")
        self.assertEqual(by, {}, "but an unparseable row must yield no claims")

    def test_cli_missing_and_timeout_are_unknown(self):
        for avail in ("cli_missing", "timed_out", "cli_error", "not_checked"):
            p = mc._build(avail)
            for svc in p["services"]:
                self.assertEqual(svc["membership"], "unknown",
                                 "%s leaked a claim" % avail)


class AnUnreadableRowIsIgnoranceNotAbsence(unittest.TestCase):
    """The nastiest failure this module can have: a CLI format change makes one
    row unparseable, and every OTHER connector is then confidently reported as
    "not listed" -- a wrong answer produced by a parser bug, wearing the
    appearance of a fact."""

    def test_an_unparseable_claudeai_row_is_counted(self):
        saw, by, unparsed = mc.parse(
            "claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - Connected\n"
            "claude.ai Something >>> brand new layout\n")
        self.assertTrue(saw)
        self.assertEqual(unparsed, 1)
        self.assertIn("gmailmcp.googleapis.com", by)

    def test_one_unreadable_row_blocks_every_absence_claim(self):
        saw, by, unparsed = mc.parse(
            "claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - Connected\n"
            "claude.ai Something >>> brand new layout\n")
        p = mc._build("ok", saw=saw, by_host=by, unparsed=unparsed)
        slack = [s for s in p["services"] if s["key"] == "slack"][0]
        self.assertEqual(slack["membership"], "unknown",
                         "an unreadable row must degrade absence to unknown")
        gmail = [s for s in p["services"] if s["key"] == "gmail"][0]
        self.assertEqual(gmail["membership"], "added",
                         "a row we DID read is still a fact")

    def test_absence_is_assertable_when_everything_parsed(self):
        saw, by, unparsed = mc.parse(
            "claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - Connected\n")
        self.assertEqual(unparsed, 0)
        p = mc._build("ok", saw=saw, by_host=by, unparsed=unparsed)
        slack = [s for s in p["services"] if s["key"] == "slack"][0]
        self.assertEqual(slack["membership"], "not_added")


class SlackHasNoKnownHost(unittest.TestCase):
    """Slack has never been connected here, so `claude mcp list` has never
    reported its URL. The entry matches on name until a real row teaches us the
    host -- guessing one would render "Not added in Claude" forever, confidently
    and wrongly."""

    def _slack(self, p):
        return [s for s in p["services"] if s["key"] == "slack"][0]

    def test_absent_slack_is_not_added_when_the_list_arrived(self):
        saw, by, _un = mc.parse(
            "claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - Connected\n")
        svc = self._slack(mc._build("ok", saw=saw, by_host=by))
        self.assertEqual(svc["membership"], "not_added")
        self.assertIsNone(svc["host"], "no host may be invented for Slack")
        self.assertFalse(svc["known_host"])

    def test_absent_slack_is_unknown_when_the_list_did_not_arrive(self):
        for avail in ("cli_missing", "timed_out", "unreadable", "not_checked"):
            svc = self._slack(mc._build(avail))
            self.assertEqual(svc["membership"], "unknown", avail)

    def test_slack_is_matched_by_name_and_LEARNS_its_host(self):
        saw, by, _un = mc.parse(
            "claude.ai Slack: https://slackmcp.example.com/mcp/v1 - Connected\n")
        svc = self._slack(mc._build("ok", saw=saw, by_host=by))
        self.assertEqual(svc["membership"], "added")
        self.assertEqual(svc["host"], "slackmcp.example.com",
                         "the host must be learned from the row, not guessed")

    def test_the_collision_suffix_does_not_defeat_the_name_match(self):
        """The CLI appends " (2)" when two display names collide."""
        saw, by, _un = mc.parse(
            "claude.ai Slack (2): https://slackmcp.example.com/mcp/v1 - ! Needs authentication\n")
        svc = self._slack(mc._build("ok", saw=saw, by_host=by))
        self.assertEqual(svc["membership"], "added")
        self.assertEqual(svc["observation"], "needs_auth")

    def test_a_name_match_does_not_swallow_a_different_connector(self):
        """"Slackbot Notifier" is not Slack."""
        saw, by, _un = mc.parse(
            "claude.ai Slackbot Notifier: https://other.example.com/mcp - Connected\n")
        p = mc._build("ok", saw=saw, by_host=by)
        self.assertEqual(self._slack(p)["membership"], "not_added")
        extra = [s for s in p["services"] if not s["catalogued"]]
        self.assertEqual([s["name"] for s in extra], ["Slackbot Notifier"])


class MultipleConnectorsPerHost(unittest.TestCase):
    def test_two_gmail_accounts_both_survive_and_roll_up_to_worst(self):
        """Two Google accounts in Claude share one host. Collapsing them would
        hide a dead connector behind a healthy one -- inverting the point."""
        saw, by, _un = mc.parse(
            "claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - ✔ Connected\n"
            "claude.ai Gmail (2): https://gmailmcp.googleapis.com/mcp/v1 - ! Needs authentication\n")
        rows = by["gmailmcp.googleapis.com"]
        self.assertEqual(len(rows), 2, "both connectors must survive")
        labels = sorted(r["label"] for r in rows)
        self.assertEqual(labels, ["claude.ai Gmail", "claude.ai Gmail (2)"])
        p = mc._build("ok", saw=saw, by_host=by)
        gmail = [s for s in p["services"] if s["key"] == "gmail"][0]
        self.assertEqual(gmail["observation"], "needs_auth",
                         "roll-up must take the WORSE state, never the healthier")


class AccountIsNeverInvented(unittest.TestCase):
    """The single highest-risk bug: the Claude account email is usually a
    @gmail.com address and is in scope everywhere. Rendering it under a Google
    label would look perfect on the developer's machine and be wrong."""

    def _claude_email(self):
        try:
            return json.load(open(os.path.expanduser("~/.claude.json")))\
                       .get("oauthAccount", {}).get("emailAddress")
        except Exception:
            return None

    def test_payload_declares_the_account_unknown(self):
        self.assertIs(mc._build("ok", saw=True)["account_known"], False)

    def test_no_identity_field_exists_at_all(self):
        blob = json.dumps(mc._build("ok", saw=True))
        for key in ('"account"', '"email"', '"username"', '"login"', '"user"'):
            self.assertNotIn(key, blob, "identity field %s must not exist" % key)

    def test_the_claude_account_email_never_appears(self):
        email = self._claude_email()
        if not email:
            self.skipTest("no local Claude account to guard against")
        saw, by, _un = mc.parse(FIXTURE.read_text())
        blob = json.dumps(mc._build("ok", saw=saw, by_host=by))
        self.assertNotIn(email, blob,
                         "the CLAUDE account email leaked into the Google payload")


class ChildProcessIsContained(unittest.TestCase):
    SRC = (HERE / "mediated_connectors.py").read_text()

    def test_env_is_an_allowlist_of_literal_names(self):
        """A denylist would hand `claude` -- and everything it spawns --
        SUTRA_DESKTOP_TOKEN, which authorises replacing /Applications/Sutra.app."""
        self.assertNotIn("dict(os.environ)", self.SRC)
        self.assertNotIn("os.environ.copy()", self.SRC)
        tree = ast.parse(self.SRC)
        allow = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Assign)
                 and any(getattr(t, "id", "") == "_ENV_ALLOW" for t in n.targets)]
        self.assertEqual(len(allow), 1, "_ENV_ALLOW must be a single literal")
        self.assertIsInstance(allow[0].value, ast.Tuple,
                              "_ENV_ALLOW must be a literal tuple, not computed")

    def test_no_secret_shaped_variable_can_reach_the_child(self):
        os.environ["SUTRA_DESKTOP_TOKEN"] = "sentinel-must-not-propagate"
        os.environ["SUTRA_SLACK_CLIENT_SECRET"] = "sentinel2"
        try:
            env = mc._child_env()
        finally:
            os.environ.pop("SUTRA_DESKTOP_TOKEN", None)
            os.environ.pop("SUTRA_SLACK_CLIENT_SECRET", None)
        for k in env:
            self.assertFalse(k.startswith("SUTRA_"), "leaked %s" % k)
            for bad in ("TOKEN", "SECRET", "KEY", "PASSWORD"):
                self.assertNotIn(bad, k.upper(), "leaked %s" % k)
        self.assertNotIn("sentinel-must-not-propagate", "".join(env.values()))

    def test_cwd_is_an_explicit_constant(self):
        """Inheriting cwd means running the CLI inside a cloned repo, where it
        enumerates that repo's .mcp.json and can execute its stdio command."""
        # AST, not a string match: the module COMMENTS on os.getcwd() to say
        # why it is not used, and a substring test fails on that comment. This
        # is the third time in this codebase a test has matched the prose
        # documenting a fix rather than the code implementing it.
        tree = ast.parse(self.SRC)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "getcwd"):
                self.fail("cwd must never be inherited from the process")
        runs = [n for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "run"]
        self.assertTrue(runs, "expected a subprocess.run call")
        for call in runs:
            kw = {k.arg for k in call.keywords}
            self.assertIn("cwd", kw, "subprocess.run must pin cwd")
            self.assertIn("env", kw, "subprocess.run must pin env")
            self.assertIn("timeout", kw, "subprocess.run must pin timeout")
            self.assertIn("stdin", kw, "subprocess.run must pin stdin")

    def test_argv_is_fixed_and_takes_no_caller_input(self):
        tree = ast.parse(self.SRC)
        for call in [n for n in ast.walk(tree)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr == "run"]:
            argv = call.args[0]
            self.assertIsInstance(argv, ast.List, "argv must be a literal list")
            for el in argv.elts[1:]:
                self.assertIsInstance(el, ast.Constant,
                                      "every argv element after the binary must be constant")


class ProbeIsRationed(unittest.TestCase):
    """Each check spawns the CLI, which opens a live connection to every one of
    the operator's connectors and rewrites Claude's needs-auth cache. It is not
    free and it is not inert."""

    def setUp(self):
        mc._reset_for_tests()
        self.calls = []
        self._real = subprocess.run
        outer = self

        def fake_run(argv, **kw):
            outer.calls.append(argv)
            class R:
                returncode = 0
                stdout = FIXTURE.read_text()
                stderr = ""
            return R()
        subprocess.run = fake_run
        self._which = mc.claude_bin
        mc.claude_bin = lambda: "/fake/claude"

    def tearDown(self):
        subprocess.run = self._real
        mc.claude_bin = self._which
        mc._reset_for_tests()

    def test_default_read_does_not_spawn_anything(self):
        p = mc.snapshot()
        self.assertEqual(self.calls, [], "a plain read must never run the CLI")
        self.assertEqual(p["availability"], "not_checked")

    def test_second_refresh_inside_the_cooldown_is_throttled(self):
        mc.snapshot(refresh=True)
        mc.snapshot(refresh=True)
        self.assertEqual(len(self.calls), 1, "cooldown must suppress the second probe")

    def test_concurrent_refreshes_produce_exactly_one_subprocess(self):
        """Without single-flight, a page hitting this in a loop spawns
        unbounded `claude` processes, each holding sockets for up to 30s."""
        threads = [threading.Thread(target=lambda: mc.snapshot(refresh=True))
                   for _ in range(12)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(self.calls), 1,
                         "12 concurrent refreshes spawned %d processes" % len(self.calls))


class HostileTextIsDefanged(unittest.TestCase):
    def test_control_bytes_and_markup_are_stripped_or_kept_inert(self):
        saw, by, _un = mc.parse(
            "claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - "
            "\x1b[31m<img src=x onerror=alert(1)>\x07\n")
        row = by["gmailmcp.googleapis.com"][0]
        self.assertNotIn("\x1b", row["raw_status"], "ANSI escape survived")
        self.assertNotIn("\x07", row["raw_status"], "control byte survived")
        # The markup itself is NOT stripped here -- the renderer escapes it.
        # This asserts only that it arrives as inert text, not that it is gone.
        self.assertEqual(row["observation"], "unknown")

    def test_status_text_is_capped(self):
        _, by, _un = mc.parse(
            "claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - " + "A" * 5000)
        self.assertLessEqual(len(by["gmailmcp.googleapis.com"][0]["raw_status"]), 120)


if __name__ == "__main__":
    unittest.main(verbosity=2)
