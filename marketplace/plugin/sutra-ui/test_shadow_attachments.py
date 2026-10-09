"""Images the founder shows Shadow (founder, 2026-10-08).

  STORE     shadow_attachments: images only, by their bytes; size and count
            caps; ids that cannot name a path; never inside the workdir.
  FRAME     session_runtime.send_user_frame puts image blocks before the text;
            with none the frame is byte-identical to before.
  ROUTES    upload / serve; the Now chat and a task's chat SHOW the images to
            Shadow and keep them on the task; an answer to Shadow's question
            keeps them too, for its next decision.
  DECIDES   the brief writer and the decider see the images and their paths,
            are told to pass one on only when the work needs it, and are
            shown each image once.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_attachments.py
"""
import asyncio
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-att-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import session_runtime                         # noqa: E402
import shadow_attachments as att               # noqa: E402
import shadow_runner                           # noqa: E402
import shadow_task_chat                        # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 32
PDF = b"%PDF-1.4\n" + b"\x00" * 32


def b64(blob):
    return base64.b64encode(blob).decode("ascii")


def fence(objective):
    return "```mission\n" + json.dumps({
        "objective": objective, "template": "research", "target_mode": "new",
        "done_when": [{"tier": "judge", "check": "it is done"}]}) + "\n```"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = mission_engine.MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def image(self, blob=PNG, name="shot.png"):
        return att.save(name, b64(blob))


class TheStore(Base):

    def test_01_the_four_image_types_are_known_by_their_bytes(self):
        for blob, media in ((PNG, "image/png"), (JPG, "image/jpeg"),
                            (GIF, "image/gif"), (WEBP, "image/webp")):
            got = self.image(blob)
            self.assertEqual(got["media_type"], media)
            self.assertTrue(os.path.exists(got["path"]))

    def test_02_a_renamed_non_image_is_refused(self):
        with self.assertRaises(att.Refused):
            att.save("notes.png", b64(b"just some text, not a picture"))

    def test_03_empty_bad_and_too_big_are_refused(self):
        with self.assertRaises(att.Refused):
            att.save("x.png", "")
        with self.assertRaises(att.Refused):
            att.save("x.png", "@@not base64@@")
        orig = att.MAX_BYTES
        att.MAX_BYTES = 10
        try:
            with self.assertRaises(att.Refused):
                att.save("x.png", b64(PNG))
        finally:
            att.MAX_BYTES = orig

    def test_04_stored_in_the_shadow_home_never_the_workdir(self):
        got = self.image()
        self.assertTrue(got["path"].startswith(
            os.path.realpath(self.tmp.name)))
        self.assertIn("attachments", got["path"])

    def test_05_an_id_can_never_name_a_path(self):
        for bad in ("../../etc/passwd", "img-zz", "", None,
                    "img-0123456789abcdef/../x"):
            self.assertIsNone(att.path_of(bad), bad)

    def test_06_blocks_skip_unknown_ids(self):
        a = self.image()
        got = att.blocks([a["id"], "img-0000000000000000"])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], "image/png")
        self.assertEqual(base64.b64decode(got[0][1]), PNG)

    def test_07_valid_ids_dedupe_and_cap(self):
        a = self.image()
        self.assertEqual(att.valid_ids([a["id"], a["id"], "nope"]), [a["id"]])
        many = [self.image()["id"] for _ in range(att.MAX_PER_MESSAGE + 1)]
        with self.assertRaises(att.Refused):
            att.valid_ids(many)

    def test_08_link_records_where_it_came_from_and_whether_seen(self):
        a, b = self.image(), self.image()
        m = {}
        att.link(m, [a["id"]], "intake", {a["id"]: "design.png"})
        att.link(m, [b["id"]], "talk", shown=True)
        att.link(m, [a["id"]], "talk")              # already there
        self.assertEqual([(r["name"], r["source"], r["shown"])
                          for r in m["attachments"]],
                         [("design.png", "intake", False),
                          (b["id"], "talk", True)])

    def test_09_the_note_names_each_path(self):
        a = self.image()
        n = att.note([a["id"]], {a["id"]: "error.png"})
        self.assertIn("error.png (image) at %s" % a["path"], n)
        self.assertIn("Read tool", n)
        self.assertIn("only when the work needs it", n)
        self.assertEqual(att.note([]), "")


