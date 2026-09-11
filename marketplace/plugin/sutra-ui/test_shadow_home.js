#!/usr/bin/env node
/* test_shadow_home.js -- PLAN-100 S81-S90: the Focus > Shadow home.
   Run: node test_shadow_home.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const html = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
assert(/16-shadow-home\.js/.test(html), "panel.html loads the home module");

const overlay = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn)=>({fn}),
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    SCREENS: {}, TITLES: {}, S: {},
    document: { addEventListener(){}, createElement(){ return {
      setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; } },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);   /* missionCardHtml + shared thread */
  vm.runInContext(src, ctx);
  return ctx;
}

const MISSIONS = [
  { id: "m-1", objective: "fix nav", state: "running", turns_used: 3, max_turns: 20 },
  { id: "m-2", objective: "research Y", state: "queued" },
  { id: "m-3", objective: "ship Z", state: "paused" },
  { id: "m-4", objective: "old", state: "done" },
];

/* 1. S81: screen + title registered; dark state honest */
{
  const ctx = fresh();
  assert(typeof ctx.SCREENS.shadow === "function", "SCREENS.shadow registered");
  assert(ctx.TITLES.shadow[0] === "Shadow", "TITLES row present");
  ctx.S.shadowHomeDark = true;
  assert(/not enabled/.test(ctx.SCREENS.shadow()), "dark = honest zero state");
  console.log("ok 1 registration + dark");
}

/* 2. S82: the home renders the SAME thread array the overlay card uses */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowThread = [{ who: "shadow", text: "the-one-thread-msg" }];
  assert(/the-one-thread-msg/.test(ctx.shadowHomeHtml()), "home renders it");
  assert(/the-one-thread-msg/.test(ctx.shadowCardHtml()), "card renders it");
  console.log("ok 2 one thread, two views");
}

/* 3. S83: plane tabs + counts; done missions excluded from Working */
{
  const ctx = fresh();
  const w = ctx.shadowPlaneHtml(["s-1", "s-2"], MISSIONS, "watching");
  assert(/Watching \u00b7 2/.test(w) && /Working \u00b7 3/.test(w),
    "live counts (done excluded)");
  assert(/data-shunwatch="s-1"/.test(w), "watch rows have toggles");
  console.log("ok 3 plane + counts");
}

/* 4. S85: mission rows carry exactly the legal actions for their state */
{
  const ctx = fresh();
  const g = ctx.shadowPlaneHtml([], MISSIONS, "working");
  assert(/data-shact="start_now" data-shmid="m-2"/.test(g), "queued: Start now");
  assert(/data-shact="drop"[\s\S]{0,60}data-shmid="m-2"/.test(g),
    "queued: Drop");
  assert(/data-shact="resume" data-shmid="m-3"/.test(g), "paused: Resume");
  assert(/data-shact="stop" data-shmid="m-1"/.test(g), "running: Stop");
  assert(!/data-shmid="m-4"/.test(g), "done missions leave the plane");
  console.log("ok 4 mission actions");
}

/* 5. S86/S87: memory -- inert until confirmed, revoke is the undo */
{
  const ctx = fresh();
  const rows = [
    { id: "i-1", text: "caveman prose", precedence: "d_ledger",
      confirmed: true },
    { id: "i-2", text: "maybe this", precedence: "history",
      confirmed: false },
    { id: "i-3", text: "old rule", precedence: "taste", confirmed: true,
      revoked_at: "2026-08-25" },
  ];
  const h = ctx.shadowMemoryHtml(rows);
  assert(/data-shrevoke="i-1"/.test(h), "confirmed rows can be revoked");
  assert(/unconfirmed \u00b7 inert/.test(h) && /data-shconfirm="i-2"/.test(h),
    "unconfirmed rows are visibly inert with one-tap confirm");
  assert(/shmem-dead/.test(h) && /revoked/.test(h),
    "revoked rows stay visible, struck through (archive never delete)");
  console.log("ok 5 memory");
}

/* 6. the controls are WIRED (the recurring lesson, pinned per surface) */
assert(/d\.shact && d\.shmid/.test(src), "home mission actions handled");
assert(/shadowWatchSet/.test(src) && /shadowInstructionAct/.test(src),
  "watch + memory controls must act");
assert(/shhomecompose/.test(src) && /sendToShadow/.test(src),
  "the home composer must send");
console.log("ok 6 controls wired");

/* gap-closure: finished rows carry retry / take-over / result excerpt */
{
  const ctx = fresh();
  const h = ctx.shadowPlaneHtml([], [
    { id: "m-f1", objective: "died", state: "failed",
      target_session: "sess-9", result_excerpt: "tail of transcript" },
  ], "working");
  assert(/Recent finished/.test(h), "finished section header");
  assert(/data-shact="retry"/.test(h), "retry one-tap present");
  assert(/data-shtakeover="sess-9"/.test(h), "take-over affordance present");
  assert(/tail of transcript/.test(h), "result excerpt rendered");
  const none = ctx.shadowPlaneHtml([], [
    { id: "m-1", objective: "live", state: "running" }], "working");
  assert(!/Recent finished/.test(none), "no finished header without rows");
  console.log("ok 7 finished rows: retry/take-over/result");
}

