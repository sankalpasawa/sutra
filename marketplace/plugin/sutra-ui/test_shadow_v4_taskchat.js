#!/usr/bin/env node
/* test_shadow_v4_taskchat.js -- Shadow v4 step 13 (C5, ADR-043): + Delegate
   opens an EMPTY task chat. One line, Enter -> POST /api/shadow/tasks -> the
   reply and a READY draft card; more lines -> POST /api/shadow/tasks/{id}/chat;
   Start is the existing action and puts the task in focus. The form is not
   deleted: it is the opt-in path behind flags.shadow_form.

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
const DRAFT = { id: "m-9", objective: "Top 10 fruits in the market, by usage",
  template: "research", state: "brief_confirm", target_mode: "new",
  turns_used: 0, max_turns: 12, version: 2,
  done_when: [{ tier: "founder_confirm", check: "a table by usage" }] };

(async () => {
  /* 1. + Delegate opens the empty task chat, not the form */
  {
    const ctx = fresh();
    ctx.S.shadowNewOpen = true;
    const h = ctx.shadowHomeHtml();
    assert(/data-shnewchat="1"/.test(h), "the task chat is the pane");
    assert(/What do you have in mind\?/.test(h), "the one guiding line");
    assert(/data-shnewtalk="1"/.test(h) && /data-shnewsend="1"/.test(h), "composer and send");
    assert(!/data-shnewpanel/.test(h), "no form");
    assert(!/data-shnewkind/.test(h), "no kind chips");
    assert(!/data-shnewdone/.test(h), "no done-when field");
    assert(!/data-shstart/.test(h), "nothing to start yet");
    console.log("ok 1 Delegate opens an empty task chat");
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

  /* 3. one line, Enter: the draft opens, the reply and the READY card show */
  {
    const ctx = fresh();
    const calls = [];
    ctx.fetch = async (url, opts) => {
      calls.push({ url, body: JSON.parse(opts.body) });
      return { ok: true, status: 200,
        json: async () => ({ mission: DRAFT, reply: "Research task. Done when you have a **table** by usage." }) };
    };
    ctx.listeners.click({ target: { dataset: { shdelegate: "1" }, closest: () => null } });
    assert.strictEqual(ctx.S.shadowNewOpen, true);
    ctx.listeners.keydown({ key: "Enter", shiftKey: false, preventDefault(){},
      target: { dataset: { shnewtalk: "1" }, value: "top 10 fruits" } });
    await settle(); await settle();
    assert.strictEqual(calls.length, 1);
    assert(/\/api\/shadow\/tasks$/.test(calls[0].url), calls[0].url);
    assert.deepStrictEqual(calls[0].body, { message: "top 10 fruits" });
    const h = ctx.shadowHomeHtml();
    assert(/shmine[\s\S]*top 10 fruits/.test(h), "the founder's line in the thread");
    assert(/shshadow[\s\S]*Research task\./.test(h), "Shadow's reply in the thread");
    assert(/data-shstart="m-9"/.test(h), "the draft card with Start");
    assert(/READY/.test(h), "the card reads READY");
    assert(/Top 10 fruits in the market, by usage/.test(h), "the card carries the sharpened objective");
    assert.strictEqual(ctx.reloads, 1, "the list is re-read so the draft row appears");
    console.log("ok 3 the first line opens the draft and shows the card");
  }

  /* 4. the next line talks to THAT task, and Start closes the chat into focus */
  {
    const ctx = fresh();
    const calls = [];
    ctx.fetch = async (url, opts) => {
      calls.push({ url, body: JSON.parse(opts.body) });
      return { ok: true, status: 200, json: async () => ({ mission: DRAFT, reply: "Sharper." }) };
    };
    const acts = [];
    ctx.shadowMissionAct = async (id, act) => { acts.push([id, act]); return { id, state: "running" }; };
    ctx.S.shadowNewOpen = true;
    ctx.shadowNewChat().mission = DRAFT;
    ctx.listeners.input({ target: { dataset: { shnewtalk: "1" }, value: "India only" } });
    ctx.listeners.click({ target: { dataset: { shnewsend: "1" }, closest: () => null } });
    await settle(); await settle();
    assert(/\/api\/shadow\/tasks\/m-9\/chat$/.test(calls[0].url), calls[0].url);
    assert.deepStrictEqual(calls[0].body, { message: "India only" });
    ctx.listeners.click({ target: { dataset: { shstart: "m-9" }, closest: () => null } });
    await settle();
    assert.deepStrictEqual(acts, [["m-9", "start_now"]], "Start is the existing action");
    assert.strictEqual(ctx.S.shadowNewOpen, false, "the task chat closes");
    assert.strictEqual(ctx.S.shadowTaskSel, "m-9", "the task is in focus");
    assert.strictEqual(ctx.S.shadowNewChat, null);
    console.log("ok 4 later lines reach the task; Start closes into focus");
  }

  /* 5. Shadow unreachable: the line stays in the thread, the error is said, nothing starts */
  {
    const ctx = fresh();
    ctx.fetch = async () => ({ ok: false, status: 503, json: async () => ({}) });
    ctx.S.shadowNewOpen = true;
    ctx.shadowNewChat().text = "top 10 fruits";
    await ctx.shadowNewTalk();
    const h = ctx.shadowHomeHtml();
    assert(/top 10 fruits/.test(h), "the founder's line is kept");
    assert(/could not take that \(503\)/.test(h), "the error is said");
    assert(!/data-shstart/.test(h), "no card");
    console.log("ok 5 a failed open is honest and loses nothing");
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

  /* 7. the form is one click away (nothing removed): the door under the chat
        box turns the form on for this open; Cancel turns it back off */
  {
    const ctx = fresh();
    ctx.S.shadowNewOpen = true;
    assert(/data-shformdoor="1"/.test(ctx.shadowNewTaskChatHtml()), "the door is drawn");
    assert.strictEqual(ctx.shadowFormOn(), false, "chat first");
    ctx.listeners.click({ target: { dataset: { shformdoor: "1" }, closest: () => null } });
    assert.strictEqual(ctx.shadowFormOn(), true, "the door opens the form");
    ctx.listeners.click({ target: { dataset: { shnewcancel: "1" }, closest: () => null } });
    assert.strictEqual(ctx.shadowFormOn(), false, "Cancel closes it again");
    console.log("ok 7 the form stays one click away");
  }

  console.log("test_shadow_v4_taskchat: all ok");
})().catch(e => { console.error(e); process.exit(1); });
