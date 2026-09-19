/* 15-shadow-overlay.js -- the Shadow overlay: dot + pill + card
   (PLAN-100 S65-S78). GATED BY THE SERVER: every capability behind
   GET /api/shadow/status; a 403 means this module mounts NOTHING -- the
   off-state invariant is "no shadow DOM exists", asserted by tests.

   ONE conversation: the card renders S.shadowThread, the same array the
   Focus home (P6) renders in full. There is no second chat state.

   Energy: nothing here polls. Status is fetched on boot and after each chat
   turn; the only timers are one-shot (pill auto-hide, nudge remove). */
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


/* ---- pure helpers (node-tested directly) -------------------------------- */

/* S65: snap a dragged dot to the nearest corner, inside the safe zones */
function snapCorner(x, y, w, h, margin){
  const m = margin == null ? 16 : margin;
  return { left: x < w / 2 ? m : null,
           right: x < w / 2 ? null : m,
           top: y < h / 2 ? m : null,
           bottom: y < h / 2 ? null : m };
}

/* S67: at most N UNSOLICITED pills per hour; nudges are exempt. history is
   a list of epoch-ms; returns [allowed, prunedHistory].

   N IS THE FOUNDER'S, AND THERE IS NO SECOND COPY OF IT. This was the
   constant SH_PILLS_PER_HOUR = 3, and the constant is GONE rather than kept
   as a fallback: a fallback is exactly how a setting goes quietly back to 3
   the moment a read fails, which is the defect this change exists to remove.
   The rate lives in presence.json, arrives on the settings GET, and is seeded
   onto S.shadowNudgeRate by applyShadowPresence.

   AN UNKNOWN RATE SUPPRESSES. If no number has arrived -- boot still in
   flight, settings unreachable, Shadow flagged off -- this returns false and
   the pill stays silent. The alternative readings are both worse: falling
   back to a number nobody set is the lie, and allowing everything would make
   a failed read the loudest Shadow ever gets. Silence is recoverable; the
   next successful settings read restores the founder's rate. NOTE this is the
   opposite default from corner_card, on purpose -- an unreadable setting must
   cost an INTERRUPTION, never the founder's only way to reach Shadow.

   ZERO IS A REAL RATE and falls out of the arithmetic: no history is ever
   short enough, so nothing unsolicited is ever allowed. */
function shadowNudgeRate(){
  if (typeof S === "undefined") return null;
  const n = S.shadowNudgeRate;
  return (typeof n === "number" && isFinite(n) && n >= 0) ? n : null;
}

function pillAllowed(history, now, limit){
  const hour = 3600 * 1000;
  const recent = (history || []).filter(t => now - t < hour);
  const max = (limit === undefined || limit === null)
    ? shadowNudgeRate() : limit;
  if (max === null) return [false, recent];        /* rate unknown: silence */
  return [recent.length < max, recent];
}

/* THE ROLLING HOUR SURVIVES THE RELOAD, and has to, or the maximum is not one.
   S._pillHistory was memory-only, so "at most 1 an hour" really meant "at most
   1 per page load" and any reload refunded the budget -- a founder who set the
   rate to 1 and worked across five reloads could be interrupted five times
   inside the hour they had capped.

   PER BROWSER, THROUGH THE HELPERS THAT ARE ALREADY THERE (lsGet/lsSet,
   01-state.js). The SETTING is server-side because it is the founder's choice
   and must follow them across a restart; the COUNTER is local because it is a
   fact about one browser's last hour, and no other client's interruptions
   should spend this one's budget. Both guarded on typeof: a vm test or a
   partial shell degrades to in-memory rather than throwing.

   Junk is dropped rather than trusted -- a hand-edited or half-written value
   costs the hour's memory, never the enforcement. */
const LS_SH_PILLS = "sutra.shadow.pills";

function shadowPillHistory(){
  if (typeof S === "undefined") return [];
  if (!S._pillHistory){
    const raw = (typeof lsGet === "function") ? lsGet(LS_SH_PILLS, []) : [];
    S._pillHistory = Array.isArray(raw)
      ? raw.filter(t => typeof t === "number" && isFinite(t)) : [];
  }
  return S._pillHistory;
}

function saveShadowPillHistory(history){
  if (typeof S !== "undefined") S._pillHistory = history;
  if (typeof lsSet === "function") lsSet(LS_SH_PILLS, history);
}

/* S71: chips come from Shadow as text; a chip renders ONLY as verb+object
   (2-6 words, starts with a verb-looking token), max 3. Anything else falls
   back to Clarify (S72). */
function validChips(chips){
  const ok = [];
  for (const c of (chips || [])){
    const words = String(c || "").trim().split(/\s+/);
    if (words.length >= 2 && words.length <= 6 && /^[A-Za-z]/.test(words[0])){
      ok.push(words.join(" "));
      if (ok.length === 3) break;
    }
  }
  return ok;
}

