"""The department page glue (UI-8): sutra_app/ui/static/js/dept_ext.js on the real page `/d/web/`.

docs/design/ui.md sections 5 (E6, E12), 6.7, 7, 9 and 10; S3-web-10; UI-D10.

Two kinds of test:

  node      the pure parts of dept_ext.js (`DeptExt.helpers`: which graph.updated matters to a team, the banner sentence, the document title)
            and the promise that loading the file in node starts nothing. One node process. They run in the merge gate.
  browser   the real J2 page, served by the fake backend of UI-0 with the real `pages/j2_ui.html` and the real static folder (marker `browser`,
            `SUTRA_BROWSER=1`): the page boots clean, both new tabs mount their view the first time they show, a fresh load of `?tab=graph`,
            `?tab=orgchart` or `#orgchart` shows the view without a click, a team the boot block calls archived hides the composers and shows the
            banner, the Agent chips open the node panel, the panel and J2's Agent drawer exclude each other, and events refresh what is on
            screen (and only what concerns this team). Each test gets its own Chrome and starts at stage 2 (the Web team asks about the menu).

            Since sync 4 (the studio pin, docs/design/j2-sync-4.md 4.3 and 4.8) the page opens in its Simple view unless a view is chosen, and the rail with
            the Sutra strip (home, team chip, Workflow graph, Org chart) lives in the Detailed view: a test names the view it works in (`Page.open(view=)`),
            and a deep link (`?tab=`, `#tab`) opens the Detailed view by itself. New here: both strips, the start page's output choice, the function chat of
            J2's panel with a question that was asked before, a question typed there, Esc with the node panel open, the rail's Artifacts flyout, a part's
            record, the Decide for me switch, the team's library page, and the attention pill clear of every control of the Simple view at a laptop and a phone width, drawn by its own
            rules (an atom's status pill by the atoms') and clear of the team strip's name from 320 to 1920 px, light and dark; in the Detailed view it has a row of its own above
            the Needs you box at 900 px and under and is clear of every control from 320 to 1920 px, light and dark, with the chat closed and open; the library page draws no empty Needs
            you box, and from 901 px its catalog's card ends above the pill.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

import fake_backend  # tests/ui is on sys.path (conftest.py)

REPO = Path(__file__).resolve().parents[2]
JS = REPO / "sutra_app" / "ui" / "static" / "js"
NODE = shutil.which("node")
browser_only = pytest.mark.browser

J2_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "j2"

DEPT = "web"
DEPT_SESSION = "cs_5e0a77b19c3d"
NO_BANNER = "This team was merged into"


# =====================================================================================================================
# 1. The pure parts, run in node (the merge gate runs these)
# =====================================================================================================================
PROBE = r"""
const DeptExt = require("__JS__/dept_ext.js");
const h = DeptExt.helpers;
const out = {};
out.loads = {init: typeof DeptExt.init, keys: Object.keys(DeptExt).sort(), helpers: Object.keys(h).sort(), started: DeptExt.state().started};
out.state = DeptExt.state();

const node = (id, dept) => ({id, dept_id: dept});
out.touches = {
  ownNode: h.touchesDept({nodes: [node("web.identity", "web")]}, "web", false),
  otherTeamOnly: h.touchesDept({nodes: [node("content.audit", "content"), node("content", "content")]}, "web", false),
  mixed: h.touchesDept({nodes: [node("content", "content"), node("web.audit", "web")]}, "web", false),
  rootOnly: h.touchesDept({nodes: [node("root", null)]}, "web", false),
  theDepartmentItself: h.touchesDept({nodes: [{id: "web", dept_id: "content"}]}, "web", false),
  otherTeamButShowingAll: h.touchesDept({nodes: [node("content", "content")]}, "web", true),
  noNodes: h.touchesDept({nodes: []}, "web", false),
  noBody: [h.touchesDept(undefined, "web", false), h.touchesDept(null, "web", false), h.touchesDept("x", "web", false), h.touchesDept({}, "web", false)],
  nodeNotAnObject: h.touchesDept({nodes: [5]}, "web", false),
  noDepartment: h.touchesDept({nodes: [node("content", "content")]}, "", false),
};
out.banner = {
  note: h.bannerText({note: "This team was merged into Content. Its history stays available."}),
  noNote: h.bannerText({}),
  blankNote: h.bannerText({note: "  \n "}),
  notABoot: h.bannerText(null),
  controlCharacters: h.bannerText({note: "a\u0000b\nc"}),
};
out.title = {
  plain: h.titleText({dept_label: "Web"}),
  trimmed: h.titleText({dept_label: "  Web\n team "}),
  empty: h.titleText({dept_label: ""}),
  missing: h.titleText({}),
  notABoot: h.titleText(undefined),
};
// init() without a document or SutraCtx does nothing harmful and can be called twice
out.initTwice = [DeptExt.init(), DeptExt.init()];
out.chipWithoutDocument = DeptExt.chip();
out.titleWithoutDocument = DeptExt.title();
out.tabWithoutViews = [DeptExt.onTab("graph"), DeptExt.onTab("orgchart"), DeptExt.onTab("map")];
out.drawersWithoutPanel = DeptExt.drawers();
out.eventsWithoutStream = DeptExt.events();
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    if NODE is None:
        pytest.skip("node is not installed")
    done = subprocess.run([NODE, "-e", PROBE.replace("__JS__", JS.as_posix())], capture_output=True, text=True, timeout=60, cwd=REPO)
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout)


def test_the_file_loads_in_node_and_starts_nothing(probe):
    assert probe["loads"]["init"] == "function"
    assert probe["loads"]["keys"] == sorted(["init", "chip", "title", "onTab", "events", "drawers", "destroy", "state", "helpers"])
    assert probe["loads"]["helpers"] == ["bannerText", "titleText", "touchesDept"]
    assert probe["loads"]["started"] is False       # a module load is not a page start


def test_touches_dept_ignores_only_other_teams_while_one_team_shows(probe):
    t = probe["touches"]
    assert t["ownNode"] is True
    assert t["otherTeamOnly"] is False
    assert t["mixed"] is True
    assert t["rootOnly"] is True                     # a node of nobody (the root) can change the team's view
    assert t["theDepartmentItself"] is True
    assert t["otherTeamButShowingAll"] is True       # "All teams" shows everything
    assert t["noDepartment"] is True


def test_touches_dept_refetches_when_the_body_does_not_say_what_changed(probe):
    t = probe["touches"]
    assert t["noNodes"] is True
    assert t["noBody"] == [True, True, True, True]
    assert t["nodeNotAnObject"] is True


def test_banner_and_title_text(probe):
    assert probe["banner"]["note"] == "This team was merged into Content. Its history stays available."
    generic = "This team was merged into another team. Its history stays available."
    assert probe["banner"]["noNote"] == generic
    assert probe["banner"]["blankNote"] == generic
    assert probe["banner"]["notABoot"] == generic
    assert probe["banner"]["controlCharacters"] == "a b c"
    assert probe["title"] == {"plain": "Web · Sutra", "trimmed": "Web team · Sutra", "empty": "", "missing": "", "notABoot": ""}


def test_nothing_breaks_without_a_page(probe):
    assert probe["state"]["started"] is False and probe["state"]["mounted"] == {"graph": False, "orgchart": False}
    assert probe["initTwice"] == [True, False]       # the second call is a no-op
    assert probe["chipWithoutDocument"] is False
    assert probe["titleWithoutDocument"] == ""
    assert probe["tabWithoutViews"] == [False, False, False]
    assert probe["drawersWithoutPanel"] is None
    assert probe["eventsWithoutStream"] is None


