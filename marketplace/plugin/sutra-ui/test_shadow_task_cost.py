"""A task's own Shadow chat costs less (founder, 2026-10-09: "0.47 dollars
for the simplest of simple tasks"; measured: the task chat was $0.33 of it,
all on the top model).

  MODEL   a task's Shadow chat runs on shadow_task_model() -- "sonnet" unless
          the task-limits key `shadow_model` or SUTRA_SHADOW_MODEL says
          otherwise ("default" = the CLI default) -- and without the skills
          catalog. The Now chat and every worker keep their argv exactly.
  MANUAL  SHADOW.md marks what only the Now chat uses; a task chat boots
          without it, and keeps everything a task needs. The Now chat reads
          the file exactly as written, markers and their note removed.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_task_cost.py
"""
import os
import re
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-taskcost-")

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_session                          # noqa: E402
import shadow_task_chat                        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def shadow_md():
    with open(os.path.join(HERE, "SHADOW.md"), encoding="utf-8") as fh:
        return fh.read()


class Model(unittest.TestCase):
    def setUp(self):
        self.saved_env = os.environ.pop("SUTRA_SHADOW_MODEL", None)
        self.saved = app_module._shadow_args
        app_module._shadow_args = lambda session_id=None, **k: (
            ["claude", "-p", "--effort", "xhigh"]
            + (["--resume", session_id] if session_id else []))
        import json_store
        json_store.write_json(mission_engine.limits_path(), {})

    def tearDown(self):
        app_module._shadow_args = self.saved
        if self.saved_env is not None:
            os.environ["SUTRA_SHADOW_MODEL"] = self.saved_env
        os.environ.pop("SUTRA_SHADOW_MODEL", None) if self.saved_env is None else None

    def test_01_a_task_chat_runs_on_sonnet_without_skills(self):
        args = app_module._task_shadow_args()
        self.assertEqual(args[args.index("--model") + 1], "sonnet")
        self.assertIn("--disable-slash-commands", args)

    def test_02_resume_keeps_its_session_and_the_model(self):
        args = app_module._task_shadow_args(session_id="sess-9")
        self.assertEqual(args[args.index("--resume") + 1], "sess-9")
        self.assertIn("--model", args)

    def test_03_the_setting_and_the_env_override_it(self):
        import json_store
        json_store.write_json(mission_engine.limits_path(),
                              {"shadow_model": "default"})
        self.assertNotIn("--model", app_module._task_shadow_args())
        json_store.write_json(mission_engine.limits_path(),
                              {"shadow_model": "haiku"})
        args = app_module._task_shadow_args()
        self.assertEqual(args[args.index("--model") + 1], "haiku")
        os.environ["SUTRA_SHADOW_MODEL"] = "opus"
        args = app_module._task_shadow_args()
        self.assertEqual(args[args.index("--model") + 1], "opus")

    def test_04_the_now_chat_and_workers_are_untouched(self):
        app_module._shadow_args = self.saved
        src = open(app_module.__file__, encoding="utf-8").read()
        start = src.index("def _shadow_args(")
        body = src[start:src.index("autocompact=autocompact)", start)]
        self.assertNotIn("--disable-slash-commands", body)
        self.assertNotIn("shadow_task_model()", body)
        worker = src[src.index("def _worker_args("):]
        worker = worker[:worker.index("\ndef ")]
        self.assertNotIn("_task_shadow_args", worker)

    def test_05_both_task_chat_launches_use_it(self):
        src = open(app_module.__file__, encoding="utf-8").read()
        self.assertIn("await chat.start(_task_shadow_args, _shadow_workdir(), "
                      "mission,", src)
        self.assertIn("chat.resume(lambda sid: _task_shadow_args(session_id=sid),",
                      src)
        self.assertNotIn("await chat.start(_shadow_args,", src)


class Manual(unittest.TestCase):
    def setUp(self):
        self.saved = providers.shadow_enabled
        providers.shadow_enabled = lambda: True

    def tearDown(self):
        providers.shadow_enabled = self.saved

    def test_10_markers_are_balanced_and_never_nested(self):
        depth = 0
        for tok in re.findall(r"<!-- (/?)now-only -->", shadow_md()):
            depth += -1 if tok else 1
            self.assertIn(depth, (0, 1), "nested or unopened now-only block")
        self.assertEqual(depth, 0, "an unclosed now-only block")

    def test_11_the_now_chat_reads_every_word(self):
        now = shadow_session.load_context()
        self.assertNotIn("now-only", now)
        stripped = re.sub(r"<!-- /?now-only -->\n?", "", shadow_md())
        for para in ("**Goals.**", "Delegation: when the founder asks",
                     "```module", "- Presence, per app"):
            self.assertIn(para, now)
        self.assertGreater(len(now), len(stripped) - 400,
                           "only the editor's note is removed")

    def test_12_a_task_chat_reads_what_a_task_needs_and_not_the_rest(self):
        task = shadow_session.load_context(scope="task")
        for need in ("## 1. Persona", "## 3. Precedence", "## 4. Conduct",
                     "```mission", "```limits", "```answer", "```remember",
                     "a task chat never proposes a second task",
                     "- Own copy", "- Files", "- Autonomy", "- Turn budget",
                     "**Answers (v4.2).**", "**Limits (v4.1).**",
                     "## 6. Two chats per task"):
            self.assertIn(need, task, need)
        for drop in ("**Goals.**", "Delegation: when the founder asks",
                     "```module", "```chips", "```goal",
                     "**Acting in the chat under discussion.**",
                     "- Presence, per app", "- Run limit", "- Restart:"):
            self.assertNotIn(drop, task, drop)
        self.assertLess(len(task), len(shadow_session.load_context()) * 0.85)

    def test_13_the_task_chat_asks_for_its_cut(self):
        seen = []
        saved = shadow_session.load_context

        def fake(scope="now"):
            seen.append(scope)
            return None
        shadow_session.load_context = fake
        try:
            import asyncio
            chat = shadow_task_chat.TaskChat("m-cut")
            with self.assertRaises(RuntimeError):
                asyncio.run(chat.start(lambda: [], ".", {"id": "m-cut"}))
        finally:
            shadow_session.load_context = saved
        self.assertEqual(seen, ["task"])


if __name__ == "__main__":
    unittest.main()
