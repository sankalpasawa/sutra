/* orgchart_view.js - the global org chart pane: the one tree, what the selected change did to it, and the change log (work package UI-5;
   docs/design/ui.md sections 3.3, 6.3, 7 and 9; S2-models-01, S3-web-04; D67, D75, UI-D7).

   The org chart is read-only: only the chat agent changes it (D67), so this view draws, marks and explains and never edits. The tree is
   drawn by GraphView in mode "chart" (the same layout, boxes, pan and zoom, List view, legend, live chip and banner as the Workflow
   graph); this file feeds it ChartMarks.toGraph(chart) and the marks of the selected change, writes the change log under it
   (ChartMarks.logHtml) and shows a small card for a clicked node.

     OrgChartView.create(host, {onOpen(node), onShow(node), dept}) -> handle
       onOpen  the card's Open chat: the host opens the node's chat panel (the id is the graph node's id: a chart node keeps its id, D44).
       onShow  the card's Show in graph: the host switches to the Workflow graph and selects the node. Without it there is no such button.
       dept    the team being viewed (default SutraCtx.dept): its box gets a ring.
     handle  {update(orgChart, changes), selectChange(seq), setFind(rows), setLive(state), refresh(), fail(err), destroy(), graphView, state(), el}

   update(orgChart, changes): orgChart is GET /api/chart, changes GET /api/chart/changes?limit=50 (ChartChangeOut[]; leaving it out keeps
   the ones in hand). The newest change is selected until the owner picks another (a click on its row, or selectChange(seq)); picking
   the newest again follows the newest once more. A change that was not applied (pending_approval, rejected, stale, failed) marks nothing.
   The card of a node has its name and purpose, Open team page (a team), Show in graph and Open chat. Esc closes it.
   refresh() asks GET /api/chart and GET /api/chart/changes itself (what Try again does).

   Gap package chart-insight: under the log, "Chart notes" (chart_notes.js; GET /api/chart/notes, read again when the chart changes or a minute has
   passed): teams that look alike, a node with no purpose, a team nobody uses, each name a button that opens its card. The card of a division also
   says where it sits ("Bakery site > Menu"). setFind(rows) keeps the boxes the rail's search found lit and fades the rest (team_find.js); null clears it.
   Both scripts are optional: without one, that part is simply not drawn.

   A classic script with ONE global, OrgChartView (see sutra_ctx.js for why); it needs graph_view.js, chart_marks.js and sutra_ctx.js
   loaded before it, and in node it is module.exports. */
