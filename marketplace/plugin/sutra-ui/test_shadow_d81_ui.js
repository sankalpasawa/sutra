#!/usr/bin/env node
/* test_shadow_d81_ui.js -- THE SUBSTRATE IS NOT A PARTICIPANT
 * (founder, 2026-09-21, pass 5; SUPERSEDES D81 for this surface).
 *
 * D81, the same day, read "all the conversations with the app should happen
 * in the Sutra chat UI and should be shown there", and every prompt the app
 * sends into the task's Shadow chat -- boot, brief ask, steering, judge --
 * became one folded row in the stream. Pass 5 is explicit that they must not
 * be chat at all:
 *
 *     "The current UI is instead showing internal Shadow lifecycle/event
 *      records such as SHADOW BOOTED WITH ITS OPERATING CONTEXT, SHADOW READ
 *      THE WORKER AND CHOSE THE NEXT INSTRUCTION ... Those are
 *      implementation/substrate details. They must NOT be rendered as
 *      conversation messages."
 *
 * WHAT THIS LANE NOW PINS, and D81's requirement is still met by the second
 * clause: the prompts and every reply to them are absent from the
 * conversation, AND nothing was dropped from the record -- the task chat is
 * a published chat of its own (app.py _publish_task_chat -> m.task_chat), so
 * all of it is still readable in Chats, verbatim. The founder's own lines and
 * Shadow's answers to them draw exactly as before.
 *
 * Run: node test_shadow_d81_ui.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
const css = fs.readFileSync(
  path.join(__dirname, "static", "panel.css"), "utf8");

function fresh(){
  const ctx = {
    console, Date,
    setTimeout: () => ({}), clearTimeout(){}, setInterval: () => ({}),
    scheduleRender(){},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    SCREENS: {}, TITLES: {}, S: {},
    fetched: [], listeners: {},
    document: {
      addEventListener(t, fn){ (ctx.listeners[t] = ctx.listeners[t] || []).push(fn); },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  ctx.loadGoalTranscript = (sid) => { ctx.fetched.push(sid); };
  ctx.goalMessages = (sid) => (ctx.S.goalTranscript || {})[sid];
  ctx.goalTranscriptHtml = () => "";
  ctx.showNudge = () => {};
  ctx.shadowPost = async () => ({ ok: true, status: 200, json: async () => ({}) });
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  return ctx;
}

const M = (over) => Object.assign({
  id: "m-1", objective: "Ship the fix", template: "fix",
  target_mode: "new", target_session: "sess-1", target_chat: "c-1",
  task_chat_session: "shadow-1", task_chat: "c-2",
  state: "running", turns_used: 3, max_turns: 12,
  done_when: [{ check: "the tests pass", tier: "judge" }],
}, over);

function pane(ctx, m){
  ctx.S.shadowMissions = [m];
  ctx.S.shadowTaskSel = m.id;
  return ctx.shadowHomeHtml();
}

let ok = 0;
const pass = (s) => console.log("ok " + (++ok) + " " + s);

const TRANSCRIPT = [
  { role: "user", text: "[Shadow boot] Read your operating context, then answer READY.\n\nYou are Shadow.", ts: "2026-09-21T10:00:00Z" },
  { role: "assistant", text: "READY", ts: "2026-09-21T10:00:05Z" },
  { role: "user", text: "Write the opening brief for this task's worker chat.\n\nFACTS\n- repo: x", ts: "2026-09-21T10:00:10Z" },
  { role: "assistant", text: "```brief\nThe brief.\n```", ts: "2026-09-21T10:00:20Z" },
  { role: "user", text: "You are Shadow, driving one target chat toward an outcome.\nOUTCOME\nShip the fix", ts: "2026-09-21T10:00:30Z" },
  { role: "assistant", text: '```json\n{"action":"continue","instruction":"go"}\n```', ts: "2026-09-21T10:00:40Z" },
  { role: "user", text: "What are you waiting on?", ts: "2026-09-21T10:01:00Z" },
  { role: "assistant", text: "Waiting on the worker's verification.", ts: "2026-09-21T10:01:20Z" },
  { role: "user", text: "You are settling ONE completion check by reading evidence.\n\nTHE CHECK:\nthe tests pass", ts: "2026-09-21T10:02:00Z" },
  { role: "assistant", text: "Reading the diff.", ts: "2026-09-21T10:02:05Z" },
  { role: "assistant", text: '```json\n{"verdict":"met","reason":"suite ran green"}\n```', ts: "2026-09-21T10:02:10Z" },
];

/* ══ 1. THE READER: an app prompt and its replies leave the stream ══════ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": TRANSCRIPT };
  const rows = ctx.shadowTalkTurns(M());
  /* only the founder's line and Shadow's answer to it survive */
  assert.strictEqual(rows.length, 2,
    "only the two real conversational turns survive, got " + rows.length);
  assert.strictEqual(JSON.stringify(rows.map(r => r.who)),
    JSON.stringify(["founder", "shadow"]), "in transcript order");
  assert.strictEqual(rows[0].text, "What are you waiting on?");
  assert.strictEqual(rows[1].text, "Waiting on the worker's verification.");
  /* the DETECTOR is unchanged -- this is what recognises a prompt as the
     app's, and every one of the four shapes is still recognised */
  for (const [text, kind] of [
      ["[Shadow boot] Read your operating context", "boot"],
      ["Write the opening brief for this task's worker chat.", "brief"],
      ["You are Shadow, driving one target chat toward an outcome.", "steer"],
      ["You are settling ONE completion check by reading evidence.", "judge"],
      ["[Pending asks on this task -- ...]", "asks"]])
    assert.strictEqual((ctx.shTalkFold(text) || {}).kind, kind,
      "the detector must still recognise: " + kind);
  assert.strictEqual(ctx.shTalkFold("What are you waiting on?"), null,
    "and must never claim a founder's line");
  assert.strictEqual(src.indexOf("SH_TALK_SKIP"), -1, "the skip list is gone");
  pass("the reader drops every app prompt and every reply to it");
}

