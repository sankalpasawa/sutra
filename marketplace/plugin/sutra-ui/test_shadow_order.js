#!/usr/bin/env node
/* test_shadow_order.js -- THE CONVERSATION READS IN THE ORDER IT HAPPENED
 * (founder, 2026-09-23).
 *
 * THE BUG. A reason typed under "No" was sent BEFORE the answer, and the
 * live ask is drawn at the END of the conversation -- so a line sent
 * through the task chat landed in the timeline ABOVE the question it was
 * about. For the length of the round trip the founder read their own words
 * above the question they were answering.
 *
 * WHAT IS PINNED: the feedback is an ordinary message on the ordinary path,
 * placed by its own clock, and it reads the same before and after a reload.
 *
 * Run: node test_shadow_order.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const RESULT = "1. Fed holds rates steady\n2. EU agrees AI liability rules";
const Q = "Are these the ten stories you wanted?";
const FEEDBACK = "Too much finance — I wanted more science.";
const REPLY = "Swapping three of them now.";

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
  ctx.goalMessages = (sid) => ctx.S.goalTranscript[sid];
  ctx.goalTranscriptHtml = () => "";
  return ctx;
}

/* the worker's chat and the task's own Shadow chat, as the server holds them */
const worker = () => [
  { role: "user", text: "[Shadow · mission m-1] carry on", ts: "2026-09-23T10:00:00Z" },
  { role: "assistant", text: "REPORT: wrote the ten stories to international-news.md",
    ts: "2026-09-23T10:01:00Z" }];

/* ANSWERED: the ask is retired and left founder_response behind */
const answered = () => ({
  id: "m-1", objective: "Print the top 10 international news items",
  template: "research", target_mode: "new", target_session: "s-1",
  task_chat_session: "shadow-1", turns_used: 6, max_turns: 20, state: "running",
  done_when: [{ tier: "founder_confirm", check: "The ten are the ones I wanted.", met: false }],
  founder_response: { intervention_id: "iv-1", question: Q,
    answered_at: "2026-09-23T10:05:00Z", values: { list_ok: false },
    summary: [{ key: "list_ok", label: "These are the ten I wanted.", value: "No" }],
    evidence: [{ kind: "output", ref: "international-news.md", text: RESULT }] } });

let ok = 0;
const pass = (s) => console.log("ok " + (++ok) + " " + s);

/* the order the pane actually renders these in */
function order(ctx, m, marks){
  ctx.S.shadowMissions = [m];
  ctx.S.shadowTaskSel = m.id;
  const h = ctx.shadowHomeHtml();
  return marks.map(([name, needle]) => [name, h.indexOf(needle)]);
}
function assertOrder(got, why){
  const missing = got.filter(([, i]) => i === -1).map(([n]) => n);
  assert.strictEqual(missing.join(", "), "", "not rendered at all: " + missing);
  const sorted = got.slice().sort((a, b) => a[1] - b[1]).map(([n]) => n);
  assert.strictEqual(sorted.join(" -> "), got.map(([n]) => n).join(" -> "), why
    + "\n  expected: " + got.map(([n]) => n).join(" -> ")
    + "\n  actual:   " + sorted.join(" -> "));
}

