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
  /* SLICE 11 removed the tab strip and left one scope chip. PASS 2
     (founder, 2026-09-15) removed the chip too, with the existing-chat
     flow it belonged to -- shadowTargetHtml and shadowRecentChatsHtml are
     gone and so is the "Work in an existing chat instead" door. Neither
     scoping control is on Home now; the DELEGATION composer stays. */
  const h = ctx.shadowHomeHtml();
  assert(!/shchattabs/.test(h), "the tab strip is not on Home any more");
  assert(!/data-shscopepick/.test(h), "the scope chip went with the flow");
  assert(!/data-shchat=/.test(h), "no chat is pickable from the workspace");
  assert(/data-shhomecompose/.test(h), "the delegation composer must remain");
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
  /* SLICE 11 removed the tab strip and left one scope chip. PASS 2
     (founder, 2026-09-15) removed the chip too, with the existing-chat
     flow it belonged to -- shadowTargetHtml and shadowRecentChatsHtml are
     gone and so is the "Work in an existing chat instead" door. Neither
     scoping control is on Home now; the DELEGATION composer stays. */
  const h = ctx.shadowHomeHtml();
  assert(!/shchattabs/.test(h), "the tab strip is not on Home any more");
  assert(!/data-shscopepick/.test(h), "the scope chip went with the flow");
  assert(!/data-shchat=/.test(h), "no chat is pickable from the workspace");
  assert(/data-shhomecompose/.test(h), "the delegation composer must remain");
  console.log("ok 10 neither tab strip nor scope chip is on Home");
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
  /* SLICE 11 removed the tab strip and left one scope chip. PASS 2
     (founder, 2026-09-15) removed the chip too, with the existing-chat
     flow it belonged to -- shadowTargetHtml and shadowRecentChatsHtml are
     gone and so is the "Work in an existing chat instead" door. Neither
     scoping control is on Home now; the DELEGATION composer stays. */
  const h = ctx.shadowHomeHtml();
  assert(!/shchattabs/.test(h), "the tab strip is not on Home any more");
  assert(!/data-shscopepick/.test(h), "the scope chip went with the flow");
  assert(!/data-shchat=/.test(h), "no chat is pickable from the workspace");
  assert(/data-shhomecompose/.test(h), "the delegation composer must remain");
  console.log("ok 10 neither tab strip nor scope chip is on Home");
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
  /* SLICE 11 moved names onto the scope picker; PASS 2 removed that picker
     with the existing-chat flow. shadowChatLabel is UNCHANGED and still the
     only namer -- the task card's "acts in" row renders it, and every rule
     above still holds. What went is the surface, not the naming. */
  assert.strictEqual(ctx.shadowChatLabel("sess-paisa"), "Paisa EMI rounding fix",
    "the namer is untouched by the picker going away");
  console.log("ok 13 chats wear real names (shadowChatLabel; picker gone)");
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
  /* the one generic label was replaced by the design's three section
     headings ("Shadow Design - Final", founder 2026-09-15) */
  assert(/class="shwsec/.test(h), "the list lost its section headings");
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

/* 14b. THE DELEGATED WORKSPACE IS TASK-FOCUSED, AND THE EXISTING-CHAT FLOW
   IS GONE (founder, 2026-09-15, PASS 2). This used to assert the flow was
   "preserved, opt-in, not default" -- rendered only when opened. It is now
   removed outright: shadowTargetHtml (the "Working with" picker),
   shadowRecentChatsHtml (the chips) and shadowWorkComposerHtml (the
   "Say anything" box plus "Work in an existing chat instead") are deleted,
   and d.shchat / d.shscopepick / d.shexisting went with them.

   WHAT STAYS IS THE DELEGATION COMPOSER, and it is now rendered
   unconditionally rather than behind the flow: the shask copy, the
   data-shhomecompose textarea and its scope attribute, the send arrow. */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = MISSIONS;
  ctx.S.sessions = [{ id: "s-1", title: "paisa emi" }];
  ctx.S.shadowWatching = ["s-1"];
  const h = ctx.shadowHomeHtml();

  /* the existing-chat surface is gone, and cannot be brought back */
  assert(!/data-shscopepick/.test(h), "the 'Working with' picker survived");
  assert(!/Choose a conversation/.test(h), "picker copy survived");
  assert(!/Recent conversations/.test(h), "recent-chat chips survived");
  assert(!/data-shchat=/.test(h), "chat chips survived");
  assert(!/data-shexisting/.test(h), "the existing-chat door survived");
  /* shadowWorkComposerHtml is pinned dead by data-shexisting / data-shchat /
     data-shscopepick above. The phrase it used to carry is NOT the guard any
     more: "Say anything…" is the reference design's placeholder for the
     Shadow<->founder composer (/api/shadow/chat), a different surface. */
  assert(!/shadowWorkComposerHtml|Work in an existing chat instead/.test(h),
    "the old workspace composer survived");
  assert(!/Work in an existing chat/.test(h), "the door label survived");
  ctx.S.shadowExistingOpen = true;          /* nothing can set this now */
  assert(!/data-shscopepick/.test(ctx.shadowHomeHtml()),
    "the flow came back when the dead flag was set");

  /* ...and the DELEGATION composer renders, unconditionally */
  assert(/data-shhomecompose/.test(h), "the delegation composer was lost");
  assert(/data-shscope=/.test(h), "the composer lost its scope attribute");
  /* WITH A TASK IN FOCUS the composer is the reference's calm box: the same
     surface and the same hooks, asserted above, asking for anything rather
     than teaching how to delegate. It is the SHADOW<->FOUNDER channel
     (/api/shadow/chat) either way -- never the worker chat. */
  assert(/Say anything/.test(h), "the calm composer placeholder was lost");
  assert(!/Tell Shadow the outcome you want/.test(h),
    "the teaching copy belongs to the un-focused pane, not the task pane");
  /* THE ASK BLOCK BELONGS TO NEW TASK (founder, 2026-09-15). "What should I
     take on? / Tell Shadow the outcome you want" is how a task is CREATED,
     so it draws behind + Delegate and nowhere else -- the workspace, focused
     or empty, carries exactly one composer and it says "Say anything…". */
  const empty = (() => { const c = fresh(); c.S.shadowHomeDark = false;
    c.S.shadowMissions = []; c.S.goals = []; return c.shadowHomeHtml(); })();
  assert(!/Tell Shadow the outcome you want/.test(empty),
    "the new-task ask must not draw on the workspace");
  assert.strictEqual((empty.match(/data-shhomecompose/g) || []).length, 1,
    "an empty workspace still has exactly one composer");
  const newTask = (() => { const c = fresh(); c.S.shadowHomeDark = false;
    c.S.shadowMissions = MISSIONS; c.S.goals = []; c.S.shadowNewOpen = true;
    return c.shadowHomeHtml(); })();
  assert(/Tell Shadow what outcome you want/.test(newTask),
    "the delegation placeholder was lost");
  assert(/Tell Shadow the outcome you want/.test(newTask),
    "the shask copy was lost");
  assert(/data-shsend="1"/.test(h), "the send arrow was lost");
  console.log("ok 14b existing-chat flow removed; delegation composer stays");
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
    /* a completion the founder has not read yet: the card carries the
       summary the engine just stamped, so the row has to survive */
    { id: "m-done",    objective: "fresh done",  state: "done" },
    /* --- must NOT appear: concluded ----------------------------------- */
    /* ...but a done row that was RETRIED steps aside for its successor */
    { id: "m-donered", objective: "superseded done", state: "done",
      retried_to: "m-fresh2" },
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
  /* a completion stays too -- it is the one row carrying the summary */
  assert(ids.includes("m-done"), "a finished task was hidden");
  /* 4. historical terminal records do not */
  ["m-donered", "m-mstop", "m-retried", "m-vestigial", "m-wonattempt"]
    .forEach(id => assert(!ids.includes(id), "history leaked into the list: " + id));
  assert(!/machine stopped|superseded/.test(h),
    "concluded work rendered in the workspace");

  /* 5. the RECORDS are untouched -- this is a filter, not a delete */
  assert.strictEqual(ctx.S.shadowMissions.length, 13,
    "the mission list itself must not be mutated");
  assert(ctx.S.shadowMissions.some(m => m.id === "m-mstop"),
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

  /* 3. done STAYS now (founder, 2026-09-15, rule 4a) -- the completion
     summary lives on that card, so the row carrying it has to survive.
     Retried is the one exception, and it is the same !retried_to the
     failed and founder-stopped rules already use. */
  assert.deepStrictEqual(
    only([{ id: "m-done", objective: "x", state: "done",
            ended_by: "founder" }]), ["m-done"],
    "a completed mission must stay readable in the list");
  assert.deepStrictEqual(
    only([{ id: "m-done", objective: "x", state: "done" }]), ["m-done"],
    "ended_by is irrelevant to a completion");
  assert.deepStrictEqual(
    only([{ id: "m-old", objective: "x", state: "done",
            retried_to: "m-new" }]), [],
    "a retried completion steps aside for its successor");

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

/* 17b. A FOUNDER-TYPED CRITERION IS THEIRS TO CONFIRM (founder, 2026-09-15).

   THE REGRESSION. e1c8d0ea routed the Delegate form's "done when" box through
   goalCriteriaToChecks, which infers a tier from SHAPE -- so any short,
   unadorned line became contains_artifact, a tier evaluated as
   `check in transcript_text`. Four missions died on it: "The file contains
   HELLO" (m-307fc348352b, m-1eec37dfd145), "The file exists and contains 5
   bullets." (m-b7ee410c3c3e), and "Tests cover it." / "The timestamp is
   visible on the task card." / "Shadow reaches DONE." (m-cd009367d41a). Each
   describes a STATE; the worker proves it by doing the thing, never by
   uttering the sentence, so met stayed False and Shadow burned its budget.

   THE PIN THAT WAS MISSING. Test 17 above already asserted
   `every(tier === "founder_confirm")` -- and kept passing through the whole
   regression, because this harness does not load 18-goal-workspace.js, so
   `typeof goalCriteriaToChecks === "function"` was false and the old code
   fell to its else-branch. It never exercised the live path. This block
   DEFINES the classifier in the context first, so the branch that shipped is
   the branch under test. */
{
  const ctx = fresh();
  const posts = [];
  /* the real classifier, present exactly as panel.html provides it. If
     shadowCreateTask consults it for founder-typed text, these come back
     contains_artifact and the assertions below fail -- which is the point. */
  ctx.goalCriteriaToChecks = (text) =>
    String(text || "").split("\n").map(s => s.trim()).filter(Boolean)
      .map(check => ({ tier: "contains_artifact", check }));
  ctx.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({ id: "m-x", state: "brief_confirm" }) });
  ctx.shadowPost = (url, body) => { posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve(/\/act$/.test(url)
        ? { accepted: true, mission_id: "m-x" }
        : { id: "m-x", state: "brief_confirm" }) }); };
  ctx.loadShadowHome = () => Promise.resolve();
  ctx.renderShadowCard = () => {};
  ctx.showNudge = () => {};
  ctx.scheduleRender = () => {};

  const CRITERIA = ["The file contains HELLO",
                    "The file exists and contains 5 bullets.",
                    "Tests cover it.",
                    "The timestamp is visible on the task card.",
                    "Shadow reaches DONE."];
  ctx.S.shadowNew = { objective: "make the file", kind: "fix",
                      done: CRITERIA.join("\n") };
  (async () => {
    await ctx.shadowCreateTask();
    const b = posts.filter(p => p.url === "/api/shadow/missions")[0].body;
    const tiers = JSON.parse(JSON.stringify(b.done_when.map(c => c.tier)));
    const checks = JSON.parse(JSON.stringify(b.done_when.map(c => c.check)));
    assert(tiers.every(t => t === "founder_confirm"),
      "every founder-typed criterion must be theirs to confirm, got: "
      + tiers.join(","));
    /* 5. the wording is preserved verbatim, never normalised or dropped */
    assert.deepStrictEqual(checks, CRITERIA,
      "the founder's own words must survive unchanged");
    /* and the classifier was NOT consulted for this path */
    assert(!tiers.includes("contains_artifact"),
      "shape inference leaked back into the Delegate form");
    console.log("ok 17b founder-typed done_when stays founder_confirm");
  })().catch(e => { console.error("FAIL 17b:", e.message); process.exit(1); });
}

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
  assert(/where it runs/.test(h) && /a new chat/.test(h),
    "must say it runs in a new chat Shadow starts");
  assert(/done when/.test(h) && /a tested PR is open/.test(h), "done-when missing");
  assert(/data-shstart="m-k"/.test(h), "Start the task missing");
  assert(/Start the task</.test(h), "Start is not labelled as the design asks");
  assert(/or keep telling me/.test(h), "the keep-talking affordance is missing");
  /* THE FLOORS LINE IS NOT ON THE BRIEF (founder, 2026-09-15). What Shadow
     may not do on its own is safety configuration and lives in Shadow
     Settings; the floors themselves and every check are untouched. */
  assert(!/destructive git operations/.test(h),
    "floors are configuration, not a row under every task");
  assert(!/floors it can/.test(h), "the floors line must not be drawn here");
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

  /* 26a/26b/26c/26e removed (founder, 2026-09-15, PASS 2): all four drove
     the existing-chat flow through data-shexisting -- binding the target to
     the open pane, sending a scoped turn, letting a hand-pick win, and
     refusing an unscoped send. None of that surface exists now. What is
     kept below is what still runs: empty input is refused (26d), the
     DELEGATED composer is global on purpose (26f), and the send button
     takes the same single path as Enter (26g). */

  /* 26d. empty input starts nothing AND eats nothing */
  {
    const ctx = armed();
    ctx.S.openPanes = ["sess-open"];
    /* openFlow removed with the flow; the guard is composer-level */
    const el = compose("   ");
    enter(ctx, el);
    assert.strictEqual(ctx.posts.length, 0, "whitespace must not be sent");
    assert.strictEqual(el.value, "   ", "and must not be silently cleared");
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
    const el = compose("via the button");
    ctx.document.querySelector = (sel) =>
      sel === "[data-shhomecompose]" ? el : null;
    ctx.listeners.click({ target: { dataset: { shsend: "1" },
      closest: () => null } });
    assert.strictEqual(ctx.posts.length, 1, "one request, from the button too");
    assert.strictEqual(ctx.posts[0].body.scope_id, undefined,
      "the delegation composer is global on purpose");
  }

  console.log("ok 26 the delegation composer: empty refused, global "
    + "scope, one send from Enter or the button");
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

  /* -- 27d/27e removed (founder, 2026-09-15, PASS 2). Both drove the
     existing-chat entry point: 27d pinned that entering the flow targets
     the pane the founder is in, 27e that an unscoped turn is refused with
     "Pick the chat". data-shexisting is no longer rendered or handled and
     shadowExistingOpen can no longer be set, so both tested a path that no
     longer exists. 27f below -- the DELEGATED flow, global on purpose --
     is untouched and is the behaviour that matters now. */

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
  assert(!has(running, "retry"), "running: Retry would clone a live mission");

  const queued = card({ id: "c", state: "queued" });
  assert(!has(queued, "start"), "queued: Start must be gone");
  assert(has(queued, "drop"), "queued: Drop is the legal exit");

  const paused = card({ id: "d", state: "paused" });
  assert(!has(paused, "start"), "paused: Start must be gone");

  const blocked = card({ id: "e", state: "blocked", block_reason: "nope" });
  assert(!has(blocked, "start"), "NEEDS YOU: Start must be gone");

  const done = card({ id: "f", state: "done" });
  assert(!has(done, "start"), "done: Start must be gone");

  /* STOP AND RESUME ARE NOT ON THIS CARD (founder, 2026-09-15): the detail
     pane reports and asks, it is not a worker control panel. Asserted in
     every state so neither can drift back. */
  for (const [name, h] of [["running", running], ["paused", paused],
                           ["blocked", blocked], ["done", done]]){
    assert(!has(h, "stop"), name + ": the Stop button must not be on the card");
    assert(!has(h, "resume"), name + ": the Resume button must not be on the card");
  }

  /* ...AND THE ACTIONS THEMSELVES ARE UNCHANGED. Every state still offers
     exactly what mission_engine.TRANSITIONS accepts, on the plane that owns
     mission actions -- same data-shact hooks, same shadowMissionAct. */
  const row = (m) => ctx.shadowPlaneHtml([], [Object.assign(
    { objective: "o", template: "fix", turns_used: 1, max_turns: 20 }, m)],
    "working");
  const pRunning = row({ id: "b", state: "running" });
  assert(has(pRunning, "stop"), "running: Stop is still the legal exit");
  assert(!has(pRunning, "resume"), "running: Resume is still not legal");
  const pPaused = row({ id: "d", state: "paused" });
  assert(has(pPaused, "resume") && has(pPaused, "stop"),
    "paused: its two legal exits are still offered");
  const pQueued = row({ id: "c", state: "queued" });
  assert(has(pQueued, "drop"), "queued: Drop is still offered");

  const failed = card({ id: "g", state: "failed" });
  assert(!has(failed, "start"), "failed: Start must be gone");
  assert(has(failed, "retry"), "failed: retry is the product's own re-run");

  const stopped = card({ id: "h", state: "stopped" });
  assert(!has(stopped, "start"), "stopped: Start must be gone");
  assert(has(stopped, "retry"), "stopped: retry is offered");
  console.log("ok 32 each state exposes only the actions the engine accepts");
}

