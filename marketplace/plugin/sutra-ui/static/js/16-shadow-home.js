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

/* ── the Shadow workspace (Focus › Shadow) ────────────────────────────────
   Two columns: what Shadow is working on, and the one task in focus.

   NOTHING HERE REPLACES AN EXISTING SURFACE. shadowPlaneHtml (the Watching
   screen's plane, with its own mission rows and action buttons) is untouched
   and still reachable; the left column below is a SELECTOR -- dot, name,
   pill -- because that is what the design asks a list to be, and because the
   actions belong to the task in focus, not to every row at once.

   The one genuinely new thing is + Delegate: an explicit "start a NEW task in
   a NEW chat" that sets target_mode server-side without the founder ever
   meeting the term, and without depending on Shadow's model output to infer
   the intent. */

/* mission state -> what the founder reads, and the dot/pill family. The
   engine's vocabulary is mission_engine.STATES; all nine are mapped, because
   a state with no label renders as a raw enum the first time it happens. */
const SH_TASK = {
  brief_confirm: { label: "READY",    cls: "ready"   },
  running:       { label: "RUNNING",  cls: "running" },
  queued:        { label: "QUEUED",   cls: ""        },
  paused:        { label: "PAUSED",   cls: ""        },
  blocked:       { label: "NEEDS YOU", cls: "blocked" },
  done:          { label: "DONE",     cls: "done"    },
  failed:        { label: "FAILED",   cls: "failed"  },
  stopped:       { label: "STOPPED",  cls: ""        },
  draft:         { label: "DRAFT",    cls: ""        },
};
function shadowTaskFace(state){
  return SH_TASK[String(state || "")] || { label: String(state || ""), cls: "" };
}

/* THE STATE IS NOT ALWAYS THE WHOLE FACE. `paused` is one word for two very
   different situations: the app restarted mid-flight (nothing is being asked
   of anyone), and Shadow finished and is WAITING ON THE FOUNDER to sign off
   the founder_confirm checks -- which is the same "it needs you" the engine
   spells `blocked` everywhere else. Reading PAUSED for the second one is what
   made a finished task look like a stalled one with nothing to do.

   shadowTaskFace(state) is untouched and still the state->face map; this is
   the MISSION-aware caller, and it is the only thing that knows the mission
   carries pause_reason. */
/* THE TWO PAUSES THAT ARE REQUESTS. Both mean "Shadow stopped because only
   the founder can carry this forward", and the engine already treats them as
   one class -- MissionEngine.pending_confirmations() lists exactly these two
   as the decisions awaiting an answer. The UI recognised only the first, so a
   mission paused on a FLOOR (a say that needs founder authority before it may
   leave the engine) read as a plain PAUSED: Shadow was waiting on the founder
   and the founder was told nothing was being asked.

   Anything else that pauses -- app_restart, founder_intervened, an ordinary
   stop -- is NOT a request and stays PAUSED. */
const SH_FOUNDER_PAUSES = ["founder_confirm", "floor_confirm"];
function shadowMissionNeedsFounder(m){
  return !!(m && m.state === "paused"
            && SH_FOUNDER_PAUSES.indexOf(m.pause_reason) !== -1);
}
function shadowTaskFaceFor(m){
  if (shadowMissionNeedsFounder(m)) return SH_TASK.blocked;
  /* the second state that is not the whole face: a start that has already
     been accepted. shadowMissionStarting() explains why brief_confirm alone
     stopped being enough; the label is the EXISTING queued one, because
     "admitted, not running yet" is what it has always meant here. */
  if (typeof shadowMissionStarting === "function" && shadowMissionStarting(m))
    return SH_TASK.queued;
  return shadowTaskFace(m && m.state);
}

/* THE WORKSPACE IS AN ACTIVE WORK SURFACE, NOT A MISSION DATABASE.

   GET /api/shadow/missions returns MissionStore.list() -- every mission file
   on disk, by design, because other readers need the whole history. This
   filter is PRESENTATION ONLY: nothing is deleted, no API or store semantics
   change, and the records stay exactly where the goals' attempts[] point.
   Historical attempts remain readable through Goals.

   The rule is "does this still represent outstanding work", decided from
   real state rather than an age cutoff -- a clock would hide a task that
   still needs you simply for being old, and keep a settled one for being
   recent:

     1. A mission whose GOAL has concluded is settled, whatever the mission
        itself says. Abandoning a goal stops its live attempt, but an attempt
        that was already blocked keeps that state forever -- so a blocked row
        under a stopped goal is vestigial, not a request. Its home is Goals.
     2. Otherwise, anything NOT terminal is unfinished work: draft,
        brief_confirm, queued, running, paused, blocked. This is what keeps
        the delegated tasks visible while they wait on a founder_confirm.
     3. A FAILED mission is the one terminal state with an action still
        pending -- Retry -- so it stays until it has actually been retried
        (retried_to) or its goal settles it.
     4. done and stopped are conclusions. They leave.

   Goals may not be loaded yet (they arrive in the same parallel read); an
   unknown goal is treated as unconcluded, so the list errs toward showing
   work rather than hiding it. */
const SH_TERMINAL = ["done", "failed", "stopped"];
const SH_GOAL_OVER = ["done", "stopped"];

function shadowTaskIsActive(m, goals){
  if (!m) return false;
  if (m.goal_id){
    const g = (goals || []).find(x => x && x.id === m.goal_id);
    if (g && SH_GOAL_OVER.includes(g.state)) return false;   // (1)
  }
  if (!SH_TERMINAL.includes(m.state)) return true;           // (2)
  if (m.state === "failed" && !m.retried_to) return true;    // (3)
  /* A STOP THE FOUNDER PRESSED IS NOT HISTORY YET (founder, 2026-09-14).
     Stop left the record on disk and reaped the delegate correctly, but the
     row vanished from the list in the same gesture -- which reads as the
     task having been deleted, and takes the card's Retry button with it,
     since the card only renders for something shadowTasks() still returns.

     `stopped` is two different endings wearing one state, and founder_stop
     ALREADY stamps the discriminator: `ended_by = "founder"`, written so
     the goal layer can tell a founder decision from machine trouble. The
     list simply never read it. A machine stop (ping-pong, and ask_founder
     on a standalone mission before it learned to block) carries no
     ended_by and still drops here, exactly as before.

     Same shape as the `failed` line above it, and for the same reason: an
     ending the founder has not dealt with yet still wants something from
     them. `!retried_to` is the same step-aside -- once a retry exists, the
     superseded row makes way for its successor.

     PRESENTATION ONLY. Nothing is deleted, no state moves, the backend stop
     path is untouched, the delegate is still reaped and the chat Shadow
     drove still stands in Chats. */
  if (m.state === "stopped" && m.ended_by === "founder"
      && !m.retried_to) return true;                         // (3b)
  return false;                                              // (4)
}

/* Every mission that still wants something from the founder, oldest first. */
function shadowTasks(){
  const S_ = (typeof S !== "undefined") ? S : {};
  const goals = S_.goals || [];
  return (S_.shadowMissions || []).filter(m => shadowTaskIsActive(m, goals));
}

/* The task in focus: the founder's pick if it still exists, else the first
   thing that wants attention, else the newest. Never null-when-there-is-work,
   so the right pane is never blank for no reason. */
function shadowSelectedTask(){
  const rows = shadowTasks();
  const S_ = (typeof S !== "undefined") ? S : {};
  /* THE TASK YOU ARE LOOKING AT DOES NOT VANISH WHEN IT FINISHES
     (founder, 2026-09-15). shadowTaskIsActive rule 4 is right and stays --
     a conclusion leaves the LIST, or the workspace becomes the mission
     database it exists not to be. But the pane was filtered by the same
     rule, so the moment a task completed the card it was showing was
     swapped for another task's, and the completion summary the engine had
     just stamped had no surface at all: the Now row said "done — result
     inside" and the inside had already been replaced.

     So the FOUNDER'S OWN PICK is honoured from the full record set, and
     everything else -- the list, the fallback ranking below, the rules in
     shadowTaskIsActive -- is untouched. Nothing new can be selected this
     way: S.shadowTaskSel is only ever written by clicking a row (and only
     active rows are drawn) or by creating a task, so the one record this
     reaches that `rows` does not is the one the founder was already
     reading. It stays until they pick something else.

     Same shape as rule 3b (a founder-stopped row stays): a conclusion the
     founder has not looked at yet is not history. */
  const held = (S_.shadowMissions || []).find(m => m && m.id === S_.shadowTaskSel);
  if (held) return held;
  if (!rows.length) return null;
  /* THE FALLBACK RANKED A DEAD ROW ABOVE A LIVE ONE (founder, 2026-09-14).
     The report was "the list says RUNNING and the card says QUEUED, turn 0
     of 20" -- read as the two surfaces disagreeing about one mission. They
     never did: both call shadowTaskFaceFor on the record the server sent,
     and for a running mission both say RUNNING. They were showing DIFFERENT
     MISSIONS, because this fallback picked the card's.

     `brief_confirm` is two different situations wearing one state, and only
     one of them is a request:

       no start_requested_at   READY -- nobody has started it, and the
                               founder's click is the next thing that has to
                               happen. Worth ranking above live work.
       start_requested_at set  the start was already taken. It is on its way,
                               or it died on the way. It wants nothing, and
                               it draws as QUEUED with turn 0 and "a new chat
                               Shadow starts when you begin" forever.

     Ranking the second kind above `running` meant one stale row -- a start
     that failed before the transition table could record it -- captured the
     detail pane for every task the founder created afterwards.

     shadowMissionStartable is the EXISTING predicate for exactly this
     split (it is what the card already asks before drawing Start), so no
     second state vocabulary is introduced, nothing is inferred from whether
     a chat exists, and no local "hasStarted" flag is invented. `blocked`
     keeps its place at the top untouched. */
  const byState = (st) => rows.find(m => m.state === st);
  const attention = byState("blocked");
  if (attention) return attention;
  const ready = rows.find(m => (typeof shadowMissionStartable === "function")
    ? shadowMissionStartable(m)
    : m.state === "brief_confirm");
  if (ready) return ready;
  for (const st of ["running", "paused", "queued", "brief_confirm"]){
    const hit = byState(st);
    if (hit) return hit;
  }
  return rows[rows.length - 1];
}

/* A task that is still WORKING says so in the ask: deleting it stops the work
   first (the server ends it through founder_stop/cancel_queued before the
   record goes). The founder must not learn that from the result.

   A task that is merely STARTING counts as working, and that is not a third
   idea about state -- it is shadowMissionStarting(), the same predicate that
   already takes Start away during provisioning. A start that has been
   accepted is work in flight, so deleting it stops something. */
const SH_LIVE_STATES = ["running", "queued", "paused", "blocked"];

function shadowTaskIsLive(m){
  return !!(m && (SH_LIVE_STATES.includes(m.state)
    || (typeof shadowMissionStarting === "function" && shadowMissionStarting(m))));
}

function shadowTaskListHtml(){
  const rows = shadowTasks();
  const sel = shadowSelectedTask();
  const S_ = (typeof S !== "undefined") ? S : {};
  if (!rows.length)
    return `<div class="shtaskempty">Nothing yet — Delegate a task and
      Shadow will run it in its own chat.</div>`;
  /* THE ROW IS NOW A ROW, NOT A BUTTON. The selector button is byte-identical
     to what it was -- same class, same hook, same three spans -- and it is
     simply no longer the outermost element, because a <button> may not
     contain another <button> and the list needed a second control on it.
     [data-shtask] is untouched, so the whole-row-is-the-control behaviour and
     its test are unaffected; the remove control is a DIFFERENT hook, checked
     first in the handler, so the two can never be confused for each other. */
  return rows.map(m => {
    const f = shadowTaskFaceFor(m);
    const on = sel && m.id === sel.id;
    return `<div class="shtaskrow${on ? " on" : ""}">
      <button class="shtask${on ? " on" : ""}"
      type="button" data-shtask="${escAttr(m.id)}">
      <span class="shtaskdot d-${esc(f.cls)}" aria-hidden="true"></span>
      <span class="shtaskname">${esc(m.objective || "(no objective)")}</span>
      <span class="shtpill shtpill-${esc(f.cls)}">${esc(f.label)}</span>
    </button>
      <button class="shtaskdel" type="button"
        data-shtaskdel="${escAttr(m.id)}"
        title="${shadowTaskIsLive(m) ? "Stop &amp; delete this task"
                                     : "Delete this task"}"
        aria-label="Delete task">\u00d7</button>
    </div>`;
  }).join("");
}

/* the floors, from the settings the app already serves. Silent when unknown --
   naming a safety rail we have not actually read would be a claim, not copy. */
function shadowFloorsLine(){
  const S_ = (typeof S !== "undefined") ? S : {};
  const floors = ((S_.shadowSettings || {}).floors) || [];
  if (!floors.length) return "";
  return `<div class="shfloors">floors it can't cross on its own: ${
    floors.map(f => esc(f)).join(" · ")}</div>`;
}

/* THE TASK CARD -- the brief, in the right pane. Deliberately NOT
   missionCardHtml: that is the compact in-thread row and stays exactly as it
   is (the overlay renders it too). This is the focused view the design asks
   for, and it reads every field off the same mission record. */
/* THE SIGN-OFF, in the card. A founder_confirm check is the one tier nothing
   else can satisfy -- not the transcript, not a verifier, not Shadow (the
   engine says so: confirm_check is "the ONLY writer of a founder_confirm met
   flag"). So a delegate that has done the work parks the mission at
   paused/founder_confirm and waits, and until now the card offered Resume and
   Stop and no way to say yes. This is that missing action, and it is the
   EXISTING one: confirm_check, by index, through shadowMissionAct.

   Per check, not per mission, because that is the shape the engine stores and
   the founder may agree with two of three. Each line shows the criterion in
   full BEFORE its button -- what is being agreed to is the whole point, so it
   is never collapsed into a count or a single "Looks done" button.

   A non-founder_confirm check that is still unmet is shown and NOT offered:
   the server refuses that index, and a button that always errors is worse
   than an honest line saying who does check it. */
