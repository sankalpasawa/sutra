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
    /* listeners are RECORDED, not discarded: the delegated click handler is
       the only way to exercise a card action end to end, and it was
       previously unreachable from here. Keyed by type -- the home module is
       the only document-level click listener in this context. */
    listeners: {},
    document: { addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return {
      setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; } },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);   /* missionCardHtml + shared thread */
  vm.runInContext(src, ctx);
  return ctx;
}

/* one context, reused for the pure predicate assertions below */
let _ctx0 = null;
function ctx0(){ if (!_ctx0) _ctx0 = fresh(); return _ctx0; }

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
  /* THE FOOTER IS ONE DOOR NOW (v7 design of record). Watching, Memory,
     Goals and Conversations are not deleted -- they moved behind it, and
     the settings test below pins that they are still reachable. */
  assert(/data-shscreen="shadowsettings"/.test(h),
    "the way into Shadow Settings was lost");
  assert(/Shadow Settings</.test(h), "the settings door is not labelled");
  assert(!/data-shwatching/.test(h) && !/data-shmemopen/.test(h)
      && !/data-shgoals/.test(h) && !/data-shchats/.test(h),
    "the workspace footer must be one door, not the old five-link index");
  console.log("ok 14 workspace: two columns, + Delegate, one settings door");
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

  /* the goals screen keeps its route and its live-goal count -- both moved
     from the workspace footer into Settings > Attention, which is the only
     thing that changed about them */
  assert(!/data-shgoals="1"/.test(h), "goals still listed in the workspace");
  ctx.S.shadowSettings = { engage: [], global: [], per_chat: {},
    attention: { watching: ["a"], off: [], alerts: 0 }, floors: [] };
  const set = ctx.shadowSettingsHtml();
  assert(/data-shgoals="1"/.test(set), "the goals screen became unreachable");
  assert(/Goals · 5/.test(set), "Settings must count LIVE goals (3+2), got "
    + (set.match(/Goals · \d+/) || ["none"])[0]);
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
    /* the founder pressed Stop: they know it exists and may still Retry it */
    { id: "m-stop",    objective: "old stopped", state: "stopped",
      ended_by: "founder" },
    /* --- must NOT appear: concluded ----------------------------------- */
    { id: "m-done",    objective: "old done",    state: "done" },
    /* a MACHINE stop (ping-pong) carries no ended_by and stays history */
    { id: "m-mstop",   objective: "machine stopped", state: "stopped" },
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
  /* a stop the FOUNDER pressed stays: it is not history until they say so */
  assert(ids.includes("m-stop"), "a founder-stopped task was hidden");
  /* 4. historical terminal records do not */
  ["m-done", "m-mstop", "m-retried", "m-vestigial", "m-wonattempt"]
    .forEach(id => assert(!ids.includes(id), "history leaked into the list: " + id));
  assert(!/old done|machine stopped|superseded/.test(h),
    "concluded work rendered in the workspace");

  /* 5. the RECORDS are untouched -- this is a filter, not a delete */
  assert.strictEqual(ctx.S.shadowMissions.length, 12,
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

/* 15c. STOP MUST NOT LOOK LIKE DELETE (founder, 2026-09-14).

   Clicking Stop ran founder_stop, left the record on disk and reaped the
   delegate -- all correct -- and then the row vanished from the list in the
   same gesture. That reads as the task having been deleted, and it took the
   Retry button with it: the card only renders for a mission shadowTasks()
   still returns, so the one action a stopped task offers was unreachable.

   The discriminator is the one founder_stop ALREADY writes. These pin each
   arm of it separately, because "stopped" is two endings in one state. */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];

  const only = (rows) => { ctx.S.shadowMissions = rows;
    return ctx.shadowTasks().map(m => m.id); };

  /* 1. the founder pressed Stop -> stays */
  assert.deepStrictEqual(
    only([{ id: "m-fs", objective: "x", state: "stopped",
            ended_by: "founder" }]), ["m-fs"],
    "a founder-stopped mission must stay visible");

  /* 2. the MACHINE stopped it (ping-pong, ask_founder on a standalone
        mission before it learned to block) -> still history */
  assert.deepStrictEqual(
    only([{ id: "m-ms", objective: "x", state: "stopped" }]), [],
    "a machine stop must stay hidden");
  assert.deepStrictEqual(
    only([{ id: "m-ms2", objective: "x", state: "stopped",
            ended_by: "machine" }]), [],
    "only ended_by=founder qualifies");

  /* 3. done is untouched: nothing is left to want */
  assert.deepStrictEqual(
    only([{ id: "m-done", objective: "x", state: "done",
            ended_by: "founder" }]), [],
    "a completed mission must never come back into the list");

  /* 4. a founder stop that was RETRIED steps aside for its successor --
        the same rule the failed arm has always used */
  assert.deepStrictEqual(
    only([{ id: "m-old", objective: "x", state: "stopped",
            ended_by: "founder", retried_to: "m-new" }]), [],
    "a retried founder-stop must step aside");

  /* 5. the failed arm is completely unchanged */
  assert.deepStrictEqual(
    only([{ id: "m-f", objective: "x", state: "failed" }]), ["m-f"],
    "an un-retried failure must still show");
  assert.deepStrictEqual(
    only([{ id: "m-f2", objective: "x", state: "failed",
            retried_to: "m-new" }]), [],
    "a retried failure must still step aside");

  /* 6. the restored row is ACTIONABLE -- Retry was the point */
  ctx.S.shadowMissions = [{ id: "m-fs", objective: "stopped task",
                            state: "stopped", ended_by: "founder" }];
  ctx.S.shadowTaskSel = "m-fs";
  const h = ctx.shadowHomeHtml();
  assert(/data-shtask="m-fs"/.test(h), "the row must render");
  assert(/data-shact="retry"[\s\S]{0,60}data-shmid="m-fs"/.test(h),
    "a founder-stopped task must offer Retry");
  assert(/STOPPED/.test(h), "it must still read as stopped, not as live work");

  /* 7. nothing was mutated -- this is a filter, not a write */
  assert.strictEqual(ctx.S.shadowMissions.length, 1);
  assert.strictEqual(ctx.S.shadowMissions[0].state, "stopped");
  assert.strictEqual(ctx.S.shadowMissions[0].ended_by, "founder");
  console.log("ok 15c a founder stop stays visible and retryable; "
    + "machine stops and done stay history");
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
      json: () => Promise.resolve(/\/act$/.test(url)
        ? { accepted: true, mission_id: "m-new" }
        : { id: "m-new", state: "brief_confirm" }) });
  };
  ctx.loadShadowHome = () => Promise.resolve();
  ctx.renderShadowCard = () => {};
  ctx.showNudge = () => {};
  ctx.scheduleRender = () => {};
  ctx.S.shadowNew = { objective: "  Fix the EMI rounding  ",
                      done: "tests pass\n\nPR open", kind: "research" };
  await ctx.shadowCreateTask();
  const creates = posts.filter(p => p.url === "/api/shadow/missions");
  assert.strictEqual(creates.length, 1, "expected exactly one CREATE");
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
  /* CREATE IS THE START (2026-09-14). This assertion used to read "creation
     must not start work" -- it is reversed on purpose, and it is the pin for
     Fix 3: the form the founder filled in IS the confirmation, so a second
     press was asking them to agree with themselves. What has NOT changed is
     how it starts: the same /act start_now the Start button posts, once, on
     the mission that was just created -- no second create, no second launch
     path and no duplicate spawn. */
  const acts = posts.filter(p => /\/act$/.test(p.url));
  assert.strictEqual(acts.length, 1, "create must start the task, exactly once");
  assert.strictEqual(acts[0].url, "/api/shadow/missions/m-new/act",
    "the start must be posted to the mission that was just created");
  assert.strictEqual(acts[0].body.action, "start_now",
    "must reuse the EXISTING start action, not a new launch path");
  assert.strictEqual(posts.length, 2, "one create + one start, and nothing else");
  assert.strictEqual(ctx.S.shadowNewOpen, false, "panel closes on success");
  assert.strictEqual(ctx.S.shadowTaskSel, "m-new", "the new task takes focus");
  assert.strictEqual(ctx.S.shadowNewBusy, false, "the panel must let go of busy");
  console.log("ok 17 + Delegate creates AND starts, through the existing paths");
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

