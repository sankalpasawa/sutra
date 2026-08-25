/* Workspace — the merged registry-first screen (PLAN-100 S57-S71).
 *
 * One screen replaces Knowledge + Files: the left pane is the ORGANISATION —
 * a registry-first tree Department > Charter > Document — documents open in
 * the SilverBullet sidecar iframe, charters are readable pages themselves,
 * folders exist as a LENS over the same documents, and search spans documents
 * and registry records. Design of record: workspace-states.html states 01-14
 * (DESIGN-LOCK.md); strings verbatim from COPY.md; transitions from
 * STATE-MACHINE.md; typed failures from ERROR-MODEL.md.
 *
 * FLAG DISCIPLINE (FLAG.md): everything here is inert until `flags.workspace`
 * is true in the SETTINGS payload. With the flag off this file registers
 * NOTHING — no SCREENS entry, no TITLES entry, and every listener below
 * early-returns — so loading the script is a zero-behaviour change. The flag
 * is read from the /api/settings payload the panel already fetches at boot;
 * there is no second fetch and no client-only gate the server does not share.
 *
 * BOUNDARIES (ARCH.md): this file owns SCREENS.workspace and the S.ws slice
 * and nothing else. It never builds a URL by hand — the iframe src comes ONLY
 * from sbUrl(port, sbPageFromPath(path)) (02-helpers.js) and is assigned as a
 * DOM property in wireWorkspace(), never rendered into markup. Every string
 * that reaches innerHTML goes through esc(); search snippets arrive as plain
 * text + integer ranges and are marked up client-side from offsets only.
 */

/* ── state slice ─────────────────────────────────────────────────────────────
   Torn down on screen exit keeping only {lens, lastDocPath} (ARCH.md memory
   plan): the tree, results and snippets of a screen nobody is looking at are
   memory spent on nothing, and the return trip refetches and rides the
   server-side tree cache. */
S.ws = {
  loaded:false, loading:false,
  tree:null,                    /* /api/workspace/tree payload */
  treeError:null,               /* {kind, message} — typed, never an HTTP status */
  lens:"org",                   /* "org" | "folders" — folders reuses S.fs (loadFs) */
  q:"", results:null,           /* /api/workspace/search payload, null = closed */
  searchSeq:0,                  /* stale-response token: only the newest query may land */
  searchEpisode:false,          /* telemetry: search_used fires once per episode */
  sel:null,                     /* {type:"doc",path} | {type:"charter",id} — what the centre shows */
  cursor:null,                  /* keyboard row cursor: {mode:"tree"|"res", i} */
  charter:null,                 /* /api/workspace/charter payload for the open charter page */
  matched:null,                 /* matched_on fields when the charter came from a record result (state 04) */
  doc:null,                     /* /api/workspace/doc payload for the open document */
  docPath:null,                 /* open doc identity — a PATH, never a title (API-CONTRACT identity rule) */
  docMtime:null,                /* mtime captured at open — the changed-on-disk comparator (F3) */
  lastRead:null,                /* {path, text, editable} — the last read copy; what "Save a copy" writes */
  docGone:false,                /* state 14 */
  changed:false,                /* state 12 banner */
  editing:false, unsaved:false, /* state 07 */
  lastDocPath:null,             /* survives teardown; boot restore per STATE-MACHINE 10→01 */
  notice:null,                  /* one transient server message (deep-link reject, failed action) */
  focusFrameOnLoad:false,       /* A11Y R1: focus moves into the iframe only on an EXPLICIT open */
  busy:null                     /* an action in flight ("fileit"|"newdoc"|"savecopy") — disables its button */
};

/* ── flag + activity predicates ────────────────────────────────────────────── */
/* The one place the flag is read. SETTINGS is the boot-fetched /api/settings
   payload; absent, malformed or false all mean OFF (FLAG.md default). */
function wsFlagOn(){
  /* S92 cutover: absent means ON; only an explicit false turns the screen
     off (FLAG.md rollback). Malformed settings fail OPEN post-cutover —
     the Workspace is the default surface, not the experiment. */
  if (!SETTINGS || !SETTINGS.flags) return true;
  return SETTINGS.flags.workspace !== false;
}
/* Every delegated listener guards on this: flag on AND the screen is showing.
   A listener that fires on another screen would be exactly the stray-attribute
   bug the connectors delegate scopes against. */
function wsActive(){ return wsFlagOn() && S.screen === "workspace"; }

/* ── copy of record (COPY.md) ────────────────────────────────────────────────
   Exact strings, one table, so a test can pin them and a copy delta is a
   one-line diff against COPY.md rather than a hunt through templates. */
const WS_COPY = {
  searching: "searching\u2026",
  search: "Search",
  edit: "Edit",
  done: "Done",
  readOnly: "read-only",
  offline: "offline",
  lensOrg: "Organisation",
  lensFolders: "Folders",
  unfiled: "Unfiled",
  recGroup: "CHARTERS AND DEPARTMENTS",
  ckCharter: "CHARTER",
  ckLinked: "LINKED FROM",
  ckFiling: "FILING",
  newDocHere: "New document here",
  unfiledNotice: "Not filed under a charter yet.",
  fileIt: "File it",
  filingNone: "none",
  filingNotFiled: "not filed",
  unsaved: "unsaved",
  emptyMsg: "Documents Sutra writes will appear under the charter they belong to.",
  newDoc: "New document",
  noResults: "No document, charter or department contains that.",
  changedNotice: "Sutra changed this file while you had it open.",
  reload: "Reload",
  keepMine: "Keep mine",
  engineDown: "Documents cannot be opened right now. The organisation is still here, and your files are untouched.",
  tryAgain: "Try again",
  docGone: "This document is no longer there. Your last read copy is on screen.",
  saveCopy: "Save a copy"
};

/* ── typed fetch ─────────────────────────────────────────────────────────────
   apiGet() throws an Error whose message is `detail || message` — it never
   surfaces the workspace envelope's `error.kind`, and ERROR-MODEL.md requires
   the frontend to switch on KIND, never on HTTP status. So workspace requests
   go through this thin variant that preserves the envelope. A network-level
   failure (fetch itself rejects — server gone) is F1 by definition, so it is
   typed engine_down; an unrecognized kind also renders F1's copy downstream
   (ERROR-MODEL fail-safe). */
async function wsGet(path){
  let r;
  try { r = await fetch(API + path, { headers: (typeof panelToken === "function" ? { "X-Sutra-Panel": panelToken() } : {}) }); }
  catch (e){
    const err = new Error("the panel backend is unreachable");
    err.kind = "engine_down"; throw err;
  }
  if (r.ok) return r.json();
  let kind = null, message = "";
  try {
    const j = await r.json();
    if (j && j.error){ kind = j.error.kind || null; message = j.error.message || ""; }
  } catch (e) { /* a non-JSON body carries no kind; fail-safe below */ }
  const err = new Error(message || (path + " -> " + r.status));
  err.kind = kind || "engine_down";
  throw err;
}

/* ── telemetry (PRD §5) ──────────────────────────────────────────────────────
   Counts only — the row the backend writes is {ts, event}; nothing here ever
   sends a query, a path or a title. Fire-and-forget with a swallowed error:
   a missing counter endpoint (S52 lands with the backend) must never cost the
   screen a visible failure. */
function wsPing(event){
  if (!wsFlagOn()) return;
  try { apiPost("/api/workspace/telemetry", { event: event }).catch(()=>{}); }
  catch (e) { /* apiPost itself throwing (test stubs) is as ignorable as a 404 */ }
}

/* ── error kind → design state (ERROR-MODEL families) ─────────────────────── */
function wsStateFromError(kind){
  return { engine_down:"13", not_found:"14", mismatch:"12", registry_empty:"08" }[kind]
    /* fail-safe: an unrecognized kind renders F1's copy — the one family whose
       message promises nothing about the file that failed */
    || "13";
}

/* ── the 14-state resolver ───────────────────────────────────────────────────
   Pure over S.ws + S.sb, so tests can drive every transition without a DOM.
   Order matters: the machine's interrupts (12, 14) and degradations (13)
   outrank steady states; search overlays (03/04/09) outrank what is under
   them; 11 is a session MODE that renders as 01-with-no-edit-affordances, so
   it resolves only when nothing more specific does. */
function wsCurrentState(){
  const w = S.ws;
  if (w.loading && !w.tree) return "10";
  if ((w.treeError && wsStateFromError(w.treeError.kind) === "13") ||
      S.sbError || (S.sb && !S.sb.running)) return "13";
  if (w.results){
    const c = w.results.counts || {};
    if (!(c.documents || 0) && !(c.records || 0)) return "09";
    if (w.sel && w.sel.type === "charter" && w.matched) return "04";
    return "03";
  }
  if (w.tree && !wsTreeHasDocs(w.tree)) return "08";
  if (w.docGone) return "14";
  if (w.changed) return "12";
  if (w.editing) return "07";
  if (w.sel && w.sel.type === "charter") return "02";
  if (w.lens === "folders") return "05";
  if (w.sel && w.sel.type === "doc" && wsDocIsUnfiled(w.sel.path)) return "06";
  if (!wsEditAllowed()) return "11";
  return "01";
}
function wsTreeHasDocs(tree){
  return (tree.unfiled || []).length > 0 ||
    (tree.departments || []).some(d => (d.charters || []).some(c => (c.docs || []).length));
}
function wsDocIsUnfiled(path){
  const t = S.ws.tree;
  return !!(t && (t.unfiled || []).some(u => u.path === path));
}
/* Best-known edit gate. The authority is server-side (SUTRA_UI_ALLOW_EDIT);
   the sidecar status and /api/fs/read both report it, so believe whichever has
   answered. Optimistic before either has — the server 403s a write regardless,
   so the only cost of optimism is a button that reports the refusal. */
