#!/usr/bin/env node
/* test_shadow_v4_talk.js -- TALK TO SHADOW: the founder's conversation with
 * ONE running task (step 1 of the Shadow conversation UX, founder 2026-09-16).
 *
 * WHAT THIS STEP IS. "Give instruction to Shadow" (the workspace composer)
 * deposits a steering line on the mission record and nothing answers; the one
 * surface that ANSWERS is the task's own Shadow chat, and Start used to close
 * it. This lane pins the second door: a floating panel on the task header that
 * talks to that same chat, through the route that already existed
 * (POST /api/shadow/tasks/{id}/chat -> shadow_task_chat.TaskChat.talk).
 *
 * WHAT IT IS NOT, and every lane below is written to keep it that way: it is
 * not an instruction. Nothing here posts to /act, nothing reaches the worker,
 * nothing spends a turn, nothing enters founder_says. Whether a casual line
 * should ever become work is step 2.
 *
 * Run: node test_shadow_v4_talk.js
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

function fresh(reply){
  const ctx = {
    console, Date,
    setTimeout: () => ({}), clearTimeout(){}, setInterval: () => ({}),
    scheduleRender(){},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    SCREENS: {}, TITLES: {}, S: {},
    posted: [], fetched: [], nudged: "",
    listeners: {},
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
  ctx.showNudge = (t) => { ctx.nudged = t; };
  ctx.shadowPost = async (url, body) => {
    ctx.posted.push({ url: url, body: body });
    const r = (typeof reply === "function") ? reply(url, body) : reply;
    if (r && r.status && !r.ok) return { ok: false, status: r.status };
    return { ok: true, status: 200,
             json: async () => ({ mission: { id: "m-1" },
                                  reply: (r && r.reply) || "Validating the pipeline." }) };
  };
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  return ctx;
}

const M = (over) => Object.assign({
  id: "m-1", objective: "Ship the fix", template: "fix",
  target_mode: "new", target_session: "sess-1", target_chat: "c-1",
  task_chat_session: "shadow-1", task_chat: "c-2",
  state: "running", turns_used: 3, max_turns: 12,
  done_when: [{ check: "the tests pass", tier: "founder_confirm" }],
}, over);

function pane(ctx, m){
  ctx.S.shadowMissions = [m];
  ctx.S.shadowTaskSel = m.id;
  return ctx.shadowHomeHtml();
}
const click = (ctx, dataset) =>
  (ctx.listeners.click || []).forEach(fn =>
    fn({ target: { dataset: dataset, closest: () => null },
         preventDefault(){}, stopPropagation(){} }));
const type = (ctx, dataset, value) =>
  (ctx.listeners.input || []).forEach(fn =>
    fn({ target: { dataset: dataset, value: value } }));
const enter = (ctx, dataset, value) =>
  (ctx.listeners.keydown || []).forEach(fn =>
    fn({ key: "Enter", shiftKey: false,
         target: { dataset: dataset, value: value },
         preventDefault(){}, stopPropagation(){} }));
const settle = () => new Promise(r => setImmediate(r));

let ok = 0;
const pass = (s) => console.log("ok " + (++ok) + " " + s);
const asyncChecks = [];

/* -- A. the second door is there, under the first, and opens the panel -- */
{
  const ctx = fresh();
  const h = pane(ctx, M());
  assert(/class="shwheadcol"/.test(h), "the two doors must stack in a column");
  assert(/data-shtakeover="sess-1"[^>]*>Open the chat/.test(h),
    "the worker chat door is unchanged");
  assert(/data-shtalk="m-1"[^>]*>Talk to Shadow/.test(h),
    "Talk to Shadow is missing");
  assert(h.indexOf("Open the chat") < h.indexOf("Talk to Shadow"),
    "Talk to Shadow sits BELOW Open the chat");
  /* closed by default: no panel, and nothing fetched for it */
  assert(!/class="shtalk"/.test(h), "the panel must start closed");

  click(ctx, { shtalk: "m-1" });
  const open = pane(ctx, M());
  assert(/class="shtalk"/.test(open), "clicking must open the panel");
  assert(/data-shtalkbox="m-1"/.test(open), "with its own composer");
  assert(/data-shtalksend="m-1"/.test(open), "and its own send");
  assert(/data-shtalkclose="1"/.test(open), "and a way to close it");
  assert.strictEqual(ctx.posted.length, 0,
    "opening the panel must not post anything");
  pass("Talk to Shadow sits under Open the chat and opens a panel");
}

/* -- A2. it FLOATS: overlapping, never reflowing the card below --------- */
{
  const ctx = fresh();
  click(ctx, { shtalk: "m-1" });
  const h = pane(ctx, M());
  /* anchored inside the header's action group, before the card */
  assert(h.indexOf('class="shtalk"') < h.indexOf("shcard2"),
    "the panel is anchored in the header, not inserted into the flow");
  const rule = css.slice(css.indexOf(".shtalk{"));
  const decl = rule.slice(0, rule.indexOf("}"));
  assert(/position:absolute/.test(decl),
    "the panel must be absolutely positioned so it cannot push content");
  assert(/z-index:/.test(decl), "and it must sit above what it overlaps");
  assert(/\.shwheadacts\{[^}]*position:relative/.test(css),
    "its anchor must be the header action group");
  pass("the panel floats over the card and cannot reflow it");
}