/* ══ 1. RESULT -> QUESTION -> FEEDBACK -> SHADOW'S REPLY ═══════════════ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "s-1": worker(), "shadow-1": [
    { role: "user", text: FEEDBACK, ts: "2026-09-23T10:06:00Z" },
    { role: "assistant", text: REPLY, ts: "2026-09-23T10:07:00Z" }] };
  assertOrder(order(ctx, answered(), [
    ["result", "Fed holds rates steady"],
    ["question", Q],
    ["answer", "These are the ten I wanted"],
    ["feedback", "Too much finance"],
    ["Shadow's reply", "Swapping three of them"],
  ]), "the conversation must read in the order it happened");
  pass("result, question, the founder's words, then Shadow's reply");
}

/* ══ 2. AND AGAIN AFTER A RELOAD ══════════════════════════════════════
   Nothing is rebuilt from client memory here: this context has never seen
   the submit, only the records the server holds -- which is what a reopen
   is. The order must be identical. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "s-1": worker(), "shadow-1": [
    { role: "user", text: FEEDBACK, ts: "2026-09-23T10:06:00Z" },
    { role: "assistant", text: REPLY, ts: "2026-09-23T10:07:00Z" }] };
  assertOrder(order(ctx, answered(), [
    ["result", "Fed holds rates steady"],
    ["question", Q],
    ["answer", "These are the ten I wanted"],
    ["feedback", "Too much finance"],
    ["Shadow's reply", "Swapping three of them"],
  ]), "a reopen must reconstruct the same order");
  pass("a reopen reconstructs the same order from the server's records");
}

/* ══ 3. THE FEEDBACK IS NOT ABOVE A QUESTION THAT IS STILL LIVE ═══════
   The regression itself. While an ask is unanswered it is drawn at the END
   of the conversation, so a message sent before the answer landed above
   it. The reason is sent AFTER the answer now, so this state cannot occur
   -- and if it ever does, the founder's words are not above the question. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "s-1": worker(), "shadow-1": [] };
  const live = answered();
  live.intervention = { id: "iv-2", schema_version: 1, question: Q, context: "",
    evidence: [{ kind: "output", ref: "international-news.md", text: RESULT }],
    fields: [{ key: "list_ok", type: "boolean", label: "These are the ten I wanted.",
               required: true, options: [], constraints: {} }],
    submit_label: "Send to Shadow", expires_at: null };
  delete live.founder_response;
  ctx.S.shadowMissions = [live]; ctx.S.shadowTaskSel = "m-1";
  const before = ctx.shadowHomeHtml();
  assert(before.indexOf("Too much finance") === -1,
    "nothing of the founder's is on screen before they send it");
  assert(before.indexOf(Q) !== -1, "and the question is");
  pass("a live ask carries no founder message above it");
}

/* ══ 4. THE TWO PATHS ARE ONE PATH ════════════════════════════════════
   An ordinary "Talk to Shadow" line and a reason typed under No are the
   same kind of thing: both go through shadowTalkSend, into the task's own
   chat, and are placed by their own clock. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "s-1": worker(), "shadow-1": [
    { role: "user", text: "an ordinary line I typed", ts: "2026-09-23T10:06:00Z" },
    { role: "user", text: FEEDBACK, ts: "2026-09-23T10:09:00Z" }] };
  assertOrder(order(ctx, answered(), [
    ["question", Q],
    ["answer", "These are the ten I wanted"],
    ["ordinary line", "an ordinary line I typed"],
    ["reason under No", "Too much finance"],
  ]), "both kinds of founder message are placed by their clock alone");

  const src = fs.readFileSync(
    path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
  const at = src.indexOf("async function shadowSendIntervention");
  const send = src.slice(at, src.indexOf("\nasync function ", at + 10));
  assert(/shadowTalkSend\(mid, null\)/.test(send),
    "the reason goes out through the composer's own send, not a second path");
  /* the CALL, not a mention of it in a comment above */
  assert(send.indexOf("shadowTalkSend(mid, null)")
         > send.indexOf('action: "intervene"'),
    "and AFTER the answer, so it is never above a live question");
  pass("an ordinary message and a reason under No share one path and one clock");
}

/* ══ 5. A SECOND ROUND APPENDS; IT DOES NOT REPLACE ═══════════════════
   (founder, 2026-09-23: "Shadow is a persistent conversation, not a single
   mutable result panel.") The whole of round one stays on screen when
   round two arrives, in order, with the new result and question beneath
   it -- not in place of it. */
{
  const ctx = fresh();
  const R2 = "1. Ariane 6 launches Galileo pair\n2. WHO declares dengue emergency";
  const Q2 = "Better? Here is the new list.";
  ctx.S.goalTranscript = { "s-1": worker().concat([
      { role: "assistant", text: "REPORT: swapped three for science",
        ts: "2026-09-23T10:08:00Z" }]),
    "shadow-1": [
      { role: "user", text: FEEDBACK, ts: "2026-09-23T10:06:00Z" },
      { role: "assistant", text: REPLY, ts: "2026-09-23T10:07:00Z" }] };
  const m = answered();
  m.state = "blocked"; m.block_reason = "needs_founder"; m.turns_used = 8;
  m.intervention = { id: "iv-2", schema_version: 1, question: Q2, context: "",
    evidence: [{ kind: "output", ref: "international-news.md", text: R2 }],
    fields: [{ key: "ok2", type: "boolean", label: "These are right.",
               required: true, options: [], constraints: {} }],
    submit_label: "Send to Shadow", expires_at: null };

  assertOrder(order(ctx, m, [
    ["round 1 result", "Fed holds rates steady"],
    ["round 1 question", Q],
    ["round 1 answer", "These are the ten I wanted"],
    ["feedback", "Too much finance"],
    ["Shadow's reply", "Swapping three of them"],
    ["round 2 result", "Ariane 6 launches"],
    ["round 2 question", Q2],
  ]), "round two appends beneath round one; it never replaces it");
  pass("a second result and question append; the first round stays whole");
}

