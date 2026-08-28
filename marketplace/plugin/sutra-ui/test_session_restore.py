"""Archive and Delete said "is recoverable". Nothing could recover.

relocate() has always written a <name>.orig.json sidecar recording where the
transcript came from -- so recovery was intended -- and no code ever read it.
The confirm dialog's promise therefore meant "the bytes are still somewhere on
your disk", which is not what a person reads it as.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import session_reader as sr


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sutra-restore-"))
        self._proj, self._store = sr.PROJECTS, sr.SUTRA_STORE
        sr.PROJECTS = self.tmp / "projects"
        sr.SUTRA_STORE = self.tmp / "store"
        (sr.PROJECTS / "-a-project").mkdir(parents=True)

    def tearDown(self):
        sr.PROJECTS, sr.SUTRA_STORE = self._proj, self._store
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _session(self, sid="sess-1"):
        p = sr.PROJECTS / "-a-project" / (sid + ".jsonl")
        p.write_text(json.dumps({"type": "user", "cwd": "/x",
                                 "message": {"role": "user", "content": "hi"}}) + "\n",
                     encoding="utf-8")
        return p


class RestoreRoundTrip(Base):
    def test_archive_then_restore_puts_it_back(self):
        p = self._session()
        moved = sr.relocate("sess-1", "archive")
        self.assertIsNotNone(moved)
        self.assertFalse(p.exists(), "the original should be gone after archiving")

        rows = sr.relocated()
        self.assertEqual([r["session_id"] for r in rows], ["sess-1"])
        self.assertEqual(rows[0]["kind"], "archive")
        self.assertTrue(rows[0]["can_restore"])

        back = sr.restore("sess-1")
        self.assertEqual(back["restored_to"], str(p))
        self.assertTrue(p.exists(), "restore did not put the transcript back")
        self.assertEqual(sr.relocated(), [], "the sidecar should be consumed")

    def test_trash_is_restorable_too(self):
        p = self._session("sess-2")
        sr.relocate("sess-2", "trash")
        self.assertEqual(sr.relocated("trash")[0]["session_id"], "sess-2")
        self.assertIsNotNone(sr.restore("sess-2"))
        self.assertTrue(p.exists())

    def test_restore_refuses_to_overwrite(self):
        """A file already sitting at the original path could be a live
        conversation with the same id. Refuse rather than clobber it."""
        p = self._session("sess-3")
        sr.relocate("sess-3", "archive")
        p.write_text("something else\n", encoding="utf-8")
        self.assertIsNone(sr.restore("sess-3"))
        self.assertEqual(p.read_text(encoding="utf-8"), "something else\n")

    def test_unknown_id_is_none_not_an_exception(self):
        self.assertIsNone(sr.restore("never-existed"))

    def test_a_sidecar_without_its_transcript_is_not_offered(self):
        self._session("sess-4")
        moved = sr.relocate("sess-4", "archive")
        os.unlink(moved["moved_to"])          # body gone, sidecar remains
        self.assertEqual(sr.relocated(), [])

    def test_relocated_survives_a_corrupt_sidecar(self):
        self._session("sess-5")
        moved = sr.relocate("sess-5", "archive")
        Path(moved["moved_to"] + ".orig.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(sr.relocated(), [])   # skipped, not raised


if __name__ == "__main__":
    unittest.main(verbosity=2)
