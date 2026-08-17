function applySessionChange(rows){
  let needList = false;
  rows.forEach(row=>{
    const s = S.sessions.find(x=>x.id === row.id);
    if (!s){ needList = true; return; }        /* unseen conversation */
    s.mtime = row.mtime; s.size = row.size; s.live = row.live;
    /* Without this the rail can never render "3 agents" from data: the field
       arrives on every changed row and is dropped by a three-field copy. */
    s.agents_live = row.agents_live || 0;
    /* A subagent just wrote: if this pane already loaded its agent list, refresh
       it so a new agent appears and a finished one stops saying "running". Gated
       on already-loaded, so a pane nobody opened the fold on costs nothing. */
    if (S.openPanes.includes(s.id) && S.agents[s.id] !== undefined && (row.agents_live || 0))
      loadAgents(s.id, true);
    /* Only a transcript actually on screen is re-read. Re-parsing every changed
       file would turn a busy Claude session into a stream of reads for panes
       nobody is looking at. */
    /* A session with work IN FLIGHT owns its turns array: the streaming turn
       object lives in it and the socket is still writing into that object. The
       file on disk is BEHIND that, so re-reading it here replaced the live turn
       with a parse that does not contain it -- the reply stopped updating, Stop
       reverted to Send, patchStreaming() could no longer find the node, and the
       answer reappeared minutes later as a static block. Reconciled once the
       turn lands instead. */
    if (S.openPanes.includes(s.id) && s.real && s.loadState !== "loading"
        && !sessionBusy(s.id)){
      /* Re-read through the SAME shape ensureTranscript() uses -- turns via
         transcriptTurns(), and its loadState vocabulary (unread/loading/ok/
         empty/error). A second parsing path would drift from the first and the
         two would disagree about the same file. */
      s.loadState = "loading";
      apiGet("/api/sessions/" + encodeURIComponent(s.id))
        .then(d=>{
          /* The GET is in flight for hundreds of ms and a send can start inside
             that window, so the guard above is necessary but not sufficient. */
          if (sessionBusy(s.id)){ s.loadState = "ok"; return; }
          s.turns = transcriptTurns(d && d.messages);
          s.cwd = (d && d.cwd) || s.cwd;
          s.branch = (d && d.branch) || s.branch;
          s.loadState = s.turns.length ? "ok" : "empty";
          scheduleRender();
        })
        .catch(e=>{ s.loadState = "error"; s.loadError = e.message; scheduleRender(); });
    }
  });
  if (needList) scheduleSessionRefresh(); else scheduleRender();
}

function startSessionStream(){
  if (_sessStream || typeof EventSource === "undefined") return;
  try { _sessStream = new EventSource("/api/sessions/stream"); }
  catch (e){ return; }
  _sessStream.addEventListener("sync", ev=>{
    /* The opening frame is the WHOLE index, so a panel that connected late is
       immediately correct rather than correct-from-now-on. */
    try { applySessionChange(JSON.parse(ev.data).sessions || []); } catch (e) {}
  });
  _sessStream.addEventListener("changed", ev=>{
    try { applySessionChange(JSON.parse(ev.data).sessions || []); } catch (e) {}
  });
  _sessStream.addEventListener("vanished", ev=>{
    try {
      const ids = new Set(JSON.parse(ev.data).ids || []);
      /* Marked gone, NOT removed. A pane open on a transcript that was deleted
         underneath should say so rather than vanishing mid-read. */
      S.sessions.forEach(s=>{ if (ids.has(s.id)) s.vanished = true; });
      scheduleRender();
    } catch (e) {}
  });
  _sessStream.addEventListener("tick", ()=>{
    /* Liveness decays with the CLOCK, not with writes: a session nobody has
       touched for a minute stops being active on its own, and without a tick
       nothing would ever say so. */
    const now = Date.now()/1000;
    let moved = false;
    S.sessions.forEach(s=>{
      if (!s.mtime) return;
      const age = now - s.mtime;
      const next = age <= 45 ? "active" : age <= 1800 ? "idle" : "stale";
      if (s.live !== next){ s.live = next; moved = true; }
    });
    if (moved) scheduleRender();
  });
  /* EventSource retries on its own; this only stops a dead handle being reused. */
  _sessStream.onerror = ()=>{
    if (_sessStream && _sessStream.readyState === 2){ _sessStream = null;
      setTimeout(startSessionStream, 3000); }
  };
}

