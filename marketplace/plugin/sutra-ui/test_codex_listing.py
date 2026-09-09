#!/usr/bin/env python3
"""test_codex_listing.py -- a Codex chat must survive a refresh.

THE BUG THIS PINS, and it was a DISAPPEARING CHAT rather than a missing badge.
The rail is not built from ~/.sutra-ui/chats; it is built from
GET /api/sessions -> session_reader.list_sessions(), which globbed exactly two
trees:

    ~/.claude/projects/*/*.jsonl
    ~/.gemini/tmp/*/chats/session-*.jsonl

Codex rollouts live at $CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl and were
returned by nothing. adoptRealSessions then replaces the rail WHOLESALE with
what this function returns, so a chat whose only transcript was a codex rollout
vanished on the next refresh while its record sat intact on disk. Measured on
the founder's machine before the fix: 55 rows, 43 claude + 12 deepseek, 0 codex,
with two codex-only chats present and neither listed.

The gap dates from the codex adapter (48622b4), which added codex_resolve_path
-- lookup BY ID, which is why provider SWITCHING always worked -- and never
extended the enumeration. Both halves now use the same recursive glob.

TITLES ARE THE OTHER HALF, and are not cosmetic here. Codex prepends its own
machine preamble to the first user message, so without the `<`-prefix rule the
Claude parser already applies, every codex row read "<recommended_plugins>" --
measured 30 of 30 on the founder's disk. And the first user message of a chat
born from a provider switch is the ENTIRE prior conversation, which would name
every switched chat after the replay preamble.

Reads only. No server, no CLI, no network.
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import session_reader as sr

#: A codex-shaped thread id: hyphenated hex, which is what codex_resolve_path's
#: _CODEX_ID accepts and what all 13 measured rollouts carry.
CX_ID = "01a08572-164d-75d0-9994-9e34e6ffb686"
CX2_ID = "01a08599-2b43-70e1-8aaa-1c2d3e4f5a6b"


def _rollout(root: Path, sid: str, stamp: str, records) -> Path:
    """One rollout where list_sessions' glob will find it: the YYYY/MM/DD
    nesting is codex's, and the filename carries the id as its last
    hyphen-joined component -- the fact codex_resolve_path already relies on."""
    d = root / "sessions" / "2026" / "09" / "09"
    d.mkdir(parents=True, exist_ok=True)
    f = d / ("rollout-%s-%s.jsonl" % (stamp, sid))
    with f.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return f


def _meta(cwd="/work/repo", branch="main", sid=CX_ID):
    return {"type": "session_meta", "timestamp": "2026-09-09T14:44:01Z",
            "payload": {"session_id": sid, "cwd": cwd,
                        "git": {"branch": branch}}}


def _user(text):
    """One user record in the shape codex actually writes.

    `payload.type` = "message" is NOT decoration: transcript_ir.from_codex_file
    gates on it (_CODEX_ITEM_TYPES), so a fixture without it is skipped by the
    reader while still being picked up by the title scan -- which is exactly
    how an early version of this file passed every listing test and failed the
    one that opened the session. Verified against a real rollout on disk:
    payload.type = 'message', content[0].type = 'input_text'.
    """
    return {"type": "response_item", "timestamp": "2026-09-09T14:44:02Z",
            "payload": {"type": "message", "role": "user",
                        "content": [{"type": "input_text", "text": text}]}}


class CodexIsDiscoverable(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sutra-codex-list-"))
        self.codex = self.tmp / "codex"
        self.claude = self.tmp / "claude-projects"
        self.gemini = self.tmp / "gemini"
        for d in (self.codex, self.claude, self.gemini):
            d.mkdir(parents=True, exist_ok=True)
        self.patches = [
            mock.patch.object(sr, "CODEX_ROOT", self.codex),
            mock.patch.object(sr, "PROJECTS", self.claude),
            mock.patch.object(sr, "GEMINI_ROOT", self.gemini),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _claude_transcript(self, sid, text="a claude prompt"):
        d = self.claude / "-work-repo"
        d.mkdir(parents=True, exist_ok=True)
        f = d / (sid + ".jsonl")
        with f.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user", "cwd": "/work/repo",
                                 "gitBranch": "main",
                                 "message": {"role": "user", "content": text}}) + "\n")
        return f

    # ------------------------------------------------------------- listing --

    def test_a_codex_rollout_is_listed(self):
        """THE HEADLINE. Before this, zero codex rows came back however many
        rollouts were on disk."""
        _rollout(self.codex, CX_ID, "2026-09-09T14-44-01",
                 [_meta(), _user("implement the parser")])
        rows = sr.list_sessions()
        self.assertEqual([r["id"] for r in rows], [CX_ID], rows)
        self.assertEqual(rows[0]["source"], "codex")

    def test_the_row_carries_what_the_rail_renders(self):
        _rollout(self.codex, CX_ID, "2026-09-09T14-44-01",
                 [_meta(cwd="/work/repo", branch="feature-x"),
                  _user("implement the parser")])
        r = sr.list_sessions()[0]
        self.assertEqual(r["title"], "implement the parser")
        self.assertEqual(r["title_source"], "prompt")
        self.assertEqual(r["cwd"], "/work/repo")
        self.assertEqual(r["branch"], "feature-x")
        self.assertTrue(r["mtime"] > 0 and r["size"] > 0)

    def test_the_listed_id_is_the_one_codex_resolve_path_accepts(self):
        """The two halves of the same fact -- enumeration and lookup -- must
        agree, or a row appears in the rail and cannot be opened."""
        _rollout(self.codex, CX_ID, "2026-09-09T14-44-01",
                 [_meta(), _user("hello")])
        listed = sr.list_sessions()[0]["id"]
        self.assertEqual(listed, CX_ID)
        self.assertIsNotNone(sr.codex_resolve_path(listed),
                             "a listed row resolves to no file")

    def test_claude_and_deepseek_discovery_are_unchanged(self):
        """Codex is ADDITIVE. The other two providers must come back exactly as
        before, in the same mtime order, with their own `source`."""
        self._claude_transcript("c1a70000-0000-4000-8000-0000000000a1")
        _rollout(self.codex, CX_ID, "2026-09-09T14-44-01",
                 [_meta(), _user("codex prompt")])
        rows = sr.list_sessions()
        by = {r["source"]: r for r in rows}
        self.assertIn("claude", by, "claude discovery regressed: %r" % (rows,))
        self.assertIn("codex", by)
        self.assertEqual(by["claude"]["title"], "a claude prompt")

    def test_no_row_is_emitted_twice(self):
        _rollout(self.codex, CX_ID, "2026-09-09T14-44-01", [_meta(), _user("one")])
        _rollout(self.codex, CX2_ID, "2026-09-09T15-00-00",
                 [_meta(sid=CX2_ID), _user("two")])
        self._claude_transcript("c1a70000-0000-4000-8000-0000000000a1")
        ids = [r["id"] for r in sr.list_sessions()]
        self.assertEqual(len(ids), len(set(ids)), "a session was listed twice: %r" % ids)

    def test_pagination_still_slices_across_all_three_providers(self):
        _rollout(self.codex, CX_ID, "2026-09-09T14-44-01", [_meta(), _user("one")])
        _rollout(self.codex, CX2_ID, "2026-09-09T15-00-00",
                 [_meta(sid=CX2_ID), _user("two")])
        self.assertEqual(len(sr.list_sessions(limit=1)), 1)
        self.assertEqual(len(sr.list_sessions(limit=1, offset=1)), 1)
        self.assertNotEqual(sr.list_sessions(limit=1)[0]["id"],
                            sr.list_sessions(limit=1, offset=1)[0]["id"])

    def test_an_empty_codex_tree_changes_nothing(self):
        self._claude_transcript("c1a70000-0000-4000-8000-0000000000a1")
        rows = sr.list_sessions()
        self.assertEqual([r["source"] for r in rows], ["claude"])

    # -------------------------------------------------------------- titles --

    def test_the_injected_preamble_is_not_a_title(self):
        """30 of 30 rows on the founder's disk read "<recommended_plugins>"
        before this. The Claude parser's `<`-prefix rule is what fixes it, and
        it is applied here rather than reinvented."""
        _rollout(self.codex, CX_ID, "2026-09-09T14-44-01",
                 [_meta(), _user("<recommended_plugins>\nsome machine text"),
                  _user("what I actually asked")])
        r = sr.list_sessions()[0]
        self.assertFalse(r["title"].startswith("<"), r["title"])
        self.assertEqual(r["title"], "what I actually asked")

    def test_a_carried_over_conversation_is_not_a_title(self):
        """The first user message of a chat born from a provider switch is the
        WHOLE prior conversation. Titling from it would name every switched
        chat after the replay preamble."""
        replay = ("<transcript-deadbeef>\n"
                  "You are taking over an in-progress working session\n"
                  "...\n</transcript-deadbeef>")
        _rollout(self.codex, CX_ID, "2026-09-09T14-44-01",
                 [_meta(), _user(replay), _user("now do the next thing")])
        self.assertEqual(sr.list_sessions()[0]["title"], "now do the next thing")

    def test_a_thread_with_no_usable_prompt_says_so(self):
        _rollout(self.codex, CX_ID, "2026-09-09T14-44-01", [_meta()])
        r = sr.list_sessions()[0]
        self.assertEqual(r["title"], "(no prompt)")
        self.assertEqual(r["title_source"], "none")

    def test_the_replay_markers_match_transcript_ir(self):
        """The two constants are RESTATED in session_reader, not imported --
        transcript_ir imports this module, so importing it back is a cycle.
        Restating is only safe while the copies agree, which is what this
        asserts."""
        import transcript_ir
        self.assertEqual(sr._REPLAY_FENCE.pattern,
                         transcript_ir._REPLAY_FENCE.pattern)
        self.assertEqual(sr._REPLAY_PREAMBLE, transcript_ir._REPLAY_PREAMBLE)

    # ------------------------------------------------------------ refusals --

    def test_a_rollout_whose_stem_carries_no_id_is_skipped(self):
        """Same None-means-skip contract _gemini_session_meta uses: a row the
        operator cannot open is worse than no row."""
        d = self.codex / "sessions" / "2026" / "09" / "09"
        d.mkdir(parents=True, exist_ok=True)
        (d / "rollout-garbage.jsonl").write_text(
            json.dumps(_meta()) + "\n", encoding="utf-8")
        self.assertEqual(sr.list_sessions(), [])

    def test_an_id_with_fewer_groups_than_a_uuid_is_read_correctly(self):
        """THE BUG A FIXTURE COULD NOT FIND. The id was first extracted by
        taking the last five hyphen-separated components of the stem, which is
        right for every rollout measured (all 5-group UUIDs) and silently wrong
        for anything else: a 4-group id absorbs the trailing piece of the
        TIMESTAMP and yields "01-01a08191-7175-..." -- a row listed under a
        name no lookup resolves, so the chat reappears and cannot be opened.
        Caught by driving a real turn, which is why this test exists rather
        than another five-group fixture."""
        short = "01a08191-7175-7f62-d36a4a7c0c82442d"       # four groups
        _rollout(self.codex, short, "2026-09-09T14-44-01",
                 [_meta(sid=short), _user("hello")])
        rows = sr.list_sessions()
        self.assertEqual([r["id"] for r in rows], [short],
                         "the id was mis-parsed out of the filename: %r"
                         % ([r["id"] for r in rows],))
        self.assertIsNotNone(sr.codex_resolve_path(rows[0]["id"]),
                             "a listed row resolves to no file")

    def test_the_timestamp_is_never_part_of_the_id(self):
        for sid in ("01a08572-164d-75d0-9994-9e34e6ffb686",
                    "01a08191-7175-7f62-d36a4a7c0c82442d",
                    "deadbeef-cafe"):
            with self.subTest(sid=sid):
                shutil.rmtree(self.codex, ignore_errors=True)
                self.codex.mkdir(parents=True, exist_ok=True)
                _rollout(self.codex, sid, "2026-09-09T14-44-01",
                         [_meta(sid=sid), _user("x")])
                got = sr.list_sessions()[0]["id"]
                self.assertEqual(got, sid)
                self.assertNotIn("2026", got, "timestamp leaked into the id")

    def test_a_codex_session_can_actually_be_OPENED(self):
        """Listing without reading is a row the operator clicks and gets
        nothing from -- the same failure _codex_session_meta refuses when it
        skips an unidentifiable rollout. read_session gained a codex arm for
        this, and read_resolve_path is what test_52 resolves listed ids
        through."""
        _rollout(self.codex, CX_ID, "2026-09-09T14-44-01",
                 [_meta(), _user("implement the parser")])
        sid = sr.list_sessions()[0]["id"]
        self.assertIsNotNone(sr.read_resolve_path(sid),
                             "a listed codex row resolves to no file")
        got = sr.read_session(sid)
        self.assertIsNotNone(got, "a listed codex row cannot be opened")
        self.assertEqual(got["id"], sid)
        self.assertTrue(any("implement the parser" in m.get("text", "")
                            for m in got["messages"]),
                        "the transcript came back without its own prompt")

    def test_read_resolve_path_does_not_teach_the_WRITE_paths_about_codex(self):
        """resolve_path is shared with append_title() (writes a Claude-shaped
        record) and relocate() (MOVES the file). Neither has a codex analogue,
        and pointing them at another vendor's tree is the failure
        codex_resolve_path was split out to avoid. The read-only resolver must
        therefore be a SEPARATE function, not an extension of that one."""
        _rollout(self.codex, CX_ID, "2026-09-09T14-44-01", [_meta(), _user("x")])
        self.assertIsNone(sr.resolve_path(CX_ID),
                          "the write-shared resolver now reaches codex's tree")
        self.assertIsNotNone(sr.read_resolve_path(CX_ID))

    def test_an_unreadable_rollout_does_not_take_down_the_listing(self):
        _rollout(self.codex, CX_ID, "2026-09-09T14-44-01", [_meta(), _user("good")])
        f = _rollout(self.codex, CX2_ID, "2026-09-09T15-00-00", [])
        f.write_text("{ this is not json\n", encoding="utf-8")
        ids = [r["id"] for r in sr.list_sessions()]
        self.assertIn(CX_ID, ids, "one bad file hid every other session")

    def test_the_glob_matches_codex_resolve_paths_own(self):
        """Both halves must keep using the same layout constant, or a rollout
        can be listed and not resolvable (or the reverse) after codex changes
        its nesting."""
        src = Path(sr.__file__).read_text(encoding="utf-8")
        self.assertIn('CODEX_ROOT.glob("sessions/**/rollout-*.jsonl")', src)
        self.assertIn('CODEX_ROOT.glob("sessions/**/rollout-*-%s.jsonl" % session_id)',
                      src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
