/* fluid.js - the parts of the page that keep it fluid (gap package fluid; docs/notes/GAP3-fluid.md).

   A page feels choppy when one event makes the browser throw a whole list away and build it again, when a streamed chunk repaints a row 80 times a
   second, or when a drag sets an attribute for every pointer event. These are the small, separate cures. Each one is pure or takes the DOM it works on,
   so each one has a test; a page that does not have this script keeps working as it did (every caller checks for it).

     createFrames(options)        a batch of jobs per animation frame: schedule(key, fn) keeps the LAST fn of a key and runs it once, on the next frame,
                                  however many times it was scheduled (flush runs them now, cancel drops one). options {raf, caf}: the page's by
                                  default; without any requestAnimationFrame a job runs at once (node, a stub DOM), so nothing waits for a frame that
                                  never comes.
     frame(key, fn), flush(), cancel(key)    the page's one instance
     signature(value)             a cheap fingerprint of data (its JSON): "" when it cannot be had. changed(holder, key, value) says whether the
                                  fingerprint under holder[key] differs from the value's, and keeps the new one: a redraw of data that did not
                                  change is skipped.
     diffList(prev, next)         the minimal edit of a keyed list when only the ends change (a chat that gains lines at the bottom, loses one at
                                  the top): which kept items changed (replace), which stretch goes (remove) and what comes in (insert)
     patchList(container, items, options)   draws items [{key, html}] into container (one root element per html) by that edit, so the lines that did
                                  not change are not touched (no flicker, the scroll, the focus and a text selection stay) and only a new line
                                  is created (options.enter: a class it gets, unless this is the first drawing). Returns {changed, rebuilt, added}.
                                  A <details data-key> open in a replaced item stays open in its new one.
     splitStream(text)            a streamed reply as {blocks, tail, settled}: the blocks that are done (the next one has begun; a list, a quote or
                                  a table is never cut apart) and the tail that is still being written. A fence keeps its blank lines.
     streamParts(state)           what to do to a streaming row already drawn: {reset, add, tail}, from the settled text of the last drawing and the
                                  text now. Only the tail and the blocks that settled since are drawn again.
     paintStream(el, parts, options)   the DOM side of it: the streaming row of a chat, appended to as the text grows (see below).

   A classic script with ONE global, Fluid (see sutra_ctx.js for why); in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);

  function report(where, error) {
    if (typeof console !== "undefined" && console && typeof console.error === "function") console.error("Fluid: " + where + " failed", error);
  }

  /* ---------------------------------------------------------------- frames */
  function createFrames(options) {
    const o = isObj(options) ? options : {};
    const raf = typeof o.raf === "function" ? o.raf : cb => (typeof root.requestAnimationFrame === "function" ? root.requestAnimationFrame(cb) : null);
    const caf = typeof o.caf === "function" ? o.caf : id => { if (typeof root.cancelAnimationFrame === "function") root.cancelAnimationFrame(id); };
    const jobs = new Map();
    let handle = null;

    function run() {
      handle = null;
      const batch = Array.from(jobs.values());
      jobs.clear();
      batch.forEach(fn => {
        try { fn(); } catch (e) { report("a frame job", e); }
      });
    }

    function schedule(key, fn) {
      if (typeof fn !== "function") return false;
      jobs.set(key, fn);                               // a later fn of the same key replaces the earlier one: it is the newer picture
      if (handle === null) {
        const id = raf(run);
        if (id === null || id === undefined) { run(); return true; }       // no frames here: now
        handle = id;
      }
      return true;
    }

    function flush() {
      if (handle !== null) { caf(handle); handle = null; }
      run();
    }

    function cancel(key) {
      jobs.delete(key);
      if (jobs.size === 0 && handle !== null) { caf(handle); handle = null; }
    }

    return {schedule, flush, cancel, pending: () => jobs.size};
  }

  const frames = createFrames();
  const frame = (key, fn) => frames.schedule(key, fn);

  /* ---------------------------------------------------------------- signatures */
  function signature(value) {
    try {
      const s = JSON.stringify(value);
      return typeof s === "string" ? s : "";
    } catch (e) {
      return "";                                        // circular: it has no fingerprint, so it is never "the same"
    }
  }

  function changed(holder, key, value) {
    const now = signature(value);
    const same = now !== "" && holder[key] === now;
    holder[key] = now;
    return !same;
  }

  /* ---------------------------------------------------------------- a keyed list, edited */
  // prev and next are [{key, html}]. Items are paired from the front while their keys agree, then from the back; what is between is removed and
  // replaced. A chat that grows at the bottom is all front: nothing is removed, the new lines are inserted.
  function diffList(prev, next) {
    const a = Array.isArray(prev) ? prev : [];
    const b = Array.isArray(next) ? next : [];
    const max = Math.min(a.length, b.length);
    let head = 0;
    while (head < max && a[head].key === b[head].key) head += 1;
    let tail = 0;
    while (tail < max - head && a[a.length - 1 - tail].key === b[b.length - 1 - tail].key) tail += 1;
    const replace = [];                                 // by index in prev (the nodes that stay): the same place, new html
    for (let i = 0; i < head; i += 1) if (a[i].html !== b[i].html) replace.push({index: i, item: b[i]});
    for (let j = 0; j < tail; j += 1) {
      const from = a.length - tail + j;
      const to = b.length - tail + j;
      if (a[from].html !== b[to].html) replace.push({index: from, item: b[to]});
    }
    const removeFrom = head;
    const removeCount = a.length - tail - head;
    const insert = b.slice(head, b.length - tail);
    return {replace, removeFrom, removeCount, insert, touched: replace.length > 0 || removeCount > 0 || insert.length > 0};
  }

  const cssEscape = s => (root.CSS && typeof root.CSS.escape === "function" ? root.CSS.escape(s) : String(s).replace(/["\\]/g, "\\$&"));

  // The <details data-key> the reader had open in the node that goes stay open in the one that comes (the same rule as SutraCtx.paint).
  function keepOpen(from, to) {
    if (!from || !to || typeof from.querySelectorAll !== "function" || typeof to.querySelector !== "function") return;
    from.querySelectorAll("details[open][data-key]").forEach(d => {
      const same = to.querySelector('details[data-key="' + cssEscape(d.getAttribute("data-key")) + '"]');
      if (same) same.open = true;
    });
  }

  function patchList(container, items, options) {
    const o = isObj(options) ? options : {};
    const list = (Array.isArray(items) ? items : []).filter(it => isObj(it) && typeof it.html === "string" && it.html !== "");
    const doc = container.ownerDocument || root.document;
    const make = typeof o.make === "function" ? o.make : html => {
      const t = doc.createElement("template");
      t.innerHTML = html;
      return t.content.firstElementChild;
    };
    const nodeOf = item => {
      let node = make(item.html);
      if (!node) {                                      // an html with no element in it: a hidden placeholder keeps the list and the DOM in step
        node = doc.createElement("span");
        node.hidden = true;
      }
      node.__fkey = item.key;
      return node;
    };
    let nodes = Array.from(container.children);
    const known = container.__fluid;
    // the container still holds what this function drew (nothing else wrote into it since)? else start from nothing
    const intact = known !== undefined && known.items.length === nodes.length && nodes.every((n, i) => n.__fkey === known.items[i].key);
    const rebuilt = !intact;
    if (rebuilt) {
      if (nodes.length > 0 || container.firstChild) container.textContent = "";
      nodes = [];
    }
    const prev = intact ? known.items : [];
    const edit = diffList(prev, list);
    if (!edit.touched && !rebuilt) return {changed: false, rebuilt: false, added: 0};
    edit.replace.forEach(r => {
      const old = nodes[r.index];
      const node = nodeOf(r.item);
      keepOpen(old, node);
      container.replaceChild(node, old);
      nodes[r.index] = node;
    });
    nodes.splice(edit.removeFrom, edit.removeCount).forEach(n => container.removeChild(n));
    const anchor = nodes[edit.removeFrom] || null;      // the first node that stays after the stretch (null: the end)
    // a line that arrives enters; a whole history that is loaded at once (more than enterMax lines, default 6) does not: that is a page, not an arrival
    const enters = o.enter && prev.length > 0 && edit.insert.length <= (Number.isFinite(o.enterMax) ? o.enterMax : 6);
    const added = edit.insert.map(item => {
      const node = nodeOf(item);
      if (enters && node.classList) node.classList.add(o.enter);
      if (anchor) container.insertBefore(node, anchor);
      else container.appendChild(node);
      return node;
    });
    nodes.splice(edit.removeFrom, 0, ...added);
    container.__fluid = {items: list.slice()};
    return {changed: true, rebuilt, added: added.length};
  }

  /* ---------------------------------------------------------------- a streamed reply: blocks that are done and a tail that is not */
  // What a line says about the block it starts: a list item, an indented line, a quote or a table row continues the block before it when that one is
  // of the same kind (it began with such a line too), so a list that has a blank line between its items stays one list. A paragraph is a block of its own.
  const CONTINUES = /^(?:[ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]|[ \t]{2,}\S|[ \t]*>|[ \t]*\|)/;
  const FENCE_OPEN = /^[ \t]*(`{3,}|~{3,})(.*)$/;
  const FENCE_CLOSE = /^[ \t]*(`{3,}|~{3,})[ \t]*$/;
  const LONG_ENOUGH = 14;       // a first line this long can no longer turn into a list marker ("123456789. " is 11)
  const blank = line => line.trim() === "";

  function fenceMarker(line) {
    const m = FENCE_OPEN.exec(line);
    return m && !(m[1][0] === "`" && m[2].indexOf("`") >= 0) ? m[1] : "";
  }
  const closes = (line, marker) => {
    const m = FENCE_CLOSE.exec(line);
    return m !== null && m[1][0] === marker[0] && m[1].length >= marker.length;
  };

  // splitStream(text) -> {blocks: [string], tail: string, settled: number}. text starts at a block boundary (outside a fence). `settled` is the length
  // of the text the blocks cover, so blocks.join("") + tail === text. The last group is always the tail; so is the one before it while the last
  // one is only begun (its first line is short and unfinished: "-" may still become "- item", which would join it to the group before).
  function splitStream(value) {
    const text = typeof value === "string" ? value : "";
    const lines = text.split("\n");
    const groups = [];                                  // {from: offset, first: its first line, complete: bool}
    let offset = 0;
    let fence = "";
    let afterBlank = true;
    lines.forEach((line, i) => {
      const last = i === lines.length - 1;
      const start = offset;
      offset += line.length + (last ? 0 : 1);
      if (fence !== "") {
        if (closes(line, fence)) fence = "";
        return;
      }
      if (blank(line)) { afterBlank = true; return; }
      if (afterBlank) {
        const joins = groups.length > 0 && CONTINUES.test(line) && CONTINUES.test(groups[groups.length - 1].first);
        if (!joins) groups.push({from: start, first: line, complete: !last || line.length >= LONG_ENOUGH});
        afterBlank = false;
      }
      const marker = fenceMarker(line);
      if (marker !== "") fence = marker;
    });
    let keep = groups.length;                           // groups that stay (not the tail)
    if (keep > 0 && !groups[keep - 1].complete) keep -= 1;
    const settledGroups = Math.max(0, keep - 1);
    if (settledGroups === 0) return {blocks: [], tail: text, settled: 0};
    const blocks = [];
    let start = 0;
    for (let g = 0; g < settledGroups; g += 1) {
      blocks.push(text.slice(start, groups[g + 1].from));
      start = groups[g + 1].from;
    }
    return {blocks, tail: text.slice(start), settled: start};
  }

  // streamParts(settledText, text) -> {reset, add, tail, settledText}. `settledText` is what the row has already drawn as done blocks. When the text no
  // longer starts with it (a long reply shows only its last characters) the row starts again.
  function streamParts(drawn, value) {
    const text = typeof value === "string" ? value : "";
    const done = typeof drawn === "string" ? drawn : "";
    const reset = done !== "" && !text.startsWith(done);
    const base = reset ? "" : done;
    const split = splitStream(text.slice(base.length));
    return {reset, add: split.blocks, tail: split.tail, settledText: base + split.blocks.join("")};
  }

  const OPEN = '<div class="cmd">';
  const CLOSE = "</div>";
  // ChatMarkdown.render wraps a reply in <div class="cmd">: the row has ONE such wrapper, so a block goes in without its own.
  function inner(html) {
    return html.startsWith(OPEN) && html.endsWith(CLOSE) ? html.slice(OPEN.length, html.length - CLOSE.length) : html;
  }

  // paintStream(el, {who, text}, {render(text, {streaming}) -> html}): the streaming row of a chat inside `el`, or nothing when parts is null. The
  // first call writes the row, a later one with the same author only adds: blocks that settled go in once and stay, the tail is replaced. So a
  // streamed chunk touches the end of the row, not the row. Returns whether it touched the DOM.
  function paintStream(el, parts, options) {
    const o = isObj(options) ? options : {};
    if (!el) return false;
    let st = el.__stream;
    if (st && st.root.parentNode !== el) st = el.__stream = undefined;                 // somebody wrote into el since
    if (!isObj(parts)) {
      if (!st && el.firstChild === null) return false;
      el.textContent = "";
      el.__stream = undefined;
      return true;
    }
    const render = typeof o.render === "function" ? o.render : () => "";
    const who = typeof parts.who === "string" ? parts.who : "";
    const text = typeof parts.text === "string" ? parts.text : "";
    let touched = false;
    if (st === undefined || st.who !== who) {
      const esc = s => String(s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
      el.innerHTML = '<div class="cstream" role="status" aria-live="polite"><small>' + esc(who) + ' is writing\u2026</small><div class="cstream-text" hidden><div class="cmd"></div></div></div>';
      const rootEl = el.firstElementChild;
      st = el.__stream = {root: rootEl, wrap: rootEl.querySelector(".cstream-text"), cmd: rootEl.querySelector(".cmd"), who, settled: "", tail: "", tailNodes: 0};
      touched = true;
    }
    const plan = streamParts(st.settled, text);
    const cmd = st.cmd;
    const drop = n => { for (let i = 0; i < n && cmd.lastChild; i += 1) cmd.removeChild(cmd.lastChild); };
    const put = html => {
      if (html === "") return 0;
      const t = (cmd.ownerDocument || root.document).createElement("template");
      t.innerHTML = html;
      const n = t.content.childNodes.length;
      cmd.appendChild(t.content);
      return n;
    };
    if (plan.reset) { cmd.textContent = ""; st.tailNodes = 0; st.tail = ""; touched = true; }
    if (!touched && plan.add.length === 0 && plan.tail === st.tail) return false;          // the same picture
    drop(st.tailNodes);
    plan.add.forEach(block => put(inner(render(block, {streaming: false}))));
    st.tailNodes = put(inner(render(plan.tail, {streaming: true})));
    st.tail = plan.tail;
    st.settled = plan.settledText;
    st.wrap.hidden = cmd.firstChild === null;
    return true;
  }

  const Fluid = {createFrames, frame, flush: () => frames.flush(), cancel: key => frames.cancel(key), pending: () => frames.pending(),
    signature, changed, diffList, patchList, splitStream, streamParts, paintStream};
  if (typeof module === "object" && module !== null && module.exports) module.exports = Fluid;
  else root.Fluid = Fluid;
})(globalThis);
