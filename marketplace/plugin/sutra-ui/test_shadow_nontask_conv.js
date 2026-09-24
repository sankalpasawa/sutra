#!/usr/bin/env node
/* test_shadow_nontask_conv.js -- A SHADOW CONVERSATION OUTLIVES NOT BEING A TASK
 * (founder, 2026-09-24).
 *
 * THE BUG. shadowSelectedTask returns the CONVERSATION row whenever
 * shadowTaskSel is SH_NO_TASK and shadowChat names it -- exactly the state
 * shadowNewTalk leaves behind when Shadow read no work in the opening line
 * ("Hi"). shadowSubmitCompose then tested only `sel.id` before routing to the
 * task chat, so the next thing the founder said was POSTed to
 * /api/shadow/tasks/<shc-...>/chat: a MISSION route addressed with a
 * CONVERSATION id. The server answers 404 "no task shc-..." and the
 * conversation is dead from its second message onwards.
 *
 * WHAT IS PINNED HERE, and the point of the file: WHICH ENDPOINT each kind of
 * selection sends to. A conversation goes to /api/shadow/chat; a mission goes
 * to /api/shadow/tasks/{id}/chat, unchanged. The suite runs the REAL source of
 * shadowSubmitCompose, sliced out of the panel file rather than copied, so it
 * cannot drift away from the function it is about.
 *
 * Run: node test_shadow_nontask_conv.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const SRC = path.join(__dirname, "static", "js");

/* THE REAL FUNCTION, NOT A COPY. shadowSubmitCompose is nested, so it is not a
   global the harness can reach. Slicing its exact text out of the file and
   evaluating it in the same context is what keeps this suite honest: edit the
   panel and this runs the edit. Every name it closes over
   (shadowSelectedTask, shadowIsConvRow, sendToShadow, shadowTalkSend,
   shadowConvSay, shadowConvBind, shadowComposeSet, shadowTalk, loadShadowHome)
   is a function declaration, so all of them are already global here. */
function sliceCompose(text){
  const at = text.indexOf("  function shadowSubmitCompose(el){");
  assert.ok(at > 0, "shadowSubmitCompose not found -- did it move or get renamed?");
  const end = text.indexOf("\n  }\n", at);
  assert.ok(end > at, "could not find the end of shadowSubmitCompose");
  return text.slice(at, end + 4);
}

function fresh(){
  const ctx = {
    console, Date, Promise, setTimeout: (f) => { f && f(); return {}; },
    /* sendToShadow returns early when this is undefined (15-shadow-overlay:810),
       which silently turned every routing assertion below into a pass-by-
       nothing. It is never called: shadowPost is stubbed. */
    fetch: () => Promise.resolve({ ok: true, status: 200,
                                   json: () => Promise.resolve({}) }),
    clearTimeout(){}, setInterval: () => ({}),
    scheduleRender(){}, renderNow(){}, SCREENS: {}, TITLES: {}, S: {}, listeners: {},
    esc: (x) => String(x == null ? "" : x), escAttr: (x) => String(x == null ? "" : x),
    document: { addEventListener(){},
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
      querySelectorAll(){ return []; } },
  };
  vm.createContext(ctx);
  const home = fs.readFileSync(path.join(SRC, "16-shadow-home.js"), "utf8");
  for (const f of ["15-shadow-overlay.js", "16-shadow-home.js"])
    vm.runInContext(fs.readFileSync(path.join(SRC, f), "utf8"), ctx);
  vm.runInContext("var shadowSubmitCompose;\n" + sliceCompose(home).trim()
                  .replace(/^function /, "shadowSubmitCompose = function "), ctx);

  /* every POST recorded, nothing real sent */
  ctx.POSTS = [];
  ctx.REPLIES = {};
  ctx.shadowPost = (url, body) => {
    ctx.POSTS.push({ url, body });
    const canned = ctx.REPLIES[url];
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve(canned || { reply: "ok" }) });
  };
  ctx.loadShadowHome = () => {};
  /* the one action every Start control in the app uses; recorded, not run */
  ctx.STARTS = [];
  ctx.shadowMissionAct = (mid, action) => {
    ctx.STARTS.push(mid + ":" + action);
    return Promise.resolve("running");
  };
  ctx.S.goals = []; ctx.S.shadowMissions = []; ctx.S.shadowThreads = {};
  ctx.S.shadowConversations = []; ctx.S.shadowChat = "global";
  return ctx;
}

/* the state shadowNewTalk leaves behind when the opening line was NOT work */
function afterNonTaskIntake(ctx, cid, said, answered){
  ctx.S.shadowThreads[cid] = [
    { who: "founder", text: said, ts: 1, newtalk: true },
    { who: "shadow",  text: answered, ts: 2, newtalk: true }];
  ctx.S.shadowChat = cid;
  ctx.S.shadowConversations = [{ id: cid, title: said, mission_id: null,
                                 created_at: "2026-09-24T10:00:00Z" }];
  ctx.S.shadowTaskSel = "__none__";
}

