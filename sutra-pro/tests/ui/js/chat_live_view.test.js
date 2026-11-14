"use strict";
// ChatLiveView + ChatLiveActivity (sutra_app/ui/static/js/chat_live_view.js, chat_live_activity.js): the reply of a direct turn as keyed blocks, live and settled by the same code
// (STR-10). A small DOM stands in for the page (tests/ui/js/helpers/fake_dom.js) and counts every node it ever creates. Run with: node --test tests/ui/js/chat_live_view.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const LV = require(path.join(JS, "chat_live_view.js"));
const A = require(path.join(JS, "chat_live_activity.js"));
const S = require(path.join(JS, "chat_live_store.js"));
const {createIntake} = require(path.join(JS, "chat_live_events.js"));
const MD = require(path.join(JS, "chat_markdown.js"));
const {createDocument} = require("./helpers/fake_dom.js");

const SID = "cs_000000000abc";
const GEN = "gen00001";
const CID = "client-0001";

function rig() {
  const doc = createDocument();
  const r = {doc, state: S.create(SID), intake: createIntake({sid: SID}), seq: 0, now: 1000, lit: []};
  r.act = a => { r.state = S.reduce(r.state, Object.assign({now: r.now}, a)); };
  r.wire = (type, payload, block, ts) => {
    r.seq += 1;
    const raw = {v: 1, id: GEN + ":" + r.seq, conversation_id: SID, message_id: 7, generation_id: GEN, attempt: 1, seq: r.seq, ts: ts || "2026-11-14T10:00:00.000Z", type, payload: payload || {}};
    if (block) raw.block_id = block;
    r.intake.push(raw).forEach(a => r.act(a));
  };
  r.begin = () => { r.act({type: "send", clientId: CID}); r.act({type: "accepted", clientId: CID, generationId: GEN, messageId: 7, attemptNo: 1}); r.wire("turn.accepted", {client_id: CID, attempt_no: 1}); };
  r.view = () => ({turn: r.state.turn, settled: r.state.settled, label: S.label(r.state, r.now), activity: S.activity(r.state, r.now), note: S.streamNote(r.state), canStop: S.canStop(r.state),
    elapsedMs: S.elapsed(r.state, r.now), polling: false});
  r.shell = (turn, attempt, opts) => { const host = doc.createElement("div"); host.innerHTML = LV.shellHtml(turn || 7, attempt || 1, opts); doc.body.appendChild(host); return host.firstElementChild; };
  r.deps = () => ({render: MD.render, highlight: pre => { r.lit.push(pre); LV.highlight(pre); }});
  r.paintLive = shell => LV.paint(shell, LV.fromLive(r.view(), {}), r.deps());
  return r;
}
const q = (node, sel) => node.querySelector(sel);
const qa = (node, sel) => node.querySelectorAll(sel);
const delta = (r, text, off, id) => r.wire("block.delta", {delta: text, offset: off}, id || "b2");

test("the shell is a constant of (turn, try): live and stored have the same html, so the list never replaces the node", () => {
  assert.equal(LV.keyOf(7, 1), "turn:7:1");
  assert.equal(LV.keyOf(7, undefined), "turn:7:1");
  assert.equal(LV.shellHtml(7, 1), LV.shellHtml(7, 1));
  assert.notEqual(LV.shellHtml(7, 1), LV.shellHtml(7, 2));
  assert.match(LV.shellHtml(7, 1, {superseded: true}), /Earlier try/);
  assert.ok(!/data-id/.test(LV.shellHtml(7, 1)), "an id would make the html differ once the reply is stored");
});

test("isReply: a text reply of a turn, and the note or error that carries the ended turn's blocks; not a plain note, an owner line or another agent line", () => {
  assert.equal(LV.isReply({role: "agent", kind: "text", turn: 7}), true);
  assert.equal(LV.isReply({role: "agent", kind: "note", turn: 7, ordered: true, blocks: [{type: "tool_use"}]}), true);
  assert.equal(LV.isReply({role: "agent", kind: "error", turn: 7, ordered: true, blocks: [{type: "tool_use"}]}), true);
  assert.equal(LV.isReply({role: "agent", kind: "note", turn: 7, text: "Stopped."}), false);
  assert.equal(LV.isReply({role: "agent", kind: "error", turn: 7, text: "x"}), false);
  assert.equal(LV.isReply({role: "user", kind: "text", turn: 7}), false);
  assert.equal(LV.isReply({role: "agent", kind: "text"}), false);
});