/* 21. THE SIGN-OFF: a delegated task that finished and is waiting on the
   founder. The engine parks it at paused/founder_confirm, confirm_check is
   the only writer of a founder_confirm `met` flag, and until this the card
   offered Resume and Stop -- neither of which is "yes, that is done". */
const AWAITING = {
  id: "m-fib", objective: "a README on Fibonacci", state: "paused",
  pause_reason: "founder_confirm", template: "fix", target_mode: "new",
  target_session: "sess-fib", turns_used: 1, max_turns: 20,
  done_when: [
    { tier: "founder_confirm", check: "the README explains it clearly",
      met: true, confirmed_by: "founder" },
    { tier: "founder_confirm", check: "a working Python example is included" },
    { tier: "transcript", check: "the example is syntactically correct" },
  ],
};

/* 21a. it reads NEEDS YOU, everywhere the state is shown */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [JSON.parse(JSON.stringify(AWAITING))];
  ctx.S.shadowTaskSel = "m-fib";
  const h = ctx.shadowHomeHtml();
  assert(!/>PAUSED</.test(h),
    "waiting on the founder must not read as a stalled task");
  assert((h.match(/>NEEDS YOU</g) || []).length >= 2,
    "NEEDS YOU in both the list row and the task header");
  assert(/shtpill-blocked/.test(h), "it wears the needs-you pill family");
  /* a mission paused for any OTHER reason is untouched */
  ctx.S.shadowMissions = [{ id: "m-r", objective: "x", state: "paused",
    pause_reason: "app_restart", done_when: [] }];
  ctx.S.shadowTaskSel = "m-r";
  assert(/>PAUSED</.test(ctx.shadowHomeHtml()),
    "a restart pause still reads PAUSED -- nothing is being asked");
  console.log("ok 21a founder_confirm reads NEEDS YOU");
}

/* 21b. what am I agreeing to? Every criterion, in full, before its button */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [JSON.parse(JSON.stringify(AWAITING))];
  ctx.S.shadowTaskSel = "m-fib";
  const h = ctx.shadowHomeHtml();
  assert(/waiting on you/.test(h), "it must say what it is waiting for");
  /* ...and it must NOT claim Shadow declared the work finished. Shadow has
     no `done`/`stop` action (mission_engine.DECISION_ACTIONS is exactly
     ("continue", "ask_founder")) and _complete is the only writer of a done
     mission, so the old headline -- "Shadow says it is done and is waiting
     on you" -- asserted something that could never have happened. It read
     worst in the premature-pause bug, where the mission parked here on turn
     1 having built nothing. */
  assert(!/says it is done/.test(h),
    "the card must not claim Shadow declared completion");
  assert(/the README explains it clearly/.test(h)
    && /a working Python example is included/.test(h)
    && /the example is syntactically correct/.test(h),
    "every criterion is shown, not a count");
  /* the text precedes the control that acts on it */
  const txt = h.indexOf("a working Python example is included");
  const btn = h.indexOf('data-shcheckix="1"');
  assert(txt > -1 && btn > txt,
    "the criterion must be readable BEFORE its Confirm button");
  assert(/shcheckmet/.test(h) && /confirmed/.test(h),
    "an already-confirmed check says so instead of asking again");
  assert(!/data-shcheckix="0"/.test(h), "a met check is not re-offered");
  assert(!/data-shcheckix="2"/.test(h),
    "a non-founder tier is not offered -- the server refuses that index");
  assert(/Shadow checks this/.test(h), "and it says who does check it");
  assert(!/done when<\/span>/.test(h),
    "the flat summary row is replaced, not duplicated, in this state");
  console.log("ok 21b the pending checks are readable before they are signed");
}

/* 21c + 21d. the click sends the EXISTING action, for the right mission and
   index, and the answer refreshes the task state */
(async () => {
  const ctx = fresh();
  const posts = [];
  let homeLoads = 0;
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [JSON.parse(JSON.stringify(AWAITING))];
  ctx.S.shadowTaskSel = "m-fib";
  ctx.fetch = () => Promise.resolve({ ok: true });
  ctx.shadowPost = (url, body) => { posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ id: "m-fib", state: "done" }) }); };
  ctx.loadShadowHome = () => { homeLoads++; };
  assert(typeof ctx.listeners.click === "function", "the click handler is wired");
  await ctx.listeners.click({ target: { dataset:
    { shcheckmid: "m-fib", shcheckix: "1" } } });
  assert.strictEqual(posts.length, 1, "exactly one action is sent");
  assert.strictEqual(posts[0].url, "/api/shadow/missions/m-fib/act",
    "the existing mission-action endpoint, for THIS mission");
  assert.strictEqual(posts[0].body.action, "confirm_check",
    "the existing action, not a new one");
  assert.strictEqual(posts[0].body.index, 1,
    "the index the engine stores the check under, as a number");
  assert(homeLoads >= 1,
    "a confirmation re-reads the mission state (settle may have ended it)");
  console.log("ok 21c/d confirm_check is sent for the right check and refreshes");
})().catch(e => { console.error("FAIL 21c/d:", e.message); process.exit(1); });

/* 22. SHADOW SETTINGS (v7). Design of record: website/preview/shadow-v7.html.
   The page is the workspace's one door, it comes back, and every control on
   it is fed by the endpoint that already serves it -- nothing here is a
   second settings store and nothing is drawn that cannot act. */
const SET = { engage: ["outcome first"],
  global: [{ id: "i-1", text: "Answer with the outcome in the first line." }],
  per_chat: { "sess-paisa": [{ id: "i-2", text: "Run the EMI check first." }] },
  attention: { watching: ["a", "b"], off: ["c"], alerts: 2 },
  floors: ["the push", "client repos", "external sends"],
  tasks: { running_at_once: 5,
           turn_budget: { feature: 30, fix: 20, research: 15, watch: 0 } } };

/* 22a. the header the design draws, and the way back */
{
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  ctx.S.sessions = [{ id: "sess-paisa", title: "paisa emi" }];
  const h = ctx.shadowSettingsHtml();
  assert(/class="sshead"/.test(h), "no settings header");
  assert(/class="ssback"[\s\S]{0,120}data-shscreen="shadow"/.test(h)
      || /data-shscreen="shadow"[\s\S]{0,120}class="ssback"/.test(h)
      || /<button class="ssback" type="button" data-shscreen="shadow"/.test(h),
    "the back button must return to the Shadow workspace");
  assert(/class="ssmark"/.test(h) && /class="sstitle"/.test(h),
    "seal + title missing from the header");
  assert(/class="sswrap"/.test(h), "the centred column is missing");
  /* four sections, in the design's order */
  const order = ["Autonomy", "Memory", "Tasks", "Attention"]
    .map(x => h.indexOf(">" + x + "<"));
  assert(order.every(i => i > -1), "a section is missing: " + order.join(","));
  assert(order.slice(1).every((v, i) => v > order[i]),
    "sections are out of the design's order");
  console.log("ok 22a settings page: header, back, centred column, sections");
}