/* S75: Shadow's watcher must never react to Shadow's own turns */
function isOwnTurn(text){
  return /^\[Shadow \u00b7/.test(String(text || ""));
}

/* S78: the dot's face for each status answer */
function dotState(status){
  if (!status) return { cls: "shdot-down", label: "Shadow is not watching" };
  if (status.watching) return { cls: "shdot-live", label: "Shadow is watching" };
  return { cls: "shdot-idle", label: "Shadow is idle" };
}

/* ---- state -------------------------------------------------------------- */
if (typeof S !== "undefined"){
  /* v10 per-chat threads. S.shadowThread stays the name every existing
     caller uses, but it is now an ACCESSOR onto the active tab's array
     (codex P2: a plain alias detaches the moment someone reassigns it,
     and sendToShadow reassigns it twice). */
  if (!S.shadowThreads) S.shadowThreads = {};
  if (!S.shadowChat) S.shadowChat = "global";
  if (!Object.getOwnPropertyDescriptor(S, "shadowThread")
      || !Object.getOwnPropertyDescriptor(S, "shadowThread").get){
    const seed = S.shadowThread || [];
    S.shadowThreads[S.shadowChat] = seed;
    try {
      delete S.shadowThread;
      Object.defineProperty(S, "shadowThread", {
        configurable: true, enumerable: true,
        get(){ const k = S.shadowChat || "global";
          if (!S.shadowThreads[k]) S.shadowThreads[k] = [];
          return S.shadowThreads[k]; },
        set(v){ S.shadowThreads[S.shadowChat || "global"] = v || []; },
      });
    } catch (e){ S.shadowThread = seed; }   /* frozen S: keep the array */
  }
  if (S.shadowQuiet === undefined) S.shadowQuiet = false;
  shadowPillHistory();     /* seeded from the browser, not reset by the reload */
}

/* ---- quiet: the switch and the clock, resolved in ONE place ---------------

   THE RULE IS WRITTEN TWICE, here and in shadow_presence.window_active, and
   test_quiet_hours_cases.json is the single table both lanes run so the two
   cannot drift. The duplication is deliberate and the alternative is worse:
   the settings GET is not polled and this overlay is pinned no-poll (see the
   boot note), so a quiet_now fetched at boot would still read "not quiet" an
   hour into the window -- wrong at exactly the boundary the setting exists to
   honour. The server's quiet_now is what the settings row STATES; this is
   what GATES, and it reads the clock at the moment of the gate.

   INCLUSIVE START, EXCLUSIVE END, AND IT WRAPS MIDNIGHT. "21:00 to 08:00" is
   the two arcs either side of midnight; a naive start<=t<end would make that
   window empty, so the setting would store fine and simply never fire. */
function shadowQuietWindowNow(window, at){
  const w = (window === undefined)
    ? (typeof S !== "undefined" ? S.shadowQuietHours : null) : window;
  if (!w || typeof w !== "object") return false;
  const mins = (hhmm) => {
    const m = /^([01][0-9]|2[0-3]):([0-5][0-9])$/.exec(String(hhmm || ""));
    return m ? Number(m[1]) * 60 + Number(m[2]) : null;
  };
  const start = mins(w.start), end = mins(w.end);
  if (start === null || end === null) return false;
  if (start === end) return false;      /* the store refuses it; be inert here */
  const now = at || new Date();
  const t = now.getHours() * 60 + now.getMinutes();
  return start < end ? (t >= start && t < end) : (t >= start || t < end);
}

/* THE ONE QUIET ANSWER every gate asks. The manual switch and the clock are
   two ways to reach one state, not two states -- a founder who pressed Quiet
   and a founder inside their quiet hours both asked for the same thing, and a
   red ring pulsing under either of them is the incoherent option. */
function shadowQuietNow(){
  if (typeof S === "undefined") return false;
  return !!(S.shadowQuiet || shadowQuietWindowNow());
}

/* one place decides what the dot shows: state class, alert pill, badge */
function applyDotState(dot, status){
  const st = dotState(status);
  const quiet = shadowQuietNow();
  /* QUIET STANDS THE ALARM DOWN, IT DOES NOT HIDE THE NEWS. The red ring and
     the "N need you" phrasing are the unsolicited half -- they are what taps
     the founder on the shoulder, and they are what quiet hours exist to stop.
     The dot, its state colour and the badge COUNT all stay: suppressing those
     would not be quiet, it would be concealment, and the founder who looks
     during their quiet hours must still find out what is waiting. */
  const al = (status && status.alerts) && !quiet;
  const nb = status && status.active_missions;
  dot.className = "shdot " + st.cls + (al ? " shdot-alert" : "");
  /* mock v5: the face is ALWAYS the S-mark; counts ride a separate badge */
  const n = (status && status.alerts) || nb || 0;
  if (typeof dot.innerHTML === "string")
    dot.innerHTML = "S" + (n ? `<span class="shbadge">${n}</span>` : "");
  else dot.textContent = "S" + (n || "");
  dot.setAttribute && dot.setAttribute("aria-label",
    al ? st.label + " \u00b7 " + al + " need you" : st.label);
}

/* ---- presence: the founder's standing choice ------------------------------

   TWO FLAGS, TWO MEANINGS, and keeping them apart is the whole point:

     S.shadowCardEvery    the durable setting ("Corner card on every screen").
                          Lives on disk in presence.json, arrives on the
                          settings GET, survives reload and restart.
     S.shadowHideSession  the card's own hide control. Browser lifetime, means
                          "not right now", and is forgotten at reload.

   The card is visible when BOTH agree. Asking one flag to carry both meanings
   is what made the settings switch a lie before this: it flipped the session
   flag, so the choice died with the page. */

function shadowCornerCardOn(){
  return !(typeof S !== "undefined" && S.shadowCardEvery === false);
}

/* THE THIRD FLAG, and the narrowest: "Hide for this app".

   S.shadowHiddenApps is the durable per-app list, off presence.json via the
   same settings GET. It is asked one question -- is the app I am looking at
   in it -- and the app I am looking at is S.modSel, the open app id the Apps
   screen already owns (18-modules.js). There is no second notion of "current
   app" invented here.

   NO APP OPEN MEANS NOT HIDDEN. S.modSel is null everywhere outside an open
   app, and null is not in any list, so the dot is untouched on every other
   screen -- which is the whole difference between this and corner_card. */
function shadowPresenceHiddenHere(){
  if (typeof S === "undefined") return false;
  const id = S.modSel;
  if (!id) return false;
  return (S.shadowHiddenApps || []).indexOf(id) !== -1;
}

/* seed the durable flags from a settings payload. Only a real value moves
   either -- a failed or flag-gated read must leave the defaults (shown, and
   hidden nowhere) standing rather than latch the card off because an answer
   was missing. */
function applyShadowPresence(settings){
  if (typeof S === "undefined") return;
  const p = (settings && settings.presence) || {};
  if (typeof p.corner_card === "boolean") S.shadowCardEvery = p.corner_card;
  if (Array.isArray(p.hidden_apps)) S.shadowHiddenApps = p.hidden_apps.slice();
  /* the rate the pill is held to. ONLY a real number moves it, and there is
     nothing to fall back to if none arrives -- pillAllowed suppresses on an
     unknown rate rather than inventing one (see its header). */
  if (typeof p.nudges_per_hour === "number" && isFinite(p.nudges_per_hour))
    S.shadowNudgeRate = p.nudges_per_hour;
  /* THE QUIET WINDOW, not a quiet boolean. The payload carries quiet_now too
     and this deliberately ignores it: a boolean seeded here would be stale by
     the next hour, so what is kept is the window and the clock is read at the
     gate (shadowQuietWindowNow). quiet_now is for the settings row to STATE.

     AN EXPLICIT null MOVES IT -- that is how a clear arrives, and an absent
     key is a read that failed rather than a window that was removed. The two
     must not be the same, or a flag-gated GET would silently un-quiet a
     founder who had set hours. */
  if (p.quiet_hours === null) S.shadowQuietHours = null;
  else if (p.quiet_hours && typeof p.quiet_hours === "object")
    S.shadowQuietHours = { start: p.quiet_hours.start,
                           end: p.quiet_hours.end };
}

/* THE ONE PLACE the dot is reconciled with the state, whatever moved.

   Every reason to hide is a guard inside mountShadowOverlay, so "should it
   be there" is asked in exactly one place; this answers the other half,
   "make the DOM agree", which mountShadowOverlay cannot do because it only
   ever adds. Before this existed each caller removed the dot itself and only
   one of them remembered the gutter. */
function syncShadowPresence(){
  if (typeof document === "undefined" || typeof S === "undefined") return;
  const dot = document.querySelector && document.querySelector(".shdot");
  if (shadowCornerCardOn() && !S.shadowHideSession
      && !shadowPresenceHiddenHere()){
    mountShadowOverlay();                 /* already a no-op when one exists */
    return;
  }
  S.shadowCardOpen = false;
  renderShadowCard();
  if (dot && dot.remove) dot.remove();
  /* and give the gutter back. mountShadowOverlay reserves 72px at the foot of
     every scrollable pane while the dot exists (visual audit r5); nothing
     released it before, so hiding the card left a blank strip behind it. */
  try { document.body.classList.remove("sh-fab-on"); } catch (_e){}
}

/* THE ONE PLACE the card appears or disappears as the setting moves. Turning
   it ON also clears the session dismissal, because "on every screen" that
   leaves the card hidden is not on. */
function applyCornerCardPref(on){
  if (typeof S === "undefined") return;
  S.shadowCardEvery = !!on;
  /* turning it on also clears the session dismissal: "on every screen" that
     leaves the card hidden is not on. It does NOT clear a per-app hide --
     that is a different, narrower choice the founder made deliberately, and
     un-making it from this switch would be silent. */
  if (on) S.shadowHideSession = false;
  syncShadowPresence();
}

/* "Hide for this app", applied. Called with the list already written, and
   also every time the OPEN APP changes -- the dot has to go and come back as
   the founder moves between apps, which is the visible difference between
   this setting and the corner-card one. */
function applyAppPresence(hiddenApps){
  if (typeof S === "undefined") return;
  if (Array.isArray(hiddenApps)) S.shadowHiddenApps = hiddenApps.slice();
  syncShadowPresence();
}

/* ---- mounting (only after a 200 from status) ----------------------------- */
let _shadowStatus;

function mountShadowOverlay(){
  if (typeof document === "undefined" || typeof S === "undefined") return;
  if (!shadowCornerCardOn()) return;               /* the standing choice */
  if (S.shadowHideSession) return;                 /* S73 hide-for-session */
  if (shadowPresenceHiddenHere()) return;          /* hidden for THIS app */
  if (document.querySelector && document.querySelector(".shdot")) return;
  const dot = document.createElement("div");
  const st = dotState(_shadowStatus);
  dot.className = "shdot " + st.cls;
  dot.textContent = "S";                    /* the S-mark: unmistakable */
  dot.setAttribute && dot.setAttribute("role", "button");
  dot.setAttribute && dot.setAttribute("aria-label", st.label);
  dot.setAttribute && dot.setAttribute("tabindex", "-1");  /* R3: click, not tab */
  applyDotState(dot, _shadowStatus);                        /* R20 + pill */
  dot.dataset && (dot.dataset.shadowdot = "1");
  if (dot.addEventListener) dot.addEventListener("click", toggleShadowCard);
  (document.body || document.documentElement).appendChild(dot);
  /* reserve a bottom gutter while the FAB exists (visual audit r5): without
     it the dot covered the last row of every scrollable pane */
  try { document.body.classList.add("sh-fab-on"); } catch (_e){}
  return dot;
}

/* the card MOUNTS (2.224.3 lesson repeated: html functions nobody renders
   are invisible). One wrapper div, replaced wholesale per state change. */
function renderShadowCard(){
  if (typeof document === "undefined" || typeof S === "undefined") return;
  const existing = document.querySelector && document.querySelector("[data-shcardwrap]");
  /* THE CARD IS REPLACED WHOLESALE and nothing carried the composer across
     the swap, so a repaint landing mid-sentence in "Talk to Shadow" took the
     focus, the caret AND the half-typed draft with it. Four callers repaint
     from the background while the founder may still be typing:
     shadowSendAndRefresh's second pass (after the POST answers),
     shadowMissionAct, goalCancelProposal and syncShadowPresence.

     Same contract render() gives the home composer: snapshot BEFORE the
     remove, restore AFTER the mount. Guarded throughout -- the node tests
     boot this file against a stub document with no activeElement. */
  const act = document.activeElement;
  const keep = (existing && act && act.dataset && act.dataset.shcompose
    && existing.contains && existing.contains(act))
    ? { value: act.value, start: act.selectionStart, end: act.selectionEnd }
    : null;
  if (existing) existing.remove();
  if (!S.shadowCardOpen) return;
  const wrap = document.createElement("div");
  wrap.dataset && (wrap.dataset.shcardwrap = "1");
  wrap.innerHTML = shadowCardHtml();
  if (wrap.addEventListener){
    wrap.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey && ev.target
          && ev.target.dataset && ev.target.dataset.shcompose){
        ev.preventDefault && ev.preventDefault();
        const text = ev.target.value;
        ev.target.value = "";
        if (text && text.trim()) shadowSendAndRefresh(text.trim());
      }
    });
    wrap.addEventListener("click", (ev) => {
      const d = (ev.target && ev.target.dataset) || {};
      if (d.shchip) return shadowSendAndRefresh(d.shchip);
      if (d.shquiet){ S.shadowQuiet = !S.shadowQuiet; return renderShadowCard(); }
      if (d.shhidesess){
        S.shadowHideSession = true; S.shadowCardOpen = false;
        renderShadowCard();
        const dot = document.querySelector && document.querySelector(".shdot");
        if (dot && dot.remove) dot.remove();               /* R12: one control */
        return;
      }
      if (d.shopenhome){
        S.shadowCardOpen = false; renderShadowCard();
        if (typeof goDest === "function") goDest("focus");
        if (typeof openScreen === "function") openScreen("shadow");
        if (typeof render === "function") render();
        return;
      }
      if (d.shstart) return shadowMissionAct(d.shstart, "start_now");
    });
  }
  (document.body || document.documentElement).appendChild(wrap);
  /* The restore is unconditional, exactly like render()'s (06-render.js).
     Send is NOT special-cased here: the Enter handler above clears the box
     before it calls, so keep.value is already "" on that path and writing it
     back is a no-op against a freshly-rendered textarea that is empty anyway.
     Nothing about what Enter does changed. */
  if (keep && wrap.querySelector){
    const box = wrap.querySelector("[data-shcompose]");
    if (box){
      box.value = keep.value;
      try {
        box.focus({ preventScroll: true });
        if (typeof keep.start === "number" && box.setSelectionRange)
          box.setSelectionRange(keep.start, keep.end);
      } catch (e) {}
    }
  }
  return wrap;
}

