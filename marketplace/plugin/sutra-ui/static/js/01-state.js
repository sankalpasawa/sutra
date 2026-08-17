/* ══════════════════════ live data — fetched from the real backend ══════════════════════
   No seed. DOMAINS/CHARTERS/PLACEMENTS/INDEX are populated by loadOrg() from /api/org/*
   against placement_engine.py's real registry. Which registry is read is decided
   SERVER-SIDE by org_api.py's SUTRA_NATIVE_HOME
   resolution — never chosen here, and there is no fixture default.
   SESSIONS are not derived from any of this: they come from GET /api/sessions, which reads
   ~/.claude/projects/**.jsonl. See adoptRealSessions(). */
const API = "";                        // same-origin
let DOMAINS = [], CHARTERS = [], PLACEMENTS = [], INDEX = [];
/* Real slash commands, read from ~/.claude by GET /api/skills. Never a
   hardcoded list: the Skills screen used to render ten invented strings
   and claim "31 total". */
let SKILLS = [], SKILLS_META = {};
/* The live provider table (GET /api/providers) and the panel's settings
   (GET /api/settings). Both are fetched; neither is a literal in this file. */
let PROVIDERS = [], SETTINGS = null, PERM_MODES = [], MODELS = [];

/* True while a turn on this session is still streaming. The composer's send button
   becomes a STOP button on exactly this condition, so the control that appears is
   always the one that will act. */
/* ── liveness + progress helpers, shared by the watcher, the composer and the
   run strip ─────────────────────────────────────────────────────────────────
   sessionBusy() is the ONE predicate that answers "does this session own its
   turns array right now". The disk watcher, the list refresh and the folder
   editor all have to ask it before replacing state a socket is writing into.
   Declared with `function` so hoisting covers the callers above; CLAUDE_SOCKETS
   and chanKey are only dereferenced at call time, long after module eval. */
function sideStreamingFor(sid){
  return ((S.sideTurns || {})[sid] || []).some(t => t.streaming);
}
function sessionBusy(sid){
  if (streamingFor(sid) || sideStreamingFor(sid)) return true;
  const ch = CLAUDE_SOCKETS.get(chanKey(sid, false));
  return !!(ch && (ch.turn || (ch.pending && ch.pending.length)));
}
/* Elapsed, in the smallest honest unit. Never rounds a wedged turn down to 0. */
function fmtDur(ms){
  if (typeof ms !== "number" || !isFinite(ms) || ms < 0) return "";
  const s = Math.floor(ms / 1000);
  return s < 60    ? s + "s"
       : s < 3600   ? Math.floor(s/60) + "m " + (s%60) + "s"
                    : Math.floor(s/3600) + "h " + Math.floor((s%3600)/60) + "m";
}
/* ONE line of truth about a turn in flight. Every value here is measured:
   elapsed from the turn's own ts_ms, counts from toolRuns, characters from the
   accumulated response. Nothing is a percentage, because nothing on the wire
   reports a denominator -- the `done` frame is the first mention of duration or
   cost, so a proportional bar would be a fabrication. */
function runPhrase(t){
  const runs = (t && t.toolRuns) || [];
  const active = runs.filter(r => r.running);
  const parts = [];
  if (t && t.ts_ms) parts.push(fmtDur(Date.now() - t.ts_ms));
  if (active.length === 1){
    const r = active[0];
    parts.push((r.name || "tool") + (r.summary ? " · " + String(r.summary).slice(0, 60) : ""));
  } else if (active.length > 1){
    parts.push(active.length + " tools running");
  } else if (t && t.retrying){
    parts.push("rate limited — retrying");
  } else if (t && t.response){
    parts.push("writing");
  } else {
    parts.push(t && t.thinking ? "thinking" : "working");
  }
  if (runs.length) parts.push((runs.length - active.length) + "/" + runs.length + " tools");
  if (t && t.response) parts.push(t.response.length + " chars");
  return parts.filter(Boolean).join("  ·  ");
}
function streamingFor(sid){
  const s = S.sessions.find(x=>x.id===sid);
  return !!(s && (s.turns||[]).some(t=>t.streaming));
}
function fmtBytes(n){
  if (typeof n !== "number") return "";
  return n < 1024 ? n + " B"
       : n < 1024*1024 ? (n/1024).toFixed(0) + " KB"
       : (n/(1024*1024)).toFixed(1) + " MB";
}
const PLANS = [{ plan_id: "sutra-ui-draft", base: {} }];  // this tier manages exactly one draft
let META = { generated_ms: 0, history_complete_from_ms: 0 };

/* ══════════════════════ persisted UI state ══════════════════════
   What survives a reload are decisions the operator made about THIS machine,
   because re-making them every load is friction, not safety: which panes and
   sections are collapsed, and the browse-pane width.
   Nothing about the REGISTRY is cached here — only layout.
   A corrupt/absent value degrades to the default; it never throws. */
const LS_LAYOUT = "sutra.panel.layout";
const LS_TERM   = "sutra.panel.term";     /* terminal pane open/closed, per browser */
const LS_TERMW  = "sutra.panel.termw";    /* its dragged width, in px */
const LS_SIDETAB= "sutra.panel.sidetab";  /* terminal | preview */
const LS_PREVURL= "sutra.panel.prevurl";  /* last previewed loopback URL */
function lsGet(key, fallback){
  try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); }
  catch (e) { return fallback; }
}
function lsSet(key, value){
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
}
function loadLayout(){
  const raw = lsGet(LS_LAYOUT, null);
  const out = { paneCollapsed:{}, folds:{}, browseW:null, browseClosed:false,
                railCollapsed:false, railSections:{}, railTab:"home" };
  if (raw && typeof raw === "object"){
    if (raw.paneCollapsed && typeof raw.paneCollapsed === "object") out.paneCollapsed = raw.paneCollapsed;
    if (raw.folds && typeof raw.folds === "object") out.folds = raw.folds;
    if (typeof raw.railCollapsed === "boolean") out.railCollapsed = raw.railCollapsed;
    if (typeof raw.browseClosed === "boolean") out.browseClosed = raw.browseClosed;
    if (raw.railSections && typeof raw.railSections === "object") out.railSections = raw.railSections;
    if (raw.railTab === "home" || raw.railTab === "code") out.railTab = raw.railTab;
    if (typeof raw.browseW === "number" && raw.browseW > 120) out.browseW = raw.browseW;
  }
  return out;
}
function saveLayout(){ lsSet(LS_LAYOUT, S.ui); }
/* The ceiling a browse-pane width has to respect to leave the session pane
   visible. wireDivider()'s limit() enforces it DURING a drag; render() has to
   enforce the same bound when it restores a width from localStorage, because
   the window may be narrower now than it was when the width was stored.
   Below the 860px breakpoint the panes stack vertically and the width is
   overridden by CSS anyway, so the value is returned untouched there. */