function shadowCheckRowsHtml(m){
  const rows = (m.done_when || []).map((c, i) => {
    const text = (c && c.check) || "";
    if (!text) return "";
    const met = !!(c && c.met);
    const mine = c && c.tier === "founder_confirm";
    const by = (c && c.confirmed_by) || "";
    return `<div class="shcheck${met ? " shcheckmet" : ""}">
      <span class="shcheckbox" aria-hidden="true">${met ? "\u2713" : ""}</span>
      <span class="shchecktxt">${esc(text)}</span>
      ${met
        ? `<span class="shcheckby">confirmed${by ? " \u00b7 " + esc(by) : ""}</span>`
        : (mine
            ? `<button class="btn shcheckdo" type="button"
                data-shcheckmid="${escAttr(m.id)}" data-shcheckix="${escAttr(i)}"
                >Confirm</button>`
            : `<span class="shcheckby">Shadow checks this</span>`)}
    </div>`;
  }).join("");
  if (!rows) return "";
  /* SHADOW NEVER SAYS IT IS DONE, and the old headline here claimed it did
     ("Shadow says it is done and is waiting on you"). It cannot say that:
     DECISION_ACTIONS is ("continue", "ask_founder") with no stop and no
     done, and _complete is the only writer of a done mission. What actually
     happened is narrower, and is what the headline now states: the checks
     Shadow CAN check have passed, and only the founder's are left.

     The CONDITION was already correct -- this block renders only from the
     awaiting branch, i.e. shadowMissionNeedsFounder(m) -- so only the
     sentence changed. It matters more after the engine fix: an
     all-founder_confirm mission now keeps RUNNING instead of parking here,
     so the headline is reached only at a boundary that was really earned. */
  const left = (m.done_when || []).filter(c =>
    c && c.tier === "founder_confirm" && !c.met).length;
  return `<div class="shconfirm">
    <div class="shconfirmq">Shadow's own checks have passed — these are waiting on you.</div>
    <div class="shconfirmsub">Only you can sign these off \u2014 read each one
      and confirm the ones you agree with.${left
        ? " " + left + " left." : ""}</div>
    <div class="shchecks">${rows}</div>
  </div>`;
}

/* ── WHAT SHADOW DID, AND WHY IT CALLS IT DONE ────────────────────────────
   THE GAP THIS CLOSES (founder, 2026-09-15). A task that finished told the
   founder two things and neither was legible: the Now row said "mission
   done" -> "done — result inside", and the inside was `result_excerpt` --
   150 characters off the head of the evidence blob plus 250 off its tail,
   which lands mid-json far more often than on a sentence. The fact the
   founder wanted -- which criteria were satisfied, and by what -- existed
   all along as the loop's own evaluation, and was thrown away.

   THE SERVER DECIDES, THIS RENDERS. Every value here is read off
   `m.completion`, which mission_engine._complete stamps at the one place
   that can write a done mission. Nothing is recomputed client-side: this
   pane must never be able to claim a check passed that the engine did not
   pass. A record without the field (a mission completed before it existed)
   renders nothing and the card falls back to what it drew before.

   AND WHAT WAS ACTUALLY DONE (founder, 2026-09-15, second pass). The check
   rows answer "why does Shadow call this done"; they never answered "what
   did it do". `c.outcome` does, and it is the worker's own closing message
   -- read off the transcript by shadow_runner.last_worker_message, stamped
   by the same _complete, and QUOTED here. Nothing on this client composes,
   shortens or rewords it, and a summary without the field renders exactly
   the markup it rendered before, which is every mission completed before
   the outcome existed.

   THE CLASSES ARE THE SIGN-OFF'S. shcheck / shcheckbox / shchecktxt /
   shcheckby / shchecks / shconfirm* already style exactly this shape one
   function up (shadowCheckRowsHtml, the founder_confirm list), and a
   satisfied check should not look like a different species from a check
   waiting on you. Only .shcheckev is new. */
function shadowCompletionHtml(m){
  const c = m && m.completion;
  if (!c) return "";
  const rows = (c.checks || []).map(k => {
    const met = !!k.met;
    /* who confirmed rides the HOW line, because "you confirmed it · founder"
       is one fact, and the tier copy is the server's word not ours */
    const how = String(k.how || "") + (k.by ? " · " + k.by : "");
    return `<div class="shcheck${met ? " shcheckmet" : ""}">
      <span class="shcheckbox" aria-hidden="true">${met ? "✓" : ""}</span>
      <span class="shchecktxt">${esc(k.check || "")}${k.evidence
        ? `<span class="shcheckev">${esc(k.evidence)}</span>` : ""}</span>
      <span class="shcheckby">${esc(how)}</span>
    </div>`;
  }).join("");
  const turns = (c.turns_used || 0) + " of " + (c.max_turns || 0) + " turns";
  const S_ = (typeof S !== "undefined") ? S : {};
  /* the copy action's own feedback, and it is per-record: a flag holding
     another mission's id must leave THIS button reading "Copy result". */
  const copied = (S_.shadowResultCopied
    && S_.shadowResultCopied.id === m.id) ? S_.shadowResultCopied : null;
  return `<div class="shconfirm shdonesum" data-shdone="${escAttr(m.id)}">
    <div class="shdonehead">
      <div class="shconfirmq">Done — ${esc(c.headline || "")}</div>
      <button class="btn shdonecopy${copied
        ? (copied.ok ? " ok" : " bad") : ""}" type="button"
        data-shcopydone="${escAttr(m.id)}" data-shcopystate="${copied
          ? (copied.ok ? "copied" : "failed") : "idle"}"
        aria-label="${copied
          ? (copied.ok ? "Copied — the result is on your clipboard"
                       : "Copy failed — the result is not on your clipboard")
          : "Copy result — this summary as text"}"
        title="Copy this result as text">${copied
          ? (copied.ok ? "Copied" : "Copy failed") : "Copy result"}</button>
    </div>
    <div class="shconfirmsub">${esc(c.objective || "")}${c.objective
      ? " — " : ""}${esc(turns)} used. These are the criteria Shadow
      checked, and what satisfied each one.</div>
    ${c.outcome ? `<div class="shdonework">${esc(c.outcome)}</div>` : ""}
    <div class="shchecks">${rows}</div>
  </div>`;
}

/* ── THE RESULT, AS TEXT YOU CAN PASTE SOMEWHERE ELSE ─────────────────────
   THE GAP THIS CLOSES (founder, 2026-09-15). The summary above is the one
   legible account of what a finished task did, and it was trapped in the
   pane: to tell anyone else -- a colleague, a ticket, the chat that asked
   for the work -- the founder had to retype it or drag-select across three
   nested divs and paste the markup's whitespace with it.

   THE SAME SOURCE, THE SAME ORDER. This reads `m.completion` and nothing
   else, exactly as shadowCompletionHtml does, so what lands on the
   clipboard is what was on screen -- headline, objective, budget, then one
   line per check carrying its verdict, the server's HOW copy, and the
   quoted artifact indented under it. No second evaluator, nothing
   recomputed, and no record without the field can produce text at all. */
function shadowCompletionText(m){
  const c = m && m.completion;
  if (!c) return "";
  const head = ["Done — " + String(c.headline || "")];
  if (c.objective) head.push(String(c.objective));
  head.push((c.turns_used || 0) + " of " + (c.max_turns || 0)
    + " turns used.");
  /* the worker's account rides along, in the pane's own order: under the
     budget line, above the verdicts, with a blank line either side so a
     paragraph of prose does not read as one more header row. The same
     shape mission_engine.completion_text writes, deliberately. */
  if (c.outcome) head.push("", String(c.outcome));
  const rows = (c.checks || []).map(k => {
    const how = String(k.how || "") + (k.by ? " · " + k.by : "");
    /* ✓ / ✗ is the shcheckbox tick in text: a plain reader must be able to
       tell a satisfied check from an outstanding one without the CSS. */
    const line = (k.met ? "✓ " : "✗ ") + String(k.check || "")
      + (how ? " — " + how : "");
    return k.evidence ? line + "\n    " + String(k.evidence) : line;
  });
  return head.join("\n") + (rows.length ? "\n\n" + rows.join("\n") : "");
}

/* how long "Copied" stays before the button goes back to offering the
   action. Long enough to read, short enough that it is never the label a
   founder comes back to and mistakes for the control. */
const SH_COPY_MS = 2200;
let shCopyTimer = null;

/* THE FALLBACK, for a context the async clipboard is not offered in.
   `navigator.clipboard` is undefined on an insecure origin and refused on a
   page the OS does not consider focused -- both reachable here, since the
   panel is served over plain http to a browser whenever the founder opens it
   outside the Electron shell. execCommand("copy") is deprecated and is still
   the only thing that works there. It needs a real selected node, so a
   textarea is mounted off-screen for exactly one tick and removed in a
   `finally` -- an early return must never leave a stray node in the body.

   readOnly, not disabled: a disabled field cannot be selected, and readOnly
   is what stops the mobile keyboard from opening over the summary. */
function shadowCopyFallback(text){
  if (typeof document === "undefined" || !document.createElement) return false;
  const ta = document.createElement("textarea");
  try {
    ta.value = text;
    if (ta.setAttribute) ta.setAttribute("readonly", "");
    /* off-screen rather than hidden: display:none cannot hold a selection */
    if (ta.style){ ta.style.position = "fixed"; ta.style.top = "-1000px"; }
    if (document.body && document.body.appendChild) document.body.appendChild(ta);
    if (ta.select) ta.select();
    return !!(document.execCommand && document.execCommand("copy"));
  } catch (e) {
    return false;
  } finally {
    if (ta && ta.remove) ta.remove();
  }
}

/* ── THE ANNOUNCEMENT, FOR SOMEBODY WHO CANNOT SEE THE BUTTON ─────────────
   THE GAP THIS CLOSES (founder, 2026-09-15). The button changing its own
   label is the SIGHTED feedback and it was the only feedback. `aria-live`
   sat on the button itself, which is the wrong node twice over: an
   interactive control as its own live region is announced inconsistently,
   and -- the fatal half -- this pane repaints by replacing innerHTML, so
   every render DESTROYS that node and builds a new one. A live region that
   did not exist before the text changed has nothing to compare against and
   announces nothing. The label change was silent.

   So the region lives OUTSIDE the repainted markup, created once and then
   only ever written to -- the same shape agToast has used since it shipped
   (17-agents.js), and the reason it actually speaks. Off-screen rather than
   hidden: display:none and [hidden] are ignored by screen readers, which is
   the one thing this node must not be. */
function shadowCopyAnnounce(msg){
  if (typeof document === "undefined" || !document.createElement) return null;
  let n = document.getElementById && document.getElementById("shdoneannounce");
  if (!n){
    n = document.createElement("div");
    n.id = "shdoneannounce";
    n.className = "shdoneannounce";
    if (n.setAttribute){
      n.setAttribute("role", "status");
      n.setAttribute("aria-live", "polite");
    }
    if (document.body && document.body.appendChild) document.body.appendChild(n);
  }
  /* cleared on the way back to idle, so the NEXT copy of the same task is a
     change of text and is announced again rather than swallowed as a repeat */
  n.textContent = msg;
  return n;
}

/* THE ACTION ITSELF. Named rather than inlined in the click handler for the
   reason every other Shadow action is: the wiring below is one `if` that
   delegates, and the behaviour is testable without a DOM.

   It is presentation-only -- no read, no write, no mission state. A failure
   that BOTH paths refuse (an older browser with neither API, a page the OS
   locks the clipboard on) is SHOWN, not swallowed: a button that says
   nothing after a click is the disease this pane keeps curing. */
async function shadowCopyResult(mid){
  const S_ = (typeof S !== "undefined") ? S : {};
  const m = (S_.shadowMissions || []).find(x => x && x.id === mid);
  const text = shadowCompletionText(m);
  if (!text) return false;                /* nothing to copy, nothing to say */
  let ok = false;
  try {
    const cb = (typeof navigator !== "undefined") && navigator.clipboard;
    if (!cb || !cb.writeText) throw new Error("no clipboard");
    await cb.writeText(text);
    ok = true;
  } catch (e) {
    /* the async API was missing or refused -- try the old one before
       telling the founder it could not be done */
    ok = shadowCopyFallback(text);
  }
  S_.shadowResultCopied = { id: mid, ok: ok };
  shadowCopyAnnounce(ok ? "Result copied to the clipboard."
                        : "The result could not be copied to the clipboard.");
  if (typeof scheduleRender === "function") scheduleRender();
  /* a second click's feedback replaces the first's, and takes the first's
     timer with it -- otherwise the older one fires mid-way through the newer
     feedback and wipes it early */
  if (typeof clearTimeout === "function" && shCopyTimer) clearTimeout(shCopyTimer);
  if (typeof setTimeout === "function") shCopyTimer = setTimeout(() => {
    /* only clear what this click set -- a later copy of another task owns
       the flag by then, and must keep its own feedback */
    if (S_.shadowResultCopied && S_.shadowResultCopied.id === mid)
      S_.shadowResultCopied = null;
    shadowCopyAnnounce("");
    if (typeof scheduleRender === "function") scheduleRender();
  }, SH_COPY_MS);
  return ok;
}

/* ── THE DELEGATE CHAT, IN THE TASK PANE ─────────────────────────────────
   THE GAP THIS CLOSES (founder, 2026-09-14). Create Task already started the
   mission -- shadowCreateTask awaits the existing shadowMissionAct(id,
   "start_now"), the worker spawns, and _publish_delegate_chat publishes the
   chat the moment the CLI announces its session id (~1.4s measured). The
   backend was never the problem. But this pane rendered a STATIC BRIEF --
   objective, "acts in", "turn 0 of 20" -- and nothing else, so for the
   fourteen seconds before the row left brief_confirm the founder watched a
   card that said QUEUED and showed no conversation at all. The chat existed
   and was simply never drawn.

   NOT A SECOND CHAT SYSTEM, and deliberately not one line of new transcript
   machinery. goalMessages / goalTranscriptHtml / loadGoalTranscript already
   render exactly this -- a headless session Shadow drives, keyed by session
   id -- for the Assignment workspace. They are generic in `sid`, so they are
   CALLED here, not copied. The gw* classes they emit are already global in
   panel.css, so no stylesheet moves either.

   THE GUARD IS THE SAME ONE goalCriteriaToChecks USES: panel.html loads
   18-goal-workspace.js right after this file, so production always has these
   functions by the time a card renders; a context that loaded this module
   alone degrades to the brief it drew before rather than throwing.

   ONE FETCH, NOT A STORM. render() runs many times a second, so the fetch is
   throttled per session exactly the way goalTranscriptChanged throttles the
   Assignment one: once when nothing is held yet, then no more often than
   every 1.5s while the mission is still live, and never for a session whose
   pane is open (09-tail.js already re-reads that one). */
