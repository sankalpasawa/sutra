"""The Workflow graph and Org chart views (UI-5): sutra_app/ui/static/js/{graph_view,orgchart_view}.js and css/sutra-graph.css.

docs/design/ui.md sections 3.3, 6.1 to 6.3, 7, 9 (X4, X5) and 10; S3-web-13; S4-fnodes-10; D75, D80.

Two kinds of test, both against what a page loads:

  node      the pure helpers of graph_view.js (`GraphView.helpers`: what a toggle asks for and whether the data in hand can serve it,
            narrowing a graph, the pan and zoom arithmetic, the sentence for screen readers, the legend). One node process for all of
            them. They run in the merge gate.
  browser   the views in a real headless Chrome (marker `browser`, `SUTRA_BROWSER=1`) on the mount page of UI-0 (`/__fake/mount/graph.html`,
            which fetches what Home and the department page would and calls update()) against the fake backend. One Chrome and one
            fake server serve the whole module; a test opens its own page and starts from stage 1 with an empty request log and empty
            local storage. A test that breaks a request on purpose empties the diagnostics itself (`clear_diagnostics`); every other
            test fails on a console error or a failed request.

The mount page loads /ui/css/j2.css, which UI-2 adds. Until it has merged the module serves a copy of the static folder with a small
stand-in sheet (the theme tokens and the few j2.css rules the pane relies on); with the real sheet the real folder is served.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

import fake_backend  # tests/ui is on sys.path (conftest.py)

REPO = Path(__file__).resolve().parents[2]
STATIC = REPO / "sutra_app" / "ui" / "static"
JS = STATIC / "js"
NODE = shutil.which("node")
browser_only = pytest.mark.browser

NINE_WORDS = {"idle", "running", "waiting", "waiting_on_you", "fault", "filed", "done_unchecked", "left_open", "not_made"}

# J2's theme tokens (dark) and the few j2.css rules the panes use, for a checkout in which UI-2 has not merged yet.
STAND_IN_CSS = """
:root{color-scheme:dark;--bg:#161513;--panel:#1c1b19;--panel2:#24221f;--ink:#ece6dc;--muted:#9a9186;--line:#2e2b27;--on:#161513;--edge:#857a6c;
--validator:#e0b25c;--bad:#ef8f7a;--ok:#9fc08a;--accent:#a58be6;--e-reads:#8fa8c8;--e-makes:#e0a458;--e-fix:#d9785f;--skyink:#141310;
--sky0:#24201b;--sky1:#100f0d;--shadow:rgb(0 0 0 / .45);--mono:Menlo,monospace;--star:#f3e6c8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14.5px/1.5 Arial,sans-serif}
.maphead{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 10px}.maphead h3{margin:0 8px 0 0}
.mappill{border-radius:12px;padding:2px 10px;border:1px solid var(--line);font-size:13px}
.mapviews{display:inline-flex;border:1px solid var(--line);border-radius:12px;overflow:hidden;margin-left:auto}
.mapviews button{border:0;background:transparent;color:var(--ink);padding:2px 12px;font:inherit;font-size:13px;cursor:pointer}
.mapviews button[aria-pressed="true"]{background:var(--line);font-weight:600}
svg path[data-edge]{fill:none;stroke-width:1.4px!important;stroke-linecap:round;stroke-dasharray:none!important;animation:none!important}
svg path[data-edge].loop{stroke-dasharray:4 4!important}
svg.ehot path[data-edge]:not(.hot),svg path[data-edge].dim{opacity:.25!important}
svg path[data-edge].hot{opacity:1!important;stroke-width:2.4px!important}
.earr{stroke-width:1;stroke-linejoin:round}
"""


# ---------------------------------------------------------------------------------------------------------------------
# Wire shapes the tests build
# ---------------------------------------------------------------------------------------------------------------------
def gnode(id: str, kind: str = "step", label: str | None = None, status: str = "idle", **extra: Any) -> dict:
    node = {"id": id, "kind": kind, "label": label if label is not None else id, "status": status, "detail": "", "chat_session_id": None,
            "org_node_id": None, "dept_id": None, "task_id": None, "fn": None, "step_ref": None, "version": 1, "meta": {}}
    node.update(extra)
    return node


def gview(nodes: list[dict], edges: list[tuple] = ()) -> dict:
    return {"version": 1, "chart_version": 1, "nodes": nodes,
            "edges": [{"src": s, "dst": d, "kind": k, "label": label} for s, d, k, label in edges]}


def base_graph(*extra: dict, edges: tuple = ()) -> dict:
    """Root, the Web team and its Identity, plus what a test adds."""
    nodes = [gnode("root", "root", "Root"), gnode("web", "department", "Web", dept_id="web"),
             gnode("web.identity", "function", "Identity", fn="identity", dept_id="web", chat_session_id="cs_77"), *extra]
    links = [("root", "web", "contains", ""), ("web", "web.identity", "has_function", "")]
    return gview(nodes, links + [e for e in edges])


# =====================================================================================================================
# 1. The pure helpers, run in node (the merge gate runs these)
# =====================================================================================================================
PROBE = r"""
const path = require("path");
const GraphLayout = require("__JS__/graph_layout.js");
const GraphView = require("__JS__/graph_view.js");
const h = GraphView.helpers;
const out = {};
const nd = (id, kind, label, status, extra) => Object.assign({id, kind, label, status: status || "idle", detail: "", chat_session_id: null, org_node_id: null, dept_id: null,
  task_id: null, fn: null, step_ref: null, version: 1, meta: {}}, extra || {});
const graph = (nodes, edges) => ({version: 1, chart_version: 1, nodes, edges: (edges || []).map(([src, dst, kind, label]) => ({src, dst, kind, label: label || ""}))});
const checked = (view) => GraphLayout.validate(view).graph;

// the graph of two teams
const two = graph([
  nd("root", "root", "Root"),
  nd("web", "department", "Web", "idle", {dept_id: "web"}), nd("faq", "division", "FAQ", "idle", {dept_id: "web"}),
  nd("web.identity", "function", "Identity", "idle", {dept_id: "web", fn: "identity"}),
  nd("s-1", "step", "Coffee shop", "running", {dept_id: "web", step_ref: "task"}), nd("s-2", "step", "Plan the page", "idle", {dept_id: "web", step_ref: "plan"}),
  nd("content", "department", "Content", "idle", {dept_id: "content"}), nd("content.audit", "function", "Audit", "idle", {dept_id: "content", fn: "audit"}),
], [["root", "web", "contains"], ["web", "faq", "contains"], ["web", "web.identity", "has_function"], ["web", "s-1", "has_step"], ["s-1", "s-2", "has_step"],
    ["root", "content", "contains"], ["content", "content.audit", "has_function"], ["s-1", "content", "step", "then"], ["web.identity", "content.audit", "handoff", "x"]]);
const frozen = JSON.stringify(two);
const ids = (v) => v.nodes.map(n => n.id);
const edgeKeys = (v) => v.edges.map(e => e.src + ">" + e.dst);

out.serves = {};
const W = {level: "full", dept: ""}, WT = {level: "full", dept: "web"}, C = {level: "chart", dept: ""}, CT = {level: "chart", dept: "web"};
[["fullAll_wantsChartAll", W, C], ["fullAll_wantsFullThis", W, WT], ["chartAll_wantsFullAll", C, W], ["chartAll_wantsChartThis", C, CT], ["fullThis_wantsFullAll", WT, W],
 ["fullThis_wantsFullThis", WT, WT], ["fullThis_wantsChartThis", WT, CT], ["fullThis_otherTeam", WT, {level: "full", dept: "content"}],
 ["chartThis_wantsFullThis", CT, WT], ["chartThis_wantsChartAll", CT, C]].forEach(([k, have, want]) => { out.serves[k] = h.serves(have, want); });

out.narrow = {
  teamFromAll: (v => ({ids: ids(v), edges: edgeKeys(v)}))(h.narrow(two, W, WT)),
  overviewFromFull: (v => ({ids: ids(v), edges: edgeKeys(v)}))(h.narrow(two, W, C)),
  overviewOfTeamFromFull: ids(h.narrow(two, W, CT)),
  serverOverviewIsKept: ids(h.narrow(two, C, C)),
  serverTeamStillLosesRoot: ids(h.narrow(graph([nd("root", "root", "Root"), nd("web", "department", "Web", "idle", {dept_id: "web"})], [["root", "web", "contains"]]), WT, WT)),
  untouchedWhenAsked: h.narrow(two, W, W) === two,
  notAGraph: [h.narrow(null, W, WT), h.narrow({nodes: 5}, W, WT), h.narrow("x", W, C)],
  noEdgesKeyStaysAbsent: ("edges" in h.narrow({nodes: two.nodes}, W, WT)) ? "present" : "absent",
  inputUnchanged: JSON.stringify(two) === frozen,
  nonObjectNodesDropped: ids(h.narrow({nodes: [null, 5, two.nodes[1]], edges: []}, W, WT)),
};
out.overviewKinds = two.nodes.filter(h.inOverview).map(n => n.id);

const k = (t) => Math.round(t.k * 1e6) / 1e6;
out.zoom = {
  in: h.zoomAbout({k: 1, x: 10, y: 20}, 2, 100, 50),
  pointerStays: (() => { const t = {k: 1.5, x: -30, y: 12}; const z = h.zoomAbout(t, 1.7, 220, 140); return [(220 - t.x) / t.k, (220 - z.x) / z.k, (140 - t.y) / t.k, (140 - z.y) / z.k]; })(),
  top: k(h.zoomAbout({k: 3, x: 0, y: 0}, 10, 0, 0)), bottom: k(h.zoomAbout({k: 0.3, x: 0, y: 0}, 0.01, 0, 0)),
  atTheLimitNothingMoves: h.zoomAbout({k: 4, x: 7, y: 9}, 3, 100, 100),
  limits: [h.MIN_SCALE, h.MAX_SCALE, h.CLICK_DISTANCE, h.FRESH_MS, h.BIG_GRAPH],
};
out.home = {wide: h.homeOf(3000, 1200), narrow: h.homeOf(400, 1200), same: h.homeOf(1200, 1200)};
const size = {w: 1000, h: 600};
const t0 = {k: 1, x: 0, y: 0};
out.reveal = {
  inside: h.bringIntoView(t0, {x: 100, y: 100, w: 168, h: 50}, size, 24),
  left: h.bringIntoView({k: 1, x: -500, y: 0}, {x: 100, y: 100, w: 168, h: 50}, size, 24),
  right: h.bringIntoView(t0, {x: 1500, y: 100, w: 168, h: 50}, size, 24),
  above: h.bringIntoView({k: 1, x: 0, y: -400}, {x: 100, y: 100, w: 168, h: 50}, size, 24),
  below: h.bringIntoView(t0, {x: 100, y: 900, w: 168, h: 50}, size, 24),
  scaled: h.bringIntoView({k: 2, x: 0, y: 0}, {x: 400, y: 100, w: 168, h: 50}, size, 24),
  tooBig: h.bringIntoView({k: 1, x: 0, y: 0}, {x: -100, y: 0, w: 2000, h: 50}, size, 24),
};

// the sentence
const base = graph([nd("root", "root", "Root"), nd("web", "department", "Web", "idle", {dept_id: "web"}), nd("web.identity", "function", "Identity", "idle", {fn: "identity"})],
  [["root", "web", "contains"], ["web", "web.identity", "has_function"]]);
const plus = (...more) => graph(base.nodes.concat(more), base.edges.map(e => [e.src, e.dst, e.kind]).concat(more.map(m => ["web", m.id, "contains"])));
const said = (a, b) => h.sentenceOf(checked(a), checked(b));
out.said = {
  none: said(base, base),
  oneAdded: said(base, plus(nd("quotes", "division", "Quotes"))),
  twoAdded: said(base, plus(nd("a", "division", "Quotes"), nd("b", "division", "FAQ"))),
  threeAdded: said(base, plus(nd("a", "division", "A"), nd("b", "division", "B"), nd("c", "division", "C"))),
  fourAdded: said(base, plus(nd("a", "division", "A"), nd("b", "division", "B"), nd("c", "division", "C"), nd("d", "division", "D"))),
  waitingOnYou: said(base, graph(base.nodes.map(n => n.id === "web.identity" ? Object.assign({}, n, {status: "waiting_on_you"}) : n), [["root", "web", "contains"], ["web", "web.identity", "has_function"]])),
  fault: said(base, graph(base.nodes.map(n => n.id === "web.identity" ? Object.assign({}, n, {status: "fault"}) : n), [["root", "web", "contains"], ["web", "web.identity", "has_function"]])),
  running: said(base, graph(base.nodes.map(n => n.id === "web" ? Object.assign({}, n, {status: "running"}) : n), [["root", "web", "contains"], ["web", "web.identity", "has_function"]])),
  waitingOnAPersona: said(base, graph(base.nodes.map(n => n.id === "web.identity" ? Object.assign({}, n, {status: "waiting", meta: {wait_on: "priority"}}) : n), [["root", "web", "contains"], ["web", "web.identity", "has_function"]])),
  backToIdle: (() => { const busy = graph(base.nodes.map(n => n.id === "web" ? Object.assign({}, n, {status: "running"}) : n), [["root", "web", "contains"], ["web", "web.identity", "has_function"]]); return said(busy, base); })(),
  needingBeatsAdded: said(base, graph(base.nodes.map(n => n.id === "web.identity" ? Object.assign({}, n, {status: "waiting_on_you"}) : n).concat([nd("q", "division", "Quotes")]), [["root", "web", "contains"], ["web", "web.identity", "has_function"], ["web", "q", "contains"]])),
  manyNeeding: said(base, graph(base.nodes.map(n => n.id === "web" || n.id === "web.identity" ? Object.assign({}, n, {status: "waiting_on_you"}) : n), [["root", "web", "contains"], ["web", "web.identity", "has_function"]])),
  addedBeatsOtherStatus: said(base, graph(base.nodes.map(n => n.id === "web" ? Object.assign({}, n, {status: "running"}) : n).concat([nd("q", "division", "Quotes")]), [["root", "web", "contains"], ["web", "web.identity", "has_function"], ["web", "q", "contains"]])),
  oneRemoved: said(plus(nd("quotes", "division", "Quotes")), base),
  twoRemoved: said(plus(nd("a", "division", "Quotes"), nd("b", "division", "FAQ")), base),
  fiveRemoved: said(plus(nd("a", "division", "A"), nd("b", "division", "B"), nd("c", "division", "C"), nd("d", "division", "D"), nd("e", "division", "E")), base),
  labelWithMarkup: said(base, plus(nd("x", "division", "<b>Bold</b> \"q\""))),
};

const legend = (mode) => h.legendHtml(mode);
out.legend = {
  graphSteps: (legend("graph").match(/<li>/g) || []).length,
  graphHasLines: /belongs to/.test(legend("graph")) && /hands over to/.test(legend("graph")) && /revises/.test(legend("graph")),
  chartWords: ["Reuse", "Add", "Rearrange"].map(w => legend("chart").includes(w)),
  chartHasNoSteps: (legend("chart").match(/<li>/g) || []).length,
  keyed: /<details class="wlegend" data-key="wlegend">/.test(legend("graph")) && /<details class="wlegend" data-key="wlegend">/.test(legend("chart")),
};

// the module does not need a DOM to load, and a missing script is named
out.loads = {create: typeof GraphView.create, helpers: Object.keys(h).sort()};
try { GraphView.create(null); out.badHost = "no error"; } catch (e) { out.badHost = e.constructor.name + ": " + e.message; }
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    if NODE is None:
        pytest.skip("node is not installed")
    script = PROBE.replace("__JS__", JS.as_posix())
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60, cwd=REPO)
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout)


