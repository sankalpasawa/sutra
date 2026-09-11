/* 16-shadow-home.js -- Focus > Shadow: the full view of the ONE thread
   (PLAN-100 S81-S90). Same S.shadowThread the overlay card renders; same
   server truth for missions, watches, memory. Renders honestly dark when
   the status endpoint answers non-200. */
"use strict";

/* one POST path for shadow surfaces: panel token attached, and a single
   retry after a token refresh -- the page outlives backend restarts. */
async function shadowPost(url, body){
  const go = () => fetch(url, { method: "POST",
    headers: { "content-type": "application/json",
      "X-Sutra-Panel": (typeof panelToken === "function" ? panelToken() : "") },
    body: JSON.stringify(body) });
  let r = await go();
  if (r.status === 403 && typeof refreshPanelToken === "function"
      && await refreshPanelToken()){
    r = await go();
  }
  return r;
}


/* attribute-context escaper (codex P2 fold): esc() is for text nodes;
   anything interpolated inside a quoted attribute goes through THIS, which
   also closes the quote-breakout vector. */
function escAttr(x){
  return String(x == null ? "" : x)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}


/* S83: ONE plane, two tabs, live counts. Pure. */
function shadowPlaneHtml(watching, missions, tab){
  const active = missions.filter(m =>
    ["running", "queued", "paused", "brief_confirm"].includes(m.state));
  const t = ["working", "goals"].includes(tab) ? tab : "watching";
  /* slice 7: a third tab is the smallest coherent entry to the goal list --
     Watching and Working keep their existing meaning and rendering. */
  const goals = (typeof S !== "undefined" && S.goals) || [];
  const liveGoals = goals.filter(g =>
    ["draft", "working", "verifying", "blocked"].includes(g.state));
  const head = `<div class="shtabs">
    <button class="btn shtab ${t === "watching" ? "on" : ""}" type="button"
      data-shtab="watching">Watching \u00b7 ${watching.length}</button>
    <button class="btn shtab ${t === "working" ? "on" : ""}" type="button"
      data-shtab="working">Working \u00b7 ${active.length}</button>
    <button class="btn shtab ${t === "goals" ? "on" : ""}" type="button"
      data-shtab="goals">Goals \u00b7 ${liveGoals.length}</button></div>`;
  if (t === "goals"){
    return head + `<div class="shplane">${
      typeof goalsListHtml === "function" ? goalsListHtml(goals)
        : `<div class="shempty">The goal list is unavailable.</div>`}</div>`;
  }
  if (t === "watching"){
    const rows = watching.map(sid => `
      <div class="shwatchrow" data-shwatch="${escAttr(sid)}">
        <span class="shobj">${esc(shadowChatLabel(sid))}</span>
        <button class="btn" type="button" data-shunwatch="${escAttr(sid)}">Stop watching</button>
      </div>`).join("");
    return head + `<div class="shplane">${rows ||
      `<div class="shempty">Shadow is not watching any session yet.</div>`}</div>`;
  }
  const foc = (typeof S !== "undefined" && S.shadowFocusMission) || null;
  const rows = active.map(m => `
    <div class="shmissionrow${m.id === foc ? " shfocused" : ""}" data-shmissionrow="${escAttr(m.id)}">
      ${missionCardHtml(m)}
      <span class="shrowacts">
        ${m.state === "queued" ? `<button class="btn" type="button"
            data-shact="start_now" data-shmid="${escAttr(m.id)}">Start now</button>
          <button class="btn" type="button" data-shact="drop"
            data-shmid="${escAttr(m.id)}">Drop</button>` : ""}
        ${m.state === "paused" ? `<button class="btn" type="button"
            data-shact="resume" data-shmid="${escAttr(m.id)}">Resume</button>` : ""}
        ${["running", "paused"].includes(m.state) ? `<button class="btn"
            type="button" data-shact="stop" data-shmid="${escAttr(m.id)}">Stop</button>` : ""}
      </span>
    </div>`).join("");
  const finished = missions.filter(m =>
    ["failed", "stopped"].includes(m.state)).slice(-5).reverse();
  const fin = finished.map(m => `
    <div class="shmissionrow shfinished${m.id === foc ? " shfocused" : ""}" data-shmissionrow="${escAttr(m.id)}">
      ${missionCardHtml(m)}
      <span class="shrowacts">
        <button class="btn" type="button" data-shact="retry"
          data-shmid="${escAttr(m.id)}">Retry</button>
        ${m.target_session ? `<button class="btn" type="button"
          data-shtakeover="${escAttr(m.target_session)}">Take over</button>` : ""}
      </span>
    </div>`).join("");
  return head + `<div class="shplane">${rows ||
    `<div class="shempty">No missions in flight.</div>`}${fin ? `
    <div class="shfinhead">Recent finished</div>` + fin : ""}</div>`;
}

