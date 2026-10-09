#!/usr/bin/env node
/* test_shadow_results.js -- "What it made" on a task (founder, 2026-10-09,
   from Paperclip). Shown for a task that has started; loaded on Show; each
   file has an Open link to the task's own file route; where the files are is
   said in words; an error offers Try again; a draft shows nothing.

   Run: node test_shadow_results.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");

function fresh(answer){
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }), setImmediate, Promise,
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {}, gets: [],
    document: { addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {}, click(){} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
      querySelectorAll(){ return []; } },
  };
  ctx.scheduleRender = () => {};
  ctx.fetch = async (url) => { ctx.gets.push(url);
    return answer || { ok: true, status: 200, json: async () => ({
      where: "copy", note: "", files: [
        { path: "docs/joy plan.md", name: "joy plan.md", folder: "docs",
          bytes: 2048, kind: "text", exists: true },
        { path: "gone.txt", name: "gone.txt", folder: "", bytes: null,
          kind: "text", exists: false }] }) }; };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  return ctx;
}
const settle = () => new Promise(r => setImmediate(() => setImmediate(r)));
const M = { id: "m-r1", state: "running" };

let n = 0;
async function test(name, fn){ await fn(); n++; console.log("ok   " + name); }

(async () => {
  await test("a started task offers Show; a draft or an unstarted one shows nothing", () => {
    const ctx = fresh();
    assert(/What it made/.test(ctx.shadowResultsHtml(M)));
    assert(/data-shresults="m-r1"[^>]*>Show</.test(ctx.shadowResultsHtml(M)));
    assert.strictEqual(ctx.shadowResultsHtml({ id: "x", state: "draft" }), "");
    assert.strictEqual(ctx.shadowResultsHtml({ id: "x", state: "brief_confirm" }), "");
  });

  await test("Show loads the task's list, and says where the files are", async () => {
    const ctx = fresh();
    ctx.listeners.click({ target: { dataset: { shresults: "m-r1" } } });
    await settle();
    assert.deepStrictEqual(ctx.gets.filter(u => /results/.test(u)),
      ["/api/shadow/tasks/m-r1/results"]);
    const h = ctx.shadowResultsHtml(M);
    assert(/2 files, in its own copy, not in your project yet/.test(h));
    assert(/joy plan\.md/.test(h) && /2 KB/.test(h));
    assert(/href="\/api\/shadow\/tasks\/m-r1\/results\/file\?path=docs%2Fjoy%20plan\.md"/.test(h),
      "Open is the task's own route, path encoded");
    assert(/not there/.test(h), "a file that is gone says so, no link");
    assert.strictEqual((h.match(/>Open</g) || []).length, 1);
  });

  await test("nothing yet says the server's note", async () => {
    const ctx = fresh({ ok: true, status: 200, json: async () =>
      ({ where: "project", files: [], note: "No files yet." }) });
    await ctx.shadowLoadResults("m-r1");
    assert(/No files yet\./.test(ctx.shadowResultsHtml(M)));
  });

  await test("a failure says so and offers Try again", async () => {
    const ctx = fresh({ ok: false, status: 404, json: async () => ({ detail: "no such task" }) });
    await ctx.shadowLoadResults("m-r1");
    const h = ctx.shadowResultsHtml(M);
    assert(/no such task/.test(h) && />Try again</.test(h));
  });

  await test("the pane draws it after the task's copy notice", () => {
    const i = home.indexOf("shadowWorkspaceHtml(sel)}");
    const j = home.indexOf("shadowResultsHtml(sel)}");
    assert(i > 0 && j > i);
  });

  await test("its style uses tokens only", () => {
    const block = css.slice(css.indexOf(".shres{"));
    const rules = block.slice(0, block.indexOf("@media (max-width:640px){.shresrow"));
    assert(!/#[0-9a-fA-F]{3,6}\b|rgba?\(/.test(rules), "no colour literal");
  });

  console.log("test_shadow_results.js: " + n + " passed");
})().catch(e => { console.error(e); process.exit(1); });
