/* graph_render.js - the pure core of the Workflow graph and Org chart views, part 2 of 3 (work package UI-4; docs/design/ui.md sections
   6.1, 7 and 10; S3-web-13, S4-fnodes-10).

   Strings in, strings out: svg() draws a layout (graph_layout.js) as an SVG string, outline() draws the same graph as a nested list for
   phones and keyboards, summary() counts it for the header pills, and the status look, the status words, the personas and the function
   chip text live here so every view says the same thing. Nothing touches the DOM, and every word that came from the wire is escaped.

   The markup follows section 3.3: svg.wgsvg[data-w][data-h] > g.wview > g.wedges (path.wedge.e-<kind>[data-edge][data-from][data-to])
   and g.wnodes > g.wnode.k-<kind>.st-<status>[data-id][tabindex][role=button], with rect.shape, text.tlab, text.tsub, circle.wbadge and
   circle.wunread inside. Colours are CSS variables with J2's tokens (--ink, --muted, --line, --ok, --bad, --validator, --e-reads,
   --e-makes, --e-fix) plus --accent and --e-org, so the three themes need no code here; they are also attributes, so a style sheet can
   override them.

   A classic script with ONE global, GraphRender (see sutra_ctx.js for why); in node it is module.exports. outline() and summary() need
   graph_layout.js (forest()); it is read when they are called, so the load order of the two files does not matter. */