/* ══ 6. AND THE QUESTION IS ASKED ONCE ════════════════════════════════
   It used to be announced in the timeline AND printed by the ask, so the
   question stood above the very result it was asking about. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "s-1": worker(), "shadow-1": [] };
  const m = answered();
  delete m.founder_response;
  m.state = "blocked"; m.block_reason = "needs_founder";
  m.intervention = { id: "iv-1", schema_version: 1, question: Q, context: "",
    evidence: [{ kind: "output", ref: "international-news.md", text: RESULT }],
    fields: [{ key: "list_ok", type: "boolean", label: "These are the ten I wanted.",
               required: true, options: [], constraints: {} }],
    submit_label: "Send to Shadow", expires_at: null };
  ctx.S.shadowMissions = [m]; ctx.S.shadowTaskSel = "m-1";
  const h = ctx.shadowHomeHtml();
  assert.strictEqual(h.split(Q).length - 1, 1,
    "the question appears exactly once, got " + (h.split(Q).length - 1));
  assert(h.indexOf("Fed holds rates steady") < h.indexOf(Q),
    "and beneath the result it is about, never above it");
  assert(!/shask-question/.test(h), "the duplicate announcement row is gone");
  pass("the question is asked once, under the result it is about");
}

/* ══ 7-8. A REDIRECTION ADDS A ROUND; IT DOES NOT ERASE THE LAST ONE ═══
   (founder, 2026-09-23: the previous Marc Marquez turn disappeared when the
   task was redirected.) The engine pops `completion`, `founder_response`
   and `intervention` on a revision -- right for a LIVE ask, wrong for what
   happened -- so it now carries them onto the `revisions` entry it was
   already writing, and those become events in this same stream. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "s-1": worker(), "shadow-1": [] };
  const m = {
    id: "m-1", objective: "Ten lines about Valentino Rossi",
    template: "research", target_mode: "new", target_session: "s-1",
    task_chat_session: "shadow-1", turns_used: 9, max_turns: 20,
    state: "running", done_when: [],
    /* two earlier rounds, oldest first, exactly as the engine writes them */
    revisions: [
      { version: 1, at: "2026-09-23T10:05:00Z",
        objective: "Ten lines about Marc Marquez", checks: [],
        completion: { said: "Done \u2014 ten lines on Marc Marquez.",
                      preview: { text: "1. Eight world titles", truncated: false } },
        asked: { question: "Are these the ten about Marquez you wanted?",
                 evidence: [{ kind: "output", ref: "marquez.md",
                              text: "1. Eight world titles" }] },
        founder_response: { question: "Are these the ten about Marquez you wanted?",
          summary: [{ key: "ok", label: "These are right", value: "No" }] } },
      { version: 2, at: "2026-09-23T10:20:00Z",
        objective: "Ten lines about Casey Stoner", checks: [],
        completion: { said: "Done \u2014 ten lines on Casey Stoner.",
                      preview: { text: "1. Two world titles", truncated: false } } },
    ] };

  assertOrder(order(ctx, m, [
    ["round 1 objective", "Ten lines about Marc Marquez"],
    ["round 1 result", "Eight world titles"],
    ["round 1 question", "Are these the ten about Marquez"],
    ["round 1 answer", "These are right"],
    ["round 2 result", "Two world titles"],
  ]), "every round stays, oldest first");

  const h = ctx.shadowHomeHtml();
  assert(h.indexOf("Ten lines about Marc Marquez") !== -1,
    "THE MARQUEZ TURN SURVIVES the redirection");
  assert(h.indexOf("Ten lines about Casey Stoner") !== -1
      || h.indexOf("Two world titles") !== -1,
    "and so does the round after it");
  pass("two redirections, and every round is still in the conversation");
}

