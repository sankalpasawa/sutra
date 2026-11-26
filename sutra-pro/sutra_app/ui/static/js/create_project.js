/* The Create project box (named projects, D426 and D427). One classic script, one global: CreateProject.

   The owner names every project (1 to 80 characters; Create stays disabled until a name is typed) and may add a source folder. In the desktop
   app "Add" opens the system folder dialog (window.sutraDesktop.chooseFolder); in a browser the folder is a path field. A picked folder asks
   "Allow Sutra Pro's team to read and edit files in <path>?" with Read and edit, Read only, Cancel. With no folder the box says where the work
   is saved: Documents/Sutra Pro/<name>, made by the server.

   Create posts POST /api/teams {name, folder?, access?}. Opened from an org chat card (`changeId`, `ref`), it answers that card instead:
   POST /api/chart/changes/<id>/decision {approve: true, names: {<ref>: name}, folder?, access?}. A refusal shows under the field its
   `details.field` names; success opens the new project's page.

   Project files (D451): optional. Files dropped or chosen in the box wait as chips (a refused type is a failed chip that says why, and stays until it is removed); they are uploaded to
   POST /api/teams/<id>/files once the project exists. A file that cannot be added does not undo the project: the box says which files failed and offers "Open the project".

   html(state), canCreate(state), savedIn(name, win), body(state), filesHtml(state), pickFiles(state, list) are pure (the node tests); open(opts) mounts the box on the page. */
