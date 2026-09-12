/* 18-modules.js -- Org > Apps v1.2: apps live within Departments.
   Design of record:
   holding/departments/experience/desktop-app/2026-09-08-modules-design.md
   (§v12, D-M11..D-M22). Program: holding/plans/apps-program/PROGRAM.md.

   NAMING. The user-facing word is App (D-M22). The internal name stays
   `module`: this file, SCREENS.modules, flags.modules, /api/modules and
   ~/.sutra-ui/modules/<id>/module.json. Only strings a person reads say App.

   An app is a finished product built inside Sutra: a chat with standing
   instructions, a page rendered from index.html, or a link to a system screen.
   THE FOLDER IS THE APP (D-M1) and EVERY APP BELONGS TO ONE DEPARTMENT (D-M13).
   This screen renders what GET /api/modules?department=… returns -- the
   grouping is the server's; the client's DOMAINS is only the tree SHAPE for
   the rail. There is no client-side registry, not even as a fallback.

   Shape (D-M16/D-M17): the facets bar Live · Draft · Directory · Apps on top;
   under it the Directory's .dpage grid -- the shared dirRail on the left with
   the app rows nested under their owning department and subtree counts, and on
   the right either the selected department's apps (Apps · In sub-departments ·
   System · Unassigned) or the open app: a header (chip · crumb · name · tagline
   · kind · status · one small "Edit in chat" button) and then the app itself,
   nothing else. Edit and + New app open seeded chats (D-M17/18/19) whose first
   line is the routing pin; move and archive are things you say in that chat.

   Attributes are data-mod* ONLY and the handlers require .mod (codex P15/P16):
   07-loaders.js owns [data-view], [data-ref] and #dirQ for the Departments
   screen and would fire on them here too.

   State on S: modules (the API answer), modKey (the query it answers),
   modWant (the query in flight), modDept (null = root | "unassigned" | ref),
   modSubtree (default on), modSel (open app id), modShowArchived, modQ (the
   rail search -- its own field, never S.dirQ), modErr, modFrameNonce,
   modNarrow (test/override for the narrow pane). */

const MOD_API = "/api/modules";
const MOD_SYS_PREFIX = "sys-";
const MOD_UNASSIGNED = "unassigned";
const MOD_HOME_DEFAULT = "~/.sutra-ui/modules";
const MOD_NARROW_PX = 720;               /* the .dpage container query (panel.css) */
const MOD_KIND_HELP = {
  chat: "a conversation that opens with these instructions as its first turn",
  page: "a page you wrote as index.html, shown inside the app",
  link: "a shortcut to a screen this app already has"
};
const MOD_SCREEN_LABEL = { terminal: "Terminal", settings: "AI Provider" };

function modS(){ return (typeof S !== "undefined" && S) ? S : null; }
function modEsc(x){ return (typeof esc === "function") ? esc(x) : String(x == null ? "" : x); }
function modChip(p){ return (typeof dirChip === "function") ? dirChip(p) : String(p || ""); }
function modRender(){
  if (typeof scheduleRender === "function") scheduleRender();
  else if (typeof render === "function") render();
}
function modTheme(){
  try {
    const t = document.documentElement && document.documentElement.getAttribute
      ? document.documentElement.getAttribute("data-theme") : null;
    if (t === "dark" || t === "light") return t;
    if (typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: light)").matches) return "light";
  } catch (e) { /* vm stub */ }
  return "dark";
}
function modIsSys(m){ return !!m && String(m.id).startsWith(MOD_SYS_PREFIX) && !m.reserved; }
function modHome(s){ return (s.modules && s.modules.home) || MOD_HOME_DEFAULT; }
function modIsNarrow(s){
  if (s && typeof s.modNarrow === "boolean") return s.modNarrow;
  try {
    const el = document.getElementById("scBody");
    if (el && el.getBoundingClientRect) return el.getBoundingClientRect().width < MOD_NARROW_PX;
  } catch (e) { /* vm stub */ }
  return false;
}
/* A chat provider must be configured before a seeded chat can open (codex r1
   P8). SETTINGS is null until /api/settings answers; that case fails OPEN, the
   way the flag guards do, because "not loaded yet" is not "not configured". */
function modProviderReady(){
  if (typeof SETTINGS === "undefined" || !SETTINGS) return true;
  return !!SETTINGS.provider;
}

/* ── data ─────────────────────────────────────────────────────────────────── */
function modQuery(s){
  let q = "?subtree=" + (s.modSubtree === false ? "0" : "1");
  if (s.modDept) q += "&department=" + encodeURIComponent(s.modDept);
  if (s.modShowArchived) q += "&include=archived";
  return q;
}
async function loadModules(force){
  const s = modS(); if (!s) return;
  const key = modQuery(s);
  if (!force && s.modules && !s.modules.error && s.modKey === key) return;
  if (s.modLoading && s.modWant === key) return;
  s.modWant = key; s.modLoading = true;
  let next;
  try {
    const data = await apiGet(MOD_API + key);
    if (s.modWant !== key) return;
    next = { modules: Array.isArray(data.modules) ? data.modules : [],
             groups: data.groups || { here: [], below: [], system: [], unassigned: [] },
             counts_by_ref: data.counts_by_ref || {}, unassigned_count: data.unassigned_count || 0,
             root: data.root || null, department: data.department || null,
             count_user: data.count_user || 0, archived: data.archived || 0,
             home: data.home || "", error: null };
  } catch (e) {
    if (s.modWant !== key) return;
    next = { modules: [], groups: null, counts_by_ref: {}, unassigned_count: 0, root: null, department: null,
             count_user: 0, archived: 0, home: "", error: (e && e.message) || String(e) };
  }
  s.modules = next; s.modKey = key; s.modLoading = false;
  modRender();
}
function modAll(s){ return (s.modules && s.modules.modules) || []; }
function modById(s, id){ return modAll(s).find(m => m.id === id) || null; }
function modSelected(s){ return s.modSel ? modById(s, s.modSel) : null; }

