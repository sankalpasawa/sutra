#!/usr/bin/env node
/* test_shadow_v4_taskchat.js -- Shadow v5 (founder, 2026-09-18): + Delegate
   opens ONE box, "What do you have in mind?". There is no door to a form,
   no done-when field and no draft to approve. The form is not deleted: it
   is the opt-in path behind flags.shadow_form, which nothing in the UI
   turns on.

   CONTRACT CHANGE, 2026-09-21 (blocks 3-5). Enter used to BE "Create the
   task": POST /api/shadow/missions with the line verbatim as the objective,
   then start_now. That is how "Hi" became a running task -- nobody was ever
   asked whether there was work in the line. Enter is now one POST to
   /api/shadow/chat, and a task exists only when Shadow answers with a
   mission fence, as a brief the founder starts. The box is unchanged; what
   changed is that it now talks to Shadow like every other box does. See
   test_shadow_hi_trace.js for the greeting and the ask side by side.

   Run: node test_shadow_v4_taskchat.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }), setImmediate,
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;"),
    escAttr: (x) => String(x == null ? "" : x).replace(/"/g, "&quot;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {},
    document: { addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
      querySelectorAll(){ return []; } },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [];
  ctx.loadShadowHome = async () => { ctx.reloads = (ctx.reloads || 0) + 1; };
  return ctx;
}
const settle = () => new Promise(r => setImmediate(() => setImmediate(r)));
/* what /api/shadow/chat hands back when Shadow read work in the line: a
   brief, not a running task -- Start is the founder's press */
const DRAFT = { id: "m-9", objective: "top 10 fruits", template: "fix",
  state: "brief_confirm", target_mode: "new", turns_used: 0, max_turns: 12,
  version: 1, done_when: [] };

