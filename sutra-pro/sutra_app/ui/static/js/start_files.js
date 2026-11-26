/* start_files.js - files where work starts (D451, T9): the paperclip, the chips, drop and paste on a box that tells a team what to do.

   The start box and the follow-up box of a team's page (`lform`, `sform`), Attention's box and the Create project box all take files the way the direct chat does (D440), through the one
   chip controller, attach_bar.js. A file is stored first (POST /api/teams/<project>/attachments, or the org chat's own upload when no project is picked) and travels with the words as
   `files: [{id, name}]`; a send is all or nothing: a chip that failed or is still uploading holds it with a sentence, and a refusal from the server keeps the words and the chips.
   Each ready chip can be kept with the project ("Add to project": POST /api/teams/<project>/files/promote). Every word from the wire is escaped.

     mount({el, chips, host, api, url, project, dept, noun, readFile, objectUrl, onChange})   -> {bar, refs(), blocked(), say(words), reset(), draw(), note()}
         el       the element that gets the paperclip button and the hidden file input (a delegated click opens the chooser)
         chips    the element that gets the chips and the note (defaults to `el`)
         host     the element that takes a drop and a paste (the form or the box); optional
         url      the upload url, or a function that gives it when a file is uploaded; project: a function that gives the project's id ("" for none): enables "Add to project"
     attachHtml(note)   chipsHtml(files, note, opts)   the markup, as pure strings
     fields()           {files: [...]} for the one send that is being made now (the page's sendText asks), else {}
     answered(res)      the server's answer to that send: kept chips are cleared on success, and a refusal is said in a sentence with the words put back
     page(doc)          the team page's wiring: mounts on #lform and #sform when they are there (the page script calls nothing)

   A classic script with ONE global, StartFiles; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const need = (name, file) => root[name] || (typeof module === "object" && module !== null && module.exports && typeof require === "function" ? require("./" + file + ".js") : null);
  const AB = () => need("AttachBar", "attach_bar");
  const CLIP = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 11.5l-8.6 8.6a5.5 5.5 0 0 1-7.8-7.8l8.9-8.9a3.7 3.7 0 0 1 5.2 5.2l-8.9 8.9a1.8 1.8 0 0 1-2.6-2.6l8.2-8.2"/></svg>';
  const NO_PROJECT_WORDS = "Files go to the projects Sutra picks and are read by the planner.";

  function attachHtml(limitNote) {
    const title = clean(limitNote) || "Attach files";
    return '<button type="button" class="sfattach" data-act="sf-attach" aria-label="Attach files" title="' + esc(title) + '">' + CLIP + "</button>" +
      '<input type="file" class="sfinput" multiple hidden tabindex="-1" aria-label="Choose files to attach"/>';
  }

  function chipsHtml(files, note, opts) {
    const list = Array.isArray(files) ? files : [];
    const ab = AB();
    const body = ab && list.length ? ab.chips(list, opts) : "";
    const words = clean(note);
    if (body === "" && words === "") return "";
    return '<div class="sfchips" role="status">' + body + (words === "" ? "" : '<p class="ccnote">' + esc(words) + "</p>") + "</div>";
  }

  // The words of a refusal from the server, in the owner's terms (the route answers {error: {code, message}} or {error: "..."}).
  function refusal(res, body) {
    const status = isObj(res) && Number.isInteger(res.status) ? res.status : 0;
    const said = isObj(body) && isObj(body.error) ? clean(body.error.message) : (isObj(body) ? clean(body.error) : "");
    if (status === 404) return "One of the files is no longer stored. Remove it and attach it again.";
    if (status === 409) return "The team is working. Your files are still here; send again when it is free.";
    if (status === 403) return said || "This project was deleted.";
    return said || "That did not work. Try again.";
  }

  function mount(options) {
    const o = isObj(options) ? options : {};
    const el = o.el;
    const chipsEl = o.chips || el;
    const host = o.host || null;
    const api = o.api;
    const ab = AB();
    let note = "";
    const limitsNote = () => { const CS = need("ChatSearch", "chat_search"); return CS && typeof CS.limitsNote === "function" ? CS.limitsNote() : ""; };
    const projectOf = () => (typeof o.project === "function" ? clean(o.project()) : "");
    const bar = ab.create({api, url: o.url, readFile: o.readFile, objectUrl: o.objectUrl, noun: o.noun || "request", onChange: () => draw()});
    let built = false;

    function draw() {
      if (el && !built) { el.innerHTML = attachHtml(limitsNote()); built = true; }
      if (chipsEl) chipsEl.innerHTML = chipsHtml(bar.files(), note, {project: typeof o.project === "function" && projectOf() !== ""});
      if (typeof o.onChange === "function") o.onChange();
    }

    const say = words => { note = clean(words); draw(); };
    const addFiles = (files, opts) => { note = ""; return bar.addFiles(files, opts); };

    async function promote(key) {
      const f = bar.files().find(x => x.key === key);
      const dept = projectOf();
      if (!f || f.status !== "ready" || dept === "" || !api) return;
      try {
        await api.post("/api/teams/" + encodeURIComponent(dept) + "/files/promote", {attachment_id: f.id, name: f.name});
        f.inProject = true;
        note = "";
      } catch (e) {
        note = clean(e && e.message) || "That file could not be added to the project.";
      }
      draw();
    }

    const act = e => {
      const b = e && e.target && e.target.closest ? e.target.closest("button") : null;
      if (!b || !b.dataset) return false;
      if (b.dataset.act === "sf-attach") { const input = el && el.querySelector ? el.querySelector(".sfinput") : null; if (input && typeof input.click === "function") input.click(); return true; }
      if (b.dataset.act === "composer-remove") { note = ""; bar.removeFile(b.dataset.key); return true; }
      if (b.dataset.act === "sf-project") { promote(b.dataset.key); return true; }
      return false;
    };
    if (el && el.addEventListener) {
      el.addEventListener("click", act);
      el.addEventListener("change", e => {
        const t = e && e.target;
        if (!t || !t.classList || !t.classList.contains("sfinput")) return;
        const picked = Array.from(t.files || []);
        t.value = "";
        if (picked.length) addFiles(picked);
      });
    }
    if (chipsEl && chipsEl !== el && chipsEl.addEventListener) chipsEl.addEventListener("click", act);
    if (host && host.addEventListener) {
      host.addEventListener("dragover", e => { if (ab.hasFiles(e && e.dataTransfer)) e.preventDefault(); });
      host.addEventListener("drop", e => { if (ab.hasFiles(e && e.dataTransfer)) { e.preventDefault(); addFiles(ab.filesOf(e.dataTransfer)); } });
      host.addEventListener("paste", e => { const files = ab.filesOf(e && e.clipboardData); if (files !== null) { e.preventDefault(); addFiles(files, {pasted: true}); } });
    }
    draw();
    return {bar, refs: () => bar.refs(), blocked: () => bar.blocked(), say, draw, note: () => note, addFiles, reset: () => { note = ""; bar.clear(); }};
  }

  /* ---------------------------------------------------------------- the team page (E30): the start box and the follow-up box */
  const live = {widgets: {}, taken: null};

  // The one send being made now. The submit is seen first (capture), so a held send never reaches the page's handler; the page's sendText then asks fields() in the same tick.
  function guard(form, widget, box) {
    form.addEventListener("submit", e => {
      const why = widget.blocked();
      if (why !== "") { e.preventDefault(); if (typeof e.stopImmediatePropagation === "function") e.stopImmediatePropagation(); widget.say(why); return; }
      const refs = widget.refs();
      const mine = refs.length ? {widget, refs, words: text(box && box.value).trim(), box, used: false} : null;
      live.taken = mine;
      if (mine && root.setTimeout) root.setTimeout(() => { if (live.taken === mine && mine.used !== true) live.taken = null; }, 0);          // a submit the page did not send (empty words) takes nothing along
    }, true);
  }

  function fields() {
    const t = live.taken;
    if (!t || t.used === true) return {};
    t.used = true;
    return {files: t.refs};
  }

  // The server's answer to that send (the page awaits its fetch): files that went are gone from the chips; a refusal keeps them, says why, and puts the words back.
  async function answered(res) {
    const t = live.taken;
    if (!t || t.used !== true) return;
    live.taken = null;
    if (isObj(res) && res.ok === true) { t.widget.reset(); return; }
    let body = null;
    try { body = res && typeof res.json === "function" ? await res.json() : null; } catch (e) { body = null; }
    t.widget.say(refusal(res, body));
    if (t.box && t.words !== "" && text(t.box.value).trim() === "") {
      t.box.value = t.words;
      if (typeof t.box.dispatchEvent === "function" && typeof root.Event === "function") t.box.dispatchEvent(new root.Event("input"));
    }
  }

  function page(doc) {
    const d = doc || root.document;
    if (!d || typeof d.getElementById !== "function") return false;
    const ctx = root.SutraCtx;
    const dept = () => (ctx && ctx.dept ? String(ctx.dept) : "");
    const api = ctx && ctx.api ? ctx.api : null;
    if (!api) return false;
    const url = () => "/api/teams/" + encodeURIComponent(dept()) + "/attachments";
    [["lform", "lbox", "lattach", "lfiles"], ["sform", "sbox", "sattach", "sfiles"]].forEach(([formId, boxId, attachId, chipsId]) => {
      const form = d.getElementById(formId), box = d.getElementById(boxId), el = d.getElementById(attachId), chipsEl = d.getElementById(chipsId);
      if (!form || !box || !el || !chipsEl || live.widgets[formId]) return;
      const widget = mount({el, chips: chipsEl, host: form, api, url, project: dept, noun: "request"});
      live.widgets[formId] = widget;
      guard(form, widget, box);
    });
    return true;
  }
  if (root.document && typeof root.document.addEventListener === "function") {
    if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", () => page(root.document));
    else root.setTimeout ? root.setTimeout(() => page(root.document), 0) : page(root.document);
  }

  const StartFiles = {mount, attachHtml, chipsHtml, refusal, fields, answered, page, guard, NO_PROJECT_WORDS, _live: live};
  if (typeof module === "object" && module !== null && module.exports) module.exports = StartFiles;
  else root.StartFiles = StartFiles;
})(typeof window !== "undefined" ? window : globalThis);