/* Mirrors `.pane{flex:1 0 380px}`. flex-SHRINK is 0, so an open session pane
   cannot be squeezed below 380px -- reserving anything less than this (the
   divider used to reserve a flat 170) hands the browse pane width that the
   session pane then refuses to give up, and .panes overflows. */
const PANE_MIN = 380, PANE_MIN_COLLAPSED = 38, BROWSE_MIN = 240;

/* The widest the browse pane may be while every OTHER pane still fits.
   Measured from the live DOM rather than assumed, so it tracks how many
   session panes are open and whether any of them is collapsed. */
/* Border width of an element, in the units flex-basis is expressed in.
   .pane is border-box-less (1px border, content-box), so a `flex:0 0 380px`
   pane actually occupies 382. Reserving the basis alone leaves the container
   short by exactly the borders and .panes overflows by a few pixels -- close
   enough to look like a rendering artefact and stay unfixed. */
function _borderX(el){
  const o = el.offsetWidth, c = el.clientWidth;
  return (typeof o === "number" && typeof c === "number" && o > 0) ? (o - c) : 0;
}

function browseMax(){
  const panes = document.getElementById("panes");
  if (!panes) return Infinity;
  const avail = panes.getBoundingClientRect().width;
  if (!avail) return Infinity;
  const kids = panes.querySelectorAll(".pane:not(.browse), .pdiv");
  let reserved = 0, n = 0;
  for (let i = 0; i < kids.length; i++){
    const el = kids[i];
    n++;
    if (el.classList.contains("pdiv")) reserved += el.getBoundingClientRect().width || 9;
    else reserved += (el.classList.contains("collapsed")
                       ? PANE_MIN_COLLAPSED : PANE_MIN) + _borderX(el);
  }
  const gap = (typeof getComputedStyle === "function")
    ? (parseFloat(getComputedStyle(panes).gap) || 0) : 11;
  const browse = panes.querySelector(".pane.browse");
  /* the ceiling is a flex-BASIS, so it too has to leave room for its own border */
  const own = browse ? _borderX(browse) : 0;
  return Math.max(BROWSE_MIN, Math.floor(avail - reserved - gap * n - own));
}

function clampBrowseW(w){
  if (typeof w !== "number" || !(w > 0)) return w;
  /* The stacking breakpoint keys on the VIEWPORT (@media max-width:860px), not
     on the panes container -- at a 980px window the container is only ~660px
     wide, so testing the container would skip the clamp in exactly the case
     that needs it. Below the breakpoint the panes stack and .pane's width is
     `auto !important`, so the stored value is left alone. */
  const vw = (typeof window !== "undefined" && window.innerWidth) || 0;
  if (vw && vw <= 860) return w;
  const max = browseMax();
  return (max === Infinity) ? w : Math.min(w, max);
}
const CONFIDENCE_FLOOR = 0.45;         // mirrors placement_engine.py:67
const DAY = 86400000;
let NOW = Date.now();
const DEPTH_BAND = 4, STALE_MS = 180*DAY, AGING_MS = 90*DAY, PROJECT_IDLE_MS = 30*DAY;

/* A 400 from /api/providers/active or /api/settings carries the SPECIFIC reason
   the write was refused ("binary 'codex' not on PATH…"). Throwing only the
   status code discarded exactly the sentence the operator needs, so read the
   body's `detail` when there is one. */
async function _fail(r, path){
  let detail = "";
  try { const j = await r.json(); detail = (j && (j.detail || j.message)) || ""; } catch (e) {}
  if (detail && typeof detail !== "string") { try { detail = JSON.stringify(detail); } catch (e) { detail = ""; } }
  return new Error(detail ? (detail + " (" + path + " -> " + r.status + ")")
                          : (path + " -> " + r.status));
}
async function apiGet(path){
  const r = await fetch(API + path);
  if (!r.ok) throw await _fail(r, path);
  return r.json();
}
async function apiPost(path, body){
  const r = await fetch(API + path, { method:"POST",
    headers:{"Content-Type":"application/json"}, body: JSON.stringify(body||{}) });
  if (!r.ok) throw await _fail(r, path);
  return r.json();
}
/* Tenancy is removed: one registry holds one org, so registry reads carry no
   scope. What stood here built a ?tenant= the server already ignored -- a query
   string that looks like a scope but is not one is what made a half-removed
   filter hard to see. */

/* ══════════════════════ derivations/* ══════════════════════ derivations ══════════════════════ */
const byRef = r => DOMAINS.find(d => d.ref === r);
const st = d => d.status || "active";
const isLive = d => st(d) !== "retired";
/* live_refs(): drops retired only. frozen stays classifiable. */
const live = () => DOMAINS.filter(isLive);

function isDescendant(ref, ancestorRef){
  let n = byRef(ref);
  while (n && n.parent_ref){ if (n.parent_ref === ancestorRef) return true; n = byRef(n.parent_ref); }
  return false;
}
/* domain_path() computes over the UNFILTERED map — retired siblings keep their ordinal
   permanently (§2.1). Passing a filtered list here is the bug the doc names. */
function dPath(ref, all){
  all = all || DOMAINS;
  const chain = []; let n = all.find(d=>d.ref===ref);
  while (n){ chain.unshift(n); n = n.parent_ref ? all.find(d=>d.ref===n.parent_ref) : null; }
  let out = "D0";
  for (let i=1;i<chain.length;i++){
    const sibs = all.filter(d=>d.parent_ref===chain[i-1].ref)
                    .sort((a,b)=>a.ts_minted_ms-b.ts_minted_ms);
    out = (i===1?"D":out+".") + (sibs.findIndex(s=>s.ref===chain[i].ref)+1);
  }
  return out;
}
const chartersOf = ref => CHARTERS.filter(c=>c.domain_ref===ref);
const placementsOf = ref => PLACEMENTS.filter(p=>p.domain_ref===ref);
/* Derived from edges at CALL time, never from status -- and never precomputed.
   The old `new Set(CHARTERS.map(...))` ran at script-parse time, when CHARTERS
   was still the empty array declared at the top of this file. loadOrg() REPLACES
   that array minutes later, so the set stayed permanently empty and the
   "superseded" pill could never render -- not on the Charters table, not in the
   Departments inspector, not in the charter preview's Superseded row. */
