/* 17-agents.js — the Agents destination, and its first agent: the SEO Writer.
 *
 * What this is. A screen where an agent works in front of you: it names each step
 * before it takes it, stops before spending credits, and puts every draft in a panel
 * you can edit before it carries on. The engine is seo_agent/ on the server; this
 * file only draws what the run folder already says and posts your answers back.
 *
 * How it coexists with render(). render() rewrites #panes wholesale and #scBody when
 * a screen's HTML changes, so SCREENS.agents returns a CONSTANT shell and a
 * MutationObserver notices the empty shell and mounts into it. Every piece of state
 * lives in S.ag, never in the DOM, so a remount costs nothing: the transcript scroll
 * offset and the composer draft come back exactly as they were.
 *
 * Pure renderers are top-level `ag*` functions so test_agents.js can slice them the
 * way test_governance.js slices gvLog(). Every string goes through agEsc().
 */

/* ── constants ─────────────────────────────────────────────────────────────── */
const AG_API = "/api/agents/seo";
const AG_STAGES = [["topic", "Topic"], ["research", "Research"], ["blueprint", "Blueprint"], ["draft", "Draft"]];
const AG_VIEW_TITLE = { topic_list: "Topic ideas", research_brief: "Research brief",
                        blueprint: "Article blueprint", article: "The draft" };
const AG_POLL_LIVE_MS = 1000;
const AG_POLL_IDLE_MS = 4000;
const AG_MAX_SUBS = 8;

/* ── tiny helpers ──────────────────────────────────────────────────────────── */
function agEsc(x){
  return String(x == null ? "" : x).replace(/[&<>"']/g, function (m) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
  });
}
function agMd(text){
  if (typeof mdHtml === "function") { try { return mdHtml(String(text || "")); } catch (e) {} }
  return "<div class=\"md-p\">" + agEsc(text).replace(/\n\n+/g, "</div><div class=\"md-p\">") + "</div>";
}
function agDur(ms){
  ms = Math.max(0, ms | 0);
  if (ms < 1000) return "<1s";
  const s = Math.round(ms / 1000);
  if (s < 60) return s + "s";
  const m = Math.floor(s / 60), r = s % 60;
  if (m < 60) return m + "m " + (r < 10 ? "0" : "") + r + "s";
  const h = Math.floor(m / 60);
  return h + "h " + (m % 60) + "m";
}
function agMs(t){
  if (!t) return NaN;
  const v = Date.parse(t);
  return isNaN(v) ? NaN : v;
}
function agNum(n){
  if (n == null || n === "" || isNaN(Number(n))) return "—";
  return Number(n).toLocaleString("en-US");
}
function agAgo(iso){
  const ms = agMs(iso); if (isNaN(ms)) return "";
  const d = Date.now() - ms;
  if (d < 60000) return "just now";
  if (d < 3600000) return Math.floor(d / 60000) + "m ago";
  if (d < 86400000) return Math.floor(d / 3600000) + "h ago";
  return Math.floor(d / 86400000) + "d ago";
}
function agWords(md){ return String(md || "").trim().split(/\s+/).filter(Boolean).length; }
function agDomain(url){
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return String(url || ""); }
}

/* Markdown blocks, split EXACTLY like editing/edit_block.py: paragraphs on blank
   lines, fences kept whole, ids p0..pN. The server addresses an edit by this id, so a
   splitter that disagreed by one would rewrite the wrong paragraph. */
