/* Run whatever render() was deferred during a drag. Called from dragend and
   from every early-return path in ondrop, so a deferred render can never be
   stranded. */
function flushRender(){ if (S.renderDirty) render(); }

/* Drag the browse/session divider. The drag writes the width straight onto the
   element instead of re-rendering per mousemove -- a full innerHTML rebuild at
   60Hz would tear down the very button being dragged. State is persisted once,
   on mouseup. Arrow keys do the same thing for keyboard users; Home clears the
   override and returns the pane to its default flex ratio. */
function wireDivider(){
  const d = document.getElementById("pdiv");
  if (!d) return;
  const panes = document.getElementById("panes");
  const browse = panes.querySelector(".pane.browse");
  if (!browse) return;
  const apply = w => { S.ui.browseW = Math.round(w);
    if (typeof invalidatePanesHtml === "function") invalidatePanesHtml();  /* r8 */
    browse.style.flex = "0 0 " + Math.round(w) + "px"; browse.style.maxWidth = "none"; };
  /* The SAME ceiling render() applies to a restored width -- a drag must not
     be able to reach a width the next reload would clamp away. */
  const limit = browseMax;
  d.onmousedown = e => {
    e.preventDefault();
    d.classList.add("dragging");
    const startX = e.clientX, startW = browse.getBoundingClientRect().width;
    const move = ev => apply(Math.max(BROWSE_MIN, Math.min(limit(), startW + (ev.clientX - startX))));
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      d.classList.remove("dragging");
      saveLayout();
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  };
  d.onkeydown = e => {
    const cur = S.ui.browseW || browse.getBoundingClientRect().width;
    if (e.key === "ArrowLeft"){ e.preventDefault(); apply(Math.max(BROWSE_MIN, cur - 24)); saveLayout(); }
    else if (e.key === "ArrowRight"){ e.preventDefault(); apply(Math.min(limit(), cur + 24)); saveLayout(); }
    else if (e.key === "Home"){ e.preventDefault(); S.ui.browseW = null; saveLayout(); render(); }
  };
}


/* ── per-TURN controls: delegated, not per-render ─────────────────────────────
   Every control inside a turn's assistant block dies the moment patchTurn()
   replaces that block: wire() binds b.onclick per render, outerHTML swaps the
   nodes, and the fresh copies have no handler until the NEXT full render.
   During streaming that gap is the normal state — which is why, observed live,
   the thinking-log toggle did nothing mid-turn. The shipped output/terminal
   buttons had the same dead window.
   ONE document-level listener (registered once at boot, same guarded pattern as
   the popover dismiss) survives any number of patches. The per-render bindings
   for these five controls are REMOVED — a click must never fire twice.
   Scoped to .turn so nothing outside a chat turn is ever intercepted; dataset
   values are captured before any await, because the node a click landed on may
   be replaced while the handler is in flight. */
function turnControlClick(e){
  const inTurn = e.target && e.target.closest && e.target.closest(".turn");
  if (!inTurn) return;

  const think = e.target.closest("[data-thinkopen]");
  if (think){
    const uid = think.dataset.thinkopen;
    if (!uid) return;
    S.thinkOpen = S.thinkOpen || {};
    if (S.thinkOpen[uid]) delete S.thinkOpen[uid];
    else S.thinkOpen[uid] = true;
    render();
    return;
  }
  const gov = e.target.closest("[data-govopen]");
  if (gov){
    const uid = gov.dataset.govopen;
    if (!uid) return;
    S.govOpen = S.govOpen || {};
    S.govOpen[uid] = !S.govOpen[uid];
    render();
    return;
  }
  const tout = e.target.closest("[data-toolout]");
  if (tout){
    S.toolOpen[tout.dataset.toolout] = !S.toolOpen[tout.dataset.toolout];
    render();
    return;
  }
  /* TYPES the command and stops — never runs it. The agent ran this once
     already; a second run is a NEW side effect behind a look-at-it control. */
  const term = e.target.closest("[data-toolterm]");
  if (term){
    const id = term.dataset.toolterm;
    let run = null;
    S.sessions.forEach(s=>(s.turns||[]).forEach(t=>
      (t.toolRuns||[]).forEach(r=>{ if (r.id === id) run = r; })));
    Object.keys(S.sideTurns||{}).forEach(sid=>(S.sideTurns[sid]||[]).forEach(t=>
      (t.toolRuns||[]).forEach(r=>{ if (r.id === id) run = r; })));
    if (!run || !run.command) return;
    sendToTerminal(run.command);
    return;
  }
  /* Drill down from a turn's agent roster into the subagent fold below it.
     No new surface: opens the fold that already ships with that agent selected.
     Async because the agent list may not be fetched yet; the fold opens FIRST so
     the click feels immediate. Everything the handler needs from the DOM is
     captured HERE, before the await — the row may not exist afterwards. */
  const row = e.target.closest("[data-agentrow]");
  if (row){
    const pane = row.closest(".pane[data-sess]");
    const sid = pane && pane.dataset.sess;
    if (!sid) return;
    const kind = row.dataset.agkind, desc = row.dataset.agdesc;
    /* rows in THIS turn sharing this key — agentMatch() refuses >1, because two
       indistinguishable rows must not both claim whichever transcript exists */
    const group = row.closest(".gv-agents");
    const peers = group
      ? Array.prototype.filter.call(group.querySelectorAll("[data-agentrow]"),
          x => x.dataset.agkind === kind && x.dataset.agdesc === desc).length
      : 1;
    /* only the newest click may apply — a slow fetch from an earlier click must
       not overwrite what the operator is looking at now */
    const token = (S._agentClick = (S._agentClick || 0) + 1);
    S.agentNote = S.agentNote || {};
    delete S.agentNote[sid];
    S.agentsFold[sid] = true;
    render();
    (async () => {
      try { await loadAgents(sid, false); }
      catch (err){ S.agentNote[sid] = "Could not read this session's subagents."; render(); return; }
      if (token !== S._agentClick) return;
      const hit = agentMatch(S.agents[sid], kind, desc, peers);
      if (hit){
        S.agentOpen[sid] = hit.id;
        loadAgentTranscript(sid, hit.id);
      } else {
        const list = S.agents[sid];
        S.agentNote[sid] = peers > 1
          ? "Two agents in this turn have the same type and description, so this row "
            + "cannot be told apart from its twin — open the one you want below."
          : (list && list.length)
            ? "Could not tell which transcript belongs to this row — it may still be "
              + "running, or its transcript is not on disk yet."
            : "No subagent transcript on disk for this agent yet.";
      }
      render();
    })();
  }
}

/* Close a pane. ONE path for the header's old × and the ⋯ menu's Close row.
   "browse" is the screens pane, not a session: nothing to hang up, and the
   closed state persists like a pane collapse does. Session ids are UUIDs, so
   the sentinel can never collide with one. */
function closePane(sid){
  if (sid === "browse"){ S.ui.browseClosed = true; saveLayout(); render(); return; }
  /* Returns the channels it KEPT because work was still in flight. Closing the
     pane hides the view; it does not cancel the reply. Say so, because the
     control now does something different from what it used to. */
  const kept = closeClaudeChannel(sid);
  S.openPanes = S.openPanes.filter(id=>id!==sid);
  if (kept.length){
    const s = S.sessions.find(x=>x.id===sid);
    S.toast = "Still running in the background — reopen “" +
              ((s && s.title) || "the session") + "” to watch it finish.";
    setTimeout(()=>{ if (S.toast) { S.toast = null; render(); } }, 6000);
  }
  render();
}

/* The ⋯ pane menu's rows (chat-surface chrome, founder 2026-08-18). Each row
   mutates EXACTLY the state the header control it replaced used to mutate --
   no second code path -- and every row closes the menu. Permissions and Model
   are not here: they are <label>s around the existing selects, so the
   [data-perm]/[data-model] handlers own them unchanged. */