/* the dead-wire pins (founder hit these live 2026-08-26): toggle + memory
   actions must send REAL bodies, and take-over routes through the router */
{
  const ctx = fresh();
  const posts = [];
  ctx.shadowPost = (path, body) => { posts.push({ path, body });
    return Promise.resolve({ ok: true, json: () => ({}) }); };
  ctx.fetch = () => Promise.resolve({ ok: false });
  ctx.loadShadowHome = () => {};
  ctx.shadowWatchSet("sess-1", false);
  ctx.shadowInstructionAct("inst-9", "confirm");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(posts[0].body)),
    { session_id: "sess-1", watch: false }, "watch toggle sends a real body");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(posts[1].body)),
    { id: "inst-9", action: "confirm" }, "memory action sends a real body");
  console.log("ok 8 dead wires carry real bodies");
}
{
  const ctx = fresh();
  const routed = [];
  ctx.shadowRouteDeepLink = (l) => { routed.push(l); return true; };
  const h = ctx.shadowPlaneHtml([], [
    { id: "m-f1", objective: "died", state: "failed",
      target_session: "sess-9" }], "working");
  assert(/data-shtakeover="sess-9"/.test(h), "take-over rendered");
  console.log("ok 9 take-over present (routing pinned in overlay suite)");
}

/* v10: per-chat tabs — one mind, many threads */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowWatching = ["sess-paisa", "sess-dayflow"];
  /* POLISH PASS: the chip's menu is drawn from the app's own chat list, not
     from the watching store (which holds raw ids the app cannot name), so a
     pickable chat has to be a listed chat. */
  ctx.S.sessions = [{ id: "sess-paisa", title: "Paisa", updated_ms: 200 },
                    { id: "sess-dayflow", title: "Dayflow", updated_ms: 100 }];
  ctx.S.shadowMissions = [{ id: "m-1", objective: "x", state: "running",
                            target_session: "sess-paisa" }];
  /* SLICE 11: the per-chat tab STRIP is gone from Home by design -- Home is
     a briefing, not a chat list. The scoping it provided now lives in one
     chip beside the composer, which still emits data-shchat, so the
     one-mind-many-threads model below is unchanged. */
  /* WORKSPACE SLICE: the existing-chat flow is opt-in in the delegated-task
     workspace, so this opens it first. What it asserts is unchanged -- the
     scoping is ONE CHIP, not a tab strip -- only where it now lives. */
  ctx.S.shadowExistingOpen = true;
  const h = ctx.shadowHomeHtml();
  assert(!/shchattabs/.test(h), "the tab strip is not on Home any more");
  assert(/data-shscopepick/.test(h), "the target chat is a single chip");
  ctx.S.shadowScopeOpen = true;
  const open = ctx.shadowHomeHtml();
  assert(/data-shchat="global"/.test(open), "no-chat option offered");
  assert(/data-shchat="sess-paisa"/.test(open), "a chat can be picked");
  assert(!/data-shtab="global"/.test(open),
    "picks use their OWN namespace — data-shtab stays the plane's");
  /* and the plane still renders its own tabs, on its own surface */
  const plane = ctx.shadowPlaneHtml(["sess-paisa"], [], "watching");
  assert(/data-shtab="watching"/.test(plane), "the plane is untouched");
  console.log("ok 10 tab strip removed; scoping is one chip");
}
{
  /* threads are isolated per tab, and the accessor survives reassignment */
  const ctx = fresh();
  ctx.S.shadowChat = "global";
  ctx.S.shadowThread.push({ who: "founder", text: "general" });
  ctx.S.shadowChat = "sess-paisa";
  ctx.S.shadowThread.push({ who: "founder", text: "about paisa" });
  assert.strictEqual(ctx.S.shadowThread.length, 1, "paisa tab has its own");
  ctx.S.shadowThread = ctx.S.shadowThread.filter(t => !t.busy);   /* the reassign */
  ctx.S.shadowThread.push({ who: "shadow", text: "still paisa" });
  assert.strictEqual(ctx.S.shadowThread.length, 2, "accessor survived reassign");
  ctx.S.shadowChat = "global";
  assert.strictEqual(ctx.S.shadowThread.length, 1, "global tab untouched");
  assert.strictEqual(ctx.S.shadowThread[0].text, "general");
  console.log("ok 11 per-tab threads isolated (accessor, not alias)");
}
{
  const ctx = fresh();
  ctx.S.shadowSettings = { engage: ["outcome first"],
    global: [{ id: "i-1", text: "everywhere rule" }],
    per_chat: { "sess-paisa": [{ id: "i-2", text: "paisa rule" }] },
    attention: { watching: ["a"], off: [], alerts: 2 },
    floors: ["destructive git"] };
  const h = ctx.shadowSettingsHtml();
  assert(/everywhere rule/.test(h) && /paisa rule/.test(h),
    "settings shows global and per-chat rules");
  assert(/data-shrevoke="i-2"/.test(h), "each rule can be revoked");
  assert(/not editable/.test(h), "floors are shown as not editable");
  console.log("ok 12 settings surface");
}

