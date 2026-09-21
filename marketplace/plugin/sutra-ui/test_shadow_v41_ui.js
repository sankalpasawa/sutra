#!/usr/bin/env node
/* test_shadow_v41_ui.js -- Shadow v4.1 on the screen (SHADOW-V3 section 13,
   founder 2026-09-21).

     V4-7  a `limits` result in the task chat's reply is drawn as ONE row in
           the stream, fixed copy from the server, with Undo -- and Undo goes
           through the same mission-action door every control uses.
     V4-9  a finished task's card carries Hand back to Shadow; a reply that
           reopened the task says so in the stream and re-reads the list; a
           409 shows the server's own sentence instead of "that task has
           finished".

   Same harness as test_shadow_v4_talk.js: the two modules in a vm, a fake
   shadowPost that records what was sent and answers what the test says.

   Run: node test_shadow_v41_ui.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

function fresh(reply){
  const ctx = {
    console, Date,
    setTimeout: () => ({}), clearTimeout(){}, setInterval: () => ({}),
    scheduleRender(){},
    /* shadowMissionAct returns early without a fetch; the fake shadowPost
       below is what actually answers, so this is never called */
    fetch: async () => { throw new Error("fetch must go through shadowPost"); },
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    escAttr: (x) => String(x == null ? "" : x).replace(/"/g, "&quot;"),
    SCREENS: {}, TITLES: {}, S: {},
    posted: [], fetched: [], nudged: "", reloads: 0,
    listeners: {},
    document: {
      addEventListener(t, fn){ (ctx.listeners[t] = ctx.listeners[t] || []).push(fn); },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
      querySelectorAll(){ return []; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  ctx.loadGoalTranscript = (sid) => { ctx.fetched.push(sid); };
  ctx.goalMessages = (sid) => (ctx.S.goalTranscript || {})[sid];
  ctx.goalTranscriptHtml = () => "";
  ctx.showNudge = (t) => { ctx.nudged = t; };
  ctx.loadShadowHome = async () => { ctx.reloads += 1; };
  ctx.loadSessions = () => {};
  ctx.shadowPost = async (url, body) => {
    ctx.posted.push({ url: url, body: body });
    const r = (typeof reply === "function") ? reply(url, body) : reply;
    if (r && r.status && !r.ok)
      return { ok: false, status: r.status,
               json: async () => (r.body || {}) };
    return { ok: true, status: 200,
             json: async () => Object.assign({ mission: { id: "m-1" } }, r || {}) };
  };
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  return ctx;
}

const M = (over) => Object.assign({
  id: "m-1", objective: "Ship the fix", template: "fix",
  target_mode: "new", target_session: "sess-1", target_chat: "c-1",
  task_chat_session: "shadow-1", task_chat: "c-2",
  state: "running", turns_used: 3, max_turns: 12,
  done_when: [{ check: "the tests pass", tier: "founder_confirm" }],
}, over);

function pane(ctx, m){
  ctx.S.shadowMissions = [m];
  ctx.S.shadowTaskSel = m.id;
  return ctx.shadowHomeHtml();
}
const click = (ctx, dataset) =>
  (ctx.listeners.click || []).forEach(fn =>
    fn({ target: { dataset: dataset, closest(){ return null; } },
         preventDefault(){}, stopPropagation(){} }));
const settle = () => new Promise(r => setImmediate(() => setImmediate(r)));
/* the composer's text lives on the talk store; shadowTalkSend reads it there */
const say = (ctx, mid, text) => { ctx.shadowTalk().text = text; return ctx.shadowTalkSend(mid); };

let ok = 0;
const pass = (s) => console.log("ok " + (++ok) + " " + s);

(async () => {
  /* ══ 1. A LIMIT SAID IN THE CHAT IS DRAWN AS A ROW WITH UNDO ═══════════ */
  {
    const ctx = fresh({ reply: "No turn limit on this task.",
      limits: { applied: [{ label: "turns: no limit, this task",
                            undo: { mid: "m-1", action: "undo_limits" } }],
                refused: [] } });
    pane(ctx, M());
    await say(ctx, "m-1","no turn limit on this one");
    await settle();
    const h = pane(ctx, M({ no_turn_limit: true }));
    assert(/turns: no limit, this task/.test(h), "the server's label is drawn");
    assert(/data-shact="undo_limits"[^>]*data-shmid="m-1"/.test(h)
           || /data-shmid="m-1"[^>]*data-shact="undo_limits"/.test(h),
           "with Undo on the row, through the mission-action hook");
    assert(/class="shsaid shfrom-shadow shlimits/.test(h),
      "as its own kind of row, on Shadow's side");
    assert(/No turn limit on this task\./.test(h), "and Shadow's one line beside it");
    assert.strictEqual(ctx.reloads, 1, "the list is re-read so the card shows the override");
    pass("a limit said in the chat is drawn with Undo");
  }

  /* ══ 2. A REFUSAL IS A ROW WITHOUT UNDO ════════════════════════════════ */
  {
    const ctx = fresh({ reply: "Ok.",
      limits: { applied: [],
                refused: ["this task has already used 12 turns -- say a bigger number, or no limit"] } });
    pane(ctx, M());
    await say(ctx, "m-1","cap it at 10");
    await settle();
    const h = pane(ctx, M());
    assert(/already used 12 turns/.test(h), "the store's sentence is drawn");
    assert(!/data-shact="undo_limits"/.test(h), "nothing to undo, no button");
    pass("a refused limit is said, not swallowed");
  }

  /* ══ 3. UNDO GOES THROUGH THE ONE ACTION DOOR ═══════════════════════════ */
  {
    const ctx = fresh({});
    pane(ctx, M());
    click(ctx, { shact: "undo_limits", shmid: "m-1" });
    await settle();
    const p = ctx.posted.find(x => /\/act$/.test(x.url));
    assert(p, "Undo posted a mission action");
    assert.strictEqual(p.url, "/api/shadow/missions/m-1/act");
    assert.strictEqual(p.body.action, "undo_limits");
    assert.strictEqual(ctx.nudged, "Put back.", "and says so");
    pass("Undo is the same mission-action path as every other control");
  }

  /* ══ 4. A FINISHED TASK'S CARD CARRIES HAND BACK ═══════════════════════ */
  {
    for (const state of ["done", "failed", "stopped"]){
      const ctx = fresh({});
      const h = pane(ctx, M({ state: state }));
      assert(/data-shact="reopen"[^>]*data-shmid="m-1"/.test(h),
             state + ": Hand back to Shadow is on the card");
      assert(/Hand back to Shadow/.test(h), state + ": with its label");
    }
    const ctx = fresh({});
    let h = pane(ctx, M({ state: "running" }));
    assert(!/data-shact="reopen"/.test(h), "a live task has nothing to hand back");
    h = pane(ctx, M({ state: "done", target_session: null }));
    assert(!/data-shact="reopen"/.test(h), "a task with no chat cannot be handed back");
    pass("Hand back to Shadow sits on every finished card that has a chat");
  }

  /* ══ 5. HAND BACK IS ONE CLICK, ONE ACTION ═════════════════════════════ */
  {
    const ctx = fresh({ state: "running" });
    pane(ctx, M({ state: "done" }));
    click(ctx, { shact: "reopen", shmid: "m-1" });
    await settle();
    const p = ctx.posted.find(x => /\/act$/.test(x.url));
    assert(p && p.body.action === "reopen", "posted the reopen action");
    assert.strictEqual(ctx.nudged, "Shadow is back on it.");
    assert(ctx.reloads >= 1, "and the list is re-read");
    pass("Hand back posts reopen and says Shadow is back on it");
  }

  /* ══ 6. A REPLY THAT REOPENED THE TASK SAYS SO IN THE STREAM ═══════════ */
  {
    const ctx = fresh({ reply: "On it.", reopened: true,
                        mission: { id: "m-1", state: "running" } });
    pane(ctx, M({ state: "done" }));
    await say(ctx, "m-1","also cover the logout path");
    await settle();
    const h = pane(ctx, M({ state: "running" }));
    assert(/Back on it/.test(h), "the reopen is said once");
    assert(/On it\./.test(h), "then Shadow's answer");
    assert(h.indexOf("Back on it") < h.indexOf("On it."), "in that order");
    assert.strictEqual(ctx.reloads, 1, "and the list is re-read");
    pass("a reopen is said in the stream and the list re-read");
  }

  /* ══ 7. A 409 SHOWS THE SERVER'S SENTENCE, NOT "FINISHED" ═══════════════ */
  {
    const why = "that chat is already driven by task m-2 (Other) -- tell that task instead";
    const ctx = fresh({ ok: false, status: 409,
                        body: { detail: { detail: why, state: "done" } } });
    pane(ctx, M({ state: "done" }));
    await say(ctx, "m-1","more please");
    await settle();
    assert.strictEqual(ctx.S.shadowScopeErr, why, "the server's own words");
    assert(!/has finished/.test(ctx.S.shadowScopeErr));
    pass("a 409 carries the server's sentence");
  }

  /* ══ 8. THE OLD LINE STILL STANDS FOR A BARE 409 ═══════════════════════ */
  {
    const ctx = fresh({ ok: false, status: 409, body: {} });
    pane(ctx, M());
    await say(ctx, "m-1","hello");
    await settle();
    assert(/has finished/.test(ctx.S.shadowScopeErr),
           "an older server with no sentence keeps the historical line");
    pass("a bare 409 keeps the historical line");
  }

  console.log("test_shadow_v41_ui.js: " + ok + " passed");
})().catch(e => { console.error(e); process.exit(1); });
