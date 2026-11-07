"use strict";
// ChatComposer (sutra_app/ui/static/js/chat_composer.js): the composer of the direct chat (work package ABS-15): attachments, send, stop, the streaming
// row and the provider rule. Run with: node --test tests/ui/js/chat_composer.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const ChatComposer = require(path.join(JS, "chat_composer.js"));
const ChatView = require(path.join(JS, "chat_view.js"));
globalThis.ChatFold = require(path.join(JS, "chat_fold.js"));          // chat_view draws a settled turn's blocks through the global, as the page does
const {create, bar, chips, streamRow, button, askBlock, providerOf} = ChatComposer;

const SID = "cs_000000000abc";
const ID = "a".repeat(64);
const READY = [{name: "claude", ready: true}, {name: "codex", ready: true}];
const NONE = [{name: "claude", ready: false, why_not: "not signed in"}, {name: "codex", ready: false, why_not: "not installed"}];

function fakeApi(handlers) {
  const calls = [];
  const api = {calls, post: async (p, body) => { calls.push({p, body}); const h = handlers[p] || handlers["*"]; if (!h) throw Object.assign(new Error("no route"), {status: 404}); return h(body); }};
  return api;
}
const file = (name, size) => ({name, size: size === undefined ? 5 : size});
const rig = (handlers, extra) => {
  const api = fakeApi(handlers || {});
  let changes = 0;
  const c = create(Object.assign({api, sid: SID, mode: "direct", readFile: async () => "aGVsbG8=", onChange: () => { changes += 1; }}, extra || {}));
  return {api, c, changes: () => changes};
};
const UP = "/api/chats/" + SID + "/attachments";
const DIRECT = "/api/chats/" + SID + "/direct";
const STOP = DIRECT + "/stop";

test("a file is checked, read, uploaded to the upload route and shown as a chip; Remove drops it", async () => {
  const {api, c} = rig({[UP]: () => ({id: ID, name: "notes.txt", kind: "text", size: 5})});
  await c.addFiles([file("notes.txt")]);
  assert.deepEqual(api.calls[0], {p: UP, body: {name: "notes.txt", content_b64: "aGVsbG8="}});
  const f = c.state().files[0];
  assert.equal(f.status, "ready"); assert.equal(f.id, ID);
  assert.match(chips(c.state().files), /<li class="ccfile ready"><span class="ccname">notes.txt<\/span><small> \(5 B\)<\/small>/);
  c.removeFile(f.key);
  assert.equal(c.state().files.length, 0);
  assert.equal(chips([]), "");
});

test("a file the limits refuse is never read or sent, and the owner is told why", async () => {
  const {api, c} = rig({});
  await c.addFiles([file("tool.exe"), file("empty.txt", 0), file("huge.pdf", 30 * 1024 * 1024)]);
  assert.equal(api.calls.length, 0);
  assert.equal(c.state().files.length, 0);
  assert.match(c.state().note, /over 20 MB/);
  assert.match(bar(c.state()), /class="ccnote"/);
});

test("no more than ten files go with one message", async () => {
  const {c} = rig({[UP]: () => ({id: ID, kind: "text", size: 5})});
  await c.addFiles(Array.from({length: 12}, (_, i) => file("f" + i + ".txt")));
  assert.equal(c.state().files.length, 10);
  assert.match(c.state().note, /Up to 10 files/);
});

test("a failed upload is a chip that says so and is not sent with the message", async () => {
  const {api, c} = rig({[UP]: () => { throw new Error("That file kind is not accepted."); }, [DIRECT]: () => ({message_id: 7, turn: "started"})});
  await c.addFiles([file("a.txt")]);
  assert.equal(c.state().files[0].status, "failed");
  assert.match(chips(c.state().files), /ccfile failed.*not attached: That file kind is not accepted\./);
  await c.send("hello");
  assert.deepEqual(api.calls[api.calls.length - 1].body, {text: "hello"});
});

test("Send posts the text and the uploaded refs to /direct, then the files are cleared and the turn is active", async () => {
  const {api, c} = rig({[UP]: () => ({id: ID, kind: "text", size: 5}), [DIRECT]: () => ({message_id: 41, turn: "started"})});
  await c.addFiles([file("a.txt")]);
  const out = await c.send("  read this  ");
  assert.deepEqual(out, {ok: true, message_id: 41});
  assert.deepEqual(api.calls[api.calls.length - 1], {p: DIRECT, body: {text: "read this", attachments: [ID], names: ["a.txt"]}});      // the names: the owner's line records them
  assert.deepEqual(c.state().files, []);
  assert.deepEqual(c.state().turn, {active: true, stopping: false, text: "", messageId: 41});
});

test("a refusal keeps the files and the box's text is the caller's; the turn is not left active", async () => {
  const {c} = rig({[UP]: () => ({id: ID, kind: "text", size: 5}), [DIRECT]: () => { throw Object.assign(new Error("This chat is already answering"), {status: 409}); }});
  await c.addFiles([file("a.txt")]);
  const out = await c.send("again");
  assert.equal(out.ok, false);
  assert.equal(c.state().turn.active, false);
  assert.equal(c.state().files.length, 1);
  assert.equal(c.state().note, "This chat is already answering");
});

