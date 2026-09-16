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
  /* QUEUED OFFERS NO START. The row is waiting on the run limit and nothing
     else, so admission would refuse the click and leave it exactly where it
     is -- the row says what it is waiting for, and keeps the one decision
     that is really the founder's. */
  assert(!/data-shact="start_now" data-shmid="m-2"/.test(g),
    "queued: no Start now -- the cap is what holds it, not a missing click");
  assert(/Waiting for a free\s+slot[\s\S]{0,120}data-shmid="m-2"/.test(g),
    "queued: says what it is waiting for");
  assert(/data-shact="drop"[\s\S]{0,60}data-shmid="m-2"/.test(g),
    "queued: Drop");
  assert(/data-shact="resume" data-shmid="m-3"/.test(g), "paused: Resume");
  assert(/data-shact="stop" data-shmid="m-1"/.test(g), "running: Stop");
  assert(!/data-shmid="m-4"/.test(g), "done missions leave the plane");
  /* NEEDS YOU MUST BE ANSWERABLE (2026-09-16). A supervisor fault now parks
     a live mission at `blocked` with no intervention form attached
     (mission_engine.INFRA_BLOCK_REASONS), so the row is the only surface
     that can offer the way back. Both edges are in TRANSITIONS already. */
  const b = ctx.shadowPlaneHtml([], [{ id: "m-9", state: "blocked",
    objective: "x", block_reason: "no_live_runtime",
    failure_class: "shadow_infra" }], "working");
  assert(/data-shact="resume" data-shmid="m-9"/.test(b), "blocked: Resume");
  assert(/data-shact="stop" data-shmid="m-9"/.test(b), "blocked: Stop");
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
  /* THE NEW TASK FORM IS THE ONLY THING ASKING (founder, 2026-09-15).
     With the panel open, the stage underneath drew "What should I take on? /
     Tell Shadow the outcome you want." plus a second outcome box -- directly
     below a form whose FIRST field is already "The outcome you want". Two
     boxes for one sentence, and only one of them creates a task. Open: the
     panel and nothing else. Closed: byte-identical to what shipped. */
  const newTask = (() => { const c = fresh(); c.S.shadowHomeDark = false;
    c.S.shadowMissions = MISSIONS; c.S.goals = []; c.S.shadowNewOpen = true;
    return c.shadowHomeHtml(); })();
  assert(!/What should I take on\?/.test(newTask),
    "the ask heading still draws behind the New Task form");
  assert(!/Tell Shadow the outcome you want/.test(newTask),
    "the ask copy still draws behind the New Task form");
  assert(!/Tell Shadow what outcome you want/.test(newTask),
    "the stage composer placeholder still draws behind the New Task form");
  assert(!/data-shhomecompose/.test(newTask),
    "the stage composer still draws behind the New Task form");
  assert(!/data-shsend="1"/.test(newTask),
    "the stage send arrow still draws behind the New Task form");
  /* ...and the form itself is untouched and still the way in */
  assert(/data-shnewpanel="1"/.test(newTask), "the New Task panel was lost");
  assert(/What should Shadow get done\?/.test(newTask),
    "the panel's own heading was lost");
  assert(/data-shnewobj="1"/.test(newTask), "the outcome field was lost");
  assert(/data-shnewdone="1"/.test(newTask), "the done-when field was lost");
  assert(/data-shnewcreate="1"/.test(newTask), "Create the task was lost");
  assert(/data-shnewcancel="1"/.test(newTask), "Cancel was lost");

  /* CLOSED IS EXACTLY AS IT WAS -- the whole of the other half of the rule.
     Same string, rendered by the same call, for a focused task and for an
     empty workspace. */
  assert(/data-shhomecompose/.test(h), "the closed workspace lost its composer");
  assert(/Say anything/.test(h), "the closed workspace lost its placeholder");
  assert(/data-shsend="1"/.test(h), "the send arrow was lost");
  assert(!/What should I take on\?/.test(h),
    "the ask heading must not draw on a focused workspace either");
  assert.strictEqual((empty.match(/data-shhomecompose/g) || []).length, 1,
    "a closed empty workspace still has exactly one composer");
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
  /* AUTONOMY RIDES THE SAME PAYLOAD, and the level has to be in the fixture
     because the page has no constant to fall back on any more: a settings
     answer without `autonomy` makes the section say "not reported", which is
     what 22d3 asserts. */
  autonomy: { level: "L3", levels: ["L0", "L1", "L2", "L3"],
              confirm_top_tier: true, worker_may_write: true,
              worker_mode: "acceptEdits" },
  tasks: { running_at_once: 5,
           turn_budget: { feature: 30, fix: 20, research: 15, watch: 0 },
           turn_budget_min: 1, turn_budget_max: 100,
           turn_budget_set: [],
           turn_budget_kinds: ["feature", "fix", "research"],
           offers: ["fix", "feature", "research", "watch"],
           offers_min: 1, offers_max: 12 },
  /* PRESENCE RIDES THE SAME PAYLOAD, and the rate has to be in the fixture
     because the page no longer has a constant to fall back on: a settings
     answer without `nudges_per_hour` makes the row say "not reported", which
     is what 22f5 asserts. */
  presence: { corner_card: true, hidden_apps: [],
              nudges_per_hour: 3,
              nudges_per_hour_min: 0, nudges_per_hour_max: 10 } };

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
  /* Autonomy is drawn to the reference AND writes: the level and the
     top-tier switch have a store now, so what must hold is the opposite of
     what it used to be -- they carry hooks, and the level on screen is the
     one the server reported. Pinned in 22d. */
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

/* 22d. AUTONOMY, to the reference AND to the store behind it.
   This case was rewritten on 2026-09-16, not extended, because what it
   asserted became false. It used to pin the section INERT -- "an unbacked
   control carries an action hook" was a FAILURE message, and it required
   >= 5 aria-disabled attributes -- which was right while the level and the
   switch had no endpoint. They have one now
   (/api/shadow/settings/autonomy), so the old assertions would have kept the
   feature out, and the shape of the case is inverted: the controls MUST
   write, and the level drawn MUST be the one the server reported. */
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
  /* the fixture says L3, so L3 is lit -- and it is the ONLY one lit */
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

  /* EVERY UNSELECTED LEVEL WRITES. The inversion of the old assertion. */
  ["L0", "L1", "L2"].forEach(lv =>
    assert(new RegExp('data-shautonomy="' + lv + '"').test(seg),
      "level " + lv + " cannot be chosen: no action hook"));
  /* ...and the SELECTED one does not: posting the value it already holds
     spends a round-trip to change nothing. */
  assert(!/data-shautonomy="L3"/.test(seg),
    "the selected level must not re-post itself");
  /* the switch carries its DESTINATION, not its state, so a repeated click
     cannot toggle twice off one render */
  assert(/data-shtoptier="0"/.test(h),
    "the top-tier switch must offer to turn OFF while it is on");
  /* nothing in the section may still claim to be inoperable */
  const auto = h.slice(h.indexOf('class="seg"'), h.indexOf('class="floorbar"'));
  assert(!/aria-disabled="true"/.test(auto),
    "a backed control still says it is not operable: " + auto.slice(0, 200));
  /* scoped to THIS section: other rows on the page may legitimately still be
     unbacked, and this case is about autonomy */
  assert(!/Not configurable yet/.test(auto), "the inert tooltip survived");
  console.log("ok 22d autonomy is drawn from the store and every control writes");
}

/* 22d2. THE LEVEL ON SCREEN IS THE SERVER'S, not a default. The old code
   carried `SH_LEVEL_NOW = "L3"`; if anything like it comes back, a founder
   running L0 would be shown Act. */
{
  const ctx = fresh();
  const set = JSON.parse(JSON.stringify(SET));
  set.autonomy = { level: "L0", levels: ["L0", "L1", "L2", "L3"],
                   confirm_top_tier: false, worker_may_write: false,
                   worker_mode: "plan" };
  ctx.S.shadowSettings = set;
  const h = ctx.shadowSettingsHtml();
  const seg = (h.match(/<div class="seg"[\s\S]*?<\/div>/) || [""])[0];
  const btns = seg.split("<button").slice(1);
  assert(btns.length === 4, "four levels, no more");
  assert(/class="on"/.test(btns[0]) && /L0/.test(btns[0]),
    "L0 was reported but is not the lit level");
  assert((seg.match(/class="on"/g) || []).length === 1,
    "exactly one level is on");
  assert(!/data-shautonomy="L0"/.test(seg), "the selected level re-posts itself");
  assert(/data-shautonomy="L3"/.test(seg), "L3 must be choosable from L0");
  /* the switch follows the server too, and offers the opposite */
  assert(/class="tog off" role="switch" aria-checked="false"/.test(h),
    "the switch must render off when the server says off");
  assert(/data-shtoptier="1"/.test(h),
    "an off switch must offer to turn ON");
  /* the CONSEQUENCE is stated, in the server's own word for it */
  assert(/read-only/.test(h), "L0 must say the worker cannot write");
  assert(/<code>plan<\/code>/.test(h),
    "the mode the server reported must be the mode shown");
  /* and the switch says it does not bite here */
  assert(/Applies at Act/.test(h),
    "the top-tier switch must say it does nothing below Act");
  console.log("ok 22d2 the level, the switch and the mode are read back, never assumed");
}

/* 22d3. NO AUTONOMY BLOCK -> SAY SO. An older server, or a settings read
   that failed, must not be drawn as L3 Act: that is the same lie the inert
   selector was written to avoid, arriving by a different road. */
{
  const ctx = fresh();
  const set = JSON.parse(JSON.stringify(SET));
  delete set.autonomy;
  ctx.S.shadowSettings = set;
  const h = ctx.shadowSettingsHtml();
  assert(/The autonomy level was not reported/.test(h),
    "a missing autonomy block must be stated, not defaulted");
  assert(!/class="seg"/.test(h),
    "no level may be drawn as selected when none was reported");
  assert(!/data-shautonomy=/.test(h),
    "nothing may write a level the page never read");
  /* the floors are NOT part of the autonomy store and must survive it */
  assert(/class="floorbar"/.test(h),
    "the floors must still render when the level is unknown");
  console.log("ok 22d3 a missing autonomy block says so and still draws the floors");
}