test("a live turn paints its who, a short status label that is announced, and a clock that is not", () => {
  const r = rig();
  r.begin();
  r.wire("turn.connecting", {provider: "claude", model: "sonnet"});
  const shell = r.shell();
  r.paintLive(shell);
  assert.equal(q(shell, ".cl-who").textContent, "Claude · via Claude sonnet");
  const status = q(shell, ".cl-status");
  assert.equal(status.getAttribute("role"), "status");
  assert.equal(status.getAttribute("aria-live"), "polite");
  assert.equal(status.textContent, "Starting Claude");
  assert.equal(q(shell, ".cl-clock").getAttribute("aria-hidden"), "true");
  r.wire("turn.started", {provider: "claude", model: "sonnet", idle_limit_s: 120});
  r.wire("attempt.failed", {provider: "claude", reason: "Claude is overloaded.", delay_s: 10});
  r.paintLive(shell);
  assert.equal(status.textContent, "Claude failed: Claude is overloaded. Retrying");        // the number is in the clock, so it is not read out every second
  assert.equal(q(shell, ".cl-clock").textContent, "in 10 s");
  r.now += 4000;
  r.paintLive(shell);
  assert.equal(status.textContent, "Claude failed: Claude is overloaded. Retrying");
  assert.equal(q(shell, ".cl-clock").textContent, "in 6 s");
  assert.equal(shell.getAttribute("data-state"), "live");
});

test("blocks are keyed: a node is created once and patched as its block grows, a tool shows its name first and its title when the input is known", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  const shell = r.shell();
  r.wire("block.start", {type: "tool_use", kind: "read", name: "Read"}, "b1", "2026-11-14T10:00:01.000Z");
  r.paintLive(shell);
  const tool = q(shell, '[data-block="b1"]');
  assert.equal(tool.tagName, "DETAILS");
  assert.equal(q(tool, ".cl-title").textContent, "Using Read");
  assert.equal(tool.getAttribute("data-status"), "open");
  r.wire("block.update", {title: "Reading src/x.py", target: "src/x.py"}, "b1");
  r.paintLive(shell);
  assert.equal(q(shell, '[data-block="b1"]'), tool);
  assert.equal(q(tool, ".cl-title").textContent, "Reading src/x.py");
  r.wire("block.end", {status: "ok"}, "b1", "2026-11-14T10:00:03.400Z");
  r.wire("block.start", {type: "text"}, "b2");
  delta(r, "Hel", 0);
  r.paintLive(shell);
  const text = q(shell, '[data-block="b2"]');
  delta(r, "lo.", 3);
  r.paintLive(shell);
  assert.equal(q(shell, '[data-block="b2"]'), text);
  assert.equal(text.textContent, "Hello.");
  assert.equal(tool.getAttribute("data-status"), "ok");
  assert.equal(q(tool, ".cl-meta").textContent, "2.4 s");                                    // the real time between the block's own events
  assert.equal(qa(shell, ".cl-block").length, 2);
  assert.deepEqual(qa(shell, ".cl-block").map(n => n.getAttribute("data-block")), ["b1", "b2"]);
});

test("a tool item expands to its target and status; the output of a stored tool is shown, cut honestly", () => {
  const r = rig();
  const shell = r.shell();
  const m = {id: 9, role: "agent", kind: "text", turn: 7, attempt: 1, ordered: true, text: "Done.", state: "ok", blocks: [
    {type: "tool_use", kind: "run", name: "Bash", text: "Running npm test"}, {type: "tool_result", kind: "run", name: "Bash", text: "3 passed", is_error: false, truncated: true}, {type: "text", kind: "other", text: "Done."}]};
  LV.paint(shell, LV.fromMessage(m, {who: "Claude"}), r.deps());
  const tool = q(shell, ".cl-tool");
  assert.equal(q(tool, ".cl-title").textContent, "Running npm test");
  assert.match(q(tool, ".cl-detail").textContent, /Status: Done/);
  assert.equal(q(tool, ".cl-out").textContent, "3 passed");
  assert.match(q(tool, ".cl-detail").textContent, /cut/);
});