test("nothing is sent while a file is uploading, with a blank message, while a turn answers, or in team mode", async () => {
  let release;
  const {api, c} = rig({[UP]: () => new Promise(resolve => { release = () => resolve({id: ID, kind: "text", size: 5}); }), [DIRECT]: () => ({message_id: 1})});
  const pending = c.addFiles([file("a.txt")]);
  assert.match((await c.send("x")).error, /finish uploading/);
  assert.equal(button(c.state(), "x").disabled, true);
  release(); await pending;
  assert.equal((await c.send("   ")).ok, false);
  assert.equal((await c.send("go")).ok, true);
  assert.match((await c.send("again")).error, /already answering/);
  assert.equal(api.calls.filter(x => x.p === DIRECT).length, 1);
  const team = rig({}, {mode: "team"});
  assert.match((await team.c.send("x")).error, /goes to the team/);
});

test("partials of this chat stream into the row, another chat's are ignored, and the row names the chosen provider", async () => {
  const {c} = rig({[DIRECT]: () => ({message_id: 5})});
  await c.send("hi");
  assert.equal(c.partial({session_id: "cs_other0000000", message_id: 5, delta: "no"}), false);
  c.partial({session_id: SID, message_id: 5, delta: "Hel"});
  c.partial({data: {session_id: SID, message_id: 5, delta: "lo <b>"}});
  assert.equal(c.state().turn.text, "Hello <b>");
  const row = streamRow(c.state(), "codex");
  assert.match(row, /Codex is writing/);
  assert.match(row, /Hello &lt;b&gt;/);
  assert.doesNotMatch(row, /<b>/);
  assert.match(streamRow(c.state(), ""), /The model is writing/);
  assert.equal(streamRow(rig({}).c.state(), "claude"), "");
});

test("the turn ends only when the reply that answers the owner's line is stored, not on another agent message", async () => {
  const {c} = rig({[DIRECT]: () => ({message_id: 10})});
  await c.send("hi");
  assert.equal(c.reconcile([{id: 10, role: "user"}]), false);
  assert.equal(c.reconcile([{id: 9, role: "agent"}]), false);
  assert.equal(c.reconcile([{id: 10, role: "user"}, {id: 11, role: "agent", kind: "note"}, {id: 12, role: "agent", kind: "text", turn: 4}]), false);
  assert.equal(c.state().turn.active, true);
  assert.equal(c.reconcile([{id: 10, role: "user"}, {id: 11, role: "agent", kind: "note"}, {id: 12, role: "agent", kind: "error", turn: 10}]), true);
  assert.equal(c.state().turn.active, false);
  assert.equal(streamRow(c.state(), "claude"), "");
});

test("the Send button becomes Stop while a direct turn answers; Stop posts to /direct/stop and then waits for the stored line", async () => {
  const {api, c} = rig({[DIRECT]: () => ({message_id: 3}), [STOP]: () => ({session_id: SID, stopped: true})});
  assert.deepEqual(button(c.state(), "x"), {label: "Send", act: "send", disabled: false});
  await c.send("long job");
  assert.deepEqual(button(c.state(), ""), {label: "Stop", act: "composer-stop", disabled: false});
  assert.deepEqual(await c.stop(), {ok: true, stopped: true});
  assert.equal(api.calls[api.calls.length - 1].p, STOP);
  assert.deepEqual(button(c.state(), ""), {label: "Stopping…", act: "composer-stop", disabled: true});
  assert.equal(c.state().turn.active, true);              // the stored reply ends it, not the click
});

test("Stop that finds nothing to stop keeps the turn until its reply is stored", async () => {
  const {c} = rig({[DIRECT]: () => ({message_id: 3}), [STOP]: () => ({session_id: SID, stopped: false})});
  await c.send("x");
  assert.deepEqual(await c.stop(), {ok: true, stopped: false});
  assert.equal(c.state().turn.active, true);
  assert.equal(c.state().turn.stopping, false);
  assert.equal(c.reconcile([{id: 4, role: "agent", kind: "text", turn: 3}]), true);
  assert.equal(c.state().turn.active, false);
});

test("a late partial after the turn ended, or another turn's partial, does not bring the row back", async () => {
  const {c} = rig({[DIRECT]: () => ({message_id: 5})});
  await c.send("hi");
  assert.equal(c.partial({session_id: SID, message_id: 4, delta: "old"}), false);
  assert.equal(c.state().turn.text, "");
  c.reconcile([{id: 6, role: "agent", kind: "text", turn: 5}]);
  assert.equal(c.partial({session_id: SID, message_id: 5, delta: "late"}), false);
  assert.equal(c.state().turn.active, false);
  assert.equal(streamRow(c.state(), "claude"), "");
});

