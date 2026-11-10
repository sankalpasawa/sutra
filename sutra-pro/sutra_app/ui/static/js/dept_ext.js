/* dept_ext.js - the glue of the department page (work package UI-8; docs/design/ui.md sections 5 (E6, E12), 6.7, 7 and 9; S3-web-10; UI-D10).

   The department page is J2's own page with the Sutra edits (scripts/port_j2_ui.py). This file is the one script that wires the new parts into it: the team's
   name in the rail and in the Simple view's strip and the title, the banner of a team that was merged away, the two new tabs (Workflow graph and Org chart),
   the node panel, and the live events.
   It needs SutraCtx and, for what it mounts, GraphView, OrgChartView, NodePanel and SutraEvents (all read when they are used, so a missing view
   only leaves its tab empty). It is loaded last (E12), after J2's page script, and it does nothing on a page whose boot block is not a team page.

     DeptExt.init()       once, after DOMContentLoaded: chip(), title(), the node panel (drawers()), the `sutra:tab` listener, and, when
                          SutraCtx.currentTab is graph or orgchart, that view. J2 shows a ?tab= (or #hash) pane at PARSE time, before the E12
                          scripts run, so the `sutra:tab` event of E6 had no listener then; currentTab is what it left behind.
     DeptExt.chip()       the team's name in every chip the page has, #deptchip (the icon rail's strip) and #deptchip-s (the Simple view's), and as their
                          title, so a name the chip cuts short is whole on hover; for a team the boot block calls archived: the banner and body.archived
                          (sutra-panel.css hides the composers, because J2 ignores a refused write silently).
     DeptExt.title()      document.title = "<team> \u00b7 Sutra" (a middle dot).
     DeptExt.onTab(name)  the first time graph or orgchart shows, create its view in #pane-graph / #pane-orgchart and fill it; a later visit
                          fetches again only when the live stream is not up (events keep it current otherwise).
     DeptExt.events()     one SutraEvents stream (topics graph, chart, chat), opened by the first view, closed by destroy(); a graph.updated
                          that touches no node of this team is ignored while the graph shows this team only.
     (init also adds heads_up_view.js, chat_attention.js and attention_pill.js, in that order: the org-wide "N need you" pill, the count in the
                          tab title and the desktop notice of gap package attention; the pill reads, it opens no second stream. The J2 page is
                          not edited for it. It also adds chart_notes.js, the Chart notes under the Org chart tab's log: gap package chart-insight.)
     DeptExt.drawers()    mounts #nodepanel once. The panel and J2's Agent drawer exclude each other in both directions (the panel closes the Agent
                          drawer when it opens and closes itself when the Agent drawer opens: node_panel.js); mounting it is what makes that true.
     DeptExt.state()      {started, tab, live, mounted: {graph, orgchart}, fetches: {graph, chart}, panel}
     DeptExt.helpers      pure parts: touchesDept, bannerText, titleText.

   A classic script with ONE global, DeptExt (see sutra_ctx.js for why); in node it is module.exports and does not start by itself. */
