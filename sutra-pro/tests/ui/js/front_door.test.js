"use strict";
// FrontDoor (sutra_app/ui/static/js/front_door.js): Home's front door. What needs the owner first (one card per question, approval and problem),
// then In progress and Done recently, and what each level adds.
// Run with: node --test tests/ui/js/front_door.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const FD = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/front_door.js"));

const tid = n => "tsk_" + String(n).padStart(12, "0");
const dept = (id, status, extra = {}) => Object.assign({id, name: id[0].toUpperCase() + id.slice(1), purpose: "Make " + id, node_status: status, session_id: "cs_" + id}, extra);
const question = (id, extra = {}) => Object.assign({message_id: id, session_id: "cs_web", kind: "question", dept_id: "web", dept_name: "Web",
  text: "@Requester Which colours?", options: [], asked_at: "2026-11-12T10:00:00Z", waiting_s: 300, stale: false}, extra);
const approval = (id, extra = {}) => Object.assign({message_id: id, session_id: "cs_org", kind: "approval", dept_id: null, dept_name: "",
  text: "Add a Design team?", options: ["Yes", "No"], asked_at: "2026-11-12T10:00:00Z", waiting_s: 30}, extra);
const head = (n, kind, extra = {}) => Object.assign({kind, tone: kind === "problem" ? "err" : "ok", task_id: tid(n), dept_id: "web", dept_name: "Web",
  title: "Menu page", text: "Web: row " + n, outcome: kind === "problem" ? "The model stopped" : "", since_s: 600, retry: kind === "problem"}, extra);

test("the levels are simple, manager and debug, in that order", () => {
  assert.deepEqual(FD.LEVELS, ["simple", "manager", "debug"]);
  assert.equal(FD.levelAt("debug", "manager"), true);
  assert.equal(FD.levelAt("simple", "manager"), false);
});

test("buckets: working, waiting and a problem are in progress; done states and finished work are done; the rest is idle, each team once", () => {
  const b = FD.buckets([dept("web", "running"), dept("ads", "waiting_on_you"), dept("ops", "fault"), dept("docs", "filed"), dept("hr", "idle"), dept("pr", "not_made"),
    dept("art", "idle")], [head(1, "finished", {dept_id: "art", dept_name: "Art", title: "Logo"})], {});
  assert.deepEqual(b.running.map(r => r.id), ["web", "ads", "ops"]);
  assert.deepEqual(b.done.map(r => [r.id, r.work || ""]), [["art", "Logo"], ["docs", ""]]);
  assert.deepEqual(b.idle.map(r => r.id), ["hr", "pr"]);
  assert.equal(b.running[1].words, "waiting on you");
});

test("buckets: a team at work again is only in progress, not also done under an older finished run", () => {
  const b = FD.buckets([dept("web", "waiting_on_you")], [head(1, "finished", {dept_id: "web", dept_name: "Web", title: "Site v1"})], {});
  assert.deepEqual(b.running.map(r => r.id), ["web"]);
  assert.deepEqual(b.done, []);
});

test("a question card: the team, how long it waited, the ask, a box and Send, and Open to the team page", () => {
  const html = FD.needCard(question(7), {elapsedMs: 0});
  assert.match(html, /class="fdcard fdask" data-msg="7" data-kind="question" data-dept="web"/);
  assert.match(html, /<span class="fdwho">Web<\/span>/);
  assert.match(html, /waiting 5 minutes/);
  assert.match(html, /<p class="fdq">Which colours\?<\/p>/);                       // the @tag is gone
  assert.match(html, /<textarea class="fdbox"[^>]*data-msg="7"/);
  assert.match(html, /data-act="fd-answer" data-msg="7"/);
  assert.match(html, /<a class="fdopen" href="\/d\/web\/\?view=simple">Open Web<\/a>/);
});

