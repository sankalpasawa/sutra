/* work_page.js - the Work page at /work (DV-2): the client and the glue.

   `create(opts)` returns the controller; `opts` carries what it touches (doc, api, setTimeout, clearTimeout), so a test drives it with fakes.
   Reads:  GET /api/work?tag=&q=&status=   GET /api/work/tags   GET /api/projects/{id}/summary
   Writes: PUT /api/work/{kind}/{id}/tags {tags}
   The search box asks after a short pause (SEARCH_MS), a tag or a state at once. Nothing here decides what a tag may be: the server says, and its sentence is shown. A classic script with ONE global,
   WorkPage; in node it is module.exports. In a page that holds #work-root it starts itself. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const SEARCH_MS = 300;
  const KIND = /^(task|project)$/;
  const ID = /^(tsk|prj)_[0-9a-f]{12}$/;
  const View = () => (typeof require === "function" && typeof module === "object" ? require("./work_view.js") : root.WorkView);
  const enc = encodeURIComponent;

  function words(e) {
    const m = e && typeof e.message === "string" ? e.message.trim() : "";
    if (e && e.status === 0) return "Sutra could not be reached. Check that it is still open.";
    return m && m.length < 240 ? m : "That did not work. Try again.";
  }

  function create(opts) {
    const o = isObj(opts) ? opts : {};
    const doc = o.doc;
    const api = o.api;
    const view = View();
    const el = id => (doc && doc.getElementById ? doc.getElementById(id) : null);
    const later = o.setTimeout || (root.setTimeout && root.setTimeout.bind(root));
    const cancel = o.clearTimeout || (root.clearTimeout && root.clearTimeout.bind(root));
    const S = {items: [], tags: [], filter: {tag: "", q: "", status: ""}, statuses: [], editing: "", summaries: {}, error: "", loaded: false};
    let timer = null;
    let painted = {};
    let sequence = 0;

    function paint(id, html) {
      const node = el(id);
      if (!node || painted[id] === html) return;
      const active = doc && doc.activeElement && doc.activeElement.id && node.contains && node.contains(doc.activeElement) ? doc.activeElement.id : "";
      node.innerHTML = html;
      painted[id] = html;
      if (active) { const back = el(active); if (back && typeof back.focus === "function") back.focus(); }
    }

    function render() {
      const filtered = !!(S.filter.tag || S.filter.q || S.filter.status);
      paint("w-filters", view.filtersHtml(S.tags, S.filter, S.statuses));
      paint("w-list", (S.error ? '<p class="cerr" role="alert">' + view.esc(S.error) + "</p>" : "") + (S.loaded ? view.listHtml(S.items, {editing: S.editing, summaries: S.summaries, filtered}) : '<p class="cempty">Loading&hellip;</p>'));
    }

    function query() {
      const q = {limit: 200};
      if (S.filter.tag) q.tag = S.filter.tag;
      if (S.filter.q) q.q = S.filter.q;
      if (S.filter.status) q.status = S.filter.status;
      return q;
    }

    async function refresh() {
      const mine = ++sequence;                                                  // a slower answer to an older question never replaces a newer one
      try {
        const [items, tags] = await Promise.all([api.get("/api/work", query()), api.get("/api/work/tags")]);
        if (mine !== sequence) return false;
        S.items = Array.isArray(items) ? items : [];
        S.tags = Array.isArray(tags) ? tags : [];
        if (!S.filter.status && !S.filter.tag && !S.filter.q) S.statuses = Array.from(new Set(S.items.map(i => i && i.status).filter(Boolean)));
        S.error = "";
        S.loaded = true;
      } catch (e) {
        if (mine !== sequence) return false;
        S.error = words(e);
      }
      render();
      return S.loaded;
    }

    function setFilter(part) {
      Object.assign(S.filter, part);
      return refresh();
    }

    function typed(text) {
      S.filter.q = String(text || "").trim();
      if (timer !== null && cancel) cancel(timer);
      timer = later ? later(() => { timer = null; refresh(); }, SEARCH_MS) : null;
    }

    async function saveTags(kind, id, tags) {
      if (!KIND.test(kind) || !ID.test(id)) return false;
      try {
        await api.put("/api/work/" + kind + "/" + enc(id) + "/tags", {tags});
        S.editing = "";
        S.error = "";
      } catch (e) {
        S.error = words(e);
        render();
        return false;
      }
      return refresh();
    }

    async function how(id) {
      if (!ID.test(id) || !/^prj_/.test(id)) return false;
      S.summaries[id] = "loading";
      render();
      try {
        S.summaries[id] = await api.get("/api/projects/" + enc(id) + "/summary");
      } catch (e) {
        S.summaries[id] = {error: e && e.status === 404 ? "There is nothing to say about that project." : words(e)};
      }
      render();
      return true;
    }

    function onClick(event) {
      const b = event && event.target && event.target.closest ? event.target.closest("button[data-act]") : null;
      if (!b) return;
      const d = b.dataset || {};
      if (d.act === "filter-tag") setFilter({tag: S.filter.tag === d.tag ? "" : d.tag});
      else if (d.act === "tags-edit") { S.editing = d.id || ""; render(); }
      else if (d.act === "tags-cancel") { S.editing = ""; render(); }
      else if (d.act === "how") how(d.id || "");
    }

    function onSubmit(event) {
      const form = event && event.target && event.target.closest ? event.target.closest("form[data-act]") : null;
      if (!form || (form.dataset || {}).act !== "tags-save") return;
      if (typeof event.preventDefault === "function") event.preventDefault();
      const field = form.elements && form.elements.tags ? form.elements.tags : form.querySelector && form.querySelector("input");
      saveTags(form.dataset.kind, form.dataset.id, view.tagsFromText(field ? field.value : ""));
    }

    function onInput(event) {
      const t = event && event.target;
      if (t && t.id === "w-q") typed(t.value);
    }

    function onChange(event) {
      const t = event && event.target;
      if (t && t.id === "w-status") setFilter({status: t.value || ""});
    }

    async function start() {
      render();
      return refresh();
    }

    return {start, refresh, setFilter, typed, saveTags, how, onClick, onSubmit, onInput, onChange, render, state: () => S};
  }

  function boot() {
    const ctx = root.SutraCtx;
    if (!ctx || !ctx.api) return null;
    const page = create({doc: root.document, api: ctx.api});
    const main = root.document.getElementById("work-root");
    if (main) {
      main.addEventListener("click", page.onClick);
      main.addEventListener("submit", page.onSubmit);
      main.addEventListener("input", page.onInput);
      main.addEventListener("change", page.onChange);
    }
    root.WorkPageController = page;
    page.start().catch(e => { if (root.console) root.console.error("WorkPage: start failed", e); });
    return page;
  }

  const WorkPage = {create, boot, words, SEARCH_MS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = WorkPage;
  else {
    root.WorkPage = WorkPage;
    const start = () => { if (root.document && root.document.getElementById("work-root")) boot(); };
    if (root.document && root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", start);
    else start();
  }
})(globalThis);