/* S86/S87: the memory section. Unconfirmed rows are visibly inert; one tap
   confirms; revoke is the undo (archive-never-delete: revoked stays listed,
   struck through). */
function shadowMemoryHtml(rows){
  const items = (rows || []).map(r => {
    const dead = !!r.revoked_at;
    const inert = !r.confirmed && !dead;
    return `<div class="shmem ${dead ? "shmem-dead" : ""}" data-shmem="${escAttr(r.id)}">
      <span class="shprec">${esc(({ d_ledger: "ledger", session: "this session",
        project: "project", taste: "taste", history: "history",
        floor: "floor" })[r.precedence] || r.precedence || "")}</span>
      <span class="shmemtext">${esc(r.text || "")}</span>
      ${inert ? `<span class="shinert">unconfirmed \u00b7 inert</span>
        <button class="btn pri" type="button" data-shconfirm="${escAttr(r.id)}">Confirm</button>` : ""}
      ${r.confirmed && !dead ? `<button class="btn" type="button"
        data-shrevoke="${escAttr(r.id)}">Revoke</button>` : ""}
      ${dead ? `<span class="shinert">revoked</span>` : ""}
    </div>`;
  }).join("");
  return `<div class="shmemory">${items ||
    `<div class="shempty">Shadow has learned nothing yet. Confirmed
     instructions appear here.</div>`}</div>`;
}

/* v10: the tabs. One per chat Shadow oversees, plus "new" (key
   "global"). A tab is the ONE mind's conversation about that chat --
   never another agent. Namespace is data-shchat so the plane's
   data-shtab keeps its meaning (three QA probes depend on it). */
function shadowChatLabel(key){
  if (!key || key === "global") return "new";
  const S_ = (typeof S !== "undefined") ? S : {};
  /* the panel already loads every session with its title for the Chats
     rail — a tab is the same chat, so it wears the same name. No second
     source of truth, no extra fetch. */
  const row = (S_.sessions || []).find(x => x && x.id === key);
  const name = (row && (row.title || row.label || row.name)) || "";
  const clean = String(name).trim().replace(/\s+/g, " ");
  if (clean) return clean.length > 24 ? clean.slice(0, 23) + "\u2026" : clean;
  /* honest fallback: say it is a session, do not pretend it is a name. The
     Watching plane is an inventory of raw ids and WANTS this; the composer's
     chat picker is a menu and must never offer one (shadowChatKeys). */
  return "session " + String(key).slice(0, 6);
}
/* does the app itself list this id as one of its chats? The same scoped list
   the Chats rail renders (/api/sessions -> _owned_transcripts), which is also
   the only place a chat has a NAME. */
function shadowChatKnown(key){
  const S_ = (typeof S !== "undefined") ? S : {};
  return !!(key && key !== "global"
    && (S_.sessions || []).some(x => x && x.id === key));
}
function shadowChatKeys(){
  /* CANDIDATES FOR THE COMPOSER'S SCOPE CHIP -- polish pass after slice 11.
     This used to be built from S.shadowWatching, and that was the bug the
     founder saw: the watching store is a passive INVENTORY of raw session
     ids (470 of them, auto-watched), so the picker offered "session ds-own"
     and "session dead-0" -- ids the app does not list as chats and cannot
     even name. A menu is not an inventory.

     The pool is now the app's own scoped chat list (S.sessions, the same one
     the Chats rail renders), ordered by the app's own recency, with the chats
     Shadow is actually engaged in -- a live mission's target, a chat that has
     taught it a rule -- lifted to the front. Nothing is deleted and no store
     is touched: an id that is not an app chat is simply not offered. */
  const S_ = (typeof S !== "undefined") ? S : {};
  const known = new Map();
  for (const x of (S_.sessions || [])) if (x && x.id) known.set(x.id, x);
  const when = (k) => { const x = known.get(k);
    return (x && (x.updated_ms || x.created_ms)) || 0; };

  const live = (S_.shadowMissions || [])
    .filter(m => ["running", "queued", "paused"].includes(m.state))
    .map(m => m.target_session);
  const taught = (S_.shadowMemory || [])
    .filter(r => r.scope === "chat" && r.scope_id).map(r => r.scope_id);
  const engaged = [];
  const seen = {};
  for (const k of [...live, ...taught]){
    if (k && !seen[k] && known.has(k)){ seen[k] = 1; engaged.push(k); }
  }
  const rest = [...known.keys()]
    .filter(k => !seen[k])
    .sort((a, b) => when(b) - when(a));      /* newest chat first */
  return engaged.concat(rest);
}