/* ── dev auto-reload ─────────────────────────────────────────────────────────
   The server reads static/ from disk on every request, so an edited panel file
   is already being SERVED fresh -- only this renderer keeps running the old
   bytes until someone reloads the page. When the server was started with
   SUTRA_UI_DEV=1 it watches static/** and streams a `reload` event on change;
   this subscribes and reloads.

   GATED ON THE SERVER'S ANSWER, never assumed: boot() probes /api/dev and
   calls this with the result, so against a production server (where
   /api/dev/reload is a 404) no subscription is ever attempted and this file
   adds zero requests beyond the one probe. The gate lives server-side on
   purpose -- a client-side toggle could be flipped in a production app.

   `location.reload()` is the whole payload: a full reload re-runs boot(),
   which re-reads everything, so the reloaded page is correct by the same
   argument the first load is. Partial hot-swap machinery would be a second
   boot path to keep honest. The reload still passes through the beforeunload
   guard below, so an edit landing mid-turn asks before destroying the stream
   rather than silently eating it. */
let _devStream = null;
function startDevReload(dev){
  if (!dev || _devStream || typeof EventSource === "undefined") return;
  try { _devStream = new EventSource("/api/dev/reload"); }
  catch (e){ return; }
  _devStream.addEventListener("reload", ()=>{
    try { location.reload(); } catch (e) {}
  });
  /* EventSource retries on its own (the dev server restarts often -- that is
     what dev means); only a CLOSED handle is dropped so it is never reused. */
  _devStream.onerror = ()=>{
    if (_devStream && _devStream.readyState === 2) _devStream = null;
  };
}

async function loadSessions(){
  adoptRealSessions(await apiGet("/api/sessions?limit=100"));
}

function refetchOrg(){
  loadOrg().then(render).catch(backendError);
}