/* 22b. every control is fed by real data -- and the nine the mock draws with
   no store behind them are absent, not faked */
{
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  ctx.S.sessions = [{ id: "sess-paisa", title: "paisa emi" }];
  const h = ctx.shadowSettingsHtml();
  /* Autonomy = the floors, locked and said to be locked */
  assert(/class="floorbar"/.test(h), "no floor bar");
  assert(/the push/.test(h) && /external sends/.test(h), "floors not listed");
  assert(/not editable/.test(h), "floors must say they cannot be changed");
  /* Memory = the confirmed rules, with the EXISTING revoke */
  assert(/Answer with the outcome/.test(h) && /Run the EMI check/.test(h),
    "memory rules missing");
  assert(/class="rscope glob"/.test(h), "a global rule is not scoped global");
  assert(/paisa emi/.test(h), "a per-chat rule must wear the chat's real name");
  assert(/data-shrevoke="i-2"/.test(h), "each rule keeps its revoke");
  /* Tasks = the kinds + Delegate actually offers. Read off the Delegate
     panel's OWN render rather than a list retyped here, so the two can never
     drift: whatever Delegate offers is what Settings states. */
  const kinds = (ctx.shadowDelegatePanelHtml().match(
    /data-shnewkind="([a-z]+)"/g) || []).map(m => m.split('"')[1]);
  assert(kinds.length >= 4, "the Delegate panel offered no kinds to compare");
  kinds.forEach(k => assert(new RegExp('class="chip"[^>]*>' + k + "<").test(h),
    "Settings does not state the kind Delegate offers: " + k));
  /* Attention = the counts, and the three screens the footer used to list */
  assert(/2 watched · 1 off · 2 waiting/.test(h), "attention counts wrong");
  assert(/data-shwatching="1"/.test(h) && /data-shgoals="1"/.test(h)
      && /data-shchats="1"/.test(h),
    "Watching / Goals / Conversations must stay reachable from Settings");
  /* Autonomy is drawn to the reference (founder, explicit) even though the
     level and the top-tier switch have no store. What must hold is that they
     do not PRETEND: no action hook, so nothing posts and nothing claims to
     remember a choice it cannot keep. Pinned in 22d. */
  /* every section the design draws is now here, in its order */
  ["Autonomy", "Memory", "Tasks", "Presence", "Add a control", "Attention"]
    .reduce((prev, name) => {
      const at = h.indexOf(">" + name + "<");
      assert(at > -1, "section missing: " + name);
      assert(at > prev, "section out of the design's order: " + name);
      return at;
    }, -1);
  /* nothing anywhere claims to keep what it cannot */
  assert(!/contenteditable/.test(h),
    "no editable field may render without a writer");
  console.log("ok 22b settings: real data only, sections in the design's order");
}

/* 22d. AUTONOMY, to the reference. Four equal levels in one well with L3
   filled, the top-tier switch on, then the floor pills -- and not one of the
   two unbacked controls carries a writer. */
{
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  const h = ctx.shadowSettingsHtml();
  const seg = (h.match(/<div class="seg"[\s\S]*?<\/div>/) || [""])[0];
  assert(seg, "no segmented control");
  [["L0", "Watch"], ["L1", "Suggest"], ["L2", "Draft"], ["L3", "Act"]]
    .forEach(([lv, nm]) => {
      assert(seg.indexOf(">" + lv + "<") > -1, "level missing: " + lv);
      assert(seg.indexOf(nm) > -1, "level name missing: " + nm);
    });
  assert((seg.match(/<button/g) || []).length === 4, "four levels, no more");
  /* L3 is the selected one, and it is the ONLY selected one */
  assert((seg.match(/class="on"/g) || []).length === 1, "exactly one level is on");
  const l3 = seg.slice(seg.lastIndexOf("<button"));
  assert(/class="on"/.test(l3) && /aria-selected="true"/.test(l3),
    "L3 must be the selected level");
  /* the switch: on, and green by CSS rather than by a second class */
  assert(/class="tog" role="switch" aria-checked="true"/.test(h),
    "the top-tier switch must render on");
  assert(/Ask me before the very top tier/.test(h), "its label is missing");
  /* order: levels, then the switch, then the floors */
  assert(h.indexOf('class="seg"') < h.indexOf('class="tog"')
    && h.indexOf('class="tog"') < h.indexOf('class="floorbar"'),
    "Autonomy must read levels -> switch -> floors");
  /* the pills carry the lock the reference draws */
  assert((h.match(/class="lk"/g) || []).length === 3, "three locked floor pills");
  /* NOTHING UNBACKED WRITES. The one invariant that survives drawing them. */
  const auto = h.slice(h.indexOf('class="seg"'), h.indexOf('class="floorbar"'));
  assert(!/data-sh[a-z]+=/.test(auto),
    "an unbacked control carries an action hook: " + auto.slice(0, 200));
  assert((auto.match(/aria-disabled="true"/g) || []).length >= 5,
    "unbacked controls must say they are not operable");
  console.log("ok 22d autonomy matches the reference and writes nothing");
}

/* 22e. TASKS, to the reference -- and every number on it is one the engine
   actually enforces, not one that merely looks right. */
{
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  const h = ctx.shadowSettingsHtml();
  const sec = h.slice(h.indexOf(">Tasks<"), h.indexOf(">Presence<"));
  /* the three rows, in the reference's order */
  const rows = ["Running at once", "Budget per task", "Delegate offers"]
    .map(k => sec.indexOf(k));
  assert(rows.every(i => i > -1), "a Tasks row is missing: " + rows.join(","));
  assert(rows.slice(1).every((v, i) => v > rows[i]), "Tasks rows out of order");
  /* the stepper: minus, the value, plus */
  const step = (sec.match(/<span class="step">[\s\S]*?<\/span>\s*<\/div>/) || [""])[0];
  assert(/\u2212/.test(step) && /\+</.test(step), "the stepper needs - and +");
  assert(/<span class="val">5<\/span>/.test(step),
    "the stepper must show MAX_RUNNING, got: " + step.slice(0, 160));
  /* the budget: the real per-kind turn budget, with the AUTO pill */
  assert(/<span class="ev">20<\/span> turns/.test(sec),
    "budget must quote TEMPLATES[fix].max_turns");
  assert(/class="auto"[^>]*>auto</.test(sec), "the AUTO pill is missing");
  /* the chips: what Delegate offers, each with the x the reference draws */
  const kinds = (ctx.shadowDelegatePanelHtml().match(
    /data-shnewkind="([a-z]+)"/g) || []).map(m => m.split('"')[1]);
  kinds.forEach(k => assert(
    new RegExp('class="chip"[^>]*>' + k + '<span class="cx"').test(sec),
    "Delegate offer missing its chip or x: " + k));
  assert(/class="chipadd"[\s\S]{0,120}\+ add</.test(sec), "no + add pill");
  /* NOTHING IN HERE WRITES. Same invariant Autonomy keeps. */
  assert(!/data-sh[a-z]+=/.test(sec),
    "an unbacked Tasks control carries an action hook");
  assert((sec.match(/aria-disabled="true"/g) || []).length >= 7,
    "the -, +, every x and + add must say they are not operable");
  /* and when the server sends no limits, none are invented */
  const d2 = JSON.parse(JSON.stringify(SET)); delete d2.tasks;
  ctx.S.shadowSettings = d2;
  const bare = ctx.shadowSettingsHtml();
  assert(/not reported/.test(bare), "a missing limit must be said, not guessed");
  assert(!/class="val">5</.test(bare), "a limit was invented from nowhere");
  console.log("ok 22e tasks: reference layout, engine-enforced numbers");
}

