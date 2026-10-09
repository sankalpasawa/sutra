#!/usr/bin/env node
/* test_shadow_workspace.js -- a task's own copy of the project, on screen
   (founder, 2026-10-08, option B). Running: one line saying so. Kept: what
   was added. Ended unfinished with changes, or clashing with the founder's
   own edits: the task stays under WAITING ON YOU as KEEP? with Keep (or Try
   again) and Throw away, which post to the workspace route.

   Run: node test_shadow_workspace.js */
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
      body: { appendChild(){} }, querySelector(){ return null; },
      querySelectorAll(){ return []; } },
  };
  ctx.scheduleRender = () => {};
  ctx.fetch = async (url, opts) => {
    const body = JSON.parse((opts && opts.body) || "null");
    ctx.posts.push({ url, body });
    return { ok: true, status: 200, json: async () => (
      { workspace: { state: body && body.action === "keep" ? "kept" : "discarded",
                     files: ["a.txt"], kept_by: "founder" } }) };
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  return ctx;
}
const settle = () => new Promise(r => setImmediate(() => setImmediate(r)));
const M = (state, ws) => ({ id: "m-w1", state, workspace: ws });

let n = 0;
async function test(name, fn){ await fn(); n++; console.log("ok   " + name); }

(async () => {
  await test("running in its own copy says so once; nothing when there is no copy", () => {
    const ctx = fresh();
    assert(/its own copy of your project/.test(
      ctx.shadowWorkspaceHtml(M("running", { state: "active" }))));
    assert.strictEqual(ctx.shadowWorkspaceHtml(M("running", null)), "");
    assert.strictEqual(ctx.shadowWorkspaceHtml(M("done", { state: "empty", files: [] })), "");
  });

  await test("kept: what was added, and that the checks passed", () => {
    const ctx = fresh();
    const h = ctx.shadowWorkspaceHtml(M("done", { state: "kept", kept_by: "auto",
      files: ["a.txt", "b.txt"] }));
    assert(/2 files added to your project — the checks passed/.test(h));
    assert(/title="a\.txt\nb\.txt"/.test(h), "the files on hover");
    assert(!/<button/.test(h), "nothing to decide");
  });

  await test("unfinished with changes: KEEP? under WAITING ON YOU, Keep and Throw away", () => {
    const ctx = fresh();
    const m = M("stopped", { state: "pending", files: ["a.txt"] });
    const h = ctx.shadowWorkspaceHtml(m);
    assert(/changed 1 file in its copy but didn't finish/.test(h));
    assert(/data-shws="keep" data-shmid="m-w1"[^>]*>Keep</.test(h));
    assert(/data-shws="discard"/.test(h));
    assert.strictEqual(ctx.shadowTaskFaceFor(m).label, "KEEP?");
    assert.strictEqual(ctx.shadowTaskSection(m), "wait");
    assert(ctx.shadowTaskIsActive(m, []), "it stays in the list until decided");
  });

  await test("a clash says why, offers Try again, and stays visible even when done", () => {
    const ctx = fresh();
    const m = M("done", { state: "clash", files: ["a.txt", "b.txt"] });
    const h = ctx.shadowWorkspaceHtml(m);
    assert(/same lines changed in your project too/.test(h));
    assert(/>Try again</.test(h));
    assert(ctx.shadowTaskIsActive(m, []));
    assert.strictEqual(ctx.shadowTaskFaceFor(m).label, "KEEP?");
  });

  await test("once decided it is an ordinary finished task again", () => {
    const ctx = fresh();
    const m = M("done", { state: "kept", files: ["a.txt"] });
    assert.strictEqual(ctx.shadowTaskFaceFor(m).label, "DONE");
    assert.strictEqual(ctx.shadowTaskSection(m), "done");
    const gone = M("stopped", { state: "discarded", files: [] });
    assert.notStrictEqual(ctx.shadowTaskFaceFor(gone).label, "KEEP?");
  });

  await test("Keep posts to the task's workspace route and redraws what came back", async () => {
    const ctx = fresh();
    ctx.S.shadowMissions = [M("stopped", { state: "pending", files: ["a.txt"] })];
    ctx.listeners.click({ target: { dataset: { shws: "keep", shmid: "m-w1" } } });
    await settle();
    const p = ctx.posts.filter(x => /\/workspace$/.test(x.url));
    assert.strictEqual(p[0].url, "/api/shadow/tasks/m-w1/workspace");
    assert.deepStrictEqual(p[0].body, { action: "keep" });
    assert.strictEqual(ctx.S.shadowMissions[0].workspace.state, "kept");
    assert.strictEqual(ctx.S.shadowWsBusy, null);
  });

  await test("the pane draws it with the other task notices", () => {
    const i = home.indexOf("shadowBudgetPauseHtml(sel)}");
    const j = home.indexOf("shadowWorkspaceHtml(sel)}");
    assert(i > 0 && j > i);
  });

  await test("its style uses tokens only", () => {
    const block = css.slice(css.indexOf(".shws{"));
    const rules = block.slice(0, block.indexOf(".shwsacts{") + 30);
    assert(!/#[0-9a-fA-F]{3,6}\b|rgba?\(/.test(rules), "no colour literal");
  });

  console.log("test_shadow_workspace.js: " + n + " passed");
})().catch(e => { console.error(e); process.exit(1); });