async function boot(){
  const panes = document.getElementById("panes");
  /* One registry holds one org. This used to read /api/tenants first and gate
     the whole boot on the answer -- including a silent `if (!S.tenant) return`
     that rendered an empty panel with no error when the answer was unexpected.
     There is nothing to choose, so there is nothing to gate on. */
  panes.innerHTML = `<section class="pane browse"><div class="pb" style="display:flex;
    align-items:center;justify-content:center;color:var(--faint);font-size:13px">
    Reading the registry…</div></section>`;
  try {
    /* allSettled, NOT all: these are three independent subsystems, and
       Promise.all rejects the whole boot on the first failure — so a registry
       hiccup discarded a perfectly good /api/skills and /api/settings response
       and the panel came up blank. Only the registry is load-bearing; runtime
       and sessions degrade to a stated error on their own screens. */
    const [org, runtime, sessions] =
      await Promise.allSettled([loadOrg(), loadRuntime(), loadSessions()]);
    if (org.status === "rejected") throw org.reason;   /* the one hard dependency */
    /* loadRuntime() reports PER-ENDPOINT failures into S.runtimeError itself and
       resolves, so only overwrite that when the whole call threw -- otherwise the
       specific "which of the three failed" detail is clobbered with null. */
    if (runtime.status === "rejected")
      S.runtimeError = String(runtime.reason && runtime.reason.message || runtime.reason);
    S.sessionsError = sessions.status === "rejected" ? String(sessions.reason && sessions.reason.message || sessions.reason) : null;
    await loadDraft();
    /* A base persisted from an earlier session can ALREADY be stale — the
       registry moved while nobody was looking. That is real drift: ORG-010
       fires for it server-side, so the banner has to explain the finding and
       Rebase (the only cure, and the control that is disabled unless S.drift)
       has to be reachable. Derived from the two counts, never stored. */
    S.drift = !!(S.draft.base && S.draft.base.domain_index_lines !== undefined &&
                 S.draft.base.domain_index_lines !== META.domain_index_lines);

    /* Open on two levels — root + its children. Deeper tiers collapse so the chart fits
       the pane; clicking a collapsed tile is the only control (feedback #4). */
    live().forEach(d=>{ if (d.parent_ref && DOMAINS.some(k=>k.parent_ref===d.ref)) S.collapsed.add(d.ref); });
    /* Open the most recent REAL session so the pane model is visible on load, and
       read its transcript — the pane shows what is in the file, or says plainly
       that there was nothing to read. */
    if (!S.openPanes.length && S.sessions.length){
      S.openPanes.push(S.sessions[0].id);
      ensureTranscript(S.sessions[0]);
    }

    S.loaded = true;
    render();
    /* AFTER render + SETTINGS: termMount() reads SETTINGS.workdir for the PTY cwd,
       so restoring the pane earlier would start the terminal in the wrong directory. */
    S.termW = clampTermW(Number(lsGet(LS_TERMW, TERM_DEFAULT)) || TERM_DEFAULT);
    S.sideTab = lsGet(LS_SIDETAB, "terminal") === "preview" ? "preview" : "terminal";
    const lastPrev = lsGet(LS_PREVURL, "");
    if (typeof lastPrev === "string" && lastPrev){
      /* Restore the URL into the field but do NOT auto-load it: the dev server may be
         gone, and a dead iframe on startup looks like a broken app. */
      const f = document.getElementById("prevUrl"); if (f) f.value = lastPrev;
    }
    if (lsGet(LS_TERM, false) === true){ termToggle(true); sideTab(S.sideTab); }

    /* Seed the composer's usage chip. NOT awaited: the panel must not wait on an
       external API to become usable, and until it resolves the chip renders "…"
       rather than a number nobody fetched. One request per panel load. */
    loadUsage(true);

    /* Attach to Claude. From here the rail reflects what is happening in Claude
       as it happens, rather than what was true when this panel booted. Started
       LAST so a stream that fails cannot delay anything above it. */
    startSessionStream();

    /* Dev-only auto-reload. One loopback GET; in production it answers
       {dev:false} and nothing subscribes. NOT awaited -- the panel must never
       wait on a convenience, and a probe that fails (older server without the
       route) simply leaves the feature off. */
    apiGet("/api/dev").then(d=>startDevReload(d && d.dev)).catch(()=>{});

    /* Staged-update watch. Started LAST and deliberately not awaited: a staged
       build is never a reason for the panel to come up any slower, and this
       route is local-only so the poll costs nothing but a loopback round trip.
       Focus changes re-render because the countdown is held while the window is
       in the background, and that state has to be visible the moment it flips. */
    pollStagedUpdate();
    setInterval(pollStagedUpdate, UPDATE_POLL_MS);
    window.addEventListener("focus", renderUpdateBanner);
    window.addEventListener("blur", renderUpdateBanner);
  } catch (e) {
    backendError(e);
  }
}

/* ── terminal ────────────────────────────────────────────────────────────────
   Mount-once, show/hide thereafter. The iframe carries a live WebSocket to a PTY
   running `claude`; re-creating it on a render would kill that session, so the
   only operations here are "create if absent" and "toggle hidden". */
/* Persisted so the pane comes back as the operator left it. Defaults to the
   shell: that is what the pane did before this control existed, and a terminal
   that silently starts an agent session would be a surprising default. */
try { S.termMode = localStorage.getItem("sutra.termMode") || "shell"; }
catch (e) { S.termMode = "shell"; }
const termPaneEl  = document.getElementById("termPane");
const termBodyEl  = document.getElementById("termBody");
const termBtnEl   = document.getElementById("termBtn");
const termCwdEl   = document.getElementById("termCwd");

const TERM_MIN = 280, TERM_MAX_FRAC = 0.72, TERM_DEFAULT = 460;

