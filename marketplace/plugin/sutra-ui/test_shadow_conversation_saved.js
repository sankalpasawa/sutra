#!/usr/bin/env node
/* test_shadow_conversation_saved.js -- a reload never loses a Shadow
   conversation (founder, 2026-10-09: the reply and the screenshot were gone
   after a refresh). The browser names the conversation so the server keeps
   it; a reload draws the screenshots again and says when Shadow is still
   answering; the browser does not save a second copy of what the server
   already saved.

   Run: node test_shadow_conversation_saved.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

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
  ctx.fetch = async () => ({ ok: true, status: 200, json: async () => ({}) });
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  ctx.shadowPost = async (url, body) => { ctx.posts.push({ url, body });
    return { ok: true, status: 200, json: async () => ({ reply: "ok", saved: true }) }; };
  return ctx;
}
const ago = (min) => new Date(Date.now() - min * 60000).toISOString();
const REC = (extra) => Object.assign({ id: "shc-abc123", mission_id: null,
  created_at: ago(5), messages: [
    { who: "founder", text: "make it better", ts: ago(5),
      images: [{ id: "img-0000000000000001", name: "ui.png", kind: "image" }] }] }, extra || {});

let n = 0;
async function test(name, fn){ await fn(); n++; console.log("ok   " + name); }

(async () => {
  await test("a reload draws the screenshot with the line again", () => {
    const ctx = fresh();
    ctx.shadowRestoreConversations([REC()]);
    const row = ctx.S.shadowThreads["shc-abc123"][0];
    assert.strictEqual(row.images[0].name, "ui.png");
    assert(/shimg/.test(ctx.shadowImagesHtml(row.images)));
  });

  await test("a reload while Shadow answers says so", () => {
    const ctx = fresh();
    ctx.shadowRestoreConversations([REC({ pending_since: ago(2) })]);
    const rows = ctx.S.shadowThreads["shc-abc123"];
    assert.strictEqual(rows.length, 2);
    assert(/Still working on this/.test(rows[1].text));
  });

  await test("past 20 minutes it says it did not finish", () => {
    const ctx = fresh();
    ctx.shadowRestoreConversations([REC({ pending_since: ago(25) })]);
    assert(/didn't finish answering/.test(ctx.S.shadowThreads["shc-abc123"][1].text));
  });

  await test("the reply replaces the waiting line when it lands", () => {
    const ctx = fresh();
    ctx.shadowRestoreConversations([REC({ pending_since: ago(1) })]);
    const done = REC();
    done.messages.push({ who: "shadow", text: "Here you go", ts: ago(0) });
    ctx.shadowRestoreConversations([done]);
    const rows = ctx.S.shadowThreads["shc-abc123"];
    assert.deepStrictEqual(rows.map(r => r.text), ["make it better", "Here you go"]);
  });

  await test("an answered conversation shows no waiting line", () => {
    const ctx = fresh();
    const done = REC({ pending_since: ago(1) });
    done.messages.push({ who: "shadow", text: "answered", ts: ago(0) });
    ctx.shadowRestoreConversations([done]);
    assert.strictEqual(ctx.S.shadowThreads["shc-abc123"].length, 2);
  });

  await test("a later line names its conversation so the server keeps it", async () => {
    const ctx = fresh();
    ctx.S.shadowThread = [];
    await ctx.sendToShadow("and the Shadow UI", { conversation_id: "shc-abc123" });
    const p = ctx.posts.filter(x => x.url === "/api/shadow/chat")[0];
    assert.strictEqual(p.body.conversation_id, "shc-abc123");
    assert(!p.body.conversation_new);
  });

  await test("the opening line names its conversation as new", () => {
    assert(/conversation_id: scopeKey,\s*conversation_new: true/.test(home));
  });

  await test("what the server saved is not saved again by the page", () => {
    assert(/if \(!serverSaved\) shadowConvSay\(scopeKey, text, "shadow", said\)/.test(home));
    assert(/if \(convId && !\(doc && doc\.saved\) && typeof shadowConvSay/.test(home));
  });

  console.log("test_shadow_conversation_saved.js: " + n + " passed");
})().catch(e => { console.error(e); process.exit(1); });