function toggleShadowCard(){
  if (typeof S === "undefined") return;
  S.shadowCardOpen = !S.shadowCardOpen;
  renderShadowCard();
}

async function shadowSendAndRefresh(text){
  renderShadowCard();               /* founder turn appears immediately */
  const doc = await sendToShadow(text);
  if (doc && doc.watching !== undefined){
    _shadowStatus = { watching: doc.watching,
                      permission_mode: (_shadowStatus || {}).permission_mode };
    const dot = document.querySelector && document.querySelector(".shdot");
    if (dot) applyDotState(dot, _shadowStatus);
  }
  renderShadowCard();
}

/* THE SAVED CHOICE IS APPLIED BEFORE THE CARD CAN EVER APPEAR.

   Status and settings are awaited TOGETHER and the mount happens after both,
   so a founder who turned the card off does not watch it flash in and vanish
   on every reload. Sequencing the two reads would produce exactly that flash;
   mounting on status alone and correcting afterwards would too.

   THE TWO LEGS FAIL DIFFERENTLY, on purpose. Status is the gate -- no answer
   means mount nothing, and a network failure must still reach the retry
   below, so its rejection is left to propagate. Settings is an ANNOTATION on
   that decision: an unreadable settings read costs the default (shown), never
   the dot, so it swallows its own failure. Presence rides the settings
   payload rather than a route of its own precisely so this stays two reads
   and not three. */
