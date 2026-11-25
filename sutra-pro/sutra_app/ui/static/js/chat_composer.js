/* chat_composer.js - the composer of the direct chat: attachments, send, stop and the streaming row (work package ABS-15; absorb design 2.2 and 2.3).

   The direct chat (ABS-7) answers the owner through the chat model, one turn at a time: POST /api/chats/{sid}/direct, the pieces of the reply arrive
   as `chat.partial` events (never stored), the stored reply, with its typed blocks, arrives as a `chat.message`. This file is the owner's side of
   that, for the node panel and for Home. Strings in, strings out, plus ONE small controller that owns the state and takes everything it touches
   (the api, the file reader, the repaint) as an argument, so node tests drive it without a page. Every word from the wire is escaped.

     create({api, sid, readFile, onChange, onTurnEnd, mode, objectUrl, live, onRelease, onSettle, now, timers, newId})   the controller (objectUrl {create, revoke}: the page's URL by default; onTurnEnd: called
                                       once when a turn that ran is over, by its stored reply or because the server lost it, so the page can read the provider
                                       pill again: a turn may have moved the chat to the other model):
         state()                       {mode, files, note, turn: {active, stopping, text, messageId}}
                                       `live: true` (the pages; STR-9) puts the turn in a ChatLiveClient: the send carries a `client_id`, the turn is told by `chat.live`
                                       frames (frame(raw)) and snapshots, the stored reply of a live turn is held back until its end (offer(rows)), Stop and Retry go to the
                                       routes of the live turn, and state().turn is a projection of the store with the same four keys. Without it (every older caller) nothing
                                       below changes: the turn is the plain {active, stopping, text, messageId} told by `chat.partial`.
         frame(raw)                    live: one `chat.live` frame of this chat           reconnect()   live: the stream (re)connected: read the snapshot
         setPolling(on)                live: the stream is down, the snapshot is polled   offer(rows)    live: the rows to show now (a held reply is kept back)
         liveView()                    live: {turn, label, activity, note, canStop, ...} for the row   pendingLine(messages)  live: the owner's line before the stored one has it
         close()                       live: stop the timers
         setMode("team" | "direct")    where Send goes (the panel keeps the team's plain message route as it was)
         addFiles(files, {pasted})     check (ChatSearch.checkFile), read, upload to POST /api/chats/{sid}/attachments; the chips show each one, an
                                       image with its thumbnail (a blob: URL, revoked when the chip goes); a pasted image gets a name of its own
         take(transfer, {pasted})      a paste or a drop on the box: false when it carries no file (a text paste pastes as text), else the files
                                       are attached (in team mode the box switches to the model, with a one-line note: the team's route takes no
                                       files) and the upload's promise is returned
         removeFile(key)
         send(text)                    POST /direct with the uploaded refs -> {ok, message_id} | {ok:false, error}; the files are kept on a refusal; a text over
                                       MAX_MESSAGE (8000) characters is refused first, in words, with nothing sent (QA direct-chat bug 7)
         retry(lineId, text, {files, mode})  the same line asked again, once: POST /direct with the same text (and the same files when this page sent
                                       them; else text only, and the note says so). `mode` ("ask" | "do") is the line's own mode as the server stored it (DV-1)
         stop()                        POST /direct/stop; the turn ends when the stored reply (or the error line) arrives
         partial(data)                 a `chat.partial` of this chat adds to the streaming text (the ChatPill rules)
         resync()                      ask GET /api/chats/{sid} whether a direct turn answers: a turn this page does not know is shown with its Stop (a reload, a
                                       second tab); a turn this page showed that the server no longer runs (it died with the last process) is over. Async,
                                       never rejects. The pages call it after they load and when the event stream says to read everything again; the app answering also
                                       clears the note a send put up because the app was down ("The app is not responding.").
         rejoin()                      the page shows this chat again after it was closed: the text streamed meanwhile is lost, so the row
                                       starts again from what comes next (the stored reply has all of it)
         reconcile(messages)           the turn ends when the reply that answers the owner's line (`turn` = its id) is in the list
     bar(state, opts)                  the mode toggle, the file chips, the attach button and the limits note
     streamParts(state, provider)      {who, text} of that row, or null; paintStreamRow(el, state, provider) draws it into el by appending (Fluid.paintStream)
     streamRow(state, provider)        the streaming row ("Claude is writing" plus the text so far), or ""
     button(state, value, flags)       {label, act, disabled} of the Send button: Send, or Stop while a direct turn is answering
     askBlock(providers)               "" when a model can answer, else the sentence that says none can (the pill's rule: only runnable providers; an empty list
                                       is the offline demo, which says so instead of asking for a sign-in)
     providerOf(providers, chosen)     the name to show in the streaming row: the chosen one if it can run, else ""
     filesOf(transfer)                 the files of a clipboardData or dataTransfer, or null when there is none (then the page lets it be)
     hasFiles(transfer)                a drag carries files (dragover: the files themselves are not readable yet)
     tooLong(text)                     "" or the sentence "Messages can be up to 8000 characters; this one has 8500."
     sendKey(event)                    true when a keydown in the message box means "send": Enter alone, never while an IME composition is open (the Enter that
                                       confirms a candidate, Safari's included: keyCode 229) and never with Shift (a new line). Home and the panel share it.
     stopPress(event)                  false for the second click of a double-click: a double-click on Send would send, and as the label turns into Stop under
                                       the pointer stop the turn it just started. A deliberate (single, or keyboard) press is true.

   Ask (DV-1, flag SUTRA_ASK_V1; the page turns it on only when the server's pill says `ask`): an Ask | Do switch in front of the box. Do is everything above, as it was.
   Ask sends the same POST /direct with `mode: "ask"`: a read-only answer about the owner's folder whose sources Sutra checks. It always goes to the model, so while it is on the
   team / model toggle is not shown and state.mode reads "direct" (without being remembered: a reload comes back in Do).
         enableAsk(on)                 the page says whether Ask exists (the pill's `ask`); off puts a chat that was asking back in Do. Until it is on, nothing below exists
         setAsk("ask" | "do")          the switch; false when Ask is not on
         state.ask                     "ask" | "do" (not enumerable: the state of a page without Ask has exactly the keys it always had)
         say(words)                    put a sentence in the note under the box
         draft(text)                   "Turn this into work": leaves Ask, points Send at the team, and returns the text (at most MAX_MESSAGE characters) for the page to put in the
                                       box. It never sends anything: the owner edits it and presses Send
     fillBox(box, text)                put a draft in a message box: the words, the caret at the end, the box focused, an `input` event so the page saves and resizes it
   With `bar(state, {ask: true})` the switch is drawn; without it the bar is exactly what it was.

   Buttons carry data-act (composer-mode, composer-ask, composer-attach, composer-remove, composer-stop) and the panel that shows the bar listens for them.
   A classic script with ONE global, ChatComposer; in node it is module.exports. */
