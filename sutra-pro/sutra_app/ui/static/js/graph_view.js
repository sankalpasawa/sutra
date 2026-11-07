/* graph_view.js - the Workflow graph pane: header, drawing, List view, pan and zoom, live updates (work package UI-5; docs/design/ui.md
   sections 3.3, 6.1, 6.2, 7, 9 and 10; S3-web-13, S4-fnodes-10; D75, D80).

   The DOM half of the graph views. The pure half is graph_layout.js (the tree and its layout), graph_render.js (the SVG string, the
   outline, the counts) and chart_marks.js; this file puts their output in a pane, keeps it live and handles the pointer. The org chart
   (orgchart_view.js) is this same view in mode "chart".

     GraphView.create(host, {mode, scope, level, dept, title, onOpen(node), onSelect(node), onRetry()}) -> handle
       mode    "graph" (default): update() takes ORCH's GraphView {version, chart_version, nodes, edges}.
               "chart": update() takes a graph {nodes, links?, cross?} (ChartMarks.toGraph's answer) and, as 2nd argument, {marks, ring}.
       scope   "this" | "all" and level "chart" | "full": what the HOST fetched (GET /api/graph?level=&dept=), used to tell whether the
               pane's own toggles can be served from the data it has or need a request of their own (see "toggles" below).
       dept    the team being viewed (default SutraCtx.dept); with none there is no This team | All teams toggle.
       onOpen  a click, Enter or Space on a node of a graph (the host opens the chat panel; for the root node it focuses the org chat).
       onSelect  the selection moved because the owner picked a node (a click or the keyboard; not for select(id)); the org chart's card.
       onRetry  what "Try again" does in chart mode (graph mode fetches /api/graph itself).
     handle  {update(data, extra), select(id), fit(), setView("graph"|"list"), setLive("live"|"polling"|"offline"), destroy(),
              refresh(), fail(err), noteMessage(sessionId, messageId), markSeen(sessionId), state(), el}

   Toggles (graph mode). The header has Graph | List, Overview | Detail and, with a team, This team | All teams. Overview is level=chart
   (root, teams, divisions and one task step per task), Detail is level=full, This team is the nodes of dept_id === dept. When the data in
   hand is wide enough (a full graph can be narrowed to an overview, an all-teams graph to one team) the pane narrows it itself; when not,
   it asks GET /api/graph?level=&dept= once, and from then on treats the host's updates as "something changed" and asks again, so a host
   that keeps fetching at its own level never undoes what the owner chose. The choice is kept in localStorage `sutra:graph:<dept or all>`.

   Pan and zoom are the pane's own (pointer events and one transform on g.wview), not d3: the scale runs from 0.25 to 4 as J2's d3.zoom
   does, a pointer that moves 4 px or less still clicks, wheel and pinch zoom about the pointer, and the first view is 1:1 centred on the
   top middle, which Fit returns to. The pane therefore needs neither d3 nor a DOM measure other than the viewport's own size.

   Nothing from the wire is ever put in markup unescaped: the drawing and the list come from graph_render.js, and everything this file
   writes by hand goes through esc(). A classic script with ONE global, GraphView (see sutra_ctx.js for why); in node it is
   module.exports, and GraphView.helpers holds the pure parts. */
