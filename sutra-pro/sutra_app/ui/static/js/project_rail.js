/* project_rail.js - the sidebar on Home, on Agent Org and on every team page (Sutra's own; J2's page is not edited for it: dept_ext.js adds it).

   One column on the left, the same on every page:
     + New project
     Attention (with the count of things that need the owner)      -> Home
     Agent Org                                                      -> /?pane=org
     MY SECTIONS  +             the owner's own groups of projects (SectionsStore, GET/PUT /api/sections, kept on the server)
       > Clients  ...           each section folds open and shut; "..." renames or deletes it
           Calm Flow  ...       each project shows its state; "..." moves it to a section
       > All projects           every project in no section
     Settings & logs
   On a phone it folds away behind a menu button.

     ProjectRail.model(departments, needs)   {needs: [{id, name, href, count}], projects: [{id, name, href, state, words}], count}
                                             from GET /api/departments and GET /api/needs-you; nothing else is read
     ProjectRail.html(model, current, view)  the column's inner markup. `current` is the open team's id ("" off a team page). view: {doc (the
                                             sections document), here ("attention" | "org" | ""), adding, renaming (a section id), allShut, error}
     ProjectRail.mount(opts)                 once per page: adds the column, the menu button and the style sheet. opts.feed false (Home):
                                             the page hands the lists in with set(); else the rail reads them itself, every few seconds
     ProjectRail.set({departments, needs})   new lists: repaint
     ProjectRail.open(bool)                  the phone drawer

   Strings in, strings out for model() and html(): every word from the wire is escaped. A classic script with ONE global, ProjectRail;
   in node it is module.exports and does not start by itself. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : "");
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const ID = /^[A-Za-z0-9_.:-]{1,120}$/;
  const idOf = v => (ID.test(text(v)) ? text(v) : "");
  const teamHref = id => "/d/" + encodeURIComponent(id) + "/";
  const ORG_HREF = "/?pane=org";

  const MAKING = ["running", "waiting"];
  const DONE = ["filed", "done_unchecked", "left_open"];
  const FINISHED = ["done", "done_with_open_items"];             // a team idle again after its last run finished (last_status) is Done
  // the state of a project as a first-time owner reads it; the mark is drawn by the style sheet (pr-<state>)
  const WORDS = {needs: "Needs your answer", making: "Being made", problem: "Something broke", done: "Done", idle: "Not started yet"};
  const POLL_MS = 8000;            // a team page: read the two lists this often (Home hands them in from its own live reads)

  /* ---------------------------------------------------------------- pure parts */
  function stateOf(d, asked) {
    const status = text(d.node_status);
    if (asked || status === "waiting_on_you") return "needs";
    if (status === "fault") return "problem";
    if (MAKING.includes(status) || idOf(d.live_task_id)) return "making";
    if (DONE.includes(status) || FINISHED.includes(text(d.last_status))) return "done";
    if (text(d.last_status) === "crashed") return "problem";
    return "idle";
  }

  function model(departments, needs) {
    const asks = new Map();
    let approvals = 0;
    let count = 0;
    (Array.isArray(needs) ? needs : []).filter(isObj).forEach(n => {
      const dept = idOf(n.dept_id);
      count += 1;
      if (dept) asks.set(dept, (asks.get(dept) || 0) + 1);
      else approvals += 1;                       // an org change waiting for a yes: it belongs to no project
    });
    const projects = (Array.isArray(departments) ? departments : []).filter(d => isObj(d) && idOf(d.id)).map(d => {
      const state = stateOf(d, asks.has(d.id));
      return {id: d.id, name: clean(d.name) || d.id, href: teamHref(d.id), state, words: WORDS[state]};
    });
    const named = new Map(projects.map(p => [p.id, p.name]));
    const list = [...asks.entries()].map(([id, n]) => ({id, name: named.get(id) || id, href: teamHref(id), count: n}));
    if (approvals > 0) list.push({id: "", name: "Your organisation", href: "/", count: approvals});
    return {needs: list, projects, count};
  }

  const SS = () => root.SectionsStore || (typeof require === "function" ? safeRequire("./sections_store.js") : null);
  function safeRequire(name) { try { return require(name); } catch (e) { return null; } }

  const ICONS = {
    attention: '<svg class="pr-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>',
    org: '<svg class="pr-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="5" rx="1"/><rect x="3" y="16" width="6" height="5" rx="1"/><rect x="15" y="16" width="6" height="5" rx="1"/><path d="M12 8v4M6 16v-4h12v4"/></svg>',
    plus: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
    more: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>',
    caret: '<svg class="pr-caret" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>',
  };

  function nameBox(form, value, label) {
    return '<form class="pr-namebox" data-pr-form="' + esc(form) + '"><input class="pr-input" type="text" maxlength="40" autocomplete="off" aria-label="' + esc(label) +
      '" placeholder="Section name" value="' + esc(value) + '"></form>';
  }

  function html(m, current, view) {
    const cur = text(current);
    const v = isObj(view) ? view : {};
    const here = text(v.here);
    const projects = m && Array.isArray(m.projects) ? m.projects : [];
    const count = m && Number.isInteger(m.count) ? m.count : 0;
    const mark = p => '<i class="pr-mark pr-' + esc(p.state) + '" aria-hidden="true"></i><span class="pr-sr">' + esc(p.words) + ", </span>";
    const row = p => '<li class="pr-row"><a class="pr-item' + (p.id === cur ? " pr-on" : "") + '" href="' + esc(p.href) + '"' +
      (p.id === cur ? ' aria-current="page"' : "") + ' title="' + esc(p.words) + '">' + mark(p) + '<span class="pr-name">' + esc(p.name) + "</span></a>" +
      '<button type="button" class="pr-more" data-pr="projmenu" data-team="' + esc(p.id) + '" aria-haspopup="menu" aria-label="Move ' + esc(p.name) + ' to a section">' + ICONS.more + "</button></li>";
    const nav = (id, href, icon, label, on, extra) => '<li><a class="pr-nav' + (on ? " pr-on" : "") + '" id="' + id + '" href="' + href + '"' + (on ? ' aria-current="page"' : "") + ">" +
      icon + '<span class="pr-name">' + label + "</span>" + (extra || "") + "</a></li>";
    const badge = count > 0 ? '<b class="pr-count" aria-label="' + count + (count === 1 ? " thing needs you" : " things need you") + '">' + count + "</b>" : "";
    const fixed = '<ul class="pr-list pr-fixed">' + nav("pr-att", "/", ICONS.attention, "Attention", here === "attention", badge) +
      nav("pr-org", ORG_HREF, ICONS.org, "Agent Org", here === "org") + "</ul>";

    const ss = SS();
    const groups = ss ? ss.group(v.doc, projects) : [{section: null, teams: projects}];
    const sections = groups.filter(g => g.section).map(g => {
      const s = g.section;
      const open = s.collapsed !== true;
      const head = v.renaming === s.id ? nameBox("rename", s.name, "New name for " + s.name)
        : '<div class="pr-secrow"><button type="button" class="pr-sectoggle" data-pr="toggle" data-sec="' + esc(s.id) + '" aria-expanded="' + open + '">' + ICONS.caret +
          '<span class="pr-secname">' + esc(s.name) + '</span></button><button type="button" class="pr-more" data-pr="secmenu" data-sec="' + esc(s.id) +
          '" aria-haspopup="menu" aria-label="Rename or delete ' + esc(s.name) + '">' + ICONS.more + "</button></div>";
      const body = !open ? "" : g.teams.length ? '<ul class="pr-list">' + g.teams.map(row).join("") + "</ul>"
        : '<p class="pr-empty pr-hint">Empty. Use &middot;&middot;&middot; on a project to move it here.</p>';
      return '<div class="pr-sec' + (open ? "" : " pr-shut") + '" data-sec="' + esc(s.id) + '">' + head + body + "</div>";
    }).join("");
    const rest = groups[groups.length - 1].teams;
    const allOpen = v.allShut !== true;
    const all = '<div class="pr-sec pr-all' + (allOpen ? "" : " pr-shut") + '"><div class="pr-secrow"><button type="button" class="pr-sectoggle" data-pr="toggle" data-sec="" aria-expanded="' +
      allOpen + '">' + ICONS.caret + '<span class="pr-secname">All projects</span></button></div>' +
      (!allOpen ? "" : rest.length ? '<ul class="pr-list">' + rest.map(row).join("") + "</ul>"
        : '<p class="pr-empty pr-hint">' + (projects.length ? "Every project is in a section." : "Your projects show here.") + "</p>") + "</div>";
    const err = clean(v.error) ? '<p class="pr-err" role="alert">' + esc(clean(v.error)) + "</p>" : "";
    const mine = '<section class="pr-group" aria-labelledby="pr-sec-h"><div class="pr-headrow"><h2 class="pr-head" id="pr-sec-h">My sections</h2>' +
      '<button type="button" class="pr-add" id="pr-addsec" data-pr="add" aria-label="New section" title="New section">' + ICONS.plus + "</button></div>" + err +
      (v.adding ? nameBox("add", "", "Name of the new section") : "") + sections + all + "</section>";
    return fixed + mine;
  }

  /* ---------------------------------------------------------------- the page */
  const doc = () => root.document || null;
  const ctx = () => root.SutraCtx || null;
  const S = {mounted: false, el: null, list: null, btn: null, menu: null, departments: [], needs: [], current: "", timer: null, open: false,
    doc: null, adding: false, renaming: "", allShut: false, error: "", pendingTeam: "", dirty: false, saving: Promise.resolve()};

  function here() {
    const d = doc();
    if (!d || S.current) return "";
    const de = d.documentElement;
    if (de.dataset.ws === "org") return "org";
    if (d.getElementById("front") && de.dataset.place !== "ws") return "attention";
    return "";
  }

  const view = () => ({doc: S.doc, here: here(), adding: S.adding, renaming: S.renaming, allShut: S.allShut, error: S.error});

  function paint(force) {
    if (!S.list) return;
    const d = doc();
    // a name being typed is never torn down by a repaint (the team page reads the lists every few seconds): paint once it is done
    if (!force && d && d.activeElement && d.activeElement.classList && d.activeElement.classList.contains("pr-input") && S.list.contains(d.activeElement)) { S.dirty = true; return; }
    S.dirty = false;
    const m = model(S.departments, S.needs);
    const next = html(m, S.current, view());
    if (S.list.dataset.html !== next) { S.list.innerHTML = next; S.list.dataset.html = next; }
    const box = S.list.querySelector(".pr-input");
    if (box && d && d.activeElement !== box) { box.focus(); if (box.select) box.select(); }
    if (S.btn) {
      const badge = S.btn.querySelector(".pr-btnbadge");
      if (badge) { badge.hidden = m.count === 0; badge.textContent = String(m.count); }
      S.btn.setAttribute("aria-label", m.count ? "Menu, " + m.count + " need you" : "Menu");
    }
  }

  function set(lists) {
    if (!isObj(lists)) return;
    if (Array.isArray(lists.departments)) S.departments = lists.departments;
    if (Array.isArray(lists.needs)) S.needs = lists.needs;
    paint();
  }

  async function load() {
    const c = ctx();
    if (!c || !c.api) return;
    const [d, n] = await Promise.allSettled([c.api.get("/api/departments"), c.api.get("/api/needs-you")]);
    const rows = r => (r.status !== "fulfilled" ? null : Array.isArray(r.value) ? r.value : isObj(r.value) && Array.isArray(r.value.items) ? r.value.items
      : isObj(r.value) && Array.isArray(r.value.departments) ? r.value.departments : null);
    set({departments: rows(d) || undefined, needs: rows(n) || undefined});
  }

  async function loadSections() {
    const ss = SS();
    if (!ss) return;
    S.doc = await ss.load();
    paint();
  }

  // One save at a time, in order: the page shows the new document at once; a refusal puts the old one back and says why.
  function commit(next) {
    const ss = SS();
    if (!ss) return Promise.resolve(false);
    const before = S.doc;
    S.doc = next;
    S.error = "";
    paint(true);
    S.saving = S.saving.then(() => ss.save(next)).then(r => {
      if (r.ok) S.doc = r.data;
      else { S.doc = before; S.error = r.error || "The sections could not be saved."; }
      paint(true);
      return r.ok;
    });
    return S.saving;
  }

  // A team page already holds event streams of its own (the page's, the node panel's); a browser gives one address only six connections, so the
  // sidebar opens no stream: it reads the two small lists again every POLL_MS while the tab is visible, and at once when the tab comes back.
  function follow() {
    if (S.timer || typeof root.setInterval !== "function") return;
    S.timer = root.setInterval(() => { const d = doc(); if (!d || d.visibilityState !== "hidden") load(); }, POLL_MS);
    const d = doc();
    if (d && d.addEventListener) d.addEventListener("visibilitychange", () => { if (d.visibilityState === "visible") load(); });
  }

  function setOpen(open) {
    S.open = open === true;
    const d = doc();
    if (d && d.body) d.body.classList.toggle("prail-open", S.open);
    if (S.btn) S.btn.setAttribute("aria-expanded", String(S.open));
    if (S.open && S.el) { const first = S.el.querySelector("a,button"); if (first && first.focus) first.focus(); }
  }

  function onNew(e) {
    const d = doc();
    const box = d && d.getElementById("fdbox");
    const onFront = box && d.documentElement.dataset.place !== "ws";
    if (!onFront) return;                       // a team page (or the back room): the link goes to Home's start box
    e.preventDefault();
    setOpen(false);
    box.focus();
    if (box.scrollIntoView) box.scrollIntoView({block: "center"});
  }

  /* ---- the small "..." menu: one at a time, under the button that opened it */
  function closeMenu(focusBack) {
    if (!S.menu || S.menu.hidden) return;
    S.menu.hidden = true;
    const from = S.menu.dataset.from ? S.el.querySelector(S.menu.dataset.from) : null;
    S.menu.dataset.from = "";
    if (focusBack && from && from.focus) from.focus();
  }

  function openMenu(button, items) {
    if (!S.menu) return;
    S.menu.innerHTML = items;
    S.menu.hidden = false;
    const at = button.getBoundingClientRect ? button.getBoundingClientRect() : null;
    const box = S.el.getBoundingClientRect ? S.el.getBoundingClientRect() : null;
    if (at && box) {
      S.menu.style.top = Math.round(at.bottom - box.top + 4) + "px";
      S.menu.style.left = "";
      S.menu.style.right = "8px";
    }
    S.menu.dataset.from = button.dataset.team ? '.pr-more[data-team="' + button.dataset.team + '"]' : '.pr-more[data-sec="' + button.dataset.sec + '"]';
    const first = S.menu.querySelector("button");
    if (first) first.focus();
  }

  function sectionMenu(button) {
    const id = button.dataset.sec;
    openMenu(button, '<button type="button" class="pr-mi" role="menuitem" data-pr="rename" data-sec="' + esc(id) + '">Rename</button>' +
      '<button type="button" class="pr-mi pr-mi-bad" role="menuitem" data-pr="delete" data-sec="' + esc(id) + '">Delete section</button>' +
      '<p class="pr-minote">Its projects go back to All projects.</p>');
  }

  function projectMenu(button) {
    const team = button.dataset.team;
    const ss = SS();
    const list = ss && S.doc ? S.doc.sections : [];
    const inSec = list.find(s => s.teams.includes(team));
    const items = list.map(s => '<button type="button" class="pr-mi" role="menuitemradio" aria-checked="' + (inSec === s) + '" data-pr="move" data-team="' + esc(team) +
      '" data-sec="' + esc(s.id) + '">' + esc(s.name) + "</button>").join("");
    openMenu(button, '<p class="pr-mhead">Move to section</p>' + items +
      (inSec ? '<button type="button" class="pr-mi" role="menuitem" data-pr="move" data-team="' + esc(team) + '" data-sec="">No section</button>' : "") +
      '<button type="button" class="pr-mi pr-mi-new" role="menuitem" data-pr="addfor" data-team="' + esc(team) + '">New section&hellip;</button>');
  }

  function onClick(e) {
    const b = e.target.closest && e.target.closest("[data-pr]");
    if (!b || !S.el.contains(b)) return;
    const act = b.dataset.pr;
    const ss = SS();
    if (act === "projmenu" || act === "secmenu") {
      e.preventDefault();
      const again = !S.menu.hidden && S.menu.dataset.from && S.el.querySelector(S.menu.dataset.from) === b;
      closeMenu(false);
      if (!again) (act === "projmenu" ? projectMenu : sectionMenu)(b);
      return;
    }
    if (!ss) return;
    if (act === "add") { closeMenu(false); S.adding = !S.adding; S.renaming = ""; S.pendingTeam = ""; paint(true); }
    else if (act === "addfor") { closeMenu(false); S.adding = true; S.renaming = ""; S.pendingTeam = b.dataset.team || ""; paint(true); }
    else if (act === "toggle") {
      const id = b.dataset.sec;
      if (!id) { S.allShut = !S.allShut; paint(true); return; }
      const next = ss.copy ? ss.copy(S.doc) : JSON.parse(JSON.stringify(S.doc || {version: 1, sections: []}));
      const s = next.sections.find(x => x.id === id);
      if (s) { s.collapsed = !s.collapsed; commit(next); }
    } else if (act === "rename") { closeMenu(false); S.renaming = b.dataset.sec; S.adding = false; paint(true); }
    else if (act === "delete") { closeMenu(false); commit(ss.remove(S.doc, b.dataset.sec)); }
    else if (act === "move") { closeMenu(false); commit(ss.assign(S.doc, b.dataset.team, b.dataset.sec || null)); }
  }

  function finishName(form, keep) {
    const ss = SS();
    const input = form.querySelector(".pr-input");
    const name = ss ? ss.cleanName(input ? input.value : "") : "";
    const kind = form.dataset.prForm;
    const renaming = S.renaming;
    const team = S.pendingTeam;
    S.adding = false;
    S.renaming = "";
    S.pendingTeam = "";
    if (!keep || !ss || name === "") { paint(true); return; }
    if (kind === "rename") { commit(ss.rename(S.doc, renaming, name)); return; }
    let next = ss.add(S.doc, name);
    const made = next.sections.length > (S.doc ? S.doc.sections.length : 0) ? next.sections[next.sections.length - 1] : null;
    if (made && team) next = ss.assign(next, team, made.id);
    commit(next);
  }

  function wireColumn(aside) {
    aside.addEventListener("click", onClick);
    aside.addEventListener("submit", e => { const f = e.target.closest("form[data-pr-form]"); if (f) { e.preventDefault(); finishName(f, true); } });
    aside.addEventListener("keydown", e => {
      const input = e.target.closest && e.target.closest(".pr-input");
      if (input && e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finishName(input.form, false); }
      if (e.key === "Escape" && !S.menu.hidden) { e.preventDefault(); e.stopPropagation(); closeMenu(true); }
    });
    // leaving the box: a typed name is kept, an empty one is dropped
    aside.addEventListener("focusout", e => {
      const input = e.target.closest && e.target.closest(".pr-input");
      if (!input || !input.form) return;
      root.setTimeout(() => { if (input.isConnected && doc().activeElement !== input) finishName(input.form, true); else if (S.dirty) paint(); }, 0);
    });
    const d = doc();
    d.addEventListener("click", e => { if (S.menu && !S.menu.hidden && !S.menu.contains(e.target) && !(e.target.closest && e.target.closest(".pr-more"))) closeMenu(false); });
  }

  function mount(opts) {
    const d = doc();
    if (S.mounted || !d || !d.body) return false;
    S.mounted = true;
    const o = isObj(opts) ? opts : {};
    const c = ctx();
    S.current = c && typeof c.dept === "string" ? c.dept : "";
    if (!d.querySelector('link[href="/ui/css/project_rail.css"]')) {
      const css = d.createElement("link");
      css.rel = "stylesheet";
      css.href = "/ui/css/project_rail.css";
      d.head.appendChild(css);
    }
    const aside = d.createElement("aside");
    aside.className = "prail";
    aside.id = "prail";
    aside.setAttribute("aria-label", "Sidebar");
    aside.innerHTML = '<a class="pr-new" id="pr-new" href="/">' + ICONS.plus.replace('width="14" height="14"', 'width="16" height="16"') + "New project</a>" +
      '<nav class="pr-body" id="pr-body" aria-label="Projects"></nav>' +
      '<div class="pr-menu" id="pr-menu" role="menu" aria-label="Options" hidden></div>' +
      '<a class="pr-foot" id="pr-settings" href="/?pane=settings">Settings &amp; logs</a>';
    const btn = d.createElement("button");
    btn.type = "button";
    btn.className = "pr-btn";
    btn.id = "prailbtn";
    btn.setAttribute("aria-controls", "prail");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", "Menu");
    btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg><span class="pr-btnbadge" hidden></span>';
    const scrim = d.createElement("div");
    scrim.className = "pr-scrim";
    scrim.addEventListener("click", () => setOpen(false));
    d.body.insertBefore(scrim, d.body.firstChild);
    d.body.insertBefore(aside, d.body.firstChild);
    d.body.insertBefore(btn, d.body.firstChild);
    d.body.classList.add("has-prail");
    S.el = aside;
    S.list = aside.querySelector("#pr-body");
    S.menu = aside.querySelector("#pr-menu");
    S.btn = btn;
    btn.addEventListener("click", () => setOpen(!S.open));
    aside.querySelector("#pr-new").addEventListener("click", onNew);
    wireColumn(aside);
    d.addEventListener("keydown", e => { if (e.key === "Escape" && S.open) { setOpen(false); btn.focus(); } });
    if (d.addEventListener) d.addEventListener("visibilitychange", () => { if (d.visibilityState === "visible") loadSections(); });
    paint();
    loadSections();
    if (o.feed !== false) { load(); follow(); }
    return true;
  }

  const ProjectRail = {model, html, mount, set, open: setOpen, load, loadSections, repaint: () => paint(true),
    state: () => ({mounted: S.mounted, open: S.open, current: S.current, doc: S.doc}), WORDS, ORG_HREF};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ProjectRail;
  else root.ProjectRail = ProjectRail;
})(globalThis);
