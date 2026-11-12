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
     (init also adds project_rail.js and its sheet: the project sidebar of every page, mounted once the script has loaded; and the view switch,
                          Simple / Manager / Debug, at the right of the studio's top bar, floating at the top right in the Detailed view. Home has
                          no switch: the level only changes what a project's page shows.)
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
    levelWatch: null,          // keeps a Simple-level page in its studio (levels())
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

  /* ---- the Raw AI chat debugger (raw_chat.js): its "Raw AI chat" button shows at the Debug level, and /d/{team}/raw opens it full screen;
     J2's page is not edited, so its script is added from here */
  function rawChat() {
    const d = doc();
    if (!d || !d.head || d.getElementById("raw_chat-js")) return false;
    const tag = d.createElement("script");
    tag.id = "raw_chat-js";
    tag.src = "/ui/js/raw_chat.js";
    d.head.appendChild(tag);
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

  /* ---- the owner's level (SutraCtx.level, the one-front brief): at Simple a team page is its studio only. sutra-panel.css hides the ways into the
     Detailed view (keyed on <html data-level>); this keeps the page in the Simple view when something else (a ?tab= link, J2's own code) asks for
     the Detailed one. The template library is a Detailed page of its own and is left alone. Manager and Debug change nothing here. */
  function levelView() {
    const c = ctx();
    const d = doc();
    if (!c || typeof c.level !== "function" || c.level() !== "simple" || !d || !d.body) return false;
    if (typeof c.onLibrary === "function" && c.onLibrary()) return false;
    if (d.body.classList.contains("simple") || typeof root.setView !== "function") return false;
    safely("setView", () => root.setView("simple", false));
    return true;
  }

  function levels() {
    const d = doc();
    levelView();
    if (!d || typeof d.addEventListener !== "function") return false;
    d.addEventListener("sutra:level", levelView);
    if (typeof root.MutationObserver === "function" && d.body) {
      S.levelWatch = new root.MutationObserver(() => levelView());
      S.levelWatch.observe(d.body, {attributes: true, attributeFilter: ["class"]});
    }
    return true;
  }

  /* ---- the project sidebar (project_rail.js): every project, what needs the owner, New project and Settings & logs. J2's page is not edited:
     its script is added from here and mounts itself into the page once it has loaded. */
  function rail() {
    const d = doc();
    if (!d || !d.head || d.getElementById("project_rail-js")) return false;
    const css = d.createElement("link");             // before the script runs, so the column does not flash unstyled
    css.rel = "stylesheet";
    css.href = "/ui/css/project_rail.css";
    d.head.appendChild(css);
    const tag = d.createElement("script");
    tag.id = "project_rail-js";
    tag.src = "/ui/js/project_rail.js";
    tag.addEventListener("load", () => { if (root.ProjectRail) safely("ProjectRail.mount", () => root.ProjectRail.mount({})); place(); });
    d.head.appendChild(tag);
    return true;
  }

  /* ---- the view switch (Simple / Manager / Debug): one small menu at the right of the studio's top bar. It only changes what a project page
     shows; Home has none. Manager and Debug also list the ways into what they add. */
  const VIEWS = [
    {level: "simple", label: "Simple", hint: "Just your project"},
    {level: "manager", label: "Manager", hint: "Adds the Detailed view, team chats and the org map"},
    {level: "debug", label: "Debug", hint: "Adds the raw AI chat, usage and log"},
  ];

  function switchMenuHtml(level) {
    const at = min => VIEWS.findIndex(v => v.level === level) >= VIEWS.findIndex(v => v.level === min);
    const opts = VIEWS.map(v => '<button type="button" class="pv-opt" role="menuitemradio" data-level="' + v.level + '" aria-checked="' + (v.level === level) + '"><b>' +
      v.label + "</b><small>" + v.hint + "</small></button>").join("");
    const extra = [];
    if (at("manager")) {
      extra.push('<button type="button" class="pv-link" role="menuitem" data-go="detail">Detailed view</button>',
        '<a class="pv-link" role="menuitem" href="/?pane=chat">Team chats</a>', '<a class="pv-link" role="menuitem" href="/?pane=chart">Org chart</a>',
        '<a class="pv-link" role="menuitem" href="/?pane=graph">Workflow graph</a>');
    }
    if (at("debug")) {
      extra.push('<button type="button" class="pv-link" role="menuitem" data-go="raw">Raw AI chat</button>', '<a class="pv-link" role="menuitem" href="/console">Usage and log</a>');
    }
    return opts + (extra.length ? '<div class="pv-sep" role="separator"></div><div class="pv-extra">' + extra.join("") + "</div>" : "");
  }

  function viewSwitch() {
    const d = doc();
    const c = ctx();
    if (!d || !d.body || !c || typeof c.level !== "function" || byId("pviewsw")) return null;
    const box = d.createElement("div");
    box.className = "pv";
    box.id = "pviewsw";
    box.innerHTML = '<button type="button" class="pv-btn" id="pv-btn" aria-haspopup="menu" aria-expanded="false" aria-controls="pv-menu"></button>' +
      '<div class="pv-menu" id="pv-menu" role="menu" aria-label="How much to show" hidden></div>';
    const btn = box.querySelector("#pv-btn");
    const menu = box.querySelector("#pv-menu");
    const paint = () => {
      const level = c.level();
      const v = VIEWS.find(x => x.level === level) || VIEWS[0];
      btn.innerHTML = v.label + ' <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
      btn.setAttribute("aria-label", "View: " + v.label + ". Change how much this project shows");
      menu.innerHTML = switchMenuHtml(level);
    };
    const show = open => {
      menu.hidden = !open;
      // a narrow bar wraps the switch to its left end: the menu then opens to the right, never under the sidebar
      menu.classList.remove("pv-left");
      if (open && typeof btn.getBoundingClientRect === "function" && btn.getBoundingClientRect().right < 300 + (d.body.classList.contains("has-prail") ? 260 : 0)) menu.classList.add("pv-left");
      btn.setAttribute("aria-expanded", String(open));
      if (open) { const on = menu.querySelector('[aria-checked="true"]'); if (on) on.focus(); }
    };
    btn.addEventListener("click", () => show(menu.hidden));
    menu.addEventListener("click", e => {
      const opt = e.target.closest(".pv-opt[data-level]");          // <html> carries data-level too
      const go = e.target.closest(".pv-link[data-go]");
      if (opt || go) e.stopPropagation();           // the studio's own click handlers (it sits in #sview) never see the menu's clicks
      if (opt) { c.setLevel(opt.dataset.level); show(false); btn.focus(); return; }
      // the next turn: the switch moves out of the studio's bar when the view changes, so the click has to be over first
      if (go && go.dataset.go === "detail") { show(false); root.setTimeout(() => { if (typeof root.setView === "function") safely("setView", () => root.setView("detail", true)); }, 0); }
      if (go && go.dataset.go === "raw") { show(false); if (root.RawChat) safely("RawChat.open", () => root.RawChat.open({})); }
    });
    d.addEventListener("click", e => { if (!menu.hidden && !box.contains(e.target)) show(false); });
    d.addEventListener("keydown", e => { if (e.key === "Escape" && !menu.hidden) { show(false); btn.focus(); } });
    d.addEventListener("sutra:level", paint);
    paint();
    place(box);
    return box;
  }

  // In the studio the switch sits at the right of its top bar (before the theme button); in the Detailed view it floats at the top right.
  function place(box) {
    const d = doc();
    const el = box || byId("pviewsw");
    if (!d || !d.body || !el) return;
    const bar = d.querySelector("#sview .stop");
    const studio = d.body.classList.contains("simple") && bar;
    const side = d.getElementById("pr-settings");        // the project sidebar's foot, once project_rail.js has mounted it
    el.classList.remove("pv-float", "pv-inrail");
    if (studio) {
      const before = bar.querySelector("#stheme2");
      if (el.parentNode !== bar) bar.insertBefore(el, before || null);
    } else if (side) {                                   // the Detailed view: at the foot of the sidebar, clear of the page's own pill and chat
      if (el.nextSibling !== side) side.parentNode.insertBefore(el, side);
      el.classList.add("pv-inrail");
    } else {
      if (el.parentNode !== d.body) d.body.appendChild(el);
      el.classList.add("pv-float");
    }
  }

  /* ---- start */
  function init() {
    if (S.started) return false;
    S.started = true;
    levels();
    // the template library is a Detailed page of its own (a tool, not a project view): it keeps J2's full width, with no sidebar and no switch
    const library = !!(ctx() && typeof ctx().onLibrary === "function" && ctx().onLibrary());
    if (!library) rail();
    if (!library) viewSwitch();
    if (typeof root.MutationObserver === "function" && doc() && doc().body) {
      new root.MutationObserver(() => place()).observe(doc().body, {attributes: true, attributeFilter: ["class"]});
    }
    chip();
    title();
    drawers();
    pickers();
    attention();
    insight();
    rawChat();
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
    init, chip, title, onTab, events, drawers, destroy, levelView,
    state: () => ({started: S.started, tab: S.tab, live: S.live, mounted: mounted(), fetches: Object.assign({}, S.fetches), panel: S.panel !== null, archived: S.archived}),
    helpers: {touchesDept, bannerText, titleText, switchMenuHtml},
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