function bootShadowOverlay(){
  if (typeof fetch === "undefined") return;
  Promise.all([
    fetch("/api/shadow/status").then(r => r.ok ? r.json() : null),
    fetch("/api/shadow/settings").then(r => r.ok ? r.json() : null)
      .catch(() => null),
  ]).then(([status, settings]) => {
    applyShadowPresence(settings);
    if (!status) return;                           /* dark: mount NOTHING */
    _shadowStatus = status;
    mountShadowOverlay();
  }).catch(() => {
    /* transient failure must not leave Shadow dark forever: ONE delayed
       retry (single-shot; the no-poll pin stands -- this is not a loop) */
    if (typeof setTimeout === "function" && !bootShadowOverlay._retried){
      bootShadowOverlay._retried = true;
      setTimeout(bootShadowOverlay, 5000);
    }
  });
}

/* THE deep-link router (the founder's dead-click fix, 2026-08-26): every
   sutra:// link Shadow hands out lands somewhere real. Wrapped so a partial
   shell never strands half-set state (deepseek fold). */
function shadowRouteDeepLink(link){
  const l = String(link || "");
  try {
    /* slice 7: a goal is directly addressable and lands in its workspace.
       Checked BEFORE the mission arm so a goal id never falls through to
       the Focus default. */
    let g = l.match(/^sutra:\/\/shadow\/goal\/(g-[a-z0-9]+)/);
    if (g){
      if (typeof S !== "undefined") S.goalSel = g[1];
      if (typeof goDest === "function") goDest("focus");
      if (typeof openGoal === "function") openGoal(g[1]);
      else if (typeof openScreen === "function") openScreen("goal");
      if (typeof render === "function") render();
      return true;
    }
    let m = l.match(/^sutra:\/\/shadow\/(?:mission\/)?(m-[a-z0-9]+)/);
    if (m){
      if (typeof S !== "undefined"){
        S.shadowTab = "working"; S.shadowFocusMission = m[1];
        /* THE LINK NOW OPENS THE TASK IT NAMES (founder, 2026-09-15).
           This already set shadowFocusMission and opened the `shadow`
           screen -- but shadowFocusMission is read by shadowPlaneHtml
           (the Watching screen's row highlight) and NOTHING else, while
           the workspace this line opens picks its card from
           S.shadowTaskSel. So every mission deep-link -- every "View" on
           a Now row, which is how a founder hears a task finished at all
           -- landed on whichever task the selection ranked first.

           Both are set, neither is renamed: the plane keeps its highlight,
           and the workspace opens the task the row was about. */
        S.shadowTaskSel = m[1];
      }
      if (typeof goDest === "function") goDest("focus");
      if (typeof openScreen === "function") openScreen("shadow");
      if (typeof render === "function") render();
      return true;
    }
    if (/^sutra:\/\/shadow/.test(l)){
      if (typeof goDest === "function") goDest("focus");
      if (typeof openScreen === "function") openScreen("shadow");
      if (typeof render === "function") render();
      return true;
    }
    m = l.match(/^sutra:\/\/session\/(.+)$/);
    if (m){
      shadowOpenSessionPane(m[1]);
      return true;
    }
  } catch (e){ /* fall through to the safe default */ }
  if (typeof goDest === "function") goDest("focus");
  if (typeof openScreen === "function") openScreen("shadow");
  if (typeof render === "function") render();
  return false;
}