def test_the_helpers_load_in_node_and_a_bad_host_is_named(probe):
    assert probe["loads"]["create"] == "function"
    assert probe["loads"]["helpers"] == sorted(["narrow", "serves", "inOverview", "zoomAbout", "homeOf", "bringIntoView", "sentenceOf", "legendHtml",
                                                 "MIN_SCALE", "MAX_SCALE", "CLICK_DISTANCE", "FRESH_MS", "BIG_GRAPH"])
    assert probe["badHost"] == "TypeError: GraphView.create: host must be an element"


def test_data_serves_a_toggle_only_when_it_is_wide_enough(probe):
    assert probe["serves"] == {
        "fullAll_wantsChartAll": True,       # a full graph of every team narrows to an overview ...
        "fullAll_wantsFullThis": True,       # ... and to one team
        "chartAll_wantsFullAll": False,      # an overview cannot give more detail
        "chartAll_wantsChartThis": True,     # but it can be cut to one team
        "fullThis_wantsFullAll": False,      # one team's data cannot give every team
        "fullThis_wantsFullThis": True,
        "fullThis_wantsChartThis": True,
        "fullThis_otherTeam": False,         # or another team
        "chartThis_wantsFullThis": False,
        "chartThis_wantsChartAll": False,
    }


def test_narrowing_to_a_team_drops_the_root_the_other_teams_and_every_link_that_lost_an_end(probe):
    team = probe["narrow"]["teamFromAll"]
    assert team["ids"] == ["web", "faq", "web.identity", "s-1", "s-2"]
    assert team["edges"] == ["web>faq", "web>web.identity", "web>s-1", "s-1>s-2"]
    assert probe["narrow"]["serverTeamStillLosesRoot"] == ["web"]               # the picture is the same whoever did the cutting


def test_an_overview_is_cut_from_a_full_graph_only_and_keeps_one_task_step(probe):
    n = probe["narrow"]
    assert n["overviewFromFull"]["ids"] == ["root", "web", "faq", "s-1", "content"]
    assert n["overviewFromFull"]["edges"] == ["root>web", "web>faq", "web>s-1", "root>content", "s-1>content"]
    assert n["overviewOfTeamFromFull"] == ["web", "faq", "s-1"]
    assert n["serverOverviewIsKept"] == ["root", "web", "faq", "web.identity", "s-1", "s-2", "content", "content.audit"]
    assert probe["overviewKinds"] == ["root", "web", "faq", "s-1", "content"]


def test_narrowing_never_changes_its_input_and_leaves_a_non_graph_to_validate(probe):
    n = probe["narrow"]
    assert n["untouchedWhenAsked"] is True and n["inputUnchanged"] is True
    assert n["notAGraph"] == [None, {"nodes": 5}, "x"]
    assert n["noEdgesKeyStaysAbsent"] == "present"                              # Object.assign keeps the key, with its undefined value
    assert n["nonObjectNodesDropped"] == ["web"]


def test_zoom_keeps_the_point_under_the_pointer_and_stays_between_a_quarter_and_four(probe):
    z = probe["zoom"]
    assert z["in"] == {"k": 2, "x": -80, "y": -10}
    a, b, c, d = z["pointerStays"]
    assert abs(a - b) < 1e-9 and abs(c - d) < 1e-9
    assert z["top"] == 4 and z["bottom"] == 0.25
    assert z["atTheLimitNothingMoves"] == {"k": 4, "x": 7, "y": 9}
    assert z["limits"] == [0.25, 4, 4, 1200, 500]


def test_the_first_view_is_one_to_one_centred_on_the_top_middle(probe):
    assert probe["home"] == {"wide": {"k": 1, "x": -900, "y": 0}, "narrow": {"k": 1, "x": 400, "y": 0}, "same": {"k": 1, "x": 0, "y": 0}}


def test_a_node_is_panned_the_least_that_puts_it_in_view(probe):
    assert probe["reveal"] == {
        "inside": {"k": 1, "x": 0, "y": 0},
        "left": {"k": 1, "x": -76, "y": 0},          # its left edge, 100 - 500 = -400, moves to the 24 px margin
        "right": {"k": 1, "x": -692, "y": 0},        # its right edge, 1668, moves to 1000 - 24
        "above": {"k": 1, "x": 0, "y": -76},
        "below": {"k": 1, "x": 0, "y": -374},
        "scaled": {"k": 2, "x": -160, "y": 0},       # at scale 2 its right edge is 1136: 160 past the margin
        "tooBig": {"k": 1, "x": 124, "y": 24},       # wider than the viewport: its left edge goes to the margin (and the top one too)
    }


def test_the_sentence_names_what_changed_and_puts_the_owner_first(probe):
    assert probe["said"] == {
        "none": "",
        "oneAdded": "Quotes was added under Web",
        "twoAdded": "Quotes and FAQ were added",
        "threeAdded": "A, B and C were added",
        "fourAdded": "4 nodes were added",
        "waitingOnYou": "Identity is waiting on you",
        "fault": "Identity is blocked",
        "running": "Web is running now",
        "waitingOnAPersona": "Identity is waiting on Prioritiser",
        "backToIdle": "Web is idle",
        "needingBeatsAdded": "Identity is waiting on you",       # a question for the owner outranks a new box
        "manyNeeding": "Web is waiting on you (and 1 more)",
        "addedBeatsOtherStatus": "Quotes was added under Web",
        "oneRemoved": "Quotes was removed",
        "twoRemoved": "Quotes and FAQ were removed",
        "fiveRemoved": "5 nodes were removed",
        "labelWithMarkup": '<b>Bold</b> "q" was added under Web',  # plain text: the page writes it with textContent
    }


def test_the_legend_has_the_seven_steps_the_edge_words_and_the_chart_marks(probe):
    lg = probe["legend"]
    assert lg["graphSteps"] == 7 and lg["graphHasLines"] is True
    assert lg["chartWords"] == [True, True, True] and lg["chartHasNoSteps"] == 0
    assert lg["keyed"] is True                                                  # data-key: the open state survives a repaint


# =====================================================================================================================
# 2. The views in a real Chrome
# =====================================================================================================================
class Server:
    def __init__(self, url: str, client: fake_backend.FakeClient) -> None:
        self.url, self.client = url, client


@pytest.fixture(scope="module")
def static_dir(tmp_path_factory) -> Path:
    if (STATIC / "css" / "j2.css").is_file():
        return STATIC
    copy = tmp_path_factory.mktemp("static") / "static"
    shutil.copytree(STATIC, copy)
    (copy / "css").mkdir(exist_ok=True)
    (copy / "css" / "j2.css").write_text(STAND_IN_CSS, encoding="utf-8")
    return copy


@pytest.fixture(scope="module")
def server(static_dir) -> Any:
    app = fake_backend.make_app(static_dir=static_dir)
    running = fake_backend.run_in_thread(app)
    try:
        yield Server(running.url, fake_backend.FakeClient(running.url, app.state.fake.token))
    finally:
        running.stop()