(async () => {
  /* 1. + Delegate opens the empty task chat, not the form */
  {
    const ctx = fresh();
    ctx.S.shadowNewOpen = true;
    const h = ctx.shadowHomeHtml();
    /* THE SCREEN CARRIES THE HOST, NOT THE PANEL. The compose box is mounted
       into [data-shnewhost] once and deliberately left out of the screen's
       markup, so that a background re-render cannot destroy the textarea the
       founder is typing into -- see test_shadow_delegate_focus.js. What the
       screen must still prove is that + Delegate opens the box and not the
       form; what is IN the box is asserted against the mounted markup. */
    assert(/data-shnewhost="1"/.test(h), "the task chat is the pane");
    const mounted = ctx.shadowNewTaskChatHtml();
    assert(/data-shnewchat="1"/.test(mounted), "and the mounted pane is the chat");
    assert(/What do you have in mind\?/.test(mounted), "the one guiding line");
    assert(/data-shnewtalk="1"/.test(mounted) && /data-shnewsend="1"/.test(mounted),
      "composer and send");
    assert(!/data-shnewpanel/.test(h), "no form");
    assert(!/data-shnewkind/.test(h), "no kind chips");
    assert(!/data-shnewdone/.test(h), "no done-when field");
    assert(!/data-shstart/.test(h), "nothing to start yet");
    assert(!/data-shformdoor/.test(h), "the form door is gone");
    assert(!/form instead/.test(h), "the form door is gone");
    console.log("ok 1 Delegate opens one box and nothing else");
  }

  /* 2. the form is the opt-in path */
  {
    const ctx = fresh();
    ctx.SETTINGS = { flags: { shadow_form: true } };
    ctx.S.shadowNewOpen = true;
    const h = ctx.shadowHomeHtml();
    assert(/data-shnewpanel="1"/.test(h) && /What should Shadow get done\?/.test(h), "the form still exists");
    assert(!/data-shnewchat/.test(h));
    console.log("ok 2 flags.shadow_form brings the form back, untouched");
  }

  /* 3. one line, Enter: it goes to Shadow, and Shadow's answer opens it */
  {
    const ctx = fresh();
    const calls = [];
    ctx.fetch = async (url, opts) => {
      calls.push({ url, body: JSON.parse(opts.body) });
      return { ok: true, status: 200,
               json: async () => ({ reply: "Opening that now.",
                                    mission: DRAFT }) };
    };
    ctx.listeners.click({ target: { dataset: { shdelegate: "1" }, closest: () => null } });
    assert.strictEqual(ctx.S.shadowNewOpen, true);
    ctx.listeners.keydown({ key: "Enter", shiftKey: false, preventDefault(){},
      target: { dataset: { shnewtalk: "1" }, value: "top 10 fruits" } });
    await settle(); await settle(); await settle();
    assert.strictEqual(calls.length, 1, "one turn, not a create and a start");
    assert(/\/api\/shadow\/chat$/.test(calls[0].url), calls[0].url);
    assert.strictEqual(calls[0].body.message, "top 10 fruits",
      "the line the founder typed is what Shadow is asked");
    assert.strictEqual(calls[0].body.intake, true,
      "and it is asked as intake -- this box is where work is opened");
    assert(!calls.some(c => /\/act$/.test(c.url)),
      "nothing is started behind the founder");
    assert.strictEqual(ctx.S.shadowNewOpen, false, "the box closes");
    assert.strictEqual(ctx.S.shadowTaskSel, "m-9", "the new task takes focus");
    assert.strictEqual(ctx.S.shadowNewChat, null, "the box is forgotten");
    console.log("ok 3 one line is a Shadow turn, and its task takes focus");
  }

  /* 4. a line with no work in it leaves no task -- and says something */
  {
    const ctx = fresh();
    const calls = [];
    ctx.fetch = async (url, opts) => {
      calls.push({ url, body: JSON.parse(opts.body) });
      return { ok: true, status: 200,
               json: async () => ({ reply: "Hi. What would you like done?" }) };
    };
    ctx.S.shadowNewOpen = true;
    ctx.shadowNewChat().text = "Hi";
    const m = await ctx.shadowNewTalk();
    await settle();
    assert.strictEqual(m, null, "no mission in the reply, no task");
    assert.strictEqual(calls.length, 1, "and no create was attempted");
    assert.strictEqual(ctx.S.shadowNewOpen, true, "the box stays open");
    const mounted = ctx.shadowNewTaskChatHtml();
    assert(/What would you like done/.test(mounted), "Shadow's answer is shown");
    assert(!/data-shstart/.test(ctx.shadowHomeHtml()), "no draft card to approve");
    assert(!/data-shnewdone/.test(mounted), "no done-when field, ever");
    assert(!/data-shformdoor/.test(mounted), "no door to the form");
    console.log("ok 4 a line with no work in it opens nothing");
  }

  /* 5. Shadow unreachable: the line stays in the thread, the error is said, nothing starts */
  {
    const ctx = fresh();
    ctx.fetch = async () => ({ ok: false, status: 503, json: async () => ({}) });
    ctx.S.shadowNewOpen = true;
    ctx.shadowNewChat().text = "top 10 fruits";
    await ctx.shadowNewTalk();
    const h = ctx.shadowHomeHtml();
    /* the thread and the error are inside the MOUNTED panel, not the screen
       markup -- the screen only carries the host it is mounted into */
    const mounted = ctx.shadowNewTaskChatHtml();
    assert(/top 10 fruits/.test(mounted), "the founder's line is kept");
    assert(/Shadow could not answer \(503\)/.test(mounted),
      "the error is said, with the status in it");
    assert(!/data-shstart/.test(h), "no card");
    assert.strictEqual(ctx.S.shadowNewOpen, true, "the box stays open to say so");
    console.log("ok 5 a failed turn is honest and loses nothing");
  }

  /* 6. an empty line sends nothing; Shift+Enter is not a send */
  {
    const ctx = fresh();
    let calls = 0;
    ctx.fetch = async () => { calls++; return { ok: true, status: 200, json: async () => ({}) }; };
    ctx.S.shadowNewOpen = true;
    ctx.listeners.keydown({ key: "Enter", shiftKey: false, preventDefault(){},
      target: { dataset: { shnewtalk: "1" }, value: "   " } });
    ctx.listeners.keydown({ key: "Enter", shiftKey: true, preventDefault(){},
      target: { dataset: { shnewtalk: "1" }, value: "x" } });
    await settle();
    assert.strictEqual(calls, 0);
    console.log("ok 6 empty and Shift+Enter send nothing");
  }

  /* 7. the door is gone: nothing in the UI turns the form on */
  {
    const ctx = fresh();
    ctx.S.shadowNewOpen = true;
    assert(!/data-shformdoor/.test(ctx.shadowNewTaskChatHtml()), "the door is gone");
    assert.strictEqual(ctx.shadowFormOn(), false, "the box is the only way in");
    ctx.listeners.click({ target: { dataset: { shformdoor: "1" }, closest: () => null } });
    assert.strictEqual(ctx.shadowFormOn(), false, "and a stale door cannot open it");
    assert.strictEqual(ctx.S.shadowNewOpen, true, "nor close the box");
    ctx.SETTINGS = { flags: { shadow_form: true } };
    assert.strictEqual(ctx.shadowFormOn(), true, "only the founder's own flag does");
    console.log("ok 7 the form door is removed; only flags.shadow_form remains");
  }

  console.log("test_shadow_v4_taskchat: all ok");
})().catch(e => { console.error(e); process.exit(1); });