/* 22d4. THE FLOOR NOTE NAMES ACT. A founder who has just been handed an Act
   button is exactly the person who needs to know what it does not buy. */
{
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  const h = ctx.shadowSettingsHtml();
  assert(/Floors are confirm-first at every level, Act included/.test(h),
    "the floor note must say the top level does not clear the floors");
  assert(/not editable\s+here/.test(h),
    "the floors must still say they are locked");
  console.log("ok 22d4 the floors say they outrank every level");
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
    "the stepper must show the cap the engine enforces, got: "
      + step.slice(0, 160));
  /* the budget: a stepper on the real per-kind turn budget, and while no
     kind carries an override the AUTO pill still says so */
  const bstep = (sec.match(
    /<span class="step"><button[^]*?data-shbudget=[^]*?<\/span>/) || [""])[0];
  assert(/<span class="val">20<\/span>/.test(bstep),
    "the budget stepper must show the kind's real budget, got: "
      + bstep.slice(0, 200));
  assert(/class="auto"[^>]*>auto</.test(sec), "the AUTO pill is missing");
  assert(!/set by you/.test(sec),
    "nothing is overridden in the fixture, so nothing may claim it is");
  /* the chips: what Delegate offers, each with the x that now REMOVES it.
     Read off the Delegate panel's OWN render rather than a list retyped
     here, so the two can never drift -- whatever Delegate offers is what
     Settings states, and both now read the server's `offers`. */
  const kinds = (ctx.shadowDelegatePanelHtml().match(
    /data-shnewkind="([a-z0-9-]+)"/g) || []).map(m => m.split('"')[1]);
  assert(kinds.length >= 4, "the Delegate panel offered no kinds to compare");
  kinds.forEach(k => assert(
    new RegExp('class="chip"[^>]*>' + k + '<button class="cx"').test(sec),
    "Delegate offer missing its chip or x: " + k));
  assert(/class="chipadd"[\s\S]{0,120}\+ add</.test(sec), "no + add pill");
  /* EVERY CONTROL ON THIS SECTION NOW HAS A STORE BEHIND IT.

     This assertion used to say the opposite. It held that the chip x's and
     "+ add" must carry NO hook and must announce themselves inoperable,
     because there was nowhere to keep a delegate kind. There is now, so the
     old invariant is not weakened here -- it is SPENT. What replaces it is
     the same rule stated the only way still worth stating: this section may
     carry no hook that is not backed by a writer, and BACKED is the
     enumeration of what is.

     ENUMERATED, NEVER PREFIX-MATCHED. A filter like `h.indexOf("shoffer")
     !== 0` would exempt every future hook whose name happened to start that
     way, which is the drift this assertion exists to catch. Each new hook
     costs one line here, on purpose.

     Asserted by ATTRIBUTE rather than by stripping markup: the steppers nest
     spans, so a non-greedy slice ends early and silently readmits whatever
     it failed to cut. */
  assert(/class="seg segmini"/.test(sec),
    "the budget row must name the kind it edits");
  const BACKED = ["shrunlimit",                    // the cap stepper
                  "shbudget", "shbudgetkind",      // the budget stepper
                  /* The four below belong to Delegate offers (mission
                     m-8b8e698494ab), not to the turn-budget work. They are
                     THAT mission's to remove: if Delegate offers stops
                     writing, these four lines go with it. */
                  "shofferdel",                    // a chip's x
                  "shofferopen", "shofferadd",     // "+ add", then submit
                  "shoffername"];                  // the name box
  const hooks = (sec.match(/data-sh[a-z]+=/g) || [])
    .map(m => m.slice(5, -1));
  const stray = hooks.filter(h => BACKED.indexOf(h) === -1);
  assert(stray.length === 0,
    "an unbacked Tasks control carries an action hook: " + stray.join(","));
  /* one live x per offered kind -- no chip draws a dead one */
  const xs = sec.match(/<button class="cx"[^>]*>/g) || [];
  assert(xs.length === kinds.length,
    "one x per offered kind, got " + xs.length + " for " + kinds.length);
  xs.forEach(x => assert(/data-shofferdel="/.test(x),
    "a chip x carries no remove hook: " + x));
  assert(/class="chipadd"[^>]*data-shofferopen="1"/.test(sec),
    "+ add must carry its hook now that a kind can be kept");
  /* the phrase the dead controls wore is gone with them */
  assert(!/Not configurable yet/.test(sec),
    "nothing in Tasks may still claim it cannot be configured");
  /* and when the server sends no limits, none are invented */
  const d2 = JSON.parse(JSON.stringify(SET)); delete d2.tasks;
  ctx.S.shadowSettings = d2;
  const bare = ctx.shadowSettingsHtml();
  assert(/not reported/.test(bare), "a missing limit must be said, not guessed");
  assert(!/class="val">5</.test(bare), "a limit was invented from nowhere");
  console.log("ok 22e tasks: reference layout, engine-enforced numbers");
}

/* ── "RUNNING AT ONCE" IS A REAL CONTROL ──────────────────────────────────
   22e1-22e6. The stepper used to be drawn dead beside a number the page could
   only read. It writes now, and these are the four things that has to mean:
   the buttons carry the value they move TO, they stop at the server's band,
   one click sends exactly one write, and what repaints is the SERVER's
   answer -- never the value that was asked for. */

/* 22e1. the buttons carry a DESTINATION, already clamped when drawn. Sending
   a direction instead would let a repeated click compound off one render. */
{
  const ctx = fresh();
  const d = JSON.parse(JSON.stringify(SET));
  d.tasks = { running_at_once: 3, running_at_once_min: 1,
              running_at_once_max: 20, turn_budget: SET.tasks.turn_budget };
  ctx.S.shadowSettings = d;
  const h = ctx.shadowSettingsHtml();
  const sec = h.slice(h.indexOf(">Tasks<"), h.indexOf(">Presence<"));
  assert(/data-shrunlimit="2"[^>]*aria-label="fewer"/.test(sec)
      || /aria-label="fewer"[^>]*data-shrunlimit="2"/.test(sec),
    "minus must target 2, got: " + sec.slice(sec.indexOf("step"), 400));
  assert(/data-shrunlimit="4"/.test(sec), "plus must target 4");
  console.log("ok 22e1 the stepper's buttons carry the value they move to");
}

/* 22e2. the ends stop instead of inviting a click into a refusal -- and the
   server's band is what decides where the ends are, not a number in here */
{
  const ctx = fresh();
  const at = (n, lo, hi) => {
    const d = JSON.parse(JSON.stringify(SET));
    d.tasks = { running_at_once: n, running_at_once_min: lo,
                running_at_once_max: hi, turn_budget: SET.tasks.turn_budget };
    ctx.S.shadowSettings = d;
    const h = ctx.shadowSettingsHtml();
    return h.slice(h.indexOf(">Tasks<"), h.indexOf(">Presence<"));
  };
  const lo = at(1, 1, 6);
  const minus = (lo.match(/<button[^>]*aria-label="fewer"[^>]*>/) || [""])[0];
  assert(/aria-disabled="true"/.test(minus),
    "at the floor, minus must say it cannot go lower: " + minus);
  assert(!/aria-disabled/.test(
    (lo.match(/<button[^>]*aria-label="more"[^>]*>/) || [""])[0]),
    "plus is still live at the floor");
  const hi = at(6, 1, 6);
  assert(/aria-disabled="true"/.test(
    (hi.match(/<button[^>]*aria-label="more"[^>]*>/) || [""])[0]),
    "at the SERVER's ceiling (6, not 20) plus must stop");
  assert(!/aria-disabled/.test(
    (hi.match(/<button[^>]*aria-label="fewer"[^>]*>/) || [""])[0]),
    "minus is still live at the ceiling");
  console.log("ok 22e2 the stepper stops at the band the server reports");
}

/* 22e3. one click, one write -- and it is the number, not a nudge */
(async () => {
  const ctx = fresh();
  const posts = [];
  ctx.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({}) });
  ctx.shadowPost = (url, body) => { posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ running_at_once: 4, min: 1, max: 20,
        running_now: 1, queued_now: 0, starting: 0, over_cap: 0 }) }); };
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  ctx.loadShadowHome = () => {}; ctx.loadShadowSettings = () => {};
  ctx.showNudge = () => {};
  await ctx.listeners.click({ target: { dataset: { shrunlimit: "4" } } });
  assert.strictEqual(posts.length, 1, "exactly one write is sent");
  assert.strictEqual(posts[0].url, "/api/shadow/settings/tasks",
    "the write goes to the tasks settings route");
  assert.strictEqual(posts[0].body.running_at_once, 4,
    "the value is sent as a NUMBER, not a string or a direction");
  console.log("ok 22e3 one click sends exactly one numeric write");
})().catch(e => { console.error("FAIL 22e3:", e.message); process.exit(1); });

/* 22e4. the SERVER's answer is what the row repaints from. The server clamps,
   and raising the cap promotes queued tasks, so the counts beside the
   stepper change as a RESULT of the write -- an optimistic paint would show
   a value the engine never stored. */
(async () => {
  const ctx = fresh();
  ctx.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({}) });
  ctx.shadowPost = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({ running_at_once: 20, min: 1, max: 20,
      running_now: 20, queued_now: 3, starting: 2, over_cap: 0 }) });
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  const nudges = [];
  ctx.showNudge = (t) => nudges.push(t);
  ctx.loadShadowHome = () => {}; ctx.loadShadowSettings = () => {};
  /* the founder asked for 999; the server kept 20 */
  await ctx.listeners.click({ target: { dataset: { shrunlimit: "999" } } });
  assert.strictEqual(ctx.S.shadowSettings.tasks.running_at_once, 20,
    "the row must show what was STORED, not what was asked for");
  assert.strictEqual(ctx.S.shadowSettings.tasks.queued_now, 3,
    "the counts come back with the write");
  /* STARTING, not started: the server does not await the spawn, so the
     nudge must not claim an arrival it has not seen */
  assert(/starting 2 that were waiting/.test(nudges.join(" ")),
    "a promotion must be said out loud: " + nudges.join(" | "));
  assert(!/started 2/.test(nudges.join(" ")),
    "the nudge must not claim work already arrived");
  /* the rest of the settings object is untouched -- one state, not a copy */
  assert.deepStrictEqual(ctx.S.shadowSettings.tasks.turn_budget,
    SET.tasks.turn_budget, "the write clobbered an unrelated limit");
  console.log("ok 22e4 the stepper repaints from the server's answer");
})().catch(e => { console.error("FAIL 22e4:", e.message); process.exit(1); });