function wsEditAllowed(){
  if (S.sb && typeof S.sb.readonly === "boolean") return !S.sb.readonly;
  if (S.ws.lastRead && typeof S.ws.lastRead.editable === "boolean") return S.ws.lastRead.editable;
  return true;
}

/* ── registration ────────────────────────────────────────────────────────────
   Deferred past module eval on purpose: SETTINGS is fetched at boot, AFTER the
   scripts run, so eval-time registration could never honour the flag. Both
   entry paths (the loader hook and wire()) call this; with the flag off it
   does nothing — SCREENS.workspace stays undefined and openScreen("workspace")
   refuses, which IS the inertness contract. TITLES gets its row here too:
   render() does `const [t,src] = TITLES[S.screen]`, so a SCREENS entry without
   a TITLES one is a TypeError that aborts render(), not a blank header. */
function wsEnsureRegistered(){
  if (!wsFlagOn() || SCREENS.workspace) return;
  SCREENS.workspace = wsScreenHtml;
  TITLES.workspace = ["Workspace",
    "registry-first tree — departments · charters · documents"];
}

/* ── loaders ─────────────────────────────────────────────────────────────── */
/* The one open path (openScreen hooks this, like loadFilesScreen for Files).
   Flag off = no fetch, no state change, nothing. */
async function loadWorkspace(force){
  if (!wsFlagOn()) return;
  wsEnsureRegistered();
  if (S.ws.loaded && !force) return;
  if (!S.ws.loaded) wsPing("workspace_open");
  S.ws.loading = true; S.ws.treeError = null; render();
  try {
    S.ws.tree = await wsGet("/api/workspace/tree");
    S.ws.loaded = true;
    /* A fresh tree can drop departments; explicit expand/collapse choices for
       refs that no longer exist are noise forever after (deepseek finding 8). */
    if (S.ws.openDeps){
      const live = new Set((S.ws.tree.departments || []).map(d => d.ref));
      live.add("__unfiled__");
      for (const k of Object.keys(S.ws.openDeps)) if (!live.has(k)) delete S.ws.openDeps[k];
    }
    /* Boot restore (STATE-MACHINE 10→01): last-open doc if it still exists,
       else the most-recently-updated doc. NOT an explicit open, so the iframe
       must not steal focus (A11Y R1) — wsOpenDoc is told so. */
    if (!S.ws.sel){
      const docs = wsAllDocs(S.ws.tree);
      let pick = S.ws.lastDocPath && docs.find(d => d.path === S.ws.lastDocPath);
      if (!pick && docs.length) pick = docs.reduce((a,b)=> (b.mtime||0) > (a.mtime||0) ? b : a);
      if (pick) wsOpenDoc(pick.path, { restore:true });
    }
  } catch (e){
    /* registry_empty never reaches here — tree answers 200 with empty arrays
       (F4); what lands here is engine_down or the fail-safe. */
    S.ws.treeError = { kind: e.kind || "engine_down", message: e.message };
  }
  S.ws.loading = false; render();
}
function wsAllDocs(tree){
  const out = [];
  (tree.departments || []).forEach(d => (d.charters || []).forEach(c =>
    (c.docs || []).forEach(x => { if (!x.missing) out.push(x); })));
  (tree.unfiled || []).forEach(x => out.push(x));
  return out;
}

/* ── search (states 03/04/09, PRD SC1-SC10) ─────────────────────────────────
   Debounced 150 ms; a sequence token drops responses that arrive for a
   superseded query — the retry story for search IS the next keystroke
   (ERROR-MODEL retry table), so a failed request renders nothing and the
   debounce re-fires it. */
let _wsSearchTimer = null;
const WS_SEARCH_DEBOUNCE_MS = 150;
function wsSearchInput(q){
  const had = !!S.ws.q;
  S.ws.q = q;
  if (_wsSearchTimer) clearTimeout(_wsSearchTimer);
  if (!q){
    /* Empty query = search CLOSED, centre keeps the last doc (SC9 / 03→01). */
    S.ws.results = null; S.ws.matched = null; S.ws.searchEpisode = false;
    S.ws.cursor = null;
    render(); return;
  }
  if (!had && !S.ws.searchEpisode){ S.ws.searchEpisode = true; wsPing("search_used"); }
  const seq = ++S.ws.searchSeq;
  /* In-flight is VISIBLE (reviewer 2026-08-25, blocker 1): a cold search on a
     large corpus takes seconds, and a silent pane reads as broken. */
  S.ws.searching = true;
  wsRenderSideOnly();
  _wsSearchTimer = setTimeout(()=>{ _wsSearchTimer = null; wsRunSearch(q, seq); },
                              WS_SEARCH_DEBOUNCE_MS);
}
async function wsRunSearch(q, seq){
  try {
    const r = await wsGet("/api/workspace/search?q=" + encodeURIComponent(q));
    if (seq !== S.ws.searchSeq) return;          /* a newer query owns the pane */
    S.ws.results = r;
    S.ws.searching = false;
    S.ws.cursor = null;
  } catch (e){
    if (seq !== S.ws.searchSeq) return;
    S.ws.searching = false;
    /* engine_down mid-search degrades the whole screen, not just the pane. */
    if ((e.kind || "engine_down") === "engine_down")
      S.ws.treeError = { kind:"engine_down", message: e.message };
  }
  wsRenderSideOnly();
}
/* Result grouping, pure and exported for tests: documents first, then records
   (state 03); the top-bar count is the TOTAL pre-cap (SC7). */
function wsGroupResults(payload){
  const docs = (payload && payload.documents) || [];
  const recs = (payload && payload.records) || [];
  const counts = (payload && payload.counts) || {};
  return {
    docs: docs, records: recs,
    total: (counts.documents || 0) + (counts.records || 0),
    truncated: !!(payload && payload.truncated)
  };
}

/* Snippet marking. The server ships PLAIN TEXT plus [start,end) offsets in
   Unicode CODE POINTS (API-CONTRACT #search); nothing renderable crosses the
   wire. Split by code points FIRST (a surrogate pair is one unit), esc() each
   inert segment, and only then author the <mark> tags here — the same
   escape-then-wrap order mdHtml() uses, for the same reason: no path to
   innerHTML that did not pass esc(). */
function wsMarkSnippet(text, ranges){
  const cps = Array.from(String(text == null ? "" : text));
  const rs = (ranges || []).slice().sort((a,b)=>a[0]-b[0]);
  let out = "", pos = 0;
  for (const r of rs){
    const a = Math.max(0, Math.min(cps.length, r[0]|0));
    const b = Math.max(a, Math.min(cps.length, r[1]|0));
    if (a > pos) out += esc(cps.slice(pos, a).join(""));
    if (b > a) out += "<mark>" + esc(cps.slice(a, b).join("")) + "</mark>";
    pos = Math.max(pos, b);
  }
  if (pos < cps.length) out += esc(cps.slice(pos).join(""));
  return out;
}

/* matched_on field names → the display words the mock uses ("charter ·
   purpose, scope"). Fields not in the map show as themselves — a new registry
   field must not vanish from the explanation. */
const WS_MATCH_WORDS = { scope_in:"scope", mint_evidence:"evidence" };
function wsMatchWords(fields){
  return (fields || []).map(f => WS_MATCH_WORDS[f] || f).join(", ");
}

/* ── opening things ──────────────────────────────────────────────────────── */
/* A document opens by PATH — never by title (identity rule). The path is
   validated by the SHIPPED validator before anything else happens: a null
   from sbPageFromPath hides/aborts the affordance entirely, it never loads a
   guess (DEEPLINKS §2). opts.restore suppresses the focus hand-off (R1);
   opts.fromSearch keeps the results pane open (03 stays 03). */