@pytest.fixture(scope="module")
def chrome() -> Any:
    cdp = pytest.importorskip("cdp")
    exe = cdp.find_chrome()
    if exe is None:
        pytest.skip("Chrome is not installed (set SUTRA_CHROME to its path)")
    with cdp.Browser(exe) as instance:
        instance._send("Emulation.setFocusEmulationEnabled", {"enabled": True})      # a headless page is never focused, so focus() alone fires no focus event
        yield instance


# window.spare(id): a place for a second view that takes no room in the page (J2's body is a flex column: a sibling would shrink the
# mount page's own pane, and the pane re-centres itself when its width changes)
SPARE = ("window.spare = id => { const d = document.body.appendChild(document.createElement('div')); d.id = id; "
         "d.style.cssText = 'position:absolute;left:0;right:0;top:1000px'; return d; }")


class Page:
    """One test's hold on the module's Chrome and fake server."""

    def __init__(self, browser: Any, server: Server) -> None:
        self.b, self.fake, self.url = browser, server.client, server.url

    def open(self, name: str = "graph", **query: str) -> "Page":
        self.b.goto(self.fake.mount_url(name, **query))
        self.b.wait_for("window.mounted === true && window.liveState === 'live'")
        assert self.b.js("window.mountErrors") == []
        self.b.js(SPARE)
        return self

    def js(self, expression: str) -> Any:
        return self.b.js(expression)

    def count(self, selector: str) -> int:
        return self.b.count(selector)

    def ids(self, selector: str = "g.wnode") -> list[str]:
        return self.js("Array.from(document.querySelectorAll(" + json.dumps(selector) + ")).map(e => e.dataset.id)")

    def classes(self, node_id: str) -> set[str]:
        return set(self.js("document.querySelector(\"g.wnode[data-id='" + node_id + "']\").getAttribute('class')").split())

    def update(self, view: dict) -> Any:
        return self.js("window.view.update(" + json.dumps(view) + ")")

    def requests(self, path: str) -> list[str]:
        return [entry["query"] for entry in self.fake.log() if entry["path"] == path]

    def zoom(self) -> dict:
        return self.js("window.view.state().zoom")

    def stage(self) -> dict:
        return self.js("(r => ({left: r.left, top: r.top, w: r.width, h: r.height}))(document.querySelector('.wstage').getBoundingClientRect())")

    def wheel(self, x: float, y: float, dy: float) -> None:
        self.b._send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": dy})

    def drag(self, start: tuple[float, float], end: tuple[float, float], steps: int = 6) -> None:
        send = self.b._send
        send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": start[0], "y": start[1]})
        send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": start[0], "y": start[1], "button": "left", "clickCount": 1})
        for i in range(1, steps + 1):
            x = start[0] + (end[0] - start[0]) * i / steps
            y = start[1] + (end[1] - start[1]) * i / steps
            send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "buttons": 1})
        send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": end[0], "y": end[1], "button": "left", "clickCount": 1})

    def move_to(self, x: float, y: float) -> None:
        self.b._send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})


@pytest.fixture()
def page(chrome, server):
    chrome.goto("about:blank")                          # closes the streams of the last test's page before the fake is reset
    server.client.reset()
    chrome.goto(server.url + "/__fake/state")           # any page of this origin: its local storage is the pages'
    chrome.js("localStorage.clear()")
    chrome.goto("about:blank")
    chrome._send("Emulation.setEmulatedMedia", {"features": []})
    chrome.set_size(1280, 900)
    chrome.clear_diagnostics()
    yield Page(chrome, server)
    errors, failed = chrome.console_errors, chrome.failed_requests
    chrome.goto("about:blank")
    assert errors == [], f"console errors: {errors}"
    assert failed == [], f"failed requests: {failed}"


LIVE_DOT, EMPTY_DOT = "\u25cf", "\u25cb"
EXTRA_NODE = gnode("s-new", "step", "Coffee break", "idle", dept_id="web", task_id="tsk_a1b2c3d4e5f6")


def with_extra_node() -> str:
    """A browser expression: the graph the server holds now, plus one more step under the Web team, drawn through update()."""
    extra = json.dumps(EXTRA_NODE)
    return ("(async () => { const g = await SutraCtx.api.get('/api/graph', {level: 'full'}); g.nodes.push(" + extra +
            "); g.edges.push({src: 'web', dst: 's-new', kind: 'has_step', label: ''}); return window.view.update(g); })()")


# ---------------------------------------------------------------------------------------------------------------------
# The drawing and the header
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_the_graph_is_one_box_per_node_in_depth_first_order_with_its_kind_and_status(page):
    page.fake.stage("2")
    page.open(level="full")
    assert page.ids() == ["root", "web", "web.identity", "web.adaptation", "web.priority", "web.coordination", "web.audit", "s-3f9a1c2b7d"]
    assert {"wnode", "k-root", "st-waiting_on_you"} <= page.classes("root")
    assert {"k-department", "st-waiting_on_you"} <= page.classes("web")
    assert {"k-function", "st-waiting_on_you"} <= page.classes("web.identity") and {"k-function", "st-idle"} <= page.classes("web.audit")
    assert {"k-step", "st-waiting_on_you"} <= page.classes("s-3f9a1c2b7d")
    assert page.count("path.wedge") == 7 and page.count("svg.wgsvg") == 1
    assert page.js("window.view.state().ids") == page.ids() and page.js("window.view.state().warnings") == []
    assert page.js("typeof d3") == "undefined"                    # the pane brings its own pan and zoom


@browser_only
def test_every_j2_status_word_and_every_edge_kind_is_drawn_for_the_full_graph(page):
    page.fake.stage("full")
    page.open(level="full")
    words = page.js("Array.from(document.querySelectorAll('g.wnode')).map(e => Array.from(e.classList).find(c => c.startsWith('st-')).slice(3))")
    assert len(words) == 21 and set(words) == NINE_WORDS
    kinds = page.js("Array.from(document.querySelectorAll('path.wedge')).map(e => e.dataset.edge)")
    assert {k: kinds.count(k) for k in set(kinds)} == {"org": 20, "handoff": 2, "speaks_to": 1, "depends_on": 2, "step": 1}
    assert page.count("path.wedge[data-tone='fix']") == 1                                   # depends_on 'revises' is terracotta
    assert page.js("Array.from(document.querySelectorAll('text.wedgelab')).map(e => e.textContent)") == ["3"]   # speaks_to carries its message count
    assert page.count("g.wnode.k-division") == 2 and page.count("g.wnode.k-division circle.wdot") == 10


@browser_only
def test_the_header_has_the_title_the_counts_the_toggles_and_no_team_toggle_on_home(page):
    page.fake.stage("2")
    page.open(level="full")
    assert page.js("document.querySelector('.maphead h3').textContent") == "Workflow graph"
    assert page.js("Array.from(document.querySelectorAll('.wsums .mappill')).map(e => e.textContent)") == ["1 team", "5 function nodes", "1 step", "1 waiting on you"]
    assert page.js("document.querySelector('.wsums .mappill:last-child').classList.contains('waiting_on_you')") is True
    groups = page.js("Array.from(document.querySelectorAll('.maphead .mapviews')).map(g => [g.getAttribute('aria-label'), Array.from(g.querySelectorAll('button')).map(b => [b.textContent, b.getAttribute('aria-pressed')])])")
    assert groups == [["View", [["Graph", "true"], ["List", "false"]]], ["How much to show", [["Overview", "false"], ["Detail", "true"]]]]
    assert page.js("document.querySelector('.maphead [data-wfit]').textContent") == "Fit" and page.count("[data-wscope]") == 0
    assert page.js("document.querySelector('.wgpane').dataset.mode") == "graph" and page.js("document.querySelector('.wgpane').dataset.view") == "graph"


@browser_only
def test_the_live_chip_shows_the_state_of_the_stream_and_an_unknown_state_is_offline(page):
    page.open(level="full")
    chip = "(e => [e.textContent, e.dataset.state, e.title])(document.querySelector('.wlive'))"
    assert page.js(chip) == [LIVE_DOT + " live", "live", "Updates arrive as they happen"]
    page.js("window.view.setLive('polling')")
    assert page.js(chip) == [EMPTY_DOT + " polling", "polling", "Checking for updates every 2 seconds"]
    page.js("window.view.setLive('offline')")
    assert page.js(chip) == [EMPTY_DOT + " offline", "offline", "Not connected to the app"]
    page.js("window.view.setLive('live'); window.view.setLive('nonsense')")
    assert page.js(chip)[1] == "offline" and page.js("window.view.state().live") == "offline" and page.js("document.querySelector('.wgpane').dataset.live") == "offline"


# ---------------------------------------------------------------------------------------------------------------------
# What the owner does to a node
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_a_click_selects_the_node_and_hands_it_to_the_host_to_open(page):
    page.fake.stage("2")
    page.open(level="full")
    page.js("window.picked = []; window.view2 = GraphView.create(window.spare('view2'), {mode: 'graph', level: 'full', onSelect: n => window.picked.push(n.id)})")
    page.b.click("g.wnode[data-id='web.adaptation']")
    assert page.js("window.opened.id") == "web.adaptation"
    opened = page.js("window.opened")
    assert opened["kind"] == "function" and opened["fn"] == "adaptation" and opened["dept_id"] == "web" and opened["chat_session_id"].startswith("cs_")
    assert page.js("window.view.state().selected") == "web.adaptation"
    assert page.classes("web.adaptation") >= {"sel"} and page.js("document.querySelector('g.wnode.sel').getAttribute('aria-current')") == "true"
    assert page.count("g.wnode.sel") == 1
    page.b.click("g.wnode[data-id='root']")                          # the root is handed over like any node: the host focuses the org chat
    assert page.js("window.opened.id") == "root" and page.ids("g.wnode.sel") == ["root"]
    assert page.js("window.picked") == []                             # a second view has its own callbacks


@browser_only
def test_enter_and_space_on_a_focused_node_open_it_and_a_click_calls_onselect_too(page):
    page.fake.stage("2")
    page.open(level="full")
    page.js("document.querySelector(\"g.wnode[data-id='web.priority']\").focus()")
    page.b.press("Enter")
    assert page.js("window.opened.id") == "web.priority"
    page.js("window.opened = null; document.querySelector(\"g.wnode[data-id='web.audit']\").focus()")
    page.b.press("Space")
    assert page.js("window.opened.id") == "web.audit" and page.js("window.view.state().selected") == "web.audit"
    assert page.js("document.activeElement.dataset.id") == "web.audit"                   # the focus survives the repaint that marks the selection
    page.js("window.opened = null; window.seen = []; const second = window.spare('second'); "
            "window.v2 = GraphView.create(second, "
            "{mode: 'graph', level: 'full', onSelect: n => window.seen.push(['select', n.id]), onOpen: n => window.seen.push(['open', n.id])}); "
            "window.v2.update(" + json.dumps(base_graph()) + ")")
    page.b.click("#second g.wnode[data-id='web']")
    assert page.js("window.seen") == [["select", "web"], ["open", "web"]]                 # onSelect first, then onOpen


@browser_only
def test_select_marks_a_node_without_calling_the_host_and_an_unknown_id_clears_the_selection(page):
    page.fake.stage("2")
    page.open(level="full")
    assert page.js("window.view.select('web.identity')") is True
    assert page.ids("g.wnode.sel") == ["web.identity"] and page.js("window.opened") is None
    assert page.js("window.view.select('web.audit')") is True and page.ids("g.wnode.sel") == ["web.audit"]
    assert page.js("window.view.select('no-such-node')") is False and page.count("g.wnode.sel") == 0 and page.js("window.view.state().selected") == ""
    assert page.js("window.view.select('nobody')") is False                                # nothing selected: nothing to clear, and still false


