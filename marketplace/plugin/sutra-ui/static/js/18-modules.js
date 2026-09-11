/* 18-modules.js -- Org > Modules (2.247.0). Design of record:
   holding/departments/experience/desktop-app/2026-09-08-modules-design.md

   A module is a finished product built inside Sutra: a chat with standing
   instructions, a page rendered from index.html, or a link to a system screen.
   THE FOLDER IS THE MODULE (D-M1): this screen renders what GET /api/modules
   returns and nothing else -- there is no client-side registry, not even as a
   fallback (codex fold). System rows are server seeds; the Settings row's
   sections are derived here from DEST_PLANES.settings (D-M9) so they can never
   drift from the plane.

   Shape: the Org destination is INLINE (rows in the rail accordion), so the
   screen owns its own list column + detail column inside the browse pane. The
   list is the "side pane like Settings" the founder asked for. Self-registers
   SCREENS.modules + TITLES.modules with typeof guards (16-shadow-home.js
   pattern) and keeps its state on S: S.modules (the API answer), S.modSel
   (selected id, in-memory in v1), S.modNew (form open), S.modFull (page
   module opened full-width), S.modShowArchived. */

const MOD_API = "/api/modules";
const MOD_SYS_PREFIX = "sys-";
const MOD_KIND_HELP = {
  chat: "a conversation that opens with these instructions as its first turn",
  page: "a page you wrote as index.html, shown inside the app",
  link: "a shortcut to a screen this app already has"
};
const MOD_SCREEN_LABEL = { terminal: "Terminal", settings: "AI Provider" };

function modS(){ return (typeof S !== "undefined" && S) ? S : null; }
function modEsc(x){ return (typeof esc === "function") ? esc(x) : String(x == null ? "" : x); }
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

/* ── data ─────────────────────────────────────────────────────────────────── */
async function loadModules(force){
  const s = modS(); if (!s) return;
  if (s.modLoading) return;
  if (!force && s.modules && !s.modules.error) return;
  s.modLoading = true;
  try {
    const data = await apiGet(MOD_API + (s.modShowArchived ? "?include=archived" : ""));
    s.modules = { modules: Array.isArray(data.modules) ? data.modules : [],
                  count_user: data.count_user || 0, archived: data.archived || 0,
                  home: data.home || "", error: null };
  } catch (e) {
    s.modules = { modules: [], count_user: 0, archived: 0, home: "",
                  error: (e && e.message) || String(e) };
  }
  s.modLoading = false;
  modRender();
}