const isSuperseded = c => !!c && CHARTERS.some(x => x.supersedes === c.id);
/* §4.6 freshness derived at render from max(placement.ts_ms) — never stored. */
function lastRouted(cid){
  const ts = PLACEMENTS.filter(p=>p.charter_id===cid).map(p=>p.ts_ms);
  return ts.length ? Math.max(...ts) : null;
}
function band(ms){
  if (ms === null) return {k:"never", cls:"p-mut", txt:"never routed"};
  const age = NOW - ms;
  if (age > STALE_MS) return {k:"stale", cls:"p-block", txt:"stale " + Math.round(age/DAY) + "d"};
  if (age > AGING_MS) return {k:"aging", cls:"p-warn", txt:"aging " + Math.round(age/DAY) + "d"};
  return {k:"fresh", cls:"p-ok", txt:"fresh " + Math.round(age/DAY) + "d"};
}
/* Function words only — articles, prepositions, conjunctions, pronouns, auxiliaries.
   Content verbs ("draft", "fix", "review") are NOT stripped: they carry routing signal.
   Without this, "the"/"for" inflate the denominator and drag a clear match under the floor. */
const STOP = new Set(("a an the this that these those and or but if then so of to in on at by for "+
  "from with about into over under is are was were be been being do does did have has had "+
  "i we you it they my our your their me us them can could should would will shall may might "+
  "please need want just").split(" "));
const tok = s => new Set((String(s||"").toLowerCase().match(/[a-z0-9]+/g) || [])
                          .filter(w => w.length>1 && !STOP.has(w)));
function jac(a,b){ const i=[...a].filter(x=>b.has(x)).length; const u=new Set([...a,...b]).size;
                   return u? i/u : 0; }
/* An undated row is a fact about THAT row, not a reason to blank the screen.
   Two real domain_updated events in this registry carry no ts_ms at all, and
   `new Date(undefined).toISOString()` throws -- which took the whole History
   screen down with a RangeError instead of showing 65 dated events and 2
   undated ones. Unrepresentable in, em-dash out. */
const fmt = ms => {
  const d = new Date(ms);
  return isNaN(d.getTime()) ? "—" : d.toISOString().slice(0,10);
};

/* ══════════════════════ simulate() — real backend, memoized on ops ══════════════════════
   The ORG-001/002/.../020 predicates now live server-side in reorg_sim.py, calling the SAME
   functions the CLI's own validation would (mece_report/lint_full/classify, not a JS
   reimplementation). This is a SYNCHRONOUS cache reader backed by an async fetch, so the rest
   of render() stays synchronous: first call for a given ops[] kicks off the real POST and
   returns a "pending" placeholder; render() gets called again once it resolves. Ring painting
   during drag stays fully client-side (blockCodesForMove below) — that is the per-hover
   budget §8.5.9 specifies; simulate() is the full validation pass, run on drop/edit, not on
   every pixel of mouse movement. */
/* The key must cover everything the ANSWER depends on. ops alone did not:
   ORG-010 fires purely from the base the server compares against the file, so
   two different bases share findings under an ops-only key. */
function simKey(ops){
  return JSON.stringify({ ops: ops || [], base: (S.draft && S.draft.base) || null });
}
/* pending:true means NOTHING IS KNOWN YET. Every consumer must render that as
   "checking…"/"—", never as 0 — a fabricated all-clear is the one answer this
   screen must never give. */
function emptySim(){
  return { domains2: DOMAINS.slice(), findings: [], maxDepth: 0, pending: true, error: null };
}
/* A cache key cannot express "the registry moved underneath us": ops and base
   are byte-identical before and after a composer turn writes a placement, yet
   the findings are not. Every registry mutation drops the cache and bumps the
   generation; a response from a superseded generation is discarded rather than
   cached, or it would immediately re-poison the cache it was cleared from. */
function invalidateSim(){
  S.simCache = {};
  S.simPending = new Set();
  S.simGen++;
}
/* Read once, in one place: a metric that came out of a pending or failed
   simulation renders as an em-dash. Never 0 for unknown. */
const simNum = (sim, v) => (sim.pending || sim.error) ? "—" : v;
function simulate(ops){
  ops = ops || [];
  const key = simKey(ops);
  if (S.simCache[key]) return S.simCache[key];
  if (!S.simPending.has(key)){
    S.simPending.add(key);
    const gen = S.simGen;
    /* now_ms: the client's clock, so the server's ORG-009/ORG-020 staleness
       bands and this page's freshness pills measure from ONE instant. */
    apiPost("/api/org/simulate", { ops, base: S.draft && S.draft.base, now_ms: NOW })
      .then(sim => {
        if (gen !== S.simGen) return;   /* the registry moved; this answer is stale */
        // server returns domains2 as a {ref: domain} dict; client code calls
        // array methods (.filter) on it, so normalize to an array here, once.
        S.simCache[key] = { domains2: Object.values(sim.domains2), findings: sim.findings,
                             maxDepth: sim.max_depth, notChecked: sim.not_checked,
                             pending: false, error: null };
        S.simPending.delete(key);
        render();
      })
      .catch(err => {
        S.simPending.delete(key);
        if (gen !== S.simGen) return;
        /* CACHE the failure. Dropping the in-flight guard and caching nothing
           meant the very next render() re-issued the same doomed POST — an
           unbounded retry storm — behind a Health screen showing "Nothing
           flagged" in green, an all-clear the server never sent. */
        S.simCache[key] = { domains2: DOMAINS.slice(), findings: [], maxDepth: 0,
                             notChecked: null, pending: false,
                             /* the raw reason; every consumer already frames it
                                with its own "Validation could not run." heading */
                             error: err.message || "the simulate request failed" };
        console.error("simulate() failed:", err);
        render();
      });
  }
  return emptySim();
}

/* ring codes for a MOVE/* ring codes for a MOVE — reads the in-memory domains array only. That is the
   per-hover budget, and why ORG-001/002/004/009 are not ring codes. */
function blockCodesForMove(src, t){
  const c = [];
  if (t.ref===src.ref || isDescendant(t.ref, src.ref))
    c.push({code:"ORG-006", subject:t.name+" is inside "+src.name});
  if (st(t) !== "active") c.push({code:"ORG-016", subject:t.name+" is "+st(t)});
  const norm = s => s.trim().toLowerCase().replace(/\s+/g," ");
  if (DOMAINS.some(d=>d.ref!==src.ref && d.parent_ref===t.ref && st(d)!=="retired" && norm(d.name)===norm(src.name)))
    c.push({code:"ORG-018", subject:'a live sibling is already named "'+src.name+'"'});
  return c;
}