test("a stop that fails says so and the button comes back", async () => {
  const {c} = rig({[DIRECT]: () => ({message_id: 3}), [STOP]: () => { throw new Error("The app is not responding."); }});
  await c.send("x");
  assert.equal((await c.stop()).ok, false);
  assert.equal(c.state().turn.stopping, false);
  assert.equal(button(c.state(), "").act, "composer-stop");
  assert.equal(c.state().note, "The app is not responding.");
});

test("a provider that cannot run is never the one shown, and with none runnable the owner is told", () => {
  assert.equal(providerOf(READY, "codex"), "codex");
  assert.equal(providerOf([{name: "claude", ready: true}, {name: "codex", ready: false}], "codex"), "");
  assert.equal(providerOf(READY, "gemini"), "");
  assert.equal(askBlock(READY), "");
  assert.match(askBlock(NONE), /No model can answer right now/);
  assert.match(askBlock(null), /No model can answer right now/);
  assert.match(askBlock([{name: "claude", ready: false, why_not: "not signed in"}]), /Sign in to Claude or Codex in Settings/);
  assert.equal(button({mode: "direct", files: [], turn: {active: false}}, "x", {blocked: true}).disabled, true);
});

test("the bar shows the mode toggle always and the attach controls only in direct mode; labels are escaped", () => {
  const team = bar({mode: "team", files: []});
  assert.match(team, /data-mode="team" aria-pressed="true"/);
  assert.doesNotMatch(team, /composer-attach/);
  const direct = bar({mode: "direct", files: [{key: "f1", name: "<img src=x>.png", status: "ready", size: 2048}]}, {labels: {team: "Plan with Sutra", direct: "Ask directly"}});
  assert.match(direct, /Plan with Sutra/);
  assert.match(direct, /data-mode="direct" aria-pressed="true"/);
  assert.match(direct, /composer-attach/);
  assert.match(direct, /Up to 10 files, 20 MB each/);
  assert.match(direct, /&lt;img src=x&gt;\.png/);
  assert.doesNotMatch(direct, /<img/);
  assert.match(direct, /\(2\.0 KB\)/);
  assert.doesNotMatch(bar({mode: "direct", files: []}, {toggle: false}), /ccmode/);
});

test("the stored reply keeps its typed blocks: the settled turn is one fold row, and a streaming one draws none", () => {
  const blocks = [{type: "tool_use", kind: "read", name: "Read", text: "a.md"}, {type: "tool_result", kind: "read", text: "ok"}, {type: "tool_use", kind: "run", name: "Bash", text: "ls"}];
  const session = {kind: "department", title: "Web", writable: true, status: "active"};
  const settled = ChatView.transcript(session, [{id: 2, role: "agent", who: "sutra", kind: "text", text: "Done.", blocks, state: "ok", at: ""}], {live: true});
  assert.match(settled, /2 tool calls: 1 read, 1 run/);
  const pending = ChatView.transcript(session, [{id: 2, role: "agent", who: "sutra", kind: "text", text: "Done.", blocks, state: "pending", at: ""}], {live: true});
  assert.doesNotMatch(pending, /tool calls/);
});

/* ---------------------------------------------------------------- GAP-chat-comfort: paste, drop, thumbnails, Retry */
const {filesOf, hasFiles} = ChatComposer;
const urlRig = () => {
  const made = [];
  const revoked = [];
  return {made, revoked, objectUrl: {create: f => { const u = "blob:http://127.0.0.1:8780/" + String(made.length + 1).padStart(8, "0"); made.push([u, f]); return u; }, revoke: u => revoked.push(u)}};
};
const image = (name, type) => ({name, size: 2048, type: type || "image/png"});

test("a text paste or a text drop is not a file paste: filesOf says null and the page lets it happen", () => {
  assert.equal(filesOf({files: [], items: [{kind: "string", type: "text/plain"}], getData: () => "hello"}), null);
  assert.equal(filesOf({files: []}), null);
  assert.equal(filesOf(null), null);
  assert.equal(filesOf("text"), null);
  const shot = image("image.png");
  assert.deepEqual(filesOf({files: [shot]}), [shot]);
  assert.deepEqual(filesOf({files: [], items: [{kind: "file", getAsFile: () => shot}]}), [shot]);
  assert.equal(hasFiles({types: ["text/plain"]}), false);
  assert.equal(hasFiles({types: ["Files", "text/uri-list"]}), true);
  assert.equal(hasFiles(undefined), false);
});

test("a pasted screenshot attaches once, with a name of its own and a thumbnail; a second paste does not look the same", async () => {
  const u = urlRig();
  const {api, c} = rig({[UP]: body => ({id: ID, name: body.name, kind: "image", size: 2048})}, {objectUrl: u.objectUrl});
  assert.equal(c.take({files: [], items: []}, {pasted: true}), false);
  assert.equal(api.calls.length, 0);
  await c.take({files: [image("image.png")]}, {pasted: true});
  await c.take({files: [image("", "image/jpeg")]}, {pasted: true});
  assert.deepEqual(api.calls.map(x => x.body.name), ["pasted-image-1.png", "pasted-image-2.jpg"]);
  assert.deepEqual(c.state().files.map(f => f.name), ["pasted-image-1.png", "pasted-image-2.jpg"]);
  const html = chips(c.state().files);
  assert.match(html, /<img class="ccthumb" src="blob:http:\/\/127\.0\.0\.1:8780\/00000001" alt=""\/>/);
  assert.equal(u.made.length, 2);
  await c.take({files: [image("logo.png")]});                         // a dropped file keeps its own name
  assert.equal(c.state().files[2].name, "logo.png");
});

