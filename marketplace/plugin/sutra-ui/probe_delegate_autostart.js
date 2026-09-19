#!/usr/bin/env node
/* throwaway probe: what does the right pane show at each paint after Enter?
   CASE A -- the list read is slow/dead, so only the panel's own knowledge is
             on screen. This is the window the founder lands in.
   CASE B -- a modelled server: create, act(start_now) stamps, the list read
             returns what the server holds. */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JS = path.join(__dirname, "static", "js");
const overlay = fs.readFileSync(path.join(JS, "15-shadow-overlay.js"), "utf8");
const src = fs.readFileSync(path.join(JS, "16-shadow-home.js"), "utf8");

function fresh(){
  const ctx = {
    console, Date, setTimeout: () => 0, clearTimeout: () => {},
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    escAttr: (x) => String(x == null ? "" : x),
    SCREENS: {}, TITLES: {}, S: {}, SETTINGS: { flags: {} },
    document: {
      addEventListener(){},
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {}, innerHTML: "" }; },
      body: { appendChild(){} }, querySelector(){ return null; },
      activeElement: null,
    },
  };
  ctx.window = ctx;
  ctx.fetch = async () => ({ ok: true, status: 200, json: async () => ({}) });
  vm.createContext(ctx);
  vm.runInContext("var __SHADOW_NO_AUTOBOOT = true;", ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  ctx.S.screen = "shadow";
  ctx.S.goals = [];
  return ctx;
}

function probe(name, { reloads }){
  const ctx = fresh();
  const S = ctx.S;
  const seen = [];
  let seq = 0;
  const SERVER = [
    { id: "m-live", objective: "an older running task", state: "running",
      turns_used: 4, max_turns: 25, target_mode: "new",
      target_session: "sid-a", done_when: [] },
    { id: "m-ready", objective: "an old brief nobody ever started",
      state: "brief_confirm", turns_used: 0, max_turns: 25,
      target_mode: "new", target_session: null, done_when: [] },
  ];
  S.shadowMissions = JSON.parse(JSON.stringify(SERVER));

  ctx.shadowPost = async (url, body) => {
    if (url === "/api/shadow/missions"){
      const m = { id: "m-" + (++seq), objective: body.objective,
        state: "brief_confirm", turns_used: 0, max_turns: 25,
        target_mode: "new", target_session: null, template: body.template,
        done_when: body.done_when || [] };
      SERVER.push(m);
      return { ok: true, status: 200,
               json: async () => JSON.parse(JSON.stringify(m)) };
    }
    const hit = /\/api\/shadow\/missions\/([^/]+)\/act/.exec(url);
    if (hit && body.action === "start_now"){
      const m = SERVER.find(x => x.id === hit[1]);
      if (m && m.state === "brief_confirm")
        m.start_requested_at = "2026-09-19T08:00:00Z";
      return { ok: true, status: 200,
               json: async () => ({ accepted: true, mission_id: hit[1] }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };
  ctx.showNudge = () => {};
  ctx.renderShadowCard = () => {};
  ctx.loadShadowHome = async () => {
    if (reloads) S.shadowMissions = JSON.parse(JSON.stringify(SERVER));
  };
  ctx.scheduleRender = () => snap();

  function snap(){
    /* shadowHomeHtml draws the compose panel in this slot while + Delegate
       is open; the card only appears once it closes. Report that honestly. */
    if (S.shadowNewOpen){ seen.push({ sel: "(+ Delegate still open)" }); return; }
    const sel = ctx.shadowSelectedTask();
    const h = sel ? ctx.shadowTaskCardHtml(sel) : "(blank pane)";
    seen.push({ sel: sel && sel.id,
      start: /data-shstart=/.test(h),
      pill: ((/<span class="shtpill[^"]*">([\s\S]*?)<\/span>/.exec(h) || [])[1]
             || "").replace(/<[^>]*>/g, "").trim(),
      runs: (/where it runs<\/span>\s*<span class="shcard2v">([^<]*)/.exec(h) || [])[1] });
  }

  S.shadowNewOpen = true;
  ctx.shadowNewChat().text = "ship the referral flow";
  return ctx.shadowNewTalk().then(() => {
    snap();
    console.log("\n== " + name + " ==");
    seen.forEach((s, i) => console.log("  paint " + (i + 1)
      + "  sel=" + s.sel + "  pill=" + (s.pill || "-")
      + "  START_BUTTON=" + s.start + "  runs=" + JSON.stringify(s.runs)));
  });
}

(async () => {
  await probe("A: list read never lands (the window after Enter)", { reloads: false });
  await probe("B: list read lands (settled)", { reloads: true });
})();
