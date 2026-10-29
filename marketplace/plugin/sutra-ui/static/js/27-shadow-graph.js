/* 27-shadow-graph.js -- the Shadow graph and the task detail (amendment A5, A5.2).

   One screen, `shadowgraph`, two modes. OVERVIEW draws Shadow, its tasks, goals, conversations, task chats, workers and departments
   as a left-to-right metro map; FOCUS (S.shadowGraphFocus = a mission id) is the per-task detail screen: that task's own graph on the
   left, Decision, Departments, Chats, Workers, Costs and Timeline on the right.

   The server lays the graph out (shadow_graph.py: col, row, edges, status); this file only renders and opens. Components render, every
   click opens an existing screen (sgOpen), and nothing here writes. Nodes are real <button>s over an SVG line layer inside one host,
   so keyboard and screen readers get the same graph; status is a word and a glyph beside the colour, never the colour alone.
   Rendering goes through the screen pass (06-render.js patches this screen with shadowPatchInto), so a focused node survives a poll.
   Every global of this file is prefixed sg / SG_. */

const SG_API = "/api/shadow/graph";
const SG_POLL_MS = 4000;
const SG_KEY = "sutra.shadow.graph";
const SG_COLW = 238, SG_NODEW = 152, SG_ROWH = 26, SG_NODEH = 40, SG_TAGW = 52, SG_TAGH = 18, SG_PADX = 16, SG_PADY = 12, SG_PHONE = 700;
const SG_STALE_S = 12;

/* a status is its word and its glyph before it is a colour */
const SG_WORD = { draft: "Draft", working: "Working", waiting: "Waiting", blocked: "Blocked", done: "Done", failed: "Failed",
  stopped: "Stopped", idle: "Idle", off: "Off" };
const SG_GLYPH = { draft: "\u25CC", working: "\u25B6", waiting: "\u2016", blocked: "!", done: "\u2713", failed: "\u2715", stopped: "\u25A0",
  idle: "\u00B7", off: "\u25CB" };
const SG_KIND = { shadow: "Shadow", conversation: "Conversation", goal: "Goal", task: "Task", task_chat: "Task chat", worker: "Worker",
  department: "Department" };
const SG_TAG = { uses: "uses", spawned: "spawned" };
const SG_EDGE_WORD = { has: "has", opened: "opened", attempt: "attempt at", steered_by: "steered by", driven_by: "driven by",
  uses: "uses", spawned: "spawned" };
const SG_ROLE = { shadow_chat: "Task chat", conversation: "Conversation", worker: "Worker", department_page: "Department", now: "Now" };
const SG_COST = { now: "Now", shadow: "Shadow", worker: "Worker", department: "Department" };
const SG_BY = { founder: "You", shadow: "Shadow", worker: "Worker", department: "Department", system: "" };
const SG_CHOICE = { use: "Used", create: "Made", none: "No department" };

let _sg = null;
let _sgRead = null;
let _sgTicker = null;