function paneMenuAction(sid, key){
  S.paneMenu = null;
  switch (key){
    case "folder": S.cwdEdit = sid; S.cwdError = null; break;
    /* the repo bar's two buttons, now rows: same state, same loaders */
    case "prs":    S.prsOpen = sid; render(); loadPrs(sid, true); return;
    case "pr": {
      const r = (S.repo && S.repo[sid]) || {};
      S.prForm = { sid, head: r.branch || "", base: (r.upstream || "").replace(/^origin\//, "") || "main", title: "", body: "" };
      S.prError = null; S.prDone = null; render();
      const t = document.querySelector("[data-prf='title']"); if (t && t.focus) t.focus();
      return;
    }
    case "usage":  S.usagePop = sid; if (typeof loadUsage === "function") loadUsage(true); break;
    case "route":  S.sessTab[sid] = (S.sessTab[sid] || "chat") === "route" ? "chat" : "route"; break;
    case "opts":   S.optsOpen[sid] = !S.optsOpen[sid]; break;   /* the ≡ control, now a row */
    case "fold":   S.ui.paneCollapsed[sid] = true; saveLayout(); break;
    case "close":  closePane(sid); return;          /* renders itself */
    default: break;
  }
  render();
}

/* ── Codex sign-in state ────────────────────────────────────────────────────
   GET /api/providers/codex/auth spawns `codex login status`, so it is
   deliberately NOT in boot()'s allSettled and NOT folded into /api/settings:
   those are read on every boot and every settings open, and a subprocess does
   not belong on either path. This runs when the AI Provider screen opens and
   after each sign-in action. There is nothing to cache -- being current is the
   entire value of the call. */
async function loadCodexAuth(force){
  /* Guarded because wire() re-enters this on EVERY render (see the wire() call
     site). `force` bypasses both guards: re-opening the screen and finishing an
     action must both be able to supersede a probe that is still in flight. */
  if (S.codexProbing && !force) return;
  if (S.codexAuth && !force) return;
  S.codexProbing = true;
  try {
    const a = await apiGet("/api/providers/codex/auth");
    /* A 200 THAT CARRIES NO STATE IS NOT AN ANSWER. Storing it would leave
       S.codexAuth falsy, the loading state on screen, and the wire() guard
       re-firing forever -- a permanent "Reading the Codex sign-in..." is the
       worst outcome available here, worse than saying we could not tell. */
    S.codexAuth = (a && typeof a === "object" && a.state) ? a : {
      state:"unknown", key_display:"", billing:null,
      detail:"the sign-in endpoint answered without a state" };
  }
  catch (e){
    /* A FAILED FETCH IS NOT A SIGNED-OUT CODEX. Rendered as the server's own
       unrecognised-answer case -- unknown, with the reason -- so a dead
       endpoint can never read as "not signed in", and never as a billing mode. */
    S.codexAuth = { state:"unknown", key_display:"", billing:null,
                    detail:"the panel could not read the Codex sign-in — " + e.message };
  }
  finally { S.codexProbing = false; }
  /* The loader owns the render, the way loadWorkspace does. This is what lets
     every caller be a bare call: an early return renders nothing, so no caller
     can turn a guard-blocked call into a render loop. */
  render();
}

/* Does the Codex block need its data fetched right now?

   PURE, so the condition that answers "does the probe ever fire?" can be
   tested without a DOM. wire() asks this on every render; openScreen forces
   independently of it.

   Off-screen is false (nothing renders it, so nothing needs it), and an answer
   already in hand is false INCLUDING the honest unknown -- otherwise a failed
   probe would re-fire on every render for as long as the screen stayed open.

   SPLIT from codexOnScreen deliberately. The sign-in POLL needs the screen
   half ALONE: during a poll an answer is always in hand, so this predicate is
   false on the first tick and would stop the watch immediately. Two questions,
   two functions. */
function codexOnScreen(){ return S.screen === "settings"; }

function codexNeedsProbe(){
  return codexOnScreen() && !S.codexAuth;
}

/* The desktop shell's bridge, or null. PREFERRED wherever it exists: it
   spawns without a request, and the API key can only travel that way. */
function codexBridge(){
  return (window.sutra && window.sutra.codexLogin) ? window.sutra : null;
}

/* The DeepSeek write path, or null. Keyed on ITS OWN verb rather than reusing
   codexBridge(): the two shipped separately, and a shell built before this
   change exposes window.sutra with codexLogin and no deepseekKeySave. Keying
   off the wrong verb would draw a field whose only transport is absent. */
function deepseekBridge(){
  return (window.sutra && window.sutra.deepseekKeySave) ? window.sutra : null;
}

/* ── the browser's own write token ──────────────────────────────────────────
   The second lane into POST /api/providers/deepseek/key, for a server started
   from a terminal rather than by the Electron shell. That server prints a
   one-time code on its stdout; POST /providers/deepseek/session trades the code
   for this token; every key write then carries it in a header.

   WHY sessionStorage AND NOT localStorage. The token dies with the server
   process, so a localStorage copy would outlive the thing it authorises and
   sit in the profile as a dead credential-write capability across reboots.
   sessionStorage survives a RELOAD -- which is the case that matters, since
   the code is single-use and a reload must not cost you the pairing -- and
   goes when the tab does.

   WHY IN STORAGE AT ALL AND NOT JUST A MODULE `let`. A module variable dies on
   reload, and with a single-use code the only recovery is restarting the
   server. Reloading the panel is not a reason to restart a backend.

   EVERY ACCESS IS GUARDED. sessionStorage throws outright in a Safari private
   window and in some embedded webviews, and the panel must render there --
   without a field it cannot use, but rendering. */
const DEEPSEEK_SESSION_KEY = "sutra.deepseek.session";

function deepseekSessionToken(){
  try { return sessionStorage.getItem(DEEPSEEK_SESSION_KEY) || null; }
  catch (e) { return null; }
}
function deepseekSetSessionToken(token){
  try { sessionStorage.setItem(DEEPSEEK_SESSION_KEY, token); return true; }
  catch (e) { return false; }
}
function deepseekClearSessionToken(){
  try { sessionStorage.removeItem(DEEPSEEK_SESSION_KEY); } catch (e) {}
}

/* Can this page write a key at all, by either lane? The render asks this, not
   "is there a bridge" -- that question is what drew a dead Remove button on
   every browser before the session lane existed. */
function deepseekCanWrite(){
  return !!deepseekBridge() || !!deepseekSessionToken();
}

/* ── watching a browser-transport sign-in ───────────────────────────────────
   The two transports have DIFFERENT completion semantics, and this is the
   whole reason the poll exists. The IPC verb resolves when the child EXITS.
   POST /providers/codex/login returns the instant the child is spawned -- it
   must, because the flow waits on a human and holding the request open would
   park a threadpool worker, leave nothing to cancel (apiGet has no timeout)
   and orphan the child on a reload. So the panel watches the CREDENTIAL
   instead, which is the better signal anyway: what matters is not that codex
   exited, it is what codex now holds.

   FOUR STOP CONDITIONS. A poll with no way to end is the same class of waste
   as the render loop this file already had:

     1. the state changed          -- the sign-in landed, or was rejected
     2. !codexOnScreen()           -- nobody is looking at the row any more
     3. S.codexBusy is not "login" -- cancelled, or superseded
     4. the deadline               -- just past the server's own 180s cap

   Generation-counted so a second sign-in supersedes the first watcher rather
   than running two, and setTimeout-chained rather than setInterval so a slow
   probe cannot stack ticks. */
const CODEX_POLL_MS = 2000;
const CODEX_POLL_CAP_MS = 190000;
let _codexPollGen = 0;

function codexStopPoll(){
  _codexPollGen++;                 /* invalidates any tick already scheduled */
  S.codexPolling = false;
}

function codexWatchLogin(before){
  const gen = ++_codexPollGen;
  S.codexPolling = true;
  const deadline = Date.now() + CODEX_POLL_CAP_MS;
  const tick = async () => {
    if (gen !== _codexPollGen) return;                       /* superseded */
    if (!codexOnScreen()){
      /* Stop watching, but do NOT cancel: the server child is still running
         and will finish or hit its cap on its own. Coming back to the screen
         re-adopts it through login_in_flight. */
      S.codexPolling = false; S.codexBusy = null; render(); return;
    }
    if (S.codexBusy !== "login"){ S.codexPolling = false; return; }
    await loadCodexAuth(true);
    if (gen !== _codexPollGen) return;
    const now = (S.codexAuth || {}).state;
    if (now !== before){
      /* The row states the new credential itself, so there is no message to
         add -- a "Signed in." banner next to "Signed in with ChatGPT" is the
         same fact twice. */
      S.codexPolling = false; S.codexBusy = null; S.codexMsg = null; render(); return;
    }
    if (Date.now() > deadline){
      S.codexPolling = false; S.codexBusy = null;
      S.codexMsg = "the sign-in did not finish. If no browser window opened, "
                 + "run `codex login` in a terminal.";
      render(); return;
    }
    setTimeout(tick, CODEX_POLL_MS);
  };
  setTimeout(tick, CODEX_POLL_MS);
}

/* The warning a codex action needs, or null when it destroys nothing.

   PURE AND SEPARATE so the invariant can be pinned by a test: every action
   that REPLACES the stored credential warns first, and nothing else nags. It
   is derived from the state just read, never encoded in the button, so a stale
   render cannot warn about the wrong direction.

   Codex holds exactly one credential and each sign-in method replaces the
   other -- and Sutra never had a copy of either, so nothing here can put one
   back. That is the fact each of these sentences has to carry. */
function codexConfirmText(verb, state){
  if (verb === "logout")
    return "Sign Codex out?\n\nThis removes the credential the codex CLI is holding on "
      + "this Mac. Sutra never had a copy, so nothing here can restore it."
      + (state === "api_key" ? " You would need the API key itself to sign back in." : "");
  if (verb === "login" && state === "api_key")
    return "Switch to a ChatGPT sign-in?\n\nCodex stores one credential, so signing in "
      + "with ChatGPT REPLACES the API key it holds now. Sutra never had a copy of that "
      + "key, so it cannot be restored here — you would need the key itself to go back.";
  if (verb === "apikey" && state === "chatgpt")
    return "Add an API key instead of your ChatGPT sign-in?\n\nCodex stores one "
      + "credential, so the API key REPLACES the ChatGPT sign-in. You would then pay per "
      + "token instead of drawing on your plan, and you would have to sign in with "
      + "ChatGPT again to go back.";
  return null;                 /* signing in from signed-out destroys nothing */
}

/* Re-read after an action, with ONE delayed retry when the state did not move.

   THE 1500ms IS A TIMING HEDGE, NOT A FIX. codex writes ~/.codex/auth.json as
   it finishes and the probe is a separate process, so a re-read that starts
   immediately can lose the race and show the previous credential. The robust
   version watches auth.json's mtime (or has the bridge resolve only once the
   file has changed) instead of sleeping. Kept identical to the Claude sign-in
   handler's hedge rather than invented here, so both age the same way. */
async function codexReprobe(expectChange){
  const before = (S.codexAuth || {}).state;
  /* FORCE, both times. An action has just changed the credential, so the
     answer in hand is precisely the STALE one -- without force the guard
     short-circuits the read and the row keeps showing the state from before
     the sign-in, which is the single thing this row exists not to do. */
  await loadCodexAuth(true);
  if (expectChange && (S.codexAuth || {}).state === before)
    setTimeout(()=>{ loadCodexAuth(true); }, 1500);
}

function wire(){
  /* With the browse pane closed there is no #scBody. A detached node keeps
     every scBody.querySelectorAll below a no-op instead of a TypeError that
     would kill wire() before the session panes got their handlers. */
  const scBody = document.getElementById("scBody") || document.createElement("div");
  const panes  = document.getElementById("panes");

  /* ── layout affordances (collapse, fold, resize) ── */
  panes.querySelectorAll("[data-pane-fold]").forEach(b=>b.onclick=()=>{
    const id = b.dataset.paneFold;
    if (S.ui.paneCollapsed[id]) delete S.ui.paneCollapsed[id];
    else S.ui.paneCollapsed[id] = true;
    saveLayout(); render(); });
  scBody.querySelectorAll("[data-fold]").forEach(b=>b.onclick=()=>{
    /* read the state off the button rather than recomputing the default -- some
       folds ship closed (an empty provider group) and a hardcoded default here
       would invert their first click */
    S.ui.folds[b.dataset.fold] = b.getAttribute("aria-expanded") === "true" ? 0 : 1;
    saveLayout(); render(); });
  wireDivider();

  /* ── settings: every control posts, and reports the server's refusal ── */
  /* ── updates ── */
  scBody.querySelectorAll("[data-upd]").forEach(b=>b.onclick=()=>{
    const what = b.dataset.upd;
    if (what === "check") checkUpdates();
    else if (what === "shell-stage") shellStage();
    else if (what === "shell-apply") shellApply();
    else installUpdate(what);
  });

  /* ── account sign-in (Usage screen) ── the same button cancels while a
     sign-in runs; on completion the account+usage re-read shows who won.
     One delayed retry covers the CLI still flushing ~/.claude.json. */
  scBody.querySelectorAll("[data-auth-login]").forEach(b=>b.onclick=async()=>{
    if (!(window.sutra && window.sutra.authLogin)) return;
    if (S.authBusy){ try { window.sutra.authLogin(); } catch(e){} return; }
    S.authBusy = true; S.authMsg = null; render();
    let r = null;
    try { r = await window.sutra.authLogin(); }
    catch(e){ r = { ok:false, error: e.message }; }
    S.authBusy = false;
    S.authMsg = r && r.ok ? "Signed in." : ((r && r.error) || "sign-in did not complete");
    await loadUsage(true);
    if (r && r.ok && !(S.account && S.account.available))
      setTimeout(()=>{ loadUsage(true).then(()=>render()); }, 1500);
    render();
  });

  scBody.querySelectorAll("[data-prov]").forEach(b=>b.onclick=()=>{
    if (b.disabled) return;                       /* not runnable -- the reason is on screen */
    S.setBusy = "prov:" + b.dataset.prov; S.setError = null; S.setOk = null; render();
    apiPost("/api/providers/active", { id: b.dataset.prov })
      .then(r=>{ PROVIDERS = r.providers || PROVIDERS;
                 SETTINGS = r.settings || SETTINGS;
                 /* THE NEW PROVIDER APPLIES TO WHATEVER YOU DO NEXT (founder
                    direction 2026-09-03), and that is only true if the open
                    sockets go. A socket is bound to its provider at spawn --
                    the binary and the protocol are both fixed there -- so a
                    message sent down an existing one would reach the OLD
                    provider while the UI claimed otherwise.

                    Dropping them here is the same move setSessProvider made
                    before selection came back to Settings. Nothing is sent and
                    nothing is replayed now: the next PROMPT opens a fresh
                    socket, and the server carries that chat's history across
                    if it had any. So a Settings change costs nothing until you
                    actually use a chat.

                    A pane mid-reply is left alone: closing it would discard a
                    reply the operator is waiting on. That pane finishes on the
                    old provider and moves on its next message. */
                 let kept = 0;
                 [...CLAUDE_SOCKETS.keys()].forEach(k=>{
                   const sid = k.replace(/::side$/, "");
                   if (streamingFor(sid) || sideStreamingFor(sid)){ kept++; return; }
                   const ch = CLAUDE_SOCKETS.get(k);
                   try { ch.ws.close(); } catch (e) {}
                   CLAUDE_SOCKETS.delete(k);
                 });
                 /* REFETCH USAGE FOR THE PROVIDER WE JUST SWITCHED TO.
                    Usage renders as a section of this very screen, and the two
                    providers keep their figures in different state (S.usage vs
                    S.deepseekUsage). Without this the section sat on "Reading
                    usage…" indefinitely: nothing had asked for the new
                    provider's numbers, and the screen-open trigger does not
                    fire because you never left the screen. force=true because
                    loadUsage early-returns on already-populated state, which
                    after a switch belongs to the OTHER provider. */
                 if (typeof loadUsage === "function") loadUsage(true);
                 S.setOk = "new chats and your next message use " + r.active + "."
                         + (kept ? " A chat is still replying and will move after it finishes." : ""); })
      .catch(e=>{ S.setError = e.message; })
      .then(()=>{ S.setBusy = null; render(); }); });
  /* ── Codex sign-in (AI Provider screen) ──────────────────────────────────
     BOTH ENTRY PATHS ask for the probe, the way loadWorkspace is entered from
     openScreen AND from wire(). openScreen alone was not enough: boot()
     restores S.screen DIRECTLY (09-tail.js:125) when the destination
     remembers this screen, so the shell can come up ON the AI Provider
     screen without openScreen ever running -- nothing asked for the probe and
     the block sat on "Reading the Codex sign-in..." forever. A permanent
     loading state is the worst answer this block can give: it is a promise
     that something is coming, and nothing was.

     Cannot loop, though wire() runs on every render: loadCodexAuth returns
     early once an answer (including the honest unknown) is in hand, and a
     stateless 200 is coerced to unknown rather than left falsy.

     AND NO RENDER IS CHAINED HERE. `loadCodexAuth().then(()=>render())` is what
     shipped first and it FROZE THE PANEL: while a probe is in flight the
     predicate is still true, the loader early-returns, and an early return is
     an ALREADY-RESOLVED promise -- so the chained render fires, re-enters
     wire(), early-returns again, and loops at microtask speed, rebuilding the
     whole panel and re-binding every handler each time. Nothing could paint or
     take input until the probe landed, and because apiGet has no timeout, a
     probe that never lands never ends the loop. The loader renders its OWN
     result instead; a call that does nothing produces nothing. */
  if (codexNeedsProbe()) loadCodexAuth();
  /* ADOPT a sign-in the server is still running. After a reload, or after
     leaving and returning to this screen, no watcher exists but a child does --
     login_in_flight is how the panel finds out. Guarded by codexPolling so
     wire(), which runs on every render, cannot start a second one. */
  if (codexOnScreen() && (S.codexAuth || {}).login_in_flight && !S.codexPolling){
    S.codexBusy = "login";
    codexWatchLogin((S.codexAuth || {}).state);
  }

  /* Separate from the Claude [data-auth-login] handler above by direction, not
     by accident: that verb is untouched and this one copies its shape.

     Every spawn runs in the DESKTOP SHELL, never behind an HTTP route -- the
     API key reaches codex on stdin and the backend port is unauthenticated,
     so a route that took a key would be a credential-write surface any local
     page could reach. In a browser there is no bridge, the row renders the CLI
     commands as text, and these buttons do not exist to be clicked.

     BOTH SWITCH ACTIONS AND SIGN OUT CONFIRM FIRST. Codex holds exactly one
     credential and each method replaces the other, so a switch DESTROYS what
     is there -- and Sutra never had a copy to restore. The warning is derived
     from the state we just read, not encoded in the button, so a stale render
     cannot warn about the wrong direction. Same shape as the connector
     disconnect confirm in 12-connectors.js. */
  scBody.querySelectorAll("[data-codex]").forEach(b=>b.onclick=async()=>{
    const verb = b.dataset.codex;
    const bridge = codexBridge();
    const st = (S.codexAuth || {}).state;
    /* Same normalisation the row renders from: a sign-in the SERVER is running
       is busy even if this page was reloaded and has forgotten about it. */
    const busyNow = S.codexBusy || ((S.codexAuth || {}).login_in_flight ? "login" : null);

    if (verb === "apikey:cancel"){ S.codexKeyOpen = false; S.codexMsg = null; render(); return; }

    /* Reveal the key field. From a ChatGPT sign-in this is a SWITCH, so it
       warns before the field even appears -- the point of no return is the
       click that says "yes, replace it", not the typing. */
    if (verb === "apikey"){
      /* Bridge-only. The row does not draw this button without one, so this is
         the belt: a stale render must not open a field whose only transport is
         absent. */
      if (!bridge) return;
      const warnSwitch = codexConfirmText("apikey", st);
      if (warnSwitch && !confirm(warnSwitch)) return;
      S.codexKeyOpen = true; S.codexMsg = null; render(); return;
    }

    /* The button that started a spawn doubles as Cancel.

       ON THE BRIDGE it re-invokes the SAME verb -- the shell SIGTERMs its
       running child and answers "cancelled". codexApiKey is re-invoked with no
       key on purpose: the main process checks for a running child before it
       validates one.

       OVER HTTP there is an explicit route, because a second POST /login is a
       409 rather than a cancel: an HTTP verb that quietly means the opposite
       thing on its second call is a worse contract than naming the operation. */
    if (busyNow){
      if (bridge){
        try {
          if (verb === "login") bridge.codexLogin();
          else if (verb === "logout") bridge.codexLogout();
          else if (verb === "apikey:save") bridge.codexApiKey("");
        } catch (e) {}
        return;
      }
      codexStopPoll();
      S.codexBusy = null; S.codexMsg = null; render();
      try { await apiPost("/api/providers/codex/login/cancel", {}); }
      catch (e){ S.codexMsg = e.message; }
      await codexReprobe(false);
      render();
      return;
    }

    const warn = codexConfirmText(verb, st);
    if (warn && !confirm(warn)) return;

    let key = null;
    if (verb === "apikey:save"){
      /* Read off the DOM at click time and never stored: not in S, not in
         localStorage, not posted anywhere. It goes to the bridge and is
         dropped when this handler returns. */
      const input = scBody.querySelector("[data-codex-key]");
      key = input ? input.value : "";
      if (!key || !key.trim()){ S.codexMsg = "Enter a key first."; render(); return; }
    }

    if (!(verb === "login" || verb === "logout" || verb === "apikey:save")) return;
    if (verb === "apikey:save" && !bridge) return;    /* no HTTP path, by design */
    S.codexBusy = verb;
    S.codexMsg = null; render();

    /* THE BROWSER SIGN-IN IS THE ONE ACTION THAT DOES NOT REPORT ITS OWN
       OUTCOME. The route answers as soon as the child exists, so there is
       nothing to await but the spawn -- the credential is watched instead. */
    if (verb === "login" && !bridge){
      const before = (S.codexAuth || {}).state;
      try {
        await apiPost("/api/providers/codex/login", {});
        codexWatchLogin(before);
      } catch (e){
        S.codexBusy = null;
        S.codexMsg = e.message;
        render();
      }
      return;
    }

    let r = null;
    try {
      if (bridge){
        r = verb === "login" ? await bridge.codexLogin()
          : verb === "logout" ? await bridge.codexLogout()
          : await bridge.codexApiKey(key);
      } else {
        /* logout only -- login returned above, and apikey has no HTTP path.
           confirm:true is REQUIRED by the route: the dialog above is
           client-side, so the flag is what stops a bare POST from destroying a
           credential nobody can restore. */
        const out = await apiPost("/api/providers/codex/logout", { confirm: true });
        r = { ok: out && out.ok !== false, error: out && out.reason };
        /* The route answers with the fresh probe, so the row is already
           current without a second round trip. */
        if (out && out.auth) S.codexAuth = out.auth;
      }
    } catch (e){ r = { ok:false, error: e.message }; }
    key = null;
    S.codexBusy = null;
    S.codexKeyOpen = false;
    S.codexMsg = r && r.ok
      ? (verb === "logout" ? "Signed out." : "Done.")
      : ((r && r.error) || "codex did not finish");
    /* RE-READ rather than assume. The action reports whether the CLI exited 0,
       which is not the same fact as which credential it now holds -- and this
       row exists to state the second one. */
    await codexReprobe(!!(r && r.ok));
    render();
  });

  /* ── DeepSeek sign-in ─────────────────────────────────────────────────────
     Separate from the codex handler above by DIRECTION, not by accident: that
     one asks a CLI to change a credential it owns and then re-reads what it
     holds. This one hands Sutra a key to keep, and the response already
     carries the new state, so there is nothing to re-probe -- PROVIDERS and
     SETTINGS are replaced from the same read that performed the write, which
     is what makes DeepSeek selectable on this paint rather than the next one.

     TWO LANES, and the render picks which one it drew a control for. The
     desktop bridge when the Electron shell is here -- the key then never
     crosses an HTTP request at all. Otherwise the token this page traded a
     one-time code for, sent as a header on the same route. What there is still
     no lane for is a browser holding NEITHER: deepseekAuthHtml draws the code
     field or the environment variables instead of a field that could only
     403. */
  scBody.querySelectorAll("[data-deepseek]").forEach(b=>b.onclick=async()=>{
    const verb = b.dataset.deepseek;
    const bridge = deepseekBridge();
    if (S.deepseekBusy) return;                        /* belt: a stale render */

    /* ── pair: trade the printed code for this page's write token ──────────
       Sent through apiPost like any other panel write. The CODE is read off
       the DOM at click time and never stored -- same discipline the key gets
       below -- and the token that comes back is the only thing kept. */
    if (verb === "pair"){
      const field = scBody.querySelector("[data-deepseek-code]");
      const code = field ? field.value : "";
      if (!code || !code.trim()){
        S.deepseekMsg = "Paste the code from the server's terminal output first.";
        S.deepseekMsgOk = false; render(); return;
      }
      S.deepseekBusy = "pair"; S.deepseekMsg = null; S.deepseekMsgOk = false; render();
      let out = null;
      try { out = await apiPost("/api/providers/deepseek/session", { code: code }); }
      catch (e){ out = { ok:false, message:"the server did not answer the sign-in code." }; }
      S.deepseekBusy = null;
      if (out && out.providers) PROVIDERS = out.providers;
      if (out && out.settings)  SETTINGS  = out.settings;
      if (out && out.ok && out.token){
        /* The code is spent either way; if storage refuses the token there is
           nothing to retry and saying so beats drawing a field that 403s. */
        S.deepseekMsgOk = deepseekSetSessionToken(out.token);
        S.deepseekMsg = S.deepseekMsgOk
          ? out.message
          : "The code was accepted but this browser will not keep the token " +
            "(private window?), so the key field cannot open. The code is used " +
            "up — restart the server for a new one.";
      } else {
        S.deepseekMsgOk = false;
        S.deepseekMsg = (out && out.message) || "That code was not accepted.";
      }
      if (field) field.value = "";
      render(); return;
    }

    if (!bridge && !deepseekSessionToken()) return;    /* no lane; nothing drawn */

    let key = null;
    if (verb === "save"){
      /* Read off the DOM at click time and never stored: not in S, not in
         localStorage, not in a closure that outlives this handler. */
      const input = scBody.querySelector("[data-deepseek-key]");
      key = input ? input.value : "";
      if (!key || !key.trim()){
        S.deepseekMsg = "Enter a key first."; S.deepseekMsgOk = false; render(); return;
      }
    }
    if (verb === "remove" && !window.confirm(
        "Remove the saved DeepSeek key?\n\n" +
        "It is deleted from your login keychain and Sutra keeps no copy, so " +
        "you will need the key itself to sign in again. DeepSeek stops being " +
        "selectable until you do.")) return;

    /* Was DeepSeek the one answering? Read BEFORE the write, because the
       response replaces SETTINGS with the state that has already fallen back. */
    const wasActive = (SETTINGS || {}).provider === "deepseek";

    S.deepseekBusy = verb; S.deepseekMsg = null; S.deepseekMsgOk = false; render();

    let r = null;
    try {
      if (bridge){
        r = verb === "save" ? await bridge.deepseekKeySave(key)
                            : await bridge.deepseekKeyRemove();
      } else {
        /* The session lane. Header name matches deepseek_session.HEADER. */
        const hdr = { "X-Sutra-Session-Token": deepseekSessionToken() };
        r = verb === "save"
          ? await apiPost("/api/providers/deepseek/key", { key: key }, hdr)
          : await apiPost("/api/providers/deepseek/key/remove", {}, hdr);
      }
    } catch (e){
      /* A 403 is the ONE case worth reading, and only because the token can
         die under this page: the server restarted and minted a fresh code. Drop
         the dead token so the render falls back to the code field instead of
         re-offering a key field that cannot work. e.message is otherwise never
         quoted -- from the IPC layer or from fetch, nothing derived from a call
         that carried a key gets rendered (same reasoning as main.js). */
      if (e && e.status === 403){
        deepseekClearSessionToken();
        r = { ok:false, message:"this browser's sign-in has expired — the server "
              + "was restarted. Paste its new code below." };
      } else {
        r = { ok:false, message: bridge
              ? "the desktop bridge did not answer. Nothing was saved."
              : "the server did not answer. Nothing was saved." };
      }
    }
    key = null;
    S.deepseekBusy = null;

    /* Whatever happened, take the state the server reported -- a REFUSED save
       still answers with the truth about the machine, and rendering the old
       state after a refusal is how a row starts disagreeing with the keychain. */
    if (r && r.providers) PROVIDERS = r.providers;
    if (r && r.settings)  SETTINGS  = r.settings;
    S.deepseekMsgOk = !!(r && r.ok);
    S.deepseekMsg = (r && r.message) || (r && r.ok ? "Done." : "That did not work.");

    if (r && r.ok && verb === "save"){
      /* Clear the field on success only. A refused key stays in the box so the
         operator can fix a paste instead of finding it again. */
      const input = scBody.querySelector("[data-deepseek-key]");
      if (input) input.value = "";
    }

    /* SIGN-OUT OF THE ACTIVE PROVIDER. The server has already re-resolved the
       active provider (load_settings -> active_provider_detail drops a stored
       choice that stopped being runnable and reports it in provider_ignored,
       which this screen already renders). What it cannot do is close the
       sockets: a socket is bound to its provider at spawn, so a message sent
       down an existing one would still reach DeepSeek while the UI said
       otherwise. Same move the provider selector makes, and the same carve-out
       -- a pane mid-reply is left to finish rather than have its answer
       discarded. */
    if (r && r.ok && verb === "remove" && wasActive){
      [...CLAUDE_SOCKETS.keys()].forEach(k=>{
        const sid = k.replace(/::side$/, "");
        if (streamingFor(sid) || sideStreamingFor(sid)) return;
        const ch = CLAUDE_SOCKETS.get(k);
        try { ch.ws.close(); } catch (e) {}
        CLAUDE_SOCKETS.delete(k);
      });
      /* Usage renders as a section of this screen and keeps the two providers'
         figures in different state, so after falling back it is showing the
         wrong provider's numbers until something asks for the new one. */
      if (typeof loadUsage === "function") loadUsage(true);
    }
    render();
  });

  scBody.querySelectorAll("[data-pmode-set]").forEach(b=>b.onclick=()=>{
    const m = b.dataset.pmodeSet;
    const spec = PERM_MODES.find(x=>x.id===m) || {};
    /* A gated mode is refused server-side with a 400. Firing the request anyway
       turned "this is locked" into "settings are broken"; say which it is
       without a round-trip. */
    if (spec.settable === false){
      const envName = (SETTINGS||{}).unsafe_modes_env || "SUTRA_UI_ALLOW_UNSAFE_PERM_MODES";
      S.setOk = null;
      S.setError = m + " auto-approves agent actions and is gated. Restart the server with "
                 + envName + "=1 to make it selectable — the gate is out of band on purpose.";
      render(); return;
    }
    /* Unlocked but still dangerous: the second gate is the operator saying yes. */
    if (spec.writes_files && !window.confirm(
        "Switch to " + m + "?\n\n" + (spec.note || "") +
        "\n\nSessions started from this panel will act under that authority until you change it back.")){
      return;
    }
    S.setBusy = "mode:" + m; S.setError = null; S.setOk = null; render();
    apiPost("/api/settings", { permission_mode: m })
      .then(r=>{ SETTINGS = r.settings || SETTINGS;
                 /* Report what will RUN, not what was written — they differ when clamped. */
                 S.setOk = "permission mode is now "
                         + ((SETTINGS||{}).permission_mode_effective || (SETTINGS||{}).permission_mode) + "."; })
      .catch(e=>{ S.setError = e.message; })
      .then(()=>{ S.setBusy = null; render(); }); });

  /* ── editor ── */
  scBody.querySelectorAll("[data-edopen]").forEach(b=>b.onclick=()=>openEdFile(b.dataset.edopen));
  const edFilter = scBody.querySelector("[data-edfilter]");
  if (edFilter) edFilter.oninput = ()=>{ S.fsQuery = edFilter.value; renderFilterOnly(); };
  /* git filter (visual audit r5): full render is fine — the input rides the
     focused-input preserve whitelist, so the caret survives. */
  const gitFilter = scBody.querySelector("[data-gitfilter]");
  if (gitFilter) gitFilter.oninput = ()=>{ S.gitQ = gitFilter.value; render(); };
  const edTa = scBody.querySelector("[data-edta]");
  if (edTa){
    /* No render() on input: a full rebuild on every keystroke would fight the caret
       and make typing in a large file unusable. The dirty pill is updated directly. */
    edTa.oninput = ()=>{
      S.edText = edTa.value;
      const pill = scBody.querySelector("[data-edsave]");
      const dirty = S.edText !== S.edBase;
      if (pill) pill.disabled = !dirty || !(S.fs&&S.fs.editable) || S.edBusy;
      const chip = scBody.querySelector(".edbar .pill");
      if (chip){ chip.textContent = dirty ? "unsaved changes" : "saved";
                 chip.className = "pill " + (dirty ? "p-warn" : "p-mut"); }
    };
    edTa.onkeydown = e=>{
      if ((e.metaKey || e.ctrlKey) && e.key === "s"){ e.preventDefault(); saveEdFile(); }
    };
  }
  const edSave = scBody.querySelector("[data-edsave]");
  if (edSave) edSave.onclick = ()=>saveEdFile();
  const edReload = scBody.querySelector("[data-edreload]");
  if (edReload) edReload.onclick = ()=>{ const p=S.edFile; S.edBase=S.edText; openEdFile(p); };

  /* ── files (SilverBullet sidecar) ── */
  /* Workspace (flag-gated): its own wiring lives in 13-workspace.js; the
     guard keeps wire() intact if that file ever fails to load. */
  if (typeof wireWorkspace === "function") wireWorkspace(scBody);
  /* sidecar iframe wiring removed — PLAN-25-EDITOR S15: Files folded into
     the Workspace and editing is native; no [data-sbframe] exists to mount. */
  /* (r5) the Knowledge->Files [data-openfiles] bridge is gone with both
     screens; the Workspace opens docs directly. */

  /* ── git ── */
  scBody.querySelectorAll("[data-gitfile]").forEach(b=>b.onclick=()=>{
    const p = b.dataset.gitfile;
    /* Clicking the selected file again closes the diff rather than re-fetching it. */
    if (S.gitFile === p){ S.gitFile = null; S.gitDiff = null; render(); return; }
    loadGitDiff(p);
  });

  /* ── workdir ── */
  const wdIn = scBody.querySelector("[data-workdir-input]");
  if (wdIn){
    wdIn.oninput = ()=>{ S.workdirDraft = wdIn.value; };   /* no render: it would fight the caret */
    wdIn.onkeydown = e=>{ if (e.key === "Enter"){ e.preventDefault();
      const b = scBody.querySelector("[data-workdir-save]"); if (b) b.click(); } };
  }
  const wdSave = scBody.querySelector("[data-workdir-save]");
  if (wdSave) wdSave.onclick = ()=>{
    const el = scBody.querySelector("[data-workdir-input]");
    const want = (el ? el.value : "").trim();
    if (!want){ S.setError = "a working directory is required"; S.setOk = null; render(); return; }
    S.setBusy = "workdir"; S.setError = null; S.setOk = null; render();
    apiPost("/api/settings", { workdir: want })
      .then(r=>{ SETTINGS = r.settings || SETTINGS;
                 /* Report what the SERVER stored (it expands ~ and resolves symlinks), not what
                    was typed -- they differ, and echoing the input would misreport the result. */
                 S.workdirDraft = null;
                 S.setOk = "sessions will now start in " + ((SETTINGS||{}).workdir || want) + "."; })
      .catch(e=>{ S.setError = e.message; })
      .then(()=>{ S.setBusy = null; render(); }); };

  const ea=scBody.querySelector("[data-expall]");
  if(ea) ea.onclick=()=>{ S.collapsed.clear(); render(); };
  const ca=scBody.querySelector("[data-collall]");
  if(ca) ca.onclick=()=>{ live().forEach(d=>{ if(d.parent_ref) S.collapsed.add(d.ref); }); render(); };

  /* No per-pane provider handlers: the row in the composer is a read-only
     indicator (founder direction 2026-09-03). Selection lives in Settings, and
     the socket-drop that used to happen here now happens there. */

  /* working directory, per session */
  panes.querySelectorAll("[data-cwdopen]").forEach(b=>b.onclick=()=>{
    const sid = b.dataset.cwdopen;
    S.cwdEdit = S.cwdEdit === sid ? null : sid;
    S.cwdError = null;
    render();
    /* Focus and put the caret at the END: the field is pre-filled with the current
       path, and selecting it all would make the first keystroke wipe a value the
       operator most likely wants to edit rather than replace. */
    const inp = panes.querySelector('[data-cwdinput="' + sid + '"]');
    if (inp){ inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); }
  });
  panes.querySelectorAll("[data-cwdsave]").forEach(b=>b.onclick=()=>{
    const sid = b.dataset.cwdsave;
    const inp = panes.querySelector('[data-cwdinput="' + sid + '"]');
    setSessCwd(sid, inp ? inp.value : "");
  });
  panes.querySelectorAll("[data-cwdcancel]").forEach(b=>b.onclick=()=>{
    S.cwdEdit = null; S.cwdError = null; render(); });
  /* usage chip + popover */
  panes.querySelectorAll("[data-usagepop]").forEach(b=>{
    const sid = b.closest("[data-sess]") && b.closest("[data-sess]").dataset.sess;
    b.onclick = ()=>{
      const opening = S.usagePop !== sid;
      S.usagePop = opening ? sid : null;
      render();
      /* Refresh ON OPEN rather than on a timer. The number only matters when
         someone is looking at it, and a background poll against an external API
         for a panel nobody has open is cost with no reader. The server's 60s
         cache makes reopening free. */
      if (opening) loadUsage(true);
    };
  });
  panes.querySelectorAll("[data-usageclose]").forEach(b=>b.onclick=()=>{
    S.usagePop = null; render(); });
  /* repository bar */
  panes.querySelectorAll("[data-prstoggle]").forEach(b=>b.onclick=()=>{
    const sid = b.dataset.prstoggle;
    const opening = S.prsOpen !== sid;
    S.prsOpen = opening ? sid : null;
    render();
    if (opening) loadPrs(sid, true);
  });
  panes.querySelectorAll("[data-propose-pr]").forEach(b=>b.onclick=()=>{
    const sid = b.dataset.proposePr;
    const r = S.repo[sid] || {};
    /* Pre-filled from what the repository already says, not blank: the head is
       the branch you are on and the base is what it tracks, which is right
       almost always -- and both stay editable because "almost" is not "always". */
    S.prForm = { sid,
      head: r.branch || "",
      base: (r.upstream || "").replace(/^origin\//, "") || "main",
      title: "", body: "" };
    S.prError = null; S.prDone = null;
    render();
    const t = panes.querySelector("[data-prf='title']"); if (t) t.focus();
  });
  panes.querySelectorAll("[data-prf]").forEach(inp=>{
    inp.oninput = ()=>{ if (S.prForm) S.prForm[inp.dataset.prf] = inp.value; };
  });
  panes.querySelectorAll("[data-prcancel]").forEach(b=>b.onclick=()=>{
    S.prForm = null; S.prError = null; render(); });
  panes.querySelectorAll("[data-prsubmit]").forEach(b=>b.onclick=async ()=>{
    if (!S.prForm || S.prBusy) return;
    S.prBusy = true; S.prError = null; render();
    try {
      const r = await apiPost("/api/repo/pr-proposal", {
        cwd: sessCwd(S.prForm.sid), head: S.prForm.head, base: S.prForm.base,
        title: S.prForm.title, body: S.prForm.body });
      /* The proposal is INERT. Say so plainly rather than letting a green tick
         imply the pull request exists -- it does not, and will not until it is
         approved under Routines. */
      S.prDone = (r.proposal && r.proposal.id) || "written";
      S.prForm = null;
      loadProposals(true);
    } catch (e){ S.prError = e.message; }
    S.prBusy = false; render();
  });
  panes.querySelectorAll("[data-prdone-dismiss]").forEach(b=>b.onclick=()=>{
    S.prDone = null; render(); });
  panes.querySelectorAll("[data-cwdinput]").forEach(inp=>{
    inp.onkeydown = e=>{
      if (e.key === "Enter"){ e.preventDefault(); setSessCwd(inp.dataset.cwdinput, inp.value); }
      else if (e.key === "Escape"){ e.preventDefault(); S.cwdEdit = null; S.cwdError = null; render(); }
    };
  });
  /* session panes */
  panes.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>{
    S.sessTab[b.dataset.sid]=b.dataset.tab; render(); });
  panes.querySelectorAll("[data-agentsfold]").forEach(b=>b.onclick=()=>{
    const sid = b.dataset.agentsfold;
    if (S.agentsFold[sid]) delete S.agentsFold[sid];
    else { S.agentsFold[sid] = true; loadAgents(sid, false); }
    render(); });
  panes.querySelectorAll("[data-agentopen]").forEach(b=>b.onclick=()=>{
    /* sid is a claude session id (uuid) and aid is agent-<hex>; neither contains a
       colon, so a single split is unambiguous. */
    const i = b.dataset.agentopen.indexOf(":");
    const sid = b.dataset.agentopen.slice(0, i), aid = b.dataset.agentopen.slice(i + 1);
    if (S.agentOpen[sid] === aid){ delete S.agentOpen[sid]; render(); return; }
    S.agentOpen[sid] = aid; loadAgentTranscript(sid, aid); render(); });
  /* Retry an interrupted turn: same text, same session, new socket. The turn is
     reset rather than duplicated, so the transcript does not grow a copy of a
     message that was never answered. */
  panes.querySelectorAll("[data-retry]").forEach(b=>b.onclick=()=>{
    const uid = b.dataset.retry;
    let sess=null, turn=null;
    S.sessions.forEach(s=>(s.turns||[]).forEach(t=>{ if (t.uid===uid){ sess=s; turn=t; } }));
    Object.keys(S.sideTurns||{}).forEach(sid=>(S.sideTurns[sid]||[]).forEach(t=>{
      if (t.uid===uid){ sess=S.sessions.find(x=>x.id===sid); turn=t; } }));
    if (!sess || !turn) return;
    turn.error = null; turn.interrupted = false; turn.response = "";
    turn.tools = []; turn.toolRuns = [];
    askClaude(sess, turn, !!turn.side);
    render();
  });

  panes.querySelectorAll("[data-close]").forEach(b=>b.onclick=()=>closePane(b.dataset.close));
  /* ⋯ pane menu (chat-surface chrome): the chip toggles, every row dispatches
     through paneMenuAction() to the SAME state the old header control mutated */
  panes.querySelectorAll("[data-panemenu]").forEach(b=>b.onclick=()=>{
    const sid = b.dataset.panemenu;
    const opening = S.paneMenu !== sid;
    S.paneMenu = opening ? sid : null;
    render();
    /* the render replaced the chip, so focus fell to <body>; a keyboard user
       who just opened the menu must land ON it (refuter 2026-08-23). Escape
       returns them to the chip (08-boot). */
    if (opening){
      const first = document.querySelector('#panemenu-' + sid + ' .mrow, #panemenu-' + sid + ' button, #panemenu-' + sid + ' select');
      if (first && first.focus) first.focus();
    } else {
      const chip = document.querySelector('[data-panemenu="' + sid + '"]');
      if (chip && chip.focus) chip.focus();
    } });
  panes.querySelectorAll("[data-mrow]").forEach(b=>b.onclick=()=>{
    const pane = b.closest("[data-sess]");
    if (pane) paneMenuAction(pane.dataset.sess, b.dataset.mrow); });
  /* the composer is NOT disabled while a turn runs: the reply streams in, and disabling
     the input mid-stream blurred it and dropped whatever was being typed next */
  panes.querySelectorAll("[data-ssend]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.ssend;
    const inp=panes.querySelector('[data-sask="'+sid+'"]');
    const text=(inp && inp.value.trim())||"";
    const composed=composeWithAttachments(sid, text);
    if(!composed) return;                       /* nothing typed AND nothing attached */
    if(inp) inp.value=""; S.composerText[sid]=""; S.palette=null;
    submitTurn(composed, sid); });

  /* ── side chat ── */
  panes.querySelectorAll("[data-optstoggle]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.optstoggle; S.optsOpen[sid]=!S.optsOpen[sid]; render(); });
  panes.querySelectorAll("[data-opt]").forEach(el=>{
    const sid=el.dataset.sid, key=el.dataset.opt;
    const commit=()=>{
      const o = (S.turnOpts[sid] = S.turnOpts[sid] || {});
      const raw = el.value;
      if (key === "allowed_tools" || key === "disallowed_tools"){
        const list = raw.split(/\s+/).filter(Boolean);
        if (list.length) o[key] = list; else delete o[key];
      } else if (key === "max_budget_usd"){
        const n = parseFloat(raw);
        if (isFinite(n) && n > 0) o[key] = n; else delete o[key];
      } else if (raw && raw.trim()){
        o[key] = raw.trim();
      } else { delete o[key]; }
      /* No render(): re-rendering on every keystroke would tear down the field
         being typed into. The value is already in S. */
    };
    el.oninput = commit; el.onchange = commit;
  });
  panes.querySelectorAll("[data-sidetoggle]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.sidetoggle;
    S.sideOpen[sid] = !S.sideOpen[sid];
    render();
  });
  panes.querySelectorAll("[data-sideclose]").forEach(b=>b.onclick=()=>{
    /* Closing HIDES it; the turns stay in S.sideTurns so reopening does not lose the
       branch. Discarding an operator's conversation on a close click would be a
       destructive default. */
    S.sideOpen[b.dataset.sideclose] = false; render();
  });
  panes.querySelectorAll("[data-sideask]").forEach(inp=>{
    const sid = inp.dataset.sideask;
    inp.oninput = ()=>{ S.sideText[sid] = inp.value; };
    inp.onkeydown = e=>{
      if (e.key === "Enter" && inp.value.trim()){
        e.preventDefault(); const t = inp.value.trim(); inp.value = ""; askSide(sid, t); }
    };
  });
  panes.querySelectorAll("[data-sidesend]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.sidesend;
    const inp=panes.querySelector('[data-sideask="'+sid+'"]');
    if (inp && inp.value.trim()){ const t=inp.value.trim(); inp.value=""; askSide(sid, t); }
  });

  /* ── stop ── */
  panes.querySelectorAll("[data-sstop]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.sstop;
    const ch=CLAUDE_SOCKETS.get(sid);
    if(!ch || !ch.open){
      /* No live socket = nothing to interrupt. Say so rather than leaving a button
         that silently does nothing. */
      const s=S.sessions.find(x=>x.id===sid);
      const t=s && (s.turns||[]).slice().reverse().find(x=>x.streaming);
      if(t){ t.streaming=false; t.stopped=true; render(); }
      return;
    }
    ch.ws.send(JSON.stringify({type:"stop"}));
  });

  /* The side chat had NO stop anywhere: the main composer's Stop resolves
     CLAUDE_SOCKETS.get(sid) -- the MAIN key -- while a side turn lives under
     chanKey(sid,true). Kept as a SEPARATE control so stopping one never kills the
     other. */
  panes.querySelectorAll("[data-sidestop]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.sidestop;
    const ch=CLAUDE_SOCKETS.get(chanKey(sid, true));
    if(!ch || !ch.open){
      const t=(S.sideTurns[sid]||[]).slice().reverse().find(x=>x.streaming);
      if(t){ t.streaming=false; t.stopped=true; render(); }
      return;
    }
    ch.ws.send(JSON.stringify({type:"stop"}));
  });

  /* ── routines ── */
  scBody.querySelectorAll("[data-prok]").forEach(b=>b.onclick=()=>
    decideProposal(b.dataset.prok, true));
  scBody.querySelectorAll("[data-prno]").forEach(b=>b.onclick=()=>
    decideProposal(b.dataset.prno, false));

  scBody.querySelectorAll("[data-rtnew]").forEach(b=>b.onclick=()=>{
    S.rtForm = {preset:"daily", hour:9, minute:0, weekday:1, model:"",
                permission_mode:(S.rt&&S.rt.permission_modes||["dontAsk"])[0],
                max_budget_usd:1, cwd:((SETTINGS||{}).workdir)||""};
    S.rtError = null; render();
  });
  scBody.querySelectorAll("[data-rtcancel]").forEach(b=>b.onclick=()=>{
    S.rtForm = null; S.rtError = null; render(); });
  scBody.querySelectorAll("[data-rtreload]").forEach(b=>b.onclick=()=>loadRoutines(true));
  scBody.querySelectorAll("[data-rtfix]").forEach(b=>b.onclick=()=>
    rtAction("/reconcile", {fix:true}, "Removed the leftover jobs."));

  /* Field edits are held in S.rtForm, not read off the DOM at submit: render()
     rebuilds the screen whenever the preset changes, and anything only in the
     DOM would be lost at that moment. */
  scBody.querySelectorAll("[data-rtf]").forEach(el=>{
    const k = el.dataset.rtf;
    const commit = ()=>{ if (!S.rtForm) return; S.rtForm[k] = el.value; };
    el.oninput = commit;
    /* A select changes the SHAPE of the form (a weekly needs a day picker), so it
       must re-render; a text input must not, or the caret jumps on every key. */
    if (el.tagName === "SELECT") el.onchange = ()=>{ commit(); render(); };
  });

  scBody.querySelectorAll("[data-rtsave]").forEach(b=>b.onclick=async ()=>{
    const f = S.rtForm || {};
    const body = {
      id:(f.id||"").trim().toLowerCase(), description:f.description, prompt:f.prompt,
      cwd:f.cwd, model:f.model||"", permission_mode:f.permission_mode,
      opts:{ max_budget_usd:Number(f.max_budget_usd)||0 },
      schedule:{ preset:f.preset, hour:Number(f.hour)||0, minute:Number(f.minute)||0,
                 weekday:Number(f.weekday)||0, cron:f.cron },
      enabled:true };
    S.rtBusy = "create"; S.rtError = null; S.rtMsg = null; render();
    try {
      const r = await apiPost("/api/routines", body);
      S.rtForm = null;
      S.rtMsg = (r.launchd && r.launchd.ok)
        ? "Created and scheduled. It has never run — use Run now to check it works."
        : "Created, but launchd refused to load it: " + ((r.launchd||{}).stderr||"no reason given");
      await loadRoutines(true);
    } catch (e) { S.rtError = e.message; }
    S.rtBusy = null; render();
  });

  scBody.querySelectorAll("[data-rtrun]").forEach(b=>b.onclick=()=>
    rtAction("/" + b.dataset.rtrun + "/run", {confirm:true}));
  scBody.querySelectorAll("[data-rttoggle]").forEach(b=>b.onclick=()=>
    rtAction("/" + b.dataset.rttoggle, {enabled: b.dataset.en === "1"},
             b.dataset.en === "1" ? "Resumed." : "Paused — it will not fire on its own."));
  scBody.querySelectorAll("[data-rtruns]").forEach(b=>b.onclick=()=>
    rtLoadRuns(b.dataset.rtruns));
  /* Open a run as a thread. Keyboard too: the row is the control, and a table
     row that only answers to a mouse is a control half the users cannot reach. */
  const openRun = el => {
    const rid = el.dataset.runopen, name = el.dataset.runname;
    if (!rid || !name) return;
    if (S.runOpen && S.runOpen.rid===rid && S.runOpen.name===name){
      S.runOpen = null; S.runDetail = null; render(); return;   /* toggle shut */
    }
    const idx = (S.rtRuns[rid] || {}).runs || [];
    const rec = idx.find(x=>x.output_file===name) || {};
    S.runOpen = {rid, name, started: rec.started_at || ""};
    S.runDetail = null;
    /* Marked read on OPEN, not on close: you have seen it the moment it is on
       screen, and a mark that waits for a close never lands when the reader
       simply navigates away. */
    markRunSeen(rid, name);
    render();
    loadRunDetail(rid, name);
  };
  scBody.querySelectorAll("[data-runopen]").forEach(el=>{
    el.onclick = ()=>openRun(el);
    el.onkeydown = e=>{ if (e.key==="Enter" || e.key===" "){ e.preventDefault(); openRun(el); } };
  });
  scBody.querySelectorAll("[data-runclose]").forEach(b=>b.onclick=()=>{
    S.runOpen = null; S.runDetail = null; render(); });
  scBody.querySelectorAll("[data-runcontinue]").forEach(b=>b.onclick=()=>{
    const d = S.runDetail;
    if (!d || !d.session_id) return;
    continueRunThread(b.dataset.runcontinue, d);
  });
  scBody.querySelectorAll("[data-rtdel]").forEach(b=>b.onclick=()=>{
    /* Deleting unloads a real launchd job. Confirm, and say what survives. */
    if (!confirm("Delete routine \"" + b.dataset.rtdel + "\"?\n\nThe scheduled job is " +
                 "removed. Its run history is kept on disk.")) return;
    rtAction("/" + b.dataset.rtdel + "/delete", {confirm:true}, "Deleted.");
  });

  /* ── permission mode (chat level) ── */
  panes.querySelectorAll("[data-perm]").forEach(sel=>sel.onchange=()=>{
    const want = sel.value;
    /* Re-render first so the select snaps back to the EFFECTIVE mode if the
       confirmation is cancelled -- leaving it showing a mode that is not
       running would be the same lie the clamp exists to prevent. */
    setPermMode(want);
  });
  panes.querySelectorAll("[data-permok]").forEach(b=>b.onclick=()=>{
    if (S.permConfirm) applyPermMode(S.permConfirm.mode, true);
  });
  panes.querySelectorAll("[data-permno]").forEach(b=>b.onclick=()=>{
    S.permConfirm = null; S.permError = null; render();
  });

  /* ── model ── */
  panes.querySelectorAll("[data-model]").forEach(sel=>sel.onchange=()=>{
    /* Per-session only. Persisting it here would silently change the default for
       every other session too; Settings is where the default lives. */
    S.model[sel.dataset.model] = sel.value;
  });

  /* ── attachments ── */
  panes.querySelectorAll("[data-attach]").forEach(b=>b.onclick=()=>pickAttachment(b.dataset.attach));
  panes.querySelectorAll("[data-attrm]").forEach(b=>b.onclick=()=>{
    const [sid, i] = b.dataset.attrm.split(":");
    (S.attach[sid]||[]).splice(+i, 1);
    render();
  });
  panes.querySelectorAll("[data-sask]").forEach(inp=>{
    const sid = inp.dataset.sask;
    /* "/" opens the palette; it only ever lists commands that actually
       resolve, because the source is GET /api/skills reading ~/.claude. */
    autoGrowComposer(inp);
    inp.oninput = ()=>{
      S.composerText[sid] = inp.value;
      autoGrowComposer(inp);
      const p = paletteFor(inp.value);
      const was = S.palette && S.palette.sid===sid;
      if (p && p.items.length){ S.palette = { sid, items:p.items, idx:0, token:p.token,
                                              kind:p.kind }; render(); }
      else if (was){ S.palette = null; render(); }
    };
    inp.onkeydown = e=>{
      const pal = S.palette && S.palette.sid===sid ? S.palette : null;
      if (pal){
        if (e.key==="ArrowDown"){ e.preventDefault(); pal.idx=(pal.idx+1)%pal.items.length; render(); return; }
        if (e.key==="ArrowUp"){ e.preventDefault(); pal.idx=(pal.idx-1+pal.items.length)%pal.items.length; render(); return; }
        if (e.key==="Enter" || e.key==="Tab"){ e.preventDefault(); applyPalette(sid, pal.idx); return; }
        if (e.key==="Escape"){ e.preventDefault(); S.palette=null; render(); return; }
      }
      /* Shift+Enter is a NEWLINE, Enter sends. Ctrl/Cmd+J too, because that is
         what readline users reach for. Returning early leaves the default
         behaviour -- in a textarea that inserts the newline for us. */
      /* Cmd/Ctrl+Enter SENDS -- the convention in Claude Code, Slack, ChatGPT and
         GitHub. It used to insert a newline too, so an operator who reached for it
         watched the message sit in the box. Shift+Enter is a newline: return early
         and the textarea default inserts it. */
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        const composed = composeWithAttachments(sid, inp.value.trim());
        if(!composed) return;
        e.preventDefault();
        inp.value=""; S.composerText[sid]=""; S.palette=null;
        submitTurn(composed, sid);
        return;
      }
      if (e.key === "Enter" && e.shiftKey) return;
      if(e.key==="Enter"){
        /* Not gated on inp.value: an attachment with no typed text is a legitimate
           message ("here is the file"), and the old guard silently swallowed it. */
        const composed = composeWithAttachments(sid, inp.value.trim());
        if(!composed) return;
        e.preventDefault();
        inp.value=""; S.composerText[sid]=""; S.palette=null;
        submitTurn(composed, sid); }
    };
    /* Drop and paste land on the composer, which is where the operator aims. */
    inp.ondragover = e=>{ e.preventDefault(); inp.classList.add("dropping"); };
    inp.ondragleave = ()=>inp.classList.remove("dropping");
    inp.ondrop = e=>{
      const files = [...((e.dataTransfer && e.dataTransfer.files) || [])];
      if (!files.length) return;                 /* let a plain text drop behave normally */
      e.preventDefault(); inp.classList.remove("dropping");
      files.forEach(f=>uploadAttachment(sid, f));
    };
    inp.onpaste = e=>{
      const items = [...((e.clipboardData && e.clipboardData.files) || [])];
      if (!items.length) return;                 /* pasted TEXT must still paste as text */
      e.preventDefault();
      items.forEach(f=>uploadAttachment(sid, f));
    };
  });
  panes.querySelectorAll("[data-pal]").forEach(r=>r.onclick=()=>{
    if (S.palette) applyPalette(S.palette.sid, +r.dataset.pal); });
  panes.querySelectorAll('.pane:not(.browse) [data-ref]').forEach(n=>n.onclick=()=>{
    S.screen="departments"; S.sel=n.dataset.ref; render(); });

  scBody.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>{S.view=b.dataset.view;render();});
  /* Directory search. render() restores focus + caret for the focused input,
     so re-rendering per keystroke does not steal the cursor. */
  const dq = scBody.querySelector("#dirQ");
  if (dq) dq.oninput = ()=>{ S.dirQ = dq.value; render(); };
  scBody.querySelectorAll("[data-chst]").forEach(b=>
    b.onclick = ()=>{ S.dirSt = b.dataset.chst; render(); });
  scBody.querySelectorAll("[data-toggle]").forEach(b=>b.onclick=()=>{
    S[b.dataset.toggle]=!S[b.dataset.toggle];
    render(); });
  scBody.querySelectorAll("[data-ref]").forEach(n=>{
    /* the tile IS the control: selecting a department also opens or closes its subtree */
    n.onclick=()=>{ const r=n.dataset.ref;
      if (DOMAINS.some(k=>k.parent_ref===r))
        S.collapsed.has(r) ? S.collapsed.delete(r) : S.collapsed.add(r);
      S.sel=r; render(); };
    if (n.getAttribute("draggable")==="true"){
      n.ondragstart=e=>{ S.drag=n.dataset.ref; n.classList.add("drg");
        e.dataTransfer.effectAllowed="move"; e.dataTransfer.setData("text/plain",n.dataset.ref);
        paintRings(n.dataset.ref); };
      n.ondragend=()=>{ S.drag=null; clearRings(); flushRender(); };
    }
    n.ondragover=e=>{ if(!S.drag) return;
      const src=byRef(S.drag), tgt=byRef(n.dataset.ref);
      if (!src||!tgt) return;
      if (blockCodesForMove(src,tgt).length) return;      /* no preventDefault ⇒ drop never fires */
      e.preventDefault(); e.dataTransfer.dropEffect="move"; };
    n.ondrop=e=>{ e.preventDefault(); if(!S.drag){ flushRender(); return; }
      const src=byRef(S.drag), tgt=byRef(n.dataset.ref);
      if (!src||!tgt) return;
      if (src.parent_ref===tgt.ref){ clearRings(); S.drag=null; flushRender(); return; }  /* inert no-op */
      if (blockCodesForMove(src,tgt).length){ clearRings(); S.drag=null; flushRender(); return; }
      S.draft.ops.push({op:"move",ref:src.ref,target:tgt.ref}); saveDraft();
      S.drag=null; render(); };
  });
  /* (r5) the Knowledge #sq wiring is gone with the screen. */
  scBody.querySelectorAll("[data-goto-domain]").forEach(r=>r.onclick=()=>{
    S.screen="departments"; S.sel=r.dataset.gotoDomain; render(); });
  const q=scBody.querySelector("#q");
  if(q) q.oninput=()=>{S.q=q.value; const p=q.selectionStart; render();
    const n=scBody.querySelector("#q"); if(n){n.focus(); n.setSelectionRange(p,p);} };
  scBody.querySelectorAll("[data-facet]").forEach(b=>b.onclick=()=>{
    const g=S.cf[b.dataset.facet]; const v=b.dataset.val;
    g.has(v)?g.delete(v):g.add(v); render(); });
  scBody.querySelectorAll("[data-sort]").forEach(h=>h.onclick=()=>{
    const c=h.dataset.sort; S.sort = {col:c, dir: S.sort.col===c ? -S.sort.dir : 1}; render(); });
  scBody.querySelectorAll("[data-charter]").forEach(r=>r.onclick=()=>{S.selCharter=r.dataset.charter;render();});
  scBody.querySelectorAll("[data-pmode]").forEach(b=>b.onclick=()=>{S.pmode=b.dataset.pmode;render();});
  scBody.querySelectorAll("[data-revert]").forEach(b=>b.onclick=()=>{
    S.draft.ops.splice(+b.dataset.revert,1); saveDraft(); render(); });
  const rat=scBody.querySelector("#rat");
  /* debounced + chained: one POST per pause, and writes cannot overtake each
     other (an earlier keystroke's request landing last used to roll the stored
     rationale backwards) */
  if(rat) rat.oninput=()=>{S.draft.rationale=rat.value; saveDraftSoon();};
  /* The drift-simulation dev control was removed: it was a developer
   affordance on a product surface, and it was inverted -- it bumped a client-side
   counter the server never compared against, so it did nothing, while Rebase (which
   should CLEAR drift) was what actually triggered ORG-010. Real drift still surfaces:
   the server compares the draft's captured base against the registry on every
   simulate, so a concurrent mint raises ORG-010 without anyone faking it. */
  const rb=scBody.querySelector("#rebase");
  /* Rebase CLEARS drift: re-capture the registry's REAL fingerprint so the
     POSTed base matches the file again and ORG-010 stops firing. It used to
     write the locally-bumped count — i.e. rebasing CREATED the drift, and
     saveDraft() persisted it server-side across reloads. */
  if(rb) rb.onclick=()=>{ S.draft.base={...S.draft.base, domain_index_lines:META.domain_index_lines,
    captured_ms:Date.now()}; S.drift=false; invalidateSim(); saveDraft(); render(); };
  const dc=scBody.querySelector("#discard");
  if(dc) dc.onclick=()=>{ S.draft={ops:[],base:{...PLANS[0].base},rationale:"",
    plan_origin:"studio-drag",validated_at_ms:null}; S.drift=false;
    invalidateSim(); saveDraft(); render(); };
  const cc=scBody.querySelector("#copyCmd");
  if(cc) cc.onclick=()=>{ const s="placement_engine.py org plan --import ~/.sutra-ui/drafts/"+PLANS[0].plan_id+".json";
    try{ navigator.clipboard.writeText(s); cc.textContent="copied"; setTimeout(()=>cc.textContent="copy",1200);}catch(e){} };
}
function paintRings(srcRef){
  const src = byRef(srcRef); if(!src) return;
  const scBody = document.getElementById("scBody");
  let n=0;
  scBody.querySelectorAll("[data-ref]").forEach(node=>{
    const t = byRef(node.dataset.ref); if(!t) return;
    const codes = blockCodesForMove(src,t);
    if (codes.length){ node.classList.add("ring"); n++;
      node.title = codes.map(c=>c.code+" · "+c.subject).join("\n"); }
    else if (t.ref!==src.ref) node.classList.add("ok-t");
  });
  const s=document.getElementById("dragStatus");
  if(s) s.innerHTML = ` <b style="color:var(--block)">${n} blocked</b> for “${esc(src.name)}”.`;
}
function clearRings(){
  const scBody = document.getElementById("scBody");
  scBody.querySelectorAll("[data-ref]").forEach(n=>{
    n.classList.remove("ring","drg","ok-t"); n.removeAttribute("title"); });
  const s=document.getElementById("dragStatus"); if(s) s.textContent="";
}
/* v3.3 (PLAN-25 S8): the session list and plane rows moved out of .rail into
   #plane, so this delegation now hangs on #app — the shared ancestor of both.
   Every branch below targets a closest() selector, so widening the container
   changes which clicks ARRIVE here, not which ones ACT. */
