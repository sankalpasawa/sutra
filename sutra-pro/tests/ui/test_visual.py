"""The visual matrix of the UI (UI-9, docs/design/ui.md section 10 "Visual checks"; S3-web-09, S3-web-10).

Runs only with SUTRA_BROWSER=1 (the gate skips it). Headless Chrome over CDP against the fake backend of UI-0, which mounts the real pages and the real
static files. Nine pages, four themes, three widths, one PNG each in `tests/ui/screens/` (its `.gitignore` holds `*`, so none is ever committed):

    pages    home-start, home-graph, home-chart, dept-simple, dept-detail-map, dept-graph, dept-orgchart, fnode-drawer, node-chat
    themes   light and dark (`localStorage j2theme`, set before the page's own scripts run), and system with the emulated
             `prefers-color-scheme` light and dark
    widths   1440, 900, 390

Each PNG file is `<page>__<theme>__<width>.png` with the theme `system-light` or `system-dark` for the two emulations. The automatic assertions, per file:
no console error and no failed request; `data-theme` is the expected word; `scrollWidth <= innerWidth` at 390 and 900; and a page-side audit of every
visible text of the new views (colour against the colour it is painted on, 4.5:1, 3:1 for large text) finds nothing. One finding is known and listed by
name in KNOWN_GAPS. The developer then opens the PNGs and writes one line per file in `tests/ui/screens/REVIEW.md` (also ignored).

One page is one test (one Chrome, four loads, twelve shots): a failure names the theme and the width it happened at.
"""
from __future__ import annotations

import json
import re
import time

import pytest

import cdp  # tests/ui is on sys.path (conftest.py)

browser_only = pytest.mark.browser

THEMES = (("light", "light", "light"), ("dark", "dark", "dark"), ("system-light", "system", "light"), ("system-dark", "system", "dark"))
WIDTHS = (1440, 900, 390)
HEIGHT = 900
SETTLE_S = 0.25                      # a resized graph or panel repaints on the next frame; the shot waits for it
PILL_404 = "status of 404"           # the console line of a 404 (it does not name the URL): the fake serves no `/api/chats/{sid}/providers` (pre-existing, announced below)

# The graph box of a filed node paints a 14 % green over --panel and J2's --muted second line on it reads 4.2:1 in the dark set (UI-4 owns
# graph_render.js and sutra-graph.css; docs/notes/UI-9.md). It is the one finding of the audit that is allowed, and only in the dark theme.
KNOWN_GAPS = {("dark", "tsub", "st-filed")}
MIN_RATIO = 4.0                      # a known gap must still be close to its recorded value: a worse one is a new finding

# page -> (stage of the fake's story, url, the expression that says the page is drawn, expression run after that (or ""), where the audit looks)
HOME_SCOPE = "body"
TEAM_SCOPE = "#pane-graph, #pane-orgchart, #nodepanel, #deptchip, .tabs, #to-home"
PAGE_SCOPE = "body"                  # J2's own views are audited whole: the new chip, tabs and chips sit among J2's text and must read next to it
PAGES = {
    "home-start": ("1", "/", "window.HomePage && HomePage.state().loaded === true", "", HOME_SCOPE),
    "home-graph": ("full", "/?pane=graph", "!!document.querySelector('#pane-graph .wnode')", "", HOME_SCOPE),
    "home-chart": ("full", "/?pane=chart", "!!document.querySelector('#pane-chart .wnode')", "", HOME_SCOPE),
    "dept-simple": ("full", "/d/web/?view=simple", "window.DeptExt && DeptExt.state().started === true && !!document.querySelector('[data-agent=identity]')", "", PAGE_SCOPE),
    "dept-detail-map": ("full", "/d/web/?view=detail", "window.DeptExt && DeptExt.state().started === true && !!document.querySelector('.tabs [data-tab=map]')", "", PAGE_SCOPE),
    "dept-graph": ("full", "/d/web/?tab=graph", "document.querySelectorAll('#pane-graph g.wnode').length > 0", "", TEAM_SCOPE),
    "dept-orgchart": ("full", "/d/web/?tab=orgchart", "document.querySelectorAll('#pane-orgchart .chgrow').length > 0", "", TEAM_SCOPE),
    "fnode-drawer": ("full", "/?pane=graph", "!!document.querySelector('#pane-graph .wnode') && !!HomePage.state().panel",
                     "HomePage.state().panel.open('web.identity', 'details')", HOME_SCOPE),
    "node-chat": ("full", "/?pane=graph", "!!document.querySelector('#pane-graph .wnode') && !!HomePage.state().panel",
                  "HomePage.state().panel.open('web.identity', 'chat')", HOME_SCOPE),
}
AFTER_OPEN = {"fnode-drawer": "!!document.querySelector('.fndetail .atomcard')", "node-chat": "!!document.querySelector('.nchat .nmsg')"}

