/* Explicitly end the work, not just the view. Used by Stop, and by app unload. */
function endClaudeChannel(sid){
  return closeClaudeChannel(sid, { force:true });
}
/* A stable per-turn id, assigned once. It is the anchor patchStreaming() writes
   through, so it must not change between renders and must never be reused. */
let _UID = 0;
/* How many session panes stand side by side. Was 2 — the founder asked for
   the vertical planes to go to SIX (2026-08-24: "the panes of the chats:
   1, 2, 3, 4, 5, 6"). .panes already scrolls horizontally and each pane
   floors at 380px, so 6 open panes overflow into scroll, never crush.
   One helper, one rule: the oldest pane is evicted first (FIFO), a re-open
   never duplicates. All three open paths go through here. */
const MAX_PANES = 6;
function pushPane(id){
  if (!S.openPanes.includes(id)) S.openPanes.push(id);
  if (S.openPanes.length > MAX_PANES) S.openPanes = S.openPanes.slice(-MAX_PANES);
}

function turnUid(t){
  if (t && !t.uid) t.uid = "t" + (++_UID);
  return t ? t.uid : "";
}

/* Run the turn. Fire-and-forget by design: tokens arrive on the socket and land on the
   turn object, which re-renders on the throttle. */
function askClaude(s, turn, side){
  if (!turn) return;
  turnUid(turn);
  turn.response = turn.response || "";
  turn.tools = turn.tools || [];
  turn.error = null;
  turn.streaming = true;
  /* Start-of-turn timestamp for the run strip's stopwatch. Set here rather than
     at object creation so it covers EVERY streaming entry -- fresh turn, retry,
     side chat -- through the one function they all pass. `|| Date.now()`
     preserves an existing stamp, so a retry keeps timing from the original send
     (a retry is the same turn, not a new one). */
  turn.ts_ms = turn.ts_ms || Date.now();
  turn.sent = groundingPrefix(turn) + turn.text;   /* exactly what the model receives */
  let ch;
  try { ch = claudeChannel(s, side); }
  catch (e){
    turn.streaming = false;
    turn.error = "could not open the Claude channel: " + e.message;
    scheduleRender(); return;
  }
  ch.pending.push(turn);
  /* The per-session model override, or undefined to let the server fall back to the
     stored setting. Sent per message rather than per connection so a change applies
     to the NEXT message without reconnecting and losing the thread. */
  const model = S.model[s.id];
  /* A side chat never resumes the MAIN thread -- that is what makes it a branch
     rather than a continuation. It does resume ITSELF (ch.sideSession, captured from
     the first `session` frame), so a multi-turn side chat is still one conversation
     instead of a series of strangers. */
  const frame = JSON.stringify({ message: turn.sent,
                                 resume: side ? (ch.sideSession || null)
                                              : resumableId(s),
                                 model: (model === undefined ? null : model),
                                 /* Per-turn CLI options. The SERVER validates every
                                    one of these (build_agent_args); nothing here is
                                    trusted, and an unknown or junk value is dropped
                                    rather than passed to the CLI. */
                                 opts: S.turnOpts[s.id] || null });
  if (ch.open) ch.ws.send(frame); else ch.queue.push(frame);
  scheduleRender();
}
/* The session id to hand the server -- or null when it provably cannot resolve.

   `claude --resume <id>` looks the id up IN THE PROJECT OF ITS WORKING DIRECTORY.
   adoptRealSessions() attaches `claude_session` to every transcript on disk, and
   those transcripts belong to whatever directory they were recorded in -- usually
   a repo, never the panel's own workdir. Sending such an id guaranteed the error
   the operator actually hit:

       No conversation found with session ID: 565ad6a3-...

   The server now replays the message without the id, so nothing is lost either
   way. This stops the doomed round trip from being made at all: a wasted claude
   invocation, several seconds of dead air, and a scary message for a request that
   was never going to work.

   A session with no recorded cwd is still tried -- unknown is not the same as
   mismatched, and the server's replay covers it if the guess is wrong. */
function resumableId(s){
  if (!s.claude_session) return null;
  /* the `provider` frame the server sends on connect, stashed on the session */
  const here  = (s.channel && s.channel.workdir) || "";
  const there = s.cwd || "";
  if (here && there && here !== there) return null;
  return s.claude_session;
}

/* classify -> file the placement -> run Claude under that placement. The classify
   round-trip is awaited (a turn cannot be grounded before it has an address); the
   Claude run is not (it streams into the pane). */
/* ── side chat ───────────────────────────────────────────────────────────────
   Deliberately NOT routed through submitTurn(): that classifies the input and files
   a placement (ADR-028). A side chat is exploratory -- "would OAuth be better?" --
   and filing it would put a decision in the registry that the operator never made.
   So no classify round-trip, and the turn carries no domain: turnBlock already
   renders a turn with no placement honestly rather than inventing one. */
function askSide(sid, text){
  const s = S.sessions.find(x=>x.id===sid);
  if (!s || !text) return;
  const turn = { text: text, ts_ms: Date.now(), response: "", tools: [],
                 error: null, streaming: true, side: true };
  (S.sideTurns[sid] = S.sideTurns[sid] || []).push(turn);
  S.sideText[sid] = "";
  askClaude(s, turn, true);       /* true = side channel, never resumes the main thread */
  render();
}

/* ── attachments ─────────────────────────────────────────────────────────────
   The file is uploaded into the workdir and referenced by RELATIVE PATH. It is not
   inlined into the prompt: a PDF or screenshot is not text, and pasting bytes into
   a message would corrupt both. The agent's cwd IS the workdir, so an @path is
   something it can already read -- no new read surface is opened. */
function composeWithAttachments(sid, text){
  const ready = (S.attach[sid]||[]).filter(a=>a.ref && !a.error && !a.pending);
  if (!text && !ready.length) return "";
  /* Refs FIRST and on their own lines: appending them after the prose ran them into
     the last sentence, and an @path glued to a word does not resolve. */
  const refs = ready.map(a=>a.ref).join("\n");
  S.attach[sid] = (S.attach[sid]||[]).filter(a=>a.pending);   /* keep in-flight ones */
  return refs ? (refs + (text ? "\n\n" + text : "")) : text;
}

function pickAttachment(sid){
  /* A hidden input, created per click and discarded: keeping one in the DOM meant
     render() replaced it mid-dialog and the change event landed on a dead node. */
  const el = document.createElement("input");
  el.type = "file"; el.multiple = true; el.style.display = "none";
  el.onchange = ()=>{ [...(el.files||[])].forEach(f=>uploadAttachment(sid, f)); el.remove(); };
  document.body.appendChild(el);
  el.click();
}

function uploadAttachment(sid, file){
  const list = (S.attach[sid] = S.attach[sid] || []);
  const entry = { name: file.name, bytes: file.size, pending: true, ref: null, error: null };
  list.push(entry);
  render();
  const fr = new FileReader();
  fr.onerror = ()=>{ entry.pending = false; entry.error = "could not read this file"; render(); };
  fr.onload = ()=>{
    /* Strip the data: URL prefix -- the server validates strict base64 and would
       reject "data:image/png;base64,..." wholesale. */
    const b64 = String(fr.result || "").split(",")[1] || "";
    apiPost("/api/attach", { name: file.name, content_b64: b64 })
      .then(r=>{ entry.pending = false; entry.ref = r.ref; entry.bytes = r.bytes;
                 entry.name = r.path.split("/").pop(); })
      /* The server's message names the real cause (too large / bad base64 / workdir
         outside the root). Keep it on THIS entry so one rejection does not discard
         the other attachments. */
      .catch(e=>{ entry.pending = false; entry.error = e.message; })
      .then(()=>render());
  };
  fr.readAsDataURL(file);
}

async function submitTurn(text, sessionId){
  const { session, result } = await runTask(text, sessionId);
  render();
  askClaude(session, result);
}

