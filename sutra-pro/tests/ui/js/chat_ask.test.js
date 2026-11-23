"use strict";
// Ask (DV-1, flag SUTRA_ASK_V1), the page's side: the Ask | Do switch of the composer, the card of sources, and "Turn this into work".
// Three things are held here. (1) Without the flag nothing changes: the bar, the state, the payloads and the transcript are what they were, byte for byte. (2) With it, Ask sends the
// same POST /direct with `mode: "ask"` (and Retry of an Ask asks again), is never remembered as the toggle's mode, and "Turn this into work" only DRAFTS: it returns text for the box
// and posts nothing. (3) The card says what code decided, plainly, for every case: some sources checked, none given, all wrong. Words from the wire are escaped.
// Run with: node --test tests/ui/js/chat_ask.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const ChatComposer = require(path.join(JS, "chat_composer.js"));
const ChatView = require(path.join(JS, "chat_view.js"));
globalThis.ChatFold = require(path.join(JS, "chat_fold.js"));
const {create, bar, button, fillBox, MAX_MESSAGE} = ChatComposer;

const SID = "cs_000000000abc";
const DIRECT = "/api/chats/" + SID + "/direct";
const RETRY = DIRECT + "/retry";

// ---- a controller with a recording api and a recording mode store (to see that Ask never touches the remembered toggle) -------------------------------------------------------------
function rig(over) {
  const calls = [];
  const saved = [];
  const api = {calls, post: async (p, body) => { calls.push({p, body}); if (p === DIRECT || p === RETRY) return {message_id: 7, turn: "started"}; throw Object.assign(new Error("no route"), {status: 404}); }, get: async () => ({})};
  const modes = {loadMode: () => "", saveMode: (sid, mode) => saved.push(mode)};
  let changes = 0;
  const c = create(Object.assign({api, sid: SID, mode: "team", modes, onChange: () => { changes += 1; }}, over || {}));
  return {c, api, calls, saved, changes: () => changes};
}
const posts = r => r.calls.filter(x => x.p === DIRECT || x.p === RETRY);

// ---- the flag off: nothing changes -------------------------------------------------------------------------------------------------------------------------------------------------------
test("without Ask the state has the keys it always had, and the bar and the Send button are what they were", () => {
  const r = rig();
  assert.deepEqual(Object.keys(r.c.state()), ["files", "note", "mode", "turn"]);
  assert.equal(r.c.state().ask, "do");                                                    // readable, but not a key of the state
  const before = bar(r.c.state(), {labels: {team: "Tell the team", direct: "Ask the model"}});
  assert.equal(bar(r.c.state(), {labels: {team: "Tell the team", direct: "Ask the model"}, ask: false}), before);
  assert.doesNotMatch(before, /composer-ask|ccask|ccasknote/);
  assert.match(before, /data-act="composer-mode" data-mode="team"/);
  assert.deepEqual(button(r.c.state(), "x"), {label: "Send", act: "send", disabled: false});
  assert.equal(JSON.stringify(r.c.state()), JSON.stringify({files: [], note: "", mode: "team", turn: {active: false, stopping: false, text: "", messageId: null}}));
});

test("without Ask a page that asks for the switch still gets none: setAsk does nothing until the page enables it", async () => {
  const r = rig({mode: "direct"});
  assert.equal(r.c.setAsk("ask"), false);
  assert.equal(r.c.state().ask, "do");
  assert.doesNotMatch(bar(r.c.state(), {ask: false}), /composer-ask/);
  await r.c.send("hello");
  assert.deepEqual(posts(r)[0].body, {text: "hello"});                                    // no `mode` key at all
});

