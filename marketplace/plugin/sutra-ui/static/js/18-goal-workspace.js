/* 18-goal-workspace.js -- V5 slice 7: the Goal workspace.

   A Goal is the persistent commitment for ONE chat. It is not a second
   agent and not a dashboard: when a goal is open it OWNS the main content
   area, with the supervisor panel beside the real target chat.

     Sutra nav -> Shadow -> selected Goal -> [ Goal panel | Target chat ]

   Two screens, both under the existing `focus` destination, so no new
   top-level navigation is introduced:

     SCREENS.goals   the list ("< All goals" lands here)
     SCREENS.goal    the workspace for S.goalSel

   REUSE, not reinvention:
     - shadowPost / esc / escAttr / showNudge      (existing helpers)
     - isOwnTurn (15-shadow-overlay)               Shadow-authored detection
     - shadowChatLabel (16-shadow-home)            real chat names
     - GET /api/sessions/{sid}                     the EXISTING transcript
     - a live pane's own s.turns                   the EXISTING ws stream
     - submitTurn(text, sid)                       the EXISTING /ws/chat send
   Nothing here opens a socket, polls, or renders a synthetic conversation. */
"use strict";

/* ---- pure helpers (node-tested directly) -------------------------------- */

/* the semantic colour family per state -- alert for blocked, deep green for
   done, slate for verifying, brown for a decision pending. Never red: a
   blocked goal is alive and waiting, not failed. */
const GOAL_STATE_CLASS = {
  draft: "gwst-draft", working: "gwst-working", verifying: "gwst-verifying",
  blocked: "gwst-blocked", done: "gwst-done", stopped: "gwst-stopped",
};

function goalStateClass(state){
  return GOAL_STATE_CLASS[String(state || "")] || "gwst-draft";
}

/* block_reason is an engine enum; the founder reads English. */
const GOAL_BLOCKER_COPY = {
  budget_exhausted: "the turn budget ran out",
  ping_pong: "the chat kept repeating itself",
  /* Shadow had no runtime to speak through -- the chat exists and is
     untouched, so this is a retryable outage, never a failed attempt. */
  no_live_runtime: "that chat isn't available to Shadow right now",
};
/* blockers where nothing was spent and the same attempt can simply be tried
   again -- they change which controls are honest to offer */
const GOAL_RETRYABLE_BLOCKERS = ["no_live_runtime"];
function goalBlockerRetryable(d){
  return GOAL_RETRYABLE_BLOCKERS.includes(String((d || {}).block_reason || ""));
}

function goalBlockerCopy(reason){
  const r = String(reason || "");
  if (!r) return "";
  return GOAL_BLOCKER_COPY[r] || r.replace(/_/g, " ");
}

/* The outstanding founder_confirm check, or null. This is what makes the
   `verifying` confirmation action offerable without new backend data: the
   detail payload already carries every check's tier, met flag and index. */
function goalPendingConfirm(d){
  for (const c of ((d && d.checks) || []))
    if (c.tier === "founder_confirm" && !c.met) return c;
  return null;
}

/* which actions make sense in this state -- and only those. Every one maps
   to an action the Goal API already implements (slice 6): start · resume ·
   stop · confirm, plus takeover, which is the existing /ws/chat path. */
function goalActions(state, d){
  switch (String(state || "")){
    case "draft":     return [{ act: "start", label: "Start", pri: true }];
    case "working":   return [{ act: "stop", label: "Stop" },
                              { act: "takeover", label: "Take over chat" }];
    case "verifying": {
      const pending = goalPendingConfirm(d);
      const acts = [];
      /* only offered when a founder_confirm check is actually outstanding --
         never a button that would have nothing to confirm */
      if (pending) acts.push({ act: "confirm", label: "Confirm done",
                               pri: true, index: pending.index });
      acts.push({ act: "stop", label: "Stop" });
      return acts;
    }
    case "blocked": {
      /* Extend budget is only honest when the budget is what ran out. On a
         no_live_runtime block the attempt died at turn 0/20, and offering
         more turns would point the founder at the wrong problem. */
      const acts = [{ act: "resume", label: goalBlockerRetryable(d)
                        ? "Try again" : "Answer & resume", pri: true }];
      if (String((d || {}).block_reason || "") === "budget_exhausted")
        acts.push({ act: "extend", label: "Extend budget" });
      acts.push({ act: "stop", label: "Stop" });
      return acts;
    }
    default:          return [];        /* done / stopped are terminal */
  }
}

/* What Shadow is doing, composed ONLY from fields the payload already has:
   state, attempt, turn_label and the unmet checks. No narration is
   generated and nothing is inferred -- if a fact is absent the clause is
   simply omitted rather than filled in. */
function goalActivityLine(d){
  if (!d) return "";
  const unmet = (d.unmet || [])[0] || null;
  switch (String(d.state || "")){
    case "draft":
      return "Not started. Shadow does nothing until you start it.";
    case "working":
      return unmet ? ("Working through this chat toward: " + unmet)
                   : "Working through this chat.";
    case "verifying":
      return unmet ? ("The chat says it is done. Waiting on: " + unmet)
                   : "The chat says it is done — checking.";
    case "blocked":
      return goalBlockerRetryable(d)
        ? "Nothing was sent and no turn was used. The chat is untouched."
        : "Stopped and waiting for you. The chat is still alive.";
    case "done":
      return "Verified. Shadow has stopped speaking into this chat.";
    case "stopped":
      return "You stopped this goal. Nothing is running.";
    default:
      return "";
  }
}

/* the two facts, never blended into a third. `2 of 3 checks` and
   `turn 11/20` come straight from the Goal API -- no percentage is ever
   synthesised here. */
function goalProgressText(d){
  const checks = (d && d.checks_label) || "0 of 0 checks";
  const turns = (d && d.turn_label) || null;
  return turns ? (checks + " · " + turns) : checks;
}

/* ---- list ---------------------------------------------------------------- */