/* ── Apps frameworks kit (design 2026-09-11-apps-frameworks-design.md) ─────
   GET /api/modules/frameworks once per screen life: version, digest, the
   per-kind profile paths, the check runner, the screens a link may open and
   the token names a page may use. null = no kit on this server (an older
   bundle): every seed degrades to the pre-kit text. */
function modFrameworks(s){ return s && s.frameworks ? s.frameworks : null; }
function modEnsureFrameworks(s){
  if (!s || s.frameworks !== undefined || s.modFwWant || typeof apiGet !== "function") return;
  s.modFwWant = true;
  Promise.resolve(apiGet(MOD_API + "/frameworks")).then(fw => { s.frameworks = fw || null; modRender(); },
                                                        () => { s.frameworks = null; });
}
/* The checks chip in an app header: one read per app + updated_at, read-only on the server. */
function modChecksFor(s, m){
  if (!s.modChecks) s.modChecks = {};
  const key = m.id + "@" + (m.updated_at || "");
  const have = s.modChecks[key];
  if (have !== undefined) return have;
  s.modChecks[key] = null;                                   /* in flight */
  if (typeof apiGet === "function")
    Promise.resolve(apiGet(MOD_API + "/" + encodeURIComponent(m.id) + "/checks")).then(r => { s.modChecks[key] = r || false; modRender(); },
                                                                                          () => { s.modChecks[key] = false; });
  return null;
}
/* Apps frameworks (D75, amended 2026-09-12: "whenever a task is given, a
   framework should be there ... if not, then a framework should be created").
   An app built before the kit gets its framework as the FIRST step of the task,
   never through a control: the server writes the stamp and the record (every
   unanswered row "not recorded"), the list is re-read, and the task goes on
   from the stamped row. The panel never writes a stamp itself. Internal: the
   only caller is modEdit. */
async function modAdopt(m){
  const s = modS(); if (!s || !m) return null;
  s.modErr = null;
  let row = null;
  try { row = await apiPost(MOD_API + "/" + encodeURIComponent(m.id), { action: "migrate_kit" }); }
  catch (e) { s.modErr = "Could not bring this app into the frameworks: " + ((e && e.message) || e); modRender(); return null; }
  await loadModules(true);
  return row || true;
}
function modChecksChip(s, m){
  if (!m.frameworkKit || m.building || m.reserved || modIsSys(m)) return "";
  const r = modChecksFor(s, m);
  if (r === null) return `<span class="mod-checks" title="reading the checks">checks…</span>`;
  if (!r || !r.live) return "";
  const live = r.live, sum = live.summary || {};
  let cls = "ok", text = `${sum.must_fix_pass || 0} checks pass`;
  if (live.blocked){ cls = "fix"; text = `${live.fails.length} to fix`; }
  else if ((live.waived || []).length){ text += ` · ${live.waived.length} waived`; }
  const stale = r.recorded && r.recorded.ran && r.recorded.summary && !live.blocked && !/^\s*\d+ must-fix pass, 0 fail/.test(r.recorded.summary);
  if (r.recorded && r.recorded.ran === false){ cls = live.blocked ? "fix" : "stale"; text += " · not yet recorded"; }
  else if (stale){ cls = "stale"; text += " · record out of date"; }
  const title = (live.fails || []).length ? "must-fix: " + live.fails.join(", ") : "run the check from Edit in chat to record it";
  return `<span class="mod-checks ${cls}" title="${modEsc(title)}">${modEsc(text)}</span>`;
}

/* The department tree for the rail: DOMAINS, live only, sorted like dirData. */
function modTree(){
  const all = (typeof DOMAINS !== "undefined" && Array.isArray(DOMAINS)) ? DOMAINS : [];
  const live = all.filter(d => d && d.ref && d.status !== "retired");
  const byRef = new Map(live.map(d => [d.ref, d]));
  const kids = new Map();
  live.forEach(d => {
    const p = d.parent_ref;
    if (p && byRef.has(p)){ if (!kids.has(p)) kids.set(p, []); kids.get(p).push(d); }
  });
  kids.forEach(v => v.sort((a, b) => String(a.path||"").localeCompare(String(b.path||""), undefined, { numeric: true })));
  const root = live.find(d => !d.parent_ref || !byRef.has(d.parent_ref)) || null;
  return { live, byRef, kids, root };
}
function modAncestors(tree, ref){
  const out = new Set(); let cur = ref;
  while (cur && tree.byRef.has(cur) && !out.has(cur)){ out.add(cur); cur = tree.byRef.get(cur).parent_ref; }
  return out;
}
function modDeptOf(s, ref){
  const d = s.modules && s.modules.department;
  if (d && d.ref === ref) return d;
  const t = modTree().byRef.get(ref);
  return t ? { ref: t.ref, path: t.path, name: t.name, description: t.description || "" } : null;
}

/* Settings sections, derived from the plane spec at render (D-M9). */
function modSettingsSections(){
  if (typeof DEST_PLANES === "undefined" || !DEST_PLANES || !Array.isArray(DEST_PLANES.settings)) return [];
  const out = [];
  for (const g of DEST_PLANES.settings){
    for (const r of (g.rows || (g.screen ? [g] : []))){
      if (!r || !r.screen) continue;
      out.push({ screen: r.screen, group: g.group || "", label: modScreenLabel(r.screen) });
    }
  }
  return out;
}
function modScreenLabel(id){
  if (MOD_SCREEN_LABEL[id]) return MOD_SCREEN_LABEL[id];
  if (typeof TITLES !== "undefined" && TITLES && Array.isArray(TITLES[id]) && TITLES[id][0]) return TITLES[id][0];
  return id;
}
function modLinkOpenable(m){
  const scr = m && m.surface && m.surface.screen;
  if (!scr || scr === "terminal" || scr === "usage") return false;
  return typeof SCREENS !== "undefined" && !!SCREENS[scr];
}