test("a send in Do, with Ask available, is exactly what it always was: no mode in the body (plain and live)", async () => {
  for (const live of [false, true]) {
    const r = rig({mode: "direct", live, timers: {set: () => 1, clear: () => {}, setInterval: () => 1, clearInterval: () => {}}, newId: () => "client-0001", now: () => 1000});
    r.c.enableAsk(true);
    await r.c.send("hello");
    assert.deepEqual(posts(r)[0].body, live ? {text: "hello", client_id: "client-0001"} : {text: "hello"}, "live " + live);
    r.c.close();
  }
});

// ---- the switch -------------------------------------------------------------------------------------------------------------------------------------------------------------------------
test("with Ask available the bar has an Ask | Do switch in front, Do selected, and the toggle as before", () => {
  const r = rig();
  r.c.enableAsk(true);
  const html = bar(r.c.state(), {labels: {team: "Tell the team", direct: "Ask the model"}, ask: true});
  assert.match(html, /^<div class="ccmode ccask" role="group" aria-label="What this message does">/);
  assert.match(html, /<button type="button" class="ccmode-opt" data-act="composer-ask" data-ask="ask" aria-pressed="false" title="[^"]*changes nothing[^"]*">Ask<\/button>/);
  assert.match(html, /<button type="button" class="ccmode-opt on" data-act="composer-ask" data-ask="do" aria-pressed="true" title="[^"]*">Do<\/button>/);
  assert.match(html, /data-act="composer-mode" data-mode="team"/);                        // the team / model toggle is still there in Do
  assert.doesNotMatch(html, /ccasknote/);
});

test("Ask selected: the box asks the model whatever the toggle said, the toggle is hidden, a plain note says what Ask does, and Send reads Ask", () => {
  const r = rig({mode: "team"});
  r.c.enableAsk(true);
  assert.equal(r.c.setAsk("ask"), true);
  assert.equal(r.c.state().ask, "ask");
  assert.equal(r.c.state().mode, "direct");
  const html = bar(r.c.state(), {ask: true});
  assert.match(html, /data-ask="ask" aria-pressed="true"/);
  assert.match(html, /<button type="button" class="ccmode-opt on" data-act="composer-ask" data-ask="ask"/);
  assert.doesNotMatch(html, /data-act="composer-mode"/);                                    // no team toggle while asking
  assert.match(html, /<p class="ccnote ccasknote">Ask only reads your folder and changes nothing\. Sutra checks every source the answer names\.<\/p>/);
  assert.match(html, /data-act="composer-attach"/);                                         // a model is asked: files can go along
  assert.deepEqual(button(r.c.state(), "x"), {label: "Ask", act: "send", disabled: false});
  assert.deepEqual(button({...r.c.state(), turn: {active: true, stopping: false, text: "", messageId: 1}, mode: "direct", ask: "ask"}, "x"), {label: "Stop", act: "composer-stop", disabled: false});
});

test("back to Do restores the toggle where it was, and Ask never wrote the remembered mode", () => {
  const r = rig({mode: "team"});
  r.c.enableAsk(true);
  r.c.setAsk("ask");
  r.c.setAsk("do");
  assert.equal(r.c.state().ask, "do");
  assert.equal(r.c.state().mode, "team");
  assert.deepEqual(r.saved, []);                                                            // the store saw nothing: a reload comes back in Do, on the team's toggle
  r.c.setMode("direct");                                                                    // the toggle's own memory still works
  r.c.setAsk("ask");
  r.c.setAsk("do");
  assert.equal(r.c.state().mode, "direct");
  assert.deepEqual(r.saved, ["direct"]);
});

test("the page taking Ask away (the server no longer has it) puts a chat that was asking back in Do", () => {
  const r = rig({mode: "team"});
  r.c.enableAsk(true);
  r.c.setAsk("ask");
  r.c.enableAsk(false);
  assert.deepEqual([r.c.state().ask, r.c.state().mode], ["do", "team"]);
  assert.equal(r.c.setAsk("ask"), false);
  assert.doesNotMatch(bar(r.c.state(), {ask: false}), /composer-ask/);
});