function goalCardHtml(row){
  const blocked = row.state === "blocked";
  return `<div class="gwcard${blocked ? " gwcard-blocked" : ""}"
    data-goalopen="${escAttr(row.id)}">
    <div class="gwcardtop">
      <span class="gwstate ${goalStateClass(row.state)}">${esc(row.state)}</span>
      <span class="gwoutcome">${esc(row.outcome || "")}</span>
    </div>
    <div class="gwmeta">${esc(goalProgressText(row))}${
      row.attempt ? " · attempt " + esc(String(row.attempt)) : ""
    } · ${esc(shadowChatLabel(row.target_session))}</div>
    ${blocked && row.block_reason
      ? `<div class="gwblockline">needs you: ${
          esc(goalBlockerCopy(row.block_reason))}</div>`
      : ""}
    <div class="gwstamp">${esc(row.updated_at || "")}</div>
  </div>`;
}

function goalsListHtml(rows){
  rows = rows || [];
  /* blocked first -- the one state that is waiting on a person */
  const order = { blocked: 0, verifying: 1, working: 2, draft: 3,
                  done: 4, stopped: 5 };
  const sorted = rows.slice().sort((a, b) =>
    (order[a.state] == null ? 9 : order[a.state])
    - (order[b.state] == null ? 9 : order[b.state]));
  if (!sorted.length){
    return `<div class="zero"><h4>Goals</h4>
      <p>No goals yet. Give Shadow an outcome for a chat and it will drive
      it there.</p></div>`;
  }
  return `<div class="gwlist">${sorted.map(goalCardHtml).join("")}</div>`;
}

/* ---- the workspace ------------------------------------------------------- */

function goalBarHtml(d){
  /* ONE way back. The bar also carries the outcome and the state, so the
     founder always knows which goal owns the screen. */
  return `<div class="gwbar">
    <button class="btn gwback" type="button" data-goalback="1">‹ All
      goals</button>
    <span class="gwbardot">·</span>
    <span class="gwbaroutcome">${esc(d.outcome || "")}</span>
    <span class="gwstate ${goalStateClass(d.state)}">${esc(d.state)}</span>
  </div>`;
}

function goalChecksHtml(checks){
  if (!checks || !checks.length){
    return `<div class="gwempty">No checks on this goal yet.</div>`;
  }
  return `<div class="gwchecks">${checks.map(c => `
    <div class="gwcheck${c.met ? " gwcheck-met" : ""}">
      <span class="gwtick">${c.met ? "✓" : "○"}</span>
      <span class="gwchecktext">${esc(c.check || "")}</span>
      <span class="gwtier">${esc(c.tier || "")}</span>
    </div>`).join("")}</div>`;
}

function goalLearnedHtml(items){
  if (!items || !items.length) return "";
  return `<div class="gwsect"><div class="gwsecthead">What I learned</div>
    ${items.map(it => `<div class="gwlearn">
      <span class="gwlearnkind">${esc(String(it.kind || "")
        .replace(/_/g, " "))}</span>
      <span class="gwlearntext">${esc(it.text || "")}</span>
    </div>`).join("")}</div>`;
}

/* Attempt history from the EXISTING attempt records. The live attempt has
   no ended_state yet, so it reads as the goal's own state rather than a
   guess; a finished one reads as how it ended plus its recorded reason,
   humanised through the same map the blocker uses. */
function goalAttemptsHtml(attempts, d){
  if (!attempts || !attempts.length) return "";
  const live = String((d && d.state) || "");
  const rows = attempts.slice().reverse().map(a => {
    const ended = a.ended_state || null;
    const label = ended || (live || "running");
    /* a note that only restates the outcome ("ended done") adds nothing
       next to the pill; only a note that CARRIES a reason is shown */
    const raw = ended && a.note ? String(a.note) : "";
    const why = (!raw || raw === "ended " + ended || raw === ended)
      ? "" : goalBlockerCopy(raw);
    return `<div class="gwattempt">
      <div class="gwattline">
        <span class="gwattno">Attempt ${esc(String(a.attempt || ""))}</span>
        <span class="gwattend ${goalStateClass(label)}">${esc(label)}</span>
      </div>
      ${why ? `<div class="gwattwhy">${esc(why)}</div>` : ""}
    </div>`;
  }).join("");
  return `<div class="gwsect"><div class="gwsecthead">Attempts</div>
    ${rows}</div>`;
}

/* The current attempt, made understandable out of existing progress data:
   which attempt, how much budget it has spent, and every check. */
function goalCurrentAttemptHtml(d){
  if (!d || ["done", "stopped", "draft"].includes(String(d.state || "")))
    return "";
  const n = d.attempt || 0;
  if (!n) return "";
  return `<div class="gwsect gwnow">
    <div class="gwsecthead">Current attempt</div>
    <div class="gwnowline">
      <span class="gwnowatt">Attempt ${esc(String(n))}</span>
      ${d.turn_label ? `<span class="gwnowturn">${
        esc(d.turn_label)}</span>` : ""}
    </div>
    <div class="gwnowchecks">${esc(d.checks_label || "")}</div>
  </div>`;
}

function goalBlockedHtml(d){
  if (d.state !== "blocked") return "";
  const unmet = (d.unmet || []).join("; ");
  return `<div class="gwblocked">
    <div class="gwblockedhead">Shadow needs you</div>
    <div class="gwblockedwhy">${esc(goalBlockerCopy(d.block_reason))}${
      unmet ? ". Still unmet: " + esc(unmet) : ""}</div>
    <div class="gwblockedprog">${esc(d.checks_label || "")}${
      d.turn_label ? " · " + esc(d.turn_label) : ""}${
      d.attempt ? " · attempt " + esc(String(d.attempt)) : ""}</div>
    <div class="gwblockednote">${goalBlockerRetryable(d)
      ? `Nothing was sent into the chat and no turn was used \u2014 try
         again, or take over on the right.`
      : `The chat is still alive. Answer below, extend the budget, or take
         over on the right.`}</div>
  </div>`;
}

function goalVerifyingHtml(d){
  if (d.state !== "verifying") return "";
  const pending = goalPendingConfirm(d);
  return `<div class="gwverifying">
    <div class="gwverifyinghead">Chat says done — checking</div>
    <div class="gwverifyingwhy">${pending
      ? "Waiting on your sign-off: " + esc(pending.check)
      : "Shadow is settling the remaining checks."}</div>
    <div class="gwverifyingprog">${esc(d.checks_label || "")}</div>
  </div>`;
}