test("a thumbnail is only a blob: URL; a PDF and a text file get a tile; a hostile name is escaped", () => {
  const html = chips([{key: "f1", name: "a.png", status: "ready", size: 1, kind: "image", preview: "javascript:alert(1)"},
    {key: "f2", name: "b.pdf", status: "ready", size: 1, kind: "pdf"}, {key: "f3", name: "<i>.md", status: "uploading", size: 1},
    {key: "f4", name: "c.png", status: "ready", size: 1, preview: 'blob:x" onerror="alert(1)'}]);
  assert.doesNotMatch(html, /javascript:|onerror|<img/);
  assert.deepEqual([...html.matchAll(/<span class="cctile" aria-hidden="true">(\w+)<\/span>/g)].map(m => m[1]), ["IMG", "PDF", "TXT", "IMG"]);
  assert.match(html, /&lt;i&gt;\.md/);
  assert.doesNotMatch(html, /<i>/);
});

test("a thumbnail's URL is revoked when its chip is removed and when the message is sent", async () => {
  const u = urlRig();
  const {c} = rig({[UP]: () => ({id: ID, kind: "image", size: 5}), [DIRECT]: () => ({message_id: 9})}, {objectUrl: u.objectUrl});
  await c.addFiles([image("one.png"), image("two.png"), file("notes.txt")]);
  assert.equal(u.made.length, 2);                                     // a text file has no thumbnail
  c.removeFile(c.state().files[0].key);
  assert.deepEqual(u.revoked, [u.made[0][0]]);
  await c.send("look");
  assert.deepEqual(u.revoked, [u.made[0][0], u.made[1][0]]);
  assert.deepEqual(c.state().files, []);
});

test("the 11th file of a paste is refused with the same note as the file chooser's", async () => {
  const {c} = rig({[UP]: () => ({id: ID, kind: "image", size: 5})}, {objectUrl: urlRig().objectUrl});
  await c.take({files: Array.from({length: 11}, (_, i) => image("shot" + i + ".png"))});
  assert.equal(c.state().files.length, 10);
  assert.match(c.state().note, /Up to 10 files/);
});

test("in team mode a pasted file switches the box to the model, with a one-line note", async () => {
  const {c} = rig({[UP]: () => ({id: ID, kind: "image", size: 5})}, {mode: "team", objectUrl: urlRig().objectUrl});
  assert.equal(c.state().mode, "team");
  await c.take({files: [image("image.png")]}, {pasted: true});
  assert.equal(c.state().mode, "direct");
  assert.equal(c.state().note, "Files go only to the model, so this message now asks the model directly.");
  assert.match(bar(c.state()), /class="ccnote" role="status">Files go only to the model/);
  const refused = rig({}, {mode: "team"});
  await refused.c.take({files: [file("tool.exe")]});
  assert.match(refused.c.state().note, /can be attached/);                // the refusal is what the owner needs to read
});

test("Retry sends the same words once, on the model, and a second press while it answers is refused", async () => {
  const {api, c} = rig({[DIRECT]: () => ({message_id: 30})}, {mode: "team"});
  const first = c.retry(12, "  What time do we open?  ");
  const second = await c.retry(12, "What time do we open?");
  assert.equal(second.ok, false);
  assert.equal((await first).ok, true);
  assert.deepEqual(api.calls.filter(x => x.p === DIRECT).map(x => x.body), [{text: "What time do we open?"}]);
  assert.equal(c.state().mode, "direct");
  assert.equal(c.state().turn.messageId, 30);
  assert.equal((await rig({}).c.retry(1, "   ")).ok, false);
});

test("Retry sends the files again when this page sent them, else text only and the note says so", async () => {
  const {api, c} = rig({[UP]: () => ({id: ID, kind: "text", size: 5}), [DIRECT]: () => ({message_id: 41})});
  await c.addFiles([file("menu.txt")]);
  await c.send("read the menu");
  c.reconcile([{id: 42, role: "agent", kind: "error", turn: 41}]);
  await c.retry(41, "read the menu", {files: 1});
  assert.deepEqual(api.calls[api.calls.length - 1].body, {text: "read the menu", attachments: [ID], names: ["menu.txt"]});
  assert.equal(c.state().note, "");
  const later = rig({[DIRECT]: () => ({message_id: 50})});            // after a reload the page does not know the files any more
  await later.c.retry(41, "read the menu", {files: 1});
  assert.deepEqual(later.api.calls[0].body, {text: "read the menu"});
  assert.equal(later.c.state().note, "Sent again without its files: attach them again to include them.");
});