test("setting the mode by program while asking leaves Ask (the owner chose the other route)", () => {
  const r = rig({mode: "team"});
  r.c.enableAsk(true);
  r.c.setAsk("ask");
  r.c.setMode("team");
  assert.deepEqual([r.c.state().ask, r.c.state().mode], ["do", "team"]);
});

// ---- the send and the retry --------------------------------------------------------------------------------------------------------------------------------------------------------
test("an Ask posts to /direct with mode ask (plain turn), and the files and names still go along", async () => {
  const r = rig({mode: "team", readFile: async () => "aGVsbG8="});
  r.api.post = async (p, body) => { r.calls.push({p, body}); if (p === DIRECT) return {message_id: 7, turn: "started"}; return {id: "a".repeat(64), kind: "text", size: 5}; };
  r.c.enableAsk(true);
  r.c.setAsk("ask");
  await r.c.addFiles([{name: "a.txt", size: 5}]);
  const out = await r.c.send("  what does it print?  ");
  assert.deepEqual(out, {ok: true, message_id: 7});
  assert.deepEqual(r.calls[r.calls.length - 1], {p: DIRECT, body: {text: "what does it print?", attachments: ["a".repeat(64)], names: ["a.txt"], mode: "ask"}});
});

function liveRig(over) {
  let n = 0;
  return rig(Object.assign({mode: "team", live: true, timers: {set: () => 1, clear: () => {}, setInterval: () => 1, clearInterval: () => {}}, now: () => 1000, newId: () => "client-" + String(++n).padStart(4, "0")}, over || {}));
}

test("an Ask on the live route carries mode ask beside the client id", async () => {
  const r = liveRig();
  r.c.enableAsk(true);
  r.c.setAsk("ask");
  await r.c.send("what does it print?");
  assert.deepEqual(posts(r)[0].body, {text: "what does it print?", client_id: "client-0001", mode: "ask"});
  r.c.close();
});

// a live turn ended the way the server ends it: the terminal frame, then the stored reply on the page (so the next Retry is allowed)
function endLive(r, line, reply) {
  let seq = 0;
  const wire = (type, payload) => { seq += 1; r.c.frame({v: 1, id: "g1:" + seq, conversation_id: SID, message_id: line, generation_id: "g1", attempt: 1, seq, ts: "t", type, payload}); };
  wire("turn.accepted", {client_id: "client-0001", attempt_no: 1});
  wire("turn.done", {message_id_reply: reply, attempt_no: 1, stored_order: []});
  assert.equal(r.c.reconcile([{id: reply, role: "agent", kind: "text", turn: line, attempt: 1}]), true);
}

test("Retry of a line this page sent as an Ask asks again, even after the switch went back to Do; a Do line is retried as a Do", async () => {
  const r = liveRig();
  r.api.post = async (p, body) => { r.calls.push({p, body}); return p === DIRECT ? {message_id: 7, turn: "started", generation_id: "g1", attempt_no: 1} : {message_id: body.message_id, turn: "started", generation_id: "g2", attempt_no: 2}; };
  r.c.enableAsk(true);
  r.c.setAsk("ask");
  await r.c.send("an ask");
  endLive(r, 7, 8);
  r.c.setAsk("do");
  r.c.setMode("direct");
  await r.c.retry(7, "an ask");
  assert.deepEqual(r.calls[r.calls.length - 1], {p: RETRY, body: {message_id: 7, client_id: "client-0002", mode: "ask"}});
  r.c.close();
  const s = liveRig();
  s.api.post = async (p, body) => { s.calls.push({p, body}); return p === DIRECT ? {message_id: 9, turn: "started", generation_id: "g1", attempt_no: 1} : {message_id: body.message_id, turn: "started", generation_id: "g2", attempt_no: 2}; };
  s.c.enableAsk(true);
  s.c.setMode("direct");
  await s.c.send("a do");
  endLive(s, 9, 10);
  s.c.setAsk("ask");
  await s.c.retry(9, "a do");
  assert.deepEqual(s.calls[s.calls.length - 1], {p: RETRY, body: {message_id: 9, client_id: "client-0002"}});          // no mode: the line was a Do
  s.c.close();
});