function goalDoneHtml(d){
  if (d.state !== "done") return "";
  return `<div class="gwverified">
    <div class="gwverifiedhead">✓ Verified</div>
    <div class="gwverifiedwhy">${esc(d.checks_label || "")} — every
      check was evaluated, not claimed.</div>
  </div>`;
}

function goalStoppedHtml(d){
  if (d.state !== "stopped") return "";
  return `<div class="gwstopped">
    <div class="gwstoppedhead">Stopped</div>
    <div class="gwstoppedwhy">You stopped this goal. Its progress and
      history are kept: ${esc(d.checks_label || "")}.</div>
  </div>`;
}

function goalActionsHtml(d){
  const acts = goalActions(d.state, d);
  if (!acts.length){
    /* terminal: say so, rather than leaving a bare gap where controls were */
    return `<div class="gwnoacts">No execution controls — this goal is
      ${esc(d.state)}.</div>`;
  }
  return `<div class="gwacts">${acts.map(a => `
    <button class="btn ${a.pri ? "pri " : ""}gwact" type="button"
      data-goalact="${escAttr(a.act)}"${
      a.index == null ? "" : ` data-goalindex="${escAttr(String(a.index))}"`}
      data-goalid="${escAttr(d.id)}">${esc(a.label)}</button>`).join("")}</div>`;
}

function goalPanelHtml(d){
  return `<div class="gwpanel">
    <div class="gwsect">
      <div class="gwsecthead">Outcome</div>
      <div class="gwpaneloutcome">${esc(d.outcome || "")}</div>
      <div class="gwstatusline">
        <span class="gwstate ${goalStateClass(d.state)}">${
          esc(d.state)}</span>
        <span class="gwprogress">${esc(goalProgressText(d))}</span>
      </div>
      <div class="gwactivity">${esc(goalActivityLine(d))}</div>
    </div>
    ${goalBlockedHtml(d)}${goalVerifyingHtml(d)}${goalDoneHtml(d)}${
      goalStoppedHtml(d)}
    ${goalCurrentAttemptHtml(d)}
    <div class="gwsect">
      <div class="gwsecthead">Checks</div>
      ${goalChecksHtml(d.checks)}
    </div>
    ${goalLearnedHtml(d.learned)}
    ${goalAttemptsHtml(d.attempts, d)}
    <div class="gwfoot">
      ${goalActionsHtml(d)}
      <div class="gwcomposer gwtoshadow">
        <div class="gwcomplabel">YOU → SHADOW</div>
        <div class="gwcomphint">Guidance about this goal. Kept with the goal,
          never sent into the chat.</div>
        <textarea class="gwcompose" data-goalshadow="${escAttr(d.id)}"
          placeholder="Tell Shadow what it is missing…"></textarea>
      </div>
    </div>
  </div>`;
}

/* ---- the target chat ----------------------------------------------------- */

/* A live pane's turns, folded back into transcript-shaped messages. This is
   the inverse of transcriptTurns() and exists so the pane can read the
   SAME live state the ordinary chat pane streams into -- no second stream. */
function goalTurnsToMessages(turns){
  const out = [];
  (turns || []).forEach(t => {
    if (t.text) out.push({ role: "user", text: t.text, ts: t.ts || "" });
    if (t.response) out.push({ role: "assistant", text: t.response,
                               ts: t.ts || "" });
  });
  return out;
}

/* The tag is what MAKES a turn identifiable as Shadow's (and what keeps it
   out of verification evidence server-side) -- but once the row is labelled
   "Shadow · mission" the prefix is said twice. Strip it for display only;
   the underlying text is never altered. */
function goalStripTag(text){
  return String(text || "").replace(/^\s*\[Shadow · mission [^\]]*\]\s*/, "");
}

/* the real transcript for this chat -- ONE source, chosen, never merged.

   WHY THE CHOICE MATTERS (live, 2026-09-11): this preferred the pane's
   `turns` array whenever it was non-empty. That array is live ONLY while
   its pane is open and its websocket is writing into it; a CLOSED pane
   holds a frozen snapshot from whenever the founder last read that chat.
   Shadow drives an Assignment's target chat headlessly, with no pane open,
   so the closed case is the normal one here -- and the snapshot won
   unconditionally, which meant the transcript refetched every few seconds
   into S.goalTranscript was fetched and then thrown away. The RHS looked
   static while Shadow and the chat were talking.

   Merging the two would be the obvious alternative and the wrong one: they
   overlap, so it would double every turn that appears in both. */
function goalMessages(sid){
  const S_ = (typeof S !== "undefined") ? S : {};
  const sess = (S_.sessions || []).find(x => x && x.id === sid);
  const pane = (sess && sess.turns && sess.turns.length)
    ? goalTurnsToMessages(sess.turns) : null;
  /* an OPEN pane owns its turns: its socket holds the streaming turn and
     the file on disk is behind it (see 09-tail.js's same reasoning) */
  const paneOpen = !!(pane && S_.openPanes
                      && S_.openPanes.indexOf(sid) !== -1);
  if (paneOpen) return pane;
  const held = (S_.goalTranscript || {})[sid];
  if (held !== undefined) return held;
  /* nothing fetched yet: a stale snapshot still beats "Reading the chat…" */
  return pane === null ? undefined : pane;
}

/* ---- live RHS ------------------------------------------------------------
   The session stream already exists and already fires on every transcript
   write (/api/sessions/stream -> applySessionChange). It re-reads the file
   for OPEN PANES only, and an Assignment's target chat is deliberately not
   one -- Shadow drives it headlessly. This is the one line of reach that
   the workspace needs: the same event, the same 1s throttle, and the
   EXISTING loadGoalTranscript fetch. No socket is added, no second
   transcript store exists, and no pane state is touched. */
let goalTranscriptAt = 0;

/* the chat an open Assignment workspace is watching, or null */
function goalWatchedSession(){
  const S_ = (typeof S !== "undefined") ? S : {};
  if (S_.screen !== "goal" || !S_.goalSel) return null;
  const d = (S_.goalDetail || {})[S_.goalSel];
  return (d && d.target_session) || null;
}

