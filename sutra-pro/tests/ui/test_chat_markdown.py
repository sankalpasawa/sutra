"""A model's direct reply drawn as markdown (package GAP-markdown; docs/design/ui.md section 4.3): the wiring and, in a real browser, the layout.

The renderer itself is tested in node (`tests/ui/js/chat_markdown.test.js`, run by `test_node_suite.py`). This file proves what node cannot see:

  wiring    Home loads chat_markdown.js once, before home.js; the team page gets it from dept_ext.js like the other chat scripts, so the frozen
            J2 page (`pages/j2_ui.html`) is not edited; sutra-panel.css has the rules the markup needs
  browser   (SUTRA_BROWSER=1) the real j2.css and sutra-panel.css on a phone-wide drawer: the reply resets J2's pre-wrap, a wide table and a long
            code line scroll inside the bubble and never the page, the stream row draws an open fence as code, no link and no image exist in
            the DOM, and the code box reads in both themes
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
def test_home_loads_the_renderer_once_and_before_the_scripts_that_draw_with_it():
    home = (PAGES_DIR / "home.html").read_text(encoding="utf-8")
    scripts = re.findall(r'<script src="/ui/js/([\w.]+\.js)"', home)
    assert scripts.count("chat_markdown.js") == 1
    assert scripts.index("chat_markdown.js") < scripts.index("chat_view.js") < scripts.index("home.js")
    assert (JS / "chat_markdown.js").is_file()


def test_the_team_page_gets_the_renderer_from_dept_ext_and_the_j2_page_is_not_edited():
    ext = (JS / "dept_ext.js").read_text(encoding="utf-8")
    injected = re.search(r"for \(const name of \[([^\]]*)\]\)", ext)
    assert injected and '"chat_markdown"' in injected.group(1)
    assert "chat_markdown" not in (PAGES_DIR / "j2_ui.html").read_text(encoding="utf-8")


def test_the_style_sheet_resets_the_bubble_and_lets_code_and_tables_scroll_in_place():
    css = (CSS / "sutra-panel.css").read_text(encoding="utf-8")
    rules = dict(re.findall(r"^([^{}\n/][^{}\n]*)\{([^}]*)\}", css, re.M))
    assert "white-space:normal" in rules[".cmd"]
    assert "overflow-x:auto" in rules[".cmd .cmd-tw"]
    assert "overflow:auto" in rules[".cmd .cmd-pre"] and "white-space:pre;" in rules[".cmd .cmd-pre"]
    assert "overflow-wrap:normal" in rules[".cmd .cmd-t th,.cmd .cmd-t td"]
    block = css[css.index(".cmd{"):css.index(".cmd del")]
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(", block) == []                   # J2's tokens only


# ---------------------------------------------------------------------------------------------------------------------
# in a real browser
# ---------------------------------------------------------------------------------------------------------------------
PAGE = """<!doctype html>
<html lang="en" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>markdown</title><link rel="stylesheet" href="css/j2.css"><link rel="stylesheet" href="css/sutra-panel.css">
<script src="js/chat_markdown.js"></script><script src="js/chat_view.js"></script><script src="js/chat_pill.js"></script></head>
<body class="simple"><aside id="nodepanel" class="agentdrawer"><div class="nchat"><div class="nmsgs" id="msgs"></div>
<div class="ccstream" id="stream"></div></div></aside></body></html>
"""

REPLY = "\n".join([
    "## The plan",
    "Here is what I would do, **in order**:",
    "1. Read the `config.toml` file",
    "   - check the `[server]` part",
    "2. Run this:",
    "   ```sh",
    "   " + "sutra-pro --a-very-long-flag-name=" + "x" * 240,
    "   ```",
    "",
    "| Option | Speed | Memory | Notes about it | More | Even more | Last |",
    "|---|---:|---:|---|---|---|---|",
    "| first-choice-with-a-long-name | 10 | 200 MB | " + "words " * 12 + "| a | b | c |",
    "",
    "> Quoted advice, and [a link](https://example.com) that stays text. ![img](https://example.com/x.png)",
])


def page_in(folder):
    (folder / "js").mkdir()
    (folder / "css").mkdir()
    for name in ("chat_markdown.js", "chat_view.js", "chat_pill.js"):
        shutil.copy(JS / name, folder / "js" / name)
    for name in ("j2.css", "sutra-panel.css"):
        shutil.copy(CSS / name, folder / "css" / name)
    (folder / "page.html").write_text(PAGE, encoding="utf-8")
    return (folder / "page.html").as_uri()


def draw(browser, theme):
    message = {"id": 7, "session_id": "cs_x", "role": "agent", "who": "sutra", "kind": "text", "text": REPLY, "state": "ok",
               "at": "2026-11-07T10:00:00Z", "turn": 6}
    session = {"id": "cs_x", "kind": "department", "title": "Web", "writable": True, "status": "active"}
    browser.js(f"document.documentElement.setAttribute('data-theme', {json.dumps(theme)});"
               f"document.getElementById('msgs').innerHTML = ChatView.transcript({json.dumps(session)}, [{json.dumps(message)}], {{}});"
               f"document.getElementById('stream').innerHTML = ChatPill.indicator({{active: true, text: 'Next:\\n```py\\nprint(1)'}}, 'claude'); true")


@pytest.mark.browser
def test_a_direct_reply_reads_as_formatted_text_and_nothing_scrolls_the_page_sideways(browser, tmp_path):
    browser.set_size(390, 800)
    browser.goto(page_in(tmp_path))
    draw(browser, "dark")
    js = browser.js
    assert js("document.querySelectorAll('#msgs .cmd ol > li').length") == 2
    assert js("document.querySelector('#msgs .cmd ol > li ul > li').textContent") == "check the [server] part"
    assert js("document.querySelector('#msgs .cmd h4').textContent") == "The plan"
    assert js("document.querySelectorAll('#msgs .cmd table th').length") == 7
    assert js("document.querySelectorAll('#msgs a, #msgs img, #stream a, #stream img').length") == 0
    assert js("getComputedStyle(document.querySelector('#msgs .nmsg.sb')).whiteSpace") == "pre-wrap"           # J2's bubble, as it was
    assert js("getComputedStyle(document.querySelector('#msgs .cmd')).whiteSpace") == "normal"
    assert js("getComputedStyle(document.querySelector('#msgs .cmd-pre')).whiteSpace") == "pre"
    # the long code line and the wide table scroll inside the bubble; the bubble stays in the drawer and the page does not scroll sideways
    assert js("(e => e.scrollWidth > e.clientWidth)(document.querySelector('#msgs .cmd-pre'))") is True
    assert js("(e => e.scrollWidth > e.clientWidth)(document.querySelector('#msgs .cmd-tw'))") is True
    assert js("document.querySelector('#msgs .nmsg.sb').getBoundingClientRect().right <= document.getElementById('nodepanel').getBoundingClientRect().right + 0.5") is True
    assert js("document.documentElement.scrollWidth <= innerWidth") is True
    assert js("document.getElementById('nodepanel').scrollWidth <= document.getElementById('nodepanel').clientWidth") is True
    # the streaming row: an unclosed fence is already a code box
    assert js("document.querySelector('#stream .cstream-text pre code').textContent") == "print(1)"
    assert js("document.querySelector('#stream .cstream-text p').textContent") == "Next:"
    assert browser.console_errors == []


@pytest.mark.browser
def test_the_code_box_and_the_table_header_read_in_both_themes(browser, tmp_path):
    browser.goto(page_in(tmp_path))
    seen = {}
    for theme in ("dark", "light"):
        draw(browser, theme)
        pre = browser.js("(s => [s.color, s.backgroundColor])(getComputedStyle(document.querySelector('#msgs .cmd-pre')))")
        th = browser.js("(s => [s.color, s.backgroundColor])(getComputedStyle(document.querySelector('#msgs .cmd-t th')))")
        assert pre[0] != pre[1] and th[0] != th[1]
        seen[theme] = pre[1]
    assert seen["dark"] != seen["light"]
    assert browser.console_errors == []