(function (root) {
  "use strict";

  /* ---------------------------------------------------------------- constants */
  const MIN_SCALE = 0.25;           // d3.zoom's extent in J2 (j2_ui.html:2209)
  const MAX_SCALE = 4;
  const CLICK_DISTANCE = 4;         // pixels a pointer may travel and still click (d3.zoom's clickDistance in J2)
  const FRESH_MS = 1200;            // how long a node that has just arrived keeps .wnew
  const BIG_GRAPH = 500;            // a graph with more nodes opens as a list (R11)
  const REVEAL_MARGIN = 24;         // room kept round a node that is panned into view
  const LEVELS = ["chart", "full"];
  const SCOPES = ["this", "all"];
  const VIEWS = ["graph", "list"];
  const LIVE_STATES = ["live", "polling", "offline"];
  const CHOICE_KEY = "sutra:graph:";   // + the team or "all": {level, scope, view}, the last choice
  const SEEN_KEY = "sutra:seen:";      // + a session id: the last message id the owner has seen there
  let instances = 0;

  /* ---------------------------------------------------------------- the pieces this file stands on */
  function need(name, file) {
    const found = root[name] || (typeof require === "function" ? require(file) : undefined);
    if (!found) throw new Error("GraphView needs " + name + ": load " + file.replace("./", "") + " before it");
    return found;
  }
  const layoutLib = () => need("GraphLayout", "./graph_layout.js");
  const renderLib = () => need("GraphRender", "./graph_render.js");
  const ctxLib = () => need("SutraCtx", "./sutra_ctx.js");

  /* ---------------------------------------------------------------- small helpers */
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const finite = Number.isFinite;
  const text = v => (typeof v === "string" ? v : (finite(v) ? String(v) : ""));
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ENTITIES[c]);
  const round2 = n => Math.round(n * 100) / 100;
  const oneOf = (list, v, fallback) => (list.includes(v) ? v : fallback);
  const unit = (n, one, many) => n + " " + (n === 1 ? one : many);
  const unique = list => Array.from(new Set(list));

  function safely(where, fn, arg) {
    try {
      return fn(arg);
    } catch (e) {
      if (typeof console !== "undefined" && console && typeof console.error === "function") console.error("GraphView: " + where + " failed", e);
      return undefined;
    }
  }

  /* ---------------------------------------------------------------- pure: what the toggles ask for */
  const OVERVIEW_KINDS = new Set(["root", "department", "division"]);
  // The nodes of level=chart: the structure and one task step per task (the server marks that step with step_ref "task").
  const inOverview = n => OVERVIEW_KINDS.has(n.kind) || (n.kind === "step" && n.step_ref === "task");

  // serves(have, want): can data fetched as `have` ({level, dept}; dept "" is every team) show what `want` asks for? A full graph can be
  // narrowed to an overview and an all-teams graph to one team, never the other way round.
  const serves = (have, want) => (have.level === "full" || want.level === "chart") && (have.dept === "" || have.dept === want.dept);

  // narrow(view, have, want) -> a GraphView with only what `want` asks for, from data fetched as `have`. One team is the nodes of
  // dept_id === dept (so not the root, whether the server or this function did the cutting: the picture is the same); an overview is cut
  // only from a full graph (an overview that the server sent is taken as it is). A link stays when both of its ends do. Not changed: view.
  function narrow(view, have, want) {
    if (!isObj(view) || !Array.isArray(view.nodes)) return view;               // not a graph: GraphLayout.validate says so
    const byDept = want.dept !== "";
    const byLevel = have.level === "full" && want.level === "chart";
    if (!byDept && !byLevel) return view;
    const nodes = view.nodes.filter(n => isObj(n) && (!byDept || n.dept_id === want.dept) && (!byLevel || inOverview(n)));
    const ids = new Set(nodes.map(n => n.id));
    const edges = Array.isArray(view.edges) ? view.edges.filter(e => isObj(e) && ids.has(e.src) && ids.has(e.dst)) : view.edges;
    return Object.assign({}, view, {nodes, edges});
  }

  /* ---------------------------------------------------------------- pure: pan and zoom (t = {k, x, y}: the point (u, v) of the drawing is at (x + k*u, y + k*v)) */
  const clampScale = k => Math.min(MAX_SCALE, Math.max(MIN_SCALE, k));

  // zoomAbout(t, factor, px, py): the scale times `factor` (kept between 0.25 and 4), the point under (px, py) staying where it is.
  function zoomAbout(t, factor, px, py) {
    const k = clampScale(t.k * factor);
    const ratio = k / t.k;
    return {k, x: px - (px - t.x) * ratio, y: py - (py - t.y) * ratio};
  }

  // The first view: 1:1 (labels keep their size), the middle of the drawing under the middle of the viewport, its top at the top.
  const homeOf = (drawingWidth, viewportWidth) => ({k: 1, x: (viewportWidth - drawingWidth) / 2, y: 0});

  // bringIntoView(t, box, size, margin): t moved the least that puts `box` ({x, y, w, h} in drawing units) inside the viewport
  // ({w, h}) with `margin` to spare; a box too big for it keeps its top left corner in view.
  function bringIntoView(t, box, size, margin) {
    const axis = (pos, extent, view, shift) => {
      const lo = pos * t.k + shift;
      const hi = (pos + extent) * t.k + shift;
      if (lo < margin) return shift + (margin - lo);
      if (hi > view - margin) return shift - (hi - (view - margin));
      return shift;
    };
    return {k: t.k, x: axis(box.x, box.w, size.w, t.x), y: axis(box.y, box.h, size.h, t.y)};
  }

  /* ---------------------------------------------------------------- pure: the sentence for screen readers */
  function listOf(names) {
    return names.length < 2 ? names.join("") : names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
  }

  // sentenceOf(prev, next): one sentence on what changed between two validated graphs, or "". A node that now needs the owner (it waits on
  // them, or it faulted) comes first, then new nodes, other status changes and removed nodes. "Quotes was added under Web", "Identity is
  // waiting on you".
  function sentenceOf(prev, next) {
    const diff = layoutLib().diff(prev, next);
    const index = g => new Map((isObj(g) && Array.isArray(g.nodes) ? g.nodes : []).map(n => [n.id, n]));
    const was = index(prev);
    const now = index(next);
    const name = n => clean(n.label) || n.id;
    const said = change => {
      const n = now.get(change.id);
      const word = renderLib().statusWord(n.status, n.kind, isObj(n.meta) ? n.meta.wait_on : undefined) || "idle";
      return name(n) + " is " + word;
    };
    const statusSentence = list => said(list[0]) + (list.length > 1 ? " (and " + (list.length - 1) + " more)" : "");
    const needing = diff.status.filter(c => c.to === "waiting_on_you" || c.to === "fault");
    if (needing.length) return statusSentence(needing);
    if (diff.added.length) {
      const names = diff.added.map(id => name(now.get(id)));
      if (names.length > 3) return names.length + " nodes were added";
      if (names.length > 1) return listOf(names) + " were added";
      const parent = now.get(diff.added[0]).parent;
      return names[0] + " was added" + (parent && now.has(parent) ? " under " + name(now.get(parent)) : "");
    }
    if (diff.status.length) return statusSentence(diff.status);
    if (diff.removed.length) {
      const names = diff.removed.map(id => name(was.get(id)));
      return names.length > 3 ? names.length + " nodes were removed" : (names.length > 1 ? listOf(names) + " were removed" : names[0] + " was removed");
    }
    return "";
  }

  /* ---------------------------------------------------------------- the legend (static: written once) */
  function legendHtml(mode) {
    const steps = ["The chat agent reads the org chart.", "It looks in the model library.", "It plans the work with the Claude and Codex models and writes a workflow.",
      "The graph is shown to you here.", "Every node is linked to its own chat: click a node to open it.", "The graph updates as the agents work.",
      "Teams and divisions are chats you can write to."];
    const key = (cls, words) => '<span class="wk"><span class="wsw ' + cls + '" aria-hidden="true"></span>' + words + "</span>";
    const body = mode === "chart"
      ? "<h4>Marks</h4><p>" + key("box", "Reuse: a plain box, the team was used as it is") + key("box add", "Add: dashed, tinted, added by the change") +
        key("box move", "Rearrange: a thick outline, moved by the change") + "</p><p>A ring marks the team you are looking at. A row of the change log shows what that change did.</p>"
      : "<h4>Boxes</h4><p>A wide box is a team. A box with five dots on top is a division of a team. A box with a role and counts is one of the five function nodes " +
        "(its open and closed work atoms). A small box is a step of a task.</p>" +
        "<h4>Outline</h4><p>Green ring: filed and checked. Amber with ?: waiting. Red with !: blocked. Double ring: running now. Dashed: left open. " +
        "Dotted amber: done, but the checks did not pass. Hollow: not made.</p>" +
        "<h4>Lines</h4><p>" + key("org", "belongs to") + key("handoff", "hands over to") + key("reads", "reads or leads to") + key("speaks", "speaks to (the number of messages)") +
        key("fix", "revises") + "</p>" +
        "<h4>In seven steps</h4><ol>" + steps.map(s => "<li>" + esc(s) + "</li>").join("") + "</ol>";
    return '<details class="wlegend" data-key="wlegend"><summary>Legend</summary><div class="wlegbody">' + body + "<p>Drag to move, scroll or pinch to zoom, Fit to come back.</p></div></details>";
  }

  /* ---------------------------------------------------------------- the pane */
  function create(host, options) {
    if (!host || typeof host.appendChild !== "function") throw new TypeError("GraphView.create: host must be an element");
    const o = isObj(options) ? options : {};
    const L = layoutLib();
    const R = renderLib();
    const C = ctxLib();
    const doc = host.ownerDocument || root.document;
    const mode = o.mode === "chart" ? "chart" : "graph";
    const deptId = mode === "graph" ? (typeof o.dept === "string" && o.dept !== "" ? o.dept : text(C.dept)) : "";
    const title = clean(o.title) || (mode === "chart" ? "Org chart" : "Workflow graph");
    const uid = (mode === "chart" ? "c" : "g") + (++instances);

    // what the host fetches (and so what its update() calls hold) and what the owner's choices ask for
    const hostLevel = oneOf(LEVELS, o.level, "chart");
    const hostScope = oneOf(SCOPES, o.scope, deptId === "" ? "all" : "this");
    const hostHave = {level: hostLevel, dept: hostScope === "this" ? deptId : ""};
    const stored = loadChoice();
    let level = stored.level || hostLevel;
    let scope = deptId === "" ? "all" : (stored.scope || hostScope);
    let view = stored.view || "graph";
    let viewChosen = stored.view !== undefined;
    const wants = () => ({level, dept: scope === "this" ? deptId : ""});

    function loadChoice() {
      if (mode !== "graph") return {};
      try {
        const v = JSON.parse(root.localStorage.getItem(CHOICE_KEY + (deptId || "all")));
        if (!isObj(v)) return {};
        const out = {};
        if (LEVELS.includes(v.level)) out.level = v.level;
        if (SCOPES.includes(v.scope)) out.scope = v.scope;
        if (VIEWS.includes(v.view)) out.view = v.view;
        return out;
      } catch (e) {
        return {};               // no storage, a private window, or something else wrote the key
      }
    }
    function saveChoice() {
      if (mode !== "graph") return;
      try {
        root.localStorage.setItem(CHOICE_KEY + (deptId || "all"), JSON.stringify({level, scope, view}));
      } catch (e) {
        /* the choice then lasts as long as the page */
      }
    }

    // ---- the markup
    const toggle = (group, label, items) => '<span class="mapviews" role="group" aria-label="' + esc(label) + '" data-group="' + group + '">' +
      items.map(([value, name]) => '<button type="button" data-w' + group + '="' + value + '" aria-pressed="false">' + esc(name) + "</button>").join("") + "</span>";
    host.innerHTML = '<div class="wgpane" data-mode="' + mode + '">' +
      '<div class="maphead"><h3>' + esc(title) + '</h3><span class="wsums"></span>' +
      '<span class="wlive" data-state="offline" title="Not connected to the app">\u25cb offline</span>' +
      toggle("view", "View", [["graph", "Graph"], ["list", "List"]]) +
      (mode === "graph" ? toggle("level", "How much to show", [["chart", "Overview"], ["full", "Detail"]]) : "") +
      (mode === "graph" && deptId !== "" ? toggle("scope", "Which teams", [["this", "This team"], ["all", "All teams"]]) : "") +
      '<button type="button" class="linkbtn wfit" data-wfit>Fit</button></div>' +
      '<div class="wbanner" role="alert" hidden><span class="wbantext"></span><button type="button" class="linkbtn" data-wretry>Try again</button></div>' +
      '<p class="wnote" hidden></p><div class="wstage"><div class="wsvg"></div></div><div class="wlist"></div><p class="wempty" hidden></p>' +
      legendHtml(mode) + '<div class="wsr" aria-live="polite"></div></div>';
    const rootEl = host.firstElementChild;
    const q = sel => rootEl.querySelector(sel);
    const sumsEl = q(".wsums");
    const liveEl = q(".wlive");
    const stageEl = q(".wstage");
    const svgBox = q(".wsvg");
    const listEl = q(".wlist");
    const bannerEl = q(".wbanner");
    const noteEl = q(".wnote");
    const emptyEl = q(".wempty");
    const srEl = q(".wsr");

    // ---- state
    let data = null;                 // {kind: "graph", raw, have} or {kind: "chart", graph, marks, ring}
    let shown = null;                // {graph, layout, warnings}: what is on the page
    let drawnPicture = "";           // the fingerprint of what accept() last drew (pictureOf), "" when there is none
    let selected = "";
    let hoverId = "";
    let focusId = "";
    let liveState = "offline";
    let t = {k: 1, x: 0, y: 0};
    let touched = false;             // the owner has panned or zoomed: updates keep the view; Fit gives it back to the layout
    let skipClick = false;
    let destroyed = false;
    let fetchSeq = 0;
    const fresh = new Set();
    const timers = new Set();
    const latest = new Map();        // session id -> the newest message id the page has heard of
    const pointers = new Map();
    let drag = null;
    let pinch = null;

    const hotId = () => hoverId || focusId;
    const nodeAt = id => (shown ? shown.layout.nodes.find(n => n.id === id) : undefined);
    const copyOf = id => {
      const n = nodeAt(id);
      return n ? Object.assign({}, n) : null;
    };
    const reducedMotion = () => typeof root.matchMedia === "function" && root.matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* ---- unread dots: a node whose session has a message the owner has not seen */
    function seenOf(sessionId) {
      try {
        const v = Number(root.localStorage.getItem(SEEN_KEY + sessionId));
        return finite(v) ? v : 0;
      } catch (e) {
        return 0;
      }
    }
    function unreadIds(prep) {
      const ids = new Set();
      prep.layout.nodes.forEach(n => {
        if (typeof n.chat_session_id === "string" && latest.has(n.chat_session_id) && latest.get(n.chat_session_id) > seenOf(n.chat_session_id)) ids.add(n.id);
      });
      return ids;
    }
    function remember(sessionId) {
      if (typeof sessionId !== "string" || !latest.has(sessionId)) return;
      try {
        root.localStorage.setItem(SEEN_KEY + sessionId, String(Math.max(latest.get(sessionId), seenOf(sessionId))));
      } catch (e) {
        /* seen until the page is closed */
      }
    }

    /* ---- the view of the data: what the pane shows now */
    function prepare() {
      if (data.kind === "chart") {
        if (!isObj(data.graph) || !Array.isArray(data.graph.nodes)) throw new TypeError("GraphView: the chart graph must be an object with a nodes array");
        const layout = L.layout(data.graph);
        return {graph: data.graph, layout, warnings: unique(layout.warnings)};
      }
      const checked = L.validate(narrow(data.raw, data.have, wants()));         // a TypeError when it is no graph at all
      const layout = L.layout(checked.graph);
      return {graph: checked.graph, layout, warnings: unique(checked.warnings.concat(layout.warnings))};
    }

    function emptyText(prep) {
      if (!prep.layout.nodes.every(n => n.kind === "root")) return "";
      if (mode === "chart") return "No teams yet. The chat agent adds one when you ask for something.";
      return scope === "this" && deptId !== "" ? "This team has no graph yet." : "Nothing to draw yet. Tell the chat agent what you need and the graph appears here.";
    }

    function pillsHtml(prep) {
      const sum = R.summary(prep.graph);
      const pills = sum.parts.map((p, i) => '<span class="mappill' + (sum.waiting > 0 && i === sum.parts.length - 1 ? " waiting_on_you" : "") + '">' + esc(p) + "</span>");
      if (prep.warnings.length) pills.push('<span class="mappill wwarn" title="' + esc(prep.warnings.join("\n")) + '">' + unit(prep.warnings.length, "warning", "warnings") + "</span>");
      return pills.join("");
    }

    function syncControls() {
      const mark = (attr, value) => rootEl.querySelectorAll("[" + attr + "]").forEach(b => b.setAttribute("aria-pressed", String(b.getAttribute(attr) === value)));
      mark("data-wview", view);
      mark("data-wlevel", level);
      mark("data-wscope", scope);
      rootEl.setAttribute("data-view", view);
      rootEl.setAttribute("data-level", level);
      rootEl.setAttribute("data-scope", scope);
      noteEl.hidden = !(shown && view === "list" && shown.layout.nodes.length > BIG_GRAPH);
      if (!noteEl.hidden) noteEl.textContent = "This graph has " + shown.layout.nodes.length + " nodes, so it opens as a list. Choose Graph to see the picture.";
    }

    /* ---- the transform of g.wview */
    function applyTransform() {
      const g = stageEl.querySelector("g.wview");
      if (g) g.setAttribute("transform", "translate(" + round2(t.x) + " " + round2(t.y) + ") scale(" + round2(t.k) + ")");
      stageEl.setAttribute("data-k", String(round2(t.k)));
    }
    function goHome() {
      t = homeOf(shown ? shown.layout.width : 0, stageEl.clientWidth);
      touched = false;
      applyTransform();
    }
    function moveTo(next) {
      t = next;
      touched = true;
      applyTransform();
    }
    // the stage's inside, where the drawing lives: its border box less the border (clientLeft and clientTop), so a pointer is placed exactly
    function viewport() {
      const r = stageEl.getBoundingClientRect();
      return {left: r.left + stageEl.clientLeft, top: r.top + stageEl.clientTop, w: stageEl.clientWidth, h: stageEl.clientHeight};
    }
    function revealNode(id) {
      const n = nodeAt(id);
      const vp = viewport();
      if (!n || !vp.w || !vp.h) return;
      const next = bringIntoView(t, n, vp, REVEAL_MARGIN);
      if (next.x !== t.x || next.y !== t.y) moveTo(next);
    }

    /* ---- hover and focus light a node and the links at it; DOM classes only, so a hover never rebuilds the picture (and loses the focus) */
    function applyHot() {
      const svg = stageEl.querySelector("svg.wgsvg");
      if (!svg) return;
      const id = drag && drag.active ? "" : (nodeAt(hotId()) ? hotId() : "");
      svg.classList.toggle("ehot", id !== "");
      const near = new Set();
      if (id !== "" && shown) {
        shown.layout.links.concat(shown.layout.edges).forEach(e => {
          if (e.from === id) near.add(e.to);
          if (e.to === id) near.add(e.from);
        });
      }
      svg.querySelectorAll("g.wnode").forEach(el => {
        const nid = el.getAttribute("data-id");
        el.classList.toggle("hot", id !== "" && nid === id);
        el.classList.toggle("near", id !== "" && nid !== id && near.has(nid));
        el.classList.toggle("dim", id !== "" && nid !== id && !near.has(nid));
      });
      svg.querySelectorAll("path.wedge").forEach(el => {
        const on = id !== "" && (el.getAttribute("data-from") === id || el.getAttribute("data-to") === id);
        el.classList.toggle("hot", on);
        el.classList.toggle("dim", id !== "" && !on);
      });
    }

    /* ---- nodes that have just arrived glow for a moment (not with reduced motion) */
    function forId(ids, fn) {
      rootEl.querySelectorAll("g.wnode[data-id], button.wobtn[data-id]").forEach(el => {
        if (ids.has(el.getAttribute("data-id"))) fn(el.tagName.toLowerCase() === "button" ? el.closest("li") : el);
      });
    }
    function applyFresh() {
      if (fresh.size) forId(fresh, el => el && el.classList.add("wnew"));
    }
    function markFresh(ids) {
      if (!ids.length || reducedMotion()) return;
      ids.forEach(id => fresh.add(id));
      const timer = root.setTimeout(() => {
        timers.delete(timer);
        ids.forEach(id => fresh.delete(id));
        if (!destroyed) forId(new Set(ids), el => el && el.classList.remove("wnew"));
      }, FRESH_MS);
      timers.add(timer);
    }

    /* ---- focus survives a repaint */
    function rememberFocus() {
      const active = doc.activeElement;
      if (!active || active === doc.body || !rootEl.contains(active) || !active.closest) return null;
      const holder = active.closest("[data-id]");
      return holder ? {id: holder.getAttribute("data-id"), list: holder.tagName.toLowerCase() === "button"} : null;
    }
    function restoreFocus(was) {
      if (!was) return;
      const el = Array.from(rootEl.querySelectorAll(was.list ? "button.wobtn[data-id]" : "g.wnode[data-id]")).find(e => e.getAttribute("data-id") === was.id);
      if (el && doc.activeElement !== el && typeof el.focus === "function") el.focus({preventScroll: true});
    }

    /* ---- paint everything the state shows */
    function paintAll() {
      const prep = shown;
      const unread = unreadIds(prep);
      const marks = data.kind === "chart" ? data.marks : undefined;
      const ring = data.kind === "chart" ? data.ring : undefined;
      const focus = rememberFocus();
      C.paint(sumsEl, pillsHtml(prep));
      const drawn = C.paint(svgBox, R.svg(prep.layout, {selected, marks, unread, ring, uid, title, action: mode === "chart" ? "Show details." : undefined}));
      C.paint(listEl, R.outline(prep.graph, {selected, unread}));
      const empty = emptyText(prep);
      emptyEl.hidden = empty === "";
      emptyEl.textContent = empty;
      rootEl.setAttribute("data-empty", String(empty !== ""));
      syncControls();
      if (!touched) goHome();
      else if (drawn) applyTransform();
      if (drawn) applyHot();
      applyFresh();
      restoreFocus(focus);
      const active = doc.activeElement;
      const focused = active && active.closest ? active.closest("g.wnode") : null;
      focusId = focused && rootEl.contains(focused) ? focused.getAttribute("data-id") : "";
    }

    function hideBanner() {
      bannerEl.hidden = true;
    }
    function showBanner(err) {
      const network = err && err.code === "network";
      const words = shown === null ? (network ? "The app is not responding." : "The graph could not be loaded.")
        : (network ? "The app is not responding. Showing the last good version." : "Showing the last good version.");
      q(".wbantext").textContent = words;
      q("[data-wretry]").textContent = network ? "Retry" : "Try again";      // X8 says Retry for a server that does not answer, X5 Try again
      bannerEl.hidden = false;
    }

    // What a picture of `next` depends on (the data, what the owner asked for, which nodes are unread): equal fingerprints draw the same picture, so a
    // refetch that brought the same data (an event about another team, the poll while the stream is down) is not laid out and drawn again (Fluid.signature).
    function pictureOf(next) {
      const F = root.Fluid;
      if (!F || typeof F.signature !== "function" || shown === null) return "";
      const sig = F.signature({k: next.kind, g: next.kind === "chart" ? next.graph : next.raw, h: next.have, w: next.kind === "graph" ? wants() : null, m: next.marks, r: next.ring});
      return sig === "" ? "" : sig + "|" + Array.from(unreadIds(shown)).sort().join(",");
    }

    // Take new data. Returns false (and keeps the last good picture, with the banner) when it is not a graph.
    function accept(next, announce) {
      const same = pictureOf(next);
      if (same !== "" && same === drawnPicture) {
        data = next;
        hideBanner();
        return true;
      }
      const previous = data;
      data = next;
      let prep;
      try {
        prep = prepare();
      } catch (e) {
        data = previous;
        showBanner(e);
        return false;
      }
      commit(prep, announce);
      drawnPicture = pictureOf(next);
      hideBanner();
      return true;
    }

    function commit(prep, announce) {
      const before = shown;
      shown = prep;
      if (selected !== "" && !nodeAt(selected)) selected = "";
      if (!viewChosen && view !== "list" && prep.layout.nodes.length > BIG_GRAPH) view = "list";
      paintAll();
      if (announce && before) {
        const diff = L.diff(before.graph, prep.graph);
        markFresh(diff.added);
        applyFresh();
        const sentence = sentenceOf(before.graph, prep.graph);
        if (sentence !== "") srEl.textContent = sentence;
      }
    }

    // render again from the data in hand (the owner changed a toggle or picked a node); no announcement, nothing glows
    function reshow() {
      let prep;
      try {
        prep = prepare();
      } catch (e) {
        showBanner(e);
        return;
      }
      commit(prep, false);
    }

    /* ---- asking for the graph (the toggles, a data update that is too narrow, Try again) */
    function refresh(announce) {
      if (destroyed) return Promise.resolve(false);
      if (mode !== "graph") return Promise.resolve(typeof o.onRetry === "function" ? safely("onRetry", o.onRetry) : false);
      const want = wants();
      const mine = ++fetchSeq;
      const params = {level: want.level};
      if (want.dept !== "") params.dept = want.dept;
      return Promise.resolve().then(() => C.api.get("/api/graph", params)).then(raw => {
        if (destroyed || mine !== fetchSeq) return false;
        return accept({kind: "graph", raw, have: want}, announce !== false);
      }, err => {
        if (!destroyed && mine === fetchSeq) showBanner(err);
        return false;
      });
    }

    function afterToggle() {
      saveChoice();
      syncControls();
      if (data !== null && data.kind === "graph" && serves(data.have, wants())) reshow();
      else refresh(false);
    }

    /* ---- what the owner can do */
    function select(id) {
      if (destroyed) return false;
      if (!nodeAt(id)) {
        if (selected !== "") {
          selected = "";
          paintAll();
        }
        return false;
      }
      selected = id;
      paintAll();
      revealNode(id);
      const item = Array.from(listEl.querySelectorAll("button.wobtn[data-id]")).find(b => b.getAttribute("data-id") === id);
      if (item && item.scrollIntoView) item.scrollIntoView({block: "nearest"});
      return true;
    }

    function activate(id) {
      const node = copyOf(id);
      if (!node) return;
      selected = id;
      if (mode === "graph") remember(node.chat_session_id);
      paintAll();
      if (typeof o.onSelect === "function") safely("onSelect", o.onSelect, node);
      if (mode === "graph" && typeof o.onOpen === "function") safely("onOpen", o.onOpen, node);
    }

    function setView(next) {
      if (destroyed || !VIEWS.includes(next)) return;
      view = next;
      viewChosen = true;
      saveChoice();
      if (shown) paintAll();
      else syncControls();
    }

    function setLive(next) {
      liveState = oneOf(LIVE_STATES, next, "offline");
      liveEl.setAttribute("data-state", liveState);
      rootEl.setAttribute("data-live", liveState);
      liveEl.textContent = liveState === "live" ? "\u25cf live" : (liveState === "polling" ? "\u25cb polling" : "\u25cb offline");
      liveEl.setAttribute("title", liveState === "live" ? "Updates arrive as they happen" : (liveState === "polling" ? "Checking for updates every 2 seconds" : "Not connected to the app"));
    }

    function noteMessage(sessionId, messageId) {
      const id = Number(messageId);
      if (destroyed || typeof sessionId !== "string" || sessionId === "" || !finite(id)) return;
      latest.set(sessionId, Math.max(latest.get(sessionId) || 0, id));
      if (shown) paintAll();
    }
    function markSeen(sessionId) {
      if (destroyed) return;
      remember(sessionId);
      if (shown) paintAll();
    }

    /* ---- events */
    const nodeOf = el => (el && el.closest ? el.closest("g.wnode") : null);
    const idOf = el => el.getAttribute("data-id");
    // focus that did not come from a mouse (:focus-visible); a browser that does not know the selector counts every focus as the keyboard's
    const byKeyboard = el => {
      try {
        return el.matches(":focus-visible");
      } catch (e) {
        return true;
      }
    };

    rootEl.addEventListener("click", e => {
      const target = e.target;
      if (!target || !target.closest) return;
      const button = target.closest("[data-wview], [data-wlevel], [data-wscope], [data-wfit], [data-wretry]");
      if (button && rootEl.contains(button)) {
        if (button.hasAttribute("data-wview")) setView(button.getAttribute("data-wview"));
        else if (button.hasAttribute("data-wlevel")) setLevel(button.getAttribute("data-wlevel"));
        else if (button.hasAttribute("data-wscope")) setScope(button.getAttribute("data-wscope"));
        else if (button.hasAttribute("data-wfit")) fit();
        else refresh(true);
        return;
      }
      if (skipClick) return;                      // the end of a drag is not a click
      const node = target.closest("g.wnode, button.wobtn");
      if (node && rootEl.contains(node)) activate(idOf(node));
    });
    rootEl.addEventListener("keydown", e => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const node = nodeOf(e.target);
      if (!node) return;                          // buttons (the list, the header) click for themselves
      e.preventDefault();
      activate(idOf(node));
    });
    rootEl.addEventListener("mouseover", e => {
      const n = nodeOf(e.target);
      if (!n || hoverId === idOf(n)) return;       // moving over the parts of one box says nothing new
      hoverId = idOf(n);
      applyHot();
    });
    rootEl.addEventListener("mouseout", e => {
      const n = nodeOf(e.target);
      if (!n || nodeOf(e.relatedTarget) === n) return;
      hoverId = "";
      applyHot();
    });
    rootEl.addEventListener("focusin", e => {
      const n = nodeOf(e.target);
      if (!n) return;
      focusId = idOf(n);
      applyHot();
      if (byKeyboard(n)) revealNode(focusId);     // Tab to a node outside the viewport pans to it; a click on a sliver of one must not move it from under the pointer
    });
    rootEl.addEventListener("focusout", e => {
      if (!nodeOf(e.target)) return;
      focusId = "";
      applyHot();
    });

    function setLevel(next) {
      if (!LEVELS.includes(next) || next === level) return;
      level = next;
      afterToggle();
    }
    function setScope(next) {
      if (!SCOPES.includes(next) || next === scope || deptId === "") return;
      scope = next;
      afterToggle();
    }
    function fit() {
      if (!destroyed) goHome();
    }

    /* ---- pan (drag), zoom (wheel, pinch) */
    function stagePoint(clientX, clientY) {
      const vp = viewport();
      return {x: clientX - vp.left, y: clientY - vp.top};
    }
    const spread = () => {
      const [a, b] = Array.from(pointers.values());
      return {d: Math.hypot(a.x - b.x, a.y - b.y) || 1, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2};
    };
    stageEl.addEventListener("pointerdown", e => {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
      if (pointers.size === 1) {
        drag = {id: e.pointerId, sx: e.clientX, sy: e.clientY, tx: t.x, ty: t.y, active: false};
      } else if (pointers.size === 2) {
        drag = null;
        const s = spread();
        const p = stagePoint(s.x, s.y);
        pinch = {d: s.d, px: p.x, py: p.y, start: Object.assign({}, t)};
      }
    });
    stageEl.addEventListener("pointermove", e => {
      const p = pointers.get(e.pointerId);
      if (!p) return;
      p.x = e.clientX;
      p.y = e.clientY;
      if (pinch && pointers.size >= 2) {
        const s = spread();
        const at = stagePoint(s.x, s.y);
        const k = clampScale(pinch.start.k * s.d / pinch.d);
        // the point of the drawing that was under the first midpoint stays under the midpoint as it moves
        const u = (pinch.px - pinch.start.x) / pinch.start.k;
        const v = (pinch.py - pinch.start.y) / pinch.start.k;
        moveTo({k, x: at.x - u * k, y: at.y - v * k});
        return;
      }
      if (!drag || drag.id !== e.pointerId) return;
      const dx = e.clientX - drag.sx;
      const dy = e.clientY - drag.sy;
      if (!drag.active) {
        if (Math.hypot(dx, dy) <= CLICK_DISTANCE) return;
        drag.active = true;
        stageEl.classList.add("panning");
        try {
          stageEl.setPointerCapture(e.pointerId);
        } catch (err) {
          /* a pointer that is already gone */
        }
        applyHot();
      }
      moveTo({k: t.k, x: drag.tx + dx, y: drag.ty + dy});
    });
    function release(e) {
      if (!pointers.delete(e.pointerId)) return;
      if (drag && drag.id === e.pointerId) {
        if (drag.active) {
          skipClick = true;
          root.setTimeout(() => { skipClick = false; }, 0);
        }
        drag = null;
        stageEl.classList.remove("panning");
        applyHot();
      }
      if (pointers.size < 2) pinch = null;
      if (pointers.size === 1 && drag === null) {          // one finger of a pinch is left: it goes on as a pan from where it is
        const [id, p] = Array.from(pointers.entries())[0];
        drag = {id, sx: p.x, sy: p.y, tx: t.x, ty: t.y, active: true};
      }
    }
    stageEl.addEventListener("pointerup", release);
    stageEl.addEventListener("pointercancel", release);
    stageEl.addEventListener("wheel", e => {
      e.preventDefault();
      const scale = e.deltaMode === 1 ? 0.05 : (e.deltaMode ? 1 : 0.002);
      const at = stagePoint(e.clientX, e.clientY);
      moveTo(zoomAbout(t, Math.pow(2, -e.deltaY * scale * (e.ctrlKey ? 10 : 1)), at.x, at.y));
    }, {passive: false});

    const resizer = typeof root.ResizeObserver === "function" ? new root.ResizeObserver(() => { if (!touched && shown) goHome(); }) : null;
    if (resizer) resizer.observe(stageEl);

    /* ---- the handle */
    function update(input, extra) {
      if (destroyed) return false;
      if (mode === "chart") {
        const e = isObj(extra) ? extra : {};
        return accept({kind: "chart", graph: input, marks: isObj(e.marks) ? e.marks : undefined, ring: typeof e.ring === "string" && e.ring !== "" ? e.ring : undefined}, true);
      }
      if (!serves(hostHave, wants())) {          // the owner asked for more than this host fetched: ask for it, and keep asking on each update
        refresh(true);
        return false;
      }
      return accept({kind: "graph", raw: input, have: hostHave}, true);
    }

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      fetchSeq += 1;
      timers.forEach(timer => root.clearTimeout(timer));
      timers.clear();
      if (resizer) resizer.disconnect();
      pointers.clear();
      host.innerHTML = "";
    }

    setLive("offline");
    syncControls();
    return {
      el: rootEl, update, select, fit, setView, setLive, destroy, noteMessage, markSeen,
      refresh: () => refresh(true),
      fail: err => { if (!destroyed) showBanner(err); },
      state: () => ({
        mode, level, scope, view, selected, hot: hotId(), live: liveState, zoom: {k: t.k, x: t.x, y: t.y}, touched,
        ids: shown ? shown.layout.nodes.map(n => n.id) : [], warnings: shown ? shown.warnings.slice() : [],
      }),
    };
  }

  const helpers = {narrow, serves, inOverview, zoomAbout, homeOf, bringIntoView, sentenceOf, legendHtml, MIN_SCALE, MAX_SCALE, CLICK_DISTANCE, FRESH_MS, BIG_GRAPH};
  const GraphView = {create, helpers};
  if (typeof module === "object" && module !== null && module.exports) module.exports = GraphView;
  else root.GraphView = GraphView;
})(globalThis);