test("rejoin: a chat shown again mid-turn starts its row from what streams next, and keeps the turn", async () => {
  const {c} = rig({[DIRECT]: () => ({message_id: 5})});
  assert.equal(c.rejoin(), false);
  await c.send("hi");
  c.partial({session_id: SID, message_id: 5, delta: "Hello"});
  assert.equal(c.rejoin(), true);
  assert.deepEqual(c.state().turn, {active: true, stopping: false, text: "", messageId: 5});
  c.partial({session_id: SID, message_id: 5, delta: " again"});
  assert.equal(c.state().turn.text, " again");
});

test("fluid. paintStreamRow draws the row into an element: through Fluid.paintStream when the page has it, else the html as before", () => {
  const {c} = rig({}), state = () => c.state();
  const el = {innerHTML: "", __html: undefined};
  // a row that is not streaming: nothing shows
  assert.equal(ChatComposer.paintStreamRow(el, state(), "claude"), false);
  assert.equal(ChatComposer.paintStreamRow(null, state(), "claude"), false);
  // no Fluid: the whole row as html, written once for the same row
  c.state().turn = {active: true, stopping: false, text: "so far", messageId: null};
  assert.equal(ChatComposer.paintStreamRow(el, state(), "claude"), true);
  assert.match(el.innerHTML, /Claude is writing/);
  assert.match(el.innerHTML, /so far/);
  const written = el.innerHTML;
  el.innerHTML = "marker";                                          // a second paint of the same row does not write again
  ChatComposer.paintStreamRow(el, state(), "claude");
  assert.equal(el.innerHTML, "marker");
  assert.equal(written.includes("marker"), false);
  // with Fluid and the markdown script: the parts go to Fluid.paintStream with the renderer
  const calls = [];
  globalThis.Fluid = {paintStream: (target, parts, options) => calls.push({target, parts, render: options.render})};
  globalThis.ChatMarkdown = {render: () => "<div class=\"cmd\"></div>"};
  try {
    assert.equal(ChatComposer.paintStreamRow(el, state(), "claude"), true);
    assert.deepEqual(calls[0].parts, {who: "Claude", text: "so far"});
    assert.equal(calls[0].target, el);
    assert.equal(calls[0].render, globalThis.ChatMarkdown.render);
    c.state().turn = {active: false, stopping: false, text: "", messageId: null};
    assert.equal(ChatComposer.paintStreamRow(el, state(), "claude"), false);
    assert.equal(calls[1].parts, null, "Fluid is told to clear the row");
  } finally {
    delete globalThis.Fluid;
    delete globalThis.ChatMarkdown;
  }
});

// ---- QA direct-chat: the Enter that confirms an IME candidate, and the second click of a double-click ------------------------------------------------

test("QA bug 2: Enter sends, but not while an IME composition is open (isComposing, or Safari's keyCode 229) and not with Shift", () => {
  const {sendKey} = ChatComposer;
  assert.equal(sendKey({key: "Enter"}), true);
  assert.equal(sendKey({key: "Enter", shiftKey: false, isComposing: false, keyCode: 13}), true);
  assert.equal(sendKey({key: "Enter", isComposing: true, keyCode: 13}), false);            // Chrome and Firefox: the Enter that confirms a candidate
  assert.equal(sendKey({key: "Enter", isComposing: false, keyCode: 229}), false);           // Safari ends the composition first, then reports 229 on that Enter
  assert.equal(sendKey({key: "Enter", shiftKey: true}), false);                             // a new line
  assert.equal(sendKey({key: "a"}), false);
  assert.equal(sendKey(null), false);
  assert.equal(sendKey(undefined), false);
});

test("QA bug 6: the second click of a double-click is not a Stop; a single click, a keyboard press and an unknown event are", () => {
  const {stopPress} = ChatComposer;
  assert.equal(stopPress({detail: 1}), true);
  assert.equal(stopPress({detail: 0}), true);                  // a keyboard activation of the button has no click count
  assert.equal(stopPress({detail: 2}), false);                 // what a double-click on Send delivers to the button that has just become Stop
  assert.equal(stopPress({detail: 3}), false);
  assert.equal(stopPress({}), true);
  assert.equal(stopPress(undefined), true);
});

test("QA bug 5: a reset partial empties the streaming row, then the next attempt's pieces fill it", async () => {
  const {c} = rig({[DIRECT]: () => ({message_id: 5})});
  await c.send("hi");
  c.partial({session_id: SID, message_id: 5, delta: "Here is a streamed answer. It has sev"});
  assert.equal(c.partial({session_id: SID, message_id: 5, delta: "", reset: true}), true);
  assert.equal(c.state().turn.text, "");
  assert.equal(c.state().turn.active, true);
  assert.equal(c.state().turn.messageId, 5);
  c.partial({session_id: SID, message_id: 5, delta: "Here is a streamed answer."});
  assert.equal(c.state().turn.text, "Here is a streamed answer.");
  assert.equal(c.partial({session_id: SID, message_id: 4, delta: "", reset: true}), false);            // another turn's reset is ignored like its pieces
  assert.equal(c.state().turn.text, "Here is a streamed answer.");
});