document.getElementById("app").addEventListener("click", e=>{
  /* Feature A: the ⋮ trigger and its menu items. These run BEFORE the data-open
     branch below, each stopPropagation()+returns, so opening the menu never also
     opens the pane, and the document-level closer added later does not
     immediately re-close a just-opened menu. */
  const mt = e.target.closest("[data-sessmenu]");
  if (mt){ e.stopPropagation();
    S.sessMenu = S.sessMenu === mt.dataset.sessmenu ? null : mt.dataset.sessmenu;
    S.sessRename = null; renderRail(); return; }
  const tsb = e.target.closest("[data-tsact]");
  if (tsb && window.sutra && window.sutra.teamsutraAction){
    e.stopPropagation();
    window.sutra.teamsutraAction(tsb.dataset.tid, tsb.dataset.tsact)
      .then(()=>loadTeamsutra(true))
      .catch(err=>{ S.tsError = String(err && err.message || err); render(); });
    return;
  }
  const act = e.target.closest("[data-act]");
  if (act){ e.stopPropagation();
    sessAction(act.dataset.act, act.dataset.sid, act.dataset.group); return; }
  /* Collapse/expand ONE plane group. Checked BEFORE [data-screen] because the
     header sits in the same delegated listener; a row click must still open its
     screen, and the header must not. Persisted per "<dest>:<label>", default
     expanded, so the store only holds groups the operator explicitly closed. */
  const pc = e.target.closest("[data-planecollapse]");
  if (pc){
    const key = pc.dataset.planecollapse;
    S.ui.planeSections = S.ui.planeSections || {};
    if (S.ui.planeSections[key]) delete S.ui.planeSections[key];
    else S.ui.planeSections[key] = true;
    saveLayout();
    renderPlane();
    return;
  }
  const b = e.target.closest("[data-screen]");
  if (b && !b.disabled){
    /* "terminal" is a PANE TOGGLE living in the nav, not a screen. Routing it
       through S.screen would set S.screen to an id SCREENS has no entry for,
       and render() would blank the browse pane. */
    if (b.dataset.screen === "terminal"){ termToggle(); renderRail(); return; }
    openScreen(b.dataset.screen);
    render(); return;
  }
  const sg = e.target.closest("[data-sgroup]");
  if (sg){ S.sgroup = sg.dataset.sgroup; render(); return; }
  const op = e.target.closest("[data-open]");
  if (op){ const id=op.dataset.open;
    markRead(id); S.sessMenu = null; S.sessRename = null;
    pushPane(id);
    /* opening a REAL session is what triggers the transcript read -- the list
       endpoint only read each file's head, so until now the turns are unknown,
       not empty */
    ensureTranscript(S.sessions.find(s=>s.id===id));
    render(); return; }
  const g = e.target.closest("[data-goto]");
  if (g){ S.screen="departments"; S.sel=g.dataset.goto; render(); }
});
document.getElementById("app").addEventListener("keydown", e=>{
  const ri = e.target.closest("[data-renameinput]");
  if (ri && e.key === "Enter"){ e.preventDefault(); renameSession(ri.dataset.sid, ri.value); }
  if (ri && e.key === "Escape"){ S.sessRename = null; renderRail(); }
});
/* One global closer: any click not on a ⋮ trigger or inside an open menu dismisses
   it. The ⋮/menu-item branches stopPropagation(), so this never fires for the
   click that opened the menu. Guarded so it costs nothing when closed. */
