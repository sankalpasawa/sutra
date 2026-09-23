#!/usr/bin/env node
/* test_shadow_done_history.js -- DONE CHANGES THE STATE, NOT THE HISTORY
 * (founder, 2026-09-23).
 *
 * THE BUG. Answering an ask pops `intervention` from the record -- it has
 * to, or a settled question would draw a live form again -- and the material
 * the question was ABOUT went with it. So a founder returning to a finished
 * task found their own "yes" to a question about output that existed
 * nowhere on this surface. The only way to see what they had agreed to was
 * to open the worker's chat, which is the one thing Shadow is meant to make
 * unnecessary.
 *
 * The ask now leaves that material on `founder_response`, and the timeline
 * draws it back: the result, the question, the answer, in that order.
 *
 * Run: node test_shadow_done_history.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

function fresh(){
  const ctx = {
    console, Date, setTimeout: () => ({}), clearTimeout(){}, setInterval: () => ({}),
    scheduleRender(){}, SCREENS: {}, TITLES: {}, S: {}, listeners: {},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    escAttr: (x) => String(x == null ? "" : x).replace(/"/g, "&quot;"),
    document: { addEventListener(){}, createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; }, querySelectorAll(){ return []; } },
  };
  vm.createContext(ctx);
  for (const f of ["15-shadow-overlay.js", "16-shadow-home.js"])
    vm.runInContext(fs.readFileSync(
      path.join(__dirname, "static", "js", f), "utf8"), ctx);
  ctx.S.shadowHomeDark = false; ctx.S.goals = [];
  ctx.S.shadowThreads = {}; ctx.S.shadowChat = "global";
  ctx.loadGoalTranscript = () => {};
  ctx.S.goalTranscript = { "s-1": [
    { role: "user", text: "[Shadow · mission m-1] carry on", ts: "2026-09-23T10:00:00Z" },
    { role: "assistant", text: "REPORT: wrote the ten stories to international-news.md",
      ts: "2026-09-23T10:01:00Z" } ] };
  ctx.goalMessages = (sid) => ctx.S.goalTranscript[sid];
  ctx.goalTranscriptHtml = () => "";
  return ctx;
}

const RESULT = "1. Fed holds rates steady\n2. EU agrees AI liability rules";
const ASKED = {
  id: "m-1", objective: "Print the top 10 international news items",
  template: "research", target_mode: "new", target_session: "s-1",
  turns_used: 4, max_turns: 20, state: "blocked", block_reason: "needs_founder",
  done_when: [{ tier: "founder_confirm", check: "The ten are the ones I wanted.", met: false }],
  intervention: { id: "iv-1", schema_version: 1,
    question: "Are these the ten stories you wanted?", context: "",
    evidence: [{ kind: "output", ref: "international-news.md", text: RESULT }],
    fields: [{ key: "list_ok", type: "boolean", label: "These are the ten I wanted.",
               required: true, options: [], constraints: {} }],
    submit_label: "Send to Shadow", expires_at: null },
};
/* what the server leaves behind once it is answered: intervention popped,
   founder_response carrying the question, the answer AND the material */
const DONE = {
  id: "m-1", objective: ASKED.objective, template: "research",
  target_mode: "new", target_session: "s-1", turns_used: 6, max_turns: 20,
  state: "done",
  done_when: [{ tier: "founder_confirm", check: "The ten are the ones I wanted.", met: true }],
  founder_response: { intervention_id: "iv-1",
    question: "Are these the ten stories you wanted?",
    answered_at: "2026-09-23T10:05:00Z", values: { list_ok: true },
    summary: [{ key: "list_ok", label: "These are the ten I wanted.", value: "Yes" }],
    evidence: [{ kind: "output", ref: "international-news.md", text: RESULT }] },
  completion: { said: "Done — ten stories in international-news.md.",
                preview: { text: RESULT, truncated: false } },
};

let ok = 0;
const pass = (s) => console.log("ok " + (++ok) + " " + s);
const pane = (m) => { const c = fresh();
  c.S.shadowMissions = [m]; c.S.shadowTaskSel = m.id;
  return { html: c.shadowHomeHtml(), ctx: c }; };