/* ── seeds (D-M17, D-M18, D-M19) ──────────────────────────────────────────── */
function modPinLine(dept){
  return `ROUTING PIN — file this session under ${modChip(dept.path)} ${dept.name} (${dept.ref}). Do not re-classify.`;
}
function modCharterLine(ref){
  if (typeof dirChartersFor !== "function") return "";
  const c = dirChartersFor(ref)[0];
  if (!c) return "";
  return (c.title || "") + (c.purpose ? " — " + c.purpose : "");
}
/* The department pin travels ONLY as the `pin` option on submitTurn (routing
   pin honoured by /api/classify): no seed text ever carries a ref (Apps
   frameworks design v1 R1-P3; the leak test fails on ROUTING PIN / dref-). */
function modDeptWords(dept){ return dept ? `${modChip(dept.path)} ${dept.name}` : "Unassigned"; }
function modCheckLine(s, kind, folder){
  const fw = modFrameworks(s);
  return fw ? `Before you say done, run  python3 ${fw.check} ${folder} --kind ${kind}  (or the sutra_app_check tool). Fix every must-fix result and run it again; read me the suggestions as they are, they do not block.` : "";
}
function modEditSeed(s, m){
  const dept = m.department ? modDeptOf(s, m.department.ref) || m.department : null;
  const fw = modFrameworks(s);
  const where = dept ? `in department ${modDeptWords(dept)}` : "with no department yet (Unassigned)";
  const folder = `${modHome(s)}/${m.id}/`;
  const files = m.kind === "page" ? `module.json (kind page · status ${m.status}) · index.html` : `module.json (kind ${m.kind} · status ${m.status})`;
  const charter = dept ? modCharterLine(dept.ref) : "";
  const kit = fw && m.frameworkKit ? [
    `Also: APP.md — the record of what this app is for, how it is checked and who keeps it. Read it first.`,
    `Framework: ${fw.kinds[m.kind] || fw.dir}${m.kind === "page" ? ". Everything stays inline: no network, no storage, only the app's own colour names (" + (fw.tokens || []).map(t => "--" + t).join(" ") + "), a body fragment." : m.kind === "chat" ? ". The only thing that changes is the opening message in module.json surface.instructions, still the visible first message, under 4000 characters." : ". The only things that change are the screen it opens, the name and the line under it."}`,
    `APP.md carries a stamp on its first line. Never edit that line, and never hand-write updated_ms or bump version — the app does both when this session ends.`,
    (m.frameworkKit.version && fw.version && m.frameworkKit.version !== fw.version)
      ? `This app was built on kit ${m.frameworkKit.version}; installed is ${fw.version}. Say in one line what changed and what it means for this app, and ask whether to update the record. Write it only if I say yes and add a Changes line saying so. If I say no, the older rules still apply.`
      : m.frameworkKit.adopted
        ? `This app adopted the frameworks on ${m.frameworkKit.adopted}; its record was filled from what the app already knew, and every row that reads "not recorded" is yours to fill from module.json${m.kind === "page" ? " and index.html" : ""} and from me.`
        : `This app was built on kit ${m.frameworkKit.version || fw.version}, the one installed; no migration to offer.`,
    `When you change anything, update the matching APP.md rows in the same turn and add one dated line at the top of ## Changes.`,
  ] : [];
  return `You are editing the app "${m.name}" (${m.kind}) ${where}.\n`
    + `Folder: ${folder}  (the folder IS the app)\n`
    + `Files: ${files}\n`
    + (charter ? `Department charter: ${charter}\n` : "")
    + (kit.length ? kit.join("\n") + "\n" : "")
    + `Rules: edit files in place; keep module.json valid (never change id); tell me what changed when done.\n`
    + `You can also move this app to another department or archive it — tell me and I apply it as a structured change.\n`
    + (kit.length ? `First: read APP.md, then module.json${m.kind === "page" ? ", then index.html" : ""}, then ask me what should change.\n${modCheckLine(s, m.kind, folder)}\nReply in plain words, no headers and no status lines. Say "app", never the internal word.`
                  : (m.kind === "page" ? `First: read both files, then ask me what should change.` : `First: read the file, then ask me what should change.`));
}
/* New app, kit present: the server has ALREADY materialized the folder (a
   starter, APP.md with the stamp, module.json); this seed opens inside it. */