# =====================================================================================================================
# 1b. The page under its team, in node (J2 sync 4, E1.3: D141, edits E20a to E20i)
# =====================================================================================================================
# The ported page's script runs in a stub DOM the way J2's own render harness runs it (pages/j2_ui_render.js), with the context script first and
# a boot block and an address of the test's choosing. What is asked afterwards is what the page builds from SutraCtx: its library and its own
# page, and whether it knows it is on the library page.
LIBRARY_PROBE = r"""
const fs = require("fs"), vm = require("vm"), path = require("path");
const root = "__ROOT__";
const page = fs.readFileSync(path.join(root, "sutra_app/ui/pages/j2_ui.html"), "utf8");
const scripts = [...page.matchAll(/<script>([\s\S]*?)<\/script>/g)];
const noop = () => noop;
const el = () => new Proxy({innerHTML: "", textContent: "", value: "", style: {}, dataset: {}, disabled: false, open: false, hidden: false,
  classList: {toggle: noop, add: noop, remove: noop, contains: () => false}, children: [], scrollHeight: 0},
  {get: (t, k) => k in t ? t[k] : k === "querySelectorAll" ? () => [] : noop, set: (t, k, v) => (t[k] = v, true)});
function run(boot, pathname, search) {
  const els = {}, replaced = [];
  const ctx = vm.createContext({
    document: {getElementById: id => id === "sutra-boot" ? (boot ? {textContent: JSON.stringify(boot)} : el()) : els[id] || (els[id] = el()),
               querySelector: () => el(), querySelectorAll: () => [], body: el(), addEventListener: noop, createElement: el, readyState: "complete"},
    location: {pathname, search, href: pathname + search, hash: ""}, history: {replaceState: (...a) => replaced.push(a[2]), state: null},
    localStorage: {getItem: () => null, setItem: noop}, CSS: {escape: x => x}, matchMedia: () => ({matches: true, addEventListener: noop}),
    fetch: () => Promise.reject(new Error("no network")), setTimeout: noop, setInterval: noop, requestAnimationFrame: noop,
    console, URLSearchParams, Date, JSON, Math, Set, Map, Promise});
  vm.runInContext(fs.readFileSync(path.join(root, "sutra_app/ui/static/js/sutra_ctx.js"), "utf8"), ctx);
  vm.runInContext(scripts[scripts.length - 1][1], ctx);
  const ask = code => vm.runInContext(code, ctx);
  return {
    dept: ask("SutraCtx.dept"), pagePath: ask("SutraCtx.pagePath"), libraryPath: ask("SutraCtx.libraryPath"), onLibrary: ask("SutraCtx.onLibrary()"),
    catOn: ask("CAT.on"), libHref: ask('libHref("prd", "Problem", "generic", 1)'), runHref: ask('runHref("j2-1")'),
    runQ: ask('(viewRun = "j2-1", runQ())'), viewHref: ask('viewHref("j2-2")'),
    loadWrites: replaced.slice(), setViewWrites: (() => { const n = replaced.length; ask('setView("simple", false)'); return replaced.slice(n); })(),
    pos: ask('(svg => motionKey(svg))({classList: {contains: () => false}})'),
  };
}
const BOOT = {page: "dept", token: "t".repeat(24), dept: "web", dept_label: "Web", archived: false, note: "", version: "0.1.0"};
const out = {
  team: run(BOOT, "/d/web/", ""),
  library: run(BOOT, "/d/web/library", "?view=artifact&q=x"),
  libraryColon: run({...BOOT, dept: "a:b"}, "/d/a:b/library", ""),
  noTeam: run(null, "/", ""),
  jTwoLibrary: run(null, "/library", ""),
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def library_probe() -> dict:
    if NODE is None:
        pytest.skip("node is not installed")
    done = subprocess.run([NODE, "-e", LIBRARY_PROBE.replace("__ROOT__", REPO.as_posix())], capture_output=True, text=True, timeout=120, cwd=REPO)
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout)


def test_the_library_page_of_a_team_knows_it_is_the_library_and_builds_its_links_under_the_team(library_probe):
    page = library_probe["library"]
    assert (page["dept"], page["pagePath"], page["libraryPath"]) == ("web", "/d/web/", "/d/web/library")
    assert page["onLibrary"] is True and page["catOn"] is True                       # E20d: J2 asked location.pathname === "/library"
    assert page["libHref"] == "/d/web/library?open=prd/problem/generic/v1"           # E20b
    assert page["runHref"] == "/d/web/?run=j2-1&view=detail&tab=library"             # E20c: back to the team's page, never to the root
    assert page["pos"].startswith("j2pos:web:")                                      # E10: pins per team


def test_the_team_page_is_not_the_library_and_shares_the_same_builders(library_probe):
    page = library_probe["team"]
    assert page["onLibrary"] is False and page["catOn"] is False
    assert page["libHref"] == "/d/web/library?open=prd/problem/generic/v1" and page["runHref"] == "/d/web/?run=j2-1&view=detail&tab=library"
    assert page["runQ"] == "&run=j2-1&dept=web"                                      # E4: every URL the page builds carries the team
    assert page["viewHref"].startswith("?run=j2-2&view=")                           # a relative query: it stays on the page it is on


def test_the_library_page_keeps_its_own_query_while_a_team_page_writes_the_view_into_the_address(library_probe):
    library, team = library_probe["library"], library_probe["team"]
    assert library["loadWrites"] == [] and library["setViewWrites"] == []           # E20d, setView: the catalog's ?view= (run | artifact) is its own
    assert team["loadWrites"] == ["/d/web/?view=simple"] and team["setViewWrites"] == ["/d/web/?view=simple"]    # a team page writes ?view= as J2's always did


def test_a_team_id_with_a_colon_keeps_its_library_path_and_its_page(library_probe):
    page = library_probe["libraryColon"]
    assert (page["dept"], page["pagePath"], page["libraryPath"], page["onLibrary"]) == ("a:b", "/d/a:b/", "/d/a:b/library", True)
    assert page["libHref"].startswith("/d/a:b/library?open=")


def test_without_a_team_the_page_behaves_as_j2s_own_does(library_probe):
    stub, library = library_probe["noTeam"], library_probe["jTwoLibrary"]
    assert (stub["dept"], stub["pagePath"], stub["libraryPath"], stub["onLibrary"], stub["catOn"]) == ("", "/", "/library", False, False)
    assert stub["libHref"] == "/library?open=prd/problem/generic/v1" and stub["runHref"] == "/?run=j2-1&view=detail&tab=library"
    assert stub["runQ"] == "&run=j2-1" and stub["pos"].startswith("j2pos::")
    assert library["onLibrary"] is True and library["catOn"] is True and library["libraryPath"] == "/library"       # J2's own address, the harness's too


# =====================================================================================================================
# 2. The real page in Chrome
# =====================================================================================================================
class Page:
    """One open team page: helpers over the browser, the fake backend's client and its request log."""

    def __init__(self, browser: Any, server: Any) -> None:
        self.b = browser
        self.server = server
        self.fake = server.client

    def open(self, query: str = "", dept: str = DEPT, view: str | None = "detail") -> "Page":
        """The team page in `view` ("detail" by default: the rail's tabs are there; "simple"; None leaves the choice to the page, as a deep link does)."""
        params, _, fragment = query.partition("#")
        parts = [p for p in params.lstrip("?").split("&") if p]
        if view and not any(p.startswith("view=") for p in parts):
            parts.append(f"view={view}")
        url = f"{self.server.url}/d/{dept}/" + ("?" + "&".join(parts) if parts else "") + ("#" + fragment if fragment else "")
        self.b.goto(url)
        self.b.wait_for("window.DeptExt !== undefined && DeptExt.state().started === true")
        return self

    def tab(self, name: str) -> None:
        self.b.click(f'.tabs [data-tab="{name}"]')

    def pool_tab(self, name: str) -> None:
        """One of J2's own tab buttons, which the new rail keeps in a pool under its flyouts (no place on screen): its click handler, as the page wires it."""
        self.js(f"document.querySelector('.tabs [data-tab=\"{name}\"]').click()")

    def js(self, expression: str) -> Any:
        return self.b.js(expression)

    def state(self) -> dict:
        return self.b.js("DeptExt.state()")

    def requests(self, path: str) -> list[dict]:
        return [e for e in self.fake.log() if e["path"] == path]

    def count(self, path: str) -> int:
        return len(self.requests(path))

    def wait_requests(self, path: str, at_least: int, timeout: float = 6.0) -> int:
        deadline = time.monotonic() + timeout
        while True:
            n = self.count(path)
            if n >= at_least or time.monotonic() > deadline:
                assert n >= at_least, f"{path} was asked {n} times, expected at least {at_least}"
                return n
            time.sleep(0.03)

    def settle(self, seconds: float = 0.7) -> None:
        """Time for a request that must NOT happen (the coalescing window is 150 ms)."""
        time.sleep(seconds)

    def hidden(self, selector: str) -> bool:
        return bool(self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); return !e || e.hidden; }})()"))

    def display(self, selector: str) -> str:
        return self.js(f"getComputedStyle(document.querySelector({json.dumps(selector)})).display")

    def drawn(self, selector: str) -> bool:
        """The element takes room on the page: not hidden, and none of its parents is (the computed `display` of a child of a hidden box is still its own)."""
        return bool(self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); return !!e && e.offsetParent !== null; }})()"))


@pytest.fixture()
def team(fake_server, fake, browser) -> Page:
    fake.stage("2")          # the Web team exists and asks about the menu
    return Page(browser, fake_server)


def graph_ready(page: Page) -> None:
    page.b.wait_for("document.querySelectorAll('#pane-graph g.wnode').length > 0")


def chart_ready(page: Page) -> None:
    page.b.wait_for("document.querySelectorAll('#pane-orgchart .chgrow').length > 0")


def stream_live(page: Page) -> None:
    page.fake.wait_subscribers(1)
    page.b.wait_for("DeptExt.state().live === 'live'")


# ---------------------------------------------------------------------------------------------------------------------
# boot
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_the_page_boots_clean_with_both_strips_the_title_and_both_new_tabs(team):
    team.open()
    team.settle(0.4)
    for chip, home in (("#deptchip", "#to-home"), ("#deptchip-s", "#to-home-s")):        # the strip of the rail and the one of the Simple view
        assert team.b.text(chip) == "Web" and team.js(f"document.querySelector({json.dumps(chip)}).title") == "Web", chip
        assert team.js(f"document.querySelector({json.dumps(home)}).getAttribute('href')") == "/", home
    assert team.js("document.title") in ("Web · Sutra", "(1) Web · Sutra")      # gap attention: the org-wide count rides in front once read
    assert team.b.count('.tabs [data-tab="graph"]') == 1 and team.b.count('.tabs [data-tab="orgchart"]') == 1
    assert team.js("document.querySelector('#rail > .railhome').firstElementChild.id") == "to-home"      # the strip is the first thing in the rail
    assert team.js("document.body.classList.contains('archived')") is False
    assert team.b.exists(".archivedbanner") is False
    assert team.b.console_errors == [] and team.b.failed_requests == []
    assert team.state()["mounted"] == {"graph": False, "orgchart": False}


@browser_only
def test_a_live_team_keeps_its_composers_in_the_simple_view(team):
    team.open(view="simple")
    team.b.wait_for("!!document.getElementById('schatbtn')")
    assert team.drawn("#sauto") and team.drawn("#sbox") is False                    # the chat pane starts closed on a wide screen
    team.b.click("#schatbtn")                                                      # the answer box is in the chat pane, which the top bar's Chat button opens
    team.b.wait_for("!document.getElementById('sapp').classList.contains('chatclosed')")
    assert team.drawn("#sbox") and team.drawn("#ssend")


# ---------------------------------------------------------------------------------------------------------------------
# the two tabs
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_the_workflow_graph_tab_mounts_once_and_asks_for_this_team(team):
    team.open()
    team.tab("graph")
    graph_ready(team)
    assert team.hidden("#pane-graph") is False and team.hidden("#pane-orgchart") is True
    assert team.state()["mounted"] == {"graph": True, "orgchart": False}
    asked = team.requests("/api/graph")
    assert len(asked) == 1 and "level=chart" in asked[0]["query"] and "dept=web" in asked[0]["query"]
    assert team.b.count("#pane-graph svg.wgsvg") == 1
    team.tab("map")
    team.tab("graph")
    assert team.b.count("#pane-graph svg.wgsvg") == 1       # a second visit does not build a second view
    assert team.b.console_errors == []


@browser_only
def test_the_org_chart_tab_mounts_once_with_its_change_log(team):
    team.open()
    team.tab("orgchart")
    chart_ready(team)
    assert team.hidden("#pane-orgchart") is False and team.hidden("#pane-graph") is True
    assert team.state()["mounted"] == {"graph": False, "orgchart": True}
    assert team.count("/api/chart") == 1 and team.count("/api/chart/changes") == 1
    assert team.b.count("#pane-orgchart .ocpane") == 1
    team.tab("map")
    team.tab("orgchart")
    assert team.b.count("#pane-orgchart .ocpane") == 1
    assert team.b.console_errors == []


