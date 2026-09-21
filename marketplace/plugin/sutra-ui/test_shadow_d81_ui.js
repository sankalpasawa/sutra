#!/usr/bin/env node
/* test_shadow_d81_ui.js -- FOLDED, NEVER DROPPED (founder D81, 2026-09-21).
 *
 * "All the conversations with the app should happen in the Sutra chat UI and
 * should be shown there." Until D81 the task stream left out every prompt the
 * app sends into the task's Shadow chat -- boot, brief ask, steering, and now
 * the judge -- together with Shadow's replies to them. This lane pins the
 * replacement: each app prompt is ONE folded row in the stream, a one-line
 * label the founder opens to read the prompt and the answer verbatim. The
 * founder's own lines and Shadow's answers to them draw exactly as before.
 *
 * Run: node test_shadow_d81_ui.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
const css = fs.readFileSync(
  path.join(__dirname, "static", "panel.css"), "utf8");

function fresh(){
  const ctx = {
    console, Date,
    setTimeout: () => ({}), clearTimeout(){}, setInterval: () => ({}),
    scheduleRender(){},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    SCREENS: {}, TITLES: {}, S: {},
    fetched: [], listeners: {},
    document: {
      addEventListener(t, fn){ (ctx.listeners[t] = ctx.listeners[t] || []).push(fn); },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  ctx.loadGoalTranscript = (sid) => { ctx.fetched.push(sid); };
  ctx.goalMessages = (sid) => (ctx.S.goalTranscript || {})[sid];
  ctx.goalTranscriptHtml = () => "";
  ctx.showNudge = () => {};
  ctx.shadowPost = async () => ({ ok: true, status: 200, json: async () => ({}) });
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  return ctx;
}

const M = (over) => Object.assign({
  id: "m-1", objective: "Ship the fix", template: "fix",
  target_mode: "new", target_session: "sess-1", target_chat: "c-1",
  task_chat_session: "shadow-1", task_chat: "c-2",
  state: "running", turns_used: 3, max_turns: 12,
  done_when: [{ check: "the tests pass", tier: "judge" }],
}, over);

function pane(ctx, m){
  ctx.S.shadowMissions = [m];
  ctx.S.shadowTaskSel = m.id;
  return ctx.shadowHomeHtml();
}

let ok = 0;
const pass = (s) => console.log("ok " + (++ok) + " " + s);

const TRANSCRIPT = [
  { role: "user", text: "[Shadow boot] Read your operating context, then answer READY.\n\nYou are Shadow.", ts: "2026-09-21T10:00:00Z" },
  { role: "assistant", text: "READY", ts: "2026-09-21T10:00:05Z" },
  { role: "user", text: "Write the opening brief for this task's worker chat.\n\nFACTS\n- repo: x", ts: "2026-09-21T10:00:10Z" },
  { role: "assistant", text: "```brief\nThe brief.\n```", ts: "2026-09-21T10:00:20Z" },
  { role: "user", text: "You are Shadow, driving one target chat toward an outcome.\nOUTCOME\nShip the fix", ts: "2026-09-21T10:00:30Z" },
  { role: "assistant", text: '```json\n{"action":"continue","instruction":"go"}\n```', ts: "2026-09-21T10:00:40Z" },
  { role: "user", text: "What are you waiting on?", ts: "2026-09-21T10:01:00Z" },
  { role: "assistant", text: "Waiting on the worker's verification.", ts: "2026-09-21T10:01:20Z" },
  { role: "user", text: "You are settling ONE completion check by reading evidence.\n\nTHE CHECK:\nthe tests pass", ts: "2026-09-21T10:02:00Z" },
  { role: "assistant", text: "Reading the diff.", ts: "2026-09-21T10:02:05Z" },
  { role: "assistant", text: '```json\n{"verdict":"met","reason":"suite ran green"}\n```', ts: "2026-09-21T10:02:10Z" },
];

/* ══ 1. THE READER: one folded row per app prompt, replies inside it ═════ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": TRANSCRIPT };
  const rows = ctx.shadowTalkTurns(M());
  assert.strictEqual(rows.length, 6, "4 folds + the founder's line + Shadow's answer");
  /* JSON compare: arrays born inside the vm realm carry another Array
     prototype, which deepStrictEqual (rightly) refuses to call equal */
  assert.strictEqual(JSON.stringify(rows.map(r => r.fold || r.who)),
    JSON.stringify(["boot", "brief", "steer", "founder", "shadow", "judge"]),
    "in transcript order");
  assert.strictEqual(JSON.stringify(rows[5].replies),
    JSON.stringify(["Reading the diff.", '```json\n{"verdict":"met","reason":"suite ran green"}\n```']),
    "every reply to an app prompt goes into its fold, across messages");
  assert.strictEqual(rows[2].replies.length, 1);
  assert(/Shadow booted/.test(rows[0].label));
  assert(/worker's brief/.test(rows[1].label));
  assert(/next instruction/.test(rows[2].label));
  assert(/judged a check/.test(rows[5].label));
  assert.strictEqual(rows[3].text, "What are you waiting on?");
  assert.strictEqual(rows[4].text, "Waiting on the worker's verification.");
  assert.strictEqual(src.indexOf("SH_TALK_SKIP"), -1, "the skip list is gone");
  pass("the reader folds every app prompt with its replies and drops nothing");
}