test("Retry of a line from before a reload is told by the line's own mode, as the server stored it, whatever the switch says now", async () => {
  const fresh = async (mode, switchTo) => {
    const r = liveRig({mode: "direct"});
    r.api.post = async (p, body) => { r.calls.push({p, body}); return {message_id: body.message_id, turn: "started", generation_id: "g2", attempt_no: 2}; };
    r.c.enableAsk(true);
    if (switchTo === "ask") r.c.setAsk("ask");
    await r.c.retry(41, "from before the reload", mode === undefined ? {} : {mode});
    const body = r.calls[0].body;
    r.c.close();
    return body;
  };
  assert.deepEqual(await fresh("ask", "do"), {message_id: 41, client_id: "client-0001", mode: "ask"});         // an Ask line: asked again as an Ask even with the switch on Do
  assert.deepEqual(await fresh("do", "ask"), {message_id: 41, client_id: "client-0001"});                       // a Do line: a Do even with the switch on Ask
  assert.deepEqual(await fresh(undefined, "ask"), {message_id: 41, client_id: "client-0001", mode: "ask"});    // a server that does not say: the switch decides
  assert.deepEqual(await fresh(undefined, "do"), {message_id: 41, client_id: "client-0001"});
});

test("a plain-turn retry of an Ask resends it as an Ask", async () => {
  const r = rig({mode: "team"});
  r.c.enableAsk(true);
  r.c.setAsk("ask");
  await r.c.send("an ask");
  r.c.setAsk("do");
  r.c.state().turn = {active: false, stopping: false, text: "", messageId: null};
  await r.c.retry(7, "an ask");
  assert.deepEqual(posts(r).map(x => x.body), [{text: "an ask", mode: "ask"}, {text: "an ask", mode: "ask"}]);
});

// ---- Turn this into work: a draft, never a send -------------------------------------------------------------------------------------------------------------------------------
test("draft() leaves Ask, points Send at the team and RETURNS the text; nothing is posted", async () => {
  const r = rig({mode: "team"});
  r.c.enableAsk(true);
  r.c.setAsk("ask");
  const text = r.c.draft('Based on my question "x", please ');
  assert.equal(text, 'Based on my question "x", please ');
  assert.deepEqual([r.c.state().ask, r.c.state().mode], ["do", "team"]);
  assert.equal(r.calls.length, 0);
  assert.deepEqual(r.c.state().turn, {active: false, stopping: false, text: "", messageId: null});
});

test("a draft is cut to the longest message, counted in characters, and a non-string is empty", () => {
  const r = rig({mode: "direct"});
  r.c.enableAsk(true);
  assert.equal(Array.from(r.c.draft("é".repeat(9000))).length, MAX_MESSAGE);
  assert.equal(r.c.draft(null), "");
  assert.equal(r.c.state().mode, "team");
});

test("fillBox puts the draft in the box, the caret at its end, focuses it and says the box changed; it sends nothing", () => {
  const log = [];
  class Ev { constructor(type, init) { this.type = type; this.init = init; } }
  const had = globalThis.Event;
  globalThis.Event = Ev;
  try {
    const box = {value: "old", setSelectionRange: (a, b) => log.push(["caret", a, b]), focus: () => log.push(["focus"]), dispatchEvent: e => { log.push(["event", e.type, e.init.bubbles]); return true; }};
    assert.equal(fillBox(box, "Based on this, please "), true);
    assert.equal(box.value, "Based on this, please ");
    assert.deepEqual(log, [["caret", 22, 22], ["focus"], ["event", "input", true]]);
    assert.equal(fillBox(null, "x"), false);
    assert.equal(fillBox({value: "a"}, "still works with a bare box"), true);
  } finally {
    globalThis.Event = had;
  }
});