function agBlocks(md){
  const lines = String(md || "").split(/(?<=\n)/);
  const out = []; let cur = [], kind = null, fence = null;
  for (const line of lines){
    const stripped = line.trim();
    let self;
    if (fence !== null){ self = "block"; if (stripped.indexOf(fence) === 0) fence = null; }
    else if (/^\s*(```|~~~)/.test(line)){ fence = stripped.slice(0, 3); self = "block"; }
    else self = stripped === "" ? "gap" : "block";
    if (kind === null) kind = self;
    if (self !== kind){ out.push([kind, cur.join("")]); cur = []; kind = self; }
    cur.push(line);
  }
  if (cur.length) out.push([kind, cur.join("")]);
  return out.filter(p => p[0] === "block").map(p => p[1]);
}

/* ── state ─────────────────────────────────────────────────────────────────── */
function agS(){
  if (typeof S === "undefined") return null;
  if (!S.ag) S.ag = {
    view: "chat",                 /* chat | knowledge | memory | library | tools | connections */
    chats: null, chatId: null, chat: null,   /* chat = {chat, messages, runs} */
    events: {}, cursors: {},      /* per run_id */
    panel: null,                  /* {run_id, name, view, data, loading, error} */
    autoOpened: null,             /* the waiting call_id whose panel already opened itself */
    picked: null, collapsed: {}, draft: "", scroll: null, stick: true,
    health: null, knowledge: null, memory: null, library: null, tools: null, conns: null,
    bpEdit: null, artEdit: null, lastEdit: null, busy: false, error: null,
    compForm: null, kwForm: null, libOpen: null, detailOpen: {},
  };
  return S.ag;
}
function agLiveRun(){
  const a = agS(); if (!a || !a.chat) return null;
  const runs = a.chat.runs || [];
  for (let i = runs.length - 1; i >= 0; i--){
    if (runs[i].status === "running" || runs[i].status === "waiting") return runs[i];
  }
  return null;
}
function agLastRun(){
  const a = agS(); if (!a || !a.chat) return null;
  const runs = a.chat.runs || [];
  return runs.length ? runs[runs.length - 1] : null;
}

/* ── projections (pure) ────────────────────────────────────────────────────── */

/* Events → the entries the run log draws. Nothing is invented: every field traces
   to an event field, and a step's body is the sentence the model wrote before it
   acted (a `note` or a `message`), the way Unify shows it. */
function agStepsFromEvents(events, state){
  const out = [], byId = {};
  let lead = null, lastStep = null, lastWait = null;
  const status = state && state.status;
  const flushLead = () => { if (lead){ out.push({ kind: "prose", text: lead.text, t: lead.t }); lead = null; } };
  for (const ev of (events || [])){
    switch (ev.type){
      case "note":
        flushLead(); lead = { text: ev.label || "", t: ev.t, note: true }; break;
      case "message":
        flushLead(); lead = { text: ev.text || "", t: ev.t }; break;
      case "step_started": {
        const e = { kind: "step", id: ev.id, label: ev.label || ev.tool || "Step", tool: ev.tool || "",
                    state: "run", lead: lead ? lead.text : "", leadNote: !!(lead && lead.note),
                    subs: [], t: ev.t, ms: null, summary: "", reason: "", detail: "", recovering: false };
        lead = null; byId[ev.id] = e; lastStep = e; out.push(e); break;
      }
      case "substep_finished": {
        const p = (ev.parent && byId[ev.parent]) || lastStep;
        if (p) p.subs.push({ label: ev.label || "", note: ev.note || "", ms: ev.ms });
        else out.push({ kind: "note", text: ev.label || "", t: ev.t });
        break;
      }
      case "step_finished": {
        const e = byId[ev.id];
        if (e){ e.state = "ok"; e.ms = ev.ms; e.summary = ev.summary || ""; }
        break;
      }
      case "step_failed": {
        const e = ev.id && byId[ev.id];
        if (e){ e.state = "bad"; e.ms = ev.ms; e.reason = ev.reason || ""; e.detail = ev.detail || ""; e.recovering = !!ev.recovering; }
        else { flushLead(); out.push({ kind: "failed", label: ev.label || "Run", reason: ev.reason || "",
                                       detail: ev.detail || "", recovering: !!ev.recovering, t: ev.t }); }
        break;
      }
      case "waiting": {
        flushLead();
        let e;
        if (ev.kind === "question")
          e = { kind: "ask", question: ev.question || "", why: ev.why || "", options: ev.options || [], t: ev.t };
        else if (ev.kind === "approval")
          e = { kind: "approval", tool: ev.tool || "", question: ev.question || "", why: ev.why || "",
                cost: ev.cost_credits || 0, mins: ev.est_minutes || 0, options: ev.options || [], t: ev.t };
        else
          e = { kind: "artifact", artifact: ev.artifact || "", view: ev.view || "article",
                prompt: ev.prompt || "", t: ev.t };
        e.live = true; e.answer = null; e.call_id = ev.call_id || null;
        lastWait = e; out.push(e); break;
      }
      case "resumed": {
        if (lastWait){
          lastWait.live = false;
          lastWait.answer = ev.answer || ev.note || (ev.by === "user" ? "answered" : "");
          if (lastWait.kind === "approval")
            lastWait.decision = ev.approved === true ? "approved" : ev.approved === false ? "declined"
              : /^approved/.test(ev.note || "") ? "approved" : /^declined/.test(ev.note || "") ? "declined" : "";
          lastWait = null;
        }
        break;
      }
      case "memory_saved": flushLead(); out.push({ kind: "mem", text: ev.text || "", t: ev.t }); break;
      case "edited": flushLead(); out.push({ kind: "edited", artifact: ev.artifact || "", block: ev.block || "",
                                             instruction: ev.instruction || "", t: ev.t }); break;
      case "saved_to_library": flushLead(); out.push({ kind: "saved", title: ev.title || "", t: ev.t }); break;
      case "stopped": flushLead(); out.push({ kind: "stopped", t: ev.t }); break;
      default: break;
    }
  }
  flushLead();
  /* a step still "running" in a run that is no longer alive was interrupted */
  if (status && status !== "running" && status !== "waiting"){
    for (const e of out){
      if (e.kind === "step" && e.state === "run"){ e.state = "bad"; e.reason = e.reason || "Interrupted before it finished."; }
      if ((e.kind === "ask" || e.kind === "approval" || e.kind === "artifact") && e.live){ e.live = false; e.answer = e.answer || "left unanswered"; }
    }
  }
  return out;
}

/* The header line of a run block: live or done, elapsed, step count. Elapsed is
   measured between the first and last event (or now while live), never estimated. */
function agRunSummary(events, state, now){
  const evs = events || [];
  const live = !!state && (state.status === "running" || state.status === "waiting");
  const start = agMs(state && state.started_at) || (evs.length ? agMs(evs[0].t) : NaN);
  const last = evs.length ? agMs(evs[evs.length - 1].t) : NaN;
  const end = live ? (now || Date.now()) : (isNaN(last) ? start : Math.max(last, agMs(state && state.updated_at) || 0));
  const steps = evs.filter(e => e.type === "step_started").length;
  const waiting = !!state && state.status === "waiting";
  return { live, waiting, steps, elapsedMs: (isNaN(start) || isNaN(end)) ? 0 : Math.max(0, end - start),
           status: state ? state.status : "" };
}

/* Which of the four stages is done, current, or ahead. */
function agStageOf(state){
  const cur = state && state.stage || "topic";
  const idx = Math.max(0, AG_STAGES.findIndex(s => s[0] === cur));
  const done = state && state.status === "done";
  return AG_STAGES.map((s, i) => ({ id: s[0], label: s[1],
    state: done ? "done" : i < idx ? "done" : i === idx ? (state && state.status === "waiting" ? "wait" : "cur") : "todo" }));
}

/* ── renderers (pure, return HTML strings) ─────────────────────────────────── */

const AG_ICON = {
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true"><path d="M5 12.5l4.2 4.2L19 7"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  ask: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M9 9.5a3 3 0 115.2 2c-1 .9-2.2 1.4-2.2 3"/><circle cx="12" cy="18" r=".8" fill="currentColor"/></svg>',
  doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 3.5h8l4 4v13H6z"/><path d="M14 3.5v4h4M9 12h6M9 16h6"/></svg>',
  coin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path d="M12 7.5v9M9.5 10h3.5a1.5 1.5 0 010 3H10a1.5 1.5 0 000 3h4"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1.1 5.8L12 16.8l-5.3 2.8 1.1-5.8L3.5 9.7l5.9-.8z"/></svg>',
  arrow: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
  chev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>',
  pencil: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M4 20h4l10.5-10.5a2.1 2.1 0 00-3-3L5 17v3z"/><path d="M13.5 6.5l4 4"/></svg>',
  up: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6"/></svg>',
  down: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6"/></svg>',
  plus: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
  spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></svg>',
};

function agGlyph(e){
  if (e.kind === "step") return e.state === "ok" ? AG_ICON.check : e.state === "bad" ? AG_ICON.x : "";
  if (e.kind === "ask") return AG_ICON.ask;
  if (e.kind === "approval") return AG_ICON.coin;
  if (e.kind === "artifact") return AG_ICON.doc;
  if (e.kind === "mem") return AG_ICON.star;
  if (e.kind === "failed" || e.kind === "stopped") return AG_ICON.x;
  return "";
}

function agSubsHtml(subs, stepId, open){
  if (!subs || !subs.length) return "";
  const show = open ? subs : subs.slice(-AG_MAX_SUBS);
  const hidden = subs.length - show.length;
  return `<div class="ag-subs">
    ${hidden > 0 ? `<button class="ag-more" type="button" data-ag="more" data-arg="${agEsc(stepId)}">${hidden} earlier …</button>` : ""}
    ${show.map(s => `<div class="trow ok"><span class="tstate" aria-hidden="true"></span>
      <span class="tname" title="${agEsc(s.label)}">${agEsc(s.label)}</span>
      <span class="tsum" title="${agEsc(s.note)}">${agEsc(s.note)}</span>
      ${s.ms ? `<span class="tverdict">${agEsc(agDur(s.ms))}</span>` : ""}</div>`).join("")}
  </div>`;
}

function agChipsHtml(options, live, chosen, action, arg){
  const opts = (options || []).filter(o => o && o.label);
  if (!opts.length) return "";
  return `<div class="ag-chips">${opts.map(o => {
    const rec = !!o.recommended;
    const isChosen = chosen && String(chosen).indexOf(o.label) !== -1;
    return `<button class="ag-chip ${rec ? "rec" : ""} ${isChosen ? "chosen" : ""}" type="button"
      ${live ? `data-ag="${agEsc(action)}" data-arg="${agEsc(arg)}" data-label="${agEsc(o.label)}"` : "disabled"}
      title="${agEsc(o.note || "")}">${agEsc(o.label)}${rec ? " <small>(Recommended)</small>" : ""}</button>`;
  }).join("")}</div>`;
}

function agEntryHtml(e, ctx){
  ctx = ctx || {};
  const open = !!(ctx.detailOpen && ctx.detailOpen[e.id || e.t]);
  switch (e.kind){
    case "step": {
      const cls = e.state;
      const verdict = e.state === "run" ? "" : e.ms != null ? `<span class="ms">${agEsc(agDur(e.ms))}</span>` : "";
      return `<div class="ag-step ${cls}" data-step="${agEsc(e.id)}">
        <span class="ag-glyph" aria-hidden="true">${agGlyph(e)}</span>
        <div class="ag-title">${agEsc(e.label)}${verdict}${e.state === "bad" && e.recovering ? `<span class="pill p-warn">trying another way</span>` : ""}</div>
        ${e.lead ? `<div class="ag-body ${e.leadNote ? "" : "md"}">${e.leadNote ? agEsc(e.lead) : agMd(e.lead)}</div>` : ""}
        ${e.state === "bad" && e.reason ? `<div class="ag-body" style="color:var(--block)">${agEsc(e.reason)}</div>` : ""}
        ${e.state === "ok" && e.summary && !e.subs.length ? `<div class="ag-body">${agEsc(e.summary)}</div>` : ""}
        ${agSubsHtml(e.subs, e.id, open)}
        ${e.detail ? `<button class="ag-more" type="button" data-ag="detail" data-arg="${agEsc(e.id)}">${open ? "Hide" : "Show"} the error detail</button>${open ? `<pre class="ag-detail">${agEsc(e.detail)}</pre>` : ""}` : ""}
      </div>`;
    }
    case "prose":
      return `<div class="ag-step quiet"><span class="ag-glyph" aria-hidden="true"></span><div class="ag-prose md">${agMd(e.text)}</div></div>`;
    case "note":
      return `<div class="ag-step quiet"><span class="ag-glyph" aria-hidden="true"></span><div class="ag-note">${agEsc(e.text)}</div></div>`;
    case "ask":
      return `<div class="ag-step ask"><span class="ag-glyph" aria-hidden="true">${agGlyph(e)}</span>
        <div class="ag-title">Asked you a question</div>
        <div class="ag-card ${e.live ? "live" : ""}">
          <div class="q">${agEsc(e.question)}</div>
          ${e.why ? `<div class="why">${agEsc(e.why)}</div>` : ""}
          ${agChipsHtml(e.options, e.live, e.answer, "choose", e.call_id || "")}
          ${e.live ? `<div class="ag-hint">Pick one, or type your own answer below.</div>`
                   : `<div class="ag-answer"><span>You said</span><b>${agEsc(e.answer || "")}</b></div>`}
        </div></div>`;
    case "approval": {
      const bits = [];
      if (e.cost) bits.push(`<b>${agEsc(e.cost)}</b> credits`);
      if (e.mins) bits.push(`about <b>${agEsc(e.mins)}</b> min`);
      return `<div class="ag-step ask"><span class="ag-glyph" aria-hidden="true">${agGlyph(e)}</span>
        <div class="ag-title">Asked before spending</div>
        <div class="ag-card ${e.live ? "live" : ""}">
          <div class="q">${agEsc(e.question)}</div>
          ${bits.length ? `<div class="ag-cost">${bits.join(" · ")}</div>` : ""}
          ${e.why ? `<div class="why">${agEsc(e.why)}</div>` : ""}
          ${e.live ? `<div class="ag-chips">
              <button class="ag-chip pri" type="button" data-ag="approve" data-arg="yes">Go ahead</button>
              <button class="ag-chip" type="button" data-ag="approve" data-arg="no">Not now</button>
            </div><div class="ag-hint">Nothing is spent until you say yes.</div>`
          : `<div class="ag-answer"><span>You said</span><b>${e.decision === "approved" ? "Go ahead" : e.decision === "declined" ? "Not now" : agEsc(e.answer || "")}</b></div>`}
        </div></div>`;
    }
    case "artifact": {
      const title = AG_VIEW_TITLE[e.view] || "Something to review";
      const isOpen = ctx.panel && ctx.panel.name === e.artifact && ctx.panel.run_id === ctx.run_id;
      return `<div class="ag-step art"><span class="ag-glyph" aria-hidden="true">${agGlyph(e)}</span>
        <div class="ag-title">Showed you: ${agEsc(title.toLowerCase())}</div>
        ${e.prompt ? `<div class="ag-body">${agEsc(e.prompt)}</div>` : ""}
        <button class="ag-artcard ${isOpen ? "open" : ""}" type="button" data-ag="open" data-arg="${agEsc(e.artifact)}" data-view="${agEsc(e.view)}" data-run="${agEsc(ctx.run_id || "")}">
          <span class="ai" aria-hidden="true">${AG_ICON.doc}</span>
          <span><span class="at">${agEsc(title)}</span><span class="as">${e.live ? "Waiting for you" : agEsc(e.answer || "reviewed")}</span></span>
          <span class="ac">${isOpen ? "Open" : "Review"} ${AG_ICON.arrow}</span>
        </button></div>`;
    }
    case "mem":
      return `<div class="ag-step mem"><span class="ag-glyph" aria-hidden="true">${agGlyph(e)}</span>
        <div class="ag-title">Saved a standing rule</div><div class="ag-body">${agEsc(e.text)}</div></div>`;
    case "edited":
      return `<div class="ag-step ok"><span class="ag-glyph" aria-hidden="true">${AG_ICON.check}</span>
        <div class="ag-title">You edited ${agEsc(e.artifact)} <span class="ms">${agEsc(e.block)}</span></div>
        <div class="ag-body">${agEsc(e.instruction)}</div></div>`;
    case "saved":
      return `<div class="ag-step ok"><span class="ag-glyph" aria-hidden="true">${AG_ICON.check}</span>
        <div class="ag-title">Saved to the Library</div><div class="ag-body">${agEsc(e.title)}</div></div>`;
    case "failed":
      return `<div class="ag-step bad"><span class="ag-glyph" aria-hidden="true">${AG_ICON.x}</span>
        <div class="ag-title">${agEsc(e.label)} failed${e.recovering ? `<span class="pill p-warn">trying another way</span>` : ""}</div>
        <div class="ag-body" style="color:var(--block)">${agEsc(e.reason)}</div>
        ${e.detail ? `<button class="ag-more" type="button" data-ag="detail" data-arg="${agEsc(e.t)}">${open ? "Hide" : "Show"} the error detail</button>${open ? `<pre class="ag-detail">${agEsc(e.detail)}</pre>` : ""}` : ""}
      </div>`;
    case "stopped":
      return `<div class="ag-step bad"><span class="ag-glyph" aria-hidden="true">${AG_ICON.x}</span>
        <div class="ag-title">Stopped</div><div class="ag-body">You stopped this run. Send a message to continue.</div></div>`;
    default: return "";
  }
}

function agRunHtml(run, events, ctx){
  ctx = ctx || {};
  const sum = agRunSummary(events, run, ctx.now);
  const entries = agStepsFromEvents(events, run);
  const collapsed = !!(ctx.collapsed && ctx.collapsed[run.run_id]);
  const head = sum.live
    ? `<span class="runstrip live"><span class="spark" aria-hidden="true">${AG_ICON.spark}</span><b class="shim">${sum.waiting ? "Waiting for you" : "Working"}</b> · ${agEsc(agDur(sum.elapsedMs))}</span>`
    : `<span class="ag-worked">${run.status === "failed" ? "Stopped with an error" : run.status === "stopped" ? "Stopped" : "Worked"} · ${agEsc(agDur(sum.elapsedMs))}</span>`;
  return `<div class="ag-turn" data-run="${agEsc(run.run_id)}">
    <div class="u">${agEsc(run.request || run.topic || "")}</div>
    <div class="ag-run">
      <div class="ag-runhead">${head}
        ${entries.length ? `<button class="ag-fold" type="button" data-ag="fold" data-arg="${agEsc(run.run_id)}" aria-expanded="${!collapsed}">${AG_ICON.chev} ${collapsed ? "Show" : "Hide"} steps <span class="n">${sum.steps}</span></button>` : ""}
        ${run.credits_spent ? `<span class="n">${agEsc(run.credits_spent)} credits</span>` : ""}
      </div>
      <div class="ag-steps" ${collapsed ? "hidden" : ""}>${entries.map(e => agEntryHtml(e, Object.assign({}, ctx, { run_id: run.run_id }))).join("")}</div>
      ${run.status === "failed" && run.error && !entries.some(e => e.kind === "failed") ? `<div class="ag-err">${agEsc(run.error)}</div>` : ""}
    </div></div>`;
}

function agStagesHtml(state){
  const st = agStageOf(state);
  return `<div class="ag-stages" role="list" aria-label="Where this article is">
    ${st.map((s, i) => `${i ? `<span class="ag-sep" aria-hidden="true">›</span>` : ""}<span class="ag-stage ${s.state}" role="listitem"><i aria-hidden="true"></i>${agEsc(s.label)}</span>`).join("")}
    <span class="sp">${state && state.credits_spent ? `<b>${agEsc(state.credits_spent)}</b> credits spent` : "no credits spent"}</span>
  </div>`;
}

function agHeroHtml(health, conns){
  const dfs = !!(health && health.dataforseo);
  const model = health ? health.model_provider : null;
  const plays = [
    ["Set up the agent for my site", "Index every page of your website and learn how you write. Runs once; everything else builds on it.",
     "Set up for my site: index example.com and learn how we write."],
    ["Suggest six topics we could own", "Studies one competitor's best pages and proposes six topics with an angle they have not taken.",
     "Suggest six topics from a competitor we could own."],
    ["Write an article about a topic I name", "Research, blueprint, then a full draft in your voice. You review at each of the four stops.",
     "Write an article about "],
  ];
  return `<div class="ag-hero">
    <h2>SEO Writer</h2>
    <p>Name a topic or ask for ideas. It studies your site, researches the keyword, builds a structure and writes the draft, stopping at four points for you to look, edit, or redirect. Anything that costs credits asks first.</p>
    <div class="ag-plays">${plays.map(p => `<button class="ag-play" type="button" data-ag="play" data-text="${agEsc(p[2])}">
      <span class="pi"><span class="pt">${agEsc(p[0])}</span><span class="pd">${agEsc(p[1])}</span></span><span class="go">Let's go ${AG_ICON.arrow}</span></button>`).join("")}</div>
    <div class="ag-setup">
      ${health && !model ? `<div class="note b"><b>No model is available.</b> The agent runs on the <code>claude</code> command line, billed to your Claude subscription. Open a terminal, run <code>claude</code> once and sign in, then come back.</div>` : ""}
      ${health && !dfs ? `<div class="note w"><b>Running on demo keyword data.</b> Search volumes and difficulty will not be real until DataForSEO is connected. <button class="btn" type="button" data-ag="view" data-arg="connections" style="margin-left:6px">Connect</button></div>` : ""}
    </div>
  </div>`;
}

function agSideHtml(a){
  const chats = a.chats || [];
  const h = a.health;
  const dotCls = !h ? "" : !h.model_provider ? "bad" : !h.dataforseo ? "warn" : "run";
  const status = !h ? "checking…" : !h.model_provider ? "no model available" : !h.dataforseo ? "demo keyword data" : "ready";
  const rows = [["knowledge", "Knowledge", AG_ICON.doc, null], ["memory", "Memory", AG_ICON.star, a.memory ? a.memory.active : null],
                ["library", "Library", AG_ICON.check, a.library ? a.library.length : null], ["tools", "Tools", AG_ICON.spark, null],
                ["connections", "Connections", AG_ICON.coin, null]];
  return `<div class="ag-agent">
      <div class="ag-mark" aria-hidden="true">S</div>
      <div style="min-width:0"><b>SEO Writer</b><span><i class="dot ${dotCls}" aria-hidden="true"></i>${agEsc(status)}</span></div>
    </div>
    <button class="newBtn" type="button" data-ag="new">${AG_ICON.plus} New chat</button>
    <div class="ag-sec">Recent</div>
    <div class="ag-chats">${chats.length ? chats.map(c => {
        const live = c.live || "";
        return `<button class="ag-chat" type="button" data-ag="chat" data-arg="${agEsc(c.id)}" aria-current="${a.view === "chat" && a.chatId === c.id}" title="${agEsc(c.title)} · ${agEsc(agAgo(c.updated_at))}">
          <span class="dot ${live === "running" ? "run" : live === "waiting" ? "wait" : "idle"}" aria-hidden="true"></span>
          <span class="t">${agEsc(c.title || "New chat")}</span></button>`;
      }).join("") : `<div class="ag-empty">No chats yet. Start one above.</div>`}</div>
    <ul class="nav">${rows.map(r => `<li><button type="button" data-ag="view" data-arg="${r[0]}" aria-current="${a.view === r[0]}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">${r[2].replace(/<svg[^>]*>|<\/svg>/g, "")}</svg>${r[1]}
      ${r[3] != null ? `<span class="ct">${agEsc(r[3])}</span>` : ""}
      ${r[0] === "connections" && h && !h.dataforseo ? `<span class="ct w">!</span>` : ""}</button></li>`).join("")}</ul>`;
}

function agComposerHtml(a){
  const live = agLiveRun();
  const running = live && live.status === "running";
  const waiting = live && live.status === "waiting";
  const w = waiting ? (live.waiting_on || {}) : null;
  const ph = running ? "Working… you can stop it, or wait."
    : waiting && w.kind === "approval" ? "Say no with a reason, or use the buttons above"
    : waiting && w.kind === "artifact" ? "Ask for changes, or approve in the panel"
    : waiting ? "Type your answer, or pick an option above"
    : a.chat ? "Ask for another article, or give feedback" : "Name a topic, or ask for ideas";
  const state = running ? `<span class="ag-cstate"><i class="dot run"></i>the agent is working · ${agEsc(live.current_step ? live.current_step.replace(/_/g, " ") : live.stage)}</span>`
    : waiting ? `<span class="ag-cstate"><i class="dot wait"></i>waiting for you</span>` : "";
  return `${state}
    <textarea data-agask rows="1" aria-label="Message the SEO Writer" placeholder="${agEsc(ph)}" ${running ? "disabled" : ""}></textarea>
    ${running ? `<button class="send stop" type="button" data-ag="stop" aria-label="Stop this run" title="Stop — the run halts after the current step"><svg width="10" height="10" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor"/></svg></button>`
             : `<button class="send" type="button" data-ag="send" aria-label="Send"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg></button>`}`;
}

function agTranscriptHtml(a){
  if (!a.chat || !(a.chat.runs || []).length) return agHeroHtml(a.health, a.conns);
  const ctx = { collapsed: a.collapsed, panel: a.panel, detailOpen: a.detailOpen, now: Date.now() };
  return (a.chat.runs || []).map(r => agRunHtml(r, a.events[r.run_id] || [], ctx)).join("");
}

/* ── the four artifact views ───────────────────────────────────────────────── */

function agTopicListHtml(data, picked){
  const topics = (data && data.topics) || [];
  if (!topics.length) return `<div class="zero"><h4>No topics yet</h4><p>The list is empty.</p></div>`;
  const demo = !!(data && data.demo);
  return `${data && data.competitor ? `<p style="margin:0 0 12px;color:var(--muted);font-size:12px">From <b style="color:var(--ink)">${agEsc(data.competitor)}</b>'s best pages${data.competitor_keywords_read ? `, ${agEsc(data.competitor_keywords_read)} keywords read` : ""}. ${demo ? "Volumes are demo numbers." : ""}</p>` : ""}
    <div role="radiogroup" aria-label="Topic ideas">${topics.map(t => `<button class="ag-topic" type="button" role="radio" aria-checked="${picked === t.id}" data-ag="pick" data-arg="${agEsc(t.id)}">
      <span class="rd" aria-hidden="true"></span>
      <span class="ti"><span class="tt">${agEsc(t.topic)}</span>
        <span class="ta">${agEsc(t.angle || "")}</span>
        <span class="tm">${t.sparked_by ? `<span class="pill p-mut">from “${agEsc(t.sparked_by)}”</span>` : ""}
          ${t.est_volume != null ? `<span class="pill ${demo ? "p-warn" : "p-acc"}">${agEsc(agNum(t.est_volume))}/mo</span>` : ""}
          ${t.est_difficulty != null ? `<span class="pill p-mut">difficulty ${agEsc(t.est_difficulty)}</span>` : ""}</span>
        ${t.why_us ? `<span class="tw">Why us: ${agEsc(t.why_us)}</span>` : ""}</span>
    </button>`).join("")}</div>`;
}

function agResearchHtml(r){
  if (!r) return `<div class="zero"><h4>Nothing to show</h4></div>`;
  const pk = r.primary_keyword || {};
  const demo = !!r.demo;
  return `<div class="ag-kw">${agEsc(pk.keyword || r.topic || "")}</div>
    <div class="ag-nums">
      <div class="ag-num ${demo ? "demo" : ""}"><b>${agEsc(agNum(pk.volume))}</b><span>searches / mo</span></div>
      <div class="ag-num ${demo ? "demo" : ""}"><b>${agEsc(agNum(pk.difficulty))}</b><span>difficulty</span></div>
      ${pk.cpc != null ? `<div class="ag-num ${demo ? "demo" : ""}"><b>$${agEsc(pk.cpc)}</b><span>cpc</span></div>` : ""}
      ${r.intent ? `<div class="ag-num"><b style="font-family:var(--sans);font-size:13px;text-transform:capitalize">${agEsc(r.intent)}</b><span>intent</span></div>` : ""}
    </div>
    ${demo ? `<div class="note w" style="margin:0 0 12px"><b>Demo numbers.</b> DataForSEO is not connected, so these figures are placeholders.</div>` : ""}
    ${r.primary_keyword_why ? `<h3 class="sec">Why this keyword</h3><p style="margin:0 0 12px;font-size:12px;color:var(--muted);line-height:1.55">${agEsc(r.primary_keyword_why)}</p>` : ""}
    ${(r.secondary_keywords || []).length ? `<h3 class="sec">Also worth using</h3><ul class="ag-list">${r.secondary_keywords.map(k => `<li>${agEsc(k.keyword)}<small>${agEsc(agNum(k.volume))}/mo · d${agEsc(k.difficulty)}</small></li>`).join("")}</ul>` : ""}
    ${(r.people_also_ask || []).length ? `<h3 class="sec">People also ask</h3><ul class="ag-list">${r.people_also_ask.map(q => `<li>${agEsc(q)}</li>`).join("")}</ul>` : ""}
    ${(r.top_results || []).length ? `<h3 class="sec">Who ranks today</h3><table class="ag-pages"><thead><tr><th></th><th>Page</th></tr></thead><tbody>${r.top_results.map(p => `<tr><td class="n">${agEsc(p.position)}</td><td><a href="${agEsc(p.url)}" target="_blank" rel="noopener">${agEsc(p.title || p.url)}</a><div class="h">${agEsc(agDomain(p.url))}${p.description ? " · " + agEsc(p.description) : ""}</div></td></tr>`).join("")}</tbody></table>` : ""}
    ${(r.what_they_all_cover || []).length ? `<h3 class="sec">What they all cover</h3><ul class="ag-list">${r.what_they_all_cover.map(x => `<li>${agEsc(x)}</li>`).join("")}</ul>` : ""}
    ${r.the_gap ? `<h3 class="sec">The gap</h3><div class="ag-gap">${agEsc(r.the_gap)}</div>` : ""}
    ${r.recommended_angle ? `<h3 class="sec">The angle</h3><p style="margin:0 0 12px;font-size:12px;color:var(--ink);line-height:1.55">${agEsc(r.recommended_angle)}</p>` : ""}
    ${r.candidates_considered != null ? `<p style="font:500 10.5px/1.5 var(--mono);color:var(--faint);margin:0">${agEsc(r.candidates_considered)} keywords considered${r.skipped_already_ranking ? ` · ${agEsc(r.skipped_already_ranking)} skipped because you already rank` : ""}</p>` : ""}`;
}

function agBlueprintHtml(bp, edit, checks){
  if (!bp) return `<div class="zero"><h4>Nothing to show</h4></div>`;
  const secs = bp.sections || [];
  const total = secs.reduce((n, s) => n + (Number(s.words) || 0), 0);
  return `<div class="ag-kw" style="font-size:17px">${agEsc(bp.title || "")}</div>
    ${bp.meta_description ? `<p style="margin:6px 0 10px;font-size:12px;color:var(--muted);line-height:1.5">${agEsc(bp.meta_description)}</p>` : ""}
    <div class="ag-nums"><div class="ag-num"><b>${agEsc(secs.length)}</b><span>sections</span></div><div class="ag-num"><b>${agEsc(agNum(total))}</b><span>words planned</span></div></div>
    ${checks ? agChecksHtml(checks) : ""}
    ${bp.keyword_placement ? `<div class="ag-gap" style="font-size:11.5px">${agEsc(bp.keyword_placement)}</div>` : ""}
    <h3 class="sec">Sections · reorder with the arrows, or ask for a rewrite</h3>
    ${secs.map((s, i) => `<div class="ag-bp" data-sec="${agEsc(s.id)}">
      <div class="bh"><span class="n">${i + 1}</span><span class="bt">${agEsc(s.heading)}</span><span class="bw">${agEsc(s.words || "")}${s.words ? "w" : ""}</span>
        <button class="ib" type="button" data-ag="bpmove" data-arg="${agEsc(s.id)}" data-dir="-1" aria-label="Move up" ${i === 0 ? "disabled" : ""}>${AG_ICON.up}</button>
        <button class="ib" type="button" data-ag="bpmove" data-arg="${agEsc(s.id)}" data-dir="1" aria-label="Move down" ${i === secs.length - 1 ? "disabled" : ""}>${AG_ICON.down}</button>
        <button class="ib" type="button" data-ag="bpedit" data-arg="${agEsc(s.id)}" aria-label="Rewrite this section's plan" title="Rewrite this section's plan">${AG_ICON.pencil}</button></div>
      <div class="bc">${agEsc(s.covers || "")}
        ${(s.internal_links || []).length ? `<div class="bl">Links: ${s.internal_links.map(l => `<a href="${agEsc(l.url)}" target="_blank" rel="noopener">${agEsc(l.anchor || l.url)}</a>`).join(" · ")}</div>` : ""}
        ${edit && edit.id === s.id ? `<div class="be"><input type="text" data-agbpinstr placeholder="What should change in this section?" value="${agEsc(edit.text || "")}" aria-label="Instruction"><button class="btn pri" type="button" data-ag="bpsubmit" data-arg="${agEsc(s.id)}" ${edit.busy ? "disabled" : ""}>${edit.busy ? "Rewriting…" : "Rewrite"}</button><button class="btn" type="button" data-ag="bpcancel">Cancel</button></div>` : ""}
      </div></div>`).join("")}`;
}

function agChecksHtml(checks){
  const list = Array.isArray(checks) ? checks : (checks && checks.results) || [];
  if (!list.length) return "";
  return `<div class="ag-checks" aria-label="Checks">${list.map(c => {
    const ok = c.ok === true || c.pass === true || c.status === "ok" || c.status === "pass";
    const warn = c.status === "warn" || c.severity === "warn";
    return `<span class="ag-check ${ok ? "" : warn ? "warn" : "bad"}" title="${agEsc(c.detail || c.message || "")}">${ok ? "✓" : warn ? "!" : "✕"} ${agEsc(c.name || c.check || "check")}</span>`;
  }).join("")}</div>`;
}

function agDiffHtml(diff){
  if (!diff) return "";
  const lines = String(diff).split("\n").filter(l => !/^(---|\+\+\+|@@)/.test(l));
  return `<pre class="ag-diff">${lines.map(l => l[0] === "+" ? `<span class="add">${agEsc(l)}</span>` : l[0] === "-" ? `<span class="del">${agEsc(l)}</span>` : agEsc(l)).join("\n")}</pre>`;
}

function agArticleHtml(md, edit, last, readOnly){
  const text = typeof md === "string" ? md : (md && md.text) || "";
  const blocks = agBlocks(text);
  if (!blocks.length) return `<div class="zero"><h4>Empty draft</h4></div>`;
  return `<p style="font:500 10.5px/1.5 var(--mono);color:var(--faint);margin:0 0 10px">${agEsc(agNum(agWords(text)))} words · ${blocks.length} blocks${readOnly ? "" : " · hover a paragraph to edit it"}</p>
    ${last && last.checks ? agChecksHtml(last.checks) : ""}
    <div class="ag-doc">${blocks.map((b, i) => {
      const id = "p" + i;
      const editing = edit && edit.id === id;
      return `<div class="ag-blk ${editing ? "editing" : ""}" data-blk="${id}">${agMd(b)}
        ${readOnly ? "" : `<button class="ib ag-editbtn" type="button" data-ag="artedit" data-arg="${id}" aria-label="Edit this block" title="Ask for a change to this block only">${AG_ICON.pencil}</button>`}
        ${editing ? `<div class="ag-editbox">
          <textarea data-agartinstr placeholder="What should change here? Only this block is rewritten; the rest stays byte for byte." aria-label="Instruction">${agEsc(edit.text || "")}</textarea>
          <div class="row"><button class="btn pri" type="button" data-ag="artsubmit" data-arg="${id}" ${edit.busy ? "disabled" : ""}>${edit.busy ? "Rewriting…" : "Rewrite this block"}</button><button class="btn" type="button" data-ag="artcancel">Cancel</button><span class="sp">${edit.error ? agEsc(edit.error) : ""}</span></div>
          ${last && last.block === id && last.diff ? agDiffHtml(last.diff) : ""}
        </div>` : ""}</div>`;
    }).join("")}</div>`;
}

function agPanelHtml(a){
  const p = a.panel; if (!p) return "";
  const title = p.title || AG_VIEW_TITLE[p.view] || p.name;
  let body, footer = "";
  const live = agLiveRun();
  const atCheckpoint = live && live.status === "waiting" && live.waiting_on && live.waiting_on.kind === "artifact"
                       && live.run_id === p.run_id && live.waiting_on.artifact === p.name;
  if (p.loading) body = `<div class="zero"><h4>Reading…</h4></div>`;
  else if (p.error) body = `<div class="ag-err">${agEsc(p.error)}</div>`;
  else if (p.view === "topic_list"){
    body = agTopicListHtml(p.data, a.picked);
    if (atCheckpoint) footer = `<button class="btn pri" type="button" data-ag="usetopic" ${a.picked ? "" : "disabled"}>Use this topic</button>
      <button class="btn" type="button" data-ag="changes" data-text="Different ideas, please. This time ">Ask for different ideas</button>
      <span class="sp">${a.picked ? "" : "Pick one to continue"}</span>`;
  } else if (p.view === "research_brief"){
    body = agResearchHtml(p.data);
    if (atCheckpoint) footer = `<button class="btn pri" type="button" data-ag="approvert">Approve &amp; continue</button>
      <button class="btn" type="button" data-ag="changes" data-text="About the research: ">Ask for changes</button>`;
  } else if (p.view === "blueprint"){
    body = agBlueprintHtml(p.data, a.bpEdit, p.checks);
    if (atCheckpoint) footer = `<button class="btn pri" type="button" data-ag="approvert" ${a.busy ? "disabled" : ""}>Approve &amp; continue</button>
      <button class="btn" type="button" data-ag="changes" data-text="About the structure: ">Ask for changes</button>
      <span class="sp">${p.dirty ? "Reordered · saved on approve" : ""}</span>`;
  } else if (p.view === "article"){
    body = agArticleHtml(p.data, a.artEdit, a.lastEdit, !!p.readOnly);
    if (p.readOnly) footer = `<button class="btn" type="button" data-ag="copymd">Copy markdown</button>`;
    else footer = `${atCheckpoint ? `<button class="btn pri" type="button" data-ag="approvert">Looks good, finish</button>` : ""}
      <button class="btn ${atCheckpoint ? "" : "pri"}" type="button" data-ag="publish" ${a.busy ? "disabled" : ""}>Save to Library</button>
      ${atCheckpoint ? `<button class="btn" type="button" data-ag="changes" data-text="About the draft: ">Ask for changes</button>` : ""}
      <button class="btn" type="button" data-ag="copymd">Copy markdown</button>`;
  } else body = `<pre class="ag-detail">${agEsc(JSON.stringify(p.data, null, 2))}</pre>`;
  return `<div class="ag-ph"><div class="pt"><h3>${agEsc(title)}</h3><div class="ps">${agEsc(p.subtitle || (atCheckpoint ? "Edit anything here, then approve, and the agent continues from your version." : p.name))}</div></div>
      <button class="ib" type="button" data-ag="closepanel" aria-label="Close the panel"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg></button></div>
    <div class="ag-pb">${body}</div>
    ${footer ? `<div class="ag-pf">${footer}</div>` : ""}`;
}

/* ── settings views ────────────────────────────────────────────────────────── */

function agKnowledgeHtml(k, form){
  if (!k) return `<div class="ag-view"><h2>Knowledge</h2><p class="lead">Reading…</p></div>`;
  const idx = k.site_index; const pages = idx ? (Array.isArray(idx) ? idx : (idx.pages || [])) : [];
  const domain = idx && !Array.isArray(idx) ? idx.domain : "";
  const voice = k.brand_voice || null;
  const comps = k.competitors; const compList = Array.isArray(comps) ? comps : (comps && (comps.competitors || comps.domains)) || [];
  const compText = form && form.text != null ? form.text : compList.map(c => typeof c === "string" ? c : (c.domain || c.name || "")).join("\n");
  return `<div class="ag-view"><h2>Knowledge</h2>
    <p class="lead">What the agent knows about the business. Big and searched, not pasted into every prompt. Rebuilt by asking the agent to index the site again.</p>
    <h3 class="sec">Site index</h3>
    ${pages.length ? `<div class="ag-row"><div class="ri"><div class="rn">${agEsc(domain || "your site")} <span class="pill p-ok">${agEsc(pages.length)} pages</span></div>
        <div class="rd">${agEsc(pages.filter(p => p.top_keyword).length)} pages with a ranking keyword${idx.indexed_at ? " · indexed " + agEsc(agAgo(idx.indexed_at)) : ""}</div>
        <table class="ag-pages" style="margin-top:10px"><thead><tr><th>Page</th><th>Ranks for</th></tr></thead><tbody>${pages.slice(0, 12).map(p => `<tr><td><a href="${agEsc(p.url || "")}" target="_blank" rel="noopener">${agEsc(p.title || p.url || "")}</a>${p.covers ? `<div class="h">${agEsc(String(p.covers).slice(0, 120))}</div>` : ""}</td><td>${p.top_keyword ? agEsc(p.top_keyword) + (p.position ? ` <small style="color:var(--faint);font-family:var(--mono)">#${agEsc(p.position)}</small>` : "") : "—"}</td></tr>`).join("")}</tbody></table>
        ${pages.length > 12 ? `<div class="rm">and ${pages.length - 12} more</div>` : ""}</div></div>`
      : `<div class="ag-row"><div class="ri"><div class="rn">No site index yet</div><div class="rd">Ask the agent: “Set up for my site: index example.com”. It catalogues every page and what each ranks for.</div></div></div>`}
    <h3 class="sec">Voice</h3>
    ${voice && voice.summary ? `<div class="ag-row"><div class="ri"><div class="rn">${agEsc(voice.company || domain || "How you write")}</div><div class="rd">${agEsc(voice.summary)}</div>
        ${(voice.avoid || []).length ? `<div class="rm">Never uses: ${voice.avoid.slice(0, 15).map(agEsc).join(", ")}</div>` : ""}</div></div>`
      : `<div class="ag-row"><div class="ri"><div class="rn">No voice profile yet</div><div class="rd">Learned from your own pages after the site is indexed.</div></div></div>`}
    <h3 class="sec">Competitors · one domain per line</h3>
    <div class="ag-form"><label><textarea data-agcomps rows="5" style="background:var(--inset);border:1px solid var(--line);color:var(--ink);border-radius:6px;padding:7px 9px;font:400 12px/1.4 var(--mono)">${agEsc(compText)}</textarea></label>
      <div class="row"><button class="btn pri" type="button" data-ag="savecomps">Save competitors</button><span class="sp">${form && form.saved ? "Saved" : "Topic ideas rotate through this list"}</span></div></div>
  </div>`;
}

function agMemoryHtml(m, form){
  const rules = (m && m.rules) || [];
  return `<div class="ag-view"><h2>Memory</h2>
    <p class="lead">Standing rules about your taste. Small, and pasted into every prompt. The agent saves one when you say something that should hold for future articles; you can add your own here.</p>
    <div class="ag-addrow"><input type="text" data-agmem placeholder="e.g. Never open an article with a question" value="${agEsc(form && form.text || "")}" aria-label="New rule"><button class="btn pri" type="button" data-ag="addmem">Add rule</button></div>
    ${rules.length ? rules.map(r => `<div class="ag-row ${r.active === false ? "off" : ""}"><div class="ri"><div class="rn">${agEsc(r.text)}</div>
        <div class="rm"><span>${agEsc(r.kind || "rule")}</span><span>${r.source === "agent" ? "saved by the agent" : "added by you"}</span><span>${agEsc(agAgo(r.t))}</span></div></div>
        <div class="ra"><button class="ag-switch" type="button" role="switch" aria-checked="${r.active !== false}" data-ag="togglemem" data-arg="${agEsc(r.id)}" aria-label="Rule on or off"></button></div></div>`).join("")
      : `<div class="ag-row"><div class="ri"><div class="rn">No rules yet</div><div class="rd">Tell the agent something like “always use British spelling” and it will ask to save it.</div></div></div>`}
  </div>`;
}

function agLibraryHtml(items){
  const list = items || [];
  return `<div class="ag-view"><h2>Library</h2>
    <p class="lead">Finished drafts. Nothing leaves this Mac; publishing is your step.</p>
    ${list.length ? list.map(it => `<div class="ag-row"><div class="ri"><div class="rn">${agEsc(it.title)} <span class="pill ${it.status === "ready" ? "p-ok" : it.status === "published" ? "p-acc" : "p-mut"}">${agEsc(it.status || "draft")}</span></div>
        <div class="rm"><span>${agEsc(agNum(it.words))} words</span>${it.primary_keyword ? `<span>${agEsc(it.primary_keyword)}</span>` : ""}<span>${agEsc(agAgo(it.created_at))}</span></div></div>
        <div class="ra"><button class="btn" type="button" data-ag="libopen" data-arg="${agEsc(it.id)}">Open</button>
          <button class="btn" type="button" data-ag="libstatus" data-arg="${agEsc(it.id)}" data-status="${it.status === "ready" ? "draft" : "ready"}">${it.status === "ready" ? "Back to draft" : "Mark ready"}</button>
          <button class="ib" type="button" data-ag="libdel" data-arg="${agEsc(it.id)}" aria-label="Delete" title="Delete this draft"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg></button></div></div>`).join("")
      : `<div class="ag-row"><div class="ri"><div class="rn">Nothing saved yet</div><div class="rd">When a draft is done, “Save to Library” in the review panel puts it here.</div></div></div>`}
  </div>`;
}

function agToolsHtml(tools){
  const list = tools || [];
  return `<div class="ag-view"><h2>Tools</h2>
    <p class="lead">What the agent can do, and what each step costs. The gate is enforced by the loop, not asked of the model: a paid step always stops here first.</p>
    ${list.map(t => `<div class="ag-row"><div class="ri"><div class="rn">${agEsc(t.name.replace(/_/g, " "))}
        <span class="pill ${t.gate === "auto" ? "p-ok" : "p-warn"}">${t.gate === "auto" ? "runs freely" : "asks first"}</span>
        ${t.cost_credits ? `<span class="pill p-acc">${agEsc(t.cost_credits)} credits</span>` : ""}</div>
        <div class="rd">${agEsc(t.description)}</div>
        <div class="rm">${t.est_minutes ? `<span>about ${agEsc(t.est_minutes)} min</span>` : ""}${t.pauses ? `<span>pauses for you</span>` : ""}</div></div></div>`).join("")}
  </div>`;
}

function agConnectionsHtml(c, h, form){
  const dfs = !!(c && c.dataforseo_login && c.dataforseo_password);
  const prov = h ? h.model_provider : null;
  return `<div class="ag-view"><h2>Connections</h2>
    <p class="lead">Two things the agent needs. Secrets are stored on this Mac, owner-only, and never sent back to this screen.</p>
    <h3 class="sec">Model</h3>
    <div class="ag-row"><div class="ri"><div class="rn">${prov === "claude-cli" ? "Claude, through the command line" : prov ? agEsc(prov) : "No model available"}
        <span class="ag-status"><i class="dot ${prov ? "ok" : "bad"}"></i>${prov === "claude-cli" ? "billed to your Claude subscription" : prov ? "connected" : "not signed in"}</span></div>
      <div class="rd">${prov ? "The same sign-in the chat uses. No API key anywhere." : "Open a terminal, run <code>claude</code> once and sign in. This screen will notice."}</div></div></div>
    <h3 class="sec">DataForSEO · real search numbers</h3>
    <div class="ag-row"><div class="ri"><div class="rn">DataForSEO <span class="ag-status"><i class="dot ${dfs ? "ok" : "warn"}"></i>${dfs ? "connected" : "not connected · demo numbers"}</span></div>
      <div class="rd">Keyword volumes, difficulty, People Also Ask and the top ten pages come from here. Without it the agent still runs, on clearly labelled demo data.</div>
      <div class="ag-form" style="margin-top:10px">
        <label><b>Login</b><input type="text" data-agdfs="login" autocomplete="off" placeholder="${dfs ? "•••••• (set)" : "the email you sign in with"}" value="${agEsc(form && form.login || "")}"></label>
        <label><b>API password</b><input type="password" data-agdfs="password" autocomplete="off" placeholder="${dfs ? "•••••• (set)" : "from app.dataforseo.com → API access"}" value="${agEsc(form && form.password || "")}"></label>
        <div class="row"><button class="btn pri" type="button" data-ag="savedfs">Save</button>${dfs ? `<button class="btn" type="button" data-ag="cleardfs">Disconnect</button>` : ""}<span class="sp">${form && form.msg ? agEsc(form.msg) : ""}</span></div>
      </div></div></div>
  </div>`;
}

/* ── the screen shell (what render() sees) ─────────────────────────────────── */
if (typeof SCREENS !== "undefined"){
  SCREENS.agents = () => `<div class="ag" id="agRoot" data-ag-shell></div>`;
}
if (typeof TITLES !== "undefined"){
  TITLES.agents = ["Agents", "agents that work in front of you · SEO Writer"];
}

/* ── mount, draw, poll ─────────────────────────────────────────────────────── */
let agObs = null, agPollTimer = null, agTick = null, agToastTimer = null;

function agApi(path){ return apiGet(AG_API + path); }
function agPostApi(path, body){ return apiPost(AG_API + path, body || {}); }

function agToast(msg){
  if (typeof document === "undefined") return;
  let t = document.getElementById("agToast");
  if (!t){ t = document.createElement("div"); t.id = "agToast"; t.className = "ag-toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("on");
  clearTimeout(agToastTimer); agToastTimer = setTimeout(() => t.classList.remove("on"), 2600);
}

function agRoot(){ return typeof document === "undefined" ? null : document.getElementById("agRoot"); }

function agEnsureObserver(){
  if (agObs || typeof MutationObserver === "undefined" || typeof document === "undefined") return;
  const target = document.getElementById("panes") || document.body;
  if (!target) return;
  agObs = new MutationObserver(() => agMountIfNeeded());
  agObs.observe(target, { childList: true, subtree: true });
  agMountIfNeeded();
}

function agMountIfNeeded(){
  const root = agRoot();
  const pane = root && root.closest ? root.closest(".pane") : null;
  if (typeof document !== "undefined")
    document.querySelectorAll(".pane.agwide").forEach(p => { if (p !== pane) p.classList.remove("agwide"); });
  if (!root){ agStopPoll(); return; }
  if (pane) pane.classList.add("agwide");
  if (!root.dataset.agLive){
    root.dataset.agLive = "1";
    root.innerHTML = `<aside class="ag-side" id="agSide" aria-label="SEO Writer"></aside>
      <section class="ag-main" id="agMain" aria-label="Conversation"><div id="agStages"></div><div class="ag-scroll" id="agScroll"></div><div class="pc" id="agComposer"></div></section>
      <aside class="ag-panel" id="agPanel" aria-label="Review"></aside>`;
    agDraw(true);
    agStartPoll();
    agBootLoad();
  }
}

function agSetHtml(id, html){
  const el = document.getElementById(id); if (!el) return false;
  if (el.__agHtml === html) return false;
  el.__agHtml = html; el.innerHTML = html; return true;
}

function agDraw(force){
  const a = agS(); const root = agRoot(); if (!a || !root) return;
  root.classList.toggle("haspanel", !!a.panel);
  agSetHtml("agSide", agSideHtml(a));
  const scroll = document.getElementById("agScroll");
  const nearBottom = scroll ? (scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 60) : true;
  if (a.view === "chat"){
    const last = agLastRun();
    agSetHtml("agStages", a.chat && last ? agStagesHtml(last) : "");
    const changed = agSetHtml("agScroll", agTranscriptHtml(a));
    if (changed && scroll){
      if (a.stick && (nearBottom || force)) scroll.scrollTop = scroll.scrollHeight;
      else if (a.scroll != null && force) scroll.scrollTop = a.scroll;
    }
    const comp = document.getElementById("agComposer");
    if (comp){
      const had = document.activeElement && comp.contains(document.activeElement);
      const before = had ? document.activeElement.selectionStart : null;
      if (agSetHtml("agComposer", agComposerHtml(a)) || force){
        const ta = comp.querySelector("[data-agask]");
        if (ta){ ta.value = a.draft || ""; agGrow(ta); if (had || a.focusComposer){ try { ta.focus({ preventScroll: true }); if (before != null) ta.setSelectionRange(before, before); else ta.setSelectionRange(ta.value.length, ta.value.length); } catch (e) {} a.focusComposer = false; } }
      }
      comp.hidden = false;
    }
  } else {
    agSetHtml("agStages", "");
    /* a settings view is a new document: start it at the top, not where the chat was */
    if (scroll && a.lastView !== a.view) scroll.scrollTop = 0;
    const html = a.view === "knowledge" ? agKnowledgeHtml(a.knowledge, a.compForm)
      : a.view === "memory" ? agMemoryHtml(a.memory, a.memForm)
      : a.view === "library" ? agLibraryHtml(a.library)
      : a.view === "tools" ? agToolsHtml(a.tools)
      : agConnectionsHtml(a.conns, a.health, a.connForm);
    agSetHtml("agScroll", html);
    const comp = document.getElementById("agComposer"); if (comp){ comp.hidden = true; }
  }
  agSetHtml("agPanel", a.panel ? agPanelHtml(a) : "");
  a.lastView = a.view;
}

function agGrow(ta){
  if (!ta) return;
  ta.style.height = "auto";
  ta.style.height = Math.min(160, Math.max(22, ta.scrollHeight)) + "px";
}

/* Polling: one second while a run is live, four when idle, none when hidden. */
function agStartPoll(){
  if (agPollTimer) return;
  const tick = async () => {
    agPollTimer = null;
    if (!agRoot()){ return; }
    const a = agS();
    if (!(typeof document !== "undefined" && document.hidden)){
      try { await agRefresh(); } catch (e) { a.error = String(e && e.message || e); }
    }
    const live = agLiveRun();
    agPollTimer = setTimeout(tick, live ? AG_POLL_LIVE_MS : AG_POLL_IDLE_MS);
  };
  agPollTimer = setTimeout(tick, 400);
  if (!agTick) agTick = setInterval(() => { if (agLiveRun() && agRoot()) agDraw(); }, 1000);
}
function agStopPoll(){
  if (agPollTimer){ clearTimeout(agPollTimer); agPollTimer = null; }
  if (agTick){ clearInterval(agTick); agTick = null; }
}

let agRefreshBusy = false, agRefreshN = 0;
async function agRefresh(){
  if (agRefreshBusy) return; agRefreshBusy = true;
  const a = agS();
  try {
    agRefreshN++;
    const live = agLiveRun();
    if (live){
      const since = a.cursors[live.run_id] || 0;
      const r = await agApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(live.run_id)}/events?since=${since}`);
      if (r.events && r.events.length){ a.events[live.run_id] = (a.events[live.run_id] || []).concat(r.events); }
      a.cursors[live.run_id] = r.next != null ? r.next : since + (r.events || []).length;
      if (r.state){
        const runs = a.chat.runs; const i = runs.findIndex(x => x.run_id === live.run_id);
        if (i >= 0) runs[i] = r.state;
        agMaybeOpenCheckpoint(r.state);
      }
    }
    if (!live || agRefreshN % 4 === 0){
      const chats = await agApi("/chats"); a.chats = chats;
      if (a.chatId && !live){
        const c = chats.find(x => x.id === a.chatId);
        if (c && a.chat && c.updated_at !== (a.chat.chat || {}).updated_at) await agLoadChat(a.chatId, true);
      }
    }
    if (agRefreshN % 8 === 1){ a.health = await agApi("/health"); }
  } finally { agRefreshBusy = false; }
  agDraw();
}