/* ══ 2. THE STREAM: folded rows drawn, verbatim text present, nothing hidden */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": TRANSCRIPT };
  const h = pane(ctx, M());
  const stream = h.slice(h.indexOf("shtimeline"));
  const folds = stream.match(/<details class="shsaid shfold" data-shfold="([a-z]+)"/g) || [];
  assert.strictEqual(folds.length, 4, "four folded rows: " + folds.join(","));
  assert.strictEqual(JSON.stringify(folds.map(f => f.match(/data-shfold="([a-z]+)"/)[1])),
    JSON.stringify(["boot", "brief", "steer", "judge"]));
  for (const shown of ["[Shadow boot]", "READY", "Write the opening brief",
                       "driving one target chat", '"instruction":"go"', "```brief",
                       "settling ONE completion check", "suite ran green"]){
    assert(stream.indexOf(shown) !== -1,
      "the transcript's own text is in the page, folded, not dropped: " + shown);
  }
  /* each fold is a <details>: closed by default, one summary line, opens on click */
  assert.strictEqual((stream.match(/<details class="shsaid shfold"[^>]*>\s*<summary class="shsaidhead">/g) || []).length, 4,
    "one summary line per fold");
  assert.strictEqual((stream.match(/<details class="shsaid shfold"[^>]* open/g) || []).length, 0,
    "folded rows start closed");
  assert(/Shadow judged a check from the evidence/.test(stream), "the judge row is labelled");
  /* the founder's own exchange draws exactly as before */
  assert(/What are you waiting on\?/.test(stream), "the founder's line");
  assert(/Waiting on the worker/.test(stream), "and Shadow's answer");
  assert(/You → Shadow/.test(stream), "with the same head as before");
  assert(stream.indexOf("The app → Shadow") !== -1, "the fold names the app as the speaker");
  pass("the stream draws every app prompt as a closed fold with its verbatim text");
}

/* ══ 3. ORDER: folds sit where the transcript puts them, founder rows unmoved */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": TRANSCRIPT };
  const h = pane(ctx, M());
  const stream = h.slice(h.indexOf("shtimeline"));
  const at = (s) => stream.indexOf(s);
  assert(at('data-shfold="boot"') < at('data-shfold="brief"'), "boot before brief");
  assert(at('data-shfold="brief"') < at('data-shfold="steer"'), "brief before steer");
  assert(at('data-shfold="steer"') < at("What are you waiting on?"), "steer before the founder's line");
  assert(at("Waiting on the worker") < at('data-shfold="judge"'), "the judge came after");
  pass("folds keep their place in the conversation");
}

/* ══ 4. THE STYLE: a fold has its own rule, grey rail, closed marker ═════ */
{
  assert(css.indexOf(".shsaid.shfold{") !== -1, "a fold is styled");
  assert(css.indexOf(".shsaid.shfold>summary{cursor:pointer") !== -1, "and reads as clickable");
  pass("panel.css carries the fold");
}

/* ══ 5. A TRANSCRIPT WITH NO APP PROMPTS is unchanged ════════════════════ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": [
    { role: "user", text: "Hello?", ts: "2026-09-21T10:01:00Z" },
    { role: "assistant", text: "Hi.", ts: "2026-09-21T10:01:20Z" },
  ] };
  const h = pane(ctx, M());
  assert.strictEqual((h.match(/shfold/g) || []).length, 0, "no fold without an app prompt");
  assert(/Hello\?/.test(h) && /Hi\./.test(h));
  pass("a plain conversation draws with no folds");
}

console.log("1.." + ok);