/* 22e5. lowering below what is in flight is NOT a kill switch, and the page
   says so rather than leaving the founder to read 1 beside three live tasks
   and conclude the setting is broken */
{
  const ctx = fresh();
  const d = JSON.parse(JSON.stringify(SET));
  d.tasks = { running_at_once: 1, running_at_once_min: 1,
              running_at_once_max: 20, running_now: 3, queued_now: 0,
              turn_budget: SET.tasks.turn_budget };
  ctx.S.shadowSettings = d;
  const h = ctx.shadowSettingsHtml();
  const sec = h.slice(h.indexOf(">Tasks<"), h.indexOf(">Presence<"));
  assert(/3 are still\s+running/.test(sec),
    "the overflow must be stated: " + sec.slice(0, 500));
  assert(/does not stop work already underway/.test(sec),
    "and it must say what the lower cap does NOT do");
  /* no overflow, but a queue -> the waiting count instead */
  d.tasks.running_at_once = 5; d.tasks.queued_now = 2;
  const sec2 = (() => { const x = ctx.shadowSettingsHtml();
    return x.slice(x.indexOf(">Tasks<"), x.indexOf(">Presence<")); })();
  assert(/2 waiting for a\s+free slot/.test(sec2),
    "a queue under the cap must be named: " + sec2.slice(0, 400));
  /* nothing to say -> nothing said */
  d.tasks.queued_now = 0; d.tasks.running_now = 1;
  const sec3 = (() => { const x = ctx.shadowSettingsHtml();
    return x.slice(x.indexOf(">Tasks<"), x.indexOf(">Presence<")); })();
  assert(!/still\s+running|waiting for a/.test(sec3),
    "a quiet cap must not editorialise");
  console.log("ok 22e5 the cap row is honest about work already underway");
}

/* 22e6. a write in flight holds BOTH ends down: four fast clicks off one
   rendered value would otherwise land on 2 instead of 5 */
(async () => {
  const ctx = fresh();
  let release = null;
  ctx.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({}) });
  let sent = 0;
  ctx.shadowPost = () => { sent++;
    return new Promise(r => { release = () => r({ ok: true, status: 200,
      json: () => Promise.resolve({ running_at_once: 4, min: 1, max: 20,
        running_now: 0, queued_now: 0, starting: 0, over_cap: 0 }) }); }); };
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  ctx.loadShadowHome = () => {}; ctx.loadShadowSettings = () => {};
  ctx.showNudge = () => {};
  const first = ctx.listeners.click({ target: { dataset: { shrunlimit: "4" } } });
  await ctx.listeners.click({ target: { dataset: { shrunlimit: "4" } } });
  await ctx.listeners.click({ target: { dataset: { shrunlimit: "4" } } });
  assert.strictEqual(sent, 1, "a second click while one is in flight resent");
  /* and while it is in flight the stepper says it is saving */
  const h = ctx.shadowSettingsHtml();
  const sec = h.slice(h.indexOf(">Tasks<"), h.indexOf(">Presence<"));
  assert((sec.match(/Saving…/g) || []).length === 2,
    "both ends must say they are saving: " + sec.slice(0, 400));
  release(); await first;
  assert(!ctx.S.shadowRunLimitBusy, "the hold must be released");
  console.log("ok 22e6 a write in flight cannot be double-sent");
})().catch(e => { console.error("FAIL 22e6:", e.message); process.exit(1); });

/* ── "BUDGET PER TASK" IS A REAL CONTROL ──────────────────────────────────
   22e7-22e12. The budget row used to be a number beside an AUTO pill that
   was telling the truth: there was no store behind it. There is one now, and
   these are the things that has to mean. They deliberately mirror 22e1-22e6
   one for one -- the same four properties (destination not direction, the
   server's band, one click one write, repaint from the server) plus the two
   the budget adds: a reset path, and a kind that cannot be set at all. */

/* 22e7. the buttons carry a DESTINATION, pre-clamped, stepping by 5. A
   direction would compound off one render; a step of 1 would be forty clicks
   from 20 to 60. */
{
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  const h = ctx.shadowSettingsHtml();
  const sec = h.slice(h.indexOf(">Tasks<"), h.indexOf(">Presence<"));
  /* the fixture's Delegate default is `fix` at 20 */
  assert(/data-shbudget="15"/.test(sec) && /data-shbudget="25"/.test(sec),
    "the budget stepper must carry 20±5 as destinations: " + sec.slice(0, 600));
  assert(/data-shbudgetkind="fix"/.test(sec),
    "each budget button must name the kind it moves");
  console.log("ok 22e7 the budget stepper sends a destination, stepping by 5");
}

/* 22e8. the band is the SERVER's, and both ends stop rather than click into
   a refusal the server would have to issue */
{
  const ctx = fresh();
  const d = JSON.parse(JSON.stringify(SET));
  d.tasks.turn_budget.fix = 1;            // at the floor
  ctx.S.shadowSettings = d;
  let h = ctx.shadowSettingsHtml();
  let sec = h.slice(h.indexOf(">Tasks<"), h.indexOf(">Presence<"));
  assert(/A task gets at least 1 turn/.test(sec),
    "at the floor the minus must say so: " + sec.slice(0, 600));
  assert(!/data-shbudget="0"/.test(sec), "the floor was stepped through");
  d.tasks.turn_budget.fix = 100;          // at the ceiling
  h = ctx.shadowSettingsHtml();
  sec = h.slice(h.indexOf(">Tasks<"), h.indexOf(">Presence<"));
  assert(/At most 100 turns for one task/.test(sec),
    "at the ceiling the plus must say so");
  assert(!/data-shbudget="105"/.test(sec), "the ceiling was stepped through");
  console.log("ok 22e8 the budget band comes from the server and holds");
}

/* 22e9. one click -> exactly one write, with a numeric `turns` and the kind */
(async () => {
  const ctx = fresh();
  const posts = [];
  ctx.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({}) });
  ctx.shadowPost = (url, body) => { posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ kind: "fix", turns: 25, auto: false,
        default: 20, min: 1, max: 100,
        turn_budget: { feature: 30, fix: 25, research: 15, watch: 0 },
        turn_budget_set: ["fix"] }) }); };
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  ctx.loadShadowSettings = () => {}; ctx.showNudge = () => {};
  await ctx.listeners.click({ target: { dataset: {
    shbudget: "25", shbudgetkind: "fix" } } });
  assert.strictEqual(posts.length, 1,
    "exactly one budget write is sent, got: " + JSON.stringify(posts));
  assert.strictEqual(posts[0].url, "/api/shadow/settings/budget",
    "the budget must not ride the cap's route: " + posts[0].url);
  assert.strictEqual(posts[0].body.turns, 25,
    "turns must be sent as a NUMBER, not a string or a direction");
  assert.strictEqual(posts[0].body.kind, "fix", "the kind must ride along");
  console.log("ok 22e9 one click sends one numeric budget write");
})().catch(e => { console.error("FAIL 22e9:", e.message); process.exit(1); });

/* 22e10. what repaints is the SERVER's answer -- and it must not clobber the
   cap sitting beside it in the same object */
(async () => {
  const ctx = fresh();
  ctx.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({}) });
  ctx.shadowPost = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({ kind: "fix", turns: 100, auto: false,
      default: 20, min: 1, max: 100,
      turn_budget: { feature: 30, fix: 100, research: 15, watch: 0 },
      turn_budget_set: ["fix"] }) });
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  ctx.loadShadowSettings = () => {}; ctx.showNudge = () => {};
  /* the founder asked for 999; the server clamped to 100 */
  await ctx.listeners.click({ target: { dataset: {
    shbudget: "999", shbudgetkind: "fix" } } });
  const t = ctx.S.shadowSettings.tasks;
  assert.strictEqual(t.turn_budget.fix, 100,
    "the row must repaint from the server's answer, not the request");
  assert.strictEqual(t.running_at_once, 5,
    "a budget write clobbered the cap beside it");
  const h = ctx.shadowSettingsHtml();
  const sec = h.slice(h.indexOf(">Tasks<"), h.indexOf(">Presence<"));
  assert(/set by you/.test(sec) && !/class="auto"[^>]*>auto</.test(sec),
    "an overridden kind must read `set by you`, never both pills: "
      + sec.slice(0, 700));
  console.log("ok 22e10 the budget repaints from the server and keeps the cap");
})().catch(e => { console.error("FAIL 22e10:", e.message); process.exit(1); });

/* 22e11. RESET. `auto` has to survive the trip as null -- Number("auto") is
   NaN, and a NaN budget would be a 400 the founder never asked for. */
(async () => {
  const ctx = fresh();
  const posts = [];
  const d = JSON.parse(JSON.stringify(SET));
  d.tasks.turn_budget.fix = 55; d.tasks.turn_budget_set = ["fix"];
  ctx.S.shadowSettings = d;
  ctx.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({}) });
  ctx.shadowPost = (url, body) => { posts.push(body);
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ kind: "fix", turns: 20, auto: true,
        default: 20, min: 1, max: 100,
        turn_budget: { feature: 30, fix: 20, research: 15, watch: 0 },
        turn_budget_set: [] }) }); };
  ctx.loadShadowSettings = () => {}; ctx.showNudge = () => {};
  /* the reset control only exists because the kind is overridden */
  const h0 = ctx.shadowSettingsHtml();
  assert(/data-shbudget="auto"/.test(
    h0.slice(h0.indexOf(">Tasks<"), h0.indexOf(">Presence<"))),
    "an overridden kind must offer a way back to auto");
  await ctx.listeners.click({ target: { dataset: {
    shbudget: "auto", shbudgetkind: "fix" } } });
  assert.strictEqual(posts.length, 1, "the reset did not send");
  assert.strictEqual(posts[0].turns, null,
    "reset must send null, got: " + JSON.stringify(posts[0].turns));
  const sec = (() => { const x = ctx.shadowSettingsHtml();
    return x.slice(x.indexOf(">Tasks<"), x.indexOf(">Presence<")); })();
  assert(/class="auto"[^>]*>auto</.test(sec) && !/set by you/.test(sec),
    "after a reset the row must be back to auto");
  console.log("ok 22e11 auto resets, and survives the trip as null");
})().catch(e => { console.error("FAIL 22e11:", e.message); process.exit(1); });

/* 22e12. WATCH HAS NO CONTROL, and the row says why rather than hiding it.
   Its budget is never consumed -- never_say returns before the budget is
   compared -- so a stepper there would look kept and never bind. Which kinds
   are settable is the SERVER's answer, not a list in the view. */
{
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  ctx.S.shadowBudgetKind = "watch";
  const h = ctx.shadowSettingsHtml();
  const sec = h.slice(h.indexOf(">Tasks<"), h.indexOf(">Presence<"));
  assert(!/data-shbudget="/.test(sec),
    "watch must carry no budget hook: " + sec.slice(0, 700));
  assert(/not spent/.test(sec), "watch must say why it has no budget");
  assert(/<span class="ev">0<\/span> turns/.test(sec),
    "watch still states its real budget");
  /* a write in flight holds the budget stepper down, same as the cap's */
  ctx.S.shadowBudgetKind = "fix"; ctx.S.shadowBudgetBusy = true;
  const busy = (() => { const x = ctx.shadowSettingsHtml();
    return x.slice(x.indexOf(">Tasks<"), x.indexOf(">Presence<")); })();
  assert((busy.match(/Saving…/g) || []).length >= 2,
    "both budget ends must say they are saving: " + busy.slice(0, 700));
  console.log("ok 22e12 watch is stated, not settable; busy holds both ends");
}

