"""test_switch_egress.py -- silent scrub plus mandatory audit trail
(GAME-PLAN-provider-switch piece 6).

The load-bearing pair is test_planted_secrets_do_not_reach_the_payload and
test_audit_row_never_contains_the_secret_it_caught: egress is silent by founder
decision D3, so the scrub has to work AND the record of it must not become a
second plaintext copy of what it found.

EVERY CREDENTIAL FIXTURE HERE IS ASSEMBLED AT RUNTIME, never written as a
literal -- including the PEM banner. PROTO-004's hook blocks key-shaped strings
in non-env files (it blocked the first draft of this file twice) and it is
right to: a synthetic fixture and a real leaked key look identical to a
scanner, and a test file full of literals trains everyone to reach for the
override. Building them from parts keeps the file clean for the hook, for
GitHub secret scanning, and for the next person grepping the repo.
"""
import json
import os
import shutil
import stat
import tempfile
import unittest

import chat_store
import replay
import shadow_egress
import switch
import switch_egress

#: Banner delimiter, built rather than written -- see the module docstring.
_D5 = "-" * 5


def _fake_credentials():
    """Synthetic credential-shaped strings, assembled so no literal appears."""
    return {
        "openai-key": "sk" + "-" + "A" * 22,
        "github-token": "ghp" + "_" + "b" * 24,
        "slack-token": "xoxb" + "-" + "1234567890" + "-" + "cdefghij",
        "aws-key-id": "AKIA" + "D" * 16,
        "stripe-key": "sk" + "_" + "live" + "_" + "e" * 24,
        "jwt": ("ey" + "JhbGciOiJIUzI1NiJ9" + "."
                + "ey" + "JzdWIiOiIxMjM0NTY3ODkwIn0" + "."
                + "f" * 20),
        "slack-webhook": ("https://hooks.slack.com/services/"
                          + "T00000000/B00000000/" + "g" * 24),
    }


def _fake_pem():
    """(body, whole_block) with the banner assembled from _D5."""
    body = "MIIEowIBAAKCAQEA1234567890\nabcdefghij"
    block = (_D5 + "BEGIN RSA PRIVATE KEY" + _D5 + "\n" + body + "\n"
             + _D5 + "END RSA PRIVATE KEY" + _D5)
    return body, block


class ScrubTest(unittest.TestCase):

    def test_planted_secrets_do_not_reach_the_payload(self):
        creds = _fake_credentials()
        text = "config dump:\n" + "\n".join(
            "%s = %s" % (k, v) for k, v in creds.items())
        clean, counts = switch_egress.scrub_payload(text)
        for name, value in creds.items():
            self.assertNotIn(value, clean, "%s survived the scrub" % name)
            self.assertIn(name, counts, "%s was redacted but not counted" % name)

    def test_pem_private_key_block_is_removed_whole(self):
        body, pem = _fake_pem()
        clean, counts = switch_egress.scrub_payload("key:\n" + pem)
        self.assertNotIn(body, clean)
        self.assertEqual(counts.get("pem-private-key"), 1)

    def test_db_uri_keeps_the_host_and_drops_the_credentials(self):
        """Blanking the whole URI would hide a schema the receiving model
        needs; the secret is the userinfo, not the host."""
        pw = "s3cr" + "etpw"
        clean, counts = switch_egress.scrub_payload(
            "DATABASE_URL=postgres://admin:%s@db.internal:5432/appdb" % pw)
        self.assertNotIn(pw, clean)
        self.assertNotIn("admin:", clean)
        self.assertIn("db.internal", clean)
        self.assertIn("appdb", clean)
        self.assertEqual(counts.get("db-uri-credentials"), 1)

    def test_assignment_style_secret_keeps_its_key_name(self):
        val = "hunter2" * 3
        clean, counts = switch_egress.scrub_payload('API_KEY = "%s"' % val)
        self.assertNotIn(val, clean)
        self.assertIn("API_KEY", clean, "the key name is information, not a secret")
        self.assertEqual(counts.get("private-key-env"), 1)

    def test_real_file_paths_are_not_normalised(self):
        """The shell scrubber rewrites $HOME and /tmp because it ships diffs to
        an outside reviewer. A replay hands over a record of work on real files
        and the target has to read those paths afterwards."""
        text = "Read /Users/someone/project/app.py and /tmp/build/out.log"
        clean, counts = switch_egress.scrub_payload(text)
        self.assertEqual(clean, text)
        self.assertEqual(counts, {})

    def test_ordinary_code_is_untouched(self):
        text = "def add(a, b):\n    return a + b\n# TODO: handle overflow"
        clean, counts = switch_egress.scrub_payload(text)
        self.assertEqual(clean, text)
        self.assertEqual(counts, {})

    def test_backwards_compatible_scrub_still_returns_a_count(self):
        """app.py:1718, sutra_mcp.py and mission_engine.py all unpack two."""
        cred = "sk" + "-" + "Z" * 18
        clean, n = shadow_egress.scrub("key %s here" % cred)
        self.assertEqual(n, 1)
        self.assertNotIn(cred, clean)

    def test_none_and_empty_are_safe(self):
        self.assertEqual(switch_egress.scrub_payload(None), ("", {}))
        self.assertEqual(switch_egress.scrub_payload(""), ("", {}))


class LogTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sutra-egress-")
        self._prev = os.environ.get("SUTRA_UI_SWITCH_EGRESS")
        os.environ["SUTRA_UI_SWITCH_EGRESS"] = os.path.join(self.tmp, "log.jsonl")

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("SUTRA_UI_SWITCH_EGRESS", None)
        else:
            os.environ["SUTRA_UI_SWITCH_EGRESS"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_row_is_appended_and_stamped(self):
        switch_egress.record({"event": "provider-switch", "target": "deepseek"})
        switch_egress.record({"event": "provider-switch", "target": "claude"})
        rows = switch_egress.read()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.get("id") and r.get("ts") for r in rows))
        self.assertEqual([r["target"] for r in rows], ["deepseek", "claude"])

    def test_log_file_is_private(self):
        switch_egress.record({"event": "x"})
        mode = stat.S_IMODE(os.stat(switch_egress.log_path()).st_mode)
        self.assertEqual(mode, 0o600,
                         "an audit log of credential activity must not be "
                         "group or world readable")

    def test_oversized_row_is_replaced_not_written(self):
        """Catches a caller who starts putting a payload in a row."""
        switch_egress.record({"event": "x", "payload": "z" * 20000})
        rows = switch_egress.read()
        self.assertEqual(len(rows), 1)
        self.assertNotIn("payload", rows[0])
        self.assertIn("log_error", rows[0])

    def test_unwritable_log_does_not_stop_a_switch_but_is_reported(self):
        # Seed FIRST so tmp/log.jsonl exists as a regular file, then point the
        # log underneath it: makedirs cannot create a directory inside a file.
        # (Setting the nested path before seeding just makes makedirs create
        # log.jsonl as a directory and the write succeeds -- which is how the
        # first version of this test passed for the wrong reason.)
        switch_egress.record({"event": "seed"})
        self.assertTrue(os.path.isfile(switch_egress.log_path()))
        os.environ["SUTRA_UI_SWITCH_EGRESS"] = os.path.join(
            self.tmp, "log.jsonl", "nested", "log.jsonl")
        row = switch_egress.record({"event": "x"})
        self.assertIn("log_error", row,
                      "an unwritable log must be reported, never swallowed")

    def test_corrupt_lines_are_skipped_on_read(self):
        with open(switch_egress.log_path(), "w") as fh:
            fh.write("{not json\n")
            fh.write(json.dumps({"event": "ok"}) + "\n")
        self.assertEqual([r["event"] for r in switch_egress.read()], ["ok"])

    def test_read_on_a_missing_log_is_empty(self):
        self.assertEqual(switch_egress.read(), [])


class PrepareTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sutra-prep-")
        self._chats = os.environ.get("SUTRA_UI_CHATS")
        self._log = os.environ.get("SUTRA_UI_SWITCH_EGRESS")
        os.environ["SUTRA_UI_CHATS"] = os.path.join(self.tmp, "chats")
        os.environ["SUTRA_UI_SWITCH_EGRESS"] = os.path.join(self.tmp, "log.jsonl")

    def tearDown(self):
        for k, v in (("SUTRA_UI_CHATS", self._chats),
                     ("SUTRA_UI_SWITCH_EGRESS", self._log)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _plan_with_secret(self):
        secret = "sk" + "-" + "DEADBEEFdeadbeef012345"
        ir = {"provider": "claude", "turns": [
            {"role": "user", "blocks": [chat_store.block_text("read the env")]},
            {"role": "assistant", "blocks": [
                chat_store.block_tool_use("Bash", {"command": "env"}, "t1"),
                chat_store.block_tool_result(
                    "OPENAI_API_KEY=%s\nPATH=/usr/bin" % secret, "t1")]},
        ]}
        rec = chat_store.begin_segment(chat_store.create(), "claude", "c-1")
        rec = chat_store.append_turn(rec, "user", [chat_store.block_text("q")])
        plan = switch.plan(rec["sutra_id"], "deepseek", ir_loader=lambda s: ir)
        self.assertTrue(plan["switch"])
        self.assertIn(secret, plan["payload"], "fixture must actually carry it")
        return plan, secret

    def test_secret_is_gone_from_the_payload_prepare_returns(self):
        plan, secret = self._plan_with_secret()
        out = switch_egress.prepare(plan)
        self.assertTrue(out["switch"])
        self.assertNotIn(secret, out["payload"])
        self.assertGreaterEqual(out["redaction_count"], 1)

    def test_audit_row_never_contains_the_secret_it_caught(self):
        """A log that recorded what it caught would be a second plaintext copy
        of every secret, in a file that exists because nobody is watching."""
        plan, secret = self._plan_with_secret()
        switch_egress.prepare(plan)
        with open(switch_egress.log_path()) as fh:
            blob = fh.read()
        self.assertNotIn(secret, blob)
        self.assertNotIn("PATH=/usr/bin", blob, "no payload content at all")
        row = switch_egress.read()[-1]
        self.assertIn("openai-key", row["redactions"])
        self.assertEqual(row["redactions"]["openai-key"], 1)

    def test_audit_row_carries_the_decisions_not_the_data(self):
        plan, _ = self._plan_with_secret()
        switch_egress.prepare(plan)
        row = switch_egress.read()[-1]
        for field in ("event", "sutra_id", "source", "target", "tier",
                      "user_turns", "chars", "chars_before_scrub", "fence_ok",
                      "sent", "window_tokens", "window_source"):
            self.assertIn(field, row, "audit row is missing %r" % field)
        self.assertEqual(row["event"], "provider-switch")
        self.assertEqual(row["source"], "claude")
        self.assertEqual(row["target"], "deepseek")
        self.assertTrue(row["sent"])
        self.assertNotIn("payload", row)

    def test_fence_is_reverified_after_scrubbing(self):
        """Scrubbing is the last mutation; a boundary checked before it is not
        checked."""
        plan, _ = self._plan_with_secret()
        out = switch_egress.prepare(plan)
        self.assertTrue(replay.fence_is_intact(
            {"prompt": out["payload"], "nonce": out["nonce"]}))
        self.assertTrue(switch_egress.read()[-1]["fence_ok"])

    def test_broken_fence_after_scrub_refuses_and_logs_not_sent(self):
        plan, _ = self._plan_with_secret()
        real = switch_egress.scrub_payload
        switch_egress.scrub_payload = (
            lambda t: (t + "\n</transcript-%s>" % plan["nonce"], {"jwt": 1}))
        try:
            out = switch_egress.prepare(plan)
        finally:
            switch_egress.scrub_payload = real
        self.assertFalse(out["switch"])
        self.assertEqual(out["reason"], "fence-integrity-failed-after-scrub")
        self.assertIn("nothing was sent", out["detail"])
        row = switch_egress.read()[-1]
        self.assertFalse(row["fence_ok"])
        self.assertFalse(row["sent"], "a refused switch must be logged as unsent")

    def test_refused_plan_passes_through_untouched(self):
        rec = chat_store.begin_segment(chat_store.create(), "claude", "c-1")
        refused = switch.plan(rec["sutra_id"], "claude")
        self.assertIs(switch_egress.prepare(refused), refused)
        self.assertEqual(switch_egress.read(), [],
                         "a not-needed plan is not an egress event")

    def test_logging_can_be_suppressed_for_a_dry_run(self):
        plan, _ = self._plan_with_secret()
        out = switch_egress.prepare(plan, log=False)
        self.assertTrue(out["switch"])
        self.assertEqual(switch_egress.read(), [])
        self.assertIn("audit", out, "the row is still returned to the caller")

    def test_clean_payload_logs_zero_redactions(self):
        ir = {"provider": "claude", "turns": [
            {"role": "user", "blocks": [chat_store.block_text("hello")]},
            {"role": "assistant", "blocks": [chat_store.block_text("hi")]}]}
        rec = chat_store.begin_segment(chat_store.create(), "claude", "c-1")
        plan = switch.plan(rec["sutra_id"], "deepseek", ir_loader=lambda s: ir)
        switch_egress.prepare(plan)
        row = switch_egress.read()[-1]
        self.assertEqual(row["redactions"], {})
        self.assertEqual(row["redaction_count"], 0)
        self.assertTrue(row["sent"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