test("QA bug 7: a message over 8000 characters is refused before anything is sent, in a sentence that names the limit, and the box keeps it", async () => {
  const {api, c} = rig({[DIRECT]: () => ({message_id: 9})});
  const out = await c.send("x".repeat(8500));
  assert.deepEqual(out, {ok: false, error: "Messages can be up to 8000 characters; this one has 8500."});
  assert.equal(api.calls.filter(x => x.p === DIRECT).length, 0);
  assert.equal(c.state().turn.active, false);
  assert.equal(c.state().note, "Messages can be up to 8000 characters; this one has 8500.");
  assert.match(bar(c.state()), /class="ccnote"[^>]*>Messages can be up to 8000 characters; this one has 8500\./);
  assert.equal((await c.send("x".repeat(8000))).ok, true);                                  // the longest message goes
  assert.equal(api.calls.filter(x => x.p === DIRECT).length, 1);
});

test("QA bug 7: the length is counted as the server counts it (characters, not UTF-16 units) and on the trimmed text", async () => {
  const {api, c} = rig({[DIRECT]: () => ({message_id: 9})});
  assert.equal((await c.send("  " + "😀".repeat(8000) + "  ")).ok, true);                  // 8000 characters, 16000 UTF-16 units, padded with spaces
  assert.deepEqual(api.calls.map(x => x.body.text.length), [16000]);
  const again = rig({[DIRECT]: () => ({message_id: 10})});
  assert.equal((await again.c.send("😀".repeat(8001))).error, "Messages can be up to 8000 characters; this one has 8001.");
  assert.equal(ChatComposer.tooLong("short"), "");
  assert.equal(ChatComposer.MAX_MESSAGE, 8000);
});

// ---- QA direct-chat bugs 3 and 4: a page that did not start the turn, and a turn the server no longer runs --------------------------------------------

const BASE = "/api/chats/" + SID;
// An api with GET as well: `session` is what GET /api/chats/{sid} says (a function, so a test can change it), `messages` what the list answers.
function liveApi(handlers, session, messages) {
  const api = fakeApi(handlers || {});
  api.gets = [];
  api.get = async (p, params) => {
    api.gets.push({p, params});
    if (p === BASE) { const s = typeof session === "function" ? session() : session; if (s instanceof Error) throw s; return s; }
    if (p === BASE + "/messages") return {messages: typeof messages === "function" ? messages() : (messages || [])};
    throw Object.assign(new Error("no route"), {status: 404});
  };
  return api;
}
const rigLive = (handlers, session, messages, extra) => {
  const api = liveApi(handlers, session, messages);
  let changes = 0;
  const c = create(Object.assign({api, sid: SID, mode: "direct", readFile: async () => "aGVsbG8=", onChange: () => { changes += 1; }}, extra || {}));
  return {api, c, changes: () => changes};
};

test("QA bug 3: a reloaded page learns from the session that a direct turn answers, shows it and offers Stop", async () => {
  const {c, changes} = rigLive({[STOP]: () => ({session_id: SID, stopped: true})}, {id: SID, direct_turn: 41}, [{id: 41, role: "user"}], {mode: "team"});          // a fresh page: Plan with Sutra
  assert.equal(c.state().turn.active, false);
  assert.equal(await c.resync(), true);
  assert.deepEqual(c.state().turn, {active: true, stopping: false, text: "", messageId: 41});
  assert.equal(c.state().mode, "direct");                                       // the Stop button lives in direct mode: the box shows that the model is answering
  assert.deepEqual(button(c.state(), ""), {label: "Stop", act: "composer-stop", disabled: false});
  assert.match(streamRow(c.state(), "claude"), /Claude is writing/);
  assert.ok(changes() > 0);
  assert.equal(c.partial({session_id: SID, message_id: 41, delta: "Hel"}), true);          // the pieces that come from now on fill the row
  assert.equal(c.partial({session_id: SID, message_id: 40, delta: "old"}), false);
  assert.equal(c.state().turn.text, "Hel");
  assert.deepEqual(await c.stop(), {ok: true, stopped: true});                      // and Stop works from a page that did not start the turn
  assert.equal(c.reconcile([{id: 41, role: "user"}, {id: 42, role: "agent", kind: "note", turn: 41}]), true);
  assert.equal(c.state().turn.active, false);
});

test("QA bug 3: a turn whose reply is already stored is not shown as answering, whatever the session still says for a moment", async () => {
  const {c} = rigLive({}, {id: SID, direct_turn: 41}, [{id: 41, role: "user"}, {id: 42, role: "agent", kind: "text", turn: 41}], {mode: "team"});
  assert.equal(await c.resync(), false);
  assert.equal(c.state().turn.active, false);
  assert.equal(c.state().mode, "team");
});