/* A SESSION LINK OPENS THAT SESSION. This arm used to store the id on
   S.pendingSessionHint and change destination -- and NOTHING in the panel ever
   read that hint, so "Open the chat" landed on Chats showing whichever panes
   were already in S.openPanes. For a founder who had just tested one
   delegated task and started another, that is the PREVIOUS task's chat: the
   link looked wired and pointed at the wrong conversation.

   No new navigation: this is the rail's own [data-open] sequence -- markRead,
   pushPane (the one helper all three open paths use), ensureTranscript, then
   the destination -- so a Shadow link opens a chat exactly the way clicking
   it in the rail does, FIFO eviction and transcript read included.

   A chat published seconds ago has no row in S.sessions yet, so an unknown id
   costs ONE list refresh before the open, and only then. Still no polling, and
   a refresh that fails still opens and still lands on Chats. */
function shadowOpenSessionPane(sid){
  const open = () => {
    if (typeof markRead === "function") markRead(sid);
    if (typeof pushPane === "function") pushPane(sid);
    if (typeof ensureTranscript === "function")
      ensureTranscript((((typeof S !== "undefined" && S.sessions) || [])
        .find(s => s && s.id === sid)) || null);
    /* goDest renders; render() alone is the fallback when the shell is
       partial (the same guard every other arm of the router carries) */
    if (typeof goDest === "function") goDest("chats");
    else if (typeof render === "function") render();
  };
  const S_ = (typeof S !== "undefined") ? S : {};
  const known = (S_.sessions || []).some(s => s && s.id === sid);
  if (known || typeof loadSessions !== "function"){ open(); return; }
  try {
    Promise.resolve().then(() => loadSessions()).then(open, open);
  } catch (e){ open(); }
}

/* event-driven pill (the overlay never polls -- pinned): whoever already
   holds fresh feed data pushes the alert count here (14-needs-you does). */
function shadowDotAlerts(n){
  const dot = document.querySelector && document.querySelector(".shdot");
  if (!dot) return;
  _shadowStatus = Object.assign({}, _shadowStatus || {}, { alerts: n });
  applyDotState(dot, _shadowStatus);
}

/* S77: cmd-shift-S toggles the card; Esc closes (S66) */
function shadowKeyHandler(ev){
  if (ev.key === "Escape" && typeof S !== "undefined" && S.shadowCardOpen){
    S.shadowCardOpen = false;
    renderShadowCard();
    return true;
  }
  if ((ev.metaKey || ev.ctrlKey) && ev.shiftKey
      && String(ev.key).toLowerCase() === "s"){
    if (typeof S !== "undefined") S.shadowCardOpen = !S.shadowCardOpen;
    renderShadowCard();
    return true;
  }
  return false;
}

/* S70: a mission renders IN the thread as a card that updates in place --
   the state chip gates Start (only a confirmed brief can start). */
/* ── HAS THIS TASK ALREADY BEEN STARTED? ──────────────────────────────────
   `brief_confirm` was read as "not started" everywhere, and for a while it
   was the same thing. It stopped being the same thing when start became a
   second-flight call: /act answers {accepted:true} and does admission and
   provisioning in a background task, because provisioning a delegate can
   take minutes. For that whole window the record still says brief_confirm
   while Shadow is already starting the task -- so Start stayed on screen
   after it had been pressed, and a page refresh in that window had nothing
   to read the pressed start from.

   `start_requested_at` is the server's stamp for exactly that window (see
   app._mark_start_requested). It is NOT a state: the mission is still
   brief_confirm, the transition table is untouched, and the scheduler still
   decides alone whether the next stop is running or queued. It only changes
   the FACE -- the founder reads the existing `queued` label, which is what
   "accepted, not running yet" has always been called here -- and it takes
   Start away, because pressing it again does nothing (shadow_runner guards
   the double start) and a button that does nothing reads as a dead click.

   Same precedent as shadowMissionNeedsFounder(): a fact carried beside the
   state, because the state alone is not the whole face. */
function shadowMissionStarting(m){
  return !!(m && m.state === "brief_confirm" && m.start_requested_at);
}
function shadowMissionStartable(m){
  return !!(m && m.state === "brief_confirm") && !shadowMissionStarting(m);
}

function missionCardHtml(m){
  if (!m) return "";
  const startable = shadowMissionStartable(m);
  /* a start that has been taken reads as queued, never as the state it is
     still technically sitting in */
  const face = shadowMissionStarting(m) ? "queued" : (m.state || "");
  /* v4: the card speaks founder language, never a raw state (SHADOW-V3
     section 7b; SH_TASK is the home module's word list, with a mirror here
     for the screens that load this module alone) */
  const WORD = { brief_confirm: "READY", queued: "QUEUED", running: "RUNNING",
    paused: "PAUSED", blocked: "NEEDS YOU", done: "DONE", failed: "FAILED",
    stopped: "STOPPED", draft: "DRAFT" };
  const word = (typeof SH_TASK !== "undefined" && SH_TASK[face] && SH_TASK[face].label)
    || WORD[face] || String(face).replace(/_/g, " ");
  return `<div class="shmission" data-shmission="${escAttr(m.id || "")}">
    <span class="shstate shstate-${esc(face)}">${esc(word)}</span>
    <span class="shobj">${esc(m.objective || "")}</span>
    ${/* the turn being worked, through the shared reader -- same guard and
         same fallback as the chat strip (06-render.js), because this file
         loads before 16-shadow-home.js defines it */""}
    <span class="shturns">${typeof shadowTurnNow === "function"
      ? shadowTurnNow(m) : (m.turns_used || 0)}/${m.max_turns || "?"}</span>
    ${(m.done_when && m.done_when[0]) ? `<span class="shdone">done when:
      ${esc(m.done_when[0].check || "")}</span>` : ""}
    ${startable ? `<button class="btn pri" type="button"
        data-shstart="${escAttr(m.id || "")}">Start</button>` : ""}
    ${m.result_excerpt ? `<div class="shresult">${esc(m.result_excerpt)}</div>` : ""}
  </div>`;
}

