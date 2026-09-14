#!/usr/bin/env node
/* test_shadow_completion_ui.js -- a finished task must SHOW what was done.
 *
 * THE GAP (founder, 2026-09-15). When a Shadow task completed, the founder
 * got a Now row reading "done - result inside" and then could not get
 * inside: shadowTaskIsActive rule 4 drops a done mission from the list, and
 * shadowSelectedTask picked its replacement from that same filtered list --
 * so the card being read was swapped out in the same tick the task
 * finished. The only rendering of a result anywhere was missionCardHtml's
 * `result_excerpt`, which is 150 characters off the head of the evidence
 * blob plus 250 off its tail.
 *
 * WHAT IS PINNED HERE:
 *   1. shadowCompletionHtml renders the server's summary and nothing else
 *   2. the card shows it, and drops the now-redundant flat "done when" row
 *   3. a record without the field renders exactly as it did before
 *   4. the task the founder is READING survives its own completion...
 *   5. ...while the LIST still drops it (rule 4 is unchanged)
 *
 * Run: node test_shadow_completion_ui.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

function fresh(){
  const ctx = {
    console, Date, setTimeout: () => ({}),
    S: {}, SCREENS: {}, TITLES: {},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    document: {
      addEventListener(){}, body: { appendChild(){} },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(
    path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8"), ctx);
  vm.runInContext(fs.readFileSync(
    path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8"), ctx);
  return ctx;
}

/* the shape mission_engine.completion_summary stamps -- kept in sync with
   test_shadow_completion_summary.py, which pins the producer */
const SUMMARY = {
  objective: "get the EMI check green",
  headline: "3 of 3 checks passed",
  checks_met: 3, checks_total: 3,
  turns_used: 5, max_turns: 20, chat: "sess-1",
  at: "2026-09-15T01:20:00Z",
  checks: [
    { check: "EMI-OK", tier: "contains_artifact", met: true,
      how: "found in the chat",
      evidence: "…the suite reports EMI-OK for every tenant…" },
    { check: "pytest test_emi.py passes", tier: "verify", met: true,
      how: "Shadow ran this check and it passed" },
    { check: "the copy reads right", tier: "founder_confirm", met: true,
      how: "you confirmed it", by: "founder",
      at: "2026-09-15T01:19:00Z" },
  ],
};

const DONE = { id: "m-done", objective: "get the EMI check green",
  template: "fix", state: "done", target_mode: "new",
  target_session: "sess-1", turns_used: 5, max_turns: 20,
  done_when: [{ tier: "contains_artifact", check: "EMI-OK" }],
  result_excerpt: '{"role": "assistant", "text": "..."} ... tail',
  completion: SUMMARY };

/* 1. the block renders every fact the server stamped, and no other */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml(DONE);
  assert(/3 of 3 checks passed/.test(h), "the headline leads");
  assert(/get the EMI check green/.test(h), "the objective is named");
  assert(/5 of 20 turns/.test(h), "the budget it spent is shown");
  SUMMARY.checks.forEach(k =>
    assert(h.indexOf(k.check) !== -1, "check missing: " + k.check));
  assert(/found in the chat/.test(h)
    && /Shadow ran this check and it passed/.test(h)
    && /you confirmed it/.test(h), "every tier says who satisfied it");
  assert(/you confirmed it · founder/.test(h),
    "a confirmation names who signed it off");
  assert(/the suite reports EMI-OK for every tenant/.test(h),
    "the artifact is quoted in the chat's own words");
  assert(/shcheckev/.test(h), "the quote has its own class");
  /* three met rows, three ticks -- a satisfied check looks satisfied */
  assert.strictEqual((h.match(/shcheckmet/g) || []).length, 3,
    "every met check draws as met");
  assert.strictEqual((h.match(/✓/g) || []).length, 3, "three ticks");
  console.log("ok 1 the summary renders");
}

/* 2. no summary -> no block. The panel must not invent one. */
{
  const ctx = fresh();
  assert.strictEqual(ctx.shadowCompletionHtml({ id: "m-1" }), "",
    "a mission without the field renders nothing");
  assert.strictEqual(ctx.shadowCompletionHtml(null), "", "null is safe");
  assert.strictEqual(
    ctx.shadowCompletionHtml({ id: "m-1", completion: null }), "",
    "an explicit null field renders nothing");
  console.log("ok 2 nothing is invented");
}

/* 3. it comes from the SERVER. Nothing here recomputes a verdict: an unmet
      row must render unmet even on a mission the server called done. */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml({ id: "m-x", completion: {
    headline: "1 of 2 checks passed", objective: "o",
    turns_used: 1, max_turns: 4,
    checks: [{ check: "found it", tier: "contains_artifact", met: true,
               how: "found in the chat" },
             { check: "not yet", tier: "verify", met: false,
               how: "still outstanding" }] } });
  assert(/1 of 2 checks passed/.test(h), "the server's count is the count");
  assert.strictEqual((h.match(/shcheckmet/g) || []).length, 1,
    "only the met row draws as met");
  assert(/still outstanding/.test(h), "the unmet row says so");
  console.log("ok 3 the verdict is the server's");
}