/* ══════════════════════ state ══════════════════════ */
const S = {
  screen:"departments", sel:null, view:"live", showRetired:false,
  toolOpen:{},                   /* tool_use id -> is its output expanded */
  turnOpts:{},                   /* session id -> per-turn CLI options (effort, budget, ...) */
  optsOpen:{},                   /* session id -> is the options row expanded */
  dirQ:"",                       /* Directory view search box */
  dirSt:null,                    /* Directory charter status filter (null = generator default) */
  /* first run. `onbDismissed` is per-load only; the persisted acknowledgement
     is settings.onboarded, so "Not now" brings the disclosure back next launch.
     runtimeError/sessionsError hold a subsystem that failed WITHOUT taking the
     boot down with it (see boot()'s allSettled). */
  onbDismissed:false, runtimeError:null, sessionsError:null,
  /* git: loaded lazily when the screen is first opened, so a workdir that is not a
     repository costs nothing until the operator actually asks. gitDiff is null while
     a fetch is in flight, "" when git genuinely returned an empty diff -- the two are
     different answers and the screen renders them differently. */
  git:null, gitError:null, gitFile:null, gitDiff:null, gitDiffTruncated:false,
  /* Usage. null means NOT READ YET, which is why the rail withholds its count
     until the screen has been opened -- a 0% before anything was fetched is a
     claim about an account nobody asked about. */
  usage:null, usageError:null,
  /* Which session pane has the usage popover open (session id), or null. Keyed by
     pane rather than a bare boolean: two panes are visible at once, and a shared
     flag would open the popover in both. */
  usagePop:null,
  /* Which session pane has the composer's session menu open (session id), or
     null. Same shape as usagePop, for the same two-panes reason. In-memory
     only: it never enters S.ui, so saveLayout() can never persist it. */
  sessMenu:null,
  /* Which session pane has the composer's ⋯ PANE menu open, or null. Named
     paneMenu, not sessMenu: sessMenu is the RAIL's per-session actions menu,
     and the two sharing one key made the chip toggle the wrong menu. In-memory
     only, like usagePop: NOT in S.ui, so saveLayout() never persists it. */
  paneMenu:null,
  /* Repository state, PER SESSION -- two panes can be in two different folders,
     and one shared object would show whichever loaded last. `undefined` means
     "not asked yet" and draws nothing; an object with available:false means
     "asked, and it is not a repo", which is a normal state worth stating. */
  repo:{}, prs:{}, prsOpen:null, prForm:null, prBusy:false, prError:null, prDone:null,
  /* Subagent transcripts, PER SESSION. `agents` is undefined until asked ([] once
     asked and none found); `agentsFold` is whether the fold is open; `agentOpen`
     is which agent id is expanded in a pane; `agentTurns` caches one agent's
     parsed turns keyed "sid:aid" (null while reading). */
  agents:{}, agentsFold:{}, agentOpen:{}, agentTurns:{},
  auto:null, autoError:null,
  /* updates: null until the operator asks -- see updatesHtml(). */
  upd:null, updBusy:null, updError:null, updMsg:null,
  /* a background stage() is in flight -- distinct from updBusy, which disables
     the buttons; staging deliberately leaves the screen usable */
  updStaging:false,
  /* routines: null until the screen is opened (it shells out to launchctl). */
  rt:null, rtError:null, rtBusy:null, rtMsg:null, rtForm:null, rtRuns:{}, rtOpen:{},
  /* The run being read: {rid, name, started}. null means none is open. runDetail
     is its parsed body, fetched on open -- not with the index, because an index
     of 10 runs would otherwise read 10 output files nobody asked for. */
  runOpen:null, runDetail:null,
  /* what the chat agent asked for; nothing applies until approved. */
  props:null, propBusy:null, propError:null,
  /* transient, self-clearing note -- see the pane close handler. */
  toast:null,
  /* permission mode confirmation, at chat level -- see permSelect(). */
  permConfirm:null, permBusy:false, permError:null,
  /* Per-session composer extras. `attach` holds one entry per pending file (each with
     its own error, so one rejected upload does not discard the others). `model` is a
     per-session OVERRIDE; undefined means "inherit the stored setting", which is why
     it is not seeded with a value. */
  attach:{}, model:{},
  /* Side chats. Turns live HERE, never in s.turns: a branch that appeared in the main
     transcript would not be a branch. Keyed by session id, per pane. */
  sideOpen:{}, sideTurns:{}, sideText:{},
  /* Skills catalog freshness. `etag` is committed only after the payload it
     describes has been applied, so a stored signature always matches the data in
     hand. `delta` is how many entries the last accepted refresh added or removed. */
  cat:{ etag:null, readAt:0, lastCheckAt:0, fails:0, inflight:false, delta:0 },
  /* editor. edText is null while a read is in flight and a STRING once loaded, so
     "" (a genuinely empty file) is distinguishable from "not read yet". edBase is
     what was loaded, so `dirty` is a comparison rather than a guess. */
  fs:null, fsError:null, fsQuery:"",
  edFile:null, edText:null, edBase:null, edBytes:null,
  edBusy:false, edError:null, edOk:null,
  /* null = "show the value in force"; a string = the operator is editing it. Kept in S
     because render() rebuilds the pane wholesale and would otherwise drop the keystrokes. */
  workdirDraft:null,
  /* Terminal pane. The iframe is mounted ONCE and then only shown/hidden: re-creating
     it on every render() would kill the PTY and the session inside it on any unrelated
     state change. termCwd records the workdir the PTY was started with, so a later
     workdir change can say plainly that the running terminal is still in the old one
     rather than silently mislabelling it. */
  termOpen:false, termCwd:null, termW:null, sideTab:"terminal",
  /* Staged desktop update. `updStaged` is the backend's local staging state --
     no network, which is the only reason polling it is acceptable. `updLeft` is
     the countdown; null means not counting. `updDeferred` is per-load and never
     persisted: deferring is not declining, and the update still applies on quit. */
  /* updDismissed holds the VERSION the operator waved away, not a boolean:
     dismissing 2.115.0 must not silence 2.116.0. */
  updStaged:null, updLeft:null, updDeferred:false, updDismissed:null, updApplyError:null,
  updFiring:false,
  /* A session is a run of turns. Each turn resolves to exactly ONE department (ADR-028);
     successive turns may land in different ones, which is how a session traces a path
     through the org. Departments do NOT hand work to each other — no such channel exists. */
  sessions:[], openPanes:[], sgroup:"recent",
  /* "recent" (most-recently-touched project first) | "az". Project grouping only. */
  sessSort:"recent",
  /* Pagination of the on-disk session list. The REST list parses titles, which
     is the expensive part, so it is fetched a page at a time as the operator
     scrolls rather than all at once at boot. sessionRows is the UNION of every
     page fetched so far, keyed by id, and is what adoptRealSessions rebuilds
     S.sessions from -- so a periodic refresh of page 0 cannot drop the pages
     already scrolled in. sessMore stays true until a short page proves the end;
     sessPaging guards against a scroll firing a second fetch mid-flight. */
  sessionRows:new Map(), sessMore:true, sessPaging:false, sessPageSize:100,
  sessTab:{}, collapsed:new Set(),
  /* sid -> the operator has deliberately scrolled AWAY from the newest turn.
     Two weaker designs failed first: a one-shot Set was consumed by an early
     render before the transcript loaded, and a turn-COUNT key skipped re-pinning
     when render() rebuilt #panes with the same turns and reset scrollTop to 0.
     What actually matters is INTENT, so that is what is stored. */
  userScrolled:new Map(),
  draft:{ ops:[], base:{...PLANS[0].base}, rationale:"", plan_origin:"studio-drag", validated_at_ms:null },
  drift:false, sort:{col:"title",dir:1}, cf:{kind:new Set(),status:new Set()}, q:"",
  pmode:"all", selCharter:null, drag:null,
  /* simGen: bumped by invalidateSim() so an in-flight simulate() response from
     before a registry mutation is discarded instead of cached.
     renderDirty: a render() deferred because a drag is in progress (B11). */
  simCache:{}, simPending:new Set(), simGen:0, renderDirty:false, loaded:false,
  /* The composer's "/" palette. (r5: the knowledge-search fields that shared
     this line died with the Knowledge screen.) */
  palette:null,
  /* Composer text per session. render() rebuilds the pane from a template, so
     text living only in the DOM is lost on ANY re-render that is not focus-
     restored -- which is every re-render triggered by something other than the
     operator typing (opening the palette, a simulate() response, a token frame).
     Keeping it in state makes it survive unconditionally. */
  composerText:{},
  /* sessionId -> working directory override. Absent means "use the global setting",
     which is what every session did before this control existed -- so an untouched
     session behaves exactly as it always has. Deliberately NOT persisted: a folder
     silently restored from a previous browser session would spawn an agent somewhere
     the operator never chose in this one. */
  cwd:{},
  cwdEdit:null,        /* sessionId whose folder editor is open, or null */
  /* No per-session provider override: provider is chosen in Settings and
     nowhere else (founder direction 2026-09-03). S.provider/providerError were
     removed with the composer control they served. */
  /* sessionId -> sutra chat id. The DURABLE chat, which outlives any one
     provider session: a chat that has run on Claude and then DeepSeek has two
     native session ids and one of these. Learned from the server's provider
     frame rather than minted here, so the two cannot disagree. */
  sutraId:{},
  /* sessionId -> the last switch frame the server sent, so the thread can show
     a marker at the point the provider changed (or say why it did not). */
  switchNote:{},
  /* Per-session actions menu (Feature A). sessMenu = the session id whose menu
     popover is open (one at a time). sessRename = the session id whose inline
     rename input is showing, or null. Pinned/unread/group are localStorage-
     persisted (see 05-chat.js), mirroring runSeen. */
  sessMenu:null, sessRename:null,
  /* Layout the operator adjusted, restored from localStorage on load:
       paneCollapsed[<"browse"|sessionId>] -> true
       folds[<fold key>]                   -> 0 (closed) | 1 (open)
       browseW                             -> px width of the browse pane */
  ui: loadLayout(),
  /* Settings screen: the in-flight/failed state of a POST, so a refused write
     shows the server's reason instead of silently doing nothing. */
  setBusy:null, setError:null, setOk:null
};
/* The real draft lives server-side at DRAFTS_DIR (outside SUTRA_NATIVE_HOME) -- boot()
   fetches it into S.draft on startup. saveDraft() posts the current S.draft back; callers
   already treat it as fire-and-forget (they call render() right after), so this stays async
   without needing every call site to await it. */