@browser_only
@pytest.mark.parametrize("query, pane, ready", [
    ("?tab=orgchart", "orgchart", chart_ready),
    ("?tab=graph", "graph", graph_ready),
    ("#orgchart", "orgchart", chart_ready),
    ("#graph", "graph", graph_ready),
])
def test_a_fresh_load_of_a_deep_link_shows_the_view_without_a_click(team, query, pane, ready):
    team.open(query, view=None)                          # no view named: the link itself leaves the Simple view
    ready(team)
    assert team.js("document.body.classList.contains('simple')") is False
    assert team.hidden(f"#pane-{pane}") is False
    assert team.js("document.querySelector('.tabs [aria-selected=true]').dataset.tab") == pane
    assert team.state()["tab"] == pane and team.state()["mounted"][pane] is True
    assert team.b.console_errors == [] and team.b.failed_requests == []


@browser_only
def test_a_deep_link_to_another_tab_mounts_neither_view(team):
    team.open("?tab=goal", view=None)
    team.settle(0.4)
    assert team.state()["mounted"] == {"graph": False, "orgchart": False}
    assert team.state()["tab"] == "goal"


# ---------------------------------------------------------------------------------------------------------------------
# archived
# ---------------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def archived_team(monkeypatch, make_fake_server, browser) -> Page:
    """A team page whose row says archived (no v1 row does: UI-D10). The patch comes first: the router keeps the bound method."""
    original = fake_backend._Services.department

    class Row:
        def __init__(self, id: str, name: str) -> None:
            self.id, self.name = id, name
            self.archived = True
            self.merged_into_name = "Content"

    def department(self, dept_id):
        row = original(self, dept_id)
        return None if row is None else Row(row.id, row.name)

    monkeypatch.setattr(fake_backend._Services, "department", department)
    server = make_fake_server()
    server.client.stage("2")
    return Page(browser, server)


@browser_only
def test_an_archived_team_shows_the_banner_and_hides_every_composer(archived_team):
    page = archived_team.open(view="simple")
    page.b.wait_for("!!document.getElementById('schatbtn')")
    page.b.click("#schatbtn")                                                      # the chat pane is open: only the archived rule can keep its box away
    page.b.wait_for("!document.getElementById('sapp').classList.contains('chatclosed')")
    assert page.js("document.body.classList.contains('archived')") is True
    sentence = "This team was merged into Content. Its history stays available."
    assert page.js("Array.from(document.querySelectorAll('.archivedbanner'), e => e.textContent)") == [sentence, sentence]
    assert page.js("Array.from(document.querySelectorAll('.archivedbanner'), e => e.getAttribute('role'))") == ["status", "status"]
    # one at the top of each of J2's two views, and the one of the view on screen is visible (J2 opens on the chat view)
    assert page.js("document.getElementById('sview').firstElementChild.classList.contains('steamstrip')") is True      # the strip stays first: the way home is never hidden
    assert page.js("document.getElementById('sview').children[1].classList.contains('archivedbanner')") is True
    assert page.js("document.querySelector('#dview .dcol').firstElementChild.classList.contains('archivedbanner')") is True
    assert page.js("document.querySelector('#sview > .archivedbanner').offsetHeight") > 0
    for selector in ("#sbox", "#ssend", "#sauto"):                      # the studio's own: the answer box, its send button and the Decide for me switch
        assert page.drawn(selector) is False, selector
    for selector in ("#box", "#send", "#lform", "#lbox", "#lsend", ".schips", "#soutpick"):      # the chat panel's, and the landing's (D139: nothing can be started)
        assert page.drawn(selector) is False, selector
    assert page.b.text("#deptchip") == "Web" and page.b.text("#deptchip-s") == "Web"             # the history stays readable
    assert page.b.console_errors == []


@browser_only
def test_an_archived_team_still_opens_its_views(archived_team):
    page = archived_team.open("?tab=orgchart", view=None)
    chart_ready(page)
    assert page.b.count(".archivedbanner") == 2
    assert page.js("document.querySelector('#dview .dcol > .archivedbanner').offsetHeight") > 0       # the detail view shows its own


# ---------------------------------------------------------------------------------------------------------------------
# the Agent chips and the two drawers
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_an_agent_chip_opens_the_node_panel_not_the_agent_drawer(team):
    team.open()
    team.b.wait_for("document.querySelector('[data-agent=identity]') !== null")
    team.js("document.querySelector('[data-agent=identity]').click()")
    team.b.wait_for("!document.getElementById('nodepanel').hidden")
    team.b.wait_for("document.getElementById('nptitle') && document.getElementById('nptitle').textContent !== ''")
    assert team.hidden("#agentdrawer") is True
    assert team.js("document.body.classList.contains('nodeopen')") is True
    assert team.js("document.body.classList.contains('agentopen')") is False
    assert team.requests("/api/graph/nodes/web.identity")           # the function's own node, found through the team record
    assert team.b.console_errors == []


@browser_only
def test_only_one_drawer_is_open_at_a_time(team):
    team.open()
    team.b.wait_for("document.querySelector('[data-agent=identity]') !== null")
    team.js("document.querySelector('[data-agent=identity]').click()")
    team.b.wait_for("!document.getElementById('nodepanel').hidden")
    team.js("document.querySelector('[data-agent=\"W-1\"]').click()")             # J2's drawer opens (W-1 is no function): the panel goes
    team.b.wait_for("!document.getElementById('agentdrawer').hidden && document.getElementById('nodepanel').hidden")
    assert team.js("document.body.classList.contains('nodeopen')") is False
    team.js("document.querySelector('[data-agent=adaptation]').click()")          # the panel opens: J2's drawer goes
    team.b.wait_for("!document.getElementById('nodepanel').hidden && document.getElementById('agentdrawer').hidden")
    assert team.js("document.body.classList.contains('agentopen')") is False


# ---------------------------------------------------------------------------------------------------------------------
# the views talk to the panel and to each other
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_a_graph_node_click_opens_its_chat_panel(team):
    team.b.expect_failed("/api/chats/cs_5e0a77b19c3d/providers", 404)          # the fake has no provider pill route (pre-existing, as the Home tests announce)
    team.open("?tab=graph")
    graph_ready(team)
    team.b.click('#pane-graph g.wnode[data-id="web"]')
    team.b.wait_for("!document.getElementById('nodepanel').hidden")
    team.b.wait_for("document.getElementById('nptitle').textContent === 'Web'")
    assert team.requests("/api/graph/nodes/web")
    assert [line for line in team.b.console_errors if "404" not in line] == []      # whether that 404 has been logged yet is a race the panel's speed decides


@browser_only
def test_the_panel_reads_the_graph_the_page_holds_before_it_asks_the_server(team):
    team.b.expect_failed(f"/api/chats/{DEPT_SESSION}/providers", 404)          # the fake has no provider pill route (pre-existing): whether the panel has asked yet is a race
    team.open()
    team.js("NodePanel.open('web.identity', 'chat')")           # no graph yet: the Identity's team is asked of the server
    team.wait_requests(f"/api/chats/{DEPT_SESSION}/messages", 1)
    assert team.count("/api/departments/web") == 1
    team.js("NodePanel.close()")
    team.tab("graph")
    graph_ready(team)
    team.js("NodePanel.open('web.identity', 'chat')")           # the graph holds the team's node: its chat is read from there
    team.wait_requests(f"/api/chats/{DEPT_SESSION}/messages", 2)
    assert team.count("/api/departments/web") == 1


@browser_only
def test_the_org_chart_card_opens_the_chat_panel(team):
    team.b.expect_failed(f"/api/chats/{DEPT_SESSION}/providers", 404)          # the fake has no provider pill route (pre-existing): whether the panel has asked yet is a race
    team.open("?tab=orgchart")
    chart_ready(team)
    team.b.click('#pane-orgchart g.wnode[data-id="web"]')
    team.b.wait_for("!document.querySelector('#pane-orgchart .ocard').hidden")
    team.b.click('#pane-orgchart [data-oc="chat"]')
    team.b.wait_for("!document.getElementById('nodepanel').hidden")
    team.b.wait_for("document.getElementById('nptitle').textContent === 'Web'")


@browser_only
def test_show_in_graph_switches_the_tab_and_selects_the_node(team):
    team.open("?tab=orgchart")
    chart_ready(team)
    assert team.state()["mounted"]["graph"] is False
    team.b.click('#pane-orgchart g.wnode[data-id="web"]')
    team.b.wait_for("!document.querySelector('#pane-orgchart .ocard').hidden")
    team.b.click('#pane-orgchart [data-oc="show"]')
    team.b.wait_for("!document.getElementById('pane-graph').hidden")
    team.b.wait_for("document.querySelector('#pane-graph g.wnode.sel[data-id=\"web\"]') !== null")     # selected once the graph had been drawn
    assert team.js("document.querySelector('.tabs [aria-selected=true]').dataset.tab") == "graph"
    assert team.hidden("#pane-orgchart") is True


@browser_only
def test_show_in_graph_selects_at_once_when_the_graph_is_already_drawn(team):
    team.open("?tab=graph")
    graph_ready(team)
    team.tab("orgchart")
    chart_ready(team)
    team.b.click('#pane-orgchart g.wnode[data-id="web"]')
    team.b.wait_for("!document.querySelector('#pane-orgchart .ocard').hidden")
    team.b.click('#pane-orgchart [data-oc="show"]')
    team.b.wait_for("document.querySelector('#pane-graph g.wnode.sel[data-id=\"web\"]') !== null")
    assert team.count("/api/graph") == 1                      # the graph in hand was enough


@browser_only
def test_the_root_node_goes_to_the_org_chart_not_to_a_chat(team):
    team.open("?tab=graph")
    graph_ready(team)
    team.b.click('#pane-graph [data-wscope="all"]')           # "All teams" draws the root
    team.b.wait_for("document.querySelector('#pane-graph g.wnode[data-id=\"root\"]') !== null")
    team.b.click('#pane-graph g.wnode[data-id="root"]')
    team.b.wait_for("!document.getElementById('pane-orgchart').hidden")
    chart_ready(team)
    assert team.hidden("#nodepanel") is True