document.addEventListener("click", e=>{
  if (!S.sessMenu) return;
  if (e.target.closest("[data-sessmenu]") || e.target.closest(".smenu")) return;
  S.sessMenu = null; S.sessRename = null; renderRail();
});
/* New session: opens an empty pane on the right, exactly like the reference */
/* One path for every "start a session", so the rail button and the per-project +
   cannot drift. `cwd` is optional: with one, the new session gets that directory
   as its working-directory override (the same per-session mechanism the composer's
   folder chip writes), which is the entire point of a + that lives on a project
   heading -- starting a session "in" a project means starting it in that folder. */
function newSession(cwd){
  const s = { id:"s-"+(++SID), title:"New session", created_ms:NOW, updated_ms:NOW,
              turns:[], local:true, loadState:"live" };
  /* BOTH fields, deliberately. S.cwd is the override map sessCwd()/claudeWsUrl()
     read (so the session really runs in that folder); s.cwd is what the rail's
     project grouping and projOf() read. Writing only the first meant the + on a
     project heading opened a session that ran in the right directory but was
     listed under "No folder" -- the one group with no + of its own, so the
     button looked like it had done nothing. */
  if (cwd){ S.cwd[s.id] = cwd; s.cwd = cwd; }
  S.sessions.unshift(s);
  pushPane(s.id);
  render();
  const inp = document.querySelector('[data-sask="'+s.id+'"]'); if (inp) inp.focus();
  return s;
}
/* With no argument the new session falls through to SETTINGS.workdir, which
   defaults to ~/sutra-ui-workspace -- a directory the operator never works in.
   Running `claude` in the repo they were discussing and hitting /resume then
   lists nothing, because claude only shows the project dir for the cwd you are
   standing in. Default to the folder in view instead. */