async function wsOpenDoc(path, opts){
  opts = opts || {};
  if (!wsFlagOn()) return;
  if (sbPageFromPath(path) === null) return;
  S.ws.sel = { type:"doc", path: path };
  S.ws.docPath = path; S.ws.lastDocPath = path;
  S.ws.charter = null; S.ws.matched = null;
  S.ws.docGone = false; S.ws.changed = false;
  S.ws.editing = false; S.ws.unsaved = false;
  S.ws.openSeq = (S.ws.openSeq || 0) + 1;      /* open-cycle token (dual consult):
     a mount resumer from an older open must never pair its text with this one */
  S.ws.doc = null; S.ws.docMtime = null; S.ws.notice = null;
  if (!opts.fromSearch){ S.ws.results = null; S.ws.q = ""; S.ws.searchEpisode = false; }
  S.ws.focusFrameOnLoad = !opts.restore;       /* R1: explicit opens only */
  wsPing("doc_opened");
  render();
  /* The sidecar renders the content; these two calls power the crumb, the
     context rail, the mtime comparator (F3) and the Save-a-copy source (F2).
     The sidecar itself starts lazily exactly as Files does. */
  if (!(S.sb && S.sb.running)) loadFilesScreen();
  try {
    const meta = await wsGet("/api/workspace/doc?path=" + encodeURIComponent(path));
    if (S.ws.docPath !== path) return;           /* a newer open won */
    S.ws.doc = meta;
    S.ws.docMtime = meta.meta ? meta.meta.mtime : null;
  } catch (e){
    if (S.ws.docPath !== path) return;
    if (e.kind === "not_found"){ S.ws.docGone = true; }
    else if ((e.kind || "") === "engine_down"){ S.ws.treeError = { kind:"engine_down", message: e.message }; }
  }
  /* Last read copy, kept for state 14's "Save a copy" — the iframe is another
     origin, so the panel cannot recover the on-screen text from it later. A
     read that fails (binary, too large) just means Save-a-copy has no source;
     the viewer itself is unaffected. */
  try {
    const r = await apiGet("/api/fs/read?path=" + encodeURIComponent(path));
    if (S.ws.docPath === path) S.ws.lastRead = { path: path, text: r.text, editable: r.editable, bytes: r.bytes };
  } catch (e) { if (S.ws.docPath === path) S.ws.lastRead = null; }
  /* default-edit (founder 2026-08-25, dual consult): an EXPLICIT open lands in
     edit once the read copy is here. Guards: stale open, restore (boot stays
     light + Reload's documented 12->01), fromSearch (03 keeps its preview and
     its per-keystroke doc-col churn would detach a mounted editor), missing
     read copy, doc gone (14), read-only (11). UNFILED docs edit too — 87% of
     the founder's corpus is unfiled (r3 measurement), so the old exclusion
     turned the feature off; the File-it banner now rides ABOVE the editor.
     NOT via wsEdit(): that is the explicit-action path — it sets unsaved=true
     (would arm wsCheckDisk's false 12), steals focus and pings telemetry.
     unsaved stays false here; onDirty owns dirty. */
  if (S.ws.docPath === path && !opts.restore && !opts.fromSearch
      && S.ws.lastRead && !S.ws.docGone && wsEditAllowed()){
    S.ws.editing = true;
  }
  render();
}

/* A charter opens by REF (identity rule). `matched` carries the matched_on
   fields when the open came from a record result — that is what makes state
   04's context rail explainable rather than an opaque ranking. */
async function wsOpenCharter(id, matched){
  if (!wsFlagOn()) return;
  S.ws.sel = { type:"charter", id: id };
  S.ws.matched = matched || null;
  S.ws.charter = null;
  S.ws.docGone = false; S.ws.changed = false; S.ws.editing = false; S.ws.unsaved = false;
  S.ws.notice = null;
  if (matched) wsPing("record_opened");
  render();
  try {
    const r = await wsGet("/api/workspace/charter?id=" + encodeURIComponent(id));
    if (!(S.ws.sel && S.ws.sel.type === "charter" && S.ws.sel.id === id)) return;
    S.ws.charter = r;
  } catch (e){
    if (!(S.ws.sel && S.ws.sel.type === "charter" && S.ws.sel.id === id)) return;
    if ((e.kind || "") === "engine_down") S.ws.treeError = { kind:"engine_down", message: e.message };
    else S.ws.notice = e.message;
  }
  render();
}

/* ── lens (states 01 ↔ 05) ─────────────────────────────────────────────────
   Folders is a LENS over the same documents, not a second spine: it reuses
   S.fs from loadFs() — the Editor's tree — rather than fetching anything new,
   and the selection carries over (STATE-MACHINE 01→05). */
function wsSetLens(lens){
  if (lens !== "org" && lens !== "folders") return;
  if (S.ws.lens === lens) return;
  S.ws.lens = lens;
  wsPing("lens_toggled");
  if (lens === "folders") loadFs(false);
  render();
}

/* ── edit / done (states 07, 12) ────────────────────────────────────────────
   Editing happens INSIDE the sidecar — the same out-of-band gate as
   /api/fs/write (SUTRA_UI_ALLOW_EDIT); this screen only tracks the mode for
   the crumb, the Done affordance and the changed-on-disk watch. In state 11
   the Edit affordance is simply absent, so this cannot fire. */
function wsEdit(){
  if (!wsFlagOn() || !wsEditAllowed() || !S.ws.docPath) return;
  S.ws.editing = true; S.ws.unsaved = true;
  S.ws.focusFrameOnLoad = true;                /* R1: Edit is an explicit open */
  wsPing("edit_entered");
  render();
}
function wsDone(){
  if (!S.ws.editing) return;
  /* flush the native editor's buffer BEFORE leaving edit mode, then tear the
     mount down — Done means "my edits are on disk" (mock 07). */
  const h = S.ws.edHandle;
  if (h){ try { h.forceSave(); } catch (_e){} }
  wsUnmountEditor();
  S.ws.editing = false; S.ws.unsaved = false;
  /* The read view renders from lastRead — refresh it so the edit just made
     in the iframe is what the reader sees (reviewer round 2). */
  (async () => {
    try {
      const path = S.ws.sel && S.ws.sel.path;
      if (!path) return;
      const r = await apiGet("/api/fs/read?path=" + encodeURIComponent(path));
      if (S.ws.sel && S.ws.sel.path === path){
        S.ws.lastRead = { path: path, text: r.text, editable: r.editable };
        render();
      }
    } catch (_e) {}
  })();
  /* One disk check on the way out: the save happened inside the sidecar, and
     an external write during the edit deserves the banner now, not on the
     next focus. (The save-conflict 409 path itself is the sidecar's/fs-write's;
     ERROR-MODEL F3.) */
  wsCheckDisk();
  render();
}

/* Changed-on-disk detection (F3). On-focus + on-Done, deliberately NOT a
   poll: the codebase's no-retry-storm rule (ERROR-MODEL retry table) and the
   mtime is only a comparator — the authority is the 409 the write path
   already returns. Only an UNSAVED buffer earns the interrupt (07→12);
   outside editing the sidecar shows disk truth already, so the stored
   comparator just moves forward. */
async function wsCheckDisk(){
  const path = S.ws.docPath;
  if (!wsActive() || !path) return;
  try {
    const meta = await wsGet("/api/workspace/doc?path=" + encodeURIComponent(path));
    if (S.ws.docPath !== path) return;
    const m = meta.meta ? meta.meta.mtime : null;
    if (S.ws.docMtime != null && m != null && m !== S.ws.docMtime){
      if (S.ws.editing && S.ws.unsaved){ S.ws.changed = true; render(); }
      else { S.ws.docMtime = m; S.ws.doc = meta; }
    }
  } catch (e){
    if (S.ws.docPath !== path) return;
    if (e.kind === "not_found" && !S.ws.docGone){ S.ws.docGone = true; render(); }
  }
}
/* State 12 exits. Reload: buffer discarded, disk re-read (12→01) — refetch
   meta + last-read copy and reload the frame. Keep mine: buffer kept, still
   unsaved (12→07) — the next save re-checks base and can 409 again. */
function wsReload(){
  const path = S.ws.docPath;
  S.ws.changed = false; S.ws.editing = false; S.ws.unsaved = false;
  if (path) wsOpenDoc(path, { restore:true });
}
function wsKeepMine(){
  S.ws.changed = false;
  S.ws.editing = true; S.ws.unsaved = true;
  render();
}

/* ── state-13 retry ─────────────────────────────────────────────────────────
   Manual, single refire (ERROR-MODEL F1): the tree fetch AND the sidecar
   relaunch probe. No loop — Try again failing lands back in 13. */
function wsTryAgain(){
  S.ws.treeError = null; S.sbError = null;
  loadWorkspace(true);
  loadFilesScreen(true);
}

/* ── unfiled → File it (state 06, PRD U5) ───────────────────────────────────
   Routes through the EXISTING classify flow — POST /api/classify writes the
   placement with work_ref.id = the text, which is why the text sent is the
   PATH: that is the join key the tree projection matches on (MIGRATION M2).
   No auto-filing anywhere else, ever (U6). */
async function wsFileIt(){
  const path = S.ws.docPath;
  if (!wsFlagOn() || !path || S.ws.busy) return;
  S.ws.busy = "fileit"; render();
  try {
    const r = await apiPost("/api/classify", { text: path });
    if (r && r.blocked){ S.ws.notice = r.blocked; }
    else await loadWorkspace(true);              /* the next projection files it (06→01) */
  } catch (e){ S.ws.notice = e.message; }
  S.ws.busy = null; render();
}

/* ── New document (states 08/09 action; state 02 "New document here") ───────
   Creates via the existing gated /api/fs/write (403 without the env, atomic
   tmp+replace) and opens in edit (STATE-MACHINE 08→07 Decision). Hidden
   whenever the edit gate is off — an affordance that cannot work is worse
   than a missing one. */
async function wsNewDoc(){
  if (!wsFlagOn() || !wsEditAllowed() || S.ws.busy) return;
  const stamp = new Date().toISOString().slice(0,19).replace(/[T:]/g,"-");
  const path = "untitled-" + stamp + ".md";
  S.ws.busy = "newdoc"; render();
  try {
    await apiPost("/api/fs/write", { path: path, text: "" });
    await loadWorkspace(true);
    await wsOpenDoc(path, {});
    wsEdit();
  } catch (e){ S.ws.notice = e.message; }
  S.ws.busy = null; render();
}

/* ── Save a copy (state 14, F2) ─────────────────────────────────────────────
   Writes the LAST READ copy to a NEW path via the same gated write — the
   deleted file does not return (STATE-MACHINE terminality table); the copy is
   a new document that then opens. Hidden without a source or without the
   gate. */
