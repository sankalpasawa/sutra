async function loadSkills(){
  const headers = S.cat.etag ? { "If-None-Match": S.cat.etag } : {};
  const res = await fetch(API + "/api/skills", { headers });
  if (res.status === 304) return false;              /* unchanged; nothing to apply */
  if (!res.ok) throw new Error("/api/skills -> " + res.status);
  const payload = await res.json();
  /* Belt and braces against any cache that strips/ignores the 304: a 200 whose
     signature equals the stored one is ALSO "unchanged", and applying it would
     re-render for nothing. */
  if (payload.signature && payload.signature === S.cat.etag) return false;
  const before = SKILLS.length;
  SKILLS = payload.items || [];
  SKILLS_META = { by_kind: payload.by_kind, by_source: payload.by_source,
                  by_provider: payload.by_provider, total: payload.total,
                  runnable: payload.runnable, providers: payload.providers || [] };
  /* Commit the signature only AFTER the data it describes has been applied. The
     other order stores a fingerprint for a payload that was never installed. */
  S.cat.etag = payload.signature || null;
  S.cat.delta = SKILLS.length - before;
  S.cat.readAt = Date.now();
  return true;
}

/* Guarded at the CALLSITE, never inside render(). An early-return in render() --
   symmetric with the S.drag guard -- would freeze the "/" palette outright: arrow
   keys, escape and re-filtering all navigate BY calling render(). */
function refreshCatalog(){
  if (S.cat.inflight) return;
  S.cat.inflight = true;
  loadSkills()
    .then(changed=>{
      S.cat.fails = 0;
      /* Defer the repaint while a palette is open or a drag is live: swapping the
         list under an open palette moves the row the operator is about to pick. The
         DATA is already swapped, so the palette cannot offer something stale. */
      if (changed && !S.palette && !S.drag) render();
      else if (changed) S.renderDirty = true;
    })
    .catch(()=>{ S.cat.fails++; })
    .then(()=>{ S.cat.inflight = false; });
}

function catalogTick(){
  /* Never poll a hidden window: a backgrounded app must not scan the disk every
     minute for a palette nobody can see. */
  if (document.visibilityState === "hidden") return;
  const now = Date.now();
  if (S.cat.fails){
    const wait = CAT_BACKOFF[Math.min(S.cat.fails - 1, CAT_BACKOFF.length - 1)];
    if (now - S.cat.lastCheckAt < wait) return;
  } else {
    const need = document.hasFocus() ? CAT_FOCUSED_MS : CAT_VISIBLE_MS;
    if (now - S.cat.lastCheckAt < need) return;
  }
  S.cat.lastCheckAt = now;
  refreshCatalog();
}

/* ── editor loaders ──────────────────────────────────────────────────────────
   On demand, like git: walking a real project at boot would cost every operator
   who never opens the editor. */
/* Files screen (SilverBullet sidecar): spawned lazily by the backend on first
   open — walking a repo and starting a process must not cost operators who
   never open Files. force=true is the retry path after a failure. */
async function loadFilesScreen(force){
  if (S.sb && S.sb.running && !force) return;
  S.sbBusy = true; S.sbError = null; render();
  try { S.sb = await apiGet("/api/files/status?start=1"); }
  catch (e) { S.sbError = e.message; S.sb = null; }
  S.sbBusy = false; render();
}

async function loadFs(force){
  if (S.fs && !force) return;
  try { S.fs = await apiGet("/api/fs/tree"); S.fsError = null; }
  catch (e) { S.fsError = e.message; S.fs = null; }
  render();
}

/* Re-render ONLY the file list. A full render() on every filter keystroke would
   rebuild the open <textarea> from S.edText -- losing the caret mid-edit, and
   thrashing on a large file. Scoped DOM surgery is the right tool for a filter. */
