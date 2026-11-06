/* chat_composer.js - the composer of the direct chat: attachments, send, stop and the streaming row (work package ABS-15; absorb design 2.2 and 2.3).

   The direct chat (ABS-7) answers the owner through the chat model, one turn at a time: POST /api/chats/{sid}/direct, the pieces of the reply arrive
   as `chat.partial` events (never stored), the stored reply, with its typed blocks, arrives as a `chat.message`. This file is the owner's side of
   that, for the node panel and for Home. Strings in, strings out, plus ONE small controller that owns the state and takes everything it touches
   (the api, the file reader, the repaint) as an argument, so node tests drive it without a page. Every word from the wire is escaped.

     create({api, sid, readFile, onChange, mode})   the controller:
         state()                       {mode, files, note, turn: {active, stopping, text, messageId}}
         setMode("team" | "direct")    where Send goes (the panel keeps the team's plain message route as it was)
         addFiles(files)               check (ChatSearch.checkFile), read, upload to POST /api/chats/{sid}/attachments; the chips show each one
         removeFile(key)
         send(text)                    POST /direct with the uploaded refs -> {ok, message_id} | {ok:false, error}; the files are kept on a refusal
         stop()                        POST /direct/stop; the turn ends when the stored reply (or the error line) arrives
         partial(data)                 a `chat.partial` of this chat adds to the streaming text (the ChatPill rules)
         reconcile(messages)           the turn ends when an agent message newer than the owner's line is in the list
     bar(state, opts)                  the mode toggle, the file chips, the attach button and the limits note
     streamRow(state, provider)        the streaming row ("Claude is writing" plus the text so far), or ""
     button(state, value, flags)       {label, act, disabled} of the Send button: Send, or Stop while a direct turn is answering
     askBlock(providers)               "" when a model can answer, else the sentence that says none can (the pill's rule: only runnable providers)
     providerOf(providers, chosen)     the name to show in the streaming row: the chosen one if it can run, else ""

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

  function chips(files) {
    const list = (Array.isArray(files) ? files : []).filter(isObj);
    if (list.length === 0) return "";
    return '<ul class="ccfiles" aria-label="Attached files">' + list.map(f => {
      const status = f.status === "ready" ? "ready" : (f.status === "failed" ? "failed" : "uploading");
      const tail = status === "uploading" ? " (uploading…)" : (status === "failed" ? " (not attached: " + esc(clean(f.error) || "it failed") + ")" : " (" + esc(size(f.size)) + ")");
      return '<li class="ccfile ' + status + '"><span class="ccname">' + esc(clean(f.name)) + "</span><small>" + tail + '</small> <button type="button" class="linkbtn" data-act="composer-remove" data-key="' +
        esc(clean(f.key)) + '" aria-label="Remove ' + esc(clean(f.name)) + '">Remove</button></li>';
    }).join("") + "</ul>";
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
    const base = "/api/chats/" + encodeURIComponent(sid);

    function setMode(mode) {
      state.mode = mode === "direct" ? "direct" : "team";
      state.note = "";
      changed();
    }

    function removeFile(key) {
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

    function addFiles(files) {
      const CS = searchOf();
      const list = Array.from(files || []);
      const jobs = [];
      state.note = "";
      list.forEach(file => {
        const why = CS ? CS.checkFile(file) : "";
        if (why !== "") { state.note = why; return; }
        if (state.files.length >= MAX_FILES) { state.note = "Up to " + MAX_FILES + " files can go with one message."; return; }
        seq += 1;
        const entry = {key: "f" + seq, name: clean(file.name), size: file.size, status: "uploading", id: "", kind: "", error: ""};
        state.files.push(entry);
        jobs.push(upload(entry, file));
      });
      changed();
      return Promise.all(jobs);
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
      if (state.turn.active) return refuse("This chat is already answering.");
      if (state.files.some(f => f.status === "uploading")) return refuse("Wait for the files to finish uploading.");
      const refs = state.files.filter(f => f.status === "ready").map(f => f.id);
      state.turn = {active: true, stopping: false, text: "", messageId: null};
      state.note = "";
      changed();
      try {
        const accepted = await api.post(base + "/direct", refs.length ? {text: body, attachments: refs} : {text: body});
        const id = isObj(accepted) && Number.isInteger(accepted.message_id) ? accepted.message_id : null;
        if (state.turn.active) state.turn.messageId = id;
        state.files = [];
        changed();
        return {ok: true, message_id: id};
      } catch (e) {
        state.turn = idle();
        state.note = asError(e, "That did not work. Try again.");
        changed();
        return {ok: false, error: state.note};
      }
    }

    async function stop() {
      if (!state.turn.active || state.turn.stopping) return {ok: false};
      state.turn.stopping = true;
      changed();
      try {
        const r = await api.post(base + "/direct/stop", {});
        if (isObj(r) && r.stopped === false) { state.turn = idle(); changed(); return {ok: true, stopped: false}; }      // it had already finished
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
      const next = CP.partial({active: turn.active, text: turn.text}, d);
      state.turn = {active: true, stopping: turn.stopping, text: next.text, messageId: turn.messageId !== null ? turn.messageId : (Number.isInteger(d.message_id) ? d.message_id : null)};
      changed();
      return true;
    }

    function reconcile(messages) {
      const turn = state.turn;
      if (!turn.active || turn.messageId === null) return false;
      const done = (Array.isArray(messages) ? messages : []).some(m => isObj(m) && m.role === "agent" && Number(m.id) > turn.messageId);
      if (!done) return false;
      state.turn = idle();
      changed();
      return true;
    }

    return {state: () => state, setMode, addFiles, removeFile, send, stop, partial, reconcile};
  }

  const ChatComposer = {create, bar, chips, streamRow, button, askBlock, providerOf, size, MAX_FILES};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatComposer;
  else root.ChatComposer = ChatComposer;
})(globalThis);
