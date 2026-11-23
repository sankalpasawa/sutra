/* project_page.js - the project page at /p/<id> (MAN-13, D326): the client and the glue to the page.

   The third layer (project_store.js, project_view.js, this file). `create(opts)` returns the controller; `opts` carries everything it touches (doc, api, EventSourceCtor, setTimeout,
   clearTimeout, setInterval, clearInterval, id), so a test drives it with fakes.

   What it reads:   GET /api/projects/{id}   GET /api/projects/{id}/messages?after=   GET /api/projects/{id}/audit?after=   GET /api/nodes/app-location
   What it writes:  POST /api/projects/{id}/approvals/{aid} {decision}   POST /api/projects/{id}/system/{item}/check|skip   POST /api/projects/{id}/stop   POST /api/projects/{id}/pause {resume}
                    POST /api/nodes/{id}/stop
   Events are invalidations: `project.*` and `node.updated` (and `task.updated`) make it refetch, coalesced to one refetch in COALESCE_MS. The stream is its own EventSource on
   /api/events?topics=project,node,task (the shared client lists only the 18 names of the older pages, and changing that moves other pages). While the stream is down the page asks every
   POLL_MS; a slow refresh every SLOW_MS covers a missed event on a stream that says it is live. The messages are read from the last whole number (`after=`), and a gap is read again.

   A classic script with ONE global, ProjectPage; in node it is module.exports. In a page that holds #project-root it starts itself. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const COALESCE_MS = 400;
  const POLL_MS = 3000;
  const SLOW_MS = 20000;
  const PAGE_LIMIT = 200;
  const EVENTS = Object.freeze(["project.created", "project.updated", "project.message", "node.updated", "task.updated", "server.hello", "server.resync"]);
  const ID = /^prj_[0-9a-f]{12}$/;
  const NODE = /^nd_[0-9a-f]{12}$/;
  const Store = () => (typeof require === "function" && typeof module === "object" ? require("./project_store.js") : root.ProjectStore);
  const View = () => (typeof require === "function" && typeof module === "object" ? require("./project_view.js") : root.ProjectView);
  const enc = encodeURIComponent;

  // The words of a failed request: the app's own message when it has one, else a plain sentence.
  function errorWords(e) {
    const m = e && typeof e.message === "string" ? e.message.trim() : "";
    if (e && e.status === 0) return "Sutra could not be reached. Check that it is still open.";
    return m && m.length < 200 ? m : "That did not work. Try again.";
  }

  function create(opts) {
    const o = isObj(opts) ? opts : {};
    const doc = o.doc;
    const api = o.api;
    const id = o.id;
    const store = Store().create();
    const view = View();
    const el = name => (doc && doc.getElementById ? doc.getElementById(name) : null);
    const later = o.setTimeout || (root.setTimeout && root.setTimeout.bind(root));
    const cancel = o.clearTimeout || (root.clearTimeout && root.clearTimeout.bind(root));
    const every = o.setInterval || (root.setInterval && root.setInterval.bind(root));
    const stopEvery = o.clearInterval || (root.clearInterval && root.clearInterval.bind(root));
    const Source = o.EventSourceCtor || root.EventSource;
    let location = null;
    let source = null;
    let soon = null;
    let poll = null;
    let slow = null;
    let busy = false;
    let again = false;
    let stopped = false;
    let gone = false;
    let painted = {};

    function paint(name, html) {
      const node = el(name);
      if (!node || painted[name] === html) return;
      const active = doc && doc.activeElement && doc.activeElement.id && node.contains && node.contains(doc.activeElement) ? doc.activeElement.id : "";
      node.innerHTML = html;
      painted[name] = html;
      if (active) { const back = el(active); if (back && typeof back.focus === "function") back.focus(); }
    }

    function render() {
      const S = store.state();
      paint("p-head", S.snapshot ? view.header(S.snapshot) : "");
      paint("p-body", view.page(S, location));
      const live = el("p-live");
      const over = S.snapshot && S.snapshot.project && ["done", "done_with_open_items", "stopped", "failed"].indexOf(S.snapshot.project.status) >= 0;      // "Live" says it is being watched: nothing runs any more (D413)
      if (live) live.textContent = over ? "" : S.live === "live" ? "Live" : S.live === "polling" ? "Updating every few seconds" : "Not connected";
      if (S.snapshot && doc && doc.title !== undefined) doc.title = (S.snapshot.project.title || "Project") + " - Sutra";
    }

    /* ---- reads */
    async function readAll(path, after, put) {
      for (let guard = 0; guard < 50; guard += 1) {                   // pages of PAGE_LIMIT, so a long project is read whole and the loop still ends
        const rows = await api.get(path, {after, limit: PAGE_LIMIT});
        const list = Array.isArray(rows) ? rows : [];
        const result = put(list);
        if (result === false || list.length < PAGE_LIMIT) return result;
        after = list[list.length - 1].seq;
      }
      return true;
    }

    async function refresh() {
      if (busy) { again = true; return false; }
      busy = true;
      try {
        do {
          again = false;
          store.setSnapshot(await api.get("/api/projects/" + enc(id)));
          if (!store.state().loaded) break;
          await readAll("/api/projects/" + enc(id) + "/audit", store.state().auditAfter, rows => { store.addAudit(rows); return true; });
          if (store.behind()) {
            const first = await readAll("/api/projects/" + enc(id) + "/messages", store.state().seq, rows => !store.addMessages(rows).gap);
            if (first === false) {                                       // a gap: start again from the last whole number, once
              await readAll("/api/projects/" + enc(id) + "/messages", store.state().seq, rows => !store.addMessages(rows).gap);
            }
          }
        } while (again && !stopped);
      } catch (e) {
        gone = !!(e && e.status === 404);
        store.setError(gone ? "That project is not here any more." : errorWords(e));
      } finally {
        busy = false;
      }
      render();
      return store.state().loaded;
    }

    async function loadLocation() {
      try { location = await api.get("/api/nodes/app-location"); } catch (e) { location = null; }       // the note is a courtesy: no note when it cannot be read
    }

    /* ---- the events */
    function invalidate() {
      if (stopped || soon !== null || !later) return;
      soon = later(() => { soon = null; refresh(); }, COALESCE_MS);
    }

    function setLive(state) {
      store.setLive(state);
      render();
    }

    function onEvent(type, data) {
      if (type === "server.hello" || type === "server.resync") { invalidate(); return; }
      const mine = !isObj(data) || data.project_id === undefined || data.project_id === id;      // a task event carries no project: it may be ours
      if (mine) invalidate();
    }

    function openStream() {
      if (!Source || stopped) return setLive("offline");
      try {
        source = new Source("/api/events?topics=project,node,task");
      } catch (e) {
        return startPolling();
      }
      source.addEventListener("open", () => { stopPolling(); setLive("live"); });
      source.addEventListener("error", () => { if (!stopped) startPolling(); });
      EVENTS.forEach(name => source.addEventListener(name, event => {
        let data = {};
        try { data = JSON.parse(event && event.data); } catch (e) { data = {}; }
        onEvent(name, data);
      }));
    }

    function startPolling() {
      setLive("polling");
      if (poll === null && every) poll = every(async () => {              // a page that never loaded keeps asking, and opens the stream once it has
        await refresh();
        if (store.state().loaded && source === null && !stopped) { stopPolling(); startLive(); }
      }, POLL_MS);
    }

    function stopPolling() {
      if (poll !== null && stopEvery) stopEvery(poll);
      poll = null;
    }

    /* ---- the owner's answers */
    async function act(button) {
      const d = button.dataset || {};
      const act = d.act;
      let url = "";
      let body = {};
      if (act === "node-answer") {
        if (!ID.test(d.project || "") || d.project !== id) return false;
        if (d.decision === "check_again" || d.decision === "skip") { url = "/api/projects/" + enc(id) + "/system/" + enc(d.item || "") + "/" + (d.decision === "skip" ? "skip" : "check"); }
        else { url = "/api/projects/" + enc(id) + "/approvals/" + enc(d.approval || ""); body = {decision: d.decision}; }
      } else if (act === "step-answer") {                      // the answer to a question of a step's own engine: the chat route of that team, as Home does (D401)
        if (!/^cs_[A-Za-z0-9_-]{1,64}$/.test(d.session || "") || !/^Option \d{1,2}$/.test(d.text || "")) return false;
        url = "/api/chats/" + enc(d.session) + "/messages";
        body = {text: d.text};
      } else if (act === "project-stop") {
        url = "/api/projects/" + enc(id) + "/stop";
      } else if (act === "project-pause") {
        url = "/api/projects/" + enc(id) + "/pause";
        body = {resume: d.resume === "1"};
      } else if (act === "node-stop") {
        if (!NODE.test(d.node || "")) return false;
        url = "/api/nodes/" + enc(d.node) + "/stop";
      } else {
        return false;
      }
      button.disabled = true;
      try {
        await api.post(url, body);
        store.setError("");
      } catch (e) {
        store.setError(errorWords(e));
        button.disabled = false;
        render();
        return false;
      }
      await refresh();
      return true;
    }

    function onClick(event) {
      const button = event && event.target && event.target.closest ? event.target.closest("button[data-act]") : null;
      if (!button) return;
      if (typeof event.preventDefault === "function") event.preventDefault();
      act(button);
    }

    function startLive() {
      openStream();
      if (slow === null && every) slow = every(() => refresh(), SLOW_MS);
    }

    async function start() {
      if (!ID.test(String(id))) { store.setError("That is not a project."); render(); return false; }
      render();
      await loadLocation();
      const ok = await refresh();
      if (ok) startLive();
      else if (!gone && !stopped) startPolling();
      return ok;
    }

    function stop() {
      stopped = true;
      if (source && typeof source.close === "function") source.close();
      source = null;
      stopPolling();
      if (soon !== null && cancel) cancel(soon);
      soon = null;
      if (slow !== null && stopEvery) stopEvery(slow);
      slow = null;
    }

    return {start, stop, refresh, onEvent, onClick, act, render, state: () => store.state(), invalidate, isStopped: () => stopped};
  }

  /* ---------------------------------------------------------------- the page */
  function idFromPath(path) {
    const found = /^\/p\/(prj_[0-9a-f]{12})\/?$/.exec(typeof path === "string" ? path : "");
    return found ? found[1] : "";
  }

  function boot() {
    const ctx = root.SutraCtx;
    if (!ctx || !ctx.api) return null;
    const page = create({doc: root.document, api: ctx.api, id: idFromPath(root.location && root.location.pathname)});
    const main = root.document.getElementById("project-root");
    if (main) main.addEventListener("click", page.onClick);
    root.ProjectPageController = page;
    page.start().catch(e => { if (root.console) root.console.error("ProjectPage: start failed", e); });
    return page;
  }

  const ProjectPage = {create, boot, idFromPath, errorWords, COALESCE_MS, POLL_MS, SLOW_MS, EVENTS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ProjectPage;
  else {
    root.ProjectPage = ProjectPage;
    const start = () => { if (root.document && root.document.getElementById("project-root")) boot(); };
    if (root.document && root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", start);
    else start();
  }
})(globalThis);