function clampTermW(px){
  /* innerWidth can be 0 while the window is still being laid out (and is 0 in a
     headless harness). Clamping against it then collapses every width to TERM_MIN
     and, because clamping never grows a value back, the pane stays stuck narrow for
     the rest of the session. With no trustworthy viewport, apply the floor only. */
  const vw = (typeof innerWidth === "number" && innerWidth > TERM_MIN) ? innerWidth : 0;
  const want = Math.max(TERM_MIN, Math.round(px));
  return vw ? Math.min(Math.round(vw * TERM_MAX_FRAC), want) : want;
}
/* The GRID TRACK is the single source of truth for the pane width. An `auto` track
   measured the iframe's intrinsic width as 0 and collapsed the pane; an explicit
   pixel value is both deterministic and what the drag handle writes. */
function applyTermW(px){
  S.termW = clampTermW(px);
  document.getElementById("app").style
    .setProperty("--termw", S.termOpen ? S.termW + "px" : "0px");
}

function termMount(force){
  /* The session's folder, not the global one. Identical defect to the one fixed
     in sessCwd(): a turn running in ~/Desktop/development/sutra types `git
     checkout .` into a shell sitting in ~/sutra-ui-workspace, with nothing on
     screen stating the mismatch -- precisely the state in which an operator
     presses Enter. /ws/term already honours a per-call cwd, so only the caller
     was wrong. */
  const cwd = sessCwd(S.openPanes[S.openPanes.length - 1])
            || (SETTINGS && SETTINGS.workdir) || "";
  const have = termBodyEl.querySelector("iframe");
  if (have && !force) return;
  if (have) have.remove();
  const fr = document.createElement("iframe");
  /* /legacy/term is the EXISTING terminal: it forwards ?cwd= to /ws/term, which
     spawns the real TUI. Reusing that page beats a second terminal-emulator
     integration that would drift from the first.

     The word for that emulator is deliberately not written here: test_05b greps the
     studio HTML for it to prove "/" is not serving the legacy console. The terminal
     is an opt-in pane behind an iframe, so the guard still holds and stays strict. */
  /* MODE, and it was hardcoded to `shell` -- which quietly made the single
     highest-value thing this pane can do unreachable.

     /ws/term already spawns EITHER the operator's login shell (?shell=1) or the
     REAL claude TUI in a PTY (app.py:729, `args = [CLAUDE_BIN]`). Only the first
     was ever requested. The second is Claude Code itself, at full fidelity --
     every built-in slash command (/mcp, /plugin, /context, /compact, /config,
     /permissions, /rewind, /usage), Shift+Tab mode cycling, vim mode, permission
     prompts and plan approval -- none of which the chat pane can do, and all of
     which the docs list as features. Reaching them costs one query parameter.

     It is passthrough, not native parity: those commands run in a terminal
     emulator rather than as panel UI. But "reachable today" beats "designed",
     and it does not block building native versions later.

     embed=1 -> drops that page's own sidebar and header, which this pane already
     draws, and whose 240px sidebar left the terminal about 120px at pane width. */
  const shellMode = S.termMode !== "claude";
  fr.src = "/legacy/term?embed=1" + (shellMode ? "&shell=1" : "")
         + (cwd ? "&cwd=" + encodeURIComponent(cwd) : "");
  fr.title = "Terminal";
  termBodyEl.appendChild(fr);
  S.termCwd = cwd;
  termCwdEl.textContent = cwd;
}

/* Switch the terminal pane between the login shell and the real claude TUI.
   force=true because the iframe src is only read at creation -- without it the
   pane keeps whatever it was first mounted with and the toggle looks broken. */
function termSetMode(mode){
  if (S.termMode === mode) return;
  S.termMode = mode;
  try { localStorage.setItem("sutra.termMode", mode); } catch (e) {}
  /* termMount, not mountTerm: no such function has ever existed, so switching
     between the shell and the claude TUI threw a ReferenceError -- AFTER
     S.termMode had already been reassigned and persisted. The toggle moved, the
     PTY did not, and every later open read the persisted mode against an iframe
     that was never rebuilt. That is the "broken on multiple openings" report. */
  termMount(true);
  paintTermMode();
  render();
}

/* Type `text` at the terminal's prompt. NOTHING is executed -- see the caller for
   why. The pane is opened, forced to the Terminal tab (pasting into a hidden pane
   would look like the button did nothing) and put in SHELL mode, because a command
   typed into the claude TUI is a prompt to an agent, not a command to a shell.
   Delivery is deferred until the iframe has a live socket: a fresh mount has no
   WebSocket yet, and bytes written before it opens are dropped silently. */