async function wsSaveCopy(){
  const src = S.ws.lastRead;
  if (!wsFlagOn() || !wsEditAllowed() || !src || S.ws.busy) return;
  const to = src.path.replace(/\.md$/i, "") + "-copy.md";
  S.ws.busy = "savecopy"; render();
  try {
    await apiPost("/api/fs/write", { path: to, text: src.text });
    S.ws.docGone = false;
    await loadWorkspace(true);
    await wsOpenDoc(to, {});
  } catch (e){ S.ws.notice = e.message; }
  S.ws.busy = null; render();
}

/* ── deep links (DEEPLINKS.md) ───────────────────────────────────────────────
   Grammar: workspace[?dept=..&charter=..&doc=..]. Precedence doc > charter >
   dept; values decoded exactly once; unknown params ignored; invalid values
   fall back to resting + a notice — never a crash, never a guessed URL.
   Client validation is a COURTESY (the shipped sbPageFromPath rules); the
   server re-validates independently through resolve. */
function wsParseRoute(route){
  const out = { dept:null, charter:null, doc:null, bad:null };
  if (typeof route !== "string" || !/^workspace(\?|$)/.test(route)){ out.bad = "not a workspace route"; return out; }
  const qs = route.indexOf("?") === -1 ? "" : route.slice(route.indexOf("?") + 1);
  for (const pair of qs.split("&")){
    if (!pair) continue;
    const eq = pair.indexOf("=");
    const k = eq === -1 ? pair : pair.slice(0, eq);
    let v = eq === -1 ? "" : pair.slice(eq + 1);
    try { v = decodeURIComponent(v); } catch (e){ out.bad = "bad encoding in " + k; continue; }
    if (k === "doc"){
      if (sbPageFromPath(v) === null) out.bad = "doc is not a plain relative .md path";
      else out.doc = v;
    }
    else if (k === "charter"){
      if (/^C-[0-9a-f]+$/i.test(v)) out.charter = v;
      else out.bad = "charter id has the wrong shape";
    }
    else if (k === "dept") out.dept = v;   /* existence is the registry's call, via resolve */
    /* unknown params: ignored, forward-compatible, never an error */
  }
  return out;
}
async function wsHandleRoute(route){
  if (!wsFlagOn()) return;
  const p = wsParseRoute(route);
  if (p.bad && !p.doc && !p.charter && !p.dept){
    S.ws.notice = p.bad; render(); return;
  }
  try {
    const r = await wsGet("/api/workspace/resolve?link=" + encodeURIComponent(route));
    if (r.doc) wsOpenDoc(r.doc, {});
    else if (r.charter) wsOpenCharter(r.charter, null);
    else if (r.dept){ S.ws.cursor = wsCursorForDept(r.dept); render(); }
    else render();
  } catch (e){
    /* Typed reject → resting + notice (DEEPLINKS §1 invalid-values rule). */
    S.ws.notice = e.message; render();
  }
}
function wsCursorForDept(ref){
  const rows = wsVisibleRows();
  const i = rows.findIndex(r => r.type === "dept" && r.key === ref);
  return i === -1 ? null : { mode:"tree", i: i };
}

/* ── keyboard (A11Y.md §1) ───────────────────────────────────────────────────
   The tree has no chevrons and no collapse, so arrows are pure traversal over
   the FLAT visual order — dept, charter, doc, Unfiled. In search, one list:
   documents group then records group. The row list is computed, not scraped
   from the DOM, so the same function drives rendering, traversal and tests. */
function wsVisibleRows(){
  const w = S.ws;
  if (w.results){
    const g = wsGroupResults(w.results);
    return g.docs.map(d => ({ type:"sdoc", key:d.path }))
      .concat(g.records.map(r => ({ type:"rec", key:r.ref, kind:r.kind })));
  }
  const rows = [];
  if (w.lens === "folders"){
    ((S.fs && S.fs.files) || []).forEach(f => {
      if (/\.md$/i.test(f.path)) rows.push({ type:"fold", key:f.path });
    });
    return rows;
  }
  const t = w.tree || {};
  /* Mirrors wsTreeHtml's collapse EXACTLY — the cursor must never land on a
     row the renderer did not draw (codex review 2026-08-25, finding 5). */
  const vis = wsActivePath(t);
  (t.departments || []).forEach(d => {
    rows.push({ type:"dept", key:d.ref });
    if (!vis.depOpen(d.ref)) return;
    (d.charters || []).forEach(c => {
      rows.push({ type:"charter", key:c.id });
      if (c.id !== vis.activeCh) return;
      (c.docs || []).forEach(x => rows.push({ type:"doc", key:x.path, gone:!!x.missing }));
    });
  });
  if ((t.unfiled || []).length){
    rows.push({ type:"dept", key:"__unfiled__" });
    if (vis.unfiledOpen) (t.unfiled || []).forEach(x => rows.push({ type:"doc", key:x.path }));
  }
  return rows;
}
/* One predicate, two consumers (renderer + cursor): the active path and the
   expansion rules live here so they cannot drift apart. First match binds
   BOTH dept and charter (codex finding 6: a doc under two charters must not
   split the pair). */
function wsActivePath(t){
  const selPath = S.ws.sel && S.ws.sel.type === "doc" ? S.ws.sel.path : null;
  const selCh = S.ws.sel && S.ws.sel.type === "charter" ? S.ws.sel.id : null;
  if (!S.ws.openDeps) S.ws.openDeps = {};
  let activeDep = null, activeCh = selCh;
  outer:
  for (const d of (t.departments || [])){
    for (const c of (d.charters || [])){
      if ((selCh && c.id === selCh)
          || (selPath && (c.docs || []).some(x => x.path === selPath))){
        activeDep = d.ref;
        if (!activeCh) activeCh = c.id;
        break outer;
      }
    }
  }
  const unfiledOpen = !!S.ws.openDeps["__unfiled__"]
    || ("__unfiled__" in S.ws.openDeps ? !!S.ws.openDeps["__unfiled__"]
        : !!(selPath && (t.unfiled || []).some(x => x.path === selPath)));
  return {
    activeDep, activeCh, unfiledOpen,
    depOpen: ref => (ref in S.ws.openDeps) ? !!S.ws.openDeps[ref] : ref === activeDep,
  };
}
function wsMoveCursor(delta){
  const rows = wsVisibleRows();
  if (!rows.length) return;
  const mode = S.ws.results ? "res" : "tree";
  let i = (S.ws.cursor && S.ws.cursor.mode === mode) ? S.ws.cursor.i + delta
        : (delta > 0 ? 0 : rows.length - 1);
  i = Math.max(0, Math.min(rows.length - 1, i));
  S.ws.cursor = { mode: mode, i: i };
  render();
}
function wsActivateRow(row){
  if (!row) return;
  if (row.type === "doc" || row.type === "fold" || row.type === "sdoc")
    wsOpenDoc(row.key, { fromSearch: row.type === "sdoc" });
  else if (row.type === "charter") wsOpenCharter(row.key, null);
  else if (row.type === "rec"){
    if (row.kind === "department"){
      /* Departments have no page in the 14 states; scroll-to is the tree's
         job — jump the cursor there and close nothing. */
      S.ws.cursor = wsCursorForDept(row.key); render();
    } else {
      const rec = ((S.ws.results || {}).records || []).find(r => r.ref === row.key);
      wsOpenCharter(row.key, rec ? rec.matched_on : null);
    }
  }
  else if (row.type === "more"){
    /* Lift the cap for this charter (or Unfiled) — one at a time keeps the
       tree honest about its size without a modal or a second lens. */
    S.ws.showAllDocs = row.key; render();
  }
  else if (row.type === "dept"){
    /* A department row is its own toggle (founder 2026-08-25): departments
       have no page, so activate = expand/collapse. Reached from a search
       RESULT (codex finding 8), the search clears first so the toggled dept
       is actually on screen. The shared predicate supplies current state. */
    if (S.ws.results){ S.ws.results = null; S.ws.q = ""; }
    if (!S.ws.openDeps) S.ws.openDeps = {};
    const openNow = wsActivePath(S.ws.tree || {}).depOpen(row.key);
    S.ws.openDeps[row.key] = !openNow;
    render();
  }
}
/* Named (not inline) so tests can drive keys without a DOM event pipeline. */
function wsKeydown(e){
  if (!wsActive()) return;
  const inSearch = !!(e.target && e.target.closest && e.target.closest("[data-wssearch]"));
  const inTyping = !inSearch && e.target &&
    /^(INPUT|TEXTAREA)$/.test((e.target.tagName || "")) === true;
  if ((e.metaKey || e.ctrlKey) && (e.key === "f" || e.key === "F")){
    /* Cmd-F focuses search from anywhere in Workspace. While the IFRAME owns
       focus this DOM listener never sees the key — that hand-off is the
       Electron before-input-event registration (A11Y R2, integrator S70);
       this branch covers every panel-owned surface. */
    e.preventDefault();
    const el = document.querySelector("[data-wssearch]");
    if (el) el.focus();
    return;
  }
  if (inTyping) return;                          /* other inputs keep their keys */
  if (e.key === "Escape"){
    if (S.ws.results || S.ws.q){
      e.preventDefault();
      /* Esc from a record view closes search and keeps the charter page
         (04→02); otherwise the centre keeps the last doc (03/09→01). Focus
         returns to the tree's prior selection. */
      S.ws.q = ""; S.ws.results = null; S.ws.searchEpisode = false;
      if (!(S.ws.sel && S.ws.sel.type === "charter")) S.ws.matched = null;
      S.ws.cursor = null;
      render();
      const sel = document.querySelector(".ws-side [data-wsfocus]");
      if (sel) sel.focus();
    }
    return;                                      /* Esc in the tree: no-op */
  }
  if (e.key === "ArrowDown"){ e.preventDefault(); wsMoveCursor(1); return; }
  if (e.key === "ArrowUp"){ e.preventDefault(); wsMoveCursor(-1); return; }
  if (e.key === "Enter" && !inSearch){
    const rows = wsVisibleRows();
    const cur = S.ws.cursor && rows[S.ws.cursor.i];
    if (cur){ e.preventDefault(); wsActivateRow(cur); }
    return;
  }
  if (e.key === "Enter" && inSearch){
    if (!S.ws.results) return;      /* nothing offered yet — Enter opens nothing */
    /* Enter in the search field opens the cursor row (or the first row when
       none is picked yet) — documents group first, so first-hit-wins is the
       document ordering the contract promises. */
    const rows = wsVisibleRows();
    const cur = (S.ws.cursor && rows[S.ws.cursor.i]) || rows[0];
    if (cur){ e.preventDefault(); wsActivateRow(cur); }
  }
}