/* 22f. PRESENCE + ADD A CONTROL, to the reference -- and the two rows that
   have real state behind them are wired to the flags the overlay owns. */
{
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  const h = ctx.shadowSettingsHtml();
  const sec = h.slice(h.indexOf(">Presence<"), h.indexOf(">Attention<"));
  /* the four rows, in the reference's order */
  const rows = ["Corner card on every screen", "Quiet hours",
                "Nudges per hour", "Hide for this app"].map(k => sec.indexOf(k));
  assert(rows.every(i => i > -1), "a Presence row is missing: " + rows.join(","));
  assert(rows.slice(1).every((v, i) => v > rows[i]), "Presence rows out of order");
  /* two switches, and a stepper showing the rate the code enforces */
  assert((sec.match(/class="tog/g) || []).length === 2, "two toggles");
  assert(/<span class="val">3<\/span>/.test(sec),
    "the stepper must show SH_PILLS_PER_HOUR, got: " + sec.slice(0, 200));
  /* the add bar */
  assert(/class="addbar"/.test(sec), "no add-a-control bar");
  assert(/Tell Shadow what to add/.test(sec), "its placeholder is missing");
  assert(/class="go"/.test(sec) && /class="sp"/.test(sec),
    "the accent dot and go button are missing");
  /* THE TWO REAL ONES ACT, through the overlay's own flags */
  assert(/data-shpresence="card"/.test(sec) && /data-shpresence="quiet"/.test(sec),
    "the two backed toggles must be operable");
  ctx.scheduleRender = () => {};
  ctx.S.shadowQuiet = false;
  ctx.listeners.click({ target: { dataset: { shpresence: "quiet" } } });
  assert.strictEqual(ctx.S.shadowQuiet, true,
    "Hide for this app must flip the SAME flag the card's quiet control does");
  ctx.listeners.click({ target: { dataset: { shpresence: "quiet" } } });
  assert.strictEqual(ctx.S.shadowQuiet, false, "and flip back");
  ctx.S.shadowHideSession = false;
  ctx.listeners.click({ target: { dataset: { shpresence: "card" } } });
  assert.strictEqual(ctx.S.shadowHideSession, true,
    "Corner card must flip the SAME flag the card's hide control does");
  /* and the switch renders the truth afterwards */
  assert(/class="tog off" role="switch"\s*\n?\s*aria-checked="false"[\s\S]{0,80}shpresence="card"/
      .test(ctx.shadowSettingsHtml().replace(/\s+/g, " "))
    || /aria-checked="false"[^>]*data-shpresence="card"/
      .test(ctx.shadowSettingsHtml().replace(/\s+/g, " ")),
    "the corner-card switch must read off once it is off");
  /* the three unbacked ones state nothing they cannot keep */
  assert(/not set/.test(sec),
    "Quiet hours has no store -- it must say so, not print mock hours");
  assert(sec.indexOf("9pm") === -1 && sec.indexOf("8am") === -1,
    "mock hours were printed as if configured");
  const inert = sec.slice(sec.indexOf("Quiet hours"));
  assert(!/data-sh[a-z]+="(?!quiet)/.test(inert.slice(0, inert.indexOf("Hide for"))),
    "an unbacked Presence control carries an action hook");
  console.log("ok 22f presence: reference layout, real flags wired, rest inert");
}

/* 22c. the read can fail, and the page says so instead of rendering empty */
{
  const ctx = fresh();
  ctx.S.shadowSettings = null;
  const h = ctx.shadowSettingsHtml();
  assert(/Could not read the rules/.test(h), "a failed read must be stated");
  assert(/data-shsetreload="1"/.test(h), "and offer the existing retry");
  assert(/data-shscreen="shadow"/.test(h),
    "the way back must survive a failed read");
  console.log("ok 22c settings: an unreadable answer is its own state");
}

/* 23. THE WHOLE TASK ROW IS THE CONTROL (founder, 2026-09-13).

   shadowTaskListHtml renders a <button data-shtask> wrapping three spans --
   the dot, the name, the pill -- and they fill it. The handler read
   ev.target.dataset, so the event target for every realistic click was a
   span with no dataset and the branch never fired: clicking the task NAME
   did nothing. These fakes are shaped like the DOM, not like a dataset bag,
   which is the whole point -- the previous tests handed the handler a
   synthesised {target:{dataset}} and could not see this class of bug. */
{
  /* one row, one child span, wired the way the browser wires them */
  const rowFor = (mid) => {
    const row = { dataset: { shtask: mid } };
    row.closest = (sel) => sel === "[data-shtask]" ? row : null;
    const child = (extra) => ({ dataset: extra || {},
      closest: (sel) => sel === "[data-shtask]" ? row : null });
    return { row, dot: child(), name: child(), pill: child() };
  };
  const parts = rowFor("m-2");
  ["dot", "name", "pill", "row"].forEach(which => {
    const ctx = fresh();
    ctx.S.shadowMissions = MISSIONS;
    ctx.S.shadowTaskSel = "m-1";
    ctx.S.shadowNewOpen = true;
    assert(typeof ctx.listeners.click === "function", "the click handler is wired");
    ctx.listeners.click({ target: parts[which] });
    assert.strictEqual(ctx.S.shadowTaskSel, "m-2",
      "clicking the " + which + " must select THAT task");
    assert.strictEqual(ctx.S.shadowNewOpen, false,
      "picking a task closes the Delegate panel, from the " + which + " too");
  });
  /* and it stays scoped: a click outside any row selects nothing */
  const ctx = fresh();
  ctx.S.shadowMissions = MISSIONS;
  ctx.S.shadowTaskSel = "m-1";
  ctx.listeners.click({ target: { dataset: {}, closest: () => null } });
  assert.strictEqual(ctx.S.shadowTaskSel, "m-1",
    "a click on nothing must not move the selection");
  /* the right pane's card must NOT be swallowed by the row selector --
     attribute selectors are exact, so data-shtaskcard is a different hook */
  assert(/data-shtaskcard="/.test(ctx.shadowTaskCardHtml(MISSIONS[0])),
    "the card keeps its own distinct hook");
  console.log("ok 23 the whole task row is clickable (dot, name, pill)");
}

/* 24. ONE READ PER GESTURE (perf fold 2026-09-13).

   SCREENS.shadow and SCREENS.shadowsettings ask for their data from inside
   render(), and render() runs on every SSE frame and every scheduleRender
   tick. Nothing stopped a second read starting while the first was still in
   the air, so opening Shadow Settings against a backend that is not instant
   cost DOZENS of requests: measured 22 for one click, 6 of every 7 of them
   the same GET issued again a frame later, plus Shadow HOME bursts that were
   still landing after the operator had navigated away.

   These pin the three rules that fixed it. They are deliberately driven the
   way render() drives them -- call the screen function repeatedly while the
   promise is unresolved -- because that IS the bug; asserting on one call
   could never see it.

   Same async-IIFE discipline test 17 documents. */
(async () => {
  /* a fetch that answers only when the test says so, and counts */
  function deferredFetch(){
    const calls = [], gates = [];
    const f = (url) => {
      calls.push(String(url));
      return new Promise(res => gates.push({ url: String(url), res }));
    };
    f.calls = calls;
    f.n = (re) => calls.filter(u => re.test(u)).length;
    f.answer = (re, body) => {
      gates.filter(g => re.test(g.url)).forEach(g => g.res({
        ok: true, status: 200, json: () => Promise.resolve(body) }));
    };
    return f;
  }
  const tick = () => new Promise(r => setImmediate(r));

  /* -- 24a: the settings screen reads ONCE, however often it is painted -- */
  {
    const ctx = fresh();
    const f = deferredFetch();
    ctx.fetch = f;
    ctx.S.screen = "shadowsettings";
    for (let i = 0; i < 12; i++) ctx.SCREENS.shadowsettings();
    assert.strictEqual(f.n(/\/api\/shadow\/settings/), 1,
      "12 paints must issue ONE /api/shadow/settings, not 12");
    f.answer(/settings/, { floors: ["x"] });
    await tick(); await tick();
    assert(ctx.S.shadowSettings && ctx.S.shadowSettings.floors,
      "the answer still lands in state");
    for (let i = 0; i < 5; i++) ctx.SCREENS.shadowsettings();
    assert.strictEqual(f.n(/\/api\/shadow\/settings/), 1,
      "once it is read, painting it again reads nothing");
  }

  /* -- 24b: Shadow Home reads ONCE, however often it is painted -- */
  {
    const ctx = fresh();
    const f = deferredFetch();
    ctx.fetch = f;
    ctx.S.screen = "shadow";
    for (let i = 0; i < 12; i++) ctx.SCREENS.shadow();
    assert.strictEqual(f.n(/\/api\/shadow\/status/), 1,
      "12 paints must issue ONE /api/shadow/status, not 12");
    assert.strictEqual(f.n(/\/api\/shadow\/(watches|missions)/), 0,
      "the parallel reads wait on /status, as they always did");
    f.answer(/status/, {});
    await tick(); await tick();
    assert.strictEqual(f.n(/\/api\/shadow\/watches/), 1, "one watches read");
    assert.strictEqual(f.n(/\/api\/shadow\/settings/), 1,
      "home still carries settings on its own parallel read");
  }

  /* -- 24c: a LAZY home read is abandoned when the operator leaves -- */
  {
    const ctx = fresh();
    const f = deferredFetch();
    ctx.fetch = f;
    ctx.S.screen = "shadow";
    ctx.SCREENS.shadow();                    /* render starts the read */
    ctx.S.screen = "shadowsettings";         /* ...the founder leaves */
    f.answer(/status/, {});
    await tick(); await tick();
    assert.strictEqual(f.n(/\/api\/shadow\/watches/), 0,
      "the five home reads must NOT be issued for a screen nobody is on");
    assert.strictEqual(ctx.S.shadowHomeDark, undefined,
      "abandoning must not leave a half-written home: the next visit reloads");
  }

  /* -- 24d: a FORCED read is never abandoned and never coalesced -- */
  {
    const ctx = fresh();
    const f = deferredFetch();
    ctx.fetch = f;
    ctx.S.screen = "shadowsettings";         /* not a home screen at all */
    ctx.loadShadowHome(true);
    f.answer(/status/, {});
    await tick(); await tick();
    assert.strictEqual(f.n(/\/api\/shadow\/watches/), 1,
      "an action that just wrote must still get its re-read, from any screen");
  }

  /* -- 24e: the door navigates, it does not fetch -- */
  {
    const ctx = fresh();
    const f = deferredFetch();
    ctx.fetch = f;
    ctx.S.shadowSettings = { floors: [] };   /* home already read them */
    ctx.listeners.click({ target: { dataset: { shscreen: "shadowsettings" },
      closest: () => null } });
    assert.strictEqual(ctx.S.screen, "shadowsettings", "it still navigates");
    assert.strictEqual(f.calls.length, 0,
      "the door must not re-read what Shadow Home already has");
    /* and the settings screen agrees: nothing left to fetch */
    ctx.SCREENS.shadowsettings();
    assert.strictEqual(f.calls.length, 0, "nor does painting the screen");
  }

  /* -- 24f: re-entering after a FAILED read still retries -- */
  {
    const ctx = fresh();
    const f = deferredFetch();
    ctx.fetch = f;
    ctx.S.shadowSettings = null;             /* the last read failed */
    ctx.listeners.click({ target: { dataset: { shscreen: "shadow" },
      closest: () => null } });
    assert.strictEqual(ctx.S.shadowSettings, undefined,
      "leaving clears a failed read, which is what made coming back retry");
    ctx.S.screen = "shadowsettings";
    ctx.SCREENS.shadowsettings();
    assert.strictEqual(f.n(/\/api\/shadow\/settings/), 1, "and it does retry");
  }

  console.log("ok 24 one read per gesture: no duplicate settings fetch, "
    + "no home burst after navigating away");
})().catch(e => { console.error("FAIL 24:", e.message); process.exit(1); });

/* 25. THE WHOLE DOOR IS THE CONTROL (founder, 2026-09-13:
   "if I shadow settings -- it doesn't open (at least immediately anyway)").

   shadowNavHtml draws ONE button wrapping a <svg> gear and a
   <span>Shadow Settings</span>, and those two children fill it. The handler
   read ev.target.dataset, so a click on the label or the icon -- which is
   every click a person actually makes -- landed on a child with no dataset
   and the branch never fired. Only the thin strip of padding between the
   children carried the hook, so the door opened on some presses and ignored
   others: a dead click that reads as a slow one.

   Same defect and same cure as [data-shtask] in test 23, and these fakes are
   shaped like the DOM for the same reason: a synthesised {target:{dataset}}
   cannot see this class of bug at all. */
{
  /* the door, wired the way the browser wires it */
  const doorFor = (screen) => {
    const door = { dataset: { shscreen: screen } };
    door.closest = (sel) => sel === "[data-shscreen]" ? door : null;
    const child = () => ({ dataset: {},
      closest: (sel) => sel === "[data-shscreen]" ? door : null });
    return { door, icon: child(), label: child() };
  };

  /* the markup this is about really does nest two elements in the button */
  {
    const ctx = fresh();
    const nav = ctx.shadowNavHtml();
    assert(/data-shscreen="shadowsettings"/.test(nav), "the door carries the hook");
    assert(/<svg/.test(nav) && /<span>Shadow Settings<\/span>/.test(nav),
      "and it wraps children that will be the click target");
  }

  const parts = doorFor("shadowsettings");
  ["label", "icon", "door"].forEach(which => {
    const ctx = fresh();
    ctx.S.screen = "shadow";
    ctx.S.shadowSettings = { floors: [] };
    ctx.fetch = () => { throw new Error("the door must not fetch"); };
    ctx.listeners.click({ target: parts[which] });
    assert.strictEqual(ctx.S.screen, "shadowsettings",
      "clicking the " + which + " must open Shadow Settings");
  });

  /* and back out again, from the child of the back button too */
  const back = doorFor("shadow");
  ["label", "door"].forEach(which => {
    const ctx = fresh();
    ctx.S.screen = "shadowsettings";
    ctx.S.shadowSettings = { floors: [] };
    ctx.listeners.click({ target: back[which] });
    assert.strictEqual(ctx.S.screen, "shadow",
      "<- Back to Shadow must work from the " + which + " too");
  });

  /* it stays scoped: a click on nothing routes nowhere */
  {
    const ctx = fresh();
    ctx.S.screen = "shadow";
    ctx.listeners.click({ target: { dataset: {}, closest: () => null } });
    assert.strictEqual(ctx.S.screen, "shadow",
      "a click on nothing must not navigate");
  }
  console.log("ok 25 the whole Shadow Settings door opens it, not just its padding");
}


/* ── 26: THE EXISTING-CHAT FLOW ACTS ON THE EXISTING CHAT ─────────────────
   Founder, 2026-09-13: "Work in existing chat — I type, press Enter, nothing
   happens." Traced live (real Chrome, real key events, repo backend): the
   handler fired, the value was read and exactly one POST went out --
   `{"message":"take this chat over"}`, with NO scope_id. Entering the flow
   left S.shadowChat at "global", sendToShadow drops scope_id for "global",
   so Shadow had no transcript to drive and answered that "global" is not a
   chat. No mission, no takeover, no driving strip: a dead Enter.

   These pin the target, not the keystroke -- the keystroke was never the
   bug, which is why they assert on the REQUEST BODY. */
(async () => {
  const compose = (v) => ({ value: v, dataset: { shhomecompose: "1" } });
  const armed = () => {
    const ctx = fresh();
    ctx.S.shadowHomeDark = false;
    ctx.scheduleRender = () => {};
    ctx.fetch = () => Promise.resolve({ ok: true,
      json: () => Promise.resolve({}) });
    ctx.posts = [];
    ctx.shadowPost = (url, body) => { ctx.posts.push({ url, body });
      return Promise.resolve({ ok: true, status: 200,
        json: () => Promise.resolve({ reply: "on it" }) }); };
    return ctx;
  };
  const enter = (ctx, el) => ctx.listeners.keydown({ key: "Enter",
    shiftKey: false, target: el, preventDefault(){ ctx.prevented = true; } });
  const openFlow = (ctx) => ctx.listeners.click({
    target: { dataset: { shexisting: "1" }, closest: () => null } });

  /* 26a. the chat the founder has open IS the target */
  {
    const ctx = armed();
    ctx.S.sessions = [{ id: "sess-open", title: "Paisa EMI" }];
    ctx.S.openPanes = ["sess-open"];
    openFlow(ctx);
    assert.strictEqual(ctx.S.shadowChat, "sess-open",
      "opening the flow must bind it to the chat already open");
    const h = ctx.shadowHomeHtml();
    assert(/Paisa EMI/.test(h), "and the picker must name it");
    assert(/data-shscope="sess-open"/.test(h),
      "the composer must carry that scope");
  }

  /* 26b. Enter sends ONE request, for the EXISTING chat -- the regression */
  {
    const ctx = armed();
    ctx.S.sessions = [{ id: "sess-open", title: "Paisa EMI" }];
    ctx.S.openPanes = ["sess-open"];
    openFlow(ctx);
    const el = compose("take this chat over");
    enter(ctx, el);
    assert(ctx.prevented, "Enter must not fall through to a newline");
    assert.strictEqual(ctx.posts.length, 1, "exactly one request");
    assert.strictEqual(ctx.posts[0].url, "/api/shadow/chat",
      "the existing Shadow endpoint, not a new one");
    assert.strictEqual(ctx.posts[0].body.scope_id, "sess-open",
      "THE BUG: the turn went out with no chat to act in");
    assert.strictEqual(ctx.posts[0].body.message, "take this chat over");
    assert.strictEqual(el.value, "", "a sent brief clears the box");
    await Promise.resolve();
    assert(!ctx.posts.some(p => /\/missions$/.test(p.url)),
      "and it must NOT delegate a new chat -- that is + Delegate's path");
  }

  /* 26c. a chat picked by hand still wins -- INSIDE the flow, which is the
     only place the picker exists (shadowTargetHtml renders inside
     shadowStageHtml). Re-ordered 2026-09-13: entering the flow now re-seeds
     the target every time, because the old "seed only when unset" rule made
     the FIRST chat the flow was ever opened from the permanent target --
     open A, use it, open B, come back, and the turn still went to A
     (measured live). Picking still wins for as long as the founder is in the
     flow; leaving and coming back re-targets, which is the point. */
  {
    const ctx = armed();
    ctx.S.sessions = [{ id: "sess-open" }, { id: "sess-picked" }];
    ctx.S.openPanes = ["sess-open"];
    openFlow(ctx);
    assert.strictEqual(ctx.S.shadowChat, "sess-open", "bound to the open chat");
    ctx.listeners.click({ target: { dataset: { shchat: "sess-picked" },
      closest: () => null } });
    assert.strictEqual(ctx.S.shadowChat, "sess-picked",
      "a pick made in the flow stands");
    enter(ctx, compose("go"));
    assert.strictEqual(ctx.posts[0].body.scope_id, "sess-picked");
  }

  /* 26d. empty input starts nothing AND eats nothing */
  {
    const ctx = armed();
    ctx.S.openPanes = ["sess-open"];
    openFlow(ctx);
    const el = compose("   ");
    enter(ctx, el);
    assert.strictEqual(ctx.posts.length, 0, "whitespace must not be sent");
    assert.strictEqual(el.value, "   ", "and must not be silently cleared");
  }

  /* 26e. no chat to act in: said out loud, never sent unscoped */
  {
    const ctx = armed();
    ctx.S.openPanes = [];                      /* nothing open to seed from */
    openFlow(ctx);
    assert.strictEqual(ctx.S.shadowChat, "global", "nothing to seed");
    const el = compose("take it over");
    enter(ctx, el);
    assert.strictEqual(ctx.posts.length, 0,
      "an unscoped turn cannot take a chat over -- it must not be sent");
    assert.strictEqual(el.value, "take it over", "the brief survives");
    assert(/Pick the chat/.test(ctx.S.shadowScopeErr || ""),
      "the founder must be told what is missing");
    assert(/Pick the chat/.test(ctx.shadowHomeHtml()), "and must see it");
    /* picking one answers it */
    ctx.listeners.click({ target: { dataset: { shchat: "sess-open" },
      closest: () => null } });
    assert.strictEqual(ctx.S.shadowScopeErr, null, "picking clears the gripe");
  }

  /* 26f. the DELEGATED composer is untouched: it is global on purpose */
  {
    const ctx = armed();
    ctx.S.shadowExistingOpen = false;          /* the task workspace */
    enter(ctx, compose("what is running?"));
    assert.strictEqual(ctx.posts.length, 1,
      "the workspace composer must still send without a chat");
    assert.strictEqual(ctx.posts[0].body.scope_id, undefined);
  }

  /* 26g. the send BUTTON takes the same path, once */
  {
    const ctx = armed();
    ctx.S.openPanes = ["sess-open"];
    openFlow(ctx);
    const el = compose("via the button");
    ctx.document.querySelector = (sel) =>
      sel === "[data-shhomecompose]" ? el : null;
    ctx.listeners.click({ target: { dataset: { shsend: "1" },
      closest: () => null } });
    assert.strictEqual(ctx.posts.length, 1, "one request, from the button too");
    assert.strictEqual(ctx.posts[0].body.scope_id, "sess-open");
  }

  console.log("ok 26 existing-chat flow: Enter sends ONE scoped turn for the "
    + "chat already open; empty and target-less are refused out loud");
})().catch(e => { console.error("FAIL 27:", e.message); process.exit(1); });

/* 27. THE EXISTING-CHAT FLOW: the arrow sends, and the target follows the
   chat the founder is actually in (founder, 2026-09-13 -- "STILL NOT
   WORKING in the real app").

   Two defects, both measured live in Chrome before these existed:

     the arrow was DEAD -- <button data-shsend="1"> holds nothing but the
     arrow <svg>, the handler read ev.target.dataset, so every real click
     landed on the svg and made ZERO requests while Enter worked fine.

     the target STUCK -- entering the flow seeded S.shadowChat only when it
     was unset, so the first chat the flow was ever opened from stayed the
     target forever: open A, use it, open B, come back, and the turn still
     went out scoped to A.

   DOM-shaped fakes again: a synthesised {target:{dataset}} cannot see the
   first bug at all, which is exactly how it survived. */
{
  /* the arrow, wired the way the browser wires it: the svg fills the button */
  const arrowParts = () => {
    const btn = { dataset: { shsend: "1" } };
    btn.closest = (sel) => sel === "[data-shsend]" ? btn : null;
    const svg = { dataset: {},
      closest: (sel) => sel === "[data-shsend]" ? btn : null };
    return { btn, svg };
  };
  /* the composer document.querySelector must hand back */
  const withComposer = (ctx, value) => {
    const box = { value, dataset: { shhomecompose: "1" } };
    ctx.document.querySelector = (sel) =>
      sel === "[data-shhomecompose]" ? box : null;
    return box;
  };

  /* -- 27a: the arrow sends, from the icon as well as the button -- */
  ["svg", "btn"].forEach(which => {
    const ctx = fresh();
    const sent = [];
    ctx.S.shadowExistingOpen = true;
    ctx.S.shadowChat = "sess-A";
    ctx.sendToShadow = (t) => { sent.push(t); return Promise.resolve({}); };
    ctx.loadShadowHome = () => {};
    const box = withComposer(ctx, "take this chat over");
    ctx.listeners.click({ target: arrowParts()[which] });
    assert.deepStrictEqual(JSON.parse(JSON.stringify(sent)),
      ["take this chat over"],
      "clicking the " + which + " must send exactly once");
    assert.strictEqual(box.value, "", "and clear the composer, as Enter does");
  });

  /* -- 27b: Enter still sends, unchanged, through the same one path -- */
  {
    const ctx = fresh();
    const sent = [];
    ctx.S.shadowExistingOpen = true;
    ctx.S.shadowChat = "sess-A";
    ctx.sendToShadow = (t) => { sent.push(t); return Promise.resolve({}); };
    ctx.loadShadowHome = () => {};
    const box = { value: "typed then Enter", dataset: { shhomecompose: "1" } };
    ctx.listeners.keydown({ key: "Enter", shiftKey: false, target: box,
      preventDefault(){} });
    assert.deepStrictEqual(JSON.parse(JSON.stringify(sent)),
      ["typed then Enter"], "Enter still sends exactly once");
  }

  /* -- 27c: one gesture is one send: the arrow does not also fire Enter -- */
  {
    const ctx = fresh();
    let calls = 0;
    ctx.S.shadowExistingOpen = true;
    ctx.S.shadowChat = "sess-A";
    ctx.sendToShadow = () => { calls++; return Promise.resolve({}); };
    ctx.loadShadowHome = () => {};
    withComposer(ctx, "once only");
    ctx.listeners.click({ target: arrowParts().svg });
    assert.strictEqual(calls, 1, "exactly one request per arrow click");
  }

  /* -- 27d: entering the flow targets the chat the founder is IN, every
        time -- the A -> B journey that failed live -- */
  {
    const ctx = fresh();
    const enter = () => ctx.listeners.click({
      target: { dataset: { shexisting: "1" }, closest: () => null } });
    const leave = () => ctx.listeners.click({
      target: { dataset: { shexisting: "0" }, closest: () => null } });

    ctx.S.openPanes = ["sess-A"];
    enter();
    assert.strictEqual(ctx.S.shadowChat, "sess-A", "chat A is the target");

    leave();
    ctx.S.openPanes = ["sess-B"];          /* the founder opens another chat */
    enter();
    assert.strictEqual(ctx.S.shadowChat, "sess-B",
      "re-entering must target chat B, not keep chat A");

    /* newest pane wins when more than one is open */
    leave();
    ctx.S.openPanes = ["sess-B", "sess-C"];
    enter();
    assert.strictEqual(ctx.S.shadowChat, "sess-C", "the newest open pane wins");

    /* a hand-picked chip still stands while the founder is INSIDE the flow */
    ctx.listeners.click({ target: { dataset: { shchat: "sess-PICKED" },
      closest: () => null } });
    assert.strictEqual(ctx.S.shadowChat, "sess-PICKED", "the picker wins");
  }

  /* -- 27e: no pane open = no invented target, and no unscoped turn -- */
  {
    const ctx = fresh();
    const sent = [];
    ctx.S.openPanes = [];
    ctx.sendToShadow = (t) => { sent.push(t); return Promise.resolve({}); };
    ctx.listeners.click({ target: { dataset: { shexisting: "1" },
      closest: () => null } });
    assert(!ctx.S.shadowChat || ctx.S.shadowChat === "global",
      "nothing to target, so nothing is invented");
    withComposer(ctx, "go");
    ctx.listeners.click({ target: arrowParts().svg });
    assert.strictEqual(sent.length, 0, "an unscoped turn is never sent");
    assert(/Pick the chat/.test(ctx.S.shadowScopeErr || ""),
      "it says which control is missing");
  }

  /* -- 27f: the DELEGATED flow is untouched -- global on purpose -- */
  {
    const ctx = fresh();
    const sent = [];
    ctx.S.shadowExistingOpen = false;      /* + Delegate workspace */
    ctx.S.shadowChat = "global";
    ctx.sendToShadow = (t) => { sent.push(t); return Promise.resolve({}); };
    ctx.loadShadowHome = () => {};
    withComposer(ctx, "start something new");
    ctx.listeners.click({ target: arrowParts().svg });
    assert.deepStrictEqual(JSON.parse(JSON.stringify(sent)),
      ["start something new"],
      "the delegated composer still sends unscoped, exactly as before");
  }
  console.log("ok 27 existing chat: the arrow sends, and the target follows "
    + "the chat the founder is in");
}

/* 28. DELETE A TASK FROM THE LEFT LIST (founder, 2026-09-14).

   The list had no way to remove a task, so delegated tasks piled up in it
   forever. These pin the three things that make the remove real rather than
   cosmetic: the control exists on every row, it goes through the EXISTING
   mission action endpoint (so the server erases the record and a refresh
   cannot bring it back), and it never fires by accident. */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = MISSIONS;
  const h = ctx.shadowTaskListHtml();
  MISSIONS.filter(m => m.state !== "done").forEach(m => {
    assert(h.indexOf('data-shtaskdel="' + m.id + '"') !== -1,
      "no remove control on row " + m.id);
  });
  /* the selector button is untouched: same hook, same three spans */
  assert(/data-shtask="m-1"/.test(h), "the row selector hook was lost");
  assert(/shtaskdot/.test(h) && /shtaskname/.test(h) && /shtpill/.test(h),
    "the row lost one of its three spans");
  /* a button may not contain a button: the delete control must be a SIBLING
     of the selector, not inside it */
  const rowStart = h.indexOf('data-shtask="m-1"');
  const closeSel = h.indexOf("</button>", rowStart);
  assert(h.indexOf('data-shtaskdel="m-1"') > closeSel,
    "the remove control is nested inside the selector button");
  console.log("ok 28 every task row carries a remove control");
}

/* 29. THE REMOVE IS A SERVER DELETE, not a local hide. */
(async () => {
  const ctx = fresh();
  const posts = [];
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [
    { id: "m-keep", objective: "keep me", state: "brief_confirm" },
    { id: "m-go", objective: "delete me", state: "brief_confirm" }];
  ctx.S.shadowTaskSel = "m-go";
  ctx.fetch = () => Promise.resolve({ ok: true });
  ctx.showNudge = () => {};
  ctx.renderShadowCard = () => {};
  ctx.scheduleRender = () => {};
  /* the server is the only thing that removes the row: the re-read comes
     back WITHOUT it, exactly as the real endpoint would answer */
  ctx.loadShadowHome = () => {
    ctx.S.shadowMissions = ctx.S.shadowMissions.filter(m => m.id !== "m-go");
    return Promise.resolve();
  };
  ctx.shadowPost = (url, body) => {
    posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ deleted: true, mission_id: "m-go" }) });
  };
  await ctx.shadowDeleteTask("m-go");
  assert.strictEqual(posts.length, 1, "exactly one write");
  assert.strictEqual(posts[0].url, "/api/shadow/missions/m-go/act",
    "must reuse the EXISTING mission action endpoint");
  assert.strictEqual(posts[0].body.action, "delete",
    "no second deletion architecture");
  /* the list is re-read from the server, never filtered locally */
  const ids = ctx.S.shadowMissions.map(m => m.id);
  assert(!ids.includes("m-go"), "the deleted task is still listed");
  assert(ids.includes("m-keep"), "an unrelated task was removed too");
  assert(!/data-shtask="m-go"/.test(ctx.shadowTaskListHtml()),
    "the deleted row still renders");
  assert(/data-shtask="m-keep"/.test(ctx.shadowTaskListHtml()),
    "the unrelated row was lost");
  assert.strictEqual(ctx.S.shadowTaskSel, null,
    "focus must not keep pointing at a record that is gone");
  console.log("ok 29 remove = one POST to the existing endpoint, server-side");
})().catch(e => { console.error("FAIL 29:", e.message); process.exit(1); });