test("a failed tool and an interrupted one say so with the real word", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "tool_use", kind: "run", name: "Bash"}, "b1");
  r.wire("block.update", {title: "Running make"}, "b1");
  r.wire("block.end", {status: "error", is_error: true}, "b1");
  r.wire("block.start", {type: "tool_use", kind: "edit", name: "Edit"}, "b2");
  r.wire("turn.stopping", {});
  r.wire("turn.stopped", {message_id_reply: 9, attempt_no: 1, exit: "cancelled", stored_order: ["b1", "b2"]});
  const shell = r.shell();
  r.paintLive(shell);
  assert.match(q(q(shell, '[data-block="b1"]'), ".cl-detail").textContent, /Status: Failed/);
  assert.match(q(q(shell, '[data-block="b2"]'), ".cl-detail").textContent, /Status: Interrupted, may have partly run/);
  assert.equal(shell.getAttribute("data-state"), "stopped");
});

test("thinking shows presence while it runs and its real duration after; never its text", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "thinking"}, "b1", "2026-11-14T10:00:00.000Z");
  const shell = r.shell();
  r.paintLive(shell);
  const think = q(shell, ".cl-think");
  assert.equal(q(think, ".cl-title").textContent, "Thinking");
  r.wire("block.end", {status: "ok"}, "b1", "2026-11-14T10:00:07.000Z");
  r.paintLive(shell);
  assert.equal(q(think, ".cl-title").textContent, "Thought");
  assert.equal(q(think, ".cl-meta").textContent, "7.0 s");
});

test("SETTLE IN PLACE: the stored message paints into the same shell, the block nodes carry over by id, and no node is created for the blocks that were already there", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "tool_use", kind: "read", name: "Read"}, "b1");
  r.wire("block.update", {title: "Reading a.py"}, "b1");
  r.wire("block.end", {status: "ok"}, "b1");
  r.wire("block.start", {type: "text"}, "b2");
  delta(r, "All done.\n\nSecond paragraph is here and long enough.", 0);
  const shell = r.shell();
  r.paintLive(shell);
  const toolNode = q(shell, '[data-block="b1"]');
  const textNode = q(shell, '[data-block="b2"]');
  const firstPara = q(textNode, "p");
  r.wire("block.end", {status: "ok"}, "b2");
  r.wire("turn.done", {message_id_reply: 9, attempt_no: 1, stored_order: ["b1", "b1", "b2"]});
  r.paintLive(shell);                                                                       // the live turn ended
  const made = r.doc.created;
  const stored = {id: 9, role: "agent", kind: "text", turn: 7, attempt: 1, ordered: true, state: "ok", text: "All done.\n\nSecond paragraph is here and long enough.", blocks: [
    {type: "tool_use", kind: "read", name: "Read", text: "Reading a.py"}, {type: "tool_result", kind: "read", name: "Read", text: "", is_error: false},
    {type: "text", kind: "other", text: "All done.\n\nSecond paragraph is here and long enough."}]};
  const models = LV.plan([stored], r.view(), {whoOf: () => "Claude"}).models;
  assert.equal(Object.keys(models)[0], "turn:7:1");
  assert.deepEqual(models["turn:7:1"].blocks.map(b => b.id), ["b1", "b2"]);                  // the stored order maps each stored block to its live id
  LV.paint(shell, models["turn:7:1"], r.deps());
  assert.equal(q(shell, '[data-block="b1"]'), toolNode);
  assert.equal(q(shell, '[data-block="b2"]'), textNode);
  assert.equal(q(textNode, "p"), firstPara);
  assert.equal(shell.getAttribute("data-id"), "9");
  assert.equal(shell.getAttribute("data-state"), "ok");
  assert.ok(r.doc.created - made <= 12, "only the tail paragraph and the copy button may be new, not the blocks: " + (r.doc.created - made));
  assert.equal(qa(shell, ".cl-block").length, 2);
});

test("plan: the live turn has its own item only until a stored message has its key; the stored message then takes the node", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  const first = LV.plan([], r.view(), {});
  assert.deepEqual(first.liveItem, {key: "turn:7:1", html: LV.shellHtml(7, 1)});
  assert.equal(first.models["turn:7:1"].source, "live");
  const second = LV.plan([{id: 9, role: "agent", kind: "text", turn: 7, attempt: 1, text: "x"}], r.view(), {});
  assert.equal(second.liveItem, null);
  assert.equal(second.models["turn:7:1"].source, "stored");
  assert.equal(LV.plan([], {turn: null}, {}).liveItem, null);
});