document.getElementById("newSession").onclick = () =>
  newSession(sessCwd(S.openPanes[S.openPanes.length - 1]) || "");
/* theme */
(function(){
  const r=document.documentElement, KEY="sutra.panel.theme";
  const rd=()=>{try{return localStorage.getItem(KEY)}catch(e){return null}};
  const wr=v=>{try{localStorage.setItem(KEY,v)}catch(e){}};
  const saved=rd(); if(saved==="light"||saved==="dark") r.setAttribute("data-theme",saved);
  /* Desktop shell: mirror into nativeTheme so the SB iframe's scheme follows
     the panel (absent in a plain browser — presence-gated like the updater). */
  const bridge=(t)=>{ try { if (window.sutra && window.sutra.setTheme) window.sutra.setTheme(t); } catch(_e){} };
  bridge(saved==="light"||saved==="dark" ? saved : "system");
  const eff=()=>r.getAttribute("data-theme")||
    (matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");
  const lab=()=>themeBtn.setAttribute("aria-label","Switch to "+(eff()==="light"?"dark":"light")+" theme");
  lab();
  themeBtn.onclick=()=>{ const n=eff()==="light"?"dark":"light";
    r.setAttribute("data-theme",n); wr(n); lab(); bridge(n); };
})();
/* ── v3.3 identity footer (PLAN-25 S12-S14) ─────────────────────────────────
   The bottom-left states the ROLE the operator is acting as and is the control
   that switches it. The menu has exactly two jobs: Act as, and Switch theme —
   deliberately no account chrome (founder direction 2026-08-24). The role is a
   session-scoping label persisted per panel; it does not (yet) re-scope any
   backend read — that wiring is a later, separate decision. */
(function(){
  const KEY = "sutra.panel.role";
  /* The holding's operating identities. Static by design: roles are a founder
     decision, not a discovery — extending this list is a one-line change. */
  const ROLES = [
    { name:"CEO of Asawa Inc.", who:"holding" },
    { name:"CEO of Sutra",      who:"subsidiary" }
  ];
  const rd = ()=>{ try{ return localStorage.getItem(KEY) }catch(e){ return null } };
  const wr = v =>{ try{ localStorage.setItem(KEY, v) }catch(e){} };
  const current = ()=> ROLES.some(x=>x.name===rd()) ? rd() : ROLES[0].name;

  const idEl = document.getElementById("identity");
  const btn  = document.getElementById("idBtn");
  const menu = document.getElementById("idMenu");
  const list = document.getElementById("roleList");
  if (!idEl || !btn || !menu || !list) return;

  function paintRole(){
    const roleEl = document.getElementById("idRole");
    if (roleEl) roleEl.textContent = current();
    list.innerHTML = ROLES.map(x=>`
      <li><button type="button" data-role="${x.name}" aria-current="${x.name===current()}">
        ${x.name}<span class="idwho">${x.who}</span></button></li>`).join("");
  }
  function setOpen(open){
    menu.hidden = !open;
    idEl.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", String(open));
  }
  btn.onclick = e => { e.stopPropagation(); setOpen(menu.hidden); };
  list.onclick = e => {
    const b = e.target.closest("[data-role]"); if (!b) return;
    wr(b.dataset.role); paintRole(); setOpen(false);
    /* v3.4: acting is FUNCTIONAL — the org surfaces re-scope to the subtree
       this role commands. Re-read (cheap, loopback) rather than stash-and-
       filter so a stale earlier read cannot leak across roles. */
    if (typeof loadOrg === "function")
      loadOrg().then(()=>render()).catch(err => console.warn("Act-as rescope failed:", err));
  };
  document.addEventListener("click", e => {
    if (!menu.hidden && !idEl.contains(e.target)) setOpen(false);
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && !menu.hidden) setOpen(false);
  });
  paintRole();
  /* The scope resolver (loadOrg) needs the acting role but must not reach into
     this closure; publish the read-only accessor. */
  globalThis.panelRole = current;
})();
/* ── opening a screen, from ANY entry point (2.118.1 hotfix) ────────────────
   The lazy loaders used to live only inside the click delegation, so entering
   a destination from the RAIL (goDest -> default screen) rendered Balance and
   Teamsutra without ever fetching — a blank screen that looked dead. This is
   the one open path now; the click handler and goDest both call it. The
   terminal pane-toggle deliberately stays OUT: it is not a screen. */