/* ── rendering ─────────────────────────────────────────────────────────────
   All chrome strings from WS_COPY; all data through esc(); tree levels are
   the classes ws-dep / ws-cha / ws-doc told by weight and indent (DESIGN-LOCK
   redline-tree); Unfiled sits below a rule. workspace.css (S13, css agent)
   owns every visual value — nothing here styles inline. */
function wsRelTime(mtime){
  if (!mtime) return "";
  const ms = mtime * 1000, diff = Date.now() - ms;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return Math.max(1, Math.round(diff/60000)) + "m ago";
  const d = new Date(ms), now = new Date();
  if (d.toDateString() === now.toDateString()) return "today";
  const opts = d.getFullYear() === now.getFullYear()
    ? { month:"short", day:"numeric" } : { year:"numeric", month:"short", day:"numeric" };
  return d.toLocaleDateString("en-US", opts);
}
/* The mock abbreviates large counts ("1.2k"); the API contract allows it. */
function wsCount(n){
  if (typeof n !== "number") return "";
  return n >= 1000 ? (Math.round(n/100)/10) + "k" : String(n);
}
/* The cursor row, computed ONCE per render pass and read per row: calling
   wsVisibleRows() inside wsRowAttrs would be O(rows²) — 16M comparisons at
   the tree's 4000-row cap, against a <100ms first-paint budget (ARCH.md). */
let _wsCursorRow = null;
function wsSyncCursorRow(){
  _wsCursorRow = S.ws.cursor ? (wsVisibleRows()[S.ws.cursor.i] || null) : null;
}
function wsRowAttrs(type, key){
  const focused = _wsCursorRow && _wsCursorRow.type === type && _wsCursorRow.key === key;
  return 'data-wstype="' + esc(type) + '" data-wskey="' + esc(key) + '"'
    + (focused ? ' data-wsfocus tabindex="0"' : ' tabindex="-1"');
}
function wsTreeHtml(){
  const t = S.ws.tree || {};
  const selPath = S.ws.sel && S.ws.sel.type === "doc" ? S.ws.sel.path : null;
  const selCh = S.ws.sel && S.ws.sel.type === "charter" ? S.ws.sel.id : null;
  /* Collapse-by-default (founder 2026-08-25, mock 01): only the ACTIVE path
     expands — the department holding the selection, and docs only under the
     selected charter (or the one holding the selected doc). Everything else
     is one row with a count; the dept row itself is the toggle. The predicate
     is shared with wsVisibleRows (wsActivePath) so cursor and pixels agree. */
  const vis = wsActivePath(t);
  const depOpen = vis.depOpen, activeCh = vis.activeCh;
  let html = "";
  (t.departments || []).forEach(d => {
    const open = depOpen(d.ref);
    html += '<button type="button" class="ws-dep' + (open ? " open" : "")
      + (!d.count ? " ws-quiet" : "") + '" '
      + wsRowAttrs("dept", d.ref) + '>'
      + esc(d.name) + '<span class="ws-count">' + esc(wsCount(d.count)) + '</span></button>';
    if (!open) return;
    (d.charters || []).forEach(c => {
      html += '<button type="button" class="ws-cha' + (selCh === c.id ? " on" : "") + '" '
        + wsRowAttrs("charter", c.id) + '>' + esc(c.title) + '</button>';
      if (c.id !== activeCh) return;
      /* Cap the expansion (reviewer 2026-08-25 finding 4): a 100-doc charter
         must not push the other departments off screen. The selected doc is
         always drawn; showAllDocs (per charter, session-scoped) lifts the cap. */
      const cap = 14;
      const docs = c.docs || [];
      const showAll = S.ws.showAllDocs === c.id || docs.length <= cap;
      let drawn = 0;
      docs.forEach(x => {
        const isSel = selPath === x.path;
        if (!showAll && drawn >= cap && !isSel) return;
        drawn++;
        html += '<button type="button" class="ws-doc'
          + (x.missing ? " gone" : "") + (isSel ? " on" : "") + '" '
          /* full path as tooltip (visual audit r3): ellipsized twins like two
             "Changelog" rows are otherwise indistinguishable */
          + 'title="' + esc(x.path) + '" '
          + wsRowAttrs("doc", x.path) + '>' + esc(x.title) + '</button>';
      });
      if (!showAll && docs.length > drawn){
        html += '<button type="button" class="ws-doc ws-more" '
          + wsRowAttrs("more", c.id) + '>\u2026 ' + (docs.length - drawn)
          + ' more</button>';
      }
    });
  });
  if ((t.unfiled || []).length){
    const uOpen = vis.unfiledOpen;
    html += '<hr class="ws-rule">'
      + '<button type="button" class="ws-dep ws-unfiled' + (uOpen ? " open" : "") + '" '
      + wsRowAttrs("dept", "__unfiled__") + '>'
      + WS_COPY.unfiled + '<span class="ws-count">' + esc(wsCount((t.unfiled || []).length)) + '</span></button>';
    if (uOpen){
      const cap = 14, docs = t.unfiled || [];
      const showAll = S.ws.showAllDocs === "__unfiled__" || docs.length <= cap;
      let drawn = 0;
      docs.forEach(x => {
        const isSel = selPath === x.path;
        if (!showAll && drawn >= cap && !isSel) return;
        drawn++;
        html += '<button type="button" class="ws-doc ws-und'
          + (isSel ? " on" : "") + '" '
          + 'title="' + esc(x.path) + '" '
          + wsRowAttrs("doc", x.path) + '>' + esc(x.title) + '</button>';
      });
      if (!showAll && docs.length > drawn){
        html += '<button type="button" class="ws-doc ws-und ws-more" '
          + wsRowAttrs("more", "__unfiled__") + '>\u2026 ' + (docs.length - drawn)
          + ' more</button>';
      }
    }
  }
  return html || '<div class="ws-none"></div>';
}
/* Folders lens (state 05): the same documents by path, straight off S.fs —
   the Editor's tree — with directory headers derived from the paths. A lens,
   not a spine: doc rows behave exactly as in 01. */
