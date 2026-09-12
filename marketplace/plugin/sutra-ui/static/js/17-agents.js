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
                        blueprint: "Article plan", article: "The draft", brand_file: "Brand file", page: "Page",
                        prompt: "Prompt" };
const AG_POLL_LIVE_MS = 1000;
const AG_POLL_IDLE_MS = 4000;

/* How long a refresh may say nothing before the card says how long it has been quiet. A run that
   has gone silent must never read the same as one that has stopped, and the only honest way to
   tell him is the gap itself: the engine's last line, and how long ago it arrived. */
const AG_REFRESH_QUIET_S = 20;
/* How many polls in a row may fail before the card stops pretending the frame it is holding is
   current. Three, at a second apiece. */
const AG_REFRESH_LOST_POLLS = 3;

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
/* How long the arrival animation is allowed to hold the .ag-enter class, in ms. It is the whole
   staged reveal plus a little, and it is a CLEANUP timer, not a gate: the agent is in the DOM,
   loading and usable from the first frame, and this only decides when the class stops being
   there so a later remount does not replay it. Keep it short -- nobody should sit through this
   twice, let alone notice it the second time. */
const AG_ENTER_MS = 780;   // must OUTLAST the longest arrival (.46s + .13s delay) or it is cut short

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
    /* THE TAB'S OWN ROUTE (owner, 2026-09-10: "the agents tab will be turned into an agents
       marketplace... I don't want the SEO writer to open automatically"). `screen` is where the
       Agents tab is, and it is the outer of the two routes on this file: "market" is the shelf of
       agents, "agent" is the SEO Writer's three columns. `view` below is the INNER route, and it
       only means anything once screen is "agent". The tab always opens on the marketplace; the
       agent is somewhere you go, and the way back is the button in its sidebar. */
    screen: "market",             /* market | agent */
    /* is a shelf fill in flight, and did the last one fail. The card never branches on "have we
       loaded"; it branches on whether each payload is null, which is the same question asked of
       the thing itself rather than of a flag beside it. */
    marketBusy: false, marketErr: null,
    /* the session-only "I have read the introduction". It claims nothing about setup -- whether
       the introduction is due at all is decided from real state by agFirstRun, never a flag. */
    introSkip: false,
    /* THE INNER ROUTE, and it now opens on "guide" (owner, 2026-09-10: "always when I open the
       agent it should always open blank, not a chat which is always opened"). The guide is the
       door: the recent chats are still in the sidebar and one click still resumes any of them,
       and typing in the box starts a new chat exactly as it did. `guideDive` is which of the
       five deep dives has replaced the guide on that same screen, null being the guide itself. */
    view: "guide",                /* guide | chat | knowledge | memory | prompts | library | tools | connections */
    guideDive: null,              /* null | site | brand | worth | research | write */
    chats: null, chatId: null, chat: null,   /* chat = {chat, messages, runs} */
    events: {}, cursors: {},      /* per run_id */
    panel: null,                  /* {run_id, name, view, data, loading, error} */
    autoOpened: null,             /* the waiting call_id whose panel already opened itself */
    picked: null, collapsed: {}, stageOpen: {}, stepOpen: {}, chatMenu: null, viewBusy: null, facePick: null,
    notified: {}, runSeen: {}, trail: [], workOpen: null, draft: "", scroll: null, stick: true,
    /* the catalogue refresh. `refresh` is GET /knowledge/refresh's job exactly as the server
       sent it -- the engine's lines included -- and `refreshSeen` is the finish whose stale
       counts have already been re-read, so one finished run re-reads them once. */
    refresh: null, refreshSeen: null, refreshPollErr: null,
    health: null, knowledge: null, cta: null, ctaForm: null, memory: null, library: null, tools: null, conns: null,
    pages: null, pageQ: "", pageType: "", pageLang: null, map: null, mapOn: false,
    bpEdit: null, artEdit: null, lastEdit: null, busy: false, error: null,
    compForm: null, coForm: null, memForm: null, connForm: null, libOpen: null, libEdit: null, detailOpen: {},
    fileEdit: null,
    prompts: null, promptEdit: null,   /* the Prompts tab's payload, and the open editor's draft */
    /* the team workspace. `ws` is GET /workspace exactly as the server sent it -- including the
       running job -- and `wsForm` is the draft in the create/join boxes. The personal access
       token is deliberately NOT in this list and must never be added to it. */
    ws: null, wsForm: null,
    /* the companies this person works for (GET /companies), the add/name form's mode, the last
       refusal in words, and whether a switch is in flight (owner, 2026-09-11) */
    companies: null, coForm: null, coErr: null, coBusy: false,
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

/* THE COMPANY NAME, decided in ONE place and read from the brand record.
   `knowledge.company` is knowledge/brand/company.json exactly as it was written, so a fresh
   install has nothing there and this answers "" -- which is the normal state for everyone who has
   not set the agent up yet, and every caller has to read correctly with the name absent.
   The brand pack's own `brand` field is deliberately NOT the source: sh.company() falls back to
   the literal "this company" when it knows nothing, and a fallback printed as a company name is a
   placeholder pretending to be data. Anything arriving here that reads like that fallback is
   dropped for the same reason. Never a hardcoded name, here or anywhere else on this screen. */
function agBrandName(a){
  const n = String((a && a.knowledge && a.knowledge.company && a.knowledge.company.brand) || "").trim();
  return (!n || n.toLowerCase() === "this company") ? "" : n;
}

/* Has this agent ever been used? true = show the introduction, false = go straight in,
   null = we have not read enough to say, so say nothing.
   Decided from real state only: a catalogue, a page index, a brand pack, a company record, a
   saved article, or a chat that already happened. There is no "seen the intro" flag behind this,
   because a flag would go on claiming after the state it stood for had changed. */
function agFirstRun(a){
  const h = a && a.health;
  if (!h) return null;
  const seen = !!(h.site_indexed || h.brand_ready || (h.page_index || {}).built
                  || (h.chats || 0) > 0 || agBrandName(a) || ((a.library || []).length > 0));
  return !seen;
}

/* ── renderers (pure, return HTML strings) ─────────────────────────────────── */

const AG_ICON = {
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true"><path d="M5 12.5l4.2 4.2L19 7"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  ask: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M9 9.5a3 3 0 115.2 2c-1 .9-2.2 1.4-2.2 3"/><circle cx="12" cy="18" r=".8" fill="currentColor"/></svg>',
  doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 3.5h8l4 4v13H6z"/><path d="M14 3.5v4h4M9 12h6M9 16h6"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1.1 5.8L12 16.8l-5.3 2.8 1.1-5.8L3.5 9.7l5.9-.8z"/></svg>',
  arrow: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
  left: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>',
  dots: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="5" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="12" cy="19" r="1.7"/></svg>',
  chev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>',
  pencil: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M4 20h4l10.5-10.5a2.1 2.1 0 00-3-3L5 17v3z"/><path d="M13.5 6.5l4 4"/></svg>',
  up: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6"/></svg>',
  down: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6"/></svg>',
  plus: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
  spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></svg>',
  link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1.5 1.5"/><path d="M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1.5-1.5"/></svg>',
};

/* A STEP FOLDS ITSELF WHEN IT IS DONE (owner, 2026-09-10: "let's say all these steps are
   there, they are all showing live around 50, 60, then they should collapse back... then only
   the thing I should be able to see is 'writing the article'"). While a step RUNS its sub-lines
   are the whole point, so it stays open and you watch it work. The moment it finishes, the
   sixty-one lines underneath it fold away and the headline plus its one-line result is all that
   is left, with a chevron on the left to open it again. A step that FAILED never folds: the
   reason it failed is the one thing you actually need to read. */
function agStepFolds(e){
  if (e.state === "run") return false;              /* live: watching it IS the point */
  if (e.state === "bad") return false;              /* a failure explains itself, always open */
  return !!((e.subs && e.subs.length) || e.lead);   /* nothing to fold, no chevron */
}

function agStepOpen(e, ctx){
  if (!agStepFolds(e)) return true;
  return !!(ctx.stepOpen && ctx.stepOpen[e.id]);
}

function agAskOpen(e, ctx){
  return !!(ctx.stepOpen && ctx.stepOpen[e.id || e.t]);
}

const AG_VIEW_WORD = { knowledge: "Knowledge", assets: "the asset ideas", memory: "what it remembers",
                       prompts: "the prompts", library: "the Library", tools: "the tools",
                       connections: "the connections" };

function agViewLoadingHtml(view){
  return `<div class="ag-vload" role="status"><span class="sp" aria-hidden="true"></span>
    <span>Opening ${agEsc(AG_VIEW_WORD[view] || "this")}\u2026</span></div>`;
}

/* WHO ELSE IS ON THIS WORKSPACE (owner, 2026-09-10: "show icons of all the people who have
   joined that workspace... I can click on each to know their name, including mine").

   Renders ONLY when a workspace is joined. One face on your own is not a team, it is noise,
   so a solo install shows nothing at all rather than a lonely circle.

   `last_seen_at` is what makes this worth looking at: every client touches it once a minute,
   so the ring says who is actually around, not just who once signed up. Somebody who has not
   been seen for AG_FACE_HERE_MS is drawn flat.

   The data comes off the workspace poll that already runs (20s server-side cache). No second
   timer: "who is on the team" changes about twice a year. */
const AG_FACE_HERE_MS = 5 * 60 * 1000;      /* seen within five minutes reads as "here now" */
const AG_FACE_MAX = 6;                      /* past this, the rest become a "+N" */

function agFaceAgo(iso){
  const t = iso ? Date.parse(iso) : NaN;
  return isFinite(t) ? Date.now() - t : Infinity;
}

function agFacesHtml(a){
  const ws = a && a.ws;
  if (!ws || !ws.configured) return "";
  const rows = (ws.members || []).filter(m => m && (m.member_id || m.name));
  if (rows.length < 1) return "";
  const meId = (ws.me && ws.me.member_id) || "";
  /* You first, then everyone else oldest-joined first. Seeing your own face where you expect
     it is what tells you the row is about people and not decoration. */
  rows.sort((x, y) => (x.member_id === meId ? -1 : y.member_id === meId ? 1 : 0));
  const show = rows.slice(0, AG_FACE_MAX);
  const rest = rows.length - show.length;
  return `<div class="ag-faces" role="list" aria-label="Who is on this workspace">
    ${show.map(m => {
      const me = m.member_id === meId;
      const here = agFaceAgo(m.last_seen_at) < AG_FACE_HERE_MS;
      const face = m.emoji || "";
      const needsFace = me && !face;
      const who = (m.name || "Someone") + (me ? " (you)" : "")
                + (needsFace ? " — pick your face" : "");
      return `<button class="ag-face ${here ? "here" : ""} ${me ? "me" : ""}" type="button" role="listitem"
        data-ag="face" data-arg="${agEsc(m.member_id || "")}"
        ${needsFace ? 'data-pickme="1"' : ""}
        aria-label="${agEsc(who)}${here ? ", here now" : ""}" title="${agEsc(who)}">
        ${face ? `<span class="e" aria-hidden="true">${agEsc(face)}</span>`
               : `<span class="i" aria-hidden="true">${agEsc(agInitials(m.name))}</span>`}</button>`;
    }).join("")}
    ${rest > 0 ? `<span class="ag-face more" title="${agEsc(rows.slice(AG_FACE_MAX).map(m => m.name || "Someone").join(", "))}">+${rest}</span>` : ""}
  </div>`;
}

/* The fallback when somebody has no face yet -- a teammate on an older Sutra, or a workspace
   whose migration has not run. Never leaves an empty circle. */
/* The picker. Free faces first and marked as such, so five people end up with five different
   ones without anybody having to coordinate. Taking one somebody else has is allowed -- past 32
   people it has to be -- it just is not the default. */
function agFacePickHtml(a){
  const p = a && a.facePick;
  if (!p) return "";
  if (p.loading) return `<div class="ag-facepick"><span class="ld">Reading the faces…</span></div>`;
  const free = new Set(p.free || []);
  return `<div class="ag-facepick">
    <div class="hd">Pick your face<button class="x" type="button" data-ag="face" data-arg="${agEsc((a.ws && a.ws.me && a.ws.me.member_id) || "")}" aria-label="Close">×</button></div>
    <div class="grid">${(p.faces || []).map(f => `<button type="button" class="f ${free.has(f) ? "" : "taken"}"
      data-ag="facepick" data-arg="${agEsc(f)}" title="${agEsc((p.names || {})[f] || "")}${free.has(f) ? "" : " · already taken"}"
      aria-label="${agEsc((p.names || {})[f] || f)}">${agEsc(f)}</button>`).join("")}</div>
  </div>`;
}