@browser_only
def test_hover_and_focus_light_a_node_its_edges_and_its_neighbours_and_fade_the_rest(page):
    page.fake.stage("3")
    page.open(level="full")
    page.b.hover("g.wnode[data-id='web.adaptation']")
    assert page.ids("g.wnode.hot") == ["web.adaptation"] and page.ids("g.wnode.near") == ["web", "web.identity"]
    assert page.ids("g.wnode.dim") == ["root", "web.priority", "web.coordination", "web.audit", "s-3f9a1c2b7d"]
    assert page.js("document.querySelector('svg.wgsvg').classList.contains('ehot')") is True
    assert page.count("path.wedge.hot") == 3 and page.count("path.wedge.dim") == 6               # the tree link, the handoff and the speaks_to into Adaptation
    assert page.js("window.view.state().hot") == "web.adaptation"
    stage = page.stage()
    page.move_to(stage["left"] + 12, stage["top"] + stage["h"] - 12)                              # empty sky
    assert page.count("g.wnode.hot, g.wnode.near, g.wnode.dim, path.wedge.hot, path.wedge.dim") == 0
    assert page.js("document.querySelector('svg.wgsvg').classList.contains('ehot')") is False
    page.js("document.querySelector(\"g.wnode[data-id='web.audit']\").focus()")                    # the keyboard lights a node the same way
    assert page.ids("g.wnode.hot") == ["web.audit"] and page.js("window.view.state().hot") == "web.audit"
    page.js("document.activeElement.blur()")
    assert page.count("g.wnode.hot") == 0 and page.js("window.view.state().hot") == ""


@browser_only
def test_tab_visits_the_nodes_depth_first_and_each_is_a_button_with_a_spoken_label(page):
    page.fake.stage("2")
    page.open(level="full")
    ids = page.ids()
    page.js("document.querySelector('g.wnode').focus()")
    visited = [page.js("document.activeElement.dataset.id")]
    for _ in range(3):
        page.b.press("Tab")
        visited.append(page.js("document.activeElement.dataset.id"))
    assert visited == ids[:4]
    assert page.js("Array.from(document.querySelectorAll('g.wnode')).every(e => e.getAttribute('role') === 'button' && e.getAttribute('tabindex') === '0')") is True
    labels = page.js("Object.fromEntries(Array.from(document.querySelectorAll('g.wnode')).map(e => [e.dataset.id, e.getAttribute('aria-label')]))")
    assert labels["web.identity"] == "Identity, Client Lead, waiting on you. Open chat." and labels["root"] == "Root, waiting on you. Go to the org chat."


# ---------------------------------------------------------------------------------------------------------------------
# Pan and zoom
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_the_first_view_is_one_to_one_on_the_top_middle_and_fit_returns_to_it(page):
    page.fake.stage("full")
    page.open(level="full")
    stage = page.stage()
    drawing = page.js("+document.querySelector('svg.wgsvg').dataset.w")
    first = page.zoom()
    assert first["k"] == 1 and first["y"] == 0 and abs(first["x"] - (stage["w"] - 2 - drawing) / 2) <= 1          # the 2 px are the stage's border
    assert page.js("window.view.state().touched") is False
    assert page.js("document.querySelector('g.wview').getAttribute('transform')") == "translate(%s 0) scale(1)" % round(first["x"], 2)
    page.wheel(stage["left"] + 300, stage["top"] + 200, -300)
    page.drag((stage["left"] + 200, stage["top"] + 450), (stage["left"] + 260, stage["top"] + 420))
    assert page.zoom()["k"] > 1 and page.js("window.view.state().touched") is True
    page.b.click("[data-wfit]")
    assert page.zoom() == first and page.js("window.view.state().touched") is False
    page.js("window.view.setView('list'); window.view.setView('graph'); window.view.fit()")      # fit() is the same as the button
    assert page.zoom() == first


@browser_only
def test_the_wheel_zooms_about_the_pointer_between_a_quarter_and_four(page):
    page.fake.stage("2")
    page.open(level="full")
    stage = page.stage()
    px, py = int(stage["left"] + 400), int(stage["top"] + 250)                # whole pixels: that is what Chrome delivers
    before = page.zoom()
    under = ((px - stage["left"] - 1 - before["x"]) / before["k"], (py - stage["top"] - 1 - before["y"]) / before["k"])   # the drawing's point under the pointer
    page.wheel(px, py, -240)
    after = page.zoom()
    assert 1.1 < after["k"] < 1.5
    assert abs(after["x"] + under[0] * after["k"] - (px - stage["left"] - 1)) < 0.01 and abs(after["y"] + under[1] * after["k"] - (py - stage["top"] - 1)) < 0.01
    page.wheel(px, py, -4000)                                                                                   # 2^8 at once: the limit holds it
    assert page.zoom()["k"] == 4
    page.wheel(px, py, 4000)
    page.wheel(px, py, 4000)
    assert page.zoom()["k"] == 0.25
    assert page.js("document.querySelector('.wstage').dataset.k") == "0.25" and "scale(0.25)" in page.js("document.querySelector('g.wview').getAttribute('transform')")


@browser_only
def test_dragging_pans_and_the_click_that_ends_a_drag_opens_nothing_while_a_short_move_still_clicks(page):
    page.fake.stage("2")
    page.open(level="full")
    stage = page.stage()
    start = page.zoom()
    node = page.js("(r => [r.left + r.width / 2, r.top + r.height / 2])(document.querySelector(\"g.wnode[data-id='web.adaptation']\").getBoundingClientRect())")
    page.drag((node[0], node[1]), (node[0] + 90, node[1] + 40))                    # grab a box and pull
    moved = page.zoom()
    assert moved["k"] == 1 and abs(moved["x"] - start["x"] - 90) < 1 and abs(moved["y"] - start["y"] - 40) < 1
    assert page.js("window.opened") is None and page.count("g.wnode.sel") == 0 and page.js("document.querySelector('.wstage').classList.contains('panning')") is False
    page.b.click("[data-wfit]")
    page.drag((node[0], node[1]), (node[0] + 3, node[1] + 2), steps=2)       # 3.6 px: no further than d3.zoom's click distance
    assert page.js("window.opened.id") == "web.adaptation" and page.zoom() == start
    assert stage["w"] > 0


@browser_only
def test_a_click_on_a_sliver_of_a_box_at_the_edge_opens_it_without_moving_it_from_under_the_pointer(page):
    page.fake.stage("2")
    page.open(level="full")
    stage = page.stage()
    box = page.js("(r => [r.left, r.right, r.top + r.height / 2])(document.querySelector(\"g.wnode[data-id='web.identity']\").getBoundingClientRect())")
    page.drag((stage["left"] + 300, stage["top"] + 500), (stage["left"] + 300 + (stage["left"] + 31 - box[1]), stage["top"] + 500))   # 30 px of the box stay in view
    panned = page.zoom()
    page.b._send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": stage["left"] + 16, "y": box[2]})
    page.b._send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": stage["left"] + 16, "y": box[2], "button": "left", "clickCount": 1})
    page.b._send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": stage["left"] + 16, "y": box[2], "button": "left", "clickCount": 1})
    page.b.wait_for("window.opened !== null")
    assert page.js("window.opened.id") == "web.identity" and page.zoom() == panned                              # a mouse focus does not pan; Tab does (see above)


@browser_only
def test_a_click_that_follows_a_drag_is_ignored_even_when_it_is_aimed_at_a_box(page):
    page.fake.stage("2")
    page.open(level="full")
    page.js("""(function () {
        const stage = document.querySelector('.wstage');
        const node = document.querySelector("g.wnode[data-id='web.audit']");
        const fire = (el, type, x, y) => el.dispatchEvent(new PointerEvent(type, {pointerId: 77, pointerType: 'mouse', clientX: x, clientY: y, isPrimary: true, button: 0, bubbles: true}));
        fire(node, 'pointerdown', 400, 300); fire(node, 'pointermove', 460, 330); fire(node, 'pointerup', 460, 330);   // a pointer id that cannot be captured
        node.dispatchEvent(new MouseEvent('click', {bubbles: true}));                                                   // the click the browser sends after the release
        window.afterDrag = window.opened;
        setTimeout(() => { node.dispatchEvent(new MouseEvent('click', {bubbles: true})); window.afterTick = window.opened && window.opened.id; }, 20);
    })()""")
    page.b.wait_for("window.afterTick")
    assert page.js("window.afterDrag") is None and page.js("window.afterTick") == "web.audit"                  # only the click of the same moment was dropped


@browser_only
def test_two_pointers_pinch_about_their_midpoint_and_one_left_goes_on_as_a_pan(page):
    page.fake.stage("2")
    page.open(level="full")
    stage = page.stage()
    start = page.zoom()
    cx, cy = int(stage["left"] + 500), int(stage["top"] + 300)
    under = ((cx - stage["left"] - 1 - start["x"]) / start["k"], (cy - stage["top"] - 1 - start["y"]) / start["k"])
    script = """
      (function () {
        const stage = document.querySelector('.wstage');
        const fire = (type, id, x, y) => stage.dispatchEvent(new PointerEvent(type, {pointerId: id, pointerType: 'touch', clientX: x, clientY: y, isPrimary: id === 1, button: 0, bubbles: true}));
        window.fire = fire;
        fire('pointerdown', 1, %(a)s, %(y)s); fire('pointerdown', 2, %(b)s, %(y)s);
        fire('pointermove', 1, %(a2)s, %(y)s); fire('pointermove', 2, %(b2)s, %(y)s);
      })()
    """ % {"a": cx - 50, "b": cx + 50, "a2": cx - 100, "b2": cx + 100, "y": cy}
    page.js(script)
    pinched = page.zoom()
    assert abs(pinched["k"] - 2) < 0.001                                           # the two pointers went from 100 to 200 px apart
    assert abs(pinched["x"] + under[0] * 2 - (cx - stage["left"] - 1)) < 0.01 and abs(pinched["y"] + under[1] * 2 - (cy - stage["top"] - 1)) < 0.01
    page.js("window.fire('pointerup', 2, %s, %s); window.fire('pointermove', 1, %s, %s)" % (cx + 100, cy, cx - 70, cy + 30))   # finger 2 lifts; finger 1 moves 30 px right and 30 down
    panned = page.zoom()
    assert panned["k"] == pinched["k"] and abs(panned["x"] - pinched["x"] - 30) < 0.001 and abs(panned["y"] - pinched["y"] - 30) < 0.001
    page.js("window.fire('pointerup', 1, %s, %s)" % (cx - 70, cy + 30))
    assert page.js("document.querySelector('.wstage').classList.contains('panning')") is False
    for scale_in, expect in ((10, 4), (0.01, 0.25)):                               # a pinch is held to the same limits as the wheel
        page.js("window.fire('pointerdown', 3, 500, 300); window.fire('pointerdown', 4, 600, 300); "
                "window.fire('pointermove', 4, %s, 300); window.fire('pointerup', 4, 600, 300); window.fire('pointerup', 3, 500, 300)" % (500 + 100 * scale_in))
        assert page.zoom()["k"] == expect