/* -- B/C/D. send a line, get Shadow's own answer, see both ------------- */
{
  const ctx = fresh({ reply: "I'm validating the data pipeline." });
  click(ctx, { shtalk: "m-1" });
  type(ctx, { shtalkbox: "m-1" }, "What are you working on?");
  click(ctx, { shtalksend: "m-1" });
  asyncChecks.push(settle().then(() => {
    assert.strictEqual(ctx.posted.length, 1, "exactly one request");
    assert.strictEqual(ctx.posted[0].url, "/api/shadow/tasks/m-1/chat",
      "it must go to the EXISTING task-chat route, got " + ctx.posted[0].url);
    /* field by field: the body is built inside the vm realm, so its
       prototype is not this realm's Object and deepStrictEqual refuses it */
    assert.strictEqual(ctx.posted[0].body.message, "What are you working on?");
    assert.deepStrictEqual(Object.keys(ctx.posted[0].body), ["message"],
      "and it carries nothing else");
    const h = pane(ctx, M());
    assert(/What are you working on\?/.test(h), "the founder's line is drawn");
    assert(/I&#x27;m validating the data pipeline\.|I'm validating the data pipeline\./
      .test(h), "Shadow's own answer is drawn");
    assert(/class="shmsg shmine"/.test(h), "as the founder bubble");
    assert(/class="shmsg shshadow"/.test(h), "and the Shadow bubble");
    pass("a line reaches the task chat and Shadow's answer comes back");
  }));
}

/* -- E. several turns keep their order ---------------------------------- */
{
  const ctx = fresh((url, body) => ({ reply: "Answer to: " + body.message }));
  click(ctx, { shtalk: "m-1" });
  asyncChecks.push((async () => {
    type(ctx, { shtalkbox: "m-1" }, "first");
    click(ctx, { shtalksend: "m-1" });
    await settle();
    enter(ctx, { shtalkbox: "m-1" }, "second");
    await settle();
    const h = pane(ctx, M());
    for (const want of ["first", "Answer to: first",
                        "second", "Answer to: second"]){
      assert(h.indexOf(want) !== -1, "lost from the thread: " + want);
    }
    assert(h.indexOf("first") < h.indexOf("second"), "and in order");
    assert.strictEqual(ctx.posted.length, 2, "one request per line");
    pass("several turns keep their order in the panel");
  })());
}

/* -- F. RELOAD: the history comes from the RECORD, not the browser ------
   A fresh context has no live thread at all. The conversation is read from
   the task chat's own transcript -- the same store, the same throttled
   reader the worker chat uses -- so a reload, and a backend restart that
   --resumes the same session, both redraw it. */
const TRANSCRIPT = [
  { role: "user", text: "[Shadow boot] Read your operating context, then answer READY.\n\nYou are Shadow." },
  { role: "assistant", text: "READY" },
  { role: "user", text: "Write the opening brief for this task's worker chat.\n\nFACTS\n- repo: x" },
  { role: "assistant", text: "```brief\nThe brief.\n```" },
  { role: "user", text: "You are Shadow, driving one target chat toward an outcome.\nOUTCOME\nShip the fix" },
  { role: "assistant", text: '```json\n{"action":"continue","instruction":"go"}\n```' },
  { role: "user", text: "What are you working on?" },
  { role: "assistant", text: "Validating the data pipeline." },
];
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": TRANSCRIPT };
  click(ctx, { shtalk: "m-1" });              /* a brand new sitting */
  const h = pane(ctx, M());
  assert(/What are you working on\?/.test(h), "the founder's line must return");
  assert(/Validating the data pipeline\./.test(h), "and Shadow's answer");
  /* ...and NOT the orchestration that shares the same session. Asserted on
     the PANEL's own thread: "instruction" is a legitimate word elsewhere on
     the page now that the other composer is named for it. */
  const thread = h.slice(h.indexOf("shtalkthread"),
                         h.indexOf("shtalkcomp"));
  assert(thread, "the thread region is missing");
  for (const hidden of ["[Shadow boot]", "READY",
                        "Write the opening brief", "brief",
                        "driving one target chat",
                        '"action"', '"instruction"']){
    assert(thread.indexOf(hidden) === -1,
      "orchestration leaked into the founder's conversation: " + hidden);
  }
  /* read through the EXISTING throttled transcript reader -- the same one
     the worker timeline already uses for sess-1, which is why both ids are
     here and why no second store or endpoint was added */
  assert(ctx.fetched.indexOf("shadow-1") !== -1,
    "the Shadow chat transcript must be read, got " + ctx.fetched.join(","));
  assert.strictEqual(
    ctx.fetched.filter(x => x === "shadow-1").length, 1,
    "and read once per throttle window, not per render");
  pass("reload and restart redraw the conversation from the record");
}