async function agBootLoad(){
  const a = agS();
  try { a.health = await agApi("/health"); } catch (e) {}
  try { a.chats = await agApi("/chats"); } catch (e) { a.chats = []; }
  if (!a.chatId && a.chats && a.chats.length){
    const live = a.chats.find(c => c.live === "waiting" || c.live === "running");
    await agLoadChat((live || a.chats[0]).id, true);
  }
  try { a.memory = await agApi("/memory"); } catch (e) {}
  try { a.library = await agApi("/library"); } catch (e) {}
  agDraw(true);
}

async function agLoadChat(chatId, keepPanel){
  const a = agS();
  const r = await agApi(`/chats/${encodeURIComponent(chatId)}`);
  a.chatId = chatId; a.chat = r; a.view = "chat";
  if (!keepPanel){ a.panel = null; a.picked = null; }
  for (const run of (r.runs || [])){
    if (!a.events[run.run_id] || run.status === "running" || run.status === "waiting"){
      const ev = await agApi(`/runs/${encodeURIComponent(chatId)}/${encodeURIComponent(run.run_id)}/events?since=0`);
      a.events[run.run_id] = ev.events || []; a.cursors[run.run_id] = ev.next != null ? ev.next : (ev.events || []).length;
      if (ev.state){ const i = r.runs.findIndex(x => x.run_id === run.run_id); if (i >= 0) r.runs[i] = ev.state; }
    }
  }
  const live = agLiveRun();
  if (live) agMaybeOpenCheckpoint(live);
  a.stick = true;
  agDraw(true);
}