test("a retry's reply has its own shell (turn:7:2); the first try is a different key and is collapsed under Earlier try once superseded", () => {
  const first = {id: 8, role: "agent", kind: "text", turn: 7, attempt: 1, text: "old", superseded: true};
  const p = LV.plan([first], {turn: null}, {});
  assert.equal(p.models["turn:7:1"].superseded, true);
  const r = rig();
  const shell = r.shell(7, 1, {superseded: true});
  LV.paint(shell, p.models["turn:7:1"], r.deps());
  assert.ok(q(shell, "details.cl-prior"));
  assert.equal(q(shell, ".cl-body").textContent, "old");
});

test("earlier tries show who failed, why, and what they ran; a possible change of files is said, and the live note repeats it", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "tool_use", kind: "edit", name: "Edit"}, "b1");
  r.wire("block.update", {title: "Editing a.py"}, "b1");
  r.wire("attempt.failed", {provider: "claude", reason: "Claude is overloaded.", delay_s: 5});
  r.wire("attempt.restart", {attempt: 2, provider: "claude", after_side_effects: true});
  const shell = r.shell();
  r.paintLive(shell);
  const prior = q(shell, ".cl-earlier details");
  assert.match(q(prior, "summary").textContent, /Earlier try: Claude failed \(Claude is overloaded\), it may have changed files/);
  assert.equal(q(prior, "li").textContent, "Editing a.py");
  assert.match(q(shell, ".cl-note").textContent, /may have changed files/);
  assert.equal(qa(shell, ".cl-block").length, 0, "the new try starts with no blocks");
});

test("a provider that sends its answer whole: a stable note, the answer appears at once in one block, no travelling caret", () => {
  const r = rig();
  r.begin();
  r.wire("turn.connecting", {provider: "codex", model: "gpt", stream_mode: "final"});
  r.wire("turn.started", {provider: "codex", model: "gpt", stream_mode: "final"});
  const shell = r.shell();
  r.paintLive(shell);
  assert.equal(q(shell, ".cl-note").textContent, "Codex sends its answer in one piece");
  r.wire("block.start", {type: "text"}, "b1");
  r.wire("block.end", {status: "ok", text: "The whole answer."}, "b1");
  r.paintLive(shell);
  assert.equal(q(shell, ".cl-text").textContent, "The whole answer.");
  assert.ok(!q(shell, ".cl-text").classList.contains("cl-writing"));
  assert.ok(q(shell, ".cl-text").classList.contains("cl-in"), "it arrives with an entrance, as a whole block");
});

test("the caret belongs to the one open text block of a running turn, and goes with Stopping and with the end", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "text"}, "b1");
  delta(r, "Hi", 0, "b1");
  const shell = r.shell();
  r.paintLive(shell);
  assert.ok(q(shell, ".cl-text").classList.contains("cl-writing"));
  r.wire("turn.stopping", {});
  r.paintLive(shell);
  assert.ok(!q(shell, ".cl-text").classList.contains("cl-writing"));
});

test("entrance only for new content: the blocks of the first drawing do not enter, the ones that arrive later do", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "tool_use", kind: "read", name: "Read"}, "b1");
  const shell = r.shell();
  r.paintLive(shell);
  assert.ok(q(shell, '[data-block="b1"]').classList.contains("cl-in") === false);
  r.wire("block.start", {type: "tool_use", kind: "read", name: "Read"}, "b2");
  r.paintLive(shell);
  assert.ok(q(shell, '[data-block="b2"]').classList.contains("cl-in"));
  assert.ok(!q(shell, '[data-block="b1"]').classList.contains("cl-in"));
});