/* 22e13. THE LABEL NAMES THE KIND IT WRITES. "Budget per task" alone was a
   lie -- the control is per kind, and a founder who set `feature` to 50 would
   read a `fix` task running to 20 as the setting silently failing. */
{
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  const labelOf = () => {
    const h = ctx.shadowSettingsHtml();
    const sec = h.slice(h.indexOf(">Tasks<"));
    const i = sec.indexOf("Budget per task");
    return sec.slice(i, sec.indexOf("</span>", i))
              .replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();
  };
  ["fix", "feature", "research", "watch"].forEach(k => {
    ctx.S.shadowBudgetKind = k;
    assert.strictEqual(labelOf(), "Budget per task · " + k,
      "the label must name the kind the stepper writes, got: " + labelOf());
  });
  /* and it must not invent a kind when the server reported no budget */
  const d2 = JSON.parse(JSON.stringify(SET)); delete d2.tasks;
  ctx.S.shadowSettings = d2;
  const bare = ctx.shadowSettingsHtml();
  assert(/Budget per task<\/span>/.test(bare),
    "with no budget reported the label must stay bare");
  console.log("ok 22e13 the label tracks the picker, and invents nothing");
}

/* 22e14. EVERY KIND AT A GLANCE, with set values distinguishable from the
   template fallbacks they would otherwise be confused with. */
{
  const ctx = fresh();
  const d = JSON.parse(JSON.stringify(SET));
  d.tasks.turn_budget = { feature: 50, fix: 20, research: 15, watch: 0 };
  d.tasks.turn_budget_set = ["feature"];
  ctx.S.shadowSettings = d;
  const h = ctx.shadowSettingsHtml();
  const ro = (h.match(/<div class="srow budall">[\s\S]*?<\/div>/) || [""])[0];
  assert(ro, "the all-kinds readout is missing");
  /* every offered kind, with its EFFECTIVE value */
  [["feature", 50], ["fix", 20], ["research", 15], ["watch", 0]].forEach(
    ([k, v]) => assert(
      new RegExp('budk[^"]*"[^>]*>' + k + ' <b>' + v + '</b>').test(ro),
      "readout missing " + k + " " + v + ": " + ro.slice(0, 400)));
  /* set is ACCENTED, fallbacks are not -- and exactly one is set here */
  assert((ro.match(/class="budk on"/g) || []).length === 1,
    "exactly the one set kind may be accented: " + ro.slice(0, 400));
  assert(/class="budk on"[^>]*>feature/.test(ro),
    "the accented kind must be the one in turn_budget_set");
  /* THE INFERENCE TRAP: a kind set to exactly its own default is still SET.
     Deriving `set` by comparing value to default would redraw it as auto and
     silently remove the founder's way back. */
  d.tasks.turn_budget_set = ["feature", "fix"];   // fix is set, to its own 20
  const ro2 = (ctx.shadowSettingsHtml()
    .match(/<div class="srow budall">[\s\S]*?<\/div>/) || [""])[0];
  assert(/class="budk on"[^>]*>fix <b>20<\/b>/.test(ro2),
    "a kind set to its own default must still read as set: "
      + ro2.slice(0, 400));
  /* the readout states, it does not write */
  assert(!/data-sh[a-z]+=/.test(ro), "the readout must carry no action hook");
  console.log("ok 22e14 the readout states every kind, set apart from fallback");
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
  /* ONE switch with no app open, not two. "Hide for this app" has no subject
     outside an app, and it says so instead of drawing a switch -- see 22f4.
     The corner card is the only Presence row that is always operable. */
  assert((sec.match(/class="tog/g) || []).length === 1,
    "with no app open the corner card is the only toggle: " + sec.slice(0, 300));
  /* the add bar */
  assert(/class="addbar"/.test(sec), "no add-a-control bar");
  assert(/Tell Shadow what to add/.test(sec), "its placeholder is missing");
  assert(/class="go"/.test(sec) && /class="sp"/.test(sec),
    "the accent dot and go button are missing");
  /* THE CORNER CARD ACTS. "Hide for this app" is asserted in 22f4 and in
     test_shadow_presence.js, where a write can be awaited.

     WHAT USED TO BE HERE, deliberately recorded rather than deleted: this
     block asserted that "Hide for this app" flipped S.shadowQuiet -- "the
     SAME flag the card's quiet control does". That was true and was the
     defect. The row's label named one thing and its switch did another, and
     the thing it did died at reload because the flag was memory-only. The
     row now has a store and a route of its own, so the assertion could not
     survive; what replaces it is the NEGATIVE claim, which is the one worth
     keeping: the two are independent in both directions. */
  assert(/data-shpresence="card"/.test(sec),
    "the corner-card toggle must be operable");
  assert(!/data-shpresence="quiet"/.test(sec),
    "no Presence row may still flip the memory-only quiet flag");
  ctx.scheduleRender = () => {};
  /* the corner-card switch is no longer one of the memory-only pair -- it
     writes to a store, so its claims moved to 22f2 where a write can be
     awaited. What is asserted HERE is only that it no longer touches the
     session flag, which is the contract this change replaced: the two mean
     different things now (standing choice vs "not right now") and conflating
     them is what made the setting die at reload. */
  ctx.S.shadowHideSession = false;
  ctx.S.shadowCardEvery = true;
  ctx.shadowPost = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({ corner_card: false }) });
  ctx.listeners.click({ target: { dataset: { shpresence: "card" } } });
  assert.strictEqual(ctx.S.shadowHideSession, false,
    "the setting must NOT flip the card's hide-for-this-session flag");
  /* nothing states a value it cannot keep: with an unconfigured payload the
     hours are "not set" and the rate is "not reported", rather than the
     mock's 9pm-8am and a 3 that nothing would enforce */
  assert(/not set/.test(sec),
    "an unset quiet window must say so, not print mock hours");
  assert(sec.indexOf("9pm") === -1 && sec.indexOf("8am") === -1,
    "mock hours were printed as if configured");
  /* QUIET HOURS IS NO LONGER INERT, and this block used to say the opposite.
     What used to be here, recorded rather than deleted: an assertion that no
     data-sh hook appeared between "Quiet hours" and "Hide for this app",
     under the rule that an unbacked control must not carry an action. That
     rule has not changed -- the row has simply stopped being unbacked. It now
     has a store (presence.json), a route
     (POST /api/shadow/settings/quiet-hours) and a clock, so the honest claim
     inverts: it must OFFER the way to change it.

     "not set" survives alongside it, and that pairing is the point. The row
     states what it truly has, which is no window, AND gives the founder the
     control to set one -- which is exactly what it could not do before. */
  assert(/data-shquietopen/.test(sec),
    "quiet hours has a store now: the row must offer the way to set it");
  assert(!/data-shquietclear/.test(sec),
    "there is no window to clear, so no clear control may be drawn");
  assert(!/quiet now/.test(sec),
    "an unset window is never quiet now");
  assert(/no app open/.test(sec),
    "with no app open the hide row must say so");
  console.log("ok 22f presence: reference layout, real flags wired, rest inert");
}

/* 22f4. "HIDE FOR THIS APP" IS PER APP, AND HAS A SUBJECT OR SAYS IT DOES
   NOT. The write itself, the dot going, and the independence from quiet are
   asserted in test_shadow_presence.js, where the overlay is loaded and a
   round-trip can be awaited. What belongs HERE is the row: which app it is
   about, and what it does when there is no app to be about.

   THE SUBJECT IS S.modSel -- the open app id the Apps screen already owns.
   If this ever starts reading something else, "this app" has quietly become
   a second notion of the current app. */
{
  const ctx = fresh();
  ctx.modSelected = (s) => ({ id: s.modSel, name: "Photo Gallery" });
  const d = JSON.parse(JSON.stringify(SET));
  /* MERGED, not replaced: the fixture's presence block carries the other
     Presence rows' values too, and dropping them here would quietly change
     what the rest of the section renders while this block is looking at one
     row of it. */
  d.presence = Object.assign({}, d.presence, { hidden_apps: [] });
  ctx.S.shadowSettings = d;

  const rowOf = () => {
    const h = ctx.shadowSettingsHtml();
    const i = h.indexOf("Hide for this app");
    return h.slice(i, h.indexOf("</div>", i)).replace(/\s+/g, " ");
  };

  /* no app open: no switch, and nothing to click */
  assert(/no app open/.test(rowOf()), "no subject must be stated: " + rowOf());
  assert(!/data-shpresence="app"/.test(rowOf()),
    "a switch with a null subject must not be drawn");

  /* an app open: a real switch, naming the app */
  ctx.S.modSel = "photo-gallery";
  assert(/data-shpresence="app"/.test(rowOf()), "the switch must appear");
  assert(/Photo Gallery/.test(rowOf()),
    "the row must name the app it is about: " + rowOf());
  assert(/aria-checked="false"/.test(rowOf()), "and read off: " + rowOf());

  /* hidden for THAT app reads on; another app is unaffected */
  d.presence.hidden_apps = ["photo-gallery"];
  assert(/aria-checked="true"/.test(rowOf()), "a hidden app reads on: " + rowOf());
  ctx.S.modSel = "recipe-box";
  assert(/aria-checked="false"/.test(rowOf()),
    "a hide on one app must not read as on for another: " + rowOf());
  console.log("ok 22f4 hide-for-this-app is about the open app, or says none");
}

/* 22f2. THE CORNER CARD IS A STORED SETTING NOW, so it is asserted the way
   the steppers are: one write, to its own route, carrying a boolean, and the
   row repaints from the SERVER's answer.

   The claim that matters most is the negative one -- the session flag does
   not move. Those two meanings shared a flag before this, which is precisely
   why the founder's choice died at reload. */