function agMaybeOpenCheckpoint(state){
  const a = agS();
  const w = state && state.status === "waiting" && state.waiting_on;
  if (!w || w.kind !== "artifact") return;
  const key = state.run_id + ":" + (w.call_id || w.artifact);
  if (a.autoOpened === key) return;
  a.autoOpened = key;
  agOpenArtifact(state.run_id, w.artifact, w.view);
}

async function agOpenArtifact(runId, name, view, extra){
  const a = agS();
  a.panel = Object.assign({ run_id: runId, name, view, data: null, loading: true, error: null }, extra || {});
  a.bpEdit = null; a.artEdit = null; a.lastEdit = null;
  agDraw();
  try {
    const d = await agApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(runId)}/artifact/${encodeURIComponent(name)}`);
    if (a.panel && a.panel.name === name){ a.panel.data = d; a.panel.loading = false; }
    if (view === "topic_list" && !a.picked && d && d.topics){
      const rec = d.topics.find(t => t.recommended); a.picked = rec ? rec.id : null;
    }
  } catch (e) { if (a.panel){ a.panel.loading = false; a.panel.error = String(e && e.message || e); } }
  agDraw();
}

/* ── actions ───────────────────────────────────────────────────────────────── */
async function agSend(text){
  const a = agS(); text = String(text || "").trim(); if (!text) return;
  a.busy = true; a.draft = ""; a.stick = true;
  try {
    if (!a.chatId){ const c = await agPostApi("/chats", { title: text.slice(0, 60) }); a.chatId = c.id; a.chat = { chat: c, runs: [], messages: [] }; }
    const live = agLiveRun();
    if (live && live.status === "waiting"){
      const w = live.waiting_on || {};
      const answer = w.kind === "approval" ? { approved: false, note: text } : w.kind === "artifact" ? { approved: false, changes: text } : { text };
      await agPostApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(live.run_id)}/answer`, { answer });
    } else {
      await agPostApi(`/chats/${encodeURIComponent(a.chatId)}/send`, { text });
    }
    await agLoadChat(a.chatId, true);
    a.chats = await agApi("/chats");
  } catch (e) { agToast("Could not send: " + (e && e.message || e)); }
  a.busy = false; agDraw(true);
}