/* 30. × DELETES ON ONE CLICK (founder, 2026-09-14).

   This used to turn the row into "Delete? Yes / No" in place -- the Agents
   rail's gesture. In the task list that ask painted UNDERNEATH neighbouring
   Shadow UI, so Yes could not reliably be clicked and the delete could not be
   completed at all. The ask is gone. What these pin is that removing it cost
   nothing else: one click writes exactly one POST to the EXISTING /act
   endpoint, no confirm() dialog is reachable (the harness defines none, so a
   surviving call throws), no second ask element renders, and the click does
   not also select the row on its way out. */
(async () => {
  const ctx = fresh();
  const posts = [];
  ctx.S.shadowMissions = [{ id: "m-go", objective: "x", state: "running" }];
  ctx.S.shadowTaskSel = "m-1";
  ctx.fetch = () => Promise.resolve({ ok: true });
  ctx.shadowPost = (url, body) => { posts.push({ url, body });
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) }); };
  ctx.scheduleRender = () => {};
  ctx.showNudge = () => {};
  ctx.renderShadowCard = () => {};
  ctx.loadShadowHome = () => Promise.resolve();

  /* NO confirm() may exist in this path at all: the harness does not define
     one, so a surviving call would throw rather than quietly pass. */
  assert.strictEqual(typeof ctx.confirm, "undefined",
    "the harness must not supply a confirm -- the code must not need one");

  /* 1. one click on × deletes, through the one existing endpoint */
  const del = { dataset: { shtaskdel: "m-go" } };
  del.closest = (sel) => sel === "[data-shtaskdel]" ? del
    : (sel === "[data-shtask]" ? { dataset: { shtask: "m-go" } } : null);
  ctx.listeners.click({ target: del });
  await new Promise(r => setTimeout(r, 0));
  assert.strictEqual(posts.length, 1, "one click on x must delete, once");
  assert.strictEqual(posts[0].url, "/api/shadow/missions/m-go/act",
    "must reuse the EXISTING mission action endpoint");
  assert.strictEqual(posts[0].body.action, "delete",
    "no second deletion architecture");

  /* 2. it must not also select the row it is deleting */
  assert.strictEqual(ctx.S.shadowTaskSel, "m-1",
    "clicking remove must not also re-select the row");

  /* 3. NO second click exists anywhere in the markup, live or inert */
  for (const st of ["running", "brief_confirm"]){
    ctx.S.shadowMissions = [{ id: "m-go", objective: "x", state: st }];
    const h = ctx.shadowTaskListHtml();
    assert(/data-shtaskdel="m-go"/.test(h), "the x is missing in " + st);
    assert(!/data-shtaskdelyes|data-shtaskdelno|shtaskask/.test(h),
      "a confirmation control came back in " + st);
    assert(!/Delete\?|Stop &amp; delete\?/.test(h),
      "the row is asking a question again in " + st);
  }
  console.log("ok 30 x deletes on one click: no ask, no dialog, one POST");
})().catch(e => { console.error("FAIL 30:", e.message); process.exit(1); });