(function (root) {
  "use strict";

  const GRAPH_TAB = "graph";
  const CHART_TAB = "orgchart";
  const COALESCE_MS = 150;           // a burst of events is one refetch
  const TOPICS = ["graph", "chart", "chat"];
  const FALLBACK_BANNER = "This team was merged into another team. Its history stays available.";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : "");
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();

  /* ---------------------------------------------------------------- pure parts */
  // A graph.updated carries only the nodes that changed. It matters to a page that shows one team when one of them belongs to the team (or to
  // nobody: the root) and always when it shows every team. A body that does not say what changed is treated as relevant: one refetch is cheap.
  function touchesDept(data, dept, showsAll) {
    if (showsAll === true || clean(dept) === "") return true;
    const nodes = isObj(data) && Array.isArray(data.nodes) ? data.nodes : null;
    if (nodes === null || nodes.length === 0) return true;
    return nodes.some(n => !isObj(n) || clean(n.dept_id) === "" || n.dept_id === dept || n.id === dept);
  }

  // The banner of an archived team: the server's own sentence (BootContext.note), else a generic one.
  function bannerText(boot) {
    const note = isObj(boot) ? clean(boot.note) : "";
    return note !== "" ? note : FALLBACK_BANNER;
  }

  function titleText(boot) {
    const label = isObj(boot) ? clean(boot.dept_label) : "";
    return label === "" ? "" : label + " \u00b7 Sutra";
  }

  /* ---------------------------------------------------------------- the page */
  const ctx = () => root.SutraCtx || null;
  const doc = () => root.document || null;
  const byId = id => (doc() ? doc().getElementById(id) : null);
  const bootOf = () => (ctx() && isObj(ctx().boot) ? ctx().boot : {});
  const deptOf = () => (ctx() && typeof ctx().dept === "string" ? ctx().dept : "");

  function report(where, error) {
    if (typeof console !== "undefined" && console && typeof console.error === "function") console.error("DeptExt: " + where + " failed", error);
  }

  // Call `fn`; a view that throws must not take the J2 page with it (its own script, and the clicks of the owner, keep working).
  function safely(where, fn) {
    try {
      return fn();
    } catch (e) {
      report(where, e);
      return undefined;
    }
  }

  const S = {
    started: false,
    listening: false,
    tab: "",
    live: "offline",
    stream: null,
    panel: null,
    graph: null,           // the GraphView handle
    chart: null,           // the OrgChartView handle
    graphDrawn: false,     // the graph view has been given its first answer
    lastGraph: null,       // the raw answer of the last GET /api/graph, which the node panel reads (getGraph)
    graphSeq: 0,
    pendingSelect: "",     // a node "Show in graph" asked for before the graph had been drawn
    fetches: {graph: 0, chart: 0},
    refetchGraph: null,
    refetchChart: null,
    archived: false,
  };

  /* ---- chip, title, banner */
  const CHIPS = ["deptchip", "deptchip-s"];          // the strip at the top of the icon rail and the one at the top of the Simple view

  function chip() {
    const boot = bootOf();
    const label = clean(boot.dept_label);
    CHIPS.map(byId).filter(Boolean).forEach(el => {
      el.textContent = label;
      if (label !== "" && typeof el.setAttribute === "function") el.setAttribute("title", label);
    });
    const d = doc();
    if (!d || !d.body) return false;
    if (boot.archived !== true) return false;
    d.body.classList.add("archived");
    S.archived = true;
    // One banner at the top of each of J2's two views (the chat view and the detail view show one at a time). The body is a flex box whose
    // direction changes with the view, so a banner of its own as a child of the body would become a column of the chat view.
    const places = [d.getElementById("sview"), d.querySelector("#dview .dcol")].filter(Boolean);
    if (places.length === 0) places.push(d.body);
    const sentence = bannerText(boot);
    places.forEach(place => {
      let banner = place.querySelector(":scope > .archivedbanner");
      if (!banner) {
        banner = d.createElement("div");
        banner.className = "banner archivedbanner";
        banner.setAttribute("role", "status");
        const strip = place.querySelector(":scope > .steamstrip");          // the Simple view's strip ("All teams", the team's name) stays the first thing on the page
        place.insertBefore(banner, strip ? strip.nextSibling : place.firstChild);
      }
      banner.textContent = sentence;
    });
    return true;
  }

  function title() {
    const t = titleText(bootOf());
    if (t !== "" && doc()) doc().title = t;
    return t;
  }

  /* ---- the node panel and the Agent drawer */
  function drawers() {
    const d = doc();
    const root_ = byId("nodepanel");
    if (!d || !root_ || !root.NodePanel) return null;
    for (const name of ["fluid", "chat_pill", "chat_fold", "chat_search", "chat_composer", "chat_markdown", "chat_draft", "chat_scroll", "rules_view", "agent_chats"]) {           // the J2 page is not edited: the chat scripts of ABS-9, ABS-10, ABS-15, GAP-markdown and GAP-chat-comfort (and fluid.js, gap package fluid) are added from here
      if (d.head && !d.getElementById(name + "-js")) {
        const tag = d.createElement("script");
        tag.id = name + "-js";
        tag.src = "/ui/js/" + name + ".js";
        d.head.appendChild(tag);
      }
    }
    if (S.panel === null) {
      S.panel = safely("NodePanel.mount", () => root.NodePanel.mount(root_, {getGraph: () => S.lastGraph}));
    }
    return S.panel;
  }

  /* ---- the org-wide "N need you" pill, the tab title count and the desktop notice (gap package attention; attention_pill.js starts itself) */
  function attention() {
    const d = doc();
    if (!d || !d.head) return false;
    for (const name of ["heads_up_view", "chat_attention", "attention_pill"]) {
      if (d.getElementById(name + "-js")) continue;
      const tag = d.createElement("script");
      tag.id = name + "-js";
      tag.src = "/ui/js/" + name + ".js";
      tag.async = false;                         // run in this order: the pill reads the two others when it starts
      d.head.appendChild(tag);
    }
    return true;
  }

  /* ---- the Chart notes of the Org chart tab (chart_notes.js, gap package chart-insight): J2's page is not edited, so its script is added from here;
     the org chart view draws the notes when the script is there and reads it again shortly when it is not yet */
  function insight() {
    const d = doc();
    if (!d || !d.head || d.getElementById("chart_notes-js")) return false;
    const tag = d.createElement("script");
    tag.id = "chart_notes-js";
    tag.src = "/ui/js/chart_notes.js";
    d.head.appendChild(tag);
    return true;
  }

  /* ---- the model picker under the chat pill (model_pick.js, gap package welcome-settings): J2's page is not edited, so its script is added from here;
     chat_pill.js draws it when the script is there and the pill is as it was when it is not */
  function pickers() {
    const d = doc();
    if (!d || !d.head) return false;
    for (const name of ["model_pick", "tab_heal"]) {
      if (d.getElementById(name + "-js")) continue;
      const tag = d.createElement("script");
      tag.id = name + "-js";
      tag.src = "/ui/js/" + name + ".js";
      d.head.appendChild(tag);
    }
    return true;
  }

  function openNode(node) {
    const panel = drawers();
    if (!panel || !isObj(node) || clean(node.id) === "") return;
    if (node.kind === "root") {                // the root is the whole organisation: its page is the Org chart
      showTab(CHART_TAB);
      return;
    }
    panel.open(node.id, "chat");
  }

  // J2's showTab is a top-level function of its page script; its rail button is the same thing when it is not there.
  function showTab(name) {
    if (typeof root.showTab === "function") {
      root.showTab(name);
      return true;
    }
    const button = doc() ? doc().querySelector('.tabs [data-tab="' + name + '"]') : null;
    if (button && typeof button.click === "function") {
      button.click();
      return true;
    }
    return false;
  }

  // "Show in graph" of the org chart's card: switch to the graph; the node is selected as soon as that graph has been drawn.
  function showInGraph(node) {
    if (!isObj(node) || clean(node.id) === "") return;
    S.pendingSelect = node.id;
    showTab(GRAPH_TAB);
    selectPending();
  }

  function selectPending() {
    if (S.pendingSelect === "" || !S.graph || !S.graphDrawn) return;
    const id = S.pendingSelect;
    S.pendingSelect = "";
    S.graph.select(id);
  }

  /* ---- the live stream */
  const mounted = () => ({graph: S.graph !== null, orgchart: S.chart !== null});

  function setLive(state) {
    S.live = state;
    if (S.graph) S.graph.setLive(state);
    if (S.chart) S.chart.setLive(state);
  }

  function showsAll() {
    if (!S.graph) return false;
    const st = safely("graph state", () => S.graph.state());
    return isObj(st) && st.scope === "all";
  }

  function loadGraph() {
    if (!S.graph || !ctx()) return Promise.resolve(false);
    const mine = ++S.graphSeq;
    S.fetches.graph += 1;
    const view = S.graph;
    return ctx().api.get("/api/graph", {level: "chart", dept: deptOf()}).then(raw => {
      if (mine !== S.graphSeq || view !== S.graph) return false;
      S.lastGraph = raw;
      S.graphDrawn = true;
      safely("graph update", () => view.update(raw));
      selectPending();
      return true;
    }, err => {
      if (mine === S.graphSeq && view === S.graph) safely("graph fail", () => view.fail(err));
      return false;
    });
  }

  function loadChart() {
    if (!S.chart) return Promise.resolve(false);
    S.fetches.chart += 1;
    return S.chart.refresh();
  }

  function onEvent(type, data) {
    if (type === "graph.updated") {
      if (S.refetchGraph && touchesDept(data, deptOf(), showsAll())) S.refetchGraph();
    } else if (type === "chart.changed" || type === "chart.approval") {
      if (S.refetchChart) S.refetchChart();
    } else if (type === "server.resync") {
      if (S.refetchGraph) S.refetchGraph();
      if (S.refetchChart) S.refetchChart();
    } else if (type === "chat.message") {
      const message = isObj(data) && isObj(data.message) ? data.message : null;
      // the owner's own line is not news to the owner, and neither is a question to a function (`ask`: the owner asked it) or the answer the owner is waiting for
      if (S.graph && message && message.who !== "user" && clean(message.ask) === "" && clean(data.session_id) !== "") safely("noteMessage", () => S.graph.noteMessage(data.session_id, message.id));
    }
  }

  function events() {
    if (S.stream !== null) return S.stream;
    if (!root.SutraEvents) return null;
    const events_ = root.SutraEvents;
    S.refetchGraph = events_.coalesce(loadGraph, COALESCE_MS);
    S.refetchChart = events_.coalesce(loadChart, COALESCE_MS);
    S.stream = safely("SutraEvents.connect", () => events_.connect({
      url: "/api/events",
      topics: TOPICS,
      onEvent: onEvent,
      onState: setLive,
      // the stream is down: the same two reads, every pollMs, for the views on screen
      pollFn: () => Promise.all([S.graph ? loadGraph() : null, S.chart ? loadChart() : null]),
    }));
    return S.stream;
  }

  /* ---- the two new tabs */
  function mountGraph() {
    const host = byId("pane-graph");
    if (!host || !root.GraphView) return false;
    S.graph = safely("GraphView.create", () => root.GraphView.create(host, {
      mode: "graph", scope: "this", level: "chart", dept: deptOf(), onOpen: openNode,
    })) || null;
    if (!S.graph) return false;
    S.graph.setLive(S.live);
    events();
    loadGraph();
    return true;
  }

  function mountChart() {
    const host = byId("pane-orgchart");
    if (!host || !root.OrgChartView) return false;
    S.chart = safely("OrgChartView.create", () => root.OrgChartView.create(host, {
      dept: deptOf(), onOpen: openNode, onShow: showInGraph,
    })) || null;
    if (!S.chart) return false;
    S.chart.setLive(S.live);
    events();
    loadChart();
    return true;
  }

  function onTab(name) {
    S.tab = typeof name === "string" ? name : "";
    if (name === GRAPH_TAB) {
      if (S.graph === null) return mountGraph();
      if (S.live !== "live") loadGraph();
      return true;
    }
    if (name === CHART_TAB) {
      if (S.chart === null) return mountChart();
      if (S.live !== "live") loadChart();
      return true;
    }
    return false;
  }

  /* ---- start */
  function init() {
    if (S.started) return false;
    S.started = true;
    chip();
    title();
    drawers();
    pickers();
    attention();
    insight();
    const d = doc();
    if (d && typeof d.addEventListener === "function") {
      d.addEventListener("sutra:tab", e => onTab(isObj(e && e.detail) ? e.detail.name : ""));
      // the panel wrote the last message id it showed: the node's unread dot goes at once
      d.addEventListener("sutra:seen", e => {
        const session = isObj(e && e.detail) ? e.detail.session : "";
        if (S.graph && session) safely("markSeen", () => S.graph.markSeen(session));
      });
      S.listening = true;
    }
    const current = ctx() && typeof ctx().currentTab === "string" ? ctx().currentTab : "";
    S.tab = current;
    if (current === GRAPH_TAB || current === CHART_TAB) onTab(current);
    return true;
  }

  function destroy() {
    if (S.stream) S.stream.close();
    if (S.refetchGraph) S.refetchGraph.cancel();
    if (S.refetchChart) S.refetchChart.cancel();
    if (S.graph) S.graph.destroy();
    if (S.chart) S.chart.destroy();
    S.stream = S.graph = S.chart = S.refetchGraph = S.refetchChart = null;
    S.graphDrawn = false;
    S.graphSeq += 1;
  }

  const DeptExt = {
    init, chip, title, onTab, events, drawers, destroy,
    state: () => ({started: S.started, tab: S.tab, live: S.live, mounted: mounted(), fetches: Object.assign({}, S.fetches), panel: S.panel !== null, archived: S.archived}),
    helpers: {touchesDept, bannerText, titleText},
  };

  if (typeof module === "object" && module !== null && module.exports) {
    module.exports = DeptExt;
  } else {
    root.DeptExt = DeptExt;
    // A team page only (Home and a stub DOM load nothing of this): start now when the DOM is ready, else when it is.
    if (bootOf().page === "dept" && doc()) {
      if (doc().readyState === "loading") doc().addEventListener("DOMContentLoaded", init);
      else init();
    }
  }
})(globalThis);