async function agAnswer(answer){
  const a = agS(); const live = agLiveRun(); if (!live) return;
  a.busy = true; agDraw();
  try {
    await agPostApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(live.run_id)}/answer`, { answer });
    a.panel = null; a.picked = null;
    await agLoadChat(a.chatId, true);
  } catch (e) { agToast("Could not answer: " + (e && e.message || e)); }
  a.busy = false; agDraw(true);
}

async function agAction(act, el){
  const a = agS(); if (!a) return;
  const arg = el.getAttribute("data-arg") || "";
  switch (act){
    case "new": a.chatId = null; a.chat = null; a.panel = null; a.picked = null; a.view = "chat"; a.draft = ""; a.focusComposer = true; agDraw(true); break;
    case "chat": a.view = "chat"; await agLoadChat(arg, false); break;
    case "view": {
      a.view = arg; a.panel = null;
      if (arg === "knowledge") a.knowledge = await agApi("/knowledge").catch(() => null);
      if (arg === "memory") a.memory = await agApi("/memory").catch(() => null);
      if (arg === "library") a.library = await agApi("/library").catch(() => []);
      if (arg === "tools") a.tools = await agApi("/tools").catch(() => []);
      if (arg === "connections"){ a.conns = await agApi("/connections").catch(() => null); a.health = await agApi("/health").catch(() => a.health); }
      agDraw(true); break;
    }
    case "play": a.view = "chat"; a.draft = el.getAttribute("data-text") || ""; a.focusComposer = true; agDraw(true); break;
    case "send": { const ta = document.querySelector("[data-agask]"); await agSend(ta ? ta.value : a.draft); break; }
    case "stop": { const live = agLiveRun(); if (!live) break;
      await agPostApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(live.run_id)}/stop`, {}).catch(e => agToast(String(e.message || e)));
      await agLoadChat(a.chatId, true); break; }
    case "fold": a.collapsed[arg] = !a.collapsed[arg]; agDraw(); break;
    case "more": case "detail": a.detailOpen[arg] = !a.detailOpen[arg]; agDraw(); break;
    case "choose": await agAnswer({ choice: el.getAttribute("data-label") || "" }); break;
    case "approve": await agAnswer({ approved: arg === "yes" }); break;
    case "open": {
      const run = el.getAttribute("data-run") || (agLastRun() || {}).run_id;
      if (a.panel && a.panel.name === arg && a.panel.run_id === run){ a.panel = null; agDraw(); }
      else await agOpenArtifact(run, arg, el.getAttribute("data-view") || "article");
      break;
    }
    case "closepanel": a.panel = null; agDraw(); break;
    case "pick": a.picked = arg; agDraw(); break;
    case "usetopic": {
      const t = ((a.panel && a.panel.data && a.panel.data.topics) || []).find(x => x.id === a.picked);
      await agAnswer({ approved: true, picked: a.picked, topic: t ? t.topic : "" }); break;
    }
    case "approvert": {
      if (a.panel && a.panel.view === "blueprint" && a.panel.dirty){
        try { const r = await agPostApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(a.panel.run_id)}/artifact/${encodeURIComponent(a.panel.name)}`, { data: a.panel.data }); a.panel.checks = r.checks; a.panel.dirty = false; }
        catch (e) { agToast("Could not save the reorder: " + (e.message || e)); break; }
      }
      await agAnswer({ approved: true }); break;
    }
    case "changes": a.draft = el.getAttribute("data-text") || ""; a.focusComposer = true; agDraw(true); break;
    case "bpmove": {
      const secs = a.panel && a.panel.data && a.panel.data.sections; if (!secs) break;
      const i = secs.findIndex(s => s.id === arg), j = i + Number(el.getAttribute("data-dir") || 0);
      if (i < 0 || j < 0 || j >= secs.length) break;
      const tmp = secs[i]; secs[i] = secs[j]; secs[j] = tmp; a.panel.dirty = true; agDraw(); break;
    }
    case "bpedit": a.bpEdit = { id: arg, text: "" }; agDraw(); setTimeout(() => { const i = document.querySelector("[data-agbpinstr]"); if (i) i.focus(); }, 0); break;
    case "bpcancel": a.bpEdit = null; agDraw(); break;
    case "bpsubmit": {
      const inp = document.querySelector("[data-agbpinstr]"); const instruction = inp ? inp.value.trim() : "";
      if (!instruction || !a.panel) break;
      a.bpEdit = { id: arg, text: instruction, busy: true }; agDraw();
      try {
        const r = await agPostApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(a.panel.run_id)}/edit`, { artifact: a.panel.name, block_id: arg, instruction });
        a.panel.checks = r.checks; a.bpEdit = null;
        a.panel.data = await agApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(a.panel.run_id)}/artifact/${encodeURIComponent(a.panel.name)}`);
        agToast("Section rewritten. Everything else is byte for byte the same.");
      } catch (e) { a.bpEdit = { id: arg, text: instruction, busy: false }; agToast("Edit failed: " + (e.message || e)); }
      agDraw(); break;
    }
    case "artedit": a.artEdit = { id: arg, text: "" }; a.lastEdit = null; agDraw(); setTimeout(() => { const i = document.querySelector("[data-agartinstr]"); if (i) i.focus(); }, 0); break;
    case "artcancel": a.artEdit = null; agDraw(); break;
    case "artsubmit": {
      const ta = document.querySelector("[data-agartinstr]"); const instruction = ta ? ta.value.trim() : "";
      if (!instruction || !a.panel) break;
      a.artEdit = { id: arg, text: instruction, busy: true }; agDraw();
      try {
        const r = await agPostApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(a.panel.run_id)}/edit`, { artifact: a.panel.name, block_id: arg, instruction });
        a.lastEdit = { block: arg, checks: r.checks, diff: r.diff };
        a.panel.data = await agApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(a.panel.run_id)}/artifact/${encodeURIComponent(a.panel.name)}`);
        a.artEdit = { id: arg, text: "", busy: false };
        agToast("Block rewritten. The rest of the draft did not move.");
      } catch (e) { a.artEdit = { id: arg, text: instruction, busy: false, error: String(e.message || e) }; }
      agDraw(); break;
    }
    case "publish": {
      if (!a.panel) break; a.busy = true; agDraw();
      try { const r = await agPostApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(a.panel.run_id)}/publish`, {});
        a.library = await agApi("/library").catch(() => a.library); agToast("Saved to the Library"); await agLoadChat(a.chatId, true); void r; }
      catch (e) { agToast("Could not save: " + (e.message || e)); }
      a.busy = false; agDraw(); break;
    }
    case "copymd": {
      const d = a.panel && a.panel.data; const text = typeof d === "string" ? d : (d && d.text) || "";
      try { await navigator.clipboard.writeText(text); agToast("Markdown copied"); } catch (e) { agToast("Could not copy"); }
      break;
    }
    case "savecomps": {
      const ta = document.querySelector("[data-agcomps]"); const lines = ta ? ta.value.split("\n").map(s => s.trim()).filter(Boolean) : [];
      try { await agPostApi("/knowledge", { competitors: { competitors: lines } }); a.compForm = { text: lines.join("\n"), saved: true }; a.knowledge = await agApi("/knowledge"); }
      catch (e) { agToast("Could not save: " + (e.message || e)); }
      agDraw(); break;
    }
    case "addmem": {
      const inp = document.querySelector("[data-agmem]"); const text = inp ? inp.value.trim() : ""; if (!text) break;
      try { await agPostApi("/memory", { text, kind: "rule" }); a.memForm = null; a.memory = await agApi("/memory"); agToast("Rule added"); }
      catch (e) { agToast("Could not add: " + (e.message || e)); }
      agDraw(); break;
    }
    case "togglemem": {
      const on = el.getAttribute("aria-checked") !== "true";
      try { await agPostApi(`/memory/${encodeURIComponent(arg)}/toggle`, { active: on }); a.memory = await agApi("/memory"); }
      catch (e) { agToast("Could not change: " + (e.message || e)); }
      agDraw(); break;
    }
    case "libopen": {
      try { const it = await agApi(`/library/${encodeURIComponent(arg)}`);
        a.panel = { run_id: it.run_id, name: "draft.md", view: "article", data: { text: it.draft || "" }, loading: false, readOnly: true, title: it.title, subtitle: `${agNum(it.words)} words · ${it.status || "draft"}` }; }
      catch (e) { agToast("Could not open: " + (e.message || e)); }
      agDraw(); break;
    }
    case "libstatus": {
      try { await agPostApi(`/library/${encodeURIComponent(arg)}/status`, { status: el.getAttribute("data-status") || "draft" }); a.library = await agApi("/library"); }
      catch (e) { agToast("Could not change: " + (e.message || e)); }
      agDraw(); break;
    }
    case "libdel": {
      if (typeof confirm === "function" && !confirm("Delete this draft from the Library? The chat that made it stays.")) break;
      try { await agPostApi(`/library/${encodeURIComponent(arg)}/delete`, {}); a.library = await agApi("/library"); agToast("Deleted"); }
      catch (e) { agToast("Could not delete: " + (e.message || e)); }
      agDraw(); break;
    }
    case "savedfs": {
      const login = (document.querySelector('[data-agdfs="login"]') || {}).value || "";
      const password = (document.querySelector('[data-agdfs="password"]') || {}).value || "";
      if (!login.trim() || !password.trim()){ a.connForm = { login, password, msg: "Both fields are needed" }; agDraw(); break; }
      try { await agPostApi("/connections", { dataforseo_login: login.trim(), dataforseo_password: password.trim() });
        a.conns = await agApi("/connections"); a.health = await agApi("/health"); a.connForm = { msg: "Saved. Real numbers from the next run." }; }
      catch (e) { a.connForm = { login, password, msg: "Could not save: " + (e.message || e) }; }
      agDraw(); break;
    }
    case "cleardfs": {
      try { await agPostApi("/connections", { dataforseo_login: "", dataforseo_password: "" });
        a.conns = await agApi("/connections"); a.health = await agApi("/health"); a.connForm = { msg: "Disconnected" }; }
      catch (e) { a.connForm = { msg: "Could not disconnect: " + (e.message || e) }; }
      agDraw(); break;
    }
    default: break;
  }
}

