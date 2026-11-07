/* chat_composer.js - the composer of the direct chat: attachments, send, stop and the streaming row (work package ABS-15; absorb design 2.2 and 2.3).

   The direct chat (ABS-7) answers the owner through the chat model, one turn at a time: POST /api/chats/{sid}/direct, the pieces of the reply arrive
   as `chat.partial` events (never stored), the stored reply, with its typed blocks, arrives as a `chat.message`. This file is the owner's side of
   that, for the node panel and for Home. Strings in, strings out, plus ONE small controller that owns the state and takes everything it touches
   (the api, the file reader, the repaint) as an argument, so node tests drive it without a page. Every word from the wire is escaped.

     create({api, sid, readFile, onChange, mode, objectUrl})   the controller (objectUrl {create, revoke}: the page's URL by default):
         state()                       {mode, files, note, turn: {active, stopping, text, messageId}}
         setMode("team" | "direct")    where Send goes (the panel keeps the team's plain message route as it was)
         addFiles(files, {pasted})     check (ChatSearch.checkFile), read, upload to POST /api/chats/{sid}/attachments; the chips show each one, an
                                       image with its thumbnail (a blob: URL, revoked when the chip goes); a pasted image gets a name of its own
         take(transfer, {pasted})      a paste or a drop on the box: false when it carries no file (a text paste pastes as text), else the files
                                       are attached (in team mode the box switches to the model, with a one-line note: the team's route takes no
                                       files) and the upload's promise is returned
         removeFile(key)
         send(text)                    POST /direct with the uploaded refs -> {ok, message_id} | {ok:false, error}; the files are kept on a refusal; a text over
                                       MAX_MESSAGE (8000) characters is refused first, in words, with nothing sent (QA direct-chat bug 7)
         retry(lineId, text, {files})  the same line asked again, once: POST /direct with the same text (and the same files when this page sent
                                       them; else text only, and the note says so)
         stop()                        POST /direct/stop; the turn ends when the stored reply (or the error line) arrives
         partial(data)                 a `chat.partial` of this chat adds to the streaming text (the ChatPill rules)
         rejoin()                      the page shows this chat again after it was closed: the text streamed meanwhile is lost, so the row
                                       starts again from what comes next (the stored reply has all of it)
         reconcile(messages)           the turn ends when the reply that answers the owner's line (`turn` = its id) is in the list
     bar(state, opts)                  the mode toggle, the file chips, the attach button and the limits note
     streamRow(state, provider)        the streaming row ("Claude is writing" plus the text so far), or ""
     button(state, value, flags)       {label, act, disabled} of the Send button: Send, or Stop while a direct turn is answering
     askBlock(providers)               "" when a model can answer, else the sentence that says none can (the pill's rule: only runnable providers)
     providerOf(providers, chosen)     the name to show in the streaming row: the chosen one if it can run, else ""
     filesOf(transfer)                 the files of a clipboardData or dataTransfer, or null when there is none (then the page lets it be)
     hasFiles(transfer)                a drag carries files (dragover: the files themselves are not readable yet)
     tooLong(text)                     "" or the sentence "Messages can be up to 8000 characters; this one has 8500."
     sendKey(event)                    true when a keydown in the message box means "send": Enter alone, never while an IME composition is open (the Enter that
                                       confirms a candidate, Safari's included: keyCode 229) and never with Shift (a new line). Home and the panel share it.
     stopPress(event)                  false for the second click of a double-click: a double-click on Send would send, and as the label turns into Stop under
                                       the pointer stop the turn it just started. A deliberate (single, or keyboard) press is true.

   Buttons carry data-act (composer-mode, composer-attach, composer-remove, composer-stop) and the panel that shows the bar listens for them.
   A classic script with ONE global, ChatComposer; in node it is module.exports. */