# ---------------------------------------------------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_the_live_chip_follows_the_stream_of_both_views(team):
    team.open("?tab=graph")
    graph_ready(team)
    stream_live(team)
    team.b.wait_for("document.querySelector('#pane-graph .wlive').dataset.state === 'live'")
    team.tab("orgchart")
    chart_ready(team)
    team.b.wait_for("document.querySelector('#pane-orgchart .wlive').dataset.state === 'live'")
    assert team.fake.state()["subscribers"] == 1             # one stream for the page, however many views
    asked = team.requests("/api/events")
    assert len(asked) == 1 and "topics=graph" in asked[0]["query"] and "chart" in asked[0]["query"] and "chat" in asked[0]["query"]


@browser_only
def test_a_graph_update_of_this_team_refetches_the_graph_once(team):
    team.open("?tab=graph")
    graph_ready(team)
    stream_live(team)
    before = team.count("/api/graph")
    for _ in range(3):                                         # a burst is one refetch
        team.fake.emit("graph.updated", {"version": 50, "nodes": [{"id": "web.audit", "dept_id": "web"}], "edges_added": 0, "edges_removed": 0})
    team.wait_requests("/api/graph", before + 1)
    team.settle()
    assert team.count("/api/graph") == before + 1


@browser_only
def test_a_graph_update_of_another_team_is_ignored_while_one_team_shows(team):
    team.open("?tab=graph")
    graph_ready(team)
    stream_live(team)
    before = team.count("/api/graph")
    team.fake.emit("graph.updated", {"version": 50, "nodes": [{"id": "content.audit", "dept_id": "content"}], "edges_added": 0, "edges_removed": 0})
    team.settle()
    assert team.count("/api/graph") == before
    team.fake.emit("graph.updated", {"version": 51, "nodes": [{"id": "root", "dept_id": None}], "edges_added": 0, "edges_removed": 0})
    team.wait_requests("/api/graph", before + 1)


@browser_only
def test_a_graph_update_of_another_team_counts_while_all_teams_show(team):
    team.open("?tab=graph")
    graph_ready(team)
    stream_live(team)
    team.b.click('#pane-graph [data-wscope="all"]')
    team.b.wait_for("document.querySelector('#pane-graph g.wnode[data-id=\"root\"]') !== null")
    before = team.count("/api/graph")
    team.fake.emit("graph.updated", {"version": 52, "nodes": [{"id": "content.audit", "dept_id": "content"}], "edges_added": 0, "edges_removed": 0})
    team.wait_requests("/api/graph", before + 1)


@browser_only
def test_chart_events_refetch_the_org_chart_and_not_the_graph(team):
    team.open("?tab=orgchart")
    chart_ready(team)
    stream_live(team)
    before = team.count("/api/chart")
    team.fake.emit("chart.changed", {"revision": 2, "version": 2, "change_id": "chg-0002", "kind": "add", "added": ["x"], "moved": [], "merged": [], "summary": "x", "archived": []})
    team.wait_requests("/api/chart", before + 1)
    team.wait_requests("/api/chart/changes", 2)
    team.fake.emit("chart.approval", {"change_id": "chg-0003", "summary": "x", "message_id": 9})
    team.wait_requests("/api/chart", before + 2)
    assert team.count("/api/graph") == 0                       # the graph tab was never opened


@browser_only
def test_a_resync_refetches_everything_that_is_on_screen(team):
    team.open("?tab=graph")
    graph_ready(team)
    team.tab("orgchart")
    chart_ready(team)
    stream_live(team)
    graphs, charts = team.count("/api/graph"), team.count("/api/chart")
    team.fake.emit("server.resync", {"reason": "gap"})
    team.wait_requests("/api/graph", graphs + 1)
    team.wait_requests("/api/chart", charts + 1)


STUB_EVENT_SOURCE = """
window.EventSource = class {
  constructor(url) { this.url = url; this.readyState = 0; this.on = {}; [1500, 1520, 1540].forEach(ms => setTimeout(() => (this.on.error || []).forEach(f => f({})), ms)); }
  addEventListener(type, fn) { (this.on[type] = this.on[type] || []).push(fn); }
  close() { this.readyState = 2; }
};
"""


@browser_only
def test_a_dropped_stream_falls_back_to_polling_both_views(team):
    team.open()
    team.js(STUB_EVENT_SOURCE)                                  # a stream that fails three times in a row, once both views have mounted
    team.tab("graph")
    graph_ready(team)
    team.tab("orgchart")
    chart_ready(team)
    team.b.wait_for("DeptExt.state().live === 'polling'")
    team.b.wait_for("document.querySelector('#pane-graph .wlive').dataset.state === 'polling' && document.querySelector('#pane-orgchart .wlive').dataset.state === 'polling'")
    graphs, charts = team.count("/api/graph"), team.count("/api/chart")
    team.wait_requests("/api/graph", graphs + 1)                # every pollMs (2 s): the same two reads, with no event to say so
    team.wait_requests("/api/chart", charts + 1)
    team.tab("map")
    team.tab("graph")                                           # a visit while the stream is down asks again
    team.wait_requests("/api/graph", graphs + 2)


@browser_only
def test_a_message_for_a_node_that_is_not_open_gives_it_an_unread_dot_and_the_panel_clears_it(team):
    team.b.expect_failed(f"/api/chats/{DEPT_SESSION}/providers", 404)          # the fake has no provider pill route (pre-existing): whether the panel has asked yet is a race
    team.open("?tab=graph")
    graph_ready(team)
    stream_live(team)
    last = team.fake.get(f"/api/chats/{DEPT_SESSION}/messages")[1]["next_after"]
    message = {"id": last, "session_id": DEPT_SESSION, "role": "agent", "who": "identity", "kind": "text", "text": "hi", "state": "ok"}
    # the owner's own line is no news
    team.fake.emit("chat.message", {"session_id": DEPT_SESSION, "message": dict(message, id=last + 5, who="user", role="user")})
    team.settle(0.3)
    assert team.b.count('#pane-graph g.wnode[data-id="web"] circle.wunread') == 0
    team.fake.emit("chat.message", {"session_id": DEPT_SESSION, "message": message})
    team.b.wait_for("document.querySelector('#pane-graph g.wnode[data-id=\"web\"] circle.wunread') !== null")
    team.b.click('#pane-graph g.wnode[data-id="web"]')
    team.b.wait_for("document.querySelector('#pane-graph g.wnode[data-id=\"web\"] circle.wunread') === null")


# ---------------------------------------------------------------------------------------------------------------------
# failure
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_a_graph_that_cannot_be_read_shows_the_banner_and_try_again_recovers(team):
    team.b.expect_failed("/api/graph", 500)
    team.fake.fail("/api/graph", 500)
    team.open("?tab=graph")
    team.b.wait_for("document.querySelector('#pane-graph .wbanner') && !document.querySelector('#pane-graph .wbanner').hidden")
    team.fake.request("POST", "/__fake/fail", {"path": "/api/graph", "status": None})            # the server is back
    team.b.click("#pane-graph [data-wretry]")
    graph_ready(team)
    team.b.wait_for("document.querySelector('#pane-graph .wbanner').hidden")


@browser_only
def test_a_view_that_throws_does_not_take_the_page_with_it(team):
    team.open()
    # a GraphView whose create() throws: the tab stays empty, the error is logged, J2's page keeps working
    team.js("(() => { const make = GraphView.create; GraphView.create = (host, o) => { if (o.mode === 'graph') throw new Error('boom'); return make(host, o); }; })()")
    team.tab("graph")
    team.settle(0.3)
    assert team.state()["mounted"]["graph"] is False
    assert any("boom" in str(e) or "GraphView.create" in str(e) for e in team.b.console_errors)
    team.b.clear_diagnostics()
    team.pool_tab("goal")
    assert team.hidden("#pane-goal") is False
    team.tab("orgchart")
    chart_ready(team)


# ---------------------------------------------------------------------------------------------------------------------
# sync 4 (docs/design/j2-sync-4.md 4.3, 4.4, 4.8): the strips, the start page's choice, the function chat, Esc, the Artifacts flyout, the studio, the library
# ---------------------------------------------------------------------------------------------------------------------
def capture(name: str) -> Any:
    return json.loads((J2_FIXTURES / name).read_text(encoding="utf-8"))


def agent_session(team: Page, who: str) -> str:
    return next(row["session_id"] for row in team.fake.get("/api/teams/web/agents")[1] if row["agent"] == who and row["kind"] == "function")


@browser_only
def test_the_rails_strip_goes_home_and_its_two_buttons_open_their_panes_and_say_which_is_on(team):
    team.open()
    graph, org = '#rail .railhome [data-tab="graph"]', '#rail .railhome [data-tab="orgchart"]'
    selected = lambda sel: team.js(f"document.querySelector({json.dumps(sel)}).getAttribute('aria-selected')")  # noqa: E731
    assert (selected(graph), selected(org)) == ("false", "false")
    assert team.js("document.getElementById('to-home').getAttribute('aria-label')") == "All teams, back to Home"
    team.b.click(graph)
    graph_ready(team)
    assert (selected(graph), selected(org)) == ("true", "false") and team.hidden("#pane-graph") is False
    team.b.click(org)
    chart_ready(team)
    assert (selected(graph), selected(org)) == ("false", "true") and team.hidden("#pane-graph") is True and team.hidden("#pane-orgchart") is False
    assert team.js("getComputedStyle(document.getElementById('rail')).width") == "84px"       # J2's own icon rail, with the strip inside it
    assert team.b.console_errors == [] and team.b.failed_requests == []