/* codes that cannot be evaluated — never 0, never passed, never a green tick */
const NOT_CHECKED = [
  ["ORG-005","authority.ceilings has no writer (0 occurrences). Ph4."],
  ["ORG-011","no applied plan exists; revert has no target. Apply is CLI-only (§5.1)."],
  ["ORG-012","origin='unrouted' has no writer (0 occurrences). Floor-held shown separately — a different signal."],
  ["ORG-013","filesystem marker, not observable from a browser. Markers >24h downgrade to warn."],
  ["ORG-014","Workflow.domain_ref unpopulated. Ph4."],
  ["ORG-019","last_routed_ms has no writer (0 occurrences). Freshness derived at render instead."]
];

/* ══════════════════════ classify — the entry point's engine ══════════════════════
   Real POST /api/classify against the actual engine (org_api.py: gather_evidence + classify()
   [NEVER resolve()] + a pick_charter walk + exactly one write_placement() call). No client-side
   scoring reimplementation — the confidence numbers here ARE the real engine's numbers. */
async function runTurn(text, ts){
  const stamp = ts || Date.now();
  let r;
  try {
    const res = await apiPost("/api/classify", { text });
    if (!res.domain_ref) {
      // mode "none": classify() found no candidate at all; nothing was written.
      r = { mode: res.mode || "none", domain: null, confidence: res.confidence || 0,
            matched: [], blocked: res.blocked, text, ts_ms: stamp };
    } else {
      const domain = byRef(res.domain_ref) || { ref: res.domain_ref, name: res.domain_name };
      r = { mode: res.mode, domain, confidence: res.confidence,
            matched: res.matched_terms || [], charter: res.charter, text, ts_ms: stamp };
      if (res.placement) {
        // mode is derived read-side by /api/org/placements too; match that here so a
        // freshly-classified row renders identically to one fetched from the list endpoint.
        const p = { ...res.placement, mode: res.mode === "floor" ? "floor" : "match" };
        PLACEMENTS.unshift(p);
        r.placement = p;
        /* the registry just changed: ORG-004/ORG-009/ORG-020 all read
           placements, and the cache is keyed on ops+base, neither of which
           moved. Without this, findings are frozen at their pre-turn values
           for the rest of the session. */
        invalidateSim();
      }
      if (res.blocked) r.blocked = res.blocked;  // e.g. no charter reachable — still shows the route
    }
  } catch (e) {
    r = { mode: "none", domain: null, confidence: 0, matched: [],
          blocked: "request failed — " + e.message, text, ts_ms: stamp };
  }
  return r;
}
let SID = 0;
/* Start a session, or append a turn to an existing one. Appending is what makes the routing
   path visible: turn 2 can resolve somewhere turn 1 did not. */
async function runTask(text, sessionId){
  const r = await runTurn(text);
  let s = sessionId && S.sessions.find(x=>x.id===sessionId);
  if (!s){
    s = { id:"s-"+(++SID), title:text.length>46?text.slice(0,46)+"…":text,
          created_ms: r.ts_ms, turns:[], local:true, loadState:"live" };
    S.sessions.unshift(s);
    if (!S.openPanes.includes(s.id)) S.openPanes.push(s.id);
    if (S.openPanes.length>2) S.openPanes = S.openPanes.slice(-2);
  }
  s.turns.push(r);
  s.updated_ms = r.ts_ms;
  return { session:s, result:r };
}
/* ══════════════════════ sessions — the REAL ones ══════════════════════
   seedSessions() used to live here. It grouped PLACEMENT rows by the first path
   segment of work_ref and presented each group as a session titled
   "Scratchpad — 3 turns", stamped seeded:true. No such session ever existed:
   the titles were manufactured from file paths and the "turns" were placement
   records replayed as if they were a conversation. It is deleted, not repaired.

   The real source already existed and is what runs now:
     GET /api/sessions          -> session_reader.list_sessions(), which reads
                                   ~/.claude/projects/<encoded-cwd>/<id>.jsonl
     GET /api/sessions/{id}     -> the parsed transcript for one of them

   The list endpoint returns {id, title, project, cwd, branch, mtime, size}. It
   deliberately does NOT return a turn count — it reads only the head of each
   file. So the rail shows the fields that exist and says "transcript unread"
   for the one that does not, rather than printing a number nobody counted. The
   count appears once the pane is opened and the transcript is actually read. */
function adoptRealSessions(rows){
  /* Sessions started IN the panel are held in memory only (they are live
     websocket threads, not files yet), so a refresh of the list must not drop
     them. Everything else is replaced wholesale by what is on disk. */
  const local = S.sessions.filter(s => s.local);
  /* PRESERVE work in flight. Rebuilding a real session empties `turns`, resets
     loadState to "unread", drops `channel` and orphans the socket's turn object
     mid-stream. Any unseen transcript anywhere under ~/.claude/projects triggers
     this path, so a `claude` started in the terminal pane used to kill the pane
     you were reading. */
  const busy = new Map(S.sessions.filter(s => s.real && sessionBusy(s.id)).map(s => [s.id, s]));
  /* A session started HERE already owns its transcript id (set from the server's
     `session` frame), so the on-disk row for it is the SAME conversation, not a
     second one. Without this the rail grows a twin: one live in-memory row and
     one read-only-looking copy of the same thread. */
  const owned = new Set(local.map(s => s.claude_session).filter(Boolean));
  const real = (rows || []).filter(r => !owned.has(r.id)).map(r => busy.get(r.id) || ({
    id: r.id,
    title: r.title || "(no prompt)",
    real: true, local: false,
    project: r.project || "", cwd: r.cwd || "", branch: r.branch || "",
    /* mtime is seconds since epoch; the rail's date buckets are in ms. This is
       the file's last write — genuinely "updated", not a fabricated "created". */
    created_ms: (r.mtime || 0) * 1000, updated_ms: (r.mtime || 0) * 1000,
    size: r.size || 0,
    turns: [], loadState: "unread", loadError: null,
    /* the jsonl filename IS the Claude session id, so continuing this session
       from the composer resumes the real thread rather than starting a cold one */
    claude_session: r.id
  }));
  S.sessions = local.concat(real)
    .sort((a,b)=>(b.updated_ms||b.created_ms)-(a.updated_ms||a.created_ms));
}

/* Fold a transcript's message list into the panel's turn shape.
   A turn is one user prompt plus everything the assistant said before the next
   prompt. These turns carry NO domain/charter/confidence, because none was ever
   computed for them: they ran in the terminal, before and outside this panel.
   Leaving those fields null is the point — the pane renders "not routed through
   the panel" rather than inventing a placement to fill the slot. */