/* 4. the card shows it, and the flat "done when" row steps aside */
{
  const ctx = fresh();
  const card = ctx.shadowTaskCardHtml(DONE);
  assert(/3 of 3 checks passed/.test(card), "the card carries the summary");
  assert(/data-shdone="m-done"/.test(card), "the block has its own hook");
  assert(!/done when/.test(card),
    "the criteria without verdicts do not print twice");
  assert(/data-shtakeover="sess-1"/.test(card),
    "Open the chat still reaches the work");
  /* a task that has NOT finished is untouched */
  const live = Object.assign({}, DONE, { state: "running" });
  delete live.completion;
  const lh = ctx.shadowTaskCardHtml(live);
  assert(/done when/.test(lh), "a live task keeps its criteria row");
  assert(!/shdonesum/.test(lh), "and gets no completion block");
  console.log("ok 4 the card shows it, once");
}

/* 5. a mission completed BEFORE this field existed renders as it always did */
{
  const ctx = fresh();
  const old = Object.assign({}, DONE);
  delete old.completion;
  const card = ctx.shadowTaskCardHtml(old);
  assert(!/shdonesum/.test(card), "no block without the field");
  assert(/done when/.test(card), "the old flat row is still its row");
  assert(/EMI-OK/.test(card), "and it still names the criteria");
  console.log("ok 5 records written before the field are unchanged");
}

/* 6. THE TASK YOU ARE READING SURVIVES ITS OWN COMPLETION.
      Rule 4 drops it from the LIST -- that is right and is pinned below --
      but the pane must not swap the card out from under the founder in the
      same tick, or the summary has no surface at all. */
{
  const ctx = fresh();
  ctx.S.goals = [];
  ctx.S.shadowMissions = [
    DONE,
    { id: "m-other", objective: "something else", state: "running",
      turns_used: 1, max_turns: 20, done_when: [] },
  ];
  ctx.S.shadowTaskSel = "m-done";
  const sel = ctx.shadowSelectedTask();
  assert(sel && sel.id === "m-done",
    "the task the founder picked stayed in the pane");
  assert(/3 of 3 checks passed/.test(ctx.shadowTaskCardHtml(sel)),
    "and it is showing the summary");

  /* 5b. the LIST still drops it -- the workspace is not a mission database */
  const ids = ctx.shadowTasks().map(m => m.id);
  assert(!ids.includes("m-done"), "a conclusion still leaves the list");
  assert(ids.includes("m-other"), "live work is still listed");

  /* and picking something else lets go of it */
  ctx.S.shadowTaskSel = "m-other";
  assert.strictEqual(ctx.shadowSelectedTask().id, "m-other",
    "the founder's next pick wins");
  console.log("ok 6 held task survives completion; the list does not grow");
}

/* 7. nothing selected -> the existing fallback ranking is untouched */
{
  const ctx = fresh();
  ctx.S.goals = [];
  ctx.S.shadowMissions = [
    DONE,
    { id: "m-run", objective: "live", state: "running", done_when: [] },
    { id: "m-blk", objective: "asks", state: "blocked",
      block_reason: "ping_pong", done_when: [] },
  ];
  assert.strictEqual(ctx.shadowSelectedTask().id, "m-blk",
    "with no pick, what needs the founder still ranks first");
  ctx.S.shadowTaskSel = "m-gone";      /* a deleted id selects nothing */
  assert.strictEqual(ctx.shadowSelectedTask().id, "m-blk",
    "a stale id falls through to the ranking, never to null");
  console.log("ok 7 the fallback ranking is unchanged");
}

/* 8. it is escaped. The check text is founder- and model-authored. */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml({ id: "m-e", completion: {
    headline: "1 of 1 checks passed", objective: "<b>obj</b>",
    turns_used: 1, max_turns: 2,
    checks: [{ check: "<script>alert(1)</script>", tier: "contains_artifact",
               met: true, how: "found in the chat",
               evidence: "<img onerror=x>" }] } });
  assert(!/<script>/.test(h), "the criterion is escaped");
  assert(!/<img /.test(h), "the quote is escaped");
  assert(!/<b>obj<\/b>/.test(h), "the objective is escaped");
  assert(/&lt;script&gt;/.test(h), "and it is still readable");
  console.log("ok 8 escaped");
}

/* 9. THE ROW'S PROMISE IS KEPT. "done - result inside" links to
      sutra://shadow/mission/<id>; the workspace picks its card from
      shadowTaskSel, so the link must set it or it opens someone else's
      task. shadowFocusMission (the Watching plane's highlight) is still
      set too -- this adds, it does not rename. */
{
  const ctx = fresh();
  const calls = [];
  ctx.goDest = (d) => calls.push("dest:" + d);
  ctx.openScreen = (s) => calls.push("screen:" + s);
  ctx.render = () => {};
  assert.strictEqual(
    ctx.shadowRouteDeepLink("sutra://shadow/mission/m-done"), true,
    "the mission link routes");
  assert(calls.includes("screen:shadow"), "it lands on Focus > Shadow");
  assert.strictEqual(ctx.S.shadowFocusMission, "m-done",
    "the plane highlight is still set");
  assert.strictEqual(ctx.S.shadowTaskSel, "m-done",
    "and the workspace opens the task the row named");

  /* end to end: the linked task is the one whose summary is drawn */
  ctx.S.goals = [];
  ctx.S.shadowMissions = [
    { id: "m-other", objective: "unrelated", state: "running",
      done_when: [] },
    DONE,
  ];
  assert(/3 of 3 checks passed/.test(ctx.shadowHomeHtml()),
    "the summary is on screen after following the link");
  console.log("ok 9 the Now row opens the task it is about");
}

console.log("test_shadow_completion_ui.js: all green");