@browser_only
def test_the_start_page_offers_what_to_make_a_pick_is_one_post_and_a_reload_shows_it(team):
    team.open(view="simple")
    team.b.wait_for("!!document.getElementById('outsel')")
    assert team.js("document.getElementById('outsel').value") == "auto"
    assert team.js("Array.from(document.querySelectorAll('#outsel option'), o => o.value)") == ["auto", "prd", "hld", "lld", "website", "business_report", "project"]
    assert "dept=web" in team.requests("/api/engine/settings")[0]["query"]           # what the team's next run makes: asked of the team, not of all teams
    team.js("(() => { const s = document.getElementById('outsel'); s.value = 'prd'; s.dispatchEvent(new Event('change', {bubbles: true})); })()")
    team.wait_requests("/api/output", 1)
    posted = team.requests("/api/output")[0]
    assert (posted["method"], posted["body"], posted["token"]) == ("POST", {"type": "prd"}, True) and "dept=web" in posted["query"]
    assert team.fake.get("/api/engine/settings", dept="web")[1]["next_run"] == {"output": "prd"}
    team.open(view="simple")                                                       # a reload shows what was picked
    team.b.wait_for("!!document.getElementById('outsel')")
    assert team.js("document.getElementById('outsel').value") == "prd"
    assert team.b.console_errors == [] and team.b.failed_requests == []


@browser_only
def test_a_team_that_has_started_keeps_the_choice_closed_and_says_why(team):
    team.b.expect_failed("/api/output", 409)
    team.fake.post("/__fake/output", {"locked": True}, token=False)
    team.open(view="simple")
    team.b.wait_for("!!document.getElementById('outsel')")
    team.js("(() => { const s = document.getElementById('outsel'); s.value = 'website'; s.dispatchEvent(new Event('change', {bubbles: true})); })()")
    team.b.wait_for("document.getElementById('soutnote').textContent !== ''")      # (the select is disabled while the request is out, too: the note is the answer)
    assert team.js("document.getElementById('soutnote').textContent") == "The team has started; choose before the first message."
    assert team.js("[document.getElementById('outsel').disabled, document.getElementById('outsel').value]") == [True, "auto"]       # locked, the old choice is back


@browser_only
def test_the_chat_panel_of_a_function_shows_a_question_that_was_asked_before_the_page_opened(team):
    team.fake.stage("full")
    status, body = team.fake.request("POST", "/api/ask?dept=web", {"who": "adaptation", "q": "Why was W-3 scored below the gate?"}, token=True)
    assert status == 200 and body["from"] == "records"
    team.open("?tab=planmap", view=None)                                           # Adaptation's own view: the panel is in its function mode
    team.b.wait_for("document.getElementById('chath').textContent === 'Adaptation chat'")
    team.b.wait_for("Array.from(document.querySelectorAll('#chatfeed .msg.withyou')).some(e => /Why was W-3 scored below the gate/.test(e.textContent))")
    sid = agent_session(team, "adaptation")
    assert team.requests(f"/api/chats/{sid}/messages") and team.requests("/api/teams/web/agents")        # the lines came from the function's own session
    answers = team.js("Array.from(document.querySelectorAll('#chatfeed .msg.adaptation'), e => e.textContent)")
    assert any(body["answer"].split("\n")[0] in text for text in answers)
    assert team.js("document.getElementById('chatsub').textContent").endswith("answers from the run's records")
    assert team.b.console_errors == [] and team.b.failed_requests == []


@browser_only
def test_a_question_typed_in_the_chat_panel_is_one_post_and_both_lines_are_kept_in_the_functions_chat(team):
    team.fake.stage("full")
    team.open("?tab=planmap", view=None)
    team.b.wait_for("document.getElementById('chath').textContent === 'Adaptation chat' && !document.getElementById('box').disabled")
    team.js("chatSet(true)")                                                       # what the Chat button does (the attention pill sits on that button: the test below)
    team.b.wait_for("(() => { const r = document.getElementById('send').getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth; })()")       # the panel has slid in
    question = "Why was W-3 scored below the gate?"
    team.b.type("#box", question)
    team.b.click("#send")
    team.wait_requests("/api/ask", 1)
    asked = team.requests("/api/ask")[0]
    assert (asked["method"], asked["body"], asked["token"]) == ("POST", {"who": "adaptation", "q": question, "run": ""}, True) and "dept=web" in asked["query"]
    team.b.wait_for("Array.from(document.querySelectorAll('#chatfeed .msg.adaptation')).some(e => /From the records/.test(e.textContent))")
    lines = team.fake.get(f"/api/chats/{agent_session(team, 'adaptation')}/messages")[1]["messages"]
    assert [(m["role"], m["ask"]) for m in lines[-2:]] == [("user", "q"), ("agent", "records")] and lines[-2]["text"] == question
    assert team.count("/api/ask") == 1 and team.b.console_errors == [] and team.b.failed_requests == []


@browser_only
def test_escape_with_the_node_panel_open_closes_only_the_node_panel(team):
    team.open()
    team.js("chatSet(true)")
    assert team.js("CHAT.on") is True
    team.b.wait_for("document.querySelector('[data-agent=identity]') !== null")
    team.js("document.querySelector('[data-agent=identity]').click()")
    team.b.wait_for("!document.getElementById('nodepanel').hidden")
    assert team.js("document.body.classList.contains('nodeopen')") is True
    team.b.press("Escape")
    team.b.wait_for("document.getElementById('nodepanel').hidden")
    assert team.js("CHAT.on") is True                                              # the chat panel behind it stayed (E9b)
    team.b.press("Escape")
    team.b.wait_for("CHAT.on === false")                                           # the next Esc is the chat panel's own


@browser_only
def test_the_attention_pill_does_not_sit_on_the_chat_button(team):
    """Both are fixed to the bottom right (the pill, "1 needs you", at z 50; J2's Chat button at z 31): a click in the middle of the button must reach the button."""
    team.open("?tab=planmap", view=None)
    team.b.wait_for("!!document.querySelector('#attnpill a.apill')")
    assert team.js("(() => { const r = document.getElementById('chatfab').getBoundingClientRect(); "
                   "return document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2).closest('#chatfab') !== null; })()") is True


# What the pill is measured against in the Simple view (the studio): every control J2 draws there (buttons, links, fields, the switch, the tabs) and the regions that hold
# them. `named` are the controls the case must find drawn (so a pass is never an empty sweep): each is also asked whether a click in its middle reaches it.
PILL_AGAINST_THE_STUDIO = r"""(() => {
  const drawn = el => { const s = getComputedStyle(el); return s.display !== "none" && s.visibility !== "hidden" && el.getClientRects().length > 0; };
  const label = el => el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + (typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().split(/\s+/).join(".") : "")
    + " \"" + (el.innerText || el.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 24) + "\"";
  const apart = (a, b) => a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top;
  const pill = document.querySelector("#attnpill a.apill");
  const p = pill.getBoundingClientRect();
  const sweep = [...new Set([
    "#sview button", "#sview a[href]", "#sview input", "#sview textarea", "#sview select", "#sview [role=switch]", "#sview [role=tab]",     // J2's controls
    "#sview .swork", "#sview .sland", "#sview .sdock", "#sview .sasha", "#sview .sdrawer",                                                    // the regions that hold them
    "#sview > .steamstrip > *",                                                                                                              // the strip the pill rides in
  ].flatMap(sel => Array.from(document.querySelectorAll(sel))))].filter(drawn);
  const named = __NAMED__;
  const missing = named.filter(sel => !(document.querySelector(sel) && drawn(document.querySelector(sel))));
  const stolen = named.filter(sel => { const el = document.querySelector(sel); if (!el || !drawn(el)) return false; const b = el.getBoundingClientRect();
    const at = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return !(at && el.contains(at)); });
  const middle = document.elementFromPoint(p.left + p.width / 2, p.top + p.height / 2);
  const cs = getComputedStyle(document.querySelector(".apillhost"));
  const seconds = cs.transitionDuration.split(",").map(parseFloat);
  const moving = cs.transitionProperty.split(",").map(s => s.trim()).filter((_, i) => seconds[i % seconds.length] > 0);        // what the pill's box animates, if anything
  return {
    over: sweep.filter(el => !apart(p, el.getBoundingClientRect())).map(label),
    swept: sweep.length, missing, stolen,
    inside: p.left >= 0 && p.top >= 0 && p.right <= innerWidth && p.bottom <= innerHeight,
    clickable: !!middle && middle.closest("a.apill") === pill,
    moving, box: [p.left, p.top, p.right, p.bottom].map(Math.round),
  };
})()"""


@pytest.fixture()
def finished_team(team, fake_server, monkeypatch) -> Page:
    """The team after a run that finished: J2's captured snapshot is of a run that paused on a question, so its outcome, pause and status are set to what a finished run says
    (the Simple view then draws its finish bar, with Open full view at its right end). The fake's cache of that capture is put back after the test."""
    j2 = fake_server.state.fx.j2
    snapshot = json.loads(j2.raw("state.json"))
    snapshot.update(outcome="Done. The site is ready.", paused=None, status="done")
    monkeypatch.setitem(j2._cache, "state.json", json.dumps(snapshot).encode())
    return team


STUDIO_NAMED = ["#sfinish [data-full]", "#sauto", "#stheme2"]               # drawn at every width: Open full view, Decide for me, the dark-mode button
STUDIO_SIZES = [
    (1280, 860, STUDIO_NAMED + ["#schatbtn", "#sdetail", "#sopen", ".srail"]),     # a laptop: the toolbar with Chat, Detailed view and Open the site, and the team rail
    (375, 812, STUDIO_NAMED + [".sdock", ".sdock .sdkchat"]),                       # a phone: the two-row toolbar and the dock under it all (the team, the plan, Chat)
]