# The page-side audit. For every visible element of `scope` that owns a text node it reads the painted colour of the text and the colour under it
# (the nearest opaque background up the tree, alpha composited; for the text of an SVG box, the fill of the box's own rectangle), and returns
# {measured, skipped, failures}. A text over a gradient or an image, a faded element and an empty box are counted in `skipped`, never silently.
AUDIT_JS = r"""
((scope) => {
  const num = s => s.split(/[\s,\/]+/).filter(Boolean).map(Number);
  const parse = s => {
    let m = /^rgba?\(([^)]+)\)$/.exec(s);
    if (m) { const p = num(m[1]); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; }
    m = /^color\(srgb ([^)]+)\)$/.exec(s);
    if (m) { const p = num(m[1]); return {r: p[0] * 255, g: p[1] * 255, b: p[2] * 255, a: p.length > 3 ? p[3] : 1}; }
    return null;
  };
  const over = (top, under) => ({r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1});
  const lin = v => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  // the colour under an element: null when it cannot be known (a gradient or an image is in the way)
  const under = el => {
    const layers = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage !== "none") return null;
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; }
    }
    let base = {r: 255, g: 255, b: 255, a: 1};
    for (let i = layers.length - 1; i >= 0; i--) base = over(layers[i], base);
    return base;
  };
  const faded = el => { for (let e = el; e && e.nodeType === 1; e = e.parentElement) if (Number(getComputedStyle(e).opacity) < 1) return true; return false; };
  const drawn = el => {
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === "none" || cs.visibility === "hidden" || e.hidden) return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const out = {measured: 0, skipped: {faded: 0, behind_image: 0, no_text: 0}, failures: []};
  const seen = new Set();
  document.querySelectorAll(scope).forEach(root => {
    const all = [root, ...root.querySelectorAll("*")];
    for (const el of all) {
      if (seen.has(el) || /^(SCRIPT|STYLE|TITLE|META|LINK|OPTION|TEXTAREA|INPUT)$/i.test(el.tagName)) continue;
      seen.add(el);
      const own = Array.from(el.childNodes).filter(n => n.nodeType === 3 && n.textContent.trim() !== "").map(n => n.textContent.trim()).join(" ");
      if (own === "" || !drawn(el)) continue;
      if (faded(el)) { out.skipped.faded += 1; continue; }
      const cs = getComputedStyle(el);
      const svg = el instanceof SVGElement;
      let fg = parse(svg ? cs.fill : cs.color);
      if (!fg) { out.skipped.no_text += 1; continue; }
      let bg;
      const box = svg ? el.closest("g.wnode") : null;
      const prev = svg ? el.previousElementSibling : null;                              // the "?" and "!" sit on their own round badge
      const shape = prev && prev.classList.contains("wbadge") ? prev : (box ? box.querySelector("rect.shape") : null);
      if (shape) {
        const f = getComputedStyle(shape).fill;
        bg = f === "none" ? null : parse(f);
        if (bg && bg.a < 1) bg = over(bg, under(box.parentElement) || {r: 255, g: 255, b: 255, a: 1});
      } else bg = under(svg ? el.parentElement : el);
      if (!bg) { out.skipped.behind_image += 1; continue; }
      if (fg.a < 1) fg = over(fg, bg);
      const px = parseFloat(cs.fontSize);
      const large = px >= 24 || (px >= 18.66 && Number(cs.fontWeight) >= 700);
      const need = large ? 3 : 4.5;
      const r = ratio(fg, bg);
      out.measured += 1;
      if (r < need) {
        const wn = el.closest(".wnode");
        out.failures.push({text: own.slice(0, 40), ratio: Math.round(r * 100) / 100, need, tag: el.tagName.toLowerCase(), cls: String(el.getAttribute("class") || ""),
          box: wn ? String(wn.getAttribute("class") || "") : "", path: (el.id ? "#" + el.id : "") + (el.parentElement ? " < " + el.parentElement.tagName.toLowerCase() + "." + String(el.parentElement.getAttribute("class") || "") : "")});
      }
    }
  });
  return out;
})(%s)
"""


def audit(browser, scope: str) -> dict:
    return browser.js(AUDIT_JS % json.dumps(scope))


def is_known_gap(theme: str, failure: dict) -> bool:
    classes = failure["cls"].split()
    return failure["ratio"] >= MIN_RATIO and any((theme, c, b) in KNOWN_GAPS for c in classes for b in failure["box"].split())


@pytest.fixture(scope="module")
def visual_browser():
    chrome = cdp.find_chrome()
    if chrome is None:
        pytest.skip("Chrome is not installed (set SUTRA_CHROME to its path)")
    with cdp.Browser(chrome) as instance:
        yield instance