function modNewSeed(s, dept, kind, row){
  const fw = modFrameworks(s);
  const where = dept ? `in ${modDeptWords(dept)}` : "with no department yet (Unassigned)";
  if (!fw || !kind || !row){
    return `Create a new app ${where}.\n`
      + `Folder root: ${modHome(s)}/  (one folder per app; the folder IS the app)\n`
      + `Ask me one question at a time: (1) what kind — chat (a conversation that opens with standing instructions), page (an index.html shown inside the app) or link (a shortcut to a screen); (2) what it should do; (3) a name.\n`
      + `Then write <slug>/module.json {id, name, tagline, kind, status:"draft", version:1, surface} and index.html if it is a page. Report the folder when done.`;
  }
  const folder = `${modHome(s)}/${row.id}/`;
  const profile = fw.kinds[kind] || fw.dir;
  const tail = `\n${modCheckLine(s, kind, folder)}\nReport ${kind === "page" ? "what the page shows when it opens" : kind === "chat" ? "the first words someone will see" : "the row and the screen it opens"}, and the check result. Plain words, no headers, no status lines. Say "app", never the internal word.`;
  if (kind === "page"){
    return `This is a new page app ${where}. Its folder is ready: index.html (a starter to replace), APP.md (the record of what it is for), module.json.\n`
      + `Folder: ${folder}\nRead ${profile} now and follow it.\n\n`
      + `Ask me six questions, one at a time, and wait for each answer:\n`
      + `1. Who opens this, and what are they trying to get done?\n2. Say it in one line someone else would understand. What should it be called?\n3. When it opens, what is the first thing on the screen?\n4. What information does it work with, and where does that live? Paste one real row, the smallest example it has to handle.\n5. What should it show when a number is missing or there is nothing to show, and what should I do then?\n6. You open it tomorrow. What do you see that tells you it worked?\n\n`
      + `Then send me ONE message with the rest already filled in, for me to correct in a line or two: how I would use it once, the shape you will use, the controls (one per line, starting with a dash), whether anything resets when I close it, which rows count as good, warning or blocked, which part of answer 6 must still be true after a future edit, who keeps it and the date to look at it again, what it replaces, and the department above. Ask whether it names a real borrower or account, and whether anyone besides me will use it, only at the very end.\n\n`
      + `Then write index.html (a body fragment: one root element with lang, inline style and script, the data baked in, images as data: URLs, colour, type and radius only from: ${(fw.tokens || []).map(t => "--" + t).join(" ")}), fill every row of APP.md, and set name and tagline in module.json. Change nothing else in module.json and never touch the first line of APP.md. This page has no network and no storage.`
      + tail;
  }
  if (kind === "chat"){
    return `This is a new chat app ${where}. Its folder is ready: module.json (the opening message lives in it) and APP.md (the record).\n`
      + `Folder: ${folder}\nRead ${profile} now and follow it.\n\n`
      + `Ask me one question at a time, in this order:\n`
      + `1. Who opens this chat and what are they trying to get done? What do they do today without it?\n2. Walk me through one use, start to finish. What is the smallest real thing someone will bring to it?\n3. What information does it work with and where does that live? Which folder may this chat read and write?\n4. Anything it must never do on its own: run commands, install things, send messages? When the information is missing or wrong, what should it say instead of guessing?\n5. Who is it talking to, and what must it never say?\n6. You open it tomorrow: what in the opening message tells you it worked?\n`
      + `Then send me ONE message with the rest filled in, for me to correct: the name and one line, who keeps it and the review date, what it replaces, the department above, and the opening message itself in full. Ask whether it names a real borrower or account, and whether anyone besides me will use it, at the end.\n\n`
      + `The opening message IS what the person reads first; there is no hidden prompt. Write it to that person: one line saying what it does, a short list of what it never does, then one question. Under 4000 characters. No keys, no account numbers. Every command it may run goes in the APP.md Backend row, word for word.\n`
      + `Write the opening message into module.json surface.instructions, set name and tagline, fill every row of APP.md. Create data-policy.json only if this chat calls one of the app's own services: one entry per call with the call, why, what could go wrong, and the check that covers it. Change nothing else in module.json and never touch the first line of APP.md.`
      + tail;
  }
  return `This is a new link app ${where}: a row that opens a screen this app already has. It has no page and no instructions. Its folder is ready: module.json and APP.md.\n`
    + `Folder: ${folder}\nRead ${profile} now and follow it.\n\n`
    + `Screens it can open: ${(fw.screens || []).join(", ")}. Never terminal or usage.\n\n`
    + `Ask me one question at a time, in this order:\n`
    + `1. Which screen should it open? (offer the list above)\n2. What should the row say, and one line under it?\n3. Who opens it and what are they after?\n4. What tells you it is the right shortcut, and what should you see if that screen is empty or gone?\n5. What does that screen show and where does that live?\n6. It files under ${modDeptWords(dept)}. Keep it there, or move it?\n`
    + `Then send me ONE message with the rest filled in: who keeps it and the review date, what it replaces by hand today. Ask whether anyone besides me will use it at the end.\n\n`
    + `Two answers are fixed by the kind; state them and ask for a nod: files are module.json only, plus the record; what must still work is "the row opens the screen; click Open and land on it".\n`
    + `Set surface.screen, name and tagline in module.json and fill every row of APP.md. Change nothing else in module.json and never touch the first line of APP.md.`
    + tail;
}
function modOpenSeededChat(s, title, cwd, seed, app){
  if (!modProviderReady()){ s.modErr = "Connect a chat provider in Settings to create or edit apps."; modRender(); return null; }
  if (typeof goDest === "function") goDest("chats");
  const dept = app && app.department_ref ? app.department_ref : null;
  const sess = (typeof newSession === "function") ? newSession(cwd || "", dept) : null;
  if (!sess) return null;
  sess.title = title;
  sess.app = app;                                     /* read by the done handler (01-state.js) */
  if (typeof submitTurn === "function") submitTurn(seed, sess.id, dept ? { pin: { department_ref: dept } } : undefined);
  if (typeof render === "function") render();
  return sess;
}
function modEditOpen(s, m){
  const dept = m.department ? m.department.ref : null;
  return modOpenSeededChat(s, "Edit · " + m.name, modHome(s) + "/" + m.id, modEditSeed(s, m),
                           { id: m.id, mode: "edit", department_ref: dept });
}
function modEdit(m){
  const s = modS(); if (!s || !m || m.reserved || modIsSys(m)) return null;
  if (!modFrameworks(s) || m.frameworkKit) return modEditOpen(s, m);
  /* D75 amendment: the task brings its framework. An app without a stamp is
     adopted FIRST, then the chat opens on the stamped row. The provider gate
     runs before the write, so a click without a provider mutates nothing; one
     adoption in flight per app, so a double click opens one chat; a failed
     adoption opens no chat -- a task never runs without its framework. */
  if (!modProviderReady()){ s.modErr = "Connect a chat provider in Settings to create or edit apps."; modRender(); return null; }
  s.modAdopting = s.modAdopting || {};
  if (s.modAdopting[m.id]) return s.modAdopting[m.id];
  const p = modAdopt(m).then(row => {
    delete s.modAdopting[m.id];
    if (!row) return null;
    const fresh = modById(s, m.id) || (typeof row === "object" ? Object.assign({}, m, row) : null);
    if (!fresh || !fresh.frameworkKit){ s.modErr = "This app did not take the frameworks; nothing was opened."; modRender(); return null; }
    return modEditOpen(s, fresh);
  });
  s.modAdopting[m.id] = p;
  return p;
}
function modNewDept(s){
  const ref = (s.modDept && s.modDept !== MOD_UNASSIGNED) ? s.modDept : (s.modules && s.modules.root ? s.modules.root.ref : null);
  return ref ? modDeptOf(s, ref) : null;
}
/* + New app. With the kit: show the kind picker (three buttons, one line
   each); the pick creates the folder on the server FIRST, then opens the chat
   inside it (D-F3). Without the kit (older server): the pre-kit seeded chat. */
