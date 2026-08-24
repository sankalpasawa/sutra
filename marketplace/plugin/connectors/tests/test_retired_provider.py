"""A retired provider must keep exactly one capability: destroy.

WHY THIS EXISTS

Retiring Slack by deleting it from the registry looked correct and was verified
to be wrong by execution: nothing raises, but every /api/connectors/slack/...
route -- including DELETE -- starts returning 404. That does not remove an
upgrader's Slack tokens from the Keychain, it removes their only way to remove
them. The tokens become unreachable, permanently.

The second attempt raised from build_strategy. That 500s the whole
/api/connectors/providers endpoint, because build_service() constructs the
strategy eagerly -- so a retired Slack took down GitHub's tile too.

Both failures were found by running the code, not by reading it. These tests
pin the shape that survives.
"""

import unittest

from connectors.registry import RetiredStrategy, get_spec, provider_ids


class SlackIsRetiredNotRemoved(unittest.TestCase):
    def test_slack_is_still_registered(self):
        """The single most important assertion in this file. Deregistering it
        makes DELETE /api/connectors/slack/{id} a 404 and strands the tokens."""
        self.assertIn("slack", provider_ids())

    def test_slack_is_marked_retired(self):
        spec = get_spec("slack")
        self.assertTrue(spec.retired)
        self.assertTrue(spec.retired_note)

    def test_github_is_not_retired(self):
        """Retirement must not leak to the provider Sutra still owns."""
        self.assertFalse(get_spec("github").retired)

    def test_the_user_slot_is_preserved(self):
        """Disconnect erases the slots the SPEC declares. Dropping "user" here
        would silently leave the Slack user token behind on every machine that
        still has one -- while reporting a successful disconnect."""
        self.assertEqual(get_spec("slack").credential_slots, ("user",))

    def test_a_retired_provider_needs_no_local_secret(self):
        """Nothing is minted any more, so demanding a client secret would render
        a 'not configured' blocker for a provider that cannot be configured."""
        self.assertFalse(get_spec("slack").needs_local_secret)


class RetiredStrategyIsBuildableButUnusable(unittest.TestCase):
    def setUp(self):
        self.st = get_spec("slack").build_strategy(None, None)

    def test_it_builds(self):
        """build_service() builds the strategy eagerly. A builder that raises
        takes /api/connectors/providers down for EVERY provider."""
        self.assertIsInstance(self.st, RetiredStrategy)

    def test_every_authorising_action_refuses(self):
        for name in ("begin", "poll", "refresh", "identity"):
            with self.subTest(action=name):
                with self.assertRaises(RuntimeError):
                    getattr(self.st, name)("x")

    def test_the_refusal_names_the_provider_and_says_what_is_possible(self):
        with self.assertRaises(RuntimeError) as cm:
            self.st.begin("")
        msg = str(cm.exception)
        self.assertIn("Slack", msg)
        self.assertIn("disconnected", msg,
                      "the message must say what CAN still be done: " + msg)

    def test_can_resume_answers_rather_than_raises(self):
        """It is a question, not an action. Raising turns a resumable-transaction
        check into a 500 on a screen that was only trying to render."""
        self.assertIs(self.st.can_resume("handle"), False)

    def test_cleanup_calls_are_inert(self):
        self.assertIsNone(self.st.cancel("h"))
        self.assertIsNone(self.st.close_all())


class TileOmissionRule(unittest.TestCase):
    """The rule connectors_api applies: omit a retired provider only when there
    is nothing left to clean up."""

    @staticmethod
    def _omitted(spec, connectors):
        return getattr(spec, "retired", False) and not connectors

    def test_omitted_when_nothing_is_stored(self):
        self.assertTrue(self._omitted(get_spec("slack"), []))

    def test_shown_when_a_connector_still_exists(self):
        """Otherwise the upgrader loses the only route to their own tokens."""
        self.assertFalse(self._omitted(get_spec("slack"), [{"id": "conn_x"}]))

    def test_a_live_provider_is_never_omitted_even_with_no_connectors(self):
        self.assertFalse(self._omitted(get_spec("github"), []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
