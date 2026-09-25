"""A DECISION box renders as the app's own callout, not as mono code
(founder, 2026-09-25).

THE LOOK THIS PINS. The readability gate writes every decision as a box of
box-drawing (or +---) characters, usually inside a fence. mdHtml turned that
into `<pre class="md-pre">`: mono text, literal borders, a dark well -- the one
element in the pane that matched nothing else. Now the fence branch (and a
run of unfenced box rows) whose content starts with `DECISION:` is lifted into
`fieldset.md-callout.md-callout-decision`: a thin --acc frame with the label
sitting on the border as the legend, no fill, --ink text (the founder's pick
from six token-only variants, 2026-09-25), with the box characters dropped
and the lines joined into prose. Nothing else changes: any other fence, box,
list or pipe row renders exactly as before, and the text stays esc()'d.

mdHtml lives in a browser file with no module system, so the checks run in
node against a slice of static/js/02-helpers.js. The driver is
tests/fixtures/md_decision_callout.js; this file only runs it and reports.

Run: .venv/bin/python -m pytest -q test_md_decision_callout.py
 or: python3 test_md_decision_callout.py -v
"""
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.join(HERE, "tests", "fixtures", "md_decision_callout.js")
CSS = (os.path.join(HERE, "static", "panel.css"),
       os.path.join(HERE, "static", "agents.css"))


def node_missing():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return False
    except (OSError, subprocess.CalledProcessError):
        return True


@unittest.skipIf(node_missing(), "node is not on PATH")
class TestDecisionCallout(unittest.TestCase):

    def test_01_renderer_checks_pass_under_node(self):
        p = subprocess.run(["node", DRIVER], capture_output=True, text=True,
                           timeout=30)
        self.assertEqual(p.returncode, 0,
                         "renderer checks failed:\n" + p.stdout + p.stderr)
        self.assertIn("all checks passed", p.stdout)

    def test_02_both_stylesheets_style_the_callout_on_tokens(self):
        """The class the renderer emits must exist in both the chat pane and
        the document reader, and must draw the frame on --acc and the radius
        on --r, never a raw colour or fill, so it follows the accent and the
        light/dark theme."""
        for css in CSS:
            with open(css, encoding="utf-8") as fh:
                text = fh.read()
            start = text.index(".md-callout{")
            block = text[start:text.index("}", start)]
            self.assertIn("border:1px solid var(--acc)", block, css)
            self.assertIn("var(--r)", block, css)
            self.assertIn("background:none", block, css)
            self.assertNotRegex(block, r"#[0-9a-fA-F]{3,8}\b", css)
            self.assertIn(".md-callout-k{", text, css)
            self.assertIn(".md-callout-b{", text, css)


if __name__ == "__main__":
    unittest.main(verbosity=2)