function modRows(s){
  const all = (s.modules && s.modules.modules) || [];
  return { yours: all.filter(m => !String(m.id).startsWith(MOD_SYS_PREFIX) || m.reserved),
           system: all.filter(m => String(m.id).startsWith(MOD_SYS_PREFIX) && !m.reserved) };
}
function modSelected(s){
  const { yours, system } = modRows(s);
  const all = yours.concat(system);
  const hit = all.find(m => m.id === s.modSel);
  return hit || yours[0] || system[0] || null;
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

/* ── html ─────────────────────────────────────────────────────────────────── */
function modDot(m){
  const st = m.status === "ready" ? "ready" : m.status === "archived" ? "archived" : "draft";
  return `<span class="mod-dot ${st}" aria-hidden="true"></span>`;
}
function modRowHtml(m, sel){
  const user = !String(m.id).startsWith(MOD_SYS_PREFIX);
  return `<li><button type="button" data-mod="${modEsc(m.id)}" aria-current="${sel === m.id}"
      title="${modEsc(m.tagline || m.name)}">
      ${modDot(m)}<span class="lab">${modEsc(m.name)}</span>
      ${user ? `<span class="pill mod-kind">${modEsc(m.kind)}</span>` : ""}
      ${m.warning ? `<span class="ct w" title="${modEsc(m.warning)}">!</span>` : ""}
    </button></li>`;
}
function modSideHtml(s){
  const { yours, system } = modRows(s);
  const sel = modSelected(s); const selId = sel ? sel.id : null;
  const archived = (s.modules && s.modules.archived) || 0;
  return `<aside class="mod-side" aria-label="Modules">
    <button class="newBtn" type="button" data-modnew>+ New module</button>
    ${yours.length ? `<h3 class="sec">Yours</h3><ul class="nav">${yours.map(m => modRowHtml(m, selId)).join("")}</ul>` : ""}
    <h3 class="sec">System</h3><ul class="nav">${system.map(m => modRowHtml(m, selId)).join("")}</ul>
    ${archived || s.modShowArchived ? `<button type="button" class="mod-arch" data-modarch>${s.modShowArchived ? "Hide archived" : "Show archived (" + archived + ")"}</button>` : ""}
  </aside>`;
}
function modOriginLine(m){
  const o = m.origin || {};
  if (o.created_by === "system") return "Sutra";
  const who = o.created_by === "shadow" ? "from Shadow" : o.created_by === "disk" ? "from disk"
            : o.created_by === "chat" ? "from a chat" : "made here";
  return who + (o.at ? " · " + modEsc(String(o.at).slice(0, 10)) : "");
}
function modActionsHtml(m){
  if (String(m.id).startsWith(MOD_SYS_PREFIX)) return "";
  const arch = m.status === "archived";
  return `<div class="mod-actions">
    ${arch ? `<button class="btn" type="button" data-modact="restore">Restore</button>`
           : `${m.status !== "ready" ? `<button class="btn" type="button" data-modact="mark_ready" ${m.kind === "page" && !m.has_page ? "disabled" : ""}>Mark ready</button>` : ""}
              <button class="btn" type="button" data-modact="archive">Archive</button>`}
    ${m.kind === "page" ? `<button class="btn" type="button" data-modreload>Reload</button>` : ""}
  </div>`;
}
function modFolderLine(s, m){
  if (String(m.id).startsWith(MOD_SYS_PREFIX) || !s.modules || !s.modules.home) return "";
  return `<p class="mod-path">${modEsc(s.modules.home)}/${modEsc(m.id)}/</p>`;
}
function modDetailHtml(s, m){
  if (!m) return "";
  const sys = String(m.id).startsWith(MOD_SYS_PREFIX);
  const head = `<div class="mod-head">
      ${s.modFull ? `<button class="btn" type="button" data-modback>&larr; Back</button>` : ""}
      <h2>${modEsc(m.name)}</h2>
      <p>${modEsc(m.tagline || MOD_KIND_HELP[m.kind] || "")}</p>
      <p class="mod-origin">${modOriginLine(m)}${sys ? "" : " · <span class=\"pill mod-kind\">" + modEsc(m.kind) + "</span> · " + modEsc(m.status)}</p>
      ${m.warning ? `<div class="note w"><b>${modEsc(m.warning)}</b></div>` : ""}
    </div>`;
  let body = "", primary = "";
  if (m.reserved){
    body = `<div class="note b"><b>This folder uses a reserved id.</b> Rename the folder to something not starting with sys- and it will load.</div>`;
  } else if (m.kind === "chat"){
    const instr = (m.surface && m.surface.instructions) || "";
    body = `<label class="mod-label" for="modinstr">Instructions — the first turn of every session this module opens</label>
      <textarea id="modinstr" class="mod-instr" data-modinstr rows="8" placeholder="You run my Friday review. Ask the five questions in order…">${modEsc(instr)}</textarea>`;
    primary = `<button class="newBtn" type="button" data-modopen>Open in Chats</button>`;
  } else if (m.kind === "page"){
    if (m.has_page){
      const src = `${MOD_API}/${m.id}/page?theme=${modTheme()}&v=${s.modFrameNonce || 0}`;
      body = `<iframe class="mod-frame" src="${modEsc(src)}" title="${modEsc(m.name)}" sandbox="allow-scripts"></iframe>`;
      primary = s.modFull ? "" : `<button class="newBtn" type="button" data-modopen>Open full width</button>`;
    } else {
      body = `<div class="zero"><h4>index.html is missing</h4><p>Write it at ${modEsc((s.modules && s.modules.home) || "~/.sutra-ui/modules")}/${modEsc(m.id)}/index.html and press Reload.</p></div>`;
    }
  } else {
    const scr = m.surface && m.surface.screen;
    if (m.id === "sys-settings"){
      const secs = modSettingsSections();
      body = `<p class="mod-blurb">Everything Sutra runs on, one section per screen.</p>
        <ul class="nav mod-sections">${secs.map(x => `<li><button type="button" data-screen="${modEsc(x.screen)}">
          <span class="lab">${modEsc(x.label)}</span>${x.group ? `<span class="ct">${modEsc(x.group)}</span>` : ""}</button></li>`).join("")}</ul>`;
    } else {
      body = `<p class="mod-blurb">${modEsc(MOD_KIND_HELP.link)}: <code>${modEsc(scr || "")}</code></p>`;
    }
    primary = modLinkOpenable(m)
      ? `<button class="newBtn" type="button" data-modopen>Open ${modEsc(m.name)}</button>`
      : `<p class="mod-blurb">This link cannot be opened from here.</p>`;
  }
  return `<section class="mod-main">${head}${body}${primary}${modActionsHtml(m)}${modFolderLine(s, m)}</section>`;
}
function modFormHtml(s){
  return `<section class="mod-main mod-form">
    <div class="mod-head"><h2>New module</h2><p>A finished thing you can open again. It lives in its own folder under ${modEsc((s.modules && s.modules.home) || "~/.sutra-ui/modules")}.</p></div>
    ${s.modErr ? `<div class="note b"><b>Not created.</b> ${modEsc(s.modErr)}</div>` : ""}
    <label class="mod-label" for="modf-name">Name</label>
    <input id="modf-name" data-modf="name" maxlength="80" placeholder="Friday review">
    <div class="mod-label">Kind</div>
    <div class="mod-kinds">
      <label><input type="radio" name="modkind" value="chat" checked> <b>chat</b> — ${modEsc(MOD_KIND_HELP.chat)}</label>
      <label><input type="radio" name="modkind" value="page"> <b>page</b> — ${modEsc(MOD_KIND_HELP.page)}</label>
    </div>
    <label class="mod-label" for="modf-tagline">Tagline</label>
    <input id="modf-tagline" data-modf="tagline" maxlength="140" placeholder="one line on what it is for">
    <label class="mod-label" for="modf-instr">Instructions (chat)</label>
    <textarea id="modf-instr" data-modf="instructions" rows="6" placeholder="You run my Friday review…"></textarea>
    <div class="mod-actions"><button class="newBtn" type="button" data-modcreate>Create</button><button class="btn" type="button" data-modcancel>Cancel</button></div>
    <p class="mod-blurb">Or ask Shadow to create one, or write module.json into a new folder from any Claude Code session — it appears here on the next open.</p>
  </section>`;
}
function modEmptyHtml(){
  return `<section class="mod-main"><div class="zero"><h4>Nothing you have built yet</h4>
    <p>Ask Sutra to create a module, or start one here.</p>
    <button class="newBtn" type="button" data-modnew>New module</button></div></section>`;
}
function modScreenHtml(s){
  if (s.modules && s.modules.error){
    return `<div class="mod"><section class="mod-main">
      <div class="note b"><b>Modules unavailable.</b> ${modEsc(s.modules.error)}</div>
      <div class="mod-actions"><button class="btn" type="button" data-modreload>Try again</button><button class="newBtn" type="button" data-modnew>New module</button></div>
    </section></div>`;
  }
  const { yours } = modRows(s);
  const sel = modSelected(s);
  const main = s.modNew ? modFormHtml(s)
             : (!yours.length && (!sel || String(sel.id).startsWith(MOD_SYS_PREFIX)) && !s.modSel) ? modEmptyHtml()
             : modDetailHtml(s, sel);
  return `<div class="mod${s.modFull ? " full" : ""}">${modSideHtml(s)}${main}</div>`;
}

/* ── open ─────────────────────────────────────────────────────────────────── */
function modOpenChat(m){
  if (typeof goDest === "function") goDest("chats");
  const s = (typeof newSession === "function") ? newSession((m.surface && m.surface.cwd) || "") : null;
  if (!s) return false;
  s.title = m.name || s.title;
  const instr = m.surface && m.surface.instructions;
  if (instr && typeof submitTurn === "function") submitTurn(instr, s.id);
  if (typeof render === "function") render();
  return true;
}
function modOpenLink(m){
  if (!modLinkOpenable(m)) return false;
  const st = modS();
  const scr = m.surface.screen;
  if (typeof openScreen === "function") openScreen(scr); else if (st) st.screen = scr;
  /* openScreen moves S.ui.dest to the screen's owner but never touches
     railOpen; the accordion must follow (codex fold: openScreen + this line,
     not goDest, which would restore the last selection instead of the target). */
  if (st && st.ui && typeof destInline === "function")
    st.ui.railOpen = destInline(st.ui.dest) ? st.ui.dest : null;
  if (typeof render === "function") render();
  return true;
}
function modOpen(m){
  if (!m || m.reserved) return false;
  if (m.kind === "chat") return modOpenChat(m);
  if (m.kind === "link") return modOpenLink(m);
  const s = modS(); if (!s || !m.has_page) return false;
  s.modFull = true; modRender(); return true;
}

/* ── actions ──────────────────────────────────────────────────────────────── */
async function modAct(id, action, body){
  const s = modS(); if (!s) return;
  try {
    await apiPost(MOD_API + "/" + encodeURIComponent(id), Object.assign({ action }, body || {}));
    s.modErr = null;
  } catch (e) { s.modErr = (e && e.message) || String(e); }
  await loadModules(true);
}
async function modCreate(){
  const s = modS(); if (!s) return;
  const q = sel => (typeof document !== "undefined" && document.querySelector) ? document.querySelector(sel) : null;
  const val = sel => { const el = q(sel); return el ? String(el.value || "") : ""; };
  const kindEl = q('input[name="modkind"]:checked');
  const body = { name: val('[data-modf="name"]').trim(), kind: kindEl ? kindEl.value : "chat",
                 tagline: val('[data-modf="tagline"]').trim(), instructions: val('[data-modf="instructions"]') };
  try {
    const row = await apiPost(MOD_API, body);
    s.modErr = null; s.modNew = false; s.modSel = row && row.id;
  } catch (e) { s.modErr = (e && e.message) || String(e); modRender(); return; }
  await loadModules(true);
}

/* ── registration ─────────────────────────────────────────────────────────── */
if (typeof SCREENS !== "undefined"){
  SCREENS.modules = () => {
    const s = modS(); if (!s) return "";
    if (s.modules === undefined){
      loadModules(false);
      return `<div class="zero"><h4>Modules</h4><p>Reading your modules…</p></div>`;
    }
    return modScreenHtml(s);
  };
}
if (typeof TITLES !== "undefined"){
  TITLES.modules = ["Modules", "~/.sutra-ui/modules · what you built here"];
}

if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("click", (ev) => {
    const s = modS(); if (!s) return;
    const t = ev.target && ev.target.closest ? ev.target.closest("[data-mod],[data-modnew],[data-modcancel],[data-modcreate],[data-modopen],[data-modact],[data-modarch],[data-modback],[data-modreload]") : null;
    if (!t) return;
    const d = t.dataset || {};
    if (d.mod !== undefined){ s.modSel = d.mod; s.modNew = false; s.modFull = false; modRender(); return; }
    if (d.modnew !== undefined){ s.modNew = true; s.modErr = null; s.modFull = false; modRender(); return; }
    if (d.modcancel !== undefined){ s.modNew = false; s.modErr = null; modRender(); return; }
    if (d.modcreate !== undefined){ modCreate(); return; }
    if (d.modback !== undefined){ s.modFull = false; modRender(); return; }
    if (d.modreload !== undefined){ s.modFrameNonce = (s.modFrameNonce || 0) + 1; loadModules(true); return; }
    if (d.modarch !== undefined){ s.modShowArchived = !s.modShowArchived; loadModules(true); return; }
    const m = modSelected(s);
    if (d.modopen !== undefined){ modOpen(m); return; }
    if (d.modact !== undefined && m){ modAct(m.id, d.modact); return; }
  });
  document.addEventListener("change", (ev) => {
    const s = modS(); if (!s) return;
    const el = ev.target;
    if (!el || !el.dataset || el.dataset.modinstr === undefined) return;
    const m = modSelected(s);
    if (m && m.kind === "chat") modAct(m.id, "set_instructions", { instructions: String(el.value || "") });
  });
}