class PdfsAndTextFiles(Base):
    """founder, 2026-10-08: "add pdfs and text files too ... similar
    functionality". A PDF goes to Shadow as a document block; a text file's
    words go in the message."""

    def test_40_a_pdf_is_known_by_its_bytes_and_rides_as_a_block(self):
        got = att.save("spec.pdf", b64(PDF))
        self.assertEqual((got["kind"], got["media_type"]),
                         ("pdf", "application/pdf"))
        self.assertTrue(got["id"].startswith("att-"))
        self.assertEqual(att.blocks([got["id"]])[0][0], "application/pdf")

    def test_41_a_text_file_needs_an_allowed_name_and_real_text(self):
        got = att.save("notes.md", b64("# Plan\nShip it.".encode("utf-8")))
        self.assertEqual(got["kind"], "text")
        self.assertEqual(att.blocks([got["id"]]), [],
                         "text is not a block: its words go in the message")
        for name, blob in (("keys.env", b"SECRET=1"),
                           ("data.bin", b"abc"),
                           ("notes.txt", b"\xff\xfe\x00bad"),
                           ("notes.txt", b"with a nul \x00 byte")):
            with self.assertRaises(att.Refused, msg=name):
                att.save(name, b64(blob))

    def test_42_the_note_carries_a_text_files_words(self):
        got = att.save("plan.md", b64(b"Step 1: ship"))
        n = att.note([got["id"]], {got["id"]: "plan.md"})
        self.assertIn("plan.md (text) at ", n)
        self.assertIn("Step 1: ship", n)
        self.assertIn("--- end of plan.md ---", n)

    def test_43_a_long_text_file_is_cut_and_says_so(self):
        orig = att.INLINE_CHARS
        att.INLINE_CHARS = 10
        try:
            got = att.save("long.txt", b64(b"0123456789ABCDEFGHIJ"))
            n = att.note([got["id"]])
        finally:
            att.INLINE_CHARS = orig
        self.assertIn("0123456789\n", n)
        self.assertNotIn("ABCDEF", n)
        self.assertIn("only the first 10 characters", n)

    def test_44_a_decision_gives_shadow_the_words_of_an_unseen_text_file(self):
        got = att.save("brief.txt", b64(b"Use the blue logo."))
        m = self.store.create("Make the banner", "feature",
                              target_mode="new", done_when=[])
        att.link(m, [got["id"]], "answer", {got["id"]: "brief.txt"})
        self.store.save(m)
        chat = shadow_task_chat.TaskChat(m["id"])
        sent = []

        async def turn(prompt, timeout, images=None):
            sent.append((prompt, images))
            return '```json\n{"action": "continue", "instruction": "go"}\n```'
        chat._turn = turn
        eng = mission_engine.MissionEngine(self.store, None, None, None)
        asyncio.run(chat.decide(eng._decision_context(self.store.load(m["id"]), "")))
        self.assertIn("Use the blue logo.", sent[0][0])
        self.assertIsNone(sent[0][1], "no image or PDF to show")


class TheFrame(unittest.TestCase):

    def frame(self, *args, **kw):
        written = []

        class Stdin:
            def write(self, b):
                written.append(b)

            async def drain(self):
                return None

        class Proc:
            stdin = Stdin()

        rt = session_runtime.SessionRuntime()
        rt.proc = Proc()
        asyncio.run(rt.send_user_frame(*args, **kw))
        return json.loads(written[0].decode("utf-8"))

    def test_10_no_images_is_the_old_frame(self):
        self.assertEqual(self.frame("hello"), {
            "type": "user", "message": {"role": "user", "content": [
                {"type": "text", "text": "hello"}]}})

    def test_12_a_pdf_rides_as_a_document_block(self):
        got = self.frame("read this", images=[("application/pdf", "JVBERi0=")])
        self.assertEqual(got["message"]["content"][0]["type"], "document")
        self.assertEqual(got["message"]["content"][0]["source"]["media_type"],
                         "application/pdf")

    def test_11_images_come_first_then_the_text(self):
        got = self.frame("look", images=[("image/png", "QUJD")])
        content = got["message"]["content"]
        self.assertEqual(content[0], {"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": "QUJD"}})
        self.assertEqual(content[1], {"type": "text", "text": "look"})


