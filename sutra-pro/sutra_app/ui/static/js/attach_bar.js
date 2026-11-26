/* attach_bar.js - the one chip controller every place that takes a file shares (D451, T8; extracted from chat_composer.js, behaviour unchanged).

   The direct chat's composer, the start box, the follow-up box, Attention's box and the Create project box all attach files the same way (D440): a file is checked against the server's own
   lists (ChatSearch.checkFile), read, uploaded to ONE url, and shown as a chip (uploading, ready, or failed with its reason, which stays until the owner removes it). A send is all or
   nothing: a failed or an uploading chip blocks it with a sentence. Strings in, strings out, plus ONE small controller that takes everything it touches (the api, the file reader, the
   repaint) as an argument, so node tests drive it without a page. Every word from the wire is escaped.

     create({api, url, readFile, onChange, objectUrl, maxFiles, noun})   url: where one file is POSTed ({name, content_b64} -> {id, kind, size, ...}); noun: "message" (default) or "request",
                                       only for the words of the over-the-limit chip
         files()                       the live list of chips: {key, name, size, status: "uploading" | "ready" | "failed", id, kind, error, preview}
         addFiles(files, {pasted})     check, read, upload; one chip per file; a Promise of every upload. A file that cannot go is a failed chip that says why and stays
         take(transfer, {pasted})      a paste or a drop: false when it carries no file (a text paste pastes as text), else the files are added and the Promise returned
         removeFile(key)  clear()  replace(list)
         refs()                        [{id, name}] of the ready files, in order: what a send carries
         uploading()  failed()  ready()  blocked()      blocked() is "" or the sentence that says why the send waits (a chip failed, or one is still uploading)
         html()                        the chips as markup (chips(files))
     chips(files)  filesOf(transfer)  hasFiles(transfer)  nameFor(file, pasted, n)  size(bytes)  kindOf(file)    the pure helpers the composer used to hold

   A classic script with ONE global, AttachBar; in node it is module.exports. */