function transcriptTurns(messages){
  const out = [];
  (messages || []).forEach(m => {
    const ts = m.ts ? Date.parse(m.ts) : 0;
    if (m.role === "user"){
      out.push({ text: m.text || "", ts_ms: ts || 0, transcript: true,
                 domain: null, mode: "transcript", confidence: 0, matched: [],
                 response: "", tools: [] });
      return;
    }
    let cur = out[out.length - 1];
    if (!cur){
      /* an assistant block before any recorded prompt — say so, do not invent
         a prompt for it */
      cur = { text: "", orphan: true, ts_ms: ts || 0, transcript: true,
              domain: null, mode: "transcript", confidence: 0, matched: [],
              response: "", tools: [] };
      out.push(cur);
    }
    if (m.text) cur.response = cur.response ? (cur.response + "\n\n" + m.text) : m.text;
    if (m.tools && m.tools.length) cur.tools = (cur.tools || []).concat(m.tools);
    if (!cur.ts_ms) cur.ts_ms = ts || 0;
  });
  return out;
}

/* Read one transcript, once, on demand. Opening a pane is the trigger; the list
   endpoint never reads message bodies. Every terminal state is explicit so the
   pane can say which one it is in — "empty" and "error" are different facts and
   neither is "0 turns". */
function ensureTranscript(s){
  if (!s || !s.real || s.loadState !== "unread") return;
  s.loadState = "loading";
  apiGet("/api/sessions/" + encodeURIComponent(s.id))
    .then(d => {
      s.turns = transcriptTurns(d && d.messages);
      s.cwd = (d && d.cwd) || s.cwd;
      s.branch = (d && d.branch) || s.branch;
      s.loadState = s.turns.length ? "ok" : "empty";
      render();
    })
    .catch(e => { s.loadState = "error"; s.loadError = e.message; render(); });
}

/* ══════════════════════ the execution channel — where the studio stops being a viewer ══════
   Until now a turn was classified, a placement was written, the charter was shown — and then
   nothing ran. This is the missing half: one WebSocket to /ws/chat per STUDIO SESSION, opened
   lazily on the first send and reused, so the server's `--resume` threads every turn of that
   session into one Claude conversation.

   The sockets live in a module-level Map, deliberately NOT on S: S is JSON-serialized into the
   draft (saveDraft), and a WebSocket is neither serializable nor meaningful to persist. The
   Claude session id IS stored on the session object (a plain string) so reopening a closed pane
   can resume the same thread. */
const CLAUDE_SOCKETS = new Map();

/* Re-rendering on every token would rebuild the whole pane tree per character and fight the
   focus/caret restoration in render() — the composer would thrash while the operator types.
   Tokens accumulate on the turn; the DOM catches up ~10x/sec. */
let _renderTimer = null;
function scheduleRender(){
  if (_renderTimer) return;
  _renderTimer = setTimeout(()=>{ _renderTimer = null; render(); }, 100);
}

/* ── streaming: patch, do not rebuild ───────────────────────────────────────
   Tokens used to call scheduleRender(), and render() replaces #panes WHOLESALE
   via innerHTML. Ten times a second, for the whole reply, the entire transcript
   was destroyed and re-parsed. That produced all three reported symptoms at
   once, and they were one bug:

     flicker     every node in the pane was replaced between frames
     scroll jump the new scroller starts at scrollTop 0, then code re-pins it,
                 so the view snapped bottom -> top -> bottom per frame
     not smooth  100ms batching is 10fps, and re-parsing a long transcript
                 costs more than the frame budget once a reply gets long

   So a token frame no longer re-renders anything. It rewrites the innerHTML of
   the ONE element that changed -- the streaming turn's [data-resp] node -- on
   an animation frame. The scroller is never replaced, so the scroll position is
   preserved by construction rather than saved and restored.

   Structural changes (a turn starting or finishing, a tool row appearing, an
   error) still go through render(): those change the shape of the pane, and
   patching text cannot express them. */
let _patchRaf = null;
const _patchDirty = new Set();

/* ── the one-second run ticker ───────────────────────────────────────────────
   Repaint in this file is purely frame-driven: scheduleStreamPatch() fires on a
   server frame and rewrites only [data-resp]. So any elapsed value would FREEZE
   between frames -- a turn stalled 90s inside one slow tool would show whatever
   number was current when the last frame landed, which is indistinguishable from
   a hang. This writes TEXT ONLY, into [data-runstrip], so it can never fight the
   caret patchStreaming() writes nor the scroll pin. It clears itself the first
   tick after the last turn finishes, so an idle app runs no timer. */
let _runTicker = null;
function tickRunStrips(){
  const live = _streamingTurns();
  if (!live.size){ clearInterval(_runTicker); _runTicker = null; return; }
  live.forEach((t, uid)=>{
    const el = document.querySelector('[data-runstrip="' + uid + '"]');
    if (el) el.textContent = runPhrase(t);
  });
}
function ensureRunTicker(){
  if (_runTicker || typeof setInterval === "undefined") return;
  if (!_streamingTurns().size) return;
  _runTicker = setInterval(()=>{ try { tickRunStrips(); } catch (e) {} }, 1000);
}

function scheduleStreamPatch(uid){
  if (uid) _patchDirty.add(uid);
  if (_patchRaf) return;
  _patchRaf = requestAnimationFrame(()=>{ _patchRaf = null; patchStreaming(); });
}

/* Every turn currently streaming, by uid, across main and side channels. */
function _streamingTurns(){
  const out = new Map();
  S.sessions.forEach(s => (s.turns || []).forEach(t => {
    if (t.streaming && t.uid) out.set(t.uid, t);
  }));
  Object.keys(S.sideTurns || {}).forEach(sid =>
    (S.sideTurns[sid] || []).forEach(t => { if (t.streaming && t.uid) out.set(t.uid, t); }));
  return out;
}

/* Replace ONE assistant block. A running turn changes its state pill, its tool
   rows and its body many times -- a turn with six tool calls used to mean six
   full render() passes, each swapping every node in the pane. Scroll survives
   that now, but the repaint does not: it is the visible flicker in "the tabs
   are very patchy". Swapping one <div> leaves the rail, the pane header, the
   tabs and the composer untouched, so nothing outside the message can flash. */