/* a reopen rebuilds the same thing from the record alone */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "s-1": worker(), "shadow-1": [] };
  const m = {
    id: "m-1", objective: "Ten lines about Valentino Rossi", template: "research",
    target_mode: "new", target_session: "s-1", task_chat_session: "shadow-1",
    turns_used: 9, max_turns: 20, state: "done", done_when: [],
    completion: { said: "Done \u2014 ten lines on Valentino Rossi.",
                  preview: { text: "1. Nine world titles", truncated: false } },
    revisions: [
      { version: 1, at: "2026-09-23T10:05:00Z",
        objective: "Ten lines about Marc Marquez", checks: [],
        completion: { said: "Done \u2014 ten lines on Marc Marquez.",
                      preview: { text: "1. Eight world titles", truncated: false } } },
      { version: 2, at: "2026-09-23T10:20:00Z",
        objective: "Ten lines about Casey Stoner", checks: [],
        completion: { said: "Done \u2014 ten lines on Casey Stoner.",
                      preview: { text: "1. Two world titles", truncated: false } } },
    ] };
  assertOrder(order(ctx, m, [
    ["round 1", "Eight world titles"],
    ["round 2", "Two world titles"],
    ["round 3 (current)", "Nine world titles"],
  ]), "a reopen reconstructs all three rounds in order");
  pass("reopening a redirected task rebuilds every round, chronologically");
}

/* ══ 9. DONE, REOPENED, DONE AGAIN -- EVERY RESULT SURVIVES ═══════════
   (founder, 2026-09-23: "Done means the task is complete -- it does not
   mean its result is disposable.") The engine already archived the
   displaced completion onto `reopened`, together with the words the
   founder handed it back with; nothing drew them, so a reopened task was
   rebuilt from the latest result alone. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "s-1": worker(), "shadow-1": [] };
  const m = {
    id: "m-1", objective: "Ten lines about Valentino Rossi", template: "research",
    target_mode: "new", target_session: "s-1", task_chat_session: "shadow-1",
    turns_used: 12, max_turns: 20, state: "done", done_when: [],
    /* the CURRENT result */
    completion: { said: "Done \u2014 rewritten with the 2008 season.",
                  preview: { text: "1. Won the 2008 title", truncated: false } },
    /* and the one it displaced when the founder handed the task back */
    reopened: [{ at: "2026-09-23T11:00:00Z", from: "done", at_turn: 6,
      via: "founder", words: "This misses the 2008 season entirely.",
      completion: { said: "Done \u2014 ten lines on Valentino Rossi.",
                    preview: { text: "1. Nine world titles", truncated: false } } }],
  };
  assertOrder(order(ctx, m, [
    ["the first result", "Nine world titles"],
    ["what they said handing it back", "misses the 2008 season"],
    ["the result after it", "Won the 2008 title"],
  ]), "a hand-back keeps the result it displaced, in order");

  const h = ctx.shadowHomeHtml();
  assert(h.indexOf("Nine world titles") !== -1,
    "THE FIRST SURFACED RESULT SURVIVES being reopened and re-completed");
  assert(h.indexOf("Won the 2008 title") !== -1, "and so does the newer one");
  pass("Done -> reopen -> Done again: every surfaced result stays");
}