/* 31. START IS NOT OFFERED FOR A TASK THAT HAS ALREADY STARTED
   (founder, 2026-09-14).

   /act answers {accepted:true} and provisions in the background, so the
   record sits in brief_confirm while Shadow is already starting the task.
   `start_requested_at` is the server's stamp for that window. The face is
   the EXISTING queued one; the Start button is gone, because pressing it
   again does nothing. */
{
  const started = { id: "m-s", objective: "go", state: "brief_confirm",
    template: "fix", target_mode: "new", turns_used: 0, max_turns: 20,
    start_requested_at: "2026-09-14T10:00:00Z" };
  const notYet = { id: "m-r", objective: "wait", state: "brief_confirm",
    template: "fix", target_mode: "new", turns_used: 0, max_turns: 20 };

  assert(ctx0().shadowMissionStartable(notYet), "READY must offer Start");
  assert(!ctx0().shadowMissionStarting(notYet), "READY is not starting");
  assert(!ctx0().shadowMissionStartable(started), "a started task offers Start");
  assert(ctx0().shadowMissionStarting(started), "the stamp was not read");

  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [notYet, started];

  ctx.S.shadowTaskSel = "m-r";
  const ready = ctx.shadowHomeHtml();
  assert(/data-shstart="m-r"/.test(ready), "READY lost its Start");
  assert(/>READY</.test(ready), "READY lost its face");

  ctx.S.shadowTaskSel = "m-s";
  const going = ctx.shadowHomeHtml();
  assert(!/data-shstart="m-s"/.test(going),
    "Start is still offered for a task that has already been started");
  assert(/>QUEUED</.test(going),
    "a started task must read as the existing QUEUED state");
  /* the LIST agrees with the card -- one predicate, both surfaces */
  const list = ctx.shadowTaskListHtml();
  assert(/shtpill-ready[^>]*>READY/.test(list), "the READY row lost its pill");
  assert(/QUEUED/.test(list), "the started row still reads READY in the list");
  /* and the compact in-thread card, which draws Start too */
  assert(!/data-shstart="m-s"/.test(ctx.missionCardHtml(started)),
    "the in-thread mission card still offers Start");
  assert(/data-shstart="m-r"/.test(ctx.missionCardHtml(notYet)),
    "the in-thread mission card lost a legitimate Start");
  console.log("ok 31 a started task never offers Start again");
}

