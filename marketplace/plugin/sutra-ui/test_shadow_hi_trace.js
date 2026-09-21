#!/usr/bin/env node
/* test_shadow_hi_trace.js -- WHERE THE "Hi" MISSION ACTUALLY COMES FROM.
 *
 * (founder, 2026-09-21, pass 17.) The greeting fix landed on the CHAT path
 * and the screenshot still showed a "Hi" task at NEEDS YOU. This lane
 * established, on the real client code, which door the Shadow tab composer
 * goes through: the answer was that it depends on whether + Delegate is
 * open, and that ONE OF THE TWO DOORS TOOK NO SHADOW TURN AT ALL -- the
 * new-task box posted straight to the create endpoint and then to
 * `start_now`, so "Hi" became a running task nobody had judged.
 *
 * Blocks 2 and 3 now pin the FIX, not the bug: both doors ask Shadow, and
 * a task exists only because Shadow said there was work. Block 1 still
 * pins which box is live, and block 4 the door that was already right.
 *
 * Run: node test_shadow_hi_trace.js
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

function fresh(){
  const ctx = {
    console, Date, setTimeout: () => ({}), clearTimeout(){},
    scheduleRender(){},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {},
    /* both create paths guard on `typeof fetch` before doing anything */
    fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
    /* every network call this file makes, recorded rather than sent */
    posted: [],
    document: {
      addEventListener(t, fn){ (ctx.listeners[t] = ctx.listeners[t] || []).push(fn); },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  /* what Shadow answers this test's /api/shadow/chat with. The default is
     the greeting answer -- words and NO fence -- because that is the case
     the whole lane exists for; a block that wants a task sets it. */
  ctx.chatDoc = { reply: "Hi. What would you like done?" };
  ctx.shadowPost = async (url, body) => {
    ctx.posted.push({ url, body });
    const doc = (url === "/api/shadow/chat")
      ? ctx.chatDoc
      : { id: "m-new", objective: (body || {}).objective,
          state: "brief_confirm", done_when: [] };
    return { ok: true, status: 200, json: async () => doc };
  };
  ctx.loadGoalTranscript = () => {};
  ctx.goalMessages = () => [];
  ctx.goalTranscriptHtml = () => "";
  ctx.loadShadowHome = () => {};
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  ctx.S.shadowMissions = [];
  return ctx;
}

let ok = 0;
const pass = (s) => console.log("ok " + (++ok) + " " + s);

/* ══ 1. THE TWO DOORS, AND WHICH ONE IS LIVE ═══════════════════════════ */
{
  const ctx = fresh();
  ctx.S.shadowNewOpen = false;
  const closed = ctx.shadowHomeHtml();
  assert(/data-shhomecompose/.test(closed),
    "with + Delegate CLOSED the stage composer is the box");
  assert(!/data-shnewtalk/.test(closed) || /data-shnewhost/.test(closed),
    "and the new-task chat is not mounted inline");

  ctx.S.shadowNewOpen = true;
  const open = ctx.shadowHomeHtml();
  assert(!/data-shhomecompose/.test(open),
    "with + Delegate OPEN the stage composer is NOT rendered");
  assert(/data-shnewhost|data-shnewtalk/.test(open),
    "the new-task panel is the box instead");
  pass("+ Delegate swaps which composer the founder is typing into");
}

