"""The server keeps a Shadow conversation (founder, 2026-10-09: a reply that
took minutes was lost when the page was refreshed -- "where's the SS, why
did the task not start").

  BEFORE    the founder's line, WITH its attachments, and a "Shadow is
            answering" mark are written before the turn starts.
  AFTER     the reply is written by the server when it lands -- whether or
            not the page is still open -- the task it opened is bound, and
            the mark is cleared. A failed turn says so in the conversation.
  NOT ASKED no conversation id: nothing written, exactly as before.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_conversation_saved.py
"""
import os
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-convsave-")

from fastapi import HTTPException              # noqa: E402
from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import providers                               # noqa: E402
import shadow_conversations as conv            # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
CID = "shc-convsave01"


class Base(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app_module.app, base_url="http://127.0.0.1")
        self.saved = (providers.shadow_enabled, app_module._shadow_chat_turn)
        providers.shadow_enabled = lambda: True
        self.seen = []
        try:
            conv.delete(CID)
        except Exception:
            pass

    def tearDown(self):
        providers.shadow_enabled, app_module._shadow_chat_turn = self.saved

    def turn(self, out=None, raises=None):
        async def fake(body):
            # what a reload DURING the turn would read
            self.seen.append(conv.load(CID))
            if raises is not None:
                raise raises
            return dict(out or {"reply": "Here are my suggestions."})
        app_module._shadow_chat_turn = fake

    def post(self, **body):
        return self.client.post("/api/shadow/chat", json=body, headers=HDR)


class Saved(Base):
    def test_01_the_opening_line_keeps_its_screenshots_and_the_reply_lands(self):
        conv.create(CID, "make the chat better")      # what Enter wrote
        self.turn()
        r = self.post(message="make the chat better", conversation_id=CID,
                      conversation_new=True,
                      attachments=[{"id": "img-0000000000000001",
                                    "name": "ui.png", "kind": "image"}])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["saved"])
        rec = conv.load(CID)
        self.assertEqual([m["who"] for m in rec["messages"]],
                         ["founder", "shadow"], "no duplicate opening line")
        self.assertEqual(rec["messages"][0]["images"][0]["name"], "ui.png")
        self.assertEqual(rec["messages"][1]["text"], "Here are my suggestions.")
        self.assertNotIn("pending_since", rec)

    def test_02_during_the_turn_a_reload_sees_the_line_and_the_mark(self):
        conv.create(CID, "first")
        self.turn()
        self.post(message="and the Shadow UI too", conversation_id=CID)
        during = self.seen[0]
        self.assertIn("pending_since", during)
        self.assertEqual(during["messages"][-1]["text"], "and the Shadow UI too")

    def test_03_a_conversation_the_enter_write_missed_is_created(self):
        self.turn()
        self.post(message="hello", conversation_id=CID, conversation_new=True)
        rec = conv.load(CID)
        self.assertEqual([m["text"] for m in rec["messages"]],
                         ["hello", "Here are my suggestions."])

    def test_04_a_task_it_opened_is_bound(self):
        conv.create(CID, "do it")
        self.turn({"reply": "Starting.", "mission": {"id": "m-abc123"}})
        self.post(message="do it", conversation_id=CID, conversation_new=True)
        self.assertEqual(conv.load(CID)["mission_id"], "m-abc123")

    def test_05_a_failed_turn_says_so_and_clears_the_mark(self):
        conv.create(CID, "q")
        self.turn(raises=HTTPException(502, "shadow turn failed: boom"))
        r = self.post(message="q", conversation_id=CID, conversation_new=True)
        self.assertEqual(r.status_code, 502)
        rec = conv.load(CID)
        self.assertIn("I couldn't answer that", rec["messages"][-1]["text"])
        self.assertNotIn("pending_since", rec)

    def test_06_no_conversation_named_means_nothing_written(self):
        self.turn()
        r = self.post(message="hi")
        self.assertNotIn("saved", r.json())
        self.assertIsNone(conv.load(CID))
        r = self.post(message="hi", conversation_id="../etc")
        self.assertNotIn("saved", r.json(), "a bad id is ignored")


class Store(unittest.TestCase):
    def setUp(self):
        try:
            conv.delete(CID)
        except Exception:
            pass
        conv.create(CID, "open")

    def test_10_images_keep_id_name_kind_and_at_most_six(self):
        rec = conv.append(CID, "founder", "x", [{"id": "img-%016d" % i,
                                                 "name": "n", "kind": "pdf",
                                                 "extra": "dropped"}
                                                for i in range(9)])
        imgs = rec["messages"][-1]["images"]
        self.assertEqual(len(imgs), 6)
        self.assertEqual(set(imgs[0]), {"id", "name", "kind"})

    def test_11_images_go_on_the_opening_line_once(self):
        conv.append(CID, "shadow", "reply")
        conv.add_images_to_opening(CID, [{"id": "img-a"}])
        conv.add_images_to_opening(CID, [{"id": "img-b"}])
        rec = conv.load(CID)
        self.assertEqual(rec["messages"][0]["images"][0]["id"], "img-a")
        self.assertNotIn("images", rec["messages"][1])

    def test_12_the_mark_comes_and_goes(self):
        self.assertIn("pending_since", conv.set_pending(CID, True))
        self.assertNotIn("pending_since", conv.set_pending(CID, False))


if __name__ == "__main__":
    unittest.main()