function modNew(){
  const s = modS(); if (!s) return null;
  if (!modProviderReady()){ s.modErr = "Connect a chat provider in Settings to create or edit apps."; modRender(); return null; }
  if (modFrameworks(s)){ s.modPick = "kind"; s.modErr = null; modRender(); return null; }
  const dept = modNewDept(s);
  return modOpenSeededChat(s, "New app · " + (dept ? dept.name : "Unassigned"), modHome(s), modNewSeed(s, dept),
                           { id: null, mode: "new", department_ref: dept ? dept.ref : null });
}
function modProvisional(kind, screen){
  const d = new Date(), p = n => String(n).padStart(2, "0");
  /* seconds plus a short random tail: two creates in one second never collide (codex R2 P4) */
  const tail = Math.floor(Math.random() * 46656).toString(36).padStart(3, "0").slice(-3);
  const id = `${kind}-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}-${tail}`;
  const name = kind === "link" ? `Link to ${modScreenLabel(screen || "")}`.trim() : `New ${kind} app`;
  return { id, name };
}
async function modNewKind(kind, screen){
  const s = modS(); if (!s || !MOD_KIND_HELP[kind]) return null;
  const fw = modFrameworks(s);
  if (kind === "link" && !screen){ s.modPick = "screen"; modRender(); return null; }
  const dept = modNewDept(s);
  const prov = modProvisional(kind, screen);
  const body = { id: prov.id, name: prov.name, kind };
  if (dept) body.department = dept.ref;
  if (kind === "link") body.screen = screen;
  s.modPick = null; s.modErr = null;
  let row;
  try { row = await apiPost(MOD_API, body); }
  catch (e) { s.modErr = "Could not create the app: " + ((e && e.message) || e); modRender(); return null; }
  if (!row || !row.id){ s.modErr = "Could not create the app."; modRender(); return null; }
  await loadModules(true);
  s.modSel = row.id;
  const sess = modOpenSeededChat(s, "New app · " + (dept ? dept.name : "Unassigned"), modHome(s) + "/" + row.id,
                                 modNewSeed(s, dept, kind, row), { id: row.id, mode: "new", department_ref: dept ? dept.ref : null });
  return sess;
}
function modPickHtml(s){
  if (!s.modPick) return "";
  const fw = modFrameworks(s) || {};
  if (s.modPick === "screen"){
    const screens = (fw.screens || []).filter(x => x !== "terminal" && x !== "usage");
    return `<div class="mod-pick" role="group" aria-label="Which screen should the link open?"><span class="mod-pick-lab">Which screen should it open?</span>
      ${screens.map(x => `<button type="button" data-modkind="link" data-modscreen="${modEsc(x)}"><b>${modEsc(modScreenLabel(x))}</b><span>${modEsc(x)}</span></button>`).join("")}
      <button type="button" class="mod-pick-cancel" data-modpickcancel>Cancel</button></div>`;
  }
  return `<div class="mod-pick" role="group" aria-label="What kind of app?"><span class="mod-pick-lab">What kind of app?</span>
    <button type="button" data-modkind="page"><b>Page</b><span>${modEsc(MOD_KIND_HELP.page)}</span></button>
    <button type="button" data-modkind="chat"><b>Chat</b><span>${modEsc(MOD_KIND_HELP.chat)}</span></button>
    <button type="button" data-modkind="link"><b>Link</b><span>${modEsc(MOD_KIND_HELP.link)}</span></button>
    <button type="button" class="mod-pick-cancel" data-modpickcancel>Cancel</button></div>`;
}
/* The done handler's callback (APPS-EVENTS.md §done): the touch endpoint is
   the write that appends the event; the forced read follows. */
async function modOnSessionDone(sess){
  const app = sess && sess.app; if (!app) return;
  try {
    if (app.id && typeof apiPost === "function")
      await apiPost(MOD_API + "/" + encodeURIComponent(app.id) + "/touch", { mode: app.mode || "edit", session_id: sess.id });
  } catch (e) { /* the read below still shows the folder's truth */ }
  await loadModules(true);
}