const SH_TRANSCRIPT_MS = 1500;
const shTranscriptAt = {};

function shadowTaskTranscript(sid, live){
  if (!sid || typeof goalMessages !== "function") return undefined;
  const S_ = (typeof S !== "undefined") ? S : {};
  const held = (S_.goalTranscript || {})[sid];
  const open = !!(S_.openPanes && S_.openPanes.indexOf(sid) !== -1);
  const now = (typeof Date !== "undefined") ? Date.now() : 0;
  const due = (held === undefined) || (live && now - (shTranscriptAt[sid] || 0)
                                       > SH_TRANSCRIPT_MS);
  if (due && !open && typeof loadGoalTranscript === "function"){
    shTranscriptAt[sid] = now;
    loadGoalTranscript(sid);
  }
  return goalMessages(sid);
}

/* The conversation block itself. Rendered only once the session EXISTS --
   before that there is genuinely nothing to show, and the "acts in" row
   above already says a chat is being started. */
function shadowTaskChatHtml(m){
  const sid = m && m.target_session;
  if (!sid || typeof goalTranscriptHtml !== "function") return "";
  const live = SH_TERMINAL.indexOf(m.state) === -1;
  return `<div class="gwchat shcard2chat">
    <div class="gwchathead">its own chat · ${esc(shadowChatLabel(sid))}</div>
    ${goalTranscriptHtml(shadowTaskTranscript(sid, live), m)}
  </div>`;
}

/* ── THE FOUNDER INTERVENTION FORM ───────────────────────────────────────
   Shadow asked a TYPED question and the mission is blocked on the answer.

   ADDITIVE AND SELF-ERASING. Every function here returns "" for a mission
   with no `intervention`, which is every mission that existed before this
   -- so a card without one renders exactly the markup it rendered before.
   `blocked` already draws as NEEDS YOU (SH_TASK.blocked), so no face, no
   state and no pill changed; only the body of the card gained a form.

   ONE RENDERER FOR EVERY TYPE. The server sends the schema, this draws it.
   Adding a type later is one more `case` here plus one validator on the
   server -- not a new panel, not a new endpoint, and nothing in the
   lifecycle. A type this build does not know is drawn as a disabled row
   saying so, rather than silently dropped, so an older panel in front of a
   newer Shadow is honest instead of broken.

   The draft lives on S, exactly like shadowNewDraft's, and the value is
   interpolated back into the markup on every render for the same reason the
   delegate panel does it: render() runs constantly and an uncontrolled
   input would lose what was typed. */
const SH_IV_INPUT = {
  text: "text", url: "url", email: "email", number: "number",
  currency: "number", percent: "number", date: "date",
  datetime: "datetime-local",
};

function shadowIvDraft(mid){
  const S_ = (typeof S !== "undefined") ? S : {};
  if (!S_.shadowIv) S_.shadowIv = {};
  if (!S_.shadowIv[mid])
    S_.shadowIv[mid] = { values: {}, errors: {}, busy: false, err: null };
  return S_.shadowIv[mid];
}

function shadowIvValue(mid, f){
  const d = shadowIvDraft(mid);
  if (Object.prototype.hasOwnProperty.call(d.values, f.key))
    return d.values[f.key];
  return f.default === undefined ? null : f.default;
}

/* ── WHAT THE "YES" ACTUALLY SIGNS OFF (founder, 2026-09-15) ─────────────
   THE GAP. 39682c81 taught the server that an intervention may name one
   done_when check and the boolean field that gates it (`confirms_check`),
   so answering Yes calls confirm_check and marks that check met. The form
   drew none of it: the founder saw "Do the tests pass? [Yes] [No]" with no
   sign that Yes was signing off a COMPLETION CRITERION. The failure that
   motivated the server work (m-cd009367d41a burning its whole budget with
   done_when[2] unmet) was invisible for exactly this reason.

   QUOTED, NEVER PARAPHRASED (founder decision, 2026-09-15). The row prints
   the check string from the mission record verbatim, in quotes. Generic
   wording -- "confirm this check" -- would leave the founder signing off
   something they cannot read, which is the whole defect.

   THE SAME THREE CONDITIONS THE SERVER ENFORCES, and no others, so the row
   appears if and only if the answer will really write the flag:
     1. the target names THIS field, and the field is boolean
        (_confirms_check refuses any other type: choice and text would need
        a policy for which answers mean yes, which that module declines to
        invent);
     2. `index` is a non-bool, non-negative integer;
     3. done_when[index] exists AND its tier is founder_confirm.
   Anything else draws NOTHING -- a stale or moved index makes confirm_check
   raise, the server catches and ledgers it, and the answer still lands. A
   card must not promise a sign-off the server will decline to write. */
function shadowIvSignsIndex(m, f){
  const t = m && m.intervention && m.intervention.confirms_check;
  if (!t || typeof t !== "object") return -1;
  if (!f || f.type !== "boolean" || t.field !== f.key) return -1;
  const i = t.index;
  /* typeof excludes the boolean true, which would otherwise index as 1 */
  if (typeof i !== "number" || i !== Math.floor(i) || i < 0) return -1;
  const c = (m.done_when || [])[i];
  if (!c || c.tier !== "founder_confirm") return -1;
  return i;
}

/* The check is real but its text is empty -- a record written without one,
   or one blanked since. The row still draws, because the sign-off is still
   going to happen and hiding it would put the founder back where they
   started; it just says plainly that there is nothing to read, rather than
   quoting an empty string as if it were the criterion. */
function shadowIvSignsHtml(m, f){
  const i = shadowIvSignsIndex(m, f);
  if (i === -1) return "";
  const text = String(((m.done_when || [])[i] || {}).check || "").trim();
  return `<div class="shivsigns">
    <span class="shivsignsk">Yes signs off</span>
    <span class="shivsignsv">${text
      ? "“" + esc(text) + "”"
      : "check " + (i + 1) + " — the record has no text for it"}</span>
  </div>`;
}

function shadowIvFieldHtml(mid, f, signs){
  const d = shadowIvDraft(mid);
  const v = shadowIvValue(mid, f);
  const err = d.errors[f.key];
  const hook = `data-shivmid="${escAttr(mid)}" data-shivkey="${escAttr(f.key)}"`;
  const opt = (o, on, extra) => `<button class="shkind${on ? " on" : ""}"
    type="button" ${hook} data-shivopt="${escAttr(o.value)}"
    title="${escAttr(o.help || "")}">${esc(o.label)}${extra || ""}</button>`;
  let body;
  switch (f.type){
    case "boolean":
      body = `<div class="shnewkinds">
        ${opt({ value: "yes", label: "Yes" }, v === true)}
        ${opt({ value: "no", label: "No" }, v === false)}</div>`;
      break;
    case "choice":
      body = `<div class="shnewkinds">${(f.options || [])
        .map(o => opt(o, v === o.value)).join("")}</div>`;
      break;
    case "multi_choice":
      body = `<div class="shnewkinds">${(f.options || []).map(o =>
        opt(o, Array.isArray(v) && v.indexOf(o.value) !== -1)).join("")}</div>`;
      break;
    case "ranking":
      body = `<div class="shnewkinds">${(f.options || []).map(o => {
        const at = Array.isArray(v) ? v.indexOf(o.value) : -1;
        return opt(o, at !== -1, at === -1 ? "" : ` <b>${at + 1}</b>`);
      }).join("")}</div>`;
      break;
    case "long_text":
      body = `<textarea rows="4" ${hook} data-shivtext="1"
        placeholder="${escAttr(f.help || "")}">${esc(v == null ? "" : v)}</textarea>`;
      break;
    default: {
      const kind = SH_IV_INPUT[f.type];
      if (!kind){
        body = `<div class="shnewerr">This panel cannot ask for
          “${esc(f.type)}” yet — update Sutra to answer it.</div>`;
        break;
      }
      body = `<input type="${escAttr(kind)}" ${hook} data-shivtext="1"
        value="${escAttr(v == null ? "" : String(v))}"
        placeholder="${escAttr(f.help || "")}">`;
    }
  }
  return `<div class="shivfield">
    <label class="shnewlabel">${esc(f.label)}${
      f.required ? ' <span class="shivreq">required</span>' : ""}</label>
    ${f.help && f.type !== "long_text" && SH_IV_INPUT[f.type] === undefined
      ? `<p class="shnewsub">${esc(f.help)}</p>` : ""}
    ${body}
    ${signs || ""}
    ${err ? `<div class="shnewerr">${esc(err)}</div>` : ""}
  </div>`;
}

function shadowInterventionHtml(m){
  const iv = m && m.intervention;
  if (!iv || !Array.isArray(iv.fields) || !iv.fields.length) return "";
  const d = shadowIvDraft(m.id);
  return `<div class="shiv" data-shivform="${escAttr(iv.id || "")}">
    <div class="shivq">${esc(iv.question || "")}</div>
    ${iv.context ? `<p class="shnewsub">${esc(iv.context)}</p>` : ""}
    ${(iv.evidence || []).length ? `<div class="shivev">${
      iv.evidence.map(e => `<div class="shivevrow">${
        e.ref ? `<span class="shivevref">${esc(e.ref)}</span>` : ""
      }<span>${esc(e.text || "")}</span></div>`).join("")}</div>` : ""}
    ${iv.fields.map(f => shadowIvFieldHtml(m.id, f, shadowIvSignsHtml(m, f)))
      .join("")}
    <div class="shnewacts">
      <button class="btn pri" type="button"
        data-shivsend="${escAttr(m.id)}"${d.busy ? " disabled" : ""}
        >${d.busy ? "Sending…" : esc(iv.submit_label || "Send to Shadow")}</button>
    </div>
    ${d.err ? `<div class="shnewerr">${esc(d.err)}</div>` : ""}
  </div>`;
}

/* THE ANSWER GOES TO SHADOW. One POST to the mission action endpoint that
   already exists -- no second write surface -- and the server decides
   everything: it checks the id is still the live question, validates each
   value against the schema it stored, and only then resumes the SAME
   delegate. A 422 comes back with per-field messages and the mission stays
   blocked, so the founder simply fixes the form and sends again. */
async function shadowSendIntervention(mid){
  if (!mid || typeof shadowPost !== "function") return null;
  const S_ = (typeof S !== "undefined") ? S : {};
  const m = (S_.shadowMissions || []).find(x => x && x.id === mid);
  const iv = m && m.intervention;
  if (!iv) return null;
  const d = shadowIvDraft(mid);
  d.busy = true; d.err = null; d.errors = {};
  if (typeof scheduleRender === "function") scheduleRender();
  let r = null;
  try {
    r = await shadowPost("/api/shadow/missions/" + mid + "/act", {
      action: "intervene", intervention_id: iv.id, values: d.values });
  } catch (e){ r = null; }
  d.busy = false;
  if (!r){
    d.err = "Could not reach Shadow just now.";
  } else if (r.status === 422){
    let body = null;
    try { body = await r.json(); } catch (e){ body = null; }
    const detail = (body && body.detail) || {};
    d.errors = detail.errors || {};
    d.err = detail.detail || "Some answers need a fix.";
  } else if (!r.ok){
    let body = null;
    try { body = await r.json(); } catch (e){ body = null; }
    const detail = (body && body.detail) || null;
    d.err = (detail && (detail.detail || detail))
      || ("That did not stick (" + r.status + ")");
  } else {
    /* answered: drop the draft so a later question starts clean */
    if (S_.shadowIv) delete S_.shadowIv[mid];
    if (typeof showNudge === "function")
      showNudge("Sent to Shadow — it picks up from here.");
  }
  if (typeof loadShadowHome === "function") await loadShadowHome(true);
  if (typeof scheduleRender === "function") scheduleRender();
  return r;
}

/* ── "last updated": how fresh the thing you are reading is ──────────────
   THE SERVER'S CLOCK, NEVER THE RENDERER'S. MissionStore.save() re-stamps
   `updated_at` on every write, so this is the age of the RECORD. A local
   render time would read "just now" forever on a task that has not moved,
   which is the exact question this row exists to answer.

   Relative, because "is this still moving?" is what a founder asks a live
   card; the exact instant stays on hover for when the relative word is not
   enough. Empty string when there is no usable stamp -- a card that cannot
   say how fresh it is must say nothing rather than guess. */
function shadowStampAgo(iso, now){
  const ms = Date.parse(String(iso == null ? "" : iso));
  if (isNaN(ms)) return "";
  const d = (now == null ? Date.now() : now) - ms;
  /* a stamp in the future is clock skew between the server and this box,
     not news from later -- it reads as fresh, never as "-3m ago" */
  if (d < 60000) return "just now";
  if (d < 3600000) return Math.floor(d / 60000) + "m ago";
  if (d < 86400000) return Math.floor(d / 3600000) + "h ago";
  return Math.floor(d / 86400000) + "d ago";
}

function shadowTaskUpdatedHtml(m){
  const iso = m && (m.updated_at || m.created_at);
  const ago = shadowStampAgo(iso);
  if (!ago) return "";
  return `<div class="shcard2row shcard2stamp"><span class="shcard2k">last updated</span>
    <span class="shcard2v" title="${escAttr(iso)}">${esc(ago)}</span></div>`;
}