(function (root) {
  "use strict";

  const NAME_CHARS = 80;
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const trimmed = v => (typeof v === "string" ? v.replace(/\s+/g, " ").trim() : "");
  const ACCESS_WORDS = {edit: "Read and edit", read: "Read only"};
  const FAILED = "That did not work. Try again.";
  const AB = () => root.AttachBar || (typeof require === "function" ? require("./attach_bar.js") : null);
  const CS = () => root.ChatSearch || (typeof require === "function" ? require("./chat_search.js") : null);
  const MAX_FILES = 50;

  function savedIn(name, win) {
    const sep = win ? "\\" : "/";
    return "Saved in " + ["Documents", "Sutra Pro", trimmed(name) || "<project name>"].join(sep);
  }

  function canCreate(state) {
    const s = isObj(state) ? state : {};
    const name = trimmed(s.name);
    if (!name || name.length > NAME_CHARS || s.busy === true) return false;
    return !(trimmed(s.folder) && !ACCESS_WORDS[s.access]);              // a picked folder waits for the trust answer
  }

  function body(state) {
    const s = isObj(state) ? state : {};
    const out = {name: trimmed(s.name)};
    const folder = trimmed(s.folder);
    if (folder) {
      out.folder = folder;
      out.access = ACCESS_WORDS[s.access] ? s.access : "edit";
    }
    return out;
  }

  const errorHtml = (s, field) => (trimmed(s.error) && (s.errorField || "name") === field ? '<p class="cperr" role="alert">' + esc(trimmed(s.error)) + "</p>" : "");

  function folderHtml(s) {
    const folder = trimmed(s.folder);
    if (folder && !ACCESS_WORDS[s.access]) {
      return '<div class="cptrust" role="group" aria-labelledby="cptrustq"><p id="cptrustq">Allow Sutra Pro\'s team to read and edit files in ' +
        "<code>" + esc(folder) + "</code>?</p>" +
        '<div class="cpacts"><button type="button" class="cpbtn cpgo" data-act="cp-access" data-access="edit">Read and edit</button>' +
        '<button type="button" class="cpbtn" data-act="cp-access" data-access="read">Read only</button>' +
        '<button type="button" class="cpbtn cpghost" data-act="cp-unfolder">Cancel</button></div></div>';
    }
    if (folder && s.desktop === true) {
      return '<p class="cppicked"><code>' + esc(folder) + "</code> · " + esc(ACCESS_WORDS[s.access]) +
        ' <button type="button" class="cplink" data-act="cp-unfolder">Change</button></p>';
    }
    if (s.desktop === true) {
      return '<div class="cprow"><button type="button" class="cpbtn" data-act="cp-add">Add</button>' +
        '<span class="cphint">' + esc(savedIn(s.name, s.win === true)) + "</span></div>";
    }
    return '<input id="cpfolder" class="cpinput" type="text" maxlength="1024" autocomplete="off" spellcheck="false" placeholder="' +
      esc(s.win === true ? "C:\\Users\\you\\Documents\\my-project" : "~/Documents/my-project") + '" value="' + esc(folder) + '" aria-label="Source folder path">' +
      (folder ? '<div class="cpacts" role="group" aria-label="What the team may do in this folder">' +
        ["edit", "read"].map(a => '<button type="button" class="cpbtn" data-act="cp-access" data-access="' + a + '" aria-pressed="' + String(s.access === a) + '">' +
          ACCESS_WORDS[a] + "</button>").join("") + "</div>"
        : '<p class="cphint">' + esc(savedIn(s.name, s.win === true)) + "</p>");
  }

  // The chips of the files waiting for the project, and the way to add more. A file waiting is "ready"; one the lists refuse is "failed" with the reason.
  function filesHtml(state) {
    const s = isObj(state) ? state : {};
    const files = Array.isArray(s.files) ? s.files : [];
    const ab = AB();
    const chips = ab && files.length ? ab.chips(files.map(f => ({key: f.key, name: f.name, size: f.size, status: f.status === "failed" ? "failed" : "ready", error: f.error, kind: f.kind}))) : "";
    const failed = Array.isArray(s.failedUploads) ? s.failedUploads : [];
    return '<p class="cplabel">Project files <span class="cpopt">(optional)</span></p>' +
      '<div class="cpdrop"><button type="button" class="cpbtn" data-act="cp-files">Add files</button><input type="file" class="cpfileinput" multiple hidden tabindex="-1" aria-label="Choose files for the project"/>' +
      '<span class="cphint"> or drop them here. Every run and chat of the project can read them. They stay on this computer.</span></div>' +
      '<div class="cpchips" role="status">' + chips + (s.filesNote ? '<p class="cphint">' + esc(s.filesNote) + "</p>" : "") + "</div>" +
      (failed.length ? '<p class="cperr" role="alert">The project was made. These files could not be added: ' + esc(failed.join(" ")) + "</p>" : "");
  }

  // The chosen files as chips: a refused type or an over-the-limit file is a failed chip with its reason; more than MAX_FILES is refused with the limit in words.
  function pickFiles(state, list) {
    const s = isObj(state) ? state : {};
    s.files = Array.isArray(s.files) ? s.files : [];
    s.seq = Number.isInteger(s.seq) ? s.seq : 0;
    const cs = CS();
    for (const f of Array.from(list || [])) {
      s.seq += 1;
      const name = trimmed(f && f.name) || "file";
      const why = cs ? cs.checkFile({name, size: f && f.size}) : "";
      const over = s.files.filter(x => x.status !== "failed").length >= MAX_FILES;
      s.files.push({key: "p" + s.seq, name, size: Number.isFinite(f && f.size) ? f.size : 0, status: why || over ? "failed" : "ready", error: why || (over ? "A project can hold " + MAX_FILES + " files." : ""), file: f});
    }
    return s.files;
  }

  function html(state) {
    const s = isObj(state) ? state : {};
    const go = canCreate(s) ? "" : " disabled";
    return '<div class="cpbox" role="dialog" aria-modal="true" aria-labelledby="cptitle" tabindex="-1">' +
      '<h2 id="cptitle">Create project</h2>' +
      (s.suggest === true ? '<p class="cplead">Sutra suggests this name for the new project. Change it if you like.</p>' : "") +
      '<label for="cpname">Project name</label>' +
      '<input id="cpname" class="cpinput" type="text" maxlength="' + NAME_CHARS + '" autocomplete="off" value="' + esc(s.name || "") + '">' +
      errorHtml(s, "name") +
      '<p class="cplabel">Source folder <span class="cpopt">(optional)</span></p>' + folderHtml(s) + errorHtml(s, "folder") + filesHtml(s) +
      '<div class="cpacts cpend"><button type="button" class="cpbtn cpghost" data-act="cp-close">Cancel</button>' +
      (s.created ? '<button type="button" class="cpbtn cpgo" data-act="cp-open">Open the project</button>'
        : '<button type="button" class="cpbtn cpgo" data-act="cp-create"' + go + ">" + (s.busy === true ? "Creating…" : "Create project") + "</button>") + "</div></div>";
  }

  /* ---------------------------------------------------------------- the box on the page */
  let current = null;

  function open(opts) {
    const o = isObj(opts) ? opts : {};
    const doc = root.document;
    const ctx = root.SutraCtx;
    if (!doc || !doc.body || !ctx || !ctx.api) return null;
    if (current) current.close();
    const bridge = root.sutraDesktop;
    const state = {
      name: trimmed(o.name), folder: "", access: null, busy: false, error: "", errorField: "", suggest: Boolean(o.changeId && o.name),
      desktop: isObj(bridge) && typeof bridge.chooseFolder === "function", win: /Win/i.test(String((root.navigator || {}).platform || "")),
    };
    const el = doc.createElement("div");
    el.className = "cpwrap";
    const before = doc.activeElement || null;
    let closed = false;

    function render(focusId) {
      el.innerHTML = html(state);
      const target = el.querySelector(focusId ? "#" + focusId : "#cpname");
      if (target && typeof target.focus === "function") {
        target.focus({preventScroll: true});
        if (target.id === "cpname" || target.id === "cpfolder") { const n = target.value.length; try { target.setSelectionRange(n, n); } catch (e) { /* not a text field */ } }
      }
    }
    function close() {
      if (closed) return;
      closed = true;
      current = null;
      if (el.parentNode) el.parentNode.removeChild(el);
      if (before && typeof before.focus === "function") { try { before.focus(); } catch (e) { /* gone */ } }
    }
    function refresh() {                              // typing: only the button and the hint change, so the caret stays put
      const go = el.querySelector('[data-act="cp-create"]');
      if (go) go.disabled = !canCreate(state);
      const hint = el.querySelector(".cphint");
      if (hint && !trimmed(state.folder)) hint.textContent = savedIn(state.name, state.win);
    }
    async function choose() {
      let picked = null;
      try { picked = await bridge.chooseFolder(); } catch (e) { picked = null; }
      if (typeof picked === "string" && picked.trim()) {
        state.folder = picked.trim();
        state.access = null;
        state.error = "";
        render();
        const first = el.querySelector('[data-act="cp-access"]');
        if (first && first.focus) first.focus();
      }
    }
    function finish(id) {
      close();
      if (typeof o.onDone === "function") o.onDone(id);
      else if (id) root.location.href = "/d/" + encodeURIComponent(id) + "/";
    }
    // After the project exists (D451): each waiting file to POST /api/teams/<id>/files, one by one. -> the sentences of the files that could not be added ([] when all went).
    async function uploadFiles(id) {
      const waiting = (state.files || []).filter(x => x.status === "ready" && x.file);
      if (!id || waiting.length === 0) return [];
      const failed = [];
      for (const f of waiting) {
        try {
          const b64 = await readFile(f.file);
          await ctx.api.post("/api/teams/" + encodeURIComponent(id) + "/files", {name: f.name, content_b64: b64});
        } catch (e) { failed.push(f.name + ": " + ((e && e.message) || FAILED)); f.status = "failed"; }
      }
      return failed;
    }
    function readFile(file) {
      return new Promise((resolve, reject) => {
        const Reader = root.FileReader;
        if (typeof Reader !== "function") { reject(new Error("This browser cannot read files.")); return; }
        const r = new Reader();
        r.onerror = () => reject(new Error("That file could not be read."));
        r.onload = () => resolve(String(r.result).split(",").slice(1).join(","));
        r.readAsDataURL(file);
      });
    }
    async function create() {
      if (!canCreate(state)) return;
      state.busy = true;
      state.error = "";
      render();
      const payload = body(state);
      try {
        let id;
        if (o.changeId) {
          const answer = await ctx.api.post("/api/chart/changes/" + encodeURIComponent(o.changeId) + "/decision",
            Object.assign({approve: true, names: {[o.ref]: payload.name}}, payload.folder ? {folder: payload.folder, access: payload.access} : {}));
          id = isObj(answer) && isObj(answer.ids_by_ref) ? answer.ids_by_ref[o.ref] : "";
        } else {
          const answer = await ctx.api.post("/api/teams", payload);
          id = isObj(answer) && isObj(answer.team) ? answer.team.id : "";
        }
        const failed = await uploadFiles(id);
        if (failed.length > 0) {                       // the project stands; the box says which files did not go and waits for the owner
          Object.assign(state, {busy: false, created: id, failedUploads: failed, files: state.files.filter(x => x.status === "failed")});
          render();
          return;
        }
        finish(id);
      } catch (err) {
        state.busy = false;
        state.error = (err && err.message) || FAILED;
        state.errorField = err && isObj(err.details) && err.details.field === "folder" ? "folder" : "name";
        render(state.errorField === "folder" && !state.desktop ? "cpfolder" : "cpname");
      }
    }

    el.addEventListener("input", e => {
      if (e.target && e.target.id === "cpname") { state.name = e.target.value; refresh(); }
      else if (e.target && e.target.id === "cpfolder") {
        const had = Boolean(trimmed(state.folder));
        state.folder = e.target.value;
        if (!state.access) state.access = "edit";
        if (had !== Boolean(trimmed(state.folder))) render("cpfolder"); else refresh();
      }
    });
    el.addEventListener("click", e => {
      if (e.target === el) { close(); return; }
      const b = e.target && e.target.closest ? e.target.closest("button[data-act]") : null;
      if (!b || b.disabled) return;
      const act = b.dataset.act;
      if (act === "cp-close") close();
      else if (act === "cp-add") choose();
      else if (act === "cp-unfolder") { state.folder = ""; state.access = null; render(); }
      else if (act === "cp-access") { state.access = b.dataset.access === "read" ? "read" : "edit"; render(); }
      else if (act === "cp-create") create();
      else if (act === "cp-files") { const input = el.querySelector(".cpfileinput"); if (input && input.click) input.click(); }
      else if (act === "cp-open") finish(state.created);
      else if (act === "composer-remove") { state.files = (state.files || []).filter(x => x.key !== b.dataset.key); render(); }
    });
    el.addEventListener("change", e => {
      const t = e.target;
      if (!t || !t.classList || !t.classList.contains("cpfileinput")) return;
      const picked = Array.from(t.files || []);
      t.value = "";
      if (picked.length) { pickFiles(state, picked); render(); }
    });
    el.addEventListener("dragover", e => { const ab = AB(); if (ab && ab.hasFiles(e.dataTransfer)) e.preventDefault(); });
    el.addEventListener("drop", e => {
      const ab = AB();
      if (!ab || !ab.hasFiles(e.dataTransfer)) return;
      e.preventDefault();
      pickFiles(state, ab.filesOf(e.dataTransfer));
      render();
    });
    el.addEventListener("keydown", e => {
      if (e.key === "Escape") { e.preventDefault(); close(); return; }
      if (e.key === "Enter" && e.target && e.target.id === "cpname") { e.preventDefault(); create(); return; }
      if (e.key !== "Tab") return;
      const list = Array.from(el.querySelectorAll("input,button:not([disabled])"));
      if (list.length === 0) return;
      const first = list[0], last = list[list.length - 1], active = doc.activeElement;
      if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
    });
    doc.body.appendChild(el);
    render();
    current = {close, el};
    return current;
  }

  const CreateProject = {html, canCreate, savedIn, body, open, filesHtml, pickFiles, NAME_CHARS};
  if (typeof module === "object" && module.exports) module.exports = CreateProject;
  else root.CreateProject = CreateProject;
})(globalThis);