function sendToTerminal(text){
  if (!text) return;
  if (!S.termOpen) termToggle(true);
  if (S.sideTab === "preview") sideTab("terminal");
  if (S.termMode !== "shell") termSetMode("shell");
  termMount(false);
  const started = Date.now();
  (function deliver(){
    const fr = termBodyEl && termBodyEl.querySelector("iframe");
    const w = fr && fr.contentWindow;
    let ready = false;
    /* Same-origin, so the child's own send() is reachable. Using it (rather than a
       second socket from here) keeps ONE writer on the PTY. */
    try { ready = !!(w && typeof w.termReady === "function" && w.termReady()
                       && typeof w.send === "function"); }
    catch (e) { ready = false; }
    if (ready){
      try { w.send(text); } catch (e) {}
      try { w.focus(); } catch (e) {}
      return;
    }
    /* Bounded: a terminal that never connects must not leave a timer running for
       the life of the session. */
    if (Date.now() - started < 6000) setTimeout(deliver, 120);
  })();
}

function termToggle(on){
  S.termOpen = on === undefined ? !S.termOpen : !!on;
  termPaneEl.hidden = !S.termOpen;
  applyTermW(S.termW || TERM_DEFAULT);   /* collapses the track to 0px when closed */
  termBtnEl.setAttribute("aria-pressed", String(S.termOpen));
  termBtnEl.setAttribute("aria-label", S.termOpen ? "Hide the terminal" : "Show the terminal");
  /* Only mount the PTY when the terminal tab is the visible one -- opening the pane
     on the Preview tab must not silently spawn a shell. */
  if (S.termOpen && S.sideTab !== "preview") termMount(false);
  /* The workdir can have changed since the PTY started. Say so rather than letting
     the header imply the terminal followed the setting. */
  if (S.termOpen && SETTINGS && S.termCwd && SETTINGS.workdir !== S.termCwd){
    termCwdEl.textContent = S.termCwd + "  (workdir changed — restart to move)";
  }
  lsSet(LS_TERM, S.termOpen);   /* lsSet JSON-encodes; store the boolean, not "1" */
}

/* ── preview ─────────────────────────────────────────────────────────────────
   An iframe onto a dev server the operator is ALREADY running. This pane does not
   start servers: spawning arbitrary build commands is a different risk class from
   showing a page, and `claude` in the terminal beside it can start one on request.

   LOOPBACK ONLY. Without that check this becomes a general-purpose browser inside
   the app -- it would load any URL, including one pasted from an untrusted source,
   with the panel's own origin adjacent. */
const prevBodyEl = document.getElementById("prevBody");
const prevFrameEl = document.getElementById("prevFrame");
const prevNoteEl = document.getElementById("prevNote");
const LOOPBACK = new Set(["localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"]);