function renderFilterOnly(){
  const host = document.querySelector(".fslist");
  if (!host || !S.fs) return;
  const q = (S.fsQuery||"").toLowerCase();
  const files = S.fs.files.filter(f=>!q || f.path.toLowerCase().includes(q));
  host.innerHTML = files.slice(0,600).map(f=>`
    <button class="opt fsf ${S.edFile===f.path?"sel":""}" type="button" data-edopen="${esc(f.path)}">
      <span class="oi"><span class="on">${esc(f.path)}</span>
      <span class="od">${fmtBytes(f.bytes)}</span></span>
    </button>`).join("");
  host.querySelectorAll("[data-edopen]").forEach(b=>
    b.onclick = ()=>openEdFile(b.dataset.edopen));
}

async function openEdFile(path){
  /* Refuse to discard unsaved work silently. This is the only confirm() in the
     editor path and it guards the one irreversible thing here. */
  if (S.edFile && S.edText !== null && S.edText !== S.edBase &&
      !window.confirm("Discard unsaved changes to " + S.edFile + "?")) return;
  S.edFile = path; S.edText = null; S.edBase = null; S.edBytes = null;
  S.edError = null; S.edOk = null;
  render();
  try {
    const r = await apiGet("/api/fs/read?path=" + encodeURIComponent(path));
    if (S.edFile !== path) return;                 /* a newer open won */
    S.edText = r.text; S.edBase = r.text; S.edBytes = r.bytes;
  } catch (e) {
    if (S.edFile !== path) return;
    S.edError = e.message; S.edText = null;
  }
  render();
}

async function saveEdFile(){
  if (!S.edFile || S.edText === null) return;
  S.edBusy = true; S.edError = null; S.edOk = null; render();
  try {
    /* base_bytes lets the SERVER detect that the file changed underneath -- most
       likely because the agent wrote it while this pane was open. Saving blind
       would discard that work with no warning. */
    const r = await apiPost("/api/fs/write",
      { path: S.edFile, text: S.edText, base_bytes: S.edBytes });
    S.edBase = S.edText; S.edBytes = r.bytes;
    S.edOk = r.path + " — " + fmtBytes(r.bytes);
    loadFs(true);                                   /* sizes in the tree are now stale */
  } catch (e) { S.edError = e.message; }
  S.edBusy = false; render();
}

/* Git is fetched on demand, not at boot: a workdir that is not a repository is a
   perfectly normal state and must not cost a failed request on every start. */
/* Dispatcher + scheduler, read when the screen is opened. Lazy for the same
   reason Git is: it walks ledger files in the workdir, and a panel that has
   never shown the screen has no business reading them on every boot. */
async function loadAuto(force){
  if (S.auto && !force) return;
  try {
    S.auto = await apiGet("/api/automation");
    S.autoError = null;
  } catch (e) {
    S.autoError = e.message; S.auto = null;
  }
  render();
}
async function loadProposals(force){
  if (S.props && !force) return;
  try { S.props = (await apiGet("/api/proposals")).proposals || []; S.propError = null; }
  catch (e) { S.propError = e.message; S.props = null; }
  render();
}
async function decideProposal(pid, approve){
  S.propBusy = pid; S.propError = null; render();
  try {
    await apiPost("/api/proposals/" + encodeURIComponent(pid) + "/decide", {approve});
    await loadProposals(true);
    await loadRoutines(true);      /* an approval may have created one */
  } catch (e) { S.propError = e.message; }
  S.propBusy = null; render();
}
async function loadTeamsutra(force){
  if (S.ts && !force) return;
  try { S.ts = await apiGet("/api/teamsutra/tasks"); S.tsError = null; }
  catch (e) { S.tsError = e.message; S.ts = null; }
  render();
}
async function loadRoutines(force){
  if (S.rt && !force) return;
  try { S.rt = await apiGet("/api/routines"); S.rtError = null; }
  catch (e) { S.rtError = e.message; S.rt = null; }
  render();
}
async function rtAction(path, body, msg){
  S.rtBusy = path; S.rtMsg = null; S.rtError = null; render();
  try {
    const r = await apiPost("/api/routines" + path, body || {});
    S.rtMsg = msg || r.note || "Done.";
    await loadRoutines(true);
  } catch (e) { S.rtError = e.message; }
  S.rtBusy = null; render();
}
async function rtLoadRuns(id){
  try { S.rtRuns[id] = await apiGet("/api/routines/" + encodeURIComponent(id) + "/runs?limit=10"); }
  catch (e) { S.rtRuns[id] = {error:e.message}; }
  render();
}
/* Usage. Lazy like Git, and re-read on every open rather than cached in S: a
   utilization figure that is quietly ten minutes stale is worse than one that
   costs a request, and the server already coalesces at 60s against a shared cache. */
