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
  /* `blocked` BELONGS ON THE PLANE THAT OWNS MISSION ACTIONS (2026-09-16).
     It was left out while it meant only "Shadow asked a question", which the
     intervention form answers elsewhere. It now also means "a supervisor
     fault parked a live mission" (mission_engine.INFRA_BLOCK_REASONS), and
     that park carries no form -- so the one surface that draws Resume and
     Stop has to show the row, or NEEDS YOU has no way back. The task is
     live by every other reckoning: SH_LIVE_STATES has listed `blocked`
     since it existed, and the row reads NEEDS YOU from the same face map. */
  const active = missions.filter(m =>
    ["running", "queued", "paused", "blocked",
     "brief_confirm"].includes(m.state));
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
        ${/* QUEUED IS NOT A DECISION THE FOUNDER CAN CLICK PAST.

              A task is `queued` for exactly one reason -- every slot the run
              limit allows is in use -- so the Start now button that used to
              be drawn here could not do anything: admission would read the
              same full cap and leave the row exactly where it was (and, until
              MissionScheduler.start was made idempotent, a queued -> queued
              transition marked the task FAILED instead). A control whose only
              outcomes are "nothing" and "harm" is not a control.

              The two things that ARE true are said instead: what it is
              waiting for, and Drop, which the founder can still decide. The
              action and its handler are untouched and still what starts a
              brief_confirm task -- this row simply stopped offering it for a
              state it cannot move. Raise Running at once, or end something,
              and the queue promotes this row on its own. */""}
        ${m.state === "queued" ? `<span class="shrowwait">Waiting for a free
            slot</span>
          <button class="btn" type="button" data-shact="drop"
            data-shmid="${escAttr(m.id)}">Drop</button>` : ""}
        ${/* A NEEDS YOU TASK MUST HAVE A WAY BACK (founder, 2026-09-16).
              `blocked` used to arrive here only from Shadow's own
              ask_founder, which always carries a question -- answering it
              resumed the task, so the row needed no button. It is now also
              where a SUPERVISOR FAULT parks a live mission
              (mission_engine.INFRA_BLOCK_REASONS: an unreadable decision, a
              say that never left, an evaluation that could not answer), and
              that park carries no form to answer. Without these two the row
              would read NEEDS YOU with nothing the founder can press, which
              is a worse dead end than the FAILED it replaced.

              Both edges are legal and already implemented -- TRANSITIONS
              lists blocked -> ("running", "stopped") -- and both actions,
              hooks and endpoints are the existing ones. Nothing new. */""}
        ${/* v4 (C9, ADR-043): a held say carries a ONE-USE approval; Approve
              sends exactly that string once. Resume stays (it recomposes),
              but is no longer the primary on a held say (codex P2). */""}
        ${m.state === "paused" && m.approval && !m.approval.used && m.pending_say
          ? `<button class="btn pri" type="button" data-shact="approve"
            data-shmid="${escAttr(m.id)}"
            data-shapproval="${escAttr(m.approval.id)}"
            title="${escAttr(m.pending_say)}">Approve</button>` : ""}
        ${["paused", "blocked"].includes(m.state) ? `<button class="btn"
            type="button"
            data-shact="resume" data-shmid="${escAttr(m.id)}">Resume</button>` : ""}
        ${["running", "paused", "blocked"].includes(m.state) ? `<button class="btn"
            type="button" data-shact="stop" data-shmid="${escAttr(m.id)}">Stop</button>` : ""}
      </span>
    </div>`).join("");
  const finished = missions.filter(m =>
    ["failed", "stopped"].includes(m.state)).slice(-5).reverse();
  const fin = finished.map(m => `
    <div class="shmissionrow shfinished${m.id === foc ? " shfocused" : ""}" data-shmissionrow="${escAttr(m.id)}">
      ${missionCardHtml(m)}
      <span class="shrowacts">
        ${/* v4.2 (founder 2026-09-21): no Retry button. The retry action
             stays on the server; the way back is the task's chat or Hand
             back to Shadow. */""}
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
const SH_PREC = { d_ledger: "ledger", session: "this session",
  project: "project", taste: "taste", history: "history", floor: "floor" };