/* v10: per-chat tabs — one mind, many threads */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowWatching = ["sess-paisa", "sess-dayflow"];
  /* POLISH PASS: the chip's menu is drawn from the app's own chat list, not
     from the watching store (which holds raw ids the app cannot name), so a
     pickable chat has to be a listed chat. */
  ctx.S.sessions = [{ id: "sess-paisa", title: "Paisa", updated_ms: 200 },
                    { id: "sess-dayflow", title: "Dayflow", updated_ms: 100 }];
  ctx.S.shadowMissions = [{ id: "m-1", objective: "x", state: "running",
                            target_session: "sess-paisa" }];
  /* SLICE 11: the tab strip is gone from Home; scoping is one chip.
     WORKSPACE SLICE: that chip lives in the existing-chat flow, which the
     delegated-task workspace renders only when it is opened. */
  ctx.S.shadowExistingOpen = true;
  const h = ctx.shadowHomeHtml();
  assert(!/shchattabs/.test(h), "the tab strip is not on Home any more");
  assert(/data-shscopepick/.test(h), "the target chat is a single chip");
  ctx.S.shadowScopeOpen = true;
  const open2 = ctx.shadowHomeHtml();
  assert(/data-shchat="sess-paisa"/.test(open2), "a chat can be picked");
  console.log("ok 10 tab strip removed; scoping is one chip");
}
{
  /* threads are isolated per tab, and the accessor survives reassignment */
  const ctx = fresh();
  ctx.S.shadowChat = "global";
  ctx.S.shadowThread.push({ who: "founder", text: "general" });
  ctx.S.shadowChat = "sess-paisa";
  ctx.S.shadowThread.push({ who: "founder", text: "about paisa" });
  assert.strictEqual(ctx.S.shadowThread.length, 1, "paisa tab has its own");
  ctx.S.shadowThread = ctx.S.shadowThread.filter(t => !t.busy);   /* the reassign */
  ctx.S.shadowThread.push({ who: "shadow", text: "still paisa" });
  assert.strictEqual(ctx.S.shadowThread.length, 2, "accessor survived reassign");
  ctx.S.shadowChat = "global";
  assert.strictEqual(ctx.S.shadowThread.length, 1, "global tab untouched");
  assert.strictEqual(ctx.S.shadowThread[0].text, "general");
  console.log("ok 11 per-tab threads isolated (accessor, not alias)");
}
{
  const ctx = fresh();
  ctx.S.shadowSettings = { engage: ["outcome first"],
    global: [{ id: "i-1", text: "everywhere rule" }],
    per_chat: { "sess-paisa": [{ id: "i-2", text: "paisa rule" }] },
    attention: { watching: ["a"], off: [], alerts: 2 },
    floors: ["destructive git"] };
  const h = ctx.shadowSettingsHtml();
  assert(/everywhere rule/.test(h) && /paisa rule/.test(h),
    "settings shows global and per-chat rules");
  assert(/data-shrevoke="i-2"/.test(h), "each rule can be revoked");
  assert(/not editable/.test(h), "floors are shown as not editable");
  console.log("ok 12 settings surface");
}

/* v10: per-chat tabs — one mind, many threads */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowWatching = ["sess-paisa", "sess-dayflow"];
  /* POLISH PASS: the chip's menu is drawn from the app's own chat list, not
     from the watching store (which holds raw ids the app cannot name), so a
     pickable chat has to be a listed chat. */
  ctx.S.sessions = [{ id: "sess-paisa", title: "Paisa", updated_ms: 200 },
                    { id: "sess-dayflow", title: "Dayflow", updated_ms: 100 }];
  ctx.S.shadowMissions = [{ id: "m-1", objective: "x", state: "running",
                            target_session: "sess-paisa" }];
  /* SLICE 11: the tab strip is gone from Home; scoping is one chip.
     WORKSPACE SLICE: that chip lives in the existing-chat flow, which the
     delegated-task workspace renders only when it is opened. */
  ctx.S.shadowExistingOpen = true;
  const h = ctx.shadowHomeHtml();
  assert(!/shchattabs/.test(h), "the tab strip is not on Home any more");
  assert(/data-shscopepick/.test(h), "the target chat is a single chip");
  ctx.S.shadowScopeOpen = true;
  const open2 = ctx.shadowHomeHtml();
  assert(/data-shchat="sess-paisa"/.test(open2), "a chat can be picked");
  console.log("ok 10 tab strip removed; scoping is one chip");
}
{
  /* threads are isolated per tab, and the accessor survives reassignment */
  const ctx = fresh();
  ctx.S.shadowChat = "global";
  ctx.S.shadowThread.push({ who: "founder", text: "general" });
  ctx.S.shadowChat = "sess-paisa";
  ctx.S.shadowThread.push({ who: "founder", text: "about paisa" });
  assert.strictEqual(ctx.S.shadowThread.length, 1, "paisa tab has its own");
  ctx.S.shadowThread = ctx.S.shadowThread.filter(t => !t.busy);   /* the reassign */
  ctx.S.shadowThread.push({ who: "shadow", text: "still paisa" });
  assert.strictEqual(ctx.S.shadowThread.length, 2, "accessor survived reassign");
  ctx.S.shadowChat = "global";
  assert.strictEqual(ctx.S.shadowThread.length, 1, "global tab untouched");
  assert.strictEqual(ctx.S.shadowThread[0].text, "general");
  console.log("ok 11 per-tab threads isolated (accessor, not alias)");
}
{
  const ctx = fresh();
  ctx.S.shadowSettings = { engage: ["outcome first"],
    global: [{ id: "i-1", text: "everywhere rule" }],
    per_chat: { "sess-paisa": [{ id: "i-2", text: "paisa rule" }] },
    attention: { watching: ["a"], off: [], alerts: 2 },
    floors: ["destructive git"] };
  const h = ctx.shadowSettingsHtml();
  assert(/everywhere rule/.test(h) && /paisa rule/.test(h),
    "settings shows global and per-chat rules");
  assert(/data-shrevoke="i-2"/.test(h), "each rule can be revoked");
  assert(/not editable/.test(h), "floors are shown as not editable");
  console.log("ok 12 settings surface");
}

