#!/usr/bin/env python3
"""A skill body is not something the founder said (founder, 2026-09-14).

THE LEAK THIS PINS. Invoking a Skill makes the Claude CLI write THREE
records: the assistant's `tool_use`, a `tool_result` ("Launching skill: X"),
and then the skill's whole SKILL.md body as a THIRD record whose type is
"user". That third record is a plain text block, so `_is_tool_result` does
not catch it, and it does not start with "<" either -- so `_parse_transcript`
appended it as an ordinary user turn. Two things then went wrong at once:

  UI        goalTranscriptHtml classifies on `role` alone, so 21,271
            characters of core:flow rendered under "you" -- indistinguishable
            from the founder having typed it into the chat.
  EVIDENCE  evidence_text reads this same parser, so an injected skill body
            counted as something the delegate chat had produced.

Measured on the live transcript for mission m-9ce90234465a (session
88696584-b230-49fb-b240-3c669156d6e6): one core:flow invocation, 21,271
characters. Across 363 local transcripts the same shape reaches 107,959.

THE DISCRIMINATOR, and why it is a PAIR. The CLI already marks these:
`isMeta` says the record is not conversation, and `sourceToolUseID` names
the tool call the context was injected for. `isMeta` ALONE is too wide --
it also covers rows a reader wants ("[Image: ...]" placeholders, "Continue
from where you left off"). Requiring both matched exactly the injected-by-
a-tool class in the corpus: 11 of 11, no false positives.

Run: python3 test_session_skill_injection.py
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import session_reader

SID = "88696584-b230-49fb-b240-3c669156d6e6"
SKILL_HEAD = "Base directory for this skill: /plugins/cache/sutra/core/skills/flow"
SKILL_BODY = SKILL_HEAD + "\n\n# The Flow — end-to-end work-resolution spine\n" \
             + ("x" * 21000)


def _rec(**kw):
    base = {"timestamp": "2026-09-14T14:39:06.000Z", "cwd": "/repo",
            "gitBranch": "main"}
    base.update(kw)
    return base


def _user(content, **kw):
    return _rec(type="user", message={"role": "user", "content": content}, **kw)


def _assistant(content, **kw):
    return _rec(type="assistant", message={"role": "assistant",
                                           "content": content}, **kw)


#: the real three-record sequence a Skill invocation writes, in order
SKILL_SEQUENCE = [
    _assistant([{"type": "text", "text": "Governance gate fired."},
                {"type": "tool_use", "id": "tu-skill-1", "name": "Skill",
                 "input": {"skill": "core:flow", "args": "recommend a db"}}]),
    _user([{"type": "tool_result", "tool_use_id": "tu-skill-1",
            "content": "Launching skill: core:flow"}]),
    _user([{"type": "text", "text": SKILL_BODY}],
          isMeta=True, sourceToolUseID="tu-skill-1"),
]


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proj = self.root / "-repo"
        self.proj.mkdir(parents=True)
        self._orig = session_reader.PROJECTS
        session_reader.PROJECTS = self.root

    def tearDown(self):
        session_reader.PROJECTS = self._orig
        self.tmp.cleanup()

    def write(self, rows, sid=SID):
        f = self.proj / (sid + ".jsonl")
        f.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                     encoding="utf-8")
        return f

    def parse(self, rows):
        """Just the messages -- _parse_transcript returns {cwd, branch,
        messages} and every assertion here is about the turns."""
        return session_reader._parse_transcript(self.write(rows))["messages"]


class TestSkillBodyIsNotATurn(Base):

    def test_01_the_injected_skill_body_is_not_a_conversation_message(self):
        msgs = self.parse(SKILL_SEQUENCE)
        for m in msgs:
            self.assertNotIn(SKILL_HEAD, m["text"],
                             "the skill body is still rendered as a turn")
        self.assertEqual([m["role"] for m in msgs], ["assistant"],
                         "only the assistant's own turn should survive")

    def test_02_the_Skill_CALL_is_still_visible(self):
        """Dropping the body must not hide that the skill ran -- the
        transcript still has to show the invocation."""
        msgs = self.parse(SKILL_SEQUENCE)
        calls = [c for m in msgs for c in m.get("calls", ())]
        self.assertEqual([c["name"] for c in calls], ["Skill"],
                         "the Skill tool_use was lost with the body")
        self.assertIn("Skill", msgs[0].get("tools", []),
                      "the back-compat name list lost the call")

    def test_03_the_tool_result_is_still_captured_as_the_calls_output(self):
        """The middle record is a tool_result and was never a turn; the new
        filter must not disturb the id-keyed output capture above it."""
        msgs = self.parse(SKILL_SEQUENCE)
        call = [c for m in msgs for c in m.get("calls", ())][0]
        self.assertIn("Launching skill", call.get("output") or "",
                      "the tool_result output stopped reaching the call")

    def test_04_isMeta_WITHOUT_a_source_tool_is_KEPT(self):
        """The pair is the predicate. isMeta alone also marks rows a reader
        wants -- dropping those would be a second bug, not a fix."""
        rows = [_user([{"type": "text", "text": "[Image: a screenshot]"}],
                      isMeta=True)]
        msgs = self.parse(rows)
        self.assertEqual(len(msgs), 1, "an isMeta row with no source tool "
                                       "call is still shown")
        self.assertIn("[Image:", msgs[0]["text"])

    def test_05_a_source_tool_WITHOUT_isMeta_is_KEPT(self):
        """Both halves are required, in both directions."""
        rows = [_user([{"type": "text", "text": "a real founder turn"}],
                      sourceToolUseID="tu-1")]
        msgs = self.parse(rows)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["text"], "a real founder turn")

    def test_06_an_ordinary_user_turn_is_untouched(self):
        rows = [_user("plain text turn"),
                _user([{"type": "text", "text": "block-shaped turn"}])]
        msgs = self.parse(rows)
        self.assertEqual([m["text"] for m in msgs],
                         ["plain text turn", "block-shaped turn"])

    def test_07_shadows_own_say_still_reads_as_a_turn(self):
        """Shadow's says land as user records and the UI tags them by text.
        They carry neither flag, so they must be completely unaffected."""
        say = "[Shadow · mission m-9ce90234465a] Two answers first"
        msgs = self.parse([_user([{"type": "text", "text": say}])])
        self.assertEqual(len(msgs), 1, "Shadow's own say was dropped")
        self.assertEqual(msgs[0]["text"], say)

    def test_08_the_system_reminder_rule_still_applies(self):
        """The pre-existing '<'-prefix filter is untouched."""
        msgs = self.parse([_user([{"type": "text",
                                   "text": "<local-command-caveat>hi"}])])
        self.assertEqual(msgs, [])

    def test_09_a_real_conversation_around_the_skill_survives(self):
        """End to end: the founder's turn and the worker's answer both stay,
        and only the injected body goes."""
        rows = ([_user("recommend a database")] + SKILL_SEQUENCE
                + [_assistant([{"type": "text", "text": "Postgres, because"}])])
        msgs = self.parse(rows)
        self.assertEqual([m["role"] for m in msgs],
                         ["user", "assistant", "assistant"])
        self.assertEqual(msgs[0]["text"], "recommend a database")
        self.assertEqual(msgs[2]["text"], "Postgres, because")
        self.assertNotIn(SKILL_HEAD, json.dumps(msgs))


class TestEvidenceIsClean(Base):
    """evidence_text reads this parser, so the body reached Shadow too."""

    def test_10_evidence_text_no_longer_carries_the_skill_body(self):
        import shadow_runner
        self.write([_user("recommend a database")] + SKILL_SEQUENCE
                   + [_assistant([{"type": "text", "text": "FINAL: postgres"}])])
        shadow_runner._RECENT_TEXT.pop(SID, None)
        blob = shadow_runner.evidence_text(SID)
        self.assertNotIn(SKILL_HEAD, blob,
                         "an injected skill body is still counted as evidence")
        self.assertIn("FINAL: postgres", blob,
                      "the chat's real output must still be evidence")

    def test_11_read_session_is_the_same_shape_as_before(self):
        self.write(SKILL_SEQUENCE)
        doc = session_reader.read_session(SID)
        self.assertEqual(doc["id"], SID)
        self.assertIn("messages", doc)
        self.assertIn("cwd", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