/* ══ 2. A GREETING IN THE NEW-TASK BOX MAKES NOTHING ══════════════════
   THIS IS THE PATH FROM THE SCREENSHOT, FIXED. shadowNewTalk used to go
   shadowCreateTask -> POST /api/shadow/missions -> act:start_now, taking
   the objective verbatim and never asking anyone. It now asks Shadow, and
   a greeting comes back as words with no fence -- so there is a reply to
   read and no task anywhere. */
{
  const ctx = fresh();
  ctx.S.shadowNewOpen = true;
  ctx.shadowNewChat().text = "Hi";
  return (async () => {
    const made = await ctx.shadowNewTalk();

    assert.strictEqual(ctx.posted.length, 1,
      "one request, not create-then-start: " + ctx.posted.map(p => p.url).join(", "));
    assert.strictEqual(ctx.posted[0].url, "/api/shadow/chat",
      "and it goes to Shadow, got " + ctx.posted[0].url);
    assert.strictEqual(ctx.posted[0].body.message, "Hi",
      "carrying the line the founder typed");

    /* the two endpoints that used to run, and must not */
    assert(!ctx.posted.some(p => p.url === "/api/shadow/missions"),
      "nothing is created for a greeting");
    assert(!ctx.posted.some(p => /\/act$/.test(p.url)),
      "and nothing is started");
    assert.strictEqual(made, null, "shadowNewTalk reports no task");
    assert.strictEqual((ctx.S.shadowMissions || []).length, 0,
      "the task list is untouched");

    /* what the founder gets instead: an answer, in the box they typed in */
    const thread = ctx.shadowNewChat().thread;
    /* joined, not deepStrictEqual: arrays built inside the vm realm carry a
       different Array prototype and never compare strictly equal here */
    assert.strictEqual(thread.map(t => t.who).join(","), "founder,shadow",
      "their line and Shadow's answer, in that order");
    assert.strictEqual(thread[1].text, "Hi. What would you like done?");
    assert.strictEqual(ctx.shadowNewChat().err, null,
      "no task is the ordinary outcome, not an error");
    assert.strictEqual(ctx.S.shadowNewOpen, true,
      "and the panel stays open so the next line can be the task");
    pass("a greeting in the new-task box is answered, and creates nothing");

    /* ══ 3. A REAL ASK OPENS A TASK -- BECAUSE SHADOW SAID SO ═══════════
       Same box, same one request. The task exists only because the reply
       carried a mission, and it lands as a brief for the founder to
       confirm: opened, not started. */
    const two = fresh();
    two.S.shadowNewOpen = true;
    two.chatDoc = { reply: "Opening that now.",
                    mission: { id: "m-africa", state: "brief_confirm",
                               objective: "Make me a 10-day Africa trip" } };
    two.shadowNewChat().text = "Make me a 10-day Africa trip";
    const m = await two.shadowNewTalk();

    assert.strictEqual(two.posted.length, 1, "still one request");
    assert.strictEqual(two.posted[0].url, "/api/shadow/chat");
    assert(m && m.id === "m-africa", "the task from Shadow's reply is returned");
    assert.strictEqual(m.state, "brief_confirm",
      "as a brief to confirm -- Start is still the founder's press");
    assert(!two.posted.some(p => /\/act$/.test(p.url)),
      "nothing auto-starts it");
    assert.strictEqual(two.S.shadowTaskSel, "m-africa",
      "and it takes focus");
    assert.strictEqual(two.S.shadowNewOpen, false, "the panel closes behind it");
    assert.strictEqual(two.S.shadowNewChat, null, "this chat is done");
    pass("a real ask opens a task, unstarted, because Shadow emitted one");

    /* ══ 4. THE OTHER DOOR IS THE ONE THAT WAS FIXED ════════════════════
       With + Delegate closed and no task selected the composer goes to
       /api/shadow/chat, where a mission exists only if Shadow emits a
       fence -- which is the path test_shadow_greeting.py covers. */
    const three = fresh();
    three.S.shadowNewOpen = false;
    three.S.shadowTaskSel = null;
    let sentToChat = null;
    three.sendToShadow = async (text) => { sentToChat = text; return null; };
    const box = { value: "Hi", dataset: { shhomecompose: "1" } };
    (three.listeners.keydown || []).forEach(fn => fn({
      key: "Enter", shiftKey: false, target: box,
      preventDefault(){}, stopPropagation(){} }));
    assert.strictEqual(sentToChat, "Hi",
      "the stage composer goes to Shadow, not to the create endpoint");
    assert(!three.posted.some(p => p.url === "/api/shadow/missions"),
      "and creates nothing by itself");
    pass("the stage composer asks Shadow; only that door was ever fixed");

    console.log("\nall Hi-trace checks passed");
  })();
}
