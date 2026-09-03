"""test_chat_store.py -- the segmented chat record (GAME-PLAN-provider-switch piece 1).

Every test runs against a temp store via SUTRA_UI_CHATS so the founder's real
~/.sutra-ui/chats is never touched -- including test_legacy_record_upgrades,
which reconstructs the on-disk shape of the two records written 2026-09-01
rather than reading them.
"""
import json
import os
import shutil
import tempfile
import unittest

import chat_store


class ChatStoreTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sutra-chats-")
        self._prev = os.environ.get("SUTRA_UI_CHATS")
        os.environ["SUTRA_UI_CHATS"] = self.tmp

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("SUTRA_UI_CHATS", None)
        else:
            os.environ["SUTRA_UI_CHATS"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------- basics --

    def test_create_roundtrips(self):
        rec = chat_store.create(cwd="/tmp/x", branch="main", title="t")
        got = chat_store.load(rec["sutra_id"])
        self.assertIsNotNone(got)
        self.assertEqual(got["cwd"], "/tmp/x")
        self.assertEqual(got["provider_history"], [])
        self.assertEqual(got["messages"], [])

    def test_store_dir_is_private(self):
        chat_store.create()
        mode = os.stat(self.tmp).st_mode & 0o777
        self.assertEqual(mode, 0o700, "chat store must not be group/world readable")

    def test_unsafe_id_never_reaches_the_filesystem(self):
        """`sutra_id` comes from the browser on every read endpoint."""
        for bad in ("../../etc/passwd", "abc", "", None, "A" * 32, "g" * 32,
                    "../" + "a" * 29):
            self.assertIsNone(chat_store.load(bad), "%r must not load" % (bad,))

    def test_save_refuses_a_bad_id(self):
        with self.assertRaises(ValueError):
            chat_store.save({"sutra_id": "nope"})

    # -------------------------------------------------------------- blocks --

    def test_typed_blocks_survive_a_roundtrip(self):
        rec = chat_store.create()
        rec = chat_store.begin_segment(rec, "claude", "sess-1")
        rec = chat_store.append_turn(rec, "user", [chat_store.block_text("hi")])
        rec = chat_store.append_turn(rec, "assistant", [
            chat_store.block_thinking("hmm"),
            chat_store.block_tool_use("Read", {"file_path": "/a"}, "tu_1"),
            chat_store.block_tool_result("contents", "tu_1"),
            chat_store.block_text("done"),
        ])
        got = chat_store.load(rec["sutra_id"])
        kinds = [b["type"] for b in got["messages"][1]["blocks"]]
        self.assertEqual(kinds, ["thinking", "tool_use", "tool_result", "text"])
        self.assertEqual(got["messages"][1]["blocks"][1]["input"],
                         {"file_path": "/a"})

    def test_unknown_block_types_are_dropped_at_write(self):
        rec = chat_store.create()
        rec = chat_store.append_turn(rec, "user", [
            {"type": "text", "text": "keep"},
            {"type": "wormhole", "payload": "drop"},
            "not-a-dict",
        ])
        got = chat_store.load(rec["sutra_id"])
        self.assertEqual([b["type"] for b in got["messages"][0]["blocks"]], ["text"])

    def test_empty_assistant_turn_is_preserved(self):
        """A tool-only turn has no prose and must not vanish."""
        rec = chat_store.create()
        rec = chat_store.append_turn(rec, "assistant", [chat_store.block_text("")])
        got = chat_store.load(rec["sutra_id"])
        self.assertEqual(len(got["messages"]), 1)
        self.assertEqual(got["messages"][0]["blocks"][0]["text"], "")

    # -------------------------------------------------------------- legacy --

    def test_legacy_record_upgrades_on_read(self):
        """The 2026-09-01 on-disk shape: messages as {role, text, ts}."""
        sid = "184b4cffae754faab4dd49d6442eff34"
        legacy = {
            "sutra_id": sid, "title": "old", "cwd": "", "branch": "",
            "created": "2026-09-01T08:54:00+05:30",
            "updated": "2026-09-01T08:54:00+05:30",
            "provider_history": [{"provider": "deepseek",
                                  "native_id": "39b53c22", "from_turn": 0}],
            "messages": [{"role": "user", "text": "q", "ts": "t0"},
                         {"role": "assistant", "text": "a", "ts": "t1"}],
        }
        os.makedirs(self.tmp, exist_ok=True)
        with open(os.path.join(self.tmp, sid + ".json"), "w") as fh:
            json.dump(legacy, fh)

        got = chat_store.load(sid)
        self.assertEqual(len(got["messages"]), 2)
        self.assertEqual(got["messages"][0]["blocks"], [{"type": "text", "text": "q"}])
        self.assertEqual(got["provider_history"][0]["provider"], "deepseek")

    def test_upgrade_does_not_rewrite_the_file(self):
        """A read-time upgrade must not touch a record it may have misparsed."""
        sid = "6309d7c9ee784aabb62019512c93ab37"
        raw = {"sutra_id": sid, "messages": [{"role": "user", "text": "q", "ts": "t"}],
               "provider_history": []}
        p = os.path.join(self.tmp, sid + ".json")
        os.makedirs(self.tmp, exist_ok=True)
        with open(p, "w") as fh:
            json.dump(raw, fh)
        with open(p) as fh:
            before = fh.read()
        chat_store.load(sid)
        with open(p) as fh:
            self.assertEqual(fh.read(), before)

    def test_mixed_shape_record_reads(self):
        """Legacy turns followed by typed ones is a normal case, not a repair."""
        sid = "0" * 32
        raw = {"sutra_id": sid, "provider_history": [], "messages": [
            {"role": "user", "text": "legacy", "ts": "t0"},
            {"role": "assistant", "ts": "t1",
             "blocks": [{"type": "text", "text": "typed"}]},
        ]}
        os.makedirs(self.tmp, exist_ok=True)
        with open(os.path.join(self.tmp, sid + ".json"), "w") as fh:
            json.dump(raw, fh)
        got = chat_store.load(sid)
        self.assertEqual(got["messages"][0]["blocks"][0]["text"], "legacy")
        self.assertEqual(got["messages"][1]["blocks"][0]["text"], "typed")

    # ------------------------------------------------------------ segments --

    def test_provider_history_after_50_turns_and_a_switch(self):
        """The founder's scenario: 50 Claude turns, then DeepSeek owns turn 50."""
        rec = chat_store.create()
        rec = chat_store.begin_segment(rec, "claude", "claude-sess")
        for i in range(50):
            rec = chat_store.append_turn(rec, "user", [chat_store.block_text("q%d" % i)])
            rec = chat_store.append_turn(rec, "assistant", [chat_store.block_text("a%d" % i)])

        self.assertEqual(chat_store.turn_count(rec), 50)
        rec = chat_store.begin_segment(rec, "deepseek", "ds-sess")

        hist = chat_store.load(rec["sutra_id"])["provider_history"]
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0], {"provider": "claude", "native_id": "claude-sess",
                                   "from_turn": 0})
        self.assertEqual(hist[1], {"provider": "deepseek", "native_id": "ds-sess",
                                   "from_turn": 50})

    def test_turn_count_counts_user_turns_only(self):
        rec = chat_store.create()
        rec = chat_store.append_turn(rec, "user", [chat_store.block_text("a")])
        rec = chat_store.append_turn(rec, "assistant", [chat_store.block_text("b")])
        self.assertEqual(chat_store.turn_count(rec), 1)

    def test_begin_segment_is_idempotent(self):
        """A browser reconnect re-binds the live session; that is not a switch."""
        rec = chat_store.create()
        rec = chat_store.begin_segment(rec, "claude", "s1")
        rec = chat_store.begin_segment(rec, "claude", "s1")
        rec = chat_store.begin_segment(rec, "claude", "s1")
        self.assertEqual(len(rec["provider_history"]), 1)
        self.assertFalse(chat_store.switched(rec))

    def test_same_provider_new_session_is_a_new_segment(self):
        """A lost Claude session replaced by a fresh one still segments -- the
        replay boundary is the SESSION, not the vendor."""
        rec = chat_store.create()
        rec = chat_store.begin_segment(rec, "claude", "s1")
        rec = chat_store.append_turn(rec, "user", [chat_store.block_text("q")])
        rec = chat_store.begin_segment(rec, "claude", "s2")
        self.assertEqual(len(rec["provider_history"]), 2)
        self.assertEqual(rec["provider_history"][1]["from_turn"], 1)
        self.assertFalse(chat_store.switched(rec), "same vendor is not a switch")

    def test_begin_segment_rejects_unknown_provider_and_empty_id(self):
        rec = chat_store.create()
        with self.assertRaises(ValueError):
            chat_store.begin_segment(rec, "gemini", "s1")
        with self.assertRaises(ValueError):
            chat_store.begin_segment(rec, "claude", "")

    def test_segment_of_turn_maps_each_turn_to_its_owner(self):
        rec = chat_store.create()
        rec = chat_store.begin_segment(rec, "claude", "s1")
        for i in range(3):
            rec = chat_store.append_turn(rec, "user", [chat_store.block_text(str(i))])
        rec = chat_store.begin_segment(rec, "deepseek", "s2")
        rec = chat_store.append_turn(rec, "user", [chat_store.block_text("3")])

        self.assertEqual(chat_store.segment_of_turn(rec, 0)["provider"], "claude")
        self.assertEqual(chat_store.segment_of_turn(rec, 2)["provider"], "claude")
        self.assertEqual(chat_store.segment_of_turn(rec, 3)["provider"], "deepseek")
        self.assertTrue(chat_store.switched(rec))

    def test_message_carries_its_own_provenance(self):
        """Provenance is stamped on the message, so a later change to the
        segment list cannot rewrite who produced a turn."""
        rec = chat_store.create()
        rec = chat_store.begin_segment(rec, "claude", "s1")
        rec = chat_store.append_turn(rec, "user", [chat_store.block_text("q")])
        rec = chat_store.begin_segment(rec, "deepseek", "s2")
        rec = chat_store.append_turn(rec, "user", [chat_store.block_text("q2")])

        msgs = chat_store.load(rec["sutra_id"])["messages"]
        self.assertEqual(msgs[0]["provider"], "claude")
        self.assertEqual(msgs[1]["provider"], "deepseek")

    # --------------------------------------------------------------- index --

    def test_index_resolves_either_provider_to_one_chat(self):
        rec = chat_store.create()
        rec = chat_store.begin_segment(rec, "claude", "c-1")
        rec = chat_store.begin_segment(rec, "deepseek", "d-1")
        sid = rec["sutra_id"]
        self.assertEqual(chat_store.resolve("claude", "c-1"), sid)
        self.assertEqual(chat_store.resolve("deepseek", "d-1"), sid)
        self.assertIsNone(chat_store.resolve("claude", "nope"))
        self.assertIsNone(chat_store.resolve("", ""))

    def test_index_key_matches_the_on_disk_format(self):
        """The existing _index.json is keyed "deepseek:<uuid>"."""
        rec = chat_store.create()
        rec = chat_store.begin_segment(rec, "deepseek", "39b53c22-b37e")
        self.assertIn("deepseek:39b53c22-b37e", chat_store.index())

    def test_reindex_drops_rows_for_removed_segments(self):
        rec = chat_store.create()
        rec = chat_store.begin_segment(rec, "claude", "c-1")
        rec = chat_store.begin_segment(rec, "deepseek", "d-1")
        rec["provider_history"] = [rec["provider_history"][0]]
        chat_store.save(rec)
        self.assertEqual(chat_store.resolve("claude", "c-1"), rec["sutra_id"])
        self.assertIsNone(chat_store.resolve("deepseek", "d-1"),
                          "a dropped segment must not leave a dangling index row")

    def test_two_chats_do_not_collide_in_the_index(self):
        a = chat_store.begin_segment(chat_store.create(), "claude", "a-1")
        b = chat_store.begin_segment(chat_store.create(), "claude", "b-1")
        self.assertEqual(chat_store.resolve("claude", "a-1"), a["sutra_id"])
        self.assertEqual(chat_store.resolve("claude", "b-1"), b["sutra_id"])

    # ------------------------------------------------------------ contract --

    def test_providers_match_adapters(self):
        """SEGMENT_PROVIDERS duplicates providers.ADAPTERS on purpose (this
        module must not do PATH probing); this pins them together."""
        import providers
        self.assertEqual(set(chat_store.SEGMENT_PROVIDERS), set(providers.ADAPTERS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
