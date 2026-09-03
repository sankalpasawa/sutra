"""test_acp_quota.py -- acp_runtime._extract_quota, the one place this build
reads DeepSeek's per-turn token usage off the wire.

The shape pinned here (`_meta.quota.token_count.{input_tokens,output_tokens}`,
`_meta.quota.model_usage[]`) was read off a live session/prompt response, not
the public ACP spec -- same discipline as the rest of acp_runtime.py's verified
wire-format comments. If DeepSeek changes this shape, this test is where that
shows up as a clean failure instead of a silently blank Usage panel.

Run: python -m pytest test_acp_quota.py -q
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from acp_runtime import _extract_quota  # noqa: E402


class ExtractQuota(unittest.TestCase):
    def test_the_verified_live_shape(self):
        result = {
            "stopReason": "end_turn",
            "_meta": {"quota": {
                "token_count": {"input_tokens": 1204, "output_tokens": 88},
                "model_usage": [
                    {"model": "deepseek-chat", "input_tokens": 1204, "output_tokens": 88},
                ],
            }},
        }
        q = _extract_quota(result)
        self.assertEqual(q["token_count"], {"input_tokens": 1204, "output_tokens": 88})
        self.assertEqual(q["model_usage"],
                          [{"model": "deepseek-chat", "input_tokens": 1204, "output_tokens": 88}])

    def test_no_meta_is_none_not_an_error(self):
        self.assertIsNone(_extract_quota({"stopReason": "end_turn"}))

    def test_meta_without_quota_is_none(self):
        self.assertIsNone(_extract_quota({"_meta": {"other": 1}}))

    def test_an_unrecognised_model_usage_key_is_not_forwarded(self):
        """Same allow-list discipline as deepseek_usage.sanitize(): a field this
        build has not been taught to read must not reach a client frame."""
        result = {"_meta": {"quota": {
            "token_count": {"input_tokens": 1, "output_tokens": 2},
            "model_usage": [{"model": "x", "input_tokens": 1, "output_tokens": 2,
                              "internal_billing_id": "acct-999"}],
        }}}
        q = _extract_quota(result)
        self.assertNotIn("internal_billing_id", q["model_usage"][0])

    def test_malformed_quota_is_none_not_fatal(self):
        self.assertIsNone(_extract_quota({"_meta": {"quota": "not-a-dict"}}))
        self.assertIsNone(_extract_quota({"_meta": "not-a-dict"}))
        self.assertIsNone(_extract_quota({"_meta": {"quota": {}}}))


if __name__ == "__main__":
    unittest.main()
