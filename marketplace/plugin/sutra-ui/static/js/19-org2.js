/* 19-org2.js -- the Org screen: one tree of names, a department strip, a list
   column and a viewer that opens on the charter (holding BUILD-PLAN.md; design
   canvas 6e5e3f8b, pages "Bare screen" and "States").

   Ships behind flags.org2 in ~/.sutra-ui/settings.json: OPT-IN, absent means
   OFF, until plan step 98 flips the default. The earlier Org screens keep every
   id and stay reachable under "Old Org" in the rail; nothing here changes them.

   Reuse (BUILD-PLAN section 1): dirData() from 03-org.js for the tree data,
   loadOrg() for the four registry reads, mdHtml() + /api/fs/read for a
   document, the Workspace's editor bundle (wsLoadEditorScript, SutraEditor)
   and /api/fs/write for editing in place, the Apps page frame for an app,
   simulate() for a move preview, the proposals gate for every request, and
   the org2_api.py reads: department, charter, search, filter, health, page.
   Every handler is delegated and scoped to `.o2`, so nothing fires on another
   screen (the 18-modules.js discipline).

   Copy discipline (founder, 2026-09-14): names, never paths; no counts at rest;
   no help text; one quiet line and at most one action per empty or error state;
   every action behind the pencil. Nothing here writes the tree: a rename, a
   move and a new sub-department are REQUESTS that wait in Approvals. */

const O2_FLAG = "org2";
const O2_MORE = 4;                       /* names per list group before "more…" */
const O2_SEARCH_MS = 220;                /* server search debounce */
const O2_KINDS = [["organisation", "Organisations"], ["department", "Departments"], ["machine", "Machine"]];
const O2_STATES = [["active", "Active"], ["no-charter", "No charter"], ["one-line", "One-line charter"]];