test("historical messages go through the same model: ordered blocks in order, a text-only message, a legacy message (text then its tools folded in one row)", () => {
  const r = rig();
  const ordered = r.shell(1, 1);
  LV.paint(ordered, LV.fromMessage({id: 2, role: "agent", kind: "text", turn: 1, ordered: true, text: "B", blocks: [{type: "text", kind: "other", text: "A"}, {type: "tool_use", kind: "read", name: "Read", text: "Reading x"},
    {type: "tool_result", kind: "read", name: "Read", text: ""}, {type: "text", kind: "other", text: "B"}]}, {who: "Claude"}), r.deps());
  assert.deepEqual(qa(ordered, ".cl-block").map(n => n.className.split(" ")[1]), ["cl-text", "cl-tool", "cl-text"]);
  const plain = r.shell(3, 1);
  LV.paint(plain, LV.fromMessage({id: 4, role: "agent", kind: "text", turn: 3, text: "Just words."}, {who: "Claude"}), r.deps());
  assert.equal(q(plain, ".cl-body").textContent, "Just words.");
  const legacy = r.shell(5, 1);
  LV.paint(legacy, LV.fromMessage({id: 6, role: "agent", kind: "text", turn: 5, text: "Answer.", blocks: [{type: "tool_use", kind: "read", name: "Read", text: "Read a"}, {type: "tool_result", kind: "read", name: "Read", text: "x"},
    {type: "tool_use", kind: "run", name: "Bash", text: "Run b"}, {type: "tool_result", kind: "run", name: "Bash", text: "y", is_error: true}]}, {who: "Claude"}), r.deps());
  assert.equal(q(legacy, ".cl-body").textContent, "Answer.");
  assert.equal(q(legacy, ".cl-steps").hidden, false);
  assert.equal(q(legacy, ".cl-steps-sum").textContent, "2 tool calls, 1 failed");
  assert.equal(qa(legacy, ".cl-steps-body .cl-tool").length, 2);
});

test("a stopped or failed turn that kept its tools and no text: the note or error row is the reply item, with its words as the ending", () => {
  const r = rig();
  const shell = r.shell(7, 1);
  LV.paint(shell, LV.fromMessage({id: 8, role: "agent", kind: "error", turn: 7, attempt: 1, ordered: true, state: "error", text: "Claude did not answer within 120 s: it sent no output for that long, so it was stopped",
    blocks: [{type: "tool_use", kind: "run", name: "Bash", text: "Running tests"}]}, {who: "Claude"}), r.deps());
  assert.equal(shell.getAttribute("data-state"), "error");
  assert.match(q(shell, ".cl-ending").textContent, /120 s/);
  assert.match(q(q(shell, ".cl-tool"), ".cl-detail").textContent, /Interrupted, may have partly run/);
});

test("hostile words stay text: a tool title, a who, a model and a reply with markup draw no element of the author's", () => {
  const r = rig();
  r.begin();
  r.wire("turn.connecting", {provider: "claude", model: "<img src=x onerror=alert(1)>"});
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "tool_use", kind: "run", name: "<script>x</script>"}, "b1");
  r.wire("block.update", {title: "<b>bold</b> & \"quotes\"", target: "<i>t</i>"}, "b1");
  r.wire("block.start", {type: "text"}, "b2");
  delta(r, "Hello <script>alert(1)</script> **bold** <img src=x>", 0);
  const shell = r.shell();
  r.paintLive(shell);
  assert.equal(qa(shell, "script").length, 0);
  assert.equal(qa(shell, "img").length, 0);
  assert.equal(qa(shell, "i").length, 0);
  assert.equal(q(q(shell, ".cl-tool"), ".cl-title").textContent, "<b>bold</b> & \"quotes\"");
  assert.match(q(shell, ".cl-who").textContent, /<img src=x onerror=alert\(1\)>/);
  assert.match(q(shell, ".cl-text").textContent, /<script>alert\(1\)<\/script>/);
});

test("Stop is in the reply while it runs (disabled while Stopping); Copy appears when it has settled with text", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  const shell = r.shell();
  r.paintLive(shell);
  assert.equal(q(shell, '.cl-actions [data-act="composer-stop"]').textContent, "Stop");
  r.act({type: "stop.pressed"});
  r.paintLive(shell);
  assert.equal(q(shell, '.cl-actions [data-act="composer-stop"]').textContent, "Stopping…");
  assert.equal(q(shell, '.cl-actions [data-act="composer-stop"]').disabled, true);
  const done = r.shell(3, 1);
  LV.paint(done, LV.fromMessage({id: 4, role: "agent", kind: "text", turn: 3, text: "Words."}, {}), r.deps());
  assert.ok(q(done, '.cl-actions [data-act="copy-reply"]'));
  assert.equal(done.__cl.text, "Words.");
});