/* tabs wear the chat's real name, from the list the rail already loads */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.sessions = [
    { id: "sess-paisa", title: "Paisa EMI rounding fix" },
    { id: "sess-long", title: "A very long chat title that must be trimmed somewhere" },
    { id: "sess-lbl", label: "named by first line" },
  ];
  ctx.S.shadowWatching = ["sess-paisa", "sess-long", "sess-lbl", "sess-unknown"];
  assert.strictEqual(ctx.shadowChatLabel("sess-paisa"), "Paisa EMI rounding fix");
  assert(ctx.shadowChatLabel("sess-long").length <= 24, "long titles trim");
  assert(/\u2026$/.test(ctx.shadowChatLabel("sess-long")), "trim shows an ellipsis");
  assert.strictEqual(ctx.shadowChatLabel("sess-lbl"), "named by first line");
  assert(/^session /.test(ctx.shadowChatLabel("sess-unknown")),
    "an unknown chat says session <id>, never a bare id");
  assert.strictEqual(ctx.shadowChatLabel("global"), "new");
  /* SLICE 11: names are now worn by the scope picker rather than a strip --
     same shadowChatLabel, same no-raw-id rule. */
  ctx.S.shadowScopeOpen = true;
  ctx.S.shadowExistingOpen = true;   /* the picker lives in that flow now */
  const h = ctx.shadowHomeHtml();
  assert(/Paisa EMI rounding fix/.test(h), "the picker renders the name");
  assert(!/>sess-pai/.test(h), "no raw id leaks into a label");
  console.log("ok 13 chats wear real names in the scope picker");
}

/* ── 14-19: the Shadow workspace + "+ Delegate" ─────────────────────────
   The one NEW capability: an explicit "start a NEW task in a NEW chat" that
   does not depend on Shadow's model output to establish the intent. */

/* 14. the two columns exist, and everything that was on the briefing still is */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = MISSIONS;
  const h = ctx.shadowHomeHtml();
  assert(/class="shwork"/.test(h), "workspace container missing");
  assert(/class="shwleft"/.test(h) && /class="shwright"/.test(h),
    "two columns missing");
  /* + Delegate is visible, prominent and in the left column */
  assert(/data-shdelegate="1"/.test(h), "+ Delegate is not rendered");
  assert(/\+ Delegate</.test(h), "+ Delegate is not labelled");
  assert(/Shadow is working on/i.test(h), "section label missing");
  /* the composer and the foot nav are always here */
  assert(/data-shhomecompose/.test(h), "Shadow composer was lost");
  assert(/data-shwatching/.test(h) && /data-shmemopen/.test(h)
      && /data-shscreen="shadowsettings"/.test(h),
    "the foot nav (Watching/Memory/Settings) was lost");
  console.log("ok 14 workspace: two columns, + Delegate, nothing lost");
}