/* ══ 2. THE STREAM: not one byte of the substrate reaches the founder ═══ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": TRANSCRIPT };
  const h = pane(ctx, M());
  const stream = h.slice(h.indexOf("shtimeline"));
  assert.strictEqual((stream.match(/shfold/g) || []).length, 0,
    "no folded substrate row may be drawn");
  for (const hidden of ["[Shadow boot]", "READY", "Write the opening brief",
                        "driving one target chat", '"instruction":"go"',
                        "```brief", "settling ONE completion check",
                        "suite ran green", "Reading the diff.",
                        "Shadow booted", "next instruction", "judged a check",
                        "The app \u2192 Shadow"]){
    assert(stream.indexOf(hidden) === -1,
      "substrate reached the conversation: " + hidden);
  }
  /* the founder's own exchange draws exactly as before, on its own side */
  assert(/What are you waiting on\?/.test(stream), "the founder's line");
  assert(/Waiting on the worker/.test(stream), "and Shadow's answer");
  assert(/class="shsaid shfrom-you/.test(stream),
    "the founder's line is on the founder's side");
  assert(/class="shsaid shfrom-shadow/.test(stream),
    "and Shadow's answer is on Shadow's");
  pass("every app prompt and reply is absent from the conversation");
}

/* ══ 3. NOTHING WAS DROPPED FROM THE RECORD (D81's other half) ══════════
   The task chat is a chat in its own right, published by the server and
   stamped on the mission, so all of the above is still readable in Chats.
   Asserted on the record the UI reads, not on a rendered string. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": TRANSCRIPT };
  const m = M();
  assert.strictEqual(m.task_chat, "c-2",
    "the mission must still carry its Shadow chat");
  assert.strictEqual(ctx.shadowTaskTranscript("shadow-1", true).length,
    TRANSCRIPT.length,
    "and the transcript reader must still return every message");
  pass("the substrate is hidden from the conversation, never deleted");
}

/* ══ 4. ORDER: the two real turns keep their place ══════════════════════ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": TRANSCRIPT };
  const h = pane(ctx, M());
  const stream = h.slice(h.indexOf("shtimeline"));
  assert(stream.indexOf("What are you waiting on?")
         < stream.indexOf("Waiting on the worker"),
    "the question comes before the answer");
  pass("the surviving turns keep their order");
}

/* ══ 5. A TRANSCRIPT WITH NO APP PROMPTS is unchanged ════════════════════ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": [
    { role: "user", text: "Hello?", ts: "2026-09-21T10:01:00Z" },
    { role: "assistant", text: "Hi.", ts: "2026-09-21T10:01:20Z" },
  ] };
  const h = pane(ctx, M());
  assert.strictEqual((h.match(/shfold/g) || []).length, 0, "no fold anywhere");
  assert(/Hello\?/.test(h) && /Hi\./.test(h));
  pass("a plain conversation is untouched by any of this");
}

console.log("1.." + ok);