/* ---- Shadow prose (v4 C6, ADR-043) ------------------------------------
   THE SHADOW VIEW SHOWS SHADOW'S WORDS AND ITS CARDS, NOTHING ELSE. A Shadow
   chat is a normal Claude Code session in the founder's repo, so its raw
   turns carry the governance scaffolding every session emits (the bracket
   header, INPUT/TYPE/ROUTE runs, the FLOW and BLUEPRINT boxes, the OS trace)
   and the protocol fences the app turns into cards. All of that stays in the
   transcript and in Chats; here it is filtered at the presentation boundary
   and the sentences that remain are rendered as markdown, the way the chat
   pane renders a reply.

   Three layers, in order: gvBody (05-chat.js, the chat pane's own scrubber)
   when it is loaded; the protocol fences; then a belt for what a stream can
   leak past both -- a lone header, a key line, an ASCII box. Nothing is
   generated: every word shown is Shadow's own. */
const SH_PROTO_FENCE = /```(?:mission|goal|chips|remember|module|brief)[ \t]*\n[\s\S]*?```/g;
/* ...AND THE SAME FENCE WHEN IT NEVER CLOSES (founder, 2026-09-17). The rule
   above needs a closing ```; a reply that opened ```chips and stopped left the
   opener on screen, and the line loop below then read it as the start of a
   code block and kept it. Measured in the founder's own conversation: a bare
   "```chips" under otherwise good prose.

   SAME VOCABULARY, SAME CONSTANT, applied only at the END of the text -- an
   unterminated protocol fence can only be the last thing in a reply. An
   ordinary ``` or ```js is untouched, because the kind list is the protocol's
   own and nothing else matches it. */
const SH_PROTO_FENCE_OPEN =
  /```(?:mission|goal|chips|remember|module|brief)[ \t]*(?:\n[\s\S]*)?$/;
const SH_GOV_HEADER = /^\s*\[[A-Z0-9-]+\s*·\s*[A-Z0-9-]+[^\]]*\]\s*$/;
const SH_GOV_KEY = new RegExp("^[\\s>*#\\-]*(" + [
  "INPUT", "TYPE", "EXISTING HOME", "ROUTE", "FIT CHECK", "ACTION",
  "TASK", "DEPTH", "EFFORT", "COST", "IMPACT",
  "TRIAGE", "ESTIMATE", "ACTUAL",
  "PLACEMENT", "BUILD-LAYER", "ACTIVATION-SCOPE", "TARGET-PATH",
  "FLOW", "BLUEPRINT", "OS TRACE",
].join("|") + ")\\s*:");
/* the trace only as the " > " chain the spec emits; "OS: macOS 14" stays */
const SH_GOV_TRACE = /^\s*`?OS:\s[^\n]*\s>\s/;
const SH_BOX_OPEN = /^\s*\+[-=]{2,}/;
const SH_BOX_ROW = /^\s*[|+]/;