function agInitials(name){
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

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
      const folds = agStepFolds(e);
      const shown = agStepOpen(e, ctx);
      const n = (e.subs || []).length;
      /* The whole headline is the hit area, not a 12px arrow. */
      const head = folds
        ? `<button class="ag-title ag-fold-t" type="button" data-ag="step" data-arg="${agEsc(e.id)}" aria-expanded="${shown}">
             <span class="cv ${shown ? "on" : ""}" aria-hidden="true">${AG_ICON.chev}</span>${agEsc(e.label)}${verdict}${!shown && n ? `<span class="n">${n} step${n === 1 ? "" : "s"}</span>` : ""}</button>`
        : `<div class="ag-title">${agEsc(e.label)}${verdict}${e.state === "bad" && e.recovering ? `<span class="pill p-warn">trying another way</span>` : ""}</div>`;
      return `<div class="ag-step ${cls} ${folds ? "foldable" : ""} ${folds && !shown ? "folded" : ""}" data-step="${agEsc(e.id)}">
        ${folds ? "" : `<span class="ag-glyph" aria-hidden="true">${agGlyph(e)}</span>`}
        ${head}
        ${shown && e.lead ? `<div class="ag-body ${e.leadNote ? "" : "md"}">${e.leadNote ? agEsc(e.lead) : agMd(e.lead)}</div>` : ""}
        ${e.state === "bad" && e.reason ? `<div class="ag-body" style="color:var(--block)">${agEsc(e.reason)}</div>` : ""}
        ${e.state === "ok" && e.summary && !n ? `<div class="ag-body">${agEsc(e.summary)}</div>` : ""}
        ${shown ? agSubsHtml(e.subs, e.id, open) : ""}
        ${e.state === "ok" && e.summary && n ? `<div class="ag-body" style="margin-top:6px">${agEsc(e.summary)}</div>` : ""}
        ${e.detail ? `<button class="ag-more" type="button" data-ag="detail" data-arg="${agEsc(e.id)}">${open ? "Hide" : "Show"} the error detail</button>${open ? `<pre class="ag-detail">${agEsc(e.detail)}</pre>` : ""}` : ""}
      </div>`;
    }
    case "prose":
      return `<div class="ag-step quiet"><span class="ag-glyph" aria-hidden="true"></span><div class="ag-prose md">${agMd(e.text)}</div></div>`;
    case "note":
      return `<div class="ag-step quiet"><span class="ag-glyph" aria-hidden="true"></span><div class="ag-note">${agEsc(e.text)}</div></div>`;
    case "ask": {
      /* AN ANSWERED QUESTION IS ONE LINE (owner, 2026-09-10). Live, it is the whole card: the
         question, the reason, the options. Answered, it is settled history, so it folds to the
         question and what you said. Click it to see the reason and the options again. */
      if (!e.live && !agAskOpen(e, ctx)) {
        return `<div class="ag-step ask foldable folded">
          <button class="ag-title ag-fold-t" type="button" data-ag="step" data-arg="${agEsc(e.id || e.t)}" aria-expanded="false">
            <span class="cv" aria-hidden="true">${AG_ICON.chev}</span><span class="qt">${agEsc(e.question)}</span>
            <span class="said"><i>You said</i>${agEsc(e.answer || "answered")}</span></button></div>`;
      }
      return `<div class="ag-step ask ${e.live ? "" : "foldable"}">
        ${e.live ? `<span class="ag-glyph" aria-hidden="true">${agGlyph(e)}</span><div class="ag-title">Asked you a question</div>`
                 : `<button class="ag-title ag-fold-t" type="button" data-ag="step" data-arg="${agEsc(e.id || e.t)}" aria-expanded="true">
                      <span class="cv on" aria-hidden="true">${AG_ICON.chev}</span>Asked you a question</button>`}
        <div class="ag-card ${e.live ? "live" : ""}">
          <div class="q">${agEsc(e.question)}</div>
          ${e.why ? `<div class="why">${agEsc(e.why)}</div>` : ""}
          ${agChipsHtml(e.options, e.live, e.answer, "choose", e.call_id || "")}
          ${e.live ? `<div class="ag-hint">${(e.options && e.options.length) ? "Pick one, or type your own answer below." : "Type your answer below."}</div>`
                   : `<div class="ag-answer"><span>You said</span><b>${agEsc(e.answer || "")}</b></div>`}
        </div></div>`;
    }
    case "approval": {
      const said = e.decision === "approved" ? "Go ahead" : e.decision === "declined" ? "Not now" : (e.answer || "answered");
      if (!e.live && !agAskOpen(e, ctx)) {
        return `<div class="ag-step ask foldable folded">
          <button class="ag-title ag-fold-t" type="button" data-ag="step" data-arg="${agEsc(e.id || e.t)}" aria-expanded="false">
            <span class="cv" aria-hidden="true">${AG_ICON.chev}</span><span class="qt">${agEsc(e.question)}</span>
            <span class="said"><i>You said</i>${agEsc(said)}</span></button></div>`;
      }
      return `<div class="ag-step ask ${e.live ? "" : "foldable"}">
        ${e.live ? `<span class="ag-glyph" aria-hidden="true">${agGlyph(e)}</span><div class="ag-title">Asked before going on</div>`
                 : `<button class="ag-title ag-fold-t" type="button" data-ag="step" data-arg="${agEsc(e.id || e.t)}" aria-expanded="true">
                      <span class="cv on" aria-hidden="true">${AG_ICON.chev}</span>Asked before going on</button>`}
        <div class="ag-card ${e.live ? "live" : ""}">
          <div class="q">${agEsc(e.question)}</div>
          ${e.mins ? `<div class="ag-cost">about <b>${agEsc(e.mins)}</b> min</div>` : ""}
          ${e.why ? `<div class="why">${agEsc(e.why)}</div>` : ""}
          ${e.live ? `<div class="ag-chips">
              <button class="ag-chip pri" type="button" data-ag="approve" data-arg="yes">Go ahead</button>
              <button class="ag-chip" type="button" data-ag="approve" data-arg="no">Not now</button>
            </div>`
          : `<div class="ag-answer"><span>You said</span><b>${agEsc(said)}</b></div>`}
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
  /* THE TWO WAYS TO START, and the first one depends on whether there is a sheet (owner,
     2026-09-10: "it only has 2 ways for now: one is to go through the asset tab and pick the
     topmost one... or else he can write his own topic").
     The card offered "Suggest six topics we could own" to everybody, which predates the asset
     engine: with 1,890 ranked ideas already judged for whether he can own them and whether
     anyone would link to them, six fresh competitor-derived guesses is the wrong first move.
     `/health.assets` now carries the sheet, so the chip can tell. suggest_topics is NOT dead --
     it is the right answer for a company with no sheet yet, which is what the else branch is. */
  const as = (health && health.assets) || null;
  const nextIdea = as && as.built && as.open > 0 ? as.next : null;
  const topPlay = nextIdea
    ? ["Write the next idea on the sheet",
       agEsc(nextIdea.title || "").slice(0, 120) + (as.open > 1 ? ` — ${as.open - 1} more waiting.` : "")
         + " Passing on it leaves it on the sheet.",
       `Write ${nextIdea.id}`]
    : ["Suggest six topics we could own", "Studies one competitor's best pages and proposes six topics with an angle they have not taken. Used when there is no asset sheet yet.",
       "Suggest six topics we could own."];
  const plays = ready ? [
    topPlay,
    ["Write an article about a topic I name", "Researches it, plans it, and writes the draft in your voice. It stops twice: the topic and the draft.",
     "Write an article about "],
    /* A third play -- rewrite one of the pages we already have -- was DELETED (owner,
       2026-09-09). It was written before the reuse check existed and nothing was ever wired
       behind it: no tool takes a page and rebuilds it, so the chip filled the composer with a
       sentence the agent could only improvise around. Deleted rather than rewired: there is no
       step to point it at. The plays left are the two the engine can actually run. */
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


/* ── the marketplace ───────────────────────────────────────────────────────────
   What the Agents tab opens on. One shelf, and on it every agent this install
   actually has. There is exactly one, the SEO Writer, and there are no greyed-out
   "coming soon" cards beside it: an honest empty shelf is better than invented
   inventory, and one plain line says more is coming without drawing a thing that
   is not there. Nothing on this screen may claim a state it has not read, so every
   fact on the card comes from a payload that has arrived, and a fact still in
   flight is left out rather than printed as a zero. */

/* One fact on the card: a label, and either a number that was read or nothing.
   `n` of null means "not read yet" and the fact is dropped -- which is the whole
   difference between "no articles" and "we have not looked". */
function agMktFact(n, one, many){
  if (n == null) return "";
  return `<span class="f"><b>${agEsc(agNum(n))}</b> ${agEsc(n === 1 ? one : many)}</span>`;
}

/* The SEO Writer's card. Everything on it traces to a route:
     the state pill and the setup line   → GET /health, through agSetupOf
     "articles in the Library"           → GET /library, its length
     "chats"                             → GET /health, its `chats`
     "pages catalogued"                  → GET /knowledge, site_index.page_count
   Before /health has landed the card says it is checking, because at that moment
   the only true thing it knows is that it does not know. */
function agSeoCardHtml(a){
  const h = a.health;
  const setup = agSetupOf(h);
  const first = agFirstRun(a);
  const state = !h ? ["", "checking…"]
    : !h.model_provider ? ["bad", "no model available"]
    : first ? ["", "not set up yet"]
    : setup.ready ? ["run", "set up and ready"]
    : ["warn", "setup unfinished"];
  const kn = a.knowledge || null;
  const pages = kn && kn.site_index ? kn.site_index.page_count : null;
  /* On a confirmed first run every one of these is zero by definition -- that is what first run
     MEANS -- so the row is three zeroes saying what "not set up yet" already said. Left off there,
     and left off per fact when its route has not answered. Nothing is hidden that is not either
     already stated or not yet known. */
  /* ONE COMPANY'S NUMBERS, ONLY WHILE THERE IS ONE COMPANY (owner, 2026-09-11: "will be there if
     one company, else if both then go away"). With several, the shelf cannot say whose six
     articles these are, so it says nothing rather than quietly showing the open one's. */
  const many = !!(h && (h.companies || 1) > 1);
  const facts = (first !== false || many) ? "" : [
    agMktFact(a.library ? a.library.length : null, "article in the Library", "articles in the Library"),
    agMktFact(h ? (h.chats || 0) : null, "chat", "chats"),
    agMktFact(pages, "page catalogued", "pages catalogued"),
  ].filter(Boolean).join("");
  /* The one line under the name is what the agent is FOR, and it does not change with state.
     What changes is the line under the facts: the next thing this install needs. */
  const missing = setup.steps.find(s => !s.ok && !s.soft);
  const next = !h ? "" : first ? "Give it your website once and it does the rest of the setup itself."
    : !missing ? "" : `Next: ${agEsc(missing.label.toLowerCase())}.`;
  return `<button class="ag-mktcard" type="button" data-ag="openagent" data-arg="seo"
      aria-label="Open the SEO Writer">
    <span class="cm" aria-hidden="true">S</span>
    <span class="cb">
      <span class="ct">SEO Writer</span>
      <span class="cd">Researches a topic, plans the article, and writes it in your voice, with sources.</span>
      <span class="cs"><i class="dot ${state[0]}" aria-hidden="true"></i>${agEsc(state[1])}</span>
      ${facts ? `<span class="cf">${facts}</span>` : ""}
      ${next ? `<span class="cn">${next}</span>` : ""}
    </span>
    <span class="cg" aria-hidden="true">Open ${AG_ICON.arrow}</span>
  </button>`;
}

/* The shelf itself. The heading, the one card, and one line about the rest. No company name: the
   shelf belongs to the person, who may work for several companies (see agMarketHtml). */
/* THE MARK BEHIND THE SHELF. One agent leaves a great deal of empty room, and the owner asked for
   the space to carry something rather than just be blank: "a big circle with the Sutra logo... as
   an underlay, and maybe a glow. The background should be matched with whatever theme it is."

   It is drawn rather than an image because it has to follow the theme picker: every stroke, the
   centre and all three gradient stops are var(--acc), so a red theme gives a red mark and a dark
   theme gives that theme's accent, with no per-theme code at all. An <img> cannot read a CSS
   variable, which is why it is inline.

   It is DECORATION and behaves like it: aria-hidden, not focusable, pointer-events:none, and
   turned down far enough that nothing on top of it is harder to read. Too faint is the right way
   to be wrong here. It does not move: a background that never stops moving is exhausting to work
   beside, so it only ever arrives with the rest of the shelf. (2026-09-10) */
const AG_MARK = `
      <svg class="ag-sutramark" viewBox="-420 -420 840 840" aria-hidden="true" focusable="false">
        <defs>
          <radialGradient id="agSutraGlow">
            <stop offset="0%" stop-color="var(--acc)" stop-opacity=".22"/>
            <stop offset="55%" stop-color="var(--acc)" stop-opacity=".07"/>
            <stop offset="100%" stop-color="var(--acc)" stop-opacity="0"/>
          </radialGradient>
        </defs>
        <circle r="410" fill="url(#agSutraGlow)"/>
        <g fill="none" stroke="var(--acc)" stroke-width="2.6" stroke-linejoin="round">
            <path d="M0 0A188 188 0 0 1 0 -300 A188 188 0 0 1 0 0" transform="rotate(0)" opacity="0.72"/>
            <path d="M0 0A188 188 0 0 1 0 -300 A188 188 0 0 1 0 0" transform="rotate(60)" opacity="0.72"/>
            <path d="M0 0A188 188 0 0 1 0 -300 A188 188 0 0 1 0 0" transform="rotate(120)" opacity="0.72"/>
            <path d="M0 0A188 188 0 0 1 0 -300 A188 188 0 0 1 0 0" transform="rotate(180)" opacity="0.72"/>
            <path d="M0 0A188 188 0 0 1 0 -300 A188 188 0 0 1 0 0" transform="rotate(240)" opacity="0.72"/>
            <path d="M0 0A188 188 0 0 1 0 -300 A188 188 0 0 1 0 0" transform="rotate(300)" opacity="0.72"/>
            <path d="M0 0A122 122 0 0 1 0 -196 A122 122 0 0 1 0 0" transform="rotate(30)" opacity="0.55"/>
            <path d="M0 0A122 122 0 0 1 0 -196 A122 122 0 0 1 0 0" transform="rotate(90)" opacity="0.55"/>
            <path d="M0 0A122 122 0 0 1 0 -196 A122 122 0 0 1 0 0" transform="rotate(150)" opacity="0.55"/>
            <path d="M0 0A122 122 0 0 1 0 -196 A122 122 0 0 1 0 0" transform="rotate(210)" opacity="0.55"/>
            <path d="M0 0A122 122 0 0 1 0 -196 A122 122 0 0 1 0 0" transform="rotate(270)" opacity="0.55"/>
            <path d="M0 0A122 122 0 0 1 0 -196 A122 122 0 0 1 0 0" transform="rotate(330)" opacity="0.55"/>
            <path d="M0 0A70 70 0 0 1 0 -112 A70 70 0 0 1 0 0" transform="rotate(0)" opacity="0.42"/>
            <path d="M0 0A70 70 0 0 1 0 -112 A70 70 0 0 1 0 0" transform="rotate(60)" opacity="0.42"/>
            <path d="M0 0A70 70 0 0 1 0 -112 A70 70 0 0 1 0 0" transform="rotate(120)" opacity="0.42"/>
            <path d="M0 0A70 70 0 0 1 0 -112 A70 70 0 0 1 0 0" transform="rotate(180)" opacity="0.42"/>
            <path d="M0 0A70 70 0 0 1 0 -112 A70 70 0 0 1 0 0" transform="rotate(240)" opacity="0.42"/>
            <path d="M0 0A70 70 0 0 1 0 -112 A70 70 0 0 1 0 0" transform="rotate(300)" opacity="0.42"/>
          <circle r="382" stroke-dasharray="2 9" stroke-width="2.4" opacity=".55" stroke-linecap="round"/>
          <circle r="368" stroke-dasharray="1 16" stroke-width="3.4" opacity=".38" stroke-linecap="round"/>
        </g>
        <circle r="15" fill="var(--acc)" opacity=".72"/>
      </svg>
    `;

/* ── which company ─────────────────────────────────────────────────────────────
   One person, several companies (owner, 2026-09-11: "one person can do the content for more than
   one company... when he opens the agent, an option to choose a company he has already worked on
   ... add another company"). A company is a folder on the server; this is the door in front of it.

   It is drawn in the shelf's own frame rather than the agent's three columns, because choosing
   happens BEFORE any one company's sidebar, chats or knowledge mean anything. Two moods:
     choose   more than one company -- a card for each, and Add another company
     name     the open company has no name yet, which is a first run: the name is asked first,
              then the agent asks for the website exactly as it always has */
function agChooseHtml(a){
  const L = a.companies;
  const rows = L ? (L.companies || []) : null;
  const f = a.coForm || {};
  const naming = f.mode === "name";
  const busy = !!a.coBusy;
  const form = (label, go, hint) => `<div class="ag-coform">
      <label><b>${label}</b><input type="text" data-agconame maxlength="80" placeholder="e.g. Acme Hiring" ${busy ? "disabled" : ""}></label>
      <div class="row"><button class="btn pri" type="button" data-ag="${go}" ${busy ? "disabled" : ""}>${busy ? "One moment…" : go === "coaddgo" ? "Add and open" : "Continue"}</button>
        ${naming ? "" : `<button class="btn" type="button" data-ag="cocancel" ${busy ? "disabled" : ""}>Cancel</button>`}</div>
      <div class="sp">${hint}</div></div>`;
  return `<div class="ag-mkt">
    ${AG_MARK}
    <header class="ag-mkth">
      <h1>${naming ? "What's the company called?" : "Which company?"}</h1>
      <p>${naming ? "The SEO Writer works for one company at a time. You can add more later."
                  : "Each company keeps its own knowledge, chats and library. Your DataForSEO and Voyage keys work for all of them."}</p>
    </header>
    ${a.coErr ? `<div class="note b" role="status">${agEsc(a.coErr)}</div>` : ""}
    ${!rows ? `<div class="ag-vload" role="status"><span class="sp" aria-hidden="true"></span><span>Reading your companies…</span></div>`
      : naming ? form("Company name", "conamego", "The agent asks for the website next, the way it does on a first run.")
      : `<div class="ag-cards">${rows.map(c => agCoCardHtml(c, busy)).join("")}</div>
         ${f.mode === "add" ? form("New company", "coaddgo", "It gets its own knowledge, chats and library. The agent asks for its website next.")
           : `<div class="row" style="margin-top:14px"><button class="btn" type="button" data-ag="coadd" ${busy ? "disabled" : ""}>${AG_ICON.plus} Add another company</button></div>`}`}
    <div class="row" style="margin-top:22px"><button class="ag-back" type="button" data-ag="market">${AG_ICON.left} All agents</button></div>
  </div>`;
}

function agCoCardHtml(c, busy){
  const name = c.name || "Unnamed company";
  return `<button class="ag-mktcard ag-cocard ${c.active ? "on" : ""}" type="button" data-ag="cosw" data-arg="${agEsc(c.id)}" ${busy ? "disabled" : ""}
      aria-label="Open ${agEsc(name)}">
    <span class="cm" aria-hidden="true">${agEsc(name.charAt(0).toUpperCase())}</span>
    <span class="cb">
      <span class="ct">${agEsc(name)}</span>
      <span class="cd">${agEsc(c.domain || "not set up yet")}</span>
      <span class="cs">${agEsc(agNum(c.chats || 0))} ${c.chats === 1 ? "chat" : "chats"}${c.active ? " · open last" : ""}</span>
    </span>
    <span class="cg" aria-hidden="true">Open ${AG_ICON.arrow}</span>
  </button>`;
}

async function agCompaniesLoad(){
  const a = agS(); if (!a) return;
  try { a.companies = await agApi("/companies"); a.coErr = null; }
  catch (e) { a.coErr = agWhy(e); }
  const open = a.companies && (a.companies.companies || []).find(c => c.active);
  if (open && !open.name && !a.coForm) a.coForm = { mode: "name" };
  agDraw(true);
  agFocusCo();
}

function agFocusCo(){
  if (typeof setTimeout !== "function" || typeof document === "undefined") return;
  setTimeout(() => { const i = document.querySelector("[data-agconame]"); if (i) i.focus(); }, 0);
}

/* Everything on this screen that belongs to the company being left. The server has already
   forgotten its side (agents_api._co_reset); this is the same promise on the screen, so not one of
   the old company's chats, articles or panels can be drawn over the new one. */
function agResetCompany(a){
  Object.assign(a, {
    chats: null, chatId: null, chat: null, events: {}, cursors: {}, panel: null, autoOpened: null,
    picked: null, collapsed: {}, stageOpen: {}, stepOpen: {}, chatMenu: null, facePick: null,
    notified: {}, runSeen: {}, trail: [], workOpen: null, draft: "", viewBusy: null,
    refresh: null, refreshSeen: null, refreshPollErr: null, health: null, knowledge: null,
    cta: null, ctaForm: null, memory: null, library: null, conns: null, assets: null,
    pages: null, pageQ: "", pageType: "", pageLang: null, map: null, mapOn: false,
    bpEdit: null, artEdit: null, lastEdit: null, compForm: null, coForm: null, memForm: null,
    connForm: null, libOpen: null, libEdit: null, detailOpen: {}, fileEdit: null,
    prompts: null, promptEdit: null, ws: null, wsForm: null, guideDive: null,
  });
}

/* NO COMPANY NAME ON THE SHELF (owner, 2026-09-11: "in the Agent Marketplace tab when I open I
   should not see any company name"). The shelf belongs to the person, who may work for several
   companies; which one is chosen once an agent is opened. */
function agMarketHtml(a){
  return `<div class="ag-mkt">
    ${AG_MARK}
    <header class="ag-mkth">
      <h1>Agents</h1>
      <p>They do a whole job in front of you, naming every step before they take it.</p>
    </header>
    <h3 class="sec">On the shelf</h3>
    <div class="ag-cards">${agSeoCardHtml(a)}</div>
    ${a.marketErr ? `<div class="note b" role="status"><b>Could not read the agent's state.</b> ${agEsc(a.marketErr)} The agent still opens.</div>` : ""}
    <!-- ONE LINE, NOT A PARAGRAPH OF APOLOGY. It said "one agent today, others are being built,
         and they will appear here when they are real" — accurate, and it read like a footnote
         explaining an empty shelf. The owner asked for the opposite: "one dark crazy line,
         decorated or designed, saying we are bringing more, fasten your seatbelt". So the empty
         shelf stops being an absence being excused and becomes the promise. (2026-09-10) -->
    <div class="ag-more" role="note">
      <span class="r"></span>
      <p><em>More are coming.</em><br>Fasten your seatbelt.</p>
      <span class="r"></span>
    </div>
  </div>`;
}

/* ── the first run ─────────────────────────────────────────────────────────────
   Opening an agent for the first time should read as an introduction, not a form. This is what
   sits where the hero sits, decided by agFirstRun from real state, and it ends in the door: the
   same play chip the hero uses, so there is no second way into setup to keep in step.
   Every claim on it is read. What it needs is health's own answer; what it will do first is the
   four setup steps agSetupOf already names, in the order the engine takes them. */
function agIntroHtml(a){
  const h = a.health;
  const setup = agSetupOf(h);
  /* [name, what to say, is it in place, is it required]. The third field is READ, never assumed:
     the website row went out green once because it was hardcoded true, which told somebody with
     nothing set up that the one required thing was done. */
  const needs = [
    ["Your website", h && h.site_indexed ? "Read." : "The address is the only thing you have to give it.",
     !!(h && h.site_indexed), true],
    ["DataForSEO", h && h.dataforseo ? "Connected." : "Not connected. Without it, keyword volumes, difficulty and who ranks are demo numbers.", !!(h && h.dataforseo), false],
    ["A Voyage key", h && h.voyage ? "Connected." : "Not set. Without it, pages are matched by words rather than meaning, so internal links are weaker. The key is free.", !!(h && h.voyage), false],
  ];
  return `<div class="ag-intro">
    <div class="i1">
      <div class="ag-mark big" aria-hidden="true">S</div>
      <h2>The SEO Writer</h2>
      <p class="l">It reads your website once, learns how you write and what you sell, and then
         writes articles about the topics you name: real keyword numbers, the pages that beat you
         today, evidence with its sources, a plan, and a draft in your own voice. You see every
         stage before it moves on.</p>
    </div>
    <div class="i2">
      <h3 class="sec">What it needs</h3>
      <ul class="ag-needs">${needs.map(n => `<li class="${n[2] ? "ok" : n[3] ? "req" : "soft"}">
        <i aria-hidden="true"></i><b>${agEsc(n[0])}</b><span>${agEsc(n[1])}</span></li>`).join("")}</ul>
    </div>
    <div class="i3">
      <h3 class="sec">What it puts in place first</h3>
      <ol class="ag-firsts">${setup.steps.map(s => `<li class="${s.ok ? "ok" : ""}">${agEsc(s.label)}</li>`).join("")}</ol>
      <p class="ag-hint">It runs once, on its own, and tells you as it goes.</p>
    </div>
    <div class="i4">
      <button class="ag-play" type="button" data-ag="play" data-text="Set up for my website: ">
        <span class="pi"><span class="pt">Set up for my website</span>
          <span class="pd">Type the address and it starts. Nothing else is needed.</span></span>
        <span class="go">Let's go ${AG_ICON.arrow}</span></button>
      <button class="ag-skip" type="button" data-ag="introskip">Skip the introduction</button>
    </div>
    ${h && !h.model_provider ? `<div class="i5"><div class="note b"><b>No model is available.</b> The agent runs on the <code>claude</code> command line, billed to your Claude subscription. Open a terminal, run <code>claude</code> once and sign in, then come back.</div></div>` : ""}
  </div>`;
}

/* ── THE GUIDE ─────────────────────────────────────────────────────────────────
   What the agent's middle column opens on, every time (owner, 2026-09-10: "always when I open
   the agent it should always open blank, not a chat which is always opened"). The recent chats
   stay in the sidebar and one click still resumes any of them; the door simply opens here.

   The words are design/AGENT-GUIDE-COPY.md, verbatim. They are not to be rewritten, improved or
   added to here: this file's job is to draw them and to fill the two slots that are real state.
   Everything else on this screen is a fixed string, which is why the tables below are data
   rather than template literals -- a slot that is not filled has to be droppable, and a sentence
   welded into markup cannot be dropped.

   THE TWO REAL SLOTS, and nothing else:
     the domain in "Set up ..."          -> agSiteDomain, from the company record / catalogue
     the count in the Tools row          -> GET /tools, whose source is seo_agent/registry.py
   Neither has a placeholder. Not known means the phrase is not drawn. */

/* THE DOMAIN, decided in ONE place, the way agBrandName decides the company name.
   Three payloads can carry it and they are asked in the order of how deliberate they are: the
   company record is what somebody typed or the setup wrote, site_index.domain is what the
   catalogue actually read, and /knowledge/cta's `domain` is the engine's own bare host. A fresh
   install has none of the three and this answers "" -- which every caller must read correctly,
   because that is the normal state on day one. Never a hardcoded domain, and never an example
   standing in for one. */
function agSiteDomain(a){
  const kn = (a && a.knowledge) || {};
  const raw = String((kn.company && kn.company.domain) || (kn.site_index && kn.site_index.domain)
                     || (a && a.cta && a.cta.domain) || "").trim();
  if (!raw) return "";
  /* the record may hold a full url or a bare host; the sentence wants the host */
  const host = raw.replace(/^[a-z]+:\/\//i, "").replace(/^www\./i, "").split(/[/?#]/)[0].trim();
  return host.indexOf(".") > 0 ? host : "";
}

/* The number of tools, as the word the sentence needs, or "" when /tools has not answered.
   The list is the registry's, exactly as the Tools tab reads it, so the guide and that tab can
   never disagree about how many there are. agToolsHtml has said "the twelve things" from a
   count since the day it said "seven" over eleven rows; this is the same discipline, one screen
   earlier. */
const AG_COUNT_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight",
                        "nine", "ten", "eleven", "twelve", "thirteen", "fourteen"];
function agCountWord(n){
  if (n == null || isNaN(Number(n))) return "";
  n = Number(n);
  return n < AG_COUNT_WORDS.length ? AG_COUNT_WORDS[n] : String(n);
}

/* THE TAB TABLE. The left column is the tab name exactly as the sidebar draws it -- the sidebar
   is the truth and this list follows it, which agGuideTabNames and its test hold in step. The
   Tools row's description is a function because it carries the one count on this screen; every
   other description is a fixed string from the copy. */
const AG_GUIDE_TABS = [
  ["Knowledge", "Everything it knows about your site and your brand. Open any file and edit it."],
  ["Asset ideas", "The ranked list of things worth writing. Tick them off as they get written."],
  ["Library", "Finished articles."],
  ["Prompts", "The instructions it actually writes by. Change the wording and the next article uses your version."],
  ["Memory", "Rules you have told it to remember for every article."],
  ["Tools", null],
  ["Connections", "Your keys, and the workspace your team joins."],
];
function agGuideTabNames(){ return AG_GUIDE_TABS.map(t => t[0]); }

/* The copy that is a whole paragraph is a single-line string on purpose. Wrapped into the
   template literal it would carry the source file's own newlines and indentation into the DOM,
   and the test that holds these sentences verbatim could then only match a normalised copy of
   them -- which is exactly the loophole a later reword would slip through. */
const AG_GUIDE_LEAD = "It reads your website, learns how you write, finds what is worth writing, and writes it one article at a time. You can change anything along the way.";
/* NO COMMAND BOX. It printed `Set up <your domain>` in a mono block, which read as a thing to
   copy and made a two-word instruction look like a command line. The owner: "need not show
   like a chat button below, just say them to type this in the chat section, that is it."
   Dropping it also removes the last place the guide had to name the site at all. (2026-09-10) */
/* SHORTER, AND THE TWO STOPS CORRECTED (2026-09-11). AFTER used to say it stops "to agree the shape
   of the article", which it has not done since the owner ruled the stops are the TOPIC and the
   DRAFT; the plan lands in the Library and is not waited on. */
const AG_GUIDE_TYPE = "Type what you want in the box below. The agent asks what it needs, one question at a time.";
const AG_GUIDE_AFTER = "It shows every step, and stops twice: to agree the topic, and to approve the draft.";

const AG_GUIDE_STEPS = [
  "It reads your site. Every page, all the text, and what each page already ranks for.",
  "It learns your brand from those pages: how you sound, what you sell, who you write for.",
  "It works out what is worth writing and gives you a ranked list of ideas.",
  "You pick one. It researches it, plans it, writes it, and edits it in several passes.",
];

/* THE FIVE DEEP DIVES. [id, heading, [paragraph, ...]] -- the heading is also the link's label on
   the main screen, so the two can never drift apart, and the paragraphs are the copy's own
   paragraph breaks. Each one REPLACES the guide on this same screen (owner: "the same blank
   screen would change"): not a modal, not a new pane, and the way back sits in the same place on
   all five so it does not move as you go between them. */
const AG_DIVES = [
  ["site", "How it reads your site", [
    "Most tools crawl a site by following links, which misses anything the homepage does not link to.",
    "This one asks four sources and compares them: your sitemaps, your content system if you have one, the web archive's record of your site, and a crawl. Four answers about the same site, cross-checked against each other.",
    "Then it checks its own work. If the sitemaps list 11,000 pages and it only managed to read 400, it says so rather than calling the job done.",
    "Every page's full text is saved with its headings intact, so a later step can quote it. It also pulls what each page already ranks for, which is how it knows which of your pages matter. A page drawn by JavaScript gets opened in a real browser, because there is nothing to read in the HTML.",
  ]],
  ["brand", "How it learns your brand", [
    "It never asks you to describe your own voice. People are bad at that. It reads your best pages and works it out.",
    "A dozen files get built in order, each one using the ones before it: how you sound, your house style, what you sell and the proof behind every claim, who you are writing for, the numbers and customer stories you are allowed to cite, and the honesty rules.",
    "All of it ends in one page the writer reads before it writes a word.",
    "Some facts a crawler can never reach. Prices drawn by JavaScript are the usual one. So there is a file you type in yourself, and what you type there beats anything read off the site.",
  ]],
  ["worth", "How it decides what is worth writing", [
    "Three methods, kept deliberately apart so they cannot agree with each other by accident.",
    "It studies what actually earns links in your industry. It looks at formats that work in other industries and asks whether they would work in yours. And it reads where practitioners argue in public, to find what people keep coming back to.",
    "Every idea then faces the same two questions. Could you own this better than anyone else? And would a stranger link to it?",
    "Only after that are the three lists merged, and duplicates are found by meaning rather than by matching words, because the same idea rarely gets written the same way twice.",
    "You get one ranked sheet. Two moments in the middle stop and ask you.",
  ]],
  ["research", "How it researches a topic", [
    "It buys real keyword numbers instead of guessing at them, and it reads the pages that currently rank to see what they cover and what they all miss.",
    "Then the part that makes the difference: four researchers with different backgrounds interview an expert about your topic, each question shaped by the last answer. That conversation becomes a written dossier, and the facts are lifted out of it with their sources attached.",
    "If a hole is found in the evidence, it runs the whole conversation again for that hole alone rather than papering over it.",
    "Every number has to trace back to a page that actually said it. One that cannot is marked, not quietly attributed to something nearby.",
  ]],
  ["write", "How it writes the article", [
    "The plan comes first: which sections, in what order, which facts belong in each, and how long each one should run.",
    "The shape depends on what kind of article it is. A comparison is built differently from a how-to, and there are eight rulebooks for the eight shapes.",
    "Then each section is written from its own facts, in your voice.",
    "Then it edits, and this is most of the work: it reads the whole thing for coherence, rewrites it to be read rather than skimmed, reshapes the sentences so the prose does not march, removes the tells of machine writing, lays in links to your own pages, and checks every number against the source it came from.",
    "You see the draft before anything is saved.",
  ]],
];
function agDive(id){ return AG_DIVES.find(d => d[0] === id) || null; }

/* The one control that must not move between the five. Drawn by ONE function, placed first in
   every dive, so "the same position on all five" is a property of the code and not of five
   copies that have to be kept in line. */
function agDiveBackHtml(){
  return `<div class="d0"><button class="ag-diveback" type="button" data-ag="guideback">${AG_ICON.left}Back</button></div>`;
}

function agDiveHtml(id){
  const d = agDive(id);
  if (!d) return "";
  return `<div class="ag-dive">
    ${agDiveBackHtml()}
    <div class="d1"><h2>${agEsc(d[1])}</h2></div>
    <div class="d2">${d[2].map(p => `<p>${agEsc(p)}</p>`).join("")}</div>
  </div>`;
}

/* The main screen. Every sentence on it is the copy; the only two things decided at draw time
   are the domain and the tool count, and each is left OUT when it is not known rather than
   filled with something that looks like it was read. */
function agGuideHtml(a){
  if (a && a.guideDive) return agDiveHtml(a.guideDive);
  const domain = agSiteDomain(a);
  /* "Set up <domain>". With a domain it is the command to type; without one the slot is not
     drawn at all, because a domain nobody gave us is not ours to print. */
  const tools = agCountWord(a && a.tools ? a.tools.length : null);
  return `<div class="ag-guide">
    <div class="g1">
      <h2>The SEO writer</h2>
      <p class="l">${agEsc(AG_GUIDE_LEAD)}</p>
    </div>
    <div class="g2">
      <h3 class="sec">How it works</h3>
      <ol class="ag-gsteps">${AG_GUIDE_STEPS.map(s => `<li>${agEsc(s)}</li>`).join("")}</ol>
    </div>
    <div class="g3">
      <h3 class="sec">To start</h3>
      <p class="gp">${agEsc(AG_GUIDE_TYPE)}</p>
      <p class="gp">${agEsc(AG_GUIDE_AFTER)}</p>
    </div>
    <div class="g4">
      <h3 class="sec">What each tab holds</h3>
      <dl class="ag-gtabs">${AG_GUIDE_TABS.map(t => {
        /* the Tools row's sentence carries the one count on this screen; no count, no sentence */
        const desc = t[1] != null ? t[1]
          : tools ? `The ${tools} things it can do, in plain words.` : "";
        return `<dt>${agEsc(t[0])}</dt><dd>${agEsc(desc)}</dd>`;
      }).join("")}</dl>
    </div>
    <div class="g5">
      <h3 class="sec">Understand it better</h3>
      <ul class="ag-gdives">${AG_DIVES.map(d => `<li><button class="ag-gdive" type="button"
        data-ag="dive" data-arg="${agEsc(d[0])}"><span>${agEsc(d[1])}</span>${AG_ICON.arrow}</button></li>`).join("")}</ul>
    </div>
  </div>`;
}

function agSideHtml(a){
  const chats = a.chats || [];
  const h = a.health;
  const setup = agSetupOf(h);
  const dotCls = !h ? "" : !h.model_provider ? "bad" : !setup.ready ? "warn" : "run";
  const status = !h ? "checking…" : !h.model_provider ? "no model available" : !setup.ready ? "needs setup" : "ready";
  /* THE COMPANY THIS AGENT IS WORKING FOR, and the way to another (owner, 2026-09-11). The name the
     person gave it wins; the brand record is the fallback for a company named before companies
     existed. It is a button, so the chooser is one click from anywhere in the agent. */
  const coName = String((h && h.company && h.company.name) || agBrandName(a) || "").trim();
  const openIdeas = a.assets && a.assets.built ? (a.assets.counts || {}).open : null;
  /* Prompts sits with Memory and not with Tools: both are things the owner tells the agent about
     how to write, and neither is a thing the agent does. The count is how many he has changed. */
  const ownPrompts = a.prompts && a.prompts.edited ? a.prompts.edited.length : null;
  const rows = [["knowledge", "Knowledge", AG_ICON.doc, null], ["memory", "Memory", AG_ICON.star, a.memory ? a.memory.active : null],
                ["prompts", "Prompts", AG_ICON.pencil, ownPrompts || null],
                ["assets", "Asset ideas", AG_ICON.spark, openIdeas || null],
                ["library", "Library", AG_ICON.check, a.library ? a.library.length : null], ["tools", "Tools", AG_ICON.spark, null],
                ["connections", "Connections", AG_ICON.link, null]];
  const connWarn = h && (!h.dataforseo || !h.voyage);
  /* THE WAY BACK OUT. The agent is now somewhere you navigate INTO, so it has to be somewhere you
     can leave, and the top of its own column is the one place that is true of every view on it --
     the chat, the seven settings screens and an open review panel alike. */
  return `<button class="ag-back" type="button" data-ag="market">${AG_ICON.left} All agents</button>
    <div class="ag-agent">
      <div class="ag-mark" aria-hidden="true">S</div>
      <div style="min-width:0"><b>SEO Writer</b>
        <button class="ag-cosw" type="button" data-ag="cochoose" title="Switch company, or add another">${agEsc(coName || "Name your company")}${AG_ICON.chev}</button>
        <span><i class="dot ${dotCls}" aria-hidden="true"></i>${agEsc(status)}</span></div>
      ${agFacesHtml(a)}
    </div>
    ${agFacePickHtml(a)}
    <button class="newBtn" type="button" data-ag="new">${AG_ICON.plus} New chat</button>
    <div class="ag-sec">Recent</div>
    <div class="ag-chats">${chats.length ? chats.map(c => {
        const live = c.live || "";
        const asking = a.chatMenu === c.id;
        /* THE CONFIRM IS THE ROW (owner, 2026-09-10: "3 dots and delete the chat"). A chat holds
           work, so a single click must not lose it, but a browser confirm() blocks the Electron
           window and looks nothing like the app. The row turns into the question instead, and
           anywhere else you click puts it back. */
        return `<div class="ag-chatrow ${asking ? "asking" : ""}">
          <button class="ag-chat" type="button" data-ag="chat" data-arg="${agEsc(c.id)}" aria-current="${a.view === "chat" && a.chatId === c.id}" title="${agEsc(c.title)} · ${agEsc(agAgo(c.updated_at))}">
            <span class="dot ${live === "running" ? "run" : live === "waiting" ? "wait" : "idle"}" aria-hidden="true"></span>
            <span class="t">${agEsc(c.title || "New chat")}</span></button>
          ${asking
            ? `<span class="ag-chatask"><span class="lb">Delete?</span>
                 <button class="yes" type="button" data-ag="chatdel" data-arg="${agEsc(c.id)}">Yes</button>
                 <button class="no" type="button" data-ag="chatmenu" data-arg="">No</button></span>`
            : `<button class="ag-chatdots" type="button" data-ag="chatmenu" data-arg="${agEsc(c.id)}"
                 title="Delete this chat" aria-label="Delete the chat ${agEsc(c.title || "New chat")}">${AG_ICON.dots}</button>`}
        </div>`;
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
    : waiting ? (w.options && w.options.length ? "Type your answer, or pick an option above" : "Type your answer")
    : a.chat ? "Ask for another article, or give feedback"
    : a.health && !setup.ready ? "Give the website, e.g. example.com" : "Name a topic, or ask for ideas";
  const step = live && live.current_step ? live.current_step.replace(/_/g, " ") : (live ? live.stage : "");
  const state = running ? `<span class="ag-cstate"><i class="dot run"></i>the agent is working · ${agEsc(step)}</span>`
    : waiting ? `<span class="ag-cstate"><i class="dot wait"></i>waiting for you</span>` : "";
  /* THE BOX HAS AN EDGE (owner, 2026-09-10: "the chat bar is always supposed to be highlighted,
     so the user knows where the chat bar is"). The textarea and the send button are wrapped in
     one element so the FIELD can carry the border, the hover and the focus ring, rather than
     three loose controls sitting on the page looking like part of it. The wrapper is what
     :focus-within lights up, so clicking anywhere in the box reads as focused -- which is what
     it actually is. `busy` is the run's own state, so a disabled box looks disabled rather than
     looking broken. */
  return `${state}
    <div class="ag-field${running ? " busy" : ""}">
      <textarea data-agask rows="1" aria-label="Message the SEO Writer" placeholder="${agEsc(ph)}" ${running ? "disabled" : ""}></textarea>
      ${running ? `<button class="send stop" type="button" data-ag="stop" aria-label="Stop this run" title="Stop — the run halts after the current step"><svg width="10" height="10" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor"/></svg></button>`
               : `<button class="send" type="button" data-ag="send" aria-label="Send"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg></button>`}
    </div>`;
}

function agTranscriptHtml(a){
  /* An empty conversation is either somebody's first sight of this agent or their hundredth. The
     introduction is drawn only for the first, decided by agFirstRun from real state, so a
     returning open goes straight to the hero and its two plays. */
  if (!a.chat || !(a.chat.runs || []).length)
    return (agFirstRun(a) === true && !a.introSkip) ? agIntroHtml(a) : agHeroHtml(a.health, a.conns);
  const ctx = { collapsed: a.collapsed, stageOpen: a.stageOpen, stepOpen: a.stepOpen, panel: a.panel, detailOpen: a.detailOpen, now: Date.now() };
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

/* The brand pack: every file the setup built, what each is for, and what needs a look.

   THIS LIST IS HARDCODED, and it is the one file list on this screen that is. The Knowledge tab
   itself renders generically (agBriefHtml from brand.built_from, agExtrasHtml from brand.extras,
   both straight off pack.py), so a file the engine adds appears there on its own with the
   engine's own label. Here a file the engine adds but this list does not know still appears --
   agBrandPackHtml's `extra` bucket catches it -- but only under its raw filename, with no
   description. So a NEW knowledge door wants a row here to read properly. */
const AG_BRAND_FILES = [
  ["company.json", "The company record", "Name, website, one line on what they do, the market. The agent asks you to confirm the one-liner."],
  ["writer-brief.md", "Writer brief", "The one page every article is written from: what they believe, how they sound, words they use and refuse."],
  ["brand-voice.md", "Brand voice", "How the brand sounds, with real examples from the site."],
  ["style-guide.md", "Style guide", "Capitalisation, numbers, punctuation, house spelling, words to avoid."],
  ["persona.md", "Readers", "Who the articles are written for. Three or four reader types and how to pick one."],
  ["features.md", "Product facts", "What they sell, integrations, pricing, proof. The close reads this."],
  ["pricing.md", "Prices and hidden facts", "Anything your site draws with JavaScript, so a crawler cannot see it. Prices, plans, trial length. Type it here and it beats anything we read off the site."],
  ["cta-pages.md", "Pages a call to action may link to", "The short list the article's close is allowed to point at."],
  ["stats.md", "Real numbers", "Figures about the company, drafted from its own pages. Edit any row and your version is the truth."],
  ["stories.md", "Customer stories", "Named customer results, drafted from the site. Edit any entry and your version is the truth."],
  ["brand-cards.json", "Brand cards", "The numbers and stories as placeable facts, each with its source."],
  ["writing-examples.md", "Worked examples", "The best on-voice articles, annotated."],
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
  /* the line under the title. Every view but one takes it from the panel; the prompt view decides
     it HERE, from the data on screen, so it cannot still say "as it shipped" a moment after he
     saved his own version. */
  let body, footer = "", sub = p.subtitle;
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
    /* A REPORT is not a brand file. The refresh's change report borrows this view because it is
       the same thing on screen -- markdown in the panel -- but it is written BY the engine and
       there is nothing on disk for a save to land on, so a read-only panel gets no Edit. */
    footer = (p.readOnly || a.fileEdit) ? "" : `<button class="btn" type="button" data-ag="fileedit">Edit</button>${p.back ? `<button class="btn" type="button" data-ag="back">Back to the pack</button>` : ""}`;
  } else if (p.view === "prompt"){
    body = agPromptHtml(p.data, a.promptEdit);
    if (p.data) sub = p.data.edited ? "your version, used by the next article" : "as it shipped";
    footer = a.promptEdit ? "" : `<button class="btn pri" type="button" data-ag="promptedit">Edit</button>
      ${p.data && p.data.edited ? `<button class="btn" type="button" data-ag="promptreset">Reset to what shipped</button>` : ""}
      <span class="sp">${p.data && p.data.edited ? "This is your version. The next article uses it." : "This is what shipped."}</span>`;
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
  return `<div class="ag-ph"><div class="pt"><h3>${agEsc(title)}</h3><div class="ps">${agEsc(sub || (atCheckpoint ? "Edit anything here, then approve, and the agent continues from your version." : p.name))}</div></div>
      <button class="ib" type="button" data-ag="closepanel" aria-label="Close the panel"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg></button></div>
    <div class="ag-pb">${body}</div>
    ${footer ? `<div class="ag-pf">${footer}</div>` : ""}`;
}

/* ── settings views ────────────────────────────────────────────────────────── */

/* Keeping the catalogue current: one tool run, reported live in the card the button sits on.

   THE RULE THIS RENDERER BROKE ONCE (owner, 2026-09-10). It drew ONE FIXED SENTENCE -- "Asking
   the site for its current list…" -- for the whole run, because the route it called threw the
   engine's lines away. Six minutes of firewall cooldowns therefore looked exactly like a hang,
   and exactly like a finish. So: EVERY WORD OF PROGRESS IN HERE WAS SAID BY THE ENGINE. The
   labels and notes come off the job the server records as refresh_site emits them; nothing on
   this side rewrites them, and nothing invents a line from the fact that a button was pressed.

   Four states and no fifth: WORKING (the last line the engine said, the ones before it, and how
   long since it arrived), WAITING (which the engine announces, and which must never be drawn as
   working), DONE (the counts, exactly where the spinner was), and STOPPED (the reason, and no
   spinner anywhere near it). The button that STARTS it sits on the catalogue heading row
   (agCatControlsHtml); this renders only what is happening, and nothing when nothing is. */
function agRefreshLive(r){ return !!(r && r.phase === "running"); }

/* A gap in seconds, in his words. Seconds up to a minute, because "0m" is not an answer to
   "is this thing alive". */
function agSecsWords(secs){
  secs = Math.max(0, Math.round(Number(secs) || 0));
  if (secs < 60) return secs + "s";
  const m = Math.floor(secs / 60), s = secs % 60;
  return m + "m" + (s ? " " + s + "s" : "");
}

/* The lines before the one on top, newest first. The engine's own words, trimmed to a few: a
   person watching an update wants to see it moving, not read a transcript. */
function agRefreshTrailHtml(steps, n){
  const list = (steps || []).slice(-(n || 3)).reverse();
  if (!list.length) return "";
  return `<ul class="trail">${list.map(s =>
    `<li><b>${agEsc(s.label || "")}</b>${s.note ? ` <span class="h">${agEsc(s.note)}</span>` : ""}</li>`).join("")}</ul>`;
}

function agRefreshWorkingHtml(r, now, lost){
  const steps = r.steps || [];
  const last = steps.length ? steps[steps.length - 1] : null;
  const quiet = Math.max(0, now - (Number(r.updated_at) || Number(r.started_at) || now));
  const w = r.waiting || null;
  /* WAITING IS NOT WORKING. fetch.py announces a firewall cooldown before it sits through one,
     with its own number, so the card says it is waiting and for how long instead of showing the
     spinner it shows for a step that is moving. */
  /* Cannot reach the app: this card is not being told anything, so it says that rather than
     spinning on a frame that may be minutes old. It is the only foot line that is not about the
     refresh itself, and it wins, because it is the reason the others cannot be trusted. */
  const foot = lost
    ? `Not hearing from Sutra · this is what it last said, ${agEsc(agSecsWords(now - (Number(lost.since) || now)))} ago`
    : (w
      ? `Waiting on the site · ${agEsc(agSecsWords(now - (Number(w.since) || now)))} of ${agEsc(agSecsWords(w.seconds))}`
      : (quiet >= AG_REFRESH_QUIET_S
          ? `Still going · nothing new for ${agEsc(agSecsWords(quiet))}`
          : ""));
  const line = last
    ? `<b>${agEsc(last.label)}</b>${last.note ? ` <span class="h">${agEsc(last.note)}</span>` : ""}`
    : `Started. Nothing back from it yet.`;
  return `<div class="ag-refresh busy${w ? " waiting" : ""}">
    <div class="hd">${agEsc(r.label || "Catching up on what changed")}${r.mode === "preview" ? " · nothing is being changed yet" : ""}</div>
    <div class="now">${w ? `<span class="hold" aria-hidden="true"></span>` : `<span class="spin" aria-hidden="true"></span>`}<span class="msg">${line}</span></div>
    ${foot ? `<div class="foot">${foot}</div>` : ""}
    ${agRefreshTrailHtml(steps.slice(0, -1), 3)}
  </div>`;
}

function agRefreshHtml(a){
  const r = a.refresh || null;
  if (!r) return "";
  const now = Date.now() / 1000;
  const lost = a.refreshPollErr && a.refreshPollErr.n >= AG_REFRESH_LOST_POLLS ? a.refreshPollErr : null;
  if (agRefreshLive(r)) return agRefreshWorkingHtml(r, now, lost);
  const res = r.result || {};
  /* STOPPED. The reason, in the sentence whoever refused wrote -- the site, the engine, or the
     browser that never reached the server. Never a spinner, and never a "Done" over the top of
     it: a failure that looks like progress is worse than the silence this replaced. */
  if (r.phase === "failed"){
    const also = res.summary && String(res.summary) !== String(r.error)
      ? `<div class="msg">${agEsc(res.summary)}</div>` : "";
    return `<div class="ag-refresh stopped"><div class="msg err">${agEsc(r.error || "The refresh did not finish.")}</div>
      ${also}
      ${agRefreshTrailHtml(r.steps, 3)}
      <div class="ag-editrow"><button class="btn" type="button" data-ag="refreshcancel">Close</button></div></div>`;
  }
  /* DONE, having changed nothing: the four piles, and the press that would act on them. */
  if (r.mode === "preview"){
    const nothing = !res.new && !res.gone && !res.changed;
    return `<div class="ag-refresh done">
      <div class="msg">${nothing ? "Nothing has changed since the last read."
        : `<b>${agEsc(agNum(res.new))} new</b>, ${agEsc(agNum(res.gone))} gone, ${agEsc(agNum(res.changed))} rewritten.${res.unchecked ? ` ${agEsc(agNum(res.unchecked))} pages give no date, so they cannot be checked without reading them.` : ""}`}</div>
      <div class="ag-editrow">
        ${nothing ? "" : `<button class="btn pri" type="button" data-ag="refreshgo">Update the catalogue</button>`}
        ${nothing || !res.report ? "" : `<button class="btn" type="button" data-ag="refreshreport">See the list</button>`}
        <button class="btn" type="button" data-ag="refreshcancel">${nothing ? "Close" : "Not now"}</button>
      </div></div>`;
  }
  /* DONE, having written: the engine's own count of what it did. */
  return `<div class="ag-refresh done">
    <div class="msg"><b>Done.</b> ${agEsc([res.summary, res.note].filter(Boolean).join(" "))}</div>
    <div class="ag-editrow"><button class="btn" type="button" data-ag="refreshchanges">See what changed</button>
      <button class="btn" type="button" data-ag="refreshcancel">Close</button></div></div>`;
}
/* The small controls that belong to the catalogue, on its heading row rather than in the body:
   the map, and the one way to bring the catalogue up to date.

   THE TRAFFIC IMPORT IS NOT A BUTTON (owner, 2026-09-09). It was built for one incident -- a
   DataForSEO balance at minus seven cents, mid-build -- and it is not a thing anybody sets out
   to do from a settings tab. The IMPORTER is untouched: POST /knowledge/traffic still works and
   the agent still offers it in the chat when an account runs dry, which is the only moment it
   makes sense. What is gone is the standing affordance. */
function agCatControlsHtml(a, canMap){
  return `<div class="ag-secctl">
    ${canMap ? `<button class="btn" type="button" data-ag="map">${a.mapOn ? "Hide the map" : "Show the map"}</button>` : ""}
    <button class="btn" type="button" data-ag="refreshcheck" title="Reads only what is new or has changed, not the whole site.">Check for changes</button>
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

/* THE FILES A PERSON FILLS IN, and the one empty state in the product that matters most.

   Every other unbuilt file on this screen is something the machine will get to. This one is not:
   only a person can supply it. pricing.md holds what a site draws with JavaScript -- prices,
   plans, trial length -- which a crawler can never see, and features.md, the file the writer reads
   for product claims, is filled FROM it. Nobody fills it in and the articles go on quoting prices
   scraped off stale translated pages. So an unfilled one is drawn as an ASK: an accent edge, a
   primary button, the reason in the row, and a door that lands in the editor rather than in a
   read-only view with an Edit button to find.

   FILLED IS THE ENGINE'S WORD, not a word count. The blank form is real text on disk (205 words
   of it), so `words` alone would have called an untouched form filled and stopped asking on the
   day it was created -- which is precisely how the seed file this replaces stayed empty for
   months. pack.inputs() carries `filled` from features.untouched(); the count is reported beside
   it, never instead of it.

   Once it IS filled the row settles down: same section, ordinary weight, and the button becomes
   Open. An ask that keeps asking after it has been answered is just noise. */
function agInputsHtml(brand){
  const list = (brand && brand.inputs) || [];
  return list.map(f => {
    /* `filled` absent means an older engine that cannot tell: keep asking rather than assume it
       is done -- the cost of asking twice is far below the cost of never asking. */
    const filled = f.filled === true;
    return `<h3 class="sec">${agEsc(f.label || f.name)}</h3>
    <div class="ag-row${filled ? "" : " ask"}"><div class="ri">
      <div class="rn">${agEsc(f.note || f.name)} <span class="pill ${filled ? "p-ok" : "p-ask"}">${filled ? "you wrote this" : "yours to write"}</span></div>
      ${filled ? "" : `<div class="rd">Nothing has been written here yet. Nobody can read these off your website, and the agent will not guess at them.</div>`}
      <div class="rm"><span>${agEsc(f.name)}</span><span>${f.exists ? (filled ? agEsc(agNum(f.words)) + " words" : "the blank form") : "not started"}</span></div></div>
      <div class="ra"><button class="btn ${filled ? "" : "pri"}" type="button" data-ag="inputwrite" data-arg="${agEsc(f.name)}" data-label="${agEsc(f.label || f.name)}">${filled ? "Open" : "Write it"}</button></div></div>`;
  }).join("");
}

/* A file the pack carries but nothing reads yet. Its own heading, because its label IS the
   heading, and said plainly to be idle rather than left to look built. */
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
  const inputs = agInputsHtml(k.brand);
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

    ${inputs}

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
      <div class="rd">Finds what's worth writing: what earns your competitors links, formats that work elsewhere, and what your audience talks about. About 30 minutes. It asks you twice: the competitors, then the communities.</div>
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
  /* "Next up" told him nothing about WHERE this idea came from ("okay next up, oh this is the
     next topic, all of that's not clear" -- owner, 2026-09-09). It is the top-ranked idea of the
     ones still open, so the card says exactly that and how many are behind it. */
  const open1 = c.open || 0;
  return `<div class="ag-view wide"><h2>Asset ideas</h2>
    <p class="lead">${agEsc(agNum(as.total))} ideas${c.done ? `, ${agEsc(agNum(c.done))} written` : ""}.
      ${as.methods_line ? agEsc(as.methods_line)
        : blocked.length ? `${3 - blocked.length} of 3 methods contributed; ${agEsc(blocked.map(agMethodName).join(" and "))} did not.`
        : "All three methods contributed."}</p>

    ${nx ? `<div class="ag-nextidea">
      <div class="nl">The idea to write next${open1 ? `<span class="nq">top of the ${agEsc(agNum(open1))} still to write</span>` : ""}</div>
      <div class="nt">${agEsc(nx.title)}</div>
      <div class="nd">${agEsc(nx.angle || "")}</div>
      <dl class="nf">
        ${nx.format ? `<div><dt>Shape</dt><dd>${agEsc(nx.format)}</dd></div>` : ""}
        ${(nx.method || []).length ? `<div><dt>Found by</dt><dd>${agEsc((nx.method || []).map(agMethodName).join(" and "))}</dd></div>` : ""}
        ${nx.linkability && nx.linkability.score ? `<div><dt>Would anyone cite it</dt><dd>${agEsc(nx.linkability.score)} out of ${agEsc(nx.linkability.of || 4)}</dd></div>` : ""}
      </dl>
      <div class="ag-editrow">
        <button class="btn pri" type="button" data-ag="ideawrite" data-arg="${agEsc(nx.id)}"
          data-text="${agEsc("Write this asset idea: " + nx.title)}">Write this one</button>
        <button class="btn" type="button" data-ag="ideadrop" data-arg="${agEsc(nx.id)}">Not this one</button>
      </div>
      <p class="nh"><b>Write this one</b> opens the chat and starts the research on it.
        <b>Not this one</b> drops it off the sheet and the next-ranked idea moves up here.</p>
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
    <p class="lead">Rules the agent follows in every article. It saves one when you tell it something that should always apply, and you can add your own.</p>
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
/* WHAT SHAPE THIS ARTICLE WAS WRITTEN TO, on the Library row. The archetype is decided once, at
   the route step, and the server reads it back off the run that made the article; the plain name
   comes from the server too, from the same list the Prompts tab names the format rules by, so the
   two screens cannot end up calling one shape by two names. A row whose run never got as far as
   the router simply has no format, and shows none rather than guessing one. */
function agLibFormat(it){
  const label = (it && (it.format_label || it.format)) || "";
  return label ? `<span title="The format this article was written to">${agEsc(label)}</span>` : "";
}

function agLibraryHtml(items){
  const list = items || [];
  const bin = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>`;
  return `<div class="ag-view"><h2>Library</h2>
    <p class="lead">Every article, from the moment it starts. You can read one while it is still being written. Nothing is published until you publish it.</p>
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
        <div class="rm">${writing && miles.length ? `<span>${agEsc(done)} of ${agEsc(miles.length)} done</span>` : `<span>${agEsc(agNum(it.words))} words</span>`}${it.primary_keyword ? `<span>${agEsc(it.primary_keyword)}</span>` : ""}${agLibFormat(it)}<span>${writing ? "started " : ""}${agEsc(agAgo(it.created_at))}</span></div>
        ${agMileStripHtml(it.id, miles, writing)}</div>
        <div class="ra">${writing ? "" : `<button class="btn" type="button" data-ag="libopen" data-arg="${agEsc(it.id)}">Open</button>
          <button class="btn" type="button" data-ag="libstatus" data-arg="${agEsc(it.id)}" data-status="${status === "ready" ? "draft" : "ready"}">${status === "ready" ? "Back to draft" : "Mark ready"}</button>`}
          <button class="ib" type="button" data-ag="libdel" data-arg="${agEsc(it.id)}" aria-label="Delete" title="Delete this article">${bin}</button></div></div>`;
    }).join("")
      : `<div class="ag-row"><div class="ri"><div class="rn">Nothing here yet</div><div class="rd">Ask for an article and its row appears here straight away, filling in as each piece is made.</div></div></div>`}
  </div>`;
}

/* ── the Prompts tab ───────────────────────────────────────────────────────────────────────
   The craft of this agent is in its prompts, and the craft is the owner's. This screen is where
   he changes it without a developer: open one, edit it, save, and the very next article is
   written from his version.

   Two halves, in the order he asked for them. Across the top, the whole write phase as a phrase
   per step, so he can see where the thing he is about to edit actually sits. Below it, the
   prompts themselves in ONE scrolling box that deliberately does not fill the screen.

   THE FORMAT RULES COME FIRST, in the flow and in the list. They are not part of the architect;
   they are what it obeys, and they decide what a section must contain. Nothing in the flow is
   marked as missing or not running: every station in it ships in this release.

   Nothing here concerns the word count. That is one question asked during a run, and it is not a
   setting. */

function agFlowHtml(flow){
  const rows = flow || [];
  if (!rows.length) return "";
  return `<div class="ag-flow" aria-label="How an article gets written, step by step">
    ${rows.map(st => `<div class="ag-flowrow ${st.rules ? "rules" : ""}">
      <div class="fh">${agEsc(st.title)}</div>
      <ol class="fs">${(st.steps || []).map(s => `<li>${agEsc(s)}</li>`).join("")}</ol>
    </div>`).join("")}
  </div>`;
}

function agPromptRowHtml(p, open){
  const n = p.lines || 0;
  return `<button class="ag-file ${open === p.name ? "on" : ""}" type="button" data-ag="promptopen" data-arg="${agEsc(p.name)}">
    <span class="fi" aria-hidden="true">${AG_ICON.doc}</span>
    <span class="ft"><span class="fn">${agEsc(p.title)}${p.edited ? ` <span class="pill p-acc">yours</span>` : ""}</span>
      <span class="fd">${agEsc(p.note || "")}</span></span>
    <span class="fm">${agEsc(agNum(n))} line${n === 1 ? "" : "s"}</span></button>`;
}

function agPromptsHtml(d, a){
  const groups = (d && d.groups) || [];
  const open = a && a.panel && a.panel.view === "prompt" ? a.panel.name : "";
  const edited = (d && d.edited) || [];
  return `<div class="ag-view"><h2>Prompts</h2>
    <p class="lead">The instructions the agent writes by. Change one and the next article uses your version. Reset puts it back.</p>
    <h3 class="sec">How an article gets written</h3>
    ${agFlowHtml(d && d.flow)}
    <h3 class="sec">The prompts${edited.length ? ` <small>${agEsc(edited.length)} changed by you</small>` : ""}</h3>
    <div class="ag-promptlist">
      ${groups.map(g => `<div class="ag-promptgroup">
        <div class="gh">${agEsc(g.title)}</div>
        <p class="gn">${agEsc(g.note || "")}</p>
        <div class="ag-files">${(g.prompts || []).map(p => agPromptRowHtml(p, open)).join("")}</div>
      </div>`).join("")}
      ${groups.length ? "" : `<div class="ag-row"><div class="ri"><div class="rn">Nothing to show</div>
        <div class="rd">The prompts could not be read. The agent may not be installed yet.</div></div></div>`}
    </div>
  </div>`;
}

/* One prompt in the review panel. It opens showing what it currently says, so he edits rather than
   starts from nothing, and the placeholders the code fills are listed above it: they are the one
   thing in the file he must not delete, and a save that has lost one is refused with the missing
   ones named.
   The strip is drawn only when the server says this prompt IS filled. A format rulebook is not:
   its words are lifted whole into another prompt, so it has no blanks of its own, and telling him
   to keep placeholders it does not have would be a warning about nothing. */
function agPromptHtml(d, edit){
  if (!d) return `<div class="zero"><h4>Nothing to show</h4></div>`;
  const toks = d.filled ? (d.tokens || []) : [];
  const head = `${d.note ? `<div class="ag-why">${agEsc(d.note)}</div>` : ""}
    ${toks.length ? `<div class="ag-toks"><span class="tl">The agent fills these in. Keep every one of them.</span>
      ${toks.map(t => `<code>{{${agEsc(t)}}}</code>`).join("")}</div>` : ""}`;
  if (edit) return `<div class="ag-editbox">${head}
    <textarea data-agprompttext class="tall" spellcheck="false" aria-label="The prompt">${agEsc(edit.text != null ? edit.text : d.text)}</textarea>
    ${edit.msg ? `<div class="ag-err">${agEsc(edit.msg)}</div>` : ""}
    <div class="row"><button class="btn pri" type="button" data-ag="promptsave" ${edit.busy ? "disabled" : ""}>${edit.busy ? "Saving…" : "Save"}</button>
      <button class="btn" type="button" data-ag="promptcancel">Cancel</button>
      <span class="sp">Saved to your own copy, never over what shipped</span></div></div>`;
  return `${head}<pre class="ag-prompttext">${agEsc(d.text)}</pre>`;
}

/* The tool's name in words. registry.label() is the ONE place that decides it -- it covers every
   work tool -- and this only has a fallback at all so a tool added upstream before its label is
   written still draws a row instead of an empty cell. The screen carried a stand-in map for the
   three tools LABELS was missing until 2026-09-09; the labels landed upstream and it was deleted,
   which is what a display fallback is for. */
function agToolName(t){
  return (t && t.label) || String((t && t.name) || "").replace(/_/g, " ");
}

function agToolsHtml(tools){
  const list = tools || [];
  /* The count is DERIVED, never typed. It said "the seven things" over eleven rows for as long as
     the eleventh tool had existed, and there are twelve now -- because a sentence with a number
     in it goes stale the day the list grows and nobody thinks to look at the paragraph above it.

     AND THERE IS ONLY ONE NUMBER IN IT. The sentence used to go on to say "the last four run for
     every article", which was true only by an accident of ordering: find_prompt was added at the
     end of the list and is not a per-article step at all, so the claim was false the day it
     landed. A positional claim about a list somebody else owns cannot be kept true, so it is
     gone, and what is left says the same useful thing without counting anything. */
  const n = list.length;
  const words = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                 "ten", "eleven", "twelve", "thirteen", "fourteen"];
  const count = n < words.length ? words[n] : String(n);
  return `<div class="ag-view"><h2>Tools</h2>
    <p class="lead">The ${agEsc(count)} thing${n === 1 ? "" : "s"} the agent can do, in the order they usually run. Setup runs once. The writing steps run again for every article, and you look at the result of each before the next starts.</p>
    ${list.map((t, i) => `<div class="ag-row"><div class="ri"><div class="rn"><span class="n">${i + 1}</span>${agEsc(agToolName(t))}</div>
        <dl class="ag-kv" style="margin:8px 0 0">
          <dt>What it does</dt><dd>${agEsc(t.does || t.description || "")}</dd>
          ${t.when ? `<dt>When it runs</dt><dd>${agEsc(t.when)}</dd>` : ""}
          ${t.needs ? `<dt>What it needs</dt><dd>${agEsc(t.needs)}</dd>` : ""}
          ${t.takes ? `<dt>How long</dt><dd>${agEsc(t.takes)}</dd>` : ""}
        </dl></div></div>`).join("")}
  </div>`;
}

/* ── the team workspace ────────────────────────────────────────────────────────
   Five people, one Supabase project the company owns. One person presses Create and gets a
   link; everybody else pastes that link once. After that nobody presses sync and nobody
   imports anything (design/WORKSPACE-PLAN.md, section 1).

   THREE THINGS THIS BLOCK IS BUILT AROUND, all from the plan's section 10.

   * "Created" is drawn from ONE field and one only: a job the server moved to `done`, which
     the server moves only after schema.verify() has seen every table. There is no branch here
     that infers success from a request that came back.
   * The personal access token is asked for at the moment it is used, in its own step, with the
     one line that says what it is for. It is never put on S.ag, never rendered into an input's
     value, and never drawn back. agTokenTyped() is the whole of how it survives a redraw.
   * Every failure gets two sentences: what failed, and what to do about it. The server writes
     both; this only draws them. And whenever the seamless route stops for any reason at all,
     the SQL fallback is already on screen with the reason above it, so there is no state a
     person can reach where the next move is not in front of them. */

const AG_WS_BUSY = ["starting", "tables", "verify", "pack", "download"];
const AG_WS_PACK_BUSY = ["building", "uploading", "packing"];

function agBytes(n){
  n = Number(n) || 0;
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(0) + " KB";
  if (n < 1073741824) return (n / 1048576).toFixed(n < 10485760 ? 1 : 0) + " MB";
  return (n / 1073741824).toFixed(1) + " GB";
}

function agWsJobLive(ws){
  const j = ws && ws.job;
  return !!(j && AG_WS_BUSY.indexOf(j.phase) !== -1);
}

/* What is happening right now, in his words rather than a state name. Read from the server's
   sync block and nothing else: a line invented on the client would keep saying "updating" long
   after the upload finished, which is the same class of lie as an unverified "created". */
function agWsNowLine(sync){
  if (!sync) return "";
  const pend = Number(sync.pending) || 0;
  if (pend > 0) return pend === 1 ? "1 change waiting to go up" : pend + " changes waiting to go up";
  if (AG_WS_PACK_BUSY.indexOf(String(sync.pack_state || "")) !== -1) return "Updating the copy for new joiners";
  if (String(sync.pack_state || "") === "unknown") return "";
  return "Up to date";
}

/* The quiet line, section 2's whole concession. He clicks Update, the click finishes in about
   two seconds, and this appears at the bottom of whatever screen he is on until the pack has
   been rebuilt. Never a modal, never a bar to watch, never something he has to dismiss — and
   never shown from a guess: it is on while the server says the pack is being rebuilt, and off
   the moment the server says it is not. */
function agQuietHtml(a){
  const sync = a && a.ws && a.ws.sync;
  if (!sync || AG_WS_PACK_BUSY.indexOf(String(sync.pack_state || "")) === -1) return "";
  return `<span class="d"></span>Updating the copy for new joiners`;
}

function agWsLinkRowHtml(link){
  if (!link) return "";
  return `<div class="ag-wslink"><code>${agEsc(link)}</code>
    <button class="btn" type="button" data-ag="wscopylink">Copy link</button></div>`;
}

function agWsMembersHtml(members, meId){
  const list = members || [];
  if (!list.length) return `<div class="rd">Nobody has joined yet. Send the link.</div>`;
  return `<div class="ag-wsmembers">${list.map(m => {
    const me = m && m.member_id && meId && m.member_id === meId;
    const seen = agAgoWords(m && m.last_seen_at);
    return `<span class="ag-wsmember"><b>${agEsc((m && m.name) || "Somebody")}</b>${me ? ` <i>you</i>` : ""}${seen ? ` <span class="h">${agEsc(seen)}</span>` : ""}</span>`;
  }).join("")}</div>`;
}

/* A job in flight. Create gets a spinner and a coarse percentage because nothing about making
   nine tables is measurable in bytes; join gets the real thing, because the download IS bytes
   and a five-minute wait behind a spinner that could mean anything is the reason section 1
   asked for a bar. When the server has not been told a total, this says how much has come down
   and draws NO bar rather than an invented one. */
function agWsJobHtml(job){
  const pct = job.pct == null ? null : Math.max(0, Math.min(100, Number(job.pct) || 0));
  const known = Number(job.total_bytes) > 0;
  const bar = job.kind === "join"
    ? (known
        ? `<div class="ag-bar"><i style="width:${Math.max(0, Math.min(100, Math.round(100 * job.done_bytes / job.total_bytes)))}%"></i></div>
           <div class="rm"><span>${agEsc(agBytes(job.done_bytes))} of ${agEsc(agBytes(job.total_bytes))}</span><span>about five minutes on a normal line</span></div>`
        : `<div class="rm"><span>${agEsc(agBytes(job.done_bytes))} so far</span><span>the total is not known yet</span></div>`)
    : (pct == null ? "" : `<div class="ag-bar"><i style="width:${pct}%"></i></div>`);
  const head = job.kind === "join" ? "Joining the workspace" : "Creating your workspace";
  return `<div class="ag-row writing"><div class="ri">
    <div class="rn"><span class="pill p-acc"><i class="spin"></i>working</span>${agEsc(head)}</div>
    <div class="rd">${agEsc(job.step || head)}</div>
    ${bar}
  </div></div>`;
}

/* THE SETUP SCRIPT, AND IT IS A ROUTE RATHER THAN AN ERROR.

   There may be no Supabase access token on this machine, and pasting the script into
   Supabase's own SQL Editor is then how a workspace gets made — not a workaround for a thing
   that broke. So it is drawn the way a step is drawn: its own heading, four numbered moves,
   the script, and one button at the end. No red, no apology.

   The line above it is whatever schema said, verbatim. It covers four different situations —
   no token was given, the script half-applied, the tables cannot be read with this key, or
   the tables are there but the knowledge bucket is not — and schema's sentence names which
   one. Rewriting it here is how a message ends up blaming the project URL for a storage
   problem, which this feature has already done once. */
function agWsPasteHtml(pv, busy){
  return `<div class="ag-row ask"><div class="ri">
    <div class="rn">Run the setup script<span class="ag-status"><i class="dot warn"></i>one paste, about thirty seconds</span></div>
    ${pv.why ? `<div class="rd">${agEsc(pv.why)}</div>` : ""}
    <ol class="ag-wssteps"><li>Open your project's SQL Editor.</li>
      <li>Paste this script in.</li>
      <li>Press Run. It either all works or none of it does, and running it twice is harmless.
        The last line it prints says whether the workspace is ready.</li>
      <li>Come back here and press <b>I've run it</b>.</li></ol>
    <pre class="ag-prompttext">${agEsc(pv.sql || "")}</pre>
    <div class="row" style="margin-top:10px">
      <button class="btn" type="button" data-ag="wscopysql">Copy the script</button>
      ${pv.editor_url ? `<a class="btn" href="${agEsc(pv.editor_url)}" target="_blank" rel="noopener">Open the SQL Editor</a>` : ""}
      <button class="btn pri" type="button" data-ag="wssqldone" ${busy ? "disabled" : ""}>${busy ? "Checking…" : "I've run it"}</button>
      <button class="btn" type="button" data-ag="wscancel">Cancel</button>
    </div>
  </div></div>`;
}

function agWsFailedHtml(job){
  const e = job.error || {};
  return `<div class="ag-row"><div class="ri">
    <div class="rn">${job.kind === "join" ? "Joining did not finish" : "The workspace was not created"}
      <span class="ag-status"><i class="dot bad"></i>nothing was left half-made</span></div>
    <div class="ag-err" style="margin:8px 0 0"><b>${agEsc(e.what || "It did not finish.")}</b>
      ${e.do ? `<div style="margin-top:4px">${agEsc(e.do)}</div>` : ""}</div>
    <div class="row" style="margin-top:10px">
      <button class="btn pri" type="button" data-ag="wsretry">Try again</button>
      <button class="btn" type="button" data-ag="wscancel">Start over</button></div>
  </div></div>`;
}

/* The two boxes and the button section 1 names, and a third box for the access token.

   WHY THE TOKEN IS ON THIS FORM AND NOT BEHIND ITS OWN STEP. There is no Supabase access
   token on the owner's machine and there may never be one, so the setup script route is not a
   consolation prize: for many people it is the only way through, and hiding it behind a step
   that asks for a credential first would put a locked door in front of the open one. So the
   token is optional, labelled with what it does and that it is not kept, and pressing Create
   with the box empty is a perfectly ordinary thing to do — the script comes straight back. */
function agWsCreateFormHtml(f){
  return `<div class="ag-row"><div class="ri">
    <div class="rn">Create a workspace<span class="ag-status"><i class="dot warn"></i>not connected</span></div>
    <div class="rd">Make a free Supabase project and paste its two details here. Your data stays in your own account.</div>
    <div class="ag-form" style="margin-top:10px">
      <div class="row"><a class="btn" href="https://supabase.com/dashboard/projects" target="_blank" rel="noopener">Go to Supabase</a>
        <span class="sp">then Project Settings → Data API</span></div>
      <label><b>Project URL</b><input type="text" data-agws="url" autocomplete="off" spellcheck="false" placeholder="https://abcdefghijklmnop.supabase.co" value="${agEsc(f.url || "")}"></label>
      <label><b>Publishable key</b><input type="text" data-agws="key" autocomplete="off" spellcheck="false" placeholder="sb_publishable_…" value="${agEsc(f.key || "")}"></label>
      <label><b>What to call it</b><input type="text" data-agws="name" autocomplete="off" placeholder="Our team" value="${agEsc(f.name || "")}"></label>
      <label><b>Access token <span class="ag-opt">optional</span></b>
        <input type="password" data-agws="token" autocomplete="off" spellcheck="false" placeholder="sbp_… — leave this empty to set the tables up yourself">
        <span class="ag-hint">Sutra uses it once to set things up. It is never written to disk and never kept. Leave this empty to get a script to paste instead.
          <a href="https://supabase.com/dashboard/account/tokens" target="_blank" rel="noopener">Get a token</a>.</span></label>
      ${f.msg ? `<div class="ag-err" style="margin:0">${agEsc(f.msg)}</div>` : ""}
      <div class="row"><button class="btn pri" type="button" data-ag="wsgo" ${f.busy ? "disabled" : ""}>${f.busy ? "Working…" : "Create"}</button>
        <button class="btn" type="button" data-ag="wscancel">Cancel</button></div>
    </div></div></div>`;
}

function agWsJoinFormHtml(f){
  return `<div class="ag-row"><div class="ri">
    <div class="rn">Join a workspace<span class="ag-status"><i class="dot warn"></i>not connected</span></div>
    <div class="rd">Paste the link your teammate sent you, and add your name. You get the team's Library, ideas and prompts.</div>
    <div class="ag-form" style="margin-top:10px">
      <label><b>The link</b><input type="text" data-agws="link" autocomplete="off" spellcheck="false" placeholder="sutra1_…" value="${agEsc(f.link || "")}"></label>
      <label><b>Your name</b><input type="text" data-agws="name" autocomplete="off" placeholder="Ravi" value="${agEsc(f.name || "")}"></label>
      ${f.msg ? `<div class="ag-err" style="margin:0">${agEsc(f.msg)}</div>` : ""}
      <div class="row"><button class="btn pri" type="button" data-ag="wsjoingo">Done</button>
        <button class="btn" type="button" data-ag="wscancel">Cancel</button>
        <span class="sp">usually takes under a minute</span></div>
    </div></div></div>`;
}

/* Connected. Section 3's four things and nothing else: the name, who is in it, the link with a
   copy button, and what is happening right now. The link lives here for good — that is where
   somebody comes back to when a sixth person joins in March. */
function agWsRestingHtml(ws, justDone){
  const w = ws.workspace || {};
  const now = agWsNowLine(ws.sync);
  const warn = justDone && justDone.error ? justDone.error : null;
  const n = (ws.members || []).length;
  return `${justDone ? `<div class="ag-row"><div class="ri"><div class="rn">${justDone.kind === "join" ? "You are on the team" : "Your workspace is ready"}
      <span class="ag-status"><i class="dot ok"></i>every table checked</span></div>
      <div class="rd">${justDone.kind === "join"
        ? "Your Library, ideas and prompts are the team's now. Nobody presses sync again."
        : "Send the link below to the rest of the team. Nothing in it can make or drop a table."}</div>
      ${warn ? `<div class="ag-err" style="margin:8px 0 0"><b>${agEsc(warn.what)}</b>${warn.do ? `<div style="margin-top:4px">${agEsc(warn.do)}</div>` : ""}</div>` : ""}
      </div></div>` : ""}
    <div class="ag-row"><div class="ri">
      <div class="rn">${agEsc(w.name || "The team workspace")}
        <span class="ag-status"><i class="dot ok"></i>connected</span></div>
      <div class="rd">${agEsc(w.url || "")}</div>
      <div class="rm" style="margin-top:8px"><span>${n === 1 ? "1 person" : n + " people"}</span>${now ? `<span>${agEsc(now)}</span>` : ""}</div>
      ${agWsMembersHtml(ws.members, ws.me && ws.me.member_id)}
      ${agWsLinkRowHtml(ws.link)}
      <div class="row" style="margin-top:10px"><button class="btn" type="button" data-ag="wsleave">Leave the workspace</button>
        <span class="sp">your own copy stays exactly as it is</span></div>
    </div></div>`;
}

/* NO "UPDATE WORKSPACE" BUTTON, DELIBERATELY. There was one for about an hour.

   A workspace created by this build is born current: schema.sql makes every table the code knows
   about and stamps the current version. So a migration can only ever apply to a workspace made
   BEFORE the change that needs it — a population that starts tiny and shrinks to nothing, and on
   2026-09-10 was exactly one person, the owner, whose workspace predated the table added that
   afternoon.

   Putting database maintenance on his screen for that was the wrong trade. His words: "this
   updating part was for us to do that one-off addition, which is not required for all days... I
   don't think we should allow him to do it." Right: a person who set a workspace up once should
   never be asked to run schema steps because we thought of a feature later.

   schema.migrate() and POST /workspace/update both still exist and are still tested. They are OUR
   tools, run deliberately, not a button somebody finds. And nothing is silent about it either:
   sync.push declines rather than queues a row a workspace cannot take, so a feature that is
   waiting on a migration waits visibly in status() instead of wedging the outbox. */

/* THE UNFINISHED WORKSPACE, which is a real state and not a theory.

   A project can end up with all ten tables and no knowledge bucket: the storage policies do
   not always attach, and the tables survive when they do not. There is a URL, a key and an id
   in connections.json, so everything that only reads settings thinks this is connected — and
   nobody can ever join it, because the pack has nowhere to live. So the tab does not draw
   "connected" from having credentials. It draws it from schema.verify(), and when verify says
   no it says so and puts the script back in front of the person with verify's own reason. */
function agWsUnfinishedHtml(ws, pv, busy){
  const why = (ws.verify && ws.verify.reason) || "";
  return `<div class="ag-row"><div class="ri">
      <div class="rn">${agEsc((ws.workspace && ws.workspace.name) || "The team workspace")}
        <span class="ag-status"><i class="dot warn"></i>not finished</span></div>
      <div class="rd">${agEsc(why || "This project is not set up as a workspace yet.")}</div>
      <div class="rm" style="margin-top:8px"><span>${agEsc((ws.workspace && ws.workspace.url) || "")}</span></div>
      <div class="row" style="margin-top:10px">
        <button class="btn pri" type="button" data-ag="wssqldone" ${busy ? "disabled" : ""}>${busy ? "Checking…" : "Check again"}</button>
        <button class="btn" type="button" data-ag="wsleave">Leave the workspace</button>
        <span class="sp">nobody can join until this is finished</span></div>
    </div></div>
    ${pv ? agWsPasteHtml(pv, busy) : ""}`;
}

function agWsHtml(ws, f){
  f = f || {};
  const head = `<h3 class="sec">Team workspace</h3>`;
  if (ws && ws.installed === false)
    return `${head}<div class="ag-row"><div class="ri"><div class="rn">Not in this build
      <span class="ag-status"><i class="dot warn"></i>nothing to set up yet</span></div>
      <div class="rd">The team workspace ships with a later version of Sutra. Nothing here is broken and nothing needs doing.</div></div></div>`;

  const job = ws && ws.job;
  if (job && AG_WS_BUSY.indexOf(job.phase) !== -1) return head + agWsJobHtml(job);
  if (job && job.phase === "paste" && job.paste) return head + agWsPasteHtml(job.paste, !!f.busy);
  if (job && job.phase === "failed") return head + agWsFailedHtml(job);

  /* Credentials are not evidence. verify() is, and only an explicit false is treated as one:
     a null means nobody has been able to ask yet (offline, or the tab has only just opened),
     and answering an unasked question either way would be inventing the answer. */
  if (ws && ws.configured && ws.verify && ws.verify.ok === false)
    return head + agWsUnfinishedHtml(ws, job && job.phase === "paste" ? job.paste : null, !!f.busy);

  /* The "ready" greeting is a moment, not a state. It rides on the job the server is still
     holding, and stops being drawn once that job is a quarter of an hour old, so a tab left
     open all afternoon settles back to the plain connected row on its own. */
  const fresh = job && job.phase === "done" && job.finished_at
    && (Date.now() / 1000 - Number(job.finished_at)) < 900;
  if (ws && ws.configured) return head + agWsRestingHtml(ws, fresh ? job : null);

  if (f.mode === "create") return head + agWsCreateFormHtml(f);
  if (f.mode === "join") return head + agWsJoinFormHtml(f);
  return `${head}<div class="ag-row"><div class="ri">
    <div class="rn">Work as a team<span class="ag-status"><i class="dot warn"></i>not connected</span></div>
    <div class="rd">One person sets it up. Everyone else pastes a link once. After that, the Library, ideas and prompts stay in sync on their own.</div>
    <div class="row" style="margin-top:10px"><button class="btn pri" type="button" data-ag="wscreate">Create workspace</button>
      <button class="btn" type="button" data-ag="wsjoin">Join workspace</button></div>
  </div></div>`;
}


function agConnectionsHtml(c, h, form, ws, wsForm){
  const dfs = !!(c && c.dataforseo_login && c.dataforseo_password);
  const voy = !!(c && c.voyage_key);
  const prov = h ? h.model_provider : null;
  form = form || {};
  /* The workspace goes first because it is the one section that is about the TEAM rather than
     about this Mac, and because the person who has just been sent a link came to this tab for
     it. The lead below counts nothing: a typed number over a list that grows is the mistake the
     Tools tab already made once. */
  return `<div class="ag-view"><h2>Connections</h2>
    <p class="lead">What the agent needs, and your team. Keys stay on this Mac and are never shown again.</p>
    ${agWsHtml(ws, wsForm)}
    <h3 class="sec">Model</h3>
    <div class="ag-row"><div class="ri"><div class="rn">${prov === "claude-cli" ? "Claude, through the command line" : prov ? agEsc(prov) : "No model available"}
        <span class="ag-status"><i class="dot ${prov ? "ok" : "bad"}"></i>${prov === "claude-cli" ? "billed to your Claude subscription" : prov ? "connected" : "not signed in"}</span></div>
      <div class="rd">${prov ? "The same sign-in the chat uses. No API key anywhere." : "Open a terminal, run <code>claude</code> once and sign in. This screen will notice."}</div></div></div>
    <h3 class="sec">DataForSEO · real search numbers</h3>
    <div class="ag-row"><div class="ri"><div class="rn">DataForSEO <span class="ag-status"><i class="dot ${dfs ? "ok" : "warn"}"></i>${dfs ? "connected" : "not connected"}</span></div>
      <div class="rd">Real search numbers: how many people search, how hard it is to rank, and who ranks now. Research needs it. Under $1 an article.</div>
      <div class="ag-form" style="margin-top:10px">
        <label><b>Login</b><input type="text" data-agdfs="login" autocomplete="off" placeholder="${dfs ? "•••••• (set)" : "the email you sign in with"}" value="${agEsc(form.login || "")}"></label>
        <label><b>API password</b><input type="password" data-agdfs="password" autocomplete="off" placeholder="${dfs ? "•••••• (set)" : "from app.dataforseo.com → API access"}" value="${agEsc(form.password || "")}"></label>
        <div class="row"><button class="btn pri" type="button" data-ag="savedfs">Save</button>${dfs ? `<button class="btn" type="button" data-ag="cleardfs">Disconnect</button>` : ""}<span class="sp">${form.msg ? agEsc(form.msg) : ""}</span></div>
      </div></div></div>
    <h3 class="sec">Voyage · pages indexed by meaning</h3>
    <div class="ag-row"><div class="ri"><div class="rn">Voyage <span class="ag-status"><i class="dot ${voy ? "ok" : "warn"}"></i>${voy ? "connected" : "not connected"}</span></div>
      <div class="rd">Helps the agent find your own pages to link to. The free plan covers a whole site.</div>
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
  /* "Agent Marketplace", not "Agents" (owner, 2026-09-11: "name the tab agent marketplace for
     now"). The pane title and the rail label say the same thing, so a person never sees the tab
     called one name and the screen it opens called another. */
  TITLES.agents = ["Agent Marketplace", "agents that work in front of you"];
}

/* ── mount, draw, poll ─────────────────────────────────────────────────────── */
let agObs = null, agPollTimer = null, agTick = null, agToastTimer = null;

function agApi(path){ return apiGet(AG_API + path); }
function agPostApi(path, body){ return apiPost(AG_API + path, body || {}); }
/* The one DELETE in the panel. apiPost cannot do it (it hardcodes POST), and adding a method
   argument there would touch every caller in the app for the sake of this one route. */
async function agDelApi(path){
  const r = await fetch(API + AG_API + path, { method: "DELETE", headers: { "X-Sutra-Panel": panelToken() } });
  if (!r.ok){
    let msg = "";
    try { msg = (await r.json()).error || ""; } catch (e) {}
    throw new Error(msg || ("That did not work (" + r.status + ")"));
  }
  return r.json();
}

/* The sentence a person should read, without the debug tail. apiPost's _fail appends
   " (/api/... -> 400)" so a developer can tell a refused token from a broken server; that is
   the right call for a log and the wrong thing to put in front of somebody who just clicked an
   emoji. The status is still on err.status for anyone who needs it. */
function agWhy(e){
  const m = String((e && e.message) || e || "").trim();
  return m.replace(/\s*\([^()]*->\s*\d{3}\)\s*$/, "") || "That did not work.";
}

function agToast(msg){
  if (typeof document === "undefined") return;
  let t = document.getElementById("agToast");
  if (!t){ t = document.createElement("div"); t.id = "agToast"; t.className = "ag-toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("on");
  clearTimeout(agToastTimer); agToastTimer = setTimeout(() => t.classList.remove("on"), 2600);
}

function agRoot(){ return typeof document === "undefined" ? null : document.getElementById("agRoot"); }

/* Is there a personal access token sitting in the box right now? Read from the DOM, answered as
   a boolean, and the value itself is never returned, copied or stored -- this exists so agDraw
   can leave the field alone, which is the whole of how the token survives a poll. */
function agTokenTyped(){
  if (typeof document === "undefined") return false;
  const el = document.querySelector('[data-agws="token"]');
  return !!(el && el.value);
}

/* Take the token out of the box and hand it over exactly once. The caller sends it and lets it
   go; nothing else in this file ever sees it. Clearing the input first is what un-blocks the
   redraw above, and means a screenshot taken a second later has nothing on it. */
function agTakeToken(){
  if (typeof document === "undefined") return "";
  const el = document.querySelector('[data-agws="token"]');
  if (!el) return "";
  const v = el.value || "";
  el.value = "";
  return v;
}

function agEnsureObserver(){
  if (agObs || typeof MutationObserver === "undefined" || typeof document === "undefined") return;
  const target = document.getElementById("panes") || document.body;
  if (!target) return;
  agObs = new MutationObserver(() => agMountIfNeeded());
  agObs.observe(target, { childList: true, subtree: true });
  agMountIfNeeded();
}

/* The two shells this tab can hold. Painted once per mount, and again when `screen` changes;
   everything inside them is agDraw's, as it always was. */
const AG_SHELL_AGENT = `<aside class="ag-side" id="agSide" aria-label="SEO Writer"></aside>
      <section class="ag-main" id="agMain" aria-label="Conversation"><div id="agStages"></div><div class="ag-scroll" id="agScroll"></div><div class="ag-quiet" id="agQuiet" role="status" hidden></div><div class="pc" id="agComposer"></div></section>
      <aside class="ag-panel" id="agPanel" aria-label="Review"></aside>`;
const AG_SHELL_MARKET = `<div class="ag-mktwrap" id="agMarket" aria-label="Agent Marketplace"></div>`;

/* Paint the shell for the screen we are on, and load what that screen needs. One function, so
   mounting into a fresh pane and moving between the two screens take exactly the same path.
   `enter` asks for the one-shot arrival animation; the class is dropped again once it has run so
   a later redraw or remount does not replay it. */
function agEnterScreen(root, enter){
  const a = agS(); if (!a || !root) return;
  const market = a.screen !== "agent";
  root.innerHTML = market ? AG_SHELL_MARKET : AG_SHELL_AGENT;
  root.classList.toggle("ismarket", market);
  root.classList.remove("haspanel");
  root.classList.toggle("ag-enter", !!enter);
  if (enter && typeof setTimeout === "function")
    setTimeout(() => { const r = agRoot(); if (r) r.classList.remove("ag-enter"); }, AG_ENTER_MS);
  agDraw(true);
  if (market){
    /* nothing on the shelf moves on its own, so the shelf keeps no clock running */
    agStopPoll();
    if (a.screen === "choose") agCompaniesLoad(); else agMarketLoad();
  } else {
    agStartPoll();
    agBootLoad();
  }
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
    /* A remount is render() repainting the pane, not somebody arriving, so it never animates. */
    agEnterScreen(root, false);
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
  /* The marketplace is one block and has no columns, no panel and no composer, so it leaves
     before any of that machinery runs. */
  if (a.screen !== "agent"){ agSetHtml("agMarket", a.screen === "choose" ? agChooseHtml(a) : agMarketHtml(a)); return; }
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
    agDrawComposer(a, force);
  } else if (a.view === "guide"){
    /* THE GUIDE. One document in the same column the conversation uses, with the composer left
       exactly where it was and exactly as usable -- typing in it starts a new chat, which is
       the only way off this screen that anybody has to learn. Nothing here waits on a payload:
       the guide is drawn from the copy on the first frame and the two real slots fill in behind
       it when their routes answer. */
    agSetHtml("agStages", "");
    /* the guide and each of its five dives is a new document, so it starts at the top rather
       than wherever the last one was scrolled to */
    if (scroll && (a.lastView !== a.view || a.lastDive !== a.guideDive)) scroll.scrollTop = 0;
    agSetHtml("agScroll", agGuideHtml(a));
    agDrawComposer(a, force);
  } else {
    agSetHtml("agStages", "");
    /* a settings view is a new document: start it at the top, not where the chat was */
    if (scroll && a.lastView !== a.view) scroll.scrollTop = 0;
    /* A TAB YOU HAVE NEVER OPENED SAYS SO WHILE IT LOADS. Now that the tab paints before its
       fetch, a first visit would otherwise render the view's own empty state -- "No articles
       yet", "Nothing saved" -- for as long as the request takes, which is a lie that then
       flickers into the truth. Only a tab holding NOTHING shows this; a second visit keeps last
       time's rows on screen and refreshes them in place, with no flicker at all. */
    const held = { knowledge: a.knowledge, assets: a.assets, memory: a.memory, prompts: a.prompts,
                   library: a.library, tools: a.tools, connections: a.conns };
    const cold = a.viewBusy === a.view && (held[a.view] === null || held[a.view] === undefined);
    const html = cold ? agViewLoadingHtml(a.view)
      : a.view === "knowledge" ? agKnowledgeHtml(a.knowledge, a)
      : a.view === "assets" ? agAssetsHtml(a.assets, a)
      : a.view === "memory" ? agMemoryHtml(a.memory, a.memForm)
      : a.view === "prompts" ? agPromptsHtml(a.prompts, a)
      : a.view === "library" ? agLibraryHtml(a.library)
      : a.view === "tools" ? agToolsHtml(a.tools)
      : agConnectionsHtml(a.conns, a.health, a.connForm, a.ws, a.wsForm);
    const searching = document.activeElement && document.activeElement.matches && document.activeElement.matches("[data-agpageq]");
    const sel = searching ? document.activeElement.selectionStart : null;
    /* Every other field on this screen survives the four-second poll because the input handler
       keeps it on S.ag and the renderer prints it back. The personal access token may do
       neither, so the only way it can survive is for the poll not to touch it: while something
       is typed in that one box, this view holds still. Pressing Create clears the box first,
       so the redraw that follows is never blocked by it. */
    if (!agTokenTyped() && agSetHtml("agScroll", html) && searching){
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
  const quiet = document.getElementById("agQuiet");
  if (quiet){ const q = agQuietHtml(a); agSetHtml("agQuiet", q); quiet.hidden = !q; }
  if (anchor) agScrollRestore(document.getElementById("agScroll"), anchor);
  a.lastView = a.view; a.lastDive = a.guideDive;
}

/* The composer, drawn identically for the two views that have one: the conversation and the
   guide. It was inline in agDraw's chat branch and is a function now for one reason -- the box
   on the guide has to be the SAME box, with the same draft, the same caret handling and the
   same run state, rather than a second one that drifts from it. */
function agDrawComposer(a, force){
  const comp = document.getElementById("agComposer");
  if (!comp) return;
  const had = document.activeElement && comp.contains(document.activeElement);
  const before = had ? document.activeElement.selectionStart : null;
  if (agSetHtml("agComposer", agComposerHtml(a)) || force){
    const ta = comp.querySelector("[data-agask]");
    if (ta){ ta.value = a.draft || ""; agGrow(ta); if (had || a.focusComposer){ try { ta.focus({ preventScroll: true }); if (before != null) ta.setSelectionRange(before, before); else ta.setSelectionRange(ta.value.length, ta.value.length); } catch (e) {} a.focusComposer = false; } }
  }
  comp.hidden = false;
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
/* ── notifications ────────────────────────────────────────────────────────────────────────
   Owner asked for these on 2026-09-10: "let's say we checked on the update content and it is
   done, then a notification would happen saying it is done".

   THE ONE RULE: only tell somebody about a thing they are NOT watching. A notification for
   something happening on screen in front of you is noise, and noise is how people turn
   notifications off permanently -- after which the one that mattered never arrives either.
   So every notification here is gated on the window not having focus.

   WHAT QUALIFIES: a run that finished, failed, or is now waiting on an answer, and a catalogue
   refresh that finished. Never step-by-step progress: "Reading page 340 of 11,000" is exactly
   the kind of thing that makes a person switch them off.

   PERMISSION IS ASKED LATE, AND THAT IS DELIBERATE. macOS prompts the first time a page asks.
   Asking on launch, before the person has any idea what Sutra would tell them, reliably gets a
   "no" that is then hard to undo. Asking the first time something genuinely took a while means
   the request arrives with a visible reason attached. */
const AG_NOTIFY_MIN_MS = 20000;   /* under this it was not a wait, and a toast would have done */

/* Is there work whose ending is worth interrupting somebody for? Also decides whether a hidden
   window keeps polling, which is why it lives here and not inside the notifier. */
function agWatching(a){
  if (!a) return false;
  return !!(agLiveRun() || agRefreshLive(a.refresh) || agWsJobLive(a.ws)
            || (a.view === "library" && agLibWriting(a)));
}

function agNotifyReady(){
  return typeof Notification === "function" && typeof document !== "undefined";
}

/* Fire one, if this person can be told and is not already looking at it. */
function agNotify(key, title, body, onClick){
  if (!agNotifyReady()) return;
  const S_ = agS(); if (!S_) return;
  S_.notified = S_.notified || {};
  if (S_.notified[key]) return;             /* a poll must not fire the same news twice */
  S_.notified[key] = true;
  /* THE GATE. hasFocus() is the honest test in Electron: a window can be fully visible on a
     second monitor while the person works in another app, and document.hidden is false for
     exactly that case. */
  if (document.hasFocus && document.hasFocus()) return;
  const show = () => {
    try {
      const n = new Notification(title, { body: body || "", tag: key, silent: false });
      n.onclick = () => {
        try { window.focus(); } catch (e) {}
        if (typeof onClick === "function") onClick();
      };
    } catch (e) { /* a shell with no notification support is not an error worth showing */ }
  };
  if (Notification.permission === "granted") return show();
  if (Notification.permission === "denied") return;      /* asked once, told no; never nag */
  try { Notification.requestPermission().then(p => { if (p === "granted") show(); }); }
  catch (e) {}
}

/* Watch the runs between polls and speak only on a TRANSITION. Comparing against what was true
   last tick is what stops a run that has been waiting for an hour re-announcing itself every
   four seconds. */
function agNotifyPass(a){
  if (!a || !agNotifyReady()) return;
  a.runSeen = a.runSeen || {};
  const runs = (a.chat && a.chat.runs) || [];
  for (const r of runs){
    if (!r || !r.run_id) continue;
    const was = a.runSeen[r.run_id];
    a.runSeen[r.run_id] = r.status;
    if (was === undefined || was === r.status) continue;   /* first sight, or nothing moved */
    /* Only a run that actually took a while. A three-second run ending is not news. */
    const ms = (r.finished_at ? Date.parse(r.finished_at) : Date.now())
             - (r.started_at ? Date.parse(r.started_at) : Date.now());
    const worth = !isFinite(ms) || ms >= AG_NOTIFY_MIN_MS;
    const open = () => { a.view = "chat"; agLoadChat(a.chatId, true); };
    const topic = (r.topic || "").trim();
    if (r.status === "waiting")
      agNotify("w:" + r.run_id + ":" + (r.waiting_on && r.waiting_on.call_id || ""),
               "Sutra needs an answer",
               (r.waiting_on && r.waiting_on.question) || "It cannot carry on until you reply.", open);
    else if (r.status === "done" && worth)
      agNotify("d:" + r.run_id, "Your article is ready to read",
               topic ? topic : "The draft is written and saved to the Library.", open);
    else if ((r.status === "failed" || r.status === "error") && worth)
      agNotify("f:" + r.run_id, "Sutra stopped",
               r.error || (topic ? "The run on " + topic + " could not finish." : "The run could not finish."), open);
  }
  /* The catalogue refresh: the owner's own example, and the strongest case for a notification,
     because it takes minutes and you are meant to go and do something else. */
  const rf = a.refresh;
  if (rf && rf.finished_at && !agRefreshLive(rf)){
    const n = rf.counts || rf || {};
    const bits = [];
    if (n.new != null) bits.push(n.new + " new");
    if (n.gone != null) bits.push(n.gone + " gone");
    if (n.changed != null) bits.push(n.changed + " changed");
    agNotify("r:" + rf.finished_at, "Knowledge is up to date",
             bits.length ? bits.join(", ") : "The catalogue has been refreshed.",
             () => { a.view = "knowledge"; agDraw(true); });
  }
}

function agStartPoll(){
  if (agPollTimer) return;
  const tick = async () => {
    agPollTimer = null;
    if (!agRoot()){ return; }
    const a = agS();
    /* A HIDDEN WINDOW STILL POLLS WHILE SOMETHING IS RUNNING. It used to skip entirely, which
       was right when nothing depended on it: a minimised window has nothing to repaint. It is
       wrong now that a finished run has to raise a notification, because the whole point of
       that notification is that you are NOT looking -- and a poll that only runs while you
       watch would tell you the draft is ready at the moment you come back to find it. Idle and
       hidden still skips, so an app left open overnight costs nothing. */
    const hidden = typeof document !== "undefined" && document.hidden;
    if (!hidden || agWatching(a)){
      try { await agRefresh(); } catch (e) { a.error = String(e && e.message || e); }
    }
    try { agNotifyPass(a); } catch (e) { /* never let a notification break the poll */ }
    const live = agWatching(a);
    agPollTimer = setTimeout(tick, live ? AG_POLL_LIVE_MS : AG_POLL_IDLE_MS);
  };
  agPollTimer = setTimeout(tick, 400);
  /* the second-by-second repaint. A refresh counts as live here as well as a run: the card's
     "nothing new for 2m 10s" is only honest if it is redrawn while the gap grows. */
  if (!agTick) agTick = setInterval(() => {
    const a = agS();
    if (agRoot() && (agLiveRun() || agRefreshLive(a && a.refresh))) agDraw();
  }, 1000);
}
function agStopPoll(){
  if (agPollTimer){ clearTimeout(agPollTimer); agPollTimer = null; }
  if (agTick){ clearInterval(agTick); agTick = null; }
}

let agRefreshBusy = false, agRefreshN = 0;
async function agRefresh(){
  if (agRefreshBusy) return; agRefreshBusy = true;
  const a = agS();
  /* the shelf has no clock (agEnterScreen stops it), and a tick that arrives from a timer already
     in flight must not start pulling a chat's events behind it */
  if (a && a.screen !== "agent"){ agRefreshBusy = false; return; }
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
    /* The workspace, on three cadences and for three reasons: every tick while a job is running
       (a bar that updates every four seconds is not a bar), every tick on the Connections tab
       (who is in it, and what is happening right now), and every eighth tick everywhere else --
       which is only there so the quiet line can appear at the bottom of whatever screen he is
       on after he presses Update. */
    if (agWsJobLive(a.ws) || a.view === "connections" || agRefreshN % 8 === 3){
      /* check=1 is the screen saying "this tab is open, a round trip is worth it": the server
         then re-reads schema.verify rather than handing back what it last knew. Off the tab
         this poll only feeds the quiet line, and eleven probes for a footnote is a poor
         trade, so it asks for nothing. */
      const q = (a.view === "connections" && !agWsJobLive(a.ws)) ? "/workspace?check=1" : "/workspace";
      a.ws = await agApi(q).catch(() => a.ws);
    }
    /* The catalogue refresh, on two cadences and for the same reasons: every tick while it is
       running (a step line that moves once every four seconds is not a step line), and on the
       Knowledge tab, where its card lives, so a run he started before opening this screen is
       drawn as it stands rather than as nothing at all. */
    if (agRefreshLive(a.refresh) || a.view === "knowledge"){
      await agPollRefresh();
    }
  } finally { agRefreshBusy = false; }
  agDraw();
}

/* THE MARKETPLACE'S ONE LOAD. Three routes the agent screen already uses, and no fourth source:
     /health    → is there a model, is the site read, is the brand pack built, how many chats
     /library   → how many articles there are
     /knowledge → the company record the name comes from, and the catalogue's page count
   /health lands first and is drawn on its own, because it carries the state pill and it is the
   quickest of the three; the other two fill their facts in behind it. A route that fails leaves
   its fact off the card rather than putting a zero there, and says so once at the bottom. */
async function agMarketLoad(){
  const a = agS(); if (!a || a.marketBusy) return;
  a.marketBusy = true; a.marketErr = null;
  try {
    try { a.health = await agApi("/health"); }
    catch (e) { a.marketErr = String((e && e.message) || e); }
    agDraw();
    const [lib, kn] = await Promise.all([
      agApi("/library").catch(() => null),
      agApi("/knowledge").catch(() => null),
    ]);
    if (lib) a.library = lib;
    if (kn) a.knowledge = kn;
  } finally { a.marketBusy = false; }
  agDraw();
}

async function agBootLoad(){
  const a = agS();
  try { a.health = await agApi("/health"); } catch (e) {}
  try { a.chats = await agApi("/chats"); } catch (e) { a.chats = []; }
  /* THE LAST CHAT IS NOT RESTORED (owner, 2026-09-10). Booting used to open the most recent
     chat -- preferring a live one -- so opening the agent dropped you into a conversation. The
     chats are all still here, in the sidebar, and one click resumes any of them; the door just
     opens on the guide instead.

     A RUN IN FLIGHT. This is the case worth thinking about, because a run WAITING on an answer
     is blocked until somebody opens it. It still lands on the guide, deliberately: nothing is
     hidden that was not already only in the sidebar, and the row for that chat carries the live
     dot (.dot.run / .dot.wait) that agSideHtml has always drawn, so a run that needs you is
     marked in the one place every chat is listed. Auto-opening it would be the behaviour the
     owner asked to remove, and the old code was not a notification anyway -- on a machine with
     nothing live it silently opened the most recent chat, which is as likely to be the wrong
     one. The run does not stop, and one click is still all it takes to get back to it. */
  try { a.memory = await agApi("/memory"); } catch (e) {}
  try { a.ws = await agApi("/workspace"); } catch (e) {}
  /* the sidebar says how many prompts he has changed, so the payload is wanted before he opens the tab */
  try { a.prompts = await agApi("/prompts"); } catch (e) {}
  try { a.library = await agApi("/library"); } catch (e) {}
  try { a.knowledge = await agApi("/knowledge"); } catch (e) {}
  try { a.cta = await agApi("/knowledge/cta"); } catch (e) {}
  /* the guide says how many things the agent can do, and the number is the registry's -- so the
     payload is wanted before he opens the Tools tab, exactly as /prompts is above. A route that
     fails leaves a.tools null and the sentence is not drawn at all. */
  try { a.tools = await agApi("/tools"); } catch (e) {}
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

/* One prompt, opened in the review panel. It always fetches, so what he reads is what is on disk
   right now and not a copy the list happened to be holding: the list carries a line count, this
   carries the text a run would load. */
async function agOpenPrompt(name){
  const a = agS();
  a.panel = { run_id: null, name, view: "prompt", data: null, loading: true, error: null,
              title: "Prompt", subtitle: name, readOnly: false };
  a.promptEdit = null; a.fileEdit = null; a.libEdit = null;
  agDraw();
  try {
    const d = await agApi(`/prompts/one?name=${encodeURIComponent(name)}`);
    if (!a.panel || a.panel.name !== name) return;      /* he clicked something else meanwhile */
    a.panel.data = d; a.panel.title = d.title || name;
    a.panel.loading = false;   /* the subtitle is agPanelHtml's, so it follows a save and a reset */
  } catch (e) {
    if (a.panel && a.panel.name === name){
      a.panel.loading = false;
      a.panel.error = "Could not read this prompt: " + String((e && e.message) || e);
    }
  }
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


/* ── the catalogue refresh, started and then watched ────────────────────────────
   The same shape as the workspace job: a press starts work on the server and returns, and one
   poll reads what that work is doing. The card is drawn from the server's job and never from
   the click, because the click knows nothing except that it happened -- which is precisely how
   the old fixed spinner came to sit there through six minutes of firewall cooldowns. */

/* Start it, and take the server's first word on what it is doing. */
async function agRefreshStart(body, prefix){
  const a = agS();
  let started = null, why = "";
  try { started = await agPostApi("/knowledge/refresh", body || {}); }
  catch (e) { why = String(prefix || "") + String((e && e.message) || e); }
  if (started){
    a.refresh = started.job || null;
    agDraw();
    /* one read straight away, so the first line the engine says appears without waiting on the
       poll's next tick */
    await agPollRefresh();
    return;
  }
  /* The press was refused. If it was refused BECAUSE one is already running -- the server's own
     409 -- then that running job is the honest thing to draw, so it is asked for before the
     refusal is. Otherwise the POST never landed, there is no job for anything to poll, and the
     reason has to be said here: nothing else will ever clear the card. */
  await agPollRefresh();
  if (!agRefreshLive(a.refresh))
    a.refresh = { phase: "failed", local: true, steps: [], error: why };
  agDraw();
}

/* Put the card away. The server is asked to forget the finished job first -- it refuses while
   one is still running, which is the point -- so a reopened tab does not show last week's run. */
async function agRefreshClear(){
  const a = agS();
  try { await agPostApi("/knowledge/refresh/dismiss", {}); } catch (e) {}
  a.refresh = null;
  agDraw();
}

/* Read the job. A poll that fails changes nothing on screen: a dropped read is not news, and
   blanking the card on one would be its own little lie. */
async function agPollRefresh(){
  const a = agS();
  let j;
  try { j = await agApi("/knowledge/refresh"); }
  catch (e) {
    /* One dropped read is not news. Several in a row means this card is no longer being told
       anything, and a spinner that is not being fed is the bug all over again -- so the count
       and when contact was lost are kept, and the card says so itself. */
    const p = a.refreshPollErr;
    a.refreshPollErr = { n: (p ? p.n : 0) + 1, since: p ? p.since : Date.now() / 1000,
                         msg: String((e && e.message) || e) };
    return;
  }
  a.refreshPollErr = null;
  const job = j && j.job;
  if (!job){
    /* the server has forgotten it; keep only a failure that never reached the server at all */
    if (a.refresh && !a.refresh.local) a.refresh = null;
    return;
  }
  a.refresh = job;
  /* A refresh that WROTE has made the heading counts and the page table stale, so they are
     re-read once, on the tick that sees it finish. */
  const done = job.mode + ":" + (job.finished_at || 0);
  if (job.phase === "done" && job.mode === "apply" && a.refreshSeen !== done){
    a.refreshSeen = done;
    a.knowledge = await agApi("/knowledge").catch(() => a.knowledge);
    if (a.pages) await agLoadPages(0);
  }
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

/* One post, one re-read, one draw -- and the server's own sentence when it refuses. A refusal
   here is a wrong key or a link that will not parse, which the server answers with what is
   wrong and what to do about it; putting a status code on screen instead is the failure mode
   spec section 10 names by hand. */
async function agWsPost(path, body){
  const a = agS();
  try {
    await agPostApi(path, body);
  } catch (e) {
    const f = a.wsForm || {};
    f.msg = String((e && e.message) || e);   /* the server's sentence, never a status code */
    f.busy = false;
    a.wsForm = f;
    a.ws = await agApi("/workspace?check=1").catch(() => a.ws);
    agDraw(); return false;
  }
  a.ws = await agApi("/workspace?check=1").catch(() => a.ws);
  agDraw(); return true;
}

/* Put the section back to its resting state. The server is asked to forget the finished job
   first -- it refuses while one is still running, which is the point -- and then GET /workspace
   is read again rather than patched in memory, so what is drawn is what is true. */
async function agWsClear(){
  const a = agS();
  try { await agPostApi("/workspace/dismiss", {}); } catch (e) {}
  try { a.ws = await agApi("/workspace?check=1"); } catch (e) {}
  agDraw();
}

async function agAction(act, el){
  const a = agS(); if (!a) return;
  const arg = el.getAttribute("data-arg") || "";
  switch (act){
    /* ── the tab's own route: the shelf, and the door into an agent ─────────── */
    /* Opening an agent. The shell is swapped and agBootLoad started in the same breath, so the
       arrival animation runs over an agent that is already loading. Nothing here waits on it. */
    /* "openagent", NOT "open". Both the marketplace card and every artifact card used to send
       "open", and a switch takes the FIRST matching case: this one ran for artifacts too, saw an
       arg that was not "seo", and broke out doing nothing. Artifact cards had been dead since
       2.257.0 (2026-09-10). One action, one name. (2026-09-12) */
    case "openagent": {
      if (arg && arg !== "seo") break;      /* one agent; an unknown id opens nothing */
      /* WHICH COMPANY FIRST, when there is a choice to make (owner, 2026-09-11): more than one
         company, or one that has not been named yet -- a first run, where the name is the first
         thing asked. One named company goes straight in, exactly as before. */
      const hh = a.health || {};
      if ((hh.companies || 1) > 1 || (hh.company && hh.company.id && !hh.company.name)){
        a.screen = "choose"; a.coForm = null; a.coErr = null; a.panel = null;
        agEnterScreen(agRoot(), true);
        break;
      }
      /* THE DOOR OPENS ON THE GUIDE, always -- not on the last conversation and not on a
         half-finished run. agBootLoad no longer restores a chat; see the note there for what
         happens to a run that is in flight. */
      a.screen = "agent"; a.view = "guide"; a.guideDive = null; a.panel = null;
      agEnterScreen(agRoot(), true);
      break;
    }
    case "market": {
      a.screen = "market"; a.panel = null;
      agEnterScreen(agRoot(), true);
      break;
    }
    /* ── which company ── see agChooseHtml. The server refuses a switch while anything is still
       running for the company being left, and that refusal is shown here in its own words. */
    /* "cochoose", NOT "choose". The answer chips under a question have sent "choose" since the
       first build; this case was added above them on 2026-09-11 and swallowed every one of them,
       so answering a question -- "Skip this one" included -- threw the person out to the company
       screen. (owner, 2026-09-12: "whenever I am clicking on this question to skip, it takes me
       back to the which company") */
    case "cochoose": {
      a.screen = "choose"; a.coForm = null; a.coErr = null; a.panel = null;
      agEnterScreen(agRoot(), true);
      break;
    }
    case "cosw": {
      if (a.coBusy) break;
      if (a.companies && arg === a.companies.active){
        a.screen = "agent"; a.view = "guide"; a.guideDive = null; a.panel = null;
        agEnterScreen(agRoot(), true);
        break;
      }
      a.coBusy = true; a.coErr = null; agDraw(true);
      try { await agPostApi("/companies/switch", { id: arg }); }
      catch (e) { a.coBusy = false; a.coErr = agWhy(e); agDraw(true); break; }
      a.coBusy = false;
      agResetCompany(a);
      a.screen = "agent"; a.view = "guide";
      agEnterScreen(agRoot(), true);
      break;
    }
    case "coadd": a.coForm = { mode: "add" }; a.coErr = null; agDraw(true); agFocusCo(); break;
    case "cocancel": a.coForm = null; a.coErr = null; agDraw(true); break;
    case "coaddgo": case "conamego": {
      if (a.coBusy) break;
      const inp = typeof document !== "undefined" ? document.querySelector("[data-agconame]") : null;
      const name = inp ? inp.value.trim() : "";
      if (!name){ a.coErr = "Type the company's name."; agDraw(true); agFocusCo(); break; }
      a.coBusy = true; a.coErr = null; agDraw(true);
      try {
        if (act === "coaddgo") await agPostApi("/companies", { name });
        else await agPostApi("/companies/rename", { id: (a.companies && a.companies.active) || "c1", name });
      } catch (e) { a.coBusy = false; a.coErr = agWhy(e); agDraw(true); agFocusCo(); break; }
      a.coBusy = false;
      agResetCompany(a);
      a.screen = "agent"; a.view = "guide";
      agEnterScreen(agRoot(), true);
      break;
    }
    /* "I have read this" -- for this sitting only, and it claims nothing about setup */
    case "introskip": a.introSkip = true; agDraw(true); break;
    /* THE FIVE DEEP DIVES, in place. The dive replaces the guide in the SAME column (owner:
       "the same blank screen would change") -- it is not a modal and not a new pane, so there
       is no second surface to close and the composer never moves. An id the list does not have
       leaves the guide where it is rather than blanking the screen. */
    case "dive": {
      if (!agDive(arg)) break;
      a.view = "guide"; a.guideDive = arg; a.panel = null; agDraw(true); break;
    }
    case "guideback": a.view = "guide"; a.guideDive = null; agDraw(true); break;
    case "new": a.chatId = null; a.chat = null; a.panel = null; a.picked = null; a.view = "chat"; a.guideDive = null; a.draft = ""; a.focusComposer = true; agDraw(true); break;
    case "chat": a.view = "chat"; a.guideDive = null; await agLoadChat(arg, false); break;
    case "view": {
      /* THE TAB PAINTS FIRST, THE NETWORK COMES SECOND (owner, 2026-09-10: "there is some
         latency when going from one tab to the next one"). This used to await every fetch
         BEFORE its first agDraw, so a click sat on the old tab for as long as the server took
         and the app felt stuck. Now the new tab is on screen before a single request goes out;
         whatever it holds from last time shows immediately and the answer redraws over it.
         `viewBusy` is what lets a never-opened tab say "loading" instead of "nothing here". */
      a.view = arg; a.panel = null; a.guideDive = null;
      a.viewBusy = arg;
      agDraw(true);
      if (arg === "knowledge"){ a.knowledge = await agApi("/knowledge").catch(() => null); a.health = await agApi("/health").catch(() => a.health); if (a.view === arg){ a.viewBusy = null; agDraw(true); } await agLoadPages(0); a.cta = await agApi("/knowledge/cta").catch(() => a.cta); if (a.mapOn && !a.map){ a.map = await agApi("/knowledge/embedding-map").catch(() => null); } }
      if (arg === "assets") a.assets = await agApi("/assets").catch(() => null);
      if (arg === "memory") a.memory = await agApi("/memory").catch(() => null);
      if (arg === "prompts"){ a.prompts = await agApi("/prompts").catch(() => null); a.promptEdit = null; }
      if (arg === "library") a.library = await agApi("/library").catch(() => []);
      if (arg === "tools") a.tools = await agApi("/tools").catch(() => []);
      if (arg === "connections"){ a.conns = await agApi("/connections").catch(() => null); a.health = await agApi("/health").catch(() => a.health); a.ws = await agApi("/workspace?check=1").catch(() => a.ws); }
      /* A LATE ANSWER FOR A TAB YOU HAVE LEFT REDRAWS NOTHING. Click Library then Tools quickly
         and Library's response lands second; without this guard it would paint Library back
         over the tab you are actually looking at. */
      if (a.view !== arg) break;
      a.viewBusy = null;
      agDraw(true); break;
    }
    case "play": a.view = "chat"; a.guideDive = null; a.draft = el.getAttribute("data-text") || ""; a.focusComposer = true; agDraw(true); break;
    case "send": { const ta = document.querySelector("[data-agask]"); await agSend(ta ? ta.value : a.draft); break; }
    case "stop": { const live = agLiveRun(); if (!live) break;
      await agPostApi(`/runs/${encodeURIComponent(a.chatId)}/${encodeURIComponent(live.run_id)}/stop`, {}).catch(e => agToast(String(e.message || e)));
      await agLoadChat(a.chatId, true); break; }
    case "fold": a.collapsed[arg] = !a.collapsed[arg]; agDraw(); break;
    case "step": a.stepOpen[arg] = !a.stepOpen[arg]; agDraw(); break;
    case "chatmenu": a.chatMenu = arg || null; agDraw(); break;
    /* CLICKING A FACE. Somebody else's says who they are and when they were last here. Your
       own opens the picker, because the one face a person wants to change is theirs. */
    case "face": {
      const ws = a.ws || {};
      const meId = (ws.me && ws.me.member_id) || "";
      const row = (ws.members || []).find(m => m && m.member_id === arg);
      if (!row){ agToast("That person is no longer on the workspace."); break; }
      /* YOUR OWN FACE OPENS THE PICKER ONLY WHILE YOU HAVE NONE. Once picked it is yours for
         good (owner, 2026-09-11), so afterwards your face behaves like everybody else's and
         just says who you are. The server refuses a second pick too; this only keeps the UI
         from offering something that would be turned down. */
      if (arg && arg === meId && !String(row.emoji || "").trim()){
        a.facePick = a.facePick ? null : { loading: true, faces: [], names: {}, free: [] };
        agDraw();
        if (a.facePick){
          try { a.facePick = Object.assign({ loading: false }, await agApi("/workspace/faces")); }
          catch (e) { a.facePick = null; agToast("The face list could not be read."); }
          agDraw();
        }
        break;
      }
      const ago = agFaceAgo(row.last_seen_at);
      agToast((row.name || "Someone") + (ago < AG_FACE_HERE_MS ? " · here now"
              : isFinite(ago) ? " · last seen " + agAgo(row.last_seen_at) : ""));
      break;
    }
    case "facepick": {
      try { await agPostApi("/workspace/face", { emoji: arg }); }
      catch (e) { agToast(agWhy(e)); break; }
      a.facePick = null;
      a.ws = await agApi("/workspace").catch(() => a.ws);
      agDraw();
      agToast("That is you now.");
      break;
    }
    case "chatdel": {
      a.chatMenu = null;
      try { await agDelApi(`/chats/${encodeURIComponent(arg)}`); }
      catch (e) { agToast(String(e.message || e)); agDraw(); break; }
      /* If the open chat was the one deleted, land somewhere real rather than on a chat id
         that no longer resolves: the next chat down, or the empty state. */
      if (a.chatId === arg){
        a.chatId = null; a.chat = null; a.events = {}; a.cursors = {}; a.panel = null; a.draft = "";
      }
      a.chats = await agApi("/chats").catch(() => a.chats);
      if (!a.chatId && a.chats && a.chats.length) await agLoadChat(a.chats[0].id, true);
      else agDraw();
      agToast("Chat deleted. Anything it wrote is still in the Library.");
      break;
    }
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
    case "closepanel": a.panel = null; a.fileEdit = null; a.libEdit = null; a.promptEdit = null; agDraw(); break;
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
    /* A form opens IN the editor. "Open", read a blank template, hunt for Edit, then type is
       three steps in front of the one thing this file exists for. Same route and same save as
       brandfile -- only the state it lands in differs. */
    case "inputwrite": {
      await agOpenBrandFile(arg, false, el.getAttribute("data-label") || "");
      const d = a.panel && a.panel.data;
      if (a.panel && !a.panel.error){
        a.fileEdit = { text: d && typeof d.text === "string" ? d.text : "" };
        agDraw();
        if (typeof document !== "undefined")
          setTimeout(() => { const t = document.querySelector("[data-agfiletext]"); if (t) t.focus(); }, 0);
      }
      break;
    }
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

    /* ── keeping the catalogue current ────────────────────────────────────────
       These five were the silent failure twice over. First agAction had no arm for
       "refreshcheck", so the click reached `default: break` and nothing happened. Then, with
       the arm in, the button called the route and sat on ONE FIXED SENTENCE until the whole
       run came back: the owner watched "Asking the site for its current list…" for several
       minutes and could not tell working from hung (2026-09-10).

       So a press no longer waits for an answer. It STARTS the tool and returns; the card is
       drawn from the job the server keeps, which carries every line refresh_site says as it
       says it, and agRefresh polls it on the live cadence the same way it polls a workspace
       job. Nothing here writes a progress line: the engine's words are the only words.

       Two steps, never one. `preview: true` reads the site's current address list, reports
       the four piles and touches nothing; only refreshgo, which he has to press, writes.
       That split is the tool's own contract (refresh_site.run) and it is what keeps a
       stray click on a settings tab from re-reading a 12,000-page site. */
    case "refreshcheck": await agRefreshStart({ preview: true }, "Could not check the site: "); break;
    case "refreshgo": await agRefreshStart({}, "The refresh did not finish: "); break;
    /* What changed, in full. The preview holds its report on the finished job (nothing has been
       written yet); after a real refresh the engine has saved it as catalogue-changes.md, so
       that is read back rather than kept on the state. */
    case "refreshreport": {
      const text = (a.refresh && a.refresh.result && a.refresh.result.report) || "";
      if (!text) break;
      a.panel = { run_id: null, name: "catalogue-changes.md", view: "brand_file",
                  data: { text }, loading: false, error: null,
                  title: "What a refresh would change", subtitle: "nothing has been written yet",
                  readOnly: true };
      a.fileEdit = null; agDraw(); break;
    }
    case "refreshchanges": {
      a.panel = { run_id: null, name: "catalogue-changes.md", view: "brand_file", data: null,
                  loading: true, error: null, title: "What changed", subtitle: "catalogue-changes.md",
                  readOnly: true };
      a.fileEdit = null; agDraw();
      try { const d = await agApi("/knowledge/changes"); a.panel.data = { text: (d && d.text) || "" }; a.panel.loading = false; }
      catch (e) { a.panel.loading = false; a.panel.error = "Could not read the change report: " + (e && e.message || e); }
      agDraw(); break;
    }
    case "refreshcancel": await agRefreshClear(); break;
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
    /* prompts: open one in the panel, edit it, save it, or put it back to what shipped */
    case "promptopen": {
      /* clicking the one already open shuts it, the same as every other list on this screen */
      if (a.panel && a.panel.view === "prompt" && a.panel.name === arg){ a.panel = null; a.promptEdit = null; agDraw(true); break; }
      await agOpenPrompt(arg); break;
    }
    case "promptedit": {
      const d = a.panel && a.panel.data; if (!d) break;
      /* it opens holding what the prompt currently says, so he edits rather than starts from
         nothing; the draft lives on a.promptEdit the way the Library editor's does */
      a.promptEdit = { text: d.text || "", busy: false, msg: "" };
      agDraw();
      if (typeof document !== "undefined")
        setTimeout(() => { const t = document.querySelector("[data-agprompttext]"); if (t) t.focus(); }, 0);
      break;
    }
    case "promptcancel": a.promptEdit = null; agDraw(); break;
    case "promptsave": {
      const p3 = a.panel, ed = a.promptEdit; if (!p3 || !ed) break;
      const ta = typeof document !== "undefined" ? document.querySelector("[data-agprompttext]") : null;
      const text = ta ? ta.value : String(ed.text || "");
      a.promptEdit = { text, busy: true, msg: "" }; agDraw();
      try {
        p3.data = await agPostApi("/prompts/save", { name: p3.name, text });
        a.promptEdit = null;
        a.prompts = await agApi("/prompts").catch(() => a.prompts);
        agToast("Saved. The next article uses it.");
      } catch (e) {
        /* the refusal is a sentence written for him (a missing {{TOKEN}}, most likely), so it
           goes where he is looking, not into a toast that fades */
        a.promptEdit = { text, busy: false, msg: String((e && e.message) || e) };
      }
      agDraw(); break;
    }
    case "promptreset": {
      const p4 = a.panel; if (!p4) break;
      try {
        p4.data = await agPostApi("/prompts/reset", { name: p4.name });
        a.promptEdit = null;
        a.prompts = await agApi("/prompts").catch(() => a.prompts);
        agToast("Back to what shipped");
      } catch (e) { agToast("Could not reset: " + ((e && e.message) || e)); }
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

    /* ── the team workspace ───────────────────────────────────────────────────
       Nothing in here decides that a workspace exists. Every one of these arms either opens a
       box, or posts and then re-reads GET /workspace and draws whatever the server said. The
       server moves a job to `done` only after schema.verify() has seen every table, so "created"
       cannot be printed from a request that merely came back. */
    /* Every arm that changes what this section is showing empties the token box first, and
       throws the value away. agDraw holds the view still while there is something in that box
       (it is the one field it cannot re-render), so a Cancel pressed over a typed token would
       otherwise leave the form frozen on screen with nothing to explain it. */
    case "wscreate": agTakeToken(); a.wsForm = { mode: "create", url: "", key: "", name: "" }; agDraw(); break;
    case "wsjoin": agTakeToken(); a.wsForm = { mode: "join", link: "", name: "" }; agDraw(); break;
    case "wscancel": agTakeToken(); a.wsForm = null; await agWsClear(); break;
    /* Create. The token box may be empty and that is an ordinary thing: with no token the
       server hands back the setup script, which is a route rather than a refusal. The token,
       if there is one, comes out of the DOM here and goes nowhere else. */
    case "wsgo": {
      const f = a.wsForm || {};
      if (!String(f.url || "").trim() || !String(f.key || "").trim()){
        f.msg = "Both the project URL and the publishable key are needed."; a.wsForm = f; agDraw(); break;
      }
      const token = agTakeToken();
      f.busy = true; f.msg = ""; a.wsForm = f; agDraw();
      const body = { url: f.url, key: f.key, name: f.name };
      if (token) body.token = token;
      await agWsPost("/workspace/create", body);
      const g = a.wsForm; if (g) g.busy = false;
      agDraw(); break;
    }
    /* "I've run it", and the Check again on an unfinished workspace: the same question either
       way -- is it set up NOW -- and the same answer, schema.verify's. */
    case "wssqldone": {
      const f = a.wsForm || {};
      const ws = a.ws || {};
      f.busy = true; a.wsForm = f; agDraw();
      const w = ws.workspace || {};
      await agWsPost("/workspace/confirm", {
        url: f.url || w.url || "", key: f.key || "", name: f.name || w.name || "" });
      const g = a.wsForm; if (g) g.busy = false;
      agDraw(); break;
    }
    case "wsjoingo": {
      agTakeToken();
      const f = a.wsForm || {};
      if (!String(f.link || "").trim() || !String(f.name || "").trim()){
        f.msg = "Paste the link and type the name your team will see."; a.wsForm = f; agDraw(); break;
      }
      await agWsPost("/workspace/join", { link: f.link, name: f.name });
      break;
    }
    case "wsretry": {
      agTakeToken();
      const job = a.ws && a.ws.job;
      a.wsForm = Object.assign({ mode: job && job.kind === "join" ? "join" : "create" }, a.wsForm,
                               { busy: false, msg: "" });
      await agWsClear(); break;
    }
    case "wscopylink": {
      const link = (a.ws && a.ws.link) || "";
      if (!link){ agToast("There is no link yet"); break; }
      try { await navigator.clipboard.writeText(link); agToast("Link copied. Send it to the team."); }
      catch (e) { agToast("Could not copy"); }
      break;
    }
    case "wscopysql": {
      const pv = a.ws && a.ws.job && a.ws.job.paste;
      if (!pv || !pv.sql){ agToast("There is nothing to copy"); break; }
      try { await navigator.clipboard.writeText(pv.sql); agToast("Script copied"); }
      catch (e) { agToast("Could not copy"); }
      break;
    }
    case "wsleave": {
      if (typeof confirm === "function" && !confirm("Leave the workspace? Your own Library, ideas and prompts stay exactly as they are on this Mac, and nothing is deleted from Supabase.")) break;
      try { await agPostApi("/workspace/leave", {}); a.wsForm = null; agToast("Left the workspace"); }
      catch (e) { agToast("Could not leave: " + (e && e.message || e)); }
      a.ws = await agApi("/workspace?check=1").catch(() => a.ws);
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
    else if (t.matches("[data-agprompttext]")){ if (a.promptEdit){ a.promptEdit.text = t.value; a.promptEdit.msg = ""; } }
    else if (t.matches("[data-agdfs]")){
      const f = a.connForm || {}; f[t.getAttribute("data-agdfs")] = t.value; f.msg = ""; a.connForm = f;
    }
    else if (t.matches("[data-agvoy]")){ const f = a.connForm || {}; f.voyage = t.value; f.vmsg = ""; a.connForm = f; }
    /* THE ONE FIELD THAT IS NEVER KEPT. Everything typed on this screen lands on S.ag so a
       redraw can print it back; the personal access token must not, so it is dropped here and
       lives only in the input until agTakeToken empties it. */
    else if (t.matches("[data-agws]")){
      const k = t.getAttribute("data-agws");
      if (k === "token") return;
      const f = a.wsForm || {}; f[k] = t.value; f.msg = ""; a.wsForm = f;
    }
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