/* ---- Shadow Home V2: The Briefing (slice 11) -----------------------------
   ONE vertical spine, not a dashboard and not a chat list. It answers four
   questions in order and then stops:

     greeting    does Shadow need me?          (state-derived, never a clock)
     Needs You   what is blocked?              (only when something is)
     Working     what is Shadow driving?
     Goals       what have I delegated?        (everything not above)
     foot        is the rest handled?          Watching · Conversations · Memory
     composer    delegation -- hero when calm, quiet when busy

   A goal appears in EXACTLY ONE band. Every band returns "" when it has
   nothing, so a calm day is a short page rather than a grid of empty tiles.
   All of it is built from the existing goal list plus the existing
   renderers; nothing new is fetched. */

function shadowGoalsBy(state){
  const S_ = (typeof S !== "undefined") ? S : {};
  return (S_.goals || []).filter(g => g && g.state === state);
}

/* the three counts the whole briefing is derived from */
function shadowBriefCounts(){
  const S_ = (typeof S !== "undefined") ? S : {};
  const all = S_.goals || [];
  const needs = all.filter(g => g.state === "blocked");
  const running = all.filter(g => ["working", "verifying"].includes(g.state));
  const rest = all.filter(g =>
    !["blocked", "working", "verifying"].includes(g.state));
  return { all, needs, running, rest };
}