/* 14b. THE DELEGATED WORKSPACE IS TASK-FOCUSED.
   The existing-chat flow is PRESERVED, not rendered: preserving a behaviour
   and always showing its UI are different things, and this workspace is
   about one delegated task. Opening the flow brings the whole thing back
   exactly as it was. */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = MISSIONS;
  ctx.S.sessions = [{ id: "s-1", title: "paisa emi" }];
  ctx.S.shadowWatching = ["s-1"];
  const closed = ctx.shadowHomeHtml();
  /* none of the existing-chat surface by default */
  assert(!/data-shscopepick/.test(closed), "'Working with' picker rendered");
  assert(!/Choose a conversation/.test(closed), "'Choose a conversation' rendered");
  assert(!/Recent conversations/.test(closed), "recent-chat chips rendered");
  assert(!/Tell Shadow the outcome you want/.test(closed),
    "the old briefing copy rendered");
  assert(!/data-shchat=/.test(closed), "chat chips (+N more) rendered");
  /* but the composer is still there, with the SAME hook and scope attribute */
  assert(/data-shhomecompose/.test(closed), "the workspace has no composer");
  assert(/data-shscope=/.test(closed), "the composer lost its scope attribute");
  /* and the door into the flow is offered */
  assert(/data-shexisting="1"/.test(closed), "no way into the existing-chat flow");

  /* opened: the real stage, unchanged */
  ctx.S.shadowExistingOpen = true;
  const open = ctx.shadowHomeHtml();
  assert(/data-shscopepick/.test(open), "the picker did not come back");
  assert(/Choose a conversation/.test(open), "the picker lost its copy");
  assert(/Recent conversations/.test(open), "the recent chips did not come back");
  assert(/Tell Shadow the outcome you want/.test(open),
    "the briefing copy did not come back");
  assert(/data-shexisting="0"/.test(open), "no way back to the tasks");
  console.log("ok 14b existing-chat flow: preserved, opt-in, not default");
}

/* 14c. NO GLOBAL HISTORY UNDER A DELEGATED TASK.
   shadowDeckHtml renders every goal Shadow has ever carried -- "Shadow's
   Work", the count, "Recently completed", the cards. That is a history of
   goals, not the state of one task, so it does not belong under the task in
   focus. The deck itself is untouched and still the goals screen's content;
   only this workspace stops rendering it.

   Reachability is the thing that must NOT regress: the deck's "N more — open
   all goals" button was the only route to SCREENS.goals, so the footer nav
   carries the same data-shgoals hook now. */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = MISSIONS;
  ctx.S.goals = Array.from({ length: 12 }, (_, i) => ({
    id: "g-" + i, outcome: "goal " + i,
    state: i < 3 ? "working" : (i < 5 ? "blocked" : "done"),
    checks_met: 1, checks_total: 2, checks_label: "1 of 2",
    unmet: ["x"], turn_label: "turn 1/20", attempt: 1 }));
  const h = ctx.shadowHomeHtml();
  assert(!/Shadow.s Work/.test(h), "'Shadow's Work' rendered under the task");
  assert(!/\d+ assignments?/.test(h), "the assignment count rendered");
  assert(!/Recently completed/.test(h), "completed history rendered");
  assert(!/class="shasg/.test(h), "assignment cards rendered");
  assert(!/class="shdeck/.test(h), "the deck container rendered");

  /* the goals screen keeps its route, and the count is live goals only */
  assert(/data-shgoals="1"/.test(h), "the goals screen became unreachable");
  assert(/Goals · 5/.test(h), "the footer must count LIVE goals (3+2), got "
    + (h.match(/Goals · \d+/) || ["none"])[0]);
  /* and the renderer is still there for the screen that owns it */
  assert(typeof ctx.shadowDeckHtml === "function",
    "shadowDeckHtml must not be deleted -- only not called here");
  assert(/Shadow.s Work/.test(ctx.shadowDeckHtml()),
    "the deck itself must still render its own content");
  console.log("ok 14c no assignment history under a delegated task");
}

/* 15. the task list is REACHABLE and states every mission state */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [
    { id: "m-a", objective: "ready one",   state: "brief_confirm" },
    { id: "m-b", objective: "running one", state: "running" },
    { id: "m-c", objective: "queued one",  state: "queued" },
    { id: "m-d", objective: "blocked one", state: "blocked" },
    { id: "m-e", objective: "failed one",  state: "failed" },
  ];
  const h = ctx.shadowHomeHtml();
  ["READY", "RUNNING", "QUEUED", "NEEDS YOU", "FAILED"].forEach(p =>
    assert(new RegExp(">" + p + "<").test(h), "status pill missing: " + p));
  assert(/data-shtask="m-a"/.test(h), "task rows are not selectable");
  /* the empty state says what to do, rather than nothing */
  const ctx2 = fresh();
  ctx2.S.shadowHomeDark = false; ctx2.S.shadowMissions = [];
  assert(/Delegate a task/.test(ctx2.shadowHomeHtml()), "no empty-state copy");
  console.log("ok 15 task list reachable, all states named");
}