function wsFoldersHtml(){
  const files = ((S.fs && S.fs.files) || []).filter(f => /\.md$/i.test(f.path));
  const selPath = S.ws.sel && S.ws.sel.type === "doc" ? S.ws.sel.path : null;
  let html = "", lastDir = null;
  files.slice().sort((a,b)=> a.path < b.path ? -1 : 1).forEach(f => {
    const cut = f.path.lastIndexOf("/");
    const dir = cut === -1 ? "" : f.path.slice(0, cut);
    const name = cut === -1 ? f.path : f.path.slice(cut + 1);
    if (dir !== lastDir){
      lastDir = dir;
      if (dir) html += '<div class="ws-fold ws-fold-dir">' + esc(dir) + '</div>';
    }
    html += '<button type="button" class="ws-fold' + (dir ? " i1" : "")
      + (selPath === f.path ? " on" : "") + '" '
      + wsRowAttrs("fold", f.path) + '>' + esc(name) + '</button>';
  });
  return html || '<div class="ws-none"></div>';
}
function wsSearchingHtml(){
  /* In-flight search (reviewer blocker 1): one quiet line, not a spinner —
     the mock's restraint applies to waiting too. */
  return '<div class="ws-searching">' + WS_COPY.searching + '</div>';
}
function wsResultsHtml(){
  const g = wsGroupResults(S.ws.results);
  let html = "";
  g.docs.forEach(d => {
    const f = d.filing || {};
    const loc = (f.department == null && f.charter == null)
      ? WS_COPY.unfiled
      : [f.department, f.charter].filter(Boolean).join(" \u00b7 ");
    html += '<button type="button" class="ws-doc ws-hit" ' + wsRowAttrs("sdoc", d.path) + '>'
      + esc(d.title)
      + '<span class="ws-s ws-loc">' + esc(loc) + '</span>'
      + (d.snippet ? '<span class="ws-s ws-snip">'
          + wsMarkSnippet(d.snippet.text, d.snippet.ranges) + '</span>' : "")
      + '</button>';
  });
  if (g.records.length){
    html += '<div class="ws-grp">' + WS_COPY.recGroup + '</div>';
    g.records.forEach(r => {
      html += '<button type="button" class="ws-rec" data-wskind="' + esc(r.kind) + '" '
        + wsRowAttrs("rec", r.ref) + '>' + esc(r.title)
        + '<span class="ws-s">' + esc(r.kind) + ' · ' + esc(wsMatchWords(r.matched_on)) + '</span>'
        + '</button>';
    });
  }
  return html || '<div class="ws-none"></div>';
}
function wsSkelHtml(n){
  let html = '<div class="ws-skel-wrap" aria-busy="true">';
  for (let i = 0; i < (n || 5); i++) html += '<div class="ws-skel"></div>';
  return html + '</div>';
}
function wsEmptyHtml(msg, actionLabel, act){
  return '<div class="ws-empty"><p>' + esc(msg) + '</p>'
    + (actionLabel
        ? '<button type="button" class="ws-act gold" data-wsact="' + esc(act) + '">'
          + esc(actionLabel) + '</button>' : "")
    + '</div>';
}
function wsNoticeHtml(kind, msg, actions){
  return '<div class="ws-notice' + (kind === "alert" ? " alert" : "") + '" role="status" aria-live="polite">'
    + esc(msg)
    + (actions || []).map(a =>
        '<button type="button" class="ws-act ' + (a.gold ? "gold" : "stone") + '" data-wsact="'
        + esc(a.act) + '">' + esc(a.label) + '</button>').join("")
    + '</div>';
}
function wsCharterPageHtml(){
  const c = S.ws.charter;
  if (!c) return wsSkelHtml(6);
  const ch = c.charter || {};
  /* Breadcrumb above the serif title (mock 02; reviewer round-2 minor 6):
     the department comes from the tree join when this charter is in it. */
  let crumbDept = null;
  ((S.ws.tree || {}).departments || []).forEach(d =>
    (d.charters || []).forEach(x => { if (x.id === ch.id) crumbDept = d.name; }));
  return '<div class="ws-page">'
    + (crumbDept ? '<div class="ws-crumb">' + esc(crumbDept) + ' \u00b7 ' + esc(ch.title) + '</div>' : "")
    + '<h1>' + esc(ch.title) + '</h1>'
    + (ch.purpose ? '<p class="ws-desc">' + esc(ch.purpose) + '</p>' : "")
    + '<div class="ws-chlist">'
    + (c.docs || []).map(d =>
        '<button type="button" class="ws-chrow" data-wstype="doc" data-wskey="' + esc(d.path) + '">'
        + esc(d.title) + '<span class="ws-chdate">' + esc(wsRelTime(d.mtime)) + '</span></button>').join("")
    + '</div>'
    + (wsEditAllowed()
        ? '<button type="button" class="ws-act gold" data-wsact="newdochere">'
          + WS_COPY.newDocHere + '</button>' : "")
    + '</div>';
}
function wsCtxHtml(state){
  const w = S.ws;
  if (state === "10") return wsSkelHtml(4);
  const row = (k, v) => '<div class="ws-cr"><span class="ws-ck">' + esc(k)
    + '</span><span class="ws-cv">' + v + '</span></div>';
  /* Charter page rail (02/04): the record's own facts; 04 adds the matched
     fields — the explanation of why search offered it. */
  if (w.sel && w.sel.type === "charter"){
    const ch = (w.charter && w.charter.charter) || {};
    let html = '<div class="ws-cs"><div class="ws-ck ws-cshead">' + WS_COPY.ckCharter + '</div>'
      + row("department", esc(ch.department ? ch.department.name : ""))
      + row("address", esc(ch.address || ""))
      + row("status", esc(ch.status || ""))
      + row("documents", esc(w.charter ? String(w.charter.doc_count) : ""));
    if (w.matched) html += row("matched", esc(wsMatchWords(w.matched)));
    return html + '</div>';
  }
  if (w.sel && w.sel.type === "doc"){
    const meta = w.doc || {};
    const f = meta.filing || {};
    const unfiledVal = (state === "12") ? WS_COPY.filingNotFiled : WS_COPY.filingNone;
    if (!f.department && !f.charter){
      /* FILING rail for an unfiled doc (06) / unfiled-while-editing (12). */
      return '<div class="ws-cs"><div class="ws-ck ws-cshead">' + WS_COPY.ckFiling + '</div>'
        + row("department", esc(unfiledVal))
        + row("charter", esc(unfiledVal))
        + '</div>';
    }
    let html = '<div class="ws-cs"><div class="ws-ck ws-cshead">' + WS_COPY.ckCharter + '</div>'
      + row("department", esc(f.department ? f.department.name : ""))
      + row("charter", esc(f.charter ? f.charter.title : ""))
      + row(S.ws.editing ? "saved" : "updated",
            esc(S.ws.editing && S.ws.unsaved ? "unsaved"
                : wsRelTime(meta.meta ? meta.meta.mtime : null)));
      /* mock-07: while EDITING the row reads "saved <ago>" / "unsaved" —
         reviewer editor-round-1 minor 2; reading keeps "updated". */
    if (state === "07" && meta.meta && meta.meta.words != null)
      html += row("words", esc(String(meta.meta.words)));
    html += '</div>';
    if ((meta.linked_from || []).length){
      html += '<div class="ws-cs"><div class="ws-ck ws-cshead">' + WS_COPY.ckLinked + '</div>'
        + meta.linked_from.map(l =>
            '<button type="button" class="ws-cl" data-wstype="doc" data-wskey="' + esc(l.path)
            + '">' + esc(l.title) + '</button>').join("")
        + '</div>';
    }
    return html;
  }
  return "";
}
function wsCrumbHtml(state){
  const w = S.ws;
  const meta = w.doc || {};
  const f = meta.filing || {};
  const parts = [];
  if (f.department) parts.push(esc(f.department.name));
  if (f.charter) parts.push(esc(f.charter.title));
  if (!parts.length && w.sel && w.sel.type === "doc") parts.push(esc(WS_COPY.unfiled));
  if ((state === "07" || state === "12") && w.unsaved) parts.push(esc(WS_COPY.unsaved));
  return parts.length ? '<div class="ws-crumb">' + parts.join(" · ") + '</div>' : "";
}
/* The document column per state. The iframe carries NO src attribute in the
   markup — wireWorkspace() assigns it as a property from sbUrl() only, the
   wire() pattern the Files screen established. */
/* ── read-state markdown renderer (reviewer round 2, blocker 1) ──────────────
   The READ state is the PANEL's (mock 02/03): serif title, themed body — the
   SilverBullet iframe appears only in EDIT (mock 07). Escape-first by
   construction: every piece of source text passes esc() BEFORE any tag is
   assembled, so no author-controlled byte reaches the DOM as markup. Links
   render only for http(s) targets. Deliberately conservative — headings,
   emphasis, code, lists, quotes, tables, rules — anything else stays plain
   escaped text rather than half-rendered risk. */
function wsMdInline(t){
  let x = esc(t);
  x = x.replace(/`([^`]+)`/g, "<code>$1</code>");
  x = x.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  x = x.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
  /* _underscore_ emphasis (visual audit r3): word-boundary guarded so
     snake_case identifiers never italicize. */
  x = x.replace(/(^|[\s(])_([^_\s](?:[^_]*[^_\s])?)_(?![A-Za-z0-9_])/g, "$1<em>$2</em>");
  x = x.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  x = x.replace(/\[\[([^\]]+)\]\]/g, '<span class="ws-wikilink">$1</span>');
  return x;
}
function wsMdHtml(text){
  const lines = String(text || "").split(/\r?\n/);
  let html = "", i = 0, para = [];
  const flush = () => {
    if (para.length){ html += "<p>" + para.map(wsMdInline).join("<br>") + "</p>"; para = []; }
  };
  while (i < lines.length){
    const ln = lines[i];
    if (/^```/.test(ln)){
      flush();
      const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      html += "<pre><code>" + esc(buf.join("\n")) + "</code></pre>";
      continue;
    }
    const h = ln.match(/^(#{1,6})\s+(.*)$/);
    if (h){ flush(); const lv = Math.min(h[1].length, 4);
      html += "<h" + lv + ">" + wsMdInline(h[2]) + "</h" + lv + ">"; i++; continue; }
    if (/^\s*([-*+]|\d+\.)\s+/.test(ln)){
      flush();
      const items = []; const ordered = /^\s*\d+\./.test(ln);
      while (i < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[i])){
        let it = lines[i].replace(/^\s*([-*+]|\d+\.)\s+/, "");
        it = it.replace(/^\[ \]\s*/, "\u25a1 ").replace(/^\[x\]\s*/i, "\u25a3 ");
        i++;
        /* lazy continuation (CommonMark; visual audit r3): a wrapped line
           belongs to its bullet \u2014 before this, it fell out of the list and
           restarted flush-left mid-sentence. A blank line or any new block
           marker still ends the item. */
        while (i < lines.length && lines[i].trim()
               && !/^\s*([-*+]|\d+\.)\s+/.test(lines[i])
               && !/^(#{1,6})\s+|^```|^\s*>|^\s*\|.*\|\s*$|^\s*(---+|\*\*\*+)\s*$/.test(lines[i])){
          it += " " + lines[i].trim(); i++;
        }
        items.push("<li>" + wsMdInline(it) + "</li>");
      }
      html += (ordered ? "<ol>" : "<ul>") + items.join("") + (ordered ? "</ol>" : "</ul>");
      continue;
    }
    if (/^\s*&gt;|^\s*>/.test(ln)){
      flush();
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      html += "<blockquote>" + buf.map(wsMdInline).join("<br>") + "</blockquote>";
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(ln)){
      flush();
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(lines[i++]);
      const cells = r => r.replace(/^\s*\||\|\s*$/g, "").split("|").map(c => wsMdInline(c.trim()));
      let t = "<table>";
      rows.forEach((r, ri) => {
        if (/^\s*\|[\s:|-]+\|\s*$/.test(r)) return;      /* separator row */
        const tag = ri === 0 ? "th" : "td";
        t += "<tr><" + tag + ">" + cells(r).join("</" + tag + "><" + tag + ">") + "</" + tag + "></tr>";
      });
      html += t + "</table>";
      continue;
    }
    if (/^\s*(---+|\*\*\*+)\s*$/.test(ln)){ flush(); html += "<hr>"; i++; continue; }
    if (!ln.trim()){ flush(); i++; continue; }
    para.push(ln); i++;
  }
  flush();
  return html;
}
/* Title strategy: a leading H1 IS the document's title (mock renders it once,
   serif); otherwise the registry title from the selection row. */