(async () => {
  const ctx = fresh();
  const posts = [];
  ctx.scheduleRender = () => {}; ctx.showNudge = () => {};
  ctx.loadShadowSettings = () => {}; ctx.loadShadowHome = () => {};
  ctx.fetch = () => Promise.resolve({ ok: true,
    json: () => Promise.resolve({}) });
  ctx.shadowPost = (url, body) => { posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ corner_card: body.corner_card }) }); };
  ctx.S.shadowSettings = { presence: { corner_card: true } };
  ctx.S.shadowCardEvery = true;
  ctx.S.shadowHideSession = false;

  await ctx.listeners.click({ target: { dataset: { shpresence: "card" } } });
  assert.strictEqual(posts.length, 1, "exactly one write is sent");
  assert.strictEqual(posts[0].url, "/api/shadow/settings/presence",
    "the write goes to the presence settings route");
  assert.strictEqual(posts[0].body.corner_card, false,
    "the value is sent as a BOOLEAN destination, not a toggle instruction");
  assert.strictEqual(ctx.S.shadowCardEvery, false, "the durable flag moved");
  assert.strictEqual(ctx.S.shadowHideSession, false,
    "the setting must NOT move the card's hide-for-this-session flag -- "
    + "that conflation is the contract this replaced");
  assert.strictEqual(ctx.S.shadowSettings.presence.corner_card, false,
    "the row repaints from the server's answer, not the optimistic value");
  assert(/aria-checked="false"[^>]*data-shpresence="card"/
    .test(ctx.shadowSettingsHtml().replace(/\s+/g, " ")),
    "the corner-card switch must read off once it is off");

  await ctx.listeners.click({ target: { dataset: { shpresence: "card" } } });
  assert.strictEqual(posts[1].body.corner_card, true,
    "it is a switch, not a one-way door");
  assert.strictEqual(ctx.S.shadowCardEvery, true, "and the flag comes back");
  console.log("ok 22f2 the corner card writes to its own route, and is not "
    + "the session flag");

  /* a write that did not land may not leave the switch claiming it did */
  const c2 = fresh();
  c2.scheduleRender = () => {}; c2.showNudge = () => {};
  c2.loadShadowSettings = () => {}; c2.loadShadowHome = () => {};
  c2.fetch = () => Promise.resolve({ ok: true,
    json: () => Promise.resolve({}) });
  c2.shadowPost = () => Promise.resolve({ ok: false, status: 500,
    json: () => Promise.reject(new Error("no body")) });
  c2.S.shadowCardEvery = true;
  await c2.listeners.click({ target: { dataset: { shpresence: "card" } } });
  assert.strictEqual(c2.S.shadowCardEvery, true,
    "a refused write must put the flag BACK -- a switch reading off over a "
    + "disk that says on is the exact failure this feature removes");
  console.log("ok 22f3 a refused write reverts rather than lying");
})().catch(e => { console.error("FAIL 22f2:", e.message); process.exit(1); });

/* 22f5. NUDGES PER HOUR IS THE FOUNDER'S NUMBER.

   The row drew a stepper with both buttons aria-disabled and no action hook,
   printing the JS constant SH_PILLS_PER_HOUR. Three things had to become true
   for it to be a setting, and they are what this asserts: it is drawn from
   the SERVER's payload, it WRITES, and it repaints from the stored answer
   rather than the optimistic one. */
(async () => {
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  const sec = (c) => { const h = c.shadowSettingsHtml();
    return h.slice(h.indexOf(">Presence<"), h.indexOf(">Attention<")); };
  let s = sec(ctx);
  assert(/<span class="val">3<\/span>/.test(s),
    "the stepper must show the payload's rate: " + s.slice(0, 400));
  assert(/data-shnudges="2"/.test(s) && /data-shnudges="4"/.test(s),
    "each button must carry its own already-clamped destination: " + s);

  /* NO NUMBER, NO CLAIM. The browser keeps no default of its own now, so a
     payload without the field must say so rather than print a 3 that nothing
     enforces -- the exact defect this row shipped with. */
  const bare = fresh();
  bare.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  delete bare.S.shadowSettings.presence.nudges_per_hour;
  const bsec = sec(bare);
  const nrow = bsec.slice(bsec.indexOf("Nudges per hour"),
                          bsec.indexOf("Hide for this app"));
  assert(/not reported/.test(nrow) && !/data-shnudges/.test(nrow),
    "with no rate in the payload the row must state nothing: " + nrow);

  /* the ends stop at the server's band */
  const edge = fresh();
  edge.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  edge.S.shadowSettings.presence.nudges_per_hour = 0;
  let es = sec(edge);
  assert(/data-shnudges="0"/.test(es) && /data-shnudges="1"/.test(es),
    "at the floor, fewer must stop at the floor: " + es);
  assert(/never unasked/.test(es),
    "a rate of 0 must say what it means, not read as a broken stepper");
  edge.S.shadowSettings.presence.nudges_per_hour = 10;
  es = sec(edge);
  assert(/data-shnudges="10"/.test(es) && /data-shnudges="9"/.test(es),
    "at the ceiling, more must stop at the ceiling: " + es);

  /* IT WRITES, and the row repaints from what the SERVER stored */
  const posts = [];
  ctx.scheduleRender = () => {};
  ctx.loadShadowSettings = () => {};
  ctx.showNudge = () => {};
  ctx.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  ctx.shadowPost = (url, body) => { posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ nudges_per_hour: 1, min: 0, max: 10 }) }); };
  await ctx.listeners.click({ target: { dataset: { shnudges: "2" } } });
  assert.strictEqual(posts.length, 1, "the click must write once");
  assert.strictEqual(posts[0].url, "/api/shadow/settings/presence",
    "the write goes to the presence settings route");
  /* property-wise, not deepStrictEqual: the body is built inside the vm, so
     its prototype is that realm's Object and a strict deep compare fails on
     the prototype rather than on anything anyone cares about */
  assert.strictEqual(posts[0].body.nudges_per_hour, 2,
    "the write carries the button's already-clamped destination");
  assert.deepStrictEqual(Object.keys(posts[0].body), ["nudges_per_hour"],
    "one write moves one field");
  assert.strictEqual(ctx.S.shadowSettings.presence.nudges_per_hour, 1,
    "the row must fold the SERVER's answer, not the value it sent");
  assert.strictEqual(ctx.S.shadowNudgeRate, 1,
    "the flag pillAllowed reads must move too, or the setting is right on "
    + "this screen and stale everywhere it is actually enforced");
  s = sec(ctx);
  assert(/<span class="val">1<\/span>/.test(s),
    "the stepper must repaint at the stored value: " + s.slice(0, 400));

  /* a refused write stores nothing, moves nothing, and says so */
  const bad = fresh();
  bad.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  bad.S.shadowNudgeRate = 3;
  bad.scheduleRender = () => {};
  bad.loadShadowSettings = () => {};
  const said = [];
  bad.showNudge = (t) => { said.push(t); return null; };
  bad.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  bad.shadowPost = () => Promise.resolve({ ok: false, status: 500,
    json: () => Promise.resolve({}) });
  await bad.listeners.click({ target: { dataset: { shnudges: "7" } } });
  assert.strictEqual(bad.S.shadowSettings.presence.nudges_per_hour, 3,
    "a refused write must not look stored");
  assert.strictEqual(bad.S.shadowNudgeRate, 3,
    "and must not move the flag the pill reads");
  assert(said.some(t => /did not stick/.test(t)),
    "a refused write must say so: " + JSON.stringify(said));
  console.log("ok 22f5 nudges per hour: the server's number, written and "
    + "repainted from the answer");
})().catch(e => { console.error("FAIL 22f5:", e.message); process.exit(1); });

/* 22f6. QUIET HOURS, THE CLOCK -- the JS half of a rule written twice.

   THE TABLE IS NOT WRITTEN HERE. It is read from test_quiet_hours_cases.json,
   the same file test_shadow_quiet_hours.py drives shadow_presence.window_active
   from, so the Python and JS copies of the wrap-around rule cannot drift apart
   without one of the two lanes going red. Adding a case to that file adds it
   to both lanes at once -- which is the reason not to inline "just one more"
   case here. */
{
  const QCASES = JSON.parse(fs.readFileSync(
    path.join(__dirname, "test_quiet_hours_cases.json"), "utf8"));
  const ctx = fresh();
  assert(typeof ctx.shadowQuietWindowNow === "function",
    "the overlay must export the window predicate the home row also uses");
  assert(QCASES.active.length > 0, "the shared table is empty");
  for (const c of QCASES.active){
    const win = QCASES.windows[c.window];
    const [h, m] = c.at.split(":").map(Number);
    /* a fixed date, deliberately not today: the rule reads hours and minutes
       only, and pinning the date is what keeps this lane from changing its
       verdict with the hour it happens to be run at */
    const at = new Date(2026, 2, 17, h, m);
    assert.strictEqual(ctx.shadowQuietWindowNow(win, at), c.quiet,
      `${c.window} @ ${c.at}: ${c.why}`);
  }
  /* the same four the Python lane pins, so neither table can be quietly
     hollowed out instead of the code being fixed */
  const ats = new Set(QCASES.active.filter(c => c.window === "wrap")
    .map(c => c.at));
  for (const need of ["21:00", "00:00", "07:59", "08:00"])
    assert(ats.has(need), "the shared table lost the " + need + " case");
  /* a junk window is not quiet, and above all does not THROW -- this runs
     inside showPill, so an exception here would take the pill down with it */
  for (const junk of [null, undefined, {}, { start: "9pm", end: "x" },
                      { start: "10:00", end: "10:00" }, "21:00-08:00", 7])
    assert.strictEqual(ctx.shadowQuietWindowNow(junk, new Date(2026, 2, 17, 3, 0)),
      false, "a junk window must read as not quiet: " + JSON.stringify(junk));
  console.log("ok 22f6 quiet hours: the wrap-around rule, from the shared "
    + "case table (" + QCASES.active.length + " cases)");
}