/* ── html: facets + rail ──────────────────────────────────────────────────── */
function modFacetsHtml(){
  const b = (v, label) => `<button type="button" data-modfacet="${v}" aria-pressed="${v === "modules"}">${label}</button>`;
  return `<div class="facets"><span class="fl">View</span><span class="seg">${b("live", "Live")}${b("draft", "Draft")}${b("dir", "Directory")}${b("modules", "Apps")}</span>
    <button class="newBtn mod-new" type="button" data-modnew>+ New app</button></div>`;
}
function modLeafHtml(s, m){
  return `<a class="dsub modleaf" href="#" data-modapp="${modEsc(m.id)}" aria-current="${s.modSel === m.id}"><span class="mod-dot ${m.status === "ready" ? "ready" : m.status === "archived" ? "archived" : "draft"}"></span>${modEsc(m.name)}<span class="pill mod-kind">${modEsc(m.kind)}</span></a>`;
}
function modRailHtml(s){
  const tree = modTree();
  const loaded = !!(s.modules && !s.modules.error && s.modules.groups);
  const counts = (loaded && s.modules.counts_by_ref) || {};
  const all = modAll(s).filter(m => !modIsSys(m));
  const byDept = new Map();
  all.forEach(m => { const r = m.department ? m.department.ref : MOD_UNASSIGNED; if (!byDept.has(r)) byDept.set(r, []); byDept.get(r).push(m); });
  const unassigned = byDept.get(MOD_UNASSIGNED) || [];
  const selRef = s.modDept || null;
  const openApp = modSelected(s);
  const anchorRef = openApp && openApp.department ? openApp.department.ref : selRef;
  const anc = (tree.root && anchorRef && anchorRef !== MOD_UNASSIGNED) ? modAncestors(tree, anchorRef) : new Set();
  const link = (d, inner, cls) => {
    const on = !openApp && (selRef ? selRef === d.ref : !!(tree.root && d.ref === tree.root.ref));
    return `<a${cls ? ` class="${cls}"` : ""} href="#" data-moddept="${modEsc(d.ref)}" aria-current="${on}">${inner}</a>`;
  };
  let rail = "";
  if (tree.root && typeof dirRail === "function"){
    rail = dirRail({ tops: [tree.root], kids: tree.kids, q: s.modQ || "", link,
      count: d => loaded ? (counts[d.ref] || 0) : null,
      open: (d, depth) => depth < 2 || anc.has(d.ref),
      extra: d => (byDept.get(d.ref) || []).map(m => modLeafHtml(s, m)).join("") });
  }
  const un = loaded ? unassigned.length : null;
  const unNode = (!tree.root || (un != null && un > 0))
    ? `<div class="mod-unas"><details class="navgrp" open><summary><span class="chip">—</span><a href="#" data-moddept="${MOD_UNASSIGNED}" aria-current="${!openApp && selRef === MOD_UNASSIGNED}">Unassigned</a>${un != null ? `<span class="navcount">${un}</span>` : ""}</summary><div class="navkids">${unassigned.map(m => modLeafHtml(s, m)).join("")}</div></details></div>`
    : "";
  return `<nav aria-label="Departments"><input class="dq" type="search" data-modq placeholder="Search departments and apps…" autocomplete="off" value="${modEsc(s.modQ || "")}">${rail}${unNode}</nav>`;
}