function patchTurn(t){
  if (!t || !t.uid) return false;
  const el = document.querySelector('[data-aturn="' + t.uid + '"]');
  if (!el) return false;                    /* not drawn yet -> caller renders */
  const pane = el.closest(".pane[data-sess]");
  const pb = pane && pane.querySelector(".pb");
  const sid = pane && pane.dataset.sess;
  const pinned = pb && !S.userScrolled.get(sid);
  el.outerHTML = turnResponse(t);
  if (pinned){
    pb.__pinning = true;
    pb.scrollTop = pb.scrollHeight;
    requestAnimationFrame(()=>{ pb.__pinning = false; });
  }
  return true;
}

function patchStreaming(){
  const live = _streamingTurns();
  let missed = false;
  _patchDirty.forEach(uid=>{
    const t = live.get(uid);
    if (!t) return;                       /* finished; render() already owns it */
    const el = document.querySelector('[data-resp="' + uid + '"]');
    if (!el){
      /* No anchor yet -- the first token of a reply that has not been drawn
         with a body element. That IS a structural change, so fall back once. */
      missed = true;
      return;
    }
    const pane = el.closest(".pane");
    const pb = pane && pane.querySelector(".pb");
    const sid = pane && pane.dataset.sess;
    const pin = pb && !S.userScrolled.get(sid);
    el.innerHTML = mdHtml(t.response) +
      '<span class="caret" style="color:var(--acc)">█</span>';
    /* Only follow the tail when the operator has not scrolled away. __pinning
       marks it as OUR scroll so the listener does not read it as intent. */
    if (pin){
      pb.__pinning = true;
      pb.scrollTop = pb.scrollHeight;
      requestAnimationFrame(()=>{ pb.__pinning = false; });
    }
  });
  _patchDirty.clear();
  if (missed) scheduleRender();
}

/* ── grounding injection ──
   THIS is the point of Sutra. What reaches Claude is never the raw utterance: it is the
   utterance under the placement the engine just resolved, mirroring what
   marketplace/plugin/hooks/placement-resolve.sh injects per turn in the real product. A weak
   route (mode "floor") says so, and an unresolved route says THAT, rather than quietly sending
   a bare prompt and letting the UI imply a grounding that never happened. */
function groundingPrefix(t){
  const L = [];
  const conf = (t && typeof t.confidence === "number") ? t.confidence.toFixed(2) : "0.00";
  if (t && t.domain){
    const ct = t.charter && t.charter.title ? t.charter.title : "";
    L.push('PLACEMENT: ' + dPath(t.domain.ref) + ' ' + (t.domain.name || "") +
           (ct ? ' | "' + ct + '"' : ' | (no charter reachable from this department)'));
    if (t.charter && t.charter.purpose) L.push('CHARTER PURPOSE: ' + t.charter.purpose);
    L.push('(confidence ' + conf + ', mode ' + (t.mode === "floor" ? "floor" : "match") + ')');
    if (t.mode === "floor")
      L.push('Held at ancestor -- no department claims this. The routing is weak, not ' +
             'authoritative: treat the placement as provisional and say so if this work ' +
             'plainly belongs somewhere else.');
    if (t.blocked) L.push('Routing note: ' + t.blocked);
  } else {
    L.push('PLACEMENT: unresolved -- no department could be resolved for this turn.');
    L.push('(confidence ' + conf + ', mode ' + ((t && t.mode) || "none") + ')');
    if (t && t.blocked) L.push('Reason: ' + t.blocked);
    L.push('Do not invent an address. Proceed, and name the gap if it matters.');
  }
  return L.join("\n") + "\n\n";
}

/* The directory THIS session runs in. S.cwd[sid] is a per-session override; with none
   set the answer is the global setting, which is what every session used before this
   control existed. Returning the effective value (never null) means callers never have
   to re-derive the fallback and cannot disagree about it. */
/* THE SESSION'S OWN DIRECTORY WINS OVER THE GLOBAL SETTING.
   Claude files a conversation under ~/.claude/projects/<encoded-cwd>/<id>.jsonl,
   so `claude --resume <id>` can only find it when the process runs in THAT
   directory. This used to answer with SETTINGS.workdir for every session, and
   the result was silent and awful: resuming a transcript that belonged to
   ~/Desktop/development/sutra was attempted from ~/sutra-ui-workspace, claude
   could not find the id, and started a BRAND NEW conversation instead --
   which is why a reply typed in Sutra opened a new thread and never appeared
   in Claude. Measured on a real session: session cwd
   /Users/tchandrakar/Desktop/development/sutra vs sent
   /Users/tchandrakar/sutra-ui-workspace.

   Order is deliberate:
     1. an explicit per-session override -- the operator chose it on purpose
     2. the session's OWN recorded cwd -- where the conversation actually lives,
        and the only directory its id resolves in
     3. the global setting -- correct only for a NEW session, which has no
        history and therefore no directory of its own yet */
function sessCwd(sid){
  const over = S.cwd && S.cwd[sid];
  if (over) return String(over).trim();
  const s = (S.sessions || []).find(x => x.id === sid);
  if (s && s.cwd) return String(s.cwd).trim();
  return ((SETTINGS || {}).workdir || "").trim();
}
/* The cwd is fixed when the agent process spawns, so it can only be carried on the
   socket URL -- not sent as a later message. Changing it therefore has to drop the
   socket (see setSessCwd), or the label would claim a directory the running process
   is not in. */
function claudeWsUrl(sid){
  const base = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/chat";
  const cwd = sid ? sessCwd(sid) : "";
  return cwd ? base + "?cwd=" + encodeURIComponent(cwd) : base;
}
/* Point this session at a different folder.
   The running agent CANNOT be moved -- its cwd was set by the spawn -- so the open
   socket is closed rather than relabelled. The next message opens a new one in the
   new directory. Closing while a turn streams would throw away a reply the operator
   is waiting on, so that case is refused with a reason instead. */
function setSessCwd(sid, raw){
  const next = (raw || "").trim();
  const prev = sessCwd(sid);
  S.cwdEdit = null;
  if (next === prev){ scheduleRender(); return; }
  /* setSessCwd's cleanup closes BOTH sockets, so the guard must see both. It was
     blind to side turns while its message promised not to discard the reply. */
  if (streamingFor(sid) || sideStreamingFor(sid)){
    S.cwdError = "finish or stop the running turn first — moving folders now would "
               + "discard the reply it is still writing.";
    scheduleRender();
    return;
  }
  S.cwdError = null;
  /* Empty means "clear the override", i.e. fall back to the global setting -- not
     "run in the filesystem root". */
  if (next) S.cwd[sid] = next; else delete S.cwd[sid];
  /* The repository bar describes the OLD folder until this is dropped. Clearing
     it makes render() re-read; leaving it would name a repo this session is no
     longer in, which is the exact failure the per-session bar exists to avoid. */
  delete S.repo[sid]; delete S.prs[sid];
  if (S.prsOpen === sid) S.prsOpen = null;
  ["", "::side"].forEach(suffix=>{
    const ch = CLAUDE_SOCKETS.get(sid + suffix);
    if (!ch) return;
    try { ch.ws.close(); } catch (e) {}
    CLAUDE_SOCKETS.delete(sid + suffix);
  });
  scheduleRender();
}
/* Every turn this channel still owes a reply gets the REAL reason it will not arrive.
   Silence and a spinner that never stops are the failure modes this replaces. */