/* ── the budget, as a length ──────────────────────────────────────────────
   "turn 14 of 20" is two numbers you have to subtract before you reach the
   thing you actually wanted to know: is this task about to run out of turns.
   A length answers that at a glance where a pair of integers does not. The
   numbers stay where they were, as the confirmation -- the same order the
   Account screen's usage meters already use.

   THE TRACK IS THAT SAME METER, reused unchanged: `.ubar` with the p-ok /
   p-warn / p-block palette. Nothing new is minted, so the colours mean the
   same severity here as everywhere else in the panel.

   THE BREAKPOINTS ARE NOT THAT METER'S (founder G9, 2026-09-15): calm below
   60%, warning from 60% through 85%, critical above 85%. `usageSev` warns at
   70 and blocks at 80 because a rate-limit window REFILLS -- crossing it
   costs you a wait. A turn budget does not refill: hitting the ceiling ends
   the run wherever it happens to be. So the founder's line warns earlier and
   reserves red for genuinely near-death, and the two meters deliberately
   disagree on WHERE the line sits while agreeing on what the colours mean.

   Spelled out here rather than called across the module boundary, because
   this file is loaded alone in the render tests and a bar that silently lost
   its colour there would be a bar the tests cannot see.

   THE EDGES BELONG TO WARNING. Exactly 60% and exactly 85% both read amber
   -- "above ~85%" is the founder's wording for critical, so 85 itself is not
   yet critical. Asserted at those exact values in test_shadow_home.js so the
   reading cannot drift.

   NO DENOMINATOR, NO BAR. `max_turns` of 0 or missing is "nobody said", not
   "a budget of zero", and a full red track would be a lie about a task that
   is fine. The row keeps the text it has always had and draws nothing --
   the same rule the freshness stamp above follows.

   OVER BUDGET CLAMPS AT 100. A worker one turn past its ceiling is spent,
   not 105% spent, and the fill cannot overflow its own track. */
function shadowBudgetPct(m){
  const max = Number(m && m.max_turns);
  if (!(max > 0)) return null;
  const used = Math.max(0, Number(m && m.turns_used) || 0);
  return Math.min(100, Math.round((used / max) * 100));
}

function shadowBudgetSev(pct){
  return pct > 85 ? "p-block" : pct >= 60 ? "p-warn" : "p-ok";
}

function shadowBudgetBarHtml(m){
  const pct = shadowBudgetPct(m);
  if (pct === null) return "";
  const max = Number(m.max_turns);
  const used = Math.min(max, Math.max(0, Number(m.turns_used) || 0));
  /* the arithmetic the bar exists to save you, kept for the screen reader
     and for hover -- a length is not readable by either */
  const rest = max - used;
  const phrase = rest === 1 ? "1 turn left" : rest + " turns left";
  return `<span class="ubar shcard2bar" role="img" title="${escAttr(phrase)}"
    aria-label="${escAttr(used + " of " + max + " turns used, " + phrase)}"
    ><i class="${shadowBudgetSev(pct)}" style="width:${pct}%"></i></span>`;
}

function shadowTaskCardHtml(m){
  if (!m) return "";
  const S_ = (typeof S !== "undefined") ? S : {};
  const f = shadowTaskFaceFor(m);
  /* THE WORKER CHAT IS COLLAPSED BY DEFAULT (founder, 2026-09-14).

     This pane is Shadow's control room: the state, the budget, what it is
     still waiting on, and the checks only the founder can sign off. Those
     are the things a founder acts on, and the transcript -- the longest
     block on the card by far -- pushed them off the top.

     NOTHING IS REMOVED. The transcript is the same block, drawn by the same
     shadowTaskChatHtml through the same Assignment-workspace machinery
     (goalMessages / goalTranscriptHtml / loadGoalTranscript); only whether
     it is expanded changed, and it is one click away. The v2.273.0 gap it
     closed -- a static brief while the chat already existed -- stays closed
     for anyone who opens it, and the two fixes that shipped beside it
     (early admit, list/card agreement) are what keep the COLLAPSED card
     honest about progress on its own.

     A fetch follows the render, so a collapsed chat is not polled at all.

     `shadowTaskChatOpen` holds the mission id, not a boolean: selecting a
     different task collapses again rather than carrying one task's choice
     onto the next. Same shape as the other per-selection flags here.

     The toggle is drawn only when there is genuinely something behind it --
     a session AND the transcript module -- so it is never a control that
     opens nothing. That is the same pair shadowTaskChatHtml itself tests,
     kept in one place. "Open the chat" in the actions row is unchanged and
     still leaves for the real session. */
  const chatReady = !!(m.target_session
    && typeof goalTranscriptHtml === "function");
  const chatOpen = chatReady && S_.shadowTaskChatOpen === m.id;
  /* NOT `m.state === "brief_confirm"`. A start that has already been accepted
     leaves the record in brief_confirm while it provisions, and offering
     Start there is the button that would not go away -- see
     shadowMissionStarting() in the overlay module for the whole story. The
     guard keeps a context that loaded this module alone working. */
  const startable = (typeof shadowMissionStartable === "function")
    ? shadowMissionStartable(m)
    : m.state === "brief_confirm";
  const checks = (m.done_when || []).map(c => c && c.check).filter(Boolean);
  /* the ONE extra state this card knows about: waiting on the founder's
     sign-off. The flat "done when" row is a summary and cannot be acted on,
     so in this state the checklist REPLACES it rather than sitting beside it
     -- the same criteria printed twice is not a compact card. */
  const awaiting = shadowMissionNeedsFounder(m);
  /* and the state after that one: the task FINISHED. The flat "done when"
     row is the same criteria without the verdicts, so the summary replaces
     it for exactly the reason the sign-off list does -- the same criteria
     printed twice is not a compact card. Keyed on the summary the server
     stamped, never on `state === "done"`, so a mission completed before the
     field existed keeps the row it has always had. */
  const finished = !!m.completion;
  /* target_mode + target_session ARE the answer to "where does this run"; no
     second source and nothing inferred. */
  const acts = m.target_mode === "new"
    ? (m.target_session
        ? `its own chat · ${esc(shadowChatLabel(m.target_session))}`
        : "a new chat Shadow starts when you begin")
    : (m.target_session
        ? esc(shadowChatLabel(m.target_session))
        : "an existing chat");
  return `<div class="shcard2" data-shtaskcard="${escAttr(m.id)}">
    <div class="shcard2head">
      <span class="shcard2tag">${esc(m.template || "task")}</span>
      <span class="shcard2obj">${esc(m.objective || "")}</span>
      <span class="shtpill shtpill-${esc(f.cls)}">${esc(f.label)}</span>
    </div>
    <div class="shcard2row"><span class="shcard2k">acts in</span>
      <span class="shcard2v">${acts}</span></div>
    ${awaiting || finished ? "" : `<div class="shcard2row"><span class="shcard2k">done when</span>
      <span class="shcard2v">${checks.length
        ? esc(checks.join(" · "))
        : "you say so — no check was set, so Shadow will ask"}</span></div>`}
    <div class="shcard2row"><span class="shcard2k">budget</span>
      <span class="shcard2v">turn ${esc(String(m.turns_used || 0))} of ${
        esc(String(m.max_turns || 0))}${shadowBudgetBarHtml(m)}</span></div>
    ${shadowTaskUpdatedHtml(m)}
    ${m.block_reason ? `<div class="shcard2row"><span class="shcard2k">stopped on</span>
      <span class="shcard2v">${esc(typeof goalBlockerCopy === "function"
        ? goalBlockerCopy(m.block_reason) : m.block_reason)}</span></div>` : ""}
    ${awaiting ? shadowCheckRowsHtml(m) : ""}
    ${finished ? shadowCompletionHtml(m) : ""}
    ${shadowInterventionHtml(m)}
    ${chatReady ? `<button class="shchattoggle${chatOpen ? " on" : ""}"
      type="button" data-shtaskchat="${escAttr(m.id)}"
      aria-expanded="${chatOpen ? "true" : "false"}">${
      chatOpen ? "\u2304 Hide worker chat" : "\u203a Show worker chat"}</button>` : ""}
    ${chatOpen ? shadowTaskChatHtml(m) : ""}
    <div class="shcard2acts">
      ${startable ? `<button class="btn pri" type="button"
        data-shstart="${escAttr(m.id)}">Start the task</button>
        <span class="shcard2hint">…or keep telling me</span>` : ""}
      ${["running", "paused", "blocked"].includes(m.state) ? `<button class="btn"
        type="button" data-shact="stop" data-shmid="${escAttr(m.id)}">Stop</button>` : ""}
      ${["paused", "blocked"].includes(m.state) ? `<button class="btn" type="button"
        data-shact="resume" data-shmid="${escAttr(m.id)}">Resume</button>` : ""}
      ${m.state === "queued" ? `<button class="btn" type="button"
        data-shact="drop" data-shmid="${escAttr(m.id)}">Drop</button>` : ""}
      ${["failed", "stopped"].includes(m.state) ? `<button class="btn"
        type="button" data-shact="retry" data-shmid="${escAttr(m.id)}">Retry</button>` : ""}
      ${m.target_session ? `<button class="btn" type="button"
        data-shtakeover="${escAttr(m.target_session)}">Open the chat</button>` : ""}
    </div>
    ${shadowFloorsLine()}
  </div>`;
}

/* ── + Delegate: the new-task panel ──────────────────────────────────────
   In the right pane, never a modal. The founder describes an outcome; the
   app posts it to the EXISTING mission endpoint with target_mode "new". The
   term never reaches the UI -- the button IS the intent. */
const SH_KINDS = ["fix", "feature", "research", "watch"];

function shadowNewDraft(){
  const S_ = (typeof S !== "undefined") ? S : {};
  if (!S_.shadowNew) S_.shadowNew = { objective: "", done: "", kind: "fix" };
  return S_.shadowNew;
}

function shadowDelegatePanelHtml(){
  const d = shadowNewDraft();
  const S_ = (typeof S !== "undefined") ? S : {};
  const busy = !!S_.shadowNewBusy;
  return `<div class="shnew" data-shnewpanel="1">
    <h3 class="shnewq">What should Shadow get done?</h3>
    <p class="shnewsub">Shadow starts a <b>new chat</b> for this and drives it
      itself. It shows up in Chats as “Shadow Task — …”.</p>
    <label class="shnewlabel" for="shnewobj">The outcome you want</label>
    <textarea id="shnewobj" rows="3" data-shnewobj="1"
      placeholder="Fix the rounding differences in the EMI checks and ship it"
      >${esc(d.objective)}</textarea>
    <label class="shnewlabel" for="shnewdone">Done when (optional, one per line)</label>
    <textarea id="shnewdone" rows="2" data-shnewdone="1"
      placeholder="the EMI check passes&#10;a tested PR is open">${esc(d.done)}</textarea>
    <label class="shnewlabel">Kind of work</label>
    <div class="shnewkinds">${SH_KINDS.map(k => `<button
      class="shkind${d.kind === k ? " on" : ""}" type="button"
      data-shnewkind="${escAttr(k)}">${esc(k)}</button>`).join("")}</div>
    <div class="shnewacts">
      <button class="btn pri" type="button" data-shnewcreate="1"${
        busy ? " disabled" : ""}>${busy ? "Creating…" : "Create the task"}</button>
      <button class="btn" type="button" data-shnewcancel="1">Cancel</button>
    </div>
    ${S_.shadowNewErr ? `<div class="shnewerr">${esc(S_.shadowNewErr)}</div>` : ""}
  </div>`;
}

/* THE WORKSPACE COMPOSER: one line, nothing else.

   shadowStageHtml() renders the EXISTING-CHAT flow -- the "Working with"
   target picker, the recent-conversation chips, the briefing copy -- around
   the same composer. All of that is still built, still wired, and still
   reachable (shadowHomeHtml renders the real thing the moment the founder
   opens that flow). It is simply not what a DELEGATED TASK workspace is
   about, so it is not rendered here by default.

   Same hook, same scope attribute, same submit path as the stage's composer:
   the delegated workspace and the existing-chat flow share one composer
   implementation, so a turn typed in either goes the same way. */
function shadowWorkComposerHtml(){
  const S_ = (typeof S !== "undefined") ? S : {};
  return `<div class="shwcomp">
    <div class="shcompwrap">
      <textarea class="shcompose" data-shhomecompose="1"
        data-shscope="${escAttr(S_.shadowChat || "global")}"
        placeholder="Say anything — it starts or continues a task…"></textarea>
      <button class="shsend" type="button" data-shsend="1"
        title="Send (or press Enter)" aria-label="Send">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" aria-hidden="true"
          ><path d="M12 19V5M5 12l7-7 7 7"/></svg></button>
    </div>
    <button class="shexisting" type="button" data-shexisting="1">Work in an
      existing chat instead</button>
  </div>`;
}

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
/* ---- Shadow Home, to the approved design ---------------------------------
   PRESENTATION ONLY. Every data-* hook, handler and string below already
   existed; what changes is composition, type and space.

   FAITHFUL TO THE REFERENCE EXCEPT WHERE IT WOULD LIE. The design shows
   "Updated 2h ago", per-assignment tags, and category icons -- a goal row
   carries no timestamp, no tags and nothing to derive an icon from, so
   those are omitted rather than invented. The state legend shows real
   counts but is deliberately NOT interactive: filtering does not exist,
   and a control that looks clickable and is not would be worse than none.

   SCOPE: the container keeps `shbrief` (every shipped rule and every test
   that names it still applies) and gains `shbrief2`, the only hook the new
   styling hangs off. No shared selector is touched. */

const SH_ICON_CHEV = '<svg class="shchev" viewBox="0 0 24 24" fill="none" '
  + 'stroke="currentColor" stroke-width="2" aria-hidden="true">'
  + '<path d="M9 18l6-6-6-6"/></svg>';

function shadowPulseClass(){
  const { needs, running } = shadowBriefCounts();
  if (needs.length) return "shpulse shpulse-needs";
  if (running.length) return "shpulse shpulse-live";
  return "shpulse shpulse-calm";
}

function shadowMastHtml(){
  return `<header class="shmast">
    <div class="shmastid">
      <h1 class="shmastname">Shadow</h1>
      <div class="shmastrole">Your autonomous supervisor</div>
      <div class="shmaststate">
        <span class="${shadowPulseClass()}" aria-hidden="true"></span>
        <span class="shgreet">${esc(shadowGreeting())}</span>
      </div>
    </div>
    <blockquote class="shquote">
      <span>“Give me the outcome,</span>
      <span>I’ll take it from here.”</span>
      <cite>— Shadow</cite>
    </blockquote>
  </header>`;
}

/* the target chat. Same data-shscopepick to open the list, same data-shchat
   to pick -- only the presentation is new. */
