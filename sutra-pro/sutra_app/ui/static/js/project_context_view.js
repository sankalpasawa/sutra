/* project_context_view.js - "Project files and memory" (D451, T11, T13, T14): the one panel for what a project keeps and what a model is given of it.

   Four sections of one project (a team, D426): Files (add, "Use in this project" switch, rename, remove, how they reach a chat), Instructions (one free-text field with a revision check),
   Memory (what the project remembers of its earlier work: read, edit, add, delete, switch off) and "What will be sent" (the exact text a chat and a run would be given now, as the server
   says it: GET /api/teams/<project>/context). The words are the owner's: project, files, memory; never department, node or a hash. Strings in, strings out, plus ONE controller that takes
   the api and the element it draws into, so node tests drive it without a page. Every word from the wire is escaped.

     filesHtml(files)  instructionsHtml(instr, ui)  memoryHtml(memory)  previewHtml(context)  panelHtml(state)      the markup, pure
     summaryLine(files, memory)     "3 files · memory on" ("" when there is nothing to say); usingLine(context)  "Using 4 project files, memory on"
     mount({el, api, onClose, readFile})  -> {open({dept, name}), close(), state()}

   A classic script with ONE global, ProjectContextView; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const num = n => (Number.isFinite(n) ? Math.round(n).toLocaleString("en-US") : "0");
  const SENT = "Files you add are sent to the model you choose (Claude or Codex) when a chat or run uses them.";
  const NOT_READ = "Excel and PowerPoint files are not read. PDFs and images are kept for reference only.";
  const STALE = "Changed since you opened it. Reload to see the new text.";
  const FAILED = "That did not work. Try again.";
  const MODE_WORDS = {
    whole: "All the text of these files goes in whole, with every message.",
    excerpts: "These files are too long to paste whole, so each message gets the parts that match it best.",
    none: "No file is switched on for this project.",
  };

  function size(n) {
    const v = Number.isFinite(n) ? Math.max(0, n) : 0;
    if (v < 1024) return Math.round(v) + " B";
    if (v < 1024 * 1024) return (v / 1024).toFixed(1) + " KB";
    return (v / (1024 * 1024)).toFixed(1) + " MB";
  }

  const KIND_WORDS = {text: "text", image: "image", pdf: "PDF"};

  /* ---------------------------------------------------------------- files */
  function fileRow(f, ui) {
    const name = clean(f.name);
    const id = esc(clean(f.id));
    const renaming = isObj(ui) && ui.renaming === f.id;
    const label = renaming
      ? '<input class="pcv-name" data-id="' + id + '" value="' + esc(name) + '" aria-label="New name for ' + esc(name) + '"/> <button type="button" class="linkbtn" data-act="pcv-rename-save" data-id="' + id + '">Save</button>'
      : '<span class="pcv-fname">' + esc(name) + "</span>";
    const kind = KIND_WORDS[clean(f.kind)] || "file";
    const how = f.reference_only === true ? "reference only: its content is not read" : num(f.chars) + " characters";
    return '<li class="pcv-file' + (f.enabled === false ? " off" : "") + '"><label class="pcv-use"><input type="checkbox" role="switch" data-act="pcv-toggle" data-id="' + id + '"' + (f.enabled === false ? "" : " checked") +
      ' aria-label="Use ' + esc(name) + ' in this project"/> Use in this project</label> ' + label + " <small>" + esc(kind) + ", " + esc(size(f.size)) + ", " + esc(how) + "</small> " +
      (renaming ? "" : '<button type="button" class="linkbtn" data-act="pcv-rename" data-id="' + id + '" aria-label="Rename ' + esc(name) + '">Rename</button> ') +
      '<button type="button" class="linkbtn" data-act="pcv-remove" data-id="' + id + '" aria-label="Remove ' + esc(name) + ' from the project">Remove</button></li>';
  }

  function filesHtml(files, ui) {
    const d = isObj(files) ? files : {};
    const list = (Array.isArray(d.files) ? d.files : []).filter(isObj);
    const totals = isObj(d.totals) ? d.totals : {files: list.length, bytes: 0, chars: 0};
    const limits = isObj(d.limits) ? d.limits : {};
    const head = '<h3 id="pcv-files">Files</h3><p class="pcv-count" aria-live="polite">' + num(totals.files) + " of " + num(limits.max_files || 50) + " files, " + esc(size(totals.bytes)) + "</p>";
    const mode = MODE_WORDS[clean(d.mode)] || MODE_WORDS.none;
    const rows = list.length ? '<ul class="pcv-list" aria-labelledby="pcv-files">' + list.map(f => fileRow(f, ui)).join("") + "</ul>" : '<p class="pcv-empty">No files yet. Add the files every run and chat of this project should know.</p>';
    const clear = list.length ? (isObj(ui) && ui.confirmClear === true
      ? ' <span role="group" aria-label="Remove every file">Remove every file? <button type="button" class="linkbtn" data-act="pcv-clear-yes">Yes, remove all</button> <button type="button" class="linkbtn" data-act="pcv-clear-no">Keep them</button></span>'
      : ' <button type="button" class="linkbtn" data-act="pcv-clear">Remove all files</button>') : "";
    return '<section class="pcv-sec" aria-labelledby="pcv-files">' + head + rows + '<p class="pcv-mode">' + esc(list.length ? mode : "") + "</p>" +
      '<p class="pcv-acts"><button type="button" class="linkbtn" data-act="pcv-add">Add files</button><input type="file" class="pcv-input" multiple hidden tabindex="-1" aria-label="Choose files to add to the project"/>' + clear + "</p>" +
      '<p class="pcv-note">' + esc(NOT_READ) + "</p></section>";
  }

  /* ---------------------------------------------------------------- instructions */
  function instructionsHtml(instr, ui) {
    const i = isObj(instr) ? instr : {};
    const u = isObj(ui) ? ui : {};
    const value = typeof u.draft === "string" ? u.draft : text(i.text);
    const max = Number.isFinite(i.max_chars) ? i.max_chars : 4000;
    const error = clean(u.instrError);
    return '<section class="pcv-sec" aria-labelledby="pcv-instr"><h3 id="pcv-instr">Instructions</h3><p class="pcv-note">Your words for this project. They go in front of every run and chat of it.</p>' +
      '<textarea class="pcv-text" rows="5" maxlength="' + esc(max * 4) + '" aria-label="Project instructions" aria-describedby="pcv-icount">' + esc(value) + "</textarea>" +
      '<p id="pcv-icount" class="pcv-count">' + num(Array.from(value).length) + " of " + num(max) + " characters</p>" +
      (error ? '<p class="pcv-err" role="alert">' + esc(error) + (u.stale === true ? ' <button type="button" class="linkbtn" data-act="pcv-reload">Reload</button>' : "") + "</p>" : "") +
      '<p class="pcv-acts"><button type="button" class="linkbtn" data-act="pcv-save-instr">Save instructions</button></p></section>';
  }

  /* ---------------------------------------------------------------- memory */
  function memoryHtml(memory, ui) {
    const m = isObj(memory) ? memory : {};
    const entries = (Array.isArray(m.entries) ? m.entries : []).filter(isObj);
    const on = m.enabled !== false;
    const u = isObj(ui) ? ui : {};
    const rows = entries.length ? '<ul class="pcv-list" aria-labelledby="pcv-mem">' + entries.map(e => {
      const id = esc(String(e.n));
      const editing = u.editing === e.n;
      const body = editing ? '<textarea class="pcv-etext" data-n="' + id + '" rows="2" aria-label="Edit this line">' + esc(text(e.text)) + '</textarea> <button type="button" class="linkbtn" data-act="pcv-edit-save" data-n="' + id + '">Save</button>' : '<span class="pcv-etxt">' + esc(text(e.text)) + "</span>";
      const from = {run: "a run", chat: "a chat", owner: "you", history: "earlier history"}[clean(e.source)] || "";
      return '<li class="pcv-entry' + (e.on === false ? " off" : "") + '"><label class="pcv-use"><input type="checkbox" role="switch" data-act="pcv-entry-toggle" data-n="' + id + '"' + (e.on === false ? "" : " checked") + ' aria-label="Remember this line"/> Remember</label> ' + body +
        (from ? " <small>from " + esc(from) + "</small>" : "") + (editing ? "" : ' <button type="button" class="linkbtn" data-act="pcv-edit" data-n="' + id + '">Edit</button>') +
        ' <button type="button" class="linkbtn" data-act="pcv-entry-delete" data-n="' + id + '" aria-label="Delete this line">Delete</button></li>';
    }).join("") + "</ul>" : '<p class="pcv-empty">Nothing yet. A line is added when a run ends or a chat is archived.</p>';
    const error = clean(u.memError);
    return '<section class="pcv-sec" aria-labelledby="pcv-mem"><h3 id="pcv-mem">Memory</h3><label class="pcv-use"><input type="checkbox" role="switch" data-act="pcv-mem-toggle"' + (on ? " checked" : "") + ' aria-label="Remember earlier work in this project"/> ' +
      (on ? "Memory is on" : "Memory is off: nothing is sent and nothing new is kept") + "</label>" + rows +
      '<p class="pcv-acts"><input class="pcv-new" aria-label="Add a line of your own" placeholder="Add a line the project should remember" maxlength="300"/> <button type="button" class="linkbtn" data-act="pcv-add-line">Add</button></p>' +
      (error ? '<p class="pcv-err" role="alert">' + esc(error) + (u.memStale === true ? ' <button type="button" class="linkbtn" data-act="pcv-reload">Reload</button>' : "") + "</p>" : "") + "</section>";
  }

  /* ---------------------------------------------------------------- what will be sent */
  function previewHtml(context) {
    const c = isObj(context) ? context : {};
    const sizes = isObj(c.sizes) ? c.sizes : {};
    if (c.off === true) return '<section class="pcv-sec" aria-labelledby="pcv-sent"><h3 id="pcv-sent">What will be sent</h3><p class="pcv-empty">Project context is switched off on this computer: nothing of it is sent.</p></section>';
    const chat = text(c.chat_stable) + (text(c.chat_context) ? "\n\n" + text(c.chat_context) : "");
    return '<section class="pcv-sec" aria-labelledby="pcv-sent"><h3 id="pcv-sent">What will be sent</h3><p class="pcv-note">Exactly this goes to the model you choose when you ask in this project\'s chat (' + num(sizes.chat_stable) + " characters) and, in a run, this (" + num(sizes.run_block) + " characters).</p>" +
      '<details><summary>In a chat</summary><pre class="pcv-pre">' + esc(chat || "Nothing: the project has no file, no instructions and nothing remembered.") + "</pre></details>" +
      '<details><summary>In a run</summary><pre class="pcv-pre">' + esc(text(c.run_block) || "Nothing.") + "</pre></details></section>";
  }

  function summaryLine(files, memory) {
    const f = isObj(files) && Array.isArray(files.files) ? files.files.length : 0;
    const on = isObj(memory) && memory.enabled !== false && Array.isArray(memory.entries) && memory.entries.length > 0;
    if (f === 0 && !on) return "";
    return (f ? f + (f === 1 ? " file" : " files") : "") + (f && (on || (isObj(memory) && memory.enabled === false)) ? " · " : "") + (on ? "memory on" : (isObj(memory) && memory.enabled === false ? "memory off" : ""));
  }

  function usingLine(context) {
    const c = isObj(context) ? context : {};
    const used = Array.isArray(c.files_used) ? c.files_used.length : 0;
    const total = Number.isFinite(c.files_total) ? c.files_total : used;
    const mem = c.memory_on === true ? "memory on" : "memory off";
    if (used === 0 && total === 0) return c.memory_on === true ? "" : "";
    return used === total ? "Using " + used + " project " + (used === 1 ? "file" : "files") + ", " + mem : "Using " + used + " of " + total + " files; " + mem;
  }

  function panelHtml(state) {
    const s = isObj(state) ? state : {};
    const name = clean(s.name) || "this project";
    if (s.loading === true) return '<div class="pcv-card" role="dialog" aria-modal="true" aria-label="Project files and memory"><p>Loading…</p></div>';
    return '<div class="pcv-card" role="dialog" aria-modal="true" aria-label="Project files and memory"><div class="pcv-head"><h2>Project files and memory</h2><p class="pcv-sub">' + esc(name) +
      '</p><button type="button" class="linkbtn pcv-close" data-act="pcv-close" aria-label="Close">Close</button></div>' +
      (clean(s.error) ? '<p class="pcv-err" role="alert">' + esc(clean(s.error)) + "</p>" : "") +
      '<p class="pcv-note">' + esc(SENT) + "</p>" + filesHtml(s.files, s.ui) + instructionsHtml(s.instructions, s.ui) + memoryHtml(s.memory, s.ui) + previewHtml(s.context) + "</div>";
  }

  /* ---------------------------------------------------------------- the controller */
  const said = (e, fallback) => (isObj(e) && clean(e.message) ? clean(e.message) : fallback);

  function defaultRead(file) {
    return new Promise((resolve, reject) => {
      const Reader = root.FileReader;
      if (typeof Reader !== "function") { reject(new Error("This browser cannot read files.")); return; }
      const r = new Reader();
      r.onerror = () => reject(new Error("That file could not be read."));
      r.onload = () => resolve(String(r.result).split(",").slice(1).join(","));
      r.readAsDataURL(file);
    });
  }

  function mount(options) {
    const o = isObj(options) ? options : {};
    const el = o.el;
    const api = o.api;
    const readFile = typeof o.readFile === "function" ? o.readFile : defaultRead;
    const state = {open: false, loading: false, dept: "", name: "", error: "", files: null, instructions: null, memory: null, context: null, ui: {}};
    const base = () => "/api/teams/" + encodeURIComponent(state.dept);
    const ping = () => { if (typeof o.onChange === "function") o.onChange(summaryLine(state.files, state.memory)); };

    function draw() {
      if (!el) return;
      el.hidden = !state.open;
      el.innerHTML = state.open ? panelHtml(state) : "";
    }

    async function load() {
      const [files, instr, memory, context] = await Promise.all([api.get(base() + "/files"), api.get(base() + "/instructions"), api.get(base() + "/memory"), api.get(base() + "/context")]);
      Object.assign(state, {files, instructions: instr, memory, context});
      state.ui = {};
      ping();
    }

    async function refresh() {
      try { await load(); state.error = ""; } catch (e) { state.error = said(e, FAILED); }
      draw();
    }

    async function open(target) {
      const t = isObj(target) ? target : {};
      Object.assign(state, {open: true, loading: true, dept: clean(t.dept), name: clean(t.name), error: ""});
      draw();
      state.loading = false;
      await refresh();
    }

    function close() { state.open = false; draw(); if (typeof o.onClose === "function") o.onClose(); }

    async function addFiles(list) {
      const failures = [];
      for (const f of list) {
        try { await api.post(base() + "/files", {name: clean(f.name), content_b64: await readFile(f)}); } catch (e) { failures.push(clean(f.name) + ": " + said(e, FAILED)); }
      }
      await refresh();
      if (failures.length) { state.error = failures.join(" "); draw(); }
    }

    const entryList = (change) => (state.memory && Array.isArray(state.memory.entries) ? state.memory.entries : []).map(e => change({n: e.n, text: e.text, on: e.on}));

    async function putMemory(entries) {
      try {
        state.memory = await api.put(base() + "/memory", {entries, rev: state.memory.rev});
        state.ui.memError = ""; state.ui.memStale = false; state.ui.editing = null;
        state.context = await api.get(base() + "/context");
      } catch (e) {
        state.ui.memError = isObj(e) && e.status === 409 ? STALE : said(e, FAILED);
        state.ui.memStale = isObj(e) && e.status === 409;
      }
      ping();
      draw();
    }

    async function act(b) {
      const a = b.dataset.act;
      const id = b.dataset.id;
      const n = b.dataset.n === undefined ? null : Number(b.dataset.n);
      try {
        if (a === "pcv-close") return close();
        if (a === "pcv-add") { const input = el.querySelector ? el.querySelector(".pcv-input") : null; if (input && input.click) input.click(); return; }
        if (a === "pcv-remove") { await api.del(base() + "/files/" + encodeURIComponent(id)); return refresh(); }
        if (a === "pcv-rename") { state.ui.renaming = id; return draw(); }
        if (a === "pcv-rename-save") {
          const box = el.querySelector ? el.querySelector(".pcv-name") : null;
          try { await api.patch(base() + "/files/" + encodeURIComponent(id), {name: clean(box && box.value)}); state.ui.renaming = null; return refresh(); } catch (e) { state.error = said(e, FAILED); return draw(); }
        }
        if (a === "pcv-clear") { state.ui.confirmClear = true; return draw(); }
        if (a === "pcv-clear-no") { state.ui.confirmClear = false; return draw(); }
        if (a === "pcv-clear-yes") { await api.del(base() + "/files"); return refresh(); }
        if (a === "pcv-reload") return refresh();
        if (a === "pcv-save-instr") {
          const box = el.querySelector ? el.querySelector(".pcv-text") : null;
          const value = text(box && box.value);
          try {
            state.instructions = await api.put(base() + "/instructions", {text: value, rev: state.instructions.rev});
            state.ui.instrError = ""; state.ui.stale = false; state.ui.draft = undefined;
            state.context = await api.get(base() + "/context");
          } catch (e) { state.ui.draft = value; state.ui.stale = isObj(e) && e.status === 409; state.ui.instrError = state.ui.stale ? STALE : said(e, FAILED); }
          return draw();
        }
        if (a === "pcv-edit") { state.ui.editing = n; return draw(); }
        if (a === "pcv-edit-save") { const box = el.querySelector ? el.querySelector(".pcv-etext") : null; return putMemory(entryList(e => (e.n === n ? Object.assign(e, {text: clean(box && box.value)}) : e))); }
        if (a === "pcv-entry-delete") { await api.del(base() + "/memory/" + n); state.memory = await api.get(base() + "/memory"); state.context = await api.get(base() + "/context"); ping(); return draw(); }
        if (a === "pcv-add-line") {
          const box = el.querySelector ? el.querySelector(".pcv-new") : null;
          const line = clean(box && box.value);
          if (!line) return;
          try { await api.post(base() + "/memory", {text: line}); state.memory = await api.get(base() + "/memory"); state.ui.memError = ""; state.context = await api.get(base() + "/context"); } catch (e) { state.ui.memError = said(e, FAILED); }
          ping();
          return draw();
        }
      } catch (e) {
        state.error = said(e, FAILED);
        draw();
      }
    }

    async function toggle(t) {
      const a = t.dataset.act;
      try {
        if (a === "pcv-toggle") { await api.patch(base() + "/files/" + encodeURIComponent(t.dataset.id), {enabled: t.checked === true}); return refresh(); }
        if (a === "pcv-mem-toggle") { state.memory = await api.put(base() + "/memory/settings", {enabled: t.checked === true}); state.context = await api.get(base() + "/context"); ping(); return draw(); }
        if (a === "pcv-entry-toggle") { const n = Number(t.dataset.n); return putMemory(entryList(e => (e.n === n ? Object.assign(e, {on: t.checked === true}) : e))); }
      } catch (e) {
        state.error = said(e, FAILED);
        draw();
      }
    }

    if (el && el.addEventListener) {
      el.addEventListener("click", e => {
        const b = e.target && e.target.closest ? e.target.closest("button") : null;
        if (b && b.dataset && b.dataset.act) { if (e.preventDefault) e.preventDefault(); act(b); }
      });
      el.addEventListener("change", e => {
        const t = e.target;
        if (!t) return;
        if (t.classList && t.classList.contains("pcv-input")) { const picked = Array.from(t.files || []); t.value = ""; if (picked.length) addFiles(picked); return; }
        if (t.dataset && t.dataset.act) toggle(t);
      });
      el.addEventListener("keydown", e => { if (e.key === "Escape" && state.open) { if (e.preventDefault) e.preventDefault(); close(); } });
    }
    return {open, close, state: () => state, refresh, addFiles};
  }

  // The page's one panel: made on first use, an overlay on the body, closed by its Close button and by Esc. `api` is the page's own (SutraCtx.api).
  let shared = null;
  function openFor(target, api) {
    const doc = root.document;
    if (!doc || typeof doc.createElement !== "function" || !api) return null;
    if (shared === null) {
      const el = doc.createElement("div");
      el.className = "pcv";
      el.hidden = true;
      doc.body.appendChild(el);
      shared = mount({el, api});
    }
    return shared.open(target);
  }

  const ProjectContextView = {openFor, filesHtml, instructionsHtml, memoryHtml, previewHtml, panelHtml, summaryLine, usingLine, mount, SENT, NOT_READ, STALE};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ProjectContextView;
  else root.ProjectContextView = ProjectContextView;
})(typeof window !== "undefined" ? window : globalThis);