/* 33. "LAST UPDATED": THE CARD SAYS HOW FRESH WHAT IT SHOWS IS.
   The stamp is the server's `updated_at` (MissionStore.save re-stamps it on
   every write), rendered relative. The failure this guards against is a row
   that reads "just now" forever because it was drawn from the RENDER clock
   instead of the record -- which would make a wedged task look alive. */
{
  const ctx = fresh();
  const MIN = 60000, HOUR = 3600000, DAY = 86400000;
  const iso = (ms) => new Date(ms).toISOString().replace(/\.\d+Z$/, "Z");
  const card = (m) => ctx.shadowTaskCardHtml(Object.assign(
    { id: "s", objective: "o", template: "fix", state: "running",
      turns_used: 1, max_turns: 20 }, m));
  const stamp = (h) =>
    (h.match(/last updated<\/span>\s*<span class="shcard2v"[^>]*>([^<]*)</) || [])[1];

  /* the bands, against a pinned clock -- no wall-clock flake */
  const NOW = Date.parse("2026-09-15T12:00:00Z");
  const ago = (s) => ctx.shadowStampAgo(s, NOW);
  assert.strictEqual(ago(iso(NOW - 5000)), "just now", "seconds = just now");
  assert.strictEqual(ago(iso(NOW - 59000)), "just now", "under a minute");
  assert.strictEqual(ago(iso(NOW - 3 * MIN)), "3m ago", "minutes");
  assert.strictEqual(ago(iso(NOW - 59 * MIN)), "59m ago", "up to the hour");
  assert.strictEqual(ago(iso(NOW - 2 * HOUR)), "2h ago", "hours");
  assert.strictEqual(ago(iso(NOW - 4 * DAY)), "4d ago", "days");
  /* server ahead of this box is skew, never news from later */
  assert.strictEqual(ago(iso(NOW + 5 * MIN)), "just now",
    "a future stamp must not render as negative time");
  /* nothing to say beats guessing */
  assert.strictEqual(ago(""), "", "empty stamp renders nothing");
  assert.strictEqual(ago(null), "", "missing stamp renders nothing");
  assert.strictEqual(ago("not a date"), "", "garbage stamp renders nothing");

  /* NOT ON THE CARD ANY MORE (founder, 2026-09-15). The row came off the
     founder-facing brief; nothing underneath it moved. */
  const live = card({ updated_at: iso(Date.now() - 2 * MIN) });
  assert(!/shcard2stamp/.test(live) && !/last updated/.test(live),
    "LAST UPDATED must not be rendered on the Shadow RHS card");
  assert(!/shcard2stamp/.test(card({ created_at: iso(Date.now() - HOUR) })),
    "and not via the created_at fallback either");

  /* THE RECORD AND THE HELPERS ARE UNTOUCHED: updated_at still arrives, and
     the formatter still formats it -- the story block's "You answered"
     stamp is the same shadowStampAgo. Only the card stopped drawing a row. */
  const row = ctx.shadowTaskUpdatedHtml(
    { updated_at: iso(Date.now() - 2 * MIN) });
  assert(/2m ago/.test(row), "the freshness helper must still format a stamp");
  assert(/title="/.test(row), "the precise timestamp must survive on hover");
  assert.strictEqual(ctx.shadowTaskUpdatedHtml({}), "",
    "with no usable stamp the helper still says nothing");

  /* it is a row on the card, not a replacement for one: the facts beside it
     are untouched */
  /* the row is `TURN | 1 of 20` now: the key carries the word, the value
     carries the count, and the meter beside it is unchanged. */
  assert(/shcard2k">turn<\/span>\s*<span class="shcard2v">1 of 20/.test(live),
    "the budget row must survive");
  assert(/shtpill-/.test(live), "the state pill must survive");
  console.log("ok 33 the task card stamps how fresh the record it drew is");
}

/* 34. THE BUDGET IS A LENGTH, NOT ONLY A PAIR OF NUMBERS.
   "turn 14 of 20" makes the founder do the subtraction before learning the
   one thing the row is for: is this about to run out. The bar answers it at
   a glance, so what this guards is that the length and the numbers can never
   disagree -- and that a task with no stated ceiling draws NO bar rather
   than a full red track, which would be a lie about a task that is fine. */
{
  const ctx = fresh();
  const card = (m) => ctx.shadowTaskCardHtml(Object.assign(
    { id: "s", objective: "o", template: "fix", state: "running",
      turns_used: 1, max_turns: 20 }, m));
  const bar = (h) =>
    (h.match(/<span class="ubar shcard2bar"[\s\S]*?<\/span>/) || [])[0] || "";
  const width = (h) => {
    const w = bar(h).match(/width:(\d+)%/); return w ? Number(w[1]) : null; };
  const sev = (h) => {
    const s = bar(h).match(/<i class="(p-[a-z]+)"/); return s ? s[1] : null; };
  /* THE METER IS NO LONGER DRAWN ON THE CARD (founder, 2026-09-15), so the
     renderer is exercised directly. It, its arithmetic and its thresholds
     are unchanged -- only the call site on the brief went away. */
  const meter = (m) => ctx.shadowBudgetBarHtml(Object.assign(
    { turns_used: 1, max_turns: 20 }, m));

  /* the arithmetic, on its own */
  const pct = ctx.shadowBudgetPct;
  assert.strictEqual(pct({ turns_used: 5, max_turns: 20 }), 25, "5/20 = 25%");
  assert.strictEqual(pct({ turns_used: 0, max_turns: 20 }), 0,
    "an untouched budget is 0%, not 'no bar' -- an empty track is a fact");
  assert.strictEqual(pct({ turns_used: 20, max_turns: 20 }), 100, "spent");
  assert.strictEqual(pct({ turns_used: 25, max_turns: 20 }), 100,
    "over budget clamps -- a fill cannot overflow its own track");
  assert.strictEqual(pct({ turns_used: -3, max_turns: 20 }), 0,
    "a nonsense count floors at 0 rather than drawing backwards");
  /* NO DENOMINATOR, NO BAR -- 'nobody said' is not 'a budget of zero' */
  assert.strictEqual(pct({ turns_used: 4 }), null, "missing max_turns = no bar");
  assert.strictEqual(pct({ turns_used: 4, max_turns: 0 }), null, "0 max = no bar");
  assert.strictEqual(pct({}), null, "a bare record draws no bar");
  assert.strictEqual(pct(null), null, "and neither does no record at all");

  /* G9, THE THRESHOLD-STATE INVARIANT (founder, 2026-09-15): calm below 60,
     warning 60 THROUGH 85, critical ABOVE 85. Deliberately not usageSev's
     70/80 -- a rate-limit window refills and a turn budget does not, so this
     meter warns earlier and reserves red for near-death.

     THE EDGES ARE ASSERTED EXACTLY, not approximately: an off-by-one here is
     invisible on screen and would only ever be caught by a founder watching a
     run die amber. 60 and 85 both belong to WARNING. */
  const s = ctx.shadowBudgetSev;
  assert.strictEqual(s(0), "p-ok", "an empty budget is calm");
  assert.strictEqual(s(59), "p-ok", "59 is the last calm percent");
  assert.strictEqual(s(60), "p-warn", "EXACTLY 60% is warning, not calm");
  assert.strictEqual(s(61), "p-warn", "and it stays warning above the line");
  assert.strictEqual(s(84), "p-warn", "84 is still warning");
  assert.strictEqual(s(85), "p-warn",
    "EXACTLY 85% is warning -- critical is ABOVE 85, so 85 is not critical");
  assert.strictEqual(s(86), "p-block", "86 is the first critical percent");
  assert.strictEqual(s(100), "p-block", "a spent budget is critical");

  /* the same two edges reached through the REAL ratio, not a hand-fed
     percent -- 12/20 is exactly 60.0%, 17/20 is exactly 85.0% */
  assert.strictEqual(pct({ turns_used: 12, max_turns: 20 }), 60,
    "12 of 20 must be exactly 60.0%");
  assert.strictEqual(s(pct({ turns_used: 12, max_turns: 20 })), "p-warn",
    "a run exactly 60% through its budget shows warning");
  assert.strictEqual(pct({ turns_used: 17, max_turns: 20 }), 85,
    "17 of 20 must be exactly 85.0%");
  assert.strictEqual(s(pct({ turns_used: 17, max_turns: 20 })), "p-warn",
    "a run exactly 85% through its budget is still warning, not critical");
  assert.strictEqual(s(pct({ turns_used: 18, max_turns: 20 })), "p-block",
    "18 of 20 is 90% -- past the line, critical");

  /* G9's required edge cases, each asserted on its own */
  assert.strictEqual(s(pct({ turns_used: 0, max_turns: 20 })), "p-ok",
    "0 turns used is calm, never an alarm");
  assert.strictEqual(pct({ turns_used: 0, max_turns: 0 }), null,
    "0 turns AND no ceiling is still 'nobody said' -- no bar, no divide by 0");
  assert.strictEqual(pct({ turns_used: 7, max_turns: undefined }), null,
    "missing max_turns falls back to no bar");
  assert.strictEqual(pct({ turns_used: 7, max_turns: null }), null,
    "a null ceiling falls back the same way");
  assert.strictEqual(s(pct({ turns_used: 30, max_turns: 20 })), "p-block",
    "turns_used past max_turns is critical, not wrapped or negative");

  /* THE CARD PRINTS THE COUNT AND NOTHING ELSE. The bar came off the brief;
     the numbers it was drawn from are exactly the ones still printed. */
  const live = card({ turns_used: 5, max_turns: 20 });
  assert(/shcard2k">turn<\/span>\s*<span class="shcard2v">5 of 20/.test(live),
    "the TURN row must still print the count, straight from the record");
  assert.strictEqual(bar(live), "", "the card must draw no track");
  assert(!/ubar|shcard2bar/.test(live), "and no meter markup of any kind");
  assert(!/turns left/.test(live), "nor the meter's words");

  /* THE METER ITSELF IS UNCHANGED: same length, same palette, same words. */
  assert.strictEqual(width(meter({ turns_used: 5, max_turns: 20 })), 25,
    "the fill must match 5 of 20");
  assert.strictEqual(sev(meter({ turns_used: 5, max_turns: 20 })), "p-ok",
    "a quarter spent is not a warning");
  assert(/class="ubar shcard2bar"/.test(meter({ turns_used: 5, max_turns: 20 })),
    "the track must be the panel's existing .ubar, not a new one");

  /* the colour changes where the thresholds say, driven by the record */
  assert.strictEqual(sev(meter({ turns_used: 15, max_turns: 20 })), "p-warn",
    "15 of 20 is 75% -- the founder should see it coming");
  assert.strictEqual(sev(meter({ turns_used: 19, max_turns: 20 })), "p-block",
    "one turn left must not still read as fine");
  const over = meter({ turns_used: 23, max_turns: 20 });
  assert.strictEqual(width(over), 100, "an overrun clamps too");
  assert.strictEqual(sev(over), "p-block", "and reads as spent");

  /* the arithmetic the bar saves you stays reachable for hover and for a
     screen reader -- a length is readable by neither */
  const m5 = meter({ turns_used: 5, max_turns: 20 });
  assert(/aria-label="5 of 20 turns used, 15 turns left"/.test(m5),
    "the meter must say what it means in words");
  assert(/title="15 turns left"/.test(m5), "and on hover");
  assert(/title="1 turn left"/.test(meter({ turns_used: 19, max_turns: 20 })),
    "one is singular -- '1 turns left' is the tell of a generated string");
  assert(/role="img"/.test(bar(m5)),
    "a bare span is announced as nothing at all");

  /* NO CEILING, NO BAR: the row keeps the text it has always had */
  assert.strictEqual(meter({ turns_used: 4, max_turns: 0 }), "",
    "with no stated ceiling the meter draws no track, not a full one");
  const unbounded = card({ turns_used: 4, max_turns: 0 });
  assert(/shcard2k">turn<\/span>\s*<span class="shcard2v">4 of 0/.test(unbounded),
    "and the budget row itself is untouched");

  /* it is an addition to a row, not a replacement for the card: the facts
     around it survive */
  assert(/shtpill-/.test(live), "the state pill must survive");
  assert(/done when/.test(live), "the done-when row must survive");
  assert(/where it runs/.test(live), "the acts-in row must survive");
  console.log("ok 34 the TURN row is the count; the meter itself is unchanged");
}

console.log("test_shadow_home.js: all green");