test("a question with options is answered by its buttons, and a long option reads as the choice and what it means", () => {
  const html = FD.needCard(question(8, {text: "Keep going or finish?\n   Option 1: Keep going: more parts\n   Option 2: Finish as it is",
    options: ["Keep going: more parts", "Finish as it is"]}), {});
  assert.match(html, /data-act="fd-option" data-msg="8" data-opt="1" data-text="Keep going: more parts"><b>Keep going<\/b><span class="fdoptwhy">more parts<\/span>/);
  assert.match(html, /data-opt="2" data-text="Finish as it is">Finish as it is<\/button>/);
  assert.doesNotMatch(html, /fd-answer/);
});

test("'send these: a; b; c' becomes three numbered questions under the lead-in", () => {
  const html = FD.needCard(question(9, {text: "@Requester Before we start.\nPlease send these: Your name; Your city; Your colours"}), {});
  assert.match(html, /<p class="fdsay">Before we start\.<\/p><p class="fdsay">Please send these:<\/p><ol class="fdqs"><li>Your name<\/li><li>Your city<\/li><li>Your colours<\/li><\/ol>/);
});

test("an approval card has Approve and Not now, carrying the card's own labels, and no team link", () => {
  const html = FD.needCard(approval(11), {});
  assert.match(html, /data-kind="approval"/);
  assert.match(html, /data-act="fd-approve" data-msg="11" data-text="Yes">Approve</);
  assert.match(html, /data-act="fd-decline" data-msg="11" data-text="No">Not now</);
  assert.doesNotMatch(html, /fdopen/);
});

test("a card being answered is disabled, and a refusal shows on its own card", () => {
  const html = FD.needCard(question(7), {busy: true, error: "This team is busy"});
  assert.match(html, /<p class="fderr" role="alert">This team is busy<\/p>/);
  assert.equal((html.match(/ disabled/g) || []).length, 2);
});

test("every word from the wire is escaped", () => {
  const html = FD.needCard(question(7, {dept_name: "<b>x</b>", text: "<img src=x onerror=1>?"}), {}) + FD.listsHtml({departments: [dept("web", "running", {name: "<i>W</i>"})]});
  assert.doesNotMatch(html, /<b>x|<img|<i>W/);
  assert.match(html, /&lt;img src=x onerror=1&gt;\?/);
});

test("a problem card: Try again, Open the team, Got it; a problem marked Got it is gone", () => {
  const html = FD.problemCard(head(3, "problem"));
  assert.match(html, /data-act="fd-retry" data-task="tsk_000000000003">Try again/);
  assert.match(html, /href="\/d\/web\/\?view=simple">Open Web/);
  assert.match(html, /data-act="fd-seen"/);
  const seen = {[tid(3)]: true};
  assert.doesNotMatch(FD.needsHtml({loaded: true, needs: [], heads: [head(3, "problem")], seen, departments: []}), /fdprob/);
});

test("Needs you: questions and approvals first, then problems; the count says how many", () => {
  const html = FD.needsHtml({loaded: true, needs: [question(7), approval(11)], heads: [head(3, "problem"), head(4, "quiet")], seen: {}, departments: []});
  assert.match(html, /Needs you <span class="fdcount">3<\/span>/);
  const order = [...html.matchAll(/data-kind="(\w+)"/g)].map(m => m[1]);
  assert.deepEqual(order, ["question", "approval", "problem"]);
  assert.equal(FD.summary({needs: [question(7)], heads: [], seen: {}}), "1 thing needs you");
});

test("nothing waits: a calm line with what is running; before the first read it says it is looking", () => {
  assert.match(FD.needsHtml({loaded: false}), /Looking/);
  const calm = FD.needsHtml({loaded: true, needs: [], heads: [], departments: [dept("web", "running"), dept("ads", "running")]});
  assert.match(calm, /Nothing needs you right now/);
  assert.match(calm, /2 teams are working: Web, Ads\./);
  assert.match(FD.needsHtml({loaded: true, needs: [], heads: [], departments: []}), /Nothing is running\./);
});