async function loadUsage(force){
  if (S.usage && !force) return;
  try {
    S.usage = await apiGet("/api/usage");
    S.usageError = null;
  } catch (e){
    S.usageError = e.message; S.usage = null;
  }
  render();
}

/* A floating popup has to be dismissible the way every other floating thing is:
   click away, or press Escape. Without this the only exit is the × -- fine for a
   block in flow, wrong for a card overlapping the transcript you want back.
   Registered ONCE at top level, not in wire(): wire() runs on every render, and
   re-adding this per render would stack a listener per repaint.
   GUARDED because test_panel.js evaluates this script in a bare Node vm whose
   `document` stub has no addEventListener -- an unguarded call takes the suite
   down before a single assertion runs. */
if (typeof document !== "undefined" && document.addEventListener){
  /* Per-turn controls (thinking log, governance chip, tool output/terminal,
     agent roster) are DELEGATED: patchTurn() replaces their DOM mid-stream, so
     per-render onclick bindings die exactly when the operator wants to click
     them. Registered once; the per-render bindings for these five are gone,
     so a click can never fire twice. */
  document.addEventListener("click", turnControlClick);
  document.addEventListener("click", e=>{
    if (!S.usagePop) return;
    /* The chip's own handler owns the toggle. Ignoring it here stops the pair
       from firing open-then-closed on one click. */
    if (e.target.closest("[data-usagepop]") || e.target.closest(".upop")) return;
    S.usagePop = null; render();
  });
  document.addEventListener("keydown", e=>{
    /* ── Escape cascade, most specific first ────────────────────────────────
       Escape was global for exactly ONE overlay. Four dismissible states had no
       Escape anywhere -- the routine-run view, the permission confirmation, the
       PR form, and the folder editor -- so the only exit was finding the right
       button with the mouse. */
    if (e.key === "Escape"){
      if (S.palette){ S.palette = null; render(); return; }
      if (S.permConfirm){ S.permConfirm = null; render(); return; }
      if (S.prForm){ S.prForm = null; render(); return; }
      if (S.cwdEdit){ S.cwdEdit = null; S.cwdError = null; render(); return; }
      if (S.runOpen){ S.runOpen = null; render(); return; }
      if (S.usagePop){ S.usagePop = null; render(); return; }
      return;
    }
    /* Bare keys must never fire while the operator is typing. */
    const kel = e.target;
    const typing = !!kel && (kel.tagName === "INPUT" || kel.tagName === "TEXTAREA"
                             || kel.tagName === "SELECT" || kel.isContentEditable);
    const mod = e.metaKey || e.ctrlKey;
    const focused = S.openPanes[S.openPanes.length - 1] || null;
    /* Cmd/Ctrl+. INTERRUPTS, wherever focus is. There was no key to stop a turn
       at all. Both channels, because a side turn has its own socket. */
    if (mod && e.key === "."){
      e.preventDefault();
      if (focused){
        [chanKey(focused, false), chanKey(focused, true)].forEach(k=>{
          const ch = CLAUDE_SOCKETS.get(k);
          if (ch && ch.open) ch.ws.send(JSON.stringify({type:"stop"}));
        });
      }
      return;
    }
    /* Cmd+W is Electron's Close Window and the app ships Electron's DEFAULT menu,
       so it is not ours to take. Close-pane is Shift+W. */
    if (mod && e.shiftKey && (e.key === "W" || e.key === "w")){
      e.preventDefault();
      if (focused){ S.openPanes = S.openPanes.filter(x => x !== focused); render(); }
      return;
    }
    if (mod && !e.shiftKey && (e.key === "n" || e.key === "N")){
      e.preventDefault();
      newSession(sessCwd(focused) || "");
      return;
    }
    if (mod && (e.key === "[" || e.key === "]")){
      e.preventDefault();
      const list = S.sessions;
      if (!list.length) return;
      const at = Math.max(0, list.findIndex(x => x.id === focused));
      const nx = list[(at + (e.key === "]" ? 1 : list.length - 1)) % list.length];
      if (nx){
        if (!S.openPanes.includes(nx.id)) S.openPanes.push(nx.id);
        if (S.openPanes.length > 2) S.openPanes = S.openPanes.slice(-2);
        ensureTranscript(nx); render();
      }
      return;
    }
    /* "/" focuses the composer, the way every chat app does it. */
    if (!typing && !mod && e.key === "/"){
      const inp = focused && document.querySelector('[data-sask="' + focused + '"]');
      if (inp){ e.preventDefault(); inp.focus(); }
      return;
    }
  });
}