/* ── html: rows, department view, app view ────────────────────────────────── */
function modDot(m){
  const st = m.status === "ready" ? "ready" : m.status === "archived" ? "archived" : "draft";
  return `<span class="mod-dot ${st}" aria-hidden="true"></span>`;
}
function modRowHtml(s, m, showDept){
  const user = !modIsSys(m);
  const dep = !showDept ? "" : m.department
    ? `<span class="mod-dep">${modEsc(modChip(m.department.path))} ${modEsc(m.department.name)}</span>`
    : `<span class="mod-dep">—</span>`;
  return `<div class="mod-row" data-modapp="${modEsc(m.id)}" title="${modEsc(m.tagline || m.name)}">
      ${modDot(m)}<span class="mod-nm">${modEsc(m.name)}</span><span class="mod-tg">${modEsc(m.tagline || "")}</span>
      ${user ? `<span class="pill mod-kind">${modEsc(m.kind)}</span>` : ""}${dep}
      ${m.warning ? `<span class="ct w" title="${modEsc(m.warning)}">!</span>` : ""}
    </div>`;
}
function modGrp(title, extra){ return `<div class="mod-grp"><h3 class="sec">${title}</h3>${extra || ""}</div>`; }
function modDeptHeadHtml(s){
  const d = s.modules.department, g = s.modules.groups || {};
  const here = (g.here || []).length;
  const below = (g.below || []).reduce((n, x) => n + ((x && x.modules) || []).length, 0);
  const sys = (g.system || []).length;
  const parts = [`${here} here`];
  if (s.modSubtree !== false && below) parts.push(`${below} below`);
  if (!s.modDept && sys) parts.push(`${sys} system`);
  if (!d) return `<div class="mod-hd"><span class="chip big">—</span><div><h1>Unassigned</h1>
      <p>This registry has no departments yet; apps wait here until one exists.</p></div></div>`;
  return `<div class="mod-hd"><span class="chip big">${modEsc(modChip(d.path) || "—")}</span>
      <div><h1>${modEsc(d.name)}</h1>${d.description ? `<p>${modEsc(d.description)}</p>` : ""}</div>
      <span class="count">${parts.join(" · ")}</span></div>`;
}
function modDeptViewHtml(s){
  const g = Object.assign({ here: [], below: [], system: [], unassigned: [] }, s.modules.groups || {});
  const d = s.modules.department;
  const atRoot = !s.modDept, unas = s.modDept === MOD_UNASSIGNED;
  const sub = s.modSubtree !== false;
  let out = modDeptHeadHtml(s);
  if (g.here.length) out += modGrp("Apps") + g.here.map(m => modRowHtml(s, m, false)).join("");
  else if (d && !unas && !(sub && g.below.length))
    out += `<div class="mod-zero"><p>Nothing here yet. New app puts it in ${modEsc(d.name)}.</p></div>`;
  if (sub && g.below.length)
    out += modGrp("In sub-departments", `<button class="mod-tog" type="button" data-modsub>this department only</button>`)
         + g.below.map(grp => (grp.modules || []).map(m => modRowHtml(s, m, true)).join("")).join("");
  else if (!sub && !unas)
    out += `<div class="mod-grp"><button class="mod-tog" type="button" data-modsub>include sub-departments</button></div>`;
  if (g.system.length) out += modGrp("System") + g.system.map(m => modRowHtml(s, m, false)).join("");
  if (g.unassigned.length) out += modGrp("Unassigned") + g.unassigned.map(m => modRowHtml(s, m, !unas)).join("");
  const archived = s.modules.archived || 0;
  if (atRoot && (archived || s.modShowArchived))
    out += `<button type="button" class="mod-arch" data-modarch>${s.modShowArchived ? "Hide archived" : "Show archived (" + archived + ")"}</button>`;
  out += `<p class="mod-hint">Select an app to open it. Below an app's header is the app itself; <b>Edit in chat</b> changes it. <b>+ New app</b> opens a chat that asks what to build.</p>`;
  return out;
}
function modOriginLine(m){
  const o = m.origin || {};
  if (o.created_by === "system") return "Sutra";
  const who = o.created_by === "shadow" ? "from Shadow" : o.created_by === "disk" ? "from disk"
            : o.created_by === "chat" ? "from a chat" : o.created_by === "marketplace" ? "installed" : "made here";
  return who + (o.at ? " · " + modEsc(String(o.at).slice(0, 10)) : "");
}
function modAppBodyHtml(s, m){
  if (m.building) return `<div class="note w"><b>${modEsc(m.warning || "building…")}</b> The folder exists; its manifest is still being written. It reappears complete on the next paint.</div>`;
  if (m.reserved) return `<div class="note b"><b>This folder uses a reserved id.</b> Rename the folder to something not starting with sys- and it will load.</div>`;
  if (m.kind === "page"){
    if (!m.has_page) return `<div class="zero"><h4>index.html is missing</h4><p>Write it at ${modEsc(modHome(s))}/${modEsc(m.id)}/index.html — or say so in Edit in chat.</p></div>`;
    const src = `${MOD_API}/${m.id}/page?theme=${modTheme()}&v=${s.modFrameNonce || 0}`;
    return `<iframe class="mod-frame" src="${modEsc(src)}" title="${modEsc(m.name)}" sandbox="allow-scripts"></iframe>`;
  }
  if (m.kind === "chat"){
    const instr = (m.surface && m.surface.instructions) || "";
    return `<span class="mod-label">Instructions — the first turn of every session this app opens (change them with Edit in chat)</span>
      <pre class="mod-ro">${modEsc(instr)}</pre>
      <p class="mod-hint" style="margin-top:8px"><a href="#" class="mod-openlink" data-modopen>Open in chat</a> — starts a session with these instructions${m.department ? ", placed under " + modEsc(m.department.name) : ""}.</p>`;
  }
  const scr = m.surface && m.surface.screen;
  if (m.id === "sys-settings"){
    const secs = modSettingsSections();
    return `<p class="mod-hint" style="margin:0 0 8px">Everything Sutra runs on, one section per screen.</p>
      <ul class="nav mod-sections">${secs.map(x => `<li><button type="button" data-screen="${modEsc(x.screen)}">
        <span class="lab">${modEsc(x.label)}</span>${x.group ? `<span class="ct">${modEsc(x.group)}</span>` : ""}</button></li>`).join("")}</ul>`;
  }
  return `<p class="mod-hint" style="margin:0">${modEsc(MOD_KIND_HELP.link)}: <code>${modEsc(scr || "")}</code>${modLinkOpenable(m) ? ` — <a href="#" class="mod-openlink" data-modopen>Open ${modEsc(m.name)}</a>` : " — this link cannot be opened from here."}</p>`;
}
function modAppViewHtml(s, m){
  const d = m.department;
  const sys = modIsSys(m);
  const crumb = `${d ? modEsc(d.name) : "Unassigned"} › ${modEsc(m.kind)}`;
  const edit = (sys || m.reserved) ? "" : `<button class="btn mod-edit" type="button" data-modedit title="Opens a chat in ${modEsc(modHome(s))}/${modEsc(m.id)}/${d ? ", placed under " + modEsc(modChip(d.path)) + " " + modEsc(d.name) : ""}"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12a8 8 0 0 1-8 8H8l-5 3 1.5-4.5A8 8 0 1 1 21 12z"/></svg>Edit in chat</button>`;
  return `<div class="mod-hd"><span class="chip big">${d ? modEsc(modChip(d.path)) : "—"}</span>
      <div><p class="crumb">${crumb}</p><h1>${modEsc(m.name)}</h1>${m.tagline ? `<p>${modEsc(m.tagline)}</p>` : ""}</div>
      ${sys ? "" : `<span class="pill mod-kind">${modEsc(m.kind)}</span>`}${edit}${modChecksChip(s, m)}<span class="count">${modEsc(m.status)}</span></div>
    <div class="mod-body">${modAppBodyHtml(s, m)}</div>`;
}
function modCrumbHtml(s, m){
  const d = m.department;
  const n = d && s.modules.counts_by_ref ? (s.modules.counts_by_ref[d.ref] || 0) : (s.modules.unassigned_count || 0);
  return `<a href="#" class="mod-back" data-modback>‹ ${d ? modEsc(d.name) : "Unassigned"} · ${n} app${n === 1 ? "" : "s"}</a>`;
}
function modScreenHtml(s){
  const facets = modFacetsHtml();
  if (s.modules && s.modules.error){
    return `<div class="mod">${facets}<section class="mod-main">
      <div class="note b"><b>Apps unavailable.</b> ${modEsc(s.modules.error)}</div>
      <div class="mod-actions"><button class="btn" type="button" data-modreload>Try again</button><button class="newBtn" type="button" data-modnew>+ New app</button></div>
    </section></div>`;
  }
  const err = (s.modErr ? `<div class="note w"><b>${modEsc(s.modErr)}</b></div>` : "") + modPickHtml(s);
  const sel = modSelected(s);
  const narrow = modIsNarrow(s);
  if (sel && narrow){
    return `<div class="mod">${facets}${err}<div class="dpage mod-page mod-narrow"><main>${modCrumbHtml(s, sel)}${modAppViewHtml(s, sel)}</main></div></div>`;
  }
  const main = sel ? modAppViewHtml(s, sel) : modDeptViewHtml(s);
  return `<div class="mod"${s.modLoading ? ' aria-busy="true"' : ""}>${facets}${err}<div class="dpage mod-page">${modRailHtml(s)}<main>${main}</main></div></div>`;
}

