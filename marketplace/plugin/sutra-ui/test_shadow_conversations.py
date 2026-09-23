"""test_shadow_conversations.py -- A CONVERSATION IS DURABLE, AND IT IS NOT
A MISSION (founder, 2026-09-23).

The rail is built from missions, so until now the mission id was the only
durable Shadow identity and a conversation that opened no task survived only
in the client's memory -- a hard refresh lost it. This lane pins the store
that fixes that, and in particular the two properties the client leans on:
the id is MINTED BY THE CLIENT (so the screen can change synchronously) and
create is therefore IDEMPOTENT on it.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_conversations.py
"""
import json
import os
import tempfile
import unittest

# THE HOME IS BOUND BEFORE THE FIRST IMPORT, not in setUp. conftest.py does
# this for pytest, and the DMG gate runs these lanes through run-tests.sh
# (plain unittest), where nothing does -- so anything that writes during
# import or outside a test method would reach the LIVE shadow home.
os.environ.setdefault("SUTRA_SHADOW_HOME",
                      tempfile.mkdtemp(prefix="shadow-conversations-"))

import shadow_conversations as C     # noqa: E402


class TheIdIsTheClients(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name

    def test_a_minted_id_has_the_shape_the_store_accepts(self):
        self.assertTrue(C.ID_RE.match(C.mint()))

    def test_a_client_id_is_taken_verbatim(self):
        rec = C.create("shc-abc123", "In the latest about motorcycles")
        self.assertEqual(rec["id"], "shc-abc123")

    def test_create_is_idempotent_on_the_id(self):
        """A retry after a dropped socket, or a double Enter, is ONE
        conversation. Forking here would split a founder's thread in two."""
        first = C.create("shc-abc123", "the first prompt")
        again = C.create("shc-abc123", "a completely different prompt")
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(again["created_at"], first["created_at"])
        self.assertEqual([m["text"] for m in again["messages"]],
                         ["the first prompt"],
                         "the second create must not append or overwrite")

    def test_an_id_that_could_escape_the_directory_is_refused(self):
        """The id becomes a FILENAME."""
        for bad in ("../../etc/passwd", "shc-../x", "m-deadbeef", "",
                    "shc-" + "x" * 60, "shc-UPPER", "shc-ab"):
            with self.assertRaises(ValueError, msg=bad):
                C.create(bad, "x")

    def test_a_mission_id_is_not_a_conversation_id(self):
        with self.assertRaises(ValueError):
            C.create("m-1234abcd", "x")


class ItSurvivesTheProcess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name

    def test_the_record_is_on_disk_and_reads_back_whole(self):
        C.create("shc-aaa111", "Hi")
        C.append("shc-aaa111", "shadow", "Hi. What would you like done?")
        path = os.path.join(self.tmp.name, "conversations", "shc-aaa111.json")
        self.assertTrue(os.path.exists(path), "the file is the durability")
        on_disk = json.load(open(path, encoding="utf-8"))
        self.assertEqual([m["text"] for m in on_disk["messages"]],
                         ["Hi", "Hi. What would you like done?"])

    def test_a_reload_sees_it_through_the_public_read(self):
        C.create("shc-aaa111", "Hi")
        self.assertEqual(C.load("shc-aaa111")["messages"][0]["text"], "Hi")

    def test_the_title_is_the_founders_own_line(self):
        rec = C.create("shc-aaa111", "  In the   latest about motorcycles ")
        self.assertEqual(rec["title"], "In the latest about motorcycles")

    def test_a_long_first_line_is_trimmed_not_summarised(self):
        rec = C.create("shc-aaa111", "x" * 200)
        self.assertTrue(rec["title"].startswith("x" * 79))
        self.assertTrue(rec["title"].endswith("…"))
        self.assertEqual(len(rec["title"]), 80)

    def test_listing_is_newest_first(self):
        C.create("shc-aaa111", "first")
        C.create("shc-bbb222", "second")
        ids = [r["id"] for r in C.list_all()]
        self.assertEqual(set(ids), {"shc-aaa111", "shc-bbb222"})


class TwoConversationsNeverTouch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name

    def test_writes_interleaved_out_of_order_stay_apart(self):
        """B answers before A -- the case that cross-contaminated in the
        client. The store must make it impossible by construction."""
        C.create("shc-aaa111", "PROMPT A")
        C.create("shc-bbb222", "PROMPT B")
        C.append("shc-bbb222", "shadow", "ANSWER TO B")
        C.append("shc-aaa111", "shadow", "ANSWER TO A")
        self.assertEqual([m["text"] for m in C.load("shc-aaa111")["messages"]],
                         ["PROMPT A", "ANSWER TO A"])
        self.assertEqual([m["text"] for m in C.load("shc-bbb222")["messages"]],
                         ["PROMPT B", "ANSWER TO B"])


class TheMissionIsNamed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name

    def test_a_new_conversation_names_no_mission(self):
        self.assertIsNone(C.create("shc-aaa111", "Hi")["mission_id"])

    def test_an_actionable_one_names_the_mission_it_opened(self):
        C.create("shc-aaa111", "Pull the news")
        rec = C.bind_mission("shc-aaa111", "m-deadbeef")
        self.assertEqual(rec["mission_id"], "m-deadbeef")
        self.assertEqual(C.load("shc-aaa111")["mission_id"], "m-deadbeef")

    def test_a_bound_conversation_cannot_be_re_pointed(self):
        """The same rule the client follows for its threads: a later answer
        never re-points a conversation the founder has already read."""
        C.create("shc-aaa111", "Pull the news")
        C.bind_mission("shc-aaa111", "m-first")
        C.bind_mission("shc-aaa111", "m-second")
        self.assertEqual(C.load("shc-aaa111")["mission_id"], "m-first")

    def test_binding_an_unknown_conversation_is_an_error_not_a_new_one(self):
        with self.assertRaises(KeyError):
            C.bind_mission("shc-nosuch1", "m-deadbeef")


class TheCaps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name

    def test_one_message_is_clipped(self):
        C.create("shc-aaa111", "x")
        rec = C.append("shc-aaa111", "shadow", "y" * (C.MAX_TEXT + 500))
        self.assertEqual(len(rec["messages"][-1]["text"]), C.MAX_TEXT)

    def test_the_transcript_is_capped_and_keeps_the_opening_line(self):
        C.create("shc-aaa111", "THE OPENING LINE")
        for i in range(C.MAX_MESSAGES + 30):
            C.append("shc-aaa111", "shadow", "turn %d" % i)
        rec = C.load("shc-aaa111")
        self.assertLessEqual(len(rec["messages"]), C.MAX_MESSAGES)
        self.assertEqual(rec["messages"][0]["text"], "THE OPENING LINE",
                         "the line that names the conversation is pinned")

    def test_only_the_two_speakers_the_pane_draws(self):
        C.create("shc-aaa111", "x")
        with self.assertRaises(ValueError):
            C.append("shc-aaa111", "worker", "a third voice")


if __name__ == "__main__":
    unittest.main()