function openScreen(id){
  /* S92 cutover: the old ids keep working — deep links, destSel restores and
     muscle memory land on the Workspace, which is where those surfaces live
     now. Redirect BEFORE the SCREENS check so a folded id never dead-ends. */
  if ((id === "knowledge" || id === "files")
      && typeof wsFlagOn === "function" && wsFlagOn() && SCREENS.workspace)
    id = "workspace";
  if (!id || !SCREENS[id]) return;
  S.screen = id;
  /* Keep the rail honest (visual audit r4): the active highlight and the pane
     title both read S.ui.dest, but nothing moved it when a screen opened from
     outside its destination — Settings showed "Org" active, Teamsutra was
     titled "Help". The screen's OWNING destination follows the open. */
  const owner = DESTS.find(d =>
    (DEST_PLANES[d] || []).some(x => x.screen === id
        || (x.rows || []).some(r => r.screen === id))   /* grouped planes (settings) */
    || DEST_DEFAULT_SCREEN[d] === id);                   /* plane-less dests (team) */
  if (owner && S.ui.dest !== owner) S.ui.dest = owner;
  /* v3.3 (PLAN-25 S9): remember the pick per destination, so returning to a
     destination restores the screen the operator was on. */
  if (DESTS.includes(S.ui.dest)) S.ui.destSel[S.ui.dest] = S.screen;
  /* Opening a screen is the OPEN gesture, the way clicking a session row is:
     a closed browse pane reopens rather than swapping content nobody can see. */
  S.ui.browseClosed = false; saveLayout();
  if (id === "git") loadGit(false);      /* lazy: only when actually opened */
  if (id === "editor") loadFs(false);    /* walking a real project is not free */
  if (id === "automation") loadAuto(false);
  if (id === "balance") loadBalance(false); /* lazy, like Git */
  if (id === "optimus") loadOptimus(false); /* lazy: reads the daemon's files */
  /* Workspace (flag-gated): guard mirrors wire() -- a missing 13-workspace.js
     must not break every other screen's open path. */
  if (id === "workspace" && typeof loadWorkspace === "function") loadWorkspace(false);

  /* force=true: unlike a repo, utilization moves while you are not looking, and
     a stale percentage is the one number this screen must not show. The 60s
     server cache is what keeps re-opening cheap. */
  /* "settings" too: Usage renders as a section of the AI Provider screen,
     so opening that screen has to fetch it -- otherwise the section would
     sit on "Reading usage..." until something else happened to load it. */
  if (id === "usage" || id === "settings") loadUsage(true);
  /* Codex's sign-in state, for the same reason usage is fetched here: the row
     renders on this screen and nothing else would ever ask for it. Spawns
     `codex login status`, hence lazy -- see loadCodexAuth. */
  if (id === "settings") loadCodexAuth(true);
  if (id === "evals") loadEvals(false);     /* lazy, like Git */
  if (id === "routines"){ loadRoutines(false); loadProposals(false); }
  if (id === "teamsutra") loadTeamsutra(false);
  if (id === "connectors") loadConnectors(false);  /* lazy: opens the connector db */
  /* Cache-only. A plain read never spawns the Claude CLI -- the probe
     contacts every one of the operator's connectors and rewrites Claude's
     own cache, so it must be an explicit act, not a side effect of opening
     a screen. The tile renders "Not checked yet" until the button is used. */
  if (id === "connectors") loadMediated(false);
}
/* ── v3.3 accent colour (PLAN-25 S16-S19) ───────────────────────────────────
   ONE hex restyles the app: applyAccent sets --acc and --on-acc inline and
   stamps data-accent on <html>; --acc-bg derives per theme in panel.css. The
   a11y floor is enforced at BUILD time: a swatch whose best text colour cannot
   reach 4.5:1 on the accent is never offered (WCAG relative luminance). */