/* 32. EVERY STATE OFFERS ONLY WHAT THE ENGINE WILL ACCEPT.
   The transition table is mission_engine.TRANSITIONS; these are the actions
   the task card draws for each state it can be in. */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  const card = (m) => ctx.shadowTaskCardHtml(Object.assign(
    { objective: "o", template: "fix", turns_used: 1, max_turns: 20 }, m));
  const has = (h, act) => new RegExp('data-shact="' + act + '"').test(h)
    || (act === "start" && /data-shstart=/.test(h));

  const ready = card({ id: "a", state: "brief_confirm" });
  assert(has(ready, "start"), "READY: Start must be available");

  const running = card({ id: "b", state: "running" });
  assert(!has(running, "start"), "running: Start must be gone");
  assert(has(running, "stop"), "running: Stop is the legal exit");
  assert(!has(running, "resume"), "running: Resume is not legal");
  assert(!has(running, "retry"), "running: Retry would clone a live mission");

  const queued = card({ id: "c", state: "queued" });
  assert(!has(queued, "start"), "queued: Start must be gone");
  assert(has(queued, "drop"), "queued: Drop is the legal exit");

  const paused = card({ id: "d", state: "paused" });
  assert(!has(paused, "start"), "paused: Start must be gone");
  assert(has(paused, "resume") && has(paused, "stop"),
    "paused: its two legal exits");

  const blocked = card({ id: "e", state: "blocked", block_reason: "nope" });
  assert(!has(blocked, "start"), "NEEDS YOU: Start must be gone");
  assert(has(blocked, "resume") && has(blocked, "stop"),
    "NEEDS YOU: blocked's two legal exits are the founder's, and it had "
    + "neither");

  const done = card({ id: "f", state: "done" });
  assert(!has(done, "start"), "done: Start must be gone");
  assert(!has(done, "stop") && !has(done, "resume"),
    "done is terminal: nothing to stop or resume");

  const failed = card({ id: "g", state: "failed" });
  assert(!has(failed, "start"), "failed: Start must be gone");
  assert(has(failed, "retry"), "failed: retry is the product's own re-run");

  const stopped = card({ id: "h", state: "stopped" });
  assert(!has(stopped, "start"), "stopped: Start must be gone");
  assert(has(stopped, "retry"), "stopped: retry is offered");
  console.log("ok 32 each state exposes only the actions the engine accepts");
}

console.log("test_shadow_home.js: all green");