function shadowTargetHtml(){
  const S_ = (typeof S !== "undefined") ? S : {};
  const active = S_.shadowChat && S_.shadowChat !== "global"
    ? S_.shadowChat : null;
  return `<div class="shscope">
    <div class="shscopelabel">Working with</div>
    <button class="shtarget${active ? " on" : ""}" type="button"
      data-shscopepick="1">
      <span class="shtargeticon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="1.7"><path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0
          1-3.9-.9L3 20.5l1.6-4.6A8.4 8.4 0 0 1 3.6 11a8.4 8.4 0 0 1 8.4-8.4
          8.4 8.4 0 0 1 9 8.9z"/></svg></span>
      <span class="shtargettext">
        <span class="shtargetname">${active
          ? esc(shadowChatLabel(active)) : "Choose a conversation"}</span>
        <span class="shtargetkind">${active
          ? "Existing conversation" : "Pick the chat Shadow takes on"}</span>
      </span>
      <svg class="shtargetchev" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2" aria-hidden="true"
        ><path d="M6 9l6 6 6-6"/></svg>
    </button>
  </div>`;
}

/* the recent-conversation chips ARE the picker: same data-shchat hook the
   dropdown list has always used, shown inline instead of behind a toggle.
   "+N more" opens the existing list rather than inventing a second one. */
const SH_CHIP_CAP = 4;
function shadowRecentChatsHtml(){
  const S_ = (typeof S !== "undefined") ? S : {};
  const keys = (typeof shadowChatKeys === "function") ? shadowChatKeys() : [];
  if (!keys.length) return "";
  const active = S_.shadowChat && S_.shadowChat !== "global"
    ? S_.shadowChat : null;
  const shown = keys.slice(0, SH_CHIP_CAP);
  const hidden = keys.length - shown.length;
  return `<div class="shrecent">
    <span class="shrecentlabel">Recent conversations</span>
    <div class="shrecentrow">
      ${shown.map(k => `<button class="shchip${k === active ? " on" : ""}"
        type="button" data-shchat="${escAttr(k)}"
        >${esc(shadowChatLabel(k))}</button>`).join("")}
      ${hidden > 0 ? `<button class="shchip shchipmore" type="button"
        data-shscopepick="1">+${hidden} more</button>` : ""}
    </div>
    ${S_.shadowScopeOpen ? `<div class="shscopelist">${
      [`<button class="btn shscopeopt" type="button"
         data-shchat="global">no chat — just talk</button>`]
        .concat(keys.map(k => `<button class="btn shscopeopt${
          k === active ? " on" : ""}" type="button"
          data-shchat="${escAttr(k)}">${esc(shadowChatLabel(k))}</button>`))
        .join("")}</div>` : ""}
  </div>`;
}

function shadowStageHtml(){
  const S_ = (typeof S !== "undefined") ? S : {};
  return `<section class="shstage">
    <div class="shstagetop">
      ${shadowTargetHtml()}
      <div class="shask">
        <div class="shasklabel">What should I take on?</div>
        <div class="shasktitle">Tell Shadow the outcome you want.</div>
        <div class="shasksub">Be specific or high level — Shadow will
          figure out the steps.</div>
      </div>
    </div>
    <div class="shcompwrap">
      <textarea class="shcompose" data-shhomecompose="1"
        data-shscope="${escAttr(S_.shadowChat || "global")}"
        placeholder="Tell Shadow what outcome you want…"></textarea>
      <button class="shsend" type="button" data-shsend="1"
        title="Hand it over (or press Enter)" aria-label="Hand it over">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="2" aria-hidden="true"
          ><path d="M12 19V5M5 12l7-7 7 7"/></svg></button>
    </div>
    ${S_.shadowScopeErr
      ? `<div class="shnewerr">${esc(S_.shadowScopeErr)}</div>` : ""}
    ${shadowRecentChatsHtml()}
  </section>`;
}

/* THE FOOTER IS ONE DOOR (design of record: website/preview/shadow-v7.html,
   the v7 task pane -- its .tnfoot holds a single "Shadow settings" row).

   Five links under a task list made the workspace read as a dashboard index,
   which is the thing the task workspace exists not to be. Watching,
   Conversations, Goals and Memory are NOT removed: every screen, hook and
   handler they had is untouched, and they are reached from the Attention and
   Memory sections of the settings page this button opens -- which is where
   the design puts them. data-shscreen is the EXISTING hook, so the route is
   the one that already worked.

   Kept exported and rendered by the same caller, so nothing else in the
   workspace had to move. */
function shadowNavHtml(){
  return `<nav class="shfoot shnav">
    <button class="btn shfootitem shnavitem shsetdoor" type="button"
      data-shscreen="shadowsettings">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="1.7" aria-hidden="true"><circle cx="12" cy="12" r="3"/>
        <path d="M19.9 14.6a1.7 1.7 0 0 0 .34 1.87l.06.06a2.06 2.06 0 1 1-2.92 2.92
          l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.55v.18a2.06 2.06 0 0 1-4.12 0
          v-.1a1.7 1.7 0 0 0-1.11-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2.06 2.06 0 1 1-2.92-2.92
          l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1.03h-.18a2.06 2.06 0 0 1 0-4.12
          h.1a1.7 1.7 0 0 0 1.55-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2.06 2.06 0 1 1 2.92-2.92
          l.06.06a1.7 1.7 0 0 0 1.87.34h.08A1.7 1.7 0 0 0 9.9 4.52v-.18a2.06 2.06 0 0 1 4.12 0
          v.1a1.7 1.7 0 0 0 1.03 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2.06 2.06 0 1 1 2.92 2.92
          l-.06.06a1.7 1.7 0 0 0-.34 1.87v.08a1.7 1.7 0 0 0 1.55 1.03h.18a2.06 2.06 0 0 1 0 4.12
          h-.18a1.7 1.7 0 0 0-1.55 1.03z"/></svg>
      <span>Shadow Settings</span></button>
  </nav>`;
}

/* ---- assignment cards ---------------------------------------------------
   Priority is outcome, then state, then supporting metadata -- exactly the
   existing fields, arranged. Blocked cards keep their real action buttons. */
const SH_PILL = { working: "Working", verifying: "Verifying",
                  blocked: "Needs you", done: "Verified",
                  stopped: "Stopped", draft: "Draft",
                  queued: "Queued", paused: "Paused" };

function shadowAssignmentHtml(g){
  const state = String(g.state || "");
  const acts = (state === "blocked" && typeof goalActions === "function")
    ? goalActions("blocked", g) : [];
  const why = state === "blocked" && g.block_reason
    && typeof goalBlockerCopy === "function"
    ? goalBlockerCopy(g.block_reason) : "";
  const line = why || shadowActivityLine(g);
  return `<article class="shasg shasg-${esc(state)}"
    data-goalopen="${escAttr(g.id)}">
    <div class="shasgmark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="1.6"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10
        a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg></div>
    <div class="shasgmain">
      <h3 class="shasgtitle">${esc(g.outcome || "")}</h3>
      ${line ? `<div class="shasgsub">${esc(line)}</div>` : ""}
      ${g.checks_label ? `<div class="shasgmeta">
        <span>${esc(g.checks_label)}</span>
        ${g.attempt ? `<span>attempt ${esc(String(g.attempt))}</span>` : ""}
      </div>` : ""}
      ${acts.length ? `<div class="shasgacts">${acts.map(a => `
        <button class="btn ${a.pri ? "pri " : ""}" type="button"
          data-goalact="${escAttr(a.act)}"
          data-goalid="${escAttr(g.id)}">${esc(a.label)}</button>`)
        .join("")}</div>` : ""}
    </div>
    <div class="shasgside">
      <span class="shstatus shstatus-${esc(state)}">
        <span class="shstatusdot" aria-hidden="true"></span>
        ${esc(SH_PILL[state] || state)}</span>
      ${g.turn_label ? `<span class="shasgturn">${
        esc(g.turn_label)}</span>` : ""}
    </div>
    ${SH_ICON_CHEV}
  </article>`;
}

/* the same cap Shadow Home has always used for the long tail */
const SH_HOME_GOAL_CAP = 8;

/* Groups are the EXISTING states, arranged -- no filter, no new ordering. */
function shadowGroupHtml(title, sub, rows){
  if (!rows.length) return "";
  return `<section class="shgroup">
    <div class="shgrouphead">
      <h2 class="shgrouptitle">${esc(title)}</h2>
      <div class="shgroupsub">${esc(sub)}</div>
    </div>
    ${rows.map(shadowAssignmentHtml).join("")}
  </section>`;
}

function shadowDeckHtml(){
  const { all, needs, running, rest } = shadowBriefCounts();
  if (!all.length) return "";
  const active = needs.concat(running);
  /* the cap is on the REMAINDER as a whole, exactly as before -- splitting
     it into two groups must not quietly let 20 completed rows onto Home */
  const shownRest = rest.slice(0, SH_HOME_GOAL_CAP);
  const hidden = rest.length - shownRest.length;
  const doneRows = shownRest.filter(g => g.state === "done");
  const other = shownRest.filter(g => g.state !== "done");
  const legend = [["Working", running.length], ["Needs you", needs.length],
                  ["Verified", rest.filter(g => g.state === "done").length]]
                 .filter(r => r[1]);
  return `<section class="shdeck">
    <div class="shdeckhead">
      <div>
        <h2 class="shdecktitle">Shadow’s Work</h2>
        <div class="shdecksub">${esc(String(all.length))} assignment${
          all.length === 1 ? "" : "s"}</div>
      </div>
      ${legend.length ? `<div class="shlegend">
        <span class="shlegenditem on">All <b>${
          esc(String(all.length))}</b></span>
        ${legend.map(([k, n]) => `<span class="shlegenditem">${esc(k)} <b>${
          esc(String(n))}</b></span>`).join("")}
      </div>` : ""}
    </div>
    ${shadowGroupHtml("Active", "In flight, or waiting on you.", active)}
    ${shadowGroupHtml("Recently completed", "These are finished and verified.",
                      doneRows)}
    ${shadowGroupHtml("Not running", "Drafted, paused or stopped.", other)}
    ${hidden > 0 ? `<button class="btn shgoalmore" type="button"
      data-shgoals="1">${hidden} more — open all goals</button>` : ""}
  </section>`;
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
  /* THE ASSIGNMENT DECK IS NOT RENDERED HERE.
     shadowDeckHtml() -- "Shadow's Work", the assignment count, "Recently
     completed" and the goal cards -- is a GLOBAL history of every goal, and
     this workspace is one delegated task. It is untouched, still built, still
     tested, and still the goals screen's content; the left list is where
     Shadow's tasks live and Chats is where conversation history lives.

     Its one live hook, data-shgoals, moved to the footer nav below so the
     goals screen keeps exactly the reachability it had -- the deck's "N more"
     button was the only route to it. */
  /* TWO COLUMNS (Focus › Shadow). Every element the briefing had is still
     rendered by the same function it always was -- the mast, the scope
     picker and composer (shadowStageHtml, which carries the existing-chat
     "Working with" flow), the foot nav, the thread, the goal deck. They have
     moved column, not changed behaviour, and no hook was renamed.

     LEFT is the inventory and the one new action. RIGHT is the single task in
     focus, the conversation, and everything that was already there. */
  const sel = shadowSelectedTask();
  const newOpen = !!S.shadowNewOpen;
  /* THE EXISTING-CHAT FLOW IS OPT-IN HERE, not deleted. Off, this workspace
     is about one delegated task; on, shadowStageHtml renders the target
     picker, the recent chats and the briefing copy exactly as it always has.
     Preserving the behaviour is not the same as rendering it everywhere. */
  const existing = !!S.shadowExistingOpen;
  const face = sel ? shadowTaskFaceFor(sel) : null;
  return `<div class="shwork">
    <aside class="shwleft">
      <button class="shdelegate${newOpen ? " on" : ""}" type="button"
        data-shdelegate="1">+ Delegate</button>
      <div class="shwlabel">Shadow is working on</div>
      <div class="shtasks">${shadowTaskListHtml()}</div>
      <div class="shwfoot">${shadowNavHtml()}</div>
    </aside>
    <section class="shwright">${err}
      <header class="shwhead">
        <span class="shwseal" aria-hidden="true">S</span>
        <h2 class="shwtitle">${newOpen ? "New task"
          : esc((sel && sel.objective) || "Shadow")}</h2>
        ${!newOpen && face ? `<span class="shtpill shtpill-${esc(face.cls)}"
          >${esc(face.label)}</span>` : ""}
      </header>
      ${newOpen ? shadowDelegatePanelHtml()
                : (sel ? shadowTaskCardHtml(sel) : "")}
      ${thread ? `<div class="shthread">${thread}</div>` : ""}
      ${existing ? `<div class="shexwrap">
        <button class="shexback" type="button" data-shexisting="0"
          >← Back to tasks</button>
        ${shadowStageHtml()}
      </div>` : shadowWorkComposerHtml()}
    </section>
  </div>`;
}

/* ── ONE READ AT A TIME (perf fold 2026-09-13) ───────────────────────────
   SCREENS.shadow calls loadShadowHome() from inside render(), and render()
   runs many times a second -- every SSE frame and every scheduleRender tick.
   Nothing stopped a second read starting while the first was still in the
   air, so entering Shadow Home against a backend that is not instant issued
   SIX requests PER PAINTED FRAME: measured 42 reads for one arrival, and the
   bursts kept landing after the operator had already navigated away, because
   the five parallel reads only start once /status has answered.

   Two rules fix it, and neither is a cache: the DATA is still read from the
   server every time somebody asks for it.

     1. coalesce -- a read already in flight is handed to the next caller
        instead of starting a second one.
     2. abandon  -- a LAZY read (the one render started) stops the moment the
        operator leaves the screens that display it, BEFORE it writes any
        S.shadow* state, so coming back reads again from scratch.

   force=true is for callers that have just CHANGED something and must see
   the result of their own write (the same force flag loadUsage/loadModules
   take): they never coalesce onto a read that may predate the write. */
let _shHomeRead = null;

/* the screens that render what loadShadowHome reads. The overlay card reads
   S.shadowMissions too, but it is repainted by renderShadowCard() after the
   action that changed them -- which is a forced read, so it is never the one
   being abandoned here. */
function shadowHomeOnScreen(){
  const S_ = (typeof S !== "undefined") ? S : {};
  return S_.screen === "shadow" || S_.screen === "shadowwatching";
}