/* 15b. THE LIST IS ACTIVE WORK, NOT THE MISSION DATABASE.
   /api/shadow/missions returns MissionStore.list() -- every record on disk,
   deliberately, because other readers need the whole history. The workspace
   filters at the PRESENTATION layer only: nothing is deleted, no store or API
   semantics move, and every record stays where the goals' attempts[] point. */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [
    { id: "g-live", state: "working" },     /* still being pursued */
    { id: "g-over", state: "stopped" },     /* the founder abandoned it */
    { id: "g-won",  state: "done" },
  ];
  ctx.S.shadowMissions = [
    /* --- must appear: unfinished work -------------------------------- */
    { id: "m-ready",   objective: "ready",   state: "brief_confirm" },
    { id: "m-run",     objective: "running", state: "running" },
    { id: "m-queue",   objective: "queued",  state: "queued" },
    { id: "m-pause",   objective: "paused",  state: "paused",
      pause_reason: "founder_confirm", target_mode: "new" },
    { id: "m-blocked", objective: "blocked", state: "blocked",
      block_reason: "ping_pong", goal_id: "g-live" },
    { id: "m-fail",    objective: "failed",  state: "failed" },
    /* --- must NOT appear: concluded ----------------------------------- */
    { id: "m-done",    objective: "old done",    state: "done" },
    { id: "m-stop",    objective: "old stopped", state: "stopped",
      ended_by: "founder" },
    { id: "m-retried", objective: "superseded",  state: "failed",
      retried_to: "m-fresh" },
    /* a goal that has concluded settles its attempts, whatever state they
       were left in -- abandoning a goal stops the LIVE attempt, so one that
       was already blocked keeps that state forever and would otherwise
       shout NEEDS YOU about work the founder ended */
    { id: "m-vestigial", objective: "blocked under a stopped goal",
      state: "blocked", block_reason: "ping_pong", goal_id: "g-over" },
    { id: "m-wonattempt", objective: "attempt of a finished goal",
      state: "done", goal_id: "g-won" },
  ];
  const ids = ctx.shadowTasks().map(m => m.id);
  const h = ctx.shadowHomeHtml();

  /* 1. active missions appear */
  ["m-ready", "m-run", "m-queue"].forEach(id =>
    assert(ids.includes(id), "active mission hidden: " + id));
  /* 2. paused / founder_confirm appears -- it is waiting on the founder */
  assert(ids.includes("m-pause"), "a paused founder_confirm task was hidden");
  /* 3. an actionable blocked mission appears (its goal is still live) */
  assert(ids.includes("m-blocked"), "an actionable blocked mission was hidden");
  /* a failed mission keeps its pending Retry */
  assert(ids.includes("m-fail"), "a retryable failure was hidden");
  /* 4. historical terminal records do not */
  ["m-done", "m-stop", "m-retried", "m-vestigial", "m-wonattempt"]
    .forEach(id => assert(!ids.includes(id), "history leaked into the list: " + id));
  assert(!/old done|old stopped|superseded/.test(h),
    "concluded work rendered in the workspace");

  /* 5. the RECORDS are untouched -- this is a filter, not a delete */
  assert.strictEqual(ctx.S.shadowMissions.length, 11,
    "the mission list itself must not be mutated");
  assert(ctx.S.shadowMissions.some(m => m.id === "m-done"),
    "a hidden mission must still be in state");
  /* 6. goals untouched */
  assert.strictEqual(ctx.S.goals.length, 3, "goals must not be touched");
  assert(ctx.S.goals.every(g => g.state),
    "no goal record was altered by rendering");

  /* 7. the actions still work on what IS shown */
  ctx.S.shadowTaskSel = "m-ready";
  assert(/data-shstart="m-ready"/.test(ctx.shadowHomeHtml()),
    "Start was lost from a shown task");
  ctx.S.shadowTaskSel = "m-fail";
  assert(/data-shact="retry"[\s\S]{0,60}data-shmid="m-fail"/
    .test(ctx.shadowHomeHtml()), "Retry was lost from a shown failure");

  /* goals not loaded yet: err toward SHOWING work, never toward hiding it */
  const ctx2 = fresh();
  ctx2.S.shadowHomeDark = false;
  ctx2.S.shadowMissions = [{ id: "m-x", objective: "x", state: "blocked",
                             goal_id: "g-unknown" }];
  assert(ctx2.shadowTasks().map(m => m.id).includes("m-x"),
    "an unknown goal must not hide live work");
  console.log("ok 15b active work only; history stays on disk and in Goals");
}

/* 16. + Delegate opens the new-task panel IN THE RIGHT PANE, and says NEW CHAT */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = MISSIONS;
  assert(!/data-shnewpanel/.test(ctx.shadowHomeHtml()), "panel open by default");
  ctx.S.shadowNewOpen = true;
  const h = ctx.shadowHomeHtml();
  assert(/data-shnewpanel="1"/.test(h), "panel did not open");
  assert(/What should Shadow get done\?/.test(h), "the ask is missing");
  assert(/new chat/.test(h), "must say Shadow starts a NEW chat");
  assert(/data-shnewobj/.test(h), "no outcome field");
  assert(/data-shnewdone/.test(h), "no optional done-when field");
  assert(/data-shnewkind="fix"/.test(h), "no template choice");
  assert(/class="shkind on"[^>]*data-shnewkind="fix"/.test(h)
      || /data-shnewkind="fix"/.test(h) && /shkind on/.test(h),
    "fix is not the default");
  /* the panel lives in the right column, not a modal overlay */
  assert(h.indexOf('class="shwright"') < h.indexOf("data-shnewpanel"),
    "the new-task panel is not in the right pane");
  /* target_mode is BACKEND vocabulary and must never reach the operator */
  assert(!/target_mode/.test(h), "target_mode leaked into the UI");
  console.log("ok 16 + Delegate opens the new-task panel, in the right pane");
}

