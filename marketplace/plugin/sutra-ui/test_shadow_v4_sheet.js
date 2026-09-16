#!/usr/bin/env node
/* test_shadow_v4_sheet.js -- Shadow v4 step 13 (C7, ADR-043): the sheet is
   "What Shadow knows" and its first section is "How Shadow behaves", the
   founder's own words, saved on change through POST /api/shadow/settings/
   behaves. The fixture is the live GET /api/shadow/settings payload
   (test_fixtures/shadow_v4/settings.json, golden E7).

   Run: node test_shadow_v4_sheet.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
const FIXTURE = JSON.parse(fs.readFileSync(
  path.join(__dirname, "test_fixtures", "shadow_v4", "settings.json"), "utf8"));

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
  return ctx;
}
const settle = () => new Promise(r => setImmediate(() => setImmediate(r)));

(async () => {
  /* 1. the sheet: title, first section, prefilled text, the door and the title row */
  {
    const ctx = fresh();
    const d = JSON.parse(JSON.stringify(FIXTURE));
    d.behaves = "Check in every 3 turns. Never say mission.";
    ctx.S.shadowSettings = d;
    const h = ctx.shadowSettingsHtml();
    assert(/<h2 class="sstitle">What Shadow knows<\/h2>/.test(h), "the sheet is What Shadow knows");
    const iBehaves = h.indexOf("How Shadow behaves");
    const iAutonomy = h.indexOf(">Autonomy<");
    assert(iBehaves !== -1 && iAutonomy !== -1 && iBehaves < iAutonomy, "behaves is the first section");
    assert(/data-shbehaves="1"/.test(h), "the behaves field carries its hook");
    assert(/Check in every 3 turns\. Never say mission\./.test(h), "prefilled from the record");
    assert(/maxlength="4000"/.test(h), "the ceiling comes from the server");
    assert(!/<button[^>]*Save/.test(h), "no Save button: it saves on change");
    assert.strictEqual(ctx.TITLES.shadowsettings[0], "What Shadow knows");
    assert(/<span>What Shadow knows<\/span>/.test(ctx.shadowNavHtml()), "the door is labelled What Shadow knows");
    /* nothing existing removed: the other sections still render */
    ["Autonomy", "Memory", "Tasks", "Delegate offers", "Presence", "Attention"]
      .forEach(s => assert(h.indexOf(">" + s + "<") !== -1, s + " section still there"));
    console.log("ok 1 the sheet is What Shadow knows, behaves first, everything else kept");
  }

  /* 2. typing keeps a draft across renders and marks it unsaved */
  {
    const ctx = fresh();
    ctx.S.shadowSettings = Object.assign({}, FIXTURE, { behaves: "old" });
    ctx.listeners.input({ target: { dataset: { shbehaves: "1" }, value: "new words" } });
    assert.strictEqual(ctx.S.shadowBehavesDraft, "new words");
    assert(/new words/.test(ctx.shadowSettingsHtml()), "the draft survives a render");
    console.log("ok 2 the draft is kept on S across renders");
  }

  /* 3. change (the blur after an edit) posts the text and shows saved */
  {
    const ctx = fresh();
    ctx.S.shadowSettings = Object.assign({}, FIXTURE, { behaves: "old" });
    const calls = [];
    ctx.fetch = async (url, opts) => {
      calls.push({ url, body: JSON.parse(opts.body) });
      return { ok: true, status: 200, json: async () => ({ behaves: "Be brief.", max: 4000 }) };
    };
    ctx.listeners.change({ target: { dataset: { shbehaves: "1" }, value: "Be brief." } });
    await settle(); await settle();
    assert.strictEqual(calls.length, 1, "one write");
    assert(/\/api\/shadow\/settings\/behaves$/.test(calls[0].url), calls[0].url);
    assert.deepStrictEqual(calls[0].body, { behaves: "Be brief." });
    assert.strictEqual(ctx.S.shadowSettings.behaves, "Be brief.", "the record follows the server");
    assert.strictEqual(ctx.S.shadowBehavesDraft, null, "the draft is released");
    assert(/ssbehaves-note">saved</.test(ctx.shadowSettingsHtml()), "says saved");
    console.log("ok 3 change writes through the behaves route and says saved");
  }

  /* 4. a refused write says so and keeps the founder's words on screen */
  {
    const ctx = fresh();
    ctx.S.shadowSettings = Object.assign({}, FIXTURE, { behaves: "old" });
    ctx.fetch = async () => ({ ok: false, status: 400, json: async () => ({}) });
    ctx.listeners.input({ target: { dataset: { shbehaves: "1" }, value: "kept" } });
    ctx.listeners.change({ target: { dataset: { shbehaves: "1" }, value: "kept" } });
    await settle(); await settle();
    const h = ctx.shadowSettingsHtml();
    assert(/did not stick/.test(h), "the refusal is said");
    assert(/>kept</.test(h), "the founder's words are not lost");
    assert.strictEqual(ctx.S.shadowSettings.behaves, "old", "the record did not move");
    console.log("ok 4 a refused write is honest and loses nothing");
  }

  /* 5. a change on some other field never touches the behaves route */
  {
    const ctx = fresh();
    ctx.S.shadowSettings = Object.assign({}, FIXTURE);
    let calls = 0;
    ctx.fetch = async () => { calls++; return { ok: true, status: 200, json: async () => ({}) }; };
    ctx.listeners.change({ target: { dataset: { shoffername: "1" }, value: "x" } });
    await settle();
    assert.strictEqual(calls, 0);
    console.log("ok 5 the change listener is scoped to the behaves field");
  }

  console.log("test_shadow_v4_sheet: all ok");
})().catch(e => { console.error(e); process.exit(1); });