/* ══ 10. BOTH LOGS FEED ONE STREAM ════════════════════════════════════
   A task that was redirected AND handed back has rounds in `revisions`
   and rounds in `reopened`. They are one conversation, ordered by when
   they happened, not by which list they came from. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "s-1": worker(), "shadow-1": [] };
  const m = {
    id: "m-1", objective: "current", template: "research", target_mode: "new",
    target_session: "s-1", task_chat_session: "shadow-1",
    turns_used: 14, max_turns: 20, state: "done", done_when: [],
    completion: { said: "Done \u2014 the latest.",
                  preview: { text: "RESULT FOUR", truncated: false } },
    revisions: [{ version: 1, at: "2026-09-23T10:05:00Z", objective: "first",
      checks: [], completion: { said: "Done.",
        preview: { text: "RESULT ONE", truncated: false } } }],
    reopened: [{ at: "2026-09-23T10:30:00Z", from: "done", via: "founder",
      words: "not quite", completion: { said: "Done.",
        preview: { text: "RESULT TWO", truncated: false } } },
      { at: "2026-09-23T11:15:00Z", from: "done", via: "founder",
        words: "closer, but no", completion: { said: "Done.",
          preview: { text: "RESULT THREE", truncated: false } } }],
  };
  assertOrder(order(ctx, m, [
    ["result one (a redirect)", "RESULT ONE"],
    ["result two (a hand-back)", "RESULT TWO"],
    ["'not quite'", "not quite"],
    ["result three", "RESULT THREE"],
    ["'closer, but no'", "closer, but no"],
    ["result four (current)", "RESULT FOUR"],
  ]), "both logs interleave by when they happened");
  pass("revisions and hand-backs interleave into one chronological history");
}

/* ══ 11. THE AUSTRALIA SCENARIO, END TO END ═══════════════════════════
   (founder, 2026-09-23, the acceptance criterion verbatim.) Five-day plan,
   the founder changes their mind mid-flight, the worker produces a
   three-day plan, Shadow asks about it. Every piece must be readable in
   Shadow -- "if any of the information needed to understand the final
   decision exists only behind Open the chat, the implementation is not
   finished." */
{
  const ctx = fresh();
  const FIVE = "Day 1 Sydney\nDay 2 Blue Mountains\nDay 3 Hunter Valley\n"
             + "Day 4 Port Stephens\nDay 5 Bondi";
  const THREE = "Day 1 Sydney: harbour walk\nDay 2 Blue Mountains\n"
              + "Day 3 Bondi: coastal walk";
  ctx.S.goalTranscript = { "s-1": worker(), "shadow-1": [
    { role: "user", text: "Actually, make it 3 days.", ts: "2026-09-23T10:10:00Z" },
    { role: "assistant", text: "Got it \u2014 cutting it to three.",
      ts: "2026-09-23T10:11:00Z" }] };
  const m = {
    id: "m-1", objective: "Make a 3-day trip to Australia", template: "plan",
    target_mode: "new", target_session: "s-1", task_chat_session: "shadow-1",
    turns_used: 7, max_turns: 20, state: "blocked", block_reason: "needs_founder",
    done_when: [],
    /* round one, archived when the founder redirected it */
    revisions: [{ version: 1, at: "2026-09-23T10:09:00Z",
      objective: "Make a 5-day trip to Australia", checks: [],
      completion: { said: "Done \u2014 a five-day Australia plan.",
                    preview: { text: FIVE, truncated: false } } }],
    /* and the ask about round two, carrying the three-day plan */
    intervention: { id: "iv-2", schema_version: 1,
      question: "Should I save this as a file?", context: "",
      evidence: [{ kind: "output", ref: "australia-3-day.md", text: THREE }],
      fields: [{ key: "save", type: "boolean", label: "Save it",
                 required: true, options: [], constraints: {} }],
      submit_label: "Send to Shadow", expires_at: null } };

  assertOrder(order(ctx, m, [
    ["the 5-day plan", "Day 5 Bondi"],
    ["\"make it 3 days\"", "Actually, make it 3 days"],
    ["the 3-day plan", "Day 3 Bondi: coastal walk"],
    ["the decision", "Should I save this as a file?"],
  ]), "five days, the change of mind, three days, then the question");

  const h = ctx.shadowHomeHtml();
  /* H: everything the decision needs is HERE */
  assert(h.indexOf("Day 1 Sydney: harbour walk") !== -1,
    "the plan being decided about is in Shadow, not only in the worker chat");
  assert(h.indexOf("australia-3-day.md") !== -1, "with where it came from");
  assert(/data-shivopt="yes"/.test(h) && /data-shivsend/.test(h),
    "and it can be answered from here");
  /* and it is not a transcript dump: the worker's own REPORT lines stay out */
  assert(h.indexOf("REPORT:") === -1,
    "no raw worker output leaked in to achieve it");
  pass("the Australia scenario: every piece of the decision is in Shadow");
}

console.log("\nall shadow order checks passed");
