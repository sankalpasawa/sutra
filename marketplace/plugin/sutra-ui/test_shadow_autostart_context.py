"""Shadow is never told the founder presses Start (founder, 2026-10-08:
"Start the task should never appear, shadow should start that kind of task on
its own"; 2026-10-09, Shadow told the founder "Press Start" for a task that
was already RUNNING, because SHADOW.md still said "The app spawns the worker
when the founder hits Start").

What Shadow reads at boot must say the task starts on its own, and must not
tell it to send the founder to a Start button.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_autostart_context.py
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def shadow_md():
    with open(os.path.join(HERE, "SHADOW.md"), encoding="utf-8") as fh:
        return fh.read()


class TheContext(unittest.TestCase):
    def test_01_it_says_the_task_starts_on_its_own(self):
        text = shadow_md()
        self.assertIn("THE TASK STARTS ON ITS OWN", text)
        self.assertIn("never ask them to press Start", text)

    def test_02_it_never_puts_the_start_on_the_founder(self):
        text = shadow_md()
        for bad in (r"when the founder (hits|presses|clicks) Start",
                    r"founder (hits|presses|clicks) Start",
                    r"press(es)? the Start button",
                    r"brief at Start\b"):
            self.assertIsNone(re.search(bad, text, re.I),
                              "SHADOW.md still says: %s" % bad)

    def test_03_a_task_that_cannot_start_says_so_itself(self):
        self.assertIn("CAN'T START", shadow_md())


if __name__ == "__main__":
    unittest.main()