/* 22f7. QUIET HOURS, THE GATE -- it silences through the gate that already
   existed, not a second one beside it. */
{
  const ctx = fresh();
  ctx.S.shadowQuiet = false;
  ctx.S.shadowQuietHours = null;
  /* a rate must be known or pillAllowed silences on its own account, which
     would make every assertion below pass for the wrong reason */
  ctx.S.shadowNudgeRate = 3;
  /* showPill needs a real-ish element back to prove it was NOT silenced */
  ctx.document.createElement = () => ({ setAttribute(){}, remove(){},
    dataset: {}, className: "", textContent: "" });
  const src15 = fs.readFileSync(
    path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
  const body = src15.slice(src15.indexOf("function showPill"));
  /* the gate is everything before the rate-limit branch, with comments
     stripped -- a claim about what the CODE does must not be satisfiable by
     prose that merely mentions the function, and slicing to a landmark rather
     than a character count keeps this from breaking when a comment grows */
  const gate = body.slice(0, body.indexOf("const isNudge"))
    .replace(/\/\*[\s\S]*?\*\//g, "");
  assert(/shadowQuietNow\(\)/.test(gate),
    "showPill must gate on the one quiet resolver, got: " + gate);
  assert(!/if \(S\.shadowQuiet\)/.test(gate),
    "the old single-flag check must be REPLACED, not joined by a second gate");

  /* no window, switch off: a pill gets through */
  assert(ctx.showPill("hello") !== null, "nothing is quiet yet");
  /* the manual switch alone still silences (the behaviour that existed) */
  ctx.S.shadowQuiet = true;
  assert.strictEqual(ctx.showPill("psst"), null, "the quiet switch still works");
  ctx.S.shadowQuiet = false;
  /* and now the CLOCK alone silences, with the switch off. The window is set
     to the hour the test is actually running in, so this asserts the gate
     reads the live clock rather than a boolean somebody seeded. */
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const nextH = String((now.getHours() + 2) % 24).padStart(2, "0");
  ctx.S.shadowQuietHours = { start: hh + ":00", end: nextH + ":00" };
  if (ctx.S.shadowQuietHours.start !== ctx.S.shadowQuietHours.end){
    assert.strictEqual(ctx.showPill("psst"), null,
      "inside the window the pill must be silenced by the clock alone");
  }
  /* a nudge-flagged pill buys past the RATE LIMIT, never past quiet */
  assert.strictEqual(ctx.showPill("urgent", { nudge: true }), null,
    "opts.nudge must not buy past quiet hours");
  /* outside the window it speaks again */
  const backH = String((now.getHours() + 3) % 24).padStart(2, "0");
  const backE = String((now.getHours() + 4) % 24).padStart(2, "0");
  ctx.S.shadowQuietHours = { start: backH + ":00", end: backE + ":00" };
  assert(ctx.showPill("hello again") !== null,
    "outside the window the pill speaks again");
  console.log("ok 22f7 quiet hours gate showPill through the existing quiet "
    + "check, and a nudge cannot buy past them");
}

/* 22f8. QUIET STANDS THE ALARM DOWN, IT DOES NOT HIDE THE NEWS. */
{
  const ctx = fresh();
  const mk = () => { const d = { className: "", innerHTML: "", attrs: {},
    setAttribute(k, v){ this.attrs[k] = v; } }; return d; };
  ctx.S.shadowQuiet = false; ctx.S.shadowQuietHours = null;
  const loud = mk();
  ctx.applyDotState(loud, { watching: true, alerts: 2 });
  assert(/shdot-alert/.test(loud.className), "alerts ring when not quiet");
  assert(/need you/.test(loud.attrs["aria-label"] || ""), "and say so");
  assert(/shbadge">2</.test(loud.innerHTML), "the count is shown");

  ctx.S.shadowQuiet = true;
  const hushed = mk();
  ctx.applyDotState(hushed, { watching: true, alerts: 2 });
  assert(!/shdot-alert/.test(hushed.className),
    "quiet must stand the alarm ring down");
  assert(!/need you/.test(hushed.attrs["aria-label"] || ""),
    "and drop the shoulder-tap phrasing");
  assert(/shbadge">2</.test(hushed.innerHTML),
    "but the COUNT stays -- being quiet is Shadow not speaking first, not "
    + "Shadow hiding what is waiting for the founder who looks");
  assert(/shdot-live/.test(hushed.className),
    "and the dot keeps its state colour, so it is still reachable");
  console.log("ok 22f8 quiet drops the alert ring, never the badge count");
}

/* 22f9. THE ROW: three states, and the writer behind them. */
(async () => {
  /* a set window renders its hours and offers both change and clear */
  const ctx = fresh();
  /* the writers guard on fetch existing before they do anything -- without it
     every click below would return early and the assertions would pass or
     fail for a reason that has nothing to do with quiet hours */
  ctx.fetch = () => Promise.resolve({ ok: true,
    json: () => Promise.resolve({}) });
  ctx.S.shadowSettings = { presence: {
    corner_card: true, hidden_apps: [], nudges_per_hour: 3,
    quiet_hours: { start: "21:00", end: "08:00" }, quiet_now: false } };
  ctx.S.shadowQuietHours = { start: "21:00", end: "08:00" };
  const h = ctx.shadowSettingsHtml();
  const sec = h.slice(h.indexOf(">Presence<"), h.indexOf(">Attention<"));
  assert(/21:00/.test(sec) && /08:00/.test(sec),
    "a set window must state its hours: " + sec.slice(0, 300));
  assert(/data-shquietopen/.test(sec), "the value opens for editing");
  assert(/data-shquietclear/.test(sec), "and a set window can be cleared");

  /* EDITING: two time fields, behind the offers input's own pattern */
  ctx.S.shadowQuietEditing = true;
  ctx.S.shadowQuietDraft = { start: "22:00", end: "07:00" };
  const ed = ctx.shadowSettingsHtml();
  assert(/type="time"[^>]*data-shquietstart/.test(ed.replace(/\s+/g, " "))
      || /data-shquietstart[^>]*type="time"/.test(ed.replace(/\s+/g, " ")),
    "the start is a native time field");
  assert(/data-shquietend/.test(ed), "and so is the end");
  assert(/class="chipin shquietin"/.test(ed),
    "the editor reuses the offers input's bar rather than inventing one");
  assert(/value="22:00"/.test(ed) && /value="07:00"/.test(ed),
    "the draft is rendered back into the fields");
  assert(/data-shquietsave/.test(ed), "save is reachable");
  assert(/data-shquietcancel/.test(ed), "and so is abandoning the edit");

  /* the draft survives a keystroke WITHOUT a re-render (the caret rule) */
  let renders = 0;
  ctx.scheduleRender = () => { renders += 1; };
  ctx.listeners.input({ target: { dataset: { shquietstart: "1" },
                                  value: "23:15" } });
  assert.strictEqual(ctx.S.shadowQuietDraft.start, "23:15", "the draft moved");
  assert.strictEqual(renders, 0,
    "typing must not re-render -- that is the caret rule this file already "
    + "follows for the offer name");

  /* SAVE: one POST, carrying the window, to its own route */
  const posts = [];
  const said = [];
  ctx.showNudge = (t) => said.push(t);
  ctx.shadowPost = (url, b) => { posts.push({ url, body: b });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ quiet_hours: b.quiet_hours,
                                    quiet_now: true }) }); };
  await ctx.listeners.click({ target: { dataset: { shquietsave: "1" } } });
  assert.strictEqual(posts.length, 1, "exactly one write is sent");
  assert.strictEqual(posts[0].url, "/api/shadow/settings/quiet-hours",
    "quiet hours has its own single-purpose route");
  /* compared as VALUES, not with deepStrictEqual: these objects are built
     inside the vm context and carry its Object.prototype, which a strict deep
     compare counts as a difference */
  assert.strictEqual(JSON.stringify(posts[0].body),
    JSON.stringify({ quiet_hours: { start: "23:15", end: "07:00" } }),
    "the window is sent whole: " + JSON.stringify(posts[0].body));
  assert.strictEqual(JSON.stringify(ctx.S.shadowQuietHours),
    JSON.stringify({ start: "23:15", end: "07:00" }),
    "the GATE's window is seeded from the stored answer");
  assert.strictEqual(JSON.stringify(ctx.S.shadowSettings.presence.quiet_hours),
    JSON.stringify({ start: "23:15", end: "07:00" }),
    "and so is the page's copy");
  assert.strictEqual(ctx.S.shadowQuietEditing, false, "the editor closes");

  /* CLEAR sends an explicit null -- the one shape the store deletes for */
  await ctx.listeners.click({ target: { dataset: { shquietclear: "1" } } });
  assert.strictEqual(posts.length, 2, "clear is a write too");
  assert.strictEqual(posts[1].body.quiet_hours, null,
    "clear must send an explicit null, not {} and not an absent key");
  assert.strictEqual(ctx.S.shadowQuietHours, null, "and the gate forgets it");

  /* AN INCOMPLETE WINDOW NEVER LEAVES THE BROWSER */
  const c2 = fresh();
  c2.scheduleRender = () => {};
  c2.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  const p2 = [];
  c2.shadowPost = (u, b) => { p2.push({ u, b });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ quiet_hours: null }) }); };
  c2.S.shadowQuietEditing = true;
  c2.S.shadowQuietDraft = { start: "21:00", end: "" };
  await c2.listeners.click({ target: { dataset: { shquietsave: "1" } } });
  assert.strictEqual(p2.length, 0, "a half window must not be sent");
  assert(/both a start and an end/.test(c2.S.shadowQuietErr || ""),
    "and the row must say what is missing: " + c2.S.shadowQuietErr);
  assert.strictEqual(c2.S.shadowQuietEditing, true,
    "the editor stays open on the field still to fill");
  c2.S.shadowQuietDraft = { start: "21:00", end: "21:00" };
  await c2.listeners.click({ target: { dataset: { shquietsave: "1" } } });
  assert.strictEqual(p2.length, 0, "start == end must not be sent either");
  assert(/differ/.test(c2.S.shadowQuietErr || ""),
    "and must say why: " + c2.S.shadowQuietErr);

  /* A REFUSED WRITE MUST NOT LOOK STORED. Nothing here is optimistic, so the
     claim is that the window did not move at all. */
  const c3 = fresh();
  c3.scheduleRender = () => {}; c3.showNudge = () => {};
  c3.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  c3.shadowPost = () => Promise.resolve({ ok: false, status: 400,
    json: () => Promise.reject(new Error("no body")) });
  c3.S.shadowQuietHours = { start: "21:00", end: "08:00" };
  c3.S.shadowQuietEditing = true;
  c3.S.shadowQuietDraft = { start: "01:00", end: "02:00" };
  await c3.listeners.click({ target: { dataset: { shquietsave: "1" } } });
  assert.strictEqual(JSON.stringify(c3.S.shadowQuietHours),
    JSON.stringify({ start: "21:00", end: "08:00" }),
    "a refused write must leave the window exactly as it was");
  assert(/refused/.test(c3.S.shadowQuietErr || ""),
    "and must say so on the row: " + c3.S.shadowQuietErr);
  console.log("ok 22f9 quiet hours: three states, one route, and a refusal "
    + "that does not lie");
})().catch(e => { console.error("FAIL 22f9:", e.message); process.exit(1); });

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

  /* STOP IS ON THIS CARD; RESUME IS STILL NOT (founder, 2026-09-16).

     This block asserted that NEITHER was, from 2026-09-15: "the detail pane
     reports and asks, it is not a worker control panel", on the stated
     understanding that both still rendered on the plane. They did -- and the
     plane is shadowPlaneHtml, which SCREENS.shadowwatching renders on the
     WATCHING screen. SCREENS.shadow, the workspace, renders this card, so a
     founder looking at a running task had a RUNNING pill, "Open the chat"
     and no way to stop the worker. Rendering each state through
     SCREENS.shadow showed actions=[] for running, paused and blocked.

     So the assertion that pinned the absence is the thing that changes, and
     only for Stop: ending work the founder no longer wants is the one
     control that has to be where the work is. Resume stays off the card --
     a NEEDS YOU task is answered by its intervention form, and the plane
     still offers it -- so the second assertion below is untouched. */
  for (const [name, h] of [["running", running], ["paused", paused],
                           ["blocked", blocked]]){
    assert(has(h, "stop"), name + ": Stop must be on the card the workspace "
      + "renders -- the plane is a different screen");
  }
  assert(!has(done, "stop"),
    "done: a completed task must never be offered Stop");
  for (const [name, h] of [["running", running], ["paused", paused],
                           ["blocked", blocked], ["done", done]]){
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
  /* ── 34b. THE ROW SHOWS THE TURN THE WORKER IS ON ──────────────────────
     turns_used counts turns that FINISHED. Between Shadow's instruction and
     the worker's last word the card read "5 of 20" while turn 6 was the one
     being worked, and across a restart that fact was recorded nowhere. The
     engine now stamps `turn_open` for exactly that span. */
  const now = ctx.shadowTurnNow;
  assert.strictEqual(typeof now, "function", "shadowTurnNow must exist");
  assert.strictEqual(now({ turns_used: 5, turn_open: 6 }), 6,
    "an open turn is the one the founder is watching");
  assert.strictEqual(now({ turns_used: 5, turn_open: null }), 5,
    "a settled mission reads exactly as it always did");
  assert.strictEqual(now({ turns_used: 5 }), 5,
    "and so does a mission from before the field existed");
  assert.strictEqual(now({ turns_used: 5, turn_open: 3 }), 5,
    "a stale open turn can never DROP the count backwards");
  assert.strictEqual(now({}), 0, "an empty record is zero, not NaN");
  const inflight = card({ turns_used: 5, turn_open: 6, max_turns: 20 });
  assert(/shcard2k">turn<\/span>\s*<span class="shcard2v">6 of 20/.test(inflight),
    "the card must print the in-flight turn");
  /* THE BUDGET IS DELIBERATELY NOT MOVED: max_turns is compared against
     turns_used in the engine, and a meter disagreeing with the thing that
     ends the mission would be the worse of the two bugs. */
  assert.strictEqual(pct({ turns_used: 5, turn_open: 6, max_turns: 20 }),
    pct({ turns_used: 5, max_turns: 20 }),
    "an open turn must not move the budget meter");
  console.log("ok 34 the TURN row is the count; the meter itself is unchanged");
}