const SH_WORDS = { 1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five" };
function shadowCount(n, noun){
  const word = SH_WORDS[n] || String(n);
  return word + " " + noun + (n === 1 ? "" : "s");
}

/* The two-second answer. Derived ONLY from goal state -- no clock, no
   invented counts. */
const SH_CALM = "Nothing needs you right now.";
function shadowGreeting(){
  const { all, needs, running, rest } = shadowBriefCounts();
  /* polish pass: was "Everything is handled." -- which claims Shadow FINISHED
     everything it oversees. It knows no such thing: this branch means only
     that no goal is blocked or running. Say exactly that. */
  if (!all.length) return SH_CALM;
  const parts = [];
  if (needs.length)
    parts.push(shadowCount(needs.length, "goal")
      + (needs.length === 1 ? " needs you." : " need you."));
  if (running.length)
    parts.push(shadowCount(running.length, "goal")
      + (running.length === 1 ? " is running." : " are running."));
  if (!parts.length) return SH_CALM;
  /* and only when there IS a remainder -- the same false-completion claim */
  if (rest.length) parts.push("Nothing else needs you.");
  return parts.join(" ");
}

/* --- NEEDS YOU: rendered only when something genuinely needs the founder */
function shadowNeedsYouHtml(){
  const { needs } = shadowBriefCounts();
  if (!needs.length) return "";
  return `<section class="shband shbandneeds">
    <div class="shbandhead shbandheadneeds">Needs you</div>
    ${needs.map(g => {
      const acts = (typeof goalActions === "function")
        ? goalActions("blocked", g) : [];
      const why = g.block_reason && typeof goalBlockerCopy === "function"
        ? goalBlockerCopy(g.block_reason) : g.block_reason;
      const meta = [g.checks_label,
                    g.attempt ? "attempt " + g.attempt : null]
        .filter(Boolean).join(" · ");
      return `<div class="shneed">
        <div class="shneedtitle" data-goalopen="${escAttr(g.id)}">${
          esc(g.outcome || "")}</div>
        ${why ? `<div class="shneedwhy">${esc(why)}</div>` : ""}
        ${meta ? `<div class="shneedmeta">${esc(meta)}</div>` : ""}
        ${acts.length ? `<div class="shneedacts">${acts.map(a => `
          <button class="btn ${a.pri ? "pri " : ""}" type="button"
            data-goalact="${escAttr(a.act)}"
            data-goalid="${escAttr(g.id)}">${esc(a.label)}</button>`)
          .join("")}</div>` : ""}
      </div>`;
    }).join("")}</section>`;
}

/* The activity line. ONLY the four permitted sources, in order; when none
   applies the line is omitted rather than filled in. */
function shadowActivityLine(g){
  if (!g) return "";
  const unmet = (g.unmet || [])[0] || null;
  if (g.state === "verifying")
    return unmet ? ("Waiting on your sign-off: " + unmet) : "";
  if (unmet) return "Waiting on: " + unmet;              /* waiting */
  if (!g.turns_used) return "Started";                   /* started */
  return "";                                             /* nothing honest */
}

/* --- WORKING: working + verifying, never blocked, never terminal */
function shadowWorkingHtml(){
  const { running } = shadowBriefCounts();
  if (!running.length) return "";
  return `<section class="shband">
    <div class="shbandhead">Working</div>
    ${running.map(g => {
      const line = [g.state, g.checks_label, g.turn_label]
        .filter(Boolean).join(" · ");
      const act = shadowActivityLine(g);
      return `<div class="shwork" data-goalopen="${escAttr(g.id)}">
        <div class="shworktitle">${esc(g.outcome || "")}</div>
        <div class="shworkline">${esc(line)}</div>
        ${act ? `<div class="shworkact">${esc(act)}</div>` : ""}
      </div>`;
    }).join("")}</section>`;
}

/* --- GOALS: the ledger. Everything NOT in the two bands above, so a goal
   is never listed twice. */
const SH_STATE_WORD = { draft: "Draft", queued: "Queued", paused: "Paused",
                        done: "Verified", stopped: "Stopped" };
const SH_HOME_GOAL_CAP = 8;

function shadowGoalsBandHtml(){
  const { rest } = shadowBriefCounts();
  if (!rest.length) return "";
  const shown = rest.slice(0, SH_HOME_GOAL_CAP);
  const hidden = rest.length - shown.length;
  return `<section class="shband">
    <div class="shbandhead">Goals</div>
    ${shown.map(g => `<div class="shgoal" data-goalopen="${escAttr(g.id)}">
      <span class="shgoaltitle">${esc(g.outcome || "")}</span>
      ${g.checks_label ? `<span class="shgoalprog">${
        esc(g.checks_label)}</span>` : ""}
      <span class="gwstate ${typeof goalStateClass === "function"
        ? goalStateClass(g.state) : ""}">${
        esc(SH_STATE_WORD[g.state] || g.state)}</span>
    </div>`).join("")}
    ${hidden > 0 ? `<button class="btn shgoalmore" type="button"
      data-shgoals="1">${hidden} more \u2014 open all goals</button>` : ""}
  </section>`;
}

/* --- FOOT: passive inventory, one line. No rows are rendered here. */
function shadowFootHtml(){
  const S_ = (typeof S !== "undefined") ? S : {};
  const watching = (S_.shadowWatching || []).length;
  const memory = (S_.shadowMemory || []).length;
  const open = !!S_.shadowMemOpen;
  return `<div class="shfoot">
    <button class="btn shfootitem" type="button" data-shwatching="1"
      >Watching \u00b7 ${watching}</button>
    <button class="btn shfootitem" type="button" data-shchats="1"
      >Conversations</button>
    <button class="btn shfootitem" type="button" data-shmemopen="1"
      >Memory \u00b7 ${memory}</button>
    <button class="btn shfootitem" type="button"
      data-shscreen="shadowsettings">Settings</button>
  </div>
  ${open ? `<div class="shfootopen">${
    shadowMemoryHtml(S_.shadowMemory || [])}</div>` : ""}`;
}

/* --- the composer. Its target chat is what a goal proposal binds to, so the
   scope lives beside it as ONE chip -- not the removed tab strip. */