test("Copy puts the reply's text on the clipboard and says so; Copy code copies one block; a refusal says so too", async () => {
  const r = rig();
  const shell = r.shell(3, 1);
  LV.paint(shell, LV.fromMessage({id: 4, role: "agent", kind: "text", turn: 3, text: "Intro.\n\n```js\nlet a = 1;\n```\n\nOutro."}, {}), r.deps());
  const written = [];
  const timers = [];
  const deps = {clipboard: {writeText: async t => { written.push(t); }}, schedule: fn => timers.push(fn)};
  const button = q(shell, '[data-act="copy-reply"]');
  assert.equal(await LV.copy(button, deps), true);
  assert.equal(written[0], "Intro.\n\n```js\nlet a = 1;\n```\n\nOutro.");
  assert.equal(button.textContent, "Copied");
  timers.forEach(f => f());
  assert.equal(button.textContent, "Copy");
  const codeButton = q(shell, '[data-act="copy-code"]');
  assert.ok(codeButton, "a settled code block has its own copy button");
  assert.equal(await LV.copy(codeButton, deps), true);
  assert.equal(written[1], "let a = 1;");
  const refused = {clipboard: {writeText: async () => { throw new Error("denied"); }}, schedule: () => {}};
  assert.equal(await LV.copy(button, refused), false);
  assert.equal(button.textContent, "Could not copy");
});

test("a code block is highlighted once, when it has settled, and its text is unchanged; while it streams nothing is highlighted", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "text"}, "b1");
  const first = "```js\nconst a = \"x\"; // note\n";
  delta(r, first, 0, "b1");
  const shell = r.shell();
  r.paintLive(shell);
  assert.deepEqual(r.lit, []);
  const pre = q(shell, "pre");
  delta(r, "```\n\nAfter the code, with enough words to settle it.", first.length, "b1");
  r.paintLive(shell);
  assert.equal(q(shell, "pre"), pre);
  assert.equal(r.lit.length, 1);
  assert.equal(q(pre, "code").textContent, "const a = \"x\"; // note");
  assert.ok(qa(pre, ".tk-k").length >= 1 && qa(pre, ".tk-s").length === 1 && qa(pre, ".tk-c").length === 1);
});

test("activity helpers: durations, summaries of real tool blocks only, label parts", () => {
  assert.equal(A.durationText(400), "");
  assert.equal(A.durationText(1400), "1.4 s");
  assert.equal(A.durationText(12000), "12 s");
  assert.equal(A.durationText(65000), "1 min 5 s");
  assert.equal(A.summary([{type: "text"}]), "");
  assert.equal(A.summary([{type: "tool_use", status: "ok"}, {type: "tool_use", status: "error"}, {type: "thinking"}]), "2 tool calls, 1 failed");
  assert.deepEqual(A.parts("Still working, no output for 25 s"), {text: "Still working, no output", clock: "for 25 s"});
  assert.deepEqual(A.parts("Reading src/x.py"), {text: "Reading src/x.py", clock: ""});
});

test("no percentage or invented count ever reaches the reply: a running turn with tools shows only what the blocks say", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "tool_use", kind: "read", name: "Read"}, "b1");
  const shell = r.shell();
  r.paintLive(shell);
  assert.ok(!/%/.test(shell.textContent));
  assert.ok(!/step \d|of \d/.test(shell.textContent));
});

test("a 4,000-piece reply of 200 KB: the shell is painted per piece without recreating the tool node or any settled paragraph", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  r.wire("block.start", {type: "tool_use", kind: "read", name: "Read"}, "b1");
  r.wire("block.end", {status: "ok"}, "b1");
  r.wire("block.start", {type: "text"}, "b2");
  const shell = r.shell();
  r.paintLive(shell);
  const tool = q(shell, '[data-block="b1"]');
  const para = "Paragraph of words that keeps going on and on for a while. ";
  let off = 0;
  const kept = new Map();
  let churn = 0;
  for (let i = 0; i < 4000; i += 1) {
    const piece = i % 80 === 79 ? "\n\n" : para.slice(0, 50);
    delta(r, piece, off);
    off += piece.length;
    const before = r.doc.elements;
    r.paintLive(shell);
    churn = Math.max(churn, r.doc.elements - before);
    qa(shell, ".cmd > p").slice(0, -1).forEach((n, k) => { if (!kept.has(k)) kept.set(k, n); else assert.equal(kept.get(k), n); });
  }
  assert.equal(q(shell, '[data-block="b1"]'), tool);
  assert.ok(off > 150000);
  assert.ok(churn <= 6, "a piece creates at most a few elements: " + churn);
});