test("QA bug 3: a session with no direct turn changes nothing, a failed read changes nothing, and a missing GET is no error", async () => {
  const quiet = rigLive({}, {id: SID, direct_turn: null});
  assert.equal(await quiet.c.resync(), false);
  assert.deepEqual(quiet.c.state().turn, {active: false, stopping: false, text: "", messageId: null});
  const down = rigLive({}, Object.assign(new Error("The app is not responding."), {status: 0}));
  assert.equal(await down.c.resync(), false);
  assert.equal(await rig({}).c.resync(), false);                                    // an api without get (the older tests' fake)
  const old = rigLive({}, {id: SID});                                               // a server that does not send the field
  assert.equal(await old.c.resync(), false);
});

test("QA bug 3: a second tab shows the turn of the first, and a later turn of another tab replaces an ended one", async () => {
  let session = {id: SID, direct_turn: 41};
  const {c} = rigLive({}, () => session, [{id: 41, role: "user"}]);
  await c.resync();
  assert.equal(c.state().turn.messageId, 41);
  assert.equal(await c.resync(), false);                                            // the same turn again: nothing moves
  c.partial({session_id: SID, message_id: 41, delta: "abc"});
  assert.equal(c.state().turn.text, "abc");
  session = {id: SID, direct_turn: 50};                                             // 41 ended and another turn began elsewhere
  assert.equal(await c.resync(), true);
  assert.deepEqual(c.state().turn, {active: true, stopping: false, text: "", messageId: 50});
});

test("QA bug 4: a turn this page started that the server no longer runs (it died with the last process) leaves the answering state", async () => {
  let session = {id: SID, direct_turn: 3};
  const {c} = rigLive({[DIRECT]: () => ({message_id: 3})}, () => session, []);
  await c.send("crash me");
  assert.equal(c.state().turn.messageId, 3);
  c.partial({session_id: SID, message_id: 3, delta: "half"});
  assert.equal(await c.resync(), false);                                            // the server still runs it: the page keeps it
  assert.equal(c.state().turn.active, true);
  session = {id: SID, direct_turn: null};                                           // the server was killed and started again: nothing answers
  assert.equal(await c.resync(), true);
  assert.deepEqual(c.state().turn, {active: false, stopping: false, text: "", messageId: null});
  assert.deepEqual(button(c.state(), "x"), {label: "Send", act: "send", disabled: false});
  assert.equal(streamRow(c.state(), "claude"), "");
  assert.equal((await c.send("again")).ok, true);                                    // and the owner can write again
});

test("QA bug 4: a read that was asked before this page's POST was answered, or while another turn began, never ends a turn it did not see", async () => {
  let release;
  const slow = rigLive({[DIRECT]: () => new Promise(resolve => { release = () => resolve({message_id: 8}); })}, {id: SID, direct_turn: null});
  const sending = slow.c.send("hello");
  await Promise.resolve();
  assert.equal(slow.c.state().turn.active, true);
  assert.equal(await slow.c.resync(), false);                                       // the POST is in flight: the server may not have started the turn yet
  assert.equal(slow.c.state().turn.active, true);
  release(); await sending;
  assert.equal(slow.c.state().turn.messageId, 8);
  // a read that says "nothing answers" and arrives after this page moved on to another turn must not end that one
  const ids = [8, 9];
  const moved = rigLive({[DIRECT]: () => ({message_id: ids.shift()})}, {id: SID, direct_turn: null});
  await moved.c.send("hello");
  assert.equal(moved.c.state().turn.messageId, 8);
  const pending = moved.c.resync();                                                  // asked while turn 8 is the page's: the answer is "nothing answers"
  moved.c.reconcile([{id: 10, role: "agent", kind: "text", turn: 8}]);              // turn 8 is over and the owner sends the next line before the read is handled
  await moved.c.send("and again");
  assert.equal(moved.c.state().turn.messageId, 9);
  await pending;
  assert.equal(moved.c.state().turn.active, true);
  assert.equal(moved.c.state().turn.messageId, 9);
  // the session still names a turn whose reply the page already has (the registry is cleared a moment after the reply is stored): not adopted again
  const stale = rigLive({[DIRECT]: () => ({message_id: 8})}, {id: SID, direct_turn: 8}, [{id: 9, role: "agent", kind: "text", turn: 8}]);
  await stale.c.send("hello");
  stale.c.reconcile([{id: 9, role: "agent", kind: "text", turn: 8}]);
  assert.equal(stale.c.state().turn.active, false);
  assert.equal(await stale.c.resync(), false);
  assert.equal(stale.c.state().turn.active, false);
});

test("QA bug 4: Stop on a turn the server does not run ends the page's turn; Stop on one it still runs keeps waiting for the stored line", async () => {
  let session = {id: SID, direct_turn: null};
  const dead = rigLive({[DIRECT]: () => ({message_id: 3}), [STOP]: () => ({session_id: SID, stopped: false})}, () => session);
  await dead.c.send("x");
  assert.deepEqual(await dead.c.stop(), {ok: true, stopped: false});
  assert.equal(dead.c.state().turn.active, false);                                   // no more Stop that does nothing
  assert.deepEqual(button(dead.c.state(), ""), {label: "Send", act: "send", disabled: false});
  session = {id: SID, direct_turn: 3};
  const live = rigLive({[DIRECT]: () => ({message_id: 3}), [STOP]: () => ({session_id: SID, stopped: false})}, () => session);
  await live.c.send("x");
  assert.deepEqual(await live.c.stop(), {ok: true, stopped: false});
  assert.equal(live.c.state().turn.active, true);                                    // the turn is about to start or to be stored: the old rule
  assert.equal(live.c.state().turn.stopping, false);
});