@browser_only
@pytest.mark.parametrize("width, height, named", STUDIO_SIZES, ids=[f"{w}x{h}" for w, h, _ in STUDIO_SIZES])
def test_the_attention_pill_is_clear_of_every_control_of_the_simple_view(finished_team, width, height, named):
    """The studio is full-bleed, so the pill (fixed, z 50) sat on one of J2's controls at every width: over the lower right of Open full view at 1280 x 860, over the lower edge of
    Decide for me and the dark-mode button at 375 x 812, and a click there went to the pill. It rides in the team strip at the very top now: in the Simple view no control of J2's, and
    none of the regions that hold them, is under its box, with the chat closed and open; it is on screen, a click in its middle reaches it, and it has no transition of layout."""
    team = finished_team
    run = json.loads((J2_FIXTURES / "runs.json").read_text(encoding="utf-8"))["live"]
    team.b.set_size(width, height)
    team.open(f"?run={run}", view="simple")
    team.b.wait_for("!!document.querySelector('#attnpill a.apill') && !!document.querySelector('#sfinish [data-full]')")
    assert team.b.text("#attnpill a.apill") == "1 needs you" and team.js("document.body.classList.contains('simple')") is True
    measure = lambda names: team.js(PILL_AGAINST_THE_STUDIO.replace("__NAMED__", json.dumps(names)))  # noqa: E731
    closed = measure(named)
    assert closed["missing"] == [] and closed["swept"] > len(named), closed          # the controls to clear are really on screen
    assert closed["over"] == [] and closed["stolen"] == [], closed
    assert closed["inside"] is True and closed["clickable"] is True and set(closed["moving"]) <= {"transform", "opacity"}, closed
    team.js("sChatOpen(true)")                                                      # Asha's panel (a column at 1280, a sheet at 375) brings the message box and Send
    team.b.wait_for("document.getElementById('ssend').getClientRects().length > 0")
    opened = measure([n for n in named if n != "#sfinish [data-full]"] + ["#sbox", "#ssend"])        # (at 375 J2's own sheet covers the finish bar while Asha's panel is open)
    assert opened["missing"] == [] and opened["over"] == [] and opened["stolen"] == [], opened
    assert opened["inside"] is True and opened["clickable"] is True, opened
    assert team.b.console_errors == [] and team.b.failed_requests == []


# `.apill` names two things: the attention pill (a link in `.apillhost`) and the status pill of a work atom (a span in `.atomcard`). The atoms' rules used to be the later ones with the
# same weight, so they drew the attention pill too, as a 21px box with the atoms' 10px corners and a plain border, and the strip's room for it was fitted to that box (0.3.1).
PILL_LOOKS = r"""(() => {
  const probe = document.createElement("span");
  const colour = value => { probe.style.color = value; document.body.appendChild(probe); const c = getComputedStyle(probe).color; probe.remove(); return c; };
  const look = el => { const s = getComputedStyle(el);
    return {display: s.display, padding: [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft].join(" "), size: s.fontSize, radius: s.borderTopLeftRadius, border: s.borderTopColor}; };
  const card = document.createElement("details");
  card.className = "atomcard";
  card.innerHTML = '<span class="apill st-closed">goal reached, and checked</span>';
  document.body.appendChild(card);
  const out = {pill: look(document.querySelector("#attnpill a.apill")), atom: look(card.firstElementChild), accent: colour("var(--accent)"), ok: colour("var(--ok)")};
  card.remove();
  return out;
})()"""


@browser_only
def test_the_attention_pill_is_drawn_by_its_own_rules_and_an_atoms_status_pill_by_the_atoms(finished_team):
    """Its own rules: a flex link with 13.5px type, 14px at the sides, 99px corners and the accent border; the 6px above and below that a corner chip has are kept where it sits in
    the bottom corner (the Detailed view from 901 px, the console) and given up where it rides in a row at the top (the Simple view's strip, a phone or tablet width), because
    that row is 27px tall. The status pill of an atom card keeps its own box: inline, 9px at the sides, 12.5px type, 10px corners and the colour of its state."""
    team = finished_team
    run = json.loads((J2_FIXTURES / "runs.json").read_text(encoding="utf-8"))["live"]
    for width, height, view, rows in [(1280, 860, "simple", "0px"), (1280, 860, "detail", "6px"), (375, 812, "detail", "0px"), (375, 812, "simple", "0px")]:
        team.b.set_size(width, height)
        team.open(f"?run={run}", view=view)
        team.b.wait_for("!!document.querySelector('#attnpill a.apill')")
        seen = team.js(PILL_LOOKS)
        where = f"{view} at {width}"
        assert seen["pill"] == {"display": "inline-flex", "padding": f"{rows} 14px {rows} 14px", "size": "13.5px", "radius": "99px", "border": seen["accent"]}, (where, seen)
        assert seen["atom"] == {"display": "inline-block", "padding": "0px 9px 0px 9px", "size": "12.5px", "radius": "10px", "border": seen["ok"]}, (where, seen)
    assert team.b.console_errors == [] and team.b.failed_requests == []


# The pill with the most to say ("2 need you, 1 to try again") and the longest team name the strip is asked to hold, in the Simple view at every width from a small phone to a wide
# screen, in both themes (the colours differ, the boxes do not), with Asha's panel closed and open: no control of J2's under the pill, the pill on screen and under a click, the
# name's text (every line of it) and "All teams" stopping short of it, no sideways scroll. Measured on the live page, by box. (The Detailed view is swept by the case after this one,
# the console in test_dept_attention.py.)
PILL_AND_STRIP = r"""(() => {
  const drawn = el => { const s = getComputedStyle(el); return s.display !== "none" && s.visibility !== "hidden" && el.getClientRects().length > 0; };
  const apart = (a, b) => a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top;
  const pill = document.querySelector("#attnpill a.apill");
  const p = pill.getBoundingClientRect();
  const sweep = "button, a[href], input, textarea, select, [role=switch], [role=tab], summary";
  const over = Array.from(document.querySelectorAll(sweep)).filter(el => !el.closest("#attnpill") && drawn(el))
    .filter(el => { const b = el.getBoundingClientRect(); return b.width > 0 && b.height > 0 && !apart(p, b); })
    .map(el => el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + " \"" + (el.innerText || el.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 24) + "\"");
  const out = {width: innerWidth, over, inside: p.left >= 0 && p.top >= 0 && p.right <= innerWidth && p.bottom <= innerHeight,
               clickable: (m => !!m && m.closest("a.apill") === pill)(document.elementFromPoint(p.left + p.width / 2, p.top + p.height / 2)),
               sideways: document.documentElement.scrollWidth > innerWidth, size: [Math.round(p.width), Math.round(p.height)], gap: null, linkApart: null};
  const strip = document.querySelector("#sview > .steamstrip");
  if (strip && drawn(strip)) {
    const name = strip.querySelector("b");
    const range = document.createRange();
    range.selectNodeContents(name);
    out.gap = Math.round(p.left - Math.max(...Array.from(range.getClientRects()).map(r => r.right)));
    out.linkApart = apart(p, strip.querySelector("a").getBoundingClientRect());
  }
  return out;
})()"""
LONG_TEAM_NAME = "Corner Bakery and Coffee Roasters of the Greater Metropolitan Area Branch Office"
CRASH_ELSEWHERE = {"kind": "problem", "tone": "err", "task_id": "tsk_00000000beef", "dept_id": "sales", "dept_name": "Sales", "title": "Quote", "status": "crashed",
                   "text": 'Sales ran into a problem on "Quote"', "outcome": "", "at": "2026-11-04T10:00:00Z", "since_s": 60, "retry": True}
PILL_WIDTHS = [320, 360, 375, 414, 480, 600, 768, 900, 901, 1024, 1280, 1440, 1920]


@browser_only
def test_the_attention_pill_and_the_team_strip_clear_each_other_from_320_to_1920_wide_in_both_themes(finished_team):
    team = finished_team
    run = json.loads((J2_FIXTURES / "runs.json").read_text(encoding="utf-8"))["live"]
    team.fake.request("POST", "/__fake/heads-up", {"items": [CRASH_ELSEWHERE]})           # one thing for the owner here and one problem elsewhere: "2 need you 1 to try again"
    problems: list[tuple] = []
    for theme in ("light", "dark"):
        team.b.set_theme(theme)
        for width in PILL_WIDTHS:
            team.b.set_size(width, 812 if width <= 600 else (1080 if width >= 1900 else 860))
            team.open(f"?run={run}", view="simple")
            team.b.wait_for("document.querySelector('#attnpill a.apill') && document.querySelector('#attnpill a.apill').textContent === '2 need you 1 to try again'")
            team.b.wait_for("!!document.querySelector('#sfinish [data-full]')")
            team.js("document.querySelector('#sview > .steamstrip b').textContent = " + json.dumps(LONG_TEAM_NAME))          # the strip's name, as long as a name can reasonably be
            for chat in (False, True):
                if chat:
                    team.js("sChatOpen(true)")
                    team.b.wait_for("document.getElementById('ssend').getClientRects().length > 0")
                seen = team.js(PILL_AND_STRIP)
                clear = seen["gap"] is not None and seen["gap"] >= 8 and seen["linkApart"] is True               # 8 px between the name's text and the pill, at least
                if seen["over"] or not (seen["inside"] and seen["clickable"] and clear) or seen["sideways"]:
                    problems.append((theme, width, "Asha's panel open" if chat else "closed", seen))
    assert problems == [], problems
    assert team.b.console_errors == [] and team.b.failed_requests == []


# The pill in the Detailed view of a team page (and, in test_dept_attention.py, on the console), measured the way the D1 cases measure it in the Simple view: against every control the page draws
# and the regions that hold them, its box on screen, a click in its middle reaching it, and the controls it must not sit on taking their own clicks. `under` is what the pill is visibly on
# (the layer right below it, at some point of its box, is the control: a control that J2's chat panel covers while the chat is open is not under the pill, a control the pill hides is);
# `over` is the plainer test, any control whose box meets the pill's, and is asked where only the pill can cover a control (the chat closed, the pill in a row of its own at the top).
PILL_AGAINST_THE_PAGE = r"""(() => {
  const drawn = el => { const s = getComputedStyle(el); return s.display !== "none" && s.visibility !== "hidden" && el.getClientRects().length > 0; };
  const label = el => el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + " \"" + (el.innerText || el.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 24) + "\"";
  const apart = (a, b) => a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top;
  const pill = document.querySelector("#attnpill a.apill");
  const p = pill.getBoundingClientRect();
  const controls = Array.from(document.querySelectorAll("button, a[href], input, textarea, select, summary, [role=switch], [role=tab], [tabindex]:not([tabindex='-1'])"))
    .filter(el => !el.closest("#attnpill") && drawn(el) && el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0);
  const under = el => {
    const b = el.getBoundingClientRect();
    const x0 = Math.max(b.left, p.left), x1 = Math.min(b.right, p.right), y0 = Math.max(b.top, p.top), y1 = Math.min(b.bottom, p.bottom);
    if (x1 <= x0 || y1 <= y0) return false;
    for (let i = 0; i < 8; i++) for (let j = 0; j < 4; j++) {
      const stack = document.elementsFromPoint(x0 + (x1 - x0) * (i + .5) / 8, y0 + (y1 - y0) * (j + .5) / 4);
      if (!stack.length || stack[0].closest("a.apill") !== pill) continue;                        // that point of the box is outside the pill's rounded shape
      const below = stack.find(e => !e.closest("#attnpill"));
      if (below && el.contains(below)) return true;
    }
    return false;
  };
  const named = __NAMED__;
  const regions = __REGIONS__.flatMap(sel => Array.from(document.querySelectorAll(sel))).filter(drawn);
  const missing = named.filter(sel => !(document.querySelector(sel) && drawn(document.querySelector(sel))));
  const stolen = named.filter(sel => { const el = document.querySelector(sel); if (!el || !drawn(el)) return false; const b = el.getBoundingClientRect();
    const at = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return !(at && el.contains(at)); });
  const middle = document.elementFromPoint(p.left + p.width / 2, p.top + p.height / 2);
  return {
    width: innerWidth, box: [p.left, p.top, p.right, p.bottom].map(Math.round), swept: controls.length,
    over: controls.filter(el => !apart(p, el.getBoundingClientRect())).map(label), under: controls.filter(under).map(label),
    regions: regions.filter(el => !apart(p, el.getBoundingClientRect())).map(label), missing, stolen,
    inside: p.left >= 0 && p.top >= 0 && p.right <= innerWidth && p.bottom <= innerHeight,
    clickable: !!middle && middle.closest("a.apill") === pill, sideways: document.documentElement.scrollWidth > innerWidth,
  };
})()"""