/* 17. THE WRITE: the exact body the existing endpoint receives.
   An async test in a sync file: an IIFE, never a top-level `return` -- that
   would END THE MODULE and silently skip every test after it. */
(async () => {
  const ctx = fresh();
  const posts = [];
  ctx.S.shadowHomeDark = false;
  ctx.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({ id: "m-new", state: "brief_confirm" }) });
  ctx.shadowPost = (url, body) => {
    posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ id: "m-new", state: "brief_confirm" }) });
  };
  ctx.loadShadowHome = () => Promise.resolve();
  ctx.scheduleRender = () => {};
  ctx.S.shadowNew = { objective: "  Fix the EMI rounding  ",
                      done: "tests pass\n\nPR open", kind: "research" };
  await ctx.shadowCreateTask();
  assert.strictEqual(posts.length, 1, "expected exactly one POST");
  assert.strictEqual(posts[0].url, "/api/shadow/missions",
    "must reuse the EXISTING mission endpoint");
  const b = posts[0].body;
  assert.strictEqual(b.target_mode, "new",
    "the button, not the model, establishes the NEW-chat intent");
  assert.strictEqual(b.objective, "Fix the EMI rounding", "objective trimmed");
  assert.strictEqual(b.template, "research", "the chosen kind is sent");
  /* JSON round-trip: values built inside the vm context carry that realm's
     Array prototype, so a bare deepStrictEqual fails on identical data --
     the same reason test 8 above compares bodies this way. */
  assert.deepStrictEqual(
    JSON.parse(JSON.stringify(b.done_when.map(c => c.check))),
    ["tests pass", "PR open"], "blank lines dropped, order kept");
  assert(b.done_when.every(c => c.tier === "founder_confirm"),
    "a founder's own words are theirs to confirm");
  assert(/Fix the EMI rounding/.test(b.manifest), "manifest carries the objective");
  /* nothing is started: Start stays a separate, explicit press */
  assert(!posts.some(p => /\/act$/.test(p.url)), "creation must not start work");
  assert.strictEqual(ctx.S.shadowNewOpen, false, "panel closes on success");
  assert.strictEqual(ctx.S.shadowTaskSel, "m-new", "the new task takes focus");
  console.log("ok 17 + Delegate posts target_mode:new to the existing endpoint");
})().catch(e => { console.error("FAIL 17:", e.message); process.exit(1); });

/* 18. an empty outcome is refused client-side, with no POST */
{
  const ctx = fresh();
  const posts = [];
  ctx.shadowPost = (url, body) => { posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({}) }); };
  ctx.fetch = () => Promise.resolve({ ok: true });
  ctx.scheduleRender = () => {};
  ctx.S.shadowNew = { objective: "   ", done: "", kind: "fix" };
  ctx.shadowCreateTask();
  assert.strictEqual(posts.length, 0, "an empty outcome must not be posted");
  assert(/will not guess/.test(ctx.S.shadowNewErr || ""), "no honest error");
  console.log("ok 18 an empty outcome is refused, nothing is sent");
}

/* 19. the task card: the brief, with Start, and the existing actions */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowSettings = { floors: ["destructive git operations",
                                    "external client repositories"] };
  ctx.S.shadowMissions = [{ id: "m-k", objective: "fix the EMI rounding",
    state: "brief_confirm", template: "fix", target_mode: "new",
    target_session: null, turns_used: 0, max_turns: 20,
    done_when: [{ tier: "founder_confirm", check: "a tested PR is open" }] }];
  ctx.S.shadowTaskSel = "m-k";
  const h = ctx.shadowHomeHtml();
  assert(/fix the EMI rounding/.test(h), "objective missing");
  assert(/acts in/.test(h) && /a new chat/.test(h),
    "must say it runs in a new chat Shadow starts");
  assert(/done when/.test(h) && /a tested PR is open/.test(h), "done-when missing");
  assert(/data-shstart="m-k"/.test(h), "Start the task missing");
  assert(/Start the task</.test(h), "Start is not labelled as the design asks");
  assert(/or keep telling me/.test(h), "the keep-talking affordance is missing");
  assert(/destructive git operations/.test(h), "floors not surfaced");
  /* a failed task offers the EXISTING retry, not a new mechanism */
  ctx.S.shadowMissions = [{ id: "m-f", objective: "nope", state: "failed",
    template: "fix", target_mode: "new", turns_used: 20, max_turns: 20 }];
  ctx.S.shadowTaskSel = "m-f";
  const f = ctx.shadowHomeHtml();
  assert(/data-shact="retry"[\s\S]{0,60}data-shmid="m-f"/.test(f),
    "a failed task must offer the existing retry");
  assert(/>FAILED</.test(f), "failure is not stated in the task UI");
  console.log("ok 19 task card: brief, Start, floors, retry on failure");
}