function goalTranscriptChanged(sid){
  if (!sid || goalWatchedSession() !== sid) return false;
  const S_ = (typeof S !== "undefined") ? S : {};
  /* an open pane is already re-read by 09-tail.js on this same event --
     doing it twice would be two GETs for one write */
  if (S_.openPanes && S_.openPanes.indexOf(sid) !== -1) return false;
  const now = Date.now();
  /* the pane path's own throttle: a running turn rewrites the file many
     times a second, and a GET + full render on each one IS the flicker */
  if (goalTranscriptAt && now - goalTranscriptAt < 1000) return false;
  goalTranscriptAt = now;
  loadGoalTranscript(sid);
  return true;
}

function goalTranscriptHtml(messages, d){
  if (messages === undefined){
    return `<div class="gwempty">Reading the chat…</div>`;
  }
  if (!messages || !messages.length){
    return `<div class="gwempty">Nothing in this chat yet.</div>`;
  }
  const rows = messages.map(m => {
    /* Shadow can only ever inject a USER turn, and it always carries the
       tag -- the same predicate the overlay uses to spot its own turns. */
    const mine = m.role === "user"
      && typeof isOwnTurn === "function" && isOwnTurn(m.text);
    const cls = mine ? "gwturn gwturn-shadow"
      : (m.role === "user" ? "gwturn gwturn-founder"
                           : "gwturn gwturn-chat");
    const who = mine ? "Shadow · mission"
      : (m.role === "user" ? "you" : "chat");
    return `<div class="${cls}">
      <span class="gwwho">${esc(who)}</span>
      <span class="gwturntext">${esc(mine ? goalStripTag(m.text)
                                          : (m.text || ""))}</span>
    </div>`;
  }).join("");
  /* the stop explanation belongs where the work ended, not only in a side
     panel: it turns a trailing-off into an explanation */
  const stopped = (d && d.state === "blocked")
    ? `<div class="gwstopmark">Shadow stopped here · ${
        esc(d.turn_label || "")} · ${
        esc(goalBlockerCopy(d.block_reason))}</div>`
    : "";
  return `<div class="gwturns" data-gwsid="${
    escAttr((d && d.target_session) || "")}">${rows}${stopped}</div>`;
}

/* ---- autoscroll ---------------------------------------------------------
   render() replaces the pane wholesale, so .gwturns is a BRAND NEW element
   at scrollTop 0 on every rebuild. Same two states the session panes already
   keep apart (06-render.js), same 24px slop, same __pinning guard:

     PINNED  the founder is at the bottom watching work arrive -> follow the
             tail as turns land
     PARKED  the founder scrolled up to read -> keep their exact offset.
             Yanking someone to the tail while they are reading is the worse
             failure, so `pinned` requires genuinely being at the bottom.

   Returning to the bottom clears the flag, so following resumes naturally.
   No polling, no timers, no second transcript or state system -- this rides
   the existing render lifecycle and the existing live session turns. */
const GOAL_PIN_SLOP = 24;      /* px, matching SESS_PIN_SLOP */

function goalAtBottom(el){
  if (!el) return true;
  return (el.scrollHeight - el.clientHeight - el.scrollTop) <= GOAL_PIN_SLOP;
}

/* captured BEFORE the rebuild */
function goalScrollState(){
  if (typeof document === "undefined" || !document.querySelector) return null;
  const el = document.querySelector(".gwturns");
  if (!el) return null;
  const sid = (el.dataset && el.dataset.gwsid) || "";
  const S_ = (typeof S !== "undefined") ? S : {};
  /* recorded intent outranks a transient measurement: if the founder has
     scrolled away, a mid-rebuild reading must not re-pin them */
  const away = !!(S_.goalUserScrolled || {})[sid];
  return { sid: sid, top: el.scrollTop,
           pinned: away ? false : goalAtBottom(el) };
}

/* restored AFTER the rebuild */
function goalRestoreScroll(prior){
  if (!prior || typeof document === "undefined") return;
  const apply = () => {
    const el = document.querySelector && document.querySelector(".gwturns");
    if (!el) return;                    /* workspace closed during rebuild */
    el.__pinning = true;                /* OUR scroll, not the founder's */
    el.scrollTop = prior.pinned
      ? el.scrollHeight
      : Math.min(prior.top, Math.max(0, el.scrollHeight - el.clientHeight));
    if (typeof requestAnimationFrame === "function")
      requestAnimationFrame(() => { el.__pinning = false; });
    else el.__pinning = false;
  };
  apply();
  /* once more after layout: a turn whose height settles late would otherwise
     leave a pinned reader short of the tail */
  if (typeof requestAnimationFrame === "function")
    requestAnimationFrame(apply);
}

/* bound once per element; the listener is what records founder intent */
function goalBindScroll(){
  if (typeof document === "undefined" || !document.querySelector) return;
  const el = document.querySelector(".gwturns");
  if (!el || el.__gwBound || !el.addEventListener) return;
  el.__gwBound = true;
  el.addEventListener("scroll", () => {
    if (el.__pinning) return;           /* ignore the scroll we just did */
    if (typeof S === "undefined") return;
    if (!S.goalUserScrolled) S.goalUserScrolled = {};
    const sid = (el.dataset && el.dataset.gwsid) || "";
    if (goalAtBottom(el)) delete S.goalUserScrolled[sid];  /* resume */
    else S.goalUserScrolled[sid] = true;                   /* park */
  }, { passive: true });
}

function goalChatHtml(d){
  const sid = d.target_session;
  return `<div class="gwchat">
    <div class="gwchathead">Target chat · ${
      esc(shadowChatLabel(sid))}</div>
    ${goalTranscriptHtml(goalMessages(sid), d)}
    <div class="gwcomposer gwtochat">
      <div class="gwcomplabel gwcomplabel-alert">YOU → CHAT · ${
        esc(shadowChatLabel(sid))}</div>
      <textarea class="gwcompose" data-goalchat="${escAttr(sid)}"
        placeholder="Type here and you take over — Shadow pauses in this
chat."></textarea>
    </div>
  </div>`;
}

function goalWorkspaceHtml(){
  const S_ = (typeof S !== "undefined") ? S : {};
  if (S_.goalDark){
    return `<div class="zero"><h4>Goals</h4>
      <p>Shadow is not enabled. Turn it on in Settings to give Shadow an
      outcome for a chat.</p></div>`;
  }
  const gid = S_.goalSel;
  const d = (S_.goalDetail || {})[gid];
  if (!gid) return goalsListHtml(S_.goals);
  if (!d) return `<div class="zero"><h4>Goal</h4><p>Looking…</p></div>`;
  return `<div class="gw">
    ${goalBarHtml(d)}
    <div class="gwcols">${goalPanelHtml(d)}${goalChatHtml(d)}</div>
  </div>`;
}