def measure_the_pill(browser: Any, named: Any = (), regions: Any = ()) -> dict:
    """The pill's place on the page in `browser`: `named` are controls that must be drawn and take a click in their middle, `regions` the boxes the pill must stay out of."""
    return browser.js(PILL_AGAINST_THE_PAGE.replace("__NAMED__", json.dumps(list(named))).replace("__REGIONS__", json.dumps(list(regions))))


def pill_problems(seen: dict, *, boxes: bool, regions: bool) -> list[str]:
    """What is wrong with the pill's place in one measurement (an empty list: nothing). `boxes` asks the plainer test too (no control's box meets the pill's), `regions` that no region does."""
    out = []
    if seen["missing"]:
        out.append(f"not drawn: {seen['missing']}")
    if seen["under"]:
        out.append(f"on {seen['under']}")
    if boxes and seen["over"]:
        out.append(f"meets {seen['over']}")
    if regions and seen["regions"]:
        out.append(f"meets the region of {seen['regions']}")
    if seen["stolen"]:
        out.append(f"takes the click of {seen['stolen']}")
    if not seen["inside"]:
        out.append(f"is off the screen at {seen['box']}")
    if not seen["clickable"]:
        out.append("is not what a click in its middle reaches")
    if seen["sideways"]:
        out.append("the page scrolls sideways")
    return out


def pill_sweep_height(width: int) -> int:
    return 812 if width <= 600 else (1080 if width >= 1900 else 860)


PILL_ROW_WIDTH = 900                                                              # up to here the pill rides in a row at the top (below, in the corner above J2's Chat button)
DETAIL_REGIONS = ["#needs", "#dview main", "#rail"]                                # the Needs you box, the page's cards and the icon rail: what the pill's row keeps clear of
CHAT_SLID_IN = ("(() => { const r = document.getElementById('send').getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth; })() "
                "&& document.getElementById('attnpill').getAnimations().length === 0")      # J2's chat panel is in place and the pill has stopped moving (it moves under the panel's header)


def detail_ready(team: Page, text: str) -> None:
    team.b.wait_for("!!document.querySelector('#attnpill a.apill') && document.querySelector('#attnpill a.apill').textContent === " + json.dumps(text)
                    + " && !!document.querySelector('#needs [data-needmsg]')")


DETAIL_WIDTHS = [(320, 812), (375, 812), (414, 812), (480, 812), (600, 812), (768, 860), (900, 860)]


@browser_only
@pytest.mark.parametrize("width, height", DETAIL_WIDTHS, ids=[str(w) for w, _ in DETAIL_WIDTHS])
def test_the_attention_pill_has_a_row_of_its_own_above_the_needs_you_box_of_the_detailed_view(team, width, height):
    """At 900px and under the pill rode at 58px from the top, where J2's Detailed view has no header: it sat on the Needs you box, over the question and, from 414 to 900px wide, over the
    "Answer in Chat" button (the button's middle gave the click to the pill, which goes to Home). The page keeps a row for it above that box now: no control and no region of the page is
    under the pill, the button takes its own click (it opens the chat and the page stays), and with the chat open (a panel over the page here) the pill sits clear of the panel's buttons."""
    team.b.set_size(width, height)
    team.open(view="detail")
    detail_ready(team, "1 needs you")
    seen = measure_the_pill(team.b, ["#needs [data-needmsg]", "#chatfab"], DETAIL_REGIONS)
    assert seen["missing"] == [] and seen["swept"] > 15, seen                      # the controls to clear are really on screen
    assert pill_problems(seen, boxes=True, regions=True) == [], seen
    team.b.click("#needs [data-needmsg]")                                          # a real click in the middle of the button: it opens the chat, the page does not go to Home
    team.b.wait_for("CHAT.on === true")
    assert team.js("location.pathname") == f"/d/{DEPT}/"
    team.b.wait_for(CHAT_SLID_IN)
    opened = measure_the_pill(team.b, ["#chatx"], [])
    assert pill_problems(opened, boxes=False, regions=False) == [], opened
    assert team.b.console_errors == [] and team.b.failed_requests == []


@browser_only
def test_the_attention_pill_is_clear_of_the_detailed_view_from_320_to_1920_wide_in_both_themes(team):
    """The pill with the most to say ("2 need you, 1 to try again") in the Detailed view at every width from a small phone to a wide screen, in both themes, with the chat closed and open: no
    control of J2's under the pill, the pill on screen and under a click, J2's Chat button, Answer in Chat and the chat's close button taking their own clicks, no sideways scroll; at 900px
    and under, where the pill rides in a row at the top, no control's box and none of the Needs you box, the cards and the rail meets it either."""
    team.fake.request("POST", "/__fake/heads-up", {"items": [CRASH_ELSEWHERE]})           # one thing for the owner here and one problem elsewhere
    problems: list[tuple] = []
    for theme in ("light", "dark"):
        team.b.set_theme(theme)
        for width in PILL_WIDTHS:
            team.b.set_size(width, pill_sweep_height(width))
            team.open(view="detail")
            detail_ready(team, "2 need you 1 to try again")
            row = width <= PILL_ROW_WIDTH
            for chat in (False, True):
                if chat:
                    team.js("chatSet(true)")
                    team.b.wait_for(CHAT_SLID_IN)
                seen = measure_the_pill(team.b, ["#chatx"] if chat else ["#needs [data-needmsg]", "#chatfab"], DETAIL_REGIONS if row and not chat else [])
                found = pill_problems(seen, boxes=row and not chat, regions=row and not chat)
                if found:
                    problems.append((theme, width, "chat open" if chat else "chat closed", found, seen["box"]))
            team.js("chatSet(false, false)")                                               # J2 remembers an open chat: the next load starts the way this one ends
    assert problems == [], problems
    assert team.b.console_errors == [] and team.b.failed_requests == []


@browser_only
def test_the_node_panel_hides_the_chat_panel_behind_it_from_the_eye_and_the_keyboard(team):
    team.open()
    team.js("chatSet(true)")
    assert team.js("getComputedStyle(document.getElementById('chatp')).visibility") == "visible"
    team.b.wait_for("document.querySelector('[data-agent=identity]') !== null")
    team.js("document.querySelector('[data-agent=identity]').click()")
    team.b.wait_for("!document.getElementById('nodepanel').hidden")
    assert team.js("[getComputedStyle(document.getElementById('chatp')).visibility, getComputedStyle(document.getElementById('chatfab')).visibility]") == ["hidden", "hidden"]


@browser_only
def test_the_rails_artifacts_flyout_lists_the_groups_of_the_run_and_a_click_opens_artifacts(team):
    groups = capture("artifacts-groups.json")["groups"]
    team.open()
    team.b.click('#rail [data-ri="artifacts"]')
    team.b.wait_for("!document.getElementById('rfly').hidden")
    assert team.js("Array.from(document.querySelectorAll('#rfl [data-artgo]'), e => [e.dataset.artgo, e.firstChild.textContent])") == [[g["id"], g["label"]] for g in groups]
    team.b.click('#rfl [data-artgo="records"]')
    team.b.wait_for("!document.getElementById('pane-artifacts').hidden")
    assert team.js("document.querySelector('.tabs [data-tab=artifacts]').getAttribute('aria-selected')") == "true" and team.hidden("#rfly") is True
    assert team.requests("/api/artifacts/groups") and "dept=web" in team.requests("/api/artifacts/groups")[0]["query"]
    assert team.b.console_errors == [] and team.b.failed_requests == []


@browser_only
def test_a_part_of_the_studio_opens_its_record_as_the_run_recorded_it(team):
    team.open(view="simple")
    team.b.wait_for("!!document.querySelector('[data-go=\"W-2\"]')")
    team.b.click('[data-go="W-2"]')
    team.b.wait_for("!document.getElementById('sdrawer').hidden")
    team.wait_requests("/api/record", 1)
    asked = team.requests("/api/record")[0]["query"]
    assert "sec=W-2" in asked and "dept=web" in asked
    record = capture("record-W-2.json")
    team.b.wait_for(f"document.getElementById('sdrawer').innerText.includes({json.dumps(record['goal'])})")
    text = team.js("document.getElementById('sdrawer').innerText")
    assert "Method" in text and all(o["text"] in text for o in record["output"])      # the method is reworded for the reader (a workflow is a task there)
    assert team.b.console_errors == [] and team.b.failed_requests == []


@browser_only
def test_the_decide_for_me_switch_is_one_post_and_follows_the_server_after_a_poll(team):
    team.open(view="simple")
    team.b.wait_for("!!document.getElementById('sauto')")
    state = lambda: team.js("document.getElementById('sauto').getAttribute('aria-checked')")  # noqa: E731
    assert state() == "false"
    team.b.click("#sauto")
    team.wait_requests("/api/settings", 1)
    posted = team.requests("/api/settings")[0]
    assert (posted["method"], posted["body"], posted["token"]) == ("POST", {"decide_for_me": True}, True) and "dept=web" in posted["query"]
    team.b.wait_for("document.getElementById('sauto').getAttribute('aria-checked') === 'true'")
    team.fake.request("POST", "/api/settings?dept=web", {"decide_for_me": False}, token=True)                 # another tab turns it off: the poll puts the switch back
    team.b.wait_for("document.getElementById('sauto').getAttribute('aria-checked') === 'false'", timeout=15)
    assert team.b.console_errors == [] and team.b.failed_requests == []