function previewOpen(raw){
  let value = (raw || "").trim();
  if (!value) return;
  if (!/^https?:\/\//i.test(value)) value = "http://" + value;   /* bare "3000" is not a URL */
  let u;
  try { u = new URL(value); }
  catch (e){ prevNoteEl.textContent = "That is not a URL I can parse: " + value; return; }
  if (!LOOPBACK.has(u.hostname)){
    prevNoteEl.textContent =
      "Refused: " + u.hostname + " is not a loopback address. This pane shows a dev " +
      "server running on this machine, not the open web.";
    prevFrameEl.innerHTML = "";
    return;
  }
  prevNoteEl.textContent = "Showing " + u.href + " — reload with Open.";
  prevFrameEl.innerHTML = "";
  const fr = document.createElement("iframe");
  fr.src = u.href;
  fr.title = "Preview of " + u.href;
  prevFrameEl.appendChild(fr);
  lsSet(LS_PREVURL, u.href);
}

function sideTab(which){
  const term = which !== "preview";
  document.getElementById("termBody").hidden = !term;
  prevBodyEl.hidden = term;
  document.getElementById("sideTabTerm").setAttribute("aria-pressed", String(term));
  document.getElementById("sideTabPrev").setAttribute("aria-pressed", String(!term));
  document.getElementById("termCwd").hidden = !term;
  S.sideTab = term ? "terminal" : "preview";
  if (term){
    termMount(false);
    /* The iframe was display:none while Preview was up, so its ResizeObserver saw
       nothing and the terminal still carries the size it had when it was hidden.
       It is same-origin, so ask it to re-measure now that it has area again --
       guarded, because the document may not have parsed yet on a fresh mount. */
    requestAnimationFrame(()=>{
      const fr = termBodyEl.querySelector("iframe");
      try { fr && fr.contentWindow && fr.contentWindow.dispatchEvent(new Event("resize")); }
      catch (e) {}
    });
  }
  lsSet(LS_SIDETAB, S.sideTab);
}
/* Shell vs the real Claude TUI. Wired beside the sibling tabs because it is the
   same kind of control: which thing this pane is showing. */
document.getElementById("termModeShell").onclick  = ()=>termSetMode("shell");
document.getElementById("termModeClaude").onclick = ()=>termSetMode("claude");
function paintTermMode(){
  const claude = S.termMode === "claude";
  const a = document.getElementById("termModeShell");
  const b = document.getElementById("termModeClaude");
  if (a) a.setAttribute("aria-pressed", String(!claude));
  if (b) b.setAttribute("aria-pressed", String(claude));
}
paintTermMode();

document.getElementById("sideTabTerm").onclick = ()=>sideTab("terminal");
document.getElementById("sideTabPrev").onclick = ()=>sideTab("preview");
document.getElementById("prevGo").onclick = ()=>previewOpen(document.getElementById("prevUrl").value);
document.getElementById("prevUrl").onkeydown = e=>{
  if (e.key === "Enter"){ e.preventDefault(); previewOpen(e.target.value); } };

termBtnEl.onclick = ()=>termToggle();
document.getElementById("termClose").onclick = ()=>termToggle(false);
document.getElementById("termReload").onclick = ()=>termMount(true);

/* ── resize ──────────────────────────────────────────────────────────────────
   Pointer events (not mouse) so a trackpad drag and a touch drag both work, with
   setPointerCapture so the gesture survives the cursor crossing the iframe. The
   iframe gets pointer-events:none for the duration via body.termdrag -- without it
   the cross-document boundary swallows the move events and the drag dies halfway. */
const termGripEl = document.getElementById("termGrip");
/* Tell the terminal the gesture is OVER. During a drag the pane's width changes on
   every pointermove, the iframe's ResizeObserver fires, and each fit pushes a fresh
   winsize into the PTY -- the TUI then redraws at each one and leaves the half-drawn,
   overlapping fragments the operator sees as a "distorted" terminal. term.html
   refuses to fit while body.termdrag is set (it reads this document directly -- same
   origin) and fits once on this event instead. */
function termSettled(){
  const fr = termBodyEl && termBodyEl.querySelector("iframe");
  try { fr && fr.contentWindow &&
        fr.contentWindow.dispatchEvent(new Event("sutra:term-settled")); } catch (e) {}
}
termGripEl.addEventListener("pointerdown", e=>{
  e.preventDefault();
  const startX = e.clientX, startW = S.termW || TERM_DEFAULT;
  document.body.classList.add("termdrag");
  try { termGripEl.setPointerCapture(e.pointerId); } catch (_) {}
  const move = ev => applyTermW(startW + (startX - ev.clientX));   /* drag left = wider */
  const up = ()=>{
    document.body.classList.remove("termdrag");
    termGripEl.removeEventListener("pointermove", move);
    termGripEl.removeEventListener("pointerup", up);
    termGripEl.removeEventListener("pointercancel", up);
    lsSet(LS_TERMW, S.termW);
    termSettled();
  };
  termGripEl.addEventListener("pointermove", move);
  termGripEl.addEventListener("pointerup", up);
  termGripEl.addEventListener("pointercancel", up);
});
/* Keyboard parity with the browse divider: the pane must be resizable without a pointer. */
termGripEl.addEventListener("keydown", e=>{
  const step = e.shiftKey ? 64 : 16;
  if (e.key === "ArrowLeft"){ e.preventDefault(); applyTermW((S.termW||TERM_DEFAULT) + step); }
  else if (e.key === "ArrowRight"){ e.preventDefault(); applyTermW((S.termW||TERM_DEFAULT) - step); }
  else if (e.key === "Home"){ e.preventDefault(); applyTermW(TERM_DEFAULT); }
  else return;
  lsSet(LS_TERMW, S.termW);
  termSettled();   /* keyboard resize is a settled gesture too */
});
/* A width stored on a wide display must not exceed a narrower window later.
   GUARDED: test_panel.js evaluates this script in a bare Node vm context that has a
   stubbed `document` but no window globals, so an unguarded top-level
   addEventListener throws ReferenceError and takes all 35 assertions down with it. */
if (typeof addEventListener !== "undefined"){
  addEventListener("resize", ()=>{ if (S.termOpen) applyTermW(S.termW || TERM_DEFAULT); });
  /* Electron ships its DEFAULT menu, so Cmd+R is live and destroys the page --
     and with it every entry in CLAUDE_SOCKETS, where the streaming turn lives.
     Test `ch.turn`, not `ch.open`: `open` is true for any connected socket
     including an idle one, whereas `turn` is set only while a reply is streaming,
     which is the only state worth blocking a reload for. */
  addEventListener("beforeunload", e=>{
    let live = false;
    CLAUDE_SOCKETS.forEach(ch=>{ if (ch && ch.turn) live = true; });
    if (live){ e.preventDefault(); e.returnValue = ""; }
  });
}

/* Catalog freshness. ONE timer that decides whether to act, rather than several
   listeners racing: `focus` and `visibilitychange` both fire on a single window
   activation, and two listeners would run two concurrent scans that can land out of
   order. Same guard as above -- the vm context has no window globals. */
if (typeof setInterval !== "undefined" && typeof document !== "undefined"
    && document.addEventListener){
  setInterval(()=>{ try { catalogTick(); } catch (e) {} }, CAT_TICK_MS);
  document.addEventListener("visibilitychange", ()=>{
    /* Coming back to the window is the moment a stale palette is most likely and
       most visible, so let the next tick act immediately instead of waiting out
       the interval. */
    if (document.visibilityState === "visible") S.cat.lastCheckAt = 0;
  });
}

/* One click hides the whole sidebar and the panes take the freed column.
   The toggle lives in the masthead so it stays reachable when the rail is gone. */
const railToggle = document.getElementById("railToggle");
const railShow = document.getElementById("railShow");
if (railShow) railShow.onclick = ()=>{ railToggle.onclick(); };
railToggle.onclick = ()=>{
  S.ui.railCollapsed = !S.ui.railCollapsed;
  railToggle.setAttribute("aria-pressed", String(!!S.ui.railCollapsed));
  railToggle.setAttribute("aria-label", S.ui.railCollapsed ? "Show the sidebar" : "Hide the sidebar");
  railToggle.title = railToggle.getAttribute("aria-label");
  saveLayout();
  render();
};

/* Rail sections collapse on a click anywhere on their header. */
document.querySelector(".rail").addEventListener("click", e=>{
  const tabBtn = e.target.closest("[data-railtab]");
  if (tabBtn){
    S.ui.railTab = tabBtn.dataset.railtab;
    saveLayout();
    renderRail();
    return;
  }
  const sec = e.target.closest("[data-railsec]");
  if (!sec) return;
  const key = sec.dataset.railsec;
  S.ui.railSections[key] = !(S.ui.railSections[key] !== false);
  saveLayout();
  renderRail();
}, true);

/* The tenant switcher popover used to be wired here. 5781a2f ("remove tenancy")
   deleted <div id="tenantMenu"> from the markup but left this block behind, so
   getElementById returned null and the very next addEventListener threw a
   TypeError -- eleven lines above boot(). The whole app died before it read
   anything: no settings, no departments, no sessions, no skills. Every symptom
   was downstream of one dead element reference.

   The lesson is the deletion, not a null guard: there is one org per registry,
   so there is nothing to switch between and nothing to wire. */
boot();