function shadowProseText(text){
  let t = String(text == null ? "" : text);
  if (typeof goalStripTag === "function") t = goalStripTag(t);
  if (typeof gvBody === "function"){
    try { t = gvBody(t); } catch (e) { /* the belt below still runs */ }
  }
  t = t.replace(SH_PROTO_FENCE, "").replace(SH_PROTO_FENCE_OPEN, "");
  const out = [];
  let fenced = false, inBox = false;
  for (const line of t.split(/\r?\n/)){
    const trimmed = line.trim();
    if (/^```/.test(trimmed)){ fenced = !fenced; out.push(line); continue; }
    if (fenced){ out.push(line); continue; }        /* code is the reply's own */
    if (inBox){ if (SH_BOX_ROW.test(line)) continue; inBox = false; }
    if (SH_BOX_OPEN.test(line)){ inBox = true; continue; }
    if (SH_GOV_HEADER.test(line)) continue;
    if (SH_GOV_KEY.test(line)) continue;
    if (SH_GOV_TRACE.test(line)) continue;
    out.push(line);
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function shadowProseHtml(text){
  const body = shadowProseText(text);
  if (!body) return "";
  if (typeof mdHtml === "function"){
    try { return mdHtml(body); } catch (e) { /* fall through to plain */ }
  }
  return esc(body).replace(/\n/g, "<br>");
}

/* one message row of a Shadow thread: the founder's words verbatim (escaped),
   Shadow's words as prose */
function shadowMsgHtml(t){
  const mine = t && t.who === "founder";
  return `
    <div class="shmsg ${mine ? "shmine" : "shshadow"}">
      ${mine ? esc((t && t.text) || "") : shadowProseHtml((t && t.text) || "")}</div>`;
}

/* the card: compact view of the ONE thread + chips + free text always */
function shadowCardHtml(){
  const thread = (typeof S !== "undefined" && S.shadowThread) || [];
  if (!thread.length && typeof S !== "undefined" && !S._shadowIntroSeeded){
    /* First-run journey: the designed one-liner, seeded locally, honest */
    S._shadowIntroSeeded = true;
    thread.push({ who: "shadow", ts: Date.now(),
      text: "I'm Shadow. I can see this app \u2014 your sessions, missions, "
            + "and what you teach me. Nothing else." });
  }
  const last = thread.slice(-6).map(t => t.mission
    ? missionCardHtml(t.mission)
    : (t.goalProposal && typeof goalProposalHtml === "function"
      ? goalProposalHtml(t.goalProposal)
      : shadowMsgHtml(t))).join("");
  const chips = validChips((typeof S !== "undefined" && S.shadowChips) || []);
  const chipHtml = chips.length
    ? chips.map(c => `<button class="btn shchip" type="button"
        data-shchip="${escAttr(c)}">${esc(c)}</button>`).join("")
    : `<button class="btn shchip" type="button" data-shchip="Clarify what you meant">Clarify</button>`;
  const perm = _shadowStatus && _shadowStatus.permission_mode;
  return `<div class="shcard" data-shadowcard="1">
    <div class="shperm">sees: your sessions \u00b7 missions \u00b7 what it
      has learned${perm ? ` \u00b7 permissions: ${escAttr(perm)}` : ""}
      <button class="btn shhide" type="button" data-shquiet="1">${
        (typeof S !== "undefined" && S.shadowQuiet) ? "Unquiet" : "Quiet"}</button>
      <button class="btn shhide" type="button" data-shhidesess="1">Hide</button>
      <button class="btn shhide" type="button" data-shopenhome="1">Open home \u2197</button>
    </div>
    <div class="shlog">${last || `<div class="shempty">Ask Shadow anything.</div>`}</div>
    <div class="shchips">${chipHtml}</div>
    <textarea class="shcompose" data-shcompose="1"
      placeholder="Talk to Shadow"></textarea>
  </div>`;
}

async function sendToShadow(text){
  if (typeof S === "undefined" || typeof fetch === "undefined") return null;
  if (isOwnTurn(text)) return null;               /* S75 self-loop guard */
  if (S.shadowBusy){
    S.shadowThread.push({ who: "shadow", ts: Date.now(),
      text: "(one moment -- still answering the last message)" });
    return null;
  }
  S.shadowBusy = true;
  S.shadowThread.push({ who: "founder", text, ts: Date.now() });
  S.shadowThread.push({ who: "shadow", ts: Date.now(), busy: true,
    text: S.shadowBooted ? "thinking\u2026"
                         : "waking up (first message boots my session -- up "
                           + "to a minute)\u2026" });
  try {
    /* the tab the founder is typing in rides the turn: the server folds
       that chat's confirmed rules in, and a remember lands scoped */
    const scope = (S.shadowChat && S.shadowChat !== "global")
      ? S.shadowChat : null;
    const r = await shadowPost("/api/shadow/chat",
      scope ? { message: text, scope_id: scope } : { message: text });
    S.shadowBusy = false;
    S.shadowThread = S.shadowThread.filter(t => !t.busy);
    if (!r.ok){
      S.shadowThread.push({ who: "shadow", ts: Date.now(),
        text: "(that failed: " + r.status + " -- try again, or check "
              + "Focus \u203a Shadow)" });
      return null;
    }
    S.shadowBooted = true;
    const doc = await r.json();
    S.shadowThread.push({ who: "shadow", text: doc.reply, ts: Date.now() });
    if (doc.chips) S.shadowChips = doc.chips;          /* R18: generated */
    if (doc.mission){                                   /* R19: card in-thread */
      S.shadowThread.push({ who: "shadow", mission: doc.mission,
                            ts: Date.now() });
    }
    if (doc.goal_proposal){        /* slice 8: a PROPOSAL, nothing created */
      S.shadowThread.push({ who: "shadow", goalProposal:
        Object.assign({ asked: text }, doc.goal_proposal), ts: Date.now() });
    }
    if (doc.remembered){                                /* R6: honest inert */
      const sc = doc.remembered.scope === "chat";
      S.shadowThread.push({ who: "shadow", ts: Date.now(),
        text: sc ? "Noted for THIS chat \u2014 inert until you confirm it"
                   + " in Shadow settings."
                 : "I will remember that everywhere once you confirm it"
                   + " in Shadow settings." });
    }
    return doc;
  } catch (e){
    S.shadowBusy = false;
    S.shadowThread = S.shadowThread.filter(t => !t.busy);
    S.shadowThread.push({ who: "shadow", ts: Date.now(),
      text: "(Shadow is not reachable -- is the app backend running?)" });
    return null;
  }
}

/* S67: the pill -- one line, auto-hide, rate-limited unless a nudge */
function showPill(text, opts){
  if (typeof document === "undefined" || typeof S === "undefined") return null;
  /* S73 quiet switch, now ALSO the clock: shadowQuietNow folds the founder's
     manual Quiet and their quiet hours into one answer. This is the same gate
     it has always been, asked a better question -- not a second gate beside
     it, which would be two places to be quiet and one of them eventually
     wrong.

     IT STAYS AHEAD OF THE isNudge BRANCH, which is load-bearing: opts.nudge
     buys a pill past the RATE LIMIT, never past quiet. "Urgent" is a claim
     about the news; quiet hours are a claim about the founder, and the
     founder's is the one that wins at 3am. */
  if (shadowQuietNow()) return null;
  const isNudge = opts && opts.nudge;
  if (!isNudge){
    /* the pruned history is saved WHETHER OR NOT the pill is allowed, so an
       hour that has rolled over is forgotten on the first suppressed attempt
       rather than only when one gets through */
    const [ok, pruned] = pillAllowed(shadowPillHistory(), Date.now());
    if (!ok){ saveShadowPillHistory(pruned); return null; }
    saveShadowPillHistory(pruned.concat([Date.now()]));
  }
  const el = document.createElement("div");
  el.className = "shpill";
  el.textContent = text || "";
  (document.body || document.documentElement).appendChild(el);
  setTimeout(() => { try { el.remove(); } catch (e) {} }, 12000);
  return el;
}

if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("keydown", shadowKeyHandler);
}

/* THE BOOT CALL. Defining a boot function is not booting (the gap the
   founder saw: everything served, nothing called). Guarded so vm tests can
   load the module inert and drive boot explicitly. */
if (typeof document !== "undefined" && typeof fetch !== "undefined"
    && !(typeof globalThis !== "undefined" && globalThis.__SHADOW_NO_AUTOBOOT)){
  try { bootShadowOverlay(); } catch (e) {}
}

/* START AND RETRY ANSWER BEFORE THEY HAPPEN. Both endpoints hand back
   {accepted:true} and provision in the background -- the deliberate
   second-flight fix, because holding the request open across a minutes-long
   spawn let client timeouts cancel it. The consequence on this side is that
   the loadShadowHome() at the end of shadowMissionAct reads a mission that
   has not moved yet, so the row keeps saying READY while Shadow is already
   running the task.

   Nothing in Shadow polls, and this does not start it polling: FOUR bounded
   re-reads, on these two actions only, each skipped the moment the mission
   has left brief_confirm. No timer is ever rescheduled and nothing runs after
   the last one. The unknown-row case (a retry CLONE has no row in the list
   yet) reloads on purpose -- that is precisely the state the founder is
   waiting to see appear.

   THE FIRST STEP IS 250ms, NOT 1000ms (founder, 2026-09-13). Measured on the
   live server: the delegate's session id lands at 367ms and the chat is
   published -- mission stamped, chat_store segment begun -- at 394ms. The
   first re-read was simply scheduled later than the thing it was waiting for
   now happens, so the founder sat 713ms in front of a row that said READY
   about a chat that already existed (task card openable at 1107ms; 450ms
   with this ladder). The LAST step moved 8000 -> 5000: the window closes
   sooner than it used to, which is the opposite of polling. */
const SH_START_ACTIONS = ["start_now", "retry"];
/* THE SCHEDULE HAS TO OUTLAST THE START, and it did not (founder,
   2026-09-14: "chat appears, worker visibly running, card still says
   QUEUED, turn 0 of 20").

   TWO DIFFERENT WAITS, measured on this machine, and the old tail covered
   only the first:

     chat published    ~1.2s   _adopt() fires on the CLI's session-id
                               announcement -- early steps cover this.
     state -> running  7-95s   provisioning finishes and the scheduler
                               admits (8 real starts: 7, 10, 12, 14, 15,
                               31, 44, 95; median 15s).

   The tail ended at 5000ms, so it missed the state transition in 8 of 8
   measured starts -- every single one. The pane was then left holding the
   last snapshot the watcher fetched, which is brief_confirm carrying
   start_requested_at: the QUEUED face, turn 0 of 20, indefinitely. Nothing
   was wrong with the face, the record or the backend; the UI simply stopped
   looking a minute too early.

   Geometric out to 90s, which covers the slowest start measured. This is
   NOT 16 reads per start: the guard below returns the moment the row has
   something to show, so a normal start spends 3-5 of these and the long
   tail only runs for a start that is genuinely still provisioning. */
const SH_START_BACKOFF = [250, 750, 1200, 1600, 2200, 3000, 4500, 6500,
  9000, 12000, 16000, 22000, 30000, 45000, 60000, 90000];

function shadowWatchStart(mid){
  if (typeof setTimeout !== "function" || !mid) return;
  SH_START_BACKOFF.forEach((ms) => {
    setTimeout(() => {
      const S_ = (typeof S !== "undefined") ? S : {};
      const row = (S_.shadowMissions || []).find(m => m && m.id === mid);
      /* TWO THINGS ARE BEING WAITED ON, not one. The state leaving
         brief_confirm was the old test, but the founder is waiting to SEE
         the conversation, and target_chat lands first and independently --
         so a watcher that stopped on the state alone could leave the pane
         without the chat the click just created. Stop when both have
         landed, or when the start has already ended (a failed start has no
         chat coming and must not be polled to the end of the schedule). */
      const ended = row
        && ["done", "failed", "stopped"].indexOf(row.state) !== -1;
      const ready = row && row.state !== "brief_confirm" && row.target_chat;
      if (ended || ready) return;
      if (typeof loadShadowHome === "function") loadShadowHome(true);
    }, ms);
  });
}

/* WHEN THE SERVER REFUSES, SAY WHAT IT SAID.

   "That did not stick (409) \u2014 try again" is the right answer to a refusal
   with no explanation, and the wrong one to a refusal that came with a
   sentence written for the founder: Resume at the run limit answers with
   "Shadow is already running 2 of 2 tasks. Stop one, or raise Running at
   once", which names the cause AND both ways out. Telling the founder to
   "try again" sends them to click the same button against the same limit.

   FastAPI puts a raised HTTPException's payload under `detail`, and this
   file's routes raise both shapes -- a bare string, and an object whose own
   `detail` is the sentence beside machine-readable fields. Anything else
   (html, a proxy error, a body that will not parse) falls back to the
   status line that shipped. */
function shadowRefusalText(body){
  const d = body && body.detail;
  if (typeof d === "string" && d.trim()) return d.trim();
  if (d && typeof d.detail === "string" && d.detail.trim())
    return d.detail.trim();
  return null;
}

/* R19/R24: mission actions from any surface (card or home). */
async function shadowMissionAct(mid, action, extra){
  if (typeof fetch === "undefined") return null;
  try {
    const r = await shadowPost("/api/shadow/missions/" + mid + "/act",
      Object.assign({ action }, extra || {}));
    const doc = r.ok ? await r.json() : null;
    if (!r.ok && typeof showNudge === "function"){
      /* survey fold: a failed action must never look like a dead click */
      let said = null;
      try { said = shadowRefusalText(await r.json()); } catch (e){ said = null; }
      showNudge(said
        || ("That did not stick (" + r.status + ") \u2014 try again"));
    }
    if (doc && typeof showNudge === "function"){
      /* founder 2026-08-26: a working click must SAY it worked */
      const said = { start_now: "Mission starting \u2014 follow it in "
          + "Focus \u203a Shadow", stop: "Stopped.", resume: "Resumed.",
        drop: "Dropped.", retry: "Retry queued \u2014 a fresh mission "
          + "takes the same brief", confirm_check: "Check confirmed.",
        /* the chat strip's Take over: ownership ended, so say what that BUYS
           rather than that a state changed */
        take_over: "You have the chat \u2014 Shadow stepped back.",
        /* the task AND the chat Shadow made for it are gone; the
           transcript is recoverable from ~/.sutra-ui/trash */
        "delete": "Task deleted \u2014 its chat went with it." };
      showNudge(said[action] || "Done.");
    }
    if (typeof loadShadowHome === "function") loadShadowHome(true);
    /* the id the SERVER names, not mid: retry clones the brief into a new
       mission and starts the clone, so mid is the row that will never move */
    if (doc && SH_START_ACTIONS.indexOf(action) !== -1)
      shadowWatchStart(doc.mission_id || mid);
    renderShadowCard();
    return doc;
  } catch (e){ return null; }
}