(function (root) {
  "use strict";

  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const searchOf = () => {
    if (root.ChatSearch) return root.ChatSearch;
    if (typeof module === "object" && module !== null && module.exports && typeof require === "function") return require("./chat_search.js");
    return null;
  };
  const MAX_FILES = 10;
  const SIZE_UNITS = ["B", "KB", "MB"];
  const REMOVE_FAILED = "Remove the file that was not attached, or it will not be read.";
  const WAIT_UPLOAD = "Wait for the files to finish uploading.";
  const IMAGE_EXT = /\.(png|jpe?g|gif|webp)$/i;
  const TILE = Object.freeze({image: "IMG", pdf: "PDF", text: "TXT"});
  const BLOB = /^blob:[A-Za-z0-9+.:\/_-]+$/;            // a thumbnail is only ever a blob: URL this page made

  function size(n) {
    let v = Number.isFinite(n) ? Math.max(0, n) : 0;
    let i = 0;
    while (v >= 1024 && i < SIZE_UNITS.length - 1) { v /= 1024; i += 1; }
    return (i === 0 ? String(Math.round(v)) : v.toFixed(1)) + " " + SIZE_UNITS[i];
  }

  // What a file is, from the server's kind once it is uploaded, else from its name: image, pdf or text.
  const kindOf = f => (["image", "pdf", "text"].includes(clean(f.kind)) ? clean(f.kind) : (IMAGE_EXT.test(clean(f.name)) ? "image" : (/\.pdf$/i.test(clean(f.name)) ? "pdf" : "text")));

  // `opts.project` (D451): a ready file also gets "Add to project" (data-act="sf-project"), or "In the project" once it is; without it the chips are exactly what the composer always drew.
  function chips(files, opts) {
    const keep = isObj(opts) && opts.project === true;
    const list = (Array.isArray(files) ? files : []).filter(isObj);
    if (list.length === 0) return "";
    return '<ul class="ccfiles" aria-label="Attached files">' + list.map(f => {
      const status = f.status === "ready" ? "ready" : (f.status === "failed" ? "failed" : "uploading");
      const tail = status === "uploading" ? " (uploading…)" : (status === "failed" ? " (not attached: " + esc(clean(f.error) || "it failed") + ")" : " (" + esc(size(f.size)) + ")");
      const preview = typeof f.preview === "string" && BLOB.test(f.preview) ? f.preview : "";
      const look = preview !== "" ? '<img class="ccthumb" src="' + esc(preview) + '" alt=""/>' : '<span class="cctile" aria-hidden="true">' + TILE[kindOf(f)] + "</span>";
      const keepBtn = !keep || status !== "ready" ? "" : (f.inProject === true ? ' <small class="ccin">In the project</small>' :
        ' <button type="button" class="linkbtn" data-act="sf-project" data-key="' + esc(clean(f.key)) + '" aria-label="Add ' + esc(clean(f.name)) + ' to the project">Add to project</button>');
      return '<li class="ccfile ' + status + '"><span class="ccname">' + esc(clean(f.name)) + "</span><small>" + tail + "</small>" + look + keepBtn + ' <button type="button" class="linkbtn" data-act="composer-remove" data-key="' +
        esc(clean(f.key)) + '" aria-label="Remove ' + esc(clean(f.name)) + '">Remove</button></li>';
    }).join("") + "</ul>";
  }

  // filesOf(clipboardData | dataTransfer) -> [File] | null. Null is "not a file paste": the page lets the text paste or the text drop happen.
  function filesOf(transfer) {
    if (transfer === null || typeof transfer !== "object") return null;
    let list = [];
    try { list = Array.from(transfer.files || []).filter(Boolean); } catch (e) { list = []; }
    if (list.length === 0 && transfer.items) {
      try { list = Array.from(transfer.items).filter(i => i && i.kind === "file" && typeof i.getAsFile === "function").map(i => i.getAsFile()).filter(Boolean); } catch (e) { list = []; }
    }
    return list.length ? list : null;
  }

  function hasFiles(transfer) {
    if (transfer === null || typeof transfer !== "object") return false;
    try { return Array.from(transfer.types || []).includes("Files"); } catch (e) { return false; }
  }

  // A pasted screenshot is called "image.png" by every browser (or has no name at all): it gets "pasted-image-<n>.<ext>", so two pastes differ.
  const PASTE_EXT = Object.freeze({"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"});
  function nameFor(file, pasted, n) {
    const name = clean(file && file.name);
    if (!pasted || (name !== "" && !/^image\.(png|jpe?g|gif|webp)$/i.test(name))) return name;
    const type = clean(file && file.type).toLowerCase();
    const ext = hasOwn(PASTE_EXT, type) ? PASTE_EXT[type] : (IMAGE_EXT.exec(name) || [".png"])[0].toLowerCase();
    return "pasted-image-" + n + ext;
  }

  const asError = (e, fallback) => (isObj(e) && clean(e.message) !== "" ? clean(e.message) : fallback);

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

  function create(options) {
    const o = isObj(options) ? options : {};
    const api = o.api;
    const urlOf = typeof o.url === "function" ? () => clean(o.url()) : () => clean(o.url);          // a function when the target changes between files (the picked project)
    const readFile = typeof o.readFile === "function" ? o.readFile : defaultRead;
    const changed = () => { if (typeof o.onChange === "function") o.onChange(); };
    const max = Number.isInteger(o.maxFiles) && o.maxFiles > 0 ? o.maxFiles : MAX_FILES;
    const noun = clean(o.noun) || "message";
    let files = [];
    let seq = 0;
    let pastes = 0;
    const urls = isObj(o.objectUrl) ? o.objectUrl : {
      create: file => (root.URL && typeof root.URL.createObjectURL === "function" ? root.URL.createObjectURL(file) : ""),
      revoke: u => { if (root.URL && typeof root.URL.revokeObjectURL === "function") root.URL.revokeObjectURL(u); },
    };
    const previewOf = file => {
      try {
        const made = typeof urls.create === "function" ? urls.create(file) : "";
        return typeof made === "string" && BLOB.test(made) ? made : "";
      } catch (e) {
        return "";                          // no thumbnail is no loss: the chip still names the file
      }
    };
    const forget = entry => {
      if (!entry || !entry.preview) return;
      try { if (typeof urls.revoke === "function") urls.revoke(entry.preview); } catch (e) { /* already gone */ }
      entry.preview = "";
    };

    async function upload(entry, file) {
      try {
        const b64 = await readFile(file);
        const ref = await api.post(urlOf(), {name: entry.name, content_b64: b64});
        if (!files.includes(entry)) return;                           // the owner removed it while it travelled
        if (!isObj(ref) || !/^[0-9a-f]{64}$/.test(text(ref.id))) throw new Error("That file could not be attached.");
        Object.assign(entry, {status: "ready", id: ref.id, kind: clean(ref.kind), size: Number.isFinite(ref.size) ? ref.size : entry.size});
      } catch (e) {
        Object.assign(entry, {status: "failed", error: asError(e, "it could not be sent")});
      }
      changed();
    }

    function addFiles(list, opts) {
      const CS = searchOf();
      const pasted = isObj(opts) && opts.pasted === true;
      const jobs = [];
      Array.from(list || []).forEach(file => {
        const name = nameFor(file, pasted, pastes + 1);
        const why = CS ? CS.checkFile(isObj(file) ? {name, size: file.size} : file) : "";
        // a file that cannot go is a chip that says why and stays until the owner removes it (FR-1): a note alone is cleared by the next action and the file is lost unseen
        const over = files.filter(f => f.status !== "failed").length >= max;
        if (why !== "" || over) {
          seq += 1;
          files.push({key: "f" + seq, name: name || "file", size: Number.isFinite(file && file.size) ? file.size : 0, status: "failed", id: "", kind: "", preview: "",
            error: why !== "" ? why : "Up to " + max + " files can go with one " + noun + "."});
          return;
        }
        if (pasted && name !== clean(file.name)) pastes += 1;
        seq += 1;
        const entry = {key: "f" + seq, name, size: file.size, status: "uploading", id: "", kind: "", error: "", preview: IMAGE_EXT.test(name) ? previewOf(file) : ""};
        files.push(entry);
        jobs.push(upload(entry, file));
      });
      changed();
      return Promise.all(jobs);
    }

    function take(transfer, opts) {
      const list = filesOf(transfer);
      return list === null ? false : addFiles(list, opts);
    }

    function removeFile(key) {
      files.filter(f => f.key === key).forEach(forget);
      files = files.filter(f => f.key !== key);
      changed();
    }

    function clear() {
      files.forEach(forget);
      files = [];
      changed();
    }

    const uploading = () => files.some(f => f.status === "uploading");
    const failed = () => files.some(f => f.status === "failed");
    return {
      files: () => files,
      addFiles, take, removeFile, clear,
      replace: list => { files.forEach(forget); files = Array.isArray(list) ? list : []; },
      refs: () => files.filter(f => f.status === "ready").map(f => ({id: f.id, name: f.name})),
      uploading, failed, ready: () => files.filter(f => f.status === "ready").length,
      blocked: () => (failed() ? REMOVE_FAILED : (uploading() ? WAIT_UPLOAD : "")),
      html: opts => chips(files, opts),
    };
  }

  const AttachBar = {create, chips, filesOf, hasFiles, nameFor, size, kindOf, MAX_FILES, REMOVE_FAILED, WAIT_UPLOAD, IMAGE_EXT};
  if (typeof module === "object" && module !== null && module.exports) module.exports = AttachBar;
  else root.AttachBar = AttachBar;
})(typeof window !== "undefined" ? window : globalThis);