/* ── wiring: one delegated listener each, bound once ───────────────────────── */
if (typeof document !== "undefined" && typeof window !== "undefined" && !window.__agWired
    && typeof document.addEventListener === "function"){
  window.__agWired = true;
  document.addEventListener("click", (ev) => {
    const el = ev.target && ev.target.closest ? ev.target.closest("[data-ag]") : null;
    if (!el || !el.closest("#agRoot")) return;
    const act = el.getAttribute("data-ag");
    if (!act) return;
    if (el.tagName === "A") return;
    ev.preventDefault();
    agAction(act, el).catch(e => agToast(String(e && e.message || e)));
  });
  document.addEventListener("keydown", (ev) => {
    const ta = ev.target;
    if (!ta || !ta.matches || !ta.matches("[data-agask]")) return;
    if (ev.key === "Enter" && !ev.shiftKey){
      ev.preventDefault();
      agSend(ta.value);
    }
  });
  document.addEventListener("input", (ev) => {
    const t = ev.target; if (!t || !t.matches) return;
    const a = agS(); if (!a) return;
    if (t.matches("[data-agask]")){ a.draft = t.value; agGrow(t); }
    else if (t.matches("[data-agcomps]")){ a.compForm = { text: t.value, saved: false }; }
    else if (t.matches("[data-agmem]")){ a.memForm = { text: t.value }; }
    else if (t.matches("[data-agdfs]")){
      const f = a.connForm || {}; f[t.getAttribute("data-agdfs")] = t.value; f.msg = ""; a.connForm = f;
    }
  });
  document.addEventListener("scroll", (ev) => {
    const el = ev.target; if (!el || el.id !== "agScroll") return;
    const a = agS(); if (!a) return;
    a.scroll = el.scrollTop;
    a.stick = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  }, true);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && agRoot()) agRefresh().catch(() => {}); });
  const start = () => agEnsureObserver();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
}