function shadowScopeChipHtml(){
  const S_ = (typeof S !== "undefined") ? S : {};
  const active = S_.shadowChat && S_.shadowChat !== "global"
    ? S_.shadowChat : null;
  const keys = (typeof shadowChatKeys === "function") ? shadowChatKeys() : [];
  if (!active && !keys.length) return "";
  return `<div class="shscope">
    <span class="shscopelabel">for</span>
    <button class="btn shscopechip" type="button" data-shscopepick="1">${
      active ? esc(shadowChatLabel(active)) : "pick a chat"}</button>
    ${S_.shadowScopeOpen ? `<div class="shscopelist">${
      [`<button class="btn shscopeopt" type="button"
         data-shchat="global">no chat \u2014 just talk</button>`]
        .concat(keys.slice(0, 8).map(k => `<button class="btn shscopeopt${
          k === active ? " on" : ""}" type="button"
          data-shchat="${escAttr(k)}">${esc(shadowChatLabel(k))}</button>`))
        .join("")}</div>` : ""}
  </div>`;
}

function shadowComposerHtml(hero){
  return `<div class="shcompwrap${hero ? " shcomphero" : ""}">
    ${hero ? `<div class="shcomphint">Delegation is how work starts. Give
      Shadow an outcome and it drives one chat until that outcome is
      real.</div>` : ""}
    ${shadowScopeChipHtml()}
    <textarea class="shcompose" data-shhomecompose="1"
      data-shscope="${escAttr((typeof S !== "undefined" && S.shadowChat)
        || "global")}"
      placeholder="Tell Shadow what outcome you want\u2026"></textarea>
  </div>`;
}

/* the briefing spine */
function shadowHomeHtml(){
  const dark = typeof S === "undefined" || S.shadowHomeDark;
  if (dark) return `
  <div class="zero"><h4>Shadow</h4>
    <p>Shadow is not enabled. Turn it on in Settings to get a chief of
    staff watching your sessions.</p></div>`;
  /* the SAME thread the corner card renders -- a goal proposal (slice 8) or
     a mission card appears here, right where the founder just typed */
  const thread = (S.shadowThread || []).map(t => {
    if (t.goalProposal && typeof goalProposalHtml === "function")
      return goalProposalHtml(t.goalProposal);
    if (t.mission && typeof missionCardHtml === "function")
      return missionCardHtml(t.mission);
    return `
    <div class="shmsg ${t.who === "founder" ? "shmine" : "shshadow"}">
      ${esc(t.text || "")}</div>`;
  }).join("");
  const err = S.shadowHomeErr ? `<div class="sherr">Could not reach Shadow
    just now \u2014 showing what I last knew.
    <button class="btn" type="button" data-shreload="1">Retry</button></div>` : "";
  const needs = shadowNeedsYouHtml();
  const working = shadowWorkingHtml();
  const goals = shadowGoalsBandHtml();
  /* hero composer exactly when nothing is demanding attention */
  const calm = !needs && !working && !goals;
  /* a calm briefing is deliberately short; without this it clings to the top
     edge of a tall pane. Modest vertical centring -- no filler is added. */
  return `<div class="shbrief${calm ? " shcalm" : ""}">${err}
    <div class="shgreet">${esc(shadowGreeting())}</div>
    ${needs}${working}${goals}
    ${thread ? `<div class="shthread">${thread}</div>` : ""}
    ${shadowComposerHtml(calm)}
    ${shadowFootHtml()}
  </div>`;
}

async function loadShadowHome(){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  try {
    const st = await fetch("/api/shadow/status");
    if (!st.ok){ S.shadowHomeDark = true;
      if (typeof scheduleRender === "function") scheduleRender(); return; }
    S.shadowHomeDark = false;
    /* diagnosis fold 2026-08-26: a failed GET must NEVER masquerade as an
       empty list -- failure is its own rendered state with a Retry */
    /* goals ride the SAME parallel read the home already does -- the
       overview needs them, and a fourth request here is cheaper than a
       second load path (slice 10) */
    const [w, m, i, g] = await Promise.all([
      fetch("/api/shadow/watches").then(r => r.ok ? r.json() : null),
      fetch("/api/shadow/missions").then(r => r.ok ? r.json() : null),
      fetch("/api/shadow/instructions").then(r => r.ok ? r.json() : null),
      fetch("/api/shadow/goals").then(r => r.ok ? r.json() : null),
    ]);
    S.shadowHomeErr = !(w && m && i && g);
    if (g) S.goals = g.goals || [];
    if (w) S.shadowWatching = w.watches || [];
    if (m) S.shadowMissions = m.missions || [];
    if (i) S.shadowMemory = i.instructions || [];
    if (typeof scheduleRender === "function") scheduleRender();
  } catch (e){ S.shadowHomeDark = true;
    if (typeof scheduleRender === "function") scheduleRender(); }
}