function shadowMemoryHtml(rows){
  const items = (rows || []).map(r => {
    const dead = !!r.revoked_at;
    const inert = !r.confirmed && !dead;
    return `<div class="shmem ${dead ? "shmem-dead" : ""}" data-shmem="${escAttr(r.id)}">
      <span class="shprec">${esc(SH_PREC[r.precedence]
        || r.precedence || "")}</span>
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
  /* NO CLASS, DELIBERATELY: none of these three is work in flight and none
     is asking for the founder, so they take the default face. (They were
     given classes of their own for one day, 2026-09-19, while the row had
     no pill and the dot was its only signal; the founder brought the pill
     back on 2026-09-20 and the reason went with it.) */
  queued:        { label: "QUEUED",   cls: ""        },
  paused:        { label: "PAUSED",   cls: ""        },
  blocked:       { label: "NEEDS YOU", cls: "blocked" },
  done:          { label: "DONE",     cls: "done"    },
  failed:        { label: "FAILED",   cls: "failed"  },
  stopped:       { label: "STOPPED",  cls: "stopped" },
  draft:         { label: "DRAFT",    cls: ""        },
};
function shadowTaskFace(state){
  return SH_TASK[String(state || "")] || { label: String(state || ""), cls: "" };
}

/* The cap the page has already been told about, or 0 when it has not been
   told yet. One reader, so a card and a settings row can never print two
   different limits, and a card that renders before /api/shadow/settings
   lands says less rather than something wrong. */
function shadowRunLimit(){
  const S_ = (typeof S !== "undefined") ? S : {};
  const n = ((S_.shadowSettings || {}).tasks || {}).running_at_once;
  return typeof n === "number" && n > 0 ? n : 0;
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
   stop -- is NOT a request and stays PAUSED.

   AUTONOMY JOINS ON THE SAME TEST, for the two reasons that ARE a request:
   autonomy_suggest (L1 composed an instruction and wants a yes) and
   autonomy_top_tier (L3's once-per-task confirmation). Both are Shadow
   waiting on the founder with a specific answer in mind, which is the
   definition this list keeps.

   autonomy_hold (L0) is deliberately ABSENT. Nothing the founder can answer
   releases it -- the task is stopped because of a SETTING, and the way out
   is to change the setting, not to say yes. Listing it would put a "needs
   you" badge on a row whose only honest action is somewhere else. */
const SH_FOUNDER_PAUSES = ["founder_confirm", "floor_confirm",
                           "autonomy_suggest", "autonomy_top_tier"];
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

/* THE PILL IS PRINTED IN THREE PLACES -- the task list row, the task card and
   the workspace header -- and it was three copies of the same span. A running
   task has to look alive on ALL of them or the founder learns which surface to
   distrust, so the markup moved here and the three sites call this.

   THE SPINNER IS DECORATION, NOT THE MESSAGE. The word RUNNING beside it is
   what carries the state: that is why the ring is aria-hidden, and why the
   reduced-motion rule is free to simply stop it without losing anything.
   `running` is read from the FACE, not from m.state, so the two states that
   are not their own face (a founder-pause, an accepted-but-not-started) keep
   showing their real face and never spin. */
/* THE LIVE COUNT, ON THE ONE LINE THAT NEVER SCROLLS (founder, 2026-09-20).
   Same two numbers the brief card printed as `TURN | 2 of 25`, in the header
   that stays put, written compactly because it sits beside the status pill
   rather than in a key/value column.

   SILENT WHEN THERE IS NOTHING TO COUNT: a draft with no budget yet would
   otherwise read `0/0`, which looks like a task that has run out rather than
   one that has not begun. */
function shadowHeadTurnHtml(m){
  const max = (m && m.max_turns) || 0;
  if (!max) return "";
  const now = (typeof shadowTurnNow === "function") ? shadowTurnNow(m) : 0;
  return `<span class="shwturn" title="turn ${esc(String(now))} of ${
    esc(String(max))}">${esc(String(now))}/${esc(String(max))}</span>`;
}

function shadowTaskPillHtml(face){
  const f = face || { label: "", cls: "" };
  const spin = f.cls === "running"
    ? `<span class="shtpillspin" aria-hidden="true"></span>` : "";
  return `<span class="shtpill shtpill-${esc(f.cls)}">`
       + `${spin}${esc(f.label)}</span>`;
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
  /* ARCHIVED IS A PLACE IN THE LIST, NOT AN ABSENCE FROM IT (founder,
     2026-09-19). The x used to erase the record, so the task left the
     workspace and the founder's only route back to what it did was the
     ledger, which this screen does not read. It now stops the task and files
     it under ARCHIVED, and this is the rule that keeps the row reachable --
     ahead of the goal test below, because filing a task away is the
     founder's decision about the ROW and must not be overridden by whatever
     its goal happens to say. */
  if (m.archived_at) return true;                            // (0)
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
  /* A FINISHED TASK IS STILL SOMETHING TO READ (founder, 2026-09-15).
     `done` fell to rule 4, so the row left the list the moment the mission
     completed -- taking the completion summary the engine had just stamped
     with it, and leaving a founder who was not already on that card with no
     way back to it. Rules 3 and 3b already make this judgement for an ending
     the founder has not dealt with yet; a completion is one of those, and
     `!retried_to` is the same step-aside they use -- once a retry exists the
     superseded row makes way for its successor.

     PRESENTATION ONLY, exactly like the rules above it: /api/shadow/missions
     returns store.list() with no state filter, so every done record was
     already being sent here and discarded. Nothing is stored, returned or
     transitioned differently. */
  if (m.state === "done" && !m.retried_to) return true;      // (4a)
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
/* ── THE LIST'S OWN ORDER, IN ONE PLACE (founder, 2026-09-21, pass 10) ──
   "When we enter the Shadow tab we want the focus to be on the FIRST item
   of the left-hand side -- not some fifth or sixth element."

   THE TWO SURFACES HAD TWO ORDERS. shadowTaskListHtml drew sections in
   SH_SECTIONS order with recency inside each; shadowSelectedTask picked by
   a STATE RANKING (blocked, then startable, then running, paused, queued,
   brief_confirm, then the last row of an unsorted array). They agreed only
   by coincidence, so entering the tab routinely opened a task several rows
   down -- the founder's report exactly.

   SO THE ORDER IS COMPUTED ONCE, HERE, and both callers read it. The
   ordering rules are unchanged, lifted verbatim out of the renderer:
   membership by section first, recency inside a section, id to break a tie.
   Nothing about which rows are LISTED moved -- shadowTasks() is still the
   membership rule and shadowTaskIsActive still decides it. */
function shadowTaskRowsInOrder(){
  const rows = shadowTasks();
  const out = [];
  for (const [key] of SH_SECTIONS){
    const mine = rows.filter(m => shadowTaskSection(m) === key)
      .sort((a, b) => (shadowTaskLaunchedAt(b) - shadowTaskLaunchedAt(a))
        || String((a && a.id) || "").localeCompare(String((b && b.id) || "")));
    for (const m of mine) out.push(m);
  }
  return out;
}

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
  /* ── THE FIRST ROW OF THE LIST, AND NOTHING ELSE (pass 10) ──────────
     The state ranking this replaces was a second opinion about which task
     matters, and it disagreed with the list the founder is looking at. The
     list already ranks by attention: WAITING ON YOU is its first section,
     so a task that needs the founder is still what opens -- not because
     this function knows about `blocked`, but because the list puts it
     first. One rule, one order, and the pane always opens on the row at
     the top of the rail.

     THE FOUNDER'S OWN PICK STILL WINS, above -- this is only the default
     for entering the tab with nothing chosen. */
  const ordered = shadowTaskRowsInOrder();
  return ordered.length ? ordered[0] : rows[rows.length - 1];
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

/* ── THE LIST IS THREE SECTIONS (founder design "Shadow Design - Final",
   2026-09-15) ───────────────────────────────────────────────────────────
   A SECTION IS NOT A STATUS. The header answers "whose move is it" --
   yours, Shadow's, or nobody's -- and the pill on the row still answers
   "what is this task doing", from shadowTaskFaceFor and nothing else. That
   is why the founder never meets `blocked`, `paused`, `queued` or
   `brief_confirm` as a heading: WAITING ON YOU is a heading, NEEDS YOU is
   a pill, and they are different sentences about the same row.

   PRESENTATION ONLY. Nothing new is read, no face is recomputed, and
   shadowTasks() still decides membership of the list -- this decides only
   the ORDER of the rows and the heading each one is drawn under.

   Keyed on the FACE LABEL, not on m.state, because the face is already the
   one place that resolves the two states that are not their own whole face
   (a founder pause reads NEEDS YOU; an accepted start reads QUEUED).
   Reading m.state here would be the second status system the list must
   not grow.

   FAILED SITS UNDER WAITING ON YOU, NOT DONE TODAY. It is terminal to the
   engine but not to the founder -- Retry is still pending on them, which is
   exactly why shadowTaskIsActive keeps it in the list at all (rule 3). The
   design has no FAILED under DONE TODAY, and calling a failure DONE or
   STOPPED would be a lie about what happened; its own FAILED pill is
   untouched, and so is every failure behaviour behind it. */
const SH_SECTIONS = [
  ["wait", "WAITING ON YOU"],
  ["run",  "RUNNING"],
  ["done", "DONE TODAY"],
  /* LAST, AND THE ONLY SECTION THE FOUNDER PUTS THINGS IN THEMSELVES. The
     three above are states the work arrives in; this one is a decision --
     the x said "I am done looking at this" (founder, 2026-09-19). */
  ["arch", "ARCHIVED"],
];
const SH_TASK_SECTION = {
  "NEEDS YOU": "wait",   // blocked, and the two founder pauses
  "READY":     "wait",   // the founder's click is the next thing to happen
  "DRAFT":     "wait",
  "FAILED":    "wait",   // Retry is the founder's move
  "RUNNING":   "run",
  "QUEUED":    "run",
  "PAUSED":    "run",
  "DONE":      "done",
  "STOPPED":   "done",
};
/* an unmapped label is a state that is not terminal -- shadowTaskIsActive
   admits every terminal one by name -- so it belongs with the work in
   flight, never in a conclusion it has not reached. */
function shadowTaskSection(m){
  /* BEFORE THE FACE, because archiving is a decision about the row and the
     state underneath it is untouched: an archived task keeps whatever face
     it ended with, and would otherwise draw under DONE TODAY as though the
     founder had never filed it. */
  if (m && m.archived_at) return "arch";
  return SH_TASK_SECTION[shadowTaskFaceFor(m).label] || "run";
}

/* WHEN A TASK WAS LAUNCHED, from the record the server already sends.

   `created_ns` is time.time_ns() stamped by MissionStore.create, and it is
   already the canonical launch clock on the server side -- resume_after_restart
   sorts the restart sweep by it, precisely because `created_at` is
   second-granularity and MissionStore.list() walks the directory by FILENAME
   (m-<random hex>.json), which is no order at all. Nothing new is stamped here.

   Falls back to `created_at` -- the same moment, one decimal place coarser --
   rescaled to nanoseconds so the two are comparable, and to 0 for a record
   carrying neither. 0 sorts last, which is the honest place for a task whose
   launch time is unknown. */
function shadowTaskLaunchedAt(m){
  const ns = m && m.created_ns;
  if (typeof ns === "number" && isFinite(ns)) return ns;
  const ms = (m && m.created_at) ? Date.parse(m.created_at) : NaN;
  return isFinite(ms) ? ms * 1e6 : 0;
}

function shadowTaskListHtml(){
  /* NEWEST LAUNCHED FIRST (founder, 2026-09-16). The list under + Delegate
     was drawn in whatever order the server handed it over, which is
     MissionStore.list()'s filename walk -- random hex, so the newest task a
     founder just created could land anywhere.

     SORTED HERE AND NOWHERE ELSE. shadowTasks() is also what
     shadowSelectedTask() ranks its fallback from (`rows.find(...)` and
     `rows[rows.length - 1]`), so sorting there would quietly change WHICH
     task the right pane opens on. This is the rendering path and only the
     rendering path.

     The id breaks a tie, so two tasks stamped in the same nanosecond -- or
     two carrying no timestamp at all -- still draw in one fixed order rather
     than whatever the walk happened to yield.

     SORTED INSIDE EACH SECTION, NOT ACROSS THE LIST (founder, 2026-09-16).
     The section order is fixed -- WAITING ON YOU, then RUNNING, then DONE
     TODAY -- and recency decides only the rows within one of them. An
     earlier pass sorted `rows` once and let SH_SECTIONS filter the result,
     which renders identically (a filter keeps relative order, and the
     headings come from SH_SECTIONS either way) but reads as a global sort.
     Doing it per section is the same work in the place the rule describes,
     so nothing has to be reasoned about to see that a timestamp can never
     move a row between sections. */
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
  /* the row itself is BYTE-IDENTICAL to what it was -- same wrapper, same
     selector button, same three spans, same delete control and the same
     two hooks. Only where it is emitted changed. */
  const rowHtml = (m) => {
    const f = shadowTaskFaceFor(m);
    const on = sel && m.id === sel.id;
    return `<div class="shtaskrow${on ? " on" : ""}">
      <button class="shtask${on ? " on" : ""}"
      type="button" data-shtask="${escAttr(m.id)}">
      <span class="shtaskdot d-${esc(f.cls)}" aria-hidden="true"></span>
      <span class="shtaskname">${esc(m.objective || "(no objective)")}</span>
      ${/* THE ROW KEEPS ITS PILL (founder, 2026-09-20, correcting the
           2026-09-19 pass: "let's not remove showing status on the LHS ...
           bring back the LHS list status like we had before").

           WHAT THE TWO DIRECTIONS TOGETHER SAY. The duplication worth
           removing was the RIGHT pane's -- the brief card printed the same
           word the header printed, about the same task, forty pixels apart.
           The LIST is not that: it is the one place a founder reads the
           state of every OTHER task, the ones the header can never speak
           for. So the card's pill is gone and this one is back.

           The dot beside it keeps the face classes added on 2026-09-19 --
           queued, paused and draft had none -- which costs nothing and
           leaves the row readable at a glance even where the name is long
           enough to crowd the word. */""}
      ${shadowTaskPillHtml(f)}
    </button>
      <button class="shtaskdel" type="button"
        data-shtaskdel="${escAttr(m.id)}"
        title="${m.archived_at ? "Delete this task permanently"
                : shadowTaskIsLive(m) ? "Stop &amp; archive this task"
                                      : "Archive this task"}"
        aria-label="${m.archived_at ? "Delete task permanently"
                                    : "Archive task"}">\u00d7</button>
    </div>`;
  };
  /* a section with nothing in it draws nothing -- not an empty heading */
  /* THE ORDER IS shadowTaskRowsInOrder's, so the row this draws first is
     by construction the row shadowSelectedTask opens on (pass 10). The
     rules are unchanged; they simply live in one place now. */
  const ordered = shadowTaskRowsInOrder();
  return SH_SECTIONS.map(([key, head]) => {
    const mine = ordered.filter(m => shadowTaskSection(m) === key);
    if (!mine.length) return "";
    return `<div class="shwsec shwsec-${key}">${head}</div>`
      + mine.map(rowHtml).join("");
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
/* \u2500\u2500 ONLY WHAT IS YOURS IS ON SCREEN (founder, 2026-09-20) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
   THE ASK: "if checks are done by shadow without aid from the user, don't
   show them at all".

   WHY IT IS RIGHT, AND WHY IT IS RIGHT *NOW* RATHER THAN BEFORE. This list
   used to be almost entirely rows reading "Shadow checks this" -- nine of
   nine on the founder's install, because everything reached them. After
   D-SH-1 and the artifact lane the opposite is true: most rows are settled
   by machine, and a wall of them is a wall of things the founder can do
   nothing about, with the one or two rows that need a decision buried in
   it. A row the founder cannot act on is not information on a surface whose
   whole job is to ask them something.

   NOTHING IS DELETED, and that distinction is the difference between this
   and hiding a problem. Shadow's own rows move into a `<details>` that
   states its own count, so the full list with every verdict is always one
   click away. What changes is what is on screen UNASKED.

   OUTSTANDING IS NOT THE SAME AS SETTLED, and the split below is on that
   rather than on tier alone. A Shadow check that has NOT passed yet is not
   "done by Shadow without aid" -- it is work still in flight, and it is
   counted separately so a founder reading "2 still running" knows the task
   is not merely waiting on them. */
/* ── WHAT THE FOUNDER SUPERSEDED, SAID OUT LOUD ──────────────────────────
   THE FAILURE (founder, 2026-09-21). A founder watching an Africa trip at
   NEEDS YOU said "actually, I want India". The record did the right thing --
   MissionStore.amend bumps the revision and _invalidate_for_revision strips
   every verdict the old objective earned -- and the screen said nothing at
   all. The Africa question the founder had been reading simply was not there
   on the next render.

   "OUTDATED" AND "NEVER HAPPENED" ARE DIFFERENT STATEMENTS, and the founder
   is owed the first one. Work was done, they changed their mind, and the
   work stopped counting: that is a fact about their task and it belongs in
   the conversation, not in a diff of two renders.

   IT IS DELIBERATELY INERT. No button, no index, no data-shact, no confirm
   hook -- a superseded check must be impossible to act on, which is the
   whole point of showing it. The live decision is drawn by
   shadowCheckRowsHtml from `done_when`, and these rows come from
   `revisions`, a ledger the engine writes and never reads. The two cannot
   be confused because they are not the same field.

   ONLY THE LAST ONE IS DRAWN. A founder who changed direction four times
   does not need all four struck-through objectives stacked above the live
   one; they need to know the previous thing is dead. The record keeps up to
   MAX_REVISIONS for the chat and the ledger. */
function shadowRevisionsHtml(m){
  const log = (m && Array.isArray(m.revisions)) ? m.revisions : [];
  const last = log.length ? log[log.length - 1] : null;
  if (!last) return "";
  const checks = Array.isArray(last.checks) ? last.checks : [];
  const was = String(last.objective || "").trim();
  return `<div class="shsaid shstale">
    <div class="shsaidhead">Outdated</div>
    <div class="shsaidtext">Superseded by your latest instruction.</div>
    ${was ? `<div class="shstalewas">${esc(was)}</div>` : ""}
    ${/* THE CRITERIA DO NOT COME WITH IT (founder, 2026-09-21: "even in
         summary -- don't show user stuff he doesn't care about, Done checks
         and all"). This listed every superseded predicate struck through,
         which put the longest strings in the product on screen to say
         something the founder already knows: the old plan is off.

         WHAT IT SAYS INSTEAD is what changed and how much went with it. The
         superseded checks stay on the record in `revisions` for anyone
         reading it back; they are not what this moment is about. */""}
    ${checks.length ? `<div class="shstalecount">${checks.length === 1
      ? "1 check retired with it" : checks.length + " checks retired with it"
      }</div>` : ""}
  </div>`;
}


function shadowCheckRowsHtml(m){
  const all = (m.done_when || []).filter(c => c && c.check);
  if (!all.length) return "";
  /* the founder's own, still outstanding -- the only rows that get a button
     and the only rows drawn without being asked for. The INDEX is the
     record's, not this filtered list's: confirm_check is by index and a
     re-numbered one would sign the wrong row. */
  const mineIx = [];
  (m.done_when || []).forEach((c, i) => {
    if (c && c.check && c.tier === "founder_confirm" && !c.met) mineIx.push(i);
  });
  const settled = all.filter(c => c.tier !== "founder_confirm" && c.met);
  const running = all.filter(c => c.tier !== "founder_confirm" && !c.met);
  const signed = all.filter(c => c.tier === "founder_confirm" && c.met);
  const rows = mineIx.map(i => {
    const c = m.done_when[i];
    return `<div class="shcheck">
      <span class="shcheckbox" aria-hidden="true"></span>
      <span class="shchecktxt">${esc(c.check)}</span>
      <button class="btn shcheckdo" type="button"
        data-shcheckmid="${escAttr(m.id)}" data-shcheckix="${escAttr(i)}"
        >Confirm</button>
    </div>`;
  }).join("");
  /* EVERYTHING ELSE, FOLDED. The summary sentence is built only from the
     counts that are non-zero, so a task with nothing outstanding never
     prints "0 still running". */
  /* the fold's own label. PLAIN, and it names no tier, no probe and no
     lane -- "Everything else Shadow is handling" is true of a settled check,
     a running one and a signed one alike, and is what a founder needs to
     know about rows they are not being asked about. */
  const said = ["Everything else Shadow is handling"];
  const others = settled.concat(running, signed);
  const fold = others.length ? `<details class="shcheckfold">
    <summary>${esc(said.join(" \u00b7 "))}</summary>
    ${others.map(c => `<div class="shcheck${c.met ? " shcheckmet" : ""}">
      <span class="shcheckbox" aria-hidden="true">${c.met ? "\u2713" : ""}</span>
      <span class="shchecktxt">${esc(c.check)}</span>
      <span class="shcheckby">${c.met
        ? (c.tier === "founder_confirm"
            ? "you confirmed it" + (c.confirmed_by
                ? " \u00b7 " + esc(c.confirmed_by) : "")
            : "Shadow checked this")
        : "Shadow is checking this"}</span>
    </div>`).join("")}
  </details>` : "";
  /* NOTHING TO ASK MEANS NOTHING TO ASK WITH. A pause carrying no founder
     row -- a floor confirm, an autonomy hold -- is explained by the card
     above it, not by a list of criteria the founder cannot act on. */
  if (!rows) return fold ? `<div class="shconfirm">${fold}</div>` : "";
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
  /* ── PLAIN ENGLISH, NOT THE MACHINERY (founder, 2026-09-21) ───────────
     THE ASK: the founder-facing surface should be "concise, plain English,
     visually scannable, focused on the decision, free of implementation
     vocabulary". What stood here announced Shadow's internal state --
     "Shadow's own checks have passed", a count of what is left, and a
     sign-off instruction -- before it got to the question.

     THE SEMANTIC QUESTION IS UNTOUCHED. The criterion is still rendered
     verbatim, character for character, in the row below: it is the thing
     being agreed to and rewording it would change what the founder signed.
     Only the framing around it changed.

     THE FOLD STAYS CLOSED and now says nothing about tiers or who settled
     what on the outside of it. */
  /* ── WHY THE FOUNDER IS THE ONE BEING ASKED (founder, 2026-09-21) ─────
     "Only you can decide whether this actually matches the trip you want."
     A Confirm button with no account of why it exists reads as a chore; the
     founder's own framing is that these are the checks Shadow CANNOT settle,
     which is a different and much shorter sentence than the tier machinery
     behind it.

     ONE LINE, CLOSED, AND THE SAME EVERY TIME. It explains the CLASS of
     question rather than this instance -- Shadow composing a bespoke
     justification per check would be one more thing to read and one more
     thing that can be wrong. Deliberately not a help panel. */
  const why = `<details class="shwhyme"><summary>Why am I needed?</summary>
    <div class="shwhymebody">Shadow settles everything it can check for
      itself \u2014 what was produced, whether it is there, whether it holds
      together. What is left is judgement about what you actually wanted,
      and that is not Shadow\u2019s to make.</div></details>`;
  return `<div class="shconfirm">
    <div class="shconfirmq">Shadow needs your decision</div>
    ${shadowDecisionHtml(m)}
    <div class="shchecks">${rows}</div>
    ${why}
    ${fold}
  </div>`;
}

/* ── THE EVIDENCE THE DECISION NEEDS, BESIDE THE DECISION ────────────────
   THE FAILURE (founder, 2026-09-21). Shadow asked "does this ten-line
   ranking work as the greatest riders ever?" and the ten riders were only
   in the worker's chat. The founder was asked to approve a list they could
   not see, and had to open a second chat to answer a question asked here.

   WHAT THIS DRAWS is `m.decision`, the packet mission_engine stamps at the
   two places a mission goes to a human. NOTHING IS COMPOSED CLIENT-SIDE and
   nothing is inferred: the artifact text is the file's own bytes and the
   facts were counted by machine in shadow_evidence, so this function cannot
   add a claim the server did not make. A record with no packet renders ""
   and the surface is exactly what it was.

   IT SITS ABOVE THE CHECK ROWS on purpose. The order of the block is the
   order of the decision: here is what was produced, here is what Shadow
   already established about it, and now here is the part only you can
   settle. Putting the evidence under the buttons would ask the question
   before showing its subject.

   THE ARTIFACT IS NOT RENDERED AS MARKDOWN. It is escaped into a <pre>,
   because this is the file AS IT IS -- a founder approving a ranking must
   see the literal lines, not a renderer's idea of them. A file that happens
   to contain markdown would otherwise be silently reformatted on the one
   surface where its exact shape is the thing being judged. */
function shadowDecisionHtml(m){
  const d = m && m.decision;
  if (!d) return "";
  const arts = (d.artifacts || []).map(a => {
    if (!a) return "";
    if (a.kind === "image"){
      /* a visual decision needs the visual. Too big to inline is stated as
         a fact rather than drawn as a broken image. */
      return `<div class="shdecart">
        <div class="shdecpath">${esc(a.path || "")}</div>
        ${a.too_big || !a.data_uri
          ? `<div class="shdecnote">too large to preview here (${esc(
              String(a.bytes || 0))} bytes) — open the task's chat</div>`
          : `<img class="shdecimg" alt="${escAttr(a.path || "artifact")}"
               src="${escAttr(a.data_uri)}">`}
      </div>`;
    }
    /* ── THE PREVIEW IS FOR THE PERSON DECIDING (founder, 2026-09-21,
         pass 8) ────────────────────────────────────────────────────────
       WHAT LEFT THIS BLOCK, and why each one:

         "233 lines · 181 distinct"   a MEASUREMENT taken to satisfy a
                                      predicate. It answers "did the probe
                                      pass", which Shadow already answered;
                                      it does not help a person judge an
                                      itinerary.
         "shown in part — open the    a caveat about the RENDERER. The file
          task's chat for the whole    is named right above it and is one
          file"                        click away; saying so in the middle
                                       of a decision is the debugger
                                       talking.
         "Shadow established: …"      the internal evidence assertion the
                                      founder named outright. It is what
                                      Shadow told ITSELF before asking.

       WHAT STAYS is what the decision is actually about: the file's name,
       the preview of its contents, and `missing` -- which explains why
       there is no preview when Shadow could not gather one, and is the one
       note here a person genuinely needs.

       NOTHING IS DELETED FROM THE RECORD. `decision.artifacts[].facts`,
       `.truncated` and `decision.established` are still stamped by
       shadow_decision, still carried by /api/shadow/missions, still in the
       Verification fold and still copied by shadowCompletionText. */
    return `<div class="shdecart">
      <div class="shdecpath">${esc(a.path || "")}</div>
      <pre class="shdectext">${esc(a.text || "")}</pre>
      ${/* A CUT PREVIEW STILL SAYS SO -- nobody should approve a list
           believing they saw all of it (the claim the 2026-09-21 sentence
           existed for, kept). What went is the RENDERER'S instruction
           ("open the task's chat for the whole file"); what stays is the
           ordinary typographic mark for "there is more", which is a fact
           about the preview rather than a note about the software. */""}
      ${a.truncated ? `<div class="shdeccut" aria-label="preview continues"
        >\u2026</div>` : ""}
    </div>`;
  }).join("");
  if (!arts && !d.missing) return "";
  return `<div class="shdec">
    ${arts}
    ${d.missing ? `<div class="shdecnote shdecmissing">${esc(d.missing)}</div>`
                : ""}
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
/* ── A CONCLUSION IS NOT AN AUDIT LOG (founder, 2026-09-15) ──────────────
   `completion.outcome` is not a summary and was never built to be one: the
   server slices it off the head and tail of the evidence blob, so it lands
   mid-json as often as on a sentence -- the release mission's ends, quite
   literally, "nothing in the release path pointed at the…". Printed whole it
   put file permissions, a grep invocation and a markdown table on the
   founder's primary completion surface.

   SO THE CARD REFUSES EVIDENCE. A sentence carrying a fence, a permission
   string, a shell invocation, a path:line reference or an enumerated
   evidence header is not the conclusion; it is the working. If a real
   sentence survives it is shown, and if none does the block draws NOTHING --
   because the conclusion is already on the card in the two places that were
   built to carry it: the headline ("1 of 1 checks passed") and the criteria
   rows with who satisfied each one.

   NOTHING IS LOST OR EDITED. completion.outcome is untouched on the record,
   still returned, still copied in full by Copy result (shadowCompletionText
   is not changed), and the whole working is behind Open the chat. This is a
   SEPARATE filter from the timeline's on purpose -- the worker rows keep
   their existing behaviour exactly. */
const SH_EVIDENCE = [
  /```/,                                   /* a fence, inline or not */
  /(^|\s)[-d][rwx-]{9}/,                   /* a permission string */
  /`\s*(grep|ls|cat|find|git|npm|node|sed|awk|rm|mv|cp|chmod|curl)\b/i,
  /\S+\.\w+:\d+/,                          /* path:line evidence */
  /^\s*\(\d+\)\s/,                         /* "(1) Path and references" */
];
function shadowResultEvidence(sentence){
  const t = String(sentence || "");
  return SH_EVIDENCE.some(re => re.test(t));
}
function shadowResultGist(text){
  return shadowSayGist(shadowSayClean(text), shadowResultEvidence);
}

/* The field as the ONE-LINE gist has always received it: every run of
   whitespace, newlines included, flattened to a single space. Nothing else
   uses this -- see the note at the call site. */
function shadowOutcomeFlat(text){
  return String(text == null ? "" : text).replace(/\s+/g, " ").trim();
}

/* ── THE SUMMARY'S ONE REPRESENTATION (founder, 2026-09-17) ────────────
   THE BUG THIS EXISTS TO MAKE UNREPEATABLE. The Summary used to decide
   WHETHER it had a result from one representation of the field and render a
   DIFFERENT one: the gate read shadowResultGist(shadowOutcomeFlat(outcome)),
   the body rendered the raw outcome. Flattening collapses the whole message
   to a single line, and SH_CONTROL_HEAD then matches that ONE line whenever
   the message merely BEGINS with a governance token -- so a 1686-character
   report whose first line was "PLACEMENT: …" was judged to contain nothing.
   Measured on the real store: 2 of 6 completed missions suppressed, both of
   them holding a perfectly good answer.

   Two representations, one decision, is the defect. So there is ONE now:
   existence and presentation are the same string, and they cannot disagree.

   WHAT IT REMOVES, and only this: Shadow/Sutra CONTROL-PLANE PREAMBLE, by
   the rule that already existed. A line matching SH_CONTROL_HEAD goes --
   the same rule, the same 22 tokens, the same regex every other founder
   surface already filters on. Nothing new is invented and nothing is
   task-specific: this is not "strip research headers" or "strip file
   reports", it is "a control-plane line is not the answer", which is true
   of every worker on every task.

   FENCES ARE JUDGED BY WHAT IS IN THEM, not by being fences. shadowSayClean
   drops EVERY fenced block, which is right for a one-line preview and wrong
   here -- a coding task's diff and a research answer's snippet are the
   result, not furniture. So a block is dropped only when the MAJORITY of its
   non-empty lines are themselves control-plane. That is what removes the
   ```INPUT ROUTING``` / ```TASK … DEPTH … COST``` blocks a governed worker
   opens with, while leaving an ordinary ```js block untouched.

   WHAT IT PRESERVES: everything else, verbatim. Headings, lists, tables,
   links, inline code and ordinary fenced code all reach mdHtml exactly as
   the worker wrote them. This is a filter over lines, never a rewriter of
   them -- no sentence is composed, shortened or reworded here.

   WHAT IT IS NOT. Not a second evaluator, not a selector: which message this
   text came from was settled upstream by shadow_runner.last_worker_message
   (evidence_messages drops Shadow's injected user turns, then a role check
   keeps only the worker's own). This never sees a transcript and cannot
   change that provenance.

   A LEGACY RECORD CANNOT BE REPAIRED HERE, and is not pretended otherwise.
   Missions completed before shadow_runner kept newlines hold a single
   flattened line on disk; if that line opens with a control head the whole
   record reads as control-plane and nothing survives. The structure is gone
   from the stored data, not discarded here, and every mission completed
   since carries its own line breaks. */
function shadowOutcomeBody(text){
  const lines = String(text == null ? "" : text).split(/\r?\n/);
  const out = [];
  for (let i = 0; i < lines.length; i++){
    if (/^\s*```/.test(lines[i])){
      /* the block, its opener and (when it has one) its closer */
      let j = i + 1;
      const block = [];
      while (j < lines.length && !/^\s*```/.test(lines[j])) block.push(lines[j++]);
      const real = block.filter(l => l.trim());
      const ctl = real.filter(l => SH_CONTROL_HEAD.test(l)).length;
      /* majority control-plane -> the block is the preamble, and goes.
         An EMPTY fence carries nothing either way and is kept, because a
         renderer that silently eats a block the worker wrote is worse than
         one that draws an empty one. */
      if (!(real.length && ctl * 2 >= real.length)){
        out.push(lines[i]);
        for (const l of block) out.push(l);
        /* an unterminated fence has no closer to carry; mdHtml closes it */
        if (j < lines.length) out.push(lines[j]);
      }
      i = j;
      continue;
    }
    if (SH_CONTROL_HEAD.test(lines[i])) continue;
    out.push(lines[i]);
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

/* ── SUMMARY: THE ANSWER, NOT THE VERDICT (founder, 2026-09-17) ─────────
   THE GAP THIS CLOSES. A finished research task said "Done — 3 of 3 checks
   passed", one sentence of gist, and three ticks. All true, and none of it
   the thing the founder asked for: to read the research they had to open the
   worker chat and hunt back through the turns for the last message.

   THE FIELD IS THE ONE THAT ALREADY EXISTS. `completion.outcome` is stamped
   once, by mission_engine._complete, from shadow_runner.last_worker_message
   -- the worker's own closing message, verbatim. Nothing here selects a
   message, re-reads a transcript, or asks a model: this renders a string the
   record already carried and the API already returned.

   AND THE SAFETY PROPERTY RIDES WITH IT. last_worker_message walks
   evidence_messages, which drops the USER turns Shadow injected, and then
   keeps only `role == "assistant"`. Two independent guards, both upstream of
   this function -- so Shadow's own control-plane text (a held say, the next
   instruction) can never reach this block. Selecting a message in JavaScript
   would have thrown both away, which is why this does not.

   RENDERED THROUGH THE EXISTING MARKDOWN RENDERER. mdHtml (02-helpers.js)
   escapes the ENTIRE input first and only then wraps already-inert text in
   tags it authors itself, with links scheme-checked against http/https -- so
   a worker message cannot inject markup here. It loads before this file
   (app.py:496 serves static/js/*.js sorted, and 02 < 16). The typeof guard
   is for a context that loaded this module alone, the same guard
   shadowTimelineHtml already uses for shadowProseHtml.

   DONE ONLY. `completion` is stamped in exactly one place -- _complete, the
   one writer of a done mission -- so `m.completion` already implies done.
   The state check is stated anyway rather than inferred: it is the rule the
   founder asked for, and a reader should not have to know the engine to see
   that it holds. */
function shadowSummaryHtml(m){
  const c = m && m.completion;
  const text = c && c.outcome;
  if (!text || !m || m.state !== "done") return "";
  /* ── THE CARD STILL REFUSES EVIDENCE (founder, 2026-09-15; kept) ─────
     `outcome` is the worker's LAST message, which is not always its
     conclusion. The case that ruling was written on had a last message that
     was the WORKING -- file permissions, a grep invocation and a table of
     hits (the fixture is EVIDENCE_OUTCOME in test_shadow_rhs) -- and the
     ruling was that the card refuses it: "the working stays behind Open the
     chat and in Copy result". test_shadow_rhs 8l pins that and it still
     holds;
     drawing a raw evidence dump under a big SUMMARY heading would be a
     louder version of exactly what that ruling removed.

     SO THE ADMISSIBILITY QUESTION IS ASKED WITH THE EXISTING ANSWER, and
     only the admissibility question: shadowResultGist returns "" when every
     sentence is filler or evidence-shaped, which is precisely "is there a
     conclusion in here at all". That verdict gates this block.

     IT DOES NOT PRODUCE THIS BLOCK. What renders is the full body through
     mdHtml -- never the gist, which is the one-line preview above and stays
     there. The gist is being used as a filter, not as content.

     AND IT IS ASKED OF THE BODY, which is the whole point of
     shadowOutcomeBody: the string that decides whether there is a result is
     the same string that gets drawn. Asking it of a flattened copy is what
     suppressed a real 1686-character answer, and the composition matters in
     both directions -- the body alone would have shown the pure-evidence
     record the 2026-09-15 ruling refuses (204 characters survive the
     control-plane filter), because a grep dump contains no control-plane
     lines to remove. Cleaning answers "what is the answer here"; the gist
     answers "is any of it a conclusion". Both, on one string. */
  const body = shadowOutcomeBody(text);
  if (!body || !shadowResultGist(body)) return "";
  const html = (typeof mdHtml === "function") ? mdHtml(body) : esc(body);
  return `<div class="shdonesummary">
      <div class="shdonesumhead">Summary</div>
      <div class="shdonesumbody md">${html}</div>
    </div>`;
}

function shadowCompletionHtml(m){
  const c = m && m.completion;
  if (!c) return "";
  /* ── THE VERDICTS FOLD (founder, 2026-09-20) ──────────────────────────
     "if checks are done by shadow without aid from the user, don't show
     them at all". On a finished task the headline ALREADY carries the fact
     that matters -- `completion.headline` is the server's own "3 of 3
     checks passed" -- so printing three rows underneath it that all say
     "Shadow verified this" is the same sentence four times.

     WHAT STAYS OPEN is anything the founder had a hand in or that did not
     pass: a row they signed is their own decision reflected back, and a row
     that failed is the reason the count is not N of N. Those are the rows
     a founder scans a finished task for.

     NOTHING IS DELETED. Every other verdict is inside the `<details>`,
     which states its own count -- one click, full list, every `how` line
     and every piece of evidence exactly as before. */
  const checks = c.checks || [];
  const rowHtml = k => {
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
  };
  /* ── INTERNAL VERIFICATION IS NOT THE RESULT (founder, 2026-09-21) ────
     THE ASK: "do not show the user internal verification machinery ...
     '3 of 3 checks passed', 'N checks', 'Shadow settled itself',
     probe/tier/evidence internals". A finished task should say what was
     DONE, not how Shadow convinced itself.

     NOTHING IS WEAKENED AND NOTHING IS DISCARDED. Every check still ran,
     `completion.checks` is still stamped by the server with every verdict
     and every piece of evidence, shadowCompletionText still copies the full
     record, and the rows below still render -- inside a closed disclosure
     that says only "Verification". The founder stops CONSUMING the
     machinery; the machinery is untouched and one click away.

     WHAT IS LEFT OUTSIDE is what the founder asked for: Done, what was
     produced, the summary, and any caveat. */
  const failed = checks.filter(k => !k.met);
  const rows = checks.map(rowHtml).join("");
  /* one sentence, and only if it is a conclusion rather than the working.
     FLATTENED FIRST, AND ONLY FOR THIS LINE (founder, 2026-09-17).
     `completion.outcome` used to arrive with every newline already collapsed
     -- shadow_runner.last_worker_message did `" ".join(text.split())` -- so
     shadowSayClean, which works line by line, only ever saw ONE line and its
     table/fence/heading rules never fired on this path. The Summary block
     below needs those newlines to render as markdown, so the backend now
     keeps them. Handing the raw field to the gist would therefore silently
     move a line that is NOT in scope: shadowSayClean would start dropping
     table rows and fences it never used to see. Flattening HERE reproduces
     exactly the string this call received before, so the gist is
     byte-identical to what it drew yesterday. */
  const work = shadowResultGist(shadowOutcomeFlat(c.outcome));
  const S_ = (typeof S !== "undefined") ? S : {};
  /* the copy action's own feedback, and it is per-record: a flag holding
     another mission's id must leave THIS button reading "Copy result". */
  const copied = (S_.shadowResultCopied
    && S_.shadowResultCopied.id === m.id) ? S_.shadowResultCopied : null;
  /* the worker's account in full, under the verdicts -- see shadowSummaryHtml */
  const summary = shadowSummaryHtml(m);
  /* the copy control is the same button in both shapes below */
  const copyBtn = `<button class="btn shdonecopy${copied
      ? (copied.ok ? " ok" : " bad") : ""}" type="button"
      data-shcopydone="${escAttr(m.id)}" data-shcopystate="${copied
        ? (copied.ok ? "copied" : "failed") : "idle"}"
      aria-label="${copied
        ? (copied.ok ? "Copied — the result is on your clipboard"
                     : "Copy failed — the result is not on your clipboard")
        : "Copy result — this summary as text"}"
      title="Copy this result as text">${copied
        ? (copied.ok ? "Copied" : "Copy failed") : "Copy result"}</button>`;
  const files = (c.artifacts || []).length ? `<div class="shdonefiles"
      >${(c.artifacts || []).map(pth =>
        `<span class="shdonefile">${esc(String(pth))}</span>`).join("")}</div>`
    : "";
  const verif = `<details class="shcheckfold shdoneverif">
      <summary>Verification</summary>
      <div class="shconfirmsub">${esc(shadowTurnNow(c) + " of "
        + (c.max_turns || 0) + " turns")} used.</div>
      <div class="shchecks">${rows}</div>
    </details>`;

  /* ── A CLEAN FINISH IS A SENTENCE, NOT A REPORT (founder, 2026-09-21,
       pass 7) ────────────────────────────────────────
     THE ASK, and it is a split rather than a deletion:

       "When Shadow/worker completes a task successfully and the user does
        NOT need to do anything manually, do NOT expose internal
        verification machinery in the main Shadow conversation ... make the
        completion appear as a natural Shadow response. DO NOT hide the
        checks when the user actually needs to inspect something."

     SO THE PREDICATE IS "IS ANYTHING WAITING ON THE FOUNDER", and it is
     read off the record rather than guessed: the task ended in `done`, no
     check failed, nothing is paused for a founder decision, no question is
     open and no instruction is held. Every one of those is the same field
     the existing controls already read -- this adds no state and decides
     nothing about the work.

     WHEN NOTHING IS WAITING, the conversation gets what a person would say:
     one line naming what was produced, the file itself, and the
     Verification fold CLOSED beside them. When something IS waiting, the
     card below renders exactly as it did -- caveat, criteria, evidence and
     all -- because then the machinery is the actionable part.

     NOTHING IS DELETED FROM THE RECORD. `completion.checks` still carries
     every criterion, verdict, `how` line and piece of evidence; the fold
     still renders all of it; shadowCompletionText still copies the full
     record; shadowSummaryHtml is still exported and still tested. Only the
     LEAD changed, and only on the clean path.

     SHADOW SPEAKS IN ITS OWN VOICE HERE. This is the moment Shadow hands
     the work back, so the line is Shadow's -- "Done — created x.txt with 10
     items" -- and shadowThirdPerson is deliberately NOT applied. The
     sentence is still the worker's own conclusion, selected and never
     composed, and it is still put through shadowNotSpeech so a record can
     never stand in for a result. */
  const nothingWaiting = m.state === "done" && !failed.length
    && !(typeof shadowMissionNeedsFounder === "function"
         && shadowMissionNeedsFounder(m))
    && !(m.intervention && m.intervention.id)
    && !(m.approval && !m.approval.used && m.pending_say)
    && !m.parked_say;
  if (nothingWaiting){
    /* ── SHADOW'S OWN CLOSING LINE WINS (founder, 2026-09-21, pass 10) ──
       THE BUG THIS FIXES. `work` is the gist of the worker's LAST message,
       so a task that asked for "a file of 10 lines about alien species"
       finished with Shadow appearing to say "Done -- a NASA-led reanalysis
       of JWST spectra...", which is one of the ten lines. The worker's
       output is EVIDENCE; the artifact is the deliverable; and the right
       level to describe the result at is the one the founder asked at.

       Shadow's own update for the final turn is written against exactly
       that -- the request, the worker's result, the artifact state and the
       verification state (shadow_runner's decide prompt) -- so where one
       exists it is the closing line. The worker gist stays the fallback,
       unchanged, for every mission with no update. */
    /* ── SHADOW'S CLOSING LINE, IN ORDER OF HOW WELL IT FITS (pass 12) ──
         completion.said   what Shadow said the work PRODUCED, stamped by
                           the one writer of a done mission, so the loop's
                           completion and the founder's Confirm carry the
                           same sentence. This is the only one written FOR
                           this moment -- it carries no ask.
         newest update     Shadow's last word about a turn. Better than the
                           worker's sentence for a mission with no result
                           line, and the shape every record before pass 12
                           has.
         the worker gist   the original fallback, unchanged.
       All three can be empty, and then the finish is "Done." -- which is
       the grounded answer for a mission whose work produced nothing
       describable, and is deliberately not filled in with a guess. */
    const stamped = (c && typeof c.said === "string") ? c.said.trim() : "";
    const closing = (stamped && !(typeof shadowNotSpeech === "function"
                                  && shadowNotSpeech(stamped)))
      ? stamped
      : ((typeof shadowLastUpdate === "function") ? shadowLastUpdate(m) : "");
    /* the worker's own closing sentence, or nothing -- never a record, and
       never a phrase invented to fill the gap */
    const said = closing || ((work && !(typeof shadowNotSpeech === "function"
                            && shadowNotSpeech(work))) ? work : "");
    /* "Done — created the file" reads as one sentence; "Done — I created
       the file" keeps its capital because the pronoun is one. Nothing else
       about the sentence is touched. */
    const tail = !said ? ""
      : (/^I\b|^I['\u2019]/.test(said)
          ? said : said.charAt(0).toLowerCase() + said.slice(1));
    return `<div class="shsaid shfrom-shadow shdonesum shdonesay"
        data-shdone="${escAttr(m.id)}">
      <div class="shsaidhead">Shadow</div>
      ${/* NO title ATTRIBUTE HERE, deliberately. The card hangs the whole
           `outcome` on the preview's hover, and on this path that string
           can be the worker's raw closing dump -- a file listing, a grep
           table. Hover is still a surface. The full record is behind Copy
           result and Open the chat, which is where it belongs. */""}
      <div class="shsaidtext">Done${tail ? " \u2014 " + esc(tail) : "."}</div>
      ${c.was ? `<div class="shdonewas">Replaced an earlier plan:
        ${esc(c.was)}</div>` : ""}
      ${/* ── THE DELIVERABLE, NOT JUST ITS NAME (founder, 2026-09-21,
             pass 14) ────────────────────────────────────────────────────
           "Founder confirmation controls WHETHER a proposal may become
           done. It does NOT control whether Shadow shows the resulting
           deliverable." A confirmed itinerary that finished as a filename
           and one line had been filed, not delivered.

           GROUNDED BY CONSTRUCTION. `completion.preview` is read off disk
           by mission_engine._complete through the same reader and the same
           ownership rule the evidence lane uses -- so this cannot show
           contents the artifact does not have, and where the worker's prose
           and the file disagree, this is the file.

           CONCISE BY DEFAULT. The reader bounds it to 24 lines; the cut is
           reported and drawn as the same ellipsis mark a decision preview
           uses. The whole file stays one click away behind the chip below,
           which is unchanged. */""}
      ${shadowDonePreviewHtml(c)}
      ${files}
      <div class="shdoneacts">${copyBtn}${verif}</div>
    </div>`;
  }

  return `<div class="shconfirm shdonesum" data-shdone="${escAttr(m.id)}">
    ${/* ── THE MOMENT IT LANDS (founder, 2026-09-17) ──────────────
         A finished task simply appeared, fully formed, indistinguishable
         from one that had been finished for an hour. This is the one beat
         that says the work just completed: a check that DRAWS ITSELF, then
         the verdicts, then the Summary easing in under them.

         CSS ONLY, AND IT RUNS ONCE. No state, no timer, no JS -- the mark
         animates on mount, which for this pane means when a done card is
         first rendered. A re-render of an already-done task replays it, and
         that is the honest cost of having no per-card memory; it is a few
         hundred milliseconds and it never blocks the content, which is
         drawn at full opacity underneath from the first frame for anyone
         with reduced motion on (see .shdoneburst in panel.css). */""}
    <div class="shdoneburst" aria-hidden="true">
      <svg viewBox="0 0 32 32" class="shdonetick"><circle cx="16" cy="16"
        r="14" class="shdonering"/><path d="M10 16.5l4 4 8-8"
        class="shdonecheck"/></svg>
    </div>
    <div class="shdonehead">
      ${/* "Done", and nothing about counts. `completion.headline` is still
           stamped by the server and still copied by shadowCompletionText --
           it is simply not what a founder is shown first. */""}
      <div class="shconfirmq">Done</div>
      ${copyBtn}
    </div>
    ${/* THE OBJECTIVE IS ALREADY THE TITLE of this pane and the head of the
         card above it; restating all 443 characters of it here made the
         conclusion the third thing on the card. What is left is the one
         fact this line adds. The criteria speak for themselves below. */""}
    ${/* WHAT WAS PRODUCED, when the server recorded any. Paths only -- the
         founder is told WHERE the work landed; the content is the summary's
         job and the chat's. */""}
    ${/* ── THE FINAL STATE, IN THE FOUNDER'S TERMS (founder, 2026-09-21,
           pass 2) ────────────────────────────────────────────────────────

         THE ASK: a finished task must answer "what was accomplished, what
         artefact exists, what was discarded, what remains" -- not "3 of 3
         checks passed", which is how Shadow convinced itself and is of no
         use to the person who asked for the work.

         EVERY LINE IS A RECORD FIELD. `completed`, `remains`, `was` and
         `revised` are stamped by mission_engine.completion_summary off the
         mission AS IT ENDED. Nothing here reads the transcript and nothing
         is concatenated out of worker messages -- the construction the
         founder ruled out, because a worker that narrated a plan it then
         abandoned would otherwise dictate the summary.

         SO A REDIRECTED TASK REPORTS THE OBJECTIVE IT FINISHED ON. The
         Africa-to-India case lands here as an India summary with one line
         naming what it stopped being; the Africa work is history, drawn by
         shadowRevisionsHtml, and never the result.

         FALLS BACK CLEANLY. A record stamped before these fields existed
         has neither list, so the block is skipped entirely and the card is
         exactly what it was. */""}
    ${c.was ? `<div class="shdonewas">Replaced an earlier plan:
      ${esc(c.was)}</div>` : ""}
    ${files ? `<div class="shdonesec">
      <div class="shdoneseclabel">What you can open</div>
      ${files}
    </div>` : ""}
    ${/* ── A CHECK IS NOT A RESULT (founder, 2026-09-21) ────────────────
         "Even in summary -- don't show user stuff he doesn't care about
         (Done checks and all)."

         WHAT LEFT THIS SURFACE: "What I completed" and "What remains", both
         built from `done_when`. They were an improvement on "3 of 3 checks
         passed" and still the wrong thing to lead with -- a criterion is
         written to be MATCHED, not read, and a list of them is a QA report
         however it is worded. The founder asked what happened, not how
         Shadow satisfied itself.

         WHAT LEADS INSTEAD is what they can act on: the file the work
         produced, and the worker's own closing account of it in its own
         words. Both are already on the record.

         NOTHING IS LOST. `completion.checks` still carries every criterion,
         verdict, `how` line and piece of evidence, and the Verification
         fold below -- closed, one click -- still renders all of it.
         shadowCompletionText still copies the full record to the clipboard,
         and `completed`/`remains` are still stamped by completion_summary
         for anything that wants them. Only the lead changed. */""}
    ${work ? `<div class="shdonework" title="${escAttr(c.outcome || "")}"
      >${esc(work)}</div>` : ""}
    ${summary}
    ${/* A CAVEAT IS PART OF THE ANSWER. A check that did NOT pass is the one
         piece of verification the founder genuinely needs on the surface --
         it qualifies the result rather than explaining the machinery. */""}
    ${/* THE CAVEAT IS A COUNT, NOT THE CRITERIA. Something that did not
         pass is the one piece of verification a founder genuinely needs on
         the surface -- it qualifies the result -- but the criteria
         THEMSELVES are the test report they asked not to read. So the
         surface says how many and where to look; the fold says which. */""}
    ${failed.length ? `<div class="shdonecaveat">${failed.length === 1
        ? "One check did not pass \u2014 see Verification below."
        : failed.length + " checks did not pass \u2014 see Verification below."
      }</div>` : ""}
    ${verif}
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
/* the produced deliverable, concisely, or "" -- see the note at its call
   site in shadowCompletionHtml */
function shadowDonePreviewHtml(c){
  const p = c && c.preview;
  if (!p || typeof p !== "object") return "";
  const text = String(p.text || "");
  if (!text.trim()) return "";
  return `<div class="shdoneprev">
    <pre class="shdectext">${esc(text)}</pre>
    ${p.truncated ? `<div class="shdeccut" aria-label="continues"
      >\u2026</div>` : ""}
  </div>`;
}

function shadowCompletionText(m){
  const c = m && m.completion;
  if (!c) return "";
  const head = ["Done — " + String(c.headline || "")];
  if (c.objective) head.push(String(c.objective));
  head.push(shadowTurnNow(c) + " of " + (c.max_turns || 0)
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
  /* THE UNKNOWN BRANCH HAD NO THROTTLE (2026-09-15). `held === undefined`
     made a read due on EVERY render until the answer landed -- and
     loadGoalTranscript has no in-flight guard of its own, so the first load
     fired one request per painted frame. That was survivable while the only
     caller was a chat the founder had opened on purpose; the agent-turn
     block reads for the selected mission automatically, which would have
     made it the loadShadowHome burst all over again (see the perf fold
     below).

     So the stamp now gates BOTH branches: the very first ask goes out
     immediately, and nothing else does until the window is up -- which also
     retries a request that was dropped. A terminal mission whose transcript
     is already held is still never re-read. Strictly fewer reads than
     before, and no new state: the same shTranscriptAt, the same
     SH_TRANSCRIPT_MS. */
  const asked = shTranscriptAt[sid];
  const waited = now - (asked || 0) > SH_TRANSCRIPT_MS;
  const due = (held === undefined) ? (asked === undefined || waited)
                                   : (live && waited);
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
/* ── THE FOUNDER SHOULD SEE THE DECISION, NOT THE NARRATION ──────────────
   (founder, 2026-09-15, from the README sign-off on the live dogfood.)

   THE SAME PROPOSITION ARRIVED THREE TIMES. The decider writes a question,
   a field label and a done_when check, and for a founder_confirm they are
   routinely one sentence in three costumes:

     question  "Does the new Shadow task-pane README section meet the bar --
                clear overview, setup/test instructions, and a short
                troubleshooting section?"
     label     "README has a clear overview, setup/test instructions, and a
                short troubleshooting section."
     signs off "README includes a clear overview, setup/test instructions,
                and a short troubleshooting section."

   Printing all three does not make the decision clearer; it makes the card
   a wall and the founder scan for the difference between them, of which
   there is none. So a line that adds nothing is not drawn.

   THE TEST IS DIRECTIONAL AND DELIBERATELY CONSERVATIVE. It asks "is this
   line WHOLLY CONTAINED in what is already on screen" -- overlap over the
   CANDIDATE's own tokens, not over the shorter of the two. A short question
   can therefore never swallow a longer label that adds something: "Was this
   a smoke test?" against "This was a smoke test and the round-trip is
   satisfactory -- close it out." scores 0.4 and the label stays. Only near
   duplicates cross 0.8.

   PRESENTATION ONLY: nothing is edited, merged or rewritten. Every string
   the decider wrote is still in the record, still sent, still validated,
   and still reachable -- a suppressed line rides on the title of the line
   that already says it. */
const SH_SAID_STOP = new Set(("a an the is are was were be been being do does "
  + "did and or but if of to in on for with that this it its as at by from "
  + "has have had not no so i you we they there here them their our your "
  + "into over under than then when which who whom what while also just "
  + "can could should would may might must will shall about").split(" "));

function shadowSaidWords(text){
  return new Set(String(text || "").toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(w => w.length > 1 && !SH_SAID_STOP.has(w)));
}

/* `said` is everything already on the card. Returns true when `line` adds
   nothing to it. An empty or near-empty line is never "redundant" -- there
   is nothing to compare, and hiding it would hide a real gap. */
const SH_SAID_SAME = 0.8;
function shadowAlreadySaid(line, said){
  const a = shadowSaidWords(line);
  if (a.size < 3) return false;
  const b = new Set();
  for (const s of [].concat(said || []))
    for (const w of shadowSaidWords(s)) b.add(w);
  if (!b.size) return false;
  let hit = 0;
  for (const w of a) if (b.has(w)) hit++;
  return hit / a.size >= SH_SAID_SAME;
}

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

/* A LABEL IS A NAME, NOT A BRIEF (founder, 2026-09-15). The decider may
   spend 200 characters on one (LABEL_MAX), and it does: the smoke-test ask
   carried a 112-character sentence -- "If not a smoke test: the actual
   objective -- what should change, in which surface, and what state counts
   as done." -- set in bold above an empty box. That is an INSTRUCTION, and
   an instruction belongs inside the box it instructs.

   So a long label on a field the founder TYPES into becomes the
   placeholder, and the prominent label steps aside. It is the same string,
   unedited, still the field's accessible name via aria-label, and the
   schema, the key, the validation and the payload are all untouched. A
   label on a chip field (boolean / choice / ranking) is never moved -- it
   has no box to move into. A required field keeps its label, because the
   REQUIRED marker must stay attached to something the eye lands on. */
const SH_LABEL_LONG = 80;

/* ── THE ASK IS THE CHECKLIST, SO THE CHECKLIST STEPS ASIDE ──────────────
   (founder, 2026-09-15, from the README sign-off on the live dogfood.)

   THE BRIEF SAID IT AND THEN THE ASK SAID IT AGAIN:

     DONE WHEN      "README includes a clear overview, setup/test
                     instructions, and a short troubleshooting section."
     YES SIGNS OFF  "README includes a clear overview, setup/test
                     instructions, and a short troubleshooting section."

   two blocks apart, the same string, because the intervention IS the
   founder confirmation for the one check left.

   WHY THE EXISTING GUARD DID NOT FIRE, and why it must not be widened:
   shadowMissionNeedsFounder() is `state === "paused"` plus a founder pause
   reason, and it is right about that -- it describes the PAUSED sign-off
   flow, where shadowCheckRowsHtml replaces the row with the checklist
   itself. This mission arrives the other way: `blocked`, block_reason
   "needs_founder", carrying an intervention. Loosening that predicate
   would change what the pause flow means. So this is a SECOND, narrower
   reason to stand the row down, and it earns it by proving coverage.

   THE PROOF IS PER CHECK, NOT A COUNT. Every UNMET check must be named by
   some boolean field of THIS intervention, through shadowIvSignsIndex --
   the same predicate the sign-off row already uses, which refuses any
   check that is not founder_confirm. So:

     one unmet founder_confirm, and the ask signs it      -> row hidden
     two unmet, the ask signs one                          -> row stays
     an unmet machine-tier check (the verifier's, never
       the founder's)                                      -> row stays
     an ordinary ask that confirms nothing                 -> row stays
     no intervention on the card at all                    -> row stays

   PRESENTATION ONLY: nothing about done_when, met, the tiers, confirms_check
   or the evaluation of any check changed. The criterion is still on screen,
   once, where the founder is being asked to sign it. */
function shadowAskCoversChecks(m){
  const iv = m && m.intervention;
  if (!iv || !Array.isArray(iv.fields) || !iv.fields.length) return false;
  const checks = (m.done_when || []);
  const unmet = [];
  checks.forEach((c, i) => { if (c && !c.met) unmet.push(i); });
  if (!unmet.length) return false;      /* nothing outstanding to stand in for */
  const signed = new Set();
  for (const f of iv.fields){
    const i = shadowIvSignsIndex(m, f);
    if (i !== -1) signed.add(i);
  }
  return unmet.every(i => signed.has(i));
}

function shadowIvFieldHtml(mid, f, signs, said){
  const d = shadowIvDraft(mid);
  const v = shadowIvValue(mid, f);
  const err = d.errors[f.key];
  const typed = f.type === "long_text" || SH_IV_INPUT[f.type] !== undefined;
  const longAsk = typed && !f.required
    && String(f.label || "").length > SH_LABEL_LONG;
  /* the label is the same sentence as the question or the check it signs
     off. The control keeps the name for a screen reader; the eye is spared
     reading it a third time. */
  const echoed = !longAsk && shadowAlreadySaid(f.label, said);
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
        ${longAsk ? `aria-label="${escAttr(f.label)}"` : ""}
        placeholder="${escAttr(f.help || (longAsk ? f.label : ""))}"
        >${esc(v == null ? "" : v)}</textarea>`;
      break;
    default: {
      const kind = SH_IV_INPUT[f.type];
      if (!kind){
        body = `<div class="shnewerr">This panel cannot ask for
          “${esc(f.type)}” yet — update Sutra to answer it.</div>`;
        break;
      }
      body = `<input type="${escAttr(kind)}" ${hook} data-shivtext="1"
        ${longAsk ? `aria-label="${escAttr(f.label)}"` : ""}
        value="${escAttr(v == null ? "" : String(v))}"
        placeholder="${escAttr(f.help || (longAsk ? f.label : ""))}">`;
    }
  }
  return `<div class="shivfield"${echoed
    ? ` role="group" aria-label="${escAttr(f.label)}"` : ""}>
    ${longAsk || echoed ? "" : `<label class="shnewlabel">${esc(f.label)}${
      f.required ? ' <span class="shivreq">required</span>' : ""}</label>`}
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
  /* EVERYTHING THE CARD ALREADY SAYS, in the order the founder reads it:
     the question, and the done_when checks any boolean here signs off. A
     field label that adds nothing to this is not drawn again. */
  const said = [iv.question].concat(iv.fields.map(f => {
    const i = shadowIvSignsIndex(m, f);
    return i === -1 ? "" : String(((m.done_when || [])[i] || {}).check || "");
  })).filter(Boolean);
  /* ── CONTEXT IS SECONDARY, AND ON A SIGN-OFF IT IS NOT DRAWN AT ALL ────
     (founder, 2026-09-15.)

     `context` is the decider answering "why can't you settle this yourself"
     -- Shadow's reasoning about its own limits. That is narration, and the
     founder is deciding, not auditing. On a founder_confirm it is never the
     thing that decides the answer: the QUESTION asks it and the SIGN-OFF
     CRITERION defines the bar, and those two are primary. So a card that
     carries confirms_check draws no context paragraph at all.

     Everywhere else it is drawn, floored at ONE line -- and skipped when it
     merely restates what is already above it.

     THE TEXT IS NEVER LOST. intervention.context is untouched in the
     record, still returned by the API, still exactly what the decider
     wrote; when the paragraph is not drawn it rides on the question's own
     title, so hovering the question shows Shadow's reasoning in full. No
     prompt, cap or stored field changed. */
  const signing = !!(iv.confirms_check
    || iv.fields.some(f => shadowIvSignsIndex(m, f) !== -1));
  const ctx = String(iv.context || "").trim();
  const showCtx = !!ctx && !signing && !shadowAlreadySaid(ctx, said);
  return `<div class="shiv" data-shivform="${escAttr(iv.id || "")}">
    <div class="shivq"${ctx && !showCtx
      ? ` title="${escAttr(ctx)}"` : ""}>${esc(iv.question || "")}</div>
    ${showCtx ? `<p class="shnewsub shivctx"
      title="${escAttr(ctx)}">${esc(ctx)}</p>` : ""}
    ${(iv.evidence || []).length ? `<div class="shivev">${
      iv.evidence.map(e => `<div class="shivevrow">${
        e.ref ? `<span class="shivevref">${esc(e.ref)}</span>` : ""
      }<span>${esc(e.text || "")}</span></div>`).join("")}</div>` : ""}
    ${iv.fields.map(f => shadowIvFieldHtml(m.id, f,
      shadowIvSignsHtml(m, f), said)).join("")}
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
/* THE TURN THE WORKER IS ACTUALLY ON (founder, 2026-09-16).

   turns_used counts turns that FINISHED -- the backend increments it after
   the boundary arrives, which is right for a budget and wrong for a status
   line. Between Shadow's instruction and the worker's last word the card
   read "turn 3 of 30" while turn 4 was the one being worked, and across a
   restart the in-flight turn was not recorded anywhere at all.

   The engine now stamps `turn_open` for exactly that span. This prefers it
   and falls back to turns_used, so a mission from before the field existed,
   a finished mission, and an idle one all read exactly as they did. The
   BUDGET is deliberately NOT changed to use this: max_turns is compared
   against turns_used in the engine, and a meter that disagreed with the
   thing that ends the mission would be the worse of the two bugs. */
function shadowTurnNow(m){
  const open = Number(m && m.turn_open) || 0;
  const used = Number(m && m.turns_used) || 0;
  return open > used ? open : used;
}

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

/* ── WHAT THE WORKER AGENT JUST DID ──────────────────────────────────────
   THE RHS IS SHADOW REPORTING, NOT THE WORKER CHAT. This is the one block
   that speaks for the delegate, and it is deliberately ONE message: the
   agent's latest say, not the transcript. The whole transcript is still one
   click away behind "Show worker chat", and the real session is behind
   "Open the chat" in the header -- those two surfaces are unchanged and
   this does not replace either.

   EVERY SOURCE HERE IS ALREADY ON THE RECORD OR ALREADY FETCHED. No field
   is invented, no endpoint is added:

     1. the live transcript, through shadowTaskTranscript -- the SAME
        throttled reader the worker-chat block already uses, at the same
        SH_TRANSCRIPT_MS, for the ONE mission in focus. `role: "assistant"`
        is the delegate's own turn (goalTurnsToMessages), and the last one
        is what it just reported.
     2. result_excerpt, for a finished mission whose session may be gone.

   Neither present -> nothing drawn. A block that says "no summary" is
   furniture, and this pane is meant to be calm. */
function shadowAgentSay(m){
  const sid = m && m.target_session;
  if (sid && typeof shadowTaskTranscript === "function"){
    const live = SH_TERMINAL.indexOf(m.state) === -1;
    const msgs = shadowTaskTranscript(sid, live);
    if (Array.isArray(msgs)){
      for (let i = msgs.length - 1; i >= 0; i--){
        const t = msgs[i];
        if (t && t.role === "assistant" && String(t.text || "").trim())
          return String(t.text).trim();
      }
    }
  }
  const ex = m && m.result_excerpt;
  return (ex && String(ex).trim()) || "";
}

/* ── THE CONTROL PLANE IS NOT THE REPORT (founder, 2026-09-15) ───────────
   WHAT WENT WRONG. The delegate is itself a governed session, so its turn
   opens with the same machinery this repo makes every session emit -- a
   PLACEMENT line, an input-routing block (TYPE / HOME / ROUTE / FIT /
   ACTION), a depth block (TASK / DEPTH / EFFORT / COST / IMPACT), and a
   TRIAGE / trace tail. Taking "the last assistant message" verbatim put all
   of that on the founder's screen: a turn that had nothing to say for a
   human filled the pane with its own scaffolding.

   That material is addressed to the orchestration layer, not to the
   founder. It is stripped HERE, at the presentation boundary, and nowhere
   else: the delegate still emits it, the transcript still stores it, the
   session still shows it, and "Open the chat" still opens the whole thing
   unabridged. Nothing about generation, storage or the worker prompt moved.

   The list is exactly the vocabulary this repo's own governance emits, so a
   line is dropped only when it is a LABEL AT THE HEAD OF A LINE followed by
   a colon -- prose that merely mentions the word is untouched. */
const SH_CONTROL_HEAD = new RegExp(
  "^[\\s>*#\\-]*(" + [
    "PLACEMENT", "INPUT ROUTING", "GROUNDING", "DOMAIN_REF", "CYNEFIN",
    "TYPE", "HOME", "ROUTE", "FIT", "ACTION", "OBJECTIVE",
    "TASK", "DEPTH", "EFFORT", "COST", "IMPACT",
    "TRIAGE", "ESTIMATE", "ACTUAL", "TRACE", "OS TRACE", "BLUEPRINT",
  ].join("|") + ")\\s*[:\u00b7]", "i");
/* rules, box art and the fence markers around a code block: furniture, and
   never the sentence the founder is looking for */
const SH_RULE_LINE = /^[\s]*[=\-_~*\u2500-\u257F\u2014\u2013]{3,}[\s]*$/;

function shadowSayClean(text){
  let t = String(text || "");
  /* the mission tag the delegate's own turns carry -- the workspace already
     strips it for display, and this is the same strip for the same reason */
  if (typeof goalStripTag === "function") t = goalStripTag(t);
  const out = [];
  let fenced = false;
  for (const raw of t.split(/\r?\n/)){
    const line = raw.trim();
    if (/^```/.test(line)){ fenced = !fenced; continue; }
    if (fenced) continue;                       /* code is not a summary */
    if (!line) continue;
    if (SH_RULE_LINE.test(line)) continue;
    if (SH_CONTROL_HEAD.test(line)) continue;
    /* the parenthetical that trails a PLACEMENT line */
    if (/^\(.*(domain_ref|confidence)\s*=/.test(line)) continue;
    /* A TABLE IS A DIAGNOSTIC, NOT A SENTENCE (founder, 2026-09-15). The
       delegate reports in markdown, and a stop notice arrives as a heading
       over a `| Field | Value received | Problem |` grid. Joined into one
       line that grid is unreadable -- and it carries no terminal
       punctuation, which is exactly how it fused onto the heading above it
       and got chopped mid-row on the founder's screen. Rows go; the prose
       around them stays; the whole table is still in the worker chat,
       untouched, behind Open the chat. */
    if (/^\|/.test(line)) continue;
    /* A HEADING IS A COMPLETE THOUGHT. Keep the words, drop the hashes, and
       CLOSE IT: the heading is usually the one sentence the founder wants
       ("Stopped -- objective is not actionable"), and without a terminator
       shadowSayGist cannot see where it ends. Nothing is added but the full
       stop -- every word is the worker's own. */
    const head = line.match(/^#{1,6}\s+(.*)$/);
    if (head){
      const said = head[1].trim();
      if (said) out.push(/[.!?:;]$/.test(said) ? said : said + ".");
      continue;
    }
    out.push(line);
  }
  /* inline emphasis markers, for the same reason the hashes go: the words
     are the worker's, the asterisks are markdown furniture, and a preview
     that reads "**Count: 7 numbered checks**" is showing the founder the
     syntax instead of the sentence. Backticks stay -- a path or a command
     in a preview is clearer fenced than bare. */
  return out.join(" ")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/\s+/g, " ").trim();
}

/* The openers a delegate puts above its actual report. A sentence counts as
   one ONLY when almost nothing is left after the phrase -- so "What I did."
   is an announcement and is skipped, while "What I did: updated the README
   with setup instructions" carries its own news and is kept whole. The
   three-word floor is measured with shadowSaidWords, so stopwords cannot
   pad a heading into looking substantive. */
const SH_SAY_FILLER = [
  /^what i (did|found|changed|ran|tested|checked|built|fixed)\b/i,
  /^here'?s (what i (did|found|changed)|the (summary|result))\b/i,
  /^(done|completed|finished|all done|that'?s it|no changes)\b/i,
  /^(summary|results?|outcome|status|update|notes?|next steps?)\b/i,
  /^(what'?s left|tl;?dr|changes|files changed|conclusion)\b/i,
  /^i (completed|finished|have (completed|finished)|did) (the|this|it|that)\b/i,
];
function shadowSayFiller(sentence){
  const s = String(sentence || "").trim();
  if (!s) return true;
  for (const re of SH_SAY_FILLER){
    const hit = s.match(re);
    if (!hit) continue;
    const rest = s.slice(hit[0].length)
      .replace(/^[\s:\u2014\u2013\-,.]+/, "").replace(/[.!?\s]+$/, "");
    if (shadowSaidWords(rest).size < 3) return true;
  }
  return false;
}

/* A REPORT IS ONE LINE (founder, 2026-09-15). Even once the control plane is
   gone a turn can be thousands of characters of tool narration, and three
   sentences of it was still a paragraph where the founder wanted a glance.
   ONE sentence, and a hard cap that cuts on a sentence end when there is one
   in range so the line never ends mid-word. Everything else is in the chat. */
const SH_SAY_MAX = 160;
const SH_SAY_SENTENCES = 1;
/* `drop` is an OPTIONAL second predicate, used by the completion card to
   refuse evidence. Called with one argument this function behaves exactly as
   it did, which is what keeps the worker timeline byte-identical. */
function shadowSayGist(text, drop){
  const t = String(text || "").trim().replace(/\s+/g, " ");
  if (!t) return "";
  /* SPLIT ON A REAL BOUNDARY, AND NEVER DROP TEXT (fixed 2026-09-15).
     The old matcher required a run of .!? followed by whitespace or end,
     and simply MATCHED NOTHING at a position where that failed -- so a
     sentence containing a filename was silently skipped and the pane showed
     its tail: "Updated marketplace/plugin/sutra-ui/README.md with setup and
     testing instructions." previewed as "md with setup and testing
     instructions." A split on whitespace PRECEDED by sentence punctuation
     has no such hole: every character survives, and the dot inside
     README.md is not a boundary because no space follows it. */
  const parts = t.split(/(?<=[.!?])\s+/).filter(x => x.trim());
  if (!parts.length) return "";
  /* SKIP THE ANNOUNCEMENT, KEEP THE NEWS (founder, 2026-09-15). The live
     pane read "WORKER AGENT · TURN 1 / What I did." -- real worker text,
     and worth nothing: the delegate writes a `## What I did` heading and
     then says what it did underneath. The heading survives cleaning (it is
     the worker's own words, and on a stop notice it is exactly the sentence
     the founder wants), so the axis is not heading-ness, it is whether the
     sentence CARRIES anything.

     NOTHING IS GENERATED. The next real sentence is selected from the same
     turn; if every sentence is an announcement, the block draws nothing
     rather than announcing an announcement. */
  let first = 0;
  while (first < parts.length
         && (shadowSayFiller(parts[first])
             || (typeof drop === "function" && drop(parts[first])))) first++;
  if (first >= parts.length) return "";
  let gist = parts.slice(first, first + SH_SAY_SENTENCES).join(" ").trim();
  /* THE SAFETY NET FOR STRUCTURE THAT GOT THIS FAR. shadowSayClean drops
     table rows, so on the path we know about this never fires -- but a
     "sentence" containing a pipe is a grid whatever produced it, and the
     founder must never again read half a row. Cut AT the structure rather
     than through it, and say nothing if that leaves nothing. */
  const bar = gist.indexOf("|");
  if (bar !== -1) gist = gist.slice(0, bar).trim();
  if (!gist) return "";
  /* an ellipsis only where the line was actually CUT. A first sentence that
     ended on its own full stop is a whole sentence, and "open. ..." reads as
     a stutter -- the rest of the turn is behind Open the chat, which the
     header already says. */
  const cut_mid = gist.length < t.length && !/[.!?]$/.test(gist);
  if (gist.length <= SH_SAY_MAX) return gist + (cut_mid ? " \u2026" : "");
  const cut = gist.slice(0, SH_SAY_MAX);
  const stop = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("? "),
                        cut.lastIndexOf("! "));
  return (stop > SH_SAY_MAX * 0.5 ? cut.slice(0, stop + 1)
                                  : cut.replace(/\s\S*$/, "")) + " \u2026";
}

/* ── THE WORKER'S OWN REPORT FOR THE TURN (founder, 2026-09-16) ──────────
   WHAT THIS CHANGES, AND WHAT IT DOES NOT. Until now the line under a turn
   was whatever shadowSayGist could salvage from the turn's prose -- the
   first sentence that survived cleaning. That is an EXCERPT, and an excerpt
   only accidentally answers the question the heading asks ("what did the
   worker do this turn?"). The live pane has read "Plan mode is active, so I
   have not created the file." for a turn whose actual news was that a plan
   had been written.

   SO THE WORKER IS ASKED TO SAY IT, and this READS what it said. The
   manifest's WORKING AGREEMENT (app._WORKER_AGREEMENT) now asks for

       REPORT: <one sentence>

   on a line of its own -- the same shape, and for the same reason, as the
   DONE-CHECK line that has always sat beside it. This function is a
   SELECTOR, not a summariser: no model is asked, no sentence is composed,
   and every word it returns is the worker's own. When the worker wrote no
   REPORT the caller falls back to exactly the behaviour it had before, so
   every historical mission renders byte-for-byte as it always did.

   IT IS STILL RUN THROUGH THE EXISTING FILTERS. What comes back here is raw
   worker text, so the caller passes it through shadowSayClean and
   shadowSayGist exactly as it passes ordinary prose -- a REPORT that is a
   table row, a control-plane label or a fenced blob cleans to nothing and
   the fallback takes over. This cannot widen what reaches the founder.

   FENCED LINES ARE NOT THE REPORT, for the same reason shadowSayClean drops
   them: a REPORT quoted inside a code block is the worker showing the
   format, not using it.

   THE FIRST VALID ONE WINS. A turn can carry several -- several lines in
   one message, or one in each of several messages -- so `ok` is an OPTIONAL
   predicate the caller uses to say what "valid" means to it, the same shape
   shadowSayGist's `drop` already has. The timeline passes "survives the
   cleaners"; called with one argument this returns the first report line it
   finds, which is what any other reader wants. Scanning forward makes the
   answer depend on the worker's own order rather than on how many messages
   the turn happened to hold. */
const SH_REPORT_LINE = /^[\s>*#\-]*REPORT\s*[:·]\s*(.+)$/i;

function shadowSayReport(text, ok){
  let t = String(text || "");
  /* the same mission tag strip the rest of this block applies, for the same
     reason -- the underlying text is never altered */
  if (typeof goalStripTag === "function") t = goalStripTag(t);
  let fenced = false;
  for (const raw of t.split(/\r?\n/)){
    const line = raw.trim();
    if (/^```/.test(line)){ fenced = !fenced; continue; }
    if (fenced) continue;
    const hit = line.match(SH_REPORT_LINE);
    if (!hit) continue;
    /* the emphasis markers go for the same reason they go in shadowSayClean:
       "**REPORT:** wrote the file" is the syntax, not the sentence */
    const said = String(hit[1] || "")
      .replace(/\*\*([^*]+)\*\*/g, "$1").replace(/__([^_]+)__/g, "$1")
      .replace(/\*\*/g, "").replace(/\s+/g, " ").trim();
    if (!said) continue;
    if (typeof ok === "function" && !ok(said)) continue;
    return said;
  }
  return "";
}

/* ── A REPORT ENDS ON A FULL STOP, OR IT ENDS WHERE IT ALWAYS DID ───────
   (founder, 2026-09-16.)

   THE RULE. shadowSayGist takes the first sentence that carries news and,
   when that sentence is longer than SH_SAY_MAX, cuts it and marks the cut
   with an ellipsis. For ordinary prose that is right -- the turn's first
   sentence is the only candidate there is. A REPORT is different: the
   worker was asked for the turn's outcome, and if its opening sentence
   overruns, a LATER sentence of the same report is still the worker's own
   complete thought and may fit whole. Showing that beats showing half of
   the first one.

   ONLY WHEN SOMETHING WAS ACTUALLY CUT. The existing answer is computed
   first and returned untouched unless it carries the cut marker, so a
   report that already fits -- which is nearly all of them -- takes exactly
   the path it took before, byte for byte. This can only ever replace an
   ellipsis with a whole sentence; it can never shorten a line that was
   already complete.

   WHAT COUNTS AS A COMPLETE SENTENCE, and it is deliberately mechanical:
   it ends in . ! or ? after the same split shadowSayGist uses, it fits the
   same cap, it carries no pipe (a grid is not a sentence, the same guard
   as below), and it is not an announcement (shadowSayFiller -- "Done."
   fits and completes and says nothing). LONGEST WINS, earliest on a tie,
   so the answer does not depend on how the worker ordered equal-length
   clauses.

   NOTHING IS COMPOSED. Every character returned is the worker's own, and
   no punctuation is added -- a sentence that the worker did not finish is
   not made to look finished. If no whole sentence fits, the existing cut,
   ellipsis and all, is what the founder sees: honest about being partial
   beats invented completeness.

   THE FALLBACK FOR A TURN WITH NO REPORT IS NOT ROUTED THROUGH THIS, on
   purpose -- shadowTimelineEvents still calls shadowSayGist directly for
   ordinary prose, so every historical turn renders exactly as it did. */
function shadowSayWhole(text){
  const t = String(text || "").trim().replace(/\s+/g, " ");
  if (!t) return "";
  const parts = t.split(/(?<=[.!?])\s+/).filter(x => x.trim());
  let best = "";
  for (const raw of parts){
    const p = raw.trim();
    if (!/[.!?]$/.test(p)) continue;        /* the worker never closed it */
    if (p.length > SH_SAY_MAX) continue;    /* it does not fit either */
    if (p.indexOf("|") !== -1) continue;    /* a grid is not a sentence */
    if (shadowSayFiller(p)) continue;       /* an announcement is not news */
    if (p.length > best.length) best = p;   /* > keeps the earliest tie */
  }
  return best;
}

/* The line the timeline draws for a REPORT: the existing answer, unless it
   had to be cut and a whole sentence of the same report fits instead. */
function shadowReportGist(text){
  const said = shadowSayGist(text);
  if (!said || !/\s…$/.test(said)) return said;
  return shadowSayWhole(text) || said;
}

/* ── A REPORT LINE IS A FIELD, NOT PROSE (founder, 2026-09-16) ───────────
   THE HOLE THIS CLOSES, found writing the tests. SH_CONTROL_HEAD drops a
   control-plane LABEL at the head of a line -- but "REPORT: PLACEMENT: D0
   ..." does not start with PLACEMENT, it starts with REPORT, so the label
   rode into the founder-facing line behind a prefix the filter had never
   heard of. The selector above already refuses that report (the extracted
   text cleans to nothing), and without this the fallback would then serve
   the very same line back as ordinary prose.

   SO THE FALLBACK NEVER SEES A REPORT LINE. Once shadowSayReport has had
   its go, a REPORT line has been read as a field and is spent: either it
   was usable, in which case we are not in the fallback at all, or it was
   not, in which case it is exactly the material this pane exists to keep
   off the screen.

   DELIBERATELY NOT IN shadowSayClean. That function is shared with the
   completion card (shadowResultGist), whose `outcome` is the worker's last
   message and may legitimately BE the report sentence; teaching the shared
   cleaner to delete it would change a surface this work is not about. The
   drop is applied here, by the one caller that needs it, which is the same
   rule the completion card's own SH_EVIDENCE filter follows. */
function shadowSayDropReport(text){
  return String(text || "").split(/\r?\n/)
    .filter(line => !SH_REPORT_LINE.test(line.trim())).join("\n");
}

/* THE TURN HAD NOTHING FOR YOU IN IT. A delegate turn that was entirely
   control plane is not the same as no turn at all -- but the preview line is
   a QUOTE OF THE WORKER, so when the worker said nothing a human can read,
   this draws no line at all (founder, 2026-09-15).

   IT USED TO SUBSTITUTE A PHRASE. A state-derived stand-in ("Working on it.")
   sat here and read, on screen, exactly like something the worker had said --
   the one thing this block must never do. A fabricated sentence in a quote
   slot is worse than a heading with nothing under it, so the fallback table
   is gone and nothing is invented in its place. The turn number in the
   heading still carries the fact that a turn happened, and the whole turn --
   control plane included -- is behind Open the chat, unabridged. */
/* ONE ROW OF THE TIMELINE. The worker's own words for one turn, or nothing. */
/* ── WAITING HAS A FACE (founder, 2026-09-17) ────────────────────
   THE GAP. Between pressing send and Shadow answering, the pane showed the
   founder's own sentence and then nothing -- so a reply that was being
   composed and a reply that was never coming looked identical. The state was
   already known (shadowTalk().busy, set by shadowTalkSend for exactly the
   span of the request); it simply was not drawn.

   NOT A SPINNER ON THE WHOLE PANE. It is a row in the stream, in the place
   the answer will appear, so the answer replaces the waiting rather than
   arriving somewhere else. It carries no clock: this is a request in flight,
   usually seconds, and a timer on it would invite the founder to watch it.

   IT IS DERIVED, NEVER STORED. No new state, nothing on the record, and it
   cannot outlive the request -- busy goes false in the same function that
   set it, including on the error path. */
/* ── ONE COLUMN, TWO SPEAKERS (founder, 2026-09-21, pass 4) ──────────────
   THE MODEL THE PRODUCT NOW CLAIMS: "I am talking to Shadow, and Shadow is
   working on my task" -- not "I am watching Shadow operate a worker-agent
   pipeline". So the main surface has exactly two visible participants, and
   every ordinary message in the stream is built here so they cannot drift
   apart:

     you     right-aligned, filled, compact -- the only speaker whose
             message is an INPUT rather than a report
     shadow  left-aligned, roomy, no card -- the voice being talked to

   THE CLASS NAMES ARE ADDITIVE. .shsaid / .shsaidhead / .shsaidtext are the
   blocks this pane has always spoken in; .shfrom-you and .shfrom-shadow are
   modifiers on top, so every row that is not a plain message (an ask, a
   decision, a superseded revision, a fold) keeps the surface it already had
   and is untouched by this. A DECISION still looks like a decision; a
   SENTENCE stopped looking like one. */
function shadowSaidRowHtml(who, bodyHtml, extra, head){
  const mine = who === "you";
  /* A SPEAKER IS NAMED ONCE PER RUN (pass 5). Three consecutive Shadow
     messages each labelled SHADOW is a log's habit, not a conversation's;
     `head === false` drops the label and the run reads as one voice
     continuing. The row keeps its class, so alignment and the screen
     reader's grouping are unchanged. */
  return `<div class="shsaid shfrom-${mine ? "you" : "shadow"}${
      extra ? " " + extra : ""}${head === false ? " shrun" : ""}">
    ${head === false ? "" : `<div class="shsaidhead">${
      head || (mine ? "You" : "Shadow")}</div>`}
    <div class="shsaidtext">${bodyHtml}</div>
  </div>`;
}

/* ── THE WORKER IS AN IMPLEMENTATION DETAIL (founder, 2026-09-21, pass 4) ──
   WHAT THIS REPLACES. The stream drew one row per worker execution, headed
   "Worker agent · turn 3", and the founder had to understand a turn count to
   read their own task. The direction is explicit: internally retain turn
   numbers, externally show none, and let the user see a continuous Shadow
   conversation regardless of how many worker executions happened.

   NOTHING IS FABRICATED, WHICH IS THE HARD PART. Shadow does not get to
   invent progress it has not observed. So a narration row is still the
   WORKER'S OWN REPORTED SENTENCE -- selected, never composed, by exactly the
   machinery that selected it yesterday (shadowSayReport -> shadowSayClean ->
   shadowSayGist). What changed is attribution and salience: it is drawn as
   Shadow speaking, without a turn number, and only when it carries a real
   transition.

   THE SALIENCE RULE, and it is deliberately mechanical rather than clever:

     keep   the FIRST report (the work started, and that is news)
     keep   the LAST report (the current state, and the founder is never
            left blind about where the task actually is)
     drop   a report whose words repeat the previous kept one
     drop   a report written in the PRESENT PARTICIPLE -- "Checking the rail
            routes", "Searching for flights", "Still working". That aspect is
            the "I'm searching... I'm checking... I'm checking again" stream
            the direction names, and it is a statement about being mid-task
            rather than about having reached anything.
     keep   everything else, including every PAST-TENSE report ("Checked the
            travel legs", "Rebuilt the route"), because a completed step IS a
            meaningful transition and dropping it would lose real history.

   Tense is the discriminator on purpose: it is a property of the worker's
   own sentence, needs no model call, and cannot silently swallow a result.
   A mission with one or two reports is never filtered at all. */
const SH_WORK_NOISE = [
  /* present participle at the head of the sentence, with or without its
     pronoun: the grammar of "in flight", not of "done" */
  /^(i’m |i'm |i am |we’re |we're |we are |just |now |still )?(search|look|check|re-?check|read|re-?read|run|re-?run|review|verify|verifying|scan|examin|investigat|explor|inspect|analys|analyz|continu|work|proceed|start|go)\w*ing\b/i,
  /^(still|now|next|then)\b/i,
  /^(let me|going to|about to|i will|i’ll|i'll)\b/i,
  /^(no (change|update|news)s?|nothing (yet|new|to report))\b/i,
];
function shadowWorkNoise(say){
  const t = String(say || "").trim();
  if (!t) return true;
  for (const re of SH_WORK_NOISE) if (re.test(t)) return true;
  return false;
}

/* ── A RECORD IS NOT A SENTENCE (founder, 2026-09-21, pass 5) ────────
   "Do NOT simply rename worker records to Shadow. That was the previous
   mistake." Pass 4 attributed the worker's selected line to Shadow, which
   was right for a line like "Rebuilt the route around five days in London"
   and WRONG for the lines that are machinery wearing a sentence's clothes:

       10 tool calls — Web search 6, fetched 3…
       DONE-CHECK: india-cricket-news.txt exists and has 10 items
       Sent worker first instruction: You are a delegate session…

   Those are bookkeeping. Attributing them to Shadow put the execution log
   back on the surface under a friendlier name.

   SO A LINE MUST EARN ITS PLACE. This is a REJECTION list, not a rewriter:
   a line that matches is not said at all, and nothing is generated to stand
   in its place. Silence is the correct output -- pass 5 says so in as many
   words. Every rejected line is still in the record and still behind Open
   the chat.

   IT IS KEYED ON SHAPE, NOT ON TOPIC. Each pattern below names a form the
   substrate emits (a counter, a labelled check, an instruction addressed to
   the worker, an id, a fence), so prose that merely mentions tools or a
   file is untouched. */
const SH_NOT_SPEECH = [
  /* tool bookkeeping: "10 tool calls", "3 tool calls — Web search 2…" */
  /^\s*\d+\s+tool[ -]calls?\b/i,
  /\btool[ -]calls?\s*[:—–-]/i,
  /* the machine-readable lines the worker agreement asks for, quoted raw */
  /^\s*(DONE-?CHECK|REPORT|VERIFY|PROBE|EVIDENCE|CRITERION|ANSWER)\s*[:·]/i,
  /* Shadow talking to the WORKER, not to the founder */
  /^\s*(sent|sending|re-?sent|issued|composed|chose|selecting|selected)\b[^.]{0,40}\b(worker|delegate)\b/i,
  /^\s*(worker|delegate)\s+(instruction|turn|session|contract|brief)\b/i,
  /\byou are a delegate session\b/i,
  /* orchestration vocabulary the founder has no use for */
  /\b(answer fence|done_when|pending_say|turn_open|target_session|mission fence|task fence|invalidat\w+ for revision)\b/i,
  /* a bare mission id is an identifier, never a sentence */
  /^\s*m-[0-9a-f]{8,}\b/i,
  /* a JSON or fence fragment that survived the cleaners */
  /^\s*[{\[]|^\s*```/,
  /* ── A SERIALIZED PAYLOAD IS NEVER A SENTENCE (founder, 2026-09-21,
       pass 6) ────────────────────────────────────────
     WHAT REACHED THE FOUNDER'S SCREEN:

         "T20I series against Bangladesh announced"… "url"… {…}

     a web-search result object flattened into one line. The rules above
     only caught a payload that OPENED with a brace, and this one opens
     with a quoted headline -- so it read as prose, survived the gist, and
     was drawn as something Shadow said.

     THESE ARE SHAPE TESTS, NOT TOPIC TESTS. A brace, a JSON key, a bare
     URL and a run of straight quotes are all things a machine writes and a
     person does not; ordinary prose with an apostrophe, a file name or a
     domain mentioned in words is untouched. A line that matches is not
     said at all -- the worker's output still flows through the mission and
     the completion record exactly as before. */
  /[{}]/,                                   /* a brace, anywhere */
  /"[A-Za-z_][\w .-]*"\s*:/,                 /* a JSON key */
  /\bhttps?:\/\//i,                         /* a bare URL */
  /\b(url|href|link|snippet|source_?url|published_?at|timestamp)\s*[:=]/i,
  /(?:"[^"]*"[^"]*){3,}/,                   /* three quoted fragments in a row */
  /* ── THE DEBUGGER'S VOCABULARY (founder, 2026-09-21, pass 8) ────────
     Named outright as "not useful conversation content": an assertion
     Shadow made to itself, a note about the renderer, a reference to the
     record or the payload or the tool count. Each is matched as a LABELLED
     CLAIM at the head or as a distinctive phrase, so prose that merely uses
     the word ("the record was set in 2019") is untouched. */
  /^\s*shadow established\b/i,
  /\bshown in part\b/i,
  /^\s*(record|payload|evidence|probe|verdict|artifact facts)\s*[:=]/i,
  /\b\d+\s+distinct\b/i,
  /\bopen the task'?s chat for the whole\b/i,
];
function shadowNotSpeech(text){
  const t = String(text || "").trim();
  if (!t) return true;
  for (const re of SH_NOT_SPEECH) if (re.test(t)) return true;
  return false;
}

/* ── SHADOW IS THE NARRATOR, NOT A VENTRILOQUIST (founder, 2026-09-21,
     pass 6) ───────────────────────────────────────────
   THE BUG PASS 5 LEFT. A worker report is written in the FIRST PERSON --
   "I’ll pull current India cricket news and write it to a file" -- and
   attributing that sentence to Shadow makes Shadow claim the worker’s own
   intentions as its own. The founder read a Shadow message that was really
   the worker talking with a new name on it:

       "Do not expose worker-facing narration/instructions as if they are
        Shadow speaking to the user ... Shadow should be the narrator /
        coordinator of the work, not a ventriloquist for the worker."

   THE SHIFT IS DETERMINISTIC AND ADDS NO WORDS. No model is asked, no
   sentence is composed, no progress is invented: the subject is moved from
   first person to the worker and every content word stays exactly as the
   worker wrote it. "I found 10 current items" becomes "The worker found 10
   current items" -- the same claim, correctly attributed.

   TWO PLACES ARE TOUCHED AND NO OTHERS:
     the HEAD of the sentence, where a subject can be rewritten without
       guessing at grammar; and
     the PRONOUNS after it, as whole words only.
   A sentence with no first person in it is returned byte-identical, so a
   subject-less report ("Created india-cricket-news.txt with 10 items")
   passes through untouched -- it is not ventriloquism and rewriting it
   would be the guesswork this deliberately refuses.

   THE ONE EXCEPTION IS THE BARE PRESENT PARTICIPLE, which is subject-less
   but reads as Shadow doing the work ("Checking the last two sources"). It
   is recognised by exactly the vocabulary SH_WORK_NOISE already uses, so
   nothing new is being guessed at, and it is narrated the same way.

   THIS DOES NOT APPLY TO SHADOW’S OWN REPLIES. What Shadow says in the
   task chat is Shadow talking to the founder, and its "I" is its own. */
const SH_PERSON_HEAD = [
  [/^I\s*['\u2019]\s*ll\b/, "The worker will"],
  [/^I\s*['\u2019]\s*ve\b/, "The worker has"],
  [/^I\s*['\u2019]\s*m\b/,  "The worker is"],
  [/^I\s*['\u2019]\s*d\b/,  "The worker would"],
  [/^I will\b/,  "The worker will"],
  [/^I have\b/,  "The worker has"],
  [/^I am\b/,    "The worker is"],
  [/^I would\b/, "The worker would"],
  [/^Let me\b/i, "The worker will"],
  [/^My\b/,      "The worker\u2019s"],
  [/^We\s*['\u2019]\s*ll\b/i, "The worker will"],
  [/^We\s*['\u2019]\s*ve\b/i, "The worker has"],
  [/^We\s*['\u2019]\s*re\b/i, "The worker is"],
  [/^We will\b/i, "The worker will"],
  [/^We have\b/i, "The worker has"],
  [/^We are\b/i,  "The worker is"],
  [/^Our\b/i,     "The worker\u2019s"],
  [/^I\b/,  "The worker"],
  [/^We\b/, "The worker"],
];
const SH_PERSON_REST = [
  [/\bI\s*['\u2019]\s*ll\b/g, "it will"],
  [/\bI\s*['\u2019]\s*ve\b/g, "it has"],
  [/\bI\s*['\u2019]\s*m\b/g,  "it is"],
  [/\bI\s*['\u2019]\s*d\b/g,  "it would"],
  [/\bI will\b/g, "it will"],
  [/\bI have\b/g, "it has"],
  [/\bI am\b/g,   "it is"],
  [/\bI\b/g,      "it"],
  [/\bmy\b/g,     "its"],
  [/\bmine\b/g,   "its"],
  [/\bwe\s*['\u2019]\s*(?:ll|ve|re)\b/gi, "it"],
  [/\bwe\b/gi,    "it"],
  [/\bour\b/gi,   "its"],
];
/* the present participles SH_WORK_NOISE already recognises as "in flight" */
const SH_GERUND_HEAD =
  /^(search|look|check|re-?check|read|re-?read|run|re-?run|review|verify|scan|examin|investigat|explor|inspect|analys|analyz|continu|work|proceed|start|go|writ|gather|collect|compil|updat|build|creat)\w*ing\b/i;

/* A SUBJECT-LESS PAST-TENSE REPORT IS STILL THE WORKER'S ("Cut the list to
   the last 7 days and re-checked each item"). It names no one, so it reads
   as Shadow claiming the work -- the same ventriloquism in a quieter voice.
   Recognised ONLY by an unambiguous past-tense opener: a regular -ed verb,
   or one of the irregulars a worker report actually opens with. The
   stop-list holds the handful of NOUNS that end in -ed and could otherwise
   be mistaken for one. Anything else is left exactly as written. */
const SH_PAST_HEAD =
  /^(?:[A-Z][a-z]{2,}ed|Cut|Wrote|Rewrote|Ran|Built|Rebuilt|Found|Got|Made|Sent|Read|Put|Set|Took|Began|Chose|Left|Kept|Held|Went|Came|Saw|Said|Drew|Brought|Split|Broke|Spent|Met|Won|Threw|Swept)\b/;
const SH_PAST_STOP =
  /^(?:Indeed|Speed|Need|Feed|Deed|Breed|Creed|Greed|Freed|Agreed|Exceed|Succeed|Proceed|Embed|Seed|Weed|Bleed|Steed|Tweed|Shed|Sled|Bred|Fled)\b/;

/* ── SHADOW'S OWN LINE FOR A TURN (founder, 2026-09-21, pass 9) ─────────
   "Worker output should always come back through Shadow's existing
   task-chat/conversation layer before it is shown to the founder."

   IT IS WRITTEN ON THE TURN SHADOW ALREADY TAKES. The decider reads the
   worker's latest output on every boundary and answers as Shadow; the
   `update` key in that same reply is its sentence to the founder
   (mission_engine.validate_update). No second model call, no second
   conversation, no new process -- the architecture the founder asked for,
   built out of the turn that was happening anyway.

   KEYED ON THE TURN IT IS ABOUT. `at_turn` is the turn whose output Shadow
   read, and a worker event carries that same number, so a sentence lands
   exactly where that turn's result belongs and nowhere else.

   ABSENT MEANS THE OLD BEHAVIOUR, EXACTLY. Every mission that ran before
   this key existed, every turn Shadow had nothing to say about, and every
   update that failed validation fall through to shadowThirdPerson -- the
   deterministic subject shift -- which is what this pane drew yesterday. */
function shadowUpdateFor(m, turn){
  const rows = (m && Array.isArray(m.shadow_updates)) ? m.shadow_updates : [];
  for (let i = rows.length - 1; i >= 0; i--){
    const r = rows[i];
    if (!r || Number(r.at_turn) !== Number(turn)) continue;
    const t = String(r.text || "").trim();
    /* the same floor every other founder-facing line crosses: Shadow's own
       sentence is not exempt from the rule that a record is never speech */
    if (!t || shadowNotSpeech(t)) return "";
    return t;
  }
  return "";
}

/* the newest founder-facing line Shadow wrote on this mission, or "" --
   the closing line of a finished task (see shadowCompletionHtml) */
function shadowLastUpdate(m){
  const rows = (m && Array.isArray(m.shadow_updates)) ? m.shadow_updates : [];
  for (let i = rows.length - 1; i >= 0; i--){
    const t = String((rows[i] && rows[i].text) || "").trim();
    if (t && !shadowNotSpeech(t)) return t;
  }
  return "";
}

function shadowThirdPerson(say){
  const raw = String(say || "").trim();
  if (!raw) return "";
  let t = raw;
  for (const [re, to] of SH_PERSON_HEAD){
    if (re.test(t)){ t = t.replace(re, to); break; }
  }
  for (const [re, to] of SH_PERSON_REST) t = t.replace(re, to);
  if (t !== raw) return t;
  const lower = () => raw.charAt(0).toLowerCase() + raw.slice(1);
  /* no first person at all -- the two subject-less shapes that still read
     as Shadow doing the work itself */
  if (SH_GERUND_HEAD.test(raw)) return "The worker is " + lower();
  if (SH_PAST_HEAD.test(raw) && !SH_PAST_STOP.test(raw))
    return "The worker " + lower();
  return raw;
}

/* the words, not the punctuation -- two reports that differ only in a
   trailing ellipsis are the same report said twice */
function shadowNarrationKey(say){
  return String(say || "").toLowerCase()
    .replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
}

/* Applied at RENDER, never to the event list itself: shadowTimelineEvents
   stays the complete, ordered record of what happened, which is what every
   other reader of it (and every test of it) depends on. This decides only
   what is worth SAYING. */
function shadowNarration(events){
  /* A RECORD IS REFUSED OUTRIGHT, whatever its position -- first, last or
     only. Unlike the salience rule below, this is not about how much to
     say; it is about whether the line is something Shadow says at all. */
  /* PASS 9: an event Shadow NARRATED is judged on Shadow's own sentence --
     it has already crossed the record floor in shadowUpdateFor, it is not
     the worker's prose, and Shadow choosing to say it IS the salience
     decision this pass otherwise has to make mechanically. Only the
     duplicate rule still applies to it. */
  const all = Array.isArray(events) ? events : [];
  /* ── ONE VOICE, OR THE OTHER (founder, 2026-09-21, pass 9) ───────────
     Once Shadow is narrating this mission, it narrates ALL of it. Falling
     back to the deterministic subject shift for the turns it said nothing
     about would put the worker's own sentences back beside Shadow's --
     two voices in one column, which is the thing this pass removes.

     A TURN SHADOW DID NOT NARRATE IS SILENCE, and that is the prompt's own
     instruction: omit the key when the turn produced nothing a person would
     want to hear. The worker's words are still on the record and still
     behind Open the chat.

     THE SHIFT IS NOT DEAD. It is the whole rendering for a mission with no
     updates at all -- every record written before this key existed, and
     every mission whose decider never sent one. */
  const narrating = all.some(e => e && e.kind === "worker" && e.own);
  const rows = all.filter(
    e => !(e && e.kind === "worker" && !e.own && !e.open
           && (narrating || (e.say && shadowNotSpeech(e.say)))));
  const shown = (e) => (e && (e.own || e.say)) || "";
  const idx = [];
  for (let i = 0; i < rows.length; i++)
    if (rows[i] && rows[i].kind === "worker" && shown(rows[i])) idx.push(i);
  if (idx.length < 2) return rows;          /* nothing to thin out */
  /* PASS 5: ONLY THE NEWEST IS EXEMPT. Pass 4 also exempted the FIRST
     report, to guarantee a start signal -- and the first report of a task is
     routinely "Searching the cricket boards for today's reports", which is
     exactly the line the founder refused. The start signal is Shadow's own
     answer to the opening request (shadowIdleLineHtml), which is now
     permanent, so the exemption has nothing left to buy. The newest report
     stays exempt for a different reason: the founder must never be blind
     about where the task is right now. */
  const last = idx[idx.length - 1];
  const drop = {};
  let prev = "";
  for (const i of idx){
    const key = shadowNarrationKey(shown(rows[i]));
    if (i !== last
        && (key === prev
            || (!rows[i].own && shadowWorkNoise(rows[i].say)))){
      drop[i] = 1; continue;
    }
    prev = key;
  }
  return rows.filter((e, i) => !drop[i]);
}

/* ── "SHADOW IS WORKING" IS THE WHOLE OF THE ACTIVITY INDICATOR ──────────
   The row a turn in flight gets. It replaces "Worker agent · turn 2" plus
   its sweep: the founder is told that Shadow is working and, because a long
   turn is the one case where silence is worrying, how long for. The clock is
   the turn's own stamp, which the timeline already carries -- no new field,
   no poll of its own. It must never become a worker log, so it says nothing
   about what the worker is doing; the last thing it REPORTED is already the
   row above. */
function shadowWorkingHtml(ts, head){
  const el = (typeof shadowTurnElapsed === "function") ? shadowTurnElapsed(ts) : "";
  return `<div class="shsaid shfrom-shadow shworking${
      head === false ? " shrun" : ""}" role="status"
      aria-live="polite">
    ${head === false ? "" : `<div class="shsaidhead">Shadow</div>`}
    <div class="shsaidtext shworkingtext"
      ><span class="shworkdot" aria-hidden="true"></span
      ><span class="shworkword">Working</span>${el
        ? `<span class="shworkclock"> \u00b7 ${esc(el)}</span>` : ""}</div>
  </div>`;
}

function shadowThinkingHtml(){
  return `<div class="shsaid shfrom-shadow shthinking" role="status" aria-live="polite">
      <div class="shsaidhead">Shadow</div>
      <div class="shsaidtext shthinkingtext"
        ><span class="shthinkdot" aria-hidden="true"></span
        ><span class="shthinkword">thinking</span
        ><span class="shthinkell" aria-hidden="true"></span></div>
    </div>`;
}

/* ── A TURN THAT IS HAPPENING HAS A CLOCK ─────────────────────
   The open turn already drew its NUMBER and nothing under it -- deliberately,
   because a turn in flight has not reported yet and previewing its newest
   sentence reads as the outcome when it is not (see shadowTimelineEvents).
   That rule stands. What this adds is the one fact a founder watching a long
   turn actually wants: how long it has been going.

   FROM THE TURN'S OWN STAMP, which the timeline already carries -- the
   instruction that opened it, or its newest message. No new field, no poll
   of its own: the pane already re-renders on the existing transcript
   throttle, and the seconds tick with it. An unstamped turn draws the bar
   and no number rather than inventing a start. */
function shadowTurnElapsed(ts){
  const t = Number(ts);
  if (!t || isNaN(t)) return "";
  const secs = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (secs > 86400) return "";            /* a stale stamp is not an elapsed */
  const m = Math.floor(secs / 60), sec = secs % 60;
  return (m < 60) ? (m + ":" + String(sec).padStart(2, "0"))
                  : (Math.floor(m / 60) + "h" + String(m % 60).padStart(2, "0"));
}

function shadowOpenTurnHtml(n, ts){
  const el = shadowTurnElapsed(ts);
  return `<div class="shagent shagentopen">
    <div class="shagenthead">Worker agent${
      n > 0 ? " \u00b7 turn " + esc(String(n)) : ""}<span class="shturnlive"
      aria-hidden="true"></span>${el ? `<span class="shturntimer"
      >${esc(el)}</span>` : ""}</div>
    <div class="shturnsweep" aria-hidden="true"><i></i></div>
  </div>`;
}

function shadowAgentRowHtml(n, say){
  return `<div class="shagent">
    <div class="shagenthead">Worker agent${
      n > 0 ? " \u00b7 turn " + esc(String(n)) : ""}</div>
    ${say ? `<div class="shagentsay" title="${escAttr(say)}">${esc(say)}</div>` : ""}
  </div>`;
}

/* kept for the single-latest-turn read: the card, and any caller that wants
   just the newest thing the delegate said. */
function shadowAgentTurnHtml(m){
  const raw = shadowAgentSay(m);
  if (!raw) return "";
  const say = shadowSayGist(shadowSayClean(raw));
  if (!say) return "";
  return shadowAgentRowHtml(Number(m && m.turns_used), say);
}

/* ── THE RIGHT PANE IS A TIMELINE OF THE DELEGATION ──────────────────────
   (founder, 2026-09-15.) It showed one row -- the newest worker turn -- so
   turn 2 ERASED turn 1 and the founder lost the history of a delegation
   that had actually happened. A delegation is a sequence: the worker works,
   Shadow reaches a boundary, the founder answers, the worker carries on.
   That sequence is the product, and it has to persist.

   WHAT A TURN IS, and it is the backend's own definition, not a second one:
   session_reader counts `turns` as the number of USER messages, so turn N
   opens at the Nth message Shadow injects and owns every assistant message
   until the next one. m.turns_used agrees with that count, which is why the
   numbering here matches the brief's TURN row exactly.

   WHICH SENTENCE REPRESENTS A TURN: the LAST assistant message in it that
   survives cleaning. A turn often ends with several messages -- a plan, a
   tool narration, then the report -- and the report is the last of them. If
   the last is all control plane the one before it is tried, so a turn is
   never dropped merely because it signed off with scaffolding.

   NO CAP ON WHICH TURNS ARE SHOWN. Every turn that said something readable
   gets a row, in order. Each row is one line, so ten turns is ten lines --
   a timeline, not a transcript, and the whole conversation is still behind
   Open the chat.

   EVERY SOURCE IS ALREADY HERE: the same throttled transcript reader, the
   same cleaning rules, and founder_response as the server stamped it. No
   endpoint, no field, no summary is invented. */
/* ── SAY ANYTHING: THE FOUNDER TALKING TO SHADOW ─────────────────────────
   (founder, 2026-09-15.) The composer posted to /api/shadow/chat, which is
   the chief-of-staff conversation -- a different Shadow session that has no
   mission in hand and no way into the delegation. So an aside typed while a
   task was running reached something that could reply about it and nothing
   that could act on it.

   WITH A TASK IN FOCUS IT NOW GOES TO THE TASK, through the mission action
   endpoint every other Shadow control already uses. The server appends it to
   the record; run_mission re-loads the record at the top of every turn, so
   the DECIDER reads it next turn and decides for itself whether it changes
   the instruction. Nothing here sends into the delegate session -- the
   founder talks to Shadow, and Shadow drives the worker, which is the whole
   point of the surface.

   WITH NO TASK IN FOCUS nothing changes: the briefing composer is still the
   chief-of-staff channel, and sendToShadow is untouched.

   THE TEXT IS NOT LOST IF THE SEND FAILS. It is cleared optimistically so
   the box feels instant, and put back verbatim if the POST does not land --
   a founder who typed three sentences into a dead network must not have to
   remember them. */
const shSaying = {};
async function shadowSayToShadow(mid, text, el){
  if (!mid || !text) return null;
  /* one in flight per task: a second Enter while the first is still in the
     air would post the same aside twice, and Shadow would read it twice */
  if (shSaying[mid]) return null;
  shSaying[mid] = true;
  if (typeof scheduleRender === "function") scheduleRender();
  let doc = null;
  try {
    const r = await shadowPost("/api/shadow/missions/" + mid + "/act",
      { action: "say", text: text });
    if (r && r.ok){
      doc = await r.json();
      if (typeof showNudge === "function") showNudge("Sent to Shadow.");
    } else {
      /* 409 is the one refusal with a reason the founder needs in words.
         v4.1 (V4-9): a finished task no longer refuses -- it reopens on the
         instruction -- so the reason is the server's own sentence (another
         task has that chat; it never got one). Everything else is a plain
         failure. */
      let refusal = null;
      if (r && r.status === 409){
        try {
          const j = await r.json();
          const d = j && j.detail;
          refusal = (d && typeof d === "object") ? d.detail : d;
        } catch (e){ refusal = null; }
      }
      const why = (r && r.status === 409)
        ? (refusal ? String(refusal)
                   : "That task has finished — Shadow is no longer working on it.")
        : "That did not send" + (r ? " (" + r.status + ")" : "")
          + " — your message is still in the box.";
      if (typeof showNudge === "function") showNudge(why);
      if (el) el.value = text;            /* nothing typed is ever lost */
    }
  } catch (e) {
    if (typeof showNudge === "function")
      showNudge("That did not send — your message is still in the box.");
    if (el) el.value = text;
  }
  shSaying[mid] = false;
  if (doc && typeof loadShadowHome === "function") loadShadowHome(true);
  if (typeof scheduleRender === "function") scheduleRender();
  return doc;
}

/* -- TALK TO SHADOW: the founder's conversation with THIS task -----------
   (founder, 2026-09-16, step 1 of the Shadow conversation UX.)

   THE GAP. "Give instruction to Shadow" (shadowSayToShadow, above) is a
   STEERING DEPOSIT: it appends to the mission's `founder_says` and the
   decider reads it on its next turn. Nothing answers. So a founder who
   simply wants to ask "what are you doing?" had nowhere to ask it once the
   task had started -- the one surface that answers, the task's own Shadow
   chat, is opened by + Delegate and closed again by Start.

   NOTHING NEW IS BUILT. Every piece here already existed and is reused as
   it stands:

     the conversation   shadow_task_chat.TaskChat.talk, through the route
                        POST /api/shadow/tasks/{id}/chat, which returns
                        Shadow's prose directly. That chat has no tools by
                        construction, so it can answer and nothing else.
     the history        the Shadow chat's OWN transcript, read through the
                        same throttled shadowTaskTranscript the worker-chat
                        block uses, keyed by the mission's
                        `task_chat_session`. That is what survives a reload
                        and a restart: nothing is stored in the browser.
     the rendering      shadowMsgHtml (15-shadow-overlay.js), the same
                        founder/Shadow bubble the drafting chat draws.

   IT IS NOT AN INSTRUCTION, AND THIS STEP DOES NOT MAKE IT ONE. A line sent
   here does not touch `founder_says`, does not reach the worker, does not
   spend a turn and does not enter the decider's context. Whether a casual
   line should ever become work is step 2, and deliberately not here. */

/* THE PROMPTS THE APP SENDS INTO THIS CONVERSATION -- the boot, the brief
   ask, the steering turn and (D81) the judge -- travel down the SAME session,
   so the transcript holds them beside the founder's own lines. They are
   matched on the opening words their one writer emits
   (shadow_task_chat.BOOT_PREFIX, shadow_task_chat.BRIEF_ASK,
   shadow_runner._DECIDE_PROMPT, shadow_judge._PROMPT).

   FOLDED, NEVER DROPPED (founder D81, 2026-09-21: "All the conversations
   with the app should happen in the Sutra chat UI and should be shown
   there"). Until D81 a matched prompt and every reply that followed it were
   left out of the stream. Now each one is ONE folded row: a one-line label
   the founder can open to read the prompt and Shadow's answer verbatim. The
   view shows the chat's own transcript, not a filtered copy of it. */
const SH_TALK_FOLD = [
  { re: /^\[Shadow boot\]/, kind: "boot",
    label: "Shadow booted with its operating context" },
  { re: /^Write the opening brief for this task's worker chat\./, kind: "brief",
    label: "Shadow wrote the worker's brief" },
  { re: /^You are Shadow, driving one target chat toward an outcome\./, kind: "steer",
    label: "Shadow read the worker and chose the next instruction" },
  { re: /^You are settling ONE completion check by reading evidence\./, kind: "judge",
    label: "Shadow judged a check from the evidence" },
  /* the pending-ask briefing with no founder line after it -- the app
     telling Shadow what the task is waiting on, and nothing else. Folded
     rather than dropped: it IS a real message on the record. */
  { re: /^\[Pending asks on this task/, kind: "asks",
    label: "Shadow was told what this task is waiting on" },
];

/* ── THE ENVELOPE IS NOT WHAT THE FOUNDER SAID (founder, 2026-09-21, pass 4)
     ────────────────────────────────────────────────────────────────────
   THE LEAK. api_shadow_task_chat prefixes a founder's line with
   mission_engine.pending_asks_text before handing it to the task chat, so
   what the transcript RECORDS for a line typed while an ask is open is

       [Pending asks on this task -- the founder may answer any of them in
        this chat; if their line answers one, emit ONE ```answer fence]
       - confirm #1: the itinerary is feasible for 10 days
       [The founder says:] I want to spend 5 days in London.

   and this stream drew every byte of it as the founder's own message. Those
   first lines are orchestration instructions addressed to Shadow; the
   founder wrote one sentence and read a paragraph of machinery back.

   THE STRIP IS HERE, AT THE PRESENTATION BOUNDARY, and nowhere else -- the
   same rule SH_CONTROL_HEAD follows. The route still sends the envelope, the
   chat still reads it, the transcript still stores it, and "Open the chat"
   still shows the whole thing. Only this pane stopped drawing it.

   IT ALSO FIXES A DUPLICATE. The live row holds what the founder TYPED and
   the persisted row held the enveloped copy, so shadowTalkKey could never
   match them and the same sentence drew twice. Both sides now key on the
   founder's own words.

   A LINE WITH NO `[The founder says:]` MARKER IS NOT THEIRS. It is the
   briefing alone, and it folds through SH_TALK_FOLD above. */
const SH_ASK_ENVELOPE = /^\[Pending asks on this task\b[\s\S]*?\[The founder says:\]\s*/;
const SH_SAYS_PREFIX = /^\[The founder says:\]\s*/;

function shadowStripEnvelope(text){
  const t = String(text == null ? "" : text);
  if (SH_ASK_ENVELOPE.test(t)) return t.replace(SH_ASK_ENVELOPE, "").trim();
  if (SH_SAYS_PREFIX.test(t)) return t.replace(SH_SAYS_PREFIX, "").trim();
  return t;
}
function shTalkFold(text){
  for (const f of SH_TALK_FOLD) if (f.re.test(text)) return f;
  return null;
}

/* THE LIVE LINES ARE KEYED BY MISSION, AND THAT IS THE WHOLE BUG (founder,
   2026-09-17). `live` was a single flat array. While the floating panel
   existed that was safe by accident: the panel drew only when its `mid`
   matched the task on screen, and opening it on another task reset the array.
   Folding the panel into the workspace composer removed both guards, and
   nothing replaced them -- so shadowTimelineEvents appended THIS SITTING'S
   lines to EVERY task's stream. A brand-new task opened showing the previous
   task's conversation.

   One map, keyed by mission id. Nothing else about the conversation moved:
   the durable record is still the task chat's own transcript, which was
   always correctly scoped by `task_chat_session`. */
function shadowTalk(){
  const S_ = (typeof S !== "undefined") ? S : {};
  if (!S_.shadowTalk)
    S_.shadowTalk = { live: {}, text: "", busy: false };
  /* a map from before this fix, or none at all, must not carry an array */
  if (!S_.shadowTalk.live || Array.isArray(S_.shadowTalk.live))
    S_.shadowTalk.live = {};
  return S_.shadowTalk;
}

/* The lines said to ONE mission this sitting. Never shared, never global. */
/* THE SAME MESSAGE FROM TWO SOURCES IS ONE ROW (founder, 2026-09-17).
   The persisted transcript keeps Shadow's RAW reply; the route returns the
   PARSED one, and the two differ:

     persisted  "PLACEMENT: unresolved (no-match) — …\n\nSent worker first
                 instruction: …"
     live       "Sent worker first instruction: …"

   The dedupe compared raw text, so it missed -- and shadowProseHtml then
   normalised both to the same visible prose, drawing what the founder read as
   the identical answer twice.

   So the key is what the founder will actually SEE: the same shadowProseText
   the renderer runs, with whitespace collapsed. Nothing is stripped that was
   not already stripped for display, and the displayed text is untouched --
   this decides only whether a row is a duplicate. */
function shadowTalkKey(text){
  const t = (typeof shadowProseText === "function")
    ? shadowProseText(text) : String(text == null ? "" : text);
  return t.replace(/\s+/g, " ").trim();
}

function shadowTalkLive(mid){
  const T = shadowTalk();
  if (!mid) return [];
  if (!T.live[mid]) T.live[mid] = [];
  return T.live[mid];
}

/* THE CONVERSATION AS THE RECORD HAS IT. Read-only, off the same endpoint
   and the same throttle the worker chat uses; a mission whose Shadow chat
   has not booted yet simply has nothing to show. */
function shadowTalkTurns(m){
  const sid = m && m.task_chat_session;
  if (!sid || typeof shadowTaskTranscript !== "function") return [];
  const msgs = shadowTaskTranscript(sid, true);
  if (!Array.isArray(msgs)) return [];
  const out = [];
  /* the folded row the replies currently belong to, or null when the last
     user line was the founder's own */
  let fold = null;
  for (const t of msgs){
    if (!t) continue;
    const text = String(t.text || "").trim();
    if (t.role === "user"){
      if (!text){ fold = null; continue; }
      /* the founder's own words, with the app's envelope taken off. When
         something was stripped this IS a founder line and never a fold --
         the briefing it was wrapped in is Shadow's, not theirs. */
      const own = shadowStripEnvelope(text);
      if (own && own !== text){
        fold = null;
        out.push({ who: "founder", text: own, ts: Date.parse(t.ts || "") });
        continue;
      }
      const f = shTalkFold(text);
      if (f){
        /* ── THE SUBSTRATE IS NOT A PARTICIPANT (founder, 2026-09-21,
             pass 5) ────────────────────────────────
           THIS REVERSES D81 FOR THIS SURFACE, and says so rather than
           quietly differing from it. D81 (same day) read "all the
           conversations with the app should happen in the Sutra chat UI and
           should be shown there", and these prompts became one folded row
           each. Pass 5 is explicit that they must not be chat at all:
           "SHADOW BOOTED WITH ITS OPERATING CONTEXT", "SHADOW READ THE
           WORKER AND CHOSE THE NEXT INSTRUCTION" are implementation
           records, and the founder should not meet one before they meet
           their own request.

           NOTHING IS DROPPED FROM THE RECORD. The task chat is a published
           chat of its own (app.py _publish_task_chat -> m.task_chat), so
           every one of these prompts and every reply to them is still
           readable in Chats, verbatim, exactly as D81 required. What
           changed is that the CONVERSATION stopped being the place it is
           read.

           THE REPLIES GO WITH THE PROMPT. `fold` still swallows every
           assistant message until the next founder line, because a reply to
           "choose the next instruction" is the instruction -- worker-facing
           text, not something Shadow said to the founder. */
        fold = { swallow: true };
      } else {
        fold = null;
        out.push({ who: "founder", text: text, ts: Date.parse(t.ts || "") });
      }
      continue;
    }
    if (t.role !== "assistant" || !text) continue;
    /* a reply to an app prompt goes WITH it -- one prompt can answer across
       several messages, so this does NOT reset per message. Pass 5: the
       prompt is not drawn, so neither is its answer (see above). */
    if (fold) continue;
    out.push({ who: "shadow", text: text, ts: Date.parse(t.ts || "") });
  }
  return out;
}

/* One line to this task's Shadow. The reply is Shadow's own prose, returned
   by the route; nothing here writes to the mission record. */
async function shadowTalkSend(mid, el){
  const T = shadowTalk();
  const text = String(T.text || "").trim();
  if (!mid || !text || T.busy) return null;
  const live = shadowTalkLive(mid);
  /* STAMPED AT THE MOMENT IT HAPPENS (founder, 2026-09-17). A live row used
     to carry no clock at all, and shadowTimelineEvents pushed it as ts: NaN.
     The comparator falls back to PUSH INDEX whenever either side is
     unstamped, and worker events are pushed before conversation events -- so
     an unstamped line sank below every worker turn however early it was sent.
     Measured on m-194c266205d3: the founder asked at 09:18:18.125Z, turn 1
     opened at 09:18:19.920Z, and the pane drew the turn ABOVE the question.

     Date.now() here is the real event time: this is the instant the founder
     pressed send. It is never inherited from a neighbour -- a borrowed stamp
     would be invented chronology, which is the one thing this stream must
     not report. */
  live.push({ who: "founder", text: text, ts: Date.now() });
  /* THE MISSION ID, NOT `true` (founder, 2026-09-17). The thinking row is
     drawn from this flag, and a bare boolean would put one task's spinner on
     every other task's pane. Truthy either way, so `if (T.busy) return` above
     is unchanged. */
  T.text = ""; T.busy = mid; T.err = null;
  if (typeof scheduleRender === "function") scheduleRender();
  let r = null, body = null;
  try {
    r = await shadowPost(
      "/api/shadow/tasks/" + encodeURIComponent(mid) + "/chat",
      { message: text });
    body = (r && r.ok) ? await r.json() : null;
  } catch (e){ body = null; }
  T.busy = false;
  /* v4.1 (V4-9): a 409 is no longer "that task has finished" -- a finished
     task REOPENS on the founder's words. The one 409 left is the server's
     own sentence (another task has that chat; it never got a chat), and
     that sentence is what the founder needs, so it is read off the body. */
  let refusal = null;
  if (r && !r.ok && r.status === 409){
    try {
      const j = await r.json();
      const d = j && j.detail;
      refusal = (d && typeof d === "object") ? d.detail : d;
    } catch (e){ refusal = null; }
  }
  if (!body){
    /* THE REFUSAL HAS TO LAND SOMEWHERE THE FOUNDER LOOKS. It used to be
       drawn inside the panel; with one composer it goes to that composer's
       own error line (shadowScopeErr, rendered by shadowStageHtml), which
       shadowSubmitCompose already clears on the next send. 409 is the one
       refusal with a reason worth words.

       AND NOTHING TYPED IS LOST. The box is cleared optimistically so it
       feels instant; a send that does not land hands the text back, the same
       way the say path always did. */
    const why = (r && r.status === 409)
      ? (refusal ? String(refusal)
                 : "That task has finished \u2014 Shadow is no longer on it.")
      : "Shadow could not answer" + (r ? " (" + r.status + ")" : "")
        + " \u2014 your message is still in the box.";
    if (typeof S !== "undefined") S.shadowScopeErr = why;
    T.live[mid] = live.filter(x => x.text !== text);
    /* THROUGH THE STORE, not straight onto the node: the box renders from
       S.shadowComposeDraft now, so a bare `el.value = text` would be undone
       by the very next repaint -- and this path always causes one. */
    shadowComposeSet(el, text);
  } else {
    /* v4.1 (V4-9): the task was finished and the founder's line reopened it.
       Said in the stream, once, before Shadow's answer -- and the list is
       re-read so the row moves out of Done today without a reload. */
    if (body.reopened)
      live.push({ who: "shadow", ts: Date.now(),
                  text: "Back on it \u2014 this task is running again." });
    if (body.reply)
      /* the instant the answer reached us, for the same reason as above.
         `replyTo` IS THE IDENTITY (founder, 2026-09-21) -- see the anchor
         note in shadowTimelineEvents. It names the founder line this reply
         answers, which is the one string both sides hold UNTRANSFORMED, so
         the live row can be retired when the transcript catches up without
         either side having to agree about how Shadow's own prose
         normalises. */
      live.push({ who: "shadow", text: String(body.reply), ts: Date.now(),
                  replyTo: shadowTalkKey(text) });
    /* v4.1 (V4-7): what the founder's words SET, as the app applied it --
       fixed copy from the server (mission_engine.limits_label), never
       Shadow's prose, with Undo on the row. A refusal is the store's own
       sentence and gets the same row without the button. */
    const lim = body.limits;
    if (lim && typeof lim === "object"){
      for (const a of (lim.applied || []))
        if (a && a.label)
          live.push({ who: "shadow", text: String(a.label), ts: Date.now(),
                      limits: a.undo ? { mid: mid } : null });
      for (const why of (lim.refused || []))
        if (why) live.push({ who: "shadow", text: String(why), ts: Date.now() });
    }
    if ((body.reopened || lim) && typeof loadShadowHome === "function")
      loadShadowHome(true);
  }
  if (typeof scheduleRender === "function") scheduleRender();
  return body;
}

/* ── A QUESTION AND ITS ANSWER ARE ONE BLOCK (founder, 2026-09-17) ────
   THE BUG. Chronology alone is not conversation. With real stamps on every
   row -- which is the fix directly above, and stays -- a worker turn that
   opened between the founder pressing send and Shadow answering sorts
   BETWEEN them:

       founder 100 · worker 150 · shadow 200

           YOU → SHADOW   "What are you doing right now?"
           WORKER TURN 1
           SHADOW         "Sent worker first instruction…"

   Every stamp there is true and the reading is still wrong: the founder has
   to step over an unrelated turn to find the reply to their own sentence.

   SO THE EXCHANGE IS THE UNIT OF DISPLAY, not the row. A founder line and
   the replies that follow it are drawn adjacent, and anything else that
   happened in between is drawn after them, in its own order, unchanged.

   THIS IS A DISPLAY PASS AND NOTHING ELSE. It runs on the sorted array,
   moves rows, and touches no `ts` -- every event keeps the stamp the record
   gave it, the history endpoint is untouched, and no orchestration decision
   reads this function. What the founder sees changes; what happened does not.

   THE SPAN A QUESTION OWNS ends at the NEXT founder line, so a worker turn
   between two separate exchanges keeps its place:

       YOU → SHADOW · SHADOW · WORKER TURN 1 · YOU → SHADOW · SHADOW

   AND ONLY UP TO THE LAST REPLY. Rows after the final reply of an exchange
   are not inside it and do not move -- which is also what makes an
   unanswered question cost nothing: with no reply in its span, the question
   is emitted where it sorted and the following turns stay where they are.
   A reply still in flight therefore never holds the stream back; it joins
   its question on the render after it lands.

   SPEAKER TEST MIRRORS THE RENDERER. shadowTimelineHtml treats any talk row
   that is not `who === "shadow"` as the founder's, so this does too -- a row
   the renderer would head "You → Shadow" is a row this pairs on. */
function shadowTimelinePair(seq){
  const isTalk = (e) => !!e && e.kind === "talk";
  const isReply = (e) => isTalk(e) && e.who === "shadow";
  const isAsk = (e) => isTalk(e) && !isReply(e);
  const out = [];
  let i = 0;
  while (i < seq.length){
    const e = seq[i];
    if (!isAsk(e)){ out.push(e); i++; continue; }
    /* the span this question owns: up to the next question, or the end */
    let end = i + 1;
    while (end < seq.length && !isAsk(seq[end])) end++;
    /* the last reply inside it -- the exchange closes there */
    let last = -1;
    for (let j = i + 1; j < end; j++) if (isReply(seq[j])) last = j;
    if (last === -1){ out.push(e); i++; continue; }
    out.push(e);
    /* the conversation first, in its own order... */
    for (let j = i + 1; j <= last; j++) if (isTalk(seq[j])) out.push(seq[j]);
    /* ...then everything it stepped over, in its own order */
    for (let j = i + 1; j <= last; j++) if (!isTalk(seq[j])) out.push(seq[j]);
    i = last + 1;
  }
  return out;
}

function shadowTimelineEvents(m){
  const out = [];
  const sid = m && m.target_session;
  const msgs = (sid && typeof shadowTaskTranscript === "function")
    ? shadowTaskTranscript(sid, SH_TERMINAL.indexOf(m.state) === -1)
    : null;
  if (Array.isArray(msgs)){
    /* group by turn: a user message opens one, assistants fill it */
    const turns = [];
    let cur = null;
    for (const t of msgs){
      if (!t) continue;
      if (t.role === "user"){
        /* the instruction that opened the turn is the turn's own clock, and
           it is the fallback when the delegate's reply carries no stamp */
        cur = { n: turns.length + 1, says: [], at: Date.parse(t.ts || "") };
        turns.push(cur); continue; }
      if (t.role !== "assistant") continue;
      /* an assistant turn before any injected instruction still counts as
         turn 1 -- the delegate spoke, and the founder should see it */
      if (!cur){ cur = { n: 1, says: [], at: NaN }; turns.push(cur); }
      cur.says.push(t);
    }
    /* THE NUMBERS ARE ANCHORED TO THE RECORD, NOT TO WHAT WE HOLD. The
       transcript in hand can be shorter than the mission -- a partial read,
       or a session whose head has been trimmed -- and numbering it 1..n
       would relabel history: the founder would read "turn 1" for something
       the brief calls turn 9. So the LAST transcript turn is turns_used and
       the rest count back from it. When the transcript is complete the
       offset is zero and nothing moves: the six-turn release mission
       numbers 1..6 against turns_used 6, exactly as it always did. */
    const used = Number(m && m.turns_used) || 0;
    const base = Math.max(0, used - turns.length);
    /* ── A TURN IN FLIGHT HAS NOT REPORTED YET (founder, 2026-09-16) ────
       THE LINE IS A REPORT ON A FINISHED TURN, so a turn that is still
       being worked shows its NUMBER and nothing under it. Previewing the
       newest sentence of a turn that is still speaking is not a report of
       it: the worker's last word so far is routinely a tool narration, an
       intention, or a caveat it is about to resolve, and the founder read
       it as the outcome. The turn still takes its row -- a turn that is
       happening is a fact, and the heading is what carries it.

       THE SIGNAL IS THE ENGINE'S OWN, not a clock and not a guess.
       mission_engine.run_mission stamps `turn_open` with the number of the
       turn it just sent and clears it when the boundary arrives
       (mission_engine.py, "THE TURN THAT IS HAPPENING RIGHT NOW"), and
       /api/shadow/missions has carried the field since the day it existed
       -- shadowTurnNow above already reads it for the card's TURN row.
       Nothing new is stored, polled or inferred.

       A TERMINAL MISSION IS NEVER IN FLIGHT. The engine clears `turn_open`
       on the ordinary boundary, but a mission that ended INSIDE a turn --
       a stall, a takeover, an out-of-road exit -- returns without reaching
       that line, so the field can outlive the run. SH_TERMINAL is the
       existing answer to "can this still change" and is used here for
       exactly that: a done/failed/stopped mission reports every turn it
       has, which is what it did before this block existed.

       A MISSION WITH NO `turn_open` BEHAVES EXACTLY AS IT DID. Absent or 0
       means no turn is open, so every row takes the completed path -- which
       is every historical record, and every existing fixture. */
    const live = SH_TERMINAL.indexOf(m && m.state) === -1;
    const openTurn = live ? (Number(m && m.turn_open) || 0) : 0;
    for (const t of turns){
      const n = base + t.n;
      if (openTurn && n === openTurn){
        /* the turn's own clock, then its newest message's, then nothing --
           the same ladder the completed row below walks */
        let at = t.at;
        for (let i = t.says.length - 1; i >= 0 && isNaN(at); i--)
          at = Date.parse(t.says[i].ts || "");
        out.push({ kind: "worker", n: n, say: "", open: true, ts: at });
        continue;
      }
      /* ── THE WORKER'S OWN REPORT, WHEN IT WROTE ONE ──────────────────
         Scanned FORWARD, first valid one wins (shadowSayReport), and put
         through the same shadowSayClean + shadowSayGist the fallback uses
         -- so the control-plane filter, the table guard and the one-line
         cap all apply to it unchanged. A REPORT that cleans to nothing is
         no REPORT at all and drops through to the walk below, which is the
         behaviour every record written before the clause existed gets. */
      const usable = (line) => !!shadowReportGist(shadowSayClean(line));
      let rep = "", pick = -1;
      for (let i = 0; i < t.says.length; i++){
        const line = shadowSayReport(t.says[i].text, usable);
        if (!line) continue;
        rep = shadowReportGist(shadowSayClean(line)); pick = i; break;
      }
      if (rep){
        const own = Date.parse(t.says[pick].ts || "");
        out.push({ kind: "worker", n: n, say: rep,
                   ts: isNaN(t.at) ? own : t.at });
        continue;
      }
      /* ── A TURN SHADOW NARRATED IS NEVER A LOST TURN (pass 9) ───────
         The worker's own output can clean to nothing -- all control plane,
         a bare payload, an announcement -- and until now that turn simply
         had no row. If Shadow wrote a founder-facing line about it, the
         line is the row: the founder hears what happened even when the
         worker said it in a shape this pane refuses to draw. */
      let drew = false;
      for (let i = t.says.length - 1; i >= 0; i--){
        const say = shadowSayGist(
          shadowSayClean(shadowSayDropReport(t.says[i].text)));
        if (say){
          drew = true;
          /* A TURN IS A SPAN, AND IT SORTS BY WHEN IT OPENED (founder,
             2026-09-15, mission m-8ef75c0f2f78). The row shows one message
             but the turn covers everything from Shadow's instruction to the
             delegate's last word -- turn 1 there ran 10:56:51 to 10:57:49.
             Keying the row on the message it DISPLAYS put an aside sent at
             10:57:37, mid-turn, in front of turn 1.

             An aside sent while a turn is still speaking cannot have reached
             that turn: Shadow reads the record at the START of the next one.
             So it belongs after the turn it interrupted, and the boundary
             that decides this is the turn's OPENING stamp. Opens are
             monotonic, so keying on them also guarantees the turns keep
             their own order. The displayed message's stamp is the fallback
             for a turn whose opening instruction carries none. */
          const own = Date.parse(t.says[i].ts || "");
          out.push({ kind: "worker", n: n, say: say,
                     ts: isNaN(t.at) ? own : t.at });
          break;
        }
      }
      if (!drew && shadowUpdateFor(m, n)){
        let at = t.at;
        for (let i = t.says.length - 1; i >= 0 && isNaN(at); i--)
          at = Date.parse(t.says[i].ts || "");
        out.push({ kind: "worker", n: n, say: "", ts: at });
      }
    }
  }
  /* the newest worker turn, for a mission whose session is gone but whose
     result the server kept */
  if (!out.length && m && m.result_excerpt){
    const say = shadowSayGist(shadowSayClean(m.result_excerpt));
    if (say) out.push({ kind: "worker", n: Number(m.turns_used) || 0,
                        say: say, ts: NaN });
  }
  /* WHAT THE FOUNDER ANSWERED, placed where it actually happened.
     ONLY THE MOST RECENT ONE EXISTS: the server assigns founder_response
     rather than appending to it, so an earlier answer on a mission that was
     asked twice is not on the record in any structured form. It is not
     reconstructed from Shadow's instruction prose -- that prose is the
     decider's own wording, with no marker to key on, and guessing at it
     would be inventing history. */
  const fr = m && m.founder_response;
  if (fr && typeof fr === "object")
    out.push({ kind: "answered", ts: Date.parse(fr.answered_at || "") });
  /* ── THE FOUNDER AND SHADOW, IN THE SAME STREAM (founder, 2026-09-17) ──
     One conversation, drawn where the worker's turns are drawn, because there
     is one door now and its answers belong beside the work they are about.

     THE SOURCE IS THE TASK CHAT'S OWN TRANSCRIPT, read through the reader
     that already existed (shadowTalkTurns -> shadowTaskTranscript), with the
     boot, brief and steering prompts filtered out. That is what makes the
     conversation survive a reload and a restart: nothing is held here.

     ...PLUS WHAT WAS SAID THIS SITTING and has not reached the transcript
     yet, deduped on the text so a line is never drawn twice. */
  const talk = (typeof shadowTalkTurns === "function") ? shadowTalkTurns(m) : [];
  /* ── ONE REPLY, ONE ROW: ANCHOR IDENTITY (founder, 2026-09-21) ─────────
     THE BUG, and it is not a race. Shadow's reply reaches this pane twice by
     design -- once live, from the route's own return value, and once
     persisted, from the task chat's transcript -- and the two copies were
     matched by comparing their TEXT. They are normalised by two different
     functions that do not agree:

       server  shadow_protocol._strip_governance_noise  keeps ASCII box art
       client  shadowProseText                          strips ASCII box art

     So a reply carrying a FLOW box -- which the persona forbids and the
     model emits anyway, which is the entire reason both strippers exist --
     produced two different keys for one message, the dedupe missed, and the
     founder read the same answer twice. Measured: the box survives
     parse_reply server-side and does not survive shadowProseText here.

     TEXT COULD NEVER HAVE WORKED. Two independent normalisers will always
     drift; every divergence is a duplicate. So the key is no longer Shadow's
     prose at all.

     THE ANCHOR IS THE FOUNDER'S OWN LINE. It is the one string both sides
     hold untransformed -- the client sent it, the route forwarded it, the
     transcript recorded it -- so it is stable identity in the sense the rest
     of this file means it. A live reply names the founder line it answers;
     once the transcript shows that line HAS been answered, the live copy has
     been superseded and is dropped. Nothing compares Shadow's words to
     Shadow's words. */
  const answered = {};
  let lastAsk = null;
  const spoken = {};
  for (const t of talk){
    /* D81: an app prompt and its replies are one folded row. It is never
       in the live lines (the app sent it, not the founder), so it takes no
       part in the dedupe and never closes a founder's question. */
    if (t.fold){
      out.push({ kind: "talk", who: "system", fold: t.fold, label: t.label,
                 text: t.text, replies: t.replies || [], ts: t.ts });
      continue;
    }
    if (t.who === "founder") lastAsk = shadowTalkKey(t.text);
    else if (t.who === "shadow" && lastAsk) answered[lastAsk] = 1;
    /* The founder's OWN lines are byte-identical in both sources -- the
       client sent the string and the transcript recorded it -- so keying
       those on text is exact rather than a guess.
       Shadow's are keyed too, but ONLY as the fallback for a live row
       written before `replyTo` existed: it catches the cases where the two
       normalisers happen to agree, and the anchor above catches the ones
       where they do not. */
    spoken[shadowTalkKey(t.text)] = 1;
    out.push({ kind: "talk", who: t.who, text: t.text, ts: t.ts });
  }
  /* THIS MISSION'S lines, never another's -- see shadowTalk */
  const mine = (typeof shadowTalkLive === "function" && m && m.id)
    ? shadowTalkLive(m.id) : [];
  for (const t of mine){
    const text = String((t && t.text) || "").trim();
    if (!text) continue;
    if (t.who === "shadow"){
      /* superseded by the persisted copy of the same exchange */
      const anchor = (t && t.replyTo) || null;
      if (anchor && answered[anchor]) continue;
      /* a live reply from before `replyTo` existed keeps the old text test
         as its only available net -- strictly better than dropping it */
      if (!anchor && spoken[shadowTalkKey(text)]) continue;
    } else if (spoken[shadowTalkKey(text)]) {
      continue;
    } else {
      spoken[shadowTalkKey(text)] = 1;
    }
    /* its OWN stamp, written by shadowTalkSend when the line was sent or
       the reply arrived. NaN only for a row from before that existed.
       A limits row carries its Undo (shadowTalkSend); the stamp stays the
       LAST field, byte for byte, because test_shadow_v4_talk.js pins that
       text to mutate it. */
    out.push({ kind: "talk", who: t.who, text: text,
               limits: (t && t.limits) || null,
               ts: Number(t && t.ts) });
  }
  /* v4.2: WHAT WAS ASKED AND ANSWERED stays in the scrollback, in its place.
     A used approval and a confirmed check are facts on the record with
     their own stamps, so they sort like every other event. */
  const ap = m && m.approval;
  if (ap && ap.used && ap.used_at)
    out.push({ kind: "ask_done", what: "approve",
               text: String(m.approved_say || m.pending_say || ""),
               ts: Date.parse(ap.used_at) });
  for (const c of ((m && m.done_when) || []))
    if (c && c.tier === "founder_confirm" && c.met && c.confirmed_at)
      out.push({ kind: "ask_done", what: "confirm",
                 text: String(c.check || ""), ts: Date.parse(c.confirmed_at) });
  /* WHAT THE FOUNDER VOLUNTEERED THROUGH THE SAY PATH. Every aside is kept --
     these are a list on the record, not a single field, so unlike an answer
     the older ones are still there and each takes its own place in the order
     it was sent.

     ONLY THE ONES THE CONVERSATION DOES NOT ALREADY SHOW. Since 2026-09-17
     the composer posts to the task chat, which records the same words to
     `founder_says` -- so every new line is in BOTH, and drawing both would
     double it. A row with no counterpart in the transcript is a genuine say
     (a mission from before the unification, or anything still calling the
     endpoint) and still gets its place. */
  for (const said of (m && m.founder_says) || []){
    const text = String((said && said.text) || "").trim();
    if (text && !spoken[shadowTalkKey(text)])
      out.push({ kind: "said", text: text,
                 ts: Date.parse((said && said.at) || "") });
  }
  /* ── ONE STREAM, SORTED ON REAL STAMPS (founder, 2026-09-15) ──────────
     THE BUG. The founder said something after turn 1 and the pane drew

         TURN 1 · TURN 2 · TURN 3 · YOU -> SHADOW

     -- every worker turn, then the aside appended. The sort was here and was
     right; what defeated it was the FALLBACK. A comparison where either side
     had no parseable stamp fell through to original index, and because the
     asides are pushed after the worker loop their index is always highest,
     so a single unstamped worker message dropped every aside to the end.

     THE SPINE ALWAYS HAS A CLOCK NOW. A worker event takes its own message
     stamp; failing that, the stamp of the instruction that opened its turn;
     failing that, it carries the previous event's stamp forward (or the next
     one's, for a leading gap). Transcript order is ground truth for the
     worker turns, so carrying a stamp along it cannot reorder them -- it
     only gives the asides something real to sort against.

     Asides always have a stamp: the server writes `at` when it records them.
     One with none left (an older record) keeps its place by index rather
     than jumping the queue.

     Index remains the tiebreaker for genuinely equal stamps, so the order is
     deterministic and a worker turn precedes an aside sent in the same
     second. */
  const seq = out.map((e, i) => Object.assign({ i: i }, e));
  /* carry a known stamp ALONG THE WORKER SPINE, forwards then backwards */
  const spine = seq.filter(e => e.kind === "worker");
  let carry = NaN;
  for (const e of spine){
    if (!isNaN(e.ts)) carry = e.ts; else if (!isNaN(carry)) e.ts = carry;
  }
  carry = NaN;
  for (let i = spine.length - 1; i >= 0; i--){
    const e = spine[i];
    if (!isNaN(e.ts)) carry = e.ts; else if (!isNaN(carry)) e.ts = carry;
  }
  const sorted = seq.sort((a, b) => {
    const at = isNaN(a.ts) ? null : a.ts, bt = isNaN(b.ts) ? null : b.ts;
    if (at !== null && bt !== null && at !== bt) return at - bt;
    return a.i - b.i;
  });
  /* ...AND THEN THE CONVERSATION IS KEPT WHOLE. See shadowTimelinePair: the
     stamps above stay exactly as they were, this only decides what sits next
     to what on screen. */
  return shadowTimelinePair(sorted);
}

/* ── THE CONVERSATION OPENS WITH WHAT THE FOUNDER ASKED FOR ──────────────
   (founder, 2026-09-21, pass 3: "the user's original objective should
   appear naturally as the YOU message at the beginning of the conversation
   ... think of the mission metadata as backend state, not UI content".)

   WHAT THIS REPLACES. shadowTaskCardHtml -- objective, WHERE IT RUNS, DONE
   WHEN, and a row of actions -- was the first and largest block of the main
   surface. Pass 3's first cut moved it INSIDE the stream, which made the
   architecture right and the screen no better: the founder still read a
   task record before reaching a word anybody said.

   THE TEST THE FOUNDER GAVE: "if a piece of information is not something
   Shadow would naturally say to the founder at that moment, it should not
   become a large UI card." Applied to the card's four parts:

     objective    IS said -- it is the founder's own opening line, so it is
                  drawn as one, from them, at the top of the thread.
     where it runs  implementation metadata. The session id is on the record
                  and behind Open the chat; it is not a thing Shadow says.
     done when    said only when Shadow needs a decision, and then it is the
                  inline DONE WHEN element, which already exists and already
                  carries its evidence. Printing it here as well is the
                  duplicate the whole redesign removes.
     actions      controls, not speech. They are on the pinned header.

   shadowTaskCardHtml IS NOT DELETED. It is still exported and still
   rendered by the tests that pin its content, and nothing that reads a
   mission changed. It simply no longer draws the main surface. */
function shadowOpeningHtml(m){
  /* ── IT IS WHAT THEY ASKED FOR, NOT WHAT THE TASK IS NOW ──────────────
     `objective` is the CURRENT revision, so on a task the founder redirected
     it holds the new one -- and the thread opened "Plan a trip to India",
     three messages above the founder saying "actually, I want India". The
     opening line of a conversation is what was said at the beginning.

     THE FIRST REVISION'S OBJECTIVE IS THAT LINE. `revisions` is the ledger
     _invalidate_for_revision writes, oldest first, and revisions[0] is the
     objective the task was created with. With no revisions the current one
     IS the original, which is the ordinary case and is unchanged. */
  const log = (m && Array.isArray(m.revisions)) ? m.revisions : [];
  const first = log.length ? String(log[0].objective || "").trim() : "";
  const text = first || String((m && m.objective) || "").trim();
  if (!text) return "";
  return shadowSaidRowHtml("you", esc(text), "shopening");
}


/* ── WHEN THERE IS NOTHING TO REPORT, SAY THAT, IN ONE LINE ──────────────
   (founder, 2026-09-21: "if Shadow genuinely needs the user to start the
   task, use a concise conversational message ... do not expose internal
   state explanation".)

   THE GAP THIS FILLS, found by rendering it: a freshly running task has no
   worker turn yet and, once the metadata card left, drew NOTHING AT ALL --
   an empty pane under a header. That is worse than the card it replaced.

   IT IS A STATE OF FACT, NOT FABRICATED PROGRESS. Each line below is true
   by construction from the record and says nothing about what the work
   found: "on it" when the loop is running and the worker has not reported,
   "ready when you are" when the task is waiting to be started. Neither
   claims a result, and neither survives the first real turn -- the moment
   there is an event, the events are what render.

   NO INTERNAL VOCABULARY. No brief, no turn count, no done_when, no pause
   reason, no state name. Those are the sentences the founder objected to. */
/* the states in which nothing has been accepted yet */
const SH_DRAFT = ["draft", "brief_confirm"];

function shadowIdleLineHtml(m){
  if (!m) return "";
  const startable = (typeof shadowMissionStartable === "function")
    ? shadowMissionStartable(m) : m.state === "brief_confirm";
  if (startable)
    return shadowSaidRowHtml("shadow",
      "Everything is ready \u2014 start when you are.", "shidle");
  /* ── SHADOW ANSWERS THE OPENING REQUEST, AND KEEPS ANSWERING IT ─────
     (founder, 2026-09-21, pass 5: START -> "Got it. I'm working through this
     now.") It used to be drawn only while the stream was otherwise EMPTY, so
     the first worker report erased it -- and a conversation whose second
     line is the middle of the work reads as though Shadow never replied.

     IT IS TRUE BY CONSTRUCTION AND SAYS NOTHING ABOUT THE WORK. The mission
     has been accepted; that is the whole claim. It is the reply Shadow made
     when the founder asked, and a transcript keeps what was said at the
     time, which is why the tense does not move once the task finishes.

     A DRAFT NEVER GETS IT -- nothing has been accepted yet, and the
     startable line above is that state's honest answer. */
  /* ── QUEUED IS NOT RUNNING, AND MUST NOT SOUND LIKE IT (founder,
       2026-09-21, pass 10) ────────────────────────────────────────────
     THE BUG. A queued task fell through to "I'm working through this now",
     which is a claim about work that has not started -- the one thing this
     line has always been careful not to make. The founder read a page with
     a title, a badge, their own sentence and nothing else, and could not
     tell a transient state from a broken one.

     WHAT IT SAYS INSTEAD IS TRUE BY CONSTRUCTION AND SAYS NOTHING ABOUT
     THE WORK: the task was accepted, it exists, it has not begun, and the
     founder need do nothing. `queued` has exactly one cause -- every slot
     the run limit allows is taken -- and that is what the second line
     names, in the words the Watching plane already uses for it.

     IT IS NOT A STATE OF ITS OWN ON SCREEN. Same Shadow row, same
     typography, one muted line and the pill this pane already draws for
     the state. No spinner, no bar, no timeline: queued must not look
     busier than running.

     IT TRANSITIONS BY CONSTRUCTION. This is computed from `state` on every
     render, so the moment the scheduler promotes the task the queued line
     is simply not what this function returns -- there is no stale
     acknowledgement to clean up, on promotion or on a drop. */
  if (m.state === "queued")
    return shadowSaidRowHtml("shadow",
      "Got it. I\u2019m lining this up now."
      + `<div class="shqueued"><span class="shtpill shtpill-queued"
          >QUEUED</span><span class="shqueuednote">Waiting for a free slot
          \u2014 I\u2019ll start as soon as one opens. Nothing needed from
          you.</span></div>`, "shidle shidlequeued");
  if (SH_DRAFT.indexOf(m.state) === -1)
    return shadowSaidRowHtml("shadow",
      "Got it. I\u2019m working through this now.", "shidle");
  return "";
}


function shadowTimelineHtml(m){
  /* THE RECORD, THEN WHAT IS WORTH SAYING ABOUT IT. shadowTimelineEvents is
     unchanged and still returns every event in order; shadowNarration is the
     salience pass that keeps the founder from reading a worker log. */
  const events = shadowNarration(shadowTimelineEvents(m).map(e => {
    if (!e || e.kind !== "worker" || e.open) return e;
    const own = shadowUpdateFor(m, e.n);
    return own ? Object.assign({}, e, { own: own }) : e;
  }));
  /* the founder has sent and Shadow has not answered yet. Appended rather
     than folded into shadowTimelineEvents because it is not an EVENT: it has
     no stamp, nothing records it, and it must never sort against real ones. */
  const T = (typeof shadowTalk === "function") ? shadowTalk() : null;
  const waiting = !!(T && T.busy && m && m.id && T.busy === m.id);
  /* v4.2: THE ASKS LIVE IN THE CONVERSATION (founder 2026-09-21: "I don't
     see any buttons there"). What the task is waiting on is drawn as rows
     at the end of the stream, each with the button that answers it, and
     the composer's typed line answers the same row (the server binds it).
     Nothing here is a second store: shadowAskRowsHtml reads the record. */
  const asks = shadowAskRowsHtml(m);
  /* ── EVERYTHING IS AN EVENT IN ONE STREAM (founder, 2026-09-21, pass 3)
       ──────────────────────────────────────────────────────────────────
     WHAT WAS WRONG, and it was architectural rather than cosmetic. This
     timeline was ONE OF SEVEN SIBLING BLOCKS in shadowHomeHtml: the task
     card above it, then the stream, then the superseded revisions, then the
     decision, then the completion, each a separate surface stacked down the
     page. Passes 1 and 2 put the right content in those blocks and left the
     blocks where they were, so the founder still read a dashboard whose
     panels happened to contain conversational copy.

     THE PROTOTYPE'S DECISION is that there is no second surface: the brief,
     the worker's turns, Shadow's narration, the decision, what was
     superseded and the final summary are all MESSAGES, in one column, in
     the order they happened. That is what this now assembles.

     ORDER IS CHRONOLOGY, and each piece sits where it occurred:
       brief      what the founder asked for -- the first thing said
       events     the worker's turns and Shadow's replies, interleaved
       outdated   the moment the founder changed direction
       asks       what is being waited on now (hold, question, parked)
       decision   the canonical check surface, with its evidence
       done       the end of the conversation
     A piece that does not apply renders "" and takes no room, so a running
     task with nothing outstanding is just brief + turns.

     NOTHING IS RE-IMPLEMENTED. Every one of these is the same function that
     drew it as a panel a moment ago, called from here instead. What changed
     is where they are rendered, not what they render. */
  /* ── THE HEADER ALREADY SAYS WHAT THE TASK IS (founder, 2026-09-21) ───
       "The objective is already represented by the page header. Do not
       repeat the full objective in a huge card immediately below it. The
       conversation should begin naturally with Shadow speaking."

     THE OPENING MESSAGE WAS THE CARD'S REPLACEMENT AND INHERITED ITS FAULT.
     Removing shadowTaskCardHtml fixed the architecture; drawing the same
     objective as a sepia .shsaid block directly under the header restated
     it in a second place and still filled the top of the stream before
     anybody spoke. The header is pinned, carries the objective, the state
     and the controls, and is enough.

     shadowOpeningHtml IS KEPT AND STILL EXPORTED -- it is the honest render
     of "the founder's opening line" and the lane that pins it is unchanged
     -- but the stream no longer opens with it. */
  /* ── TURN ONE IS THE FOUNDER'S (founder, 2026-09-21, pass 5) ────────
     "The first user input itself MUST appear as a normal USER → SHADOW
     conversation message. That is conversational turn #1 ... There is no
     reason for the user to see 'Shadow booted with its operating context'
     before seeing what THEY asked Shadow to do."

     THIS REVERSES PASS 3, which removed this row on the grounds that the
     pinned header already carries the objective. That was true and beside
     the point: a header is a label, and a conversation that opens on the
     other party talking has lost its first turn. The header is unchanged
     and still the anchor when the stream is scrolled.

     IT IS THE ORIGINAL ASK, not the current revision -- shadowOpeningHtml
     reads revisions[0] for exactly that reason, so a task the founder
     redirected still opens on the sentence they actually opened it with,
     with the redirect further down where they said it. */
  const brief = shadowOpeningHtml(m);
  const outdated = shadowRevisionsHtml(m);
  const decision = shadowMissionNeedsFounder(m) ? shadowCheckRowsHtml(m) : "";
  const done = (m && m.completion) ? shadowCompletionHtml(m) : "";
  const tail = outdated + asks + decision + done;
  /* pass 5: Shadow's answer to the opening request stands whatever else
     happened afterwards -- see shadowIdleLineHtml */
  const idle = shadowIdleLineHtml(m);
  if (!brief && !events.length && !waiting && !tail && !idle) return "";
  /* who spoke last, so a run of messages from one side is labelled once.
     brief is the founder; idle, when drawn, is Shadow answering it. */
  let lastWho = idle ? "shadow" : (brief ? "you" : "");
  const runHead = (who) => {
    const same = lastWho === who;
    lastWho = who;
    return same ? false : undefined;
  };
  return `<div class="shtimeline">${brief}${idle}${events.map(e => {
    /* ── AN ANSWER IS THE FOUNDER SPEAKING (pass 5) ──────────────
       It was drawn as a `.shstory` card headed "You answered · 6d ago" with
       the question and a label/value list under it -- a record of a form
       submission, sitting in a stream of messages. Pass 5 names "answered"
       among the internal records that must not be chat, and requires that
       every actual user message become a USER message.

       SO IT IS ONE, and its body is what the founder chose: the values
       they picked, in the server's own labels. Nothing is composed -- if
       the record carries no summary the row is not drawn, because a bare
       "you answered" is the card this replaces. shadowStoryHtml is kept
       and still exported. */
    if (e.kind === "answered") return shadowAnsweredHtml(m, runHead("you"));
    if (e.kind === "ask_done"){
      /* WHAT WAS SETTLED, SAID RATHER THAN LABELLED (pass 4). The heads
         read "Shadow · held, then sent" and "Shadow · done when" -- the
         internal vocabulary of the hold and the criterion, on a surface
         that is meant to be one voice talking. Same two facts, same
         record, said the way Shadow would say them. */
      const line = e.what === "approve"
        ? "You approved that, so I sent it — once."
        : "You confirmed: " + esc(e.text);
      return shadowSaidRowHtml("shadow", line, "shask shask-done",
                               runHead("shadow"));
    }
    if (e.kind === "said" || e.kind === "talk"){
      /* THE SAME BLOCK BOTH SIDES SPEAK IN, and the same one the worker's
         turns use: a head that names the speaker over the line itself. No new
         class, no new surface -- the head is the only thing that differs. */
      const mine = !(e.kind === "talk" && e.who === "shadow");
      /* TWO PARTICIPANTS, TWO NAMES (founder, 2026-09-21, pass 4). The head
         used to read "You → Shadow", which is the shape of a message being
         RELAYED -- true of the plumbing and wrong about the product. There
         is one conversation and the founder is in it, so the founder is
         "You" and the other side is "Shadow". */
      const who = mine ? "You" : "Shadow";
      /* SHADOW'S OWN PROSE GOES THROUGH THE SANITISER, THE FOUNDER'S DOES NOT
         (founder, 2026-09-17) -- the same split shadowMsgHtml has always
         made. Shadow's replies can carry the protocol fences the Now chat
         speaks in (```chips and its five siblings); the panel this stream
         replaced ran them through shadowProseHtml and this did not, so a
         bare "```chips" reached the founder. The founder's own words are
         theirs and are only escaped.

         ONE SANITISER, NOT A SECOND: shadowProseText/-Html in
         15-shadow-overlay.js is the existing one, and the unterminated-fence
         case was fixed there rather than here. The guards below keep this
         renderable in a context that loaded this module alone. */
      /* ── A REPLY THAT IS A RECORD IS NOT DRAWN (pass 5) ──────────
         Shadow's side of the task chat is mostly speech and occasionally
         bookkeeping -- "Sent worker first instruction: You are a delegate
         session…" is a real reply on real records, and it is the worker's
         business. The founder's OWN lines are never tested: they are the
         founder's words and belong on screen whatever shape they take. */
      if (!mine && shadowNotSpeech(
            (typeof shadowProseText === "function")
              ? shadowProseText(e.text) : e.text)) return "";
      const body = mine ? esc(e.text)
        : (typeof shadowProseHtml === "function") ? shadowProseHtml(e.text)
        : (typeof shadowProseText === "function") ? esc(shadowProseText(e.text))
        : esc(e.text);
      /* v4.1 (V4-7): the chip under the reply -- the label the server set,
         and Undo through the same mission-action door every control uses */
      const undo = (e.limits && e.limits.mid)
        ? ` <button class="btn shlimundo" type="button" data-shact="undo_limits"
            data-shmid="${escAttr(e.limits.mid)}"
            title="Put the previous limit back">Undo</button>` : "";
      const run = runHead(mine ? "you" : "shadow");
      return shadowSaidRowHtml(mine ? "you" : "shadow", body + undo,
                               undo ? "shlimits" : "",
                               run === false ? false : who);
    }
    /* ── THE WORKER DOES NOT SPEAK ON THIS SURFACE (founder, 2026-09-21,
         pass 4) ────────────────────────────────────
       A turn in flight is "Shadow is working"; a turn that reported is
       Shadow saying what the worker reported, in the worker's own words and
       with no turn number attached. shadowOpenTurnHtml and
       shadowAgentRowHtml are NOT deleted -- they are still exported, still
       the honest render of "the worker's Nth turn", and still what any
       caller wanting that view gets. The main conversation stopped being
       one of those callers. */
    if (e.kind === "worker" && e.open)
      return shadowWorkingHtml(e.ts, runHead("shadow"));
    /* ── SHADOW'S OWN SENTENCE WINS (pass 9) ─────────────────────────
       When Shadow wrote one for this turn it IS the message -- first
       person, its own voice, its own reading of what the worker produced.
       shadowThirdPerson is the fallback for a turn it said nothing about,
       and it stays exactly what it was. */
    return shadowSaidRowHtml("shadow",
                             esc(e.own || shadowThirdPerson(e.say)),
                             e.own ? "shsay shsayown" : "shsay",
                             runHead("shadow"));
  }).join("")}${outdated}${asks}${decision}${done}${
    waiting ? shadowThinkingHtml() : ""}</div>`;
}

/* ── THE ASK ROWS (v4.2) ─────────────────────────────────────────────────
   One row per thing the task is waiting on, read off the record the same
   way mission_engine.pending_asks reads it (kept in step by
   test_shadow_v42_ui.js): a held instruction (Approve / Withdraw), an
   unmet founder-confirm check while the loop waits (Confirm), a typed
   question (answered on its form, drawn below), a parked instruction after
   a take-over (Hand back). Every button is the SAME mission-action door the
   card uses; the hint line says the composer answers the same row. */
function shadowAskRowsHtml(m){
  if (!m || !m.id) return "";
  const id = escAttr(m.id);
  const rows = [];
  const ap = m.approval;
  if (m.state === "paused" && ap && !ap.used && m.pending_say){
    rows.push(`<div class="shsaid shask shask-hold">
      <div class="shsaidhead">Shadow · holding</div>
      <div class="shsaidtext">I am holding one instruction; it waits for you.</div>
      <div class="shcard2 shaskcard">
        <div class="shcard2row"><span class="shcard2k">instruction</span>
          <span class="shcard2v shapprovesay">${esc(m.pending_say)}</span></div>
        <div class="shcard2acts">
          <button class="btn pri" type="button" data-shact="approve"
            data-shmid="${id}" data-shapproval="${escAttr(ap.id)}">Approve</button>
          <button class="btn" type="button" data-shact="answer"
            data-shkind="withdraw" data-shmid="${id}">Withdraw</button>
        </div>
      </div>
      <div class="shsaidtext shaskhint">Or say it here: “yes”, “change it to …”, or “I did it myself”.</div>
    </div>`);
  }
  if (m.intervention && m.intervention.id){
    rows.push(`<div class="shsaid shask shask-question">
      <div class="shsaidhead">Shadow · question</div>
      <div class="shsaidtext">${esc(m.intervention.question || "")}</div>
      <div class="shsaidtext shaskhint">Answer on the form below.</div>
    </div>`);
  }
  /* ── ONE DECISION, ONE PLACE (founder, 2026-09-21) ──────────────────
     A founder_confirm row USED TO BE DRAWN HERE TOO, with its own live
     Confirm button, while shadowCheckRowsHtml drew the same row with
     another one a few hundred pixels below. The same criterion carried two
     working buttons on one screen, and answering either left the other
     sitting there looking unanswered. That is the duplicate the founder
     named: "there should be ONE canonical representation of a user
     decision".

     THE ONE THAT SURVIVED IS THE RICHER ONE. shadowCheckRowsHtml draws the
     decision packet with it -- shadowDecisionHtml: the artifact the
     decision is about and the facts shadow_evidence counted -- so the
     question is asked next to the thing being judged. This block could
     only ever print the sentence. Keeping the poorer copy and deleting the
     evidence would have been the wrong half to keep.

     NOTHING ELSE IN THIS FUNCTION MOVED. The holding/approval row, the
     intervention question and the parked say are not drawn anywhere else
     and are untouched. */
  if (m.state === "paused" && m.parked_say){
    rows.push(`<div class="shsaid shask shask-parked">
      <div class="shsaidhead">Shadow · parked</div>
      <div class="shsaidtext">You took over, so I parked my next instruction instead of holding it:</div>
      <div class="shcard2 shaskcard">
        <div class="shcard2row"><span class="shcard2k">parked</span>
          <span class="shcard2v shapprovesay">${esc(m.parked_say)}</span></div>
        <div class="shcard2acts">
          <button class="btn pri" type="button" data-shact="resume"
            data-shmid="${id}">Hand back to Shadow</button>
        </div>
      </div>
      <div class="shsaidtext shaskhint">On hand back I ask whether it is still wanted; I never resend it on my own.</div>
    </div>`);
  }
  return rows.join("");
}

/* ── THE STORY: what happened either side of the founder's answer ─────────
   Two facts the record has carried all along and the panel never drew:

     founder_response  what YOU answered, and what it signed off. Stamped by
                       the server when the intervention was resolved, so
                       "what happened after I answered" stops being a thing
                       the founder has to reconstruct from the chat.
     last_instruction  Shadow's own last word TO the delegate -- the turn it
                       sent after reading the answer. This is Shadow talking,
                       which is exactly what this pane is for.

   Both are read-only reads of fields already delivered by
   /api/shadow/missions. Nothing is written, nothing is derived from state,
   and a mission without them draws nothing. */
/* ── WHAT THE FOUNDER CHOSE, AS A MESSAGE FROM THE FOUNDER ──────────
   (founder, 2026-09-21, pass 5.) An intervention is answered on a FORM, so
   the record holds choices rather than a sentence: `founder_response.summary`
   is the server's own [{label, value}] list. That is still the founder
   speaking, and pass 5 requires every actual user message to be a USER
   message, so it is drawn as one.

   NOTHING IS COMPOSED. The labels and the values are the server's, joined
   with a comma; no verb is added, no sentence is built around them. A
   response with no summary draws nothing at all rather than a bare "you
   answered", which is the record-shaped row this replaces.

   THE QUESTION IS NOT REPEATED HERE. Shadow already asked it, in its own
   row, above -- printing it again beside the answer is the duplication the
   redesign removes. */
function shadowAnsweredHtml(m, head){
  const fr = m && m.founder_response;
  if (!fr || typeof fr !== "object") return "";
  const parts = (Array.isArray(fr.summary) ? fr.summary : [])
    .map(x => {
      const label = String((x && (x.label || x.key)) || "").trim();
      const value = (x && x.value !== undefined && x.value !== null)
        ? String(x.value).trim() : "";
      if (!label && !value) return "";
      return (label && value) ? label + ": " + value : (label || value);
    })
    .filter(Boolean);
  if (!parts.length) return "";
  return shadowSaidRowHtml("you", esc(parts.join(" · ")), "shanswered", head);
}

function shadowStoryHtml(m){
  if (!m) return "";
  const fr = m.founder_response;
  const answered = (fr && typeof fr === "object") ? `<div class="shstoryrow">
    <div class="shstoryhead">You answered${fr.answered_at
      ? " \u00b7 " + esc(shadowStampAgo(fr.answered_at)) : ""}</div>
    ${fr.question ? `<div class="shstoryq">${esc(fr.question)}</div>` : ""}
    ${Array.isArray(fr.summary) && fr.summary.length
      ? `<ul class="shstorylist">${fr.summary.map(x => `<li>${
          esc(String((x && x.label) || (x && x.key) || ""))}${
          x && x.value !== undefined && x.value !== null
            ? ` <b>${esc(String(x.value))}</b>` : ""}</li>`).join("")}</ul>`
      : ""}
  </div>` : "";
  /* THE "SHADOW -> THE AGENT" ROW IS GONE (founder, 2026-09-15).
     last_instruction is the turn Shadow injects INTO the delegate session --
     worker instruction and context ("You are a delegate session working for
     the founder via Shadow. Objective: ... Work step by step"), addressed to
     the agent and not to the founder. It belongs to the worker chat, which
     still carries it in full behind "Open the chat".

     PRESENTATION ONLY, and deliberately narrow: the field is untouched on
     the record, still delivered by /api/shadow/missions, still what Shadow
     sends and still what the delegate receives. Only this pane stopped
     drawing it. What the FOUNDER did -- founder_response -- stays, because
     that half of the story is theirs. */
  if (!answered) return "";
  return `<div class="shstory">${answered}</div>`;
}

/* ── WHAT SHADOW WANTS TO REMEMBER ───────────────────────────────────────
   The SAME instructions the memory list holds (S.shadowMemory, loaded by
   loadShadowHome) and the SAME confirm hook it has always used --
   data-shconfirm -> shadowInstructionAct(id, "confirm"). Nothing about
   storage, precedence or the confirm/revoke lifecycle changed; the
   UNCONFIRMED ones simply surface here, in the Shadow<->founder flow where
   the decision actually belongs, instead of only behind the footer door.

   Confirmed and revoked rows are NOT drawn here -- they are not asking for
   anything, and the full list (with Revoke) is unchanged. */
function shadowPendingMemoryHtml(){
  const S_ = (typeof S !== "undefined") ? S : {};
  const rows = (S_.shadowMemory || [])
    .filter(r => r && !r.confirmed && !r.revoked_at);
  if (!rows.length) return "";
  return rows.map(r => `<div class="shremember" data-shmem="${escAttr(r.id)}">
    <span class="shrememberk">${esc(
      (r.scope === "chat" && r.scope_id) ? shadowChatLabel(r.scope_id)
        : (SH_PREC[r.precedence] || r.precedence || "shadow"))}</span>
    <span class="shremembertext">I\u2019ll remember: ${esc(r.text || "")}</span>
    <button class="btn pri shrememberok" type="button"
      data-shconfirm="${escAttr(r.id)}">Confirm</button>
  </div>`).join("");
}

function shadowTaskCardHtml(m){
  if (!m) return "";
  const S_ = (typeof S !== "undefined") ? S : {};
  const f = shadowTaskFaceFor(m);
  /* HISTORICAL (founder, 2026-09-14), kept because it explains why the
     transcript was never the point of this card. The collapsed toggle it
     describes was itself removed on 2026-09-15 -- "Open the chat" in the
     header is the one door now -- but the reasoning below is why:

     THE WORKER CHAT IS COLLAPSED BY DEFAULT (founder, 2026-09-14).

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
  /* the SECOND reason the flat row stands down: the ask below this card is
     the founder confirmation for every check still outstanding, so printing
     the criteria here prints them twice. See shadowAskCoversChecks. */
  const askedOff = shadowAskCoversChecks(m);
  /* and the state after that one: the task FINISHED. The flat "done when"
     row is the same criteria without the verdicts, so the summary replaces
     it for exactly the reason the sign-off list does -- the same criteria
     printed twice is not a compact card. Keyed on the summary the server
     stamped, never on `state === "done"`, so a mission completed before the
     field existed keeps the row it has always had. */
  const finished = !!m.completion;
  /* target_mode + target_session ARE the answer to "where does this run"; no
     second source and nothing inferred.

     EXCEPT THAT "WHEN YOU BEGIN" WAS A LIE FOR THE WHOLE OF PROVISIONING
     (founder, 2026-09-19: "we're having to hot start the task again, we
     shouldn't need to do that"). Enter on + Delegate creates AND starts --
     measured on this machine, every mission since 2026-09-18 carries
     start_requested_at equal to created_at, so the start is always taken in
     the same second. What the founder then landed on was this line, which
     is drawn from target_session alone and therefore said "a new chat Shadow
     starts WHEN YOU BEGIN" for the entire gap before the delegate exists.

     THAT GAP IS NOT SHORT. m-223632491565: created 02:52:07, criteria
     written 02:52:27, session spawned and chat published 02:52:52 -- 45
     seconds of a card instructing the founder to begin a task Shadow had
     already begun. Told to begin it, they look for the way to begin it.

     shadowMissionStarting() is the EXISTING predicate for exactly this
     window -- the same one that takes Start away and draws the QUEUED face
     -- so no new state, no new flag, and nothing is inferred from whether a
     chat exists. The moment target_session lands, the line below is the
     chat's name, unchanged. */
  const starting = (typeof shadowMissionStarting === "function")
    && shadowMissionStarting(m);
  const acts = m.target_mode === "new"
    ? (m.target_session
        ? `its own chat · ${esc(shadowChatLabel(m.target_session))}`
        : (starting ? "a new chat — Shadow is starting it now"
                    : "a new chat Shadow starts when you begin"))
    : (m.target_session
        ? esc(shadowChatLabel(m.target_session))
        : "an existing chat");
  /* THE KIND TAG IS GONE (founder, 2026-09-19). It printed `m.template` --
     and since the v5 one-box Delegate never asks for a kind, every task the
     founder creates carries the default offer, so the tag was the same word
     on every card. A constant is not information; it was nine pixels of
     mono-caps saying "fix" beside a title that already said what the work
     was. The FIELD is untouched: create() still stamps a template, the
     engine still budgets and constrains by it, and Settings still edits it
     per kind -- only the badge that quoted it here came off. */
  return `<div class="shcard2" data-shtaskcard="${escAttr(m.id)}">
    <div class="shcard2head">
      <span class="shcard2obj">${esc(m.objective || "")}</span>
      ${/* KEPT, AND THE ATTEMPT TO REMOVE IT IS WHY THIS NOTE EXISTS
           (founder, 2026-09-21, pass 2). This line restates the objective
           about 80px below the same sentence in the pinned header, which
           reads as the title twice and was removed on exactly that
           reasoning -- the same reasoning that took the state pill out
           below.

           IT WENT STRAIGHT BACK. `.shwtitle` is `white-space:nowrap` with
           `text-overflow:ellipsis`, so the header shows as much of the
           objective as the width allows and no more. On the short fixtures
           this looks like pure duplication; on a real 443-character
           objective the header is a truncated fragment and THIS is the only
           place the founder can read what they asked for. Two lanes pinned
           it (test_shadow_home, test_shadow_rhs) and both were right.

           The duplication is real and is the price of the header not
           wrapping. If it is worth removing, the header is what changes.

           THE SECOND OF THE THREE, GONE 2026-09-19. This pill sat roughly
           40px below the header's, saying the same word about the same
           task. The header's is pinned and adjacent to the title, so it is
           the one that stays. */""}
    </div>
    <div class="shcard2row"><span class="shcard2k">where it runs</span>
      <span class="shcard2v">${acts}</span></div>
    ${awaiting || finished || askedOff ? "" : `<div class="shcard2row"><span class="shcard2k">done when</span>
      <span class="shcard2v">${checks.length
        ? esc(checks.join(" · "))
        : "Shadow is writing these — you left it open"}</span></div>`}
    ${/* THE TURN ROW IS THE COUNT, WITHOUT THE TRACK (founder, 2026-09-15).
         The meter came off the brief; the numbers it was drawn from are
         exactly the ones still printed here. shadowBudgetPct / SevbarHtml,
         the thresholds and turn counting itself are all untouched. */""}
    ${/* THE TURN ROW MOVED TO THE HEADER (founder, 2026-09-20). It is the
         one fact on this card that CHANGES while you read -- and the card
         now scrolls away with the conversation, so a live count sitting in
         it would be invisible for exactly the long run it matters on. The
         header is the pane's one pinned line; shadowTurnNow and max_turns
         are unchanged, and shadowHeadTurnHtml is their only new reader. */""}
    ${/* WHY IT IS WAITING, ON THE CARD THE FOUNDER ACTUALLY OPENS.

         The QUEUED pill says the state; it does not say the cause, and the
         cause is the one thing that makes the state make sense -- a task
         "queued" for no visible reason reads as a task that failed to
         start. The reason is never ambiguous: `queued` is written by
         MissionScheduler.start and by nothing else, and it means one thing
         -- every slot the run limit allows is in use.

         MEASURED IN THE LIVE APP (run-limit walkthrough, 2026-09-16). This
         sentence was first put on the Watching plane's row, where
         shadowPlaneHtml draws the queued row's actions. That plane's
         "Working" tab is unreachable: SCREENS.shadowwatching passes the
         literal "watching" to shadowPlaneHtml, so the tab renders as a
         button that changes nothing. The copy was live, correct, tested --
         and on a surface the founder cannot open. It belongs here, on the
         task card, which is where the founder was already looking.

         The number comes from the settings the page has already loaded --
         no new fetch, and no second opinion about the cap. Absent (the card
         rendered before the settings landed), the sentence stands without
         it rather than guessing a number. */""}
    ${m.state === "queued" ? `<div class="shcard2row"><span class="shcard2k"
      >waiting for</span><span class="shcard2v">a free slot${
        shadowRunLimit() ? ` — Running at once is ${esc(String(
          shadowRunLimit()))}` : ""}. It starts on its own when one
        frees.</span></div>` : ""}
    ${/* LAST UPDATED IS NOT DRAWN (founder, 2026-09-15). Presentation only:
         updated_at is still on the record, still returned by the API, and
         still what the freshness helpers below read -- the row simply does
         not belong on a founder-facing brief. */""}
    ${/* STOPPED ON IS NOT DRAWN (founder, 2026-09-15). "needs founder" is
         what the NEEDS YOU pill above already says, in the founder's own
         words; the raw blocker restated it in the engine's. block_reason is
         untouched on the record, still returned, and still what
         goalBlockerCopy reads for the Goal workspace. */""}
    ${/* ── THE ASK AND THE RESULT MOVED TO THE END OF THE THREAD
         (founder, 2026-09-20: "we shouldn't have to scroll up or down to
         look at the necessary stuff") ────────────────────────────────────
         THE BUG, and it is a placement bug rather than a rendering one.
         This card is the FIRST row of the scroller and the conversation
         grows downward from it (shadowStageHtml: card, then timeline). So
         the sign-off list and the done summary -- the two things a founder
         opens a task to act on -- sat ABOVE every turn the task had taken.
         On a task with twenty turns the founder lands at the newest row and
         has to scroll back past all of them to reach the Confirm button
         that the scroll position itself was telling them about.

         THE ORDER IS NOW THE ORDER THINGS HAPPENED: brief, then the turns,
         then what it came to. Both blocks render after the timeline in
         shadowStageHtml, which is the bottom of the scroller and directly
         above the composer -- where the founder already is.

         The PREDICATES are unchanged and still computed here, because the
         card still reads them to decide whether to draw its flat "done
         when" row. Only the two calls moved. */""}
    ${/* v4 (C9, ADR-043): A HELD SAY IS SHADOW ASKING, so it belongs on this
         card like the intervention form does. The founder reads the exact
         string, and Approve releases that string once through the say path
         (one-use approval, bound to task, version, turn and hash). Stop and
         Resume stay off this card, as ruled 2026-09-15. */""}
    ${m.state === "paused" && m.approval && !m.approval.used && m.pending_say ? `
    <div class="shapprove" data-shapprove="${escAttr(m.id)}">
      <div class="shcard2row"><span class="shcard2k">${esc(
        m.pause_reason === "floor_confirm" ? "floor" : "wants to say")}</span>
        <span class="shcard2v shapprovesay">${esc(m.pending_say)}</span></div>
      <div class="shcard2acts">
        <button class="btn pri" type="button" data-shact="approve"
          data-shmid="${escAttr(m.id)}"
          data-shapproval="${escAttr(m.approval.id)}">Approve</button>
        <span class="shcard2hint">one use, this text only</span>
      </div>
    </div>` : ""}
    ${/* NO SECOND DOOR TO THE WORKER CHAT (founder, 2026-09-15). "Open the
         chat" in the header is the single entry point now, so the inline
         toggle and the transcript it revealed are gone from this card. The
         session, the transcript, shadowTaskChatHtml and the data-shtaskchat
         handler are all untouched -- this pane simply stopped offering a
         second way in, which is what kept it a report rather than a chat. */""}
    <div class="shcard2acts">
      ${startable ? `<button class="btn pri" type="button"
        data-shstart="${escAttr(m.id)}">Start the task</button>
        <span class="shcard2hint">…or keep telling me</span>` : ""}
      ${/* STOP COMES BACK TO THIS CARD, BECAUSE ITS REPLACEMENT WAS ON
           ANOTHER SCREEN (founder, 2026-09-16).

           The note this replaces removed Stop and Resume on 2026-09-15 --
           "this pane is where Shadow reports and asks, not a worker control
           panel" -- on the stated understanding that "the same two buttons
           on the same two hooks still render in shadowPlaneHtml". They do.
           shadowPlaneHtml is rendered by SCREENS.shadowwatching, which is
           the WATCHING screen, and only under its Working tab. It is not
           this screen. SCREENS.shadow renders shadowTaskListHtml on the left
           and this card on the right, so on the surface the founder actually
           works from, a running task offered its state pill, "Open the chat"
           and nothing else.

           MEASURED BY RENDERING IT (2026-09-16), one mission per state
           through SCREENS.shadow, counting data-shact hooks in the output:

             running  pill RUNNING    actions []      <- no way to stop it
             paused   pill NEEDS YOU  actions []
             blocked  pill NEEDS YOU  actions []
             queued   pill QUEUED     actions [drop]

           A previous pass had already found half of this: it unpinned the
           Watching screen's tab so the Working rows could be reached at all,
           and its note says plainly that until then "there was no reachable
           way to STOP a running task, only the row's x which deletes it".
           Making the other screen reachable did not put the control where
           the work is.

           NOTHING NEW IS INVENTED. Same `data-shact="stop"` hook, same
           shadowMissionAct, same endpoint, same founder_force_stop behind
           it, and the same state condition shadowPlaneHtml has always used.
           It sits beside Drop and Retry, which never left this card.

           RESUME IS STILL NOT DRAWN HERE, deliberately: a NEEDS YOU task is
           answered by its intervention form (shadowInterventionHtml) or from
           the Watching screen, and ending work the founder no longer wants
           is the ask this slice covers. */""}
      ${/* STOP IS WITHHELD AT NEEDS YOU, AND NOWHERE ELSE (founder,
           2026-09-21: "do not show Stop as though a worker is currently
           burning turns"). A task parked on the founder's signature has no
           turn in flight -- the loop is waiting on them -- so Stop there
           described a cost that was not being incurred.

           THE NARROWING IS shadowMissionNeedsFounder, NOT `state`. The
           first cut of this withheld Stop from every paused and blocked
           task, and test_shadow_home caught it: a task paused for a STALL,
           or blocked, is exactly when the founder most needs to end work,
           and the assertion that pins Stop to the card ("ending work the
           founder no longer wants is the one control that has to be where
           the work is") was written for that case. Only the four founder
           pause reasons are a decision the founder is being asked for; the
           rest keep the control they had.

           NOTHING IS STRANDED EITHER WAY. Answering the ask releases the
           pause and Stop returns on the same render, and the task list row
           carries its own stop throughout. */""}
      ${/* STOP IS ON THE HEADER NOW, not here -- see the note at its new
           site in shadowHomeHtml. Drawing it in both places would be the
           duplicate-control bug this pass exists to remove. */""}
      ${m.state === "queued" ? `<button class="btn" type="button"
        data-shact="drop" data-shmid="${escAttr(m.id)}">Drop</button>` : ""}
      ${/* v4.2 (founder 2026-09-21): the Retry button is gone from here too.
           The action survives on the server for the API; nothing draws it. */""}
      ${/* v4.1 (V4-9): DONE IS NOT A DEAD END. Hand back puts Shadow back to
           work in the SAME chat -- what the founder did there by hand is read
           as chat, and they confirm at the end. Retry (above) stays for "run
           it again from the start in a new chat". Typing in the task's chat
           does the same reopen; this is the click for it. */""}
      ${["done", "failed", "stopped"].includes(m.state) && m.target_session
        ? `<button class="btn" type="button" data-shact="reopen"
        data-shmid="${escAttr(m.id)}"
        title="Shadow goes back to work in the same chat; you confirm when it is done"
        >Hand back to Shadow</button>` : ""}
    </div>
    ${/* THE FLOORS LINE IS NOT DRAWN (founder, 2026-09-15). What Shadow may
         not do on its own is safety CONFIGURATION, and it belongs in Shadow
         Settings, which still renders it; repeating it under every task made
         the brief a safety sheet. shadowFloorsLine, the floors themselves and
         every floor check are untouched -- a floor still blocks, still pauses
         on floor_confirm, and still reads NEEDS YOU. */""}
  </div>`;
}

/* ── + Delegate: the new-task panel ──────────────────────────────────────
   In the right pane, never a modal. The founder describes an outcome; the
   app posts it to the EXISTING mission endpoint with target_mode "new". The
   term never reaches the UI -- the button IS the intent. */
/* THE FALLBACK, NOT THE LIST. Delegate offers is a real setting now: the
   server sends the founder's kinds on every settings read, and
   shadowOfferKinds() below is what every surface asks. These four are what
   an unconfigured install offers and what renders in the window before the
   first settings read lands -- keep them in step with
   mission_engine.BUILTIN_OFFERS, which is the source of record. */
const SH_KINDS = ["fix", "feature", "research", "watch"];

/* The kinds Shadow offers, from the server when it has answered.

   ONE READER FOR THREE SURFACES -- the Delegate form's kind buttons, the
   budget picker, and the Settings chips. They used to share a constant,
   which is why they could not drift; they share this instead, so they still
   cannot, and now they follow the founder. */
function shadowOfferKinds(){
  const S_ = (typeof S !== "undefined") ? S : {};
  const offers = ((S_.shadowSettings || {}).tasks || {}).offers;
  return (Array.isArray(offers) && offers.length) ? offers : SH_KINDS;
}

function shadowNewDraft(){
  const S_ = (typeof S !== "undefined") ? S : {};
  if (!S_.shadowNew) S_.shadowNew = { objective: "", done: "", kind: "fix" };
  /* A DRAFT CANNOT SIT ON A RETIRED KIND. The draft outlives the settings
     read and outlives a removal, so a founder who removed `watch` while a
     draft was on it would otherwise post a kind the route now refuses. The
     coercion belongs here rather than in the panel, because the create path
     reads the draft too and both must agree. */
  const kinds = shadowOfferKinds();
  if (kinds.indexOf(S_.shadowNew.kind) === -1) S_.shadowNew.kind = kinds[0];
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
    <div class="shnewkinds">${shadowOfferKinds().map(k => `<button
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

/* ── v5: THE LINE IS THE TASK (founder, 2026-09-18) ───────────────────────
   + Delegate opens ONE box, "What do you have in mind?", and that is the
   whole of it. The line the founder types IS the objective -- the same
   thing the form called "The outcome you want" -- and Enter is the same
   press "Create the task" always was: one create, one start, the delegate
   spawns. No second step, nothing to confirm, no draft to approve.

   WHAT WENT, AND WHY (founder, 2026-09-18). The door under the box ("Use
   the form instead") is gone: one way in cannot drift from itself, and two
   doors onto two different create paths is how they drift. Done-when is
   gone with it and is not asked for anywhere on this surface -- a task with
   no machine checks is exactly what the form produced whenever that
   optional field was left empty, which is what it nearly always was, and
   the founder still signs off on the result the same way.

   NOTHING ABOUT CREATING IS RE-IMPLEMENTED. shadowNewTalk hands the line
   to shadowCreateTask -- the one writer of POST /api/shadow/missions
   followed by the existing shadowMissionAct(id, "start_now") -- so this box
   and the (flag-only) form cannot disagree about what a task is or how it
   starts, and the start keeps every guard it already had.

   THE FORM IS NOT DELETED. shadowDelegatePanelHtml and its Create button
   are untouched and still the way in when `flags.shadow_form` is true in
   the founder's settings -- opt-in, off by default, and no longer reachable
   by a click from this box. */
function shadowFormOn(){
  /* the box is the way in; the form is the founder's own settings flag and
     nothing in the UI turns it on -- the door that used to is removed */
  return typeof SETTINGS !== "undefined" && !!SETTINGS && !!SETTINGS.flags
    && SETTINGS.flags.shadow_form === true;
}

function shadowNewChat(){
  const S_ = (typeof S !== "undefined") ? S : {};
  if (!S_.shadowNewChat)
    S_.shadowNewChat = { thread: [], busy: false, err: null, text: "" };
  return S_.shadowNewChat;
}

/* -- THE + Delegate COMPOSE PANEL IS MOUNTED, NOT RE-RENDERED ------------
   FOUNDER, 2026-09-18: "when we are typing, it goes out of focus, and you
   have to put the cursor in again" -- and then, on the fix: it has to live at
   the re-render source, with no setTimeout, no autoFocus and no programmatic
   refocus left anywhere in the path that types into this box.

   WHAT WAS DESTROYING IT. render() rebuilds two things wholesale:
   `panesEl.innerHTML = panesHtml` and `scBody.innerHTML = html`. #scBody is
   inside #panes, so either one recreates every node on the screen. The
   textarea the founder was typing into is a NEW node afterwards, and the old
   one was blurred the instant it left the document -- so the next keystroke
   goes nowhere.

   WHY IT HAD TO BE THE NODE, not a restore. Measured in Chrome 153: an
   innerHTML swap, a detach-and-graft-back, and a plain within-document move
   ALL drop focus to <body>. Only never removing the node keeps the caret
   without touching it afterwards, which is the requirement.

   HOW. The screen's markup carries an EMPTY host, [data-shnewhost], where the
   panel used to be inlined. shadowMountNewTalk() builds the panel into that
   host once. From then on -- while the panel is open, on this screen only --
   both wholesale swaps are replaced by shadowPatchInto(), which leaves any
   subtree it did not need to change alone and refuses outright to touch
   #scBody, the host, or the textarea. The textarea is therefore the SAME
   NODE for the whole life of the panel, and nothing anywhere re-places the
   cursor: the browser simply never took it away.

   THE BLAST RADIUS IS ONE SCREEN WITH ONE PANEL OPEN. shadowPanelMounted()
   is false for every other screen, and false on this one the moment
   + Delegate is shut, and both call sites fall straight back to the original
   innerHTML line. */

/* The three nodes the patch may never replace, remove, or write into.
   #scBody is here because panesHtml renders it EMPTY -- its contents are the
   screen pass's business, and letting the panes pass see "empty" as a change
   would delete the screen under the panel. */
function shadowKeepNode(el){
  if (!el || el.nodeType !== 1) return false;
  if (el.id === "scBody") return true;
  const d = el.dataset || {};
  return d.shnewhost !== undefined || d.shnewtalk !== undefined;
}

/* does this subtree CONTAIN something that must be kept? if so it may be
   recursed into, but never replaced wholesale */
function shadowHoldsKeep(el){
  if (!el || el.nodeType !== 1) return false;
  if (shadowKeepNode(el)) return true;
  if (!el.querySelector) return false;
  return !!el.querySelector("#scBody,[data-shnewhost],[data-shnewtalk]");
}

function shadowSyncAttrs(o, n){
  const want = {};
  const na = n.attributes || [];
  for (let i = 0; i < na.length; i++){
    want[na[i].name] = 1;
    if (o.getAttribute(na[i].name) !== na[i].value)
      o.setAttribute(na[i].name, na[i].value);
  }
  const oa = o.attributes || [];
  for (let i = oa.length - 1; i >= 0; i--)
    if (!want[oa[i].name]) o.removeAttribute(oa[i].name);
}

/* THE ONE THING THAT IS ALLOWED TO KILL THE BOX, and it is not churn.
   Set for the duration of one patch pass by shadowPatchInto: true while the
   INCOMING markup still asks for a keep node, false when it has stopped --
   and "it has stopped" is the only honest reading of + Delegate being shut.

   Why it had to become explicit. The first cut used position as the proxy:
   a slot the new markup no longer had was taken to mean the panel was over,
   so the subtree in it was removed keep-node and all. But a slot can also go
   away, or change tag, or shift index, because something ELSE on the screen
   moved -- a task arriving in the list, an error line appearing, a pill the
   header grew. Read positionally, every one of those is indistinguishable
   from a close, and each one would have taken the founder's cursor with it.
   Read from the markup, none of them is: the html still carries a host, so
   the panel still exists, so the node stays. */
let shPatchWantsKeep = true;

function shadowPatchNode(o, n, parent){
  if (shadowKeepNode(o)) return;              /* never touched, ever */
  if (o.nodeType !== n.nodeType
      || (o.nodeType === 1 && o.tagName !== n.tagName)){
    /* the slot changed SHAPE around something that must not die. Leave the
       old subtree exactly as it is: one pass of stale markup around a live
       cursor costs nothing, and the pass after the panel closes replaces it
       the ordinary way. */
    if (shPatchWantsKeep && shadowHoldsKeep(o)) return;
    parent.replaceChild(n.cloneNode(true), o);
    return;
  }
  if (o.nodeType !== 1){
    if (o.nodeValue !== n.nodeValue) o.nodeValue = n.nodeValue;
    return;
  }
  if (o.outerHTML === n.outerHTML) return;    /* unchanged: leave it alone */
  if (!shadowHoldsKeep(o)){
    /* exactly what the innerHTML swap did to this subtree, and no more */
    parent.replaceChild(n.cloneNode(true), o);
    return;
  }
  shadowSyncAttrs(o, n);
  shadowPatchChildren(o, n);
}

function shadowPatchChildren(o, n){
  const a = [], b = [];
  for (let i = 0; i < o.childNodes.length; i++) a.push(o.childNodes[i]);
  for (let i = 0; i < n.childNodes.length; i++) b.push(n.childNodes[i]);
  /* a slot that genuinely went away takes whatever was in it -- but ONLY
     when the incoming markup has stopped asking for the box (+ Delegate
     shut). A list that got shorter for any other reason is churn, and churn
     does not get to remove the node the founder is typing into. */
  for (let i = a.length - 1; i >= b.length; i--){
    if (shPatchWantsKeep && shadowHoldsKeep(a[i])) continue;
    o.removeChild(a[i]);
  }
  for (let i = 0; i < b.length; i++){
    if (i < a.length) shadowPatchNode(a[i], b[i], o);
    else o.appendChild(b[i].cloneNode(true));
  }
}

/* Reconcile host's children against html. Returns true when it handled the
   write, so the caller can fall back to innerHTML if it did not. */
function shadowPatchInto(host, html){
  if (!host || typeof document === "undefined" || !document.createElement)
    return false;
  const tpl = document.createElement("div");
  tpl.innerHTML = html;
  /* ask the INCOMING markup, once, whether the box still belongs on screen --
     see shPatchWantsKeep. Nested patches restore the outer answer, so a mount
     pass inside a screen pass cannot leave the flag wrong for the caller. */
  const prev = shPatchWantsKeep;
  shPatchWantsKeep = !!(tpl.querySelector
    && tpl.querySelector("#scBody,[data-shnewhost],[data-shnewtalk]"));
  try { shadowPatchChildren(host, tpl); }
  finally { shPatchWantsKeep = prev; }
  return true;
}

/* Is the panel actually in the document right now? The textarea's presence
   is the test, not S alone: on the render that OPENS + Delegate the host is
   still empty, so that pass takes the ordinary innerHTML path and the mount
   below fills it. Nothing is focused yet at that point. */
function shadowPanelMounted(){
  if (typeof document === "undefined" || !document.querySelector) return false;
  if (typeof S === "undefined" || !S || S.screen !== "shadow") return false;
  if (!S.shadowNewOpen) return false;
  if (typeof shadowFormOn === "function" && shadowFormOn()) return false;
  return !!document.querySelector("[data-shnewtalk]");
}

/* Build once, then update in place. The textarea is a keep-node, so the
   value, the selection and the focus the browser is holding are never
   written by a render -- the DOM node is the draft. */
/* THE HOST THAT ALREADY HOLDS THE BOX WINS. Protecting a subtree whose shape
   changed (see shPatchWantsKeep) can leave a second, EMPTY host cloned in
   beside the live one for a pass. Plain document order would then hand the
   mount whichever came first, and an empty host means "build it" -- a second
   textarea, and the founder's caret stranded in the first. Asking for the
   host that contains a box makes that unreachable: while one exists it is the
   only host this function will ever write to. */
function shadowNewTalkHost(){
  if (typeof document === "undefined" || !document.querySelector) return null;
  const box = document.querySelector("[data-shnewhost] [data-shnewtalk]");
  const held = (box && box.closest) ? box.closest("[data-shnewhost]") : null;
  return held || document.querySelector("[data-shnewhost]");
}

function shadowMountNewTalk(){
  if (typeof document === "undefined" || !document.querySelector) return;
  const host = shadowNewTalkHost();
  if (!host) return;
  const html = shadowNewTaskChatHtml();
  if (!host.firstChild){ host.innerHTML = html; return; }   /* mounted once */
  shadowPatchInto(host, html);
}

function shadowNewTaskChatHtml(){
  const c = shadowNewChat();
  const rows = c.thread.map(t => (typeof shadowMsgHtml === "function")
    ? shadowMsgHtml(t)
    : `<div class="shmsg ${t.who === "founder" ? "shmine" : "shshadow"}">${esc(t.text || "")}</div>`
  ).join("");
  return `<div class="shnewchat" data-shnewchat="1">
    ${rows ? `<div class="shthread">${rows}</div>` : ""}
    <div class="shwcomp"><div class="shcompwrap">
      <textarea class="shcompose" data-shnewtalk="1" rows="2"
        placeholder="What do you have in mind?"${c.busy ? " disabled" : ""}>${esc(c.text || "")}</textarea>
      <button class="btn shsend" type="button" data-shnewsend="1"
        aria-label="Send"${c.busy ? " disabled" : ""}>↑</button>
    </div></div>
    ${c.err ? `<div class="shnewerr">${esc(c.err)}</div>` : ""}
  </div>`;
}

/* THE ONE LINE, AND WHAT IT DOES. The founder's line goes to Shadow and
   Shadow answers it. If the line held work, Shadow says so with a mission
   fence and the task opens as a brief for the founder to confirm; if it did
   not, there is a reply and no task. Which of the two happened is Shadow's
   read of the sentence, not a rule in this file.

   THE LINE IS NEVER LOST. It goes into the thread before the request and
   stays there whatever comes back -- the reply under it, or the reason the
   turn failed. Never a cleared field and no explanation. */
async function shadowNewTalk(){
  if (typeof fetch === "undefined" || typeof S === "undefined") return null;
  const c = shadowNewChat();
  const text = String(c.text || "").trim();
  if (!text || c.busy) return null;
  c.thread.push({ who: "founder", ts: Date.now(), text });
  c.text = ""; c.busy = true; c.err = null;
  if (typeof scheduleRender === "function") scheduleRender();
  /* ── THIS BOX IS A CHAT, SO IT TALKS FIRST (founder, 2026-09-21) ──────
     THE BUG. It was chat-SHAPED and was not a chat: every Enter went
     straight to shadowCreateTask -> POST /api/shadow/missions, and then to
     `start_now`. So "Hi" became a task with no work in it, the worker was
     spawned on it, reported "no work requested", and the founder was asked
     "What do you want done?" -- a clarification about a task they never
     opened. Traced end to end in test_shadow_hi_trace.js: two requests, and
     Shadow was asked about neither.

     IT NOW GOES WHERE THE ANSWERS COME FROM. /api/shadow/chat is the same
     door the stage composer uses, and a mission exists there ONLY because
     Shadow emits a `mission` fence -- so a greeting gets a reply and
     nothing else, and a real ask opens a task through the path that already
     existed. No second rule, no classifier here, nothing about the create
     endpoint changed: the Delegate FORM still posts to it, where a founder
     typing into "The outcome you want" is deliberate.

     AND IT NO LONGER STARTS WHAT IT OPENS. The task lands as a draft and
     Start is the founder's press, which is what SHADOW.md has always said
     ("Start is the founder's") and what the rest of this pane already
     assumes. Auto-starting a task Shadow had just inferred is how a
     greeting reached a worker at all. */
  let m = null;
  try {
    const r = await shadowPost("/api/shadow/chat",
                               { message: text, intake: true });
    /* the status is in the sentence the founder reads: a 503 is a Shadow
       that has not booted and a 403 is a stale token, and those are two
       different things to do about it */
    if (!r || !r.ok)
      throw new Error("Shadow could not answer ("
                      + ((r && r.status) || "no reply") + ").");
    const doc = await r.json();
    if (doc && doc.reply)
      c.thread.push({ who: "shadow", ts: Date.now(), text: String(doc.reply) });
    m = (doc && (doc.mission || (doc.missions || [])[0])) || null;
  } catch (e){
    m = null;
    c.err = String((e && e.message) || "Shadow could not answer.");
  }
  c.busy = false;
  if (!m){
    /* NO TASK IS THE ORDINARY OUTCOME NOW, not a failure: Shadow answered
       and there was no work in the line. The panel stays open so the
       conversation can continue -- the next line may well be the task. */
    S.shadowNewOpen = true;
  } else {
    /* a real ask: the task exists, put it in focus and let this chat go */
    if (typeof S !== "undefined"){
      if (!Array.isArray(S.shadowMissions)) S.shadowMissions = [];
      if (!S.shadowMissions.some(x => x && x.id === m.id))
        S.shadowMissions = S.shadowMissions.concat([m]);
      S.shadowTaskSel = m.id;
      S.shadowNewOpen = false;
    }
    S.shadowNewChat = null;
    if (typeof loadShadowHome === "function") loadShadowHome(true);
  }
  if (typeof scheduleRender === "function") scheduleRender();
  return m;
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

/* the recent-conversation chips ARE the picker: same data-shchat hook the
   dropdown list has always used, shown inline instead of behind a toggle.
   "+N more" opens the existing list rather than inventing a second one. */
const SH_CHIP_CAP = 4;
/* ── THE COMPOSER SAYS WHAT IT IS FOR RIGHT NOW (founder, 2026-09-21) ────
   "When RUNNING: Talk to Shadow... When NEEDS YOU: Reply or change the
   plan..." -- and the second half of that is the point. A founder looking at
   a Confirm button needs to know the box below it is not a form field for
   that question: they can answer it, ignore it, or change the task outright,
   and the placeholder is the only thing on screen that says so.

   IT IS A LABEL, NOT A MODE. Nothing about what the composer DOES changes
   with the state -- the same send path, the same task chat, the same
   `mission` fence that can amend a live task. Only the invitation changes. */
function shadowComposePlaceholder(compact){
  if (!compact) return "Tell Shadow what outcome you want\u2026";
  const S_ = (typeof S !== "undefined") ? S : {};
  const sel = (typeof shadowSelectedTask === "function")
    ? shadowSelectedTask() : null;
  if (sel && typeof shadowMissionNeedsFounder === "function"
      && shadowMissionNeedsFounder(sel)) {
    return "Reply, or change the plan\u2026";
  }
  if (sel && SH_TERMINAL.indexOf(sel.state) !== -1) {
    return "Ask Shadow about this, or start something new\u2026";
  }
  return "Talk to Shadow\u2026";
}


function shadowStageHtml(compact){
  const S_ = (typeof S !== "undefined") ? S : {};
  return `<section class="shstage${compact ? " shstage-calm" : ""}">
    ${compact ? "" : `<div class="shstagetop">
      <div class="shask">
        <div class="shasklabel">What should I take on?</div>
        <div class="shasktitle">Tell Shadow the outcome you want.</div>
        <div class="shasksub">Be specific or high level — Shadow will
          figure out the steps.</div>
      </div>
    </div>`}
    <div class="shcompwrap">
      ${/* THE DRAFT IS RENDERED, not merely carried (founder, 2026-09-18:
           "sometimes when you are typing in it, the focus from that field is
           going"). This box used to render EMPTY every time and keep what was
           typed only in the live DOM node -- so the half-written sentence
           existed in exactly one place, an element render() replaces, and it
           survived only if the focus snapshot happened to catch it. Every
           other typed field in this file already stores its draft in S and
           renders it back (shnewtalk, shbehaves, shmemory, shoffername,
           shquiet*); this one was the exception, which is why a repaint could
           empty it. Stored on input, NEVER re-rendered on keystroke -- a
           render per character would fight the caret, which is the bug those
           other text stores exist to avoid. */""}
      <textarea class="shcompose" data-shhomecompose="1"
        data-shscope="${escAttr(S_.shadowChat || "global")}"
        placeholder="${escAttr(shadowComposePlaceholder(compact))}">${
        esc(S_.shadowComposeDraft || "")}</textarea>
      <button class="shsend" type="button" data-shsend="1"
        title="Hand it over (or press Enter)" aria-label="Hand it over">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="2" aria-hidden="true"
          ><path d="M12 19V5M5 12l7-7 7 7"/></svg></button>
    </div>
    ${S_.shadowScopeErr
      ? `<div class="shnewerr">${esc(S_.shadowScopeErr)}</div>` : ""}
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
      <span>What Shadow knows</span></button>
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
    /* v4 C6: Shadow's words as prose, the founder's verbatim */
    if (typeof shadowMsgHtml === "function") return shadowMsgHtml(t);
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
  const face = sel ? shadowTaskFaceFor(sel) : null;
  return `<div class="shwork">
    <aside class="shwleft">
      <button class="shdelegate${newOpen ? " on" : ""}" type="button"
        data-shdelegate="1">+ Delegate</button>
      <div class="shtasks">${shadowTaskListHtml()}</div>
      <div class="shwfoot">${shadowNavHtml()}</div>
    </aside>
    <section class="shwright">${err}
      <header class="shwhead">
        ${/* THE SEAL IS GONE (founder, 2026-09-21, pass 4: "remove the S
             logo"). A circled monogram beside a title that already says
             Shadow is a brand mark on a surface that is meant to read as a
             conversation -- and the pane has exactly one voice, so nothing
             needs disambiguating. The header is now back-arrow, title,
             state, controls; .shwseal's rules leave panel.css with it. */""}
        <h2 class="shwtitle">${newOpen ? "New task"
          : esc((sel && sel.objective) || "Shadow")}</h2>
        <div class="shwheadacts">
          ${/* ── THE TURN COUNT IS BACKEND STATE (founder, 2026-09-21,
               pass 4) ─────────────────────────────────────────────────
             THIS REVERSES THE 2026-09-20 RULING that pinned `2/25` to this
             line, and says so rather than quietly differing from it. That
             ruling was right about WHERE a live count belongs (the header,
             which never scrolls) and this direction changes WHETHER the
             founder should be reading a worker turn count at all: "the user
             should never have to understand how many worker turns occurred",
             and worker turn number is named as state that stays in the
             backend. A budget the founder cannot act on, ticking beside the
             status, is the worker pipeline showing through.

             shadowHeadTurnHtml IS NOT DELETED -- it is still exported and
             still the honest render of turns_used/max_turns for any surface
             that wants it (the corner card, the watching plane). The task
             header stopped being one of them. The RUNNING pill still says
             the task is alive, and the activity row in the stream still
             says how long the current turn has been going. */""}
          ${!newOpen && face ? shadowTaskPillHtml(face) : ""}
          ${/* THE WORKER CHAT LIVES BEHIND THIS BUTTON AND NOWHERE ELSE.
               Same data-shtakeover hook and same target_session it has
               always carried -- it simply sits where the reference puts
               it, so the split between "Shadow's report" (this pane) and
               "the delegate's actual chat" (that button) is the first
               thing the header says. */""}
          ${/* ONE DOOR HERE, AND IT IS THE WORKER'S. The floating "Talk to
               Shadow" panel that sat beside this button is gone (founder,
               2026-09-17): the founder's conversation with Shadow is the
               workspace composer and the stream below it, not a second
               surface to open. Same hook, same target_session, unchanged. */""}
          ${/* ── REPLAY, ON A TASK THAT HAS STOPPED (founder, 2026-09-21,
                 pass 2: "DONE [Replay] [Open the chat] / STOPPED [Replay]
                 [Open the chat]").

                 THIS REVERSES A SAME-DAY RULING, and says so rather than
                 quietly differing from it. shadowPlaneHtml still carries
                 the note "v4.2 (founder 2026-09-21): no Retry button. The
                 retry action stays on the server; the way back is the
                 task's chat or Hand back to Shadow." That was about the
                 finished-task ROWS on the Watching plane, where five of
                 them stacked their own buttons; pass 2 asks for one control
                 on the HEADER of the task you are reading. Both can be
                 true, and the plane's rows are untouched.

                 NOTHING NEW ON THE SERVER. `retry` is the existing action
                 (app.py -> mission_engine.clone_for_retry), which rebuilds
                 the mission from its ORIGINAL brief as a new attempt. It is
                 labelled Replay because that is what it does to the founder:
                 run this again. The old mission is not mutated. */""}
          ${/* DONE AND STOPPED ONLY, which is exactly the two states pass 2
               names. A FAILED task is deliberately excluded: the v4.2
               ruling above is still live for it (test_shadow_home pins
               "no Retry button" on a selected failure), and a failure is
               the one ending where re-running the same brief unchanged is
               usually the wrong move -- the way back there is the task's
               chat or Hand back to Shadow, as that ruling says. */""}
          ${/* ── STOP BELONGS WITH THE OTHER HEADER CONTROLS (founder,
                 2026-09-21, pass 2: "RUNNING [Stop] [Open the chat]").
                 It was drawn inside the task card's action row, which is
                 the first block of the SCROLLER -- so on a long task it
                 left the screen and the founder could not end work without
                 scrolling back. The header is pinned; the controls that
                 change the task's state belong on it.

                 SAME HOOK, SAME PREDICATE. data-shact="stop" and the
                 needs-founder guard from pass 1 are unchanged; only where
                 the button is drawn moved. The card's row keeps Resume,
                 Approve and Hand back, which are answers to what the card
                 is showing rather than controls over the run. */""}
          ${/* THE TASK'S OWN CONTROLS, ON THE PINNED HEADER (founder,
               2026-09-21, pass 3). Start, Drop and Hand back used to sit in
               the metadata card's action row; that card has left the main
               surface, and these are controls rather than things Shadow
               says, so the header is where they belong. Same hooks, same
               predicates, same handlers -- only the site moved. */""}
          ${!newOpen && sel && (typeof shadowMissionStartable === "function"
              ? shadowMissionStartable(sel) : sel.state === "brief_confirm")
            ? `<button class="btn pri" type="button"
                data-shstart="${escAttr(sel.id)}">Start the task</button>
               <span class="shcard2hint shwhint">\u2026or keep telling me</span>`
            : ""}
          ${!newOpen && sel && sel.state === "queued"
            ? `<button class="btn" type="button" data-shact="drop"
                data-shmid="${escAttr(sel.id)}">Drop</button>` : ""}
          ${!newOpen && sel && !shadowMissionNeedsFounder(sel)
            && ["running", "paused", "blocked"].includes(sel.state)
            ? `<button class="btn" type="button" data-shact="stop"
                data-shmid="${escAttr(sel.id)}">Stop</button>` : ""}
          ${!newOpen && sel && ["done", "stopped"].includes(sel.state)
            ? `<button class="btn" type="button" data-shact="retry"
                data-shmid="${escAttr(sel.id)}">Replay</button>` : ""}
          ${/* HAND BACK: done is not a dead end. Same hook and same
               condition it had on the card -- Shadow returns to work in the
               SAME chat, where Replay starts a fresh attempt. */""}
          ${!newOpen && sel && ["done", "failed", "stopped"].includes(sel.state)
            && sel.target_session
            ? `<button class="btn" type="button" data-shact="reopen"
                data-shmid="${escAttr(sel.id)}">Hand back to Shadow</button>` : ""}
          ${!newOpen && sel && sel.target_session ? `<button class="btn"
            type="button" data-shtakeover="${escAttr(sel.target_session)}"
            >Open the chat</button>` : ""}
        </div>
      </header>
      ${newOpen ? (shadowFormOn() ? shadowDelegatePanelHtml()
                                  : `<div class="shnewhost"
                                       data-shnewhost="1"></div>`)
                : ""}
      ${/* THE BRIEF IS NO LONGER PINNED HERE -- it is the first message of
           the conversation, inside the scroller below (founder, 2026-09-20:
           "way too complicated with many scroll bars ... make it like a long
           interactive chat"). See the block above .shwscroll. */""}
      ${/* ── ONE SCROLLER, AND IT IS THE CONVERSATION (founder, 2026-09-18)
           THE PROBLEM. `.pb` (#scBody) scrolls the whole screen, so reading
           back through a long delegation carried the objective and the brief
           card off the top with it -- the two things that say WHAT is being
           worked and HOW it is judged were the first to leave. On a
           twenty-turn task the founder was scrolling a wall of turns with no
           header to anchor them.

           SO THE PANE OWNS ITS OWN HEIGHT. `.shwork` is now exactly the
           pane's height rather than `min-height:100%`, which takes the
           scroll away from `.pb` without touching `.pb` -- it is shared by
           every other screen and none of them change.

           THE HEAD AND THE CARD ARE PINNED. The conversation -- worker
           turns, Shadow's replies, the founder's own lines, an intervention
           form, a pending-memory row -- scrolls inside this element.

           THE COMPOSER IS PINNED TOO, and that is a decision, not an
           oversight: it is the founder's half of the conversation, so by the
           letter it belongs in the scroller. But a composer that scrolls
           away has to be hunted for before you can type, which is the
           opposite of what pinning the header was for. It sits below this
           block, outside it, always reachable. */""}
      <div class="shwscroll"${sel && !newOpen
        ? ` data-shscroll="${escAttr(sel.id)}"` : ""}>
      ${/* ── MESSAGE ZERO (founder, 2026-09-20) ──────────────────────────
           THE REPORT: "way too complicated with many scroll bars ... let's
           make it like a long interactive chat".

           WHAT WAS COMPLICATED. Five regions of this pane declared their own
           overflow -- the task list, the brief card, the conversation, a turn
           log and the done summary -- and up to four could be on screen at
           once. Every one of them was a correct local fix; their SUM is that
           nothing tells you which box your wheel is about to move.

           THE BRIEF WAS ALREADY A MESSAGE. "here is the task, here is where
           it runs, here is what done means" is the opening line of the
           conversation, and it was drawn as a pinned form above it with a
           32% cap and a scrollbar of its own -- so on a short pane the
           founder scrolled a brief inside a pane inside a screen.

           IT IS THE FIRST ROW OF THE THREAD NOW. It scrolls with everything
           else and it clips nothing, so the Confirm buttons the cap existed
           to keep reachable are simply always at their full height.

           WHAT STAYS PINNED IS THE HEADER, which is what the 2026-09-18
           change was actually protecting: the objective, the state and --
           new, below -- the live turn count never leave the screen, so
           reading back through twenty turns still has its anchor. */""}
      ${/* ── THE STREAM IS THE SURFACE (founder, 2026-09-21, pass 3) ─────
           The card, the superseded revisions, the decision and the
           completion used to be drawn HERE, as four siblings around the
           timeline. They are now messages inside it -- see the long note at
           the top of shadowTimelineHtml -- so this is one call, and the
           main content area is one continuous conversation rather than a
           stack of panels.

           WHAT IS STILL A SIBLING, and why each has to be: the pending
           MEMORY rows are global to Shadow rather than to this task; the
           intervention FORM is an input, not a message, and answers a
           question the stream has already shown; and the composer is the
           bottom of the conversation, not part of it. Nothing else. */""}
      ${newOpen || !sel ? "" : shadowTimelineHtml(sel)}
      ${/* WHAT IT CAME TO, AT THE END OF WHAT HAPPENED (founder,
           2026-09-20). These two used to render inside the task card above,
           which is the FIRST row of this scroller -- so the sign-off and
           the done summary sat above every turn of the conversation and the
           founder scrolled back through the whole task to reach them. Here
           they are the last rows before the composer, which is where the
           pane already opens. See the note at their old site in
           shadowTaskCardHtml; the predicates are unchanged. */""}
      ${/* the founder's answer is INSIDE the timeline now, at the point it
           happened -- drawing it here as well would be the same card twice */""}
      ${thread ? `<div class="shthread">${thread}</div>` : ""}
      ${newOpen ? "" : shadowPendingMemoryHtml()}
      </div>
      ${/* ── THE QUESTION IS PINNED, THE CONVERSATION SCROLLS (founder,
           2026-09-18) ───────────────────────────────────────
           NEEDS YOU is the one state that needs TWO things on screen at once:
           the question, and the turns that earned it. Inside the scroller they
           competed for the same pixels -- and the form won every time, because
           the pane opens at the NEWEST row and on a blocked mission that IS
           the form. Measured in Chrome, six turns and a four-line conversation
           on the record, the scroller opened at its newest row:

               window   turn rows visible   conversation lines visible
               660px           0                       0
               900px           0                       1

           So the founder, looking at the section that exists to show what the
           delegate did, saw no turn at all -- which is the report this fixes.

           PINNED BELOW THE SCROLLER it is always on screen without taking the
           conversation’s height with it, and it sits directly above the
           composer, next to the other place the founder types. Same markup,
           same data-shivform hook, same handlers, same submit -- only its
           parent changed.

           IT YIELDS BEFORE THE CONVERSATION DOES. .shwright>.shiv caps its
           share of the pane and scrolls itself, so a long form can never do to
           the turns what the brief card did (see panel.css).

           NO OTHER STATE MOVES: shadowInterventionHtml returns "" unless the
           mission is carrying a question, so every running, done, failed and
           stopped mission renders exactly the markup it did before. */""}
      ${newOpen || !sel ? "" : shadowInterventionHtml(sel)}
      ${/* THE ASK BLOCK IS THE NEW-TASK COMPOSER (founder, 2026-09-15).
           "What should I take on? / Tell Shadow the outcome you want" is
           how a task is CREATED, and it was drawing under the workspace as
           a second composer below the task. The workspace gets "Say
           anything…" and nothing else; + Delegate opens the New Task panel,
           where that copy still belongs and is untouched.

           ...AND THE PANEL IS THE ONLY ONE ASKING (founder, 2026-09-15, same
           day, second pass). With the panel OPEN this drew the ask block and
           a SECOND outcome box directly under a form whose first field is
           already "The outcome you want" -- two places to type the same
           sentence, one of which creates nothing. The panel is self-contained
           (its own heading, data-shnewobj, done-when, kinds, Create/Cancel),
           so the stage is simply not rendered behind it.

           CLOSED IS BYTE-IDENTICAL: shadowStageHtml(true) is exactly what
           shadowStageHtml(!newOpen) evaluated to whenever newOpen was false,
           which is every render that is not the New Task form. Nothing else
           moves -- no hook renamed, no copy edited, no handler touched, and
           every composer consumer already guards on absence
           (shadowSubmitCompose's `if (!el) return`, render's `if (el)`
           caret restore, and the Enter listener, which needs the element
           itself). */""}
      ${newOpen ? "" : shadowStageHtml(true)}
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
    /* the durable presence choice rides this payload; seeding it here keeps
       the settings switch and the overlay reading one value, not two */
    if (s && typeof applyShadowPresence === "function") applyShadowPresence(s);
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
    /* same seeding as the home read: one value behind the switch and the dot */
    if (S.shadowSettings && typeof applyShadowPresence === "function")
      applyShadowPresence(S.shadowSettings);
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

   IT ALL WRITES NOW. This section used to be drawn inert on purpose, with a
   comment explaining that the level and the toggle "have no field, no
   endpoint and no writer anywhere in this build" and that nothing here would
   "pretend to remember a choice it cannot keep". The store landed
   (mission_engine's autonomy section, /api/shadow/settings/autonomy), so the
   controls carry their hooks and that comment is gone, exactly as it said it
   would be.

   THE LEVEL IS READ BACK, NEVER ASSUMED. There was a `SH_LEVEL_NOW = "L3"`
   constant here standing in for the setting; it is deleted rather than
   defaulted, because a client-side default is how a page ends up showing L3
   while the server runs L0. `d.autonomy.level` is the only source, and when
   the block is missing the section says so instead of guessing.

   WHAT EACH LEVEL DOES IS STATED, not implied by its name. "Draft" does not
   tell a founder that the worker is capped at plan; the sub-line does, and
   it quotes `worker_mode` from the server so the sentence on screen is the
   mode the next spawn will really use.

   THE FLOORS ARE UNCHANGED and still not editable here: they are rank 1 in
   SHADOW.md's precedence and no level, L3 included, can lower them. The note
   now says that in terms of the levels, since a founder who has just been
   given an Act button is exactly the person who needs to know what it does
   not buy. */
const SH_LEVELS = [["L0", "Watch"], ["L1", "Suggest"],
                   ["L2", "Draft"], ["L3", "Act"]];

/* What each level actually does, in the founder's terms. Kept beside the
   names so the two cannot drift apart. */
const SH_LEVEL_WHAT = {
  L0: "Shadow watches and never speaks. Running tasks pause.",
  L1: "Shadow asks before every instruction it sends.",
  L2: "Shadow works, but its tasks can only read and plan \u2014 nothing is changed.",
  L3: "Shadow works and its tasks can change things, at your permission level.",
};

function shadowSetAutonomyHtml(d){
  const a = (d && d.autonomy) || null;
  const floors = (d.floors || []).filter(Boolean);
  const floorRow = `<div class="srow">${floors.length
      ? `<span class="floorbar">${floors.map(f => `<span><span class="lk"
          aria-hidden="true">\ud83d\udd12</span>${esc(f)}</span>`).join("")}</span>`
      : `<span class="ssempty">No floors were reported.</span>`}</div>
    <p class="ssnote">Floors are confirm-first at every level, Act included
      \u2014 Shadow cannot be talked out of them, and they are not editable
      here.</p>`;
  /* NO LEVEL RATHER THAN A GUESSED ONE. An older server, or a settings read
     that failed, must not be drawn as L3: that is the exact lie the inert
     selector was written to avoid, just arriving by a different road. */
  if (!a || !a.level)
    return `<div class="ssempty">The autonomy level was not reported.</div>`
      + floorRow;
  const busy = (typeof S !== "undefined" && S.shadowAutonomyBusy) || false;
  const seg = SH_LEVELS.map(([lv, name]) => {
    const on = lv === a.level;
    /* the SELECTED level carries no hook: clicking it would post the value
       it already has, and a control that spends a round-trip to change
       nothing reads as broken the moment the network is slow */
    const hook = (on || busy) ? "" : ` data-shautonomy="${escAttr(lv)}"`;
    return `<button type="button" role="tab"${on ? ' class="on"' : ""}
      aria-selected="${on}"${hook}${busy && !on
        ? ' aria-disabled="true" tabindex="-1" title="Saving\u2026"'
        : ""}><span class="lv">${esc(lv)}</span>${esc(name)}</button>`;
  }).join("");
  const top = !!a.confirm_top_tier;
  /* THE SWITCH ONLY BITES AT L3, AND SAYS SO. It is still writable at every
     level -- a founder setting up L1 today may well be arranging what
     happens when they move to Act later, and refusing the click would lose
     that -- but drawing it as live while it governs nothing would be the
     same pretence this section just stopped making. */
  const topNote = a.level === "L3"
    ? "Shadow asks once per task before it first acts."
    : "Applies at Act. Nothing to ask about at " + esc(a.level) + ".";
  const what = SH_LEVEL_WHAT[a.level] || "";
  /* the CONSEQUENCE, from the server's own resolver rather than inferred
     from the level here -- if a ceiling ever changes, this line changes with
     it instead of quietly becoming wrong */
  const mode = a.worker_mode
    ? `<p class="ssnote">Tasks run at <code>${esc(a.worker_mode)}</code>${
        a.worker_may_write ? "" : " \u2014 read-only"}.</p>`
    : "";
  return `<div class="seg" role="tablist" aria-label="Autonomy level">${seg}</div>
    <p class="ssnote">${esc(what)}</p>${mode}
    <div class="srow"><span class="k">Ask me before the very top tier</span>
      <span class="tog${top ? "" : " off"}" role="switch" aria-checked="${top}"${busy
          ? ' aria-disabled="true" title="Saving\u2026"'
          : ` data-shtoptier="${top ? "0" : "1"}" tabindex="0"`}></span></div>
    <p class="ssnote">${topNote}</p>
    ${floorRow}`;
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

/* HOW SHADOW BEHAVES (v4 C7, ADR-043): the founder's own words, one text,
   first on the sheet. Saved on change (the blur after an edit), through
   POST /api/shadow/settings/behaves, into the same limits store the numbers
   below use; it binds the next Shadow boot. The draft is kept on S across
   the background re-renders, like every other typed field here. */
function shadowSetBehavesHtml(d){
  const S_ = (typeof S !== "undefined") ? S : {};
  const text = (S_.shadowBehavesDraft != null) ? S_.shadowBehavesDraft
                                                : ((d && d.behaves) || "");
  const note = S_.shadowBehavesBusy ? "saving"
    : (S_.shadowBehavesErr ? S_.shadowBehavesErr
    : (S_.shadowBehavesSaved ? "saved" : ""));
  const max = Number(d && d.behaves_max) || 4000;
  return `<div class="ssbehaves">
    <textarea class="ssbehaves-text" rows="5" data-shbehaves="1" maxlength="${max}"
      placeholder="In your own words: when to check in, what to ask before doing, what to leave alone.">${esc(text)}</textarea>
    <div class="ssnote ssbehaves-note">${esc(note)}</div>
  </div>`;
}

async function shadowBehavesSave(text){
  if (typeof fetch === "undefined" || typeof S === "undefined") return null;
  S.shadowBehavesBusy = true; S.shadowBehavesErr = null; S.shadowBehavesSaved = false;
  if (typeof scheduleRender === "function") scheduleRender();
  let r = null;
  try {
    r = await shadowPost("/api/shadow/settings/behaves",
                         { behaves: String(text == null ? "" : text) });
  } catch (e){ r = null; }
  let body = null;
  try { body = (r && r.ok) ? await r.json() : null; } catch (e){ body = null; }
  S.shadowBehavesBusy = false;
  if (body && body.behaves !== undefined){
    if (S.shadowSettings) S.shadowSettings.behaves = body.behaves;
    S.shadowBehavesDraft = null;
    S.shadowBehavesSaved = true;
  } else {
    S.shadowBehavesErr = "That did not stick — try again.";
  }
  if (typeof scheduleRender === "function") scheduleRender();
  return body;
}

/* THE FOUNDER'S OWN MEMORY TEXT, and the twin of shadowSetBehavesHtml in
   every respect: same textarea, same save-on-change, same note line.

   NOT THE LEARNED-RULE LIST. shadowSetMemoryHtml below still renders
   `global` / `per_chat` -- what Shadow learned and the founder CONFIRMED,
   append-only, each row carrying its own provenance. This box is what the
   founder simply wants remembered, typed directly. Two questions, two
   stores; typing here cannot rewrite a rule Shadow was told it had learned.
   The list is no longer on this page, and the record is untouched. */
function shadowSetMemoryTextHtml(d){
  const S_ = (typeof S !== "undefined") ? S : {};
  const text = (S_.shadowMemoryDraft != null) ? S_.shadowMemoryDraft
                                              : ((d && d.memory) || "");
  const note = S_.shadowMemoryBusy ? "saving"
    : (S_.shadowMemoryErr ? S_.shadowMemoryErr
    : (S_.shadowMemorySaved ? "saved" : ""));
  const max = Number(d && d.memory_max) || 4000;
  return `<div class="ssbehaves">
    <textarea class="ssbehaves-text" rows="5" data-shmemory="1" maxlength="${max}"
      placeholder="What Shadow should carry into every task: who you are, what matters, what to never forget.">${esc(text)}</textarea>
    <div class="ssnote ssbehaves-note">${esc(note)}</div>
  </div>`;
}

async function shadowMemorySave(text){
  if (typeof fetch === "undefined" || typeof S === "undefined") return null;
  S.shadowMemoryBusy = true; S.shadowMemoryErr = null; S.shadowMemorySaved = false;
  if (typeof scheduleRender === "function") scheduleRender();
  let r = null;
  try {
    r = await shadowPost("/api/shadow/settings/memory",
                         { memory: String(text == null ? "" : text) });
  } catch (e){ r = null; }
  let body = null;
  try { body = (r && r.ok) ? await r.json() : null; } catch (e){ body = null; }
  S.shadowMemoryBusy = false;
  if (body && body.memory !== undefined){
    if (S.shadowSettings) S.shadowSettings.memory = body.memory;
    S.shadowMemoryDraft = null;
    S.shadowMemorySaved = true;
  } else {
    S.shadowMemoryErr = "That did not stick \u2014 try again.";
  }
  if (typeof scheduleRender === "function") scheduleRender();
  return body;
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

   THE TWO NUMBERS ARE REAL. running_at_once is the cap MissionScheduler
   actually enforces before it queues -- and the budget is what
   MissionStore.create stamps onto a new mission as max_turns, which is what
   fails it when spent. Both ride the settings endpoint that was already
   being read, so this page states the limits the engine keeps rather than a
   number that merely looks right.

   BOTH STEPPERS WRITE NOW. Running at once POSTs /api/shadow/settings/tasks,
   the budget POSTs /api/shadow/settings/budget -- one route per field, which
   is why there are two. Each is the same store the engine reads, so - and +
   move what the engine enforces rather than a display copy of it. The clamp
   is the SERVER's in both cases (min/max come back from the endpoint); the
   buttons are only disabled at the ends so a founder is not invited to click
   into a refusal.

   AUTO IS STILL TRUE, JUST NO LONGER THE ONLY TRUTH. The budget is chosen by
   the kind of work; that was right and has not changed. What is new is that
   the founder may override the number a kind supplies. So the pill is a
   STATE, not a label: `auto` while the kind carries no override, `set by you`
   once it does -- read from the server's turn_budget_set, never inferred by
   comparing the value to the default, because setting a budget to exactly its
   default is a real choice and comparing would redraw it as untouched.

   THE ROW PICKS ITS OWN KIND. It used to quote shadowNewDraft().kind -- the
   kind a draft on a DIFFERENT screen happened to be on. That is harmless for
   a number you can only read and dangerous for one you can move: a founder
   would set `fix` believing they had set everything. The picker makes the
   target explicit, and the Delegate-offers chips below stay the four-kind
   summary of what the row edits one at a time.

   WATCH IS NOT SETTABLE and the row says why rather than hiding it. Its
   budget is never consumed -- never_say returns before the budget is ever
   compared -- so a control there would look kept and never bind. Which kinds
   are settable comes from the server (turn_budget_kinds), not a list here.

   EVERY CONTROL ON THIS SECTION NOW WRITES. The chips' x and "+ add" were
   the last two that did not, drawn because the reference drew them and inert
   because there was nowhere to keep a delegate kind. There is now
   (mission_engine, delegate offers), so they carry hooks like everything
   else here. Autonomy still follows the old rule; this section no longer
   has anything to apply it to.

   WHAT THE SUB-LINES ARE FOR. Lowering the cap does not stop work already
   underway -- the server says so and refuses to pretend otherwise -- so
   when more are running than the cap allows, the row says which, rather
   than leaving the founder to read "3" beside five live tasks and conclude
   the setting is broken. The budget has the same problem for the same reason
   and gets the same treatment: max_turns is stamped at create(), so a change
   binds the next task and never re-budgets one already running. */
function shadowSetTasksHtml(d){
  const t = (d && d.tasks) || {};
  const run = t.running_at_once;
  const budgets = t.turn_budget || {};
  /* the kind this row EDITS. Seeded from the kind Delegate opens on, so the
     first read is the same number it always quoted, but the founder can
     point it elsewhere -- and once it can be moved, the target has to be
     visible rather than inherited from another screen's draft state. */
  /* THE CURSOR CANNOT OUTLIVE THE KIND IT POINTS AT (observed, 2026-09-16).
     S.shadowBudgetKind survives a removal, and the picker only draws OFFERED
     kinds -- so selecting `research`, then removing it, left no pill lit
     while the steppers still carried data-shbudgetkind="research". The row
     would have gone on budgeting a kind the founder had just retired, with
     nothing on screen saying which kind it was editing. Same coercion
     shadowNewDraft() does for the delegate draft, and for the same reason. */
  const offered = shadowOfferKinds();
  const want = (typeof S !== "undefined" && S.shadowBudgetKind)
    || (shadowNewDraft().kind) || offered[0];
  const kind = (offered.indexOf(want) > -1) ? want : offered[0];
  const turns = budgets[kind];
  const lo = (typeof t.running_at_once_min === "number")
    ? t.running_at_once_min : 1;
  const hi = (typeof t.running_at_once_max === "number")
    ? t.running_at_once_max : 20;
  const busy = (typeof S !== "undefined" && S.shadowRunLimitBusy) || false;
  /* an end-stop says so instead of clicking into a no-op; `busy` holds both
     ends down for the one round-trip, so a double-click cannot send two */
  const end = (atEnd) => (atEnd || busy)
    ? ` aria-disabled="true" tabindex="-1" title="${escAttr(
        busy ? "Saving\u2026" : (atEnd === "lo"
          ? "At least " + lo + " task runs at a time"
          : "At most " + hi + " tasks run at once"))}"`
    : "";
  const stepper = run === undefined
    ? `<span class="ssempty">not reported</span>`
    : `<span class="step"><button type="button"${end(run <= lo && "lo")
        } data-shrunlimit="${escAttr(String(Math.max(lo, run - 1)))}"
        aria-label="fewer">\u2212</button><span class="val">${
        esc(String(run))}</span><button type="button"${end(run >= hi && "hi")
        } data-shrunlimit="${escAttr(String(Math.min(hi, run + 1)))}"
        aria-label="more">+</button></span>`;
  const over = (typeof t.running_now === "number" && run !== undefined
                && t.running_now > run) ? t.running_now - run : 0;
  const note = over
    ? `<div class="srow ssnote">${esc(String(t.running_now))} are still
        running \u2014 the new limit holds the next ${esc(String(over))
        } back, it does not stop work already underway.</div>`
    : (t.queued_now
        ? `<div class="srow ssnote">${esc(String(t.queued_now))} waiting for a
            free slot.</div>`
        : "");
  /* THE BUDGET STEPPER. Same three rules the cap stepper keeps -- the button
     carries its already-clamped DESTINATION so a repeated click cannot
     compound off one render, the band is the server's, and `busy` holds both
     ends down for the round-trip. The step is 5, not 1: the band is 1-100, so
     a founder moving 20 to 60 would otherwise be clicking forty times. */
  const BSTEP = 5;
  const blo = (typeof t.turn_budget_min === "number") ? t.turn_budget_min : 1;
  const bhi = (typeof t.turn_budget_max === "number") ? t.turn_budget_max : 100;
  /* which kinds may be set at all is the SERVER's answer, not a list here --
     it derives it from the never_say invariant */
  const bkinds = t.turn_budget_kinds
    || shadowOfferKinds().filter(k => budgets[k] !== 0);
  const bset = t.turn_budget_set || [];
  const settable = bkinds.indexOf(kind) > -1;
  const bbusy = (typeof S !== "undefined" && S.shadowBudgetBusy) || false;
  const bend = (atEnd) => (atEnd || bbusy)
    ? ` aria-disabled="true" tabindex="-1" title="${escAttr(
        bbusy ? "Saving…" : (atEnd === "lo"
          ? "A task gets at least " + blo + " turn"
          : "At most " + bhi + " turns for one task"))}"`
    : "";
  /* the picker: which kind the stepper moves. Memory-only, like the overlay's
     hide/quiet flags -- it selects a target, it does not store a preference */
  const picker = `<span class="seg segmini" role="group"
      aria-label="which kind of task">${shadowOfferKinds().map(k =>
      `<button type="button" class="segb${k === kind ? " on" : ""}"
        data-shbudgetkind="${escAttr(k)}"${k === kind
          ? ' aria-pressed="true"' : ''}>${esc(k)}</button>`).join("")}</span>`;
  const bstepper = !settable
    ? `<span><span class="ev">${esc(String(turns))}</span> turns
        <span class="auto" title="a watch task never speaks, so it never
          spends a turn — there is no budget to set"
          >not spent</span></span>`
    : `<span class="step"><button type="button"${bend(turns <= blo && "lo")
        } data-shbudgetkind="${escAttr(kind)}" data-shbudget="${escAttr(
        String(Math.max(blo, turns - BSTEP)))}"
        aria-label="smaller budget">−</button><span class="val">${
        esc(String(turns))}</span><button type="button"${
        bend(turns >= bhi && "hi")} data-shbudgetkind="${escAttr(kind)
        }" data-shbudget="${escAttr(String(Math.min(bhi, turns + BSTEP)))}"
        aria-label="bigger budget">+</button></span>
      <span>turns</span>${bset.indexOf(kind) > -1
        ? `<button type="button" class="auto set"${bbusy
            ? ' aria-disabled="true" tabindex="-1"' : ''
          } data-shbudgetkind="${escAttr(kind)}" data-shbudget="auto"
          title="you set this — click to go back to auto"
          >set by you</button>`
        : `<span class="auto" title="the kind of work chose this"
            >auto</span>`}`;
  const budget = turns === undefined
    ? `<span class="ssempty">not reported</span>`
    : `${picker} ${bstepper}`;
  /* THE LABEL NAMES THE KIND IT WRITES. "Budget per task" was a lie: this
     control is per KIND, for whichever kind the picker is on, and a label
     that claims otherwise makes a founder who sets `feature` to 50 read a
     `fix` task running to 20 as the setting silently failing. It reads the
     SAME `kind` variable every write-hook on this row carries, so the label
     cannot drift from what the stepper actually moves. */
  const blabel = `Budget per task${turns === undefined ? ""
    : ` <span class="kdim">· ${esc(kind)}</span>`}`;
  /* EVERY KIND, AT A GLANCE. The stepper edits one kind at a time, so without
     this the founder can only see the number for whichever kind the picker is
     on and has to click through all of them to learn what the rest run at.
     `on` comes from the SERVER's turn_budget_set, never from comparing a
     value to its default -- setting a budget to exactly its default is a real
     choice, and comparing would redraw it as untouched and take the reset
     control away. No new storage and no new key: both fields are already on
     the wire and already read by this function. */
  const readout = turns === undefined ? "" :
    `<div class="srow budall">${shadowOfferKinds().map(k => {
      const v = budgets[k];
      const on = bset.indexOf(k) > -1;
      return `<span class="budk${on ? " on" : ""}" title="${escAttr(on
          ? "you set this" : "falling through to the template default")}"
        >${esc(k)} <b>${v === undefined ? "—" : esc(String(v))}</b></span>`;
    }).join("")}<span class="budlg">accented = you set it</span></div>`;
  /* the budget's own honesty line, mirroring the cap's above: a new budget
     cannot reach a task that is already running, because max_turns was
     stamped onto it when it was created */
  const bnote = (settable && turns !== undefined
                 && typeof t.running_now === "number" && t.running_now)
    ? `<div class="srow ssnote">${esc(String(t.running_now))} already running
        keep the budget they started with — this sets the next one.</div>`
    : "";
  return `<div class="srow"><span class="k">Running at once</span>${stepper}</div>
    ${note}
    <div class="srow"><span class="k">${blabel}</span>${budget}</div>
    ${readout}
    ${bnote}`;
}

/* DELEGATE OFFERS -- the kinds Shadow may be asked to start.

   ITS OWN SECTION, NOT A THIRD ROW UNDER TASKS (founder, 2026-09-16). It
   shipped as a row directly beneath "Budget per task", and that row already
   carries a segmented picker listing every kind -- fix, feature, research,
   watch, and now whatever the founder has added, because the picker reads
   the same offers list. Two pill rows of identical names, stacked, one
   label apart: the founder read the BUDGET PICKER as the offers control and
   reported the chips as rendering in the wrong place. They were not in the
   wrong container; they were indistinguishable from the control above them.

   A heading and a section rule are what separate two lists that look alike.
   The sub-line then says which is which, because "these are the kinds" and
   "this picks a kind to budget" is exactly the confusion that was reported
   and a heading alone does not answer it.

   THE CHIPS WRITE NOW, and they are the list the engine actually reads: the
   same offers the mission fence gates on, the Delegate form presents, and
   Shadow's boot context names. What used to be four names typed into four
   files is one setting with one store behind it.

   THE X CARRIES THE NAME, NOT AN INDEX. A removal posts the kind, so a
   render that landed between the click and the write cannot shift what gets
   removed -- the same reason the steppers carry their destination value.

   THE FLOOR IS THE SERVER'S. The last chip's x is held down rather than
   hidden: a founder who has narrowed to one kind should see why they cannot
   go further, not watch the control vanish. The server refuses it anyway
   (offers_min), so this is a courtesy, not the guard.

   ADD IS A TWO-STEP GESTURE. "+ add" opens an input rather than posting
   something; there is no name to send until one is typed. It is memory-only
   state (S.shadowOfferAdding), like the budget picker's target -- an
   unsubmitted box is not a preference worth keeping.

   REMOVING NEVER TOUCHES WORK ALREADY DONE. A task keeps the kind it was
   created with, and Retry still rebuilds a retired kind, because the store
   un-offers without un-defining. The row does not say so: it would be
   explaining a bug the founder cannot hit. */
function shadowSetOffersHtml(t){
  const S_ = (typeof S !== "undefined") ? S : {};
  const offers = t.offers;
  if (!Array.isArray(offers) || !offers.length)
    return [`<span class="ssempty">not reported</span>`, ""];
  const budgets = t.turn_budget || {};
  const busy = !!S_.shadowOfferBusy;
  const floor = (typeof t.offers_min === "number") ? t.offers_min : 1;
  const ceil = (typeof t.offers_max === "number") ? t.offers_max : 12;
  const atFloor = offers.length <= floor;
  const full = offers.length >= ceil;
  const chips = offers.map(k => {
    const off = busy || atFloor;
    const why = busy ? "Saving\u2026"
      : (atFloor ? "Shadow needs at least " + floor
                   + " kind of work to offer"
                 : "Stop offering " + k);
    /* the x's tag is written unbroken on purpose: the settings assertions
       match `<button class="cx"` as one string, and a line wrap between the
       tag and its first attribute would silently fail every one of them */
    const x = `<button class="cx" type="button"${off
      ? ' aria-disabled="true" tabindex="-1"'
      : ` data-shofferdel="${escAttr(k)}"`} title="${escAttr(why)
      }" aria-label="${escAttr("Remove " + k)}">\u00d7</button>`;
    return `<span class="chip"${budgets[k] === undefined ? ""
      : ` title="${escAttr(budgets[k] + " turns")}"`}>${esc(k)}${x}</span>`;
  }).join("");
  /* the input replaces the pill while it is open -- two controls for one
     gesture would leave the founder wondering which one adds */
  const add = S_.shadowOfferAdding
    ? `<span class="chipin"><input type="text" data-shoffername="1"
        value="${escAttr(S_.shadowOfferDraft || "")}" maxlength="24"
        placeholder="review" aria-label="name the kind of work"
        autofocus><button type="button" class="go"${busy
          ? ' aria-disabled="true" tabindex="-1"' : ' data-shofferadd="1"'
        } aria-label="add">\u2192</button></span>`
    : `<button class="chipadd" type="button"${(busy || full)
        ? ` aria-disabled="true" tabindex="-1" title="${escAttr(busy
            ? "Saving\u2026" : "At most " + ceil + " kinds on offer")}"`
        : ' data-shofferopen="1"'}>+ add</button>`;
  const note = S_.shadowOfferErr
    ? `<div class="srow ssnote">${esc(S_.shadowOfferErr)}</div>` : "";
  return [`<span class="chips">${chips}${add}</span>`, note];
}

/* The section body: what these are, then the chips themselves.

   The sub-line leads rather than trails. It is the line that tells the
   founder this row DECIDES WHICH KINDS EXIST, as against the picker one
   section up that merely chooses which of them to budget -- and a
   disambiguation placed under the thing it disambiguates is read second,
   which is too late. */
function shadowSetOffersSecHtml(d){
  const t = (d && d.tasks) || {};
  const [chips, note] = shadowSetOffersHtml(t);
  return `<div class="ssnote" style="margin:0 0 10px">The kinds of work you
      can hand Shadow. Removing one stops it being offered; tasks already
      created keep the kind they started with.</div>
    <div class="srow">${chips}</div>
    ${note}`;
}

/* PRESENCE, to the design of record's .ssec "Presence", then the
   "Add a control" bar below it.

   TWO OF THESE ARE REAL, and they are real in different ways.

   CORNER CARD IS NOW DURABLE. It reads and writes S.shadowCardEvery, which
   is seeded from the settings GET and persisted by
   POST /api/shadow/settings/presence into presence.json -- so turning it off
   survives a reload and a restart. It is deliberately NOT the same flag as
   the card's own "hide" control (S.shadowHideSession, browser lifetime,
   "not right now"): one state per meaning, and the card is visible when both
   agree. Before this, the switch flipped the session flag and the founder's
   choice died with the page.

   HIDE FOR THIS APP IS NOW DURABLE, AND IS NO LONGER QUIET. It used to flip
   S.shadowQuiet -- the nudge mute -- which meant the row's label named one
   thing and its switch did another, and the other died at reload. It now
   reads S.shadowHiddenApps and writes POST /api/shadow/settings/presence/app,
   keyed on S.modSel: the open app id the Apps screen already owns. The dot is
   suppressed at mount time for that app only (shadowPresenceHiddenHere in
   15-shadow-overlay.js), so leaving the app brings it straight back.

   WITH NO APP OPEN THE ROW HAS NO SUBJECT and says "no app open" instead of
   drawing a switch. A switch whose target is null would either do nothing or
   hide the dot somewhere the founder was not looking; the first is the lie
   this section exists to refuse, and the second is worse.

   QUIET IS STILL MEMORY-ONLY, and is now reached ONLY from the card's own
   Quiet button (15-shadow-overlay.js). S.shadowQuiet gates showNudge there.
   It has no store behind it and no row here pretends otherwise -- which is
   the point: it is not the same thing as hiding Presence, and the two are
   independent now.

   NUDGES PER HOUR IS NOW THE FOUNDER'S NUMBER. It was stated-not-settable,
   read off the JS constant SH_PILLS_PER_HOUR -- and that constant is now
   DELETED rather than demoted to a fallback, because a fallback is how a
   setting quietly reverts to 3 the first time a read fails. The rate lives in
   presence.json beside the corner card, arrives on the same settings GET, and
   is written by POST /api/shadow/settings/presence. The stepper's band comes
   from the server that clamps it, and 0 is a real setting -- "never unasked" --
   not an off state.

   WHAT THE LIMIT ACTUALLY GOVERNS, stated plainly so this row cannot become
   the next thing that overclaims: the unsolicited pill (showPill in
   15-shadow-overlay.js, gated by pillAllowed). It is NOT a limit on showNudge,
   the toast that confirms something the founder just did -- an answer to a
   click is not an interruption and has never been counted.

   QUIET HOURS NOW HAS ALL THREE -- a field, a clock and a window. It is the
   fourth key in presence.json, written by POST /api/shadow/settings/quiet-hours,
   and it is the only Presence setting whose EFFECTIVE value changes without
   anyone writing it: the window is stored, "is it quiet right now" is derived.
   The row still prints no hours it was not given -- "not set" when the store
   says null, and the mock's "9pm to 8am" appears nowhere, because those hours
   were chosen by a designer and not by this founder.

   WHAT QUIET HOURS ACTUALLY SILENCE, stated as plainly as the rate row above:
   the unsolicited pill (showPill), through the SAME gate the card's Quiet
   button has always used -- shadowQuietNow folds the switch and the clock into
   one answer -- and the corner dot's alert RING. Not the badge count, and not
   showNudge. Being quiet is Shadow not speaking first; it is not Shadow hiding
   what is waiting for the founder who looks.

   ADD A CONTROL is drawn and inert for the same reason the steppers are:
   there is nowhere for a new control to be kept. */
function shadowSetPresenceHtml(d){
  const S_ = (typeof S !== "undefined") ? S : {};
  /* the STANDING choice, not the session dismissal: this row states what the
     founder chose, which is what survives the reload that clears the other */
  const card = S_.shadowCardEvery !== false;
  /* held down for the one round-trip, exactly as the steppers are: a second
     click landing mid-write would send a value built off a stale render */
  const busy = !!S_.shadowCornerBusy;
  /* WHICH APP "THIS APP" IS: S.modSel, the open app id the Apps screen
     already owns. No second notion of a current app is invented here, and
     there is deliberately no fallback -- when no app is open the row has no
     subject, and it says so rather than hiding the dot for something the
     founder is not looking at. */
  const appId = S_.modSel || null;
  const openApp = (appId && typeof modSelected === "function")
    ? modSelected(S_) : null;
  /* THE PAYLOAD FIRST, THE SEEDED FLAG SECOND -- the same precedence the
     nudges row below uses, and for the same reason. Both are meant to hold
     one value (applyShadowPresence seeds the flag from this very payload),
     but only `d` is guaranteed fresh at the moment this renders; preferring
     the flag would make the switch depend on a seeding that happens to have
     run, which is a race the row does not need to have. */
  const presHidden = (d && d.presence && Array.isArray(d.presence.hidden_apps))
    ? d.presence.hidden_apps : (S_.shadowHiddenApps || []);
  const hiddenHere = !!appId && presHidden.indexOf(appId) !== -1;
  const appBusy = !!S_.shadowAppPresenceBusy;
  const tog = (on, attr) => `<span class="tog${on ? "" : " off"}" role="switch"
    aria-checked="${on}" tabindex="0" ${attr}></span>`;
  const held = (on, attr) => `<span class="tog${on ? "" : " off"}" role="switch"
        aria-checked="${on}"
        aria-disabled="true" tabindex="-1" title="Saving…" ${attr}></span>`;
  const togBusy = (on, attr) => busy ? held(on, attr) : tog(on, attr);
  const togApp = (on, attr) => appBusy ? held(on, attr) : tog(on, attr);
  /* NUDGES PER HOUR, AND THE BROWSER KEEPS NO COPY OF THE NUMBER. It comes off
     the settings payload, or off the flag the overlay was seeded with from
     that same payload -- and when neither has one the row says "not
     reported", which is the truth and is also exactly the state pillAllowed
     treats as silence. There is no client-side default to fall back to:
     SH_PILLS_PER_HOUR is deleted, so this row cannot print a 3 that nothing
     enforces, which is the defect it shipped with. */
  const pres = (d && d.presence) || {};
  const rate = (typeof pres.nudges_per_hour === "number")
    ? pres.nudges_per_hour
    : (typeof S_.shadowNudgeRate === "number" ? S_.shadowNudgeRate : null);
  /* the band is the SERVER's, like the cap stepper's -- these ends only draw
     the stops, and the server clamps whatever is sent regardless */
  const nlo = (typeof pres.nudges_per_hour_min === "number")
    ? pres.nudges_per_hour_min : 0;
  const nhi = (typeof pres.nudges_per_hour_max === "number")
    ? pres.nudges_per_hour_max : 10;
  const nbusy = !!S_.shadowNudgeBusy;
  const nend = (atEnd) => (atEnd || nbusy)
    ? ` aria-disabled="true" tabindex="-1" title="${escAttr(nbusy ? "Saving…"
        : (atEnd === "lo" ? "Shadow will not interrupt you unasked"
                          : "At most " + nhi + " an hour"))}"`
    : "";
  return `<div class="srow"><span class="k">Corner card on every screen</span>
      ${togBusy(card, 'data-shpresence="card"')}</div>
    <div class="srow"><span class="k">Quiet hours</span>
      ${shadowSetQuietHtml(pres)}</div>
    <div class="srow"><span class="k">Nudges per hour</span>${rate === null
      ? `<span class="ssempty">not reported</span>`
      : `<span class="step"><button type="button"${nend(rate <= nlo && "lo")
          } data-shnudges="${escAttr(String(Math.max(nlo, rate - 1)))}"
          aria-label="fewer">\u2212</button><span class="val">${
          esc(String(rate))}</span><button type="button"${
          nend(rate >= nhi && "hi")} data-shnudges="${escAttr(
          String(Math.min(nhi, rate + 1)))}"
          aria-label="more">+</button></span>${rate === 0
          ? `<span class="auto" title="Shadow will still answer you \u2014 it
              just will not speak first">never unasked</span>` : ""}`}</div>
    <div class="srow"><span class="k">Hide for this app${
      openApp ? ` · <span class="ev">${esc(openApp.name
        || openApp.id)}</span>` : ""}</span>
      ${appId
        ? togApp(hiddenHere, 'data-shpresence="app"')
        : `<span class="ssempty">no app open</span>`}</div>`;
}

/* QUIET HOURS, the one Presence row with a clock behind it.

   THREE STATES, and the row is only ever in one of them: not set / a window /
   being edited. The editor REPLACES the value rather than sitting beside it,
   which is the offers input's pattern (.chipin, shadowOfferAdding) -- two
   controls for one gesture leaves the founder wondering which one is live.

   NOTHING IS PREFILLED. Opening the editor with no window gives two empty
   time fields, not "21:00 to 08:00": the mock's hours were never chosen by
   anyone, and a prefill is a suggestion the founder can save without reading.
   Save stays shut until both ends carry a time, so the round-trip that would
   fail on a half window never leaves the browser.

   "QUIET NOW" IS THE SERVER'S READING, not this page's. The row states what
   the backend answered on the GET; what actually silences a nudge is the
   overlay's own live evaluation of the window (shadowQuietWindowNow). They
   agree because they are one machine -- and printing the server's answer is
   what makes a disagreement visible instead of silent. */
function shadowSetQuietHtml(pres){
  const S_ = (typeof S !== "undefined") ? S : {};
  const win = (pres && pres.quiet_hours) || null;
  const busy = !!S_.shadowQuietBusy;
  if (S_.shadowQuietEditing){
    const dr = S_.shadowQuietDraft || {};
    /* SAVE IS LIVE EVEN WHEN THE FIELDS ARE EMPTY, and the completeness check
       lives in the writer instead. The input listener stores keystrokes
       WITHOUT re-rendering (the caret rule this file already follows for the
       offer name and the new-task fields), so a disabled-until-valid button
       drawn at render time would never learn that the fields had been filled
       -- a dead control that looks like a bug in the setting rather than in
       the button. The writer refuses an incomplete window and says why. */
    return `<span class="chipin shquietin">
      <input type="time" data-shquietstart="1" value="${escAttr(dr.start || "")}"
        aria-label="quiet from"${busy ? " disabled" : ""}>
      <span class="shquietdash" aria-hidden="true">–</span>
      <input type="time" data-shquietend="1" value="${escAttr(dr.end || "")}"
        aria-label="quiet until"${busy ? " disabled" : ""}>
      <button type="button" class="go"${busy
        ? ' aria-disabled="true" tabindex="-1" title="Saving…"'
        : ' data-shquietsave="1"'
        } aria-label="save quiet hours">→</button>
      <button type="button" class="cx"${busy
        ? ' aria-disabled="true" tabindex="-1"'
        : ' data-shquietcancel="1"'} aria-label="cancel">×</button>
    </span>${S_.shadowQuietErr
      ? `<div class="srow ssnote">${esc(S_.shadowQuietErr)}</div>` : ""}`;
  }
  if (!win) return `<span><span class="ev" role="button" tabindex="0"
      data-shquietopen="1" title="Set the hours Shadow stays quiet"
      >not set</span></span>`;
  /* the value is the control: clicking the hours opens them for editing, the
     way the offers pill opens the name field */
  /* "QUIET NOW" IS EVALUATED AT PAINT, NOT READ OFF THE PAYLOAD. The GET
     carries a server-computed quiet_now and this deliberately does not trust
     it: S.shadowSettings is filled by a read that happens on entering the
     screen and is then HELD, so a boolean taken from it would still read
     "quiet now" an hour after the window closed -- the same staleness that
     keeps the overlay's gate on a live clock. The window is the durable fact;
     whether it is quiet is derived, here and at the gate, from the same
     function. The payload's copy is kept only as the fallback for a context
     that has the settings page without the overlay loaded. */
  const inWindow = (typeof shadowQuietWindowNow === "function")
    ? shadowQuietWindowNow(win)
    : !!(pres && pres.quiet_now);
  const now = inWindow
    ? `<span class="auto" title="Shadow will not speak first until ${
        escAttr(win.end)}">quiet now</span>` : "";
  return `<span><span class="ev" role="button" tabindex="0"
      data-shquietopen="1" title="Change the hours Shadow stays quiet"
      >${esc(win.start)} \u2013 ${esc(win.end)}</span>${now}
    <button type="button" class="cx"${busy
      ? ' aria-disabled="true" tabindex="-1" title="Saving\u2026"'
      : ' data-shquietclear="1"'
      } aria-label="Clear quiet hours" title="Clear quiet hours">\u00d7</button>
    </span>`;
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
    <h2 class="sstitle">What Shadow knows</h2>
  </header>`;
  if (!d) return `<div class="shset">${head}
    <div class="ssbody"><div class="sswrap">
      <div class="zero"><h4>Shadow settings</h4>
      <p>Could not read the rules just now.
      <button class="btn" type="button" data-shsetreload="1">Retry</button></p>
      </div></div></div></div>`;
  return `<div class="shset">${head}
    <div class="ssbody"><div class="sswrap">
      ${/* ── TWO BOXES (founder, 2026-09-17) ──────────────────────
           Eight sections became two. Autonomy, Tasks, Delegate offers,
           Presence, Add a control and Attention are gone from this page --
           every one of them was a control the founder had to form an opinion
           about before Shadow could be useful, and the answer to most of
           them is a default.

           NOTHING WAS DELETED FROM THE ENGINE. The settings still exist,
           their routes still answer, and their stored values still bind:
           autonomy() already defaults to L3, max_running and the budgets
           keep their stored numbers. What went is the SURFACE, not the
           behaviour -- which also means a value that was stranded ON with no
           way to change it had to be dealt with explicitly rather than left
           pinned (confirm_top_tier; see the release note).

           The two that stay are the two that are genuinely the founder's
           own words, and they are the same shape: a text box. */""}
      ${shadowSettingsSecHtml("Personality", shadowSetBehavesHtml(d))}
      ${shadowSettingsSecHtml("Memory", shadowSetMemoryTextHtml(d))}
      ${/* NAMED, NOT INFERRED. This section carried no class of its own and
            the stylesheet reached it with :has(.chips) -- which happened to
            be correct, and was still the wrong way to write it: the rule
            silently depends on what the section CONTAINS, so any future row
            with chips in it inherits the offers treatment. An id and a class
            say which section this is, in the markup that owns it. */""}
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
  TITLES.shadowsettings = ["What Shadow knows",
    "how it behaves \u00b7 the rules it lives by \u00b7 what it remembers"];
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
    /* THE TAB THE FOUNDER PRESSED, not the one this screen was born on.
       The literal "watching" here made the plane's own Working and Goals
       tabs render as buttons that change nothing: the click handler sets
       S.shadowTab and re-renders, and the re-render threw the answer away.

       MEASURED IN THE LIVE APP (run-limit walkthrough, 2026-09-16), and the
       cost was not cosmetic. shadowPlaneHtml's Working rows carry Stop and
       Resume -- and the task card deliberately does NOT draw them ("this
       pane is where Shadow reports and asks, not a worker control panel",
       founder 2026-09-15), on the stated understanding that "the same two
       buttons on the same two hooks still render in shadowPlaneHtml". With
       the tab pinned shut, that understanding was false in effect: there
       was no reachable way to STOP a running task, only the row's × which
       deletes it. The design note and this line disagreed; the note is the
       decision, so this line is what changes.

       Nothing else moves: the same function, the same three tabs, the same
       data-shtab hooks the QA probes read, and "watching" remains the
       default for a page that has not been told otherwise. */
    return `<div class="shwatchscreen">${
      shadowPlaneHtml(S_.shadowWatching || [], S_.shadowMissions || [],
                      S_.shadowTab || "watching")}</div>`;
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
    /* d.shchat / d.shscopepick went with the existing-chat picker they
       served (founder, 2026-09-15). Both were rendered only by
       shadowTargetHtml and shadowRecentChatsHtml, and both are gone.
       S.shadowChat keeps its default "global", which is what the delegation
       composer wants -- + Delegate starts its own chat. */
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
        /* v4: opening starts an empty task chat; closing forgets nothing on
           the server (a draft already opened stays in the list as READY) */
        if (S.shadowNewOpen) shadowNewChat();
      }
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    if (d.shnewsend){
      /* the arrow and Enter must read and clear the same node -- see the
         keydown handler for why the node, not the store, is the draft */
      const box = (typeof document !== "undefined" && document.querySelector)
        ? document.querySelector("[data-shnewtalk]") : null;
      if (box){ shadowNewChat().text = box.value; box.value = ""; }
      shadowNewTalk();
      return;
    }
    /* Talk to Shadow: the founder's conversation with THIS task. Opening and
       closing is local state only -- no request, nothing paused, and the
       worker is not told. Re-opening reads the record again, so the history
       comes back from the transcript rather than from the browser. */

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
        /* d.shexisting went with its UI: it was rendered in exactly two places,
       the workspace composer's "Work in an existing chat instead" and the
       shexwrap "Back to tasks", and both are gone. */
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
    /* v4 (SHADOW-V3 section 2): one click from the working chat to the
       task's own chat in Focus > Shadow -- the other half of "Open the chat" */
    if (d.shopentask){
      if (typeof S !== "undefined") S.shadowTaskSel = d.shopentask;
      if (typeof shadowRouteDeepLink === "function")
        shadowRouteDeepLink("sutra://shadow/" + d.shopentask);
      else if (typeof openScreen === "function") openScreen("shadow");
      return;
    }
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
    /* PRESENCE. The two rows behave differently now and the difference is
       the point: QUIET is still the same in-memory flag the card toggles,
       reached from a second place. CORNER CARD is a stored setting, so it
       goes through a writer that talks to the server and repaints from the
       answer -- see shadowSetCornerCard. */
    if (d.shpresence){
      if (d.shpresence === "card") return shadowSetCornerCard();
      /* "app" is the per-app hide. It is a WRITE, like "card" and unlike the
         old quiet arm this replaces -- so it returns into the writer rather
         than flipping a flag and repainting. */
      if (d.shpresence === "app") return shadowSetAppPresence();
      if (d.shpresence === "quiet" && typeof S !== "undefined")
        S.shadowQuiet = !S.shadowQuiet;
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    /* NUDGES PER HOUR. A stored setting, so it goes the way the cap stepper
       and the corner card go: the button carries its already-clamped
       destination, the writer posts it, and the row repaints from the answer
       the server stored. */
    if (d.shnudges !== undefined) return shadowSetNudgeRate(d.shnudges);
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
    /* RUNNING AT ONCE and BUDGET PER TASK. The two settings controls on this
       page with a store behind them. Each button carries the value it would
       MOVE TO (already clamped to the server's band when it was drawn), so
       the handler sends a number rather than a direction -- a repeated click
       cannot compound into a value nobody asked for while an earlier write is
       in flight. */
    if (d.shrunlimit !== undefined) return shadowSetRunLimit(d.shrunlimit);
    /* AUTONOMY. Same rule as the two steppers: the button carries the value
       it would MOVE TO, so a repeated click cannot compound, and the toggle
       carries its DESTINATION ("0"/"1") rather than its current state. */
    if (d.shautonomy !== undefined)
      return shadowSetAutonomy({ level: d.shautonomy });
    if (d.shtoptier !== undefined)
      return shadowSetAutonomy({ confirm_top_tier: d.shtoptier === "1" });
    /* "auto" is a RESET, and it has to survive the trip as null rather than
       becoming Number("auto") -> NaN. The budget branch is tested before the
       bare kind-picker branch because the stepper buttons carry BOTH. */
    if (d.shbudget !== undefined)
      return shadowSetTurnBudget(d.shbudgetkind,
                                 d.shbudget === "auto" ? null : d.shbudget);
    if (d.shbudgetkind !== undefined){
      /* picking a kind only moves what the row POINTS AT -- no write, and
         deliberately no store: it is a cursor, not a preference */
      if (typeof S !== "undefined") S.shadowBudgetKind = d.shbudgetkind;
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    /* DELEGATE OFFERS. The x carries the NAME rather than a position, so a
       re-render landing between the click and the write cannot shift which
       kind gets removed. */
    if (d.shofferdel !== undefined) return shadowOfferRemove(d.shofferdel);
    if (d.shofferopen !== undefined){
      /* opening the box is not a write: there is no name to send yet */
      if (typeof S !== "undefined"){
        S.shadowOfferAdding = true;
        S.shadowOfferDraft = "";
        S.shadowOfferErr = null;
      }
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    /* QUIET HOURS. Opening and cancelling are not writes -- there is no window
       to send yet -- so they move local state and repaint, exactly as the
       offers box does. Save and clear are the two that talk to the server, and
       clear sends an explicit null rather than an empty object so "cleared"
       arrives as the one shape the store deletes the key for. */
    if (d.shquietopen !== undefined){
      if (typeof S !== "undefined"){
        const cur = ((S.shadowSettings || {}).presence || {}).quiet_hours || null;
        S.shadowQuietEditing = true;
        /* seeded from the STORED window when there is one, so "change" starts
           from what is in force; empty when there is none, because the mock's
           hours are not this founder's */
        S.shadowQuietDraft = cur ? { start: cur.start, end: cur.end }
                                 : { start: "", end: "" };
        S.shadowQuietErr = null;
      }
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    if (d.shquietcancel !== undefined){
      if (typeof S !== "undefined"){
        S.shadowQuietEditing = false;
        S.shadowQuietDraft = null;
        S.shadowQuietErr = null;
      }
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    if (d.shquietsave !== undefined) return shadowSetQuietHours();
    if (d.shquietclear !== undefined) return shadowSetQuietHours(null);
    if (d.shofferadd !== undefined) return shadowOfferAdd();
    if (d.shivsend) return shadowSendIntervention(d.shivsend);
    if (d.shact && d.shmid)
      return shadowMissionAct(d.shmid, d.shact,
        d.shact === "approve" && d.shapproval ? { approval_id: d.shapproval }
        /* v4.2: the ask row's button carries which ask it answers */
        : d.shact === "answer" ? Object.assign({ kind: d.shkind },
            d.shindex != null && d.shindex !== "" ? { index: Number(d.shindex) } : {})
        : undefined);
    /* v5: Start is only ever the existing mission action now. The
       special case that used to sit here closed the task chat when the
       founder started the draft that chat had written -- and the box no
       longer writes a draft to start: it creates and starts in one press. */
    if (d.shstart) return shadowMissionAct(d.shstart, "start_now");
    if (d.shunwatch) return shadowWatchSet(d.shunwatch, false);
    if (d.shconfirm) return shadowInstructionAct(d.shconfirm, "confirm");
    if (d.shrevoke) return shadowInstructionAct(d.shrevoke, "revoke");
  });
  /* WHO HAS THE CARET IS STATE TOO (founder, 2026-09-18). render() restores
     focus from a snapshot of document.activeElement taken at the top of the
     pass -- which is correct, and is not enough: if ANYTHING detached the
     textarea in an earlier tick (a repaint from a path that does not go
     through render(), two renders in a row, an overlay mount) then
     activeElement is already <body> by the time the snapshot runs, and no
     later render has any way to know the founder was typing. A flag in S
     survives that, because it is not stored on the element being replaced.

     THE FLAG IS WHAT FOCUS LANDED ON, not merely "the box was entered". An
     earlier draft only ever SET it here and left the clearing to focusout --
     and this sequence then stole focus: type in the box, a repaint detaches
     it, founder clicks the corner card or any other field, and the next
     render pulled them straight back out of it. Writing the flag from where
     focus ARRIVED closes that: a click into anything else is a focusin on
     that thing, and says so. A detach fires no focusin at all, so the flag
     stands and the restore below can put the founder back.

     MEASURED IN CHROME 2026-09-18, because the first attempt at the focusout
     half was written from memory and was wrong. Replacing #scBody's innerHTML
     under the focused textarea fires, in this order:

         blur     target=TEXTAREA isConnected=true  relatedTarget=null
         focusout target=TEXTAREA isConnected=true  relatedTarget=null

     -- so a detach is NOT distinguishable from a real click-away at the
     moment focusout runs. isConnected is still true (the unfocusing steps run
     before the node is actually removed) and relatedTarget is null for both.
     Deciding there cleared the flag on every rebuild, which is the exact bug
     this was supposed to fix: driven live, 7 of 202 characters landed.

     SO THE DECISION IS DEFERRED ONE TICK, where the two cases separate
     cleanly and without a heuristic: a node removed by a rebuild is
     disconnected by then, a node the founder merely clicked away from is
     still in the document. The deferred check only ever CLEARS, never sets,
     so it cannot fight the focusin above or the restore below. */
  document.addEventListener("focusin", (ev) => {
    if (typeof S === "undefined") return;
    const d = (ev.target && ev.target.dataset) || {};
    S.shadowComposeFocus = !!d.shhomecompose;
  });
  document.addEventListener("focusout", (ev) => {
    const t = ev.target, d = (t && t.dataset) || {};
    if (!d.shhomecompose || typeof S === "undefined") return;
    if (typeof t.selectionStart === "number") S.shadowComposeCaret = t.selectionStart;
    /* focusout with a relatedTarget is a move to something focusable, and the
       focusin on THAT has already said so -- nothing left to decide. */
    if (ev.relatedTarget) return;
    const settle = () => {
      if (typeof S === "undefined") return;
      if (t.isConnected === false) return;       /* a rebuild: still typing */
      const a = document.activeElement;
      if (a === t) return;                       /* focus came straight back */
      if (a && a.dataset && a.dataset.shhomecompose) return;  /* the new node */
      if (typeof document.hasFocus === "function" && !document.hasFocus()) return;
      S.shadowComposeFocus = false;              /* clicked onto dead space */
    };
    if (typeof setTimeout === "function") setTimeout(settle, 0); else settle();
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
    /* The existing-chat scope guard that stood here went with its flow
       (founder, 2026-09-15): shadowExistingOpen can no longer be set, so the
       branch was unreachable. The delegation composer it deliberately
       exempted is the only one left, and it is global on purpose --
       + Delegate starts its own chat. shadowScopeErr itself STAYS: the
       "Shadow did not load" message below still uses it. */
    /* never a silent no-op: if the overlay module did not load there is no
       send path, and that is worth saying out loud */
    if (typeof sendToShadow !== "function"){
      S_.shadowScopeErr = "Shadow did not load — reload the app.";
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    S_.shadowScopeErr = null;
    /* WITH A TASK IN FOCUS, THE ASIDE GOES TO THE TASK (founder,
       2026-09-15). Same box, same hooks, same gesture -- the destination is
       decided by whether the founder is looking at a delegation. With none
       selected this is still the briefing composer and the path below is
       byte-identical to what it always was. */
    const sel = (typeof shadowSelectedTask === "function")
      ? shadowSelectedTask() : null;
    if (sel && sel.id && !S_.shadowNewOpen){
      /* ONE DOOR TO SHADOW (founder, 2026-09-17). This box used to deposit a
         line on the record through shadowSayToShadow and nothing answered;
         a second, floating panel was the only surface that talked back. The
         founder had to decide which of the two a sentence was, which is a
         classification only Shadow can make -- so there is now one box, and
         it goes where the answers come from.

         NOTHING ABOUT THE OPERATIONAL PATH MOVED. The route this calls,
         POST /api/shadow/tasks/{id}/chat, already did BOTH halves: it
         returns Shadow's reply AND appends the founder's words to
         `founder_says` (app._record_founder_talk), which is what
         _decision_context hands the decider, what `seen` consumes once, and
         what standing_instructions are composed from. The say endpoint is
         untouched and still serves anything that calls it. */
      shadowTalk().text = text.trim();
      shadowComposeSet(el, "");
      shadowTalkSend(sel.id, el);
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    shadowComposeSet(el, "");
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
    /* v4: Enter in the task chat sends the line; Shift+Enter is a newline */
    if (ev.key === "Enter" && !ev.shiftKey && ev.target && ev.target.dataset
        && ev.target.dataset.shnewtalk){
      ev.preventDefault && ev.preventDefault();
      shadowNewChat().text = ev.target.value;
      /* THE NODE IS THE DRAFT NOW. It is mounted and no render rewrites it,
         so emptying the store is not enough -- the send has to empty the box
         itself, exactly as the founder pressing Enter expects. This places no
         cursor and moves no focus; it is the submit clearing its own field. */
      ev.target.value = "";
      shadowNewTalk();
      return;
    }
    /* the offer box submits on Enter and abandons on Escape -- the two keys
       every one-field inline input in this app already answers to */
    const od = (ev.target && ev.target.dataset) || {};
    if (!od.shoffername) return;
    if (ev.key === "Enter"){
      ev.preventDefault && ev.preventDefault();
      shadowOfferAdd();
    } else if (ev.key === "Escape" && typeof S !== "undefined"){
      S.shadowOfferAdding = false;
      S.shadowOfferDraft = "";
      S.shadowOfferErr = null;
      if (typeof scheduleRender === "function") scheduleRender();
    }
  });
  /* The new-task fields keep what is typed across the background re-renders
     the session stream causes. Stored, NEVER re-rendered on keystroke: a
     render per character would fight the caret, which is the bug the
     composer's own text store exists to avoid. */
  /* v4: "How Shadow behaves" saves on change, which is the blur after an
     edit -- no Save button, no keystroke writes */
  document.addEventListener("change", (ev) => {
    const d = (ev.target && ev.target.dataset) || {};
    if (d.shbehaves) shadowBehavesSave(ev.target.value);
    if (d.shmemory) shadowMemorySave(ev.target.value);
  });
  document.addEventListener("input", (ev) => {
    const t = ev.target, d = (t && t.dataset) || {};
    /* THE "TALK TO SHADOW" BOX, kept the same way and for the same reason as
       every field below it. Stored without rendering: shadowStageHtml() reads
       it back on the NEXT repaint, whatever caused that repaint, so a
       background render can no longer take a half-typed brief with it. */
    if (d.shhomecompose){
      if (typeof S !== "undefined"){
        S.shadowComposeDraft = t.value;
        S.shadowComposeCaret = t.selectionStart;
      }
      return;
    }
    /* v4: the task chat line and the behaves text, kept across the
       background re-renders like every typed field here */
    if (d.shnewtalk){ shadowNewChat().text = t.value; return; }
    if (d.shbehaves){
      if (typeof S !== "undefined"){ S.shadowBehavesDraft = t.value; S.shadowBehavesSaved = false; }
      return;
    }
    if (d.shmemory){
      if (typeof S !== "undefined"){ S.shadowMemoryDraft = t.value; S.shadowMemorySaved = false; }
      return;
    }
    /* the intervention form's typed fields, on the SAME listener the
       delegate panel already uses -- one input handler, not a second one */
    if (d.shivtext && d.shivmid && d.shivkey){
      shadowIvDraft(d.shivmid).values[d.shivkey] = t.value;
      return;
    }
    /* the offer name, kept across the background re-renders the session
       stream causes -- same reason the new-task fields are kept, and stored
       without re-rendering for the same caret reason */
    if (d.shoffername){
      if (typeof S !== "undefined") S.shadowOfferDraft = t.value;
      return;
    }
    /* the two ends of the quiet window, kept for the same reason and in the
       same way: stored without re-rendering, so a background repaint cannot
       throw away a half-typed time */
    if (d.shquietstart || d.shquietend){
      if (typeof S !== "undefined"){
        S.shadowQuietDraft = S.shadowQuietDraft || { start: "", end: "" };
        if (d.shquietstart) S.shadowQuietDraft.start = t.value;
        else S.shadowQuietDraft.end = t.value;
      }
      return;
    }
    if (!d.shnewobj && !d.shnewdone) return;
    const draft = shadowNewDraft();
    if (d.shnewobj) draft.objective = t.value;
    else draft.done = t.value;
  });
}

/* THE ONE WRITER of the composer's text. A programmatic `el.value = ...`
   fires no `input` event, so anything that set the node directly left the
   store holding something else -- and the store is what the next repaint
   renders. Three callers: the two sends, which empty it, and the send that
   did not land, which hands the founder's line back. */
function shadowComposeSet(el, text){
  const v = String(text == null ? "" : text);
  if (typeof S !== "undefined"){
    S.shadowComposeDraft = v;
    S.shadowComposeCaret = v.length;
  }
  if (el) el.value = v;
}

/* THE LAST WORD ON THE "TALK TO SHADOW" BOX, called from the end of render()
   after its own focus restore has run -- see 06-render.js.

   It is a FLOOR, not a replacement. render()'s snapshot path is more precise
   (it carries the exact caret of the element it saw focused) and wins whenever
   it fired: this returns immediately if the box already has focus. What it
   adds is the case that path cannot cover -- focus lost in an earlier tick, so
   there was nothing to snapshot -- and the draft, which is now restored on
   EVERY pass whether or not anyone was focused.

   Guarded throughout: the node tests boot this file against a stub document. */
function shadowRestoreCompose(){
  if (typeof document === "undefined" || typeof S === "undefined") return;
  if (!document.querySelector) return;
  const el = document.querySelector("[data-shhomecompose]");
  if (!el) return;                         /* another screen; nothing to keep */
  const draft = S.shadowComposeDraft || "";
  if (el.value !== draft) el.value = draft;
  if (!S.shadowComposeFocus) return;       /* never grab focus nobody gave it */
  if (document.activeElement === el) return;
  try {
    el.focus({ preventScroll: true });
    if (el.setSelectionRange){
      const n = String(el.value || "").length;
      const c = (typeof S.shadowComposeCaret === "number")
        ? Math.max(0, Math.min(S.shadowComposeCaret, n)) : n;
      el.setSelectionRange(c, c);
    }
  } catch (e) {}
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
  /* A LINE THE FOUNDER TYPED IS THEIRS TO JUDGE (founder, 2026-09-15).
     Restores the pre-e1c8d0ea default for THIS path. That commit routed the
     Delegate form through goalCriteriaToChecks, which infers a tier from
     SHAPE -- so any short, unadorned line became contains_artifact, and that
     tier is evaluated as `check in transcript_text`, a literal substring
     search over the worker's words.

     MEASURED, four missions. "The file contains HELLO" (m-307fc348352b,
     m-1eec37dfd145), "The file exists and contains 5 bullets."
     (m-b7ee410c3c3e), "Tests cover it." / "The timestamp is visible on the
     task card." / "Shadow reaches DONE." (m-cd009367d41a) all classified
     contains_artifact. Every one describes a STATE; the worker proves it by
     doing the thing, never by uttering the sentence. So met stayed False
     forever, `done` was unreachable, and Shadow spent its budget demanding
     more proof of work that was already finished.

     THE COMMIT'S SECOND REASON NO LONGER HOLDS. It argued the old default
     made the premature-pause bug reachable -- "with zero machine checks the
     confirmation boundary was satisfied vacuously on turn 1". The SAME
     commit fixed that in mission_engine: `others_met = bool(machine) and
     all(...)`. With no machine check there is nothing to have passed, so an
     all-founder_confirm mission cannot pause vacuously. This was defending a
     hole that was already closed.

     THE COST, STATED: contains_artifact is no longer reachable from the
     Delegate form unless Shadow proposes it. That is the right trade --
     unreachable-but-honest beats reachable-but-unsatisfiable -- and Shadow's
     own proposals still reach the tier through goalTierFor, which is
     untouched, as are goalCriteriaToChecks, goalIsLiteralArtifact and the
     goal card's path. */
  const done_when = String(d.done || "").split("\n")
    .map(s => s.trim()).filter(Boolean)
    .map(check => ({ tier: "founder_confirm", check }));
  S.shadowNewBusy = true;
  S.shadowNewErr = null;
  if (typeof scheduleRender === "function") scheduleRender();
  let r = null;
  try {
    r = await shadowPost("/api/shadow/missions", {
      objective: objective,
      template: shadowOfferKinds().includes(d.kind)
        ? d.kind : shadowOfferKinds()[0],
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
  /* ── THE NEXT VIEW MUST BE THIS TASK, NOT WHICHEVER ONE THE FALLBACK PICKS
     (founder, 2026-09-19) ────────────────────────────────────────────────
     S.shadowTaskSel now names a mission the LIST has never heard of: the
     create answered, but S.shadowMissions is whatever the last read left
     behind. shadowSelectedTask() looks its pick up in exactly that array,
     misses, and falls through to its ranking — whose FIRST rule is "the
     first startable task", i.e. a brief_confirm row with no start stamp.
     So the view Enter lands on was another task's brief, with another
     task's "Start the task" button on it, and pressing that is a manual
     start step in the next view. Measured with the panel driven headless:
     one running task plus one old unstarted brief, Enter on a new task,
     and the pane drew the OLD brief with Start.

     SEEDING IS NOT A LOCAL STATE MACHINE. The record put in is the one the
     server just sent back, unmodified but for the stamp below, and the
     forced read at the end of this function replaces the whole array with
     the server's answer. It closes the gap between the two; it does not
     become a second source of truth.

     THE STAMP GOES ON WITH IT, and that is the point rather than a detail.
     The record from create is brief_confirm with no start_requested_at,
     which is precisely the shape that draws "Start the task" — so seeding
     it raw would put the button the founder is complaining about onto the
     NEW card too, for the length of the start round-trip. This function is
     committed to starting it in the same breath, so the row says so; if
     that start does not land, the stamp comes off below and Start is
     offered honestly. */
  const seedRow = Object.assign({}, m,
    { start_requested_at: m.start_requested_at || new Date().toISOString() });
  if (!Array.isArray(S.shadowMissions)) S.shadowMissions = [];
  if (!S.shadowMissions.some(x => x && x.id === m.id))
    S.shadowMissions = S.shadowMissions.concat([seedRow]);
  if (typeof scheduleRender === "function") scheduleRender();
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
  if (!started){
    /* the start did NOT land, so the seeded row must stop claiming it did:
       the nudge sends the founder to a Start button, and that button has to
       be there. The forced read below normally corrects this on its own --
       the server never stamped either -- but a read that fails must not
       leave a row that hides the only action left on it. */
    S.shadowMissions = (S.shadowMissions || []).map(x =>
      (x && x.id === m.id) ? Object.assign({}, x, { start_requested_at: null })
                           : x);
    if (typeof showNudge === "function")
      showNudge("Task created, but it did not start — press Start on the brief.");
  }
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
     this only stops a stale id from outliving the row it named.

     AN ARCHIVE IS NOT A DISAPPEARANCE (founder, 2026-09-19): the row is
     still there, under ARCHIVED, so the pane stays on the task the founder
     was just looking at instead of jumping to whatever ranks next. Only the
     second press -- the one that erases -- clears the pick. */
  if (doc && !doc.archived && typeof S !== "undefined"
      && S.shadowTaskSel === mid)
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

/* Write "Corner card on every screen" -- the durable presence choice.

   THE DOT MOVES FIRST, THEN THE SERVER CONFIRMS IT. A visibility toggle that
   waited for a round-trip before anything happened would read as a dead
   click, so the card appears or disappears immediately -- and the local flag
   is REVERTED if the write does not land, because a switch that reads ON over
   a disk that says OFF is the failure this whole change exists to remove.

   REPAINTS FROM THE ANSWER, like the steppers: the server's stored boolean is
   folded into S.shadowSettings.presence and re-applied, so the row and the
   overlay both state what is on disk rather than what was clicked.

   BUSY HOLDS THE SWITCH for the round-trip, for the reason the stepper's does
   -- two quick clicks would otherwise race and land on whichever write the
   server happened to finish second. */
async function shadowSetCornerCard(){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  if (S.shadowCornerBusy) return;
  const was = S.shadowCardEvery !== false;
  const next = !was;
  S.shadowCornerBusy = true;
  if (typeof applyCornerCardPref === "function") applyCornerCardPref(next);
  else S.shadowCardEvery = next;
  if (typeof scheduleRender === "function") scheduleRender();
  try {
    const r = await shadowPost("/api/shadow/settings/presence",
                               { corner_card: next });
    const body = (r && r.ok) ? await r.json() : null;
    if (body && typeof body.corner_card === "boolean"){
      if (S.shadowSettings)
        S.shadowSettings.presence = Object.assign({}, S.shadowSettings.presence,
          { corner_card: body.corner_card });
      if (typeof applyCornerCardPref === "function")
        applyCornerCardPref(body.corner_card);
      if (typeof showNudge === "function")
        showNudge(body.corner_card
          ? "Corner card is on — Shadow is on every screen."
          : "Corner card is off — Focus › Shadow still has it.");
    } else {
      /* put it back: nothing was stored, so nothing may look stored */
      if (typeof applyCornerCardPref === "function") applyCornerCardPref(was);
      else S.shadowCardEvery = was;
      if (typeof showNudge === "function")
        showNudge("That did not stick — try again");
    }
  } catch (e){
    if (typeof applyCornerCardPref === "function") applyCornerCardPref(was);
    else S.shadowCardEvery = was;
    if (typeof showNudge === "function")
      showNudge("That did not stick — try again");
  }
  S.shadowCornerBusy = false;
  if (typeof scheduleRender === "function") scheduleRender();
}

/* Write "Quiet hours" -- a window, or null to clear it.

   NOTHING IS OPTIMISTIC HERE, unlike the corner card. That switch moves the
   dot immediately because a visibility toggle that waits reads as a dead
   click; this row is text, the round-trip is one hop, and the hours the
   founder is about to rely on at 3am must be the hours the DISK holds. So the
   row repaints from the answer and only from the answer.

   THE FIELDS ARE READ FROM THE DOM, not from the draft. The draft exists to
   survive a background re-render, but the input listener stores it without
   re-rendering, so on the save path the elements are the freshest truth --
   and reading them is also what makes this correct if a repaint happened to
   land between the last keystroke and the click.

   AN INCOMPLETE WINDOW NEVER LEAVES THE BROWSER. The server refuses it
   identically (it has to -- a hand-written POST is not an input element), but
   saying so here costs no round-trip and keeps the editor open on the field
   the founder still has to fill.

   CLEAR SENDS EXPLICIT null. Not {}, not omitting the key: null is the one
   shape set_quiet_hours deletes the key for, and an absent key is a 400 by
   design so a malformed request can never silently erase the setting. */
async function shadowSetQuietHours(window){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  if (S.shadowQuietBusy) return;
  let payload = null;
  if (window === undefined){
    const pick = (sel) => {
      const el = (typeof document !== "undefined" && document.querySelector)
        ? document.querySelector(sel) : null;
      return el ? String(el.value || "") : "";
    };
    const dr = S.shadowQuietDraft || {};
    const start = pick("[data-shquietstart]") || dr.start || "";
    const end = pick("[data-shquietend]") || dr.end || "";
    S.shadowQuietDraft = { start, end };
    if (!start || !end){
      S.shadowQuietErr = "Set both a start and an end.";
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    if (start === end){
      S.shadowQuietErr = "Quiet hours need a start and an end that differ.";
      if (typeof scheduleRender === "function") scheduleRender();
      return;
    }
    payload = { start, end };
  }
  S.shadowQuietBusy = true;
  S.shadowQuietErr = null;
  if (typeof scheduleRender === "function") scheduleRender();
  try {
    const r = await shadowPost("/api/shadow/settings/quiet-hours",
                               { quiet_hours: payload });
    const body = (r && r.ok) ? await r.json() : null;
    if (body && body.quiet_hours !== undefined){
      if (S.shadowSettings)
        S.shadowSettings.presence = Object.assign({}, S.shadowSettings.presence,
          { quiet_hours: body.quiet_hours, quiet_now: !!body.quiet_now });
      /* the overlay gates off the WINDOW, so it is seeded from the stored one
         -- one state, reached from the page that just changed it */
      S.shadowQuietHours = body.quiet_hours;
      S.shadowQuietEditing = false;
      S.shadowQuietDraft = null;
      if (typeof showNudge === "function")
        showNudge(body.quiet_hours
          ? "Quiet hours " + body.quiet_hours.start + " to "
            + body.quiet_hours.end + " — Shadow will not speak first then."
          : "Quiet hours cleared — Shadow can speak at any hour.");
    } else {
      S.shadowQuietErr = (r && r.status === 400)
        ? "Those hours were refused — check the start and the end."
        : "That did not stick — try again.";
    }
  } catch (e){
    S.shadowQuietErr = "That did not stick — try again.";
  }
  S.shadowQuietBusy = false;
  if (typeof scheduleRender === "function") scheduleRender();
}

/* Write "Nudges per hour".

   THE SERVER IS THE CLAMP, and its answer is what the row repaints from --
   never the optimistic value. Same rule as the cap stepper, for the same
   reason: the number is floored and ceilinged on the way in, so painting what
   was sent and then discovering something else was stored is the failure this
   avoids. Nothing here is optimistic at all, which is why this writer has no
   put-it-back arm the way shadowSetCornerCard does.

   BOTH ENDS ARE HELD DOWN for the round-trip. A founder clicking + four times
   quickly would otherwise send four writes off ONE rendered value and land on
   2 instead of 5.

   THE FLAG THE PILL READS MOVES TOO. S.shadowNudgeRate is what pillAllowed
   consults, and it lives on the client for the life of the page, so folding
   the answer only into S.shadowSettings would leave the setting correct on the
   settings screen and stale everywhere the limit is actually enforced until
   the next reload. */
async function shadowSetNudgeRate(n){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  if (S.shadowNudgeBusy) return;
  S.shadowNudgeBusy = true;
  if (typeof scheduleRender === "function") scheduleRender();
  try {
    const r = await shadowPost("/api/shadow/settings/presence",
                               { nudges_per_hour: Number(n) });
    const body = (r && r.ok) ? await r.json() : null;
    if (body && typeof body.nudges_per_hour === "number"){
      S.shadowNudgeRate = body.nudges_per_hour;
      if (S.shadowSettings)
        S.shadowSettings.presence = Object.assign({}, S.shadowSettings.presence,
          { nudges_per_hour: body.nudges_per_hour,
            nudges_per_hour_min: body.min,
            nudges_per_hour_max: body.max });
      if (typeof showNudge === "function")
        showNudge(body.nudges_per_hour === 0
          ? "Shadow will not speak first — it still answers when you ask."
          : "Nudges per hour is " + body.nudges_per_hour + ".");
    } else if (typeof showNudge === "function"){
      showNudge("That limit did not stick — try again");
    }
  } catch (e){
    if (typeof showNudge === "function")
      showNudge("That limit did not stick — try again");
  }
  S.shadowNudgeBusy = false;
  if (typeof loadShadowSettings === "function") loadShadowSettings(true);
  if (typeof scheduleRender === "function") scheduleRender();
}

/* Write "Hide for this app" -- Presence, for the open app only.

   THE SUBJECT IS S.modSel, read at CLICK time rather than carried on the
   element. The founder can change apps between the render and the click, and
   an id baked into the markup would then hide the dot for the app they just
   left. No app open means no subject, and the row does not draw a switch in
   that state -- this guard is the second half of that, for a synthesised
   click or a selection that cleared mid-flight.

   OPTIMISTIC, THEN CORRECTED BY THE SERVER, exactly as the corner card is.
   The dot has to go the instant the switch moves or the control feels
   broken; if the write then fails, the list is put back to what it was and
   the founder is told, because nothing was stored and nothing may look
   stored.

   THE ANSWER IS THE WHOLE LIST. The route returns hidden_apps and this
   repaints from it rather than patching one id in -- so a hide written from
   another window (or a stale client) is reconciled by the next write instead
   of being silently undone by it. */
async function shadowSetAppPresence(){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  if (S.shadowAppPresenceBusy) return;
  const appId = S.modSel;
  if (!appId) return;                     /* no subject: nothing to write */
  const was = (S.shadowHiddenApps || []).slice();
  const next = was.indexOf(appId) === -1;
  S.shadowAppPresenceBusy = true;
  if (typeof applyAppPresence === "function")
    applyAppPresence(next ? was.concat([appId])
                          : was.filter(x => x !== appId));
  if (typeof scheduleRender === "function") scheduleRender();
  try {
    const r = await shadowPost("/api/shadow/settings/presence/app",
                               next ? { hide: appId } : { show: appId });
    const body = (r && r.ok) ? await r.json() : null;
    if (body && Array.isArray(body.hidden_apps)){
      if (S.shadowSettings)
        S.shadowSettings.presence = Object.assign({}, S.shadowSettings.presence,
          { hidden_apps: body.hidden_apps });
      if (typeof applyAppPresence === "function")
        applyAppPresence(body.hidden_apps);
      if (typeof showNudge === "function")
        showNudge(body.hidden
          ? "Hidden here — Shadow is still on every other screen."
          : "Shadow is back on this app.");
    } else {
      if (typeof applyAppPresence === "function") applyAppPresence(was);
      else S.shadowHiddenApps = was;
      if (typeof showNudge === "function")
        showNudge("That did not stick — try again");
    }
  } catch (e){
    if (typeof applyAppPresence === "function") applyAppPresence(was);
    else S.shadowHiddenApps = was;
    if (typeof showNudge === "function")
      showNudge("That did not stick — try again");
  }
  S.shadowAppPresenceBusy = false;
  if (typeof scheduleRender === "function") scheduleRender();
}

/* Write "Running at once".

   THE SERVER IS THE CLAMP, and the answer is what the row repaints from --
   never the optimistic value. Two reasons: the server floors/ceilings the
   number, and raising the cap PROMOTES queued tasks, so the counts beside
   the stepper change as a result of the write. Painting the requested value
   and then discovering the server stored something else is the failure this
   avoids.

   BUSY HOLDS BOTH ENDS DOWN for the round-trip: a founder clicking + four
   times quickly would otherwise send four writes off ONE rendered value and
   land on 2 instead of 5. */
/* AUTONOMY, written the way the two steppers are: one guard so a
   double-click cannot send two, fold the server's answer into the settings
   object the page already reads rather than keeping a second copy, then
   re-read. ONE FUNCTION FOR BOTH FIELDS because the route takes both -- the
   toggle's meaning depends on the level, so a client that could write one
   without restating the other would be able to draw a state the server never
   reported.

   IT RE-READS THE HOME, NOT JUST THE SETTINGS. Dropping to L0 pauses running
   tasks and the rows have to say so; raising back does NOT un-pause them
   (the founder resumes by hand), and the list is what tells the truth about
   which of those two just happened. */
async function shadowSetAutonomy(patch){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  if (S.shadowAutonomyBusy) return;
  S.shadowAutonomyBusy = true;
  if (typeof scheduleRender === "function") scheduleRender();
  try {
    const r = await shadowPost("/api/shadow/settings/autonomy", patch);
    const body = (r && r.ok) ? await r.json() : null;
    if (body && S.shadowSettings){
      S.shadowSettings.autonomy = Object.assign(
        {}, S.shadowSettings.autonomy, {
          level: body.level,
          levels: body.levels,
          confirm_top_tier: body.confirm_top_tier,
          worker_may_write: body.worker_may_write,
          worker_mode: body.worker_mode,
        });
    }
    if (typeof showNudge === "function"){
      if (!body){
        showNudge("That did not stick — try again");
      } else if (patch.level !== undefined){
        const name = (SH_LEVELS.find(p => p[0] === body.level) || [])[1] || "";
        /* HELD IS SAID OUT LOUD. Lowering to L0/L1 parks running tasks, and a
           founder who is not told that reads the still-listed rows as the
           setting having failed. */
        showNudge("Autonomy is " + body.level + " " + name
          + (body.held ? " — " + body.held + " waiting for you." : "."));
      } else {
        showNudge(body.confirm_top_tier
          ? "Shadow will ask once before it first acts."
          : "Shadow will not ask before it acts.");
      }
    }
  } catch (e) {
    if (typeof showNudge === "function")
      showNudge("That did not stick — try again");
  }
  S.shadowAutonomyBusy = false;
  loadShadowSettings(true);
  loadShadowHome(true);
}

async function shadowSetRunLimit(n){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  if (S.shadowRunLimitBusy) return;
  S.shadowRunLimitBusy = true;
  if (typeof scheduleRender === "function") scheduleRender();
  try {
    const r = await shadowPost("/api/shadow/settings/tasks",
                               { running_at_once: Number(n) });
    const body = (r && r.ok) ? await r.json() : null;
    if (body && S.shadowSettings){
      /* fold the answer into the settings object the page already reads --
         one state, not a second copy of the cap living beside it */
      S.shadowSettings.tasks = Object.assign({}, S.shadowSettings.tasks, {
        running_at_once: body.running_at_once,
        running_at_once_min: body.min,
        running_at_once_max: body.max,
        running_now: body.running_now,
        queued_now: body.queued_now,
      });
    }
    if (typeof showNudge === "function"){
      if (!body){
        showNudge("That limit did not stick — try again");
      } else if (body.starting){
        /* STARTING, not started: a promoted task may still have to spawn its
           worker, which is why the server does not await the drain. The list
           is what reports arrival. */
        showNudge("Running at once is " + body.running_at_once
          + " — starting " + body.starting + " that were waiting.");
      } else if (body.over_cap){
        showNudge("Running at once is " + body.running_at_once
          + " — " + body.over_cap + " already underway keep going.");
      } else {
        showNudge("Running at once is " + body.running_at_once + ".");
      }
    }
  } catch (e) {
    if (typeof showNudge === "function")
      showNudge("That limit did not stick — try again");
  }
  S.shadowRunLimitBusy = false;
  /* re-read rather than trust the fold: a promotion moves mission rows too,
     and the home is what draws them */
  loadShadowSettings(true);
  loadShadowHome(true);
}

/* Write "Budget per task" for ONE kind. `turns` of null resets it to auto.

   SAME THREE RULES AS THE CAP WRITER, for the same reasons: the server is the
   clamp so the row repaints from its ANSWER and never the requested value;
   `busy` holds both ends down for the round-trip so a fast double-click sends
   one write, not two; and the answer is folded into the settings object the
   page already reads rather than kept beside it.

   THE NUDGE SAYS "NEW TASKS ONLY" BECAUSE THAT IS THE ONE THING THE NUMBER
   ON SCREEN CANNOT SAY. max_turns is stamped onto a mission at create(), so
   a founder who raises the budget while three tasks are running will see none
   of them change, and a setting that appears not to have worked is worse than
   one that explains its own scope.

   AND IT DOES NOT RELOAD THE HOME, unlike the cap writer. That is deliberate,
   not an omission: raising the cap PROMOTES queued missions, so the home's
   rows move and have to be re-read. A budget change starts nothing and stops
   nothing -- no row moves, so there is nothing there to re-read. */
async function shadowSetTurnBudget(kind, turns){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  if (S.shadowBudgetBusy) return;
  S.shadowBudgetBusy = true;
  if (typeof scheduleRender === "function") scheduleRender();
  try {
    const r = await shadowPost("/api/shadow/settings/budget",
      { kind: kind, turns: turns === null ? null : Number(turns) });
    const body = (r && r.ok) ? await r.json() : null;
    if (body && S.shadowSettings){
      /* the whole map, not the one key: the row and all four Delegate-offer
         chips read off turn_budget, so patching one and trusting the rest is
         how a chip goes stale */
      S.shadowSettings.tasks = Object.assign({}, S.shadowSettings.tasks, {
        turn_budget: body.turn_budget,
        turn_budget_set: body.turn_budget_set,
        turn_budget_min: body.min,
        turn_budget_max: body.max,
      });
    }
    if (typeof showNudge === "function"){
      if (!body){
        showNudge("That budget did not stick — try again");
      } else if (body.auto){
        showNudge("Budget for " + body.kind + " is back to auto ("
          + body.turns + " turns).");
      } else {
        showNudge("Budget for " + body.kind + " is " + body.turns
          + " turns — new tasks only.");
      }
    }
  } catch (e) {
    if (typeof showNudge === "function")
      showNudge("That budget did not stick — try again");
  }
  S.shadowBudgetBusy = false;
  loadShadowSettings(true);
}

/* Write "Delegate offers" -- add or remove one kind.

   THE SERVER IS THE AUTHORITY, and the chips repaint from its answer rather
   than from the optimistic list. The same two reasons the cap stepper has:
   the server validates the name and can refuse it, and an add MINTS a kind
   with a budget only the server knows. Painting a chip and then discovering
   it was rejected is the failure this avoids.

   ONE VERB PER WRITE. The route refuses both together, and the UI has no
   gesture that produces both -- an add and a remove are two clicks.

   A REFUSAL IS SAID, NOT SWALLOWED. The store's message names the reason
   (the name, the ceiling, the last-offer floor), so it goes on the row where
   the founder is looking rather than only into a nudge that scrolls away. */
async function shadowOfferWrite(body, said){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  if (S.shadowOfferBusy) return;
  S.shadowOfferBusy = true;
  S.shadowOfferErr = null;
  if (typeof scheduleRender === "function") scheduleRender();
  try {
    const r = await shadowPost("/api/shadow/settings/offers", body);
    const answer = (r && r.ok) ? await r.json() : null;
    if (answer && S.shadowSettings){
      /* offers AND the budget map together: a minted kind arrives with a
         budget, and a chip that could not state its turns would render bare */
      S.shadowSettings.tasks = Object.assign({}, S.shadowSettings.tasks, {
        offers: answer.offers,
        offers_min: answer.min,
        offers_max: answer.max,
        turn_budget: answer.turn_budget,
        turn_budget_kinds: answer.turn_budget_kinds,
      });
    }
    if (!answer){
      /* the route answers 400 with the store's own sentence; prefer it to a
         generic line, because "at least 1 delegate offer" tells the founder
         what to do and "did not stick" does not */
      let why = null;
      try { why = ((await r.json()) || {}).detail; } catch (e) {}
      S.shadowOfferErr = why || "That did not stick — try again.";
    } else {
      S.shadowOfferAdding = false;
      S.shadowOfferDraft = "";
      if (typeof showNudge === "function") showNudge(said(answer));
    }
  } catch (e) {
    S.shadowOfferErr = "Could not reach Shadow — try again.";
  }
  S.shadowOfferBusy = false;
  /* re-read rather than trust the fold: the Delegate form reads offers too */
  loadShadowSettings(true);
}

function shadowOfferAdd(){
  if (typeof S === "undefined") return;
  const name = String(S.shadowOfferDraft || "").trim();
  if (!name){
    /* an empty box is not a refusal worth a round-trip */
    S.shadowOfferErr = "Name the kind of work first.";
    if (typeof scheduleRender === "function") scheduleRender();
    return;
  }
  return shadowOfferWrite({ add: name },
    (a) => "Shadow now offers " + a.offers.length + " kinds of work.");
}

function shadowOfferRemove(name){
  return shadowOfferWrite({ remove: name },
    () => "Shadow no longer offers " + name + ". Tasks already created keep "
      + "the kind they started with.");
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