/* ---- creation: the confirmation card (slice 8) ---------------------------
   Shadow already interprets natural language and already answers in fenced
   blocks (shadow_protocol). A `goal` block arrives here as a PROPOSAL --
   nothing has been created, nothing is stored server-side. This card is the
   confirmation step: it separates what the founder ASKED from what Shadow
   BELIEVES the outcome is from what will COUNT as done, lets the founder
   edit any of it, and only their Confirm writes anything.

   It renders inside the existing Shadow thread, next to mission cards, so
   creation is an extension of Shadow rather than a second surface. */

function goalProposalKey(p){
  /* stable per-proposal id so two proposals in one thread edit separately */
  return "gp-" + String((p && p.ts) || 0);
}

/* the founder's edits live in ordinary UI state, keyed by proposal -- the
   goal itself is never duplicated on the client */
function goalDraftFor(p){
  const S_ = (typeof S !== "undefined") ? S : {};
  if (!S_.goalDrafts) S_.goalDrafts = {};
  const k = goalProposalKey(p);
  if (!S_.goalDrafts[k]){
    S_.goalDrafts[k] = {
      outcome: p.outcome || "",
      /* one check per line, so editing needs no new widget */
      criteria: (p.done_when || []).map(c => c.check).join("\n"),
      target_session: p.target_session || null,
    };
  }
  return S_.goalDrafts[k];
}

/* THE TIER CONTRACT, mirrored from shadow_protocol.tier_for (python).
   Two copies is the smaller evil: the alternative is a round-trip to the
   server to classify text the founder is still typing.

   This function used to stamp `contains_artifact` on EVERY line -- Shadow's
   proposed tiers and the founder's own typing alike -- which is what made
   the protocol-side fix insufficient on its own. contains_artifact is a
   literal substring test (mission_engine:284); a line that is a criterion
   DESCRIPTION can never match it, and the attempt then repeats itself until
   the ping-pong guard stops it (live: goal g-d804849d1400, 2026-09-11).

   A literal artifact is a MARKER, not a sentence. Conservative on purpose:
   a false negative costs one sign-off, a false positive costs the goal. */
const GOAL_ARTIFACT_MAX_CHARS = 60;
const GOAL_ARTIFACT_MAX_WORDS = 8;
const GOAL_CRITERION_MARKER =
  /(—|–|\b(?:not|rather|instead|each|either|such as|e\.g\.|etc|distinct|concrete|explicit(?:ly)?|genuine|generic|appropriate|relevant|valid|reasonable|must|should|listed|stated|named|tied|hedge|at least|no more than)\b)/i;

function goalIsLiteralArtifact(check){
  const s = String(check == null ? "" : check).trim();
  if (!s || s.length > GOAL_ARTIFACT_MAX_CHARS) return false;
  if (s.split(/\s+/).length > GOAL_ARTIFACT_MAX_WORDS) return false;
  return !GOAL_CRITERION_MARKER.test(s);
}

function goalTierFor(check, proposed){
  const want = String(proposed == null ? "" : proposed).trim();
  if (want === "contains_artifact" && goalIsLiteralArtifact(check))
    return "contains_artifact";
  if (want === "founder_confirm") return "founder_confirm";
  return "founder_confirm";
}

/* What each tier COSTS the founder, said plainly on the card. */
const GOAL_TIER_WORD = {
  contains_artifact: "Shadow checks this",
  founder_confirm: "you confirm this",
};

function goalCriteriaToChecks(text, proposedByText){
  const by = proposedByText || {};
  return String(text || "").split("\n")
    .map(s => s.trim()).filter(Boolean)
    .map(check => {
      const proposed = by[check];
      /* TWO DIFFERENT QUESTIONS, deliberately answered differently.
         A line SHADOW proposed is judged by goalTierFor, mirroring the
         python boundary exactly -- including "a missing tier means Shadow
         did not think about it, so the founder decides".
         A line the FOUNDER TYPED has no proposal behind it at all: the
         widget is a plain textarea and has no tier to omit. Shape is the
         only signal there is, and a literal-shaped marker genuinely IS
         substring-matchable -- refusing to machine-check it would make
         contains_artifact unreachable from the UI without buying any
         safety, which is a different bug, not a fix for this one. */
      const tier = (proposed === undefined)
        ? (goalIsLiteralArtifact(check) ? "contains_artifact"
                                        : "founder_confirm")
        : goalTierFor(check, proposed);
      return { tier: tier, check: check };
    });
}

/* the proposal's own tiers, keyed by check text, so an unedited line keeps
   whatever the protocol boundary already resolved for it */
function goalProposedTiers(p){
  const out = {};
  for (const c of ((p && p.done_when) || []))
    if (c && c.check) out[String(c.check).trim()] = c.tier;
  return out;
}