/* 35. A QUEUED CARD SAYS WHAT IT IS WAITING FOR, and names the limit.

   The pill says the state; the founder needs the CAUSE, and there is only
   one -- every slot the run limit allows is in use. Found in the live app:
   a task sat on QUEUED with a Drop button and nothing saying why, which
   reads as a task that failed to start. */
{
  const ctx = fresh();
  const card = (m, cap) => {
    ctx.S.shadowSettings = cap === undefined ? undefined
      : { tasks: { running_at_once: cap } };
    return ctx.shadowTaskCardHtml(Object.assign(
      { id: "m-q", objective: "waits", template: "fix", max_turns: 20 }, m));
  };

  const queued = card({ state: "queued" }, 2);
  assert(/waiting for/.test(queued), "the queued card states the wait");
  assert(/a free slot/.test(queued), "…in the founder's words");
  assert(/Running at once is 2/.test(queued),
    "…and names the limit that is holding it, from the settings the page "
    + "already loaded");
  assert(/starts on its own/.test(queued),
    "…and that no click is owed: promotion is automatic");

  /* the cap is not known yet: say less, never guess a number */
  const early = card({ state: "queued" }, undefined);
  assert(/waiting for/.test(early) && /a free slot/.test(early),
    "the sentence stands without the settings");
  assert(!/Running at once is/.test(early),
    "a card that has not been told the cap must not invent one");

  /* and it belongs to `queued` alone -- a running task is not waiting */
  for (const st of ["running", "paused", "blocked", "done", "brief_confirm"])
    assert(!/waiting for/.test(card({ state: st }, 2)),
      st + " is not waiting for a slot");
  console.log("ok 35 a queued card says why it is waiting");
}

/* 36. THE WATCHING SCREEN RENDERS THE TAB THE FOUNDER PRESSED.

   It passed the literal "watching", so the plane's Working and Goals tabs
   were buttons that changed nothing -- and since the task card deliberately
   does not draw Stop or Resume ("the same two buttons still render in
   shadowPlaneHtml"), there was no reachable way to STOP a running task at
   all. Measured in the live app, 2026-09-16. */
{
  const ctx = fresh();
  ctx.S.shadowWatching = [];
  ctx.S.shadowMissions = MISSIONS;

  const def = ctx.SCREENS.shadowwatching();
  assert(/data-shtab="watching"/.test(def),
    "the three tabs are still drawn");
  assert(!/data-shact="stop"/.test(def),
    "watching is still the default a page starts on");

  ctx.S.shadowTab = "working";
  const working = ctx.SCREENS.shadowwatching();
  assert(/data-shact="stop" data-shmid="m-1"/.test(working),
    "pressing Working must actually reach the rows that carry Stop");
  assert(/Waiting for a free\s+slot/.test(working),
    "…and the queued row's reason with them");
  console.log("ok 36 the watching screen honours the tab that was pressed");
}

/* ── "DELEGATE OFFERS" IS A REAL CONTROL ──────────────────────────────────
   22g1-22g6. The chips were drawn dead beside a list the page had compiled
   into it: SH_KINDS, four names in a const, with no way to keep a fifth.
   They write now, and these are the things that has to mean.

   22g1  the list is the SERVER's, and one list feeds both surfaces
   22g2  the floor is honoured, and said rather than hidden
   22g3  one click removes, with the NAME and one POST
   22g4  add is two steps, and repaints from the server's answer
   22g5  a refusal is shown on the row, in the server's own words
   22g6  a draft sitting on a removed kind cannot post a dead kind */

/* 22g1. the founder's list, not the page's constant -- and the Delegate form
   and the Settings chips read the same one, so they cannot drift. */
{
  const ctx = fresh();
  const d = JSON.parse(JSON.stringify(SET));
  d.tasks.offers = ["fix", "review", "spike"];
  d.tasks.turn_budget = { fix: 20, review: 20, spike: 7 };
  d.tasks.turn_budget_kinds = ["fix", "review", "spike"];
  ctx.S.shadowSettings = d;
  const sec = (h => h.slice(h.indexOf(">Tasks<"), h.indexOf(">Presence<")))(
    ctx.shadowSettingsHtml());
  ["fix", "review", "spike"].forEach(k => assert(
    new RegExp('class="chip"[^>]*>' + k + '<button class="cx"').test(sec),
    "a founder-set kind is missing its chip: " + k));
  assert(!/>feature</.test(sec) && !/>watch</.test(sec),
    "a kind the founder does not offer must not be stated");
  /* the chip quotes the budget the server sent for that kind */
  assert(/class="chip" title="7 turns">spike</.test(sec),
    "a minted kind's chip must state its own budget");
  /* and the Delegate form offers exactly the same three */
  const kinds = (ctx.shadowDelegatePanelHtml().match(
    /data-shnewkind="([a-z0-9-]+)"/g) || []).map(m => m.split('"')[1]);
  assert.deepStrictEqual(kinds, ["fix", "review", "spike"],
    "the Delegate form and Settings must read one list");
  /* with no offers reported, the fallback renders rather than nothing --
     the page must be usable before the first settings read lands */
  const bare = fresh();
  assert(/data-shnewkind="fix"/.test(bare.shadowDelegatePanelHtml()),
    "the Delegate form must fall back, not render empty");
  console.log("ok 22g1 the offers are the founder's, and one list feeds both");
}

/* 22g2. the floor: at one offer the x is held down and says why, rather than
   vanishing. A founder who narrowed to one kind should see the limit, not
   watch the control disappear. */
{
  const ctx = fresh();
  const d = JSON.parse(JSON.stringify(SET));
  d.tasks.offers = ["fix"];
  ctx.S.shadowSettings = d;
  const sec = (h => h.slice(h.indexOf(">Tasks<"), h.indexOf(">Presence<")))(
    ctx.shadowSettingsHtml());
  const x = (sec.match(/<button class="cx"[^>]*>/) || [""])[0];
  assert(x, "the last chip still draws its x");
  assert(/aria-disabled="true"/.test(x), "at the floor the x must be held down");
  assert(!/data-shofferdel/.test(x),
    "a held-down x must not also carry a live hook");
  assert(/at least 1 kind of work/.test(sec),
    "the floor must be explained, got: " + x);
  /* at the ceiling, "+ add" goes down the same way */
  const c = JSON.parse(JSON.stringify(SET));
  c.tasks.offers = ["fix", "feature"]; c.tasks.offers_max = 2;
  ctx.S.shadowSettings = c;
  const full = ctx.shadowSettingsHtml();
  assert(/chipadd[^>]*aria-disabled="true"/.test(full),
    "at the ceiling + add must say it cannot");
  assert(/At most 2 kinds on offer/.test(full), "…and why");
  console.log("ok 22g2 the floor and the ceiling are honoured and explained");
}

/* 22g3. one click removes: the NAME is sent, not a position, and exactly one
   POST goes out. */
(async () => {
  const ctx = fresh();
  const posts = [];
  ctx.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({}) });
  ctx.shadowPost = (url, body) => { posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ offers: ["fix", "feature", "research"],
        min: 1, max: 12,
        turn_budget: { fix: 20, feature: 30, research: 15 },
        turn_budget_kinds: ["fix", "feature", "research"] }) }); };
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  ctx.loadShadowSettings = () => {}; ctx.loadShadowHome = () => {};
  ctx.showNudge = () => {};
  await ctx.listeners.click({ target: { dataset: { shofferdel: "watch" } } });
  assert.strictEqual(posts.length, 1, "exactly one write is sent");
  assert.strictEqual(posts[0].url, "/api/shadow/settings/offers");
  assert.strictEqual(posts[0].body.remove, "watch",
    "the NAME is sent, so a re-render cannot shift what is removed");
  assert(!("add" in posts[0].body), "one verb per write");
  assert.deepStrictEqual(ctx.S.shadowSettings.tasks.offers,
    ["fix", "feature", "research"],
    "the row must repaint from the server's list");
  assert.strictEqual(ctx.S.shadowSettings.tasks.running_at_once, 5,
    "the write clobbered an unrelated setting");
  console.log("ok 22g3 one click removes by name, in one POST");
})().catch(e => { console.error("FAIL 22g3:", e.message); process.exit(1); });

/* 22g4. add is two steps -- open the namer, then submit -- and the new chip
   comes back from the SERVER, never painted optimistically. */