function org2FlagOn(){
  return !!(typeof SETTINGS !== "undefined" && SETTINGS && SETTINGS.flags
            && SETTINGS.flags[O2_FLAG] === true);
}
function o2S(){
  if (!S.o2) S.o2 = { sel:null, view:"charter", doc:null, app:null, other:null, page:null, q:"", lq:"",
                      hits:null, filter:{ open:false, kind:[], state:[], refs:null, busy:false },
                      sheet:null, flash:null, health:{}, edHandle:null,
                      expanded:null, more:{}, loading:false, error:null, loaded:false,
                      dept:{}, deptErr:{}, apps:{}, menu:false, panel:null };
  return S.o2;
}
function o2Icon(k){ return (typeof ICON !== "undefined" && ICON && ICON[k]) ? ICON[k] : ""; }
function o2Svg(k){
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${o2Icon(k)}</svg>`;
}
const O2_CHEV = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>`;
const O2_FUNNEL = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 5h18l-7 8v6l-4 2v-8z"/></svg>`;
const O2_X = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>`;
const O2_SHIELD = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l7 3v6c0 4.5-3 7.8-7 9-4-1.2-7-4.5-7-9V6z"/></svg>`;
const O2_DOC = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h11l5 5v11a1 1 0 01-1 1H4a1 1 0 01-1-1V5a1 1 0 011-1z"/><path d="M14 4v6h6M7 14h8M7 17h5"/></svg>`;
const O2_APP = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/></svg>`;
const O2_PAGE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v5"/></svg>`;

function o2Esc(x){ return (typeof esc === "function") ? esc(x) : String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"); }
function o2Date(ms){ const n = Number(ms); if (!n) return ""; try { return new Date(n).toISOString().slice(0, 10); } catch (e) { return ""; } }
function o2Render(){ if (typeof render === "function") render(); }
function o2IsPage(p){ return /\.html?$/i.test(String(p || "")); }
function o2IsDoc(p){ return typeof sbPageFromPath === "function" ? !!sbPageFromPath(p) : /\.md$/i.test(String(p || "")); }

/* Registration waits for the flag (13-workspace.js wsEnsureRegistered): SETTINGS
   arrives after the scripts ran, so eval-time registration could never honour
   it. TITLES gets its row in the same breath: render() destructures
   TITLES[S.screen], so a SCREENS entry without one is a TypeError. */
function o2EnsureRegistered(){
  if (typeof SCREENS === "undefined" || typeof TITLES === "undefined") return;
  if (!org2FlagOn() || SCREENS.org2) return;
  SCREENS.org2 = o2ScreenHtml;
  TITLES.org2 = ["Org", ""];
}

/* ── data ─────────────────────────────────────────────────────────────────── */
function o2Data(){
  if (typeof DOMAINS === "undefined" || !DOMAINS || !DOMAINS.length || typeof dirData !== "function")
    return { live: [], byRef: new Map(), kids: new Map(), root: null };
  return dirData();
}
/* Interim node kind (plan S27) until the engine stores one (S94): the root has
   no parent; under the root, the machine is the importer's "Desktop" or any
   node carrying a cwd or an import origin; the other root children are
   organisations; everything below is a department. */
function o2Kind(n, d){
  if (!n.parent_ref || !d.byRef.has(n.parent_ref)) return "root";
  if (d.root && n.parent_ref === d.root.ref){
    if (n.name === "Desktop" || n.cwd || /import/i.test(String(n.origin || ""))) return "machine";
    return "org";
  }
  return "dept";
}
function o2Expanded(){
  const st = o2S();
  if (!st.expanded){
    st.expanded = new Set();
    const d = o2Data();
    if (d.root) st.expanded.add(d.root.ref);          /* the home opens one level */
  }
  return st.expanded;
}
function o2Chain(ref, d){
  const names = [], seen = new Set(); let n = d.byRef.get(ref);
  while (n && !seen.has(n.ref)){ seen.add(n.ref); names.unshift(n.name); n = n.parent_ref ? d.byRef.get(n.parent_ref) : null; }
  return names;
}
function o2Subtree(ref, d){
  const out = new Set([ref]), stack = [ref];
  while (stack.length){
    const r = stack.pop();
    (d.kids.get(r) || []).forEach(k => { if (!out.has(k.ref)){ out.add(k.ref); stack.push(k.ref); } });
  }
  return out;
}

/* ── loaders ──────────────────────────────────────────────────────────────── */
/* The one open path (openScreen hooks this). Wraps loadOrg(), which has no
   loading or error state of its own, so the screen can say "Sutra is not
   reachable" instead of staying blank (plan S16, S53). */
async function loadOrg2(force){
  if (!org2FlagOn()) return;
  o2EnsureRegistered();
  const st = o2S();
  if (st.loading) return;
  if (st.loaded && !force) return;
  st.loading = true; st.error = null; o2Render();
  try {
    if (typeof loadOrg === "function") await loadOrg();
    st.loaded = true;
    if (!st.sel){ const d = o2Data(); st.sel = d.root ? d.root.ref : null; }
  } catch (e) {
    st.error = (e && e.message) || String(e);
  }
  st.loading = false;
  o2Render();
  if (st.sel) o2LoadDept(st.sel, force);
}
async function o2LoadDept(ref, force){
  const st = o2S();
  if (!ref || (st.dept[ref] && !force)) return;
  if (!st.busy) st.busy = {};
  if (st.busy[ref]) return;                             /* one read in flight per department */
  st.busy[ref] = true;
  try {
    st.dept[ref] = await apiGet("/api/org2/department/" + encodeURIComponent(ref));
    delete st.deptErr[ref];
  } catch (e) {
    st.deptErr[ref] = (e && e.message) || String(e);
  }
  delete st.busy[ref];
  o2Render();
}
/* Apps of ONE department, read directly: loadModules() owns S.modules and the
   Apps screen's cache, so calling it from here would invalidate that screen. */
async function o2LoadApps(ref){
  const st = o2S();
  if (!ref || st.apps[ref] !== undefined) return;
  st.apps[ref] = null;                                  /* in flight */
  try {
    const r = await apiGet("/api/modules?subtree=0&department=" + encodeURIComponent(ref));
    const body = (r && r.groups) ? r : ((r && r.modules && r.modules.groups) ? r.modules : {});
    st.apps[ref] = ((body.groups || {}).here || []).filter(m => m && !m.reserved);
  } catch (e) { st.apps[ref] = []; }
  o2Render();
}
/* Search beyond names (plan S74): charter titles, filed work and documents are
   matched server-side; the answer is a set of refs that joins the name match
   in the tree. Debounced; a stale answer is dropped by comparing the query. */
function o2SearchSoon(){
  const st = o2S();
  if (st.qTimer && typeof clearTimeout === "function") clearTimeout(st.qTimer);
  if (typeof setTimeout === "function") st.qTimer = setTimeout(o2SearchServer, O2_SEARCH_MS);
  else o2SearchServer();
}
async function o2SearchServer(){
  const st = o2S();
  const q = String(st.q || "").trim();
  if (q.length < 2){ st.hits = null; o2Render(); return; }
  try {
    const r = await apiGet("/api/org2/search?q=" + encodeURIComponent(q));
    if (String(st.q || "").trim() === q) st.hits = new Set(r.refs || []);
  } catch (e) { if (String(st.q || "").trim() === q) st.hits = null; }
  o2Render();
}
/* The funnel (plan S76): kinds and states are chips; the server answers with
   the refs that match every chosen axis and the tree dims the rest. */
async function o2ApplyFilter(){
  const st = o2S(), f = st.filter;
  if (!f.kind.length && !f.state.length){ f.refs = null; f.busy = false; o2Render(); return; }
  f.busy = true; o2Render();
  const key = f.kind.join(",") + "|" + f.state.join(",");
  try {
    const r = await apiGet("/api/org2/filter?kind=" + encodeURIComponent(f.kind.join(",")) + "&state=" + encodeURIComponent(f.state.join(",")));
    if (f.kind.join(",") + "|" + f.state.join(",") === key) f.refs = new Set(r.refs || []);
  } catch (e) { f.refs = null; }
  f.busy = false;
  o2Render();
}
function o2FilterOn(){ const f = o2S().filter; return !!(f.kind.length || f.state.length); }
async function o2LoadHealth(ref, force){
  const st = o2S();
  if (!ref || (st.health[ref] && !force && !st.health[ref].error)) return;
  st.health[ref] = { data: null, error: null };
  try { st.health[ref].data = await apiGet("/api/org2/health/" + encodeURIComponent(ref)); }
  catch (e) { st.health[ref].error = (e && e.message) || String(e); }
  o2Render();
}

/* ── selection and opens ──────────────────────────────────────────────────── */
function o2Select(ref){
  const st = o2S(), d = o2Data();
  if (!d.byRef.has(ref)) return;
  o2UnmountEditor();
  st.sel = ref; st.view = "charter"; st.doc = null; st.app = null; st.other = null; st.page = null;
  st.menu = false; st.panel = null; st.sheet = null; st.more = {};
  const ex = o2Expanded(); ex.add(ref);
  let n = d.byRef.get(ref);
  while (n && n.parent_ref && d.byRef.has(n.parent_ref)){ ex.add(n.parent_ref); n = d.byRef.get(n.parent_ref); }
  o2Render();
  o2LoadDept(ref);
}
async function o2OpenCharter(cid){
  const st = o2S();
  o2UnmountEditor();
  st.view = "other"; st.other = { id: cid, data: null, error: null }; st.menu = false; st.sheet = null; o2Render();
  try {
    const r = await apiGet("/api/org2/charter/" + encodeURIComponent(cid));
    if (st.other && st.other.id === cid) st.other.data = r;
  } catch (e) {
    if (st.other && st.other.id === cid) st.other.error = (e && e.message) || String(e);
  }
  o2Render();
}
/* A document opens in place, read first (plan S54); when the server says it is
   editable the Workspace's editor mounts over the text (plan S55) and saves
   through /api/fs/write with the bytes captured here, so a file changed by
   another session raises the 409 lane instead of being overwritten. */
async function o2OpenDoc(path, title){
  const st = o2S();
  if (!o2IsDoc(path)) return;
  o2UnmountEditor();
  st.view = "doc"; st.doc = { path, title: title || path, text: null, error: null, editable: null, bytes: null, conflict: false, saveState: null };
  st.menu = false; st.sheet = null; o2Render();
  try {
    const r = await apiGet("/api/fs/read?path=" + encodeURIComponent(path));
    if (st.doc && st.doc.path === path){ st.doc.text = String(r.text == null ? "" : r.text); st.doc.editable = !!r.editable; st.doc.bytes = r.bytes; }
  } catch (e) {
    if (st.doc && st.doc.path === path) st.doc.error = (e && e.message) || String(e);
  }
  o2Render();
}
/* An .html artifact filed under the department opens in the same sandboxed
   frame an app page uses, served by /api/org2/page under the page CSP (plan S56). */
function o2OpenPage(path, title){
  const st = o2S();
  if (!o2IsPage(path)) return;
  o2UnmountEditor();
  st.view = "page"; st.page = { path, title: title || String(path).split("/").pop() };
  st.menu = false; st.sheet = null; o2Render();
}
function o2OpenApp(m){
  const st = o2S();
  o2UnmountEditor();
  st.view = "app"; st.app = m; st.menu = false; st.sheet = null; o2Render();
}
function o2CloseViewer(){
  const st = o2S();
  o2UnmountEditor();
  st.view = "charter"; st.doc = null; st.app = null; st.other = null; st.page = null; st.sheet = null; o2Render();
}

/* ── the editor in place (reuses the Workspace bundle and contract) ──────── */
function o2Dark(){
  if (typeof document === "undefined") return true;
  const r = document.documentElement;
  const t = r && r.getAttribute ? r.getAttribute("data-theme") : null;
  if (t) return t === "dark";
  return !!(typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
}
async function o2MountEditor(el){
  const st = o2S();
  const doc = st.doc;
  if (!doc || st.view !== "doc" || doc.text === null || !doc.editable || st.edHandle) return;
  const path = doc.path;
  if (typeof wsLoadEditorScript !== "function"){ doc.editable = false; o2Render(); return; }
  try { await wsLoadEditorScript(); }
  catch (e) { doc.editable = false; o2Render(); return; }   /* read view instead of an empty column */
  if (st.doc !== doc || st.view !== "doc" || st.edHandle) return;   /* the state moved on while loading */
  const live = (typeof document !== "undefined" && document.querySelector) ? document.querySelector("#scBody [data-o2editor]") : null;
  if (live) el = live;
  else if (!el || el.isConnected === false) return;
  if (typeof window === "undefined" || !window.SutraEditor) return;
  st.edHandle = window.SutraEditor.mount({
    parent: el,
    path: path,
    title: doc.title || path.split("/").pop(),
    text: doc.text || "",
    readOnly: false,
    dark: o2Dark(),
    save: async (text) => {
      try {
        const r = await apiPost("/api/fs/write", { path: path, text: text, base_bytes: doc.bytes });
        doc.text = text; doc.bytes = r.bytes; doc.conflict = false;
      } catch (e) {
        if (e && e.status === 409) doc.conflict = true;
        o2Render();
        throw e;
      }
    },
    onDirty: () => {},
    onSaveState: (s) => { doc.saveState = s; if (s === "failed") o2Render(); },
    navigate: (ref) => { if (o2IsDoc(ref)) o2OpenDoc(ref); },
    flash: (m) => { st.flash = String(m || ""); o2Render(); },
  });
}
function o2UnmountEditor(){
  const st = S.o2;
  if (!st || !st.edHandle) return;
  const h = st.edHandle;
  try { h.forceSave(); } catch (e) {}
  try { h.destroy(); } catch (e) {}
  st.edHandle = null;
}
/* Called by wire() after every paint (07-loaders.js). The paint replaced the
   viewer's DOM, so either mount into the new container, move the live editor
   view back in (the Workspace's own trick: state, undo and dirty survive), or
   tear down when the screen or the document is gone. */
function wireOrg2(scBody){
  const st = S.o2;
  if (!st) return;
  if (S.screen !== "org2"){ o2UnmountEditor(); return; }
  const el = scBody && scBody.querySelector ? scBody.querySelector("[data-o2editor]") : null;
  if (!el){ o2UnmountEditor(); return; }
  if (!st.edHandle){ void o2MountEditor(el); return; }
  const dom = st.edHandle.view && st.edHandle.view.dom;
  if (dom && dom.isConnected === false) el.appendChild(dom);
}

/* ── requests: rename, move, new sub-department (plan S60, S70, S72) ─────── */
function o2OpenSheet(kind){
  const st = o2S(), d = o2Data();
  const n = st.sel ? d.byRef.get(st.sel) : null;
  if (!n) return;
  o2UnmountEditor();
  st.menu = false; st.panel = null;
  st.sheet = { kind, name: kind === "rename" ? n.name : "", target: "", error: null, busy: false };
  o2Render();
}
function o2MoveTargets(n, d){
  const inside = o2Subtree(n.ref, d);
  return d.live.filter(x => !inside.has(x.ref) && x.ref !== n.parent_ref)
    .map(x => ({ ref: x.ref, label: o2Chain(x.ref, d).join(" › ") }))
    .sort((a, b) => a.label.localeCompare(b.label));
}
async function o2SendRequest(){
  const st = o2S(), d = o2Data(), sh = st.sheet;
  const n = st.sel ? d.byRef.get(st.sel) : null;
  if (!sh || !n || sh.busy) return;
  const name = String(sh.name || "").trim();
  let kind, args;
  if (sh.kind === "rename"){ kind = "org.rename"; args = { ref: n.ref, name }; if (!name || name === n.name){ sh.error = !name ? "A name is needed" : "That is the current name"; o2Render(); return; } }
  else if (sh.kind === "move"){ kind = "org.move"; args = { ref: n.ref, target: sh.target, base: (S.draft && S.draft.base) || null }; if (!sh.target){ sh.error = "Choose where it goes"; o2Render(); return; } }
  else { kind = "org.create"; args = { parent: n.ref, name }; if (!name){ sh.error = "A name is needed"; o2Render(); return; } }
  sh.busy = true; sh.error = null; o2Render();
  try {
    const r = await apiPost("/api/org2/request", { kind, args });
    st.sheet = null;
    st.flash = "Waiting for approval · " + ((r && r.summary) || "");
    st.panel = "approvals";
    if (typeof loadProposals === "function") loadProposals(true);
  } catch (e) {
    sh.busy = false; sh.error = (e && e.message) || String(e);
  }
  o2Render();
}
function o2SheetHtml(n, d){
  const st = o2S(), sh = st.sheet;
  const title = sh.kind === "rename" ? "Rename" : sh.kind === "move" ? "Move" : "New sub-department";
  let fields;
  if (sh.kind === "move"){
    const opts = o2MoveTargets(n, d).map(t => `<option value="${o2Esc(t.ref)}"${sh.target === t.ref ? " selected" : ""}>${o2Esc(t.label)}</option>`).join("");
    fields = `<label for="o2starget">Under</label><select id="o2starget" data-o2starget><option value="">Choose…</option>${opts}</select>${o2MovePreviewHtml(n, d)}`;
  } else {
    fields = `<label for="o2sname">Name</label><input id="o2sname" type="text" data-o2sname value="${o2Esc(sh.name)}" maxlength="80" autocomplete="off">`;
  }
  const body = `<div class="o2vb"><div class="o2sheet"><div class="o2mono">request · waits for approval</div><h1>${o2Esc(title)}</h1>${fields}
    <div class="o2acts2"><button type="button" class="btn primary" data-o2act="request" ${sh.busy ? "disabled" : ""}>Request</button>
    <button type="button" class="btn" data-o2act="sheetclose">Cancel</button>${sh.error ? `<span class="o2err">${o2Esc(sh.error)}</span>` : ""}</div></div></div>`;
  return o2ViewerShell(n.name, o2Svg("edit"), body);
}
/* Preview a move (plan S66): the same simulation the studio's rings use, on
   the one op, listed as dots and names; never an Apply here. */
function o2MovePreviewHtml(n, d){
  const sh = o2S().sheet;
  if (!sh.target || typeof simulate !== "function") return "";
  const sim = simulate([{ op: "move", ref: n.ref, target: sh.target }]);
  if (!sim || sim.pending) return `<div class="o2prev o2quiet">Checking…</div>`;
  if (sim.error) return `<div class="o2prev o2quiet">The check could not run</div>`;
  const rows = (sim.findings || []);
  const sev = s => s === "block" ? "var(--block)" : s === "warn" ? "var(--warn)" : "var(--ok)";
  if (!rows.length) return `<div class="o2prev"><div class="o2prow"><span class="o2dot" style="background:var(--ok)"></span><span>Nothing in the way</span></div></div>`;
  return `<div class="o2prev">${rows.map(f => `<div class="o2prow"><span class="o2dot" style="background:${sev(f.sev)}"></span><span>${o2Esc(f.subject || f.code || "")}</span></div>`).join("")}</div>`;
}

/* ── tree ─────────────────────────────────────────────────────────────────── */
function o2SearchHtml(){
  const st = o2S();
  return `<div class="o2search">${o2Svg("know")}<input type="search" data-o2q value="${o2Esc(st.q)}" placeholder="Search" aria-label="Search the organisation"><button type="button" class="o2funnel" data-o2filter aria-label="Filter" aria-pressed="${o2FilterOn()}" aria-expanded="${!!st.filter.open}">${O2_FUNNEL}</button></div>${st.filter.open ? o2FilterHtml() : ""}`;
}
function o2FilterHtml(){
  const f = o2S().filter;
  const chip = (axis, v, label, on) => `<button type="button" class="o2chip" data-o2chip="${axis}:${v}" aria-pressed="${on}">${o2Esc(label)}</button>`;
  return `<div class="o2pop" role="group" aria-label="Filter">
    <div class="o2chips">${O2_KINDS.map(([v, l]) => chip("kind", v, l, f.kind.indexOf(v) !== -1)).join("")}</div>
    <div class="o2chips">${O2_STATES.map(([v, l]) => chip("state", v, l, f.state.indexOf(v) !== -1)).join("")}</div>
    ${o2FilterOn() ? `<div class="o2chips"><button type="button" class="o2more" data-o2act="filterclear">Clear</button></div>` : ""}
  </div>`;
}
function o2TreeHtml(){
  const st = o2S(), d = o2Data(), ex = o2Expanded();
  const q = String(st.q || "").trim().toLowerCase();
  const fr = st.filter.refs;
  const hit = n => (!q || String(n.name || "").toLowerCase().indexOf(q) !== -1 || (st.hits && st.hits.has(n.ref)))
                && (!fr || fr.has(n.ref));
  const narrowing = !!q || !!fr;
  const subtreeHit = n => hit(n) || (d.kids.get(n.ref) || []).some(subtreeHit);
  const row = (n, depth, chain) => {
    const ks = d.kids.get(n.ref) || [];
    const kind = o2Kind(n, d);
    const open = narrowing ? true : ex.has(n.ref);
    const dim = narrowing && !subtreeHit(n);
    const title = chain.concat([n.name]).join(" › ");
    const chev = ks.length
      ? `<button type="button" class="o2chev" data-o2tog="${o2Esc(n.ref)}" aria-label="${open ? "Collapse" : "Expand"} ${o2Esc(n.name)}">${O2_CHEV}</button>`
      : `<span class="o2chev"></span>`;
    const exp = ks.length ? ` aria-expanded="${open}"` : "";
    const self = `<div role="treeitem" tabindex="0" class="o2row o2k-${kind}${dim ? " dim" : ""}" data-o2ref="${o2Esc(n.ref)}" aria-selected="${st.sel === n.ref}"${exp} style="--d:${depth}" title="${o2Esc(title)}">${chev}<span class="o2name">${o2Esc(n.name)}</span></div>`;
    return self + (open ? ks.map(c => row(c, depth + 1, chain.concat([n.name]))).join("") : "");
  };
  if (!d.root) return `<div class="o2tree" role="tree"></div>`;
  return `<div class="o2tree" role="tree">${row(d.root, 0, [])}</div>`;
}
function o2SkelTree(){
  return `<div class="o2tree" aria-busy="true">${[60, 90, 120, 80, 140, 110, 96, 130, 70, 118].map(w => `<div class="o2skel" style="width:${w}px"></div>`).join("")}</div>`;
}

/* ── strip, list, viewer ──────────────────────────────────────────────────── */
function o2MenuHtml(n, d){
  const item = (act, label) => `<button type="button" role="menuitem" data-o2act="${act}">${label}</button>`;
  const kind = n ? o2Kind(n, d) : "dept";
  let acts = "";
  if (kind !== "root") acts += item("rename", "Rename…");
  if (kind !== "root" && kind !== "machine") acts += item("move", "Move…");
  acts += item("create", "New sub-department…");
  return `<div class="smenu o2menu" role="menu">${acts}<div class="o2msep"></div>${item("changes", "Changes")}${item("approvals", "Approvals")}${item("health", "Health")}</div>`;
}
function o2StripHtml(n, d, dept){
  const st = o2S();
  const parent = n.parent_ref ? d.byRef.get(n.parent_ref) : null;
  const retired = dept && dept.status === "retired";
  const succ = retired && dept.successors && dept.successors.length ? dept.successors[0] : null;
  const pill = retired ? `<span class="pill p-mut">retired</span>${succ ? `<span class="o2parent">merged into ${o2Esc(succ.name || "")}</span>` : ""}` : "";
  return `<div class="o2strip"><h2>${o2Esc(n.name)}</h2>${parent ? `<span class="o2parent">${o2Esc(parent.name)}</span>` : ""}${pill}
    <span class="o2acts">
      <button type="button" class="o2ib" data-o2act="chart" aria-label="Chart" aria-pressed="${st.view === "chart"}">${o2Svg("dept")}</button>
      <button type="button" class="o2ib" data-o2act="pencil" aria-label="Edit" aria-haspopup="menu" aria-expanded="${!!st.menu}">${o2Svg("edit")}</button>
      ${st.menu ? o2MenuHtml(n, d) : ""}
    </span></div>`;
}
function o2Row(label, svg, attrs, on, cls){
  return `<button type="button" class="o2li${on ? " on" : ""}${cls ? " " + cls : ""}" ${attrs}>${svg}<span>${o2Esc(label)}</span></button>`;
}
function o2Group(label, rows, key){
  if (!rows.length) return "";
  const st = o2S();
  const all = !!st.more[key];
  const shown = all ? rows : rows.slice(0, O2_MORE);
  const more = rows.length > O2_MORE && !all ? `<button type="button" class="o2more" data-o2more="${o2Esc(key)}">more…</button>` : "";
  return `<div class="o2g"><div class="o2gl">${o2Esc(label)}</div>${shown.join("")}${more}</div>`;
}
function o2ListHtml(n, d, dept, err){
  const st = o2S();
  const lq = String(st.lq || "").trim().toLowerCase();
  const keep = name => !lq || String(name || "").toLowerCase().indexOf(lq) !== -1;
  let groups = "";
  if (err){
    groups = `<div class="o2quiet">Sutra did not answer for ${o2Esc(n.name)}</div><div style="padding:0 8px"><button type="button" class="btn" data-o2act="retrydept">Try again</button></div>`;
  } else if (!dept){
    groups = [110, 140, 96, 128, 84, 150, 100].map(w => `<div class="o2skel" style="width:${w}px"></div>`).join("");
  } else {
    const c = dept.charter;
    const charterRow = c
      ? o2Row(c.title || n.name, O2_SHIELD, `data-o2act="charter"`, st.view === "charter")
      : o2Row("No charter yet", O2_SHIELD, `data-o2act="charter"`, st.view === "charter", "mut");
    groups += o2Group("Charter", keep(c ? c.title : "No charter yet") ? [charterRow] : [], "charter");
    groups += o2Group("Departments", (dept.children || []).filter(x => keep(x.name)).map(x => o2Row(x.name, o2Svg("dept"), `data-o2ref="${o2Esc(x.ref)}"`, false)), "departments");
    groups += o2Group("Filed work", (dept.filed || []).filter(x => keep(x.label)).map(x => o2Row(x.label, o2IsPage(x.id) ? O2_PAGE : o2Svg("plc"), `data-o2filed="${o2Esc(x.id || "")}" data-o2title="${o2Esc(x.label)}"`, st.view === "page" && st.page && st.page.path === x.id)), "filed");
    groups += o2Group("Other charters", (dept.charters || []).filter(x => keep(x.title)).map(x => o2Row(x.title, O2_SHIELD, `data-o2charter="${o2Esc(x.id)}"`, st.view === "other" && st.other && st.other.id === x.id)), "charters");
    groups += o2Group("Documents", (dept.docs || []).filter(x => keep(x.title)).map(x => o2Row(x.title, O2_DOC, `data-o2doc="${o2Esc(x.path)}" data-o2title="${o2Esc(x.title)}"`, st.view === "doc" && st.doc && st.doc.path === x.path)), "docs");
    const apps = st.apps[n.ref];
    if (apps === undefined) o2LoadApps(n.ref);
    groups += o2Group("Apps", (apps || []).filter(m => keep(m.name)).map(m => o2Row(m.name, O2_APP, `data-o2app="${o2Esc(m.id)}"`, st.view === "app" && st.app && st.app.id === m.id)), "apps");
    if (!groups) groups = `<div class="o2quiet">Nothing named ${o2Esc(st.lq)}</div><div style="padding:0 8px"><button type="button" class="btn" data-o2act="clearlq">Clear</button></div>`;
  }
  return `<div class="o2list"><div class="o2search o2lsearch">${o2Svg("know")}<input type="search" data-o2lq value="${o2Esc(st.lq || "")}" placeholder="Search ${o2Esc(n.name)}" aria-label="Search ${o2Esc(n.name)}"></div>${groups}</div>`;
}
function o2FacetRow(label, value, unsourced){
  return `<div class="o2f"><b>${o2Esc(label)}</b><span${unsourced ? ' class="ns"' : ""}>${unsourced ? "not sourced yet" : value}</span></div>`;
}
function o2FacetsHtml(n, d, dept){
  const c = dept.charter;
  const chain = (dept.address && dept.address.length) ? dept.address : o2Chain(n.ref, d);
  const kids = (dept.children || []).map(x => x.name);
  const parent = n.parent_ref ? d.byRef.get(n.parent_ref) : null;
  const succ = (dept.successors || []).map(s => s.name).filter(Boolean);
  const since = o2Date(dept.ts_minted_ms || n.ts_minted_ms);
  const status = dept.status || "active";
  const life = `<span class="pill ${status === "active" ? "p-ok" : "p-mut"}">${o2Esc(status)}</span>${since ? " since " + since : ""}${succ.length ? " · merged into " + o2Esc(succ.join(", ")) : " · no successor"}`;
  const rel = `${parent ? "parent " + o2Esc(parent.name) : "the root"} · sub-departments: ${kids.length ? o2Esc(kids.join(", ")) : "none"}`;
  const filed = c ? (dept.filed || []).filter(p => p.charter_id === c.id) : [];
  const filedTxt = filed.length ? o2Esc(filed.slice(0, 6).map(p => p.label).join(" · ")) + (filed.length > 6 ? " · more…" : "") : "none yet";
  return `<div class="o2facets">
    ${o2FacetRow("Address", o2Esc(chain.join(" › ")))}
    ${o2FacetRow("Lifecycle", life)}
    ${o2FacetRow("Relations", rel)}
    ${c ? o2FacetRow("Filed under this charter", filedTxt) : ""}
    ${o2FacetRow("Governance", (c ? "this charter" : "no charter") + ' · references: <span class="ns">not sourced yet</span>')}
    ${o2FacetRow("Org scope", "", true)}${o2FacetRow("Tier reach", "", true)}${o2FacetRow("Build layer", "", true)}
  </div>`;
}
function o2ViewerShell(title, svg, body, cls){
  return `<div class="o2viewer${cls ? " " + cls : ""}"><div class="o2vh">${svg}<b>${o2Esc(title)}</b><button type="button" class="o2ib o2x" data-o2act="close" aria-label="Close">${O2_X}</button></div>${body}</div>`;
}
function o2CharterBody(n, d, dept, c){
  const kind = (c && c.kind) || "standing", status = (c && c.status) || "active";
  const purpose = String((c && c.purpose) || "").trim();
  const oneLine = !!c && purpose.length > 0 && purpose.length < 60 && purpose.indexOf(". ") === -1;
  if (!c){
    return `<div class="o2vb"><div class="o2empty">${O2_SHIELD}<h1>No charter yet</h1></div>${o2FacetsHtml(n, d, dept)}</div>`;
  }
  return `<div class="o2vb">
    <div class="o2mono">charter · ${o2Esc(kind)} · ${o2Esc(status)}${oneLine ? ' <span class="pill p-warn">one line</span>' : ""}</div>
    <h1>${o2Esc(c.title || n.name)}</h1>
    <p class="o2purpose">${o2Esc(purpose)}</p>
    ${o2FacetsHtml(n, d, dept)}
  </div>`;
}
function o2ViewerHtml(n, d, dept, err){
  const st = o2S();
  if (st.sheet) return o2SheetHtml(n, d);
  if (st.view === "chart") return o2ChartHtml(n, d);
  if (st.view === "doc" && st.doc) return o2DocHtml(st.doc);
  if (st.view === "page" && st.page) return o2PageHtml(st.page);
  if (st.view === "app" && st.app) return o2AppHtml(st.app);
  if (st.view === "other" && st.other) return o2OtherHtml(n, st.other);
  if (err) return o2ViewerShell(n.name, O2_SHIELD, `<div class="o2vb"><div class="o2empty"><h1>Sutra did not answer</h1><button type="button" class="btn" data-o2act="retrydept">Try again</button></div></div>`);
  if (!dept) return `<div class="o2viewer" aria-busy="true"><div class="o2vb"><div class="o2skel" style="width:120px;margin:0 0 14px"></div><div class="o2skel" style="width:260px;height:22px;margin:0 0 18px"></div><div class="o2skel" style="width:520px;margin:0 0 8px"></div><div class="o2skel" style="width:480px;margin:0 0 8px"></div><div class="o2skel" style="width:300px;margin:0"></div></div></div>`;
  const c = dept.charter;
  return o2ViewerShell(c ? (c.title || n.name) : n.name, O2_SHIELD, o2CharterBody(n, d, dept, c));
}
function o2OtherHtml(n, o){
  if (o.error) return o2ViewerShell(n.name, O2_SHIELD, `<div class="o2vb"><div class="o2empty"><h1>Sutra did not answer</h1></div></div>`);
  if (!o.data) return `<div class="o2viewer" aria-busy="true"><div class="o2vb"><div class="o2skel" style="width:260px;height:22px;margin:0 0 18px"></div><div class="o2skel" style="width:520px"></div></div></div>`;
  const c = o.data.charter || {};
  const dep = o.data.department || {};
  const owner = dep.name ? `${o2Esc(dep.name)}${dep.status === "retired" ? ' <span class="pill p-mut">retired</span>' + (dep.successor ? " &rarr; " + o2Esc(dep.successor) : "") : ""}` : "unknown";
  const filed = (o.data.filed || []);
  const filedTxt = filed.length ? o2Esc(filed.slice(0, 6).map(p => p.label).join(" · ")) + (filed.length > 6 ? " · more…" : "") : "none yet";
  return o2ViewerShell(c.title || "Charter", O2_SHIELD, `<div class="o2vb">
    <div class="o2mono">charter · ${o2Esc(c.kind || "project")} · ${o2Esc(c.status || "active")}</div>
    <h1>${o2Esc(c.title || "")}</h1>
    <p class="o2purpose">${o2Esc(c.purpose || "")}</p>
    <div class="o2facets">${o2FacetRow("Owner", owner)}${o2FacetRow("Filed under this charter", filedTxt)}</div>
  </div>`);
}
function o2DocHtml(doc){
  const title = doc.title || String(doc.path || "").split("/").pop();
  let body;
  if (doc.error) body = `<div class="o2vb"><div class="o2empty">${O2_DOC}<h1>Not on disk anymore</h1><button type="button" class="btn" data-o2act="changes">Show in Changes</button></div></div>`;
  else if (doc.text === null) body = `<div class="o2vb" aria-busy="true"><div class="o2skel" style="width:520px;margin:0 0 8px"></div><div class="o2skel" style="width:480px;margin:0 0 8px"></div><div class="o2skel" style="width:300px"></div></div>`;
  else if (doc.editable){
    const line = doc.conflict
      ? `<div class="o2vline warn"><span>Changed in another session</span><button type="button" class="btn" data-o2act="reload">Reload</button></div>`
      : (doc.saveState === "failed" ? `<div class="o2vline warn"><span>Not saved</span><button type="button" class="btn" data-o2act="reload">Reload</button></div>` : "");
    body = `${line}<div class="o2ed" data-o2editor></div>`;
  }
  else body = `<div class="o2vb"><div class="ws-mdbody o2md">${typeof mdHtml === "function" ? mdHtml(doc.text) : "<pre>" + o2Esc(doc.text) + "</pre>"}</div></div>`;
  return o2ViewerShell(title, O2_DOC, body);
}
function o2PageHtml(p){
  const theme = (typeof modTheme === "function") ? modTheme() : "dark";
  return o2ViewerShell(p.title, O2_PAGE, `<iframe class="o2frame" src="${o2Esc("/api/org2/page?path=" + encodeURIComponent(p.path) + "&theme=" + theme)}" title="${o2Esc(p.title)}" sandbox="allow-scripts"></iframe>`, "wide");
}
function o2AppHtml(m){
  if (m.kind === "page" && m.has_page){
    const theme = (typeof modTheme === "function") ? modTheme() : "dark";
    const api = (typeof MOD_API !== "undefined") ? MOD_API : "/api/modules";
    return o2ViewerShell(m.name, O2_APP, `<iframe class="o2frame" src="${o2Esc(api + "/" + m.id + "/page?theme=" + theme)}" title="${o2Esc(m.name)}" sandbox="allow-scripts"></iframe>`, "wide");
  }
  const line = m.kind === "page" ? "Nothing to show yet" : (m.kind === "chat" ? "Opens as a chat" : "Opens elsewhere");
  const act = (m.kind === "chat" || m.kind === "link") && typeof modOpen === "function"
    ? `<button type="button" class="btn" data-o2act="openapp">${m.kind === "chat" ? "Open in chat" : "Open"}</button>` : "";
  return o2ViewerShell(m.name, O2_APP, `<div class="o2vb"><div class="o2empty">${O2_APP}<h1>${line}</h1>${act}</div></div>`);
}
/* The chart from any level: this department, its sub-departments, and theirs,
   names only; a leaf shows one tile and a quiet line (design BareChart, StateLeafChart). */
function o2ChartHtml(n, d){
  const tile = (x, cls) => `<button type="button" class="o2tile${cls ? " " + cls : ""}" data-o2ref="${o2Esc(x.ref)}" title="${o2Esc(x.name)}">${o2Esc(x.name)}</button>`;
  const ks = d.kids.get(n.ref) || [];
  const head = `<div class="o2crow">${tile(n, "on")}</div>`;
  if (!ks.length) return `<div class="o2viewer wide"><div class="o2vb o2chart">${head}<div class="o2quiet">Nothing below ${o2Esc(n.name)}</div></div></div>`;
  const cols = ks.map(k => {
    const g = d.kids.get(k.ref) || [];
    const gc = g.slice(0, 4).map(x => tile(x, "sm")).join("") + (g.length > 4 ? `<button type="button" class="o2tile sm mut" data-o2ref="${o2Esc(k.ref)}" aria-label="More under ${o2Esc(k.name)}">…</button>` : "");
    return `<div class="o2col">${tile(k)}${g.length ? `<div class="o2gc">${gc}</div>` : ""}</div>`;
  }).join("");
  return `<div class="o2viewer wide"><div class="o2vb o2chart">${head}<div class="o2cols">${cols}</div></div></div>`;
}

/* ── pencil destinations: Changes, Approvals, Health ─────────────────────── */
function o2PanelShell(title, body, extra){
  return `<div class="o2panel" role="dialog" aria-label="${o2Esc(title)}"><h4>${o2Esc(title)}${extra || ""}<button type="button" class="o2ib o2x" data-o2act="panelclose" aria-label="Close">${O2_X}</button></h4>${body}</div>`;
}
function o2ChangesHtml(n, d){
  const refs = o2Subtree(n.ref, d);
  const rows = (typeof INDEX !== "undefined" && Array.isArray(INDEX) ? INDEX : [])
    .filter(e => e && e.ref && refs.has(e.ref))
    .slice().sort((a, b) => (b.ts_ms || 0) - (a.ts_ms || 0)).slice(0, 60);
  const nameOf = r => (d.byRef.get(r) || {}).name || "";
  const label = e => e.event === "domain_minted" ? `${o2Esc(e.name || nameOf(e.ref))} created`
    : e.op === "retire" ? `${o2Esc((e.before && e.before.name) || nameOf(e.ref))} retired`
    : e.op === "rename" && e.before && e.after ? `${o2Esc(e.before.name)} renamed ${o2Esc(e.after.name || "")}`
    : e.op === "move" || e.op === "reparent" ? `${o2Esc((e.before && e.before.name) || nameOf(e.ref))} moved`
    : `${o2Esc(nameOf(e.ref) || (e.op || e.event || "changed"))} ${o2Esc(e.op && nameOf(e.ref) ? e.op : "")}`.trim();
  let body = "";
  if (!rows.length) body = `<div class="o2quiet">No changes yet</div>`;
  else {
    let day = "";
    body = rows.map(e => {
      const dd = o2Date(e.ts_ms);
      const head = dd !== day ? `<div class="o2gl">${o2Esc(dd)}</div>` : "";
      day = dd;
      const hh = e.ts_ms ? new Date(Number(e.ts_ms)).toISOString().slice(11, 16) : "";
      return `${head}<div class="o2prow"><span class="dt">${hh}</span><span>${label(e)}</span></div>`;
    }).join("");
  }
  const from = (typeof META !== "undefined" && META && META.history_complete_from_ms) ? o2Date(META.history_complete_from_ms) : "";
  if (from) body += `<div class="o2band">Reconstructed before ${o2Esc(from)}</div>`;
  return o2PanelShell("Changes", body);
}
function o2ApprovalsHtml(){
  const st = o2S();
  if (typeof S.props === "undefined" || S.props === null){
    if (typeof loadProposals === "function" && !st.propsAsked){ st.propsAsked = true; loadProposals(false); }
    return o2PanelShell("Approvals", `<div class="o2quiet">Checking…</div>`);
  }
  const props = Array.isArray(S.props) ? S.props : [];
  const pend = props.filter(p => p.status === "pending");
  const done = props.filter(p => p.status !== "pending").slice(0, 6);
  const sum = p => o2Esc(p.summary || p.title || ((p.kind || "") + " " + ((p.args && (p.args.name || p.args.id)) || "")).trim());
  const rowP = p => `<div class="o2prow"><b>${o2Esc(p.kind || "")}</b><span>${sum(p)}<span class="o2pact"><button type="button" class="btn" data-o2decide="${o2Esc(p.id)}" data-o2ok="1" ${S.propBusy === p.id ? "disabled" : ""}>Approve</button><button type="button" class="btn" data-o2decide="${o2Esc(p.id)}" data-o2ok="0" ${S.propBusy === p.id ? "disabled" : ""}>Reject</button></span></span></div>`;
  const rowD = p => `<div class="o2prow"><b>${o2Esc(p.kind || "")}</b><span>${sum(p)} <span class="pill ${p.status === "approved" ? "p-ok" : "p-mut"}">${o2Esc(p.status)}</span>${p.status === "failed" && p.result && p.result.error ? `<div class="o2quiet" style="padding:2px 0 0">${o2Esc(p.result.error)}</div>` : ""}</span></div>`;
  const body = `<div class="o2gl">Waiting</div>${pend.length ? pend.map(rowP).join("") : `<div class="o2quiet">Nothing waiting</div>`}${done.length ? `<div class="o2gl">Decided</div>${done.map(rowD).join("")}` : ""}${S.propError ? `<div class="o2quiet">${o2Esc(S.propError)}</div>` : ""}`;
  return o2PanelShell("Approvals", body);
}
/* Health for one subtree (plan S84-S86): the structure check the studio runs,
   then what the server finds by reading charters: departments with no charter,
   one-line charters, and overlapping siblings. Names throughout; a name opens
   that department. */
function o2HealthHtml(n, d){
  const st = o2S();
  const sim = (typeof simulate === "function" && S.draft) ? simulate(S.draft.ops || []) : null;
  const names = [...o2Subtree(n.ref, d)].map(r => (d.byRef.get(r) || {}).name).filter(Boolean);
  const sev = s => s === "block" ? "var(--block)" : s === "warn" ? "var(--warn)" : "var(--ok)";
  const dot = (color, html) => `<div class="o2prow"><span class="o2dot" style="background:${color}"></span><span>${html}</span></div>`;
  let body;
  if (!sim || sim.pending) body = `<div class="o2quiet">Checking…</div>`;
  else if (sim.error) body = `<div class="o2quiet">The check could not run</div><div style="padding:0 8px"><button type="button" class="btn" data-o2act="health">Try again</button></div>`;
  else {
    const mine = (sim.findings || []).filter(f => names.some(nm => String(f.subject || "").indexOf(nm) !== -1));
    body = `<div class="o2gl">Structure</div>` + (mine.length ? mine.map(f => dot(sev(f.sev), o2Esc(f.subject || f.code || ""))).join("") : dot("var(--ok)", `Nothing flagged for ${o2Esc(n.name)}`));
  }
  const h = st.health[n.ref];
  if (!h) o2LoadHealth(n.ref);
  const link = x => `<button type="button" class="o2lnk" data-o2ref="${o2Esc(x.ref)}">${o2Esc(x.name)}</button>`;
  if (!h || (!h.data && !h.error)) body += `<div class="o2gl">Charters</div><div class="o2quiet">Checking…</div>`;
  else if (h.error) body += `<div class="o2gl">Charters</div><div class="o2quiet">Sutra did not answer</div><div style="padding:0 8px"><button type="button" class="btn" data-o2act="healthretry">Try again</button></div>`;
  else {
    const un = h.data.unowned || [], one = h.data.one_line || [], ov = h.data.overlaps || [];
    body += `<div class="o2gl">Charters</div>`;
    if (!un.length && !one.length && !ov.length) body += dot("var(--ok)", `Every department under ${o2Esc(n.name)} has a charter`);
    if (un.length) body += dot("var(--warn)", `No charter: ${un.map(link).join(", ")}`);
    if (one.length) body += dot("var(--warn)", `One line: ${one.map(link).join(", ")}`);
    if (ov.length) body += ov.map(o => dot("var(--warn)", `${o2Esc(o.a)} and ${o2Esc(o.b)} overlap`)).join("");
  }
  return o2PanelShell("Health", body);
}
function o2PanelHtml(n, d){
  const st = o2S();
  if (st.panel === "changes") return o2ChangesHtml(n, d);
  if (st.panel === "approvals") return o2ApprovalsHtml();
  if (st.panel === "health") return o2HealthHtml(n, d);
  return "";
}

/* ── the screen ───────────────────────────────────────────────────────────── */
function o2ScreenHtml(){
  const st = o2S();
  if (!st.loaded && !st.loading && !st.error) loadOrg2(false);
  const d = o2Data();
  const n = st.sel ? d.byRef.get(st.sel) : null;
  const dept = n ? st.dept[n.ref] : null, err = n ? st.deptErr[n.ref] : null;
  let banner = st.error
    ? `<div class="o2line warn"><span>Sutra is not reachable</span><button type="button" class="btn" data-o2act="retry">Retry</button></div>` : "";
  if (st.flash) banner += `<div class="o2line acc"><span>${o2Esc(st.flash)}</span><button type="button" class="o2ib o2x" data-o2act="flashclose" aria-label="Dismiss">${O2_X}</button></div>`;
  const left = `<div class="o2left">${o2SearchHtml()}${(st.loading && !d.root) ? o2SkelTree() : o2TreeHtml()}</div>`;
  let content;
  if (!d.root && !st.loading){
    content = `<div class="o2strip"><h2>Sutra</h2></div><div class="o2body">${o2ViewerShell("Sutra", o2Svg("dept"), `<div class="o2vb"><div class="o2empty">${o2Svg("dept")}<h1>No departments yet</h1></div></div>`)}</div>`;
  } else if (!n){
    content = `<div class="o2strip"><div class="o2skel" style="width:170px;height:18px;margin:0"></div></div><div class="o2body"><div class="o2list">${[110, 140, 96, 128].map(w => `<div class="o2skel" style="width:${w}px"></div>`).join("")}</div><div class="o2viewer" aria-busy="true"></div></div>`;
  } else {
    const wide = !st.sheet && (st.view === "chart" || st.view === "app" || st.view === "page");
    content = `${o2StripHtml(n, d, dept)}<div class="o2body${wide ? " wide" : ""}">${wide ? "" : o2ListHtml(n, d, dept, err)}${o2ViewerHtml(n, d, dept, err)}${st.panel ? o2PanelHtml(n, d) : ""}</div>`;
  }
  return `<div class="o2${st.error ? " off" : ""}">${left}<div class="o2main">${banner}${content}</div></div>`;
}

/* ── registration + handlers ──────────────────────────────────────────────── */
if (typeof document !== "undefined" && document.addEventListener){
  const SEL = "[data-o2tog],[data-o2ref],[data-o2act],[data-o2filed],[data-o2charter],[data-o2doc],[data-o2app],[data-o2more],[data-o2decide],[data-o2filter],[data-o2chip]";
  document.addEventListener("click", (ev) => {
    if (!S.o2 || S.screen !== "org2") return;
    const t = ev.target && ev.target.closest ? ev.target.closest(SEL) : null;
    if (!t || !t.closest(".o2")) return;                 /* never outside this screen */
    const st = o2S(), ds = t.dataset || {}, d = o2Data();
    if (ds.o2tog !== undefined){ ev.preventDefault(); ev.stopPropagation(); const ex = o2Expanded(); if (ex.has(ds.o2tog)) ex.delete(ds.o2tog); else ex.add(ds.o2tog); o2Render(); return; }
    if (ds.o2ref !== undefined){ ev.preventDefault(); o2Select(ds.o2ref); return; }
    if (ds.o2more !== undefined){ st.more[ds.o2more] = true; o2Render(); return; }
    if (ds.o2charter !== undefined){ ev.preventDefault(); o2OpenCharter(ds.o2charter); return; }
    if (ds.o2doc !== undefined){ ev.preventDefault(); o2OpenDoc(ds.o2doc, ds.o2title); return; }
    if (ds.o2filed !== undefined){ ev.preventDefault(); if (o2IsDoc(ds.o2filed)) o2OpenDoc(ds.o2filed, ds.o2title); else if (o2IsPage(ds.o2filed)) o2OpenPage(ds.o2filed, ds.o2title); return; }
    if (ds.o2app !== undefined){ ev.preventDefault(); const apps = st.apps[st.sel] || []; const m = apps.find(x => x.id === ds.o2app); if (m) o2OpenApp(m); return; }
    if (ds.o2decide !== undefined){ if (typeof decideProposal === "function") decideProposal(ds.o2decide, ds.o2ok === "1"); return; }
    if (ds.o2filter !== undefined){ st.filter.open = !st.filter.open; o2Render(); return; }
    if (ds.o2chip !== undefined){
      const [axis, v] = String(ds.o2chip).split(":");
      const arr = st.filter[axis]; if (!arr) return;
      const i = arr.indexOf(v); if (i === -1) arr.push(v); else arr.splice(i, 1);
      o2ApplyFilter(); return;
    }
    const act = ds.o2act;
    if (act === "retry"){ loadOrg2(true); return; }
    if (act === "retrydept"){ if (st.sel){ delete st.deptErr[st.sel]; o2Render(); o2LoadDept(st.sel, true); } return; }
    if (act === "chart"){ o2UnmountEditor(); st.view = st.view === "chart" ? "charter" : "chart"; st.doc = null; st.app = null; st.other = null; st.page = null; st.sheet = null; st.menu = false; o2Render(); return; }
    if (act === "pencil"){ st.menu = !st.menu; o2Render(); return; }
    if (act === "charter"){ o2CloseViewer(); return; }
    if (act === "close"){ o2CloseViewer(); return; }
    if (act === "clearlq"){ st.lq = ""; o2Render(); return; }
    if (act === "filterclear"){ st.filter.kind = []; st.filter.state = []; o2ApplyFilter(); return; }
    if (act === "flashclose"){ st.flash = null; o2Render(); return; }
    if (act === "reload"){ if (st.doc) o2OpenDoc(st.doc.path, st.doc.title); return; }
    if (act === "openapp"){ if (st.app && typeof modOpen === "function") modOpen(st.app); return; }
    if (act === "rename" || act === "move" || act === "create"){ o2OpenSheet(act); return; }
    if (act === "sheetclose"){ st.sheet = null; o2Render(); return; }
    if (act === "request"){ o2SendRequest(); return; }
    if (act === "healthretry"){ if (st.sel){ delete st.health[st.sel]; o2LoadHealth(st.sel, true); o2Render(); } return; }
    if (act === "changes" || act === "approvals" || act === "health"){ st.panel = st.panel === act ? null : act; st.menu = false; o2Render(); return; }
    if (act === "panelclose"){ st.panel = null; o2Render(); return; }
  });
  document.addEventListener("input", (ev) => {
    if (!S.o2 || S.screen !== "org2") return;
    const el = ev.target;
    if (!el || !el.dataset || !el.closest || !el.closest(".o2")) return;
    if (el.dataset.o2q !== undefined){ o2S().q = String(el.value || ""); o2SearchSoon(); o2Render(); return; }
    if (el.dataset.o2lq !== undefined){ o2S().lq = String(el.value || ""); o2Render(); return; }
    if (el.dataset.o2sname !== undefined){ const sh = o2S().sheet; if (sh){ sh.name = String(el.value || ""); sh.error = null; } return; }
  });
  document.addEventListener("change", (ev) => {
    if (!S.o2 || S.screen !== "org2") return;
    const el = ev.target;
    if (!el || !el.dataset || !el.closest || !el.closest(".o2")) return;
    if (el.dataset.o2starget !== undefined){ const sh = o2S().sheet; if (sh){ sh.target = String(el.value || ""); sh.error = null; o2Render(); } }
  });
  document.addEventListener("keydown", (ev) => {
    if (!S.o2 || S.screen !== "org2") return;
    if (ev.key === "Escape" && (S.o2.menu || S.o2.panel || S.o2.filter.open || S.o2.sheet)){ S.o2.menu = false; S.o2.panel = null; S.o2.filter.open = false; S.o2.sheet = null; o2Render(); return; }
    if (ev.key === "Enter" && ev.target && ev.target.dataset){
      if (ev.target.dataset.o2sname !== undefined && ev.target.closest && ev.target.closest(".o2")){ ev.preventDefault(); o2SendRequest(); return; }
      if (ev.target.dataset.o2ref !== undefined && ev.target.closest && ev.target.closest(".o2")) o2Select(ev.target.dataset.o2ref);
    }
  });
}