function loadShadowHome(force){
  if (_shHomeRead && !force) return _shHomeRead;
  const p = _loadShadowHome(!force);
  if (!p || typeof p.then !== "function") return p;
  _shHomeRead = p;
  const clear = () => { if (_shHomeRead === p) _shHomeRead = null; };
  p.then(clear, clear);
  return p;
}

async function _loadShadowHome(lazy){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  try {
    const st = await fetch("/api/shadow/status");
    /* left Shadow Home while /status was in the air: the five reads below
       are for a screen nobody is looking at. Return BEFORE any assignment --
       S.shadowHomeDark stays undefined, so the next visit loads properly
       rather than painting a home with no lists in it. */
    if (lazy && !shadowHomeOnScreen()) return;
    if (!st.ok){ S.shadowHomeDark = true;
      if (typeof scheduleRender === "function") scheduleRender(); return; }
    S.shadowHomeDark = false;
    /* diagnosis fold 2026-08-26: a failed GET must NEVER masquerade as an
       empty list -- failure is its own rendered state with a Retry */
    /* goals ride the SAME parallel read the home already does -- the
       overview needs them, and a fourth request here is cheaper than a
       second load path (slice 10) */
    /* settings joins the SAME parallel read (workspace slice): the task card
       names the floors, and reading them is cheaper than a second load path.
       It is NOT part of shadowHomeErr -- a missing settings answer costs one
       advisory line, never the page. */
    const [w, m, i, g, s] = await Promise.all([
      fetch("/api/shadow/watches").then(r => r.ok ? r.json() : null),
      fetch("/api/shadow/missions").then(r => r.ok ? r.json() : null),
      fetch("/api/shadow/instructions").then(r => r.ok ? r.json() : null),
      fetch("/api/shadow/goals").then(r => r.ok ? r.json() : null),
      fetch("/api/shadow/settings").then(r => r.ok ? r.json() : null)
        .catch(() => null),
    ]);
    if (s) S.shadowSettings = s;
    S.shadowHomeErr = !(w && m && i && g);
    if (g) S.goals = g.goals || [];
    if (w) S.shadowWatching = w.watches || [];
    if (m) S.shadowMissions = m.missions || [];
    if (i) S.shadowMemory = i.instructions || [];
    if (typeof scheduleRender === "function") scheduleRender();
  } catch (e){ S.shadowHomeDark = true;
    if (typeof scheduleRender === "function") scheduleRender(); }
}

/* Coalesced for the reason loadShadowHome is: SCREENS.shadowsettings asks
   for this from inside render(), so every frame painted while the answer was
   outstanding started another identical GET. */
let _shSettingsRead = null;

function loadShadowSettings(force){
  if (_shSettingsRead && !force) return _shSettingsRead;
  const p = _loadShadowSettings();
  if (!p || typeof p.then !== "function") return p;
  _shSettingsRead = p;
  const clear = () => { if (_shSettingsRead === p) _shSettingsRead = null; };
  p.then(clear, clear);
  return p;
}

async function _loadShadowSettings(){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  try {
    const r = await fetch("/api/shadow/settings");
    S.shadowSettings = r.ok ? await r.json() : null;
  } catch (e){ S.shadowSettings = null; }
  if (typeof scheduleRender === "function") scheduleRender();
}

/* ── SHADOW SETTINGS ─────────────────────────────────────────────────────
   Design of record: website/preview/shadow-v7.html (commit c4ac22df) -- the
   full-screen settings the v7 mock draws. Its shape is reproduced here:
   back / seal / "Shadow" header, then a centred 600px column of sections,
   each a heading over hairline-separated rows, no explainer copy.

   WHAT IS AND IS NOT BUILT. The mock draws thirteen controls. Four have a
   store behind them today and those are the four here -- floors, memory
   rules, the delegate kinds, and attention -- every one read from the
   endpoint that already serves them (/api/shadow/settings). The other nine
   (autonomy level, "ask before the top tier", concurrency, per-task budget,
   quiet hours, nudges per hour, corner card, hide-for-this-app, and the
   add-a-control chat row) have NO backing: no field, no endpoint, no writer.
   The mock's own status table marks them "v7 to build". They are left out
   rather than drawn inert, because a toggle that silently does nothing is a
   worse lie than an absent one, and rather than invented here, because a
   second settings store is exactly what this page must not become.

   REACHABILITY. Attention carries Watching, Goals and Conversations. The
   workspace footer is one door now, and these are the rooms behind it --
   same hooks (data-shwatching / data-shgoals / data-shchats), same screens,
   same handlers. Nothing was removed; it moved one level in. */
function shadowSettingsSecHtml(head, body){
  return `<section class="ssec"><h3 class="ssh">${esc(head)}</h3>${body}</section>`;
}

/* AUTONOMY, to the design of record (website/preview/shadow-v7.html .ssec
   "Autonomy"): the four-level selector in one rounded well, the top-tier
   confirm toggle, then the floor pills.

   HONEST ABOUT WHAT SAVES. The floors are real -- the server holds them and
   they are the one part of autonomy that is enforced (SHADOW.md section 2:
   never ledger-overridable). The LEVEL and the TOGGLE have no field, no
   endpoint and no writer anywhere in this build; the mock's own status table
   marks them "v7 to build". Founder asked for the section to match the
   reference, so it is drawn exactly as drawn -- L3 selected, the toggle on --
   and deliberately carries NO action hook: nothing here posts, and nothing
   pretends to remember a choice it cannot keep. When the store lands, the
   controls gain a data- attribute and this comment goes. */
const SH_LEVELS = [["L0", "Watch"], ["L1", "Suggest"],
                   ["L2", "Draft"], ["L3", "Act"]];
/* what the build actually runs at. A constant, not a stored preference --
   naming it here keeps the one place a future setting would be read. */
const SH_LEVEL_NOW = "L3";

function shadowSetAutonomyHtml(d){
  const seg = SH_LEVELS.map(([lv, name]) => {
    const on = lv === SH_LEVEL_NOW;
    return `<button type="button" role="tab"${on ? ' class="on"' : ""}
      aria-selected="${on}" aria-disabled="true" tabindex="-1"
      title="Not configurable yet"><span class="lv">${esc(lv)}</span>${
      esc(name)}</button>`;
  }).join("");
  const floors = (d.floors || []).filter(Boolean);
  return `<div class="seg" role="tablist" aria-label="Autonomy level">${seg}</div>
    <div class="srow"><span class="k">Ask me before the very top tier</span>
      <span class="tog" role="switch" aria-checked="true" aria-disabled="true"
        title="Not configurable yet"></span></div>
    <div class="srow">${floors.length
      ? `<span class="floorbar">${floors.map(f => `<span><span class="lk"
          aria-hidden="true">\ud83d\udd12</span>${esc(f)}</span>`).join("")}</span>`
      : `<span class="ssempty">No floors were reported.</span>`}</div>
    <p class="ssnote">Floors are confirm-first, always \u2014 Shadow cannot be
      talked out of them, and they are not editable here.</p>`;
}

/* Memory: the confirmed instructions, global first, then per chat. The row
   is the mock's .rule -- scope pill, the text, and the × that revokes. It
   uses the EXISTING revoke hook, so this is the same action the memory list
   has always offered, wearing the design's row. The text is NOT editable:
   there is no amend endpoint, and a field that silently discards what was
   typed is worse than a read-only one. */
function shadowSetRuleHtml(scope, glob, r){
  return `<div class="rule">
    <span class="rscope${glob ? " glob" : ""}">${esc(scope)}</span>
    <span class="rtext">${esc((r && r.text) || "")}</span>
    <button class="rx" type="button" data-shrevoke="${escAttr((r && r.id) || "")}"
      title="Revoke this" aria-label="Revoke this">\u00d7</button>
  </div>`;
}

function shadowSetMemoryHtml(d){
  const rows = [];
  for (const r of (d.global || [])) rows.push(shadowSetRuleHtml("global", true, r));
  for (const key of Object.keys(d.per_chat || {}))
    for (const r of (d.per_chat[key] || []))
      rows.push(shadowSetRuleHtml(shadowChatLabel(key), false, r));
  if (!rows.length)
    return `<div class="ssempty">Shadow has learned nothing yet. Confirmed
      instructions appear here.</div>`;
  return rows.join("");
}

/* TASKS, to the design of record's .ssec "Tasks": Running at once as a
   stepper, Budget per task as a value with the AUTO pill, and Delegate
   offers as removable chips with "+ add".

   THE TWO NUMBERS ARE REAL. running_at_once is mission_engine.MAX_RUNNING --
   the cap MissionScheduler actually enforces before it queues -- and the
   budget is TEMPLATES[kind].max_turns, which is what a mission is created
   with and what fails it when spent. Both now ride the settings endpoint
   that was already being read, so this page states the limits the engine
   keeps rather than a number that merely looks right.

   AUTO IS LITERALLY TRUE HERE: the budget is not a preference, it is chosen
   by the kind of work. The pill says so, and the row names the kind it is
   quoting rather than implying one number governs every task.

   WHAT DOES NOT WRITE. The stepper's -/+, the chips' x and "+ add" are drawn
   because the reference draws them, and carry NO action hook: there is no
   writer for any of the three, and a control that answers a click by doing
   nothing is worse than one that says it cannot yet. Same rule the Autonomy
   section follows. */
function shadowSetTasksHtml(d){
  const t = (d && d.tasks) || {};
  const run = t.running_at_once;
  const budgets = t.turn_budget || {};
  /* the kind Delegate opens on is the one whose budget this row quotes --
     read from the draft's own default, never a second copy of it */
  const kind = (shadowNewDraft().kind) || SH_KINDS[0];
  const turns = budgets[kind];
  const dead = ' aria-disabled="true" tabindex="-1" title="Not configurable yet"';
  const stepper = run === undefined
    ? `<span class="ssempty">not reported</span>`
    : `<span class="step"><button type="button"${dead
        } aria-label="fewer">\u2212</button><span class="val">${
        esc(String(run))}</span><button type="button"${dead
        } aria-label="more">+</button></span>`;
  const budget = turns === undefined
    ? `<span class="ssempty">not reported</span>`
    : `<span><span class="ev">${esc(String(turns))}</span> turns
        <span class="auto" title="set by the kind of work, not by you"
          >auto</span></span>`;
  return `<div class="srow"><span class="k">Running at once</span>${stepper}</div>
    <div class="srow"><span class="k">Budget per task</span>${budget}</div>
    <div class="srow"><span class="k" style="flex:none">Delegate offers</span>
      <span class="chips">${SH_KINDS.map(k => `<span class="chip"${
        budgets[k] === undefined ? "" : ` title="${escAttr(
          budgets[k] + " turns")}"`}>${esc(k)}<span class="cx"${dead
        } aria-hidden="true">\u00d7</span></span>`).join("")}
        <button class="chipadd" type="button"${dead}>+ add</button>
      </span></div>`;
}

/* PRESENCE, to the design of record's .ssec "Presence", then the
   "Add a control" bar below it.

   TWO OF THESE ARE REAL, and they are the two the overlay has always had:
   the corner card's hide-for-this-session (S.shadowHideSession, the card's
   own "hide" control) and quiet (S.shadowQuiet, which gates showNudge at
   15-shadow-overlay.js). Both are wired here to the SAME flags the card
   toggles -- one state, two places to reach it, no copy. They are
   memory-only, exactly as they are today; this does not make them durable
   and does not pretend to.

   NUDGES PER HOUR is read from SH_PILLS_PER_HOUR, the rate pillAllowed
   actually enforces. Stated, not settable: there is no writer.

   QUIET HOURS has nothing behind it -- no field, no clock, no scheduler --
   so the row renders with the value it truly has, which is none, and
   without the AUTO pill. AUTO on this row would claim something chose those
   hours; nothing did. The reference's "9pm to 8am" is mock copy.

   ADD A CONTROL is drawn and inert for the same reason the steppers are:
   there is nowhere for a new control to be kept. */
function shadowSetPresenceHtml(){
  const S_ = (typeof S !== "undefined") ? S : {};
  const dead = ' aria-disabled="true" tabindex="-1" title="Not configurable yet"';
  const card = !S_.shadowHideSession;      /* shown unless hidden this session */
  const quiet = !!S_.shadowQuiet;
  const tog = (on, attr) => `<span class="tog${on ? "" : " off"}" role="switch"
    aria-checked="${on}" tabindex="0" ${attr}></span>`;
  const rate = (typeof SH_PILLS_PER_HOUR !== "undefined")
    ? SH_PILLS_PER_HOUR : null;
  return `<div class="srow"><span class="k">Corner card on every screen</span>
      ${tog(card, 'data-shpresence="card"')}</div>
    <div class="srow"><span class="k">Quiet hours</span>
      <span><span class="ev">not set</span></span></div>
    <div class="srow"><span class="k">Nudges per hour</span>${rate === null
      ? `<span class="ssempty">not reported</span>`
      : `<span class="step"><button type="button"${dead
          } aria-label="fewer">\u2212</button><span class="val">${
          esc(String(rate))}</span><button type="button"${dead
          } aria-label="more">+</button></span>`}</div>
    <div class="srow"><span class="k">Hide for this app</span>
      ${tog(quiet, 'data-shpresence="quiet"')}</div>`;
}

function shadowSetAddHtml(){
  return `<div class="addbar">
    <span class="sp" aria-hidden="true">\u25cf</span>
    <input type="text" disabled
      placeholder="Tell Shadow what to add \u2014 e.g. Pause on weekends"
      aria-label="Add a control" title="Not configurable yet">
    <button class="go" type="button" aria-disabled="true" tabindex="-1"
      title="Not configurable yet" aria-label="add">\u2192</button>
  </div>`;
}

/* Attention: the counts the endpoint already returns, and the way back into
   the three screens the workspace footer used to list. */