function failChannel(ch, detail, opts){
  const hit = ch.pending.splice(0);
  if (ch.turn) hit.push(ch.turn);
  ch.turn = null;
  hit.forEach(t=>{
    t.streaming = false;
    if (!t.error) t.error = ch.lastError || detail;
    /* INTERRUPTED is not the same as FAILED. The agent did not refuse and did
       not error -- the transport went away, usually because the server
       restarted. That is recoverable, and a turn that says so can offer a
       retry instead of leaving a red line the reader can only stare at. */
    if (opts && opts.interrupted && !ch.lastError) t.interrupted = true;
  });
  if (hit.length) scheduleRender();
}
/* A side chat gets its OWN socket under a synthetic key rather than the map being
   re-keyed. Restructuring CLAUDE_SOCKETS would touch every call site on the live
   chat path -- the one part of this app that already works -- to buy nothing the
   suffix does not. `side` is the only difference: a separate key, and (in askClaude)
   no resume, so the main thread is never continued or mutated. */
function chanKey(sid, side){ return side ? sid + "::side" : sid; }

function claudeChannel(s, side){
  const key = chanKey(s.id, side);
  let ch = CLAUDE_SOCKETS.get(key);
  if (ch && (ch.ws.readyState === WebSocket.CONNECTING || ch.ws.readyState === WebSocket.OPEN))
    return ch;
  const ws = new WebSocket(claudeWsUrl(s.id));
  ch = { ws:ws, sid:s.id, key:key, side:!!side, open:false, queue:[], pending:[],
         turn:null, last:null, lastError:null, cwd:sessCwd(s.id) };
  CLAUDE_SOCKETS.set(key, ch);
  ws.onopen = ()=>{ ch.open = true; ch.queue.splice(0).forEach(m=>ws.send(m)); };
  ws.onmessage = ev=>{
    let f; try { f = JSON.parse(ev.data); } catch (e) { return; }
    if (f.type === "start"){
      /* the server emits exactly one "start" per message, in order — that is the
         demarcation that binds the next token stream to the right queued turn */
      ch.turn = ch.pending.shift() || ch.turn;
      if (ch.turn){ ch.turn.streaming = true; ch.last = ch.turn; }
    } else if (f.type === "provider"){
      /* the server states, per connect, which binary it resolved and which
         permission mode it will run under -- including whether that mode
         writes files without asking. Dropping this frame meant the pane could
         not say what it was actually about to do. */
      s.channel = f;
      /* The server confines any agent cwd to $HOME and fell back to the default.
         Drop the override and SAY SO -- leaving it set would show a folder chip for
         a directory this session is demonstrably not running in. */
      if (f.cwd_refused){
        delete S.cwd[s.id];
        S.cwdError = "refused " + f.cwd_refused + " — the working directory must be "
                   + "inside your home folder. Running in " + (f.workdir || "the default") + ".";
        S.cwdEdit = s.id;
      } else if (S.cwd[s.id] && f.workdir){
        /* Show what the server RESOLVED (it expands ~ and follows symlinks), not what
           was typed -- they differ, and echoing the input would misreport the result. */
        S.cwd[s.id] = f.workdir;
      }
    } else if (f.type === "session"){
      /* A SIDE channel must never write s.claude_session: that field is what the main
         thread resumes from, and overwriting it with the branch's id would silently
         redirect every later main message into the side conversation -- the exact
         opposite of "the side discussion does not change the primary task".
         The id is still kept on the turn, so the side chat can resume ITSELF. */
      if (!ch.side) s.claude_session = f.id;
      else ch.sideSession = f.id;
      if (ch.turn) ch.turn.claude_session = f.id;
    } else if (f.type === "token"){
      if (ch.turn){
        ch.turn.response = (ch.turn.response || "") + f.text;
        /* Prose is arriving, so this is no longer the thinking phase. `thinking`
           was set by the server's thinking frame and cleared only on tool-start,
           done, stopped, retry and error -- never on a token. On an extended-
           thinking turn that calls no tool the state therefore read "thinking"
           for the entire time the answer was visibly being written. No forced
           repaint here: the run ticker rewrites the strip within a second. */
        ch.turn.thinking = false;
        /* TEXT ONLY -- patched in place, no re-render. See patchStreaming().
           Return early so the scheduleRender() at the end of this handler does
           not undo the whole point by rebuilding the pane anyway. */
        scheduleStreamPatch(turnUid(ch.turn));
        return;
      }
    } else if (f.type === "retrying"){
      /* A rate-limit backoff. Without this the pane went silent and a WAITING
         turn was indistinguishable from a WEDGED one. */
      if (ch.turn){ ch.turn.retrying = f.detail || "retrying"; }
    } else if (f.type === "sysinit"){
      /* What the session actually resolved, as opposed to what was requested --
         they differ whenever a fallback or a settings default applies. */
      ch.sysinit = f;
    } else if (f.type === "thinking"){
      /* Presence only -- the server does not forward the thinking text, so the UI
         says "thinking" and nothing more. */
      if (ch.turn) ch.turn.thinking = true;
    } else if (f.type === "tool"){
      if (ch.turn){
        /* Two parallel stores ON PURPOSE.
           `tools`    -- flat names, the shape the TRANSCRIPT reader produces and a
                         test pins. Left exactly as it was.
           `toolRuns` -- live lifecycle keyed by the server's tool_use id, which is
                         the only thing that can correlate a start with its end.
           Merging them would either break transcript rendering or invent a
           completion state for replayed turns that was never recorded. */
        const runs = (ch.turn.toolRuns = ch.turn.toolRuns || []);
        if (f.phase === "end"){
          /* Match by id. A result whose start was never seen is NOT invented as a
             finished tool -- it is dropped, because a row with no name is noise. */
          const r = f.id && runs.find(x=>x.id === f.id);
          if (r){ r.running = false; r.ok = f.ok !== false; r.endedAt = Date.now();
                  /* what the tool RETURNED -- the server used to discard it, so a
                     failing tool showed a red dot with no reason attached */
                  if (f.output) r.output = f.output; }
        } else {
          runs.push({ id:f.id, name:f.name || "tool", summary:f.summary || "",
                      /* Shell commands only, and only when the server sent one --
                         this is what the "terminal" control re-opens. */
                      command:f.command || "",
                      caller:f.caller || null, running:true, ok:null,
                      startedAt: Date.now() });
          ch.turn.thinking = false;      /* a tool call ends the thinking phase */
          (ch.turn.tools = ch.turn.tools || []).push(f.name || "tool");
        }
      }
    } else if (f.type === "done"){
      if (ch.turn){
        ch.turn.streaming = false;
        ch.turn.thinking = false;
        /* Server-measured, not client-timed: the wall clock here would include
           queueing and render latency that the operator did not pay for. */
        if (typeof f.duration_ms === "number") ch.turn.duration_ms = f.duration_ms;
        if (typeof f.cost_usd === "number") ch.turn.cost_usd = f.cost_usd;
        if (typeof f.num_turns === "number") ch.turn.num_turns = f.num_turns;
        /* A tool still marked running when the turn ends never reported a result.
           Mark it UNKNOWN rather than silently completing it. */
        (ch.turn.toolRuns || []).forEach(r=>{ if (r.running){ r.running = false; r.ok = null; } });
      }
      ch.turn = null;
      /* A completed turn is the ONLY moment utilization actually moved, which is
         why the chip refreshes here instead of on a clock. The 60s server cache
         absorbs a burst of quick turns, so this cannot become a request per turn. */
      loadUsage(true);
      /* The agent may have committed, branched or staged during that turn, so the
         bar's branch / ahead / diff numbers are stale the moment it ends. */
      loadRepo(ch.sid, true);
      if (S.prsOpen === ch.sid) loadPrs(ch.sid, true);
    } else if (f.type === "stopped"){
      /* The operator's own interrupt is NOT an error. It gets its own state so the
         turn is not painted red and blamed on the tool. */
      if (ch.turn){
        ch.turn.streaming = false; ch.turn.thinking = false; ch.turn.stopped = true;
        (ch.turn.toolRuns||[]).forEach(r=>{ if (r.running){ r.running = false; r.ok = null; } });
      }
      ch.turn = null;
    } else if (f.type === "retry"){
      /* The saved thread id was rejected, so the server is re-running THIS SAME
         message without it. Not an error and not a new turn: the turn already on
         screen stays exactly where it is and keeps streaming into the replay.
         All that changes is that the dead id is forgotten, and any tool runs from
         the aborted attempt are cleared so they do not appear twice. */
      if (f.resume_reset) s.claude_session = null;
      ch.lastError = null;
      if (ch.turn){
        ch.turn.toolRuns = [];
        ch.turn.response = "";        /* the accumulator the token frames append to */
        ch.turn.thinking = false;
        ch.turn.retried = f.detail || "restarted as a new thread";
      }
    } else if (f.type === "error"){
      ch.lastError = f.detail || "claude failed with no detail";
      /* the stored thread id was rejected -- forget it, or every following message
         re-sends the same dead id and the channel fails identically forever */
      if (f.resume_reset) s.claude_session = null;
      const t = ch.turn || ch.last;
      if (t){
        t.streaming = false; t.thinking = false; t.error = ch.lastError;
        /* Same rule as `done`: a tool that never reported is UNKNOWN, not failed.
           Marking it failed would attribute the turn's error to a specific tool
           that may well have succeeded before the failure happened elsewhere. */
        (t.toolRuns || []).forEach(r=>{ if (r.running){ r.running = false; r.ok = null; } });
        ch.turn = null;
      }
      else failChannel(ch, ch.lastError);   /* refused before any turn started */
    }
    /* MID-TURN frames change one assistant block and nothing else, so they
       patch that block instead of rebuilding the pane. Anything structural --
       a turn starting or finishing, a channel error, a session id arriving --
       still goes through render(), because those change the shape of the pane
       and a node swap cannot express them. patchTurn() returns false when the
       block is not on screen yet, and then we render as before. */
    const midTurn = (f.type === "tool" || f.type === "thinking" ||
                     f.type === "retrying");
    if (midTurn && ch.turn && patchTurn(ch.turn)) return;
    scheduleRender();
  };
  ws.onclose = ev=>{
    /* Delete by the channel's OWN key. Deleting by s.id would evict the MAIN
       channel when a side chat's socket closed. */
    if (CLAUDE_SOCKETS.get(key) === ch) CLAUDE_SOCKETS.delete(key);
    /* 1006 is an ABNORMAL close: no close frame, i.e. the server went away
       rather than saying goodbye. Restarting the backend does exactly this. */
    const abnormal = !ev || ev.code === 1006 || !ev.wasClean;
    failChannel(ch,
      abnormal ? "The connection to the agent dropped before the reply finished. "
               + "This happens when the backend restarts."
               : "The agent channel closed before the reply finished (code "
               + ev.code + ").",
      { interrupted: abnormal });
  };
  return ch;
}
/* A PANE IS A VIEW. THE SESSION IS THE WORK.
   This used to read "the pane IS the session's lifetime" and closed the socket
   on pane close, which killed a reply that was still arriving and wrote
   "pane closed before the reply finished" over it. Closing a window must never
   destroy work that is still running -- you close a tab in Claude Code and the
   conversation is still there when you come back.

   So: a channel with a turn IN FLIGHT SURVIVES the pane closing. Tokens keep
   landing on the turn object, which lives in S.sessions, not in the DOM -- so
   reopening the pane shows everything that arrived while it was shut, still
   streaming if it still is.

   An IDLE channel is still closed, because the original comment's worry is
   real: a socket with nothing in flight is a claude process kept alive for
   nothing. That is the only case where closing costs nothing. */
function closeClaudeChannel(sid, opts){
  const force = !!(opts && opts.force);
  const kept = [];
  [chanKey(sid, false), chanKey(sid, true)].forEach(key=>{
    const ch = CLAUDE_SOCKETS.get(key);
    if (!ch) return;
    const busy = !!ch.turn || (ch.pending && ch.pending.length);
    if (busy && !force){ kept.push(key); return; }   /* let the work finish */
    CLAUDE_SOCKETS.delete(key);
    /* No failChannel() here: nothing was in flight, so there is no turn to
       report a failure for. Reporting one was the message you were reading. */
    try { ch.ws.close(); } catch (e) {}
  });
  return kept;
}