function _lum(hex){
  const m = /^#([0-9a-f]{6})$/i.exec(hex || ""); if (!m) return null;
  const c = [0,2,4].map(i => {
    const v = parseInt(m[1].slice(i, i+2), 16) / 255;
    return v <= .03928 ? v/12.92 : Math.pow((v+.055)/1.055, 2.4);
  });
  return .2126*c[0] + .7152*c[1] + .0722*c[2];
}
function _contrast(a, b){
  const la = _lum(a), lb = _lum(b);
  if (la === null || lb === null) return 0;
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + .05) / (lo + .05);
}
/* The text colour that lives ON the accent, or null when neither ink clears
   the floor — a null swatch is dropped, never rendered dimmer (S19). */
function onAccFor(hex){
  const dark = "#0C0B09", light = "#ffffff";
  const cd = _contrast(hex, dark), cl = _contrast(hex, light);
  const best = cd >= cl ? {c:dark, r:cd} : {c:light, r:cl};
  return best.r >= 4.5 ? best.c : null;
}
const ACCENT_KEY = "sutra.panel.accent";
const ACCENTS = ["#B8574B","#4A6B8B","#2D5A3E","#7C5CBF","#8a6d12","#3E7C8A"];
function applyAccent(hex){
  const r = document.documentElement;
  if (!hex){                      /* reset: the shipped token palette returns */
    r.style.removeProperty("--acc"); r.style.removeProperty("--on-acc");
    r.removeAttribute("data-accent");
    try{ localStorage.removeItem(ACCENT_KEY) }catch(e){}
    return true;
  }
  const on = onAccFor(hex);
  if (!on) return false;          /* below the floor: refuse, keep the current */
  r.style.setProperty("--acc", hex);
  r.style.setProperty("--on-acc", on);
  r.setAttribute("data-accent", hex);
  try{ localStorage.setItem(ACCENT_KEY, hex) }catch(e){}
  return true;
}
function buildAccentRow(){
  const row = document.getElementById("accentRow");
  if (!row) return;
  let cur = null; try{ cur = localStorage.getItem(ACCENT_KEY) }catch(e){}
  row.innerHTML =
    `<button type="button" class="sw swreset" data-accent="" aria-current="${!cur}"
       title="Default palette" aria-label="Default palette"></button>` +
    ACCENTS.filter(h => onAccFor(h)).map(h => `
      <button type="button" class="sw" data-accent="${h}" aria-current="${cur===h}"
        style="background:${h}" title="${h}" aria-label="Accent ${h}"></button>`).join("");
  row.onclick = e => {
    const b = e.target.closest("[data-accent]"); if (!b) return;
    if (applyAccent(b.dataset.accent || null)) buildAccentRow();
  };
}
(function(){
  /* boot apply (S17): a stored accent that no longer clears the floor (or was
     hand-edited into garbage) is dropped rather than half-applied. */
  let saved = null; try{ saved = localStorage.getItem(ACCENT_KEY) }catch(e){}
  if (saved && !applyAccent(saved)) { try{ localStorage.removeItem(ACCENT_KEY) }catch(e){} }
  buildAccentRow();
})();
/* Telemetry line (PLAN-25 S14): the same utilization number the Usage screen
   shows, or an honest em-dash before the first read. renderRail() refreshes it
   on every render, so it tracks loadUsage() without its own timer. */