@browser_only
def test_a_node_outside_the_viewport_is_panned_into_view_by_focus_and_by_select(page):
    page.fake.stage("full")
    page.open(level="full")
    stage = page.stage()
    inside = ("(r => (s => r.left >= s.left && r.right <= s.right && r.top >= s.top && r.bottom <= s.bottom)(document.querySelector('.wstage').getBoundingClientRect()))"
              "(document.querySelector(\"g.wnode[data-id='%s']\").getBoundingClientRect())")
    assert stage["w"] < 3073 and page.js(inside % "s-8d2e6b4a1f") is False                   # the Content team's step is off to the right
    page.js("document.querySelector(\"g.wnode[data-id='s-8d2e6b4a1f']\").focus()")             # Tab got there
    assert page.js(inside % "s-8d2e6b4a1f") is True and page.js("window.view.state().touched") is True
    page.b.click("[data-wfit]")
    assert page.js(inside % "s-8d2e6b4a1f") is False
    assert page.js("window.view.select('s-8d2e6b4a1f')") is True and page.js(inside % "s-8d2e6b4a1f") is True


# ---------------------------------------------------------------------------------------------------------------------
# Live updates
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_an_event_makes_the_page_refetch_once_and_the_pane_redraws_what_changed(page):
    page.fake.stage("2")
    page.open(level="full")
    assert page.requests("/api/graph") == ["level=full"] and page.classes("web.adaptation") >= {"st-idle"}
    assert page.js("document.querySelector('.wsr').textContent") == ""                           # the first drawing says nothing
    page.fake.stage("3")
    page.fake.emit("graph.updated")
    page.b.wait_for("document.querySelector(\"g.wnode[data-id='web.adaptation']\").classList.contains('st-running')")
    assert page.requests("/api/graph") == ["level=full", "level=full"]
    assert page.classes("web.identity") >= {"st-idle"} and page.count("path.wedge") == 9         # the handoff and speaks_to links appeared
    assert page.js("document.querySelector('.wsr').textContent") == "Root is running now (and 4 more)"      # five boxes changed their status
    page.js("window.drawn = document.querySelector('svg.wgsvg')")
    page.js("Promise.all(Array.from({length: 4}, () => fetch('/__fake/emit', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({event: 'graph.updated'})})))")
    page.b.wait_for("window.events.filter(e => e === 'graph.updated').length >= 5")
    time.sleep(0.4)
    assert len(page.requests("/api/graph")) == 3                                                   # four events in a burst: one refetch (the mount page coalesces)
    assert page.js("document.querySelector('svg.wgsvg') === window.drawn") is True                  # the same graph again: the picture is not rebuilt
    assert page.js("document.querySelector('.wsr').textContent") == "Root is running now (and 4 more)"


@browser_only
def test_an_update_keeps_the_selection_and_the_zoom_marks_what_arrived_and_says_so(page):
    page.fake.stage("2")
    page.open(level="full")
    stage = page.stage()
    page.js("window.view.select('web.identity')")
    page.wheel(stage["left"] + 300, stage["top"] + 200, -300)
    zoomed = page.zoom()
    assert zoomed["k"] > 1
    transform = page.js("document.querySelector('g.wview').getAttribute('transform')")
    assert page.js(with_extra_node()) is True
    assert page.ids() == ["root", "web", "web.identity", "web.adaptation", "web.priority", "web.coordination", "web.audit", "s-3f9a1c2b7d", "s-new"]
    assert page.zoom() == zoomed and page.js("document.querySelector('g.wview').getAttribute('transform')") == transform      # zoom and pan are kept
    assert page.ids("g.wnode.sel") == ["web.identity"]                                           # and so is the selection
    assert page.ids("g.wnode.wnew") == ["s-new"] and page.js("Array.from(document.querySelectorAll('li.wnew > button')).map(e => e.dataset.id)") == ["s-new"]   # only the node that arrived glows
    assert page.js("document.querySelector('.wsr').textContent") == "Coffee break was added under Web"
    assert page.js("document.querySelector('.wsr').getAttribute('aria-live')") == "polite"
    assert page.js("(r => [r.width, r.height])(document.querySelector('.wsr').getBoundingClientRect())") == [1, 1]            # read by screen readers, never seen
    page.b.wait_for("document.querySelectorAll('.wnew').length === 0", timeout=5)                  # after 1.2 s
    assert page.js("window.view.state().zoom") == zoomed


