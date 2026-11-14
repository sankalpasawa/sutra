/* chat_live_view.js - the reply of a direct chat turn as keyed blocks, live and settled by the SAME code (work package STR-10; streaming design D207, D212, D219;
   docs/design/streaming/architecture.md "Settle in place", "Block rendering with stable ids", "Activity timeline").

   One reply is ONE node in the transcript (a "shell", drawn by Fluid.patchList with a fixed html, so the list never replaces it). This file paints what is inside it from a
   MODEL, and the model comes from either side: a live turn (ChatLiveClient.view()) or a stored message (ChatMessageOut with its typed blocks, or just its text for a message
   that has none). The blocks are keyed: a node per block id, never recreated, patched when its block changes. When the stored message replaces the live turn the shell is the
   same node and the block ids carry over (turn.done's stored_order), so nothing is rebuilt: only the tail text block is drawn once more, as final.

     keyOf(turn, attempt)        "turn:<owner line>:<try>", the key of the shell, the same live and stored
     shellHtml(turn, attempt, {superseded})   the html of the shell: a constant of (turn, attempt), so the transcript list never replaces the node
     isReply(message)            a stored message that is the reply item of a turn (an agent text line with `turn`, or the note/error that carries the ended turn's blocks)
     fromLive(view, deps)        the model of a live turn, or null (no turn, or not accepted yet); deps {who}
     fromMessage(message, deps)  the model of a stored message; deps {ids (stored_order), who, canRetry}
     paint(shell, model, deps)   draw the model into the shell, touching only what changed. deps {render (ChatMarkdown.render), highlight, Fluid}
     supersede(messages)         the rows with `superseded` set on every try that a later try of the same owner line replaced (what the server reads, worked out again by a page that read the first try early)
     plan(messages, view, deps)  {models, liveItem}: the model of every reply item of the list, and the item of the live turn while no stored message has its key
     sync(host, models, deps)    paint every shell under `host`: models {key: model}
     copyText(shell)             the text of the reply in the shell (what Copy puts on the clipboard)
     copy(button, deps)          the Copy and Copy-code actions: the clipboard, with a polite word of feedback
     highlight(pre)              a small, safe highlighter (strings, comments, numbers, keywords), run once when a code block has settled

   Every string is put into the page with textContent; the only html set from text is ChatMarkdown's, which escapes first. No percentage, count or tool line is made up: the
   timeline is what the blocks say (chat_live_activity.js). A classic script with ONE global, ChatLiveView; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const str = v => (typeof v === "string" ? v : "");
  const clean = v => str(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const need = (name, file) => {
    if (root[name]) return root[name];
    if (typeof module === "object" && module !== null && module.exports && typeof require === "function") return require("./" + file);
    return null;
  };
  const Activity = () => need("ChatLiveActivity", "chat_live_activity.js");
  const Store = () => need("ChatLiveStore", "chat_live_store.js");
  const FluidOf = () => need("Fluid", "fluid.js");
  const MarkdownOf = () => need("ChatMarkdown", "chat_markdown.js");
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const PROVIDERS = {claude: "Claude", codex: "Codex", stub: "The demo provider"};
  const providerName = p => (Object.prototype.hasOwnProperty.call(PROVIDERS, p) ? PROVIDERS[p] : clean(p));

  const keyOf = (turn, attempt) => "turn:" + turn + ":" + (Number.isInteger(attempt) && attempt > 0 ? attempt : 1);

  // The html never changes for a (turn, attempt): everything that changes is painted into it. A superseded reply (a later try replaced it) is collapsed under "Earlier try".
  function shellHtml(turn, attempt, opts) {
    const o = isObj(opts) ? opts : {};
    const attrs = ' data-who="agent" data-kind="text" data-turn="' + esc(turn) + '" data-attempt="' + esc(Number.isInteger(attempt) && attempt > 0 ? attempt : 1) + '"';
    if (o.superseded === true) return '<div class="nmsg sb team clive cl-superseded"' + attrs + '><details class="cl-prior"><summary>Earlier try</summary><div class="cl-inner"></div></details></div>';
    return '<div class="nmsg sb team clive"' + attrs + '><div class="cl-inner"></div></div>';
  }

  const isReply = m => isObj(m) && str(m.role) === "agent" && Number.isInteger(m.turn) && m.turn > 0 &&
    (((str(m.kind) || "text") === "text") || (((str(m.kind) === "note") || (str(m.kind) === "error")) && m.ordered === true && Array.isArray(m.blocks) && m.blocks.length > 0));

  /* ---------------------------------------------------------------- models */
  function textOfBlocks(blocks) {
    return blocks.filter(b => b.type === "text").map(b => b.text).join("");
  }

  function fromLive(view, deps) {
    const d = isObj(deps) ? deps : {};
    const t = isObj(view) ? view.turn : null;
    if (!t || t.messageId === null || t.generationId === undefined) return null;
    const S = Store();
    const live = !S.terminal(t.phase);
    const blocks = t.blocks;
    const label = live ? str(view.label) : "";
    return {key: keyOf(t.messageId, t.attemptNo), turn: t.messageId, attempt: t.attemptNo, id: null, source: "live", live, phase: t.phase, state: live ? "live" : (t.phase === "stopped" ? "stopped" : (t.phase === "failed" ? "error" : "ok")),
      who: str(d.who) || providerName(t.provider) || "The model", meta: t.provider !== "" ? "via " + providerName(t.provider) + (clean(t.model) !== "" ? " " + clean(t.model) : "") : "", label, activity: isObj(view.activity) ? view.activity.kind : "", note: live ? str(view.note) : "",
      blocks, text: textOfBlocks(blocks), earlier: t.earlier, afterSideEffects: t.afterSideEffects, canStop: live && view.canStop === true, stopping: t.phase === "stopping",
      elapsedMs: live ? view.elapsedMs : 0, streamMode: t.streamMode, error: t.error, legacy: false, superseded: false, ending: "", polling: view.polling === true,
      detail: live && isObj(view.activity) ? str(view.activity.detail) : "", canRetry: false, siblingError: false};
  }

  function fromMessage(m, deps) {
    const d = isObj(deps) ? deps : {};
    const A = Activity();
    const kind = str(m.kind) || "text";
    const failed = kind === "error" || str(m.state) === "error";
    const ordered = m.ordered === true && Array.isArray(m.blocks) && m.blocks.length > 0;
    let blocks;
    if (ordered) {
      blocks = A.fromStored(m.blocks, {ids: Array.isArray(d.ids) ? d.ids : [], failed});
    } else {
      blocks = [];
      if (kind === "text" && str(m.text) !== "") blocks.push({id: "s0", type: "text", kind: "other", name: "", title: "", target: "", status: "ok", text: str(m.text), isError: false, truncated: false, output: "", startTs: "", endTs: ""});
      if (Array.isArray(m.blocks) && m.blocks.length > 0) {                          // a message from before ordered blocks: its text, then its tools folded into one row
        const tools = A.fromStored(m.blocks.filter(b => isObj(b) && b.type !== "text"), {ids: [], legacy: true, failed: false}).map((b, i) => Object.assign(b, {id: "s" + (i + 1)}));
        blocks = blocks.concat(tools);
      }
    }
    let ending = "";
    if (kind === "note" || kind === "error") ending = str(m.text);
    return {key: keyOf(m.turn, m.attempt), turn: m.turn, attempt: Number.isInteger(m.attempt) && m.attempt > 0 ? m.attempt : 1, id: m.id, source: "stored", live: false, phase: "", state: failed ? "error" : (kind === "note" ? "stopped" : "ok"),
      who: str(d.who) || "The model", meta: "", label: "", activity: "", note: "", blocks, text: textOfBlocks(blocks), earlier: [],
      afterSideEffects: blocks.some(b => b.type === "tool_use" && (b.kind === "edit" || b.kind === "run")), canStop: false, stopping: false,
      elapsedMs: 0, streamMode: "", error: null, legacy: !ordered && Array.isArray(m.blocks) && m.blocks.length > 0, superseded: m.superseded === true, ending, polling: false,
      detail: "", canRetry: false, siblingError: false};
  }

  /* ---------------------------------------------------------------- the shell's parts */
  function el(doc, tag, cls, text) {
    const e = doc.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function ensure(shell) {
    const doc = shell.ownerDocument || root.document;
    let cl = shell.__cl;
    const host = shell.querySelector(".cl-inner") || shell;
    if (cl && cl.host === host && host.parentNode !== null) return cl;
    host.textContent = "";
    const who = el(doc, "small", "cl-who");
    const head = el(doc, "div", "cl-head");
    const status = el(doc, "div", "cl-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.setAttribute("aria-atomic", "true");
    const state = el(doc, "span", "cl-state");
    status.appendChild(state);
    const clock = el(doc, "span", "cl-clock");
    clock.setAttribute("aria-hidden", "true");
    head.appendChild(status);
    head.appendChild(clock);
    const note = el(doc, "span", "cl-note");
    head.appendChild(note);
    const earlier = el(doc, "div", "cl-earlier");
    const body = el(doc, "div", "cl-body");
    const steps = el(doc, "details", "cl-steps");                                       // a message from before ordered blocks keeps its tools folded in one row
    steps.hidden = true;
    const stepsSummary = el(doc, "summary", "cl-steps-sum");
    const stepsBody = el(doc, "div", "cl-steps-body");
    steps.appendChild(stepsSummary);
    steps.appendChild(stepsBody);
    const ending = el(doc, "div", "cl-ending");
    const actions = el(doc, "div", "cl-actions");
    // the status and the actions share ONE row under the blocks: it is there while the reply streams and when it has settled, so the words above it never move at settle
    const foot = el(doc, "div", "cl-foot");
    foot.appendChild(head);
    foot.appendChild(actions);
    [who, earlier, body, steps, ending, foot].forEach(n => host.appendChild(n));
    cl = shell.__cl = {host, who, head, foot, status, state, clock, earlier, body, steps, stepsSummary, stepsBody, note, ending, actions, nodes: new Map(), sig: {}, painted: false, text: ""};
    return cl;
  }

  function setText(node, value, cl, key) {
    if (cl.sig[key] === value) return false;
    cl.sig[key] = value;
    node.textContent = value;
    return true;
  }

  function setAttr(node, name, value) {
    if (value === "" || value === null || value === undefined || value === false) { if (node.hasAttribute(name)) node.removeAttribute(name); } else if (node.getAttribute(name) !== String(value)) node.setAttribute(name, String(value));
  }

  /* ---------------------------------------------------------------- blocks */
  function makeBlock(doc, b, cl) {
    let node;
    if (b.type === "text") {
      node = el(doc, "div", "cl-block cl-text");
      node.appendChild(el(doc, "div", "cl-tx"));
    } else if (b.type === "thinking") {
      node = el(doc, "div", "cl-block cl-think");
      node.appendChild(el(doc, "span", "cl-mark"));
      node.appendChild(el(doc, "span", "cl-title"));
      node.appendChild(el(doc, "span", "cl-meta"));
    } else {
      node = el(doc, "details", "cl-block cl-tool");
      const sum = el(doc, "summary", "cl-sum");
      sum.appendChild(el(doc, "span", "cl-mark"));
      sum.appendChild(el(doc, "span", "cl-title"));
      sum.appendChild(el(doc, "span", "cl-meta"));
      node.appendChild(sum);
      node.appendChild(el(doc, "div", "cl-detail"));
    }
    node.setAttribute("data-block", b.id);
    if (cl.painted) node.classList.add("cl-in");                                       // an arrival enters; what was there when the reply first drew does not
    return node;
  }

  function paintTool(node, b, A, cl) {
    const d = A.describe(b);
    const sig = [d.title, d.status, d.durationText, d.target, b.output === undefined ? "" : b.output.length, b.kind].join("\u0001");
    if (node.__sig === sig) return;
    node.__sig = sig;
    setAttr(node, "data-status", d.status);
    setAttr(node, "data-kind", d.kind);
    const sum = node.children[0];
    sum.children[1].textContent = d.title;
    sum.children[2].textContent = d.status === "open" ? "" : (d.status === "ok" ? d.durationText : d.statusWord + (d.durationText ? ", " + d.durationText : ""));
    const detail = node.children[1];
    detail.textContent = "";
    const doc = node.ownerDocument || root.document;
    const rows = [];
    if (d.target !== "") rows.push(["Target", d.target]);
    rows.push(["Status", d.statusWord + (d.durationText ? " (" + d.durationText + ")" : "")]);
    rows.forEach(([k, v]) => { const row = el(doc, "div", "cl-row"); row.appendChild(el(doc, "b", "", k + ": ")); row.appendChild(el(doc, "span", "", v)); detail.appendChild(row); });
    if (d.output !== "") {
      const pre = el(doc, "pre", "cl-out", d.output);
      detail.appendChild(pre);
      if (d.truncated) detail.appendChild(el(doc, "small", "cl-cut", "The output was cut."));
    }
    setAttr(node, "data-has-detail", "1");
  }

  function paintThink(node, b, A) {
    const d = A.describe(b);
    const sig = d.status + d.durationText;
    if (node.__sig === sig) return;
    node.__sig = sig;
    setAttr(node, "data-status", d.status);
    node.children[1].textContent = d.status === "open" ? "Thinking" : "Thought";
    node.children[2].textContent = d.status === "open" || d.durationText === "" ? "" : d.durationText;
  }

  function addCopyButtons(tx, doc) {
    tx.querySelectorAll("pre").forEach(pre => {
      if (pre.querySelector(".cl-copycode")) return;
      const b = el(doc, "button", "cl-copycode", "Copy");
      b.setAttribute("type", "button");
      b.setAttribute("data-act", "copy-code");
      b.setAttribute("aria-label", "Copy this code");
      pre.appendChild(b);
    });
  }

  function reorder(container, wanted) {
    let ref = container.firstChild;
    wanted.forEach(node => {
      if (node === ref) { ref = ref.nextSibling; return; }
      container.insertBefore(node, ref);
    });
    while (ref) { const next = ref.nextSibling; container.removeChild(ref); ref = next; }
  }

  function paintBlocks(cl, model, deps, doc) {
    const A = Activity();
    const F = deps.Fluid || FluidOf();
    const render = typeof deps.render === "function" ? deps.render : (MarkdownOf() ? MarkdownOf().render : () => "");
    const highlight = typeof deps.highlight === "function" ? deps.highlight : highlightPre;
    const seen = new Set();
    const bodyNodes = [];
    const stepNodes = [];
    let lastOpenText = null;
    model.blocks.forEach(b => { if (b.type === "text" && b.status === "open") lastOpenText = b.id; });
    const folded = model.legacy === true;
    model.blocks.forEach(b => {
      seen.add(b.id);
      let rec = cl.nodes.get(b.id);
      if (rec && rec.type !== b.type) { if (rec.node.parentNode) rec.node.parentNode.removeChild(rec.node); cl.nodes.delete(b.id); rec = undefined; }
      if (!rec) { rec = {type: b.type, node: makeBlock(doc, b, cl)}; cl.nodes.set(b.id, rec); }
      const node = rec.node;
      if (b.type === "text") {
        const writing = model.live && b.id === lastOpenText && !model.stopping && model.phase === "running";
        const tx = node.children[0];
        const streaming = model.live || b.status === "open";
        F.paintText(tx, b.text, {render, streaming, highlight});
        if (!streaming) addCopyButtons(tx, doc);
        if (node.classList.contains("cl-writing") !== writing) node.classList.toggle("cl-writing", writing);
        const empty = b.text === "";
        if (node.hidden !== empty) node.hidden = empty;
      } else if (b.type === "thinking") {
        paintThink(node, b, A);
      } else {
        paintTool(node, b, A, cl);
      }
      (folded && b.type === "tool_use" ? stepNodes : bodyNodes).push(node);
    });
    for (const [id, rec] of Array.from(cl.nodes.entries())) {
      if (!seen.has(id)) { if (rec.node.parentNode) rec.node.parentNode.removeChild(rec.node); cl.nodes.delete(id); }
    }
    reorder(cl.body, bodyNodes);
    reorder(cl.stepsBody, stepNodes);
    const hasSteps = stepNodes.length > 0;
    if (cl.steps.hidden === hasSteps) cl.steps.hidden = !hasSteps;
    if (hasSteps) setText(cl.stepsSummary, A.summary(model.blocks), cl, "steps");
  }

  /* ---------------------------------------------------------------- the rest of the shell */
  function paintEarlier(cl, model, doc) {
    const sig = model.earlier.map(e => [e.provider, e.reason, e.afterSideEffects ? 1 : 0, (e.lines || []).join("|"), e.blocks ? e.blocks.length : 0].join("~")).join("^^");
    if (cl.sig.earlier === sig) return;
    cl.sig.earlier = sig;
    cl.earlier.textContent = "";
    cl.earlier.hidden = model.earlier.length === 0;
    model.earlier.forEach(e => {
      const d = el(doc, "details", "cl-prior");
      const who = providerName(e.provider) || "The model";
      const why = clean(e.reason).replace(/[.\s]+$/, "");
      d.appendChild(el(doc, "summary", "", "Earlier try: " + who + (why ? " failed (" + why + ")" : " stopped") + (e.afterSideEffects ? ", it may have changed files" : "")));
      const lines = (Array.isArray(e.lines) && e.lines.length > 0) ? e.lines : (e.blocks || []).filter(b => b.type === "tool_use").map(b => b.title || ("Using " + (b.name || "a tool")));
      const ul = el(doc, "ul", "cl-prior-list");
      lines.slice(0, 20).forEach(line => ul.appendChild(el(doc, "li", "", clean(line))));
      if (lines.length > 0) d.appendChild(ul);
      cl.earlier.appendChild(d);
    });
  }

  // Retry is offered on a reply that was stopped or failed and is the owner's newest line; a reply whose failure has its own error line (which has its own Retry) does not repeat it.
  const retryShown = model => model.canRetry === true && (model.state === "stopped" || (model.state === "error" && model.siblingError !== true));

  function paintActions(cl, model, deps, doc) {
    const want = [];
    if (model.live) {
      want.push(model.stopping ? {act: "composer-stop", label: "Stopping…", disabled: true, aria: "Stopping the answer"} : {act: "composer-stop", label: "Stop", disabled: !model.canStop, aria: "Stop the answer"});
    } else if (model.text !== "") {
      want.push({act: "copy-reply", label: "Copy", aria: "Copy the answer"});
    }
    if (!model.live && retryShown(model)) want.push({act: "retry-direct", label: "Retry", turn: model.turn, aria: "Ask again"});
    const sig = want.map(w => w.act + w.label + (w.disabled ? "1" : "0") + (w.turn || "")).join("|");
    if (cl.sig.actions === sig) return;
    cl.sig.actions = sig;
    cl.actions.textContent = "";
    cl.actions.hidden = want.length === 0;
    want.forEach(w => {
      const b = el(doc, "button", "linkbtn cl-act", w.label);
      b.setAttribute("type", "button");
      b.setAttribute("data-act", w.act);
      if (w.turn) b.setAttribute("data-turn", String(w.turn));
      if (w.aria) b.setAttribute("aria-label", w.aria);
      if (w.disabled) b.disabled = true;
      cl.actions.appendChild(b);
    });
  }

  function paint(shell, model, deps) {
    if (!shell || !isObj(model)) return false;
    const d = isObj(deps) ? deps : {};
    const doc = shell.ownerDocument || root.document;
    const cl = ensure(shell);
    const A = Activity();
    setText(cl.who, model.who + (model.meta !== "" ? " · " + model.meta : ""), cl, "who");
    // the status: a short label (announced on a change of state) and a clock that is not announced
    const lab = A.parts(model.label);
    const secs = model.live && model.elapsedMs >= 3000 ? Math.round(model.elapsedMs / 1000) + " s" : "";
    setText(cl.state, lab.text, cl, "state");
    setText(cl.clock, lab.clock !== "" ? lab.clock : (lab.text !== "" ? secs : ""), cl, "clock");
    cl.head.hidden = lab.text === "" && !(model.live && (model.note || model.afterSideEffects));
    setAttr(shell, "data-state", model.state);
    setAttr(shell, "data-phase", model.phase);
    setAttr(shell, "data-activity", model.live ? model.activity : "");
    setAttr(shell, "data-stream", model.live ? model.streamMode : "");
    if (model.id !== null && model.id !== undefined) setAttr(shell, "data-id", model.id); else if (shell.hasAttribute("data-id")) shell.removeAttribute("data-id");
    const live = model.live === true;
    if (shell.classList.contains("cl-live") !== live) shell.classList.toggle("cl-live", live);
    setAttr(cl.body, "aria-busy", live ? "true" : "");
    paintEarlier(cl, model, doc);
    paintBlocks(cl, model, d, doc);
    const notes = [];
    const retry = !model.live && retryShown(model);
    if (model.live && model.note) notes.push(model.note);
    if (model.live && model.detail) notes.push(model.detail);
    if (model.live && model.afterSideEffects) notes.push("An earlier try may have changed files.");
    if (retry && model.afterSideEffects) notes.push("This try may have changed files. Trying again can repeat that.");
    setText(cl.note, notes.join(" "), cl, "note");
    cl.note.hidden = notes.length === 0;
    setAttr(shell, "data-note", notes.length > 0 ? "1" : "");
    cl.head.hidden = lab.text === "" && notes.length === 0;
    cl.foot.hidden = cl.head.hidden && cl.actions.hidden;
    setText(cl.ending, !live && model.source === "stored" ? clean(model.ending) : "", cl, "ending");
    cl.ending.hidden = cl.sig.ending === "";
    paintActions(cl, model, d, doc);
    cl.foot.hidden = cl.head.hidden && cl.actions.hidden;
    cl.text = model.text;
    cl.painted = true;
    return true;
  }

  // supersede(messages) -> messages: a reply, and the notes and errors stored with it, of a try that a LATER try of the same owner line replaced, is `superseded`. The server says so in
  // what it reads; a page that read the first try before the retry's reply was stored has not been told, so it works it out from the rows it has (the same rule). New objects only
  // where a flag changes; the list and the rows are otherwise returned as they are.
  function supersede(messages) {
    const list = Array.isArray(messages) ? messages : [];
    const newest = new Map();
    const tryOf = m => (Number.isInteger(m.attempt) && m.attempt > 0 ? m.attempt : 1);
    list.forEach(m => { if (isObj(m) && m.role === "agent" && Number.isInteger(m.turn) && m.turn > 0) newest.set(m.turn, Math.max(newest.get(m.turn) || 1, tryOf(m))); });
    let changed = false;
    const out = list.map(m => {
      if (!isObj(m) || m.role !== "agent" || !Number.isInteger(m.turn) || m.superseded === true || tryOf(m) >= (newest.get(m.turn) || 1)) return m;
      changed = true;
      return Object.assign({}, m, {superseded: true});
    });
    return changed ? out : list;
  }

  // plan(messages, view, deps) -> {models: {key: model}, liveItem: {key, html} | null}: what the transcript needs to draw the replies as shells. Every reply item of the list gets
  // its model from the STORED message (the block ids of a turn that just settled are its stored_order, so the node carries over); the live turn gets an item of its own only
  // while no stored message of that (turn, try) is on the page: it is the same key, so the stored message takes the node over. deps {whoOf(message), canRetry(message)}.
  function plan(messages, view, deps) {
    const d = isObj(deps) ? deps : {};
    const models = {};
    const turn = isObj(view) && isObj(view.turn) ? view.turn : null;
    const settled = isObj(view) && isObj(view.settled) ? view.settled : null;
    (Array.isArray(messages) ? messages : []).forEach(m => {
      if (!isReply(m)) return;
      const attempt = Number.isInteger(m.attempt) && m.attempt > 0 ? m.attempt : 1;
      let ids = [];
      if (turn && turn.messageId === m.turn && turn.attemptNo === attempt) ids = turn.storedOrder;
      else if (settled && settled.messageId === m.turn && settled.attemptNo === attempt) ids = settled.storedOrder;
      const model = fromMessage(m, {ids, who: typeof d.whoOf === "function" ? d.whoOf(m) : ""});
      // how the turn ended, from the lines that were stored with the reply: a note after it says it was stopped, an error line says it failed (and has its own Retry)
      const same = x => isObj(x) && x !== m && x.role === "agent" && x.turn === m.turn && (Number.isInteger(x.attempt) && x.attempt > 0 ? x.attempt : 1) === attempt && !isReply(x);
      const rows = Array.isArray(messages) ? messages : [];
      if (rows.some(x => same(x) && str(x.kind) === "error")) { model.state = "error"; model.siblingError = true; }
      else if (rows.some(x => same(x) && str(x.kind) === "note" && /^Stopped\b/.test(str(x.text)))) model.state = "stopped";           // a switch note is not a stop
      model.canRetry = typeof d.canRetry === "function" ? d.canRetry(model) === true : false;
      models[model.key] = model;
    });
    const live = fromLive(view, {who: typeof d.who === "string" ? d.who : ""});
    let liveItem = null;
    if (live && !models[live.key]) {
      models[live.key] = live;
      liveItem = {key: live.key, html: shellHtml(live.turn, live.attempt)};
    }
    return {models, liveItem};
  }

  function sync(host, models, deps) {
    if (!host || !isObj(models)) return 0;
    let n = 0;
    host.querySelectorAll(".clive").forEach(shell => {
      const key = keyOf(Number(shell.getAttribute("data-turn")), Number(shell.getAttribute("data-attempt")));
      const model = models[key];
      if (model && paint(shell, model, deps)) n += 1;
    });
    return n;
  }

  /* ---------------------------------------------------------------- copy */
  function copyText(shell) {
    return shell && shell.__cl ? shell.__cl.text : "";
  }

  // Copy and Copy code. `deps` {clipboard {writeText}, schedule(fn, ms)}: the page's own by default. The button says "Copied" for a moment (a change of its text, read by the
  // screen reader through its own label), and says "Could not copy" when the browser refused.
  async function copy(button, deps) {
    const d = isObj(deps) ? deps : {};
    if (!button || typeof button.closest !== "function") return false;
    const act = button.getAttribute("data-act");
    const shell = button.closest(".clive");
    let text = "";
    if (act === "copy-code") {
      const pre = button.closest("pre");
      const code = pre ? (pre.querySelector("code") || pre) : null;
      text = code ? code.textContent : "";
    } else {
      text = copyText(shell);
    }
    if (text === "") return false;
    const clipboard = d.clipboard || (root.navigator && root.navigator.clipboard) || null;
    const schedule = typeof d.schedule === "function" ? d.schedule : (fn, ms) => root.setTimeout(fn, ms);
    const was = button.textContent;
    let ok = false;
    try {
      if (clipboard && typeof clipboard.writeText === "function") { await clipboard.writeText(text); ok = true; }
      else if (typeof d.fallback === "function") ok = d.fallback(text) === true;
    } catch (e) {
      ok = false;
    }
    button.textContent = ok ? "Copied" : "Could not copy";
    schedule(() => { button.textContent = was; }, 1600);
    return ok;
  }

  /* ---------------------------------------------------------------- highlight (once, on settle) */
  const KEYWORDS = new Set(("function return const let var if else for while class import from export new this null true false undefined async await try catch throw def lambda None True False pass " +
    "elif in is not and or with as yield raise except finally fn pub struct impl use mut match enum interface type public private static void int string bool package func go defer select switch case break continue").split(" "));
  const TOKEN = /(\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/)|("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`)|(\b\d[\d_.]*\b)|(\b[A-Za-z_][A-Za-z0-9_]*\b)/g;

  function highlightPre(pre) {
    const code = pre && typeof pre.querySelector === "function" ? (pre.querySelector("code") || pre) : null;
    if (!code) return false;
    const doc = code.ownerDocument || root.document;
    const text = code.textContent;
    if (text === "" || text.length > 60000) return false;
    const frag = doc.createDocumentFragment();
    let last = 0;
    let m;
    TOKEN.lastIndex = 0;
    while ((m = TOKEN.exec(text)) !== null) {
      const cls = m[1] !== undefined ? "tk-c" : (m[2] !== undefined ? "tk-s" : (m[3] !== undefined ? "tk-n" : (KEYWORDS.has(m[4]) ? "tk-k" : "")));
      if (cls === "") continue;
      if (m.index > last) frag.appendChild(doc.createTextNode(text.slice(last, m.index)));
      frag.appendChild(el(doc, "span", cls, m[0]));
      last = m.index + m[0].length;
    }
    if (last === 0) return false;
    if (last < text.length) frag.appendChild(doc.createTextNode(text.slice(last)));
    code.textContent = "";
    code.appendChild(frag);
    return true;
  }

  const ChatLiveView = {keyOf, shellHtml, isReply, fromLive, fromMessage, supersede, plan, paint, sync, copyText, copy, highlight: highlightPre, providerName};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatLiveView;
  else root.ChatLiveView = ChatLiveView;
})(globalThis);