class TheRoutes(Base):

    def setUp(self):
        super().setUp()
        self._saved = app_module._SHADOW.get("session")
        self.sent = []

    def tearDown(self):
        app_module._SHADOW["session"] = self._saved
        super().tearDown()

    def shadow_says(self, raw):
        sent = self.sent

        class Rt:
            async def send_user_frame(self, text, images=None):
                sent.append((text, images))

            async def demux_turn(self, collect, sid):
                await collect({"type": "token", "text": raw})
                return (sid or "shadow-sess", 0.0, True, None, None)

        class Sess:
            alive = True
            session_id = "shadow-sess"
            rt = Rt()
            carry_stamp = None

        app_module._SHADOW["session"] = Sess()

    def upload(self, blob=PNG, name="shot.png"):
        return self.client.post("/api/shadow/attachments", headers=HDR,
                                json={"name": name, "content_b64": b64(blob)})

    def test_20_upload_and_serve(self):
        r = self.upload()
        self.assertEqual(r.status_code, 200, r.text)
        doc = r.json()
        self.assertTrue(doc["id"].startswith("img-"))
        got = self.client.get(doc["url"])
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.headers["content-type"], "image/png")
        self.assertEqual(got.content, PNG)
        self.assertEqual(self.client.get(
            "/api/shadow/attachments/img-0000000000000000").status_code, 404)

    def test_21_an_unsupported_file_says_why(self):
        r = self.upload(b"PK\x03\x04 a zip, a docx", "doc.docx")
        self.assertEqual(r.status_code, 400)
        self.assertIn("only images, PDFs and text files", r.json()["detail"])

    def test_21b_a_text_file_is_served_as_plain_text_never_a_page(self):
        r = self.upload(b"<script>alert(1)</script>", "evil.html")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["kind"], "text")
        got = self.client.get(r.json()["url"])
        self.assertTrue(got.headers["content-type"].startswith("text/plain"))
        self.assertEqual(got.headers["x-content-type-options"], "nosniff")

    def test_21c_a_pdf_is_accepted_and_served_as_a_pdf(self):
        r = self.upload(PDF, "spec.pdf")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["kind"], r.json()["media_type"]),
                         ("pdf", "application/pdf"))
        got = self.client.get(r.json()["url"])
        self.assertEqual(got.headers["content-type"], "application/pdf")

    def test_22_the_now_chat_is_shown_the_image_and_its_task_keeps_it(self):
        img = self.upload().json()
        self.shadow_says("On it.\n" + fence("Match this design"))
        # intake starts the task; no real worker in a test
        real = shadow_runner.start_mission_async
        shadow_runner.start_mission_async = lambda *a, **k: None
        try:
            r = self.client.post("/api/shadow/chat", headers=HDR, json={
                "message": "build this", "intake": True,
                "attachments": [{"id": img["id"], "name": "design.png"}]})
        finally:
            shadow_runner.start_mission_async = real
        self.assertEqual(r.status_code, 200, r.text)
        text, images = self.sent[-1]
        self.assertEqual(images[0][0], "image/png", "Shadow SEES it")
        self.assertIn("design.png (image) at ", text)
        self.assertTrue(text.endswith("build this"))
        m = self.store.load(r.json()["mission"]["id"])
        self.assertEqual([(a["id"], a["source"], a["shown"])
                          for a in m["attachments"]],
                         [(img["id"], "intake", False)])

    def test_23_an_image_alone_is_a_message(self):
        img = self.upload().json()
        self.shadow_says("Nice photo.")
        r = self.client.post("/api/shadow/chat", headers=HDR, json={
            "message": "", "attachments": [img["id"]]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(self.sent[-1][0].endswith("(see the attached file)"))

    def test_24_no_images_sends_the_old_way(self):
        self.shadow_says("Hi.")
        self.client.post("/api/shadow/chat", headers=HDR,
                         json={"message": "hi"})
        self.assertIsNone(self.sent[-1][1])

    def test_25_a_tasks_chat_is_shown_it_and_marks_it_seen(self):
        img = self.upload().json()
        m = self.store.create("a task", "fix", target_mode="new",
                              done_when=[])
        self.store.transition(m["id"], "brief_confirm", "b")
        talked = []

        class Chat:
            async def talk(self, text, images=None):
                talked.append((text, images))
                return "Got it.", {}

        async def fake_chat(mission):
            return Chat()

        real = app_module._ensure_task_chat
        app_module._ensure_task_chat = fake_chat
        try:
            r = self.client.post("/api/shadow/tasks/%s/chat" % m["id"],
                                 headers=HDR, json={
                                     "message": "like this",
                                     "attachments": [img["id"]]})
        finally:
            app_module._ensure_task_chat = real
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(talked[0][1][0][0], "image/png")
        rows = self.store.load(m["id"])["attachments"]
        self.assertEqual((rows[0]["source"], rows[0]["shown"]),
                         ("talk", True), "this chat has seen it")

    def test_26_an_answer_keeps_its_images_for_the_next_decision(self):
        img = self.upload().json()
        m = self.store.create("a task", "fix", target_mode="new",
                              target_session="sess-1", done_when=[])
        mid = m["id"]
        self.store.transition(mid, "brief_confirm", "b")
        self.store.transition(mid, "running", "admitted")
        blocked = self.store.block(mid, "needs_founder", "which design?")
        blocked["intervention"] = mission_engine.shadow_intervention \
            .validate_request({"question": "Which design?", "fields": [
                {"key": "pick", "type": "text", "label": "Pick"}]})
        self.store.save(blocked)
        ivid = blocked["intervention"]["id"]
        launched = []
        real = shadow_runner._launch
        shadow_runner._launch = lambda m_, *a, **k: launched.append(m_)
        try:
            r = self.client.post("/api/shadow/missions/%s/act" % mid,
                                 headers=HDR, json={
                                     "action": "intervene",
                                     "intervention_id": ivid,
                                     "values": {"pick": "this one"},
                                     "attachments": [{"id": img["id"],
                                                      "name": "pick.png"}]})
        finally:
            shadow_runner._launch = real
        self.assertEqual(r.status_code, 200, r.text)
        m = self.store.load(mid)
        self.assertEqual(m["founder_response"]["attachments"],
                         [{"id": img["id"], "name": "pick.png"}])
        self.assertEqual((m["attachments"][0]["source"],
                          m["attachments"][0]["shown"]), ("answer", False))
        self.assertIn("1 file with the answer",
                      shadow_runner._founder_answer_text(
                          m["founder_response"]))


class ShadowDecides(Base):

    def mission_with(self, shown=False):
        a = self.image(name="design.png")
        m = self.store.create("Match this design", "feature",
                              target_mode="new", done_when=[])
        att.link(m, [a["id"]], "intake", {a["id"]: "design.png"}, shown=shown)
        self.store.save(m)
        return self.store.load(m["id"]), a

    def test_30_the_brief_writer_sees_unseen_images_and_their_paths(self):
        m, a = self.mission_with()
        facts = app_module._brief_facts(m)
        text = shadow_task_chat._facts_text(facts)
        self.assertIn("design.png: %s" % a["path"], text)
        self.assertIn("Pass one on ONLY when the work needs it",
                      " ".join(shadow_task_chat.BRIEF_ASK.split()))
        chat = shadow_task_chat.TaskChat(m["id"])
        seen = []

        async def turn(prompt, timeout, images=None):
            seen.append(images)
            return "```brief\nthe brief\n```"
        chat._turn = turn
        asyncio.run(chat.brief(m, facts))
        self.assertEqual(seen[0][0][0], "image/png")

    def test_31_a_seen_image_is_not_shown_again(self):
        m, _a = self.mission_with(shown=True)
        chat = shadow_task_chat.TaskChat(m["id"])
        seen = []

        async def turn(prompt, timeout, images=None):
            seen.append(images)
            return "```brief\nb\n```"
        chat._turn = turn
        asyncio.run(chat.brief(m, app_module._brief_facts(m)))
        self.assertIsNone(seen[0])

    def test_32_the_decider_lists_them_and_says_when_to_pass_one_on(self):
        m, a = self.mission_with()
        eng = mission_engine.MissionEngine(self.store, None, None, None)
        ctx = eng._decision_context(m, "")
        self.assertEqual(ctx["new_images"], [a["id"]])
        prompt = shadow_runner.render_decide_prompt(ctx)
        self.assertIn("FILES THE FOUNDER ATTACHED TO THIS TASK", prompt)
        self.assertIn(a["path"], prompt)
        self.assertIn("Never pass one on that the work does not need", prompt)

    def test_33_no_images_leaves_the_prompt_unchanged(self):
        m = self.store.create("plain", "fix", target_mode="new",
                              done_when=[])
        eng = mission_engine.MissionEngine(self.store, None, None, None)
        ctx = eng._decision_context(m, "")
        self.assertNotIn("images", ctx)
        self.assertNotIn("FILES THE FOUNDER", shadow_runner
                         .render_decide_prompt(ctx))

    def test_34_the_task_chat_decision_shows_new_images(self):
        m, a = self.mission_with()
        chat = shadow_task_chat.TaskChat(m["id"])
        seen = []

        async def turn(prompt, timeout, images=None):
            seen.append(images)
            return '```json\n{"action": "continue", "instruction": "go"}\n```'
        chat._turn = turn
        eng = mission_engine.MissionEngine(self.store, None, None, None)
        asyncio.run(chat.decide(eng._decision_context(m, "")))
        self.assertEqual(seen[0][0][0], "image/png")

    def test_35_after_a_decision_the_images_are_marked_seen(self):
        m, a = self.mission_with()
        self.store.transition(m["id"], "brief_confirm", "b")
        self.store.transition(m["id"], "running", "admitted")
        m = self.store.load(m["id"])
        m["turns_used"] = 1
        self.store.save(m)

        async def decider(ctx):
            return {"action": "continue", "instruction": "Open the design."}

        eng = mission_engine.MissionEngine(self.store, None, None, None,
                                           decider=decider)
        asyncio.run(eng._instruction(self.store.load(m["id"]), "ok"))
        rows = self.store.load(m["id"])["attachments"]
        self.assertTrue(rows[0]["shown"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