@browser_only
def test_a_node_that_arrives_does_not_glow_under_reduced_motion_but_is_still_announced(page):
    page.fake.stage("2")
    page.open(level="full")
    page.b._send("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
    assert page.js(with_extra_node()) is True
    assert page.count(".wnew") == 0 and page.js("document.querySelector('.wsr').textContent") == "Coffee break was added under Web"


@browser_only
def test_a_question_for_the_owner_is_announced_before_anything_else_and_a_sentence_is_plain_text(page):
    page.open(level="full")                                                                       # stage 1: the root alone
    page.update(base_graph())
    assert page.js("document.querySelector('.wsr').textContent") == "Web and Identity were added"
    waiting = base_graph(gnode("q", "division", "<b>Quotes</b> & \"co\"", dept_id="web"))
    waiting["nodes"][2]["status"] = "waiting_on_you"
    waiting["edges"].append({"src": "web", "dst": "q", "kind": "contains", "label": ""})
    page.update(waiting)
    assert page.js("document.querySelector('.wsr').textContent") == "Identity is waiting on you"
    page.update(base_graph(gnode("q", "division", "<b>Quotes</b> & \"co\"", dept_id="web"), edges=(("web", "q", "contains", ""),)))
    assert page.js("document.querySelector('.wsr').textContent") == "Identity is idle"
    assert page.count("b") == 0 and page.count(".wsr *") == 0                                      # text, never markup


# ---------------------------------------------------------------------------------------------------------------------
# The List view and the phone
# ---------------------------------------------------------------------------------------------------------------------
def fixture(name: str) -> Any:
    return json.loads((fake_backend.FIXTURES_DIR / name).read_text(encoding="utf-8"))


def overview_ids(graph: dict) -> list[str]:
    return [n["id"] for n in graph["nodes"] if n["kind"] in ("root", "department", "division") or (n["kind"] == "step" and n["step_ref"] == "task")]


@browser_only
def test_the_list_view_is_the_same_graph_with_the_same_click_targets(page):
    page.fake.stage("2")
    page.open(level="full")
    ids = page.ids()
    page.b.click("[data-wview='list']")
    assert page.js("document.querySelector('.wgpane').dataset.view") == "list" and page.js("window.view.state().view") == "list"
    assert page.js("getComputedStyle(document.querySelector('.wstage')).display") == "none"
    assert page.js("getComputedStyle(document.querySelector('.wlist')).display") == "block" and page.js("getComputedStyle(document.querySelector('[data-wfit]')).display") == "none"
    assert page.js("document.querySelector('.wlist ul.wtree').getAttribute('role')") == "tree"
    assert page.ids("button.wobtn") == ids                                                              # the same nodes in the same order
    assert page.js("document.querySelector(\"button.wobtn[data-id='web.identity']\").getAttribute('aria-label')") == "Client Lead, Identity \u00b7 1 open \u00b7 1 closed, waiting on you"
    assert page.js("[document.querySelectorAll('li[aria-level=\"1\"]').length, document.querySelectorAll('li[aria-level=\"3\"]').length]") == [1, 6]
    page.b.click("button.wobtn[data-id='web.adaptation']")
    assert page.js("window.opened.id") == "web.adaptation" and page.js("document.querySelector(\"button.wobtn[data-id='web.adaptation']\").closest('li').classList.contains('sel')") is True
    assert page.js("document.activeElement.dataset.id") == "web.adaptation"                              # the selection repaints the list and the focus stays
    page.js("window.opened = null; document.querySelector(\"button.wobtn[data-id='web.audit']\").focus()")
    page.b.press("Enter")
    assert page.js("window.opened.id") == "web.audit"
    page.b.click("[data-wview='graph']")
    assert page.js("getComputedStyle(document.querySelector('.wstage')).display") == "block" and page.js("getComputedStyle(document.querySelector('.wlist')).display") == "none"
    assert page.ids("g.wnode.sel") == ["web.audit"]                                                       # one selection, in both pictures


@browser_only
def test_a_phone_gets_the_list_in_place_of_the_picture_and_nothing_scrolls_sideways(page):
    page.b.set_size(390, 800)
    page.fake.stage("full")
    page.open(level="full")
    assert page.js("getComputedStyle(document.querySelector('.wstage')).display") == "none"
    assert page.js("getComputedStyle(document.querySelector('.wlist')).display") == "block"
    assert page.js("['[data-group=\"view\"]', '[data-wfit]'].map(s => getComputedStyle(document.querySelector(s)).display)") == ["none", "none"]
    assert page.js("document.documentElement.scrollWidth <= window.innerWidth") is True
    page.b.click("button.wobtn[data-id='web.identity']")
    assert page.js("window.opened.id") == "web.identity"
    page.b.set_size(900, 800)
    assert page.js("getComputedStyle(document.querySelector('.wstage')).display") == "block"             # the picture is back above 600 px


# ---------------------------------------------------------------------------------------------------------------------
# The toggles: Overview | Detail and This team | All teams
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_overview_and_detail_narrow_a_full_graph_without_another_request_and_the_choice_is_kept(page):
    page.fake.stage("full")
    graph = fixture("graph-full.json")
    page.open(level="full")
    assert len(page.ids()) == 21
    page.b.click("[data-wlevel='chart']")
    assert page.ids() == overview_ids(graph) and page.js("window.view.state().level") == "chart"
    assert page.js("Array.from(document.querySelectorAll('.wsums .mappill')).map(e => e.textContent)") == ["2 teams", "2 divisions", "2 steps", "1 waiting on you"]
    assert page.js("document.querySelector('[data-wlevel=chart]').getAttribute('aria-pressed')") == "true" and page.js("document.querySelector('.wgpane').dataset.level") == "chart"
    assert page.js("document.querySelector('.wsr').textContent") == ""                                       # a toggle is not news
    assert page.count(".wnew") == 0
    page.b.click("[data-wlevel='full']")
    assert len(page.ids()) == 21 and page.requests("/api/graph") == ["level=full"]                            # nothing was asked for
    page.b.click("[data-wlevel='chart']")
    assert json.loads(page.js("localStorage.getItem('sutra:graph:all')")) == {"level": "chart", "scope": "all", "view": "graph"}
    page.open(level="full")                                                                                   # a new page: the choice is back
    assert page.js("window.view.state().level") == "chart" and page.ids() == overview_ids(graph)
    assert page.js("document.querySelector('[data-wlevel=chart]').getAttribute('aria-pressed')") == "true"


@browser_only
def test_detail_on_an_overview_asks_for_the_full_graph_once_and_keeps_asking_for_it(page):
    page.fake.stage("full")
    graph = fixture("graph-full.json")
    page.open(level="chart")
    assert page.ids() == overview_ids(graph) and page.requests("/api/graph") == ["level=chart"]
    page.b.click("[data-wlevel='full']")
    page.b.wait_for("document.querySelectorAll('g.wnode').length === 21")
    assert page.requests("/api/graph") == ["level=chart", "level=full"]
    assert page.js("document.querySelector('.wsr').textContent") == ""                                       # asked for by the owner, so not announced
    page.fake.emit("graph.updated")                                                                           # the host refetches the overview ...
    page.b.wait_for("window.events.includes('graph.updated')")
    time.sleep(0.5)
    assert page.requests("/api/graph") == ["level=chart", "level=full", "level=chart", "level=full"]          # ... and the pane asks again for what the owner chose
    assert len(page.ids()) == 21
    page.b.click("[data-wlevel='chart']")                                                                     # the full graph in hand serves an overview
    assert page.ids() == overview_ids(graph) and len(page.requests("/api/graph")) == 4


@browser_only
def test_this_team_and_all_teams_on_a_team_page_narrow_or_ask_as_needed(page):
    page.fake.stage("full")
    graph = fixture("graph-full.json")
    web = [n["id"] for n in graph["nodes"] if n["dept_id"] == "web"]
    page.open(level="full", dept="web")
    assert page.ids() == web and "root" not in page.ids()                                                    # the team's subtree, without the root
    assert page.requests("/api/graph") == ["level=full&dept=web"]
    groups = page.js("Array.from(document.querySelectorAll('.maphead .mapviews')).map(g => g.dataset.group)")
    assert groups == ["view", "level", "scope"]
    assert page.js("Array.from(document.querySelectorAll('[data-wscope]')).map(b => [b.textContent, b.getAttribute('aria-pressed')])") == [["This team", "true"], ["All teams", "false"]]
    page.b.click("[data-wscope='all']")
    page.b.wait_for("document.querySelectorAll('g.wnode').length === 21")
    assert page.requests("/api/graph") == ["level=full&dept=web", "level=full"]                                # every team is more than the team's data holds
    page.b.click("[data-wscope='this']")
    assert page.ids() == web and len(page.requests("/api/graph")) == 2                                         # and back again needs no request
    assert json.loads(page.js("localStorage.getItem('sutra:graph:web')")) == {"level": "full", "scope": "this", "view": "graph"}
    assert page.js("localStorage.getItem('sutra:graph:all')") is None                                           # kept per team


@browser_only
def test_a_stored_choice_that_the_host_did_not_fetch_for_is_asked_for_and_a_broken_one_is_ignored(page):
    page.fake.stage("full")
    page.open(level="full", dept="web")
    page.b.click("[data-wscope='all']")
    page.b.wait_for("document.querySelectorAll('g.wnode').length === 21")
    page.b.click("[data-wview='list']")
    page.open(level="full", dept="web")                                                                       # reload: the host fetches the team, the owner chose every team
    page.b.wait_for("document.querySelectorAll('g.wnode').length === 21")
    assert page.js("document.querySelector('.wgpane').dataset.scope") == "all" and page.js("document.querySelector('.wgpane').dataset.view") == "list"
    assert page.requests("/api/graph")[-2:] == ["level=full&dept=web", "level=full"]
    page.js("localStorage.setItem('sutra:graph:web', '{\"level\": \"sideways\", \"scope\": 7, \"view\": \"list\"}')")
    page.open(level="full", dept="web")
    assert page.js("window.view.state().level") == "full" and page.js("window.view.state().scope") == "this" and page.js("window.view.state().view") == "list"   # only the valid part is used
    page.js("localStorage.setItem('sutra:graph:web', 'not json')")
    page.open(level="full", dept="web")
    assert page.js("(s => [s.level, s.scope, s.view])(window.view.state())") == ["full", "this", "graph"]


# ---------------------------------------------------------------------------------------------------------------------
# Empty, broken and big graphs
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_a_page_without_usable_local_storage_still_draws_toggles_and_marks_nothing_seen(page):
    page.fake.stage("full")
    page.b.goto(page.fake.mount_url("graph", level="full"))                                                     # the page that will block its own storage
    page.b.wait_for("window.mounted === true")
    page.js(SPARE)
    page.js("""(() => {
        const refuse = () => { throw new DOMException('blocked', 'SecurityError'); };
        Storage.prototype.getItem = refuse; Storage.prototype.setItem = refuse;
        const host = window.spare('blocked');
        window.blocked = GraphView.create(host, {mode: 'graph', level: 'full'});
        window.blocked.update(%s);
    })()""" % json.dumps(base_graph()))
    assert page.count("#blocked g.wnode") == 3 and page.js("window.blocked.state().view") == "graph"
    page.b.click("#blocked [data-wlevel='chart']")
    assert page.count("#blocked g.wnode") == 2 and page.js("window.blocked.state().level") == "chart"          # the toggle works without storage
    page.b.click("#blocked [data-wlevel='full']")
    page.js("window.blocked.setView('list'); window.blocked.noteMessage('cs_77', 4); window.blocked.markSeen('cs_77')")
    assert page.js("window.blocked.state().view") == "list" and page.count("#blocked g.wnode") == 3
    assert page.count("#blocked circle.wunread") == 1                                                            # nothing can be written, so it stays unseen for now


@browser_only
def test_a_graph_with_only_the_root_says_there_is_nothing_to_draw_yet(page):
    page.open(level="full")                                                                                   # stage 1
    assert page.ids() == ["root"] and page.js("document.querySelector('.wgpane').dataset.empty") == "true"
    assert page.js("(e => [e.hidden, e.textContent])(document.querySelector('.wempty'))") == [False, "Nothing to draw yet. Tell the chat agent what you need and the graph appears here."]
    page.update(base_graph())
    assert page.js("document.querySelector('.wempty').hidden") is True and page.js("document.querySelector('.wgpane').dataset.empty") == "false"
    page.js("window.team = GraphView.create(window.spare('team'), {mode: 'graph', level: 'full', dept: 'web', scope: 'this'})")
    page.js("window.team.update(" + json.dumps(gview([gnode("root", "root", "Root")])) + ")")
    assert page.js("(e => [e.hidden, e.textContent])(document.querySelector('#team .wempty'))") == [False, "This team has no graph yet."]
    assert page.count("#team g.wnode") == 0 and page.js("document.querySelector('#team .wsums').textContent") == ""
    assert page.count("#team [data-wscope]") == 2 and page.js("window.team.state().scope") == "this"                  # with a team: This team | All teams, and This team first
    page.js("window.plain = GraphView.create(window.spare('plain'), {dept: 'web'})")
    assert page.js("(s => [s.mode, s.level, s.scope])(window.plain.state())") == ["graph", "chart", "this"]          # the defaults: a graph, an overview, this team


@browser_only
def test_something_that_is_not_a_graph_keeps_the_last_good_one_with_a_banner_and_try_again_asks_again(page):
    page.fake.stage("2")
    page.open(level="full")
    ids = page.ids()
    banner = "(e => [e.hidden, e.querySelector('.wbantext').textContent, e.querySelector('button').textContent, e.getAttribute('role')])(document.querySelector('.wbanner'))"
    assert page.js(banner) == [True, "", "Try again", "alert"]                                                     # there is nothing to say yet
    assert page.js("[window.view.update({}), window.view.update(null), window.view.update({nodes: 'x'}), window.view.update({nodes: [], edges: 5})]") == [False] * 4
    assert page.js(banner) == [False, "Showing the last good version.", "Try again", "alert"] and page.ids() == ids and page.js("window.view.state().ids") == ids
    assert page.js("window.view.fail({code: 'network'}); document.querySelector('.wbantext').textContent") == "The app is not responding. Showing the last good version."
    assert page.js("document.querySelector('[data-wretry]').textContent") == "Retry"                           # a server that does not answer: Retry (X8)
    page.b.click("[data-wretry]")
    page.b.wait_for("document.querySelector('.wbanner').hidden === true")
    assert page.requests("/api/graph") == ["level=full", "level=full"] and page.ids() == ids
    page.fake.fail("/api/graph", 500)                                                                           # the server breaks: the pane keeps what it has
    page.js("window.view.refresh()")
    page.b.wait_for("document.querySelector('.wbanner').hidden === false")
    assert page.ids() == ids and page.js("document.querySelector('.wbantext').textContent") == "Showing the last good version."
    assert page.js("document.querySelector('[data-wretry]').textContent") == "Try again"
    page.fake.fail("/api/graph", None)
    page.b.click("[data-wretry]")
    page.b.wait_for("document.querySelector('.wbanner').hidden === true")
    page.b.clear_diagnostics()                                                                                  # the 500 was on purpose


@browser_only
def test_a_view_that_never_had_a_graph_says_it_could_not_load_one(page):
    page.open(level="full")
    page.js("window.fresh = GraphView.create(window.spare('fresh'), {mode: 'graph', level: 'full'})")
    assert page.js("window.fresh.update('nonsense')") is False
    assert page.js("(e => [e.hidden, e.querySelector('.wbantext').textContent])(document.querySelector('#fresh .wbanner'))") == [False, "The graph could not be loaded."]
    page.js("window.fresh.fail({code: 'network'})")
    assert page.js("document.querySelector('#fresh .wbantext').textContent") == "The app is not responding."
    assert page.js("document.querySelector('#fresh [data-wretry]').textContent") == "Retry"
    assert page.count("#fresh g.wnode") == 0


def big_graph(count: int) -> dict:
    nodes = [gnode("root", "root", "Root")] + [gnode("s-%d" % i, "step", "Step %d" % i, "idle") for i in range(count - 1)]
    return gview(nodes, [("root", "s-%d" % i, "has_step", "") for i in range(count - 1)])


@browser_only
def test_a_graph_of_more_than_500_nodes_opens_as_a_list_with_a_note_unless_the_owner_chose(page):
    page.open(level="full")
    page.update(big_graph(500))
    assert page.js("window.view.state().view") == "graph" and page.js("document.querySelector('.wnote').hidden") is True and page.count("g.wnode") == 500
    page.update(big_graph(501))
    assert page.js("window.view.state().view") == "list" and page.count("g.wnode") == 501 and page.count("button.wobtn") == 501
    assert page.js("(e => [e.hidden, e.textContent])(document.querySelector('.wnote'))") == [False, "This graph has 501 nodes, so it opens as a list. Choose Graph to see the picture."]
    page.b.click("[data-wview='graph']")
    assert page.js("document.querySelector('.wnote').hidden") is True and page.js("getComputedStyle(document.querySelector('.wstage')).display") == "block"
    page.update(big_graph(502))
    assert page.js("window.view.state().view") == "graph"                                                       # the owner chose the picture: it stays
    page.js("localStorage.setItem('sutra:graph:all', '{\"view\": \"graph\"}')")
    page.open(level="full")
    page.update(big_graph(600))
    assert page.js("window.view.state().view") == "graph"                                                       # a remembered choice counts as a choice


# ---------------------------------------------------------------------------------------------------------------------
# Words from the wire, unread dots, the legend, two views on a page, destroy
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_words_from_the_wire_are_never_markup_in_the_picture_the_list_the_pills_or_the_sentence(page):
    page.open(level="full")
    evil = "<img src=x onerror=\"window.pwned = 1\"><script>window.pwned = 2</script>\"'&"
    graph = base_graph(gnode("x", "division", evil, "<i>odd</i>", dept_id="web", detail=evil), edges=(("web", "x", "contains", ""),))
    page.js("window.pwned = 0")
    assert page.update(graph) is True
    assert page.js("window.pwned") == 0 and page.count("img") == 0 and page.count("i") == 0 and page.count("svg script, .wlist script, .maphead script") == 0
    assert page.js("document.querySelector(\"g.wnode[data-id='x'] .tlab\").textContent").startswith("<img src=x onerror")
    assert page.js("document.querySelector(\"button.wobtn[data-id='x'] .wolab\").textContent").startswith("<img src=x onerror")
    assert page.js("document.querySelector('.wsr').textContent") == "Web, Identity and " + evil + " were added"
    pill = page.js("(e => [e.textContent, e.title])(document.querySelector('.wsums .wwarn'))")
    assert pill[0] == "1 warning" and "<i>odd</i>" in pill[1] and "idle" in pill[1]                              # an unknown status is drawn as idle and counted


@browser_only
def test_a_node_whose_session_has_an_unseen_message_wears_a_dot_until_it_is_opened_or_marked_seen(page):
    page.open(level="full")
    page.update(base_graph())
    dot = "document.querySelectorAll(\"g.wnode[data-id='web.identity'] circle.wunread\").length"
    assert page.js(dot) == 0
    page.js("window.view.noteMessage('cs_77', 5)")
    assert page.js(dot) == 1 and page.count("g.wnode circle.wunread") == 1 and page.count("button.wobtn[data-id='web.identity'] .wounread") == 1
    page.js("window.view.markSeen('cs_77')")
    assert page.js(dot) == 0 and page.js("localStorage.getItem('sutra:seen:cs_77')") == "5"
    page.js("window.view.noteMessage('cs_77', 4)")                                                                # an older message is nothing new
    assert page.js(dot) == 0
    page.js("window.view.noteMessage('cs_77', 9)")
    assert page.js(dot) == 1
    page.b.click("g.wnode[data-id='web.identity']")                                                               # opening the chat reads it
    assert page.js(dot) == 0 and page.js("localStorage.getItem('sutra:seen:cs_77')") == "9"
    page.js("window.view.noteMessage('cs_other', 3); window.view.noteMessage('', 3); window.view.noteMessage('cs_77', 'x'); window.view.markSeen('nobody')")
    assert page.count("circle.wunread") == 0                                                                      # no node has that session; nonsense is ignored


@browser_only
def test_the_legend_lists_the_seven_steps_and_stays_open_when_the_picture_changes(page):
    page.fake.stage("2")
    page.open(level="full")
    assert page.js("(d => [d.open, d.dataset.key, d.querySelector('summary').textContent])(document.querySelector('.wlegend'))") == [False, "wlegend", "Legend"]
    assert page.js("Array.from(document.querySelectorAll('.wlegend li')).map(e => e.textContent)") == [
        "The chat agent reads the org chart.", "It looks in the model library.", "It plans the work with the Claude and Codex models and writes a workflow.",
        "The graph is shown to you here.", "Every node is linked to its own chat: click a node to open it.", "The graph updates as the agents work.",
        "Teams and divisions are chats you can write to."]
    page.b.click(".wlegend summary")
    page.js("window.legend = document.querySelector('.wlegend')")
    assert page.js(with_extra_node()) is True
    assert page.js("document.querySelector('.wlegend') === window.legend && window.legend.open") is True


@browser_only
def test_two_views_on_one_page_do_not_share_ids_and_each_draws_its_own_graph(page):
    page.fake.stage("full")
    page.open(level="full")
    page.js("""(async () => {
        const host = window.spare('chart');
        window.second = OrgChartView.create(host, {});
        window.second.update(await SutraCtx.api.get('/api/chart'), await SutraCtx.api.get('/api/chart/changes', {limit: 50}));
    })()""")
    ids = page.js("Array.from(document.querySelectorAll('[id]')).map(e => e.id)")
    assert len(ids) == len(set(ids)) and any(i.startswith("ea-") for i in ids)
    assert page.count("#host g.wnode") == 21 and page.count("#chart g.wnode") == 5
    markers = page.js("Array.from(document.querySelectorAll('marker')).map(m => m.id)")
    assert len(markers) == len(set(markers)) and len(markers) > 3


@browser_only
def test_destroy_empties_the_host_stops_every_timer_and_makes_the_handle_inert(page):
    page.fake.stage("2")
    page.open(level="full")
    page.js("window.cleared = []; const real = window.clearTimeout; window.clearTimeout = id => { window.cleared.push(id); return real(id); }")
    page.js(with_extra_node())                                                                                    # a node is glowing: its timer is pending
    assert page.count(".wnew") > 0 and page.js("window.cleared.length") == 0
    page.js("window.view.destroy(); window.view.destroy()")
    assert page.js("window.cleared.length") == 1                                                                  # the glow timer was cancelled, once
    assert page.js("document.getElementById('host').innerHTML") == ""
    asked = len(page.requests("/api/graph"))
    page.fake.emit("graph.updated")                                                                               # the mount page still refetches and calls update()
    page.b.wait_for("window.events.includes('graph.updated')")
    time.sleep(0.4)
    assert len(page.requests("/api/graph")) == asked + 1                                                          # the host's own request; the pane asked for nothing
    assert page.js("[window.view.update(%s), window.view.select('web'), window.view.fit(), window.view.setView('list'), window.view.setLive('live')]" % json.dumps(base_graph())) == [False, False, None, None, None]
    assert page.js("window.view.refresh()") is False and page.js("document.getElementById('host').innerHTML") == "" and page.js("window.mountErrors") == []


# =====================================================================================================================
# 3. The org chart
# =====================================================================================================================
def rows(page: Page) -> list[dict]:
    return page.js("Array.from(document.querySelectorAll('.chglog .chgrow')).map(e => ({seq: e.dataset.change, sel: e.classList.contains('sel'), "
                   "pressed: e.getAttribute('aria-pressed'), text: e.textContent, reason: e.querySelector('.chgreason') ? e.querySelector('.chgreason').textContent : null}))")


def marks(page: Page) -> dict[str, str]:
    return page.js("Object.fromEntries(Array.from(document.querySelectorAll('g.wnode')).map(e => [e.dataset.id, Array.from(e.classList).filter(c => c.startsWith('mk-')).join(' ')]).filter(p => p[1]))")


@browser_only
def test_the_chart_is_the_one_tree_with_the_newest_applied_change_marked_and_the_log_under_it(page):
    page.fake.stage("2")
    page.open(mode="chart")
    assert page.js("document.querySelector('.maphead h3').textContent") == "Org chart" and page.js("document.querySelector('.wgpane').dataset.mode") == "chart"
    assert page.ids() == ["root", "web"] and page.js("Array.from(document.querySelectorAll('.wsums .mappill')).map(e => e.textContent)") == ["1 team"]
    assert marks(page) == {"web": "mk-add"}                                                                  # change 2 added the Web team
    assert page.js("document.querySelector(\"g.wnode[data-id='web'] .wtag\").textContent") == "added"
    assert "added by task: Coffee shop landing page" in page.js("document.querySelector(\"g.wnode[data-id='web'] title\").textContent")
    assert "added by task: Coffee shop landing page" in page.js("document.querySelector(\"g.wnode[data-id='web']\").getAttribute('aria-label')")
    log = rows(page)
    assert [r["seq"] for r in log] == ["2", "1"] and [r["sel"] for r in log] == [True, False] and [r["pressed"] for r in log] == ["true", "false"]
    assert log[0]["reason"] == "No team makes websites" and log[1]["reason"] is None                           # the selected row explains itself
    assert log[0]["text"].startswith("Change 2") and "Added the Web team" in log[0]["text"] and "for 'Coffee shop landing page'" in log[0]["text"]
    assert page.js("document.querySelector('.chgrow time').getAttribute('datetime')") == "2026-11-04T10:00:03Z"
    assert page.count("[data-wview]") == 2 and page.count("[data-wlevel], [data-wscope]") == 0                # a list and the picture, no graph toggles
    assert page.js("document.querySelector('.wlegend').textContent").count("Reuse") == 1 and "Rearrange" in page.js("document.querySelector('.wlegend').textContent")


@browser_only
def test_a_change_waiting_for_a_yes_marks_nothing_and_a_click_on_an_older_row_marks_what_that_change_did(page):
    page.fake.stage("full")
    page.open(mode="chart")
    assert page.ids() == ["root", "web", "faq", "content", "menu"] and marks(page) == {}                       # the newest change is not applied yet
    log = rows(page)
    assert [r["seq"] for r in log] == ["6", "5", "4", "3", "2", "1"] and log[0]["sel"] is True and "waiting for your yes or no" in log[0]["text"]
    assert log[0]["reason"] == "FAQ and Menu answer the same questions"
    page.b.click(".chgrow[data-change='5']")
    assert marks(page) == {"content": "mk-add", "menu": "mk-move"}                                              # added the Content team and moved Menu into it
    assert page.js("Array.from(document.querySelectorAll('.wtag')).map(e => e.textContent)") == ["added", "moved"]
    assert "moved by task: Move Menu to a Content team" in page.js("document.querySelector(\"g.wnode[data-id='menu'] title\").textContent")
    log = rows(page)
    assert [r["sel"] for r in log] == [False, True, False, False, False, False] and log[1]["pressed"] == "true" and log[1]["reason"] == "Menu belongs with the words and pictures"
    assert page.js("document.querySelector(\"g.wnode[data-id='menu']\").querySelector('rect.shape').getAttribute('stroke-width')") == "2.4"
    page.b.click(".chgrow[data-change='4']")
    assert marks(page) == {"faq": "mk-add", "menu": "mk-add"}
    page.b.click(".chgrow[data-change='3']")
    assert marks(page) == {"web": "mk-reuse"} and page.count(".wtag") == 0                                      # a reused team is a plain box
    assert "reused by task: Menu page" in page.js("document.querySelector(\"g.wnode[data-id='web'] title\").textContent")
    page.b.click(".chgrow[data-change='1']")
    assert marks(page) == {"root": "mk-add"}
    page.b.click(".chgrow[data-change='6']")
    assert marks(page) == {} and rows(page)[0]["sel"] is True and page.js("window.view.state().selected") is None   # the newest again: follow the newest
    assert page.js("[window.view.selectChange(5), window.view.state().selected, window.view.selectChange('4'), window.view.state().selected]") == [True, 5, True, 4]
    assert page.js("[window.view.selectChange(99), window.view.selectChange('x'), window.view.selectChange(null), window.view.state().selected]") == [False, False, False, 4]
    assert page.js("[window.view.selectChange(6), window.view.state().selected]") == [True, None]


@browser_only
def test_a_new_change_takes_the_selection_to_the_newest_unless_the_owner_picked_an_older_one(page):
    page.fake.stage("2")
    page.open(mode="chart")
    assert page.requests("/api/chart") == [""] and page.requests("/api/chart/changes") == ["limit=50"]
    page.fake.fixture("chart", "3")
    page.fake.emit("chart.changed")
    page.b.wait_for("document.querySelectorAll('.chgrow').length === 6")
    assert page.requests("/api/chart") == ["", ""] and page.requests("/api/chart/changes") == ["limit=50", "limit=50"]
    assert [r["sel"] for r in rows(page)] == [True, False, False, False, False, False] and page.ids() == ["root", "web", "faq", "content", "menu"]
    page.fake.fixture("chart", "2")                                                                             # (the story rewinds)
    page.open(mode="chart")
    assert page.js("window.view.selectChange(1)") is True and marks(page) == {"root": "mk-add"}
    page.fake.fixture("chart", "3")
    page.fake.emit("chart.changed")
    page.b.wait_for("document.querySelectorAll('.chgrow').length === 6")
    assert [r["sel"] for r in rows(page)] == [False, False, False, False, False, True] and marks(page) == {"root": "mk-add"}   # the picked change stays


@browser_only
def test_a_clicked_box_opens_a_card_with_its_name_purpose_and_what_it_can_do(page):
    page.fake.stage("full")
    page.open(mode="chart")
    card = "(e => ({hidden: e.hidden, name: e.querySelector('h4') && e.querySelector('h4').textContent, purpose: e.querySelector('.ocpurpose') && e.querySelector('.ocpurpose').textContent, " \
           "tag: e.querySelector('.octag') && e.querySelector('.octag').textContent, acts: Array.from(e.querySelectorAll('.ocacts > *')).map(a => a.textContent), label: e.getAttribute('aria-label')}))(document.querySelector('.ocard'))"
    assert page.js(card)["hidden"] is True
    page.b.click("g.wnode[data-id='web']")
    shown = page.js(card)
    assert shown == {"hidden": False, "name": "Web", "purpose": "Websites and landing pages", "tag": None, "acts": ["Open team page", "Open chat"], "label": "Web"}
    assert page.js("document.querySelector(\"[data-oc='team']\").getAttribute('href')") == "/d/web/" and page.ids("g.wnode.sel") == ["web"]
    page.b.click(".chgrow[data-change='3']")                                                                    # the card follows the selected change
    assert page.js(card)["tag"] == "reused by task: Menu page"
    page.b.click("[data-oc='chat']")
    assert page.js("window.opened.id") == "web" and page.js("window.opened.kind") == "department"
    page.b.click("[data-oc='close']")
    assert page.js(card)["hidden"] is True and page.js("document.querySelector('.ocard').textContent") == ""
    page.b.click("g.wnode[data-id='faq']")
    assert page.js(card)["acts"] == ["Open chat"] and page.js(card)["purpose"] == "Questions people ask"      # a division has no team page
    page.b.press("Escape")
    assert page.js(card)["hidden"] is True
    page.b.click("g.wnode[data-id='root']")
    assert page.js(card)["name"] == "Root" and page.js(card)["purpose"] is None and page.js(card)["acts"] == ["Open chat"]
    page.js("""(async () => {
        const host = window.spare('other');
        window.other = OrgChartView.create(host, {onShow: n => window.log.push(['show', n.id]), onOpen: n => window.log.push(['open', n.id])});
        window.other.update(await SutraCtx.api.get('/api/chart'), await SutraCtx.api.get('/api/chart/changes', {limit: 50}));
    })()""")
    page.js("window.log = []")
    page.b.click("#other g.wnode[data-id='content']")
    assert page.js("Array.from(document.querySelectorAll('#other .ocacts > *')).map(a => a.textContent)") == ["Open team page", "Show in graph", "Open chat"]
    page.b.click("#other [data-oc='show']")
    page.b.click("#other [data-oc='chat']")
    assert page.js("window.log") == [["show", "content"], ["open", "content"]]


@browser_only
def test_the_card_goes_when_its_box_does_and_a_host_callback_that_throws_breaks_nothing(page):
    page.fake.stage("full")
    page.open(mode="chart")
    page.b.click("g.wnode[data-id='menu']")
    assert page.js("document.querySelector('.ocard').hidden") is False
    page.js("window.chart2 = " + json.dumps(fixture("chart.v3.json")) + "; window.chart2.nodes = window.chart2.nodes.filter(n => n.id !== 'menu'); window.view.update(window.chart2)")
    assert page.ids() == ["root", "web", "faq", "content"] and page.js("document.querySelector('.ocard').hidden") is True and page.js("window.view.state().card") == ""
    page.js("""(async () => {
        const host = window.spare('bad');
        window.bad = OrgChartView.create(host, {onOpen: () => { throw new Error('host bug'); }});
        window.bad.update(await SutraCtx.api.get('/api/chart'), await SutraCtx.api.get('/api/chart/changes', {limit: 50}));
    })()""")
    page.b.click("#bad g.wnode[data-id='web']")
    page.b.click("#bad [data-oc='chat']")
    assert page.js("document.querySelector('#bad .ocard').hidden") is False and page.count("#bad g.wnode") == 5
    assert any("onOpen failed" in line for line in page.b.console_errors)
    page.b.clear_diagnostics()                                                                                  # the error was on purpose


@browser_only
def test_the_team_being_viewed_has_a_ring_and_nobody_else_does(page):
    page.fake.stage("full")
    page.open(mode="chart", dept="web")
    assert page.ids("g.wnode.cur") == ["web"] and page.count("rect.wcur") == 1
    page.open(mode="chart")
    assert page.count("g.wnode.cur") == 0 and page.count("rect.wcur") == 0


@browser_only
def test_an_empty_chart_is_the_root_and_a_sentence(page):
    page.open(mode="chart")                                                                                     # stage 1
    assert page.ids() == ["root"] and marks(page) == {"root": "mk-add"} and [r["seq"] for r in rows(page)] == ["1"]
    assert page.js("(e => [e.hidden, e.textContent])(document.querySelector('.wempty'))") == [False, "No teams yet. The chat agent adds one when you ask for something."]
    page.fake.stage("2")
    page.fake.emit("chart.changed")
    page.b.wait_for("document.querySelectorAll('g.wnode').length === 2")
    assert page.js("document.querySelector('.wempty').hidden") is True
    assert page.js("document.querySelector('.wsr').textContent") == "Web was added under Root"


@browser_only
def test_something_that_is_not_a_chart_keeps_the_last_good_one_and_try_again_asks_for_both_lists(page):
    page.fake.stage("full")
    page.open(mode="chart")
    log = rows(page)
    assert page.js("[window.view.update({}), window.view.update(null), window.view.update({nodes: 3})]") == [False] * 3
    assert page.js("(e => [e.hidden, e.querySelector('.wbantext').textContent])(document.querySelector('.wbanner'))") == [False, "Showing the last good version."]
    assert page.ids() == ["root", "web", "faq", "content", "menu"] and rows(page) == log
    page.b.click("[data-wretry]")
    page.b.wait_for("document.querySelector('.wbanner').hidden === true")
    assert page.requests("/api/chart") == ["", ""] and page.requests("/api/chart/changes") == ["limit=50", "limit=50"]
    assert page.js("window.view.update(" + json.dumps(fixture("chart.v3.json")) + ", 'not a list')") is True and rows(page) == log     # no list: the one in hand stays
    page.fake.fail("/api/chart/changes", 500)
    page.js("window.view.fail({code: 'x'}); window.view.refresh()")
    page.b.wait_for("document.querySelector('.wbanner').hidden === false")
    assert page.ids() == ["root", "web", "faq", "content", "menu"]
    page.fake.fail("/api/chart/changes", None)
    page.b.click("[data-wretry]")
    page.b.wait_for("document.querySelector('.wbanner').hidden === true")
    page.b.clear_diagnostics()                                                                                  # the 500 was on purpose


@browser_only
def test_a_change_is_picked_with_the_keyboard_and_the_row_keeps_the_focus(page):
    page.fake.stage("full")
    page.open(mode="chart")
    page.js("document.querySelector(\".chgrow[data-change='5']\").focus()")
    page.b.press("Enter")
    assert rows(page)[1]["sel"] is True and marks(page) == {"content": "mk-add", "menu": "mk-move"}
    assert page.js("document.activeElement.dataset.change") == "5"                                              # the log was repainted, the focus came back
    page.js("document.querySelector(\".chgrow[data-change='4']\").focus()")
    page.b.press("Space")
    assert rows(page)[2]["sel"] is True and page.js("document.activeElement.dataset.change") == "4"
    assert page.js("Array.from(document.querySelectorAll('.chgrow')).every(e => e.getAttribute('role') === 'button' && e.getAttribute('tabindex') === '0')") is True


@browser_only
def test_the_chart_pane_has_the_list_the_live_chip_and_destroys_cleanly(page):
    page.fake.stage("full")
    page.open(mode="chart")
    page.js("window.view.graphView.setView('list')")
    assert page.ids("button.wobtn") == ["root", "web", "faq", "content", "menu"] and page.js("getComputedStyle(document.querySelector('.wstage')).display") == "none"
    page.b.click("button.wobtn[data-id='content']")
    assert page.js("document.querySelector('.ocard h4').textContent") == "Content"                              # the list opens the same card
    assert page.js("document.querySelector('.wlive').textContent") == "\u25cf live"
    page.js("window.view.setLive('polling')")
    assert page.js("document.querySelector('.wlive').dataset.state") == "polling"
    page.js("window.view.destroy(); window.view.destroy()")
    assert page.js("document.getElementById('host').innerHTML") == "" and page.js("window.view.update(" + json.dumps(fixture("chart.v3.json")) + ")") is False
    assert page.js("window.view.selectChange(5)") is False


# ---------------------------------------------------------------------------------------------------------------------
# A pane that is hidden when it is made, the window, a vanished selection and the scripted first task
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_a_pane_made_while_hidden_finds_its_first_view_when_shown_and_follows_the_window_until_it_is_moved(page):
    page.open(level="full")
    page.js("""(() => {
        const box = window.spare('late');
        box.hidden = true;
        window.late = GraphView.create(box, {mode: 'graph', level: 'full'});
        window.late.update(%s);
    })()""" % json.dumps(base_graph()))
    home = ("(() => { const s = document.querySelector('#late .wstage'), z = window.late.state().zoom;"
            " return [z.k, z.y, Math.round((z.x - (s.clientWidth - +document.querySelector('#late svg.wgsvg').dataset.w) / 2) * 10) / 10]; })()")
    page.js("document.getElementById('late').hidden = false")
    page.b.wait_for("document.querySelector('#late .wstage').clientWidth > 0 && window.late.state().zoom.x > 0")
    assert page.js(home) == [1, 0, 0]                                                                          # centred, though it was made with no width
    page.b.set_size(900, 800)
    page.b.wait_for("document.querySelector('#late .wstage').clientWidth <= 900 && JSON.stringify(" + home + ") === '[1,0,0]'")   # and again after the window changed
    assert page.js(home) == [1, 0, 0]
    page.js("window.late.el.querySelector('.wstage').dispatchEvent(new WheelEvent('wheel', {deltaY: -200, clientX: 300, clientY: 200, bubbles: true, cancelable: true}))")
    moved = page.js("window.late.state().zoom")
    assert moved["k"] > 1 and page.js("window.late.state().touched") is True
    page.b.set_size(1100, 800)
    page.b.wait_for("document.querySelector('#late .wstage').clientWidth > 1000")
    assert page.js("window.late.state().zoom") == moved                                                        # the owner moved it: the window leaves it alone


@browser_only
def test_the_selection_is_dropped_when_its_node_goes(page):
    page.open(level="full")
    page.update(base_graph())
    page.js("window.view.select('web.identity')")
    assert page.ids("g.wnode.sel") == ["web.identity"]
    page.update(gview([gnode("root", "root", "Root"), gnode("web", "department", "Web", dept_id="web")], [("root", "web", "contains", "")]))
    assert page.count("g.wnode.sel") == 0 and page.js("window.view.state().selected") == "" and page.count("li.sel") == 0
    assert page.js("document.querySelector('.wsr').textContent") == "Identity was removed"


@browser_only
def test_the_graph_draws_itself_while_the_scripted_first_task_plays(page):
    page.open(level="full")                                                                                     # stage 1: the root alone
    assert page.ids() == ["root"]
    page.fake.wait_subscribers(1)
    status, answer = page.fake.post("/api/chats/cs_org/messages", {"text": "A website for my cafe"})
    assert status == 202 and answer["turn"] == "started"
    page.fake.wait_flows()
    page.b.wait_for("document.querySelector(\"g.wnode[data-id='web.identity']\") !== null && document.querySelectorAll('g.wnode').length === 8")
    assert page.js("window.events.includes('graph.updated')") is True and page.js("window.mountErrors") == []
    assert page.js("document.querySelector('.wsr').textContent") != "" and page.js("document.querySelector('.wempty').hidden") is True
    assert page.classes("web.identity") >= {"st-waiting_on_you"}