// ---- the card ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
const OK = {path: "src/app.py", start: 3, end: 4, label: "checked", how: "lines"};
const QUOTED = {path: "README.md", start: 2, end: 2, quote: "Second line", label: "checked", how: "quote"};
const GONE = {path: "src/gone.py", start: 1, end: 9, label: "could not find", reason: "there is no such file"};
const card = (over = {}) => Object.assign({type: "answer_sources", question: "what does it print?", sources: [OK, QUOTED, GONE], checked: 2, missing: 1, more: 0}, over);

function wellFormed(markup) {
  const stack = [];
  for (const m of markup.matchAll(/<(\/?)([A-Za-z][\w:-]*)((?:\s+[\w:.-]+="[^"<]*")*)\s*(\/?)>|<[^>]*>/g)) {
    assert.ok(m[2] !== undefined, `a malformed tag: ${m[0].slice(0, 80)}`);
    if (m[1] === "/") assert.equal(stack.pop(), m[2], `</${m[2]}> closes the wrong tag`);
    else if (m[4] !== "/") stack.push(m[2]);
  }
  assert.deepEqual(stack, [], "every tag is closed");
  assert.equal(/&(?!(?:amp|lt|gt|quot|#39);)/.test(markup), false, "a stray &");
}

test("some sources checked and one not: each is listed with the label code gave it and why, and the head counts them", () => {
  const html = ChatView.card(card());
  wellFormed(html);
  assert.match(html, /^<div class="ncard c-answer t-mixed" data-card="answer_sources" data-tone="mixed" data-checked="2" data-missing="1">/);
  assert.match(html, /<p class="ashead">2 of 3 sources checked; 1 could not be found\.<\/p>/);
  assert.match(html, /<li class="asrc st-checked" data-label="checked"><code class="aspath">src\/app\.py<\/code> <span class="asln">lines 3 to 4<\/span> <span class="aslabel">checked<\/span><small class="ashow">The file and those lines are there\.<\/small><\/li>/);
  assert.match(html, /<code class="aspath">README\.md<\/code> <span class="asln">line 2<\/span> <q class="asq">Second line<\/q> <span class="aslabel">checked<\/span><small class="ashow">The file is there and the quoted words are on those lines\.<\/small>/);
  assert.match(html, /<li class="asrc st-missing" data-label="could not find"><code class="aspath">src\/gone\.py<\/code> <span class="asln">lines 1 to 9<\/span> <span class="aslabel">could not find<\/span><small class="ashow">It could not be found: there is no such file\.<\/small><\/li>/);
  assert.match(html, /<p class="asnote">Checked means Sutra looked: the file and the lines are there, and so are the quoted words when there are any\. It does not mean the answer is right\.<\/p>/);
});

test("an answer with no source says so plainly: no sources given, nothing checked, and no list", () => {
  for (const c of [card({sources: [], checked: 0, missing: 0}), {type: "answer_sources"}, {type: "answer_sources", sources: null}]) {
    const html = ChatView.card(c);
    wellFormed(html);
    assert.match(html, /data-tone="none" data-checked="0" data-missing="0"/);
    assert.match(html, /<p class="ashead">No sources given\. Nothing in this answer points to a file, so none of it was checked\.<\/p>/);
    assert.doesNotMatch(html, /<ul|asnote|aslabel/);
    assert.match(html, /data-act="ask-to-work"/);                                           // the button is still there: the question can still become work
  }
});

test("when every source is wrong the card says none could be found and not to rely on the answer", () => {
  const html = ChatView.card(card({sources: [GONE, {...GONE, path: "b.py"}, {...GONE, path: "../x", reason: "the path goes up out of the folder"}], checked: 0, missing: 3}));
  wellFormed(html);
  assert.match(html, /data-tone="bad" data-checked="0" data-missing="3"/);
  assert.match(html, /<p class="ashead">None of the 3 sources could be found\. Do not rely on this answer until you have looked yourself\.<\/p>/);
  assert.equal((html.match(/class="aslabel">could not find</g) || []).length, 3);
  assert.doesNotMatch(html, /class="aslabel">checked</);
  assert.match(html, /It could not be found: the path goes up out of the folder\./);
  assert.match(ChatView.card(card({sources: [GONE], checked: 0, missing: 1})), /<p class="ashead">The source could not be found\./);
});

test("when every source is checked the head says so, and a single source is grammatical", () => {
  assert.match(ChatView.card(card({sources: [OK, QUOTED], checked: 2, missing: 0})), /data-tone="ok"[^>]*>.*<p class="ashead">All 2 sources were checked\.<\/p>/);
  assert.match(ChatView.card(card({sources: [OK]})), /<p class="ashead">The source was checked\.<\/p>/);
});

test("a label is checked only when the wire says exactly checked; anything else is could not find, whatever the words around it", () => {
  const html = ChatView.card(card({sources: [{...OK, label: "Checked"}, {...OK, label: "verified"}, {...OK, label: " checked "}, {...OK, label: undefined}, {...OK, label: "checked, confirmed"}], checked: 5}));
  assert.equal((html.match(/class="aslabel">could not find</g) || []).length, 4);
  assert.equal((html.match(/class="aslabel">checked</g) || []).length, 1);                // " checked " is cleaned to checked, the others are not
  assert.match(html, /data-checked="1" data-missing="4"/);
  assert.doesNotMatch(html, /verified|confirmed/);
});

test("marks past the limit are said, not hidden", () => {
  assert.match(ChatView.card(card({more: 6})), /<p class="asmore">and 6 more marks that were not checked\.<\/p>/);
  assert.doesNotMatch(ChatView.card(card({more: 0})), /asmore/);
});

test("every word from the wire is escaped and the markup stays well formed", () => {
  const evil = '<img src=x onerror=alert(1)>"&\'';
  const html = ChatView.card(card({question: evil, sources: [{path: evil, start: 1, end: 2, quote: evil, label: "could not find", reason: evil}, {...OK, path: evil}], checked: 1, missing: 1}));
  wellFormed(html);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;&quot;&amp;&#39;/);
});

test("the draft is a sentence the owner finishes: the question and up to five checked files, never a source that was not found", () => {
  assert.equal(ChatView.workDraft(card()), 'Based on my question "what does it print?" and what you found in src/app.py (lines 3 to 4), README.md (line 2), please ');
  assert.equal(ChatView.workDraft(card({sources: [GONE]})), 'Based on my question "what does it print?", please ');
  assert.equal(ChatView.workDraft(card({question: "", sources: [OK]})), "Based on what you found in src/app.py (lines 3 to 4), please ");
  assert.equal(ChatView.workDraft(card({question: "", sources: []})), "Please ");
  assert.equal(ChatView.workDraft(null), "Please ");
  const many = Array.from({length: 8}, (_, i) => ({...OK, path: "f" + i + ".py"}));
  assert.match(ChatView.workDraft(card({sources: many})), /f0\.py \(lines 3 to 4\), f1\.py .*, f4\.py \(lines 3 to 4\) and 3 more, please $/);
  assert.equal(ChatView.workDraft(card({sources: [OK, OK]})).match(/src\/app\.py/g).length, 1);              // the same source twice is named once
  const long = ChatView.workDraft(card({question: "q".repeat(900)}));
  assert.ok(long.length < 600 && long.startsWith('Based on my question "' + "q".repeat(200) + '"'));
});

test("the button carries the draft, escaped, in data-draft and is a plain button (the page puts the draft in the box; the card posts nothing)", () => {
  const html = ChatView.card(card({question: 'say "hi" <b>'}));
  wellFormed(html);
  const found = /<button type="button" class="lbtn" data-act="ask-to-work" data-draft="([^"]*)" title="[^"]*">Turn this into work<\/button>/.exec(html);
  assert.ok(found, html.slice(-300));
  assert.equal(found[1].replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&"), ChatView.workDraft(card({question: 'say "hi" <b>'})));
  assert.doesNotMatch(html, /<form|<a |href=|type="submit"/);
});

test("the transcript draws the card as a Sutra message right after the answer, and an unknown card is still plain text", () => {
  const messages = [
    {id: 1, role: "user", who: "user", kind: "text", text: "what does it print?", state: "ok"},
    {id: 2, role: "agent", who: "sutra", kind: "text", text: "It prints hello [src/app.py:4].", turn: 1, state: "ok"},
    {id: 3, role: "agent", who: "sutra", kind: "card", text: "", card: card(), turn: 1, attempt: 1, state: "ok"},
    {id: 4, role: "agent", who: "sutra", kind: "card", text: "", card: {type: "from_the_future", text: "a new card"}, state: "ok"},
  ];
  const html = ChatView.transcript({kind: "department", writable: true, status: "active"}, messages, {});
  wellFormed(html);
  const row = /<div class="nmsg sb team" data-id="3" data-who="sutra" data-kind="card" data-state="ok"><small>Sutra<\/small>(<div class="ncard c-answer[\s\S]*?)<\/div><\/div>(?=<div|$)/.exec(html);
  assert.ok(row, "the card row");
  assert.ok(html.indexOf('data-id="2"') < html.indexOf('data-id="3"'));
  assert.match(html, /<div class="ncard c-unknown" data-card="unknown">a new card<\/div>/);
});

test("other cards are drawn as they were", () => {
  const task = ChatView.card({type: "task", task_id: "tsk_b7c8d9e0f1a2", dept_id: "web", dept_name: "Web", title: "Build", status: "running"});
  assert.match(task, /^<div class="ncard ready c-task"/);
  assert.doesNotMatch(task, /answer|ask-to-work/);
});

test("say() puts a sentence in the note under the box, which the bar draws, so a draft that could not be written is not silent", () => {
  const r = rig({mode: "direct"});
  r.c.enableAsk(true);
  r.c.setAsk("ask");
  r.c.draft("Based on this, please ");                                                     // the page leaves Ask first, then finds the box closed
  r.c.say("The message box is closed right now, so the draft was not written. Try again when it opens.");
  assert.equal(r.c.state().note, "The message box is closed right now, so the draft was not written. Try again when it opens.");
  assert.match(bar(r.c.state(), {ask: true}), /<p class="ccnote" role="status">The message box is closed right now, so the draft was not written\. Try again when it opens\.<\/p>/);
  assert.equal(r.calls.length, 0);                                                          // and nothing was posted
  r.c.say("");
  assert.equal(r.c.state().note, "");
});

test("without Ask the team bar never draws a note, as it never did", () => {
  const r = rig({mode: "team"});
  r.c.say("a note");
  assert.doesNotMatch(bar(r.c.state(), {labels: {team: "Tell the team", direct: "Ask the model"}}), /ccnote/);
  assert.doesNotMatch(bar(r.c.state(), {ask: false}), /ccnote/);
});


test("a turn that tried to change something or reach the web says so on the card, plainly, and a turn that did not says nothing", () => {
  assert.doesNotMatch(ChatView.card(card()), /asrefused|tried/);
  assert.doesNotMatch(ChatView.card(card({tried: 0})), /asrefused/);
  const one = ChatView.card(card({tried: 1}));
  wellFormed(one);
  assert.match(one, /<p class="asnote asrefused">This answer also tried one action that changes something or reaches the web\. Ask does not allow that\.<\/p>/);
  assert.match(ChatView.card(card({tried: 3})), /also tried 3 actions that change something or reach the web\./);
  assert.match(ChatView.card(card({sources: [], checked: 0, missing: 0, tried: 2})), /asrefused/);          // also on an answer that named no source
});