(function (root) {
  "use strict";

  function need(name, file) {
    const found = root[name] || (typeof require === "function" ? require(file) : undefined);
    if (!found) throw new Error("OrgChartView needs " + name + ": load " + file.replace("./", "") + " before it");
    return found;
  }

  // A script this view can do without (chart_notes.js, team_find.js): the global when the page has it, else a require in node, else undefined.
  function optional(name, file) {
    if (root[name]) return root[name];
    try {
      return typeof require === "function" ? require(file) : undefined;
    } catch (e) {
      return undefined;
    }
  }

  const NOTES_EVERY_MS = 60000;
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const finite = Number.isFinite;
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ENTITIES[c]);
  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

  function safely(where, fn, arg) {
    try {
      return fn(arg);
    } catch (e) {
      if (typeof console !== "undefined" && console && typeof console.error === "function") console.error("OrgChartView: " + where + " failed", e);
      return undefined;
    }
  }

  function create(host, options) {
    if (!host || typeof host.appendChild !== "function") throw new TypeError("OrgChartView.create: host must be an element");
    const o = isObj(options) ? options : {};
    const GV = need("GraphView", "./graph_view.js");
    const CM = need("ChartMarks", "./chart_marks.js");
    const C = need("SutraCtx", "./sutra_ctx.js");
    const doc = host.ownerDocument || root.document;
    const dept = typeof o.dept === "string" && o.dept !== "" ? o.dept : (typeof C.dept === "string" ? C.dept : "");

    host.innerHTML = '<div class="ocpane"><div class="ocgraph"></div><section class="ocard" role="region" hidden></section><div class="oclog"></div>' +
      '<section class="ocnotes" aria-label="Chart notes" hidden></section><style class="ocfind"></style></div>';
    const paneEl = host.firstElementChild;
    const cardEl = paneEl.querySelector(".ocard");
    const logEl = paneEl.querySelector(".oclog");
    const notesEl = paneEl.querySelector(".ocnotes");
    const findEl = paneEl.querySelector("style.ocfind");

    // selectedSeq null: follow the newest change; notes, notesAt, notesVersion: the Chart notes and when they were read; find: the rows of the rail's search
    const state = {graph: null, changes: [], selectedSeq: null, cardId: "", marks: {}, notes: null, notesAt: 0, notesVersion: null, find: null};
    let destroyed = false;
    let fetchSeq = 0;
    let notesSeq = 0;
    let notesTimer = 0;

    const gv = GV.create(paneEl.querySelector(".ocgraph"), {mode: "chart", title: "Org chart", dept, onSelect: node => showCard(node), onRetry: () => refresh()});

    // the change selected now: the owner's pick while it is still in the log, else the newest (undefined for the helpers of chart_marks.js)
    const pickedSeq = () => (state.selectedSeq !== null && state.changes.some(c => c.seq === state.selectedSeq) ? state.selectedSeq : undefined);

    // the log is repainted whenever a change is picked; a row that had the focus gets it back
    function paintLog() {
      const active = doc.activeElement;
      const row = active && active.closest && logEl.contains(active) ? active.closest(".chgrow[data-change]") : null;
      const kept = row ? row.getAttribute("data-change") : null;
      C.paint(logEl, CM.logHtml(state.changes, pickedSeq()));
      if (kept !== null) {
        const again = Array.from(logEl.querySelectorAll(".chgrow[data-change]")).find(r => r.getAttribute("data-change") === kept);
        if (again && doc.activeElement !== again) again.focus({preventScroll: true});
      }
    }

    function paintCard() {
      const node = state.cardId !== "" && state.graph ? state.graph.nodes.find(n => n.id === state.cardId) : undefined;
      if (!node) {
        state.cardId = "";
        cardEl.hidden = true;
        C.paint(cardEl, "");
        return;
      }
      const mark = hasOwn(state.marks, node.id) ? state.marks[node.id] : null;
      const acts = [];
      if (node.kind === "department") acts.push('<a class="ocbtn" data-oc="team" href="/d/' + encodeURIComponent(node.id) + '/">Open team page</a>');
      if (typeof o.onShow === "function") acts.push('<button type="button" class="ocbtn" data-oc="show">Show in graph</button>');
      if (typeof o.onOpen === "function") acts.push('<button type="button" class="ocbtn" data-oc="chat">Open chat</button>');
      cardEl.setAttribute("aria-label", node.label);
      cardEl.hidden = false;
      const CN = optional("ChartNotes", "./chart_notes.js");
      const address = CN ? CN.addressOf(state.graph.nodes, node.id) : "";
      C.paint(cardEl, '<div class="ochead"><h4>' + esc(node.label) + '</h4><button type="button" class="occlose" data-oc="close" aria-label="Close">\u00d7</button></div>' +
        (address !== "" ? '<p class="ocaddr">' + esc(address) + "</p>" : "") + (node.detail !== "" ? '<p class="ocpurpose">' + esc(node.detail) + "</p>" : "") + (mark ? '<p class="octag">' + esc(mark.tag) + "</p>" : "") +
        '<div class="ocacts">' + acts.join("") + "</div>");
    }

    function showCard(node) {
      state.cardId = node.id;
      paintCard();
    }

    function draw() {
      state.marks = CM.marks(state.changes, pickedSeq());
      const ok = gv.update(state.graph, {marks: state.marks, ring: dept});
      paintLog();
      paintCard();
      applyFind();
      return ok;
    }

    // The Chart notes under the log. A team page loads chart_notes.js after this script (J2's page cannot list it), so a note that arrives first waits for it.
    function paintNotes(tries) {
      if (destroyed || !state.notes) return;
      const CN = optional("ChartNotes", "./chart_notes.js");
      if (!CN) {
        if (tries < 10 && typeof root.setTimeout === "function") notesTimer = root.setTimeout(() => paintNotes(tries + 1), 150);
        return;
      }
      const markup = CN.html(state.notes);
      notesEl.hidden = markup === "";
      C.paint(notesEl, markup);
    }

    // Read the notes when the chart has a new version or the last read is a minute old (a team goes quiet with time, not with a change). A failed read keeps what it had.
    function loadNotes(chart) {
      if (destroyed || !C.api || typeof C.api.get !== "function") return;
      const version = isObj(chart) ? chart.version : null;
      if (state.notes !== null && version === state.notesVersion && Date.now() - state.notesAt < NOTES_EVERY_MS) return;
      state.notesVersion = version;
      state.notesAt = Date.now();
      const mine = ++notesSeq;
      Promise.resolve().then(() => C.api.get("/api/chart/notes")).then(out => {
        if (destroyed || mine !== notesSeq || !isObj(out)) return;
        state.notes = out;
        paintNotes(0);
      }, () => { state.notesAt = 0; });
    }

    // setFind(rows): the rows of GET /api/find (team_find.js). Their boxes stay lit, the boxes above them stay in view, the rest fade. Nothing or null clears it.
    function applyFind() {
      const TF = optional("TeamFind", "./team_find.js");
      if (!TF || !state.find || !state.graph) {
        findEl.textContent = "";
        paneEl.removeAttribute("data-find");
        return;
      }
      const lit = TF.dimming(state.find, state.graph.nodes);
      const css = TF.dimCss(".ocpane[data-find]", lit.hits, lit.ancestors);
      findEl.textContent = css;
      if (css === "") paneEl.removeAttribute("data-find");
      else paneEl.setAttribute("data-find", "1");
    }

    function setFind(rows) {
      if (destroyed) return false;
      state.find = Array.isArray(rows) && rows.length > 0 ? rows : null;
      applyFind();
      return state.find !== null;
    }

    function update(chart, changes) {
      if (destroyed) return false;
      let graph;
      try {
        graph = CM.toGraph(chart);
      } catch (e) {
        gv.fail(e);                                    // the last good chart stays on the page, with the banner
        return false;
      }
      state.graph = graph;
      if (Array.isArray(changes)) state.changes = changes.filter(isObj);
      const ok = draw();
      loadNotes(chart);
      return ok;
    }

    function selectChange(seq) {
      const wanted = typeof seq === "string" && /^\d+$/.test(seq) ? Number(seq) : seq;
      const known = state.changes.filter(c => finite(c.seq)).map(c => c.seq);
      if (destroyed || !known.includes(wanted)) return false;
      state.selectedSeq = wanted === known.reduce((a, b) => Math.max(a, b)) ? null : wanted;
      if (state.graph) draw();
      return true;
    }

    function refresh() {
      if (destroyed) return Promise.resolve(false);
      const mine = ++fetchSeq;
      return Promise.all([C.api.get("/api/chart"), C.api.get("/api/chart/changes", {limit: 50})]).then(
        ([chart, changes]) => (destroyed || mine !== fetchSeq ? false : update(chart, changes)),
        err => {
          if (!destroyed && mine === fetchSeq) gv.fail(err);
          return false;
        });
    }

    logEl.addEventListener("click", e => {
      const row = e.target && e.target.closest ? e.target.closest(".chgrow[data-change]") : null;
      if (row) selectChange(Number(row.getAttribute("data-change")));
    });
    logEl.addEventListener("keydown", e => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const row = e.target && e.target.closest ? e.target.closest(".chgrow[data-change]") : null;
      if (!row) return;
      e.preventDefault();
      selectChange(Number(row.getAttribute("data-change")));
    });
    notesEl.addEventListener("click", e => {
      const button = e.target && e.target.closest ? e.target.closest("[data-note-node]") : null;
      const node = button && state.graph ? state.graph.nodes.find(n => n.id === button.getAttribute("data-note-node")) : undefined;
      if (node) showCard(node);
    });
    cardEl.addEventListener("click", e => {
      const button = e.target && e.target.closest ? e.target.closest("[data-oc]") : null;
      if (!button) return;
      const node = state.graph ? state.graph.nodes.find(n => n.id === state.cardId) : undefined;
      const act = button.getAttribute("data-oc");
      if (act === "close") {
        state.cardId = "";
        paintCard();
      } else if (node && act === "show") {
        safely("onShow", o.onShow, Object.assign({}, node));
      } else if (node && act === "chat") {
        safely("onOpen", o.onOpen, Object.assign({}, node));
      }
    });
    paneEl.addEventListener("keydown", e => {
      if (e.key !== "Escape" || cardEl.hidden) return;
      state.cardId = "";
      paintCard();
    });

    return {
      el: paneEl, graphView: gv, update, selectChange, refresh, setFind,
      setLive: s => gv.setLive(s),
      fail: err => gv.fail(err),
      state: () => ({selected: pickedSeq() === undefined ? null : pickedSeq(), card: state.cardId, changes: state.changes.map(c => c.seq), marks: Object.assign({}, state.marks)}),
      destroy() {
        if (destroyed) return;
        destroyed = true;
        fetchSeq += 1;
        notesSeq += 1;
        if (notesTimer && typeof root.clearTimeout === "function") root.clearTimeout(notesTimer);
        gv.destroy();
        host.innerHTML = "";
      },
    };
  }

  const OrgChartView = {create};
  if (typeof module === "object" && module !== null && module.exports) module.exports = OrgChartView;
  else root.OrgChartView = OrgChartView;
})(globalThis);