/* ---------------------------------------------------------------- STR-11: Stop, Retry, honest labels */
const reply = (over) => Object.assign({id: 9, role: "agent", kind: "text", turn: 7, attempt: 1, ordered: true, state: "ok", text: "Partial words.", blocks: [{type: "text", kind: "other", text: "Partial words."}]}, over || {});
const noteRow = {id: 10, role: "agent", kind: "note", turn: 7, attempt: 1, text: "Stopped. What was written is kept."};
const errorRow = {id: 10, role: "agent", kind: "error", turn: 7, attempt: 1, text: "Claude failed.", state: "error"};

test("a reply that was stopped (a note follows it) is stopped, and offers Retry only when the page says it may", () => {
  const r = rig();
  const shell = r.shell(7, 1);
  const yes = LV.plan([reply(), noteRow], {turn: null}, {canRetry: () => true}).models["turn:7:1"];
  assert.equal(yes.state, "stopped");
  LV.paint(shell, yes, r.deps());
  const retry = q(shell, '.cl-actions [data-act="retry-direct"]');
  assert.ok(retry);
  assert.equal(retry.getAttribute("data-turn"), "7");
  assert.equal(retry.getAttribute("aria-label"), "Ask again");
  assert.ok(q(shell, '.cl-actions [data-act="copy-reply"]'), "Copy stays");
  const no = LV.plan([reply(), noteRow], {turn: null}, {canRetry: () => false}).models["turn:7:1"];
  const other = r.shell(7, 1);
  LV.paint(other, no, r.deps());
  assert.equal(q(other, '[data-act="retry-direct"]'), null);
});

test("a failed reply that has its own error line leaves Retry to that line; a failed turn whose error row IS the reply item has it in the reply", () => {
  const r = rig();
  const withLine = LV.plan([reply(), errorRow], {turn: null}, {canRetry: () => true}).models["turn:7:1"];
  assert.equal(withLine.state, "error");
  assert.equal(withLine.siblingError, true);
  const a = r.shell(7, 1);
  LV.paint(a, withLine, r.deps());
  assert.equal(q(a, '[data-act="retry-direct"]'), null);
  const primary = {id: 9, role: "agent", kind: "error", turn: 7, attempt: 1, ordered: true, state: "error", text: "Claude did not answer.", blocks: [{type: "tool_use", kind: "read", name: "Read", text: "Reading a"}]};
  const b = r.shell(7, 1);
  LV.paint(b, LV.plan([primary], {turn: null}, {canRetry: () => true}).models["turn:7:1"], r.deps());
  assert.ok(q(b, '[data-act="retry-direct"]'));
  assert.match(q(b, ".cl-ending").textContent, /did not answer/);
});

test("Retry says first that the try may have changed files when it ran an edit or a command", () => {
  const r = rig();
  const edit = reply({blocks: [{type: "tool_use", kind: "edit", name: "Edit", text: "Editing a.py"}, {type: "tool_result", kind: "edit", name: "Edit", text: ""}, {type: "text", kind: "other", text: "Partial words."}]});
  const shell = r.shell(7, 1);
  LV.paint(shell, LV.plan([edit, noteRow], {turn: null}, {canRetry: () => true}).models["turn:7:1"], r.deps());
  assert.match(q(shell, ".cl-note").textContent, /may have changed files. Trying again can repeat that/);
  assert.equal(shell.getAttribute("data-note"), "1");
  const read = reply({blocks: [{type: "tool_use", kind: "read", name: "Read", text: "Reading a"}, {type: "text", kind: "other", text: "Partial words."}]});
  const clean = r.shell(7, 1);
  LV.paint(clean, LV.plan([read, noteRow], {turn: null}, {canRetry: () => true}).models["turn:7:1"], r.deps());
  assert.equal(q(clean, ".cl-note").hidden, true);
});

