/* project_rail.js - the project sidebar on Home and on every team page (Sutra's own; J2's page is not edited for it: dept_ext.js adds it).

   One column on the left, the same on every page: "+ New project" at the top, then "Needs you" (projects with an open question or an
   approval, with a count), then "Projects" (every team: being made, needs you, done), the open project marked, and one quiet
   "Settings & logs" link at the bottom. On a phone it folds away behind a menu button.

     ProjectRail.model(departments, needs)   {needs: [{id, name, href, count}], projects: [{id, name, href, state, words}]}
                                             from GET /api/departments and GET /api/needs-you; nothing else is read
     ProjectRail.html(model, current)        the column's inner markup; `current` is the open team's id ("" on Home)
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
  const teamHref = id => "/d/" + encodeURIComponent(id) + "/?view=simple";

  const MAKING = ["running", "waiting"];
  const DONE = ["filed", "done_unchecked", "left_open"];
  // the state of a project as a first-time owner reads it; the mark is drawn by the style sheet (pr-<state>)
  const WORDS = {needs: "Needs your answer", making: "Being made", problem: "Something broke", done: "Done", idle: "Not started yet"};
  const POLL_MS = 8000;            // a team page: read the two lists this often (Home hands them in from its own live reads)

  /* ---------------------------------------------------------------- pure parts */
  function model(departments, needs) {
    const asks = new Map();
    let approvals = 0;
    (Array.isArray(needs) ? needs : []).filter(isObj).forEach(n => {
      const dept = idOf(n.dept_id);
      if (dept) asks.set(dept, (asks.get(dept) || 0) + 1);
      else approvals += 1;                       // an org change waiting for a yes: it belongs to no project
    });
    const projects = (Array.isArray(departments) ? departments : []).filter(d => isObj(d) && idOf(d.id)).map(d => {
      const status = text(d.node_status);
      const state = asks.has(d.id) || status === "waiting_on_you" ? "needs" : status === "fault" ? "problem"
        : MAKING.includes(status) || idOf(d.live_task_id) ? "making" : DONE.includes(status) ? "done" : "idle";
      return {id: d.id, name: clean(d.name) || d.id, href: teamHref(d.id), state, words: WORDS[state]};
    });
    const named = new Map(projects.map(p => [p.id, p.name]));
    const list = [...asks.entries()].map(([id, count]) => ({id, name: named.get(id) || id, href: teamHref(id), count}));
    if (approvals > 0) list.push({id: "", name: "Your organisation", href: "/?pane=chart", count: approvals});
    return {needs: list, projects};
  }

  function html(m, current) {
    const cur = text(current);
    const mark = (state, words) => '<i class="pr-mark pr-' + esc(state) + '" aria-hidden="true"></i><span class="pr-sr">' + esc(words) + ", </span>";
    // the open project is marked once, in Projects (its Needs you row is only tinted)
    const row = (p, extra, own) => '<li><a class="pr-item' + (p.id && p.id === cur ? " pr-on" : "") + '" href="' + esc(p.href) + '"' +
      (own && p.id && p.id === cur ? ' aria-current="page"' : "") +(p.words ? ' title="' + esc(p.words) + '"' : "") + ">" + extra + '<span class="pr-name">' + esc(p.name) + "</span>" +
      (p.count ? '<b class="pr-count" aria-label="' + p.count + (p.count === 1 ? " question" : " questions") + '">' + p.count + "</b>" : "") + "</a></li>";
    const needs = m && Array.isArray(m.needs) ? m.needs : [];
    const projects = m && Array.isArray(m.projects) ? m.projects : [];
    const needsHtml = needs.length ? '<section class="pr-group" aria-labelledby="pr-needs-h"><h2 class="pr-head" id="pr-needs-h">Needs you</h2><ul class="pr-list">' +
      needs.map(n => row(Object.assign({words: "Needs your answer"}, n), mark("needs", "Needs your answer"))).join("") + "</ul></section>" : "";
    const projHtml = '<section class="pr-group" aria-labelledby="pr-proj-h"><h2 class="pr-head" id="pr-proj-h">Projects</h2>' +
      (projects.length ? '<ul class="pr-list">' + projects.map(p => row(p, mark(p.state, p.words), true)).join("") + "</ul>"
        : '<p class="pr-empty">Your projects show here.</p>') + "</section>";
    return needsHtml + projHtml;
  }

  /* ---------------------------------------------------------------- the page */
  const doc = () => root.document || null;
  const ctx = () => root.SutraCtx || null;
  const S = {mounted: false, el: null, list: null, btn: null, departments: [], needs: [], current: "", timer: null, open: false};

  function paint() {
    if (!S.list) return;
    const next = html(model(S.departments, S.needs), S.current);
    if (S.list.dataset.html !== next) { S.list.innerHTML = next; S.list.dataset.html = next; }
    if (S.btn) {
      const n = model(S.departments, S.needs).needs.reduce((a, b) => a + b.count, 0);
      const badge = S.btn.querySelector(".pr-btnbadge");
      if (badge) { badge.hidden = n === 0; badge.textContent = String(n); }
      S.btn.setAttribute("aria-label", n ? "Projects, " + n + " need you" : "Projects");
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
    aside.setAttribute("aria-label", "Your projects");
    aside.innerHTML = '<a class="pr-new" id="pr-new" href="/"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>New project</a>' +
      '<nav class="pr-body" id="pr-body" aria-label="Projects"></nav>' +
      '<a class="pr-foot" id="pr-settings" href="/?pane=settings">Settings &amp; logs</a>';
    const btn = d.createElement("button");
    btn.type = "button";
    btn.className = "pr-btn";
    btn.id = "prailbtn";
    btn.setAttribute("aria-controls", "prail");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", "Projects");
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
    S.btn = btn;
    btn.addEventListener("click", () => setOpen(!S.open));
    aside.querySelector("#pr-new").addEventListener("click", onNew);
    d.addEventListener("keydown", e => { if (e.key === "Escape" && S.open) { setOpen(false); btn.focus(); } });
    paint();
    if (o.feed !== false) { load(); follow(); }
    return true;
  }

  const ProjectRail = {model, html, mount, set, open: setOpen, load, state: () => ({mounted: S.mounted, open: S.open, current: S.current}), WORDS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ProjectRail;
  else root.ProjectRail = ProjectRail;
})(globalThis);