/* Writes are CHAINED, never concurrent. The rationale field posted on every
   keystroke with no ordering guarantee, so a slow early request could land
   after a fast later one and the server would keep the older text — the field
   silently reverting a word or two behind what was typed. Structural edits
   (drop/revert/discard/rebase) flush immediately; typing debounces. */
let _draftChain = Promise.resolve();
let _draftTimer = null;
function _postDraft(){
  const body = { ops: S.draft.ops.slice(), rationale: S.draft.rationale, base: S.draft.base };
  _draftChain = _draftChain
    .then(() => apiPost("/api/org/draft", body))
    .catch(err => console.error("saveDraft failed:", err));  /* keep the chain alive */
  return _draftChain;
}
function saveDraft(){
  if (_draftTimer){ clearTimeout(_draftTimer); _draftTimer = null; }
  return _postDraft();
}
function saveDraftSoon(){
  if (_draftTimer) clearTimeout(_draftTimer);
  _draftTimer = setTimeout(()=>{ _draftTimer = null; _postDraft(); }, 300);
}
async function loadDraft(){
  try {
    const d = await apiGet("/api/org/draft");
    if (d && Array.isArray(d.ops)) {
      S.draft = { ops:d.ops, base:d.base||{}, rationale:d.rationale||"",
                  plan_origin:"studio-drag", validated_at_ms:null };
    }
  } catch (e) { console.error("loadDraft failed:", e); }
}