function paintTelemetry(){
  const el = document.getElementById("idStat");
  if (!el) return;
  /* Provider-aware since 2026-09-03. This line read Claude's window
     percentage unconditionally, so with DeepSeek selected the footer asserted
     "26% of the usage window" for a plan the panel was not using -- while the
     Usage screen two panes away showed a USD balance. */
  const pu = providerUsage();
  el.textContent = pu ? pu.long : "—";
}
/* ══════════════════════ bootstrap ══════════════════════
   One registry, one org, so there is no scope to settle before reading it.
   boot() reads the registry, the runtime and the sessions together and lets
   each degrade on its own. */

const shq = p => "'" + String(p).replace(/'/g, "'\\''") + "'";
function sessAction(action, sid, group){
  const s = S.sessions.find(x=>x.id===sid); if(!s) return;
  switch(action){
    case "pin": togglePin(sid); S.sessMenu=null; break;
    case "unread": markUnread(sid); S.sessMenu=null; break;
    case "group": setGroup(sid, group||""); S.sessMenu=null; break;
    case "group-new": { const n=(prompt("Group name")||"").trim(); if(n) setGroup(sid,n); S.sessMenu=null; break; }
    case "rename": S.sessRename=sid; renderRail();
      { const i=document.querySelector('[data-renameinput][data-sid="'+sid+'"]'); if(i){ i.focus(); i.select(); } } return;
    case "rename-save": { const i=document.querySelector('[data-renameinput][data-sid="'+sid+'"]');
      renameSession(sid, i?i.value:""); return; }
    case "fork": forkSession(sid); return;
    case "archive": archiveSession(sid); return;
    case "delete": deleteSession(sid); return;
    case "open-terminal": { const cwd=sessCwd(sid); if(cwd) sendToTerminal("cd "+shq(cwd)+"\n"); S.sessMenu=null; break; }
    case "open-editor": S.sessMenu=null; S.screen="editor"; loadFs(true); render(); return;
    case "open-repo":
      pushPane(sid);
      loadRepo(sid,true); S.sessMenu=null; break;
    case "open-finder": revealSession(sid); return;
  }
  render();
}
async function renameSession(sid, title){
  title=(title||"").trim(); if(!title){ S.sessRename=null; renderRail(); return; }
  const s=S.sessions.find(x=>x.id===sid);
  if (s && !s.real){ s.title=title; S.sessRename=null; S.sessMenu=null; render(); return; }
  try{ await apiPost("/api/sessions/"+encodeURIComponent(sid)+"/rename", {title});
    if(s) s.title=title; S.sessRename=null; S.sessMenu=null;
    S.toast="renamed — the same record Claude writes, so it shows there too";
  }catch(e){ S.toast="rename failed: "+e.message; }
  render();
}
function forkSession(sid){
  const src=S.sessions.find(x=>x.id===sid); if(!src) return;
  const s=newSession(sessCwd(sid));
  s.title="Fork of "+(src.title||"session");
  s.fork=true; s.forkOf=sid;
  s.claude_session=src.claude_session||src.id;
  S.turnOpts[s.id]=Object.assign({}, S.turnOpts[s.id], {fork_session:true});
  S.sessMenu=null; render();
}
async function archiveSession(sid){
  if(!confirm("Archive this session? The transcript moves out of Claude's project folder to ~/.sutra-ui/archive — it stops listing here and in Claude, and is recoverable.")) return;
  try{ await apiPost("/api/sessions/"+encodeURIComponent(sid)+"/archive", {});
    S.sessions=S.sessions.filter(x=>x.id!==sid); S.openPanes=S.openPanes.filter(x=>x!==sid);
    S.sessMenu=null; S.toast="archived — recoverable in ~/.sutra-ui/archive";
  }catch(e){ S.toast="archive failed: "+e.message; }
  render();
}
async function deleteSession(sid){
  if(!confirm("Delete this session? History is NOT destroyed — the transcript moves to ~/.sutra-ui/trash and can be restored.")) return;
  try{ await apiPost("/api/sessions/"+encodeURIComponent(sid)+"/delete", {});
    S.sessions=S.sessions.filter(x=>x.id!==sid); S.openPanes=S.openPanes.filter(x=>x!==sid);
    S.sessMenu=null; S.toast="deleted — recoverable in ~/.sutra-ui/trash";
  }catch(e){ S.toast="delete failed: "+e.message; }
  render();
}
async function revealSession(sid){
  S.sessMenu=null;
  try{ await apiPost("/api/sessions/"+encodeURIComponent(sid)+"/reveal", {}); }
  catch(e){ S.toast="could not reveal: "+e.message; render(); }
}

function backendError(e){
  document.getElementById("panes").innerHTML =
    `<section class="pane browse"><div class="pb">
      <div class="zero"><h4>Could not reach the backend</h4>
      <p>${esc(e.message)}</p>
      <p style="color:var(--faint)">Is the server running? <code>uvicorn app:app</code> from
      <code>sutra-ui/</code>.</p></div></div></section>`;
  console.error(e);
}

/* v3.4 Act-as: resolve the acting role to a VIEW SCOPE over the one org tree.
   CEO of Asawa Inc. commands the whole tree; CEO of Sutra commands the Sutra
   subtree. Pure so the vm harness can test it without a DOM.

   Anchor order (codex+deepseek converged 2026-08-24: a display-name regex is
   the WEAKEST anchor): (1) the known dref of "Sutra OS" in the founder's
   registry -- a no-op on other installs; (2) structural: a depth-1 child of
   the root whose name says sutra. No match FAILS OPEN with scope.missing set,
   and loadOrg's caller paints a loud chip -- blanking the founder's whole org
   on a rename would read as data loss (deepseek argued fail-closed; overruled
   for exactly that reason, the misconfig stays visible either way). */
function scopeOrgForRole(role, domains, charters, placements){
  const whole = { domains, charters, placements, scope:{ role, ref:null, name:null, missing:false } };
  if (!role || !/sutra/i.test(role) || /asawa/i.test(role)) return whole;
  const root = domains.find(d => !d.parent_ref) || null;
  const anchor =
    domains.find(d => d.ref === "dref-a19b505fe0d92ce3") ||
    (root && domains.find(d => d.parent_ref === root.ref && /sutra/i.test(d.name || ""))) ||
    null;
  if (!anchor){
    whole.scope.missing = true;
    console.warn("Act-as: no Sutra scope anchor in this registry — showing the whole tree");
    return whole;
  }
  const keep = new Set([anchor.ref]);
  /* BFS over parent_ref; bounded passes so a damaged registry with a parent
     loop cannot hang the shell (same defence as 03-org's depth walk). */
  for (let pass = 0, grew = true; grew && pass < 100; pass++){
    grew = false;
    for (const d of domains){
      if (!keep.has(d.ref) && d.parent_ref && keep.has(d.parent_ref)){ keep.add(d.ref); grew = true; }
    }
  }
  return {
    domains: domains.filter(d => keep.has(d.ref)),
    charters: charters.filter(c => keep.has(c.domain_ref)),
    placements: placements.filter(p => keep.has(p.domain_ref)),
    scope: { role, ref: anchor.ref, name: anchor.name, missing: false },
  };
}

/* Registry reads. Separated from the runtime reads below because they answer
   different questions: what the org IS, versus what this machine can run. */
async function loadOrg(){
  const [tree, charters, placements, history] = await Promise.all([
    apiGet("/api/org/tree?include_retired=true"),
    apiGet("/api/org/charters"),
    apiGet("/api/org/placements"),
    apiGet("/api/org/history"),
  ]);
  ORG_ALL = { domains: tree, charters, placements };
  const scoped = scopeOrgForRole(
    (typeof panelRole === "function" ? panelRole() : ""), tree, charters, placements);
  DOMAINS = scoped.domains;
  CHARTERS = scoped.charters;
  PLACEMENTS = scoped.placements;
  S.orgScope = scoped.scope;
  INDEX = history.events || [];   /* History stays whole-tree by design */
  // history_complete_from_ms is DERIVED server-side (earliest event carrying a
  // before/after snapshot), not a stored engine field -- see /api/org/history.
  META.history_complete_from_ms = history.meta.history_complete_from_ms;
  META.history_derived = history.meta.derived;
  META.domain_index_lines = history.meta.domain_index_lines;
  META.legacy_events = history.meta.legacy_events;
  invalidateSim();
}

/* Machine state, not registry state: what can run, and how it is configured. */
async function loadRuntime(){
  /* allSettled, NOT all. These are three independent endpoints, and under
     Promise.all a 500 from /api/skills -- a catalog walk that touches every
     plugin directory on the machine -- discarded a perfectly good
     /api/settings response and left SETTINGS null for the life of the window.
     The Settings screen then rendered "GET /api/settings has not answered",
     which is not what happened and cannot be falsified from the screen.
     Each subsystem now fails on its own and says which one failed. */
  const [skillsR, provsR, settingsR] = await Promise.allSettled([
    apiGet("/api/skills"),
    apiGet("/api/providers"),
    apiGet("/api/settings"),
  ]);
  const reason = r => String((r.reason && r.reason.message) || r.reason);
  const failed = [];

  if (skillsR.status === "fulfilled"){
    const skills = skillsR.value;
    SKILLS = skills.items || [];
    SKILLS_META = { by_kind: skills.by_kind, by_source: skills.by_source,
                    by_provider: skills.by_provider, total: skills.total,
                    runnable: skills.runnable, providers: skills.providers || [] };
    S.cat.etag = skills.signature || null;
  } else {
    failed.push("GET /api/skills — " + reason(skillsR));
  }

  if (provsR.status === "fulfilled") PROVIDERS = provsR.value.providers || [];
  else failed.push("GET /api/providers — " + reason(provsR));

  if (settingsR.status === "fulfilled"){
    const settings = settingsR.value;
    SETTINGS = settings.settings || null;
    PERM_MODES = settings.permission_modes || [];
    MODELS_BY_PROVIDER = settings.models_by_provider || {};
    TURN_OPTIONS_BY_PROVIDER = settings.turn_options_by_provider || {};
    PERM_MODES_BY_PROVIDER = settings.permission_modes_by_provider || {};
    CLAUDE_ACCOUNT = settings.claude_account || null;
    paintAvatar();
  } else {
    failed.push("GET /api/settings — " + reason(settingsR));
  }

  /* Reported, not thrown: boot() already treats the runtime as degradable, and
     the screens read S.runtimeError to say what actually failed. */
  S.runtimeError = failed.length ? failed.join(" · ") : null;
  /* The freshness baseline is seeded from the SAME response that populated
     SKILLS (S.cat.etag, set above), so the first poll compares against what is
     actually on screen rather than re-fetching a catalog the panel already has. */
  S.cat.readAt = Date.now();
  S.cat.lastCheckAt = Date.now();
}

/* ── skills auto-refresh ─────────────────────────────────────────────────────
   The catalog was read ONCE, in boot(). Installing a plugin or writing a new
   command meant the palette kept offering yesterday's list until the app was
   restarted -- and, worse, could keep offering a command that no longer resolves.

   ETag, not a separate probe endpoint: /api/skills returns the signature of the
   payload it is actually returning, from the same scan. A /signature endpoint would
   scan twice and let the client store a fingerprint describing state it never
   received -- a missed update that never self-corrects, because every later probe
   matches the stored value.

   Only /api/skills is polled. Re-fetching /api/settings on a timer would clobber a
   permission-mode or workdir change the operator is in the middle of making. */
const CAT_TICK_MS      = 20000;   /* how often we CONSIDER refreshing */
const CAT_FOCUSED_MS   = 60000;   /* refresh at most this often while focused */
const CAT_VISIBLE_MS   = 300000;  /* ... and far less often when merely visible */
const CAT_BACKOFF      = [60000, 120000, 300000];