function shadowSetAttentionHtml(d){
  const S_ = (typeof S !== "undefined") ? S : {};
  const a = d.attention || {};
  const goals = ((S_.goals || []).filter(g => g &&
    ["draft", "working", "verifying", "blocked"].includes(g.state))).length;
  const link = (attr, label, n) => `<button class="btn ssgo" type="button" ${attr}
    >${esc(label)}${n === null ? "" : " \u00b7 " + esc(String(n))}</button>`;
  return `<div class="srow"><span class="k">Overseen</span>
      <span class="v">${esc(String((a.watching || []).length))} watched \u00b7 ${
      esc(String((a.off || []).length))} off \u00b7 ${
      esc(String(a.alerts || 0))} waiting</span></div>
    <div class="srow"><span class="k">Where it looks</span><span class="ssgos">
      ${link('data-shwatching="1"', "Watching", (a.watching || []).length)}
      ${link('data-shgoals="1"', "Goals", goals)}
      ${link('data-shchats="1"', "Conversations", null)}
    </span></div>`;
}

function shadowSettingsHtml(){
  const d = (typeof S !== "undefined" && S.shadowSettings) || null;
  const head = `<header class="sshead">
    <button class="ssback" type="button" data-shscreen="shadow"
      title="Back to Shadow" aria-label="Back to Shadow">\u2190</button>
    <span class="ssmark" aria-hidden="true"><b>S</b></span>
    <h2 class="sstitle">Shadow</h2>
  </header>`;
  if (!d) return `<div class="shset">${head}
    <div class="ssbody"><div class="sswrap">
      <div class="zero"><h4>Shadow settings</h4>
      <p>Could not read the rules just now.
      <button class="btn" type="button" data-shsetreload="1">Retry</button></p>
      </div></div></div></div>`;
  return `<div class="shset">${head}
    <div class="ssbody"><div class="sswrap">
      ${shadowSettingsSecHtml("Autonomy", shadowSetAutonomyHtml(d))}
      ${shadowSettingsSecHtml("Memory", shadowSetMemoryHtml(d))}
      ${shadowSettingsSecHtml("Tasks", shadowSetTasksHtml(d))}
      ${shadowSettingsSecHtml("Presence", shadowSetPresenceHtml())}
      <section class="ssec addset"><h3 class="ssh">Add a control</h3>${
        shadowSetAddHtml()}</section>
      ${shadowSettingsSecHtml("Attention", shadowSetAttentionHtml(d))}
    </div></div>
  </div>`;
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

/* LIVE WHILE YOU WATCH, WITHOUT THE STORM (founder, 2026-09-15).

   THE BUG. Shadow blocked a mission and attached a founder intervention
   while the founder was already looking at it. The card went on saying
   RUNNING until the page was refreshed, because this screen read ONCE:
   `S.shadowHomeDark === undefined` is true only on first paint, and
   S.shadowMissions is written in exactly one place (_loadShadowHome). No
   poll, no subscription, and the session SSE carries transcripts only --
   so nothing on the client ever learned the mission had blocked.

   WHY IT WAS ONCE-ONLY. The 2026-09-13 perf fold was fixing a real storm:
   render() runs many times a second and called this on every frame --
   measured at SIX requests per painted frame, 42 reads for one arrival. It
   fixed that by making the read once-only, and the live updates went with
   it.

   THE THROTTLE IS THE MIDDLE GROUND, and it is the idiom already used twice
   in this file's neighbourhood (goalTranscriptAt, SH_TRANSCRIPT_MS): at most
   ONE read every SH_HOME_POLL_MS, never one per frame. The storm cannot
   recur -- 4s is two orders of magnitude off the frame rate -- and nothing
   about the read itself changed:

     * loadShadowHome() without `force` still hands back an in-flight read
       rather than starting a second one;
     * _loadShadowHome(lazy) still returns BEFORE any assignment if the
       operator navigated away while /status was in the air;
     * SCREENS.shadow is only called for the ACTIVE screen (06-render.js),
       so a founder who is not looking at Shadow pays nothing.

   First paint is untouched, and it stamps the clock so the very next render
   does not immediately fire a second, redundant read. */
const SH_HOME_POLL_MS = 4000;
let shHomeAt = 0;

/* THE DRIVER, BECAUSE THERE IS NO RENDER LOOP TO RIDE (founder dogfood,
   2026-09-15, second failure).

   The throttle above was necessary and not sufficient. It only runs when
   SCREENS.shadow() runs, SCREENS.shadow() only runs when render() runs, and
   render() is NOT a loop -- scheduleRender() is a one-shot 100ms debounce
   fired by events (a keystroke, a frame into an OPEN pane, a finished
   fetch). A founder watching a headless delegate generates none of those:
   the delegate chat is opt-in and closed, the session SSE re-reads open
   panes only, and the two 1s intervals in this app (tickRunStrips,
   updTick) neither call render() nor are active here. So the refresh was
   self-extinguishing -- it repainted when something changed, and nothing
   changed because nothing repainted.

   This is the missing heartbeat, and it is deliberately NOT render(): it
   calls loadShadowHome() directly, whose completion already calls
   scheduleRender(). render() keeps its existing event-driven contract.

   SELF-CLEARING, the same shape ensureRunTicker already uses in
   01-state.js: the tick itself checks whether the screen is still showing
   and clears its own interval when it is not, so a founder who navigates
   away pays nothing and no second timer can accumulate. shadowHomeOnScreen()
   is the EXISTING predicate _loadShadowHome already uses for its lazy
   abandon.

   No storm is possible: one read per SH_HOME_POLL_MS, from a timer, fully
   decoupled from frame rate -- which is what the 2026-09-13 perf fold was
   protecting (six requests per painted frame). loadShadowHome() also still
   coalesces, so even a burst cannot produce overlapping reads. */
let _shHomeTicker = null;

function ensureShadowHomeTicker(){
  if (_shHomeTicker || typeof setInterval === "undefined") return;
  _shHomeTicker = setInterval(() => {
    if (!shadowHomeOnScreen()){
      if (typeof clearInterval === "function") clearInterval(_shHomeTicker);
      _shHomeTicker = null;
      return;
    }
    try { loadShadowHome(); } catch (e) {}
  }, SH_HOME_POLL_MS);
}

if (typeof SCREENS !== "undefined"){
  SCREENS.shadow = () => {
    ensureShadowHomeTicker();
    const now = (typeof Date !== "undefined") ? Date.now() : 0;
    if (typeof S !== "undefined" && S.shadowHomeDark === undefined){
      shHomeAt = now;
      loadShadowHome();
      return `<div class="zero"><h4>Shadow</h4><p>Looking\u2026</p></div>`;
    }
    if (now - shHomeAt >= SH_HOME_POLL_MS){
      shHomeAt = now;
      loadShadowHome();
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
        S.shadowScopeErr = null;          /* ...and answers the one complaint */
      }
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    /* THE WHOLE DOOR IS THE CONTROL (founder, 2026-09-13: "it doesn't open,
       at least immediately anyway").

       It was not slow -- it was DEAD for most of its own surface. The button
       shadowNavHtml draws wraps an <svg> gear and a <span>Shadow Settings</span>
       and they fill it, but this handler read ev.target.dataset, so clicking
       the LABEL or the ICON -- everything a person actually aims at -- hit a
       child with no dataset and the branch never fired. Only the few px of
       padding between the two children carried the hook, which is why it
       opened on some clicks and ignored others.

       Read through closest(), the same way [data-shtask] just above and the
       rail's own [data-open] (07-loaders.js) have always done. No markup and
       no style changed; "<- Back to Shadow" keeps working as before, since a
       button whose only child is a text node was already its own target. */
    const doorEl = (ev.target && ev.target.closest)
      ? ev.target.closest("[data-shscreen]") : null;
    const shscreen = d.shscreen || (doorEl && doorEl.dataset.shscreen) || "";
    if (shscreen){
      if (typeof openScreen === "function") openScreen(shscreen);
      else if (typeof S !== "undefined") S.screen = shscreen;
      /* The door does NOT read the settings (perf fold 2026-09-13). It used
         to call loadShadowSettings() on every shscreen click -- including
         "<- Back to Shadow", which does not show them -- and the settings
         screen then asked for the same endpoint again from its own lazy
         loader. One gesture, two identical GETs, before the render loop
         multiplied either of them.

         SCREENS.shadowsettings is the one load path now. The single thing
         the unconditional call really bought is kept: a read that FAILED
         (null) is cleared here, so leaving and coming back retries, exactly
         as it has always done. A read that SUCCEEDED is reused -- Shadow
         Home already put it in S.shadowSettings on its way past. */
      if (typeof S !== "undefined" && S.shadowSettings === null)
        delete S.shadowSettings;
      if (typeof render === "function") render();
      return;
    }
    if (d.shreload){
      if (typeof loadShadowHome === "function") loadShadowHome(true); return; }
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
    /* THE WHOLE ARROW IS THE CONTROL (founder, 2026-09-13). The send button
       is a <button data-shsend="1"> whose ONLY child is the arrow <svg>, and
       the svg covers all of it -- so a dataset read on ev.target matched
       nothing a person could actually hit and the arrow was dead: measured
       zero POSTs, the typed text left sitting in the box. Enter worked, the
       arrow never did.

       Resolved through closest(), the same cure as [data-shtask] and the
       settings door. There is still exactly ONE submit -- both the arrow and
       Enter call shadowSubmitCompose, which is the only path to
       sendToShadow. No second submission path, no markup change. */
    const sendEl = (ev.target && ev.target.closest)
      ? ev.target.closest("[data-shsend]") : null;
    if (d.shsend || sendEl){
      shadowSubmitCompose(document.querySelector
        && document.querySelector("[data-shhomecompose]"));
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
    /* reveal or re-collapse the worker transcript, in place. Presentation
       only: no read, no write, no mission state -- the next render decides
       whether to draw the block, and drawing it is what triggers the
       existing throttled transcript fetch. */
    if (d.shtaskchat){
      S.shadowTaskChatOpen =
        (S.shadowTaskChatOpen === d.shtaskchat) ? null : d.shtaskchat;
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    /* Copy result. Resolved through closest() for the same reason the send
       arrow and the settings door are -- a click that lands on anything
       inside the button must still be the button. */
    const copyEl = (ev.target && ev.target.closest)
      ? ev.target.closest("[data-shcopydone]") : null;
    const copyMid = d.shcopydone
      || (copyEl && copyEl.dataset && copyEl.dataset.shcopydone) || "";
    if (copyMid){ shadowCopyResult(copyMid); return; }
    if (d.shtakeover){
      /* navigation, never mutation: land the founder where the delegate
         session can be resumed by hand */
      if (typeof shadowRouteDeepLink === "function")
        shadowRouteDeepLink("sutra://session/" + d.shtakeover);
      else if (typeof goDest === "function") goDest("chats");
      return;
    }
    /* ── + Delegate ─────────────────────────────────────────────────────── */
    if (d.shdelegate){
      if (typeof S !== "undefined"){
        S.shadowNewOpen = !S.shadowNewOpen;
        S.shadowNewErr = null;
      }
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    if (d.shnewcancel){
      if (typeof S !== "undefined"){ S.shadowNewOpen = false; S.shadowNewErr = null; }
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    if (d.shnewkind){
      shadowNewDraft().kind = d.shnewkind;
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    if (d.shnewcreate){ shadowCreateTask(); return; }
    /* the existing-chat flow: entered and left explicitly. Nothing about it
       changes -- only whether the delegated-task workspace is showing it. */
    if (d.shexisting !== undefined){
      if (typeof S !== "undefined"){
        S.shadowExistingOpen = d.shexisting === "1";
        if (S.shadowExistingOpen){
          S.shadowNewOpen = false;
          S.shadowScopeErr = null;
          /* THE FLOW IS BOUND TO THE CHAT THE FOUNDER IS IN (founder,
             2026-09-13 -- "nothing happens"). It was not: entering the flow
             left S.shadowChat at "global", sendToShadow drops scope_id for
             "global", and the turn went out with no target at all. Shadow
             then answered that "global" is not a chat, so no mission was
             proposed, nothing took the chat over, and the founder saw a
             dead Enter.

             The open pane IS the existing chat -- the same S.openPanes the
             rail and the panes render from, newest last.

             SEEDED ON EVERY ENTRY (founder, 2026-09-13). It used to seed
             only a scope that was still unset, which meant the FIRST chat
             the flow was ever opened from became the permanent target:
             open chat A, use the flow, then open chat B and come back, and
             the turn still went out scoped to A -- measured live. The flow
             must target the chat the founder is actually in, so entering it
             re-resolves the target every time.

             A chip picked by hand still wins: this runs only when the flow
             is ENTERED, never on a render, so a pick made inside the flow
             stands until the founder leaves and comes back. With no pane
             open nothing is seeded and the composer says which control is
             missing, rather than sending an unscoped turn. Nothing is
             created here: this picks the target, it does not start work. */
          const panes = S.openPanes || [];
          const sid = panes[panes.length - 1];
          if (sid) S.shadowChat = sid;
        }
      }
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    /* picking a task in the left column only changes what the right pane
       shows -- it starts nothing and writes nothing.

       THE WHOLE ROW IS THE CONTROL (founder, 2026-09-13). Read through
       closest(), not off ev.target: the row is a <button> wrapping three
       spans (the dot, the name, the pill) and they fill it, so a dataset
       read on the event target matched only the few px of padding the spans
       do not cover. Clicking the task NAME -- the obvious target -- did
       nothing at all, and a dead click reads as a slow one.

       Same pattern as the rail's own [data-open] (07-loaders.js), which has
       always done this. `data-shtaskcard` does not match `[data-shtask]` --
       attribute selectors are exact -- so the right pane's card is
       untouched, and no markup or style changed here. */
    /* REMOVE, and it is checked BEFORE the row selector on purpose: the
       delete control sits inside the row, so a click on it is also a click
       in the row, and selecting the task on the way to deleting it would be
       a pointless repaint. Attribute selectors are exact, so [data-shtaskdel]
       and [data-shtask] never match each other's element -- the order here
       decides which one wins when both are in the ancestor chain. */
    const close = (sel) => (ev.target && ev.target.closest)
      ? ev.target.closest(sel) : null;
    /* ONE CLICK DELETES (founder, 2026-09-14). × used to turn the row into
       "Delete? Yes / No" in place -- the gesture the Agents rail uses. In the
       task list that ask rendered UNDERNEATH neighbouring Shadow UI, so the
       Yes it demanded could not reliably be hit and the delete was, in
       practice, unreachable. A destructive control the founder cannot
       complete is worse than one that needs no second click, so the ask is
       gone: × deletes. Nothing below it changed -- the same
       shadowDeleteTask, the same single POST to the existing /act endpoint,
       the same server-side erase, and the chat Shadow drove is still left
       alone in Chats. A browser confirm() is NOT the fallback: it blocks the
       Electron window (17-agents.js, founder 2026-09-10). */
    const delRow = close("[data-shtaskdel]");
    if (delRow){
      if (ev.stopPropagation) ev.stopPropagation();
      shadowDeleteTask(delRow.dataset.shtaskdel);
      return;
    }
    const taskRow = (ev.target && ev.target.closest)
      ? ev.target.closest("[data-shtask]") : null;
    if (taskRow){
      if (typeof S !== "undefined"){
        S.shadowTaskSel = taskRow.dataset.shtask;
        S.shadowNewOpen = false;
      }
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    /* the driven chat's own strip. Both go through the SAME mission action
       path every other Shadow control uses -- no second write surface. After
       either, the chat's row is re-read, so the composer unlocks (take over)
       or the strip disappears (stop) without a reload. */
    if (d.shtakeoverchat || d.shstopchat){
      const mid = d.shtakeoverchat || d.shstopchat;
      const act = d.shtakeoverchat ? "take_over" : "stop";
      shadowMissionAct(mid, act).then(() => {
        if (typeof loadSessions === "function") loadSessions();
      });
      return;
    }
    /* THE SIGN-OFF. The existing mission action, with the index the engine
       stores the check under -- no new endpoint, no new state, and the same
       shadowMissionAct that already nudges "Check confirmed." and re-reads
       the home. Confirming the LAST check settles the mission server-side
       (api_shadow_mission_act -> settle_confirmation), so that re-read is
       also what moves the row out of the list. */
    /* PRESENCE: the SAME two flags the overlay card toggles, reached from
       settings. Nothing new is stored -- hide re-mounts or removes the dot
       exactly as the card's own control does, and mountShadowOverlay is
       already a no-op when a dot exists. */
    if (d.shpresence){
      if (typeof S !== "undefined"){
        if (d.shpresence === "quiet"){
          S.shadowQuiet = !S.shadowQuiet;
        } else if (d.shpresence === "card"){
          S.shadowHideSession = !S.shadowHideSession;
          if (S.shadowHideSession){
            S.shadowCardOpen = false;
            const dot = typeof document !== "undefined" && document.querySelector
              && document.querySelector(".shdot");
            if (dot && dot.remove) dot.remove();
            if (typeof renderShadowCard === "function") renderShadowCard();
          } else if (typeof mountShadowOverlay === "function"){
            mountShadowOverlay();
          }
        }
      }
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    if (d.shcheckmid !== undefined && d.shcheckix !== undefined)
      return shadowMissionAct(d.shcheckmid, "confirm_check",
                              { index: Number(d.shcheckix) });
    /* THE INTERVENTION FORM. Its option buttons write the draft and repaint;
       only Send talks to the server. confirm_check above is untouched and
       stays a separate flow, exactly as it was. */
    if (d.shivopt && d.shivmid && d.shivkey){
      const S_ = (typeof S !== "undefined") ? S : {};
      const mm = (S_.shadowMissions || []).find(x => x && x.id === d.shivmid);
      const fld = ((mm && mm.intervention && mm.intervention.fields) || [])
        .find(f => f && f.key === d.shivkey);
      if (fld){
        const draft = shadowIvDraft(d.shivmid);
        const cur = draft.values[d.shivkey];
        if (fld.type === "boolean"){
          draft.values[d.shivkey] = (d.shivopt === "yes");
        } else if (fld.type === "multi_choice"){
          const list = Array.isArray(cur) ? cur.slice() : [];
          const at = list.indexOf(d.shivopt);
          if (at === -1) list.push(d.shivopt); else list.splice(at, 1);
          draft.values[d.shivkey] = list;
        } else if (fld.type === "ranking"){
          const list = Array.isArray(cur) ? cur.slice() : [];
          const at = list.indexOf(d.shivopt);
          if (at === -1) list.push(d.shivopt); else list.splice(at, 1);
          draft.values[d.shivkey] = list;
        } else {
          draft.values[d.shivkey] = d.shivopt;
        }
        delete draft.errors[d.shivkey];
      }
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    if (d.shivsend) return shadowSendIntervention(d.shivsend);
    if (d.shact && d.shmid) return shadowMissionAct(d.shmid, d.shact);
    if (d.shstart) return shadowMissionAct(d.shstart, "start_now");
    if (d.shunwatch) return shadowWatchSet(d.shunwatch, false);
    if (d.shconfirm) return shadowInstructionAct(d.shconfirm, "confirm");
    if (d.shrevoke) return shadowInstructionAct(d.shrevoke, "revoke");
  });
  /* ONE submit path, two ways to reach it. The design has a send button and
     the composer has always sent on Enter; rather than write the send twice,
     the keydown body moved here verbatim and both callers use it. Nothing
     about what happens on submit changed. */
  function shadowSubmitCompose(el){
    if (!el) return;
    const S_ = (typeof S !== "undefined") ? S : {};
    const text = String(el.value || "");
    /* empty: send nothing AND clear nothing. The box used to empty itself
       on any Enter, so a stray keypress silently ate a half-written brief. */
    if (!text.trim()) return;
    /* THE EXISTING-CHAT FLOW MUST HAVE A CHAT. Without one the turn goes out
       unscoped and Shadow has no transcript to drive -- the founder's dead
       Enter. Say which control is missing instead of sending a turn that
       cannot do what was asked. The delegated composer is untouched: it is
       global on purpose (+ Delegate starts its own chat). */
    if (S_.shadowExistingOpen && (!S_.shadowChat || S_.shadowChat === "global")){
      S_.shadowScopeErr = "Pick the chat Shadow should work in — "
        + "it will not guess which one.";
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    /* never a silent no-op: if the overlay module did not load there is no
       send path, and that is worth saying out loud */
    if (typeof sendToShadow !== "function"){
      S_.shadowScopeErr = "Shadow did not load — reload the app.";
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    S_.shadowScopeErr = null;
    el.value = "";
    sendToShadow(text.trim()).then(() => {
      if (typeof loadShadowHome === "function") loadShadowHome(true);
      if (typeof scheduleRender === "function") scheduleRender();
    });
    if (typeof scheduleRender === "function") scheduleRender();
  }
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && ev.target && ev.target.dataset
        && ev.target.dataset.shhomecompose){
      ev.preventDefault && ev.preventDefault();
      shadowSubmitCompose(ev.target);
    }
  });
  /* The new-task fields keep what is typed across the background re-renders
     the session stream causes. Stored, NEVER re-rendered on keystroke: a
     render per character would fight the caret, which is the bug the
     composer's own text store exists to avoid. */
  document.addEventListener("input", (ev) => {
    const t = ev.target, d = (t && t.dataset) || {};
    /* the intervention form's typed fields, on the SAME listener the
       delegate panel already uses -- one input handler, not a second one */
    if (d.shivtext && d.shivmid && d.shivkey){
      shadowIvDraft(d.shivmid).values[d.shivkey] = t.value;
      return;
    }
    if (!d.shnewobj && !d.shnewdone) return;
    const draft = shadowNewDraft();
    if (d.shnewobj) draft.objective = t.value;
    else draft.done = t.value;
  });
}

/* THE DELEGATION WRITE. One POST, to the endpoint that already exists.

   target_mode "new" is set HERE, by the button the founder pressed -- not
   parsed out of a model reply and not typed by anyone. That is the whole
   point of + Delegate: the intent is established by the action, so a
   delegated task can never depend on Shadow having guessed correctly.

   CREATE IS THE START (founder, 2026-09-14). It used to land the mission in
   brief_confirm and wait for a second, explicit press, on the rule that
   every mission and goal confirms its brief before it runs. That rule is
   about a brief the founder did not write -- a mission Shadow PROPOSED, or a
   goal attempt composed from earlier ones, where the confirm step is the
   founder reading something for the first time. It was never about this
   form: the founder typed the outcome, typed what will count as done, chose
   the kind and pressed a button labelled "Create the task". There is nothing
   left to confirm, so the second press only asked them to agree with
   themselves.

   The press therefore does both, and the SECOND HALF IS THE EXISTING START
   -- shadowMissionAct(id, "start_now"), the identical call the Start button
   makes. Nothing about spawning is re-implemented here: one create, one
   start, one mission, one delegate chat, and the start path keeps its own
   guards (shadow_runner refuses a double start, the scheduler owns
   admission and the cap). If the start fails the task is still there, in
   brief_confirm, with its Start button -- which is the old behaviour, and
   the honest thing to fall back to. */
async function shadowCreateTask(){
  if (typeof fetch === "undefined" || typeof S === "undefined") return null;
  const d = shadowNewDraft();
  const objective = String(d.objective || "").trim();
  if (!objective){
    S.shadowNewErr = "Say what you want done — Shadow will not guess an outcome.";
    if (typeof scheduleRender === "function") scheduleRender();
    return null;
  }
  /* THE SAME CLASSIFIER THE GOAL CARD USES, not a second opinion.
     This used to stamp founder_confirm on EVERY line. The reasoning was that
     a line the founder typed is theirs to judge -- but goalCriteriaToChecks
     already settled exactly this question for founder-typed text and settled
     it the other way: shape is the only signal there is, and a
     literal-shaped marker genuinely IS substring-matchable, so refusing to
     machine-check it makes contains_artifact unreachable from the UI without
     buying any safety.

     It is also what made the engine's premature-pause bug reachable from the
     Delegate form every single time: with zero machine checks the
     confirmation boundary was satisfied vacuously on turn 1.

     Nothing is loosened -- goalIsLiteralArtifact is unchanged (<=60 chars,
     <=8 words, no criterion vocabulary), so "exit code 0" machine-checks and
     "three distinct reasons" still becomes the founder's to confirm.

     The guard is real: panel.html loads 18-goal-workspace.js right after
     this file, so production always takes the first branch; a context that
     loaded this module alone degrades to the previous behaviour rather than
     throwing. */
  const done_when = (typeof goalCriteriaToChecks === "function")
    ? goalCriteriaToChecks(d.done)
    : String(d.done || "").split("\n")
        .map(s => s.trim()).filter(Boolean)
        .map(check => ({ tier: "founder_confirm", check }));
  S.shadowNewBusy = true;
  S.shadowNewErr = null;
  if (typeof scheduleRender === "function") scheduleRender();
  let r = null;
  try {
    r = await shadowPost("/api/shadow/missions", {
      objective: objective,
      template: SH_KINDS.includes(d.kind) ? d.kind : "fix",
      target_mode: "new",
      done_when: done_when,
      /* the delegate boots on this: the objective plus what will count. */
      manifest: "You are a delegate session working for the founder via "
        + "Shadow. Objective: " + objective
        + (done_when.length ? " It is done when: "
            + done_when.map(c => c.check).join("; ") + "." : "")
        + " Work step by step; say what you did and what is left.",
    });
  } catch (e){ r = null; }
  if (!r || !r.ok){
    S.shadowNewBusy = false;
    S.shadowNewErr = r
      ? ("Could not create the task (" + r.status + ")")
      : "Could not reach Shadow to create the task.";
    if (typeof scheduleRender === "function") scheduleRender();
    return null;
  }
  const m = await r.json();
  /* reconcile with the server, then put the new task in focus so the brief
     is the next thing on screen — a brief of work already under way, not
     one waiting for a second press */
  S.shadowNew = { objective: "", done: "", kind: "fix" };
  S.shadowNewOpen = false;
  S.shadowTaskSel = m.id;
  /* THE EXISTING START, on the mission that was just created. Awaited before
     the panel lets go of `busy`, so the create button cannot be pressed a
     second time while the start is still in the air. shadowMissionAct does
     the rest of what it always does — says it started, re-reads the home,
     and runs the bounded catch-up re-reads that watch the row leave
     brief_confirm. */
  let started = null;
  if (typeof shadowMissionAct === "function"){
    try { started = await shadowMissionAct(m.id, "start_now"); }
    catch (e){ started = null; }
  }
  S.shadowNewBusy = false;
  if (!started && typeof showNudge === "function")
    showNudge("Task created, but it did not start — press Start on the brief.");
  if (typeof loadShadowHome === "function") await loadShadowHome(true);
  if (typeof scheduleRender === "function") scheduleRender();
  return m;
}

/* THE REMOVE. One POST, through the EXISTING mission action endpoint --
   the same shadowMissionAct every other Shadow control uses, so there is no
   second write surface and no second lifecycle.

   IT IS THE SERVER THAT DELETES. Nothing is hidden locally: the row leaves
   because shadowMissionAct's forced re-read comes back without it, which is
   also why a refresh cannot bring it back -- the mission file is gone.

   A LIVE TASK IS ENDED FIRST, by the server, through the paths that already
   exist (cancel_queued for a queued attempt, founder_stop for a live one,
   then release_delegate). That is what the warning says out loud: this
   stops the work, and it is not undoable. The chat Shadow drove is NOT
   deleted -- it stays in Chats with its transcript, exactly as it does
   after Stop or Take over.

   THERE IS NO CONFIRMATION STEP (founder, 2026-09-14). The in-row
   "Delete? Yes / No" that used to gate this painted under neighbouring
   Shadow UI, so Yes could not reliably be clicked and the delete could not
   be finished at all. × now calls straight through to here. A confirm()
   is not the alternative -- it blocks the Electron window (17-agents.js).
   Everything below this line is unchanged. */
async function shadowDeleteTask(mid){
  if (!mid) return null;
  if (typeof shadowMissionAct !== "function") return null;
  const doc = await shadowMissionAct(mid, "delete");
  /* the focus must not keep pointing at a record that no longer exists.
     shadowSelectedTask() already falls back when its pick is missing, so
     this only stops a stale id from outliving the row it named. */
  if (doc && typeof S !== "undefined" && S.shadowTaskSel === mid)
    S.shadowTaskSel = null;
  if (typeof scheduleRender === "function") scheduleRender();
  return doc;
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
  /* force: this read must show the write that just happened, so it never
     coalesces onto a read that was already in the air before the POST. */
  loadShadowHome(true);
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
  loadShadowHome(true);
}