const el = (h)=>{ const t=document.createElement("template"); t.innerHTML=h.trim(); return t.content; };
const esc = s => String(s==null?"":s).replace(/[&<>"]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[m]));

/* ══════════════════════ markdown, rendered safely ══════════════════════
   Transcript text is UNTRUSTED — it is whatever was typed into a session or
   returned by a model. Turning it into HTML is a new injection surface, so the
   ordering here is not stylistic, it is the whole safety argument:

     1. esc() the ENTIRE input first. After this line no '<' survives, so no
        markup in the source can ever become an element.
     2. Only then apply markdown, and only ever by wrapping already-inert text
        in tags THIS function authors.

   Nothing takes a different path to innerHTML. Links are scheme-checked
   against http/https, so `javascript:` and `data:` URLs cannot survive even
   though the surrounding text is inert. Parked spans use \u0000 sentinels,
   which cannot appear in escaped output, so later passes cannot corrupt them. */
const MD_URL_OK = /^https?:\/\//i;

function mdHtml(src){
  let t = esc(src).replace(/\r\n?/g, "\n");
  const slot = [];
  const park = html => "\u0000" + (slot.push(html) - 1) + "\u0000";

  /* STREAMING: the fence regex below needs the CLOSING ``` to exist, so while
     a reply streamed, an open fence and everything inside it rendered as prose
     and then collapsed into <pre> when the close arrived -- the pane visibly
     re-shaped on every fenced block. Close an unterminated fence before
     parsing so streamed code is code from its first token. Line-anchored
     toggle on purpose: an inline ``` in prose must not flip the state. */
  {
    let open = false;
    for (const l of t.split("\n")) if (/^[ \t]*```/.test(l)) open = !open;
    if (open) t += "\n```";
  }

  t = t.replace(/```[ \t]*([A-Za-z0-9_+.#-]*)\n([\s\S]*?)```/g,
    (m, lang, code) => park('<pre class="md-pre"><code>' + code.replace(/\n+$/, "") + "</code></pre>"));
  t = t.replace(/`([^`\n]+)`/g, (m, c) => park('<code class="md-code">' + c + "</code>"));
  t = t.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, (m, label, url) =>
    MD_URL_OK.test(url)
      ? park('<a class="md-a" href="' + url + '" target="_blank" rel="noopener noreferrer">' + label + "</a>")
      : m);
  t = t.replace(/(^|[\s(])(https?:\/\/[^\s<>()\[\]]+)/g, (m, pre, url) =>
    pre + park('<a class="md-a" href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + "</a>"));

  const inline = x => x
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*\w])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/(^|[^_\w])_([^_\n]+)_/g, "$1<em>$2</em>")
    .replace(/~~([^~\n]+)~~/g, "<del>$1</del>");

  const rows = t.split("\n");
  const out = [];
  const isTableSep = l => /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(l) && l.indexOf("-") !== -1 && l.indexOf("|") !== -1;
  const cells = l => l.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(c => inline(c.trim()));
  let i = 0;
  while (i < rows.length){
    const line = rows[i];

    if (!line.trim()){ i++; continue; }
    if (/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(line)){ out.push("<hr class=\"md-hr\">"); i++; continue; }

    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h){ const n = h[1].length; out.push("<h" + n + ' class="md-h">' + inline(h[2].trim()) + "</h" + n + ">"); i++; continue; }

    /* table: a header row followed by a |---|---| separator */
    if (line.indexOf("|") !== -1 && i + 1 < rows.length && isTableSep(rows[i + 1])){
      const head = cells(line);
      i += 2;
      const body = [];
      while (i < rows.length && rows[i].indexOf("|") !== -1 && rows[i].trim()){ body.push(cells(rows[i])); i++; }
      out.push('<div class="md-tw"><table class="md-t"><thead><tr>'
        + head.map(c => "<th>" + c + "</th>").join("")
        + "</tr></thead><tbody>"
        + body.map(r => "<tr>" + r.map(c => "<td>" + c + "</td>").join("") + "</tr>").join("")
        + "</tbody></table></div>");
      continue;
    }

    if (/^\s*&gt;\s?/.test(line)){
      const buf = [];
      while (i < rows.length && /^\s*&gt;\s?/.test(rows[i])){ buf.push(rows[i].replace(/^\s*&gt;\s?/, "")); i++; }
      out.push('<blockquote class="md-q">' + inline(buf.join(" ")) + "</blockquote>");
      continue;
    }

    const ul = /^(\s*)[-*+]\s+(.*)$/, ol = /^(\s*)\d+[.)]\s+(.*)$/;
    if (ul.test(line) || ol.test(line)){
      /* NESTING. This used to match on the item text alone and ignore the
         indent, so "- a / <2 spaces>- b" came out as two SIBLINGS -- a
         structure the writer did not type. Depth is the leading whitespace,
         two spaces (or one tab) per level, which is what every markdown writer
         actually produces. */
      const lines = [];
      while (i < rows.length && (ul.test(rows[i]) || ol.test(rows[i]))){
        const isOl = ol.test(rows[i]);
        const m = rows[i].match(isOl ? ol : ul);
        const indent = m[1].replace(/\t/g, "  ").length;
        lines.push({ depth: Math.floor(indent / 2), ordered: isOl, text: inline(m[2]) });
        i++;
      }
      const render = (start, depth) => {
        const tag = lines[start].ordered ? "ol" : "ul";
        let html = "<" + tag + ' class="md-l">', k = start;
        while (k < lines.length && lines[k].depth >= depth){
          if (lines[k].depth > depth){
            /* a deeper run belongs INSIDE the item just emitted */
            const [inner, next] = render(k, lines[k].depth);
            html = html.replace(/<\/li>$/, inner + "</li>");
            k = next;
            continue;
          }
          html += "<li>" + lines[k].text + "</li>";
          k++;
        }
        return [html + "</" + tag + ">", k];
      };
      out.push(render(0, lines[0].depth)[0]);
      continue;
    }

    const para = [];
    while (i < rows.length && rows[i].trim()
           && !/^(#{1,6})\s/.test(rows[i]) && !ul.test(rows[i]) && !ol.test(rows[i])
           && !/^\s*&gt;\s?/.test(rows[i]) && !/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(rows[i])){
      para.push(rows[i]); i++;
    }
    /* A parked BLOCK (a fenced code block) on its own line is not prose. Wrapping
       it produced `<p><pre>...</pre></p>`, which is invalid -- the browser closes
       the <p> before the <pre> and the stray </p> lands after it, breaking the
       spacing around every code block in a reply. */
    const joined = para.join("\n");
    if (/^\u0000\d+\u0000$/.test(joined.trim())) out.push(joined.trim());
    else out.push('<p class="md-p">' + inline(joined).replace(/\n/g, "<br>") + "</p>");
  }

  return out.join("").replace(/\u0000(\d+)\u0000/g, (m, n) => slot[Number(n)]);
}

/* ══════════════════════ rail ══════════════════════ */
/* (r5) the duplicate sbPageFromPath that lived here is gone — ONE definition
   remains below (the stricter, previously-winning one). It survives the
   sidecar's retirement as the WORKSPACE's doc-path validator. */
const ICON = {
  term:'<rect x="2.5" y="4" width="19" height="16" rx="2"/><path d="M6.5 9.5l3 2.5-3 2.5M12.5 15h5"/>',
  git:'<circle cx="6" cy="6" r="2.6"/><circle cx="6" cy="18" r="2.6"/><circle cx="18" cy="9" r="2.6"/><path d="M6 8.6v6.8M8.6 6H14a1.5 1.5 0 011.5 1.5v0"/>',
  edit:'<path d="M4 20h4l10.5-10.5a2.1 2.1 0 00-3-3L5 17v3z"/><path d="M13.5 6.5l4 4"/>',
  files:'<path d="M3.5 6.5h6l2 2h9v10.5h-17z"/><path d="M3.5 6.5v-2h5"/>',
  dept:'<rect x="9" y="3" width="6" height="5" rx="1"/><rect x="2" y="16" width="6" height="5" rx="1"/><rect x="16" y="16" width="6" height="5" rx="1"/><path d="M12 8v4M5 16v-2h14v2"/>',
  chart:'<path d="M4 4h11l5 5v11a1 1 0 01-1 1H4a1 1 0 01-1-1V5a1 1 0 011-1z"/><path d="M14 4v6h6M7 14h8M7 17h5"/>',
  plc:'<path d="M3 7h7l2 3h9"/><path d="M3 7v11a1 1 0 001 1h16a1 1 0 001-1v-8"/><circle cx="16.5" cy="14.5" r="2.2"/>',
  know:'<circle cx="11" cy="11" r="7"/><path d="M20 20l-4.3-4.3"/>',
  reorg:'<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="12" r="2.5"/><path d="M6 8.5v7M8.5 6h4a3 3 0 013 3v.8M8.5 18h4a3 3 0 003-3v-.8"/>',
  hist:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/>',
  health:'<path d="M3 13h4l2.5 6 4-14 2.5 8h5"/>',
  skills:'<path d="M12 3l7.5 4.3v8.6L12 20.2 4.5 15.9V7.3z"/><path d="M12 12l7.5-4.4M12 12v8.2M12 12L4.5 7.6"/>',
  link:'<path d="M10.1 13.9a4 4 0 0 0 5.7 0l2.8-2.8a4 4 0 0 0-5.7-5.7l-1.3 1.3"/><path d="M13.9 10.1a4 4 0 0 0-5.7 0l-2.8 2.8a4 4 0 1 0 5.7 5.7l1.3-1.3"/>',
  rout:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.4V12l3 1.8"/><path d="M4.5 5.5l2.2 2.2M19.5 5.5l-2.2 2.2"/>',
  auto:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.2V12l3.2 1.9"/><path d="M12 3.5v1.4M20.5 12h-1.4M12 20.5v-1.4M3.5 12h1.4"/>',
  gear:'<circle cx="12" cy="12" r="3.1"/><path d="M19.4 13.5a7.9 7.9 0 000-3l2-1.5-2-3.4-2.3 1a7.9 7.9 0 00-2.6-1.5L14 2.5h-4l-.5 2.6a7.9 7.9 0 00-2.6 1.5l-2.3-1-2 3.4 2 1.5a7.9 7.9 0 000 3l-2 1.5 2 3.4 2.3-1a7.9 7.9 0 002.6 1.5l.5 2.6h4l.5-2.6a7.9 7.9 0 002.6-1.5l2.3 1 2-3.4z"/>',
  chevron:'<path d="M6 9l6 6 6-6"/>',
  /* v3.3 destinations (PLAN-25 S7) */
  focus:'<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1"/>',
  chats:'<path d="M20.5 12c0 4.1-3.8 7.4-8.5 7.4-1.1 0-2.2-.2-3.2-.5L4 20.5l1.7-4A7 7 0 013.5 12c0-4.1 3.8-7.4 8.5-7.4s8.5 3.3 8.5 7.4z"/>',
  team:'<circle cx="9" cy="8" r="3.2"/><path d="M3 19c0-3.2 2.7-5.4 6-5.4s6 2.2 6 5.4"/><path d="M16 5.6a3.2 3.2 0 010 5.6M18 13.8c2 .8 3.4 2.6 3.4 5.2"/>',
  bal:'<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17M12 12c2.4-1.6 2.4-4.9 0-6.5M12 12c-2.4 1.6-2.4 4.9 0 6.5"/>',
  /* A gauge: what a utilization window is. Deliberately not the clock `rout`
     already uses -- two nav rows with the same glyph are two rows nobody can
     tell apart at 14px. */
  usage:'<path d="M4.2 17a8.5 8.5 0 1115.6 0"/><path d="M12 17l4.2-5.2"/><circle cx="12" cy="17" r="1.3"/>',
  evals:'<rect x="4" y="3.5" width="16" height="17" rx="2"/><path d="M8.5 12.2l2.4 2.4 4.6-5.2"/><path d="M8.5 17h7"/>'
};
/* ── Files bridge helpers ────────────────────────────────────────────────────
   A Knowledge row can open its document in Files. The path arrives from the
   REGISTRY (placement work_ref), not from user HTML, but it still becomes part
   of a URL this window loads, so it is validated as a path and nothing else:
   no scheme, no host, no traversal, no absolute or home-relative form. Returns
   the SilverBullet page name (path minus .md) or null when the value is not a
   markdown document -- callers use null to hide the affordance entirely. */
function sbPageFromPath(p){
  if (typeof p !== "string") return null;
  const raw = p.trim();
  if (!raw) return null;
  /* A colon would allow a scheme (javascript:, http://elsewhere); a backslash
     is a path separator on the other OS and a normalizer's blind spot. */
  if (/[:\\]/.test(raw) || /[\u0000-\u001f\u007f]/.test(raw)) return null;
  if (raw[0] === "/" || raw[0] === "~") return null;
  if (!/\.md$/i.test(raw)) return null;
  const page = raw.slice(0, -3);
  if (!page) return null;                       /* the literal ".md" */
  const segs = page.split("/");
  /* Empty segment catches "a//b" and "foo/.md"; dot segments catch traversal. */
  if (segs.some(s => s === "" || s === "." || s === "..")) return null;
  return page;
}

/* (r5) sbUrl DELETED with the sidecar: no iframe URL is ever built again.
   sbPageFromPath above stays — the workspace still validates doc paths
   through it before any open (DEEPLINKS §2). */

/* A DOM-id-safe, stable hash of an arbitrary key (a cwd can contain / and .).
   Only needs to be collision-free within one render, not cryptographic. */
function hashKey(str){
  let h = 5381;
  for (let i = 0; i < str.length; i++) h = ((h << 5) + h + str.charCodeAt(i)) >>> 0;
  return h.toString(36);
}

function railSpec(){
  const sim = S.loaded ? simulate(S.draft.ops) : null;
  /* "0 open issues" and "we have not been told yet" are different facts, and a
     green-looking 0 for the second is the more expensive lie. Before the
     registry has been read at all, every count is withheld for the same
     reason -- a 0 there would be a claim about a registry nobody has read. */
  const openIssues = !sim ? undefined
    : sim.pending ? "…" : (sim.error ? "!" : sim.findings.length);
  const c = v => S.loaded ? v : undefined;
  return {
    org:[
      /* Workspace (flag-gated, FLAG.md): one surface over the organisation's
         documents. Ships hidden; S92 cutover turns the flag on by default. */
      ...(typeof wsFlagOn === "function" && wsFlagOn()
        ? [{id:"workspace", n:"Workspace", i:"know"}] : []),
      {id:"departments",n:"Departments",i:"dept", c:c(live().length)},
      {id:"charters",   n:"Charters",   i:"chart",c:c(CHARTERS.length)},
      {id:"placements", n:"Placements", i:"plc",  c:c(PLACEMENTS.length)},
      /* Knowledge + Files inventory rows DELETED (r5): the S92 fold's
         one-release clock expired; the Workspace is the only org surface. */
    ],
    change:[
      {id:"reorg",  n:"Reorg plans", i:"reorg", c:PLANS.length},
      {id:"history",n:"History",     i:"hist"},
      /* Git sits in CHANGE because that is what it reports: what changed in the
         working tree. The count is withheld until the screen has been opened --
         a 0 before anything was read would be a claim about a repo nobody looked at. */
      {id:"git",    n:"Git",         i:"git",   c:(S.git ? ((S.git.status||{}).files||[]).length : undefined)},
      /* Editor sits next to Git: both are views of the same working tree, one shows
         what changed and the other lets you change it. Count withheld until read. */
      {id:"editor", n:"Editor",      i:"edit",  c:(S.fs ? S.fs.files.length : undefined)},
      {id:"health", n:"Health",      i:"health",c:openIssues, warn:true}
    ],
    runtime:[
      {id:"skills",  n:"Skills",   i:"skills",c:(SKILLS.length||undefined)},
      /* Dispatcher + scheduler. The count is the dispatch ledger's row count and
         is withheld until the screen has been opened, for the same reason Git's
         is: a 0 before the file was read is a claim about a project nobody
         looked at. */
      {id:"automation",n:"Automation",i:"auto",
       c:(S.auto ? (((S.auto.dispatcher||{}).ledger||{}).rows) : undefined)},
      /* Routines sit next to Automation because both are "what runs without me",
         but they are not the same: Automation REPORTS on subsystems, a routine is
         something the operator creates. Count withheld until read, like Git. */
      {id:"routines", n:"Routines",  i:"rout",
       c:(S.rt ? (S.rt.routines||[]).length : undefined)},
      /* Teamsutra: tasks filed from the Ask Sutra selection chat. The count is
         the OPEN work (queued + claimed + needs_review) — done/dropped would
         inflate it into a lie. Withheld until the screen has been read. */
      /* External World. The count is the number of ACTIVE connectors, and it is
         withheld until the screen has been opened, for the same reason Git's is:
         a 0 before anything was read is a claim about a machine nobody looked
         at. */
      {id:"connectors", n:"Connectors", i:"link",
       c:(S.conn && S.conn.providers
            ? S.conn.providers.reduce((n,p)=>n+(p.connected||0),0) : undefined),
       warn:(S.conn && S.conn.providers
            ? S.conn.providers.some(p=>p.needs_attention>0) : false)},
      /* "Help" to the operator; `teamsutra` in the code, the store and the API
         (founder, 2026-08-24 — a user-facing rename, deliberately not a
         migration: renaming the id would move ~/.sutra-ui/teamsutra and break
         every filed task's provenance for a word on a rail). */
      {id:"teamsutra", n:"Help", i:"rout",
       c:(S.ts ? (S.ts.tasks||[]).filter(t=>["queued","claimed","needs_review"].includes(t.status)).length : undefined)},
      /* Usage sits in RUNTIME because it describes the running account, not the
         org. The count is the ACTIVE window's percentage -- the one number worth
         seeing without opening anything -- and is withheld until the screen has
         been read, like Git's, so the rail never asserts a figure nobody fetched. */
      /* Provider-aware since 2026-09-03: a percentage here while DeepSeek is
         selected describes a plan the panel is not using. See providerUsage. */
      {id:"usage",    n:"Usage",     i:"usage",
       c:((providerUsage() || {}).short) ?? undefined},
      /* Terminal is a PANE TOGGLE, not a screen -- but it belongs in the rail
         anyway. It shipped as a 19px unlabelled icon in the footer and the first
         operator to use it reported "I don't see terminal": a control nobody can
         find is not a shipped feature. The footer icon stays for muscle memory;
         renderRail routes this id to termToggle() instead of setting S.screen. */
      /* Balance is a DESIGN PREVIEW, shipped enabled by explicit founder direction
         (2026-08-07) as a deliberate §8.5.3 exception: no backing state exists yet
         (holding/state/balance/ absent, Stage 1 baseline not started), so the
         screen renders "not yet observing" + a labeled sample — no counts, ever. */
      {id:"balance", n:"Balance",  i:"bal"},
      /* Evals reports the Verifier layer: registry counts + nightly decay
         scorecard. Count = current FAILS from the latest run, withheld until
         the screen has been opened (Git rule: a 0 before the file was read is
         a claim about a run nobody looked at). */
      {id:"evals",  n:"Evals",   i:"evals",
       c:(S.evals && S.evals.present && S.evals.scorecard ? S.evals.scorecard.fail : undefined),
       warn:true},
      {id:"terminal",n:"Terminal", i:"term", toggle:true},
      /* Settings is not a count -- it is provider + permission mode + workdir,
         all three of which are single values with a live server behind them. */
      {id:"settings",n:"Settings", i:"gear"}
    ]
  };
}

function sessMenuHtml(s){
  const sid=s.id;
  if (S.sessRename===sid){
    return `<div class="smenu" role="menu">
      <div class="smrename">
        <input data-renameinput data-sid="${sid}" value="${esc(s.title||"")}"
               aria-label="Rename session" maxlength="200"/>
        <button type="button" data-act="rename-save" data-sid="${sid}">Save</button>
      </div></div>`;
  }
  const real=!!s.real, grp=groupMap()[sid]||"";
  const groups=[...new Set(Object.values(groupMap()))].filter(Boolean);
  const mi=(act,label,extra="")=>`<button type="button" role="menuitem" data-act="${act}" data-sid="${sid}" ${extra}>${label}</button>`;
  return `<div class="smenu" role="menu">
    <div class="smsec">Open in</div>
    ${mi("open-terminal","Terminal")}
    ${mi("open-editor","Editor")}
    ${mi("open-finder","Finder")}
    ${mi("open-repo","Repository bar")}
    <div class="smdiv"></div>
    ${mi("pin", isPinned(sid)?"Unpin":"Pin")}
    ${mi("unread","Mark as unread")}
    ${real?mi("rename","Rename…"):""}
    ${real?mi("fork","Fork"):""}
    <div class="smsec">Move to group</div>
    ${groups.map(g=>mi("group",(g===grp?"✓ ":"")+esc(g),`data-group="${esc(g)}"`)).join("")}
    ${mi("group-new","New group…")}
    ${grp?mi("group","Remove from group",'data-group=""'):""}
    ${real?`<div class="smdiv"></div>${mi("archive","Archive")}
      <button type="button" role="menuitem" class="danger" data-act="delete" data-sid="${sid}">Delete</button>`:""}
  </div>`;
}

/* ── v3.3 shell (PLAN-25 S6-S9) ─────────────────────────────────────────────
   The rail renders the six DESTINATIONS; the second plane renders the chosen
   destination's rows, every one of them an EXISTING screen. railSpec() stays
   the single source for live counts — the planes consume it, so the badge
   logic (and its tests) did not move. */
const DEST_LABEL = { now:"Now", focus:"Focus", chats:"Chats", org:"Org",
                     team:"Help", settings:"Settings" };
const DEST_ICON  = { now:"hist", focus:"focus", chats:"chats", org:"dept",
                     team:"team", settings:"gear" };

/* A destination whose plane spec is empty is FULL-BLEED: no second plane, and
   its screen opens directly — a persisted destSel must not reroute it (codex
   P1, 2026-08-24: a stale destSel.team could hijack Help to another screen).
   Chats is exempt: its plane is the session surface, not rows. */
function destFullBleed(d){
  return d !== "chats" && !(DEST_PLANES[d] || []).length;
}
/* An INLINE destination keeps its rows (so destSel still means something) but
   shows them in the rail accordion instead of a second plane (2.226.0). */
function destInline(d){ return DEST_INLINE.has(d); }
/* The ONE predicate for "no 240px plane column" (codex P1, 2026-08-25):
   full-bleed (no rows) or inline (rows live in the rail). renderPlane and the
   terminal clamp key off this; destSel routing keys off destFullBleed alone. */
function destNoPlane(d){ return destFullBleed(d) || destInline(d); }

function goDest(d){
  if (!DESTS.includes(d)) return;
  S.ui.dest = d;
  if (d === "chats"){
    /* Chats is the session surface: the browse pane yields to session panes,
       exactly as the old Code tab behaved. */
    S.ui.browseClosed = true;
  } else {
    /* 2.118.1: route through openScreen so the lazy loaders fire — entering
       Focus/Team Sutra from the rail used to render Balance/Teamsutra blank,
       because the fetch calls lived only in the click delegation. */
    const sel = destFullBleed(d) ? null : S.ui.destSel[d];
    /* Entering an inline destination opens its accordion; entering any other
       destination closes it (codex P2: one slot, never a stale open section). */
    S.ui.railOpen = destInline(d) ? d : null;
    /* S92 cutover: entering Org lands on the Workspace when it is on; the
       static default (departments) remains the rollback path, and a stored
       destSel still wins — the operator's last pick outranks the default. */
    let fallback = DEST_DEFAULT_SCREEN[d];
    if (d === "org" && typeof wsFlagOn === "function" && wsFlagOn() && SCREENS.workspace)
      fallback = "workspace";
    const target = (sel && SCREENS[sel]) ? sel : fallback;
    if (typeof openScreen === "function" && SCREENS[target]) openScreen(target);
    else { S.ui.browseClosed = false; S.screen = target; }
  }
  saveLayout(); render();
}

/* One destination's plane rows, decorated with railSpec()'s live counts. */
function planeRows(dest){
  const spec = railSpec();
  const byId = {};
  [...spec.org, ...spec.change, ...spec.runtime].forEach(it => { byId[it.id] = it; });
  const row = r => {
    const it = r.screen ? (byId[r.screen] || {}) : {};
    return { screen: r.screen, label: r.label || it.n || r.screen,
             soon: !!r.soon, disabled: !!(r.soon || it.disabled), dis: it.dis,
             c: it.c, warn: !!it.warn, toggle: !!it.toggle };
  };
  const groups = [];
  for (const entry of (DEST_PLANES[dest] || [])){
    /* A row can be feature-flagged (FLAG.md). With the flag off the row must
       not render at all — the byId fallback would otherwise show a bare id. */
    if (entry.flag === "workspace" && !(typeof wsFlagOn === "function" && wsFlagOn())) continue;
    /* (r5) the S92 foldsInto rows are gone from DEST_PLANES; no filter needed. */
    if (entry.group) groups.push({ label: entry.group, rows: entry.rows.map(row) });
    else {
      if (!groups.length || groups[groups.length-1].label) groups.push({ label:null, rows:[] });
      groups[groups.length-1].rows.push(row(entry));
    }
  }
  return groups;
}

function renderPlane(){
  const app = document.getElementById("app"), plane = document.getElementById("plane");
  if (!app || !plane) return;
  app.classList.add("threecol");
  const dest = DESTS.includes(S.ui.dest) ? S.ui.dest : "now";
  /* Full-bleed = empty plane spec (Now by design; Help since 2026-08-24 —
     a one-row plane is a click that buys nothing). One predicate with goDest. */
  const off = destNoPlane(dest);
  const wasOff = app.classList.contains("noplane");
  app.classList.toggle("noplane", off);
  plane.hidden = off;
  /* 2.118.1 (codex fold): the plane appearing or leaving changes the fixed
     chrome the terminal clamp reserves — a width valid on Now can zero the
     detail track once the 240px plane is back. Re-clamp on every flip. */
  if (wasOff !== off && typeof applyTermW === "function" && S.termOpen)
    applyTermW(S.termW || 460);
  const head = document.getElementById("planeHead");
  const body = document.getElementById("planeBody");
  const chats = document.getElementById("planeChats");
  setHtmlIfChanged(head, `<h2>${DEST_LABEL[dest] || ""}</h2>`);
  if (chats) chats.hidden = dest !== "chats";
  if (!body) return;
  body.hidden = dest === "chats";
  if (dest === "chats"){ setHtmlIfChanged(body, ""); return; }
  /* Inline destinations own their rows in the rail; a hidden plane must not
     hold a second set of data-screen / aria-current controls (deepseek P2). */
  if (off){ setHtmlIfChanged(body, ""); return; }
  const planeHtml = planeRows(dest).map(g => {
    /* A group with no label is not a group -- it is the ungrouped remainder, and
       giving it a collapse control would offer to hide rows under a header the
       operator cannot see. Only labelled groups collapse. */
    const ckey = dest + ":" + (g.label || "");
    const collapsible = !!g.label;
    const collapsed = collapsible && !!(S.ui.planeSections && S.ui.planeSections[ckey]);
    const bodyId = "pg-" + hashKey(ckey);
    const head = !collapsible ? "" : `
      <div class="rgrp rgrph ${collapsed ? "collapsed" : ""}">
        <button type="button" class="rgtog" data-planecollapse="${esc(ckey)}"
            aria-expanded="${!collapsed}" aria-controls="${bodyId}"
            title="${collapsed ? "Expand" : "Collapse"} ${esc(g.label)}">
          <svg class="rgchev" width="9" height="9" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="3" aria-hidden="true">
            <path d="M9 6l6 6-6 6"/></svg>
          <span class="rgn">${esc(g.label)}</span>
        </button>
      </div>`;
    return `
    ${head}
    <ul class="nav" id="${bodyId}" ${collapsed ? "hidden" : ""}>${g.rows.map(it=>`
      <li><button type="button" ${it.screen?`data-screen="${it.screen}"`:""} ${it.disabled?"disabled":""}
          aria-current="${it.toggle ? (it.screen==="terminal" && S.termOpen)
                                    : (!S.ui.browseClosed && S.screen===it.screen)}"
          ${it.soon?'title="Coming soon — part of Focus"':""}>
        <span class="lab">${esc(it.label)}</span>
        ${it.soon?`<span class="dis">soon</span>`
          : it.disabled && it.dis ? `<span class="dis">${esc(it.dis)}</span>`
          : (it.c!==undefined?`<span class="ct ${it.warn?"w":""}">${it.c}</span>`:"")}
      </button></li>`).join("")}</ul>`;
  }).join("");
  setHtmlIfChanged(body, planeHtml);        /* r9: only when it changed */
}

/* The one usage figure worth showing without opening anything, for WHICHEVER
   provider is selected.

   Three surfaces render this number -- the rail badge, the footer telemetry
   line, and the per-pane menu row -- and each of them used to derive Claude's
   window percentage directly from S.usage. So selecting DeepSeek changed the
   Usage SCREEN and left three "26%" readings behind it, all of them describing
   a plan the panel was no longer using. Reported 2026-09-03 with a screenshot:
   the screen said "USD 1.81" while the rail said 26 and the footer said "26% of
   the usage window".

   One derivation, three callers. The two providers report different KINDS of
   fact -- a percentage of a rate-limit window versus a pay-as-you-go balance --
   so this returns pre-phrased strings per surface rather than a number the
   callers would have to label themselves and could label inconsistently.

   Returns null when there is nothing true to show yet, which every caller
   renders as its own kind of blank. That matches the existing rule for Claude:
   the rail withholds a figure until the screen has been read, so it never
   asserts a number nobody fetched. */
function providerUsage(){
  if (SETTINGS && SETTINGS.provider === "deepseek"){
    const u = S.deepseekUsage;
    const bal = u && u.available && (u.balances || [])[0];
    if (!bal || bal.total_balance == null) return null;
    const amt = String(bal.total_balance);
    return { short: "$" + amt,
             long:  (bal.currency || "USD") + " " + amt + " balance",
             row:   "$" + amt + " balance" };
  }
  const u = S.usage;
  if (!u || !u.available) return null;
  const pct = Math.round((((u.limits || []).find(r => r.active)
                           || (u.limits || [])[0] || {}).percent) ?? NaN);
  if (!Number.isFinite(pct)) return null;
  return { short: pct, long: pct + "% of the usage window", row: pct + "% used" };
}

/* Row metadata, in USER language (founder 2026-08-24: "user-friendly and
   concise"). The list endpoint reads only each .jsonl's head, so an unopened
   session has no turn count — but the file's size and the word "transcript"
   are file-system provenance, not something a user thinks in. The row says
   "not opened yet" and stops. Lifted to module scope so the pins in
   test_panel.js exercise the SHIPPED function, not a copy. */
function rowMeta(s){
  /* The badge is computed BEFORE the guard chain, not inside its last branch.
     `running` is the panel's own in-flight turn; `live` is the transcript
     being written by Claude outside the panel; `agents_live` lights once the
     subagent liveness fold lands. Only active/running draw — a badge on every
     row would say nothing. */
  const running = sessionBusy(s.id);
  /* WHICH PROVIDER WROTE THIS TRANSCRIPT. /api/sessions has always returned
     `source` ("claude" | "deepseek", session_reader.py:124 and :244) and the
     rail has never rendered it -- so with 30 Claude and 35 DeepSeek sessions on
     this machine the list showed 65 indistinguishable rows. Not a livedot:
     those mean "something is happening right now", and this is a property of
     the file, so it gets its own quiet tag.

     Both providers are labelled rather than only the non-default. There is no
     default to be the exception to -- the two are near evenly split -- and
     labelling one silently implies the other. */
  const prov = s.source
    ? `<span class="provtag ${esc(s.source)}"
         title="This transcript was written by ${esc(s.source)}">${esc(s.source)}</span>`
    : "";
  const badge = prov
    + (running ? `<span class="livedot" title="A turn is running in this panel">running</span>` : "")
    + (!running && s.live === "active"
         ? `<span class="livedot" title="Being written right now in Claude">live</span>` : "")
    + (s.agents_live ? `<span class="livedot" title="Subagent transcripts being written right now"
         >${s.agents_live} agent${s.agents_live===1?"":"s"}</span>` : "");
  if (s.vanished) return badge + `<span style="color:var(--block)">deleted on disk</span>`;
  if (!s.real) return badge + `<span>${s.turns.length} turn${s.turns.length===1?"":"s"}</span>`;
  if (s.loadState === "ok" || s.loadState === "empty")
    return badge + `<span>${s.turns.length} turn${s.turns.length===1?"":"s"}</span>`;
  if (s.loadState === "loading") return badge + `<span>opening…</span>`;
  if (s.loadState === "error") return badge + `<span style="color:var(--block)">can't be opened</span>`;
  return badge + `<span>not opened yet</span>`;
}

/* `project` is the ENCODED directory name (slashes turned into dashes), which
   reads as gibberish in a 200px rail. `cwd` is the same directory unencoded,
   so prefer its last segment. */
function rowWorkspace(s){
  const c = (s.cwd || "").replace(/\/+$/, "");
  if (c) return c.slice(c.lastIndexOf("/") + 1);
  return (s.project || "").replace(/^-+|-+$/g, "");
}

/* The workspace label earns its pixels only when it DIFFERENTIATES: with every
   listed session in one workspace it repeats the same word down the rail and
   says nothing (founder 2026-08-24). */
function workspaceLabel(s, sessions){
  if (!s.real) return "";
  const ws = new Set((sessions || []).filter(x => x && x.real).map(rowWorkspace).filter(Boolean));
  return ws.size > 1 ? rowWorkspace(s) : "";
}

/* ── unchanged-HTML skip, shared (r9) ────────────────────────────────────────
   #scBody got this in #143 and #panes in r8, but the RAIL, the plane and the
   session list still rebuilt on EVERY render — and the rail is the most
   clicked surface in the app. Replacing a button between mousedown and
   mouseup means the browser never fires a click on it: the founder's "I press
   it and nothing happens". Measured: a real-input sweep clicked the Workspace
   rail row, the press and release both landed on it, and the screen never
   changed. Regions whose markup is unchanged are left alone.
   Any code that patches DOM inside one of these regions WITHOUT going through
   its renderer must call invalidateHtmlCache(el) so the next identical render
   still repaints. */
function setHtmlIfChanged(el, html){
  if (!el) return false;
  if (el.__lastHtml === html) return false;
  el.__lastHtml = html;
  el.innerHTML = html;
  return true;
}
function invalidateHtmlCache(el){ if (el) el.__lastHtml = null; }

function renderRail(){
  const nav = document.getElementById("railnav");
  const railHtml = !nav ? "" : DESTS.map(d=>{
    const inline = destInline(d);
    const open = inline && S.ui.railOpen === d;
    /* While the accordion is open the CHILD row carries the highlight and the
       parent only reads as the open section (data-open); collapsed, the parent
       takes the highlight back so the rail still says where you are. */
    const current = S.ui.dest === d && !open;
    const chev = inline ? `<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>` : "";
    /* Child rows carry data-screen ONLY (never data-dest) so the #app screen
       delegation opens them and the rail capture handler lets them through. */
    const sub = !open ? "" : `<ul class="nav sub" id="acc-${d}">${planeRows(d).flatMap(g => g.rows).map(it=>`
      <li><button type="button" ${it.screen?`data-screen="${it.screen}"`:""} ${it.disabled?"disabled":""}
          aria-current="${!S.ui.browseClosed && S.screen===it.screen}"
          ${it.soon?'title="Coming soon — part of Focus"':""}>
        <span class="lab">${esc(it.label)}</span>
        ${it.soon?`<span class="dis">soon</span>`
          : it.disabled && it.dis ? `<span class="dis">${esc(it.dis)}</span>`
          : (it.c!==undefined?`<span class="ct ${it.warn?"w":""}">${it.c}</span>`:"")}
      </button></li>`).join("")}</ul>`;
    return `
    <li><button type="button" data-dest="${d}" aria-current="${current}"
        ${inline?`data-open="${open}" aria-expanded="${open}" aria-controls="acc-${d}"`:""}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">${ICON[DEST_ICON[d]]}</svg>
      ${DEST_LABEL[d]}${chev}
    </button>${sub}</li>`;
  }).join("");
  setHtmlIfChanged(nav, railHtml);          /* r9: only when it changed */
  renderPlane();
  if (typeof paintTelemetry === "function") paintTelemetry();


  /* Sessions, two ways.
     RECENT is the familiar shape — date buckets, newest first.
     BY DEPARTMENT is the one only Sutra can offer: every turn already resolved to exactly one
     accountable department, so the session list and the org chart are the same tree. */
  document.querySelectorAll("[data-sgroup]").forEach(b=>
    b.setAttribute("aria-pressed", String(S.sgroup===b.dataset.sgroup)));
  /* The sort control only means something under Project grouping (see the markup
     comment). Its label states the CURRENT order, not the one clicking would
     produce -- a control whose text is a promise about the next click reads as
     the current state to everyone who is not thinking about it. */
  const sortBtn = document.getElementById("sessSort");
  if (sortBtn){
    const on = S.sgroup === "project";
    sortBtn.disabled = !on;
    sortBtn.setAttribute("aria-pressed", String(on && S.sessSort === "az"));
    sortBtn.title = !on
      ? "Sorting applies to Project grouping"
      : (S.sessSort === "az" ? "Sorted A–Z — click for most recent"
                             : "Sorted by most recent — click for A–Z");
    sortBtn.setAttribute("aria-label", sortBtn.title);
  }

  const bucket = ms => {
    const d = Math.floor((NOW - ms)/DAY);
    return d<=0 ? "Today" : d===1 ? "Yesterday" : d<=7 ? "Previous 7 days"
         : d<=30 ? "Previous 30 days" : "Older";
  };
  const deptsOf = s => [...new Set(s.turns.filter(t=>t.domain).map(t=>dPath(t.domain.ref)))];
  const sessMeta = rowMeta, projOf = rowWorkspace;

  const sessRow = (s, trail) => {
    const sid=s.id, open=S.openPanes.includes(sid);
    return `<li class="srow${isPinned(sid)?" pinned":""}" data-sid="${sid}">
      <button type="button" class="rowopen" data-open="${sid}"
          aria-current="${open}"
          title="${esc(s.real ? (s.cwd || s.project || "") : "started in this panel")}">
        <span class="t">${isUnread(sid)?'<span class="udot" aria-label="unread"></span>':""}${esc(s.title)}</span>
        <span class="m">${sessMeta(s)}${trail||""}</span>
      </button>
      <button type="button" class="rowmenu" data-sessmenu="${sid}"
          aria-haspopup="true" aria-expanded="${S.sessMenu===sid}"
          aria-label="Actions for ${esc(s.title)}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="5" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="12" cy="19" r="1.6"/></svg>
      </button>
      ${S.sessMenu===sid?sessMenuHtml(s):""}
    </li>`;
  };

  let html = "";
  if (S.sgroup === "recent"){
    const order = ["Today","Yesterday","Previous 7 days","Previous 30 days","Older"];
    const g = {};
    S.sessions.forEach(s=>{ const k=bucket(s.updated_ms||s.created_ms); (g[k]=g[k]||[]).push(s); });
    html = order.filter(k=>g[k]).map(k=>`
      <div class="rgrp">${k}</div>
      <ul class="rlist">${pinFirst(g[k]).map(s=>{
        const ds = deptsOf(s);
        const held = s.turns.some(t=>t.mode==="floor");
        const ws = s.real ? workspaceLabel(s, S.sessions) : "";
        const trailTxt = s.real ? ws : (ds.length?ds.join(" → "):"—");
        const trail = (trailTxt ? `<span>${esc(trailTxt)}</span>` : "")
          + (held?'<span style="color:var(--warn)">held</span>':"");
        return sessRow(s, trail);}).join("")}</ul>`).join("");
    if (!S.sessions.length) html = `<p style="padding:10px 12px;font-size:11px;color:var(--faint)">
      ${S.sessionsError
        ? `Could not read <code>~/.claude/projects</code> — ${esc(S.sessionsError)}.
           Nothing is claimed here about what is or is not on disk.`
        : `No sessions on disk under <code>~/.claude/projects</code>, and none started here yet.`}</p>`;
  } else if (S.sgroup === "project"){
    /* Keyed on the FULL cwd, labelled with its last segment. Two checkouts can
       share a basename ("sutra" under two parents) and merging them would put
       sessions from different repositories in one group -- and, worse, give the
       group's + a directory it might not belong to. The full path is also what
       the + needs, so the key is the useful value rather than a display string. */
    const g = new Map();
    S.sessions.forEach(s=>{
      const key = (s.cwd || "").replace(/\/+$/, "") || null;
      const label = key ? key.slice(key.lastIndexOf("/") + 1) : (projOf(s) || "No folder");
      if (!g.has(key)) g.set(key, {label, cwd:key, items:[], last:0});
      const e = g.get(key);
      e.items.push(s);
      e.last = Math.max(e.last, s.updated_ms || s.created_ms || 0);
    });
    const groups = [...g.values()].sort((a,b)=>
      S.sessSort === "az"
        ? a.label.localeCompare(b.label, undefined, {numeric:true, sensitivity:"base"})
        /* Default is most-recently-touched first: the project you were last in is
           the one you are most likely returning to. */
        : (b.last - a.last));
    html = groups.map(grp=>{
      /* Collapse is per project, keyed by cwd under the "project:" namespace so
         a folder collapsed here cannot also collapse a same-named bucket in the
         department view. Default is EXPANDED: only an explicit collapse persists,
         so a fresh install shows every group open. */
      const ckey = "project:" + (grp.cwd || "\u2205");
      const collapsed = !!(S.ui.sessCollapsed && S.ui.sessCollapsed[ckey]);
      const bodyId = "rl-" + hashKey(ckey);
      return `
      <div class="rgrp rgrph ${collapsed ? "collapsed" : ""}">
        <button type="button" class="rgtog" data-sesscollapse="${esc(ckey)}"
            aria-expanded="${!collapsed}" aria-controls="${bodyId}"
            title="${collapsed ? "Expand" : "Collapse"} ${esc(grp.label)}">
          <svg class="rgchev" width="9" height="9" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="3" aria-hidden="true">
            <path d="M9 6l6 6-6 6"/></svg>
          <span class="rgn" title="${esc(grp.cwd || "sessions with no recorded folder")}">${esc(grp.label)}</span>
          <span class="rgc">${grp.items.length}</span>
        </button>
        ${grp.cwd ? `<button type="button" class="rgadd" data-newproj="${esc(grp.cwd)}"
             title="New session in ${esc(grp.cwd)}"
             aria-label="New session in ${esc(grp.label)}">
           <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                stroke-width="2.6" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
         </button>` : ""}
      </div>
      <ul class="rlist" id="${bodyId}" ${collapsed ? "hidden" : ""}>${pinFirst(grp.items
        .sort((a,b)=>(b.updated_ms||b.created_ms||0)-(a.updated_ms||a.created_ms||0)))
        .map(s=>{
          const held = s.turns.some(t=>t.mode==="floor");
          const trail = held?'<span style="color:var(--warn)">held</span>':"";
          return sessRow(s, trail);}).join("")}</ul>`;}).join("");
    if (!groups.length) html = `<p style="padding:10px 12px;font-size:11px;color:var(--faint)">
      No sessions yet. Transcripts are read from <code>~/.claude/projects</code>.</p>`;
  } else {
    const g = {};
    S.sessions.forEach(s=>s.turns.forEach(t=>{
      if (!t.domain) return; (g[t.domain.ref]=g[t.domain.ref]||[]).push({s,t}); }));
    html = Object.entries(g)
      .sort((a,b)=>dPath(a[0]).localeCompare(dPath(b[0]),undefined,{numeric:true}))
      .map(([ref,items])=>{
        const d = byRef(ref); if(!d) return "";
        const held = items.filter(x=>x.t.mode==="floor").length;
        const uniq = [...new Map(items.map(x=>[x.s.id,x.s])).values()];
        return `<div class="rgrp">${esc(dPath(ref))} ${esc(d.name)}${held?` · ${held} held`:""}</div>
          <ul class="rlist">${pinFirst(uniq).map(s=>
            sessRow(s, `<span>${items.filter(x=>x.s.id===s.id).length} turn(s) here</span>`)
          ).join("")}</ul>`;
      }).join("");
    if (!html) html = `<p style="padding:10px 12px;font-size:11px;color:var(--faint)">
      Nothing filed yet. Transcripts read from <code>~/.claude/projects</code> ran outside
      this panel, so no department was ever resolved for them — they group under Recent only.</p>`;
  }
  setHtmlIfChanged(document.getElementById("sessions"), html);
}



/* ── who is signed in ─────────────────────────────────────────────────────
 * The rail footer used to be a hardcoded "TC" -- a developer's own initials,
 * shipped to every operator. Sutra runs on top of Claude Code, so the person's
 * identity is already known; it comes from the /api/settings payload.
 *
 * Unknown stays unknown. When Claude has no account on this machine (fresh
 * install, signed out) the chip renders a neutral dot rather than inventing
 * initials, because a plausible-looking wrong identity is worse than an
 * obviously absent one.
 */
let CLAUDE_ACCOUNT = null;

function paintAvatar(){
  const el = document.querySelector(".rfoot .av");
  if (!el) return;
  const a = CLAUDE_ACCOUNT;
  if (a && a.initials){
    el.textContent = a.initials;
    el.classList.remove("av-unknown");
    /* Full identity on hover: two people with the same initial otherwise have
       no way to tell which account the panel is driving. */
    el.title = [a.display_name, a.email].filter(Boolean).join(" — ")
             || "signed in to Claude";
  } else {
    el.textContent = "";
    el.classList.add("av-unknown");
    el.title = "Not signed in to Claude on this machine";
  }
}