(async () => {
  const ctx = fresh();
  const posts = [];
  ctx.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({}) });
  ctx.shadowPost = (url, body) => { posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({
        offers: ["fix", "feature", "research", "watch", "review"],
        min: 1, max: 12,
        turn_budget: { fix: 20, feature: 30, research: 15, watch: 0,
                       review: 20 },
        turn_budget_kinds: ["fix", "feature", "research", "review"] }) }); };
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  ctx.loadShadowSettings = () => {}; ctx.loadShadowHome = () => {};
  const nudges = []; ctx.showNudge = (m) => nudges.push(m);

  /* opening the namer is NOT a write: there is no name to send yet */
  await ctx.listeners.click({ target: { dataset: { shofferopen: "1" } } });
  assert.strictEqual(posts.length, 0, "opening the box must not post");
  const open = ctx.shadowSettingsHtml();
  assert(/data-shoffername="1"/.test(open), "the namer must render");
  assert(!/class="chipadd"/.test(open),
    "the pill and the box must not both offer to add");

  /* typing is stored without a re-render, like every other field here */
  ctx.listeners.input({ target: { dataset: { shoffername: "1" },
                                  value: "review" } });
  assert.strictEqual(ctx.S.shadowOfferDraft, "review");

  await ctx.listeners.click({ target: { dataset: { shofferadd: "1" } } });
  assert.strictEqual(posts.length, 1, "exactly one write is sent");
  assert.strictEqual(posts[0].body.add, "review");
  assert(ctx.S.shadowSettings.tasks.offers.indexOf("review") > -1,
    "the new kind must arrive from the server's answer");
  assert.strictEqual(ctx.S.shadowSettings.tasks.turn_budget.review, 20,
    "…with the budget the server minted it at, so the chip can state it");
  assert(!ctx.S.shadowOfferAdding, "the namer must close on success");
  assert(nudges.length === 1, "the founder is told once");
  console.log("ok 22g4 add is two steps and repaints from the server");
})().catch(e => { console.error("FAIL 22g4:", e.message); process.exit(1); });

/* 22g5. a refusal is SHOWN, in the server's own words. "at least 1 delegate
   offer" tells the founder what happened; "did not stick" does not. */
(async () => {
  const ctx = fresh();
  ctx.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({}) });
  ctx.shadowPost = () => Promise.resolve({ ok: false, status: 400,
    json: () => Promise.resolve({ detail: "'Code Review!' is not a usable "
      + "kind name" }) });
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  ctx.loadShadowSettings = () => {}; ctx.loadShadowHome = () => {};
  ctx.showNudge = () => {};
  ctx.S.shadowOfferAdding = true; ctx.S.shadowOfferDraft = "Code Review!";
  await ctx.listeners.click({ target: { dataset: { shofferadd: "1" } } });
  assert(/not a usable kind name/.test(ctx.S.shadowOfferErr || ""),
    "the server's reason must be kept, got: " + ctx.S.shadowOfferErr);
  const sec = ctx.shadowSettingsHtml();
  assert(/not a usable kind name/.test(sec),
    "the reason must reach the row, not only a nudge");
  assert(ctx.S.shadowOfferAdding,
    "a refused add must keep the box open so the name can be fixed");
  assert.deepStrictEqual(ctx.S.shadowSettings.tasks.offers, SET.tasks.offers,
    "a refused write must not move the list");
  /* an empty name is refused without a round-trip */
  const c2 = fresh();
  let sent = 0;
  c2.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({}) });
  c2.shadowPost = () => { sent++; return Promise.resolve({ ok: true,
    status: 200, json: () => Promise.resolve({}) }); };
  c2.S.shadowSettings = JSON.parse(JSON.stringify(SET));
  c2.S.shadowOfferAdding = true; c2.S.shadowOfferDraft = "   ";
  await c2.listeners.click({ target: { dataset: { shofferadd: "1" } } });
  assert.strictEqual(sent, 0, "an empty name must not reach the server");
  assert(/Name the kind of work first/.test(c2.S.shadowOfferErr || ""));
  console.log("ok 22g5 a refusal is shown on the row, in the server's words");
})().catch(e => { console.error("FAIL 22g5:", e.message); process.exit(1); });

/* 22g6. a draft sitting on a kind the founder just removed must not post a
   dead kind -- the create path and the form must agree on the coercion. */
{
  const ctx = fresh();
  const d = JSON.parse(JSON.stringify(SET));
  d.tasks.offers = ["research", "feature"];
  ctx.S.shadowSettings = d;
  ctx.S.shadowNew = { objective: "x", done: "", kind: "watch" };
  const panel = ctx.shadowDelegatePanelHtml();
  assert(!/data-shnewkind="watch"/.test(panel),
    "a retired kind must not be offered");
  assert.strictEqual(ctx.shadowNewDraft().kind, "research",
    "the draft must fall back to the first kind actually on offer");
  assert(/class="shkind on" type="button"\s+data-shnewkind="research"/
    .test(panel), "…and the form must show that as the selected one");
  console.log("ok 22g6 a draft cannot sit on a kind that is no longer offered");
}

/* ── 37. STOP IS ON THE SCREEN THE FOUNDER IS ON ───────────────────────────
   THE REPORT (founder, 2026-09-16): "a RUNNING mission shows only RUNNING and
   Open the chat -- no Stop".

   IT WAS TRUE, AND SOURCE-READING WOULD HAVE MISSED IT. The Stop button
   existed the whole time, in shadowPlaneHtml, on the same data-shact hook --
   but shadowPlaneHtml is rendered by SCREENS.shadowwatching (the Watching
   screen, Working tab). SCREENS.shadow -- the workspace -- renders
   shadowTaskListHtml and shadowTaskCardHtml, and the card had had Stop and
   Resume removed on the stated understanding that the plane still drew them.
   It did; on another screen.

   Rendering one mission per state through SCREENS.shadow and counting
   data-shact hooks gave, before the fix:

       running  pill RUNNING    actions []
       paused   pill NEEDS YOU  actions []
       blocked  pill NEEDS YOU  actions []
       queued   pill QUEUED     actions [drop]

   So these assert the RENDERED SCREEN, not the card helper in isolation:
   calling shadowTaskCardHtml directly would have passed throughout the bug.
*/
const STOPPABLE = { id: "m-stop", objective: "a long job", turns_used: 3,
  max_turns: 20, target_session: "sid-stop" };
function screenFor(over){
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [Object.assign({}, STOPPABLE, over)];
  ctx.S.shadowWatching = [];
  ctx.S.shadowTaskSel = "m-stop";
  return ctx.SCREENS.shadow();
}
const stopBtn = /data-shact="stop"\s+data-shmid="m-stop"|data-shact="stop"[^>]*m-stop/;

/* 23a. the state the report was filed about */
{
  const h = screenFor({ state: "running" });
  assert(stopBtn.test(h), "a RUNNING task must offer Stop on the workspace");
  assert(/>Stop</.test(h), "…and it must be labelled Stop");
  assert(/data-shtakeover=/.test(h), "Open the chat is untouched");
  console.log("ok 37a RUNNING offers Stop");
}

/* 23b + 23c. the two states that read NEEDS YOU. Existing semantics say Stop
   is available in both (shadowPlaneHtml has always drawn it for
   running/paused/blocked, and TRANSITIONS allows stopped from each). */
{
  const paused = screenFor({ state: "paused", pause_reason: "founder_confirm" });
  assert(stopBtn.test(paused), "a NEEDS YOU (paused) task must offer Stop");
  const blocked = screenFor({ state: "blocked", block_reason: "needs_founder" });
  assert(stopBtn.test(blocked), "a NEEDS YOU (blocked) task must offer Stop");
  console.log("ok 37b/c paused and blocked offer Stop");
}

/* 23d. QUEUED keeps Drop and does NOT gain Stop: nothing is running to stop,
   and Drop is the existing exit for a task still waiting for a slot. */
{
  const h = screenFor({ state: "queued" });
  assert(/data-shact="drop"/.test(h), "a QUEUED task keeps Drop");
  assert(!/data-shact="stop"/.test(h), "…and is not offered Stop");
  console.log("ok 37d QUEUED keeps Drop, not Stop");
}

/* 23e. DONE IS NEVER OFFERED A STOP. The backend refuses it -- founder_force_stop
   returns a terminal mission untouched -- and the UI must not ask a question
   whose answer is "no". Retry is the existing offer for failed/stopped. */
{
  const done = screenFor({ state: "done" });
  assert(!/data-shact="stop"/.test(done),
    "a completed task must never be offered Stop");
  assert(!/data-shact="retry"/.test(done), "nor Retry -- it succeeded");
  for (const st of ["failed", "stopped"]){
    const h = screenFor({ state: st });
    assert(!/data-shact="stop"/.test(h), st + " is already ended");
    assert(/data-shact="retry"/.test(h), st + " keeps Retry");
  }
  console.log("ok 37e terminal states are not offered Stop");
}

/* 23f. the click sends the EXISTING action to the EXISTING endpoint. No second
   force-stop route: `stop` is what founder_force_stop is wired behind. */
(async () => {
  const ctx = fresh();
  const posts = [];
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [Object.assign({}, STOPPABLE, { state: "running" })];
  ctx.S.shadowTaskSel = "m-stop";
  ctx.fetch = () => Promise.resolve({ ok: true });
  ctx.shadowPost = (url, body) => { posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ id: "m-stop", state: "stopped",
                                    ended_by: "founder" }) }); };
  ctx.loadShadowHome = () => {};
  assert(typeof ctx.listeners.click === "function", "the click handler is wired");
  await ctx.listeners.click({ target: { dataset:
    { shact: "stop", shmid: "m-stop" } } });
  assert.strictEqual(posts.length, 1, "exactly one action is sent");
  assert.strictEqual(posts[0].url, "/api/shadow/missions/m-stop/act",
    "the existing mission-action endpoint");
  assert.strictEqual(posts[0].body.action, "stop",
    "the existing action -- never a second force-stop route");
  console.log("ok 37f clicking Stop sends the existing stop action");
})().catch(e => { console.error("FAIL 37f:", e.message); process.exit(1); });

/* 23g. THE ASSERTION THAT WOULD HAVE CAUGHT IT. The control must be reachable
   from the workspace itself -- the bug was that it lived only on another
   screen, so every card-level test passed while the founder had no button. */
{
  const h = screenFor({ state: "running" });
  const card = (() => {
    const ctx = fresh();
    ctx.S.shadowHomeDark = false;
    return ctx.shadowTaskCardHtml(
      Object.assign({}, STOPPABLE, { state: "running" }));
  })();
  assert(/data-shact="stop"/.test(card), "the card draws it…");
  assert(/data-shact="stop"/.test(h),
    "…and the SCREEN that renders the card must show it -- asserting the " +
    "helper alone is what let this ship");
  console.log("ok 37g Stop is reachable from the workspace screen itself");
}

console.log("test_shadow_home.js: all green");