/* ── navigation ───────────────────────────────────────────────────────────── */
function modFollowRail(st){
  if (st && st.ui && typeof destInline === "function")
    st.ui.railOpen = destInline(st.ui.dest) ? st.ui.dest : null;
}
function modFacet(view){
  const st = modS(); if (!st) return;
  if (view === "modules"){ if (typeof openScreen === "function") openScreen("modules"); }
  else { st.view = view; if (typeof openScreen === "function") openScreen("departments"); }
  modFollowRail(st);
  if (typeof render === "function") render();
}
function modSelectDept(ref){
  const s = modS(); if (!s) return;
  s.modDept = ref || null;
  s.modSel = null; s.modErr = null;
  loadModules(true);
  modRender();
}
function modOpenApp(id){
  const s = modS(); if (!s) return;
  const m = modById(s, id); if (!m) return;
  s.modSel = id; s.modErr = null;
  if (m.department && m.department.ref !== s.modDept && s.modDept !== null && s.modDept !== m.department.ref){
    /* keep the rail's selection coherent with the open app's department */
    s.modDept = m.department.ref;
    loadModules(true);
  }
  modRender();
}

/* ── open paths ───────────────────────────────────────────────────────────── */
function modOpenChat(m){
  const s = modS();
  const dept = m.department ? m.department.ref : null;
  if (typeof goDest === "function") goDest("chats");
  const sess = (typeof newSession === "function") ? newSession((m.surface && m.surface.cwd) || "", dept) : null;
  if (!sess) return false;
  sess.title = m.name || sess.title;
  const instr = m.surface && m.surface.instructions;
  const seed = instr || "";                            /* the pin travels as the option, never as text */
  if (seed.trim() && typeof submitTurn === "function") submitTurn(seed, sess.id, dept ? { pin: { department_ref: dept } } : undefined);
  if (typeof render === "function") render();
  return true;
}
function modOpenLink(m){
  if (!modLinkOpenable(m)) return false;
  const st = modS();
  const scr = m.surface.screen;
  if (typeof openScreen === "function") openScreen(scr); else if (st) st.screen = scr;
  modFollowRail(st);
  if (typeof render === "function") render();
  return true;
}
function modOpen(m){
  if (!m || m.reserved || m.building) return false;
  if (m.kind === "chat") return modOpenChat(m);
  if (m.kind === "link") return modOpenLink(m);
  return false;                                     /* a page IS its body; nothing to open */
}

/* ── registration ─────────────────────────────────────────────────────────── */
if (typeof SCREENS !== "undefined"){
  SCREENS.modules = () => {
    const s = modS(); if (!s) return "";
    if (s.modules === undefined){
      loadModules(false);
      return `<div class="zero"><h4>Apps</h4><p>Reading your apps…</p></div>`;
    }
    modEnsureFrameworks(s);                          /* one read; null on an older server */
    return modScreenHtml(s);
  };
}
if (typeof TITLES !== "undefined"){
  TITLES.modules = ["Apps", "~/.sutra-ui/modules · one department each"];
}

if (typeof document !== "undefined" && document.addEventListener){
  const SEL = "[data-modapp],[data-moddept],[data-modfacet],[data-modnew],[data-modedit],[data-modopen],[data-modsub],[data-modback],[data-modreload],[data-modarch],[data-modkind],[data-modpickcancel]";
  document.addEventListener("click", (ev) => {
    const s = modS(); if (!s) return;
    const t = ev.target && ev.target.closest ? ev.target.closest(SEL) : null;
    if (!t || !t.closest(".mod")) return;                 /* never outside the Apps screen (codex P16) */
    const d = t.dataset || {};
    if (d.moddept !== undefined){ ev.preventDefault(); modSelectDept(d.moddept === MOD_UNASSIGNED ? MOD_UNASSIGNED : d.moddept); return; }
    if (d.modapp !== undefined){ ev.preventDefault(); modOpenApp(d.modapp); return; }
    if (d.modfacet !== undefined){ modFacet(d.modfacet); return; }
    if (d.modnew !== undefined){ modNew(); return; }
    if (d.modkind !== undefined){ modNewKind(d.modkind, d.modscreen || null); return; }
    if (d.modpickcancel !== undefined){ s.modPick = null; modRender(); return; }
    if (d.modback !== undefined){ ev.preventDefault(); s.modSel = null; modRender(); return; }
    if (d.modsub !== undefined){ s.modSubtree = s.modSubtree === false; loadModules(true); modRender(); return; }
    if (d.modreload !== undefined){ s.modFrameNonce = (s.modFrameNonce || 0) + 1; loadModules(true); return; }
    if (d.modarch !== undefined){ s.modShowArchived = !s.modShowArchived; loadModules(true); return; }
    const m = modSelected(s);
    if (d.modedit !== undefined && m){ modEdit(m); return; }
    if (d.modopen !== undefined && m){ ev.preventDefault(); modOpen(m); return; }
  });
  document.addEventListener("input", (ev) => {
    const s = modS(); if (!s) return;
    const el = ev.target;
    if (!el || !el.dataset || el.dataset.modq === undefined) return;
    if (!el.closest || !el.closest(".mod")) return;   /* same scope guard as the click handler (codex R4 P2) */
    s.modQ = String(el.value || "");        /* render() restores focus + caret for the focused input */
    modRender();
  });
}