/* ══ 1. WHILE IT IS ASKING ═════════════════════════════════════════════ */
{
  const h = pane(ASKED).html;
  assert(/Are these the ten stories you wanted\?/.test(h), "the question is on screen");
  assert(h.indexOf("Fed holds rates steady") !== -1,
    "and so is what it is asking about -- no worker chat needed");
  assert(/data-shivsend/.test(h), "with a way to answer it");
  pass("the ask shows the question AND the result it is about");
}

/* ══ 2. AFTER DONE, ALL OF IT IS STILL THERE ══════════════════════════ */
{
  const h = pane(DONE).html;
  assert(h.indexOf("Fed holds rates steady") !== -1,
    "THE RESULT SURVIVES Done");
  assert(/Are these the ten stories you wanted\?/.test(h),
    "THE QUESTION SURVIVES Done");
  assert(/These are the ten I wanted/.test(h),
    "AND WHAT THE FOUNDER ANSWERED survives Done");
  assert(/Done — ten stories/.test(h), "with the closing line beneath it");
  pass("result, question and answer all survive the transition to Done");
}

/* ══ 3. IT IS HISTORY, NOT A FORM ═════════════════════════════════════ */
{
  const h = pane(DONE).html;
  assert(!/data-shivsend/.test(h),
    "a settled question must not offer to be answered again");
  assert(!/Send to Shadow/.test(h), "nor carry its submit button");
  pass("the answered exchange is history, with nothing left to press");
}

/* ══ 4. THE ORDER IS THE ORDER IT HAPPENED ════════════════════════════ */
{
  const h = pane(DONE).html;
  const iEv = h.indexOf("Fed holds rates steady");
  const iQ  = h.indexOf("Are these the ten stories");
  const iA  = h.indexOf("These are the ten I wanted");
  assert(iEv !== -1 && iQ !== -1 && iA !== -1, "all three are present");
  assert(iEv < iQ && iQ < iA,
    "result, then question, then answer -- got " + [iEv, iQ, iA].join(","));
  pass("the exchange reads in the order it happened");
}

/* ══ 5. DONE DOES NOT TAKE THE TASK OUT OF REACH ══════════════════════ */
{
  const c = fresh();
  c.S.shadowMissions = [DONE];
  assert(c.shadowTasks().some(t => t.id === "m-1"),
    "the finished task is still in the list, so there is a way back to it");
  c.S.shadowTaskSel = null;
  c.S.shadowMissions = [DONE];
  assert(c.shadowTaskListHtml().indexOf("m-1") !== -1,
    "and still drawn as a row");
  pass("a finished task stays reachable; only archiving files it away");
}

/* ══ 6. A FOLLOW-UP CONTINUES THE SAME CONVERSATION ═══════════════════
   The founder disagrees after Done. The conversation they type into is the
   one they are reading -- not an empty one -- so what they said lands under
   the exchange above it. */
{
  const c = fresh();
  c.S.shadowMissions = [DONE];
  c.S.shadowTaskSel = "m-1";
  const before = c.shadowHomeHtml();
  assert(before.indexOf("Fed holds rates steady") !== -1, "the history is there");

  c.S.goalTranscript["s-1"] = c.S.goalTranscript["s-1"].concat([
    { role: "user", text: "I don't like this list — too much finance.",
      ts: "2026-09-23T10:20:00Z" },
    { role: "assistant", text: "REPORT: swapped three finance stories for science.",
      ts: "2026-09-23T10:22:00Z" }]);
  const after = c.shadowHomeHtml();
  assert(after.indexOf("Fed holds rates steady") !== -1,
    "the earlier result is NOT cleared by the follow-up");
  assert(/Are these the ten stories you wanted\?/.test(after),
    "nor is the question they answered");
  assert(after.indexOf("too much finance") !== -1
      || after.indexOf("swapped three finance") !== -1,
    "and the follow-up joins the same conversation");
  pass("a disagreement after Done continues the conversation, not an empty one");
}

console.log("\nall done-history checks passed");