function goalProposalHtml(p){
  const d = goalDraftFor(p);
  const key = goalProposalKey(p);
  const checks = goalCriteriaToChecks(d.criteria, goalProposedTiers(p));
  const created = p.createdId || null;
  const target = d.target_session;
  const ready = !!(String(d.outcome || "").trim()) && checks.length > 0
    && !!target;
  if (created){
    /* created: draft on the server, awaiting the EXISTING Start action */
    return `<div class="gwprop gwprop-made" data-gwprop="${escAttr(key)}">
      <div class="gwprophead">Goal created · draft</div>
      <div class="gwpropoutcome">${esc(d.outcome)}</div>
      <div class="gwpropmeta">${esc(String(checks.length))} check${
        checks.length === 1 ? "" : "s"} · ${esc(shadowChatLabel(target))}</div>
      <div class="gwpropnote">Nothing is running yet. Start when you are
        ready.</div>
      <div class="gwpropacts">
        <button class="btn pri" type="button"
          data-gwpropstart="${escAttr(created)}">Start</button>
        <button class="btn" type="button"
          data-gwpropopen="${escAttr(created)}">Open goal</button>
      </div>
      ${p.error ? `<div class="gwproperr">${esc(p.error)}</div>` : ""}
    </div>`;
  }
  return `<div class="gwprop" data-gwprop="${escAttr(key)}">
    <div class="gwprophead">Set a goal for this chat?</div>
    ${p.asked ? `<div class="gwpropasked">
      <span class="gwproplabel">You asked</span>
      <span class="gwpropasktext">${esc(p.asked)}</span></div>` : ""}
    <div class="gwpropfield">
      <span class="gwproplabel">Outcome — what Shadow will pursue</span>
      <textarea class="gwpropin" data-gwpropoutcome="${escAttr(key)}"
        placeholder="One sentence: what must be true">${esc(d.outcome)}</textarea>
    </div>
    <div class="gwpropfield">
      <span class="gwproplabel">Done when — what will count as done</span>
      ${p.needs_criteria && !d.criteria ? `<div class="gwpropask">
        Shadow could not tell what would count as done from that. Say what
        to check — one per line — and it will not guess.</div>` : ""}
      <textarea class="gwpropin" data-gwpropcriteria="${escAttr(key)}"
        placeholder="One check per line">${esc(d.criteria)}</textarea>
      <div class="gwpropcount">${esc(String(checks.length))} check${
        checks.length === 1 ? "" : "s"}</div>
      ${checks.length ? `<div class="gwproptiers">${checks.map(c => `
        <div class="gwproptier">
          <span class="gwtier">${esc(GOAL_TIER_WORD[c.tier] || c.tier)}</span>
          <span class="gwproptiertext">${esc(c.check)}</span>
        </div>`).join("")}</div>` : ""}
    </div>
    <div class="gwpropfield">
      <span class="gwproplabel">Target chat</span>
      <span class="gwproptarget">${target
        ? esc(shadowChatLabel(target))
        : "no chat in focus — open the chat's tab first"}</span>
    </div>
    <div class="gwpropnote">Shadow keeps working through this chat until the
      outcome is satisfied or it needs you. It does not start a new chat.</div>
    <div class="gwpropacts">
      <button class="btn pri" type="button" ${ready ? "" : "disabled "
        }data-gwpropcreate="${escAttr(key)}">Create goal</button>
      <button class="btn" type="button"
        data-gwpropcancel="${escAttr(key)}">Cancel</button>
    </div>
    ${p.error ? `<div class="gwproperr">${esc(p.error)}</div>` : ""}
  </div>`;
}

function goalProposalIn(key){
  const S_ = (typeof S !== "undefined") ? S : {};
  const thread = S_.shadowThread || [];
  for (const t of thread)
    if (t.goalProposal && goalProposalKey(t.goalProposal) === key)
      return t.goalProposal;
  return null;
}

/* Confirm: the ONE write. Uses the existing POST /api/shadow/goals, which
   creates in `draft` -- creation never starts work. */
async function goalCreateFromProposal(key){
  const p = goalProposalIn(key);
  if (!p || p.createdId) return null;
  const d = goalDraftFor(p);
  /* the SAME tiers the card showed -- what the founder read is what is
     written, never a different classification at POST time */
  const checks = goalCriteriaToChecks(d.criteria, goalProposedTiers(p));
  if (!String(d.outcome || "").trim() || !checks.length
      || !d.target_session){
    p.error = "An outcome, at least one check and a target chat are all "
      + "required.";
    if (typeof scheduleRender === "function") scheduleRender();
    return null;
  }
  let r = null;
  try {
    r = await shadowPost("/api/shadow/goals", {
      outcome: String(d.outcome).trim(),
      target_session: d.target_session,
      done_when: checks });
  } catch (e){ r = null; }
  if (!r || !r.ok){
    /* honest about the failure, including the one-active-goal 409 */
    let detail = "";
    try { detail = (await r.json()).detail || ""; } catch (e){ detail = ""; }
    p.error = r
      ? ("Could not create the goal (" + r.status + ")"
         + (detail ? ": " + detail : ""))
      : "Could not reach Shadow to create the goal.";
    if (typeof showNudge === "function") showNudge(p.error);
    if (typeof scheduleRender === "function") scheduleRender();
    return null;
  }
  const goal = await r.json();
  p.createdId = goal.id;
  p.error = null;
  if (typeof showNudge === "function")
    showNudge("Goal created — draft. Start it when you are ready.");
  await loadGoals();
  if (typeof scheduleRender === "function") scheduleRender();
  return goal;
}

/* Start: the EXISTING goal action, then reconcile with the server before
   claiming anything, because start is fire-and-forget. */
async function goalStartCreated(gid){
  if (!gid) return null;
  const r = await goalAct(gid, "start");      /* re-fetches goal + list */
  const S_ = (typeof S !== "undefined") ? S : {};
  const after = (S_.goalDetail || {})[gid] || null;
  if (!r || !r.ok){
    if (typeof showNudge === "function")
      showNudge("Start did not stick — the goal is still a draft");
    return null;
  }
  /* never claim it is working unless the SERVER says so */
  if (typeof showNudge === "function"){
    showNudge(after && after.state === "working"
      ? "Working — following it in the goal workspace"
      : "Start accepted — the workspace shows its real state");
  }
  openGoal(gid);                              /* the slice 7 workspace */
  return after;
}

function goalCancelProposal(key){
  const S_ = (typeof S !== "undefined") ? S : {};
  const thread = S_.shadowThread || [];
  const i = thread.findIndex(t => t.goalProposal
    && goalProposalKey(t.goalProposal) === key);
  if (i !== -1) thread.splice(i, 1);
  if (S_.goalDrafts) delete S_.goalDrafts[key];
  if (typeof scheduleRender === "function") scheduleRender();
  if (typeof renderShadowCard === "function") renderShadowCard();
}

/* ---- loaders ------------------------------------------------------------- */

async function loadGoals(){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  try {
    const r = await fetch("/api/shadow/goals");
    if (!r.ok){ S.goalDark = true;
      if (typeof scheduleRender === "function") scheduleRender(); return; }
    S.goalDark = false;
    const doc = await r.json();
    S.goals = doc.goals || [];
  } catch (e){ S.goalDark = true; }
  if (typeof scheduleRender === "function") scheduleRender();
}