async function loadShadowSettings(){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  try {
    const r = await fetch("/api/shadow/settings");
    S.shadowSettings = r.ok ? await r.json() : null;
  } catch (e){ S.shadowSettings = null; }
  if (typeof scheduleRender === "function") scheduleRender();
}

function shadowSettingsHtml(){
  const d = (typeof S !== "undefined" && S.shadowSettings) || null;
  if (!d) return `<div class="zero"><h4>Shadow settings</h4>
    <p>Could not read the rules just now.
    <button class="btn" type="button" data-shsetreload="1">Retry</button></p></div>`;
  const rows = [];
  rows.push(`<div class="setrow"><span class="k">How I engage</span><span>${
    (d.engage || []).map(esc).join(" \u00b7 ")}</span></div>`);
  rows.push(`<div class="setrow"><span class="k">Remember \u2014 everywhere</span><span>${
    (d.global || []).length
      ? (d.global || []).map(r => `${esc(r.text || "")}
          <button class="btn" type="button" data-shrevoke="${escAttr(r.id)}">Revoke</button>`).join("<br>")
      : "<span class='shempty'>nothing yet</span>"}</span></div>`);
  for (const key of Object.keys(d.per_chat || {})){
    rows.push(`<div class="setrow"><span class="k">Remember \u2014 ${
      esc(shadowChatLabel(key))}</span><span>${
      (d.per_chat[key] || []).map(r => `${esc(r.text || "")}
        <button class="btn" type="button" data-shrevoke="${escAttr(r.id)}">Revoke</button>`).join("<br>")
    }</span></div>`);
  }
  const a = d.attention || {};
  rows.push(`<div class="setrow"><span class="k">Attention</span><span>${
    (a.watching || []).length} overseen \u00b7 ${
    (a.off || []).length} off \u00b7 ${a.alerts || 0} waiting</span></div>`);
  rows.push(`<div class="setrow"><span class="k">Floors</span><span
    style="color:var(--faint)">${(d.floors || []).map(esc).join(" \u00b7 ")
    } \u2014 confirm-first, always (not editable)</span></div>`);
  return `<div class="shsettings"><div class="panelbox">${rows.join("")}</div></div>`;
}

if (typeof SCREENS !== "undefined"){
  SCREENS.shadowsettings = () => {
    if (typeof S !== "undefined" && S.shadowSettings === undefined){
      loadShadowSettings();
      return `<div class="zero"><h4>Shadow settings</h4><p>Reading\u2026</p></div>`;
    }
    return shadowSettingsHtml();
  };
}
if (typeof TITLES !== "undefined"){
  TITLES.shadowsettings = ["Shadow settings",
    "the rules it lives by \u00b7 what it remembers"];
}

/* The existing Watching experience, on its own screen so Home never renders
   session rows. Same shadowPlaneHtml the plane always used -- no new
   watching UI and no change to auto-watch semantics. */
if (typeof SCREENS !== "undefined"){
  SCREENS.shadowwatching = () => {
    const S_ = (typeof S !== "undefined") ? S : {};
    if (S_.shadowHomeDark) return `<div class="zero"><h4>Watching</h4>
      <p>Shadow is not enabled.</p></div>`;
    if (S_.shadowWatching === undefined){
      loadShadowHome();
      return `<div class="zero"><h4>Watching</h4><p>Looking\u2026</p></div>`;
    }
    return `<div class="shwatchscreen">${
      shadowPlaneHtml(S_.shadowWatching || [], S_.shadowMissions || [],
                      "watching")}</div>`;
  };
}
if (typeof TITLES !== "undefined"){
  TITLES.shadowwatching = ["Watching",
    "chats Shadow keeps an eye on \u00b7 passive"];
}

if (typeof SCREENS !== "undefined"){
  SCREENS.shadow = () => {
    if (typeof S !== "undefined" && S.shadowHomeDark === undefined){
      loadShadowHome();
      return `<div class="zero"><h4>Shadow</h4><p>Looking\u2026</p></div>`;
    }
    return shadowHomeHtml();
  };
}
if (typeof TITLES !== "undefined"){
  TITLES.shadow = ["Shadow",
    "your chief of staff \u00b7 one conversation, everywhere"];
}

/* The home controls act (they rendered un-wired before -- the recurring
   disease, now cured surface by surface). One delegated listener. */
