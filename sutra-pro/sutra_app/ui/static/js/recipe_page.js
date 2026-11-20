/* recipe_page.js - the Recipes page at /recipes (DV-3): the client and the glue.

   `create(opts)` returns the controller; `opts` carries what it touches (doc, api, newId), so a test drives it with fakes.
   Reads:  GET /api/recipes?archived=   GET /api/recipes/{id}
   Writes: POST /api/recipes   PUT /api/recipes/{id}   POST /api/recipes/{id}/revert|archive|copy|start   POST /api/recipes/import
   Starting sends one `client_id`, made when the form opens, so a double press starts nothing twice. What the server refuses is shown in its own words. A classic script with ONE global, RecipePage; in node
   it is module.exports. In a page that holds #recipes-root it starts itself. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const View = () => (typeof require === "function" && typeof module === "object" ? require("./recipe_view.js") : root.RecipeView);
  const enc = encodeURIComponent;

  function words(e) {
    const m = e && typeof e.message === "string" ? e.message.trim() : "";
    if (e && e.status === 0) return "Sutra could not be reached. Check that it is still open.";
    return m && m.length < 300 ? m : "That did not work. Try again.";
  }

  function randomId() {
    const bytes = new Uint8Array(12);
    (root.crypto || {getRandomValues: a => a.fill(7)}).getRandomValues(bytes);
    return "r" + Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");
  }

  function create(opts) {
    const o = isObj(opts) ? opts : {};
    const doc = o.doc;
    const api = o.api;
    const view = View();
    const newId = o.newId || randomId;
    const el = id => (doc && doc.getElementById ? doc.getElementById(id) : null);
    const S = {recipes: [], archived: false, open: null, mode: "", draft: null, error: "", sent: "", clientId: "", loaded: false, listError: ""};
    let painted = {};

    function paint(id, html) {
      const node = el(id);
      if (!node || painted[id] === html) return;
      node.innerHTML = html;
      painted[id] = html;
    }

    function render() {
      paint("r-list", (S.listError ? '<p class="cerr" role="alert">' + view.esc(S.listError) + "</p>" : "") + (S.loaded ? view.listHtml(S.recipes) : '<p class="cempty">Loading&hellip;</p>'));
      let detail = "";
      if (S.mode === "edit" || S.mode === "new") detail = view.editHtml(S.draft, S);
      else if (S.mode === "import") detail = view.importHtml(S);
      else if (S.open) detail = view.detailHtml(S.open, S) + (S.mode === "start" ? view.startHtml(S.open, S) : "");
      paint("r-detail", detail);
    }

    async function refresh() {
      try {
        const found = await api.get("/api/recipes", S.archived ? {archived: 1} : undefined);
        S.recipes = Array.isArray(found) ? found : [];
        S.listError = "";
        S.loaded = true;
      } catch (e) {
        S.listError = words(e);
      }
      render();
      return S.loaded;
    }

    async function open(id) {
      if (!view.ID.test(String(id))) return false;
      try {
        S.open = await api.get("/api/recipes/" + enc(id));
        S.mode = "";
        S.error = "";
        S.sent = "";
      } catch (e) {
        S.listError = words(e);
      }
      render();
      return !!S.open;
    }

    const close = () => { S.open = null; S.mode = ""; S.draft = null; S.error = ""; S.sent = ""; render(); };

    function readForm(form) {
      const f = form.elements || {};
      const v = name => (f[name] ? f[name].value : "");
      const body = {overview: String(v("overview")).trim(), needs: view.toLines(v("needs")).map(label => ({label}))};
      view.PARTS.forEach(([p]) => { body[p] = view.toLines(v(p)); });
      return {title: String(v("title")).trim(), body, note: String(v("note")).trim()};
    }

    async function save(form) {
      const got = readForm(form);
      const id = form.dataset ? form.dataset.id : "";
      try {
        const made = id ? await api.put("/api/recipes/" + enc(id), got) : await api.post("/api/recipes", got);
        S.error = "";
        S.mode = "";
        S.draft = null;
        await refresh();
        return open(made.id);
      } catch (e) {
        S.error = words(e);
        S.draft = Object.assign({}, S.draft || {}, {id, title: got.title, body: got.body});
        S.mode = id ? "edit" : "new";                                           // the form stays open with what was typed
        render();
        return false;
      }
    }

    async function start(form) {
      const needs = S.open && S.open.body ? S.open.body.needs.length : 0;
      const blanks = [];
      for (let i = 0; i < needs; i += 1) blanks.push(String(form.elements && form.elements["blank" + i] ? form.elements["blank" + i].value : "").trim());
      try {
        const sent = await api.post("/api/recipes/" + enc(S.open.id) + "/start", {blanks, client_id: S.clientId});
        S.sent = sent.duplicate ? "That was already sent." : "Sent to Sutra. Look at the chat on Home: Sutra will plan it and ask you what it needs to ask.";
        S.mode = "";
        S.error = "";
      } catch (e) {
        S.error = words(e);
      }
      render();
      return !S.error;
    }

    async function readFile(form) {
      try {
        const draft = await api.post("/api/recipes/import", {markdown: String(form.elements && form.elements.markdown ? form.elements.markdown.value : "")});
        S.draft = Object.assign({}, draft, {id: ""});
        S.mode = "new";
        S.error = "";
      } catch (e) {
        S.error = words(e);
      }
      render();
      return S.mode === "new";
    }

    async function act(name, d) {
      if (name === "open") return open(d.id);
      if (name === "close" || name === "start-cancel") { if (name === "start-cancel") { S.mode = ""; S.error = ""; render(); return true; } return close(); }
      if (name === "new") { S.open = null; S.mode = "new"; S.draft = {id: "", title: "", body: {procedure: [""]}}; S.error = ""; render(); return true; }
      if (name === "import-open") { S.open = null; S.mode = "import"; S.error = ""; render(); return true; }
      if (name === "toggle-archived") { S.archived = !S.archived; return refresh(); }
      if (name === "edit" && S.open) { S.mode = "edit"; S.draft = {id: S.open.id, title: S.open.title, body: S.open.body}; S.error = ""; render(); return true; }
      if (name === "start-open" && S.open) { S.mode = "start"; S.clientId = newId(); S.error = ""; S.sent = ""; render(); return true; }
      try {
        if (name === "copy" && S.open) { const made = await api.post("/api/recipes/" + enc(S.open.id) + "/copy", {}); await refresh(); return open(made.id); }
        if (name === "archive" && S.open) { await api.post("/api/recipes/" + enc(S.open.id) + "/archive", {archived: d.archived === "1"}); close(); return refresh(); }
        if (name === "revert" && S.open) { const made = await api.post("/api/recipes/" + enc(S.open.id) + "/revert", {version: Number(d.version)}); await refresh(); return open(made.id); }
      } catch (e) {
        S.error = words(e);
        render();
      }
      return false;
    }

    function onClick(event) {
      const b = event && event.target && event.target.closest ? event.target.closest("button[data-act]") : null;
      if (b) act(b.dataset.act, b.dataset || {});
    }

    function onSubmit(event) {
      const form = event && event.target && event.target.closest ? event.target.closest("form[data-act]") : null;
      if (!form) return;
      if (typeof event.preventDefault === "function") event.preventDefault();
      const what = (form.dataset || {}).act;
      if (what === "save") save(form);
      else if (what === "start") start(form);
      else if (what === "import") readFile(form);
    }

    return {start: async () => { render(); return refresh(); }, refresh, open, act, save, onClick, onSubmit, render, state: () => S};
  }

  function boot() {
    const ctx = root.SutraCtx;
    if (!ctx || !ctx.api) return null;
    const page = create({doc: root.document, api: ctx.api});
    const main = root.document.getElementById("recipes-root");
    if (main) { main.addEventListener("click", page.onClick); main.addEventListener("submit", page.onSubmit); }
    root.RecipePageController = page;
    page.start().catch(e => { if (root.console) root.console.error("RecipePage: start failed", e); });
    return page;
  }

  const RecipePage = {create, boot, words};
  if (typeof module === "object" && module !== null && module.exports) module.exports = RecipePage;
  else {
    root.RecipePage = RecipePage;
    const start = () => { if (root.document && root.document.getElementById("recipes-root")) boot(); };
    if (root.document && root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", start);
    else start();
  }
})(globalThis);
