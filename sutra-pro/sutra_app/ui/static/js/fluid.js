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
     paintText(el, text, options)      the same append-only drawing for ONE text block of the live chat (STR-10), without the "is writing" header: blocks that settled
                                  stay as DOM that is never written again, only the tail is drawn again, and a code fence that is still open is ONE <pre> whose
                                  text grows (never recreated while it streams, and kept as it is when it settles). options {render, streaming, highlight}:
                                  highlight(pre) is called once for a fence that settled, never while it streams.

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
  // What a line says about the block it starts: a list item, an indented line (any indent: ChatMarkdown's list takes one space or a tab as a
  // continuation too), a quote or a table row continues the block before it when that one is OPEN, that is, when ANY of its lines was such a line (a
  // list may begin in the middle of a group: "Steps:\n1. one" is one group whose list goes on after a blank line), so a list that has a blank line
  // between its items stays one list. Joining too much only makes a bigger block; joining too little draws a list in two pieces while it streams.
  // A paragraph is a block of its own.
  const CONTINUES = /^(?:[ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]|[ \t]+\S|[ \t]*>|[ \t]*\|)/;
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
    const groups = [];                                  // {from: offset, open: a line of it can be continued, complete: its first line is finished}
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
        const joins = groups.length > 0 && CONTINUES.test(line) && groups[groups.length - 1].open;
        if (!joins) groups.push({from: start, open: false, complete: !last || line.length >= LONG_ENOUGH});
        afterBlank = false;
      }
      if (CONTINUES.test(line)) groups[groups.length - 1].open = true;
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


  /* ---------------------------------------------------------------- one text block of the live chat: settled blocks stay, the tail is drawn again */
  // The tail as segments: text between fences, and each fence (open or closed) as {kind: "fence", opener, marker, body, closed}. The fences become ONE <pre> each whose text grows;
  // the text segments are drawn by `render`. A fence that is still open runs to the end of the tail.
  function segmentsOf(tail) {
    const lines = tail.split("\n");
    const segs = [];
    let text = "";
    let textStart = 0;
    let offset = 0;
    let open = null;
    const flush = at => { if (text !== "") { segs.push({kind: "text", text, start: textStart, end: at}); text = ""; } };
    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];
      const end = Math.min(tail.length, offset + line.length + 1);
      if (open !== null) {
        if (closes(line, open.marker)) {
          segs.push({kind: "fence", opener: open.opener, marker: open.marker, body: tail.slice(open.bodyStart, Math.max(open.bodyStart, offset - 1)), closed: true, start: open.start, end});
          open = null;
        }
      } else {
        const marker = fenceMarker(line);
        if (marker !== "") { flush(offset); open = {marker, opener: line, bodyStart: offset + line.length + 1, start: offset}; } else {
          if (text === "") textStart = offset;
          text += line + (i === lines.length - 1 ? "" : "\n");
        }
      }
      offset += line.length + 1;
    }
    if (open !== null) {
      // a last line of one or two fence characters is the closing line being typed: it is not code (and would not be there when the block settles)
      const partial = new RegExp("(^|\\n)[ \\t]*" + (open.marker[0] === "`" ? "`" : "~") + "{1,2}$");
      segs.push({kind: "fence", opener: open.opener, marker: open.marker, body: tail.slice(open.bodyStart).replace(partial, ""), closed: false, start: open.start, end: tail.length});
    }
    flush(tail.length);
    return segs;
  }

  const squash = t => t.split("\n").map(l => l.replace(/^[ \t]+/, "")).join("\n").replace(/\s+$/, "");
  // the code that streamed (`a`) is the beginning of, or the same as, the code of the settled block (`b`): a settle can arrive in the same piece as the last lines of the fence
  const sameCode = (a, b) => squash(b).startsWith(squash(a));

  function paintText(el, value, options) {
    const o = isObj(options) ? options : {};
    if (!el) return false;
    const render = typeof o.render === "function" ? o.render : () => "";
    const streaming = o.streaming !== false;
    const text = typeof value === "string" ? value : "";
    const doc = el.ownerDocument || root.document;
    let st = el.__txt;
    if (st && st.cmd.parentNode !== el) st = el.__txt = undefined;                       // somebody wrote into el since
    if (text === "") {
      if (!st) return false;
      st.cmd.textContent = "";
      st.settled = ""; st.tail = ""; st.segs = []; st.tailStreaming = true;
      return true;
    }
    let touched = false;
    if (!st) {
      const cmd = doc.createElement("div");
      cmd.className = "cmd";
      el.textContent = "";
      el.appendChild(cmd);
      st = el.__txt = {cmd, settled: "", tail: "", tailStreaming: true, segs: []};
      touched = true;
    }
    const cmd = st.cmd;
    const plan = streamParts(st.settled, text);
    if (plan.reset) { cmd.textContent = ""; st.segs = []; st.tail = ""; st.settled = ""; touched = true; }
    let add = plan.add;
    let tail = plan.tail;
    if (!streaming && tail !== "") { add = add.concat([tail]); tail = ""; }             // the turn is over: the tail is a block like the others
    if (!touched && add.length === 0 && tail === st.tail && st.tailStreaming === streaming) return false;       // the same picture
    const fragment = html => {
      if (html === "") return null;
      const t = doc.createElement("template");
      t.innerHTML = html;
      return t.content;
    };
    const mark = pre => { if (typeof o.highlight === "function" && pre && !pre.__lit) { pre.__lit = true; try { o.highlight(pre); } catch (e) { report("highlight", e); } } };
    const nodesOf = f => (f === null ? [] : Array.from(f.childNodes));
    const drop = seg => { seg.nodes.forEach(n => { if (n.parentNode === cmd) cmd.removeChild(n); }); };
    const place = (f, anchor) => { if (f !== null) cmd.insertBefore(f, anchor || null); };

    // 1. blocks that settled: drawn once, final, in front of what stays in the tail. A <pre> that streamed in the tail is the node that stays when its block settles (same code), and
    // is highlighted now. A segment of the old tail that lies after the settled text is the tail still (a fence that went on, a paragraph that was begun) and is not touched.
    let kept = st.segs;
    if (add.length > 0) {
      const consumed = add.join("").length;
      const gone = st.segs.filter(sg => sg.start < consumed);
      const fences = gone.filter(sg => sg.kind === "fence").map(sg => sg.node);
      gone.forEach(drop);
      kept = st.segs.filter(sg => sg.start >= consumed);
      kept.forEach(sg => { sg.start -= consumed; sg.end -= consumed; });
      const anchor = (kept.find(sg => sg.nodes.length > 0) || {nodes: []}).nodes[0] || null;
      add.forEach(block => {
        const f = fragment(inner(render(block, {streaming: false})));
        if (f === null) return;
        Array.from(f.childNodes).forEach(n => {
          if (n.tagName !== "PRE") return;
          const at = fences.findIndex(k => sameCode(k.textContent, n.textContent));
          let node = n;
          if (at >= 0) {
            node = fences.splice(at, 1)[0];
            const code = node.querySelector("code") || node;
            if (code.textContent !== n.textContent) code.textContent = n.textContent;           // the final text has its indent and trailing blank lines settled
            f.replaceChild(node, n);
          }
          mark(node);
        });
        place(f, anchor);
      });
      st.segs = kept;
    }

    // 2. the tail: segments, reconciled with what is drawn: a text segment is drawn again when it changed, a fence only grows its text, and nothing after the first difference is kept
    const next = tail === "" ? [] : (streaming ? segmentsOf(tail) : [{kind: "text", text: tail, start: 0, end: tail.length}]);
    const old = st.segs;
    let i = 0;
    while (i < old.length && i < next.length && old[i].kind === next[i].kind) {
      const a = old[i];
      const b = next[i];
      if (a.kind === "fence") {
        // the opener line may still be typed ("```py", then "```python"): the <pre> does not depend on it, so it is the same node
        if (a.body !== b.body) { a.code.textContent = b.body; a.body = b.body; }
        a.opener = b.opener;
        a.marker = b.marker;
        a.closed = b.closed;
        a.start = b.start;
        a.end = b.end;
      } else if (a.text !== b.text || a.streaming !== streaming) {
        const later = old.slice(i + 1).find(sg => sg.nodes.length > 0);
        drop(a);
        const f = b.text.trim() === "" ? null : fragment(inner(render(b.text, {streaming})));
        a.nodes = nodesOf(f);
        place(f, later ? later.nodes[0] : null);
        a.text = b.text;
        a.streaming = streaming;
      }
      a.start = b.start;
      a.end = b.end;
      i += 1;
    }
    old.slice(i).forEach(drop);
    old.length = i;
    next.slice(i).forEach(b => {
      if (b.kind === "fence") {
        const f = fragment(inner(render(b.opener + "\n" + b.marker, {streaming: true})));         // an empty fence: the skeleton of the <pre>, which the text then fills
        const pre = f && f.childNodes.length === 1 && f.firstChild.tagName === "PRE" ? f.firstChild : null;
        if (pre) {
          const code = pre.querySelector("code") || pre;
          code.textContent = b.body;
          cmd.appendChild(pre);
          old.push({kind: "fence", opener: b.opener, marker: b.marker, body: b.body, closed: b.closed, node: pre, code, nodes: [pre], start: b.start, end: b.end});
          return;
        }
        const g = fragment(inner(render(b.opener + "\n" + b.body + (b.closed ? "\n" + b.marker : ""), {streaming: true})));
        const ns = nodesOf(g);
        place(g, null);
        old.push({kind: "text", text: b.opener + "\n" + b.body, streaming, nodes: ns, start: b.start, end: b.end});
        return;
      }
      const f = b.text.trim() === "" ? null : fragment(inner(render(b.text, {streaming})));
      const ns = nodesOf(f);
      place(f, null);
      old.push({kind: "text", text: b.text, streaming, nodes: ns, start: b.start, end: b.end});
    });
    st.tail = tail;
    st.tailStreaming = streaming;
    st.settled = plan.settledText + (add.length > plan.add.length ? plan.tail : "");
    return true;
  }

  const Fluid = {createFrames, frame, flush: () => frames.flush(), cancel: key => frames.cancel(key), pending: () => frames.pending(),
    signature, changed, diffList, patchList, splitStream, streamParts, paintStream, paintText, segmentsOf};
  if (typeof module === "object" && module !== null && module.exports) module.exports = Fluid;
  else root.Fluid = Fluid;
})(globalThis);