def png_name(page: str, label: str, width: int) -> str:
    return f"{page}__{label}__{width}.png"


@browser_only
@pytest.mark.parametrize("page", list(PAGES))
def test_one_page_in_every_theme_and_width(page, fake, fake_server, visual_browser, screens_dir):
    stage, url, ready, after, scope = PAGES[page]
    browser = visual_browser
    browser.expect_failed("/providers", 404)
    for label, theme, scheme in THEMES:
        fake.reset()
        fake.stage(stage)
        browser.clear_diagnostics()
        browser.set_size(WIDTHS[0], HEIGHT)
        browser.set_theme(theme, scheme)
        browser.goto(fake_server.url + url)
        browser.wait_for(ready, timeout=15)
        if after:
            browser.js(after)
            browser.wait_for(AFTER_OPEN[page], timeout=10)
        for width in WIDTHS:
            where = f"{page} / {label} / {width}"
            browser.set_size(width, HEIGHT)
            time.sleep(SETTLE_S)
            expected = scheme if theme == "system" else theme
            assert browser.js("document.documentElement.dataset.theme") == expected, where
            if theme == "system":                                           # the emulation is what the page followed
                assert browser.js("matchMedia('(prefers-color-scheme: light)').matches") is (scheme == "light"), where
            if width <= 900:
                assert browser.js("document.documentElement.scrollWidth <= window.innerWidth"), (where, browser.js("[document.documentElement.scrollWidth, window.innerWidth]"))
            result = audit(browser, scope)
            assert result["measured"] > 3, (where, result)                  # the audit looked at text: an empty audit proves nothing
            failures = [f for f in result["failures"] if not is_known_gap(expected, f)]
            assert failures == [], (where, json.dumps(failures))
            if page == "home-graph" and expected == "dark" and width == 1440:                 # the allowed finding is still there: the day it is fixed, KNOWN_GAPS must go
                assert len(result["failures"]) >= 1, (where, "KNOWN_GAPS is stale: the graph's filed box now reads well in dark")
            shot = browser.shot(screens_dir / png_name(page, label, width))
            assert shot.stat().st_size > 2000, where
        assert [line for line in browser.console_errors if PILL_404 not in line] == [], (page, label, browser.console_errors)
        assert browser.failed_requests == [], (page, label, browser.failed_requests)


@browser_only
def test_the_audit_sees_a_text_that_misses_its_ratio(fake, fake_server, visual_browser):
    """The audit is not blind: a text that is --muted on a --panel2 box painted nearly the same colour is reported, one on its own colour is not."""
    browser = visual_browser
    fake.reset()
    fake.stage("1")
    browser.set_theme("dark", "dark")
    browser.goto(fake_server.url + "/")
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    browser.js("""(() => { const d = document.createElement('div'); d.id = 'probe'; d.style.cssText = 'position:fixed;left:0;top:0;background:#777777;color:#7a7a7a';
                 d.textContent = 'low contrast'; document.body.appendChild(d);
                 const e = document.createElement('div'); e.id = 'probe2'; e.style.cssText = 'position:fixed;left:0;top:40px;background:#000000;color:#ffffff';
                 e.textContent = 'high contrast'; document.body.appendChild(e); })()""")
    low = audit(browser, "#probe")
    high = audit(browser, "#probe2")
    assert low["measured"] == 1 and [f["text"] for f in low["failures"]] == ["low contrast"] and low["failures"][0]["ratio"] < 1.2
    assert high["measured"] == 1 and high["failures"] == []
    gradient = browser.js("""(() => { const g = document.createElement('div'); g.id = 'probe3'; g.style.cssText = 'position:fixed;left:0;top:80px;background:linear-gradient(red,blue);color:red';
                   g.textContent = 'over a gradient'; document.body.appendChild(g); return 1; })()""")
    skipped = audit(browser, "#probe3")
    assert gradient == 1 and skipped["measured"] == 0 and skipped["skipped"]["behind_image"] == 1        # said, not silently passed


def test_the_known_gap_matcher_is_narrow():
    gap = {"cls": "tsub", "box": "wnode k-function st-filed", "ratio": 4.22}
    assert is_known_gap("dark", gap) is True
    assert is_known_gap("light", gap) is False                              # only the dark theme
    assert is_known_gap("dark", {**gap, "ratio": 3.2}) is False             # a worse number is a new finding
    assert is_known_gap("dark", {**gap, "box": "wnode k-function st-idle"}) is False
    assert is_known_gap("dark", {**gap, "cls": "tlab"}) is False
    assert re.fullmatch(r"[a-z-]+__[a-z-]+__\d+\.png", png_name("home-start", "system-dark", 390))