function sgState(){
  if (!_sg) _sg = { graph: null, detail: null, dark: false, err: false, loaded: false, at: 0, forFocus: undefined, cur: null, tip: null, pin: null,
    includeDone: false, fit: false };
  return _sg;
}
function sgReset(){ _sg = null; _sgRead = null; if (_sgTicker && typeof clearInterval === "function") clearInterval(_sgTicker); _sgTicker = null; }
function sgS(){ return (typeof S !== "undefined" && S) ? S : {}; }
function sgEsc(x){ return (typeof esc === "function") ? esc(x) : String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function sgAttr(x){ return sgEsc(x).replace(/"/g, "&quot;"); }
function sgNow(){ return (typeof Date !== "undefined") ? Date.now() : 0; }
function sgPhone(){ return typeof window !== "undefined" && window.innerWidth > 0 && window.innerWidth < SG_PHONE; }
function sgWhen(at){ const m = /T(\d\d:\d\d)/.exec(String(at || "")); return m ? m[1] : ""; }
function sgFocus(){ const f = sgS().shadowGraphFocus; return (typeof f === "string" && /^m-[0-9a-f]{12}$/.test(f)) ? f : null; }
function sgSetFocus(mid){
  sgS().shadowGraphFocus = mid || null;
  if (typeof lsSet === "function") lsSet(SG_KEY, mid || null);
  const st = sgState();
  st.cur = null; st.tip = null; st.pin = null;
}
function sgRepaint(){ if (typeof scheduleRender === "function") scheduleRender(); }

/* ── reads: one GET (two in focus mode is not needed: the detail holds the focus graph), coalesced like _shHomeRead ───────── */
function sgUrl(){
  const f = sgFocus();
  return f ? SG_API + "/task/" + encodeURIComponent(f) : SG_API + "?include_done=" + (sgState().includeDone ? 1 : 0);
}
function sgLoad(force){
  if (_sgRead && !force) return _sgRead;
  if (typeof fetch === "undefined") return null;
  const st = sgState(), focus = sgFocus(), url = sgUrl();
  st.forFocus = focus;
  const p = Promise.resolve().then(() => fetch(url)).then(async r => {
    if (r.status === 403){ st.dark = true; st.err = false; st.loaded = true; return; }
    if (r.status === 404 && focus){                       /* the task is gone: leave its detail, never keep asking */
      sgSetFocus(null); st.detail = null; st.forFocus = undefined; return;
    }
    if (!r.ok) throw new Error("graph " + r.status);
    const j = await r.json();
    st.dark = false; st.err = false; st.loaded = true; st.at = sgNow();
    if (focus){ st.detail = j; if (j && j.graph && !st.cur) st.cur = "task:" + focus; }
    else { st.graph = j; }
  }).catch(() => { st.err = true; st.loaded = true; });
  _sgRead = p;
  const clear = () => { if (_sgRead === p) _sgRead = null; sgRepaint(); };
  p.then(clear, clear);
  return p;
}
function sgOnScreen(){ return sgS().screen === "shadowgraph"; }
function ensureShadowGraphTicker(){
  if (_sgTicker || typeof setInterval === "undefined") return;
  _sgTicker = setInterval(() => {
    if (!sgOnScreen()){
      if (typeof clearInterval === "function") clearInterval(_sgTicker);
      _sgTicker = null;
      return;
    }
    try { sgLoad(); } catch (e) {}
  }, SG_POLL_MS);
}

/* ── what is drawn ─────────────────────────────────────────────────────────────────────────────────────────────────────── */
function sgData(){
  const st = sgState(), f = sgFocus();
  if (f) return (st.detail && st.detail.task && st.detail.task.id === f) ? st.detail : null;
  return st.graph;
}
function sgGraph(){ const d = sgData(); return d ? (sgFocus() ? d.graph : d) : null; }
function sgNode(id){ const g = sgGraph(); return g ? (g.nodes || []).filter(n => n.id === id)[0] || null : null; }
function sgEdgeById(id){ const g = sgGraph(); return g ? (g.edges || []).filter(e => e.id === id)[0] || null : null; }
function sgPos(n){ return { x: SG_PADX + n.col * SG_COLW, y: SG_PADY + n.row * SG_ROWH }; }
function sgSize(g){
  let c = 0, r = 0;
  (g.nodes || []).forEach(n => { c = Math.max(c, n.col); r = Math.max(r, n.row); });
  return { w: SG_PADX * 2 + c * SG_COLW + SG_NODEW, h: SG_PADY * 2 + r * SG_ROWH + SG_NODEH };
}

/* the edge as a metro line: orthogonal runs, a 45 degree join, round caps */
function sgPath(a, b){
  const pa = sgPos(a), pb = sgPos(b);
  const x1 = pa.x + SG_NODEW, y1 = pa.y + SG_NODEH / 2, x2 = pb.x, y2 = pb.y + SG_NODEH / 2;
  if (y1 === y2 || x2 <= x1 + 6) return "M" + x1 + " " + y1 + (y1 === y2 ? " H" + x2 : " L" + x2 + " " + y2);
  const s = y2 > y1 ? 1 : -1, bx = x1 + Math.min(18, (x2 - x1) / 2), d = Math.min(8, bx - x1, Math.abs(y2 - y1) / 2);
  return "M" + x1 + " " + y1 + " H" + (bx - d) + " L" + bx + " " + (y1 + s * d) + " V" + (y2 - s * d) + " L" + (bx + d) + " " + y2 + " H" + x2;
}
function sgEdgeSvg(e, nodes){
  const a = nodes[e.source], b = nodes[e.target];
  if (!a || !b) return "";
  const pa = sgPos(a), cls = "sgedge e-" + e.kind + (e.held ? " e-held" : "") + (e.live ? " live" : "");
  const start = e.kind === "spawned" && !e.held
    ? `<circle class="sgplus" cx="${pa.x + SG_NODEW + 5}" cy="${pa.y + SG_NODEH / 2}" r="5"/><path class="sgplusm" d="M${pa.x + SG_NODEW + 2} ${pa.y + SG_NODEH / 2} h6 M${pa.x + SG_NODEW + 5} ${pa.y + SG_NODEH / 2 - 3} v6"/>` : "";
  return `<path class="${cls}" data-sgedge="${sgAttr(e.id)}" d="${sgPath(a, b)}"/>${start}`;
}
function sgShape(kind){
  switch (kind){
    case "shadow": return `<circle class="sgo" cx="11" cy="11" r="9.5"/><circle class="sgi" cx="11" cy="11" r="3.5"/>`;
    case "goal": return `<path class="sgo" d="M11 1.5 L20.5 11 L11 20.5 L1.5 11 Z"/>`;
    case "conversation": return `<circle class="sgo" cx="10" cy="10" r="6"/><path class="sgl" d="M14 14 L19 19"/>`;
    case "task_chat": return `<rect class="sgo" x="2" y="3" width="18" height="12" rx="4"/><path class="sgl" d="M7 15 L5 20 L11 15"/>`;
    case "worker": return `<rect class="sgo" x="2" y="3" width="18" height="12" rx="4"/><path class="sgl" d="M7 15 L5 20 L11 15"/><path class="sgl" d="M11 6 v6 M8 9 h6"/>`;
    case "department": return `<circle class="sgo" cx="11" cy="11" r="9.5"/><circle class="sgo" cx="11" cy="11" r="5"/>`;
    default: return `<circle class="sgo" cx="11" cy="11" r="7.5"/>`;
  }
}
function sgNodeHtml(n, st, style){
  const word = SG_WORD[n.status] || n.status;
  const cur = (st.cur || "") === n.id;
  const aria = (SG_KIND[n.kind] || n.kind).toLowerCase() + ": " + n.label + ", " + word;
  const sub = [n.sub].filter(Boolean).map(sgEsc).join(" ");
  return `<button type="button" class="sgnode sgk-${n.kind} sgs-${n.status}${cur ? " cur" : ""}" data-sgnode="${sgAttr(n.id)}"
    data-sgk="${sgAttr(n.open.kind)}" data-sgr="${sgAttr(n.open.ref || "")}"${style ? ` style="${style}"` : ""}
    tabindex="${cur ? 0 : -1}" aria-label="${sgAttr(aria)}"><svg class="sgshape" viewBox="0 0 22 22" width="22" height="22" aria-hidden="true">${sgShape(n.kind)}</svg>
    <span class="sgtxt"><span class="sglab">${sgEsc(n.label)}</span><span class="sgsub"><span class="sgglyph" aria-hidden="true">${SG_GLYPH[n.status] || ""}</span> ${
      sgEsc(word)}${sub ? " \u00b7 " + sub : ""}</span></span></button>`;
}
function sgDecidedBy(e){
  const dec = (sgFocus() && sgState().detail && sgState().detail.decision) || null;
  if (e.held || (dec && dec.decided_by === "code"))
    return "by the rule: " + (dec && (dec.overrides || []).length ? dec.overrides.map(o => o.note).join("; ") : (e.reason || "held"));
  return dec && dec.decided_by === "stub" ? "decided without the model" : "decided by agent";
}
function sgTipHtml(){
  const st = sgState(), key = st.pin || st.tip;
  if (!key) return { html: "", at: null };
  if (key.indexOf("edge:") === 0){
    const e = sgEdgeById(key.slice(5)), g = sgGraph();
    if (!e || !g) return { html: "", at: null };
    const t = (g.nodes || []).filter(n => n.id === e.target)[0];
    const p = t ? sgPos(t) : { x: 0, y: 0 };
    return { at: { x: Math.max(0, p.x - 120), y: p.y + SG_NODEH + 4 },
      html: `<b>${sgEsc(e.held ? "held" : SG_EDGE_WORD[e.kind] || e.kind)}</b>${e.reason ? `<span>${sgEsc(e.reason)}</span>` : ""}${
        e.confidence ? `<span>Confidence: ${sgEsc(e.confidence)}</span>` : ""}<span>${sgEsc(sgDecidedBy(e))}</span>` };
  }
  const n = sgNode(key);
  if (!n) return { html: "", at: null };
  const p = sgPos(n);
  return { at: { x: p.x + 12, y: p.y + SG_NODEH + 4 },
    html: `<b>${sgEsc(SG_KIND[n.kind] || n.kind)}: ${sgEsc(n.label)}</b><span>${sgEsc(SG_GLYPH[n.status] || "")} ${sgEsc(SG_WORD[n.status] || n.status)}</span>${
      n.tip ? `<span>${sgEsc(n.tip)}</span>` : ""}${n.cost_usd ? `<span>About $${sgEsc(n.cost_usd.toFixed(2))} so far</span>` : ""}${
      n.since ? `<span>Since ${sgEsc(sgWhen(n.since))}</span>` : ""}` };
}

/* the wide graph: node buttons over an SVG layer in one host */
function sgGraphHtml(g){
  const st = sgState(), nodes = {};
  (g.nodes || []).forEach(n => { nodes[n.id] = n; });
  if (!st.cur || !nodes[st.cur]) st.cur = (sgFocus() && nodes["task:" + sgFocus()]) ? "task:" + sgFocus() : ((g.nodes || []).filter(n => n.kind === "task")[0] || g.nodes[0] || {}).id || null;
  const z = sgSize(g);
  const lines = (g.edges || []).map(e => sgEdgeSvg(e, nodes)).join("");
  const btns = (g.nodes || []).map(n => { const p = sgPos(n); return sgNodeHtml(n, st, `left:${p.x}px;top:${p.y}px;width:${SG_NODEW}px;height:${SG_NODEH}px`); }).join("");
  const tags = (g.edges || []).filter(e => e.kind === "uses" || e.kind === "spawned" || e.held).map(e => {
    const a = nodes[e.source], b = nodes[e.target];
    if (!a || !b) return "";
    const pb = sgPos(b);
    const word = e.held ? "held" : SG_TAG[e.kind];
    return `<button type="button" class="sgtag t-${e.held ? "held" : e.kind}" data-sgtag="${sgAttr(e.id)}" style="left:${pb.x - Math.round((SG_COLW - SG_NODEW + SG_TAGW) / 2)}px;top:${pb.y + SG_NODEH / 2 - SG_TAGH / 2}px"
      aria-label="${sgAttr(word + ": " + (e.reason || ""))}">${sgEsc(word)}</button>`;
  }).join("");
  const tip = sgTipHtml();
  const tipEl = tip.html ? `<div class="sgtip" role="tooltip" style="left:${tip.at.x}px;top:${tip.at.y}px">${tip.html}</div>` : "";
  const scale = st.fit && typeof window !== "undefined" && window.innerWidth ? Math.max(0.4, Math.min(1, (window.innerWidth - 80) / z.w)) : 1;
  return `<div class="sgscroll"><div class="sghostwrap" style="width:${Math.round(z.w * scale)}px;height:${Math.round(z.h * scale)}px">
    <div class="sghost" data-sghost="1" role="group" aria-label="Shadow graph" style="width:${z.w}px;height:${z.h}px;transform:scale(${scale})">
    <svg class="sglines" width="${z.w}" height="${z.h}" viewBox="0 0 ${z.w} ${z.h}" aria-hidden="true">${lines}</svg>${btns}${tags}${tipEl}</div></div></div>`;
}

/* phone: one indented column with a left rail, 44 px targets, the tooltip inline under the node */
function sgListHtml(g){
  const st = sgState(), nodes = {};
  (g.nodes || []).forEach(n => { nodes[n.id] = n; });
  if (!st.cur || !nodes[st.cur]) st.cur = ((g.nodes || []).filter(n => n.kind === "task")[0] || g.nodes[0] || {}).id || null;
  const into = {};
  (g.edges || []).forEach(e => { (into[e.target] = into[e.target] || []).push(e); });
  const order = (g.nodes || []).slice().sort((a, b) => a.row - b.row || a.col - b.col);
  const key = st.pin || st.tip;
  const rows = order.map(n => {
    const lines = (into[n.id] || []).filter(e => e.reason || e.held).map(e =>
      `<button type="button" class="sgtag t-${e.held ? "held" : e.kind}" data-sgtag="${sgAttr(e.id)}">${sgEsc(e.held ? "held" : SG_TAG[e.kind] || e.kind)}</button>`).join("");
    const open = key === n.id ? `<div class="sgtip inline" role="tooltip">${sgTipHtml().html}</div>` : "";
    return `<li class="sgrow" style="margin-left:${n.col * 14}px">${sgNodeHtml(n, st, "")}${lines}${open}</li>`;
  }).join("");
  return `<ul class="sglist" data-sghost="1" role="group" aria-label="Shadow graph">${rows}</ul>`;
}

/* no counts at rest: the header says what kind of thing is happening, never how many */
function sgSummary(g){
  const t = (g.nodes || []).filter(n => n.kind === "task");
  const bits = [];
  if (t.some(n => n.status === "working")) bits.push("Working");
  if (t.some(n => n.status === "waiting")) bits.push("Waiting on you");
  return bits.join(", ");
}
function sgBanner(){
  const st = sgState(), age = st.at ? Math.round((sgNow() - st.at) / 1000) : 0;
  if (st.err) return `<div class="sgnote warn" role="status">Could not refresh. Retrying\u2026 <button type="button" class="btn" data-sgretry="1">Retry</button></div>`;
  if (st.at && age >= SG_STALE_S) return `<div class="sgnote" role="status">Updated ${age}s ago</div>`;
  return "";
}

/* ── the detail sections (focus mode) ───────────────────────────────────────────────────────────────────────────────────── */
function sgOpenBtn(label, o, cls){
  if (!o || !o.kind || o.kind === "none") return "";
  return `<button type="button" class="btn sgbtn${cls ? " " + cls : ""}" data-sgk="${sgAttr(o.kind)}" data-sgr="${sgAttr(o.ref || "")}">${sgEsc(label)}</button>`;
}
function sgSec(title, body){ return `<section class="sgsec"><h3>${sgEsc(title)}</h3>${body}</section>`; }
function sgDecisionHtml(d){
  const dec = d.decision;
  if (!dec) return sgSec("Decision", `<p class="sgquiet">No department was chosen for this task.</p>`);
  const c = dec.choice || {};
  const named = (dec.final_ref && (d.departments || []).filter(x => x.ref === dec.final_ref)[0]) || (dec.result_ref && (d.departments || []).filter(x => x.ref === dec.result_ref)[0]);
  const verb = SG_CHOICE[dec.final_action] || dec.final_action;
  const what = dec.final_action === "none" ? verb : verb + " " + (named ? named.name : (dec.final_ref || dec.result_ref || c.name || "a department"));
  const by = dec.decided_by === "agent" ? "decided by agent" : "by the rule" + ((dec.overrides || []).length ? ": " + dec.overrides.map(o => o.note).join("; ") : "");
  const cands = (dec.considered || []).map(ref => {
    const row = (d.departments || []).filter(x => x.ref === ref)[0];
    return `<li>${sgOpenBtn(row ? row.name : ref, { kind: "dept_page", ref }, "link")}</li>`;
  }).join("");
  return sgSec("Decision", `<p><b>${sgEsc(what)}</b>${dec.held ? " \u00b7 held" : ""}</p><p>${sgEsc(c.reason || "")}</p>
    <p class="sgquiet">Confidence: ${sgEsc(c.confidence || "")} \u00b7 ${sgEsc(by)}</p>${cands ? `<p class="sgquiet">Looked at</p><ul class="sgplain">${cands}</ul>` : ""}`);
}
function sgDeptsHtml(d){
  const rows = (d.departments || []).map(x => `<div class="sgcard"><b>${sgEsc(x.name)}</b> <span class="sgquiet">${sgEsc(SG_WORD[x.state === "not_started" ? "idle" : x.state === "stopped" ? "off" : x.state] || x.state)}</span>
    <p class="sgquiet">${sgEsc(x.goal || "")}</p>${sgOpenBtn("Open", { kind: "dept_page", ref: x.ref })}</div>`).join("");
  return sgSec("Departments", rows || `<p class="sgquiet">None used.</p>`);
}
function sgChatsHtml(d, workers){
  const rows = (d.chats || []).filter(c => !!workers === (c.role === "worker")).map(c => {
    const alt = c.alt_open || (c.open && c.open.kind === "session" ? c.open : null);
    return `<div class="sgcard"><b>${sgEsc(c.label)}</b> <span class="sgquiet">${sgEsc(SG_ROLE[c.role] || c.role)}${c.live ? " \u00b7 Working" : ""}</span>
      <div class="sgacts">${sgOpenBtn("Open", c.open)}${alt ? sgOpenBtn("Open in Chats", alt) : ""}</div></div>`;
  }).join("");
  return sgSec(workers ? "Workers" : "Chats", rows || `<p class="sgquiet">${workers ? "No worker." : "No chats."}</p>`);
}
function sgCostsHtml(d){
  const rows = (d.costs || []).map(c => `<tr><td>${sgEsc(SG_COST[c.role] || c.role)}</td><td>about $${sgEsc(Number(c.usd).toFixed(2))}</td></tr>`).join("");
  return sgSec("Costs", rows ? `<table class="sgtable">${rows}<tr><th>Total</th><th>about $${sgEsc(Number(d.total_usd || 0).toFixed(2))}</th></tr></table>` : `<p class="sgquiet">Nothing spent yet.</p>`);
}
function sgTimelineHtml(d){
  const rows = (d.timeline || []).map(t => `<li><span class="sgwhen">${sgEsc(sgWhen(t.at))}</span> ${SG_BY[t.by] ? `<b>${sgEsc(SG_BY[t.by])}</b> ` : ""}${sgEsc(t.text)}</li>`).join("");
  return sgSec("Timeline", rows ? `<ol class="sgtl">${rows}</ol>` : `<p class="sgquiet">Nothing yet.</p>`);
}
function sgHeaderHtml(d){
  const t = d.task, word = { draft: "Draft", brief_confirm: "Draft", running: "Working", queued: "Waiting", paused: "Waiting", blocked: "Blocked", done: "Done", failed: "Failed", stopped: "Stopped" }[t.state] || t.state;
  return `<header class="sgtaskhead"><h2>${sgEsc(t.objective)}</h2><p class="sgquiet">${sgEsc(word)} \u00b7 ${sgEsc(t.template)} \u00b7 ${
    sgEsc(t.executor === "department" ? "run by a department" : "run by a worker")} \u00b7 Started ${sgEsc(sgWhen(t.created))} \u00b7 Updated ${sgEsc(sgWhen(t.updated))} \u00b7 Turn ${sgEsc(t.turns_used)}</p></header>`;
}

/* ── the screen ─────────────────────────────────────────────────────────────────────────────────────────────────────────── */
function sgHtml(){
  const st = sgState(), focus = sgFocus();
  const crumb = `<nav class="sgcrumb" aria-label="Where you are"><button type="button" class="btn sgbtn link" data-sghome="1">Home</button><span aria-hidden="true"> \u203a </span>${
    focus ? `<button type="button" class="btn sgbtn link" data-sgleave="1">Shadow graph</button><span aria-hidden="true"> \u203a </span><span>Task</span>` : `<span>Shadow graph</span>`}</nav>`;
  const g = sgGraph();
  const ctl = focus
    ? `<button type="button" class="btn sgbtn" data-sgleave="1">Back to the graph</button>`
    : `<button type="button" class="btn sgbtn" data-sgdone="1" aria-pressed="${st.includeDone ? "true" : "false"}">Include finished</button>`;
  const fit = `<button type="button" class="btn sgbtn" data-sgfit="1" aria-pressed="${st.fit ? "true" : "false"}">Fit</button>`;
  const head = `<div class="sghead">${crumb}<span class="sgsum" role="status">${g ? sgEsc(sgSummary(g)) : ""}</span><span class="sgctl">${ctl}${fit}</span></div>`;
  if (st.dark) return `<div class="sgwrap">${head}<div class="zero"><h4>Shadow is not enabled</h4><p>Turn it on in Settings to see how its work connects.</p></div></div>`;
  if (!g){
    if (st.err) return `<div class="sgwrap">${head}<div class="zero"><h4>Shadow graph</h4><p>Could not read Shadow's tasks. <button type="button" class="btn" data-sgretry="1">Retry</button></p></div></div>`;
    return `<div class="sgwrap">${head}<div class="sgskel" role="status" aria-busy="true"><div class="sgskelbar"></div><div class="sgskelbar"></div><div class="sgskelbar"></div>
      <p class="sgquiet">Reading Shadow's tasks\u2026</p></div></div>`;
  }
  const bare = (g.nodes || []).filter(n => n.kind !== "shadow").length === 0;
  if (bare && !focus) return `<div class="sgwrap">${head}${sgBanner()}<div class="zero"><h4>Shadow graph</h4><p>No tasks yet. Tell Shadow what you need on Home.
    <button type="button" class="btn" data-sghome="1">Home</button></p></div></div>`;
  const draw = sgPhone() ? sgListHtml(g) : sgGraphHtml(g);
  const legend = `<div class="sglegend" aria-label="Key">Key: <span>Task</span> <span>Department</span> <span>Goal</span> <span class="k-uses">uses (solid)</span>
    <span class="k-spawned">spawned (dashed, +)</span> <span class="k-held">held (dotted)</span></div>`;
  if (!focus) return `<div class="sgwrap">${head}${sgBanner()}${draw}${legend}</div>`;
  const d = sgData();
  return `<div class="sgwrap sgfocus">${head}${sgBanner()}${sgHeaderHtml(d)}<div class="sgcols"><div class="sgleft">${draw}${legend}</div><div class="sgright">${
    sgDecisionHtml(d)}${sgDeptsHtml(d)}${sgChatsHtml(d, false)}${sgChatsHtml(d, true)}${sgCostsHtml(d)}${sgTimelineHtml(d)}</div></div></div>`;
}

if (typeof SCREENS !== "undefined"){
  SCREENS.shadowgraph = () => {
    const st = sgState(), s = sgS();
    ensureShadowGraphTicker();
    if (s.shadowGraphFocus === undefined){
      let saved = null;
      try { saved = (typeof lsGet === "function") ? lsGet(SG_KEY, null) : null; } catch (e) {}
      s.shadowGraphFocus = (typeof saved === "string" && /^m-[0-9a-f]{12}$/.test(saved)) ? saved : null;
    }
    if (!_sgRead && (!st.loaded || st.forFocus !== sgFocus() || (sgFocus() && !sgData()))) sgLoad();
    return sgHtml();
  };
}
if (typeof TITLES !== "undefined") TITLES.shadowgraph = ["Shadow graph", "how Shadow's work connects"];

/* ── opening: every node, tag and button lands on an existing screen ───────────────────────────────────────────────────── */
function sgOpen(o){
  if (!o || !o.kind || o.kind === "none" || !o.ref) return false;
  const s = sgS();
  try {
    switch (o.kind){
      case "task":
        if (typeof shadowRouteDeepLink === "function") shadowRouteDeepLink("sutra://shadow/" + o.ref);
        else { s.shadowTaskSel = o.ref; if (typeof openScreen === "function") openScreen("shadow"); }
        return true;
      case "conversation":
        s.shadowChat = o.ref;
        s.shadowTaskSel = (typeof SH_NO_TASK !== "undefined") ? SH_NO_TASK : "__none__";
        if (typeof lsSet === "function") lsSet("sutra.shadow.conv", o.ref);
        if (typeof goDest === "function") goDest("focus");
        if (typeof openScreen === "function") openScreen("shadow");
        return true;
      case "session":
        if (typeof shadowOpenSessionPane === "function") shadowOpenSessionPane(o.ref);
        return true;
      case "dept_page":
        /* o2OpenDept only selects the row: the Org screen is opened first, or the graph stays where it was (found in the P5 walk) */
        if (typeof goDest === "function") goDest("org");
        if (typeof window !== "undefined" && typeof window.o2OpenDept === "function") window.o2OpenDept(o.ref);
        else if (typeof openScreen === "function" && typeof SCREENS !== "undefined" && SCREENS.org2) openScreen("org2");
        return true;
      case "goal":
        if (typeof openGoal === "function") openGoal(o.ref);
        return true;
    }
  } catch (e) {}
  return false;
}
function sgOpenGraph(mid){
  sgSetFocus(mid || null);
  const st = sgState();
  st.detail = null; st.forFocus = undefined;
  if (typeof openScreen === "function") openScreen("shadowgraph");
  sgLoad(true);
  if (typeof render === "function") render();
}
/* the Details jump (chat strip, Home): focus a task and open the screen; Home's missions are read once when none are there yet */
function sgDetailJump(mid){
  const s = sgS();
  if (!mid) return;
  s.shadowGraphFocus = mid;
  if (typeof lsSet === "function") lsSet(SG_KEY, mid);
  const st = sgState();
  st.cur = null; st.tip = null; st.pin = null; st.detail = null; st.forFocus = undefined;
  if (!(s.shadowMissions || []).length && typeof loadShadowHome === "function") { try { loadShadowHome(true); } catch (e) {} }
  if (typeof openScreen === "function") openScreen("shadowgraph");
  if (typeof render === "function") render();
}
/* which mission does this chat belong to (its task chat, its Sutra id, or the chat it drives)? */
function sgMissionForSession(sess){
  if (!sess) return null;
  const ids = [sess.id, sess.sutra_id].filter(Boolean);
  const hit = (sgS().shadowMissions || []).filter(m => m && m.id && ids.some(i => i === m.task_chat_session || i === m.task_chat || i === m.target_session));
  return hit.length ? hit[hit.length - 1].id : null;
}

/* ── events: one delegated set ─────────────────────────────────────────────────────────────────────────────────────────── */
const SG_KEYS = ["sgnode", "sgtag", "sgk", "sgdone", "sgfit", "sgleave", "sghome", "sgretry", "shdetail", "shgraph"];
function sgFind(t){
  for (let el = t, i = 0; el && i < 8; el = el.parentNode, i++){
    const d = el.dataset;
    if (d && SG_KEYS.some(k => d[k] !== undefined)) return { el, d };
  }
  return null;
}
function sgInHost(t){
  for (let el = t, i = 0; el && i < 12; el = el.parentNode, i++){ if (el.dataset && el.dataset.sghost !== undefined) return true; }
  return false;
}
/* does this subtree hold the graph node or tag that has the keyboard focus? (shadowHoldsKeep asks) */
function sgHoldsFocus(el){
  if (typeof document === "undefined" || !document.activeElement || !el || !el.contains) return false;
  const a = document.activeElement, d = a.dataset;
  if (!d || (d.sgnode === undefined && d.sgtag === undefined)) return false;
  try { return el === a || el.contains(a); } catch (e) { return false; }
}
function sgFocusCur(){
  const st = sgState();
  if (typeof document === "undefined" || !document.querySelector || !st.cur) return;
  const el = document.querySelector('[data-sgnode="' + st.cur + '"]');
  if (el && el.focus) { try { el.focus({ preventScroll: false }); } catch (e) {} }
}
function sgNeighbour(key){
  const g = sgGraph(), st = sgState();
  if (!g || !st.cur) return null;
  const nodes = g.nodes || [], cur = nodes.filter(n => n.id === st.cur)[0];
  if (!cur) return null;
  if (key === "ArrowRight"){ const e = (g.edges || []).filter(x => x.source === cur.id)[0]; return e ? e.target : null; }
  if (key === "ArrowLeft"){ const e = (g.edges || []).filter(x => x.target === cur.id)[0]; return e ? e.source : null; }
  const col = nodes.filter(n => n.col === cur.col).sort((a, b) => a.row - b.row), i = col.indexOf(cur);
  const j = key === "ArrowDown" ? i + 1 : i - 1;
  return col[j] ? col[j].id : null;
}
function sgTaskOf(id){
  const g = sgGraph();
  if (!g || !id) return null;
  if (id.indexOf("task:") === 0) return id.slice(5);
  const m = /^(?:tchat|worker):(m-[0-9a-f]{12})$/.exec(id);
  if (m) return m[1];
  const e = (g.edges || []).filter(x => x.target === id && x.source.indexOf("task:") === 0)[0];
  return e ? e.source.slice(5) : null;
}
function sgKeydown(ev){
  const f = sgFind(ev.target);
  if (!f || f.d.sgnode === undefined || !sgInHost(ev.target)) return false;
  const st = sgState(), k = ev.key;
  st.cur = f.d.sgnode;
  if (k === "ArrowRight" || k === "ArrowLeft" || k === "ArrowUp" || k === "ArrowDown"){
    const to = sgNeighbour(k);
    if (ev.preventDefault) ev.preventDefault();
    if (to){ st.cur = to; st.tip = to; sgRepaint(); sgFocusCur(); }
    return true;
  }
  if (k === " " || k === "Spacebar" || k === "i"){
    if (ev.preventDefault) ev.preventDefault();
    st.pin = st.pin === st.cur ? null : st.cur;
    sgRepaint();
    return true;
  }
  if (k === "f"){
    const mid = sgTaskOf(st.cur);
    if (mid){ if (ev.preventDefault) ev.preventDefault(); sgOpenGraph(mid); }
    return true;
  }
  if (k === "Escape"){
    if (st.pin || st.tip){ st.pin = null; st.tip = null; sgRepaint(); }
    else if (sgFocus()) sgOpenGraph(null);
    return true;
  }
  return false;
}
function sgClick(ev){
  const f = sgFind(ev.target);
  if (!f) return false;
  const d = f.d, st = sgState();
  if (d.shdetail !== undefined){ sgDetailJump(d.shdetail); return true; }
  if (d.shgraph !== undefined){ sgOpenGraph(null); return true; }
  if (d.sgnode !== undefined){
    st.cur = d.sgnode;
    sgOpen({ kind: d.sgk, ref: d.sgr });
    return true;
  }
  if (d.sgtag !== undefined){ st.pin = st.pin === "edge:" + d.sgtag ? null : "edge:" + d.sgtag; sgRepaint(); return true; }
  if (d.sgk !== undefined){ sgOpen({ kind: d.sgk, ref: d.sgr }); return true; }
  if (d.sgdone !== undefined){ st.includeDone = !st.includeDone; sgLoad(true); sgRepaint(); return true; }
  if (d.sgfit !== undefined){ st.fit = !st.fit; sgRepaint(); return true; }
  if (d.sgleave !== undefined){ sgOpenGraph(null); return true; }
  if (d.sghome !== undefined){
    if (typeof goDest === "function") goDest("focus");
    if (typeof openScreen === "function") openScreen("shadow");
    if (typeof render === "function") render();
    return true;
  }
  if (d.sgretry !== undefined){ sgLoad(true); return true; }
  return false;
}
function sgHover(ev){
  if (!sgOnScreen()) return false;
  const f = sgFind(ev.target), st = sgState();
  let want = null;
  if (f && f.d.sgnode !== undefined) want = f.d.sgnode;
  else if (f && f.d.sgtag !== undefined) want = "edge:" + f.d.sgtag;
  if (want === st.tip) return false;
  if (!want && !sgInHost(ev.target)) { if (!st.tip) return false; }
  st.tip = want;
  sgRepaint();
  return true;
}
if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("click", (ev) => { sgClick(ev); });
  document.addEventListener("keydown", (ev) => { sgKeydown(ev); });
  document.addEventListener("keyup", (ev) => { if (ev.key === " " && sgFind(ev.target) && ev.preventDefault) ev.preventDefault(); });
  document.addEventListener("mouseover", (ev) => { sgHover(ev); });
  document.addEventListener("focusin", (ev) => { sgHover(ev); });
}
if (typeof window !== "undefined" && window.addEventListener){
  let was = null;
  window.addEventListener("resize", () => { const p = sgPhone(); if (was !== null && p !== was && sgOnScreen()) sgRepaint(); was = p; });
}
