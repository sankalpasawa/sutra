"use strict";
// ChatView's done card offers Try again exactly while the Heads up lane does (gap package attention): opts.retryTasks names the tasks, the
// button carries data-act="retry-task" and the task id, and a card without it is byte for byte what it was.
// Run with: node --test tests/ui/js/chat_view_retry.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ChatView = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_view.js"));

const TASK = "tsk_b7c8d9e0f1a2";
const ORG = {id: "cs_org", node_id: "root", kind: "org", title: "Sutra", writable: true, status: "active"};
const doneMsg = (over = {}) => ({id: 41, session_id: "cs_org", role: "agent", who: "sutra", kind: "card", text: "", state: "ok", at: "2026-11-04T10:00:00Z",
  card: Object.assign({type: "done", task_id: TASK, dept_id: "web", dept_name: "Web", title: "Landing page", status: "crashed", outcome: "The team stopped unexpectedly."}, over)});

test("a crashed task's card has Try again while the lane offers it, and none otherwise", () => {
  const offered = ChatView.transcript(ORG, [doneMsg()], {retryTasks: {[TASK]: true}});
  assert.match(offered, /<button type="button" class="lbtn" data-act="retry-task" data-task="tsk_b7c8d9e0f1a2">Try again<\/button>/);
  assert.match(offered, /data-act="retry-task"[^>]*>Try again<\/button><a class="lbtn" data-act="open-team"/);       // beside Open the team
  const plain = ChatView.transcript(ORG, [doneMsg()], {});
  assert.doesNotMatch(plain, /retry-task/);
  assert.equal(ChatView.transcript(ORG, [doneMsg()], {retryTasks: {}}), plain);
  assert.equal(ChatView.transcript(ORG, [doneMsg()], {retryTasks: {tsk_000000000000: true}}), plain);       // another task's offer
  assert.equal(ChatView.transcript(ORG, [doneMsg()], {retryTasks: "yes"}), plain);
});

test("the card alone (no context) is unchanged, and a task id that is not one never gets a button", () => {
  const c = doneMsg().card;
  assert.doesNotMatch(ChatView.card(c), /retry-task/);
  assert.match(ChatView.card(c, {retry: true}), /data-act="retry-task" data-task="tsk_b7c8d9e0f1a2">Try again</);
  const bad = Object.assign({}, c, {task_id: '"><img src=x onerror=1>'});
  assert.doesNotMatch(ChatView.card(bad, {retry: true}), /retry-task|<img/);
});

test("other cards ignore the offer", () => {
  const task = {id: 42, session_id: "cs_org", role: "agent", who: "sutra", kind: "card", text: "", state: "ok", at: "2026-11-04T10:00:00Z",
    card: {type: "task", task_id: TASK, dept_id: "web", dept_name: "Web", title: "Landing page", status: "running"}};
  assert.doesNotMatch(ChatView.transcript(ORG, [task], {retryTasks: {[TASK]: true}}), /retry-task/);
});