async function loadGoal(gid){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  if (!S.goalDetail) S.goalDetail = {};
  try {
    const r = await fetch("/api/shadow/goals/" + encodeURIComponent(gid));
    if (!r.ok){
      if (r.status === 403) S.goalDark = true;
      if (typeof scheduleRender === "function") scheduleRender(); return;
    }
    S.goalDark = false;
    const d = await r.json();
    S.goalDetail[gid] = d;
    loadGoalTranscript(d.target_session);
  } catch (e){ /* keep the last known detail rather than blanking it */ }
  if (typeof scheduleRender === "function") scheduleRender();
}

/* the EXISTING session transcript endpoint -- the same one a restored pane
   reads. Fetched once per open; live updates ride the pane's own ws state
   through goalMessages(). No polling loop. */
async function loadGoalTranscript(sid){
  if (!sid || typeof fetch === "undefined" || typeof S === "undefined") return;
  if (!S.goalTranscript) S.goalTranscript = {};
  try {
    const r = await fetch("/api/sessions/" + encodeURIComponent(sid));
    S.goalTranscript[sid] = r.ok ? ((await r.json()).messages || []) : null;
  } catch (e){ S.goalTranscript[sid] = null; }
  if (typeof scheduleRender === "function") scheduleRender();
}

/* Keep the rail honest. openScreen() derives the owning destination from
   DEST_PLANES, and these two screens are deliberately NOT plane rows (no new
   rail entries), so it would leave S.ui.dest pointing at whatever the
   operator was on -- measured in the running app: the rail highlighted "Now"
   while the Goal workspace filled the screen. Goals live under Focus, the
   same destination Shadow lives under. */
function goalOwnDest(){
  if (typeof S === "undefined" || !S.ui) return;
  if (typeof DESTS !== "undefined" && !DESTS.includes("focus")) return;
  S.ui.dest = "focus";
}

/* ---- the live workspace ---------------------------------------------------
   SLICE 7 MADE THIS SCREEN FETCH-ONCE ("Nothing here opens a socket, polls,
   or renders a synthetic conversation"), and SCREENS.goal only calls
   loadGoal when NO detail is cached. goalAct() refetches after a founder
   action, which is why manual testing never caught it -- you only ever
   looked right after clicking something.

   Measured live (goal g-d804849d1400, 2026-09-11): the mission ran two
   turns, evaluated its checks and blocked in 107s while the open workspace
   kept showing the snapshot taken at Start -- "WORKING, turn 0/20, 0 of 2"
   for several minutes. Every change driven by the MISSION LOOP rather than
   by the founder had no path to the screen.

   The smallest honest fix: re-read the EXISTING endpoint, on the EXISTING
   loadGoal path, only while the goal can actually change, and only while
   its workspace is on screen. No socket, no new endpoint, no synthetic
   progress -- the screen shows server state or it shows nothing new.

   Chained setTimeout, not setInterval, for 07-loaders.js's stated reason:
   a slow response must not stack a queue of overlapping requests. */

/* states where the mission loop can still move something */
const GOAL_LIVE_STATES = ["working", "verifying"];
const GOAL_POLL_MS = 4000;
let goalPollTimer = null, goalPollGid = null, goalPollBusy = false;

function goalIsLive(d){
  return GOAL_LIVE_STATES.includes(String((d || {}).state || ""));
}

/* is this goal's workspace the thing actually on screen? */
function goalScreenOpen(gid){
  const S_ = (typeof S !== "undefined") ? S : {};
  return S_.screen === "goal" && S_.goalSel === gid;
}

function goalStopPoll(){
  if (goalPollTimer !== null && typeof clearTimeout === "function")
    clearTimeout(goalPollTimer);
  goalPollTimer = null;
  goalPollGid = null;
}

function goalStartPoll(gid){
  if (typeof setTimeout !== "function" || !gid) return;
  if (goalPollGid === gid && goalPollTimer !== null) return;   /* already on */
  goalStopPoll();
  goalPollGid = gid;
  const tick = async () => {
    goalPollTimer = null;
    if (!goalScreenOpen(gid)){ goalStopPoll(); return; }
    const S_ = (typeof S !== "undefined") ? S : {};
    const d = (S_.goalDetail || {})[gid];
    /* terminal or holding: the loop cannot move it, so stop asking */
    if (d && !goalIsLive(d)){ goalStopPoll(); return; }
    if (!goalPollBusy){
      goalPollBusy = true;
      try { await loadGoal(gid); }
      catch (e) {}
      finally { goalPollBusy = false; }
    }
    /* re-armed only AFTER the response, so one slow read delays the next
       tick instead of overlapping it */
    if (goalScreenOpen(gid) && goalPollGid === gid){
      const now = (((typeof S !== "undefined" && S.goalDetail) || {})[gid]);
      if (!now || goalIsLive(now)) goalPollTimer = setTimeout(tick, GOAL_POLL_MS);
      else goalStopPoll();
    }
  };
  goalPollTimer = setTimeout(tick, GOAL_POLL_MS);
}

/* called from SCREENS.goal on every paint: arms the poll for a live goal,
   disarms it the moment the goal stops being live. Idempotent. */
function goalSyncPoll(gid){
  const S_ = (typeof S !== "undefined") ? S : {};
  const d = (S_.goalDetail || {})[gid];
  if (gid && goalScreenOpen(gid) && (!d || goalIsLive(d))) goalStartPoll(gid);
  else goalStopPoll();
}

function openGoal(gid){
  if (typeof S === "undefined" || !gid) return;
  S.goalSel = gid;
  goalOwnDest();
  if (typeof openScreen === "function") openScreen("goal");
  else S.screen = "goal";
  goalOwnDest();                     /* openScreen may re-derive it */
  loadGoal(gid);
  goalStartPoll(gid);
  if (typeof render === "function") render();
}

function closeGoal(){
  if (typeof S === "undefined") return;
  goalStopPoll();                    /* leaving the workspace ends the poll */
  S.goalSel = null;
  goalOwnDest();
  if (typeof openScreen === "function") openScreen("goals");
  else S.screen = "goals";
  goalOwnDest();
  loadGoals();
  if (typeof render === "function") render();
}

/* ---- actions ------------------------------------------------------------- */

/* Slice 6: start/resume are FIRE-AND-FORGET -- the response says "accepted",
   not "running". So every action re-reads the goal instead of trusting the
   body it got back. */