/* -- F2. the record and a live line are never drawn twice --------------- */
{
  const ctx = fresh({ reply: "Validating the data pipeline." });
  ctx.S.goalTranscript = { "shadow-1": [] };
  click(ctx, { shtalk: "m-1" });
  type(ctx, { shtalkbox: "m-1" }, "What are you working on?");
  click(ctx, { shtalksend: "m-1" });
  asyncChecks.push(settle().then(() => {
    /* the transcript catches up with what was just said */
    ctx.S.goalTranscript["shadow-1"] = TRANSCRIPT;
    const h = pane(ctx, M());
    assert.strictEqual((h.match(/What are you working on\?/g) || []).length, 1,
      "the founder's line must not double when the transcript lands");
    assert.strictEqual(
      (h.match(/Validating the data pipeline\./g) || []).length, 1,
      "nor Shadow's answer");
    pass("a live line and its record are never drawn twice");
  }));
}

/* -- H/I/J. the worker is not touched ---------------------------------- */
{
  const ctx = fresh();
  pane(ctx, M());                       /* the pane holds the record */
  click(ctx, { shtalk: "m-1" });
  type(ctx, { shtalkbox: "m-1" }, "why that approach?");
  click(ctx, { shtalksend: "m-1" });
  asyncChecks.push(settle().then(() => {
    for (const p of ctx.posted){
      assert(!/\/act$/.test(p.url),
        "a conversation must never take the instruction path: " + p.url);
      assert(!/missions\//.test(p.url),
        "nor any mission action route: " + p.url);
      assert(!/sessions\//.test(p.url),
        "and never the worker session: " + p.url);
    }
    /* the mission object the pane holds is untouched: no turn accounting,
       no budget, no state -- the frontend writes none of it */
    const m = ctx.S.shadowMissions[0];
    assert.strictEqual(m.turns_used, 3, "turns_used must not move");
    assert.strictEqual(m.max_turns, 12, "nor the budget");
    assert.strictEqual(m.state, "running", "nor the state");
    assert.strictEqual(m.founder_says, undefined,
      "a conversation is not an instruction: founder_says stays untouched");
    /* closing does not post either */
    const before = ctx.posted.length;
    click(ctx, { shtalkclose: "1" });
    assert.strictEqual(ctx.posted.length, before,
      "closing the panel must not post");
    assert(!/class="shtalk"/.test(pane(ctx, M())), "and it closes");
    pass("talking touches no turn, no budget, no state, no worker");
  }));
}

/* -- K. a finished task offers no conversation ------------------------- */
{
  for (const state of ["done", "failed", "stopped"]){
    const ctx = fresh();
    const h = pane(ctx, M({ state: state }));
    assert(!/data-shtalk=/.test(h),
      state + ": a finished task must not offer Talk to Shadow");
    assert(/data-shtakeover="sess-1"/.test(h),
      state + ": the worker chat door is still there, unchanged");
  }
  /* and a refusal from the server is said in words, not swallowed */
  const ctx = fresh({ ok: false, status: 409 });
  click(ctx, { shtalk: "m-1" });
  type(ctx, { shtalkbox: "m-1" }, "still there?");
  click(ctx, { shtalksend: "m-1" });
  asyncChecks.push(settle().then(() => {
    const h = pane(ctx, M());
    assert(/has finished/.test(h),
      "a 409 must reach the founder in words, got: " + h.slice(0, 200));
    pass("a terminal task offers no conversation, and says so if asked");
  }));
}

/* -- L. the instruction path is untouched ------------------------------ */
{
  const ctx = fresh();
  const h = pane(ctx, M());
  assert(/placeholder="Give instruction to Shadow…"/.test(h),
    "the instruction composer is renamed, not removed");
  assert.strictEqual((h.match(/data-shhomecompose/g) || []).length, 1,
    "still exactly one instruction composer");
  enter(ctx, { shhomecompose: "1" }, "use CSV instead");
  asyncChecks.push(settle().then(() => {
    assert.strictEqual(ctx.posted.length, 1, "one request");
    assert.strictEqual(ctx.posted[0].url, "/api/shadow/missions/m-1/act",
      "the instruction still takes the SAY path, got " + ctx.posted[0].url);
    assert.strictEqual(ctx.posted[0].body.action, "say",
      "with the same action as before");
    assert.strictEqual(ctx.posted[0].body.text, "use CSV instead",
      "and the same payload");
    pass("Give instruction to Shadow still uses its existing path");
  }));
}

Promise.all(asyncChecks).then(() => {
  console.log("\nall shadow Talk-to-Shadow tests passed");
}, (e) => { console.error(e); process.exitCode = 1; });