/* 20. THE TWO DEFECTS THE POLISH PASS FOUND, as a standing guard.

   Neither was visible to any test above -- both rendered valid markup and
   valid CSS, and both looked catastrophic on screen:

     a) a CLASS COLLISION. The workspace's status pill was called .shpill,
        which panel.css already used for the overlay's floating notification
        (position:fixed; z-index:60). Every status pill inherited that, left
        the flow, and stacked on top of the page.
     b) AN UNSIZED <svg>. shadowNavHtml's icons carry a viewBox and no
        width/height, and nothing styled them -- so each took the CSS default
        intrinsic size, 300x150px, and four footer rows rendered as four
        dashboard tiles.

   So this asserts the two invariants, not the two symptoms: every sh* class
   the workspace emits resolves to a rule, and every <svg> it emits has a size
   from somewhere. */
{
  const cssTxt = fs.readFileSync(
    path.join(__dirname, "static", "panel.css"), "utf8");
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowSettings = { floors: ["destructive git operations"] };
  ctx.S.shadowMissions = MISSIONS;
  ctx.S.goals = [{ id: "g-1", outcome: "ship it", state: "working",
    checks_met: 1, checks_total: 3, checks_label: "1 of 3", unmet: ["x"],
    turn_label: "turn 2/20", attempt: 1 }];
  ctx.S.sessions = [{ id: "s-1", title: "paisa emi" }];
  ctx.S.shadowWatching = ["s-1"]; ctx.S.shadowMemory = [];
  ctx.S.shadowScopeOpen = true;
  ctx.S.shadowThread = [{ who: "shadow", text: "hi" }];
  const h = ctx.SCREENS.shadow();

  /* (a) the pill must not wear a class the overlay already owns */
  assert(!/class="[^"]*\bshpill\b/.test(h),
    ".shpill is the overlay's fixed-position pill -- the workspace must not "
    + "reuse it");

  /* every sh* class resolves to a rule. Optional STATE modifiers are the one
     allowance: .shasg-<state> and .shstatus-<state> decorate a base class
     that is styled, and adding colours for goal states would be redesigning
     Goals, which this pass must not do. */
  const seen = new Set();
  for (const m of h.matchAll(/class="([^"]+)"/g))
    m[1].split(/\s+/).filter(Boolean).forEach(c => seen.add(c));
  const optional = /^(shasg|shstatus)-/;
  const unstyled = [...seen].filter(c => /^sh/.test(c) && !optional.test(c)
    && !new RegExp("\\." + c.replace(/-/g, "\\-") + "\\b").test(cssTxt));
  assert.deepStrictEqual(unstyled, [],
    "sh* classes with no CSS rule (this is how the 300x150 icons happened): "
    + unstyled.join(", "));

  /* (b) every icon has an intrinsic size, from the attribute or from CSS */
  const svgs = [...h.matchAll(/<svg\b[^>]*>/g)].map(s => s[0]);
  assert(svgs.length > 0, "expected icons in the workspace");
  /* An icon is sized either by its own class or by an ancestor-scoped
     `<wrapper> svg{width:…}` rule, so the check looks at the classes in
     scope at that point in the markup rather than at the tag alone. */
  const bare = [];
  const rx = /<svg\b[^>]*>/g;
  let mm;
  while ((mm = rx.exec(h)) !== null){
    const tag = mm[0];
    if (/\swidth="/.test(tag)) continue;
    const own = (tag.match(/class="([^"]*)"/) || [])[1] || "";
    /* every class opened before this point -- the svg's ancestors are among
       them, which is enough to prove a descendant rule can reach it */
    const inScope = new Set(own.split(/\s+/).filter(Boolean));
    for (const c of h.slice(0, mm.index).matchAll(/class="([^"]+)"/g))
      c[1].split(/\s+/).filter(Boolean).forEach(x => inScope.add(x));
    const sized = [...inScope].some(c =>
      new RegExp("\\." + c.replace(/-/g, "\\-")
        + "(?:\\b[^{]*)?\\{[^}]*width:").test(cssTxt)
      || new RegExp("\\." + c.replace(/-/g, "\\-")
        + "\\b[^{]*svg\\{[^}]*width:").test(cssTxt));
    if (!sized) bare.push(tag.slice(0, 70));
  }
  assert.deepStrictEqual(bare, [],
    "an <svg> with no width attribute and nothing sizing it in CSS defaults "
    + "to 300x150px: " + bare.join(" | "));
  /* the footer icons are the ones that bit, and they are sized by descendant
     rule rather than by their own class -- pin that rule explicitly */
  assert(/\.shwleft \.shnavitem svg\{[^}]*width:/.test(cssTxt),
    "the footer nav icons must be sized in CSS -- their markup carries none");

  /* and the footer stays subordinate: no border, no fill, small type */
  assert(/\.shwleft \.shnavitem\{[^}]*border:0/.test(cssTxt),
    "the footer nav must not render as bordered cards");
  console.log("ok 20 no class collisions, no unstyled classes, no unsized icons");
}

console.log("test_shadow_home.js: all green");