function wsReadView(){
  const w = S.ws;
  if (!w.lastRead || w.lastRead.path !== (w.sel && w.sel.path))
    return '<div class="ws-read">' + wsSkelHtml(6) + '</div>';
  let text = w.lastRead.text || "";
  let title = null;
  const m = text.match(/^\s*#\s+(.+)\r?\n/);
  if (m){ title = m[1]; text = text.slice(m.index + m[0].length); }
  if (!title){
    const docs = wsAllDocs(w.tree || {});
    const row = docs.find(d => d.path === w.sel.path);
    title = (row && row.title) || w.sel.path.split("/").pop();
  }
  return '<div class="ws-read"><h1 class="ws-doctitle">' + esc(title) + "</h1>"
    + '<div class="ws-mdbody">' + wsMdHtml(text) + "</div></div>";
}
/* ── native editor lifecycle (PLAN-25-EDITOR S10-S14) ────────────────────────
   The vendored bundle (static/vendor/sutra-editor.js, sha-pinned in
   VENDOR-MANIFEST.md) loads LAZILY on first edit — boot stays light. The
   handle lives on S.ws.edHandle; save goes through /api/fs/write with the
   base bytes captured at read (the same 409 conflict lane the plain editor
   uses); a 409 raises state 12 and autosave pauses (consult contract). */
let _wsEditorScript = null;
function wsLoadEditorScript(){
  if (window.SutraEditor) return Promise.resolve();
  if (_wsEditorScript) return _wsEditorScript;
  _wsEditorScript = new Promise((resolve, reject) => {
    const sc = document.createElement("script");
    sc.src = "/static/vendor/sutra-editor.js";
    sc.onload = () => resolve();
    sc.onerror = () => { _wsEditorScript = null; reject(new Error("editor bundle failed to load")); };
    document.head.appendChild(sc);
  });
  return _wsEditorScript;
}
async function wsMountEditor(el){
  const w = S.ws;
  if (!w.sel || w.sel.type !== "doc" || !w.lastRead || w.lastRead.path !== w.sel.path) return;
  const seq = w.openSeq;                           /* this open cycle (dual consult) */
  try { await wsLoadEditorScript(); }
  catch (e){
    /* fall back to READ view (deepseek): editing with no editor is state 07
       showing an empty column — a lie. The notice says why. */
    w.notice = String(e.message || e); w.editing = false; render(); return;
  }
  if (!S.ws.editing || S.ws.edHandle) return;      /* state moved on while loading */
  /* STATE re-check after the await, mirroring the entry predicate (dual
     consult): the DOM re-query below covers container death but not a
     mid-flight second open — sel can be doc B while lastRead is still doc A,
     and mounting would save A's text under B's path. The seq token also
     catches A->B->A round-trips faster than the script load. */
  if (S.ws.openSeq !== seq) return;
  if (!S.ws.sel || S.ws.sel.type !== "doc" || !S.ws.lastRead
      || S.ws.lastRead.path !== S.ws.sel.path) return;
  /* THE CONTAINER MAY BE DEAD: any render() during the (possibly 1.3MB) script
     load replaced scBody's DOM, so the element we were handed can be detached
     — the editor then mounts invisibly into an orphan (reviewer blocker,
     editor round 1: flat-white light edit). Always re-query the LIVE one. */
  const live = document.querySelector("#scBody [data-wseditor]");
  if (live) el = live;
  else if (el && el.isConnected === false) return;  /* nowhere real to mount */
  const path = w.sel.path;
  const docs = wsAllDocs(w.tree || {});
  const row = docs.find(d => d.path === path);
  S.ws.edHandle = window.SutraEditor.mount({
    parent: el,
    path: path,
    title: (row && row.title) || path.split("/").pop(),
    text: w.lastRead.text || "",
    readOnly: !wsEditAllowed(),
    dark: (function(){
      const r = document.documentElement;
      const t = r && r.getAttribute ? r.getAttribute("data-theme") : null;
      if (t) return t === "dark";
      return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    })(),
    save: async (text) => {
      const r = await apiPost("/api/fs/write",
        { path: path, text: text, base_bytes: S.ws.lastRead ? S.ws.lastRead.bytes : null });
      S.ws.lastRead = { path: path, text: text, editable: true, bytes: r.bytes };
      S.ws.changed = false;
    },
    onDirty: (d) => { S.ws.unsaved = d; wsRenderCtxOnly(); },
    onSaveState: (st) => {
      if (st === "failed"){ S.ws.changed = true; render(); }   /* state 12 lane */
      else wsRenderCtxOnly();
    },
    navigate: (ref) => { const p = wsParseRoute(ref); if (p && p.doc) wsOpenDoc(p.doc); },
    flash: (m) => { S.ws.notice = m; render(); },
  });
}
function wsUnmountEditor(){
  if (S.ws.edHandle){ try { S.ws.edHandle.destroy(); } catch (_e){} S.ws.edHandle = null; }
}
function wsRenderCtxOnly(){
  const ctx = document.querySelector("#scBody .ws-ctx");
  if (ctx) ctx.innerHTML = wsCtxHtml(wsCurrentState());
}
function wsDocColHtml(state){
  const w = S.ws;
  if (state === "10") return wsSkelHtml(8);
  if (state === "13")
    return wsEmptyHtml(WS_COPY.engineDown, WS_COPY.tryAgain, "tryagain");
  if (state === "08")
    return wsEmptyHtml(WS_COPY.emptyMsg, wsEditAllowed() ? WS_COPY.newDoc : null, "newdoc");
  if (state === "09")
    return wsEmptyHtml(WS_COPY.noResults, wsEditAllowed() ? WS_COPY.newDoc : null, "newdoc");
  if ((state === "02" || state === "04") ) return wsCharterPageHtml();
  let html = "";
  if (w.notice) html += wsNoticeHtml("info", w.notice, []);
  if (state === "14")
    html += wsNoticeHtml("info", WS_COPY.docGone,
      (wsEditAllowed() && w.lastRead) ? [{ act:"savecopy", label:WS_COPY.saveCopy, gold:true }] : []);
  if (state === "12")
    html += wsNoticeHtml("alert", WS_COPY.changedNotice,
      [{ act:"reload", label:WS_COPY.reload, gold:true },
       { act:"keepmine", label:WS_COPY.keepMine }]);
  /* File-it also rides above the EDITOR: unfiled docs default-edit now
     (state 07 wins the resolver), and filing must stay one click (r3). */
  if (state === "06"
      || (state === "07" && w.sel && w.sel.type === "doc" && wsDocIsUnfiled(w.sel.path)))
    html += wsNoticeHtml("info", WS_COPY.unfiledNotice,
      wsEditAllowed() ? [{ act:"fileit", label:WS_COPY.fileIt, gold:true }] : []);
  html += wsCrumbHtml(state);
  if (w.sel && w.sel.type === "doc"){
    /* READ is the panel's own rendered view (mock 02/03). EDITING mounts the
       NATIVE editor — SilverBullet's forked editor core in a plain div
       (PLAN-25-EDITOR S11); the iframe is gone (S14). */
    if (S.ws.editing)
      html += '<div class="ws-editor" data-wseditor></div>';
    else
      html += wsReadView();
  }
  return html;
}
/* Top-right cluster, shared by the full render AND the search's side-only
   render — reviewer round 3, minor 1: the Edit->count swap claimed in
   2.222.9 never fired on the search path because only wsScreenHtml built
   this markup. One builder, two callers, no drift. */
function wsTopRightHtml(state, g){
  return '<span class="ws-topright">'
    + (g ? '<span class="ws-rescount">' + g.total + '</span>' : "")
    + (state === "13" ? '<span class="ws-chip alert"><i class="ws-dot"></i>' + WS_COPY.offline + '</span>' : "")
    + (!wsEditAllowed() && state !== "13" ? '<span class="ws-chip">' + WS_COPY.readOnly + '</span>' : "")
    + (S.ws.editing
        ? '<button type="button" class="ws-act gold" data-wsact="done">' + WS_COPY.done + '</button>'
        : (wsEditAllowed() && !g && S.ws.sel && S.ws.sel.type === "doc" && !S.ws.docGone && state !== "13"
            ? '<button type="button" class="ws-act" data-wsact="edit">' + WS_COPY.edit + '</button>' : ""))
    + '</span>';
}
/* The search + action cluster live in the browse pane's OWN header row (.ph)
   — 06-render.js asks for this when S.screen === "workspace". One header, no
   second band: the .ws-top rectangle is gone (founder 2026-08-25, r3). */
function wsPaneHeadHtml(){
  if (!wsFlagOn()) return "";
  const state = wsCurrentState();
  const g = S.ws.results ? wsGroupResults(S.ws.results) : null;
  return '<input class="ws-search" data-wssearch placeholder="' + WS_COPY.search + '"'
    + ' value="' + esc(S.ws.q) + '" aria-label="' + WS_COPY.search + '">'
    + wsTopRightHtml(state, g);
}
function wsScreenHtml(){
  const state = wsCurrentState();
  wsSyncCursorRow();
  const lens =
    '<div class="ws-lens" role="tablist">'
    + '<button type="button" data-wslens="org" aria-selected="' + (S.ws.lens === "org") + '">'
    + WS_COPY.lensOrg + '</button>'
    + '<button type="button" data-wslens="folders" aria-selected="' + (S.ws.lens === "folders") + '">'
    + WS_COPY.lensFolders + '</button></div>';
  let side;
  if (state === "10") side = wsSkelHtml(9);
  else if (S.ws.searching && !S.ws.results) side = wsSearchingHtml();
  else if (S.ws.results) side = wsResultsHtml();
  else side = lens + (S.ws.lens === "folders" ? wsFoldersHtml() : wsTreeHtml());
  return '<div class="ws">'
    + '<div class="ws-panes">'
    + '<div class="ws-side" role="tree">' + side + '</div>'
    + '<div class="ws-doccol"><div class="ws-col">' + wsDocColHtml(state) + '</div></div>'
    + '<div class="ws-ctx">' + wsCtxHtml(state) + '</div>'
    + '</div></div>';
}

/* Scoped re-render for keystroke-driven search: replacing only the side pane
   and the doc column keeps the search input — and its caret — alive, the same
   reason renderFilterOnly() exists for the editor filter. */
function wsRenderSideOnly(){
  const side = document.querySelector("#scBody .ws-side");
  if (!side){ render(); return; }
  const state = wsCurrentState();
  wsSyncCursorRow();
  const tr = document.querySelector("#panes .pane.browse .ws-topright");
  if (tr){
    const g2 = S.ws.results ? wsGroupResults(S.ws.results) : null;
    tr.outerHTML = wsTopRightHtml(state, g2);
  }
  side.innerHTML = (S.ws.searching && !S.ws.results) ? wsSearchingHtml()
    : S.ws.results ? wsResultsHtml()
    : ('<div class="ws-lens" role="tablist">'
       + '<button type="button" data-wslens="org" aria-selected="' + (S.ws.lens === "org") + '">'
       + WS_COPY.lensOrg + '</button>'
       + '<button type="button" data-wslens="folders" aria-selected="' + (S.ws.lens === "folders") + '">'
       + WS_COPY.lensFolders + '</button></div>')
      + (S.ws.lens === "folders" ? wsFoldersHtml() : wsTreeHtml());
  const col = document.querySelector("#scBody .ws-doccol .ws-col");
  if (col && (state === "09" || state === "03" || state === "04"))
    col.innerHTML = wsDocColHtml(state);
  const count = document.querySelector("#scBody .ws-rescount");
  if (count && S.ws.results) count.textContent = String(wsGroupResults(S.ws.results).total);
}

/* ── wiring — the integrator calls this from wire() ─────────────────────────
   Everything per-render lives here: registration (idempotent), teardown on
   screen exit, the search input binding, and the iframe src assignment —
   which happens HERE as a property, never in markup, from sbUrl() only
   (ARCH.md S34: no new URL builders anywhere). */
function wireWorkspace(scBody){
  const edEl = scBody && scBody.querySelector && scBody.querySelector("[data-wseditor]");
  if (edEl && S.ws.editing && !S.ws.edHandle) void wsMountEditor(edEl);
  if (edEl && S.ws.edHandle && S.ws.edHandle.view
      && S.ws.edHandle.view.dom && S.ws.edHandle.view.dom.isConnected === false){
    /* re-render replaced the container: move the live editor back in — CM's
       view DOM relocates cleanly; state, undo and dirty tracking survive. */
    edEl.appendChild(S.ws.edHandle.view.dom);
  }
  if (!S.ws.editing && S.ws.edHandle) wsUnmountEditor();
  if (!wsFlagOn()) return;
  wsEnsureRegistered();
  /* Teardown on exit (ARCH memory plan): keep only lens + lastDocPath. */
  if (S.screen !== "workspace"){
    if (S.ws.loaded){
      wsUnmountEditor();               /* PLAN-25 S10: no orphaned CM view */
      const keep = { lens: S.ws.lens, lastDocPath: S.ws.lastDocPath };
      S.ws.loaded = false; S.ws.loading = false;
      S.ws.tree = null; S.ws.treeError = null;
      S.ws.q = ""; S.ws.results = null; S.ws.searchEpisode = false;
      S.ws.sel = null; S.ws.cursor = null; S.ws.charter = null; S.ws.matched = null;
      S.ws.doc = null; S.ws.docPath = null; S.ws.docMtime = null; S.ws.lastRead = null;
      S.ws.docGone = false; S.ws.changed = false; S.ws.editing = false; S.ws.unsaved = false;
      S.ws.notice = null; S.ws.busy = null;
      S.ws.lens = keep.lens; S.ws.lastDocPath = keep.lastDocPath;
    }
    return;
  }
  scBody = scBody || document.getElementById("scBody");
  if (!scBody) return;
  /* the input lives in the browse pane's .ph now, not in scBody (r3) */
  const search = document.querySelector("#panes .pane.browse [data-wssearch]");
  if (search){
    /* No render() per keystroke — it would fight the caret; results repaint
       through wsRenderSideOnly() when the debounced fetch lands. */
    search.oninput = ()=> wsSearchInput(search.value);
  }
  const frame = scBody.querySelector("[data-wsframe]");
  if (frame && S.sb && S.sb.running && S.ws.docPath){
    const page = sbPageFromPath(S.ws.docPath);
    const url = page === null ? null : sbUrl(S.sb.port, page);
    /* A null from either validator leaves the frame BLANK — nothing loads a
       guess (DEEPLINKS §2). Skipping the reassignment when the URL already
       matches keeps unrelated re-renders from reloading the document. */
    if (url && frame.src !== url){
      frame.onload = ()=>{
        /* A11Y R1: focus enters the frame only after an EXPLICIT open action;
           background reloads never steal it. */
        if (S.ws.focusFrameOnLoad){ S.ws.focusFrameOnLoad = false; try { frame.focus(); } catch (e){} }
      };
      frame.src = url;
    }
  }
  /* Restore keyboard focus to the cursor row after a full render — the roving
     tabindex row is the only [data-wsfocus] in the pane. */
  const foc = scBody.querySelector(".ws-side [data-wsfocus]");
  if (foc && document.activeElement !== search &&
      document.activeElement && document.activeElement.tagName !== "IFRAME") {
    /* only reclaim focus when a tree/results traversal is in progress.
       preventScroll (glitch fix 2026-08-25): a plain focus() yanked the
       freshly rebuilt tree to the cursor row on EVERY background render —
       the second half of the scroll glitch. The rAF nearest-scroll runs
       AFTER render()'s scroll restore, so arrow-key traversal still follows
       the cursor while a background repaint moves nothing. */
    if (S.ws.cursor){
      try { foc.focus({ preventScroll: true }); } catch (_e){ foc.focus(); }
      requestAnimationFrame(()=>{
        if (foc.isConnected && document.activeElement === foc){
          try { foc.scrollIntoView({ block: "nearest" }); } catch (_e){}
        }
      });
    }
  }
}

/* ── delegated events ────────────────────────────────────────────────────────
   Document-level, registered ONCE at module eval (the connectors precedent:
   #scBody is rebuilt every render, so a listener on it dies with the
   element). First line of each guard is the flag/screen check — with the
   flag off these handlers see the event and do NOTHING, which is the
   inertness the tests pin. */
document.addEventListener("click", e => {
  if (!wsActive()) return;
  if (!(e.target && e.target.closest)) return;
  if (!e.target.closest("#scBody")) return;

  const lens = e.target.closest("[data-wslens]");
  if (lens){ wsSetLens(lens.dataset.wslens); return; }

  const act = e.target.closest("[data-wsact]");
  if (act){
    const a = act.dataset.wsact;
    if (a === "edit") wsEdit();
    else if (a === "done") wsDone();
    else if (a === "reload") wsReload();
    else if (a === "keepmine") wsKeepMine();
    else if (a === "savecopy") wsSaveCopy();
    else if (a === "tryagain") wsTryAgain();
    else if (a === "fileit") wsFileIt();
    else if (a === "newdoc" || a === "newdochere") wsNewDoc();
    return;
  }

  const row = e.target.closest("[data-wstype]");
  if (row){
    wsActivateRow({ type: row.dataset.wstype, key: row.dataset.wskey,
                    kind: row.dataset.wskind });
    return;
  }
});
document.addEventListener("keydown", wsKeydown);
/* Changed-on-disk / doc-gone detection rides window focus — the moment the
   operator comes back is the moment stale state would mislead them, and a
   poll would violate the no-retry-storm rule. */
/* The panel-test harness stubs window without addEventListener; the guard
   costs nothing in the real browser and keeps the module loadable there. */
if (typeof window.addEventListener === "function")
  window.addEventListener("focus", ()=>{ if (wsActive()) wsCheckDisk(); });
