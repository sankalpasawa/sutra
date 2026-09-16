#!/usr/bin/env node
/* test_shadow_v4_now.js -- Shadow v4 step 14 (C4, ADR-043): the Now page
   carries the box "What do you have in mind?". One message goes to the Now
   chat; the reply is Shadow's prose and one draft card per task it split
   out; Start each, or Start all. The needs-you cards stay render-only.

   Run: node test_shadow_v4_now.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const html = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
assert(/14-needs-you\.js/.test(html), "panel.html loads the Now module");
const now = fs.readFileSync(path.join(__dirname, "static", "js", "14-needs-you.js"), "utf8");
const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }), setImmediate,
    setInterval: () => 1, clearInterval: () => {},
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;"),
    SCREENS: {}, TITLES: {}, S: { screen: "now" }, listeners: {}, nudges: [],
    document: { addEventListener(t, fn){ (ctx.listeners[t] = ctx.listeners[t] || []).push(fn); },
      createElement(){ const el = { setAttribute(){}, remove(){}, dataset: {}, textContent: "" }; return el; },
      body: { appendChild(el){ ctx.nudges.push(el.textContent); } },
      querySelector(){ return null; }, querySelectorAll(){ return []; } },
  };
  vm.createContext(ctx);
  vm.runInContext(now, ctx);
  vm.runInContext(overlay, ctx);
  ctx.fire = (type, ev) => (ctx.listeners[type] || []).forEach(fn => fn(ev));
  return ctx;
}
const settle = () => new Promise(r => setImmediate(() => setImmediate(r)));
const D = (id, objective) => ({ id, objective, template: "research", state: "brief_confirm",
  target_mode: "new", turns_used: 0, max_turns: 12, version: 1, done_when: [] });

(async () => {
  /* 1. the box is on the page, with and without needs-you cards */
  {
    const ctx = fresh();
    ctx.S.needsYou = [];
    const empty = ctx.SCREENS.now();
    assert(/Nothing needs you right now/.test(empty), "empty state kept");
    assert(/data-nystart/.test(empty), "the door to Shadow kept");
    assert(/data-nyask="1"/.test(empty) && /What do you have in mind\?/.test(empty), "the box");
    ctx.S.needsYou = [{ item_id: "m-1", producer: "shadow", kind: "needs_decision",
      title: "Approve the push", why_now: "floor" }];
    const full = ctx.SCREENS.now();
    assert(full.indexOf("nyfeed") < full.indexOf("data-nyask"), "cards first, then the box");
    console.log("ok 1 the box is on Now, after the cards or alone");
  }

  /* 2. Enter sends one message to the Now chat; many fences draw many cards and Start all */
  {
    const ctx = fresh();
    const calls = [];
    ctx.fetch = async (url, opts) => {
      calls.push({ url, body: JSON.parse(opts.body) });
      return { ok: true, status: 200, json: async () => ({
        reply: "Three tasks. **Start** when ready.",
        missions: [D("m-a", "Fix the login bug"), D("m-b", "Research SSO vendors"),
                   D("m-c", "Draft the pricing page")],
        mission: D("m-a", "Fix the login bug") }) };
    };
    ctx.S.needsYou = [];
    ctx.fire("keydown", { key: "Enter", shiftKey: false, preventDefault(){},
      target: { dataset: { nycomp: "1" }, value: "fix login, research SSO, draft pricing" } });
    await settle(); await settle();
    assert.strictEqual(calls.length, 1);
    assert(/\/api\/shadow\/chat$/.test(calls[0].url), calls[0].url);
    assert.deepStrictEqual(calls[0].body, { message: "fix login, research SSO, draft pricing" });
    const h = ctx.SCREENS.now();
    assert(/Three tasks\./.test(h), "Shadow's reply");
    assert.strictEqual((h.match(/data-shstart="m-[abc]"/g) || []).length, 3, "three draft cards");
    assert(/Fix the login bug/.test(h) && /Draft the pricing page/.test(h));
    assert(/data-nystartall="1"/.test(h), "Start all");
    assert(/>READY</.test(h) && !/>brief_confirm</.test(h), "cards speak founder language, never a raw state");
    assert.strictEqual(ctx.nowChat().text, "", "the box is cleared after a send");
    console.log("ok 2 one message, three drafts, Start all");
  }

  /* 3. one fence: one card, no Start all; the reply alone is also fine */
  {
    const ctx = fresh();
    ctx.fetch = async () => ({ ok: true, status: 200,
      json: async () => ({ reply: "One task.", missions: [D("m-1", "Top 10 fruits")], mission: D("m-1", "Top 10 fruits") }) });
    ctx.S.needsYou = [];
    ctx.nowChat().text = "top 10 fruits";
    await ctx.nowSend();
    const h = ctx.SCREENS.now();
    assert.strictEqual((h.match(/data-shstart=/g) || []).length, 1);
    assert(!/data-nystartall/.test(h), "no Start all for one draft");
    ctx.fetch = async () => ({ ok: true, status: 200, json: async () => ({ reply: "Just talk." }) });
    ctx.nowChat().text = "hello";
    await ctx.nowSend();
    const h2 = ctx.SCREENS.now();
    assert(/Just talk\./.test(h2) && !/data-shstart=/.test(h2), "a reply with no task draws no card");
    console.log("ok 3 one draft has no Start all; prose alone draws no card");
  }

  /* 4. Start all starts every draft through the existing action and clears the drafts */
  {
    const ctx = fresh();
    const acts = [];
    ctx.shadowMissionAct = async (id, act) => { acts.push([id, act]); return { id, state: "running" }; };
    ctx.S.needsYou = [];
    ctx.nowChat().missions = [D("m-a", "A"), D("m-b", "B")];
    ctx.nowChat().reply = "Two tasks.";
    ctx.fire("click", { target: { dataset: { nystartall: "1" }, closest: () => null } });
    await settle(); await settle();
    assert.deepStrictEqual(acts, [["m-a", "start_now"], ["m-b", "start_now"]]);
    const h = ctx.SCREENS.now();
    assert(!/data-shstart=/.test(h) && !/data-nystartall/.test(h), "drafts cleared");
    assert(ctx.nudges.some(n => /Started 2 tasks/.test(n)), "says what started");
    console.log("ok 4 Start all starts each draft and clears them");
  }

  /* 5. Start on one card removes that draft from the box; the others stay */
  {
    const ctx = fresh();
    const acts = [];
    ctx.shadowMissionAct = async (id, act) => { acts.push([id, act]); return { id }; };
    ctx.nowChat().missions = [D("m-a", "A"), D("m-b", "B")];
    ctx.fire("click", { target: { dataset: { shstart: "m-a" }, closest: () => null } });
    await settle();
    assert.deepStrictEqual(ctx.nowChat().missions.map(m => m.id), ["m-b"]);
    assert.deepStrictEqual(acts, [["m-a", "start_now"]], "the overlay's own hook started it");
    console.log("ok 5 a single Start leaves the box with the rest");
  }

  /* 6. Shadow unreachable: the words stay, the error is said */
  {
    const ctx = fresh();
    ctx.fetch = async () => ({ ok: false, status: 503, json: async () => ({}) });
    ctx.S.needsYou = [];
    ctx.nowChat().text = "top 10 fruits";
    await ctx.nowSend();
    const h = ctx.SCREENS.now();
    assert(/could not take that \(503\)/.test(h));
    assert(/top 10 fruits/.test(h), "the founder's words are not lost");
    console.log("ok 6 a failed send is honest and loses nothing");
  }

  console.log("test_shadow_v4_now: all ok");
})().catch(e => { console.error(e); process.exit(1); });