@browser_only
def test_the_teams_library_page_is_the_same_page_and_draws_the_catalog_of_the_one_library(team):
    catalog = capture("catalog.json")
    team.b.goto(f"{team.server.url}/d/web/library")
    team.b.wait_for("window.DeptExt !== undefined && DeptExt.state().started === true")
    team.b.wait_for("CAT.loaded === true")
    assert team.js("[location.pathname, CAT.on, SutraCtx.libraryPath, SutraCtx.onLibrary()]") == ["/d/web/library", True, "/d/web/library", True]
    assert "dept=web" in team.requests("/api/catalog")[0]["query"]                    # the data is global, the path says the team
    shelf = catalog["shelf"]      # sync 6: the page draws the two shelves (Artifacts, Artifact templates), not the "By run" list of sync 5
    assert team.js("[CAT.arts.length, CAT.rts.length, CAT.types.length]") == [len(catalog["artifacts"]), len(shelf["run_templates"]), len(shelf["types"])]
    assert team.js("document.body.classList.contains('libpage')") is True and team.hidden("#pane-catalog") is False
    shown = team.js("document.getElementById('pane-catalog').innerText")
    assert all(rt["name"] in shown for rt in shelf["run_templates"]) and "Artifacts" in shown and "Artifact templates" in shown      # every run template of the shelf, from catalog.json
    assert team.b.console_errors == [] and team.b.failed_requests == []


# What is drawn of J2's Needs you box (`#needs`). J2's page hides it on the library page with the `hidden` attribute ("no run here: nothing needs you"), and J2's own
# `.needs{display:flex}` is an author rule, which beats the browser's `[hidden]{display:none}`: an empty bordered box was drawn above the catalog.
NEEDS_BOX = r"""(() => {
  const el = document.getElementById("needs"), r = el.getBoundingClientRect();
  return {hidden: el.hidden, display: getComputedStyle(el).display, drawn: el.getClientRects().length > 0, height: Math.round(r.height), children: el.children.length,
          text: el.innerText.trim().replace(/\s+/g, " "), asks: el.querySelectorAll("[data-needmsg]").length,
          anyDrawn: Array.from(document.querySelectorAll(".needs")).filter(e => e.getClientRects().length > 0).length};
})()"""
NEEDS_SIZES = [(1280, 860), (375, 812)]


@pytest.fixture()
def idle_team(finished_team, fake_server, monkeypatch) -> Page:
    """The finished team with nothing left to answer: J2 also reads a paused message of Identity at the end of the chat as a question, so the pause is taken off the transcript too."""
    j2 = fake_server.state.fx.j2
    snapshot = json.loads(j2.raw("state.json"))                      # the finished run of `finished_team`
    for line in snapshot["chat"]:
        line.pop("pause", None)
    monkeypatch.setitem(j2._cache, "state.json", json.dumps(snapshot).encode())
    return finished_team


@browser_only
@pytest.mark.parametrize("width, height", NEEDS_SIZES, ids=[str(w) for w, _ in NEEDS_SIZES])
def test_the_library_page_draws_no_empty_needs_you_box(team, width, height):
    """There is no run on the library page, so J2's script hides the Needs you box and never paints into it. The box is `hidden` and has no child, and it is not drawn: no bordered
    strip of 18px (the box's padding and border) sits above the catalog at a laptop or a phone width."""
    team.b.set_size(width, height)
    team.b.goto(f"{team.server.url}/d/{DEPT}/library")
    team.b.wait_for("window.DeptExt !== undefined && DeptExt.state().started === true")
    team.b.wait_for("CAT.loaded === true")
    seen = team.js(NEEDS_BOX)
    assert seen["hidden"] is True and seen["children"] == 0 and seen["text"] == "", seen            # J2's page hid an empty box: that is what is measured
    assert (seen["display"], seen["drawn"], seen["anyDrawn"], seen["height"]) == ("none", False, 0, 0), seen
    assert team.hidden("#pane-catalog") is False and team.js("document.body.classList.contains('libpage')") is True       # and this is the library page, with its catalog
    assert team.b.console_errors == [] and team.b.failed_requests == []


@browser_only
@pytest.mark.parametrize("width, height", NEEDS_SIZES, ids=[str(w) for w, _ in NEEDS_SIZES])
@pytest.mark.parametrize("asked", [True, False], ids=["a question", "nothing to answer"])
def test_a_team_page_still_draws_its_needs_you_box(request, asked, width, height):
    """What hides the box on the library page does not reach a team page: with a question for the owner it is drawn with the question and its "Answer in Chat" button, and with nothing to
    answer (a run that finished) it is drawn as J2 draws it, "Nothing needs you right now"."""
    team = request.getfixturevalue("team" if asked else "idle_team")
    team.b.set_size(width, height)
    team.open(view="detail")
    team.b.wait_for("!!document.querySelector('#needs .needbadge')")
    seen = team.js(NEEDS_BOX)
    assert seen["hidden"] is False and seen["display"] == "flex" and seen["drawn"] is True and seen["anyDrawn"] == 1 and seen["height"] > 40, seen
    if asked:
        assert seen["asks"] == 1 and seen["text"].startswith("Needs you 1 "), seen
    else:
        assert seen["asks"] == 0 and seen["text"].startswith("Needs you 0 Nothing needs you right now."), seen
    assert team.b.console_errors == [] and team.b.failed_requests == []


# The library page from 901px: J2 stops its content card 76px above the bottom of the window (room for the Chat button) and the pill rides 10px above that button, so the pill's box (34px
# tall, 102px to 68px from the bottom) was 26px inside the card: it covered the catalog's last row buttons, at 901px with the chat closed and open and at 1024 and 1280px with it open (8 of the
# 20 cells from 901px, light and dark; at other heights of the window, 600 to 1300px, 8 of 18 cells, which rows are under it depends on the height). While the pill shows, the card now ends above it.
LIBRARY_CARD_AND_PILL = r"""(() => {
  const card = document.querySelector("#dview .work").getBoundingClientRect(), pill = document.querySelector("#attnpill a.apill"), main = document.querySelector("#dview main");
  return {card: Math.round(card.bottom), pill: pill ? Math.round(pill.getBoundingClientRect().top) : null, pad: getComputedStyle(main).paddingBottom, height: innerHeight};
})()"""


def library_ready(team: Page, text: str | None = None) -> None:
    team.b.goto(f"{team.server.url}/d/{DEPT}/library")
    team.b.wait_for("window.DeptExt !== undefined && DeptExt.state().started === true")
    team.b.wait_for("CAT.loaded === true")
    if text:
        team.b.wait_for("!!document.querySelector('#attnpill a.apill') && document.querySelector('#attnpill a.apill').textContent === " + json.dumps(text))


@browser_only
def test_the_attention_pill_is_clear_of_the_library_page_from_901_to_1920_wide_in_both_themes(team):
    """The pill with the most to say on the library page at every width from 901px, in both themes, with the chat closed and open: no control of the catalog is under the pill, the pill is on
    screen and under a click, J2's Chat button (the chat's close button while it is open) takes its own click, no sideways scroll, and the card of the catalog ends above the pill's top."""
    team.fake.request("POST", "/__fake/heads-up", {"items": [CRASH_ELSEWHERE]})           # one thing for the owner here and one problem elsewhere
    problems: list[tuple] = []
    for theme in ("light", "dark"):
        team.b.set_theme(theme)
        for width in [w for w in PILL_WIDTHS if w > PILL_ROW_WIDTH]:
            team.b.set_size(width, pill_sweep_height(width))
            library_ready(team, "2 need you 1 to try again")
            for chat in (False, True):
                if chat:
                    team.js("chatSet(true)")
                    team.b.wait_for(CHAT_SLID_IN)
                seen = measure_the_pill(team.b, ["#chatx"] if chat else ["#chatfab"], [])
                found = pill_problems(seen, boxes=False, regions=False)                    # the catalog's list rows are clipped by the card: what is under the pill is what is drawn there
                edge = team.js(LIBRARY_CARD_AND_PILL)
                if edge["card"] > edge["pill"]:
                    found.append(f"the card of the catalog ends at {edge['card']}, under the pill's top at {edge['pill']}")
                if found:
                    problems.append((theme, width, "chat open" if chat else "chat closed", found, seen["box"]))
            team.js("chatSet(false, false)")                                               # J2 remembers an open chat: the next load starts the way this one ends
    assert problems == [], problems
    assert team.b.console_errors == [] and team.b.failed_requests == []


@browser_only
def test_the_library_page_makes_room_for_the_attention_pill_only_while_it_shows_and_only_there(team):
    """The 34px of room is the library page's, and only while the pill shows: with nothing for the owner the card keeps J2's own bottom edge (76px up, the Chat button's room), and the
    Detailed view of a team page, with the pill, keeps J2's 76px too (its cards are the page's own to size)."""
    team.b.set_size(1280, 860)
    team.fake.stage("3")                                                           # the owner answered: nothing needs them, and the fake has no problem elsewhere
    library_ready(team)
    team.wait_requests("/api/needs-you", 1)
    team.wait_requests("/api/heads-up", 1)
    team.settle(0.5)                                                               # the first read is drawn
    assert team.hidden("#attnpill") is True
    idle = team.js(LIBRARY_CARD_AND_PILL)
    assert (idle["pad"], idle["card"]) == ("76px", idle["height"] - 76), idle
    team.fake.stage("2")
    library_ready(team, "1 needs you")
    shown = team.js(LIBRARY_CARD_AND_PILL)
    assert (shown["pad"], shown["card"] <= shown["pill"]) == ("110px", True), shown
    team.open(view="detail")
    detail_ready(team, "1 needs you")
    assert team.js(LIBRARY_CARD_AND_PILL)["pad"] == "76px"
    assert team.b.console_errors == [] and team.b.failed_requests == []