/* Repository state for one session. Keyed by session because the folder is.
   Re-read after a turn completes (the agent may have committed or branched) and
   whenever the session's folder changes -- both are moments the bar would
   otherwise go quietly stale and describe a repository that is no longer there. */
/* Subagent list for one session. Keyed by session id like the repo bar and
   idempotent the same way: undefined means "not asked", [] means "asked, none".
   The list route reads each agent file, so this is fetched on demand -- when the
   fold opens or a pane is receiving agent writes -- never per repaint. */
async function loadAgents(sid, force){
  if (!sid) return;
  if (S.agents[sid] !== undefined && !force) return;
  try { S.agents[sid] = await apiGet("/api/sessions/" + encodeURIComponent(sid) + "/agents"); }
  catch (e){ S.agents[sid] = []; }
  scheduleRender();
}
/* One subagent's transcript, parsed through the SAME transcriptTurns() the main
   pane uses so an agent turn and a top-level one render identically. Keyed by
   sid+":"+aid so two open agents never clobber each other; null while in flight. */
async function loadAgentTranscript(sid, aid){
  const key = sid + ":" + aid;
  if (S.agentTurns[key] !== undefined) return;
  S.agentTurns[key] = null;
  try {
    const d = await apiGet("/api/sessions/" + encodeURIComponent(sid)
                           + "/agents/" + encodeURIComponent(aid));
    /* Keep the RAW messages: the agent detail renders them as a step sequence
       (Claude's agent view), not folded into one turn. */
    S.agentTurns[key] = (d && d.messages) || [];
  } catch (e){ S.agentTurns[key] = []; }
  scheduleRender();
}
async function loadRepo(sid, force){
  if (!sid) return;
  if (S.repo[sid] !== undefined && !force) return;
  const cwd = sessCwd(sid);
  if (!cwd){ S.repo[sid] = {available:false, reason:"no working directory"}; scheduleRender(); return; }
  try { S.repo[sid] = await apiGet("/api/repo?cwd=" + encodeURIComponent(cwd)); }
  catch (e){ S.repo[sid] = {available:false, reason:e.message}; }
  scheduleRender();
}
/* Pull requests are a NETWORK call through gh, so unlike the repo read they are
   fetched only when the list is actually opened. */
async function loadPrs(sid, force){
  if (!sid) return;
  if (S.prs[sid] && !force) return;
  const cwd = sessCwd(sid);
  if (!cwd) return;
  try { S.prs[sid] = await apiGet("/api/repo/pulls?cwd=" + encodeURIComponent(cwd)); }
  catch (e){ S.prs[sid] = {available:false, reason:e.message, pulls:[]}; }
  scheduleRender();
}

async function loadRunDetail(rid, name){
  try {
    S.runDetail = await apiGet("/api/routines/" + encodeURIComponent(rid)
                               + "/output?name=" + encodeURIComponent(name));
  } catch (e){ S.runDetail = {error:e.message}; }
  /* Only paint if this is still the run being looked at -- clicking through a
     list faster than the reads return would otherwise let an earlier response
     land on top of a later one. */
  if (S.runOpen && S.runOpen.rid===rid && S.runOpen.name===name) render();
}

