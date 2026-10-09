#!/usr/bin/env node
/* test_shadow_tap.js -- tap to answer (founder, 2026-10-08, from Paperclip).
   A question with one yes/no or pick-one field is sent the moment the
   founder taps (No still opens "What should I change?" and waits for Send);
   a verdicts field draws approve / reject / later on each item; a form with
   several fields keeps its Send button and sends nothing on a tap.

   Run: node test_shadow_tap.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");

function fresh(intervention){
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }), setImmediate, Promise,
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {},
    document: { addEventListener(t, fn){ if (t === "click" && ctx.listeners.click) return;
        ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {}, click(){} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
      querySelectorAll(){ return []; } },
  };
  ctx.scheduleRender = () => {};
  ctx.fetch = async () => ({ ok: true, status: 200, json: async () => ({}) });
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  ctx.sent = [];
  ctx.shadowSendIntervention = (mid) => { ctx.sent.push(mid); };
  ctx.S.shadowMissions = [{ id: "m-t1", state: "blocked", intervention }];
  return ctx;
}
const tap = (ctx, key, opt, extra) => ctx.listeners.click({ target: { dataset:
  Object.assign({ shivmid: "m-t1", shivkey: key, shivopt: opt }, extra || {}) } });

const CHOICE = { id: "iv1", question: "Which region?", fields: [{ key: "region",
  type: "choice", label: "Region", options: [{ value: "eu", label: "EU" },
  { value: "us", label: "US" }] }] };
const YESNO = { id: "iv2", question: "Ship it?", fields: [{ key: "ok",
  type: "boolean", label: "Ship it" }] };
const TWO = { id: "iv3", question: "Two things", fields: [CHOICE.fields[0],
  { key: "note", type: "text", label: "Note" }] };
const VERD = { id: "iv4", question: "Which headlines?", fields: [{ key: "h",
  type: "verdicts", label: "Headlines", required: true,
  options: [{ value: "h1", label: "Rivers <run> deep" }, { value: "h2", label: "Ten facts" }] }] };

let n = 0;
function test(name, fn){ fn(); n++; console.log("ok   " + name); }

test("one pick-one field: the tap sends it, and there is no Send button", () => {
  const ctx = fresh(CHOICE);
  const m = ctx.S.shadowMissions[0];
  assert(!/data-shivsend=/.test(ctx.shadowInterventionHtml(m)));
  tap(ctx, "region", "us");
  assert.deepStrictEqual(ctx.sent, ["m-t1"]);
  assert.strictEqual(ctx.shadowIvDraft("m-t1").values.region, "us");
});

test("yes sends on the tap; no opens the box and waits for Send", () => {
  const ctx = fresh(YESNO);
  const m = ctx.S.shadowMissions[0];
  tap(ctx, "ok", "no");
  assert.deepStrictEqual(ctx.sent, [], "a No is the start of a sentence");
  const h = ctx.shadowInterventionHtml(m);
  assert(/What should I change\?/.test(h) && /data-shivsend="m-t1"/.test(h));
  tap(ctx, "ok", "yes");
  assert.deepStrictEqual(ctx.sent, ["m-t1"]);
});

test("a form with several fields sends nothing on a tap and keeps Send", () => {
  const ctx = fresh(TWO);
  tap(ctx, "region", "eu");
  assert.deepStrictEqual(ctx.sent, []);
  assert(/data-shivsend="m-t1"/.test(ctx.shadowInterventionHtml(ctx.S.shadowMissions[0])));
});

test("a failed send brings Send back so the founder can retry", () => {
  const ctx = fresh(CHOICE);
  ctx.shadowIvDraft("m-t1").err = "network down";
  assert(/data-shivsend="m-t1"/.test(ctx.shadowInterventionHtml(ctx.S.shadowMissions[0])));
});

test("verdicts: a row per item, three taps each, label escaped", () => {
  const ctx = fresh(VERD);
  const h = ctx.shadowInterventionHtml(ctx.S.shadowMissions[0]);
  assert.strictEqual((h.match(/class="shverdrow"/g) || []).length, 2);
  assert.strictEqual((h.match(/data-shivverdict=/g) || []).length, 6);
  assert(/Rivers &lt;run> deep/.test(h));
  assert(/data-shivsend="m-t1"/.test(h), "several answers: Send stays");
});

test("verdicts: a tap sets it, another verdict replaces it, the same one clears it", () => {
  const ctx = fresh(VERD);
  tap(ctx, "h", "h1", { shivverdict: "approve" });
  tap(ctx, "h", "h2", { shivverdict: "later" });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(ctx.shadowIvDraft("m-t1").values.h)),
    { h1: "approve", h2: "later" });
  tap(ctx, "h", "h2", { shivverdict: "reject" });
  tap(ctx, "h", "h1", { shivverdict: "approve" });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(ctx.shadowIvDraft("m-t1").values.h)),
    { h2: "reject" });
  assert.deepStrictEqual(ctx.sent, [], "verdicts never send on a tap");
  assert(/class="shkind on shkindno"/.test(ctx.shadowInterventionHtml(ctx.S.shadowMissions[0])));
});

test("its style uses tokens only", () => {
  const block = css.slice(css.indexOf(".shverd{"));
  const rules = block.slice(0, block.indexOf(".shverdbtns{") + 40);
  assert(!/#[0-9a-fA-F]{3,6}\b|rgba?\(/.test(rules), "no colour literal");
});

console.log("test_shadow_tap.js: " + n + " passed");
