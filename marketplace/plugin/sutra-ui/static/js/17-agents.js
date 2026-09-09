/* 17-agents.js — the Agents destination, and its first agent: the SEO Writer.
 *
 * What this is. A screen where an agent works in front of you: it names each step
 * before it takes it and puts every draft in a panel you can edit before it carries
 * on. The engine is seo_agent/ on the server; this file only draws what the run
 * folder already says and posts your answers back.
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
const AG_STAGES = [["setup", "Setup"], ["topic", "Topic"], ["research", "Research"], ["blueprint", "Blueprint"], ["draft", "Draft"]];
const AG_VIEW_TITLE = { brand_pack: "The brand pack", topic_list: "Topic ideas", research_brief: "Research brief",
                        blueprint: "Article plan", article: "The draft", brand_file: "Brand file", page: "Page" };
const AG_POLL_LIVE_MS = 1000;
const AG_POLL_IDLE_MS = 4000;

/* THE LIVE LIBRARY (2026-09-09). The Library used to mean "finished articles". It now holds a row
   from the moment a run starts, because the checkpoints that used to stop and show him each piece
   are gone: the research, the plan and the brand pack are announced and the run carries straight
   on, so the Library is where he watches an article being made.
   The cost of that is the thing to design against: a person opening the tab mid-run sees half a
   thing, and unless the state is readable at a glance the tab reads as full of broken articles.
   So a row being written is the only one that carries the accent, a turning marker and a count of
   how far it has got, which is the same accent-means-working vocabulary the chat already uses. */
const AG_LIB_STATE = {                        /* status -> [existing pill class, the word on screen] */
  writing:   ["p-acc", "writing"],            /* accent: working, the same as .ag-stage.cur */
  ready:     ["p-ok",  "ready to read"],
  published: ["p-acc", "published"],          /* unchanged from before the live Library */
};
/* The plain name for each milestone. The server sends `label` already written for a person, so
   this is only the fallback for a row whose payload predates it, never a second copy in use. */
const AG_MILE_LABEL = { research: "Researched", picture: "The search picture", plan: "Planned",
                        draft: "Written", edited: "Edited" };
/* Which panel each milestone opens in. Every one of these renderers already exists; "edited" has
   no view of its own, and an empty string falls to agPanelHtml's plain-JSON branch on purpose
   rather than inventing a screen for a report nobody asked to see prettily. */
const AG_MILE_VIEW = { research: "research_brief", picture: "article", plan: "blueprint",
                       draft: "article", edited: "" };
const AG_MAX_SUBS = 8;
const AG_LINK_WEAK = 0.45;      /* mirrors LINK_WEAK_SCORE in the engine: below this a link is flagged weak */
const AG_PAGE_LIMIT = 5;        /* rows in the page table, and the step the pager takes; the server defaults to the same */