(function (root) {
  "use strict";

  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const FILES = {ChatDraft: "chat_draft", ChatPill: "chat_pill", ChatSearch: "chat_search", ChatLiveClient: "chat_live_client", ChatLiveStore: "chat_live_store"};
  const need = name => {
    if (root[name]) return root[name];
    if (typeof module === "object" && module !== null && module.exports && typeof require === "function" && hasOwn(FILES, name)) return require("./" + FILES[name] + ".js");
    return null;
  };
  const pillOf = () => need("ChatPill");
  const searchOf = () => need("ChatSearch");
  const MAX_FILES = 10;
  const MAX_MESSAGE = 8000;            // the longest message POST /direct takes (chat_v2.MAX_CHARS), counted in characters
  const SIZE_UNITS = ["B", "KB", "MB"];

  const idle = () => ({active: false, stopping: false, text: "", messageId: null});

  // Ask (DV-1): the words of the switch. Simple words: what it reads, what it never does, that Sutra checks the sources.
  const ASK_TITLE = "Ask: an answer about your folder. It only reads, it changes nothing, and Sutra checks every source it names.";
  const DO_TITLE = "Do: tell the team what to do, or ask the model, as before.";
  const ASK_NOTE = "Ask only reads your folder and changes nothing. Sutra checks every source the answer names.";

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
    if (ready(providers).length > 0) return "";
    // no provider listed at all is the offline demo (the stub answers the team's agent, but is not a model to choose): there is nothing to sign in to
    if (Array.isArray(providers) && providers.length === 0) return "This is the offline demo: there is no Claude or Codex to ask directly. Plan with Sutra (or tell the team) works here.";
    return "No model can answer right now. Sign in to Claude or Codex in Settings, then try again.";
  }

  // What a file is, from the server's kind once it is uploaded, else from its name: image, pdf or text.
  const IMAGE_EXT = /\.(png|jpe?g|gif|webp)$/i;
  const kindOf = f => (["image", "pdf", "text"].includes(clean(f.kind)) ? clean(f.kind) : (IMAGE_EXT.test(clean(f.name)) ? "image" : (/\.pdf$/i.test(clean(f.name)) ? "pdf" : "text")));
  const REMOVE_FAILED = "Remove the file that was not attached, or it will not be read.";
  const WAIT_UPLOAD = "Wait for the files to finish uploading.";
  const TEAM_FILES = "Files go only to the model. Remove them, or ask the model.";
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
    const askOn = o.ask === true;                                             // Ask exists (DV-1): the switch is drawn, and while it is on the box always asks the model
    const asking = askOn && s.ask === "ask";
    const askSwitch = !askOn ? "" : '<div class="ccmode ccask" role="group" aria-label="What this message does">' +
      '<button type="button" class="ccmode-opt' + (asking ? " on" : "") + '" data-act="composer-ask" data-ask="ask" aria-pressed="' + asking + '" title="' + esc(ASK_TITLE) + '">' + esc(clean(labels.ask) || "Ask") + "</button>" +
      '<button type="button" class="ccmode-opt' + (asking ? "" : " on") + '" data-act="composer-ask" data-ask="do" aria-pressed="' + !asking + '" title="' + esc(DO_TITLE) + '">' + esc(clean(labels.do) || "Do") + "</button></div>";
    const toggle = asking || o.toggle === false ? "" : '<div class="ccmode" role="group" aria-label="Where this message goes">' +
      '<button type="button" class="ccmode-opt' + (mode === "team" ? " on" : "") + '" data-act="composer-mode" data-mode="team" aria-pressed="' + (mode === "team") + '">' + esc(team) + "</button>" +
      '<button type="button" class="ccmode-opt' + (mode === "direct" ? " on" : "") + '" data-act="composer-mode" data-mode="direct" aria-pressed="' + (mode === "direct") + '">' + esc(direct) + "</button></div>";
    // the team's route has no note of its own; with Ask available the page can say something there (a draft that could not be written), and only then
    // a file is never hidden: the chips are drawn in "Tell the team" too (a file only ever goes to the model, FR-3), and so is the note that says why a send was refused
    const held = chips(s.files);
    if (mode !== "direct") return askSwitch + toggle + held + ((askOn || held !== "") && clean(s.note) !== "" ? '<p class="ccnote" role="status">' + esc(clean(s.note)) + "</p>" : "");
    const CS = searchOf();
    const limit = CS ? CS.limitsNote() : "";
    const attach = '<div class="ccattach"><button type="button" class="linkbtn" data-act="composer-attach" title="' + esc(limit) + '">Attach files</button>' +
      '<input type="file" class="ccinput" multiple hidden tabindex="-1" aria-label="Choose files to attach"/><small>' + esc(limit) + "</small></div>";
    const note = clean(s.note) === "" ? "" : '<p class="ccnote" role="status">' + esc(clean(s.note)) + "</p>";
    const about = asking ? '<p class="ccnote ccasknote">' + esc(ASK_NOTE) + "</p>" : "";
    return askSwitch + about + toggle + chips(s.files) + attach + note;
  }

  function streamRow(state, provider) {
    const s = isObj(state) && isObj(state.turn) ? state.turn : {};
    const CP = pillOf();
    if (!CP || s.active !== true) return "";
    return CP.indicator({active: true, text: text(s.text)}, provider);
  }

  // The streaming row as parts, and drawn INTO an element: with fluid.js and the markdown script a streamed chunk touches the end of the row (the blocks
  // that are done stay, the tail is written again) instead of the whole row; without them the row is the html string, as before. True when a row shows.
  function streamParts(state, provider) {
    const s = isObj(state) && isObj(state.turn) ? state.turn : {};
    const CP = pillOf();
    if (!CP || s.active !== true || typeof CP.streamParts !== "function") return null;
    return CP.streamParts({active: true, text: text(s.text)}, provider);
  }

  function paintStreamRow(el, state, provider) {
    if (!el) return false;
    const F = root.Fluid;
    const MD = root.ChatMarkdown;
    if (F && MD && typeof F.paintStream === "function") {
      const parts = streamParts(state, provider);
      F.paintStream(el, parts, {render: MD.render});
      return parts !== null;
    }
    const html = streamRow(state, provider);
    if (el.__html !== html) { el.innerHTML = html; el.__html = html; }
    return html !== "";
  }

  function button(state, value, flags) {
    const s = isObj(state) ? state : {};
    const f = isObj(flags) ? flags : {};
    const turn = isObj(s.turn) ? s.turn : idle();
    if (s.mode === "direct" && turn.active === true) return {label: turn.stopping === true ? "Stopping…" : "Stop", act: "composer-stop", disabled: turn.stopping === true};
    const files = Array.isArray(s.files) ? s.files : [];
    const uploading = files.some(x => isObj(x) && x.status === "uploading");
    const failed = files.some(x => isObj(x) && x.status === "failed");
    const why = s.mode !== "direct" ? "" : (failed ? REMOVE_FAILED : (uploading ? WAIT_UPLOAD : ""));          // FR-2: the reason is the button's title
    const out = {label: s.ask === "ask" ? "Ask" : "Send", act: "send", disabled: f.disabled === true || (s.mode === "direct" && (uploading || failed || f.blocked === true))};
    if (why !== "") out.title = why;
    return out;
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

  let limitsAsked = false;

  function create(options) {
    const o = isObj(options) ? options : {};
    const api = o.api;
    const sid = clean(o.sid);
    const readFile = typeof o.readFile === "function" ? o.readFile : defaultRead;
    const changed = () => { if (typeof o.onChange === "function") o.onChange(); };
    const ended = () => { if (typeof o.onTurnEnd === "function") o.onTurnEnd(); };
    let downNote = "";                       // the note a transport failure ("The app is not responding.") put up: it goes when the page reads the session again
    const failNote = (e, fallback) => { const words = asError(e, fallback); downNote = isObj(e) && e.code === "network" ? words : ""; return words; };
    // Where the box sends is the owner's choice for this chat and survives a reload (ChatDraft keeps it beside the draft); storage that is missing or blocked just means the default.
    const modes = isObj(o.modes) ? o.modes : (() => { try { const D = need("ChatDraft"); return D ? D.create() : null; } catch (e) { return null; } })();
    const rememberedMode = (() => { try { return modes && typeof modes.loadMode === "function" ? modes.loadMode(sid) : ""; } catch (e) { return ""; } })();
    let modeNow = rememberedMode !== "" ? rememberedMode : (o.mode === "direct" ? "direct" : "team");
    const state = {files: [], note: ""};
    // The page checks a file with the server's own lists (D440, A4): read once per page load, the built-in lists stay the offline default and a failed read changes nothing.
    if (!limitsAsked && api && typeof api.get === "function") {
      const CSL = searchOf();
      if (CSL && typeof CSL.setLimits === "function") {
        limitsAsked = true;
        try { Promise.resolve(api.get("/api/chats/attachment-limits")).then(r => CSL.setLimits(r)).catch(() => { limitsAsked = false; }); } catch (e) { limitsAsked = false; }
      }
    }
    // Ask (DV-1): `askAllowed` is the page's word that the server has it; `askNow` the switch; `modeBefore` where Do goes back to (the team / model toggle, which Ask never remembers)
    let askAllowed = false;
    let askNow = "do";
    let modeBefore = null;
    const asking = () => askAllowed && askNow === "ask";
    Object.defineProperty(state, "ask", {enumerable: false, configurable: true, get: () => (asking() ? "ask" : "do")});
    Object.defineProperty(state, "mode", {enumerable: true, configurable: true, get: () => modeNow, set: v => {
      const next = v === "direct" ? "direct" : "team";
      if (next === modeNow) return;
      modeNow = next;
      try { if (modes && typeof modes.saveMode === "function") modes.saveMode(sid, next); } catch (e) { /* no storage: the choice lasts until the reload */ }
    }});
    // The live turn (STR-9): a ChatLiveClient told by `chat.live` frames. `state.turn` is then its projection (the same four keys); without it the turn is the plain object it was.
    const LiveClient = o.live === true ? need("ChatLiveClient") : null;
    const LS = LiveClient ? need("ChatLiveStore") : null;
    const newId = typeof o.newId === "function" ? o.newId : () => "s" + Array.from({length: 24}, () => Math.floor(Math.random() * 16).toString(16)).join("");
    const live = LiveClient && LS ? LiveClient.create({sid, api, now: o.now, timers: o.timers, onChange: () => changed(),
      onRelease: rows => { if (typeof o.onRelease === "function") o.onRelease(rows); },
      onTerminal: () => { if (typeof o.onSettle === "function") o.onSettle(); }}) : null;
    let plain = idle();
    let pending = null;                      // live: the owner's line as the page showed it before the server stored it: {clientId, text}
    const project = () => {
      const t = live.state().turn;
      if (t === null) return idle();
      return {active: !LS.terminal(t.phase), stopping: t.phase === "stopping", text: t.blocks.filter(b => b.type === "text").map(b => b.text).join(""), messageId: t.messageId};
    };
    Object.defineProperty(state, "turn", {enumerable: true, configurable: true, get: () => (live ? project() : plain), set: v => { plain = v; }});
    let seq = 0;
    let pastes = 0;
    const sent = new Map();                 // owner line id -> the attachment refs this page sent with it (a Retry sends them again)
    const modes_ = new Map();               // owner line id -> "ask" | "do": how this page sent it, so that a Retry is the same kind of turn (an Ask stays read only)
    const remember = (id, asked) => { if (id !== null) { modes_.set(id, asked ? "ask" : "do"); while (modes_.size > 50) modes_.delete(modes_.keys().next().value); } };
    // How a Retry asks (D350): the server stores the mode with the owner's line and the page passes it (`opts.mode`, from the line's own `mode`); a server that does not say, and a line this page
    // sent itself, are told by what the page remembers; only then does the switch decide. The server never lets a Retry widen an Ask, whatever the page sends.
    const askedBefore = (lineId, told) => (told === "ask" ? true : told === "do" ? false : (modes_.has(lineId) ? modes_.get(lineId) === "ask" : asking()));
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
      if (asking()) leaveAsk();                                         // the toggle is not drawn while asking; a program that sets the mode means it
      state.mode = mode === "direct" ? "direct" : "team";
      state.note = "";
      changed();
    }

    // Back to Do: the toggle comes back as it was before Ask. Nothing was remembered while asking, so nothing is undone in storage.
    function leaveAsk() {
      askNow = "do";
      if (modeBefore !== null) modeNow = modeBefore;
      modeBefore = null;
    }

    function enableAsk(on) {
      const next = on === true;
      if (next === askAllowed) return;
      if (!next && asking()) { leaveAsk(); state.note = ""; }
      askAllowed = next;
      changed();
    }

    function setAsk(value) {
      if (!askAllowed) return false;
      const next = value === "ask" ? "ask" : "do";
      if (next === askNow) return true;
      if (next === "ask") {
        modeBefore = modeNow;
        askNow = "ask";
        modeNow = "direct";                                             // Ask always goes to the model; set directly so the toggle's own memory is not touched
      } else {
        leaveAsk();
      }
      state.note = "";
      changed();
      return true;
    }

    // A sentence under the box (the same place as every other note of the composer): what the page wants the owner to know and that no other part of the composer says.
    function say(words) {
      state.note = clean(words);
      changed();
    }

    // "Turn this into work": the owner leaves Ask and Send points at the team again (Plan with Sutra / Tell the team). The text is only RETURNED: the page puts it in the
    // box. Nothing is posted here, ever.
    function draft(value) {
      if (asking()) leaveAsk();
      state.mode = "team";
      state.note = "";
      changed();
      return Array.from(text(value)).slice(0, MAX_MESSAGE).join("");
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
        // a file that cannot go is a chip that says why and stays until the owner removes it (FR-1): a note alone is cleared by the next action and the file is lost unseen
        const over = state.files.filter(f => f.status !== "failed").length >= MAX_FILES;
        if (why !== "" || over) {
          seq += 1;
          state.files.push({key: "f" + seq, name: name || "file", size: Number.isFinite(file && file.size) ? file.size : 0, status: "failed", id: "", kind: "", preview: "",
            error: why !== "" ? why : "Up to " + MAX_FILES + " files can go with one message."});
          return;
        }
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
      if (state.mode !== "direct") return state.files.length > 0 ? refuse(TEAM_FILES) : {ok: false, error: "This message goes to the team."};
      if (body === "") return {ok: false, error: "Write a message first."};
      const long = tooLong(body);
      if (long !== "") return refuse(long);                              // nothing is sent and the box keeps the words
      if (state.turn.active) return refuse("This chat is already answering.");
      if (state.files.some(f => f.status === "failed")) return refuse(REMOVE_FAILED);          // never send the rest and erase the one that failed (FR-2)
      if (state.files.some(f => f.status === "uploading")) return refuse(WAIT_UPLOAD);
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
    async function ask(body, refs, names, how) {
      const asked = how === undefined ? asking() : how === true;           // a retry of a line that was an Ask asks again, whatever the switch says now
      if (live) return askLive(body, refs, names, null, asked);
      state.turn = {active: true, stopping: false, text: "", messageId: null};
      state.note = "";
      changed();
      try {
        const payload = refs.length ? {text: body, attachments: refs, names} : {text: body};
        if (asked) payload.mode = "ask";                                   // DV-1: only an Ask names a mode; a Do sends exactly what it always sent
        const accepted = await api.post(base + "/direct", payload);
        const id = isObj(accepted) && Number.isInteger(accepted.message_id) ? accepted.message_id : null;
        remember(id, asked);
        if (state.turn.active) state.turn.messageId = id;
        if (id !== null && refs.length) {
          sent.set(id, {refs: refs.slice(), names: names.slice()});
          while (sent.size > 50) sent.delete(sent.keys().next().value);
        }
        changed();
        return {ok: true, message_id: id};
      } catch (e) {
        state.turn = idle();
        state.note = failNote(e, "That did not work. Try again.");
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
      const how = askedBefore(Number(lineId), isObj(opts) ? opts.mode : undefined);
      const out = live && Number.isInteger(Number(lineId)) && Number(lineId) > 0 ? await retryLive(Number(lineId), body, known, how) : (known ? await ask(body, known.refs, known.names, how) : await ask(body, [], [], how));
      if (out.ok && !known && Number.isFinite(o.files) && o.files > 0) {
        state.note = "Sent again without its files: attach them again to include them.";
        changed();
      }
      return out;
    }

    // Ask the server whether a direct turn answers in this chat, and make the page say what is true (QA direct-chat bugs 3 and 4). `direct_turn` of
    // GET /api/chats/{sid} is the owner's line the running turn answers, else null.
    //   - a turn answers that this page does not know (a reload, a second tab, the panel opened on it): it is shown, with its Stop, in direct mode; the pieces
    //     that come from now on fill the row. Not when its reply is already stored (the server clears its note a moment after it stores the reply).
    //   - nothing answers and this page showed a turn the server had accepted (the process that ran it is gone): the turn is over here too; its stored
    //     reply, or the line that says it was interrupted, is in the transcript. The turn is judged by the id that was the page's BEFORE the read: a turn
    //     whose POST was not answered yet, or one that began while the read travelled, is never ended by an older answer.
    // Resolves to whether the page changed. Never rejects: a failed read changes nothing.
    async function resync() {
      if (!api || typeof api.get !== "function") return false;
      if (live) return resyncLive();
      const known = state.turn.active ? state.turn.messageId : null;
      let running = null;
      try {
        const session = await api.get(base);
        running = isObj(session) && Number.isInteger(session.direct_turn) && session.direct_turn > 0 ? session.direct_turn : null;
      } catch (e) {
        return false;
      }
      if (downNote !== "" && state.note === downNote) {              // the app answered: what the failed send said about it is stale
        state.note = "";
        downNote = "";
        changed();
      }
      const turn = state.turn;
      if (running === null) {
        if (!turn.active || known === null || turn.messageId !== known) return false;
        state.turn = idle();
        changed();
        ended();
        return true;
      }
      if (turn.active && (turn.messageId === null || turn.messageId === running)) return false;
      try {
        const page = await api.get(base + "/messages", {after: running - 1, limit: 50});
        const list = isObj(page) && Array.isArray(page.messages) ? page.messages : [];
        if (list.some(m => isObj(m) && m.role === "agent" && m.turn === running)) return false;
      } catch (e) { /* the list is not readable now: show the turn, the next reconcile ends it if it is over */ }
      if (state.turn.active && (state.turn.messageId === null || state.turn.messageId === running)) return false;       // this page began it while we asked
      state.mode = "direct";
      state.turn = {active: true, stopping: false, text: "", messageId: running};
      changed();
      return true;
    }

    function rejoin() {
      if (live) { if (!state.turn.active) return false; live.reconnect(); return true; }
      if (!state.turn.active || state.turn.text === "") return false;
      state.turn = Object.assign({}, state.turn, {text: ""});
      changed();
      return true;
    }

    async function stop() {
      if (live) return stopLive();
      if (!state.turn.active || state.turn.stopping) return {ok: false};
      state.turn.stopping = true;
      changed();
      try {
        const r = await api.post(base + "/direct/stop", {});
        if (isObj(r) && r.stopped === false) {                     // nothing was running to stop: the reply is on its way or stored (reconcile ends the turn), or the
          state.turn.stopping = false;                             // server no longer runs this turn at all (resync ends it, so Stop is not a button that does nothing)
          changed();
          await resync();
          return {ok: true, stopped: false};
        }
        return {ok: true, stopped: true};
      } catch (e) {
        state.turn.stopping = false;
        state.note = failNote(e, "The turn could not be stopped.");
        changed();
        return {ok: false, error: state.note};
      }
    }

    function partial(data) {
      if (live) return live.partial(data);
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
      if (live) return reconcileLive(messages);
      const turn = state.turn;
      if (!turn.active || turn.messageId === null) return false;
      const done = (Array.isArray(messages) ? messages : []).some(m => isObj(m) && m.role === "agent" && m.turn === turn.messageId);
      if (!done) return false;
      state.turn = idle();
      changed();
      ended();
      return true;
    }


    /* ---------------------------------------------------------------- the live turn (STR-9) */
    const endNow = () => { live.dispatch({type: "clear"}); ended(); };

    // One POST /direct as a live turn: the page's own `client_id` goes with it, so the server's `turn.accepted`, the 202 and the stored line all name the same send
    // (one bubble, a repeated POST is `duplicate`, never a second turn). Stop pressed before the 202 is sent right after it.
    async function askLive(body, refs, names, retryOf, asked) {
      const clientId = newId();
      live.dispatch({type: "send", clientId});
      pending = retryOf === null ? {clientId, text: body} : null;
      state.note = "";
      changed();
      try {
        const payload = refs.length ? {text: body, attachments: refs, names, client_id: clientId} : {text: body, client_id: clientId};
        if (asked === true) payload.mode = "ask";                          // DV-1: only an Ask names a mode
        const accepted = await api.post(base + "/direct", payload);
        if (isObj(accepted) && Number.isInteger(accepted.message_id)) remember(accepted.message_id, asked === true);
        return await acceptedLive(clientId, accepted, refs, names);
      } catch (e) {
        return failedLive(clientId, e);
      }
    }

    async function acceptedLive(clientId, accepted, refs, names) {
      const id = isObj(accepted) && Number.isInteger(accepted.message_id) ? accepted.message_id : null;
      const generation = isObj(accepted) && typeof accepted.generation_id === "string" ? accepted.generation_id : "";
      live.dispatch({type: "accepted", clientId, generationId: generation, messageId: id,
        attemptNo: isObj(accepted) && Number.isInteger(accepted.attempt_no) ? accepted.attempt_no : 1});
      if (id !== null && refs && refs.length) {
        sent.set(id, {refs: refs.slice(), names: names.slice()});
        while (sent.size > 50) sent.delete(sent.keys().next().value);
      }
      // a duplicate answer is the first request's turn, maybe over already: read where it is now. A fresh turn needs no read: its frames start at seq 1 and the intake would hold every
      // one of them back while the read travelled. (The flag-off route has no generation: that turn is told by chat.partial and the stored reply.)
      if (isObj(accepted) && accepted.duplicate === true) live.snapshot();
      const t = live.state().turn;
      if (t && t.stopQueued && t.messageId !== null) await stopRequest();
      changed();
      return {ok: true, message_id: id};
    }

    function failedLive(clientId, e) {
      const words = failNote(e, "That did not work. Try again.");
      live.dispatch({type: "send.failed", clientId, message: words, code: isObj(e) && e.code ? String(e.code) : "send"});
      live.dispatch({type: "clear"});                                    // a send that was never accepted leaves no turn behind
      pending = null;
      state.note = words;
      changed();
      return {ok: false, error: words};
    }

    // The owner's Retry on a line whose turn failed or was stopped: the live route reuses the owner's line and runs a new try (no second bubble, no repeated side
    // effect of the owner's words); a server without the live chat has no such route and the words are sent again as they always were.
    async function retryLive(lineId, body, known, asked) {
      const clientId = newId();
      live.dispatch({type: "send", clientId, messageId: lineId});
      pending = null;
      state.note = "";
      changed();
      try {
        const payload = {message_id: lineId, client_id: clientId};
        if (asked === true) payload.mode = "ask";                           // DV-1: an Ask is retried as an Ask (read only, with its sources)
        const accepted = await api.post(base + "/direct/retry", payload);
        return await acceptedLive(clientId, accepted, [], []);
      } catch (e) {
        live.dispatch({type: "clear"});
        if (isObj(e) && e.status === 404) return known ? askLive(body, known.refs, known.names, null, asked) : askLive(body, [], [], null, asked);
        if (isObj(e) && e.code === "not_retryable") {
          state.note = "That message was answered already.";
          changed();
          return {ok: false, error: state.note};
        }
        return failedLive(clientId, e);
      }
    }

    async function stopRequest() {
      try {
        const r = await api.post(base + "/direct/stop", {});
        if (isObj(r) && r.stopped === false) {                           // nothing runs: the snapshot says whether the turn ended (a stopped reply is stored) or never was
          await live.snapshot();
          return {ok: true, stopped: false};
        }
        return {ok: true, stopped: true};
      } catch (e) {
        live.dispatch({type: "stop.failed"});
        state.note = failNote(e, "The turn could not be stopped.");
        changed();
        return {ok: false, error: state.note};
      }
    }

    async function stopLive() {
      const t = live.state().turn;
      if (t === null || LS.terminal(t.phase) || t.phase === "stopping") return {ok: false};
      live.dispatch({type: "stop.pressed"});                             // "Stopping" shows at once, whatever the network does
      const now = live.state().turn;
      if (now && now.stopQueued && now.messageId === null) return {ok: true, queued: true};          // the POST is in flight: its 202 sends the stop (never before: it could reach a chat with no turn)
      return stopRequest();
    }

    // The turn ends when the reply of its try is on the page and the live generation has ended; a held reply never ends it (the row settles in place instead).
    function reconcileLive(messages) {
      const t = live.state().turn;
      if (t === null || t.messageId === null) return false;
      if (live.holds(t.messageId, t.attemptNo)) return false;
      const done = (Array.isArray(messages) ? messages : []).some(m => isObj(m) && m.role === "agent" && m.turn === t.messageId &&
        (m.attempt === undefined || m.attempt === null ? t.attemptNo === 1 : m.attempt === t.attemptNo));
      if (!done) return false;
      endNow();
      return true;
    }

    async function resyncLive() {
      const t0 = live.state().turn;
      const known = t0 && !LS.terminal(t0.phase) ? t0.messageId : null;
      let running = null;
      let liveInfo = false;
      try {
        const session = await api.get(base);
        running = isObj(session) && Number.isInteger(session.direct_turn) && session.direct_turn > 0 ? session.direct_turn : null;
        liveInfo = isObj(session) && isObj(session.live);
      } catch (e) {
        return false;
      }
      if (downNote !== "" && state.note === downNote) { state.note = ""; downNote = ""; changed(); }
      const t = live.state().turn;
      const activeNow = t !== null && !LS.terminal(t.phase);
      if (running === null) {
        if (!activeNow || known === null || t.messageId !== known) return false;
        if (t.source === "live") { await live.snapshot(); return true; }          // the server runs nothing: the snapshot says so, and the stored line tells how it ended
        endNow();
        return true;
      }
      if (activeNow && (t.messageId === null || t.messageId === running)) { if (liveInfo && t.source === "live" && t.generationId === "") await live.snapshot(); return false; }
      try {
        const page = await api.get(base + "/messages", {after: running - 1, limit: 50});
        const list = isObj(page) && Array.isArray(page.messages) ? page.messages : [];
        if (list.some(m => isObj(m) && m.role === "agent" && m.turn === running && !live.holds(running, m.attempt))) return false;
      } catch (e) { /* the list is not readable now: show the turn, the next reconcile ends it if it is over */ }
      const now = live.state().turn;
      if (now !== null && !LS.terminal(now.phase) && (now.messageId === null || now.messageId === running)) return false;       // this page began it while we asked
      state.mode = "direct";
      if (liveInfo) {
        if (await live.snapshot()) { changed(); return true; }
      }
      live.dispatch({type: "adopt", messageId: running});
      return true;
    }

    // The owner's line as this page showed it before the server had it: gone as soon as a stored line carries the same client_id (one bubble, also with a second tab).
    function pendingLine(messages) {
      if (pending === null) return null;
      if ((Array.isArray(messages) ? messages : []).some(m => isObj(m) && m.client_id === pending.clientId)) { pending = null; return null; }
      return pending;
    }

    return {state: () => state, setMode, enableAsk, setAsk, draft, say, addFiles, take, removeFile, send, retry, stop, partial, rejoin, reconcile, resync,
      live: () => live !== null, frame: raw => { if (live) live.frame(raw); }, reconnect: () => (live && project().active ? live.reconnect() : Promise.resolve(false)), setPolling: on => { if (live) live.setPolling(on); },
      offer: rows => (live ? live.offer(rows) : (Array.isArray(rows) ? rows : [])), liveView: () => (live ? live.view() : null), pendingLine: messages => (live ? pendingLine(messages) : null),
      close: () => { if (live) live.close(); }};
  }

  // A draft into a message box (DV-1, "Turn this into work"): the words, the caret at their end, the box focused, and an `input` event so the page saves the draft and
  // resizes the box as it does for typing. It sends nothing; false when there is no box.
  function fillBox(box, words) {
    if (!box || typeof box !== "object") return false;
    const value = text(words);
    box.value = value;
    try { if (typeof box.setSelectionRange === "function") box.setSelectionRange(value.length, value.length); } catch (e) { /* a box that cannot place a caret still has its words */ }
    try { if (typeof box.focus === "function") box.focus(); } catch (e) { /* the words are in */ }
    try {
      const Ev = root.Event;
      if (typeof box.dispatchEvent === "function" && typeof Ev === "function") box.dispatchEvent(new Ev("input", {bubbles: true}));
    } catch (e) { /* no event, no autosave of this draft: the words are still in the box */ }
    return true;
  }

  const ChatComposer = {create, bar, chips, streamRow, streamParts, paintStreamRow, button, askBlock, providerOf, filesOf, hasFiles, sendKey, stopPress, tooLong, size, fillBox, MAX_FILES, MAX_MESSAGE, TEAM_FILES};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatComposer;
  else root.ChatComposer = ChatComposer;
})(globalThis);