(function (root) {
  "use strict";

  const freeze = Object.freeze;

  function layoutModule() {
    let found = root.GraphLayout;
    if (!found && typeof require === "function") found = require("./graph_layout.js");
    if (!found) throw new Error("GraphRender needs GraphLayout: load graph_layout.js before calling outline or summary");
    return found;
  }

  /* ---------------------------------------------------------------- small helpers */
  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const finite = Number.isFinite;                 // true only for a number that is not NaN or infinite (it does not convert)
  const text = v => (typeof v === "string" ? v : (finite(v) ? String(v) : ""));
  const round1 = n => Math.round(n * 10) / 10;
  const num = n => String(round1(n));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  // Words from the wire on one line: control characters and runs of white space become one space.
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const count = v => (finite(v) ? Math.max(0, Math.floor(v)) : 0);
  const group = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  // "1 call", "12 calls", "9,120 tokens": the number grouped by thousands, the unit singular for exactly one.
  const unit = (n, one, many) => group(n) + " " + (n === 1 ? one : many);
  const DOT = " \u00b7 ";
  const ELLIPSIS = "\u2026";

  // Does `coll` (an array of ids, a Set, or an object of id -> truthy) name `id`? (Not `instanceof Set`: a Set from another realm fails it.)
  function has(coll, id) {
    if (Array.isArray(coll)) return coll.includes(id);
    if (!isObj(coll)) return false;
    if (typeof coll.has === "function") return coll.has(id) === true;
    return hasOwn(coll, id) && Boolean(coll[id]);
  }

  /* ---------------------------------------------------------------- words */
  // The persona of each function: a UI constant copied from J2 (MAPLABEL.persona, j2_ui.html:1590).
  const PERSONA = freeze({identity: "Client Lead", adaptation: "Strategist", priority: "Prioritiser", coordination: "Scheduler", audit: "Quality Reviewer"});
  const KIND_WORDS = freeze({root: "root", department: "team", division: "division", function: "function", step: "step"});
  // J2's MAPW (function nodes) and MAPS (the rest), j2_ui.html:1598-1599; a function that is waiting names who it waits on.
  const FUNCTION_WORDS = freeze({filed: "filed and checked", done_unchecked: "done \u00b7 checks did not pass", running: "running now",
    left_open: "left open", waiting_on_you: "waiting on you", not_made: "not made", fault: "blocked", idle: "idle"});
  const OTHER_WORDS = freeze({filed: "filed", done_unchecked: "done \u00b7 checks did not pass", running: "running now", left_open: "left open",
    waiting: "waiting", waiting_on_you: "waiting on you", fault: "fault", not_made: "not made", idle: ""});

  // The word for a kind of node. An unknown kind is a step.
  function kindWord(kind) {
    return hasOwn(KIND_WORDS, kind) ? KIND_WORDS[kind] : KIND_WORDS.step;
  }

  // Who a function waits on: "you", a function's persona, or whatever else the server named (a builder id).
  function whoWord(waitOn) {
    if (typeof waitOn === "string" && hasOwn(PERSONA, waitOn)) return PERSONA[waitOn];
    return clean(waitOn) || "someone";
  }

  // statusWord(status, kind, waitOn) -> the words under a node, J2's mapState. An unknown status is idle; for a function node that
  // is waiting, `waitOn` (meta.wait_on) says for whom.
  function statusWord(status, kind, waitOn) {
    const known = hasOwn(OTHER_WORDS, status) ? status : "idle";
    if (kind !== "function") return OTHER_WORDS[known];
    return known === "waiting" ? "waiting on " + whoWord(waitOn) : FUNCTION_WORDS[known];
  }

  /* ---------------------------------------------------------------- the status look (J2's mapLook and mapBadge, j2_ui.html:1607-1618) */
  const PANEL = "var(--panel)";
  const AMBER = "var(--validator)";
  const makeLook = (stroke, width, fill, dash, badge, ring) =>
    freeze({stroke, width, fill, dash, badge, badgeFill: badge === "!" ? "var(--bad)" : AMBER, ring});
  // One colour means one thing everywhere: green filed and checked, amber waiting, red fault, grey everything else.
  const LOOKS = freeze({
    idle: makeLook("var(--line)", 1.5, PANEL, "", "", false),
    running: makeLook("var(--muted)", 1.5, PANEL, "", "", true),                 // a double ring
    waiting: makeLook(AMBER, 4, PANEL, "", "?", false),
    waiting_on_you: makeLook(AMBER, 4, PANEL, "", "?", false),
    fault: makeLook("var(--bad)", 4, PANEL, "", "!", false),
    filed: makeLook("var(--ok)", 1.5, "color-mix(in srgb, var(--ok) 14%, var(--panel))", "", "", false),
    done_unchecked: makeLook(AMBER, 4, PANEL, "2 3", "", false),                 // thick amber, dotted
    left_open: makeLook("var(--muted)", 1.5, PANEL, "6 4", "", false),           // dashed
    not_made: makeLook("var(--line)", 1.5, "none", "", "", false),               // hollow
  });

  // statusLook(status) -> {status, stroke, width, fill, dash, badge, badgeFill, ring, warning}. `status` is the word the look belongs
  // to: an unknown word (or none) is idle, and `warning` says so ("" for a known word). `dash` is a stroke-dasharray value ("" for a
  // solid line), `badge` the mark in the corner ("!", "?" or ""), `ring` true for the double ring of a running node.
  function statusLook(status) {
    const known = hasOwn(LOOKS, status);
    const word = known ? status : "idle";
    return Object.assign({status: word}, LOOKS[word], {warning: known ? "" : "unknown status " + JSON.stringify(text(status)) + ", drawn as idle"});
  }

  /* ---------------------------------------------------------------- the chip */
  // The key of a function node: the wire `fn`, else its label, else the end of its id ("web.identity").
  function functionKey(n) {
    const id = text(n.id);
    const tail = id.slice(id.lastIndexOf(".") + 1);
    const found = [n.fn, clean(n.label).toLowerCase(), tail].find(k => typeof k === "string" && hasOwn(PERSONA, k));
    return found === undefined ? "" : found;
  }

  function secondsText(s) {
    const secs = finite(s) ? Math.max(0, s) : 0;
    return secs < 10 ? String(round1(secs)) : group(secs);
  }

  // chipText(node) -> {line1, line2, tip}: what a box says.
  //   function    line1 the persona ("Client Lead"); line2 "<Function> . <open> open . <closed> closed", just the function name when the
  //               node has no atoms; tip "12 calls . 41 s . 9,120 tokens" and " . 1 failed" when an atom failed (S4-fnodes-10).
  //               The numbers are meta.stats.atoms_open, atoms_closed, atoms_failed, atoms_total, calls, seconds, tokens_in and
  //               tokens_out; a missing one is 0.
  //   department, division   the label, then the detail     step   the label, then the detail or else the step_ref     root   the label
  function chipText(node) {
    const n = isObj(node) ? node : {};
    const label = clean(n.label) || clean(n.id);
    if (n.kind === "function") {
      const stats = isObj(n.meta) && isObj(n.meta.stats) ? n.meta.stats : {};
      const key = functionKey(n);
      const failed = count(stats.atoms_failed);
      const tip = [unit(count(stats.calls), "call", "calls"), secondsText(stats.seconds) + " s",
        unit(count(stats.tokens_in) + count(stats.tokens_out), "token", "tokens")];
      if (failed > 0) tip.push(failed + " failed");
      return {
        line1: key === "" ? label : PERSONA[key],
        line2: count(stats.atoms_total) > 0 ? label + DOT + count(stats.atoms_open) + " open" + DOT + count(stats.atoms_closed) + " closed" : label,
        tip: tip.join(DOT),
      };
    }
    const detail = clean(n.detail);
    const line2 = n.kind === "root" ? "" : (n.kind === "step" ? detail || clean(n.step_ref) : detail);
    return {line1: label, line2, tip: [label, line2].filter(Boolean).join(DOT)};
  }

  /* ---------------------------------------------------------------- svg */
  // How each kind of link looks. `tone` is the colour family (J2's reads, makes and fix, plus org for the tree), `dotted` the line style.
  const EDGE_LOOKS = freeze({
    handoff: freeze({tone: "makes", verb: "hands to", dotted: false}),
    depends_on: freeze({tone: "reads", verb: "reads", dotted: false}),
    speaks_to: freeze({tone: "reads", verb: "speaks to", dotted: true}),
    step: freeze({tone: "reads", verb: "leads to", dotted: false}),
  });
  const TREE_LOOK = freeze({kind: "org", tone: "org", dotted: false});
  const TONES = freeze(["org", "reads", "makes", "fix"]);
  const toneColor = tone => (tone === "org" ? "var(--e-org, var(--edge))" : "var(--e-" + tone + ")");
  const MARK_WORDS = freeze({add: "added", move: "moved"});
  const MARKS = freeze(["add", "move", "reuse"]);
  const FALLBACK_SIZE = freeze({w: 140, h: 40});

  // The arrowhead of J2's edges (j2_ui.html:2000): rounded, about 6 px.
  const ARROW = "M1.4 1.4 L7.2 4 L1.4 6.6 Q2.4 4 1.4 1.4 Z";
  const LABEL_SIZE = 13;          // the font sizes of a box's two lines (J2's .tlab and .tsub)
  const SUB_SIZE = 11;
  const TEXT_MARGIN = 4;          // room kept free at each side of a box

  /* ---------------------------------------------------------------- text width (there is no DOM here to measure with) */
  // The advance of each printable ASCII character in 1/1000 em, space first: Arial's (Helvetica's) metrics, which the page's font
  // stack falls back to. 95 values, from the space (32) to the tilde (126).
  const ASCII_WIDTHS = freeze([
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,          // space ! " # $ % & ' ( ) * + , - . /
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,          // 0 to 9 : ; < = > ?
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,         // @ A to O
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,          // P to Z [ \ ] ^ _
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,          // ` a to o
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,               // p to z { | } ~
  ]);
  const MIDDLE_DOT = 0xb7;        // 333, the separator of the chip's second line
  const ELLIPSIS_CODE = 0x2026;   // 1000
  const WIDE_FROM = 0x2e80;       // from here (CJK, emoji, ...) a character is about one em wide; any other one counts as an n

  function charWidth(code) {
    if (code >= 32 && code <= 126) return ASCII_WIDTHS[code - 32];
    if (code === MIDDLE_DOT) return 333;
    if (code === ELLIPSIS_CODE) return 1000;
    return code >= WIDE_FROM ? 1000 : 556;
  }

  // textWidth(str, size) -> the width in px of `str` set at `size` px (an estimate, to the pixel at best). Counts code points; a text
  // that is not a string is "" (a finite number is its digits) and a size that is not a number is 0.
  function textWidth(str, size) {
    let units = 0;
    for (const ch of text(str)) units += charWidth(ch.codePointAt(0));
    return units * (finite(size) ? size : 0) / 1000;
  }

  // fit(str, width, size) -> `str` itself when it fits a box `width` px wide at `size` px, else the longest start of it that leaves room
  // for an ellipsis at the end (the whole text then goes in the tooltip). A width that is not a number is no room at all.
  function fit(str, width, size) {
    const words = text(str);
    const room = finite(width) ? Math.max(0, width - 2 * TEXT_MARGIN) : 0;
    if (textWidth(words, size) <= room) return words;
    const dots = textWidth(ELLIPSIS, size);
    let used = 0;
    let kept = "";
    for (const ch of words) {
      const next = used + textWidth(ch, size);
      if (next + dots > room) break;
      used = next;
      kept += ch;
    }
    return kept.trimEnd() + ELLIPSIS;
  }

  const still = v => (finite(v) ? v : 0);         // a coordinate that is no number counts as 0

  // A short stable name for a drawing (FNV-1a over its shape), so that two drawings on one page get different marker and gradient ids
  // unless the caller names them.
  function fingerprint(parts) {
    let h = 0x811c9dc5;
    JSON.stringify(parts).split("").forEach(ch => {
      h = Math.imul(h ^ ch.charCodeAt(0), 0x01000193) >>> 0;
    });
    return "d" + h.toString(16).padStart(8, "0");
  }

  // The look of a link of this kind. An unknown kind is a plain blue link (the same as `step`); depends_on labelled "revises" is terracotta.
  function edgeLook(kind, label) {
    const known = hasOwn(EDGE_LOOKS, kind) ? kind : "step";
    const base = EDGE_LOOKS[known];
    const revises = known === "depends_on" && text(label).trim().toLowerCase() === "revises";
    return {kind: known, tone: revises ? "fix" : base.tone, verb: revises ? "revises" : base.verb, dotted: base.dotted};
  }

  // The mark of an org chart node (ChartMarks.marks), or null.
  function markOf(marks, id) {
    const m = isObj(marks) && hasOwn(marks, id) && isObj(marks[id]) ? marks[id] : {};
    return MARKS.includes(m.mark) && {mark: m.mark, tag: clean(m.tag)};          // false when there is no mark
  }

  // svg(layout, view) -> the html of the whole <svg>.
  //   layout  GraphLayout.layout's answer.
  //   view    {selected, hot, marks, unread, fresh, ring, uid, title, action}, all optional:
  //     selected  an id: that node gets .sel
  //     hot       an id, the node under the pointer or focus: it and the links at it light up (.hot, and svg.ehot), the nodes beside it
  //               get .near and the rest fade (.dim)
  //     marks     ChartMarks.marks' answer: .mk-add (dashed, tinted) and .mk-move (2.4 px) in --accent with the word "added" or "moved"
  //               above the box, and .mk-reuse (plain); the tag goes in the tooltip and the aria-label
  //     unread    ids (an array, a Set or an object map) that get a dot        fresh  ids that get .wnew (just added)
  //     ring      an id that gets a ring (the team being viewed)
  //     uid       keeps the ids of arrowheads and gradients apart when two graphs share a page (letters, digits, - and _; default a
  //               fingerprint of the drawing, so that two different drawings never share an id)
  //     title     the aria-label of the picture (default "Graph")
  //     action    the end of each node's aria-label (default "Open chat.", for the root "Go to the org chat.")
  // The picture has no viewBox: its size is data-w by data-h in its own pixels (width and height say the same), so a view can zoom the
  // g.wview group and fit it to the box it lives in.
  function svg(layout, view) {
    const v = isObj(view) ? view : {};
    const L = isObj(layout) ? layout : {};
    const list = key => (Array.isArray(L[key]) ? L[key].filter(isObj) : []);
    const nodes = list("nodes");
    const links = list("links");
    const edges = list("edges");
    const width = finite(L.width) ? L.width : 0;
    const height = finite(L.height) ? L.height : 0;
    const uid = typeof v.uid === "string" && /^[A-Za-z0-9_-]{1,40}$/.test(v.uid) ? v.uid
      : fingerprint([width, height, nodes.map(n => [text(n.id), still(n.x), still(n.y), still(n.w), still(n.h)]), links.map(e => text(e.d)), edges.map(e => [text(e.kind), text(e.d)])]);
    const hot = typeof v.hot === "string" && nodes.some(n => n.id === v.hot) ? v.hot : "";

    // who is next to the hot node, so that the rest can fade
    const near = new Set();
    links.concat(edges).forEach(e => {
      if (e.from === hot) near.add(e.to);
      if (e.to === hot) near.add(e.from);
    });
    const nameOf = new Map(nodes.map(n => [n.id, clean(n.label) || clean(n.id)]));

    // one link as a <path>: its classes, its stroke (a gradient from source to target when the layout gave both ends) and its arrowhead
    const tones = new Set();
    const gradients = [];
    const pathOf = (e, look, loop, extra, inner) => {
      const d = typeof e.d === "string" ? clean(e.d) : "";
      if (d === "") return "";
      tones.add(look.tone);
      let stroke = toneColor(look.tone);
      if (["x1", "y1", "x2", "y2"].every(k => finite(e[k]))) {
        const id = "eg-" + uid + "-" + (gradients.length + 1);
        gradients.push('<linearGradient id="' + id + '" gradientUnits="userSpaceOnUse" x1="' + num(e.x1) + '" y1="' + num(e.y1) + '" x2="' + num(e.x2) + '" y2="' + num(e.y2) +
          '"><stop offset="0" style="stop-color:' + toneColor(look.tone) + ';stop-opacity:.82"/><stop offset="1" style="stop-color:' + toneColor(look.tone) + '"/></linearGradient>');
        stroke = "url(#" + id + ")";
      }
      const classes = ["wedge", "e-" + look.kind, loop ? "loop" : "", hot === "" ? "" : (e.from === hot || e.to === hot ? "hot" : "dim")].filter(Boolean).join(" ");
      // J2's style sheet forces `stroke-dasharray: none` on every edge, so a dotted line is set inline, where !important wins
      const dots = look.dotted && !loop ? ' style="stroke-dasharray:1.5 4 !important"' : "";
      return '<path class="' + classes + '" data-edge="' + look.kind + '" data-tone="' + look.tone + '"' + extra + ' data-from="' + esc(e.from) + '" data-to="' + esc(e.to) +
        '" d="' + esc(d) + '" fill="none" stroke="' + stroke + '" marker-end="url(#ea-' + look.tone + "-" + uid + ')"' + dots + ">" + inner + "</path>";
    };

    const drawn = links.map(e => pathOf(e, TREE_LOOK, false, "", "")).filter(Boolean);
    edges.forEach(e => {
      const kind = text(e.kind);
      const look = edgeLook(kind, e.label);
      const label = clean(e.label);
      const counted = look.kind === "speaks_to" && label !== "";
      const said = !counted ? "" : " (" + (/^\d+$/.test(label) ? unit(Number(label), "message", "messages") : label) + ")";
      const title = (nameOf.get(e.from) || clean(e.from)) + " " + look.verb + " " + (nameOf.get(e.to) || clean(e.to)) + said;
      const path = pathOf(e, look, e.loop === true, kind === "" || look.kind === kind ? "" : ' data-kind="' + esc(kind) + '"', "<title>" + esc(title) + "</title>");
      if (path === "") return;
      drawn.push(path);
      if (counted && finite(e.lx) && finite(e.ly)) {
        drawn.push('<text class="wedgelab e-speaks_to" data-from="' + esc(e.from) + '" data-to="' + esc(e.to) + '" x="' + num(e.lx) + '" y="' + num(e.ly - 4) +
          '" text-anchor="middle" font-size="11" fill="var(--muted)" paint-order="stroke" stroke="var(--skyink, var(--bg))" stroke-width="5" stroke-linejoin="round">' + esc(label) + "</text>");
      }
    });

    const markers = TONES.filter(t => tones.has(t)).map(t => '<marker id="ea-' + t + "-" + uid + '" viewBox="0 0 8 8" refX="7.2" refY="4" markerWidth="6" markerHeight="6" ' +
      'markerUnits="userSpaceOnUse" orient="auto"><path class="earr e-' + t + '" d="' + ARROW + '" fill="' + toneColor(t) + '" stroke="' + toneColor(t) + '"/></marker>');
    const boxes = nodes.map(n => nodeSvg(n, v, hot, near));
    return '<svg xmlns="http://www.w3.org/2000/svg" class="wgsvg' + (hot === "" ? "" : " ehot") + '" data-w="' + num(width) + '" data-h="' + num(height) + '" width="' + num(width) + '" height="' + num(height) +
      '" role="group" aria-label="' + esc(clean(v.title) || "Graph") + '"><defs>' + markers.concat(gradients).join("") + '</defs><g class="wview"><g class="wedges">' + drawn.join("") +
      '</g><g class="wnodes">' + boxes.join("") + "</g></g></svg>";
  }

  // One node: a <g> with its box, words, badge and dot.
  function nodeSvg(n, v, hot, near) {
    const kind = hasOwn(KIND_WORDS, n.kind) ? n.kind : "step";
    const look = statusLook(n.status);
    const mark = markOf(v.marks, n.id);
    const chip = chipText(Object.assign({}, n, {kind}));
    const x = finite(n.x) ? n.x : 0;
    const y = finite(n.y) ? n.y : 0;
    const w = finite(n.w) ? n.w : FALLBACK_SIZE.w;
    const h = finite(n.h) ? n.h : FALLBACK_SIZE.h;
    const cx = x + w / 2;
    const cy = y + h / 2;

    const classes = ["wnode", "k-" + kind, "st-" + look.status];
    if (v.selected === n.id) classes.push("sel");
    if (hot !== "") classes.push(n.id === hot ? "hot" : (near.has(n.id) ? "near" : "dim"));
    if (has(v.fresh, n.id)) classes.push("wnew");
    if (v.ring === n.id) classes.push("cur");
    if (mark) classes.push("mk-" + mark.mark);

    // the box: the status look, which an org chart mark paints over
    let stroke = look.stroke;
    let strokeWidth = look.width;
    let fill = look.fill;
    let dash = look.dash;
    if (mark && mark.mark === "add") {
      stroke = "var(--accent)";
      strokeWidth = 1.8;
      dash = "5 3";
      fill = "color-mix(in srgb, var(--accent) 12%, var(--panel))";
    } else if (mark && mark.mark === "move") {
      stroke = "var(--accent)";
      strokeWidth = 2.4;
      dash = "";
    }
    const box = (cls, grow, radius, paint, dashed) => '<rect class="' + cls + '" x="' + num(x - grow) + '" y="' + num(y - grow) + '" width="' + num(w + 2 * grow) + '" height="' + num(h + 2 * grow) +
      '" rx="' + radius + '" fill="' + paint + '" stroke="' + stroke + '" stroke-width="' + strokeWidth + '"' + (dashed && dash !== "" ? ' stroke-dasharray="' + dash + '"' : "") + "/>";
    const current = v.ring === n.id ? '<rect class="wcur" x="' + num(x - 6) + '" y="' + num(y - 6) + '" width="' + num(w + 12) + '" height="' + num(h + 12) +
      '" rx="14" fill="none" stroke="var(--accent)" stroke-width="2"/>' : "";
    const shapes = current + (look.ring ? box("wring", 4, 12, "none", false) : "") + box("shape", 0, 8, fill, true);

    // a division wears the five-dot team glyph
    const glyph = kind === "division" ? [-16, -8, 0, 8, 16].map(dx => '<circle class="wdot" cx="' + num(cx + dx) + '" cy="' + num(y + 5) + '" r="2" fill="var(--muted)"/>').join("") : "";
    const two = chip.line2 !== "";
    const shown1 = fit(chip.line1, w, LABEL_SIZE);
    const shown2 = fit(chip.line2, w, SUB_SIZE);
    const lab = '<text class="tlab" x="' + num(cx) + '" y="' + num(two ? cy - 3 : cy + 4.5) + '" text-anchor="middle" font-size="' + LABEL_SIZE + '" fill="var(--ink)">' + esc(shown1) + "</text>";
    const sub = two ? '<text class="tsub" x="' + num(cx) + '" y="' + num(cy + 13) + '" text-anchor="middle" font-size="' + SUB_SIZE + '" fill="var(--muted)">' + esc(shown2) + "</text>" : "";
    const tag = mark && hasOwn(MARK_WORDS, mark.mark) ? '<text class="wtag" x="' + num(x + 2) + '" y="' + num(y - 5) + '" font-size="10" fill="var(--accent)">' + MARK_WORDS[mark.mark] + "</text>" : "";
    const badge = look.badge === "" ? "" : '<circle class="wbadge" cx="' + num(x + w - 2) + '" cy="' + num(y + 2) + '" r="8" fill="' + look.badgeFill + '"/><text class="wbadget" x="' + num(x + w - 2) +
      '" y="' + num(y + 6) + '" text-anchor="middle" font-size="12" font-weight="700" fill="var(--on)">' + look.badge + "</text>";
    const unread = has(v.unread, n.id) ? '<circle class="wunread" cx="' + num(x + 8) + '" cy="' + num(y + 8) + '" r="4" fill="var(--accent)"/>' : "";

    // "Identity, Client Lead, waiting on you. Open chat."
    const meta = isObj(n.meta) ? n.meta : {};
    const key = kind === "function" ? functionKey(n) : "";
    const name = clean(n.label) || clean(n.id);
    const role = key === "" ? kindWord(kind) : PERSONA[key];
    const spoken = [name, role.toLowerCase() === name.toLowerCase() ? "" : role, statusWord(look.status, kind, meta.wait_on)].filter(Boolean).join(", ");
    const aria = spoken + "." + (mark && mark.tag !== "" ? " " + mark.tag + "." : "") + " " + (clean(v.action) || (kind === "root" ? "Go to the org chat." : "Open chat."));
    // the tooltip: the chip's own, then the words in full when the box had to cut them, then the mark
    const full = [chip.line1, chip.line2].filter(Boolean).join(DOT);
    const cut = shown1 !== chip.line1 || shown2 !== chip.line2;
    const tooltip = [chip.tip, cut && chip.tip !== full ? full : "", mark ? mark.tag : ""].filter(Boolean).join("\n");

    return '<g class="' + classes.join(" ") + '" data-id="' + esc(n.id) + '" tabindex="0" role="button" aria-label="' + esc(aria) + '"' + (v.selected === n.id ? ' aria-current="true"' : "") + ">" +
      "<title>" + esc(tooltip) + "</title>" + shapes + glyph + lab + sub + tag + badge + unread + "</g>";
  }

  /* ---------------------------------------------------------------- outline and summary */
  // outline(graph, view) -> the html of a nested <ul role="tree">: the same graph as a list, for phones and keyboards. Every node is a
  // <button data-id> (the same click target as its box); the links other than the tree are not listed. view {selected, unread, fresh}.
  function outline(graph, view) {
    const v = isObj(view) ? view : {};
    const tree = layoutModule().forest(isObj(graph) ? graph.nodes : []);
    const byId = new Map(tree.nodes.map(n => [n.id, n]));
    const parts = ['<ul class="wtree" role="tree">'];
    const stack = [{ids: tree.roots, i: 0, level: 1}];
    while (stack.length) {
      const top = stack[stack.length - 1];
      if (top.i >= top.ids.length) {
        stack.pop();
        if (stack.length) parts.push("</ul></li>");
        continue;
      }
      const n = byId.get(top.ids[top.i++]);
      const kids = tree.children.get(n.id);
      const kind = hasOwn(KIND_WORDS, n.kind) ? n.kind : "step";
      const chip = chipText(Object.assign({}, n, {kind}));
      const look = statusLook(n.status);
      const word = statusWord(look.status, kind, (isObj(n.meta) ? n.meta : {}).wait_on);
      const classes = ["woitem", "k-" + kind, "st-" + look.status, v.selected === n.id ? "sel" : "", has(v.fresh, n.id) ? "wnew" : ""].filter(Boolean).join(" ");
      parts.push('<li class="' + classes + '" role="treeitem" aria-level="' + top.level + '"' + (kids.length ? ' aria-expanded="true"' : "") + '><button type="button" class="wobtn" data-id="' +
        esc(n.id) + '" aria-label="' + esc([chip.line1, chip.line2, word].filter(Boolean).join(", ")) + '"' + (v.selected === n.id ? ' aria-current="true"' : "") +
        '><span class="wolab">' + esc(chip.line1) + "</span>" + (chip.line2 === "" ? "" : '<span class="wosub">' + esc(chip.line2) + "</span>") +
        (word === "" ? "" : '<span class="wost">' + esc(word) + "</span>") + (has(v.unread, n.id) ? '<span class="wounread" title="Unread messages"></span>' : "") + "</button>");
      if (kids.length) {
        parts.push('<ul role="group">');
        stack.push({ids: kids, i: 0, level: top.level + 1});
      } else {
        parts.push("</li>");
      }
    }
    parts.push("</ul>");
    return parts.join("");
  }

  // summary(graph) -> {line, parts, waiting}: the header pills, for example "2 teams . 10 function nodes . 1 waiting on you".
  // Teams, divisions, function nodes and steps are listed when there are any (the root is not counted). `waiting` counts the nodes that
  // wait on the owner and have no such node above them, so a team and its Identity that ask the same question count once.
  function summary(graph) {
    const tree = layoutModule().forest(isObj(graph) ? graph.nodes : []);
    const byId = new Map(tree.nodes.map(n => [n.id, n]));
    const total = {department: 0, division: 0, function: 0, step: 0};
    const covered = new Map();                    // id -> does this node, or one above it, wait on the owner
    let waiting = 0;
    tree.order.forEach(id => {
      const n = byId.get(id);
      const kind = hasOwn(KIND_WORDS, n.kind) ? n.kind : "step";
      if (hasOwn(total, kind)) total[kind] += 1;                          // the root is not in the list
      const asks = n.status === "waiting_on_you";
      const above = covered.get(n.parent) === true;                       // (a root has no parent: null is not in the map)
      if (asks && !above) waiting += 1;
      covered.set(id, asks || above);
    });
    const parts = [];
    if (total.department > 0) parts.push(unit(total.department, "team", "teams"));
    if (total.division > 0) parts.push(unit(total.division, "division", "divisions"));
    if (total.function > 0) parts.push(unit(total.function, "function node", "function nodes"));
    if (total.step > 0) parts.push(unit(total.step, "step", "steps"));
    if (waiting > 0) parts.push(waiting + " waiting on you");
    return {line: parts.join(DOT), parts, waiting};
  }

  const GraphRender = {svg, outline, summary, statusLook, statusWord, PERSONA, kindWord, chipText, edgeLook, textWidth, fit};
  if (typeof module === "object" && module !== null && module.exports) module.exports = GraphRender;
  else root.GraphRender = GraphRender;
})(globalThis);