if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("click", (ev) => {
    const d = (ev.target && ev.target.dataset) || {};
    if (d.shchat){
      if (typeof S !== "undefined"){
        S.shadowChat = d.shchat;
        S.shadowScopeOpen = false;        /* picking closes the picker */
      }
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    if (d.shscreen){
      if (typeof openScreen === "function") openScreen(d.shscreen);
      else if (typeof S !== "undefined") S.screen = d.shscreen;
      if (typeof loadShadowSettings === "function") loadShadowSettings();
      if (typeof render === "function") render();
      return;
    }
    if (d.shreload){
      if (typeof loadShadowHome === "function") loadShadowHome(); return; }
    /* slice 11 foot line. Watching opens the EXISTING plane on its own
       screen (no rows on Home); Conversations is the EXISTING chats
       destination; Memory reveals the EXISTING memory list inline. */
    if (d.shwatching){
      if (typeof S !== "undefined") S.shadowTab = "watching";
      if (typeof openScreen === "function") openScreen("shadowwatching");
      if (typeof render === "function") render();
      return;
    }
    if (d.shchats){
      if (typeof goDest === "function") goDest("chats");
      return;
    }
    if (d.shmemopen){
      if (typeof S !== "undefined") S.shadowMemOpen = !S.shadowMemOpen;
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    /* the composer's target chat: one chip, not the removed tab strip */
    if (d.shscopepick){
      if (typeof S !== "undefined") S.shadowScopeOpen = !S.shadowScopeOpen;
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    if (d.shgoals){
      if (typeof openScreen === "function") openScreen("goals");
      if (typeof render === "function") render();
      return;
    }
    if (d.shtab){ if (typeof S !== "undefined") S.shadowTab = d.shtab;
      /* lazy, like every other Shadow surface: the goal list is fetched
         when the tab is actually opened, and nothing polls */
      if (d.shtab === "goals" && typeof loadGoals === "function"
          && typeof S !== "undefined" && S.goals === undefined) loadGoals();
      if (typeof scheduleRender === "function") scheduleRender(); return; }
    if (d.shtakeover){
      /* navigation, never mutation: land the founder where the delegate
         session can be resumed by hand */
      if (typeof shadowRouteDeepLink === "function")
        shadowRouteDeepLink("sutra://session/" + d.shtakeover);
      else if (typeof goDest === "function") goDest("chats");
      return;
    }
    if (d.shact && d.shmid) return shadowMissionAct(d.shmid, d.shact);
    if (d.shstart) return shadowMissionAct(d.shstart, "start_now");
    if (d.shunwatch) return shadowWatchSet(d.shunwatch, false);
    if (d.shconfirm) return shadowInstructionAct(d.shconfirm, "confirm");
    if (d.shrevoke) return shadowInstructionAct(d.shrevoke, "revoke");
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && ev.target && ev.target.dataset
        && ev.target.dataset.shhomecompose){
      ev.preventDefault && ev.preventDefault();
      const text = ev.target.value; ev.target.value = "";
      if (text && text.trim() && typeof sendToShadow === "function"){
        sendToShadow(text.trim()).then(() => {
          if (typeof loadShadowHome === "function") loadShadowHome();
          if (typeof scheduleRender === "function") scheduleRender();
        });
        if (typeof scheduleRender === "function") scheduleRender();
      }
    }
  });
}

async function shadowWatchSet(sid, watch){
  if (typeof fetch === "undefined") return;
  try {
    /* the founder's dead-toggle fix: the BODY was the path string */
    const r = await shadowPost("/api/shadow/watches",
      { session_id: sid, watch: !!watch });
    if (r && typeof showNudge === "function")
      showNudge(!r.ok ? "The watch toggle did not stick \u2014 try again"
        : (watch ? "Watching." : "Stopped watching."));
  } catch (e) {}
  loadShadowHome();
}

async function shadowInstructionAct(id, action){
  if (typeof fetch === "undefined") return;
  try {
    /* same disease as the watch toggle: Confirm/Revoke never reached the API */
    const r = await shadowPost("/api/shadow/instructions", { id, action });
    if (r && typeof showNudge === "function")
      showNudge(!r.ok ? "That memory action did not stick \u2014 try again"
        : (action === "confirm"
            ? "Confirmed \u2014 Shadow applies it from its next boot."
            : "Revoked \u2014 kept in the list, struck through."));
  } catch (e) {}
  loadShadowHome();
}