const box = (v) => ({ value: v, dataset: {}, focus(){}, setSelectionRange(){} });
const urls = (ctx) => ctx.POSTS.map(p => p.url);
const chatPosts = (ctx) => ctx.POSTS.filter(p => p.url === "/api/shadow/chat");
const taskPosts = (ctx) => ctx.POSTS.filter(p => /^\/api\/shadow\/tasks\//.test(p.url));

let pass = 0, fail = 0;
function t(name, fn){
  try { fn(); console.log("  ok   " + name); pass++; }
  catch (e){ console.log("  FAIL " + name + "\n       " + e.message); fail++; }
}
const settle = () => new Promise(r => setImmediate(r));

(async () => {
console.log("test_shadow_nontask_conv.js");

/* ── 1. a non-task conversation can be continued ───────────────────────── */
{
  const ctx = fresh();
  afterNonTaskIntake(ctx, "shc-aaa111", "Hi", "Hey! How can I help?");
  ctx.shadowSubmitCompose(box("What are you doing?"));
  await settle();
  t("1. continuing a non-task conversation does NOT hit a task route", () => {
    assert.deepStrictEqual(taskPosts(ctx).map(p => p.url), [],
      "posted to a mission route: " + JSON.stringify(urls(ctx)));
  });
  t("1. it goes to /api/shadow/chat, the ordinary Shadow door", () => {
    assert.strictEqual(chatPosts(ctx).length, 1, JSON.stringify(urls(ctx)));
    assert.strictEqual(chatPosts(ctx)[0].body.message, "What are you doing?");
  });
}

/* ── 2. it survives leaving and coming back ────────────────────────────── */
{
  const ctx = fresh();
  /* the server's record, as /api/shadow/conversations returns it */
  ctx.shadowRestoreConversations([{ id: "shc-bbb222", title: "Hi",
    mission_id: null, created_at: "2026-09-24T10:00:00Z",
    messages: [{ who: "founder", text: "Hi", ts: 1 },
               { who: "shadow", text: "Hey! How can I help?", ts: 2 }] }]);
  ctx.S.shadowChat = "shc-bbb222"; ctx.S.shadowTaskSel = "__none__";
  t("2. the conversation is still in the rail after a reopen", () => {
    const rows = ctx.shadowTasks();
    assert.strictEqual(rows.length, 1);
    assert.ok(ctx.shadowIsConvRow(rows[0]));
    assert.strictEqual(rows[0].id, "shc-bbb222");
  });
  t("2. its transcript came back", () => {
    assert.deepStrictEqual(
      ctx.S.shadowThreads["shc-bbb222"].map(m => m.who + ":" + m.text),
      ["founder:Hi", "shadow:Hey! How can I help?"]);
  });
  ctx.shadowSubmitCompose(box("Still there?"));
  await settle();
  t("2. Talk to Shadow works after the reopen", () => {
    assert.deepStrictEqual(taskPosts(ctx).map(p => p.url), []);
    assert.strictEqual(chatPosts(ctx).length, 1, JSON.stringify(urls(ctx)));
  });
}

/* ── 3. non-task -> task, through the EXISTING classification ──────────── */
{
  const ctx = fresh();
  afterNonTaskIntake(ctx, "shc-ccc333", "Hi", "Hey! How can I help?");
  ctx.REPLIES["/api/shadow/chat"] = { reply: "Planning that now.",
    mission: { id: "msn-777", state: "running", objective: "3-day trip to India" } };
  ctx.shadowSubmitCompose(box("Actually, help me plan a 3-day trip to India."));
  await settle(); await settle(); await settle();
  t("3. the task-like line still goes through the ordinary door", () => {
    assert.strictEqual(chatPosts(ctx).length, 1);
    assert.deepStrictEqual(taskPosts(ctx).map(p => p.url), []);
  });
  t("3. the conversation binds to the mission Shadow opened", () => {
    const bind = ctx.POSTS.filter(p =>
      p.url === "/api/shadow/conversations/shc-ccc333/messages"
      && p.body && p.body.mission_id);
    assert.strictEqual(bind.length, 1, "no bind: " + JSON.stringify(urls(ctx)));
    assert.strictEqual(bind[0].body.mission_id, "msn-777");
  });
}

/* ── 3b. THE TRANSITION STARTS THE TASK, IT DOES NOT ASK ───────────────
   (founder, 2026-09-24: "Hi" then "Give me the latest news about MotoGP"
   ended on READY + [Start the task] and had to be clicked.)

   WHY IT DID. The server starts what it creates only from intake
   (app.py `if intake:`), because a mission proposed inside an ordinary chat
   keeps its brief. This path posts through the shared /api/shadow/chat with
   no intake flag, so the mission arrived in brief_confirm. The start is now
   taken client-side by the same shadowMissionAct("start_now") shadowNewTalk
   already calls at line 5699. */
{
  const ctx = fresh();
  afterNonTaskIntake(ctx, "shc-fff666", "Hi", "Hey! How can I help?");
  ctx.REPLIES["/api/shadow/chat"] = { reply: "On it.",
    mission: { id: "msn-motogp", state: "brief_confirm",
               objective: "Latest news about MotoGP" } };
  ctx.shadowSubmitCompose(box("Give me the latest news about MotoGP"));
  await settle(); await settle(); await settle();
  t("3b. a task found mid-conversation is started automatically", () => {
    assert.deepStrictEqual(ctx.STARTS, ["msn-motogp:start_now"],
      "no automatic start: " + JSON.stringify(ctx.STARTS));
  });
  t("3b. through the existing action, not a new endpoint", () => {
    assert.deepStrictEqual(
      ctx.POSTS.filter(p => /start|run/i.test(p.url)).map(p => p.url), []);
  });
}

/* ── 3c. a mission that is ALREADY running is not started twice ────────── */
{
  const ctx = fresh();
  afterNonTaskIntake(ctx, "shc-ggg777", "Hi", "Hey!");
  ctx.REPLIES["/api/shadow/chat"] = { reply: "Already going.",
    mission: { id: "msn-live", state: "running", objective: "x" } };
  ctx.shadowSubmitCompose(box("Do the thing"));
  await settle(); await settle(); await settle();
  t("3c. an already-running mission is not re-started", () => {
    assert.deepStrictEqual(ctx.STARTS, []);
  });
}

/* ── 4. non-task -> non-task, and both halves are kept ─────────────────── */
{
  const ctx = fresh();
  afterNonTaskIntake(ctx, "shc-ddd444", "Hi", "Hey! How can I help?");
  ctx.REPLIES["/api/shadow/chat"] = { reply: "Waiting on you, mostly." };
  ctx.shadowSubmitCompose(box("What are you doing?"));
  await settle(); await settle(); await settle();
  t("4. a second casual line is answered, not routed at a task", () => {
    assert.strictEqual(chatPosts(ctx).length, 1);
    assert.deepStrictEqual(taskPosts(ctx).map(p => p.url), []);
  });
  t("4. a non-task reply starts nothing", () => {
    assert.deepStrictEqual(ctx.STARTS, []);
  });
  t("4. both halves are written to the conversation record", () => {
    const said = ctx.POSTS.filter(p =>
      p.url === "/api/shadow/conversations/shc-ddd444/messages" && p.body && p.body.who);
    assert.deepStrictEqual(said.map(p => p.body.who + ":" + p.body.text),
      ["founder:What are you doing?", "shadow:Waiting on you, mostly."]);
  });
}

/* ── 5 + 6. THE REGRESSION: a selected MISSION is untouched ────────────── */
{
  const ctx = fresh();
  ctx.S.shadowMissions = [{ id: "msn-111", state: "running",
    objective: "Ten stories", done_when: ["x"], turns_used: 1 }];
  ctx.S.shadowTaskSel = "msn-111";
  ctx.S.shadowChat = "global";
  let sent = null;
  ctx.shadowTalkSend = (mid) => { sent = mid; };
  t("5. a mission is still what shadowSelectedTask returns", () => {
    const sel = ctx.shadowSelectedTask();
    assert.strictEqual(sel.id, "msn-111");
    assert.ok(!ctx.shadowIsConvRow(sel), "a mission must not look like a conversation");
  });
  ctx.shadowSubmitCompose(box("Make it five."));
  t("6. Talk to Shadow on an existing task still goes to the task chat", () => {
    assert.strictEqual(sent, "msn-111");
  });
  t("6. and it does NOT go through the ordinary chat door", () => {
    assert.strictEqual(chatPosts(ctx).length, 0, JSON.stringify(urls(ctx)));
  });
  t("6. nor does it start anything", () => {
    assert.deepStrictEqual(ctx.STARTS, []);
  });
  t("6. nor does it write a conversation record", () => {
    assert.deepStrictEqual(
      ctx.POSTS.filter(p => /conversations/.test(p.url)).map(p => p.url), []);
  });
}

/* ── 7. chronological order across a reopen ────────────────────────────── */
{
  const ctx = fresh();
  ctx.shadowRestoreConversations([{ id: "shc-eee555", title: "Hi",
    mission_id: null, created_at: "2026-09-24T10:00:00Z",
    messages: [{ who: "founder", text: "Hi", ts: 1 },
               { who: "shadow", text: "Hey! How can I help?", ts: 2 },
               { who: "founder", text: "What are you doing?", ts: 3 },
               { who: "shadow", text: "Waiting on you, mostly.", ts: 4 }] }]);
  t("7. the whole exchange reads in the order it happened", () => {
    assert.deepStrictEqual(
      ctx.S.shadowThreads["shc-eee555"].map(m => m.who + ":" + m.text),
      ["founder:Hi", "shadow:Hey! How can I help?",
       "founder:What are you doing?", "shadow:Waiting on you, mostly."]);
  });
  t("7. an unbound conversation is drawn once, as a conversation", () => {
    const rows = ctx.shadowTasks().filter(r => r.id === "shc-eee555");
    assert.strictEqual(rows.length, 1);
    assert.strictEqual(rows[0].state, "queued");
  });
}

console.log("\n" + (fail ? "FAILED " + fail + " of " + (pass + fail)
                         : "OK " + pass + " assertions"));
process.exit(fail ? 1 : 0);
})();
