#!/usr/bin/env node
/* test_shadow_costs.js -- what a task cost and the monthly spending limit
   (founder, 2026-10-08, from Paperclip). The task header shows its cost; the
   list shows a line at 80% and at the limit; a task paused on the limit says
   why with Continue; settings carries the limit and saves it.

   Run: node test_shadow_costs.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }), setImmediate, Promise,
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {}, posts: [],
    document: { addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {}, click(){} }; },
      body: { appendChild(){} },
      querySelector(sel){ return sel === "[data-shmonthbudget]" ? ctx.input : null; },
      querySelectorAll(){ return []; } },
  };
  ctx.input = { value: "" };
  ctx.scheduleRender = () => {};
  ctx.fetch = async (url, opts) => {
    ctx.posts.push({ url, body: JSON.parse((opts && opts.body) || "null") });
    const b = ctx.posts[ctx.posts.length - 1].body;
    if (b && b.monthly_usd === "bad")
      return { ok: false, status: 400, json: async () => ({ detail: "the budget is an amount in dollars" }) };
    return { ok: true, status: 200, json: async () => ({ budget_usd: b && b.monthly_usd,
      spent_usd: 1.5, level: "ok" }) };
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  return ctx;
}
const settle = () => new Promise(r => setImmediate(() => setImmediate(r)));

let n = 0;
async function test(name, fn){ await fn(); n++; console.log("ok   " + name); }

(async () => {
  await test("a task shows what it cost; nothing under half a cent", () => {
    const ctx = fresh();
    assert(/class="shwcost"[^>]*>\$0\.42</.test(ctx.shadowTaskCostHtml({ cost_usd: 0.4211 })));
    assert(/\$12</.test(ctx.shadowTaskCostHtml({ cost_usd: 12.4 })));
    assert.strictEqual(ctx.shadowTaskCostHtml({ cost_usd: 0.001 }), "");
    assert.strictEqual(ctx.shadowTaskCostHtml({}), "");
  });

  await test("the list says it at 80% and at the limit, and never without a limit", () => {
    const ctx = fresh();
    assert.strictEqual(ctx.shadowBudgetBannerHtml(), "");
    ctx.S.shadowBudget = { budget_usd: null, spent_usd: 50, level: "none" };
    assert.strictEqual(ctx.shadowBudgetBannerHtml(), "");
    ctx.S.shadowBudget = { budget_usd: 10, spent_usd: 3, level: "ok" };
    assert.strictEqual(ctx.shadowBudgetBannerHtml(), "");
    ctx.S.shadowBudget = { budget_usd: 10, spent_usd: 8.2, level: "warn" };
    assert(/You've used \$8\.20 of your \$10 monthly limit/.test(ctx.shadowBudgetBannerHtml()));
    ctx.S.shadowBudget = { budget_usd: 10, spent_usd: 10.4, level: "over" };
    assert(/Spending limit reached.*New tasks won't start/.test(ctx.shadowBudgetBannerHtml()));
  });

  await test("a task paused on the limit says why, reads NEEDS YOU, and has Continue", () => {
    const ctx = fresh();
    const m = { id: "m-b1", state: "paused", pause_reason: "budget_spent" };
    const h = ctx.shadowBudgetPauseHtml(m);
    assert(/spending limit is used up/.test(h));
    assert(/data-shact="resume" data-shmid="m-b1">Continue</.test(h));
    assert.strictEqual(ctx.shadowTaskFaceFor(m).label, "NEEDS YOU");
    assert.strictEqual(ctx.shadowBudgetPauseHtml({ id: "x", state: "paused",
      pause_reason: "app_restart" }), "");
  });

  await test("the pane draws the notice beside the other task notices", () => {
    const i = home.indexOf("shadowQuietHtml(sel)}");
    const j = home.indexOf("shadowBudgetPauseHtml(sel)}");
    const k = home.indexOf("shadowInterventionHtml(sel)}");
    assert(i > 0 && j > i && k > j);
  });

  await test("settings: the limit and this month's spend, saved by POST", async () => {
    const ctx = fresh();
    ctx.S.shadowBudget = { budget_usd: 20, spent_usd: 4.25, level: "ok" };
    const h = ctx.shadowSetTasksHtml({ tasks: { running_at_once: 3, turn_budgets: {} } });
    assert(/Monthly spending limit/.test(h) && /value="20"/.test(h));
    assert(/\$4\.25 spent this month/.test(h));
    ctx.input.value = "35";
    ctx.listeners.click({ target: { dataset: { shmonthbudgetsave: "1" } } });
    await settle();
    const p = ctx.posts.filter(x => x.url === "/api/shadow/budget");
    assert.deepStrictEqual(p[0].body, { monthly_usd: 35 });
    assert.strictEqual(ctx.S.shadowBudget.budget_usd, 35);
    ctx.input.value = "";
    await ctx.shadowSaveMonthBudget();
    assert.deepStrictEqual(ctx.posts[ctx.posts.length - 1].body, { monthly_usd: null },
      "empty clears the limit");
  });

  await test("junk is refused on the row and never clears the limit", async () => {
    const ctx = fresh();
    ctx.S.shadowBudget = { budget_usd: 20, spent_usd: 1, level: "ok" };
    ctx.input.value = "abc";
    await ctx.shadowSaveMonthBudget();
    assert.strictEqual(ctx.posts.filter(x => x.url === "/api/shadow/budget").length, 0,
      "nothing was sent");
    assert.strictEqual(ctx.S.shadowBudget.budget_usd, 20, "the limit stands");
    assert(/Enter an amount in dollars/.test(
      ctx.shadowSetTasksHtml({ tasks: { running_at_once: 3, turn_budgets: {} } })));
  });

  await test("the server's refusal is said on the row", async () => {
    const ctx = fresh();
    ctx.S.shadowBudget = { budget_usd: 20, spent_usd: 1, level: "ok" };
    ctx.input.value = "-5";
    ctx.fetch = async () => ({ ok: false, status: 400,
      json: async () => ({ detail: "the budget can't be negative" }) });
    await ctx.shadowSaveMonthBudget();
    assert(/the budget can&#39;t be negative|the budget can't be negative/.test(
      ctx.shadowSetTasksHtml({ tasks: { running_at_once: 3, turn_budgets: {} } })));
  });

  await test("its style uses tokens only", () => {
    const block = css.slice(css.indexOf(".shwcost{"));
    const rules = block.slice(0, block.indexOf(".shbudgetin{") + 30);
    assert(!/#[0-9a-fA-F]{3,6}\b|rgba?\(/.test(rules), "no colour literal");
  });

  console.log("test_shadow_costs.js: " + n + " passed");
})().catch(e => { console.error(e); process.exit(1); });