/* ── tiny helpers ──────────────────────────────────────────────────────────── */
function agEsc(x){
  return String(x == null ? "" : x).replace(/[&<>"']/g, function (m) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
  });
}
function agMd(text){
  if (typeof mdHtml === "function") { try { return mdHtml(String(text || "")); } catch (e) {} }
  // the same machine tags mdHtml hides; this branch escapes for itself, so it strips for itself
  return "<div class=\"md-p\">" + agEsc(text).replace(/&lt;!--[\s\S]*?--&gt;/g, "")
    .replace(/\n\n+/g, "</div><div class=\"md-p\">") + "</div>";
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
/* agAgo is the short form the run log wants ("1h ago"). The catalogue line is a
   sentence a person reads, so it gets words: "read an hour ago". */
function agAgoWords(iso){
  const ms = agMs(iso); if (isNaN(ms)) return "";
  const d = Date.now() - ms;
  if (d < 60000) return "just now";
  const mins = Math.floor(d / 60000);
  if (mins < 60) return mins === 1 ? "a minute ago" : mins + " minutes ago";
  const hrs = Math.floor(d / 3600000);
  if (hrs < 24) return hrs === 1 ? "an hour ago" : hrs + " hours ago";
  const days = Math.floor(d / 86400000);
  return days === 1 ? "yesterday" : days + " days ago";
}
function agWords(md){ return String(md || "").trim().split(/\s+/).filter(Boolean).length; }
function agDomain(url){
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return String(url || ""); }
}
function agPath(url){
  try { const u = new URL(url); return (u.pathname.replace(/\/$/, "") || "/"); } catch (e) { return String(url || ""); }
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
    picked: null, collapsed: {}, stageOpen: {}, trail: [], workOpen: null, refresh: null, trafficForm: null, draft: "", scroll: null, stick: true,
    health: null, knowledge: null, cta: null, ctaForm: null, memory: null, library: null, tools: null, conns: null,
    pages: null, pageQ: "", pageType: "", pageLang: null, map: null, mapOn: false,
    bpEdit: null, artEdit: null, lastEdit: null, busy: false, error: null,
    compForm: null, coForm: null, memForm: null, connForm: null, libOpen: null, libEdit: null, detailOpen: {},
    fileEdit: null,
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
/* Is any Library row still being written? agLiveRun only knows about the chat that is LOADED, and
   the Library is a screen you sit on without a chat open, so this is the second thing that makes a
   poll worth doing quickly. It reads the rows we already have, never the network. */
function agLibWriting(a){
  return ((a && a.library) || []).some(it => it && it.status === "writing");
}

/* ── projections (pure) ────────────────────────────────────────────────────── */

/* Events → the entries the run log draws. Nothing is invented: every field traces
   to an event field, and a step's body is the sentence the model wrote before it
   acted (a `note` or a `message`), the way Unify shows it. */
function agStepsFromEvents(events, state){
  const out = [], byId = {};
  let lead = null, lastStep = null, lastWait = null, stage = "";
  const push = (e) => { e.stage = stage; out.push(e); return e; };
  const status = state && state.status;
  const flushLead = () => { if (lead){ push({ kind: "prose", text: lead.text, t: lead.t }); lead = null; } };
  for (const ev of (events || [])){
    switch (ev.type){
      case "note":
        flushLead(); lead = { text: ev.label || "", t: ev.t, note: true }; break;
      case "message":
        flushLead(); lead = { text: ev.text || "", t: ev.t }; break;
      case "step_started": {
        if (ev.stage) stage = ev.stage;
        const e = { kind: "step", id: ev.id, label: ev.label || ev.tool || "Step", tool: ev.tool || "",
                    state: "run", lead: lead ? lead.text : "", leadNote: !!(lead && lead.note),
                    subs: [], t: ev.t, ms: null, summary: "", reason: "", detail: "", recovering: false };
        lead = null; byId[ev.id] = e; lastStep = e; push(e); break;
      }
      case "substep_finished": {
        const p = (ev.parent && byId[ev.parent]) || lastStep;
        if (p) p.subs.push({ label: ev.label || "", note: ev.note || "", ms: ev.ms });
        else push({ kind: "note", text: ev.label || "", t: ev.t });
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
        else { flushLead(); push({ kind: "failed", label: ev.label || "Run", reason: ev.reason || "",
                                       detail: ev.detail || "", recovering: !!ev.recovering, t: ev.t }); }
        break;
      }
      case "waiting": {
        if (ev.stage) stage = ev.stage;
        flushLead();
        let e;
        if (ev.kind === "question")
          e = { kind: "ask", question: ev.question || "", why: ev.why || "", options: ev.options || [], t: ev.t };
        else if (ev.kind === "approval")
          e = { kind: "approval", tool: ev.tool || "", question: ev.question || "", why: ev.why || "",
                mins: ev.est_minutes || 0, options: ev.options || [], t: ev.t };
        else
          e = { kind: "artifact", artifact: ev.artifact || "", view: ev.view || "article",
                prompt: ev.prompt || "", t: ev.t };
        e.live = true; e.answer = null; e.call_id = ev.call_id || null;
        lastWait = e; push(e); break;
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
      /* An artifact that was MADE, not one that is waiting. Since 2026-09-09 the research, the
         plan and the brand pack no longer stop the run: they are written, announced with this
         event, and the next step starts underneath. So it is deliberately not a `waiting` row and
         carries no `live` flag, no call_id and no answer. `label` arrives already written for a
         person ("the research"), so nothing here maps the view to a name a second time. */
      case "artifact_ready":
        flushLead();
        push({ kind: "ready", artifact: ev.artifact || "", view: ev.view || "article",
               label: ev.label || "", t: ev.t });
        break;
      case "memory_saved": flushLead(); push({ kind: "mem", text: ev.text || "", t: ev.t }); break;
      case "edited": flushLead(); push({ kind: "edited", artifact: ev.artifact || "", block: ev.block || "",
                                             instruction: ev.instruction || "", t: ev.t }); break;
      case "saved_to_library": flushLead(); push({ kind: "saved", title: ev.title || "", t: ev.t }); break;
      case "stopped": flushLead(); push({ kind: "stopped", t: ev.t }); break;
      default: break;
    }
  }
  flushLead();
  /* Every row belongs to the stage that was open when it happened; rows before the first
     stage-bearing event belong to no stage and render loose above the groups. */
  for (const e of out) if (e.stage == null) e.stage = "";
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

/* Which of the five stages is done, current, or ahead. A run that never left setup
   shows Setup as its stage; an article run starts at Topic. */
function agStageOf(state){
  const cur = state && state.stage || "topic";
  const idx = Math.max(0, AG_STAGES.findIndex(s => s[0] === cur));
  const done = state && state.status === "done";
  return AG_STAGES.map((s, i) => ({ id: s[0], label: s[1],
    state: done ? "done" : i < idx ? "done" : i === idx ? (state && state.status === "waiting" ? "wait" : "cur") : "todo" }));
}

/* The setup state, from health: what is in place and what the next step is. */
function agSetupOf(h){
  if (!h) return { steps: [], next: "", ready: false };
  const pi = h.page_index || {};
  const steps = [
    { id: "model", label: "Model signed in", ok: !!h.model_provider },
    { id: "site", label: "Site read", ok: !!h.site_indexed },
    { id: "index", label: "Pages indexed by meaning", ok: !!pi.built, soft: !h.voyage },
    { id: "brand", label: "Brand pack built", ok: !!h.brand_ready },
  ];
  const missing = steps.find(s => !s.ok && !s.soft);
  return { steps, ready: !missing, next: missing ? missing.id : "" };
}

/* ── renderers (pure, return HTML strings) ─────────────────────────────────── */

const AG_ICON = {
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true"><path d="M5 12.5l4.2 4.2L19 7"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  ask: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M9 9.5a3 3 0 115.2 2c-1 .9-2.2 1.4-2.2 3"/><circle cx="12" cy="18" r=".8" fill="currentColor"/></svg>',
  doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 3.5h8l4 4v13H6z"/><path d="M14 3.5v4h4M9 12h6M9 16h6"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1.1 5.8L12 16.8l-5.3 2.8 1.1-5.8L3.5 9.7l5.9-.8z"/></svg>',
  arrow: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
  chev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>',
  pencil: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M4 20h4l10.5-10.5a2.1 2.1 0 00-3-3L5 17v3z"/><path d="M13.5 6.5l4 4"/></svg>',
  up: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6"/></svg>',
  down: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6"/></svg>',
  plus: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
  spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></svg>',
  link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1.5 1.5"/><path d="M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1.5-1.5"/></svg>',
};

function agGlyph(e){
  if (e.kind === "step") return e.state === "ok" ? AG_ICON.check : e.state === "bad" ? AG_ICON.x : "";
  if (e.kind === "ask" || e.kind === "approval") return AG_ICON.ask;
  if (e.kind === "artifact") return AG_ICON.doc;
  /* "ready" is deliberately absent: a made-and-announced artifact gets no icon, only the small
     grey dot .ag-step.quiet draws, so it does not carry the weight the checkpoint doc glyph does */
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
        ${e.state === "ok" && e.summary && e.subs.length ? `<div class="ag-body" style="margin-top:6px">${agEsc(e.summary)}</div>` : ""}
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
    case "approval":
      return `<div class="ag-step ask"><span class="ag-glyph" aria-hidden="true">${agGlyph(e)}</span>
        <div class="ag-title">Asked before going on</div>
        <div class="ag-card ${e.live ? "live" : ""}">
          <div class="q">${agEsc(e.question)}</div>
          ${e.mins ? `<div class="ag-cost">about <b>${agEsc(e.mins)}</b> min</div>` : ""}
          ${e.why ? `<div class="why">${agEsc(e.why)}</div>` : ""}
          ${e.live ? `<div class="ag-chips">
              <button class="ag-chip pri" type="button" data-ag="approve" data-arg="yes">Go ahead</button>
              <button class="ag-chip" type="button" data-ag="approve" data-arg="no">Not now</button>
            </div>`
          : `<div class="ag-answer"><span>You said</span><b>${e.decision === "approved" ? "Go ahead" : e.decision === "declined" ? "Not now" : agEsc(e.answer || "")}</b></div>`}
        </div></div>`;
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
    /* The quiet twin of the "artifact" row above. That one is a checkpoint: a card, a doc glyph,
       a Review button and a run held still behind it. This one must read as a line you pass over
       unless you want it, because the run has already moved on to the next step and five of these
       in a transcript must not feel like five interruptions. So it borrows the log_step note
       vocabulary exactly: .quiet (the small grey dot, no icon), no card, no pill, no warn colour
       and no button of its own. The only thing you can act on is the label, as an inline link. */
    case "ready": {
      const isOpen = ctx.panel && ctx.panel.name === e.artifact && ctx.panel.run_id === ctx.run_id;
      const label = e.label || (AG_VIEW_TITLE[e.view] || "it").toLowerCase();
      return `<div class="ag-step quiet"><span class="ag-glyph" aria-hidden="true"></span>
        <div class="ag-note">Ready to read: <button class="ag-openlink ${isOpen ? "open" : ""}" type="button"
          data-ag="open" data-arg="${agEsc(e.artifact)}" data-view="${agEsc(e.view)}" data-run="${agEsc(ctx.run_id || "")}"
          >${agEsc(label)}</button>. It is in the Library too.</div></div>`;
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

/* The run log, grouped by stage. One line per stage when shut; the steps inside when open.
   A run's rows are already stamped with the stage that was open when they happened, so this
   is a pure fold with no second copy of the tool -> stage map. */
function agStageGroups(entries){
  const label = {}; for (const [k, v] of AG_STAGES) label[k] = v;
  const groups = [], byStage = {};
  for (const e of (entries || [])){
    const key = e.stage || "";
    let g = byStage[key];
    if (!g){ g = { stage: key, label: label[key] || "", entries: [], steps: 0, ms: 0, live: false, bad: false, summary: "" };
             byStage[key] = g; groups.push(g); }
    g.entries.push(e);
    if (e.kind === "step"){
      g.steps++;
      if (e.ms) g.ms += e.ms;
      if (e.state === "run") g.live = true;
      if (e.state === "bad") g.bad = true;
      if (e.summary) g.summary = e.summary;
    }
    if ((e.kind === "ask" || e.kind === "approval" || e.kind === "artifact") && e.live){ g.live = true; g.waiting = true; }
  }
  return groups;
}

function agGroupHeadHtml(g, runId, open){
  const bits = [];
  if (g.steps) bits.push(g.steps + (g.steps === 1 ? " step" : " steps"));
  if (g.ms) bits.push(agDur(g.ms));
  const state = g.waiting ? "wait" : g.live ? "run" : g.bad ? "bad" : "ok";
  const word = g.waiting ? "waiting for you" : g.live ? "working" : g.bad ? "had a problem" : (g.summary || "");
  return `<button class="ag-stagehead ${state}" type="button" data-ag="stageopen"
    data-arg="${agEsc(runId + ":" + g.stage)}" aria-expanded="${open ? "true" : "false"}">
    <span class="chev" aria-hidden="true">${AG_ICON.chev}</span>
    <b>${agEsc(g.label)}</b>
    <span class="meta">${agEsc(bits.join(" · "))}</span>
    <span class="what" title="${agEsc(word)}">${agEsc(word)}</span>
  </button>`;
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
      </div>
      <div class="ag-steps" ${collapsed ? "hidden" : ""}>${agGroupsHtml(entries, run, ctx)}</div>
      ${run.status === "failed" && run.error && !entries.some(e => e.kind === "failed") ? `<div class="ag-err">${agEsc(run.error)}</div>` : ""}
    </div></div>`;
}

function agGroupsHtml(entries, run, ctx){
  const groups = agStageGroups(entries);
  const named = groups.filter(g => g.stage);
  const opened = (ctx && ctx.stageOpen) || {};
  const inner = e => agEntryHtml(e, Object.assign({}, ctx, { run_id: run.run_id }));
  return groups.map(g => {
    if (!g.stage) return g.entries.map(inner).join("");     // before any stage: loose rows
    const key = run.run_id + ":" + g.stage;
    /* shut by default; the stage being worked on opens itself, and a lone stage stays open */
    const open = key in opened ? !!opened[key] : (g.live || named.length === 1);
    return `<div class="ag-stagegroup ${open ? "open" : ""}">
      ${agGroupHeadHtml(g, run.run_id, open)}
      <div class="ag-stagebody" ${open ? "" : "hidden"}>${g.entries.map(inner).join("")}</div>
    </div>`;
  }).join("");
}

function agStagesHtml(state){
  const st = agStageOf(state);
  return `<div class="ag-stages" role="list" aria-label="Where this is">
    ${st.map((s, i) => `${i ? `<span class="ag-sep" aria-hidden="true">›</span>` : ""}<span class="ag-stage ${s.state}" role="listitem"><i aria-hidden="true"></i>${agEsc(s.label)}</span>`).join("")}
    <span class="sp">${state && state.status === "waiting" ? "waiting for you" : state && state.status === "running" ? "working" : state && state.status === "done" ? "done" : ""}</span>
  </div>`;
}

function agHeroHtml(health, conns){
  const model = health ? health.model_provider : null;
  const setup = agSetupOf(health);
  const ready = !!health && setup.ready;
  const plays = ready ? [
    ["Suggest six topics we could own", "Studies one competitor's best pages and proposes six topics with an angle they have not taken.",
     "Suggest six topics we could own."],
    ["Write an article about a topic I name", "Real keyword numbers, the pages that win, evidence with sources, a plan, then the draft in your voice. You review at each of the four stops.",
     "Write an article about "],
    ["Improve one of our existing pages", "Names the page, checks what ranks around it, and rebuilds it from the evidence.",
     "Improve our page "],
  ] : [
    ["Set up for my website", "Reads every page, indexes them by meaning, and learns how you write, who you write for and what you sell. Runs once.",
     "Set up for my website: "],
  ];
  return `<div class="ag-hero">
    <h2>SEO Writer</h2>
    <p>${ready ? "Name a topic or ask for ideas. It researches the keyword with real numbers, reads what already ranks, gathers evidence with sources, plans the article, writes it in your voice and links it to your own pages. You look at each stage before it moves on."
                : "Give it your website once. It reads every page, learns how you write and what you sell, and builds the writer brief every article follows. Then you name topics."}</p>
    <div class="ag-plays">${plays.map(p => `<button class="ag-play" type="button" data-ag="play" data-text="${agEsc(p[2])}">
      <span class="pi"><span class="pt">${agEsc(p[0])}</span><span class="pd">${agEsc(p[1])}</span></span><span class="go">Let's go ${AG_ICON.arrow}</span></button>`).join("")}</div>
    ${health ? `<div class="ag-setupbar" aria-label="Setup">${setup.steps.map(s => `<span class="ag-sstep ${s.ok ? "ok" : s.soft ? "soft" : ""}"><i aria-hidden="true"></i>${agEsc(s.label)}${!s.ok && s.soft ? " · no Voyage key" : ""}</span>`).join("")}</div>` : ""}
    <div class="ag-setup">
      ${health && !model ? `<div class="note b"><b>No model is available.</b> The agent runs on the <code>claude</code> command line, billed to your Claude subscription. Open a terminal, run <code>claude</code> once and sign in, then come back.</div>` : ""}
      ${health && !health.dataforseo ? `<div class="note w"><b>DataForSEO is not connected.</b> Keyword volumes, difficulty and who ranks come from there. <button class="btn" type="button" data-ag="view" data-arg="connections" style="margin-left:6px">Connect</button></div>` : ""}
      ${health && !health.voyage ? `<div class="note w"><b>No Voyage key.</b> Without it the agent cannot index pages by meaning, so internal links fall back to weaker matching. The key is free. <button class="btn" type="button" data-ag="view" data-arg="connections" style="margin-left:6px">Add it</button></div>` : ""}
    </div>
  </div>`;
}

function agSideHtml(a){
  const chats = a.chats || [];
  const h = a.health;
  const setup = agSetupOf(h);
  const dotCls = !h ? "" : !h.model_provider ? "bad" : !setup.ready ? "warn" : "run";
  const status = !h ? "checking…" : !h.model_provider ? "no model available" : !setup.ready ? "needs setup" : "ready";
  const brand = (a.knowledge && a.knowledge.company && a.knowledge.company.brand) || "";
  const openIdeas = a.assets && a.assets.built ? (a.assets.counts || {}).open : null;
  const rows = [["knowledge", "Knowledge", AG_ICON.doc, null], ["memory", "Memory", AG_ICON.star, a.memory ? a.memory.active : null],
                ["assets", "Asset ideas", AG_ICON.spark, openIdeas || null],
                ["library", "Library", AG_ICON.check, a.library ? a.library.length : null], ["tools", "Tools", AG_ICON.spark, null],
                ["connections", "Connections", AG_ICON.link, null]];
  const connWarn = h && (!h.dataforseo || !h.voyage);
  return `<div class="ag-agent">
      <div class="ag-mark" aria-hidden="true">S</div>
      <div style="min-width:0"><b>SEO Writer${brand ? ` · ${agEsc(brand)}` : ""}</b><span><i class="dot ${dotCls}" aria-hidden="true"></i>${agEsc(status)}</span></div>
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
      ${r[0] === "connections" && connWarn ? `<span class="ct w">!</span>` : ""}</button></li>`).join("")}</ul>`;
}

function agComposerHtml(a){
  const live = agLiveRun();
  const running = live && live.status === "running";
  const waiting = live && live.status === "waiting";
  const w = waiting ? (live.waiting_on || {}) : null;
  const setup = agSetupOf(a.health);
  const ph = running ? "Working… you can stop it, or wait."
    : waiting && w.kind === "approval" ? "Say no with a reason, or use the buttons above"
    : waiting && w.kind === "artifact" ? "Ask for changes, or approve in the panel"
    : waiting ? "Type your answer, or pick an option above"
    : a.chat ? "Ask for another article, or give feedback"
    : a.health && !setup.ready ? "Give the website, e.g. example.com" : "Name a topic, or ask for ideas";
  const step = live && live.current_step ? live.current_step.replace(/_/g, " ") : (live ? live.stage : "");
  const state = running ? `<span class="ag-cstate"><i class="dot run"></i>the agent is working · ${agEsc(step)}</span>`
    : waiting ? `<span class="ag-cstate"><i class="dot wait"></i>waiting for you</span>` : "";
  return `${state}
    <textarea data-agask rows="1" aria-label="Message the SEO Writer" placeholder="${agEsc(ph)}" ${running ? "disabled" : ""}></textarea>
    ${running ? `<button class="send stop" type="button" data-ag="stop" aria-label="Stop this run" title="Stop — the run halts after the current step"><svg width="10" height="10" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor"/></svg></button>`
             : `<button class="send" type="button" data-ag="send" aria-label="Send"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg></button>`}`;
}

function agTranscriptHtml(a){
  if (!a.chat || !(a.chat.runs || []).length) return agHeroHtml(a.health, a.conns);
  const ctx = { collapsed: a.collapsed, stageOpen: a.stageOpen, panel: a.panel, detailOpen: a.detailOpen, now: Date.now() };
  return (a.chat.runs || []).map(r => agRunHtml(r, a.events[r.run_id] || [], ctx)).join("");
}

/* ── the artifact views ────────────────────────────────────────────────────── */

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

/* One labelled block of the brief. Empty content renders nothing, so a brief that
   skipped a step (no balance, no index) shows only what was actually found. */
function agBlock(title, inner, note){
  if (!inner) return "";
  return `<h3 class="sec">${agEsc(title)}${note ? ` <small>${agEsc(note)}</small>` : ""}</h3>${inner}`;
}
function agUl(items, fmt){
  const list = (items || []).filter(x => x != null && x !== "");
  if (!list.length) return "";
  return `<ul class="ag-list">${list.map(x => `<li>${fmt ? fmt(x) : agEsc(typeof x === "string" ? x : JSON.stringify(x))}</li>`).join("")}</ul>`;
}
function agKwRow(k){
  if (typeof k === "string") return agEsc(k);
  return `${agEsc(k.keyword || "")}${k.volume != null ? ` <small>${agEsc(agNum(k.volume))}/mo</small>` : ""}${k.kd != null ? ` <small>kd ${agEsc(k.kd)}</small>` : ""}${k.why ? `<div class="h">${agEsc(k.why)}</div>` : ""}`;
}

function agResearchHtml(r){
  if (!r) return `<div class="zero"><h4>Nothing to show</h4></div>`;
  /* the new brief carries keywords.primary; an older run carried primary_keyword */
  const kw = r.keywords || {};
  const pk = kw.primary || r.primary_keyword || {};
  const serp = r.serp || {};
  const win = r.winners || {};
  const world = r.world || {};
  const spec = r.build_spec || {};
  const band = spec.word_band || {};
  const demo = !!r.demo;
  return `<div class="ag-kw">${agEsc(pk.keyword || r.topic || "")}</div>
    ${r.topic && pk.keyword && r.topic !== pk.keyword ? `<div class="ag-sub">${agEsc(r.topic)}</div>` : ""}
    <div class="ag-nums">
      <div class="ag-num ${demo ? "demo" : ""}"><b>${agEsc(agNum(pk.volume))}</b><span>searches / mo</span></div>
      <div class="ag-num ${demo ? "demo" : ""}"><b>${agEsc(agNum(pk.kd != null ? pk.kd : pk.difficulty))}</b><span>difficulty</span></div>
      ${pk.intent ? `<div class="ag-num"><b style="font-family:var(--sans);font-size:13px;text-transform:capitalize">${agEsc(pk.intent)}</b><span>intent</span></div>` : ""}
      ${band.min ? `<div class="ag-num"><b>${agEsc(agNum(band.min))}–${agEsc(agNum(band.max))}</b><span>words that rank</span></div>` : ""}
    </div>
    ${pk.split_world ? `<div class="note w" style="margin:0 0 12px"><b>Shared phrase.</b> Part of this keyword's searches belong to another field. ${agEsc(pk.why || "")}</div>` : pk.why ? `<p class="ag-why">${agEsc(pk.why)}</p>` : ""}
    ${r.cannibalisation && r.cannibalisation.url ? `<div class="note w" style="margin:0 0 12px"><b>You already rank for this.</b> <a href="${agEsc(r.cannibalisation.url)}" target="_blank" rel="noopener">${agEsc(agPath(r.cannibalisation.url))}</a> sits at #${agEsc(r.cannibalisation.rank)} for “${agEsc(r.cannibalisation.keyword)}”. A second page can split that traffic. The team should know.</div>` : ""}
    ${r.angle ? agBlock("The angle", `<div class="ag-gap">${agEsc(r.angle)}</div>`) : ""}
    ${r.spine ? agBlock("What the article argues", `<p class="ag-p">${agEsc(r.spine)}</p>`) : ""}
    ${world.about ? agBlock("What it is about, and not about", `<dl class="ag-kv"><dt>About</dt><dd>${agEsc(world.about)}</dd><dt>Not about</dt><dd>${agEsc(world.not_about || "")}</dd></dl>`) : ""}
    ${agBlock("Also worth weaving in", agUl(kw.variations, agKwRow), "same meaning as the primary")}
    ${agBlock("Section-worthy sub-topics", agUl(kw.secondary, agKwRow))}
    ${(serp.who_ranks || r.top_results || []).length ? agBlock("Who ranks today", `<table class="ag-pages"><thead><tr><th>#</th><th>Page</th></tr></thead><tbody>${(serp.who_ranks || r.top_results).slice(0, 10).map(t => `<tr><td class="n">${agEsc(t.rank || t.position)}</td><td><a href="${agEsc(t.url)}" target="_blank" rel="noopener">${agEsc(t.title || t.url)}</a><div class="h">${agEsc(t.domain || agDomain(t.url))}</div></td></tr>`).join("")}</tbody></table>`) : ""}
    ${serp.ai_overview && serp.ai_overview.text ? agBlock("Google's own answer", `<p class="ag-p">${agEsc(String(serp.ai_overview.text).slice(0, 900))}</p>${(serp.ai_overview.cites || []).length ? `<div class="ag-sub">Cites: ${serp.ai_overview.cites.slice(0, 8).map(agEsc).join(", ")}</div>` : ""}`) : ""}
    ${agBlock("Questions people ask", agUl(serp.paa_on || r.people_also_ask))}
    ${agBlock("What the winning pages all cover", agUl(win.common_h2s || r.what_they_all_cover))}
    ${agBlock("Where they drift", agUl(win.drift))}
    ${(win.gaps_to_own || []).length || r.the_gap ? agBlock("The gap we can own", (win.gaps_to_own || []).length ? agUl(win.gaps_to_own) : `<div class="ag-gap">${agEsc(r.the_gap)}</div>`) : ""}
    ${(r.verdict || []).length ? agBlock("Verdict", agUl(r.verdict)) : ""}
    ${r.evidence_count != null || r.ownpage_count != null ? agBlock("Evidence gathered", `<div class="ag-nums"><div class="ag-num"><b>${agEsc(agNum(r.evidence_count))}</b><span>facts with sources</span></div><div class="ag-num"><b>${agEsc(agNum(r.ownpage_count))}</b><span>of your pages found</span></div>${r.cost_usd != null ? `<div class="ag-num"><b>$${agEsc(Number(r.cost_usd).toFixed(2))}</b><span>DataForSEO spent</span></div>` : ""}</div>`) : ""}
    ${r.reuse && r.reuse.verdict ? agBlock("Do you already have this?", `<p class="ag-p"><b>${agEsc(r.reuse.verdict)}.</b> ${agEsc(r.reuse.why || "")}</p>${agUl(r.reuse.chosen_links, u => `<a href="${agEsc(u)}" target="_blank" rel="noopener">${agEsc(agPath(u))}</a>`)}`) : ""}
    ${r.persona && r.persona.name ? agBlock("Written for", `<p class="ag-p"><b>${agEsc(r.persona.name)}.</b> ${agEsc(r.persona.lens || r.persona.why || "")}</p>`) : ""}
    ${agResearchTeamHtml(r)}
    ${agTrailHtml(r)}
    ${(r.notes || []).length ? agBlock("Notes", agUl(r.notes)) : ""}`;
}

/* who researched this and what they asked. Empty for a run from before the research team. */
function agResearchTeamHtml(r){
  const ev = r.evidence || {};
  const team = ev.team || [];
  if (!team.length) return "";
  const turns = ev.turns || [];
  return agBlock("Who researched this",
    `<div class="ag-sub">${agEsc(team.length)} researchers asked ${agEsc(ev.questions || turns.length)} questions across ${agEsc(ev.searches || 0)} searches${ev.dossier_words ? `, then wrote a ${agEsc(agNum(ev.dossier_words))}-word dossier the facts were lifted from` : ""}.</div>
     <ul class="ag-ul">${team.map(t => `<li><b>${agEsc(t.role)}</b>${t.focus ? " — " + agEsc(t.focus) : ""}</li>`).join("")}</ul>
     ${turns.length ? `<div class="ag-qs">${turns.slice(0, 12).map(t => `<div class="ag-q"><span class="who">${agEsc(t.persona)}</span>${agEsc(t.question)}</div>`).join("")}${turns.length > 12 ? `<div class="ag-sub">and ${agEsc(turns.length - 12)} more</div>` : ""}</div>` : ""}`);
}

/* every step of the research kept its own file; this is how a person opens one */
function agTrailHtml(r){
  const a = agS(); if (!a) return "";
  const rows = a.trail || [];
  if (!rows.length) return "";
  return agBlock("The evidence trail",
    `<div class="ag-sub">Every step kept its own file. Open any of them to see exactly what it did.</div>
     <div class="ag-trail">${rows.map(x => `<button class="ag-trailrow" type="button" data-ag="work" data-arg="${agEsc(x.file)}">
        <b>${agEsc(x.label)}</b><span class="n">${agEsc(x.note)}</span><span class="b">${agEsc(agBytes(x.bytes))}</span>
      </button>`).join("")}</div>
     ${a.workOpen ? `<div class="ag-workfile"><div class="h"><b>${agEsc(a.workOpen.label)}</b><button class="ag-more" type="button" data-ag="workclose">Close</button></div><pre>${agEsc(JSON.stringify(a.workOpen.data, null, 2).slice(0, 24000))}</pre></div>` : ""}`);
}

function agBytes(n){
  n = Number(n) || 0;
  return n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(0) + " KB" : (n / 1048576).toFixed(1) + " MB";
}

/* `readOnly` exists for one caller: a plan opened from a Library row. That panel has no run_id
   (it reads the file through the Library, not through the run), so the reorder and the per-section
   rewrite would post to a run that is not there. Drawing a control that cannot work is worse than
   not drawing it, so read-only leaves the plan and drops the three buttons. Every other caller
   passes three arguments and is untouched. */
function agBlueprintHtml(bp, edit, checks, readOnly){
  if (!bp) return `<div class="zero"><h4>Nothing to show</h4></div>`;
  const secs = bp.sections || [];
  const ks = bp.keyword_set || {};
  const newShape = secs.length && secs[0].h2 !== undefined;
  return `${bp.h1 || bp.title ? `<div class="ag-kw">${agEsc(bp.h1 || bp.title)}</div>` : ""}
    <div class="ag-sub">${agEsc(secs.length)} sections${bp.format_archetype ? ` · ${agEsc(String(bp.format_archetype).replace(/-/g, " "))}` : ""}${bp.word_band && bp.word_band.min ? ` · ${agEsc(agNum(bp.word_band.min))}–${agEsc(agNum(bp.word_band.max))} words` : bp.target_words ? ` · about ${agEsc(agNum(bp.target_words))} words` : ""}${bp.angle_filter ? ` · kept ${agEsc(bp.angle_filter.kept)} of ${agEsc((bp.angle_filter.kept || 0) + (bp.angle_filter.dropped || 0))} facts` : ""}</div>
    ${checks ? agChecksHtml(checks) : ""}
    ${ks.primary ? `<dl class="ag-kv" style="margin-top:10px"><dt>Primary</dt><dd>${agEsc(ks.primary)}</dd>${(ks.variations || []).length ? `<dt>Variations</dt><dd>${ks.variations.map(agEsc).join(", ")}</dd>` : ""}${(ks.secondaries || []).length ? `<dt>Sub-topics</dt><dd>${ks.secondaries.map(agEsc).join(", ")}</dd>` : ""}</dl>` : ""}
    ${secs.map((s, i) => {
      const id = s.id || ("s" + (i + 1));
      const heading = newShape ? s.h2 : s.heading;
      const job = newShape ? s.job : s.covers;
      const ev = newShape ? (s.evidence || []).length + (s.h3 || []).reduce((n, h) => n + (h.evidence || []).length, 0) : null;
      const links = newShape ? (s.internal_links || []) : (s.internal_links || []).map(l => l.url);
      const editing = edit && edit.id === id;
      return `<div class="ag-bp" data-sec="${agEsc(id)}">
        <div class="bh"><span class="n">${i + 1}</span><span class="bt">${agEsc(heading || "")}</span>
          ${s.target_keyword ? `<span class="pill p-acc" title="Keyword this heading carries">${agEsc(s.target_keyword)}</span>` : ""}
          ${ev != null ? `<span class="bw">${ev} facts</span>` : s.words ? `<span class="bw">${agEsc(s.words)}w</span>` : ""}
          ${readOnly ? "" : `<button class="ib" type="button" data-ag="bpmove" data-arg="${agEsc(id)}" data-dir="-1" aria-label="Move up" ${i === 0 ? "disabled" : ""}>${AG_ICON.up}</button>
          <button class="ib" type="button" data-ag="bpmove" data-arg="${agEsc(id)}" data-dir="1" aria-label="Move down" ${i === secs.length - 1 ? "disabled" : ""}>${AG_ICON.down}</button>
          <button class="ib" type="button" data-ag="bpedit" data-arg="${agEsc(id)}" aria-label="Ask for a change to this section" title="Rewrite this section only">${AG_ICON.pencil}</button>`}</div>
        <div class="bc">${agEsc(job || "")}
          ${(s.h3 || []).length ? `<ul class="ag-h3s">${s.h3.map(h => `<li>${agEsc(h.h3)}${(h.evidence || []).length ? ` <small>${h.evidence.length} facts</small>` : ""}</li>`).join("")}</ul>` : ""}
          ${links.length ? `<div class="bl">Links to your pages: ${links.map(u => `<a href="${agEsc(u)}" target="_blank" rel="noopener">${agEsc(agPath(u))}</a>`).join(" · ")}</div>` : ""}
          ${editing ? `<div class="be"><input type="text" data-agbpinstr placeholder="What should change in this section?" value="${agEsc(edit.text || "")}" aria-label="Instruction">
              <button class="btn pri" type="button" data-ag="bpsubmit" data-arg="${agEsc(id)}" ${edit.busy ? "disabled" : ""}>${edit.busy ? "Rewriting…" : "Rewrite"}</button>
              <button class="btn" type="button" data-ag="bpcancel">Cancel</button></div>` : ""}
        </div></div>`;
    }).join("")}
    ${(bp.faq || []).length ? agBlock("FAQ the article will answer", agUl(bp.faq)) : ""}
    ${(bp.orphan_keywords || []).length ? agBlock("Searched-for phrases no section covers", agUl(bp.orphan_keywords, k => `${agEsc(k.keyword)} <small>${agEsc(agNum(k.volume))}/mo</small>`), "consider a section") : ""}
    ${bp.persona && bp.persona.name ? `<div class="ag-sub" style="margin-top:12px">Written for <b>${agEsc(bp.persona.name)}</b></div>` : ""}`;
}

function agChecksHtml(checks){
  const list = Array.isArray(checks) ? checks : (checks && checks.results) || (checks && typeof checks === "object" && !checks.results
    ? Object.keys(checks).map(k => ({ name: k, ok: !!checks[k] })) : []);
  if (!list.length) return "";
  return `<div class="ag-checks" aria-label="Checks">${list.map(c => {
    const ok = c.ok === true || c.pass === true || c.status === "ok" || c.status === "pass";
    const warn = c.status === "warn" || c.severity === "warn";
    return `<span class="ag-check ${ok ? "" : warn ? "warn" : "bad"}" title="${agEsc(c.detail || c.message || "")}">${ok ? "✓" : warn ? "!" : "✕"} ${agEsc(c.name || c.check || "check")}</span>`;
  }).join("")}</div>`;
}

function agDiffHtml(diff){
  if (!diff) return "";
  return `<pre class="ag-diff">${String(diff).split("\n").map(l => l.startsWith("+") && !l.startsWith("+++") ? `<span class="add">${agEsc(l)}</span>`
    : l.startsWith("-") && !l.startsWith("---") ? `<span class="del">${agEsc(l)}</span>` : agEsc(l)).join("\n")}</pre>`;
}

/* The links the pass laid in, with the match score each one earned. */
function agLinksHtml(rep){
  if (!rep) return "";
  const inline = (rep.placed || []).filter(p => p.kind === "inline");
  const rm = (rep.placed || []).filter(p => p.kind === "read-more");
  const ext = rep.external_kept || [];
  if (!inline.length && !rm.length && !ext.length && !rep.note) return "";
  const score = p => {
    const v = p.rr != null ? p.rr : p.sim;
    if (v == null) return "";
    const weak = Number(v) < AG_LINK_WEAK;
    return `<span class="ag-score ${weak ? "weak" : ""}" title="How well the page matched the section (rerank score)">match ${agEsc(Number(v).toFixed(2))}${weak ? " · weak" : ""}</span>`;
  };
  return `<div class="ag-links">
    <h3 class="sec">Links placed <small>${inline.length} to your pages · ${rm.length} read-more · ${ext.length} sources</small></h3>
    ${rep.note ? `<p class="ag-sub">${agEsc(rep.note)}</p>` : ""}
    ${inline.map(p => `<div class="ag-link"><span class="an">“${agEsc(p.anchor)}”</span> → <a href="${agEsc(p.url)}" target="_blank" rel="noopener">${agEsc(agPath(p.url))}</a>${score(p)}<div class="h">in “${agEsc(p.section)}”${p.why ? ` · ${agEsc(p.why)}` : ""}</div></div>`).join("")}
    ${rm.map(p => `<div class="ag-link"><span class="an">Read more</span> → <a href="${agEsc(p.url)}" target="_blank" rel="noopener">${agEsc(agPath(p.url))}</a><div class="h">after “${agEsc(p.after_section)}”</div></div>`).join("")}
    ${ext.map(k => `<div class="ag-link"><span class="an">Source</span> → <a href="${agEsc(k.url)}" target="_blank" rel="noopener">${agEsc(agDomain(k.url))}</a>${k.anchor_phrase ? `<div class="h">on “${agEsc(k.anchor_phrase)}”</div>` : `<div class="h">as a numbered citation</div>`}</div>`).join("")}
    ${rep.integrity_clean === false ? `<div class="ag-err">Some text moved beyond the declared links, so those blocks were put back exactly as they were.</div>` : ""}
  </div>`;
}

function agArticleHtml(md, edit, last, readOnly, extra){
  const text = typeof md === "string" ? md : (md && md.text) || "";
  const blocks = agBlocks(text);
  if (!blocks.length) return `<div class="zero"><h4>Empty draft</h4></div>`;
  extra = extra || {};
  const rep = extra.write || {};
  const cov = rep.coverage_checklist || rep.checklist || rep.coverage;
  const len = rep.length;
  return `<p class="ag-sub" style="margin:0 0 10px">${agEsc(agNum(agWords(text)))} words${len && len.band_min ? ` · aimed ${agEsc(agNum(len.band_min))}–${agEsc(agNum(len.band_max))}` : ""} · ${blocks.length} blocks${readOnly ? "" : " · hover a paragraph to edit it"}</p>
    ${cov ? agChecksHtml(cov) : last && last.checks ? agChecksHtml(last.checks) : ""}
    ${extra.links ? agLinksHtml(extra.links) : ""}
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

/* The brand pack: every file the setup built, what each is for, and what needs a look. */
const AG_BRAND_FILES = [
  ["company.json", "The company record", "Name, website, one line on what they do, the market. The agent asks you to confirm the one-liner."],
  ["writer-brief.md", "Writer brief", "The one page every article is written from: what they believe, how they sound, words they use and refuse."],
  ["brand-voice.md", "Brand voice", "How the brand sounds, with real examples from the site."],
  ["style-guide.md", "Style guide", "Capitalisation, numbers, punctuation, house spelling, words to avoid."],
  ["persona.md", "Readers", "Who the articles are written for. Three or four reader types and how to pick one."],
  ["features.md", "Product facts", "What they sell, integrations, pricing, proof. The close reads this."],
  ["cta-pages.md", "Pages a call to action may link to", "The short list the article's close is allowed to point at."],
  ["stats.md", "Real numbers", "Figures about the company, drafted from its own pages. Edit any row and your version is the truth."],
  ["stories.md", "Customer stories", "Named customer results, drafted from the site. Edit any entry and your version is the truth."],
  ["brand-cards.json", "Brand cards", "The numbers and stories as placeable facts, each with its source."],
  ["writing-examples.md", "Worked examples", "The best on-voice articles, annotated."],
  ["voices.md", "Bylines", "Who signs the writing. Filled by the team."],
  ["writer-brief-rulings.md", "Rulings", "Decisions that outrank everything else in the brief."],
  ["writing-integrity.md", "Writing integrity", "The honesty contract: no invented customers, no hype, cite properly."],
  ["field-sources.md", "Where the audience talks", "The checked communities where practitioners argue in public."],
  ["page-shortlist.md", "Pages the voice was learned from", "Twenty to forty pages, top-traffic plus the positioning pages."],
  ["type-roles.json", "Page types", "Which page types carry numbers, stories, products, articles."],
  ["seo-aeo-geo-checklist.md", "SEO checklist", "The per-article gate the write phase follows."],
];

function agBrandPackHtml(pack, opts){
  opts = opts || {};
  const files = (pack && pack.files) || [];
  const byName = {};
  for (const f of files) byName[f.name] = f;
  const known = AG_BRAND_FILES.map(r => r[0]);
  const extra = files.filter(f => known.indexOf(f.name) === -1 && f.exists);
  const built = files.filter(f => f.exists).length;
  /* A standing screen carries no nags; a live moment does. At a checkpoint the agent has
     stopped and is waiting on a person, so what it is waiting for is the panel's whole job.
     The Knowledge tab is a reference screen and shows none of this. The CALLER decides that,
     never the data, so the same payload reads two ways in the two places. `confirm` is the
     field to send; `needs_review` is the older name and is still read so the checkpoint keeps
     working while the builders are rewritten. */
  const ask = opts.atCheckpoint ? ((pack && (pack.confirm || pack.needs_review)) || []) : [];
  return `<p class="ag-sub" style="margin:0 0 10px">${built} of ${AG_BRAND_FILES.length} files built</p>
    ${ask.length ? `<div class="ag-card" style="margin:0 0 12px"><div class="q">Before I carry on, there ${ask.length === 1 ? "is one thing" : "are " + ask.length + " things"} I need you to decide.</div>
      <ul class="ag-list" style="margin:8px 0 0">${ask.map(r => `<li>${agEsc(typeof r === "string" ? r : (r.question || r.text || ""))}</li>`).join("")}</ul></div>` : ""}
    <div class="ag-files">${AG_BRAND_FILES.map(r => {
      const f = byName[r[0]];
      const ok = !!(f && f.exists);
      return `<button class="ag-file ${ok ? "" : "off"}" type="button" data-ag="brandfile" data-arg="${agEsc(r[0])}" ${ok ? "" : "disabled"}>
        <span class="fi" aria-hidden="true">${AG_ICON.doc}</span>
        <span class="ft"><span class="fn">${agEsc(r[1])}</span><span class="fd">${agEsc(r[2])}</span></span>
        <span class="fm">${ok ? (f.words ? agEsc(agNum(f.words)) + " words" : "built") : "not built yet"}</span></button>`;
    }).join("")}${extra.map(f => `<button class="ag-file" type="button" data-ag="brandfile" data-arg="${agEsc(f.name)}"><span class="fi" aria-hidden="true">${AG_ICON.doc}</span><span class="ft"><span class="fn">${agEsc(f.name)}</span></span><span class="fm">${agEsc(agNum(f.words))} words</span></button>`).join("")}</div>`;
}

function agBrandFileHtml(d, edit){
  if (!d) return `<div class="zero"><h4>Nothing to show</h4></div>`;
  const isJson = typeof d.text !== "string";
  const text = isJson ? JSON.stringify(d, null, 2) : d.text;
  if (edit) return `<div class="ag-editbox"><textarea data-agfiletext class="tall" aria-label="File text">${agEsc(edit.text != null ? edit.text : text)}</textarea>
    <div class="row"><button class="btn pri" type="button" data-ag="filesave" ${edit.busy ? "disabled" : ""}>${edit.busy ? "Saving…" : "Save"}</button><button class="btn" type="button" data-ag="filecancel">Cancel</button><span class="sp">${edit.msg ? agEsc(edit.msg) : "Your text becomes the truth; the builders never overwrite it."}</span></div></div>`;
  return isJson ? `<pre class="ag-detail" style="max-height:none">${agEsc(text)}</pre>` : `<div class="ag-doc">${agMd(text)}</div>`;
}

function agPageHtml(d){
  if (!d) return `<div class="zero"><h4>Nothing to show</h4></div>`;
  const r = d.row || {};
  return `<div class="ag-sub" style="margin:0 0 10px"><a href="${agEsc(d.url)}" target="_blank" rel="noopener">${agEsc(d.url)}</a></div>
    <div class="ag-nums">${r.traffic_clean != null || r.traffic != null ? `<div class="ag-num"><b>${agEsc(agNum(r.traffic_clean != null ? r.traffic_clean : r.traffic))}</b><span>visits / mo</span></div>` : ""}
      <div class="ag-num"><b>${agEsc(agNum(r.word_count || agWords(d.text)))}</b><span>words</span></div>
      ${r.top_keyword ? `<div class="ag-num"><b style="font-family:var(--sans);font-size:13px">${agEsc(r.top_keyword)}</b><span>top keyword${r.position ? " · #" + agEsc(r.position) : ""}</span></div>` : ""}
      ${r.type ? `<div class="ag-num"><b style="font-family:var(--sans);font-size:13px">${agEsc(r.type)}</b><span>type</span></div>` : ""}</div>
    <div class="ag-doc">${agMd(d.text)}</div>`;
}

/* A saved article is a document: edit the words and save over it, no run needed. The draft
   lives on a.libEdit the way a.ctaForm holds the link list, so a redraw between keystrokes
   cannot throw away what he has typed, and the word count is his own text's, not a stale one. */
function agLibEditHtml(p, ed){
  return `<div class="ag-libedit">
    <label class="ag-lbl">Title</label>
    <input class="in" type="text" data-aglibtitle value="${agEsc(ed.title || "")}" aria-label="Title" />
    <label class="ag-lbl">The article</label>
    <textarea class="in ta" data-aglibbody rows="26" spellcheck="true" aria-label="The article">${agEsc(ed.draft || "")}</textarea>
    <div class="ag-editrow">
      <button class="btn pri" type="button" data-ag="libsave" data-arg="${agEsc(p.libId)}" ${ed.busy ? "disabled" : ""}>${ed.busy ? "Saving…" : "Save"}</button>
      <button class="btn" type="button" data-ag="libcancel">Cancel</button>
      <span class="ag-sub">${agEsc(agNum(agWords(ed.draft)))} words</span>
      ${ed.error ? `<span class="ag-err">${agEsc(ed.error)}</span>` : ""}
    </div></div>`;
}

/* One idea, with everything that argues for it. Every field here traces to a step that produced
   it, so a person can tell an idea backed by fifteen competitor pages from one a model liked. */
function agIdeaHtml(d){
  if (!d) return `<div class="zero"><h4>Nothing to show</h4></div>`;
  const lk = d.linkability || {}, ow = d.ownability || {}, ru = d.reuse || {};
  const rows = [
    ["The angle", d.angle], ["Shape", d.format],
    ["Found by", (d.method || []).map(agMethodName).join(", ")],
    ["Fit", d.brand_fit + (d.transplant_from ? ` (the shape comes from ${d.transplant_from})` : "")],
    ["Would anyone cite it", lk.score != null ? `${lk.score}/${lk.of || 4} — ${lk.why || ""}` : ""],
    ["Can we own it", ow.verdict == null ? "" : `${ow.verdict ? "yes" : "no"} — ${ow.why || ""}`],
    ["Do we have it already", ru.verdict ? `${ru.verdict}${ru.why ? " — " + ru.why : ""}` : ""],
    ["How hard to beat", d.beatability], ["Effort", d.effort],
  ].filter(r => r[1] != null && String(r[1]).trim() && String(r[1]).trim() !== "()");
  return `<div class="ag-idea">
    ${rows.map(r => `<div class="ir"><span class="k">${agEsc(r[0])}</span><span class="v">${agEsc(String(r[1]))}</span></div>`).join("")}
    ${(d.proof || []).length ? `<div class="ir"><span class="k">The proof</span><span class="v">${
      (d.proof || []).map(x => `<a href="${agEsc(x.url || "")}" target="_blank" rel="noopener">${agEsc(x.what || x.url || "")}</a>${x.domains ? ` — ${agEsc(agNum(x.domains))} sites link to it` : ""}`).join("<br>")}</span></div>` : ""}
    ${(ru.links || []).length ? `<div class="ir"><span class="k">Pages we already have</span><span class="v">${
      (ru.links || []).map(u => `<a href="${agEsc(u)}" target="_blank" rel="noopener">${agEsc(agPath(u))}</a>`).join("<br>")}</span></div>` : ""}
    ${d.built && d.built.library_id ? `<div class="ir"><span class="k">Written</span><span class="v">It is in the Library, saved ${agEsc(agAgo(d.built.at))}</span></div>` : ""}
  </div>`;
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
  } else if (p.view === "brand_pack"){
    body = agBrandPackHtml(p.data, { atCheckpoint });
    if (atCheckpoint) footer = `<button class="btn pri" type="button" data-ag="approvert">Looks right, continue</button>
      <button class="btn" type="button" data-ag="changes" data-text="About the brand pack: ">Ask for changes</button>
      <span class="sp">Open a file to read or edit it</span>`;
  } else if (p.view === "brand_file"){
    body = agBrandFileHtml(p.data, a.fileEdit);
    footer = a.fileEdit ? "" : `<button class="btn" type="button" data-ag="fileedit">Edit</button>${p.back ? `<button class="btn" type="button" data-ag="back">Back to the pack</button>` : ""}`;
  } else if (p.view === "idea"){
    body = agIdeaHtml(p.data);
  } else if (p.view === "page"){
    body = agPageHtml(p.data);
  } else if (p.view === "research_brief"){
    body = agResearchHtml(p.data);
    if (atCheckpoint) footer = `<button class="btn pri" type="button" data-ag="approvert">Approve &amp; continue</button>
      <button class="btn" type="button" data-ag="changes" data-text="About the research: ">Ask for changes</button>`;
  } else if (p.view === "blueprint"){
    body = agBlueprintHtml(p.data, a.bpEdit, p.checks, !!p.readOnly);
    if (atCheckpoint) footer = `<button class="btn pri" type="button" data-ag="approvert" ${a.busy ? "disabled" : ""}>Approve &amp; continue</button>
      <button class="btn" type="button" data-ag="changes" data-text="About the plan: ">Ask for changes</button>
      <span class="sp">${p.dirty ? "Reordered · saved on approve" : ""}</span>`;
  } else if (p.view === "article"){
    body = (p.libId && a.libEdit) ? agLibEditHtml(p, a.libEdit)
      : agArticleHtml(p.data, a.artEdit, a.lastEdit, !!p.readOnly, { links: p.links, write: p.write });
    if (p.readOnly) footer = a.libEdit ? ""
      : `${p.libId ? `<button class="btn pri" type="button" data-ag="libedit" data-arg="${agEsc(p.libId)}">Edit</button>` : ""}<button class="btn" type="button" data-ag="copymd">Copy markdown</button>`;
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

/* Keeping the catalogue current. One line that replaces itself while it works, then a link to
   what changed. Never a chat log: a person watching an update wants one line, not a transcript.
   The two buttons that START it sit on the catalogue heading row (agCatControlsHtml); this
   renders only what is happening right now, and nothing at all when nothing is. */
function agRefreshHtml(a){
  const r = a.refresh || null;
  let box = "";
  if (r && r.busy) {
    box = `<div class="ag-refresh busy"><span class="spin" aria-hidden="true"></span><span class="msg">${agEsc(r.step || "Working…")}</span></div>`;
  } else if (r && r.preview) {
    const n = r.preview;
    const nothing = !n.new && !n.gone && !n.changed;
    box = `<div class="ag-refresh">
      <div class="msg">${nothing ? "Nothing has changed since the last read."
        : `<b>${agEsc(agNum(n.new))} new</b>, ${agEsc(agNum(n.gone))} gone, ${agEsc(agNum(n.changed))} rewritten.${n.unchecked ? ` ${agEsc(agNum(n.unchecked))} pages give no date, so they cannot be checked without reading them.` : ""}`}</div>
      <div class="ag-editrow">
        ${nothing ? "" : `<button class="btn pri" type="button" data-ag="refreshgo">Update the catalogue</button>`}
        <button class="btn" type="button" data-ag="refreshcancel">${nothing ? "Close" : "Not now"}</button>
      </div></div>`;
  } else if (r && r.done) {
    box = `<div class="ag-refresh done">
      <div class="msg"><b>Done.</b> ${agEsc(r.done)}</div>
      <div class="ag-editrow"><button class="btn" type="button" data-ag="refreshchanges">See what changed</button>
        <button class="btn" type="button" data-ag="refreshcancel">Close</button></div></div>`;
  } else if (r && r.error) {
    box = `<div class="ag-refresh"><div class="msg err">${agEsc(r.error)}</div>
      <div class="ag-editrow"><button class="btn" type="button" data-ag="refreshcancel">Close</button></div></div>`;
  }
  return box + (a.trafficForm ? `<div class="ag-libedit" style="margin-top:8px">
      <label class="ag-lbl">Where the traffic file is on this Mac</label>
      <input class="in" type="text" data-agtraffic placeholder="/Users/you/Desktop/top-pages.csv" value="${agEsc(a.trafficForm.path || "")}" />
      <div class="ag-editrow">
        <button class="btn pri" type="button" data-ag="trafficgo" ${a.trafficForm.busy ? "disabled" : ""}>${a.trafficForm.busy ? "Reading…" : "Import"}</button>
        <button class="btn" type="button" data-ag="trafficcancel">Cancel</button>
        <span class="ag-sub">A CSV with a page address column and a traffic column.</span>
        ${a.trafficForm.error ? `<span class="ag-err">${agEsc(a.trafficForm.error)}</span>` : ""}
      </div></div>` : "");
}

/* The small controls that belong to the catalogue, on its heading row rather than in the body:
   the map, and the two ways to bring the catalogue up to date. */
function agCatControlsHtml(a, canMap){
  return `<div class="ag-secctl">
    ${canMap ? `<button class="btn" type="button" data-ag="map">${a.mapOn ? "Hide the map" : "Show the map"}</button>` : ""}
    <button class="btn" type="button" data-ag="refreshcheck" title="Reads only what is new or has changed, not the whole site.">Check for changes</button>
    <button class="btn" type="button" data-ag="trafficimport">Import a traffic file</button>
  </div>`;
}

/* The one line about the catalogue. With no search traffic connected the middle clause is left
   out and said plainly at the end, because "0 rank for something" reads as a failure. */
function agCatLine(idx){
  const traffic = idx.has_traffic != null ? !!idx.has_traffic : !!idx.ranking_pages;
  const parts = [agEsc(agNum(idx.page_count)) + " pages"];
  if (traffic) parts.push(agEsc(agNum(idx.ranking_pages)) + " rank for something");
  parts.push(agEsc(agNum(idx.ok_pages)) + " with full text");
  if (idx.indexed_at) parts.push("read " + agEsc(agAgoWords(idx.indexed_at)));
  if (!traffic) parts.push("search traffic not connected yet");
  return parts.join(" · ");
}

/* Which language the page list is showing. About a fifth of the owner's pages are
   translations, so an unfiltered list drops Swedish and Japanese rows into an English one,
   which is the confusion this whole screen exists to remove. So the default is the site's own
   language, from the company record. null means he has not chosen and gets that default; ""
   means he chose All; a code means he chose that one. On a site with only one language there
   is nothing to filter, so the default is All and no control is drawn. */
function agEffLang(a, idx, co){
  if (a.pageLang != null) return a.pageLang;
  if (!Object.keys((idx && idx.languages) || {}).length) return "";
  return String((co && co.language_code) || "").trim().toLowerCase();
}

/* Why the row count is smaller than the catalogue. A filtered list that does not say it is
   filtered is the same confusion in a different place. */
function agPagesNote(bits, total){
  return bits.length ? ` · ${bits.join(", ")} · ${agEsc(agNum(total))} pages in all` : "";
}

/* The map of the pages. agDrawMap paints the canvas after agDraw; this is only its frame. */
function agMapHtml(a){
  return `<div class="ag-map"><canvas id="agMap" width="900" height="520" aria-label="Map of your pages"></canvas>
    <div class="ag-maptip" id="agMapTip" hidden></div>
    <div class="ag-mapcap">pages that mean similar things sit close together, hover to read, click to open</div>
    ${a.map ? `<div class="ag-maplegend">${agMapLegend(a.map)}</div>` : `<div class="rd" style="padding:10px">Loading the map…</div>`}</div>`;
}

/* The writer brief: a short readable window on the page, the whole thing one click away, and one
   door behind which the files it was assembled from wait for anyone who wants them.
   The section draws its own heading, because its two controls belong on that heading row. */
function agBriefHtml(brand, open){
  const b = brand || {};
  const br = b.brief || {};
  const name = b.brand || "the business";
  const head = ctl => `<div class="ag-sechead"><h3 class="sec">The writer brief</h3>${ctl}</div>`;
  if (!br.exists) return head("") + `<div class="ag-row"><div class="ri"><div class="rn">Not written yet</div>
      <div class="rd">Built during setup from the site's own pages: what they believe, how they sound, the words they use and refuse.</div></div></div>`;
  const built = b.built_from || [];
  const files = built.map(f => `<button class="ag-file ${f.exists ? "" : "off"}" type="button" data-ag="brandfile" data-arg="${agEsc(f.name)}" data-label="${agEsc(f.label || f.name)}" ${f.exists ? "" : "disabled"}>
        <span class="fi" aria-hidden="true">${AG_ICON.doc}</span>
        <span class="ft"><span class="fn">${agEsc(f.label || f.name)}</span><span class="fd">${agEsc(f.note || "")}</span></span>
        <span class="fm">${f.exists ? (f.words ? agEsc(agNum(f.words)) + " words" : "written") : "not written yet"}</span></button>`).join("");
  // Both doors sit ABOVE the brief, not below it. Found 2026-09-09 by opening the real pack: the
  // brief runs 3,090 words, so anything after it is a screen and a half down and nobody finds it.
  // Open reuses the same brandfile route the built-from files use, so there is one way in, not two.
  // The window itself is short and scrolls, so the sections under it stay reachable. Shortened
  // 2026-09-09 after the owner read the real pack: at 62vh the box still owned the whole screen.
  return head(`<div class="ag-secctl">
      <button class="btn" type="button" data-ag="brandfile" data-arg="writer-brief.md" data-label="Writer brief" title="Opens the whole brief in the side panel, nothing left out.">Open</button>
      ${built.length ? `<button class="btn" type="button" data-ag="detail" data-arg="builtfrom" aria-expanded="${open ? "true" : "false"}">${open ? "Hide how this was built" : "See how this was built"}</button>` : ""}
    </div>`) + `
    <p class="ag-sub ag-briefsub">This is what the writer reads before writing an article about ${agEsc(name)}. The first part of it is below; Open shows all of it.</p>
    ${open && built.length ? `<div class="ag-files" style="margin:0 0 10px">${files}</div>` : ""}
    <div class="ag-brief">${agMd(br.text || "")}</div>`;
}

/* A file the pack carries but nothing reads yet. Its own heading, because its label IS the
   heading ("Who writes"), and said plainly to be idle rather than left to look built. */
function agExtrasHtml(brand){
  const list = (brand && brand.extras) || [];
  return list.map(f => `<h3 class="sec">${agEsc(f.label || f.name)}</h3>
    <div class="ag-row ${f.exists ? "" : "off"}"><div class="ri">
      <div class="rn">${agEsc(f.note || f.name)} <span class="pill ${f.in_use === false ? "p-mut" : "p-ok"}">${f.in_use === false ? "not in use yet" : "read on every article"}</span></div>
      <div class="rm"><span>${agEsc(f.name)}</span><span>${f.exists ? (f.words ? agEsc(agNum(f.words)) + " words" : "written") : "not written yet"}</span></div></div>
      ${f.exists ? `<div class="ra"><button class="btn" type="button" data-ag="brandfile" data-arg="${agEsc(f.name)}" data-label="${agEsc(f.label || f.name)}">Open</button></div>` : ""}</div>`).join("");
}

/* The pages an article's close is allowed to send a reader to. The crawl suggests some; the
   owner adds, removes and saves. The draft lives on a.ctaForm until Save, exactly the way the
   competitors box and the company form hold their draft. */
function agCtaHtml(cta, form){
  const rows = (form && form.rows) || (cta && cta.rows) || [];
  const dom = (cta && cta.domain) || "";
  return `<p class="ag-sub" style="margin:0 0 8px">The only pages the last line of an article may send a reader to${dom ? ", on " + agEsc(dom) : ""}.</p>
    <div class="ag-ctalist">${rows.length ? rows.map((r, i) => `<div class="ag-ctarow${r.mine ? " mine" : ""}">
        <input type="text" data-agcta="url" data-i="${i}" value="${agEsc(r.url || "")}" placeholder="https://${agEsc(dom || "example.com")}/pricing" aria-label="Page address">
        <input type="text" data-agcta="note" data-i="${i}" value="${agEsc(r.note || "")}" placeholder="when to point here" aria-label="When to point here">
        <span class="ag-ctasrc">${r.mine ? "yours" : "suggested"}</span>
        <button class="ib" type="button" data-ag="ctadel" data-arg="${i}" aria-label="Remove this page" title="Remove this page"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
        ${r.title === "" && r.url ? `<div class="ag-ctanote">This page is not in the catalogue yet, so there is nothing read about it. The link still works.</div>` : ""}
      </div>`).join("") : `<div class="rd">No pages yet. Add the one an article should send a reader to.</div>`}</div>
    <div class="ag-editrow" style="margin-top:8px">
      <button class="btn" type="button" data-ag="ctaadd">Add a page</button>
      <button class="btn pri" type="button" data-ag="ctasave" ${form && form.busy ? "disabled" : ""}>${form && form.busy ? "Saving…" : "Save"}</button>
      <span class="ag-sub">${form && form.msg ? agEsc(form.msg) : "A page you add stays; rebuilding the pack never removes it."}</span>
    </div>`;
}

function agKnowledgeHtml(k, a){
  a = a || {};
  if (!k) return `<div class="ag-view"><h2>Knowledge</h2><p class="lead">Reading…</p></div>`;
  const idx = k.site_index || {};
  const co = k.company || {};
  const pi = k.page_index || {};
  const pages = a.pages || null;
  const types = idx.types || {};
  const typeNames = idx.type_names || {};
  const typeList = Object.keys(types).sort((x, y) => types[y] - types[x]);
  const langs = idx.languages || {};
  const langNames = idx.language_names || {};
  const own = String(co.language_code || "").trim().toLowerCase();
  const eff = agEffLang(a, idx, co);
  /* the site's own language leads the list even when no row carries it explicitly: the
     catalogue leaves the primary language blank, so it would otherwise have no option */
  const langList = Object.keys(langs).sort((x, y) => langs[y] - langs[x]).filter(c => c !== own);
  if (own && Object.keys(langs).length) langList.unshift(own);
  const langLabel = c => langNames[c] || (c === own ? "the site's own language" : c);
  const comps = k.competitors; const compList = Array.isArray(comps) ? comps : (comps && (comps.competitors || comps.domains)) || [];
  const compText = a.compForm && a.compForm.text != null ? a.compForm.text : compList.map(c => typeof c === "string" ? c : (c.domain || c.name || "")).join("\n");
  const cf = a.coForm || {};
  const indexed = !!idx.page_count;
  const mapReady = !!pi.built;
  const extras = agExtrasHtml(k.brand);
  return `<div class="ag-view wide"><h2>Knowledge</h2>
    <p class="lead">Everything the agent knows about ${agEsc(co.brand || idx.domain || "the business")}. Click anything to read it.</p>

    <h3 class="sec">The company</h3>
    <div class="ag-row"><div class="ri">
      <div class="ag-form" style="max-width:none">
        <div class="two"><label><b>Name</b><input type="text" data-agco="brand" value="${agEsc(cf.brand != null ? cf.brand : co.brand || "")}" placeholder="Company name"></label>
          <label><b>Website</b><input type="text" data-agco="domain" value="${agEsc(cf.domain != null ? cf.domain : co.domain || "")}" placeholder="example.com"></label></div>
        <label><b>One line on what they do</b><input type="text" data-agco="brand_oneliner" value="${agEsc(cf.brand_oneliner != null ? cf.brand_oneliner : co.brand_oneliner || "")}" placeholder="Drafted from the site during setup; confirm or fix it"></label>
        <label><b>The field they sell into</b><input type="text" data-agco="niche_definition" value="${agEsc(cf.niche_definition != null ? cf.niche_definition : co.niche_definition || "")}" placeholder="Used to judge whether a topic is theirs"></label>
        <div class="two"><label><b>Market for keyword numbers</b><input type="text" data-agco="location_name" value="${agEsc(cf.location_name != null ? cf.location_name : co.location_name || "United States")}"></label>
          <label><b>Language</b><input type="text" data-agco="language_code" value="${agEsc(cf.language_code != null ? cf.language_code : co.language_code || "en")}"></label></div>
        <div class="row"><button class="btn pri" type="button" data-ag="saveco">Save</button><span class="sp">${cf.msg ? agEsc(cf.msg) : co.wordpress_url ? "WordPress site · read through its own API" : ""}</span></div>
      </div></div></div>

    <div class="ag-sechead"><h3 class="sec">The site catalogue</h3>${indexed ? agCatControlsHtml(a, mapReady) : ""}</div>
    ${indexed ? `<div class="ag-row"><div class="ri">
        <div class="rn">${agEsc(idx.domain || "your site")}</div>
        <div class="rd">${agCatLine(idx)}</div>
        ${agRefreshHtml(a)}
        ${a.mapOn && mapReady ? agMapHtml(a) : ""}
        ${typeList.length ? `<div class="rm">${typeList.slice(0, 8).map(t => `<span>${agEsc(typeNames[t] || t)} <b>${agEsc(agNum(types[t]))}</b></span>`).join("")}</div>` : ""}
        <div class="ag-addrow" style="margin:12px 0 8px"><input type="search" data-agpageq placeholder="Search pages by title, address or keyword" value="${agEsc(a.pageQ || "")}" aria-label="Search pages">
          <select data-agpagetype aria-label="Page type"><option value="">All types</option>${typeList.map(t => `<option value="${agEsc(t)}" ${a.pageType === t ? "selected" : ""}>${agEsc(typeNames[t] || t)}</option>`).join("")}</select>
          ${langList.length ? `<select data-agpagelang aria-label="Language">${langList.map(c => `<option value="${agEsc(c)}" ${eff === c ? "selected" : ""}>${agEsc(langLabel(c))}</option>`).join("")}<option value="" ${eff === "" ? "selected" : ""}>All languages</option></select>` : ""}</div>
        ${pages ? `<table class="ag-pages"><thead><tr><th>Page</th><th>Type</th><th>Visits/mo</th><th>Ranks for</th><th>Text</th></tr></thead><tbody>${(pages.rows || []).map(p => `<tr><td><button class="ag-pagelink" type="button" data-ag="page" data-arg="${agEsc(p.url)}">${agEsc(p.title || agPath(p.url))}</button><div class="h">${agEsc(agPath(p.url))}</div></td><td class="m">${agEsc(typeNames[p.type] || p.type || "")}</td><td class="m">${(p.traffic_clean || p.traffic) ? agEsc(agNum(p.traffic_clean || p.traffic)) : "—"}</td><td>${p.top_keyword ? agEsc(p.top_keyword) + (p.position ? ` <small class="m">#${agEsc(p.position)}</small>` : "") : "—"}</td><td class="m">${p.body_status === "ok" ? agEsc(agNum(p.word_count)) + "w" : agEsc(p.body_status || "")}</td></tr>`).join("")}</tbody></table>
          <div class="ag-pager"><span>${agEsc(agNum(pages.offset + 1))}–${agEsc(agNum(Math.min(pages.total, pages.offset + (pages.rows || []).length)))} of ${agEsc(agNum(pages.total))}${agPagesNote([
              a.pageQ ? `matching "${agEsc(a.pageQ)}"` : "",
              a.pageType ? agEsc(typeNames[a.pageType] || a.pageType) : "",
              eff ? "in " + agEsc(langLabel(eff)) : ""].filter(Boolean), idx.page_count)}</span>
            <button class="btn" type="button" data-ag="pagesprev" ${pages.offset <= 0 ? "disabled" : ""}>Previous</button><button class="btn" type="button" data-ag="pagesnext" ${pages.offset + (pages.rows || []).length >= pages.total ? "disabled" : ""}>Next</button></div>` : `<div class="rd">Loading pages…</div>`}
      </div></div>`
      : `<div class="ag-row"><div class="ri"><div class="rn">No site catalogue yet</div><div class="rd">In the chat, give the agent the website. It reads every page and what each ranks for, and the catalogue appears here.</div></div></div>`}

    ${agBriefHtml(k.brand, !!(a.detailOpen && a.detailOpen.builtfrom))}

    ${extras}

    <h3 class="sec">Links the close may point at</h3>
    ${agCtaHtml(a.cta, a.ctaForm)}

    <h3 class="sec">Competitors · one domain per line</h3>
    <div class="ag-form"><label><textarea data-agcomps rows="5" class="mono">${agEsc(compText)}</textarea></label>
      <div class="row"><button class="btn pri" type="button" data-ag="savecomps">Save competitors</button><span class="sp">${a.compForm && a.compForm.saved ? "Saved" : "Topic ideas rotate through this list; their pages are never cited as sources"}</span></div></div>
  </div>`;
}

const AG_MAP_COLOURS = ["var(--acc)", "var(--ok)", "var(--warn)", "var(--block)", "#7c6cf0", "#2aa7c9", "#c96a2a", "#8a8a8a"];
function agMapTypes(m){
  const counts = {};
  for (const p of (m && m.points) || []) counts[p.k || "page"] = (counts[p.k || "page"] || 0) + 1;
  return Object.keys(counts).sort((x, y) => counts[y] - counts[x]);
}
function agMapLegend(m){
  return agMapTypes(m).slice(0, AG_MAP_COLOURS.length).map((t, i) => `<span><i style="background:${AG_MAP_COLOURS[i]}"></i>${agEsc(t)}</span>`).join("");
}
/* Draw the map onto the canvas that agKnowledgeHtml rendered. Not pure: it needs the
   DOM, so it runs after agDraw. Hover finds the nearest point within 8px. */
function agDrawMap(){
  if (typeof document === "undefined") return;
  const a = agS(); const cv = document.getElementById("agMap");
  if (!a || !cv || !a.map || !a.map.points) return;
  const ctx = cv.getContext("2d"); if (!ctx) return;
  const W = cv.width, H = cv.height, pad = 18;
  const types = agMapTypes(a.map);
  const colour = t => { const i = types.indexOf(t || "page"); return AG_MAP_COLOURS[i >= 0 && i < AG_MAP_COLOURS.length ? i : AG_MAP_COLOURS.length - 1]; };
  const css = getComputedStyle(document.documentElement);
  const resolve = c => c.startsWith("var(") ? (css.getPropertyValue(c.slice(4, -1)).trim() || "#888") : c;
  ctx.clearRect(0, 0, W, H);
  const pts = a.map.points;
  const sx = x => pad + (x + 1) / 2 * (W - 2 * pad), sy = y => pad + (1 - (y + 1) / 2) * (H - 2 * pad);
  cv.__agPts = [];
  for (const p of pts){
    const x = sx(p.x), y = sy(p.y);
    const r = 2 + Math.min(4, Math.log10(1 + (p.v || 0)));
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = resolve(colour(p.k)); ctx.globalAlpha = 0.72; ctx.fill(); ctx.globalAlpha = 1;
    cv.__agPts.push([x, y, p]);
  }
  if (!cv.__agHover){
    cv.__agHover = true;
    const nearest = ev => {
      const rect = cv.getBoundingClientRect();
      const mx = (ev.clientX - rect.left) * (cv.width / rect.width), my = (ev.clientY - rect.top) * (cv.height / rect.height);
      let best = null, bd = 64;
      for (const [x, y, p] of (cv.__agPts || [])){ const d = (x - mx) * (x - mx) + (y - my) * (y - my); if (d < bd){ bd = d; best = p; } }
      return { best, rect };
    };
    cv.addEventListener("mousemove", ev => {
      const { best, rect } = nearest(ev);
      const tip = document.getElementById("agMapTip"); if (!tip) return;
      if (!best){ tip.hidden = true; return; }
      tip.hidden = false; tip.textContent = (best.t || agPath(best.u)) + (best.k ? "  ·  " + best.k : "") + (best.v ? "  ·  " + agNum(best.v) + " visits/mo" : "");
      tip.style.left = Math.min(rect.width - 260, (ev.clientX - rect.left) + 12) + "px"; tip.style.top = ((ev.clientY - rect.top) + 12) + "px";
    });
    cv.addEventListener("mouseleave", () => { const tip = document.getElementById("agMapTip"); if (tip) tip.hidden = true; });
    cv.addEventListener("click", ev => { const { best } = nearest(ev); if (best) agOpenPage(best.u); });
  }
}

/* What is worth writing about, and what has been written. The one row a person acts on is the
   next open idea, so it sits at the top as a chip that WRITES THE MESSAGE. The chip carries the
   idea's id in a data attribute, never in the prose, so nothing downstream has to read an id out
   of a sentence and decide to look it up. */
function agAssetsHtml(as, a){
  if (!as) return `<div class="ag-view"><h2>Asset ideas</h2><p class="lead">Reading…</p></div>`;
  const c = as.counts || {};
  const busy = a && a.assetsBusy;
  if (!as.built) return `<div class="ag-view"><h2>Asset ideas</h2>
    <p class="lead">What is worth writing about, worked out from evidence rather than a hunch.</p>
    <div class="ag-row"><div class="ri"><div class="rn">Not built yet</div>
      <div class="rd">Three ways of finding ideas, kept apart until the end: which competitor pages
        actually earn links and the shape that earned them, formats proven in other industries, and
        what your audience argues about in public. Then they are merged, ranked, and checked against
        pages you already have.<br><br>It takes about half an hour and it stops twice to ask you:
        once for the competitor list, once for the communities.</div>
      <div class="ag-editrow" style="margin-top:10px">
        <button class="btn pri" type="button" data-ag="assetsbuild" ${busy ? "disabled" : ""}>${busy ? "Starting…" : "Work out what to write"}</button>
        <span class="ag-sub">It runs in the chat, so you can watch it and answer as it goes.</span>
      </div></div></div></div>`;

  const nx = as.next;
  const blocked = as.methods_blocked || [];
  const rows = as.rows || [];
  const filt = (a && a.assetFilter) || "open";
  const matching = rows.filter(r => filt === "all" ? true : (r.status || "open") === filt);
  // Paged, and not optionally. The owner's own run produced 1,892 ideas; drawn in one go that is
  // 41,000 DOM nodes and a page 165,000 pixels tall, which is not a list anybody can use. Found by
  // loading his real sheet, 2026-09-09. Same page size and same control as the site catalogue, so
  // there is one idiom on this screen and not two.
  const off = Math.min((a && a.assetOffset) || 0, Math.max(0, matching.length - 1));
  const shown = matching.slice(off, off + AG_IDEA_LIMIT);
  return `<div class="ag-view wide"><h2>Asset ideas</h2>
    <p class="lead">${agEsc(agNum(as.total))} ideas${c.done ? `, ${agEsc(agNum(c.done))} written` : ""}.
      ${as.methods_line ? agEsc(as.methods_line)
        : blocked.length ? `${3 - blocked.length} of 3 methods contributed; ${agEsc(blocked.map(agMethodName).join(" and "))} did not.`
        : "All three methods contributed."}</p>

    ${nx ? `<div class="ag-nextidea">
      <div class="nl">Next up</div>
      <div class="nt">${agEsc(nx.title)}</div>
      <div class="nd">${agEsc(nx.angle || "")}</div>
      <div class="nm">${agEsc(nx.format || "")}${(nx.method || []).length ? " · found by " + agEsc((nx.method || []).map(agMethodName).join(" and ")) : ""}${nx.linkability && nx.linkability.score ? ` · ${agEsc(nx.linkability.score)}/${agEsc(nx.linkability.of || 4)} on whether anyone would cite it` : ""}</div>
      <div class="ag-editrow">
        <button class="btn pri" type="button" data-ag="ideawrite" data-arg="${agEsc(nx.id)}"
          data-text="${agEsc("Write this asset idea: " + nx.title)}">Write this one</button>
        <button class="btn" type="button" data-ag="ideadrop" data-arg="${agEsc(nx.id)}">Not this one</button>
      </div>
      <div class="nw">This can still be turned down later. The topic gate reads the live search
        results, and if they argue for a different intent than this idea assumes, it stops rather
        than write the wrong article.</div>
    </div>` : `<div class="ag-row"><div class="ri"><div class="rn">Nothing left to write</div>
        <div class="rd">Every idea on the sheet is written or dropped. Ask for the ideas to be rebuilt when you want more.</div></div></div>`}

    <div class="ag-editrow" style="margin:14px 0 8px">
      ${[["open", "To write"], ["done", "Written"], ["dropped", "Dropped"], ["all", "All"]].map(f =>
        `<button class="btn ${filt === f[0] ? "pri" : ""}" type="button" data-ag="assetfilter" data-arg="${f[0]}">${f[1]}${f[0] !== "all" ? ` ${agEsc(agNum(c[f[0]] || 0))}` : ""}</button>`).join("")}
    </div>

    ${matching.length > AG_IDEA_LIMIT ? `<div class="ag-pager" style="margin:0 0 8px">
      <span>${agEsc(agNum(off + 1))}–${agEsc(agNum(Math.min(matching.length, off + shown.length)))} of ${agEsc(agNum(matching.length))}</span>
      <button class="btn" type="button" data-ag="ideaprev" ${off <= 0 ? "disabled" : ""}>Previous</button>
      <button class="btn" type="button" data-ag="ideanext" ${off + shown.length >= matching.length ? "disabled" : ""}>Next</button></div>` : ""}
    ${shown.length ? `<table class="ag-pages"><thead><tr><th>Idea</th><th>Shape</th><th>Found by</th><th>Cite it?</th><th>Have it?</th></tr></thead><tbody>${shown.map(r => `<tr>
      <td><button class="ag-pagelink" type="button" data-ag="ideaopen" data-arg="${agEsc(r.id)}">${agEsc(r.title || r.id)}</button>
        <div class="h">${agEsc((r.angle || "").slice(0, 110))}</div>
        ${r.status === "done" ? `<span class="pill p-ok">written</span>` : r.status === "dropped" ? `<span class="pill p-mut">dropped</span>` : ""}</td>
      <td class="m">${agEsc(r.format || "")}</td>
      <td class="m">${agEsc((r.method || []).map(agMethodName).join(", "))}</td>
      <td class="m">${r.linkability && r.linkability.score != null ? agEsc(r.linkability.score) + "/" + agEsc(r.linkability.of || 4) : "—"}</td>
      <td class="m">${agEsc((r.reuse && r.reuse.verdict) || "—")}</td></tr>`).join("")}</tbody></table>`
      : `<div class="ag-row"><div class="ri"><div class="rd">Nothing in this list.</div></div></div>`}
  </div>`;
}

/* The method names as a person would say them, never as the folder is called. */
const AG_IDEA_LIMIT = 25;      // one page of the sheet, the same as the site catalogue's table
const AG_METHOD_NAMES = {"competitors": "the competitor study", "formats": "other industries",
                         "trends": "what your audience argues about",
                         // the builders' own METHOD constants, as the workflow names them
                         "competitor-study": "the competitor study",
                         "model-other-niches": "other industries",
                         "study-trends": "what your audience argues about",
                         "imported": "a sheet you loaded"};
function agMethodName(m){ return AG_METHOD_NAMES[m] || m; }

function agMemoryHtml(m, form){
  const rules = (m && m.rules) || [];
  return `<div class="ag-view"><h2>Memory</h2>
    <p class="lead">Standing rules about your taste. Every step that shapes or writes prose reads them: the plan, the headings, each section, the edits, the intro and the close. The agent saves one when you say something that should hold for every future article. Add your own here.</p>
    <div class="ag-addrow"><input type="text" data-agmem placeholder="e.g. Never open an article with a question" value="${agEsc(form && form.text || "")}" aria-label="New rule"><button class="btn pri" type="button" data-ag="addmem">Add rule</button></div>
    ${rules.length ? rules.map(r => `<div class="ag-row ${r.active === false ? "off" : ""}"><div class="ri"><div class="rn">${agEsc(r.text)}</div>
        <div class="rm"><span>${agEsc(r.kind || "rule")}</span><span>${r.source === "agent" ? "saved by the agent" : "added by you"}</span><span>${agEsc(agAgo(r.t))}</span></div></div>
        <div class="ra"><button class="ag-switch" type="button" role="switch" aria-checked="${r.active !== false}" data-ag="togglemem" data-arg="${agEsc(r.id)}" aria-label="Rule on or off"></button></div></div>`).join("")
      : `<div class="ag-row"><div class="ri"><div class="rn">No rules yet</div><div class="rd">Tell the agent something like “always use British spelling” and it will ask to save it.</div></div></div>`}
  </div>`;
}

/* One row's progress strip: the smaller sibling of agStagesHtml in the chat, in the same three
   states and the same colours (done, the one being worked on now, still ahead). It has to stay one
   line, because the Library is a list you scan and not a dashboard, so it is chips with a dot each
   and nothing else. A milestone that exists is a button that opens that file in the panel; one
   that does not is a <span>, never a disabled button, so there is nothing to click and nothing to
   reach with the keyboard. No milestones at all means the payload predates them, and the strip is
   simply not drawn: the row keeps exactly the shape it had. */
function agMileStripHtml(id, miles, writing){
  const list = miles || [];
  if (!list.length) return "";
  /* only a row still being written has a "now" step; a stopped run's gaps are gaps, not promises */
  const nextIdx = writing ? list.findIndex(m => !m.exists) : -1;
  return `<div class="ag-miles" aria-label="What is made so far">${list.map((m, i) => {
    const label = m.label || AG_MILE_LABEL[m.key] || m.key;
    if (!m.exists){
      const cur = i === nextIdx;
      return `<span class="ag-mile ${cur ? "cur" : "todo"}" title="${agEsc(cur ? "being made now" : "not made yet")}"><i aria-hidden="true"></i>${agEsc(label)}</span>`;
    }
    return `<button class="ag-mile done" type="button" data-ag="libmile" data-arg="${agEsc(id)}" data-name="${agEsc(m.key)}" data-label="${agEsc(label)}"
      title="${agEsc((m.note || label) + (m.at ? " · " + agAgo(m.at) : ""))}"><i aria-hidden="true"></i>${agEsc(label)}</button>`;
  }).join("")}</div>`;
}

/* The Library. A row is born the moment a run starts (see AG_LIB_STATE), so this list mixes
   articles being written with articles that are done, and the whole job of the markup is making
   that difference obvious in a glance down the page: a row being written is the only one with the
   accent edge, a turning marker in its pill and a count of how far it has got.
   It offers no Open and no Mark ready while it is writing. There is nothing whole to open yet, and
   the run would overwrite a state set by hand when it finishes. The way into a half-made article
   is the strip, which is the point of the strip. */
function agLibraryHtml(items){
  const list = items || [];
  const bin = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>`;
  return `<div class="ag-view"><h2>Library</h2>
    <p class="lead">Every article, from the moment it starts. A row appears as soon as the agent begins and fills in piece by piece, so you can read any part of one while the rest is still being made. Nothing leaves this Mac; publishing is your step.</p>
    ${list.length ? list.map(it => {
      const status = it.status || "draft";
      const writing = status === "writing";
      const miles = it.milestones || [];
      const done = miles.filter(m => m.exists).length;
      const state = AG_LIB_STATE[status] || ["p-mut", status];
      /* A row born at run start is called "Writing…" until the real title exists, and the pill
         beside it already says writing, so the name is saying nothing twice. What he asked for is
         on the row (`request`), so use that: it is the only thing that identifies the article
         before it has a title, and the row renames itself the moment there is one. */
      const name = (writing && it.request) || it.title;
      return `<div class="ag-row ${writing ? "writing" : ""}"><div class="ri"><div class="rn">${agEsc(name)} <span class="pill ${state[0]}">${writing ? `<i class="spin" aria-hidden="true"></i>` : ""}${agEsc(state[1])}</span></div>
        <div class="rm">${writing && miles.length ? `<span>${agEsc(done)} of ${agEsc(miles.length)} done</span>` : `<span>${agEsc(agNum(it.words))} words</span>`}${it.primary_keyword ? `<span>${agEsc(it.primary_keyword)}</span>` : ""}<span>${writing ? "started " : ""}${agEsc(agAgo(it.created_at))}</span></div>
        ${agMileStripHtml(it.id, miles, writing)}</div>
        <div class="ra">${writing ? "" : `<button class="btn" type="button" data-ag="libopen" data-arg="${agEsc(it.id)}">Open</button>
          <button class="btn" type="button" data-ag="libstatus" data-arg="${agEsc(it.id)}" data-status="${status === "ready" ? "draft" : "ready"}">${status === "ready" ? "Back to draft" : "Mark ready"}</button>`}
          <button class="ib" type="button" data-ag="libdel" data-arg="${agEsc(it.id)}" aria-label="Delete" title="Delete this article">${bin}</button></div></div>`;
    }).join("")
      : `<div class="ag-row"><div class="ri"><div class="rn">Nothing here yet</div><div class="rd">Ask for an article and its row appears here straight away, filling in as each piece is made.</div></div></div>`}
  </div>`;
}

function agToolsHtml(tools){
  const list = tools || [];
  return `<div class="ag-view"><h2>Tools</h2>
    <p class="lead">The seven things the agent can do, in the order they usually run. Setup runs once. The last four run for every article, and you look at the result of each before the next starts.</p>
    ${list.map((t, i) => `<div class="ag-row"><div class="ri"><div class="rn"><span class="n">${i + 1}</span>${agEsc(t.label || String(t.name || "").replace(/_/g, " "))}</div>
        <dl class="ag-kv" style="margin:8px 0 0">
          <dt>What it does</dt><dd>${agEsc(t.does || t.description || "")}</dd>
          ${t.when ? `<dt>When it runs</dt><dd>${agEsc(t.when)}</dd>` : ""}
          ${t.needs ? `<dt>What it needs</dt><dd>${agEsc(t.needs)}</dd>` : ""}
          ${t.takes ? `<dt>How long</dt><dd>${agEsc(t.takes)}</dd>` : ""}
        </dl></div></div>`).join("")}
  </div>`;
}

function agConnectionsHtml(c, h, form){
  const dfs = !!(c && c.dataforseo_login && c.dataforseo_password);
  const voy = !!(c && c.voyage_key);
  const prov = h ? h.model_provider : null;
  form = form || {};
  return `<div class="ag-view"><h2>Connections</h2>
    <p class="lead">Three things the agent needs. Secrets are stored on this Mac, owner-only, and never sent back to this screen.</p>
    <h3 class="sec">Model</h3>
    <div class="ag-row"><div class="ri"><div class="rn">${prov === "claude-cli" ? "Claude, through the command line" : prov ? agEsc(prov) : "No model available"}
        <span class="ag-status"><i class="dot ${prov ? "ok" : "bad"}"></i>${prov === "claude-cli" ? "billed to your Claude subscription" : prov ? "connected" : "not signed in"}</span></div>
      <div class="rd">${prov ? "The same sign-in the chat uses. No API key anywhere." : "Open a terminal, run <code>claude</code> once and sign in. This screen will notice."}</div></div></div>
    <h3 class="sec">DataForSEO · real search numbers</h3>
    <div class="ag-row"><div class="ri"><div class="rn">DataForSEO <span class="ag-status"><i class="dot ${dfs ? "ok" : "warn"}"></i>${dfs ? "connected" : "not connected"}</span></div>
      <div class="rd">Keyword volumes, difficulty, who ranks, the questions people ask and Google's own answer come from here. Research needs it. Each research run costs under a dollar of their credit.</div>
      <div class="ag-form" style="margin-top:10px">
        <label><b>Login</b><input type="text" data-agdfs="login" autocomplete="off" placeholder="${dfs ? "•••••• (set)" : "the email you sign in with"}" value="${agEsc(form.login || "")}"></label>
        <label><b>API password</b><input type="password" data-agdfs="password" autocomplete="off" placeholder="${dfs ? "•••••• (set)" : "from app.dataforseo.com → API access"}" value="${agEsc(form.password || "")}"></label>
        <div class="row"><button class="btn pri" type="button" data-ag="savedfs">Save</button>${dfs ? `<button class="btn" type="button" data-ag="cleardfs">Disconnect</button>` : ""}<span class="sp">${form.msg ? agEsc(form.msg) : ""}</span></div>
      </div></div></div>
    <h3 class="sec">Voyage · pages indexed by meaning</h3>
    <div class="ag-row"><div class="ri"><div class="rn">Voyage <span class="ag-status"><i class="dot ${voy ? "ok" : "warn"}"></i>${voy ? "connected" : "not connected"}</span></div>
      <div class="rd">Reads every page and works out what it is about, so the agent can find the right page of yours to link to from each section, and tell whether you already write about a topic. The free tier is enough for a whole site.</div>
      <div class="ag-form" style="margin-top:10px">
        <label><b>API key</b><input type="password" data-agvoy="key" autocomplete="off" placeholder="${voy ? "•••••• (set)" : "pa-… from dash.voyageai.com"}" value="${agEsc(form.voyage || "")}"></label>
        <div class="row"><button class="btn pri" type="button" data-ag="savevoy">Save</button>${voy ? `<button class="btn" type="button" data-ag="clearvoy">Disconnect</button>` : ""}<span class="sp">${form.vmsg ? agEsc(form.vmsg) : ""}</span></div>
      </div></div></div>
  </div>`;
}

/* ── the screen shell (what render() sees) ─────────────────────────────────── */
if (typeof SCREENS !== "undefined"){
  SCREENS.agents = () => `<div class="ag" id="agRoot" data-ag-shell></div>`;
}
if (typeof TITLES !== "undefined"){
  TITLES.agents = ["Agents", "agents that work in front of you"];
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

/* Opening the review panel narrows this column: .haspanel gives 46% of the row to the panel,
   so every block in the settings document rewraps and the company form drops to one column.
   The browser keeps the same scrollTop through that, but the content that lives at that pixel
   is no longer the content that lived there, and when the document gets shorter the browser
   clamps scrollTop as well. Both read as the page jumping. The chat view never shows it
   because agDraw puts that column back where it was on every redraw; the settings views had
   nothing of the kind. So: note which block is at the top of the viewport before the class
   flips, and put it back there after. Reading and setting scrollTop is what agDraw already
   does for the chat, so this stays inside that precedent. */
function agScrollAnchor(scroll){
  const view = scroll && scroll.firstElementChild; if (!view) return null;
  const kids = view.children || []; const base = scroll.getBoundingClientRect().top;
  let anc = null;
  for (let i = 0; i < kids.length; i++){
    const top = kids[i].getBoundingClientRect().top - base;
    if (top <= 1) anc = { idx: i, delta: top }; else break;
  }
  return anc;
}
function agScrollRestore(scroll, anc){
  if (!scroll || !anc) return;
  const view = scroll.firstElementChild; if (!view) return;
  const el = (view.children || [])[anc.idx]; if (!el) return;
  scroll.scrollTop += (el.getBoundingClientRect().top - scroll.getBoundingClientRect().top) - anc.delta;
}

function agDraw(force){
  const a = agS(); const root = agRoot(); if (!a || !root) return;
  const scroll = document.getElementById("agScroll");
  const panelFlips = root.classList.contains("haspanel") !== !!a.panel;
  const anchor = (panelFlips && a.view !== "chat" && scroll) ? agScrollAnchor(scroll) : null;
  root.classList.toggle("haspanel", !!a.panel);
  agSetHtml("agSide", agSideHtml(a));
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
    const html = a.view === "knowledge" ? agKnowledgeHtml(a.knowledge, a)
      : a.view === "assets" ? agAssetsHtml(a.assets, a)
      : a.view === "memory" ? agMemoryHtml(a.memory, a.memForm)
      : a.view === "library" ? agLibraryHtml(a.library)
      : a.view === "tools" ? agToolsHtml(a.tools)
      : agConnectionsHtml(a.conns, a.health, a.connForm);
    const searching = document.activeElement && document.activeElement.matches && document.activeElement.matches("[data-agpageq]");
    const sel = searching ? document.activeElement.selectionStart : null;
    if (agSetHtml("agScroll", html) && searching){
      const q = document.querySelector("[data-agpageq]"); if (q){ try { q.focus({ preventScroll: true }); q.setSelectionRange(sel, sel); } catch (e) {} }
    }
    if (a.view === "knowledge" && a.mapOn) agDrawMap();
    const comp = document.getElementById("agComposer"); if (comp){ comp.hidden = true; }
  }
  /* the Library editor redraws while he types (the word count is live), so put the caret back
     exactly where the composer branch above puts its own */
  const act = document.activeElement;
  const typing = act && act.matches && act.matches("[data-aglibbody],[data-aglibtitle]")
    ? { sel: act.getAttribute("data-aglibbody") != null ? "[data-aglibbody]" : "[data-aglibtitle]",
        from: act.selectionStart, to: act.selectionEnd } : null;
  if (agSetHtml("agPanel", a.panel ? agPanelHtml(a) : "") && typing){
    const back = document.querySelector(typing.sel);
    if (back){ try { back.focus({ preventScroll: true }); back.setSelectionRange(typing.from, typing.to); } catch (e) {} }
  }
  if (anchor) agScrollRestore(document.getElementById("agScroll"), anchor);
  a.lastView = a.view;
}

function agGrow(ta){
  if (!ta) return;
  ta.style.height = "auto";
  ta.style.height = Math.min(160, Math.max(22, ta.scrollHeight)) + "px";
}

/* Polling: one second while a run is live, four when idle, none when hidden.
   A Library row being written counts as live too. It is the same timer and the same two speeds,
   not a second clock: watching a row fill in is exactly the case the fast cadence was built for,
   and the milestones would otherwise never appear without a manual reload. */
function agStartPoll(){
  if (agPollTimer) return;
  const tick = async () => {
    agPollTimer = null;
    if (!agRoot()){ return; }
    const a = agS();
    if (!(typeof document !== "undefined" && document.hidden)){
      try { await agRefresh(); } catch (e) { a.error = String(e && e.message || e); }
    }
    const live = agLiveRun() || (a && a.view === "library" && agLibWriting(a));
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
    /* The Library refreshes itself only while it is the screen in front of him AND something can
       change on it: a run going, or a row still being written. Off that screen, or with nothing
       moving, this stays exactly as quiet as it was before the live Library existed. */
    if (a.view === "library" && (live || agLibWriting(a))){
      a.library = await agApi("/library").catch(() => a.library);
    }
    if (agRefreshN % 8 === 1 || (live && agRefreshN % 20 === 0)){ a.health = await agApi("/health"); }
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
  try { a.knowledge = await agApi("/knowledge"); } catch (e) {}
  try { a.cta = await agApi("/knowledge/cta"); } catch (e) {}
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
  a.bpEdit = null; a.artEdit = null; a.lastEdit = null; a.fileEdit = null; a.libEdit = null;
  a.trail = []; a.workOpen = null;
  agDraw();
  try {
    const d = await agApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(runId)}/artifact/${encodeURIComponent(name)}`);
    if (a.panel && a.panel.name === name){ a.panel.data = d; a.panel.loading = false; }
    if (view === "topic_list" && !a.picked && d && d.topics){
      const rec = d.topics.find(t => t.recommended); a.picked = rec ? rec.id : null;
    }
    if (view === "research_brief" && a.panel && a.panel.name === name){
      /* every step of the research kept its own file; the panel lists them so one can be opened */
      const t = await agApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(runId)}/trail`).catch(() => null);
      a.trail = (t && t.rows) || [];
    }
    if (view === "article" && a.panel && a.panel.name === name){
      /* the receipts beside the draft: which links were laid in, and the coverage counts */
      const base = `/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(runId)}/artifact/`;
      a.panel.links = await agApi(base + "links-report.json").catch(() => null);
      a.panel.write = await agApi(base + "write-report.json").catch(() => null);
    }
  } catch (e) { if (a.panel){ a.panel.loading = false; a.panel.error = String(e && e.message || e); } }
  agDraw();
}

/* Opening one milestone of a Library row. It reads the run's own file THROUGH the Library, so a
   piece can be read while the run that is making it carries on, and nothing has to be copied to
   serve it. Read-only by construction: the panel has no run_id, because there is no run to answer.
   Built to survive a server that has not caught up. The route is new, and an older one answers
   404 for every name; a failure has to land as a sentence in the panel rather than leaving it on
   "Reading…" for ever, so the catch says what happened in his words. */
async function agOpenLibMilestone(itemId, key, label){
  const a = agS();
  const name = "lib:" + itemId + ":" + key;
  a.panel = { run_id: null, name, view: AG_MILE_VIEW[key] || "", data: null, loading: true, error: null,
              title: label || AG_MILE_LABEL[key] || key, subtitle: "", readOnly: true, libMile: key };
  a.bpEdit = null; a.artEdit = null; a.lastEdit = null; a.fileEdit = null; a.libEdit = null;
  a.trail = []; a.workOpen = null;
  agDraw();
  try {
    const d = await agApi(`/library/${encodeURIComponent(itemId)}/artifact/${encodeURIComponent(key)}`);
    if (!a.panel || a.panel.name !== name) return;           /* he clicked something else meanwhile */
    a.panel.data = (d && d.data != null) ? d.data : { text: (d && d.text) || "" };
    a.panel.title = (d && d.label) || a.panel.title;
    a.panel.subtitle = (d && (d.note || d.file)) || "";
    a.panel.loading = false;
  } catch (e) {
    if (a.panel && a.panel.name === name){
      a.panel.loading = false;
      a.panel.error = "Could not read this part: " + String(e && e.message || e);
    }
  }
  agDraw();
}

async function agOpenBrandFile(name, back, label){
  const a = agS();
  a.panel = { run_id: null, name: "brand/" + name, view: "brand_file", data: null, loading: true, error: null,
              title: label || (AG_BRAND_FILES.find(r => r[0] === name) || [name, name])[1], subtitle: name, back: !!back };
  a.fileEdit = null; a.libEdit = null; agDraw();
  try { a.panel.data = await agApi(`/knowledge/brand/${encodeURIComponent(name)}`); a.panel.loading = false; }
  catch (e) { a.panel.loading = false; a.panel.error = String(e && e.message || e); }
  agDraw();
}

async function agOpenPage(url){
  const a = agS();
  a.panel = { run_id: null, name: "page:" + url, view: "page", data: null, loading: true, error: null, title: "Page", subtitle: agPath(url) };
  agDraw();
  try { const d = await agApi(`/knowledge/page?url=${encodeURIComponent(url)}`); a.panel.data = d; a.panel.title = d.title || agPath(url); a.panel.loading = false; }
  catch (e) { a.panel.loading = false; a.panel.error = String(e && e.message || e); }
  agDraw();
}

/* The list as it stands on screen: the draft if there is one, otherwise what the server sent.
   Always a fresh copy, so a draft edit never writes into a.cta behind Save's back. */
function agCtaRows(a){
  const src = (a.ctaForm && a.ctaForm.rows) || (a.cta && a.cta.rows) || [];
  /* title rides along so an edit does not lose it; it is never posted back */
  return src.map(r => ({ url: r.url || "", note: r.note || "", mine: !!r.mine, title: r.title }));
}

async function agLoadPages(offset){
  const a = agS();
  const k = a.knowledge || {};
  const lang = agEffLang(a, k.site_index || {}, k.company || {});
  const params = `offset=${encodeURIComponent(offset || 0)}&limit=${AG_PAGE_LIMIT}&q=${encodeURIComponent(a.pageQ || "")}`
    + `&type=${encodeURIComponent(a.pageType || "")}&lang=${encodeURIComponent(lang)}`;
  try { a.pages = await agApi(`/knowledge/pages?${params}`); } catch (e) { a.pages = { total: 0, offset: 0, rows: [] }; }
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
      // The idea's id travels BESIDE the message, never inside it. Cleared immediately: an id
      // left on the state would silently attach itself to whatever the user typed next, and the
      // wrong article would tick the wrong idea off the sheet.
      const idea = a.chipIdea || "";
      a.chipIdea = null;
      await agPostApi(`/chats/${encodeURIComponent(a.chatId)}/send`, idea ? { text, idea } : { text });
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
      if (arg === "knowledge"){ a.knowledge = await agApi("/knowledge").catch(() => null); a.health = await agApi("/health").catch(() => a.health); agDraw(true); await agLoadPages(0); a.cta = await agApi("/knowledge/cta").catch(() => a.cta); if (a.mapOn && !a.map){ a.map = await agApi("/knowledge/embedding-map").catch(() => null); } }
      if (arg === "assets") a.assets = await agApi("/assets").catch(() => null);
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
    case "work": {
      const p = a.panel; if (!p) break;
      a.workOpen = { label: arg, data: { loading: true } }; agDraw();
      try {
        const r = await agApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(p.run_id)}/work/${encodeURIComponent(arg)}`);
        a.workOpen = { label: r.label || arg, data: r.data };
      } catch (e) { a.workOpen = { label: arg, data: { error: String(e && e.message || e) } }; }
      agDraw(); break;
    }
    case "workclose": a.workOpen = null; agDraw(); break;
    case "stageopen": {
      /* the default is computed, so record the opposite of what is on screen right now */
      const now = el.getAttribute("aria-expanded") === "true";
      a.stageOpen[arg] = !now; agDraw(); break;
    }
    case "more": case "detail": a.detailOpen[arg] = !a.detailOpen[arg]; agDraw(); break;
    case "choose": await agAnswer({ choice: el.getAttribute("data-label") || "" }); break;
    case "approve": await agAnswer({ approved: arg === "yes" }); break;
    case "open": {
      const run = el.getAttribute("data-run") || (agLastRun() || {}).run_id;
      if (a.panel && a.panel.name === arg && a.panel.run_id === run){ a.panel = null; agDraw(); }
      else await agOpenArtifact(run, arg, el.getAttribute("data-view") || "article");
      break;
    }
    case "closepanel": a.panel = null; a.fileEdit = null; a.libEdit = null; agDraw(); break;
    case "back": {
      const live = agLiveRun();
      if (live && live.waiting_on && live.waiting_on.artifact === "brand") await agOpenArtifact(live.run_id, "brand", "brand_pack");
      else { a.panel = null; agDraw(); }
      break;
    }
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

    /* The chip that writes the message. It fills the composer with WORDS, and separately parks the
       idea's ID on the state. The id then travels beside the message on send, never inside it, so
       nothing downstream has to read an id out of prose. See agSend. */
    case "ideawrite": {
      a.draft = el.getAttribute("data-text") || "";
      a.chipIdea = arg;
      a.view = "chat"; a.panel = null; a.focusComposer = true;
      agDraw(true); break;
    }
    case "ideadrop": {
      try { a.assets = await agPostApi(`/assets/${encodeURIComponent(arg)}/status`, { status: "dropped" }); }
      catch (e) { agToast("Could not drop it: " + (e && e.message || e)); }
      agDraw(true); break;
    }
    case "assetfilter": a.assetFilter = arg; a.assetOffset = 0; agDraw(true); break;
    case "ideaprev": a.assetOffset = Math.max(0, ((a.assetOffset || 0) - AG_IDEA_LIMIT)); agDraw(true); break;
    case "ideanext": a.assetOffset = (a.assetOffset || 0) + AG_IDEA_LIMIT; agDraw(true); break;
    case "ideaopen": {
      a.panel = { run_id: null, name: "idea:" + arg, view: "idea", data: null, loading: true,
                  error: null, title: "Asset idea", subtitle: arg };
      agDraw();
      try { const d = await agApi(`/assets/${encodeURIComponent(arg)}`); a.panel.data = d;
            a.panel.title = d.title || arg; a.panel.loading = false; }
      catch (e) { a.panel.loading = false; a.panel.error = String(e && e.message || e); }
      agDraw(); break;
    }
    case "assetsbuild": {
      a.assetsBusy = true; agDraw();
      try {
        await agSend("Work out what is worth writing about. Build the asset ideas.");
        a.view = "chat";
      } catch (e) { agToast("Could not start it: " + (e && e.message || e)); }
      a.assetsBusy = false; agDraw(true); break;
    }
    case "bpmove": {
      const secs = a.panel && a.panel.data && a.panel.data.sections; if (!secs) break;
      const i = secs.findIndex((s, k) => (s.id || ("s" + (k + 1))) === arg), j = i + Number(el.getAttribute("data-dir") || 0);
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
    /* knowledge */
    case "brandfile": await agOpenBrandFile(arg, !!(a.panel && a.panel.view === "brand_pack"), el.getAttribute("data-label") || ""); break;
    case "fileedit": { const d = a.panel && a.panel.data; a.fileEdit = { text: d && typeof d.text === "string" ? d.text : JSON.stringify(d, null, 2) }; agDraw(); break; }
    case "filecancel": a.fileEdit = null; agDraw(); break;
    case "filesave": {
      const ta = document.querySelector("[data-agfiletext]"); if (!ta || !a.panel) break;
      const name = a.panel.name.replace(/^brand\//, "");
      a.fileEdit = { text: ta.value, busy: true }; agDraw();
      try {
        const body = name.endsWith(".json") ? { data: JSON.parse(ta.value) } : { text: ta.value };
        await agPostApi(`/knowledge/brand/${encodeURIComponent(name)}`, body);
        a.panel.data = await agApi(`/knowledge/brand/${encodeURIComponent(name)}`);
        a.fileEdit = null; a.knowledge = await agApi("/knowledge").catch(() => a.knowledge); agToast("Saved");
      } catch (e) { a.fileEdit = { text: ta.value, busy: false, msg: "Could not save: " + (e.message || e) }; }
      agDraw(); break;
    }
    /* the pages a close may point at: the draft lives on a.ctaForm until Save, the same way
       the competitors box and the company form hold theirs */
    case "ctaadd": { const rows = agCtaRows(a); rows.push({ url: "", note: "", mine: true }); a.ctaForm = { rows }; agDraw(); break; }
    case "ctadel": { const rows = agCtaRows(a); rows.splice(Number(arg), 1); a.ctaForm = { rows }; agDraw(); break; }
    case "ctasave": {
      const rows = agCtaRows(a);
      const send = rows.map(r => ({ url: String(r.url || "").trim(), note: String(r.note || "").trim() })).filter(r => r.url);
      a.ctaForm = { rows, busy: true }; agDraw();
      try { a.cta = await agPostApi("/knowledge/cta", { rows: send }); a.ctaForm = null; agToast("Saved"); }
      catch (e) { a.ctaForm = { rows, busy: false, msg: "Could not save: " + (e.message || e) }; }
      agDraw(); break;
    }
    case "page": await agOpenPage(arg); break;
    case "pagesprev": await agLoadPages(Math.max(0, ((a.pages && a.pages.offset) || 0) - AG_PAGE_LIMIT)); break;
    case "pagesnext": await agLoadPages(((a.pages && a.pages.offset) || 0) + AG_PAGE_LIMIT); break;
    case "map": {
      a.mapOn = !a.mapOn; agDraw();
      if (a.mapOn && !a.map){ a.map = await agApi("/knowledge/embedding-map").catch(e => { agToast(String(e.message || e)); return null; }); agDraw(); }
      break;
    }
    case "saveco": {
      const rec = {};
      document.querySelectorAll("[data-agco]").forEach(i => { rec[i.getAttribute("data-agco")] = i.value; });
      try { await agPostApi("/knowledge", { company: rec }); a.coForm = { msg: "Saved" }; a.knowledge = await agApi("/knowledge"); }
      catch (e) { a.coForm = Object.assign({}, rec, { msg: "Could not save: " + (e.message || e) }); }
      agDraw(); break;
    }
    case "savecomps": {
      const ta = document.querySelector("[data-agcomps]"); const lines = ta ? ta.value.split("\n").map(s => s.trim()).filter(Boolean) : [];
      try { await agPostApi("/knowledge", { competitors: { competitors: lines } }); a.compForm = { text: lines.join("\n"), saved: true }; a.knowledge = await agApi("/knowledge"); }
      catch (e) { agToast("Could not save: " + (e.message || e)); }
      agDraw(); break;
    }
    /* memory, library */
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
        a.panel = { run_id: it.run_id, name: "draft.md", view: "article", data: { text: it.draft || "" }, loading: false,
                    readOnly: true, libId: it.id, title: it.title, subtitle: `${agNum(it.words)} words · ${it.status || "draft"}` };
        a.libEdit = null; }
      catch (e) { agToast("Could not open: " + (e.message || e)); }
      agDraw(); break;
    }
    case "libmile": {
      const key = el.getAttribute("data-name") || "";
      /* clicking the one already open shuts it, the same as the transcript's artifact card */
      if (a.panel && a.panel.name === "lib:" + arg + ":" + key){ a.panel = null; agDraw(); }
      else await agOpenLibMilestone(arg, key, el.getAttribute("data-label") || "");
      break;
    }
    case "libedit": {
      const p2 = a.panel; if (!p2) break;
      a.libEdit = { title: p2.title || "", draft: (p2.data && p2.data.text) || "", busy: false, error: "" };
      agDraw();
      setTimeout(() => { const t = document.querySelector("[data-aglibbody]"); if (t) t.focus(); }, 0);
      break;
    }
    case "libcancel": a.libEdit = null; agDraw(); break;
    case "libsave": {
      const ed = a.libEdit; if (!ed) break;
      const title = String(ed.title || "").trim(), draft = String(ed.draft || "");
      if (!draft.trim()){ a.libEdit = { title, draft, busy: false, error: "An empty article is not a save." }; agDraw(); break; }
      a.libEdit = { title, draft, busy: true, error: "" }; agDraw();
      try {
        const m = await agPostApi(`/library/${encodeURIComponent(arg)}/save`, { draft, title });
        a.library = await agApi("/library").catch(() => a.library);
        if (a.panel){
          a.panel.data = { text: draft };
          a.panel.title = (m && m.title) || title;
          a.panel.subtitle = `${agNum(m && m.words)} words · ${(m && m.status) || "draft"} · edited by you`;
        }
        a.libEdit = null; agToast("Saved");
      } catch (e) { a.libEdit = { title, draft, busy: false, error: String((e && e.message) || e) }; }
      agDraw(); break;
    }
    case "libstatus": {
      try { await agPostApi(`/library/${encodeURIComponent(arg)}/status`, { status: el.getAttribute("data-status") || "draft" }); a.library = await agApi("/library"); }
      catch (e) { agToast("Could not change: " + (e.message || e)); }
      agDraw(); break;
    }
    case "libdel": {
      if (typeof confirm === "function" && !confirm("Delete this article from the Library? The chat that made it stays.")) break;
      try { await agPostApi(`/library/${encodeURIComponent(arg)}/delete`, {}); a.library = await agApi("/library"); agToast("Deleted"); }
      catch (e) { agToast("Could not delete: " + (e.message || e)); }
      agDraw(); break;
    }
    /* connections */
    case "savedfs": {
      const login = (document.querySelector('[data-agdfs="login"]') || {}).value || "";
      const password = (document.querySelector('[data-agdfs="password"]') || {}).value || "";
      if (!login.trim() || !password.trim()){ a.connForm = Object.assign({}, a.connForm, { login, password, msg: "Both fields are needed" }); agDraw(); break; }
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
    case "savevoy": {
      const key = (document.querySelector('[data-agvoy="key"]') || {}).value || "";
      if (!key.trim()){ a.connForm = Object.assign({}, a.connForm, { vmsg: "Paste the key first" }); agDraw(); break; }
      try { await agPostApi("/connections", { voyage_key: key.trim() });
        a.conns = await agApi("/connections"); a.health = await agApi("/health"); a.connForm = { vmsg: "Saved. Ask the agent to index the pages by meaning." }; }
      catch (e) { a.connForm = { voyage: key, vmsg: "Could not save: " + (e.message || e) }; }
      agDraw(); break;
    }
    case "clearvoy": {
      try { await agPostApi("/connections", { voyage_key: "" });
        a.conns = await agApi("/connections"); a.health = await agApi("/health"); a.connForm = { vmsg: "Disconnected" }; }
      catch (e) { a.connForm = { vmsg: "Could not disconnect: " + (e.message || e) }; }
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
    if (!ta || !ta.matches) return;
    if (ta.matches("[data-agask]") && ev.key === "Enter" && !ev.shiftKey){ ev.preventDefault(); agSend(ta.value); }
    if (ta.matches("[data-agpageq]") && ev.key === "Enter"){ ev.preventDefault(); agLoadPages(0); }
  });
  let agSearchTimer = null;
  document.addEventListener("input", (ev) => {
    const t = ev.target; if (!t || !t.matches) return;
    const a = agS(); if (!a) return;
    if (t.matches("[data-agask]")){ a.draft = t.value; agGrow(t); }
    else if (t.matches("[data-agcomps]")){ a.compForm = { text: t.value, saved: false }; }
    else if (t.matches("[data-agmem]")){ a.memForm = { text: t.value }; }
    else if (t.matches("[data-agco]")){ const f = a.coForm || {}; document.querySelectorAll("[data-agco]").forEach(i => { f[i.getAttribute("data-agco")] = i.value; }); f.msg = ""; a.coForm = f; }
    else if (t.matches("[data-agpageq]")){ a.pageQ = t.value; clearTimeout(agSearchTimer); agSearchTimer = setTimeout(() => agLoadPages(0), 250); }
    else if (t.matches("[data-agcta]")){
      const rows = agCtaRows(a); const i = Number(t.getAttribute("data-i"));
      if (rows[i]){ rows[i][t.getAttribute("data-agcta")] = t.value; rows[i].mine = true; a.ctaForm = { rows }; }
    }
    else if (t.matches("[data-aglibtitle]")){ if (a.libEdit) a.libEdit.title = t.value; }
    else if (t.matches("[data-aglibbody]")){ if (a.libEdit) a.libEdit.draft = t.value; }
    else if (t.matches("[data-agfiletext]")){ if (a.fileEdit) a.fileEdit.text = t.value; }
    else if (t.matches("[data-agdfs]")){
      const f = a.connForm || {}; f[t.getAttribute("data-agdfs")] = t.value; f.msg = ""; a.connForm = f;
    }
    else if (t.matches("[data-agvoy]")){ const f = a.connForm || {}; f.voyage = t.value; f.vmsg = ""; a.connForm = f; }
  });
  document.addEventListener("change", (ev) => {
    const t = ev.target; if (!t || !t.matches) return;
    const a = agS(); if (!a) return;
    if (t.matches("[data-agpagetype]")){ a.pageType = t.value; agLoadPages(0); }
    else if (t.matches("[data-agpagelang]")){ a.pageLang = t.value; agLoadPages(0); }
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