/* Carry on from a scheduled run, in a real chat pane.
   The run already happened on a claude session and its id was recorded at the
   time, so this is a genuine resume rather than a fresh thread primed with the
   old text: seeding `claude_session` is exactly what the composer's own resume
   path uses, and the agent keeps the context the run built. */
function continueRunThread(rid, d){
  const s = newSession();
  s.title = rid + " · run thread";
  s.claude_session = d.session_id;
  /* The run executed in the ROUTINE's folder (routines.py spawns with the
     routine's cwd), which is where its transcript is filed -- and `claude
     --resume <id>` only resolves in that directory. newSession() was called with
     no argument, so sessCwd fell through to SETTINGS.workdir, the resume failed,
     and the button whose whole purpose is "carry on from where it stopped"
     produced a cold conversation. Both fields: S.cwd drives sessCwd(), s.cwd
     drives the rail grouping. */
  const _rt = ((S.rt && S.rt.routines) || []).find(x => x.id === rid);
  if (_rt && _rt.cwd){ S.cwd[s.id] = _rt.cwd; s.cwd = _rt.cwd; }
  /* The reply is shown as the first turn so the pane is not blank -- you are
     continuing a conversation, and a conversation with no visible history reads
     as a new one. Marked replayed, because these turns were not classified by
     this panel and no placement was ever filed for them. */
  if (d.result){
    s.turns.push({ uid:"run-"+d.session_id, text:"(scheduled run — " + rid + ")",
                   response:String(d.result), streaming:false, real:true,
                   claude_session:d.session_id });
  }
  S.runOpen = null; S.runDetail = null;
  render();
}

async function loadGit(force){
  if (S.git && !force) return;
  try {
    const [status, log] = await Promise.all([apiGet("/api/git/status"), apiGet("/api/git/log")]);
    S.git = { repo: status.repo, status, commits: log.commits || [] };
    S.gitError = null;
  } catch (e) {
    /* The server's message names the actual cause (not a repo / outside the root /
       git not installed). Surfacing our own wording would lose that. */
    S.gitError = e.message; S.git = null;
  }
  render();
}

async function loadGitDiff(path){
  S.gitFile = path; S.gitDiff = null; S.gitDiffTruncated = false; render();
  try {
    const d = await apiGet("/api/git/diff?path=" + encodeURIComponent(path));
    if (S.gitFile !== path) return;          /* a newer selection won; drop this one */
    S.gitDiff = d.text || ""; S.gitDiffTruncated = !!d.truncated;
  } catch (e) {
    if (S.gitFile !== path) return;
    S.gitDiff = ""; S.gitError = e.message;
  }
  render();
}

/* The REAL sessions. session_reader.list_sessions() walks
   ~/.claude/projects/<encoded-cwd>/*.jsonl, newest first. Nothing here is
   derived from placements. */
/* ── live sync with Claude ───────────────────────────────────────────────────
   Sutra reads Claude's transcripts, and it used to read them ONCE, at boot. A
   conversation you had in Claude afterwards simply did not exist here until the
   panel was reloaded, which is what made the two feel like separate programs
   that happen to share a directory.

   The server watches ~/.claude/projects and streams what changed. This end
   applies it: liveness on every session, new conversations appearing in the rail
   as they are started, and a transcript that is OPEN IN A PANE re-read as it
   grows -- so a chat happening in Claude updates here while it happens.

   EventSource, not a socket: one-way traffic, and the browser reconnects on its
   own with no lifecycle for this file to get wrong. */
let _sessStream = null, _sessRefreshTimer = null;

/* A new conversation means the rail needs the full record (title, cwd, branch),
   which the watcher deliberately does not carry -- it stats, it does not parse.
   Coalesced, because starting Claude writes several lines in quick succession
   and each one would otherwise trigger its own list read. */
function scheduleSessionRefresh(){
  clearTimeout(_sessRefreshTimer);
  _sessRefreshTimer = setTimeout(()=>{ loadSessions().then(()=>render()); }, 700);
}

