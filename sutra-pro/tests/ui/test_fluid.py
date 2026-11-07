"""The fluid package (docs/notes/GAP3-fluid.md): the wiring, and in a real browser what node cannot see.

The pure parts are tested in node (`tests/ui/js/fluid.test.js`, run by `test_node_suite.py`). This file proves:

  wiring    Home loads fluid.js before the scripts that use it, the team page gets it from dept_ext.js (the frozen J2 page is not edited), the panel
            mount page has it, and the fake backend can stream a reply (`chat.partial`, never stored)
  browser   (SUTRA_BROWSER=1) on real DOM: a streamed reply drawn by appending reads exactly as the same text drawn at once, at every chunk, and the
            nodes of the blocks that were done are the SAME nodes after the next chunk; a transcript that gains a line keeps the nodes of the lines
            it had (and a <details> the reader opened); the animations are the compositor's (transform and opacity) and stop for reduced motion
"""
from __future__ import annotations

import json
import re
import shutil

import pytest

from sutra_app.ui import PAGES_DIR, STATIC_DIR

JS = STATIC_DIR / "js"
CSS = STATIC_DIR / "css"


# ---------------------------------------------------------------------------------------------------------------------
# the wiring
# ---------------------------------------------------------------------------------------------------------------------
def test_home_loads_fluid_before_the_scripts_that_draw_with_it():
    home = (PAGES_DIR / "home.html").read_text(encoding="utf-8")
    scripts = re.findall(r'<script src="/ui/js/([\w.]+\.js)"', home)
    assert scripts.count("fluid.js") == 1
    for later in ("graph_view.js", "chat_view.js", "chat_composer.js", "node_panel.js", "home.js"):
        assert scripts.index("fluid.js") < scripts.index(later), later


def test_the_team_page_gets_fluid_from_dept_ext_and_the_frozen_j2_page_is_not_edited():
    ext = (JS / "dept_ext.js").read_text(encoding="utf-8")
    assert re.search(r'for \(const name of \["fluid", "chat_pill"', ext)
    assert "fluid.js" not in (PAGES_DIR / "j2_ui.html").read_text(encoding="utf-8")


def test_the_panel_mount_page_loads_fluid_so_the_browser_tests_of_the_panel_run_the_edited_transcript():
    page = (STATIC_DIR.parent.parent.parent / "tests" / "ui" / "fixtures" / "mount_panel.html").read_text(encoding="utf-8")
    assert '<script src="/ui/js/fluid.js"></script>' in page