// ---- QA direct-chat P3: the provider pill is read again when a turn ends ------------------------------------------------------------------------------

test("QA P3: the page is told when a turn ends, so the provider pill can be read again (the turn may have switched the chat to the other model)", async () => {
  let ended = 0;
  const {c} = rigLive({[DIRECT]: () => ({message_id: 3})}, {id: SID, direct_turn: 3}, [], {onTurnEnd: () => { ended += 1; }});
  await c.send("hello");
  assert.equal(ended, 0);                                                           // sending is not the end
  c.partial({session_id: SID, message_id: 3, delta: "hi"});
  assert.equal(ended, 0);
  assert.equal(c.reconcile([{id: 4, role: "agent", kind: "text", turn: 2}]), false);          // another line's reply is not this turn's
  assert.equal(ended, 0);
  assert.equal(c.reconcile([{id: 4, role: "agent", kind: "text", turn: 3}]), true);           // the stored reply ends it
  assert.equal(ended, 1);
  assert.equal(c.reconcile([{id: 4, role: "agent", kind: "text", turn: 3}]), false);          // once
  assert.equal(ended, 1);
});

test("QA P3: a turn the server lost, and a refused send, are told apart: only the lost turn (it ran, then ended) asks for the pill again", async () => {
  let session = {id: SID, direct_turn: 5};
  let ended = 0;
  const {c} = rigLive({[DIRECT]: () => ({message_id: 5})}, () => session, [], {onTurnEnd: () => { ended += 1; }});
  await c.send("crash me");
  session = {id: SID, direct_turn: null};
  assert.equal(await c.resync(), true);
  assert.equal(ended, 1);
  const refused = rigLive({[DIRECT]: () => { throw Object.assign(new Error("no"), {status: 409}); }}, {id: SID, direct_turn: null}, [], {onTurnEnd: () => { ended += 1; }});
  assert.equal((await refused.c.send("x")).ok, false);                              // nothing ran: the pill cannot have changed
  assert.equal(ended, 1);
  assert.doesNotThrow(() => rigLive({}, {id: SID}, [], {onTurnEnd: "not a function"}).c.reconcile([]));          // a missing or odd hook is no hook
});

// ---- QA direct-chat P3: 'The app is not responding.' goes when the app answers again ------------------------------------------------------------------

const down = () => Object.assign(new Error("The app is not responding."), {name: "ApiError", status: 0, code: "network"});

test("QA P3: the note of a send that found the app down goes when the page reads the session again, a note of another kind stays", async () => {
  let session = down();
  const {c, changes} = rigLive({[DIRECT]: () => { throw down(); }}, () => session, []);
  assert.deepEqual(await c.send("hello"), {ok: false, error: "The app is not responding."});
  assert.equal(c.state().note, "The app is not responding.");
  assert.equal(await c.resync(), false);                                            // the app is still down (the read fails): the note stays
  assert.equal(c.state().note, "The app is not responding.");
  session = {id: SID, direct_turn: null};                                           // the app is back and the page read it
  const before = changes();
  await c.resync();
  assert.equal(c.state().note, "");
  assert.ok(changes() > before);                                                    // and the page was told to repaint
  // a refusal of another kind is the owner's to read until they act
  const busy = rigLive({[DIRECT]: () => { throw Object.assign(new Error("This chat is already answering."), {name: "ApiError", status: 409, code: "busy"}); }}, {id: SID, direct_turn: null}, []);
  await busy.c.send("hello");
  await busy.c.resync();
  assert.equal(busy.c.state().note, "This chat is already answering.");
  const long = rigLive({}, {id: SID, direct_turn: null}, []);
  await long.c.send("x".repeat(8001));
  await long.c.resync();
  assert.match(long.c.state().note, /Messages can be up to 8000 characters/);
});

test("QA P3: a note the owner has since replaced is not cleared by the page reading the session", async () => {
  const {c} = rigLive({[DIRECT]: () => { throw down(); }}, {id: SID, direct_turn: null}, []);
  await c.send("hello");
  await c.send("");                                                                  // an empty line is refused first (and sets no note)
  await c.send("x".repeat(8001));                                                    // a newer refusal replaces the 'not responding' note
  await c.resync();
  assert.match(c.state().note, /Messages can be up to 8000 characters/);
});

test("QA P3: the offline demo has no model to ask, and the sentence does not send the owner to a sign-in that cannot work there", () => {
  const words = askBlock([]);                                                      // the server listed no provider at all: nothing to sign in to
  assert.match(words, /offline demo/i);
  assert.match(words, /Plan with Sutra|Tell the team/);
  assert.doesNotMatch(words, /Sign in/);
  assert.equal(askBlock([{name: "codex", ready: true}]), "");
});