async function goalAct(gid, action, extra){
  if (typeof fetch === "undefined") return null;
  const body = Object.assign({ action }, extra || {});
  let r = null;
  try {
    r = await shadowPost("/api/shadow/goals/" + encodeURIComponent(gid)
                         + "/act", body);
  } catch (e){ r = null; }
  if (typeof showNudge === "function"){
    if (!r || !r.ok){
      showNudge("That did not stick" + (r ? " (" + r.status + ")" : "")
                + " — try again");
    } else {
      const said = { start: "Starting — watch the chat on the right",
                     resume: "Resuming in the same chat",
                     stop: "Stopped.",
                     guidance: "Noted for this goal." };
      showNudge(said[action] || "Done.");
    }
  }
  /* reconcile with the server's ACTUAL state, never the action's echo */
  await loadGoal(gid);
  await loadGoals();
  if (typeof scheduleRender === "function") scheduleRender();
  return r;
}

/* YOU -> SHADOW: founder guidance on the goal. Never reaches the chat. */
async function goalTellShadow(gid, text){
  if (!text || !text.trim()) return null;
  return goalAct(gid, "guidance", { text: text.trim() });
}

/* "Take over chat" is a focus affordance, not a lifecycle action: the pause
   is a consequence of the founder's turn travelling the ordinary /ws/chat
   path, so nothing is sent and no state is changed here. */
function goalFocusTakeover(){
  if (typeof document === "undefined" || !document.querySelector) return null;
  const el = document.querySelector("[data-goalchat]");
  if (!el) return null;
  if (el.focus) el.focus();
  if (el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  if (typeof showNudge === "function")
    showNudge("Type in the chat — Shadow pauses there as soon as you do");
  return el;
}

/* YOU -> CHAT: the ORDINARY operator send. submitTurn goes through
   claudeChannel -> /ws/chat with no shadow source, which is exactly what
   makes the server pause Shadow in this chat (founder_takeover). There is
   no second chat route here on purpose. */
function goalTakeOver(sid, text){
  if (!sid || !text || !text.trim()) return null;
  if (typeof submitTurn === "function") return submitTurn(text.trim(), sid);
  if (typeof showNudge === "function")
    showNudge("The chat channel is not available in this view");
  return null;
}

/* ---- screens ------------------------------------------------------------- */

if (typeof SCREENS !== "undefined"){
  SCREENS.goals = () => {
    /* dark FIRST: a flag-off Shadow must say so, not sit on "Looking…" */
    if (typeof S !== "undefined" && S.goalDark){
      return `<div class="zero"><h4>Goals</h4>
        <p>Shadow is not enabled. Turn it on in Settings.</p></div>`;
    }
    if (typeof S !== "undefined" && S.goals === undefined){
      loadGoals();
      return `<div class="zero"><h4>Goals</h4><p>Looking…</p></div>`;
    }
    return goalsListHtml((typeof S !== "undefined" && S.goals) || []);
  };
  SCREENS.goal = () => {
    const S_ = (typeof S !== "undefined") ? S : {};
    if (S_.goalSel && !(S_.goalDetail || {})[S_.goalSel]){
      loadGoal(S_.goalSel);
      goalSyncPoll(S_.goalSel);
      return `<div class="zero"><h4>Goal</h4><p>Looking…</p></div>`;
    }
    /* every paint re-decides: a goal that just went blocked stops the poll
       on the same render that shows the founder it is blocked */
    goalSyncPoll(S_.goalSel);
    return goalWorkspaceHtml();
  };
}
if (typeof TITLES !== "undefined"){
  TITLES.goals = ["Goals", "outcomes Shadow is driving · one per chat"];
  TITLES.goal = ["Goal", "the outcome, and the chat working on it"];
}

/* ---- events -------------------------------------------------------------- */

if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("click", (ev) => {
    const t = ev.target;
    const d = (t && t.dataset) || {};
    if (d.goalback) return closeGoal();
    if (d.goalact && d.goalid){
      if (d.goalact === "extend")
        return goalAct(d.goalid, "resume", { extra_turns: 10 });
      if (d.goalact === "confirm"){
        /* the EXISTING confirm action, on the check the panel offered */
        return goalAct(d.goalid, "confirm",
                       { index: parseInt(d.goalindex, 10) || 0 });
      }
      if (d.goalact === "takeover"){
        /* not a lifecycle action and not a second channel: it puts the
           founder in the YOU -> CHAT field, whose first keystroke goes
           through /ws/chat and pauses Shadow server-side. */
        return goalFocusTakeover();
      }
      return goalAct(d.goalid, d.goalact);
    }
    /* slice 8: the confirmation card */
    if (d.gwpropcreate) return goalCreateFromProposal(d.gwpropcreate);
    if (d.gwpropcancel) return goalCancelProposal(d.gwpropcancel);
    if (d.gwpropstart) return goalStartCreated(d.gwpropstart);
    if (d.gwpropopen) return openGoal(d.gwpropopen);
    const card = t && t.closest ? t.closest("[data-goalopen]") : null;
    if (card && card.dataset) return openGoal(card.dataset.goalopen);
  });
  /* edits live in UI state; input (not keydown) so a paste counts too */
  document.addEventListener("input", (ev) => {
    const el = ev.target; const d = (el && el.dataset) || {};
    const key = d.gwpropoutcome || d.gwpropcriteria;
    if (!key) return;
    const p = goalProposalIn(key);
    if (!p) return;
    const draft = goalDraftFor(p);
    if (d.gwpropoutcome) draft.outcome = el.value;
    else draft.criteria = el.value;
    /* re-render so the Create button's enabled state stays honest */
    if (typeof scheduleRender === "function") scheduleRender();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter" || ev.shiftKey) return;
    const el = ev.target;
    const d = (el && el.dataset) || {};
    if (d.goalshadow){
      ev.preventDefault && ev.preventDefault();
      const text = el.value; el.value = "";
      goalTellShadow(d.goalshadow, text);
      return;
    }
    if (d.goalchat){
      ev.preventDefault && ev.preventDefault();
      const text = el.value; el.value = "";
      goalTakeOver(d.goalchat, text);
      if (typeof scheduleRender === "function") scheduleRender();
    }
  });
}