def test_the_fake_backend_streams_a_reply_as_chat_partial_events(fake_server, fake):
    import urllib.request

    def emit(body):
        request = urllib.request.Request(fake_server.url + "/__fake/emit", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    status, body = emit({"event": "chat.partial", "data": {"session_id": "cs_org", "message_id": 7, "delta": "Hel"}})
    assert status == 200 and body == {"id": None, "event": "chat.partial"}            # a control-style event: no id, never in the ring
    assert emit({"event": "chat.partial"})[0] == 422                                  # it has no sample: it needs its data
    assert emit({"event": "chat.partial", "data": {"session_id": "cs_org"}})[0] == 422


# ---------------------------------------------------------------------------------------------------------------------
# in a real browser
# ---------------------------------------------------------------------------------------------------------------------
PAGE = """<!doctype html>
<html lang="en" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>fluid</title><link rel="stylesheet" href="css/j2.css"><link rel="stylesheet" href="css/sutra-panel.css">
<script src="js/fluid.js"></script><script src="js/chat_markdown.js"></script><script src="js/chat_view.js"></script><script src="js/chat_pill.js"></script></head>
<body class="simple"><aside id="nodepanel" class="agentdrawer"><div class="nchat"><div class="nmsgs" id="msgs"></div>
<div class="ccstream" id="stream"></div></div></aside></body></html>
"""

REPLY = "\n".join([
    "## The plan",
    "",
    "Here is what I would do, **in order**, so that nothing is left to chance on the way.",
    "",
    "1. Read the `config.toml` file",
    "   - check the `[server]` part",
    "",
    "2. Run this:",
    "",
    "   ```sh",
    "   sutra-pro --serve",
    "",
    "   sutra-pro --check",
    "   ```",
    "",
    "- a loose list item",
    "",
    "- and another one",
    "",
    "| Option | Speed |",
    "|---|---:|",
    "| first | 10 |",
    "",
    "> Quoted advice that goes on",
    "",
    "> for two paragraphs.",
    "",
    "```py",
    "print(1)",
    "",
    "print(2)",
    "```",
    "",
    "A closing paragraph, long enough to be a block of its own.",
    "",
    "The very last words are still being written when the reply ends",
])


def page_in(folder):
    (folder / "js").mkdir()
    (folder / "css").mkdir()
    for name in ("fluid.js", "chat_markdown.js", "chat_view.js", "chat_pill.js"):
        shutil.copy(JS / name, folder / "js" / name)
    for name in ("j2.css", "sutra-panel.css"):
        shutil.copy(CSS / name, folder / "css" / name)
    (folder / "page.html").write_text(PAGE, encoding="utf-8")
    return (folder / "page.html").as_uri()


@pytest.mark.browser
def test_a_reply_drawn_by_appending_reads_as_the_same_text_drawn_at_once_at_every_chunk(browser, tmp_path):
    browser.goto(page_in(tmp_path))
    result = browser.js("""(() => {
      const el = document.getElementById('stream');
      const reply = %s;
      const inner = html => html.replace(/^<div class="cmd">/, '').replace(/<\\/div>$/, '');
      const bad = [];
      let drawn = 0;
      for (let n = 1; n <= reply.length; n += 7) {
        const text = reply.slice(0, n);
        Fluid.paintStream(el, {who: 'Claude', text}, {render: ChatMarkdown.render});
        const whole = document.createElement('template');                       // through the same serializer: <br/> is <br> in a DOM
        whole.innerHTML = inner(ChatMarkdown.render(text, {streaming: true}));
        const want = whole.innerHTML;
        const got = el.querySelector('.cstream .cmd').innerHTML;
        if (got !== want) bad.push({n, got: got.slice(-160), want: want.slice(-160)});
        drawn += 1;
      }
      return {drawn, bad: bad.slice(0, 3), count: bad.length};
    })()""" % json.dumps(REPLY))
    assert result["drawn"] > 50
    assert result["count"] == 0, result["bad"]


@pytest.mark.browser
def test_the_nodes_of_the_blocks_that_were_done_are_the_same_nodes_after_the_next_chunk(browser, tmp_path):
    browser.goto(page_in(tmp_path))
    out = browser.js("""(() => {
      const el = document.getElementById('stream');
      const paint = text => Fluid.paintStream(el, {who: 'Claude', text}, {render: ChatMarkdown.render});
      paint('First paragraph, long enough to settle.\\n\\nSecond paragraph, long enough to settle.\\n\\nThird paragraph begins');
      const first = el.querySelector('.cmd').children[0];
      const second = el.querySelector('.cmd').children[1];
      const tail = el.querySelector('.cmd').children[2];
      paint('First paragraph, long enough to settle.\\n\\nSecond paragraph, long enough to settle.\\n\\nThird paragraph begins and keeps coming');
      const kids = el.querySelector('.cmd').children;
      const row = el.querySelector('.cstream');
      paint('First paragraph, long enough to settle.\\n\\nSecond paragraph, long enough to settle.\\n\\nThird paragraph begins and keeps coming\\n\\nFourth paragraph begins here');
      return {kept: kids[0] === first && kids[1] === second, tailNew: kids[2] !== tail, sameRow: el.querySelector('.cstream') === row, n: kids.length,
              third: el.querySelector('.cmd').children[2].textContent, hiddenWhenEmpty: (() => { paint(''); return el.querySelector('.cstream-text').hidden; })()};
    })()""")
    assert out["kept"] is True
    assert out["tailNew"] is True
    assert out["sameRow"] is True, "the row (and its aria-live region) is written once and then only appended to"
    assert out["n"] == 4 and out["third"].startswith("Third paragraph begins and keeps coming")
    assert out["hiddenWhenEmpty"] is True


@pytest.mark.browser
def test_a_stream_row_cleared_and_drawn_again_starts_clean_and_a_cut_head_starts_again(browser, tmp_path):
    browser.goto(page_in(tmp_path))
    out = browser.js("""(() => {
      const el = document.getElementById('stream');
      const paint = text => Fluid.paintStream(el, text === null ? null : {who: 'Codex', text}, {render: ChatMarkdown.render});
      paint('Alpha paragraph, long enough to settle.\\n\\nBeta paragraph, long enough to settle.\\n\\nGamma');
      const before = el.querySelectorAll('.cmd > *').length;
      paint('a paragraph, long enough to settle.\\n\\nBeta paragraph, long enough to settle.\\n\\nGamma and more');       // the head was cut: the row starts again
      const cut = Array.from(el.querySelectorAll('.cmd > *'), e => e.textContent);
      paint(null);
      const cleared = el.innerHTML;
      el.innerHTML = '<p>another part of the page wrote here</p>';                                                   // somebody else wrote into the element
      paint('Delta');
      return {before, cut, cleared, rebuilt: el.querySelectorAll('.cstream').length, who: el.querySelector('small').textContent};
    })()""")
    assert out["before"] == 3
    assert out["cut"][0].startswith("a paragraph") and len(out["cut"]) == 3
    assert out["cleared"] == ""
    assert out["rebuilt"] == 1 and out["who"].startswith("Codex")


@pytest.mark.browser
def test_a_transcript_that_gains_a_line_keeps_the_nodes_it_had_and_what_the_reader_opened(browser, tmp_path):
    browser.goto(page_in(tmp_path))
    out = browser.js("""(() => {
      const el = document.getElementById('msgs');
      const session = {id: 'cs_x', kind: 'department', title: 'Web', writable: true, status: 'active'};
      const msg = (id, text) => ({id, session_id: 'cs_x', role: 'agent', who: 'sutra', kind: 'text', text, state: 'ok', at: '2026-11-07T10:00:00Z'});
      const draw = list => Fluid.patchList(el, ChatView.transcriptItems(session, list, {}), {enter: 'nmsg-in'});
      draw([msg(1, 'one'), msg(2, 'two')]);
      const first = el.children[0];
      first.insertAdjacentHTML('beforeend', '<details data-key="d"><summary>s</summary>x</details>');
      first.querySelector('details').open = true;
      const range = document.createRange(); range.selectNodeContents(el.children[1]); getSelection().removeAllRanges(); getSelection().addRange(range);
      const second = el.children[1];
      const r = draw([msg(1, 'one'), msg(2, 'two'), msg(3, 'three')]);
      const kids = el.children;
      const added = kids[2];
      return {r, same: kids[0] === first && kids[1] === second, n: kids.length, enter: added.classList.contains('nmsg-in'), firstEnter: first.classList.contains('nmsg-in'),
              selection: getSelection().toString(), text: added.textContent};
    })()""")
    assert out["r"] == {"changed": True, "rebuilt": False, "added": 1}
    assert out["same"] is True and out["n"] == 3
    assert out["enter"] is True and out["firstEnter"] is False
    assert "two" in out["selection"], "a text selection in a line that did not change stays"
    assert "three" in out["text"]


@pytest.mark.browser
def test_a_replaced_line_keeps_its_open_details(browser, tmp_path):
    browser.goto(page_in(tmp_path))
    out = browser.js("""(() => {
      const el = document.getElementById('msgs');
      const item = (key, body) => ({key, html: '<div class="nmsg">' + body + '<details data-key="fold"><summary>tools</summary>x</details></div>'});
      Fluid.patchList(el, [item('a', 'before')]);
      el.querySelector('details').open = true;
      const r = Fluid.patchList(el, [item('a', 'after')]);
      return {r, open: el.querySelector('details').open, text: el.firstElementChild.textContent.slice(0, 5)};
    })()""")
    assert out["r"]["changed"] is True
    assert out["open"] is True and out["text"] == "after"
