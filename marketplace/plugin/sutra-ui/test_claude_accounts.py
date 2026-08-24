"""Resolving a connector's account must never produce a plausible wrong answer.

The hazard is specific and permanent: ~/.claude.json holds the CLAUDE account
email, which is frequently a @gmail.com address, and every Gmail response is
full of OTHER people's addresses. Any code that reaches for "an email-shaped
string near here" will look correct on the developer's machine and be wrong for
someone whose Claude login differs from their connected account, or whose most
recent sent mail went to a colleague.
"""

import ast
import json
import unittest
from unittest import mock

import claude_accounts as ca


def _boom(_t, _s):
    raise RuntimeError("boom")


def _sse(payload):
    """The proxy replies as SSE even for one message."""
    return "event: message\ndata: " + json.dumps(payload) + "\n\n"


def _threads(messages):
    return {"result": {"content": [{"text": json.dumps(
        {"threads": [{"id": "t1", "messages": messages}]})}]}}


class GmailAccount(unittest.TestCase):
    def _resolve(self, result):
        with mock.patch.object(ca, "_call_tool", return_value=result):
            return ca._gmail_account("tok", "srv")

    def test_returns_the_sender_of_the_operators_own_sent_mail(self):
        got = self._resolve(_threads([
            {"sender": "me@example.com", "toRecipients": ["someone@else.com"]}]))
        self.assertEqual(got, "me@example.com")

    def test_never_returns_a_RECIPIENT(self):
        """The single most likely wrong answer: the person you last emailed."""
        got = self._resolve(_threads([
            {"toRecipients": ["colleague@other.com"], "ccRecipients": ["boss@x.com"]}]))
        self.assertIsNone(got, "a recipient was returned as the account")

    def test_an_unfamiliar_shape_yields_None_not_a_scraped_address(self):
        """If the response shape changes, the honest answer is None. Scraping an
        address out of the blob would return whatever happened to be first."""
        got = self._resolve({"result": {"content": [{"text": json.dumps(
            {"conversations": [{"participants": ["stranger@nope.com"]}]})}]}})
        self.assertIsNone(got)

    def test_an_empty_or_missing_result_is_None(self):
        self.assertIsNone(self._resolve(None))
        self.assertIsNone(self._resolve({}))
        self.assertIsNone(self._resolve(_threads([])))

    def test_the_source_contains_no_regex_fallback_over_the_raw_blob(self):
        """A structural guard, because this is the mutation that survives every
        behavioural test written from a well-formed fixture."""
        src = open("claude_accounts.py").read()
        tree = ast.parse(src)
        fn = [n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_gmail_account"][0]
        # An AST walk for actual `re.*` CALLS. A substring check fails here for
        # a funny reason: the source legitimately contains "search_threads", the
        # tool name -- so a naive scan flags the correct code.
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "re"):
                self.fail("_gmail_account must not pattern-match addresses out of "
                          "the response; it must read the sender field")


class Resolve(unittest.TestCase):
    def test_a_connector_with_no_resolver_is_absent_not_None(self):
        """Absent means "we never asked"; None means "we asked and could not
        tell". The tile renders those differently and must be able to."""
        # RESOLVERS holds a direct reference to the function object, so patching
        # the module attribute does not reach it. Patch the table.
        with mock.patch.object(ca, "_session_token", return_value="t"), \
             mock.patch.object(ca, "server_ids", return_value={"Gmail": "s1"}), \
             mock.patch.object(ca, "RESOLVERS",
                               {"gmail": ("Gmail", lambda t, s: "a@b.com")}):
            out = ca.resolve(["gmail", "gdrive", "slack"])
        self.assertEqual(out, {"gmail": "a@b.com"})

    def test_no_token_yields_nothing_rather_than_raising(self):
        with mock.patch.object(ca, "_session_token", return_value=None):
            self.assertEqual(ca.resolve(["gmail"]), {})

    def test_a_resolver_that_raises_is_None_not_a_crash(self):
        with mock.patch.object(ca, "_session_token", return_value="t"), \
             mock.patch.object(ca, "server_ids", return_value={"Gmail": "s1"}), \
             mock.patch.object(ca, "RESOLVERS", {"gmail": ("Gmail", _boom)}):
            self.assertEqual(ca.resolve(["gmail"]), {"gmail": None})

    def test_a_connector_absent_from_the_server_list_is_skipped(self):
        with mock.patch.object(ca, "_session_token", return_value="t"), \
             mock.patch.object(ca, "server_ids", return_value={}):
            self.assertEqual(ca.resolve(["gmail"]), {})


class TokenHandling(unittest.TestCase):
    def test_the_token_is_never_returned_by_any_public_function(self):
        with mock.patch.object(ca, "_session_token", return_value="SECRET-TOKEN"), \
             mock.patch.object(ca, "server_ids", return_value={"Gmail": "s1"}), \
             mock.patch.object(ca, "RESOLVERS",
                               {"gmail": ("Gmail", lambda t, s: "a@b.com")}):
            out = ca.resolve(["gmail"])
        self.assertNotIn("SECRET-TOKEN", json.dumps(out))

    def test_the_metadata_only_view_is_requested(self):
        """Determining an address must not read message content. The view that
        omits subject, snippet and body is the whole reason this is acceptable."""
        seen = {}
        def fake(token, sid, name, arguments):
            seen.update(arguments); return None
        with mock.patch.object(ca, "_call_tool", side_effect=fake):
            ca._gmail_account("t", "s")
        self.assertEqual(seen.get("view"), "THREAD_VIEW_METADATA_ONLY")
        self.assertEqual(seen.get("pageSize"), 1, "one thread is enough")


if __name__ == "__main__":
    unittest.main(verbosity=2)