(function (root) {
  "use strict";

  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const need = name => {
    if (root[name]) return root[name];
    if (typeof module === "object" && module !== null && module.exports && typeof require === "function") return require("./" + (name === "ChatPill" ? "chat_pill" : "chat_search") + ".js");
    return null;
  };
  const pillOf = () => need("ChatPill");
  const searchOf = () => need("ChatSearch");
  const MAX_FILES = 10;
  const MAX_MESSAGE = 8000;            // the longest message POST /direct takes (chat_v2.MAX_CHARS), counted in characters
  const SIZE_UNITS = ["B", "KB", "MB"];

  const idle = () => ({active: false, stopping: false, text: "", messageId: null});

  function size(n) {
    let v = Number.isFinite(n) ? Math.max(0, n) : 0;
    let i = 0;
    while (v >= 1024 && i < SIZE_UNITS.length - 1) { v /= 1024; i += 1; }
    return (i === 0 ? String(Math.round(v)) : v.toFixed(1)) + " " + SIZE_UNITS[i];
  }

  /* ---------------------------------------------------------------- strings */
  const ready = providers => (Array.isArray(providers) ? providers.filter(p => isObj(p) && p.ready === true && (p.name === "claude" || p.name === "codex")) : []);

  function providerOf(providers, chosen) {
    return ready(providers).some(p => p.name === chosen) ? chosen : "";
  }

  function askBlock(providers) {
    return ready(providers).length > 0 ? "" : "No model can answer right now. Sign in to Claude or Codex in Settings, then try again.";
  }

  // What a file is, from the server's kind once it is uploaded, else from its name: image, pdf or text.
  const IMAGE_EXT = /\.(png|jpe?g|gif|webp)$/i;
  const kindOf = f => (["image", "pdf", "text"].includes(clean(f.kind)) ? clean(f.kind) : (IMAGE_EXT.test(clean(f.name)) ? "image" : (/\.pdf$/i.test(clean(f.name)) ? "pdf" : "text")));
  const TILE = Object.freeze({image: "IMG", pdf: "PDF", text: "TXT"});
  const BLOB = /^blob:[A-Za-z0-9+.:\/_-]+$/;            // a thumbnail is only ever a blob: URL this page made

  function chips(files) {
    const list = (Array.isArray(files) ? files : []).filter(isObj);
    if (list.length === 0) return "";
    return '<ul class="ccfiles" aria-label="Attached files">' + list.map(f => {
      const status = f.status === "ready" ? "ready" : (f.status === "failed" ? "failed" : "uploading");
      const tail = status === "uploading" ? " (uploading…)" : (status === "failed" ? " (not attached: " + esc(clean(f.error) || "it failed") + ")" : " (" + esc(size(f.size)) + ")");
      const preview = typeof f.preview === "string" && BLOB.test(f.preview) ? f.preview : "";
      const look = preview !== "" ? '<img class="ccthumb" src="' + esc(preview) + '" alt=""/>' : '<span class="cctile" aria-hidden="true">' + TILE[kindOf(f)] + "</span>";
      return '<li class="ccfile ' + status + '"><span class="ccname">' + esc(clean(f.name)) + "</span><small>" + tail + "</small>" + look + ' <button type="button" class="linkbtn" data-act="composer-remove" data-key="' +
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

  // "" when `body` fits in one message, else the sentence the server would refuse it with. Characters are counted as the server counts them (a code
  // point is one, as in Python), not in UTF-16 units: an emoji is one character here and two in `.length`.
  function tooLong(body) {
    const n = Array.from(text(body)).length;
    return n > MAX_MESSAGE ? "Messages can be up to " + MAX_MESSAGE + " characters; this one has " + n + "." : "";
  }

  // The Enter that confirms an IME candidate is not a send: `isComposing` is true in Chrome and Firefox; Safari ends the composition first and then
  // reports keyCode 229 on that Enter.
  function sendKey(e) {
    return isObj(e) && e.key === "Enter" && e.shiftKey !== true && e.isComposing !== true && e.keyCode !== 229;
  }

  // `detail` is the click count: the 2nd click of a double-click on the Send button (which has just become Stop) must not stop the turn the 1st started.
  function stopPress(e) {
    return !(isObj(e) && Number.isFinite(e.detail) && e.detail > 1);
  }

  function bar(state, opts) {
    const s = isObj(state) ? state : {};
    const o = isObj(opts) ? opts : {};
    const labels = isObj(o.labels) ? o.labels : {};
    const team = clean(labels.team) || "Tell the team";
    const direct = clean(labels.direct) || "Ask the model";
    const mode = s.mode === "direct" ? "direct" : "team";
    const toggle = o.toggle === false ? "" : '<div class="ccmode" role="group" aria-label="Where this message goes">' +
      '<button type="button" class="ccmode-opt' + (mode === "team" ? " on" : "") + '" data-act="composer-mode" data-mode="team" aria-pressed="' + (mode === "team") + '">' + esc(team) + "</button>" +
      '<button type="button" class="ccmode-opt' + (mode === "direct" ? " on" : "") + '" data-act="composer-mode" data-mode="direct" aria-pressed="' + (mode === "direct") + '">' + esc(direct) + "</button></div>";
    if (mode !== "direct") return toggle;
    const CS = searchOf();
    const limit = CS ? CS.limitsNote() : "";
    const attach = '<div class="ccattach"><button type="button" class="linkbtn" data-act="composer-attach">Attach files</button>' +
      '<input type="file" class="ccinput" multiple hidden tabindex="-1" aria-label="Choose files to attach"/><small>' + esc(limit) + "</small></div>";
    const note = clean(s.note) === "" ? "" : '<p class="ccnote" role="status">' + esc(clean(s.note)) + "</p>";
    return toggle + chips(s.files) + attach + note;
  }

  function streamRow(state, provider) {
    const s = isObj(state) && isObj(state.turn) ? state.turn : {};
    const CP = pillOf();
    if (!CP || s.active !== true) return "";
    return CP.indicator({active: true, text: text(s.text)}, provider);
  }

  function button(state, value, flags) {
    const s = isObj(state) ? state : {};
    const f = isObj(flags) ? flags : {};
    const turn = isObj(s.turn) ? s.turn : idle();
    if (s.mode === "direct" && turn.active === true) return {label: turn.stopping === true ? "Stopping…" : "Stop", act: "composer-stop", disabled: turn.stopping === true};
    const uploading = (Array.isArray(s.files) ? s.files : []).some(x => isObj(x) && x.status === "uploading");
    return {label: "Send", act: "send", disabled: f.disabled === true || (s.mode === "direct" && (uploading || f.blocked === true))};
  }

  /* ---------------------------------------------------------------- the controller */
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
    const sid = clean(o.sid);
    const readFile = typeof o.readFile === "function" ? o.readFile : defaultRead;
    const changed = () => { if (typeof o.onChange === "function") o.onChange(); };
    const state = {mode: o.mode === "direct" ? "direct" : "team", files: [], note: "", turn: idle()};
    let seq = 0;
    let pastes = 0;
    const sent = new Map();                 // owner line id -> the attachment refs this page sent with it (a Retry sends them again)
    const base = "/api/chats/" + encodeURIComponent(sid);
    const urls = isObj(o.objectUrl) ? o.objectUrl : {
      create: file => (root.URL && typeof root.URL.createObjectURL === "function" ? root.URL.createObjectURL(file) : ""),
      revoke: url => { if (root.URL && typeof root.URL.revokeObjectURL === "function") root.URL.revokeObjectURL(url); },
    };
    const previewOf = file => {
      try {
        const url = typeof urls.create === "function" ? urls.create(file) : "";
        return typeof url === "string" && BLOB.test(url) ? url : "";
      } catch (e) {
        return "";                          // no thumbnail is no loss: the chip still names the file
      }
    };
    const forget = entry => {
      if (!entry || !entry.preview) return;
      try { if (typeof urls.revoke === "function") urls.revoke(entry.preview); } catch (e) { /* already gone */ }
      entry.preview = "";
    };

    function setMode(mode) {
      state.mode = mode === "direct" ? "direct" : "team";
      state.note = "";
      changed();
    }

    function removeFile(key) {
      state.files.filter(f => f.key === key).forEach(forget);
      state.files = state.files.filter(f => f.key !== key);
      changed();
    }

    async function upload(entry, file) {
      try {
        const b64 = await readFile(file);
        const ref = await api.post(base + "/attachments", {name: entry.name, content_b64: b64});
        if (!state.files.includes(entry)) return;                     // the owner removed it while it travelled
        if (!isObj(ref) || !/^[0-9a-f]{64}$/.test(text(ref.id))) throw new Error("That file could not be attached.");
        Object.assign(entry, {status: "ready", id: ref.id, kind: clean(ref.kind), size: Number.isFinite(ref.size) ? ref.size : entry.size});
      } catch (e) {
        Object.assign(entry, {status: "failed", error: asError(e, "it could not be sent")});
      }
      changed();
    }

    function addFiles(files, opts) {
      const CS = searchOf();
      const pasted = isObj(opts) && opts.pasted === true;
      const list = Array.from(files || []);
      const jobs = [];
      state.note = "";
      list.forEach(file => {
        const name = nameFor(file, pasted, pastes + 1);
        const why = CS ? CS.checkFile(isObj(file) ? {name, size: file.size} : file) : "";
        if (why !== "") { state.note = why; return; }
        if (state.files.length >= MAX_FILES) { state.note = "Up to " + MAX_FILES + " files can go with one message."; return; }
        if (pasted && name !== clean(file.name)) pastes += 1;
        seq += 1;
        const entry = {key: "f" + seq, name, size: file.size, status: "uploading", id: "", kind: "", error: "", preview: IMAGE_EXT.test(name) ? previewOf(file) : ""};
        state.files.push(entry);
        jobs.push(upload(entry, file));
      });
      changed();
      return Promise.all(jobs);
    }

    function take(transfer, opts) {
      const files = filesOf(transfer);
      if (files === null) return false;
      const switched = state.mode !== "direct";
      state.mode = "direct";
      const jobs = addFiles(files, opts);
      if (switched && state.note === "") {
        state.note = "Files go only to the model, so this message now asks the model directly.";
        changed();
      }
      return jobs;
    }

    function refuse(error) {
      state.note = error;
      changed();
      return {ok: false, error};
    }

    async function send(value) {
      const body = text(value).trim();
      if (state.mode !== "direct") return {ok: false, error: "This message goes to the team."};
      if (body === "") return {ok: false, error: "Write a message first."};
      const long = tooLong(body);
      if (long !== "") return refuse(long);                              // nothing is sent and the box keeps the words
      if (state.turn.active) return refuse("This chat is already answering.");
      if (state.files.some(f => f.status === "uploading")) return refuse("Wait for the files to finish uploading.");
      const ready = state.files.filter(f => f.status === "ready");
      const accepted = await ask(body, ready.map(f => f.id), ready.map(f => f.name));
      if (accepted.ok) {
        state.files.forEach(forget);
        state.files = [];
        changed();
      }
      return accepted;
    }

    // One POST /direct: the turn is active while it travels and after it was accepted; a refusal ends it and says why.
    async function ask(body, refs, names) {
      state.turn = {active: true, stopping: false, text: "", messageId: null};
      state.note = "";
      changed();
      try {
        const payload = refs.length ? {text: body, attachments: refs, names} : {text: body};
        const accepted = await api.post(base + "/direct", payload);
        const id = isObj(accepted) && Number.isInteger(accepted.message_id) ? accepted.message_id : null;
        if (state.turn.active) state.turn.messageId = id;
        if (id !== null && refs.length) {
          sent.set(id, {refs: refs.slice(), names: names.slice()});
          while (sent.size > 50) sent.delete(sent.keys().next().value);
        }
        changed();
        return {ok: true, message_id: id};
      } catch (e) {
        state.turn = idle();
        state.note = asError(e, "That did not work. Try again.");
        changed();
        return {ok: false, error: state.note};
      }
    }

    // Retry of a direct line that failed: the same words, once (a second press while it answers is refused), on the model whatever the mode was.
    async function retry(lineId, value, opts) {
      const body = text(value).trim();
      if (body === "") return {ok: false, error: "There is nothing to send again."};
      if (state.turn.active) return refuse("This chat is already answering.");
      const o = isObj(opts) ? opts : {};
      const known = sent.get(Number(lineId));
      state.mode = "direct";
      const out = known ? await ask(body, known.refs, known.names) : await ask(body, [], []);
      if (out.ok && !known && Number.isFinite(o.files) && o.files > 0) {
        state.note = "Sent again without its files: attach them again to include them.";
        changed();
      }
      return out;
    }

    function rejoin() {
      if (!state.turn.active || state.turn.text === "") return false;
      state.turn = Object.assign({}, state.turn, {text: ""});
      changed();
      return true;
    }

    async function stop() {
      if (!state.turn.active || state.turn.stopping) return {ok: false};
      state.turn.stopping = true;
      changed();
      try {
        const r = await api.post(base + "/direct/stop", {});
        if (isObj(r) && r.stopped === false) {                     // nothing was running to stop: the reply is on its way or stored; reconcile ends the turn
          state.turn.stopping = false;
          changed();
          return {ok: true, stopped: false};
        }
        return {ok: true, stopped: true};
      } catch (e) {
        state.turn.stopping = false;
        state.note = asError(e, "The turn could not be stopped.");
        changed();
        return {ok: false, error: state.note};
      }
    }

    function partial(data) {
      const CP = pillOf();
      const d = isObj(data) && isObj(data.data) ? data.data : data;
      if (!CP || !isObj(d) || d.session_id !== sid) return false;
      const turn = state.turn;
      if (!turn.active) return false;                                  // a late piece, after the stored reply ended the turn
      if (turn.messageId !== null && Number.isInteger(d.message_id) && d.message_id !== turn.messageId) return false;      // another turn's
      const next = CP.partial({active: turn.active, text: turn.text}, d);
      state.turn = {active: true, stopping: turn.stopping, text: next.text, messageId: turn.messageId !== null ? turn.messageId : (Number.isInteger(d.message_id) ? d.message_id : null)};
      changed();
      return true;
    }

    function reconcile(messages) {
      const turn = state.turn;
      if (!turn.active || turn.messageId === null) return false;
      const done = (Array.isArray(messages) ? messages : []).some(m => isObj(m) && m.role === "agent" && m.turn === turn.messageId);
      if (!done) return false;
      state.turn = idle();
      changed();
      return true;
    }

    return {state: () => state, setMode, addFiles, take, removeFile, send, retry, stop, partial, rejoin, reconcile};
  }

  const ChatComposer = {create, bar, chips, streamRow, button, askBlock, providerOf, filesOf, hasFiles, sendKey, stopPress, tooLong, size, MAX_FILES, MAX_MESSAGE};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatComposer;
  else root.ChatComposer = ChatComposer;
})(globalThis);