test("stalled: the note under a running reply carries the real silence and the real idle limit, and says nothing about a limit the server did not send", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude", idle_limit_s: 120});
  r.now += 5000;
  r.wire("heartbeat", {idle_ms: 22000, idle_limit_s: 120});
  const shell = r.shell();
  r.now += 3000;
  r.paintLive(shell);
  assert.equal(q(shell, ".cl-state").textContent, "Still working, no output");
  assert.equal(q(shell, ".cl-clock").textContent, "for 25 s");
  assert.match(q(shell, ".cl-note").textContent, /stopped after 120 s without output/);
  const r2 = rig();
  r2.begin();
  r2.wire("turn.started", {provider: "claude"});
  r2.wire("heartbeat", {idle_ms: 30000, idle_limit_s: null});
  const s2 = r2.shell();
  r2.paintLive(s2);
  assert.equal(q(s2, ".cl-note").hidden, true);
});

test("the Stop button is named for a screen reader and is a real button that a keyboard can press", () => {
  const r = rig();
  r.begin();
  r.wire("turn.started", {provider: "claude"});
  const shell = r.shell();
  r.paintLive(shell);
  const stop = q(shell, '[data-act="composer-stop"]');
  assert.equal(stop.tagName, "BUTTON");
  assert.equal(stop.getAttribute("type"), "button");
  assert.equal(stop.getAttribute("aria-label"), "Stop the answer");
  r.act({type: "stop.pressed"});
  r.paintLive(shell);
  assert.equal(q(shell, '[data-act="composer-stop"]').getAttribute("aria-label"), "Stopping the answer");
});

test("supersede: every row of an earlier try of an owner line that has a later try is marked, the newest try and other lines are not, and an unchanged list is the same list", () => {
  const rows = [{id: 1, role: "user", kind: "text"}, {id: 2, role: "agent", kind: "text", turn: 1, attempt: 1}, {id: 3, role: "agent", kind: "note", turn: 1, attempt: 1},
    {id: 4, role: "agent", kind: "text", turn: 1, attempt: 2}, {id: 5, role: "agent", kind: "text", turn: 9}];
  const out = LV.supersede(rows);
  assert.deepEqual(out.map(m => m.superseded === true), [false, true, true, false, false]);
  assert.equal(out[0], rows[0]);
  assert.equal(rows[1].superseded, undefined, "the row that came in is not changed");
  const same = [{id: 2, role: "agent", kind: "text", turn: 1, attempt: 1}];
  assert.equal(LV.supersede(same), same);
  assert.deepEqual(LV.supersede(null), []);
});

test("a switch note stored with a reply does not make it a stopped reply (no Retry on a reply that answered)", () => {
  const switched = {id: 10, role: "agent", kind: "note", turn: 7, attempt: 1, text: "Switched Codex to Claude; carried 1 message"};
  const model = LV.plan([reply(), switched], {turn: null}, {canRetry: () => true}).models["turn:7:1"];
  assert.equal(model.state, "ok");
  const r = rig();
  const shell = r.shell(7, 1);
  LV.paint(shell, model, r.deps());
  assert.equal(q(shell, '[data-act="retry-direct"]'), null);
  assert.ok(q(shell, '[data-act="copy-reply"]'));
  const empty = {id: 9, role: "agent", kind: "note", turn: 7, attempt: 1, ordered: true, text: "Stopped before the model wrote anything.", blocks: [{type: "tool_use", kind: "read", name: "Read", text: "Reading a"}]};
  assert.equal(LV.plan([empty], {turn: null}, {canRetry: () => true}).models["turn:7:1"].state, "stopped");
});

test("the reply is signed as the page signs the stored one (Sutra), and the provider and model are said as what they are: via Claude sonnet, while it runs", () => {
  const r = rig();
  r.begin();
  r.wire("turn.connecting", {provider: "claude", model: "sonnet"});
  const shell = r.shell();
  LV.paint(shell, LV.fromLive(r.view(), {who: "Sutra"}), r.deps());
  assert.equal(q(shell, ".cl-who").textContent, "Sutra \u00b7 via Claude sonnet");
  const stored = LV.plan([reply()], {turn: null}, {whoOf: () => "Sutra"}).models["turn:7:1"];
  const done = r.shell(7, 1);
  LV.paint(done, stored, r.deps());
  assert.equal(q(done, ".cl-who").textContent, "Sutra");
});