test("In progress and Done recently link each team to its page; Manager adds a Chat button per team; idle teams are folded away", () => {
  const state = {departments: [dept("web", "running"), dept("docs", "filed"), dept("hr", "idle")], heads: []};
  const simple = FD.listsHtml(Object.assign({level: "simple"}, state));
  assert.match(simple, /In progress[\s\S]*href="\/d\/web\/\?view=simple"/);
  assert.match(simple, /Done recently[\s\S]*href="\/d\/docs\/\?view=simple"/);
  assert.match(simple, /<details class="fdidle" data-key="fd-idle"><summary>Other teams \(1\)/);
  assert.doesNotMatch(simple, /fd-chat/);
  assert.match(FD.listsHtml(Object.assign({level: "manager"}, state)), /data-act="fd-chat" data-node="web"/);
});

test("Done recently shows five, then a button for the rest", () => {
  const many = Array.from({length: 7}, (_, i) => dept("t" + i, "filed"));
  const html = FD.listsHtml({level: "simple", departments: many, heads: []});
  assert.equal((html.match(/st-filed/g) || []).length, 5);
  assert.match(html, /data-act="fd-more">2 more/);
  assert.equal((FD.listsHtml({level: "simple", departments: many, heads: [], moreDone: true}).match(/st-filed/g) || []).length, 7);
});

test("what each level adds: nothing at Simple; org chart, graph, team chats at Manager; settings, usage and log and the Raw AI chat hook at Debug", () => {
  assert.equal(FD.navHtml("simple"), "");
  const manager = FD.navHtml("manager");
  assert.deepEqual([...manager.matchAll(/data-pane="(\w+)"/g)].map(m => m[1]), ["chart", "graph", "chat"]);
  assert.doesNotMatch(manager, /console|raw-ai-chat|settings/);
  const debug = FD.navHtml("debug");
  assert.deepEqual([...debug.matchAll(/data-pane="(\w+)"/g)].map(m => m[1]), ["chart", "graph", "chat", "settings"]);
  assert.match(debug, /href="\/console">Usage and log/);
  assert.match(debug, /data-act="fd-hook" data-hook="raw-ai-chat"/);
});

test("Debug only: the whole Heads up lane, quiet teams and finished work included", () => {
  const heads = [head(1, "problem"), head(2, "quiet"), head(3, "finished"), head(4, "finished"), head(5, "finished"), head(6, "finished")];
  assert.equal(FD.debugHtml({level: "manager", heads}), "");
  const html = FD.debugHtml({level: "debug", heads, seen: {}});
  assert.equal((html.match(/class="huitem/g) || []).length, 6);                    // every row, no "+N more"
  assert.match(FD.debugHtml({level: "debug", heads: []}), /No crashed work/);
});

test("after a send here: Sutra's reply to the last line, the team that took it, and a choice it waits on", () => {
  const messages = [
    {id: 1, role: "user", text: "old"}, {id: 2, role: "agent", text: "old answer"},
    {id: 3, role: "user", text: "A flyer"}, {id: 4, role: "agent", text: "@Requester I gave this to the Web team."},
    {id: 5, role: "agent", text: "", card: {type: "task", dept_id: "web", dept_name: "Web", title: "A flyer"}},
    {id: 6, role: "agent", text: "", card: {type: "choice", question: "Which team?", options: [{id: "web", label: "Web"}, {id: "none", label: "A new team"}]}},
  ];
  assert.equal(FD.latestHtml({show: false, messages}), "");
  const html = FD.latestHtml({show: true, messages, status: "Planning…"});
  assert.doesNotMatch(html, /old answer/);
  assert.match(html, /<p class="fdphase">Planning…<\/p>/);
  assert.match(html, /I gave this to the Web team\./);
  assert.match(html, /<a class="fdopen" href="\/d\/web\/\?view=simple">Web<\/a> is on it: A flyer/);
  assert.match(html, /data-act="fd-choose" data-msg="6" data-option="none" data-text="A new team"/);
  assert.match(html, /data-act="fd-conversation"/);
  assert.doesNotMatch(FD.latestHtml({show: true, messages, answers: {6: "Web"}}), /fd-choose/);       // a pressed choice is not offered again
});
