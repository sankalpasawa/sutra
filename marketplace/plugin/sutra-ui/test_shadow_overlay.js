#!/usr/bin/env node
/*
 * test_shadow_overlay.js -- PLAN-100 S65-S79: the overlay integration suite.
 * Real module under vm, minimal stubs, assertions on real behavior.
 * Run: node test_shadow_overlay.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const html = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
assert(/15-shadow-overlay\.js/.test(html), "panel.html loads the overlay module");

const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");

/* S76 energy: the module must not poll -- no setInterval at all */
assert(!/setInterval/.test(src), "overlay must be event-driven, never poll");

function fresh(opts){
  opts = opts || {};
  const appended = [];
  const ctx = {
    console, Date,
    setTimeout: (fn, ms) => ({ fn, ms }), clearTimeout(){},
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    S: {}, listeners: {},
    fetch: opts.fetch,
    /* the panel's own localStorage helpers (01-state.js), when a test wants
       the pill counter to outlive the context the way it outlives a reload.
       ABSENT BY DEFAULT on purpose: every other block here runs without them
       and must still work, because a partial shell has no lsGet either. */
    lsGet: opts.lsGet, lsSet: opts.lsSet,
    document: {
      createElement(tag){
        const el = { tagName: tag, className: "", textContent: "",
                     dataset: {}, _attrs: {},
                     setAttribute(k, v){ el._attrs[k] = v; },
                     remove(){} };
        return el;
      },
      body: { appended, appendChild(el){ appended.push(el); } },
      querySelector(){ return null; },
      addEventListener(type, fn){ ctx.listeners[type] = fn; },
    },
    _appended: appended,
  };
  ctx.__SHADOW_NO_AUTOBOOT = true;   /* tests drive boot explicitly */
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  return ctx;
}

/* the 2.224.1 lesson: served code that nobody calls. Pin the call sites. */
assert(/^\s*try \{ bootShadowOverlay\(\); \}/m.test(src),
  "the module must CALL bootShadowOverlay on load");
assert(/addEventListener\("click", toggleShadowCard\)/.test(src),
  "the dot must open the card on click");
assert(/function renderShadowCard/.test(src)
       && /appendChild\(wrap\)/.test(src),
  "the card must MOUNT, not just return html");
const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");
const dotRule = css.slice(css.indexOf(".shdot{"), css.indexOf("}", css.indexOf(".shdot{")));
assert(/right:\s*\d/.test(dotRule) && /bottom:\s*\d/.test(dotRule),
  "the dot needs default coordinates or it renders nowhere (2.224.3 bug)");

/* 1. S65: snap picks the nearest corner */
{
  const ctx = fresh();
  const J = (o) => JSON.stringify(o);   /* vm objects have foreign protos */
  assert.strictEqual(J(ctx.snapCorner(10, 10, 1000, 800)),
    J({ left: 16, right: null, top: 16, bottom: null }));
  assert.strictEqual(J(ctx.snapCorner(990, 790, 1000, 800)),
    J({ left: null, right: 16, top: null, bottom: 16 }));
  console.log("ok 1 snap");
}

/* 2. S67: N unsolicited pills an hour, nudges exempt -- where N is the
   FOUNDER'S, off presence.json, and no longer a constant in this module.

   THE SEED IS NOW PART OF THE SETUP, deliberately. These three assertions
   used to pass with no state at all because the rate was compiled in; the
   rate arrives on the settings GET now, so a test that asserts the old
   numbers without seeding them would be asserting a fallback -- and the whole
   point of this change is that there is no fallback. */
{
  const ctx = fresh();
  const now = Date.now();
  ctx.S.shadowNudgeRate = 3;
  let [ok] = ctx.pillAllowed([], now);            assert(ok);
  [ok] = ctx.pillAllowed([now-1, now-2, now-3], now); assert(!ok);
  [ok] = ctx.pillAllowed([now - 3700e3, now - 3800e3, now - 3900e3], now);
  assert(ok, "stale history prunes");
  console.log("ok 2 pill rate");
}

/* 2b. THE SETTING IS THE LIMIT. The founder's number is what bites, at both
   ends of the band and at the value that means silence. */
{
  const ctx = fresh();
  const now = Date.now();

  /* one an hour: the first is allowed, the second is not */
  ctx.S.shadowNudgeRate = 1;
  assert(ctx.pillAllowed([], now)[0], "1/hour must allow the first");
  assert(!ctx.pillAllowed([now - 1000], now)[0],
    "1/hour must refuse the second inside the hour");
  assert(ctx.pillAllowed([now - 3700e3], now)[0],
    "1/hour must allow again once the hour has rolled past");

  /* zero: never unasked, no matter how empty the history is */
  ctx.S.shadowNudgeRate = 0;
  assert(!ctx.pillAllowed([], now)[0],
    "0 must silence completely -- an empty history is not a licence");
  assert.strictEqual(ctx.showPill("psst"), null,
    "0 must silence showPill itself, not merely pillAllowed");

  /* the same number still exempts a nudge: a limit on what Shadow says
     unasked was never a limit on an answer it was asked for */
  assert(ctx.showPill("asked for", { nudge: true }),
    "an exempt nudge must still show at a rate of 0");

  /* NO RATE, NO PILL. This is the case the deleted constant used to hide:
     nothing has arrived from the server, so there is no number to enforce and
     the honest answer is silence rather than a 3 nobody set. */
  const cold = fresh();
  assert(!cold.pillAllowed([], now)[0],
    "an unknown rate must suppress, never fall back to a compiled-in number");
  assert.strictEqual(cold.showPill("hello"), null,
    "showPill must stay silent until a rate has arrived");
  assert.strictEqual(typeof cold.SH_PILLS_PER_HOUR, "undefined",
    "SH_PILLS_PER_HOUR must be GONE -- a fallback is how the setting reverts");

  /* seeding is what turns it on, and only a real number does it */
  cold.applyShadowPresence({ presence: { nudges_per_hour: 2 } });
  assert.strictEqual(cold.S.shadowNudgeRate, 2, "the payload seeds the rate");
  assert(cold.pillAllowed([], now)[0], "and the seeded rate enforces");
  cold.applyShadowPresence({ presence: {} });
  assert.strictEqual(cold.S.shadowNudgeRate, 2,
    "a payload without the field must leave the last known rate standing");
  cold.applyShadowPresence(null);
  assert.strictEqual(cold.S.shadowNudgeRate, 2,
    "a failed settings read must not clear the rate");
  console.log("ok 2b the founder's rate is the limit, 0 included");
}

/* 2c. THE ROLLING HOUR SURVIVES THE RELOAD. The counter lives in
   localStorage, so a reload cannot refund a budget the founder capped. */
{
  const store = {};
  const ls = {
    lsGet: (k, fb) => (k in store ? store[k] : fb),
    lsSet: (k, v) => { store[k] = JSON.parse(JSON.stringify(v)); },
  };
  const first = fresh(ls);
  first.S.shadowNudgeRate = 1;
  assert(first.showPill("the one nudge you allowed"), "the first is allowed");
  assert.strictEqual(first.showPill("the second"), null, "the second is not");
  assert(Array.isArray(store["sutra.shadow.pills"])
         && store["sutra.shadow.pills"].length === 1,
    "the pill must be recorded in the browser, not only in memory");

  /* the reload: a brand-new context over the SAME localStorage */
  const after = fresh(ls);
  after.S.shadowNudgeRate = 1;
  assert.strictEqual(after.showPill("after the reload"), null,
    "a reload refunded the hour's budget -- the maximum is not a maximum");

  /* and an hour later the budget is genuinely back */
  store["sutra.shadow.pills"] = [Date.now() - 3700e3];
  const later = fresh(ls);
  later.S.shadowNudgeRate = 1;
  assert(later.showPill("an hour later"), "a stale hour must not hold the cap");

  /* junk in the store costs the hour's memory, never the enforcement */
  store["sutra.shadow.pills"] = "not a list";
  const junk = fresh(ls);
  junk.S.shadowNudgeRate = 0;
  assert.strictEqual(junk.showPill("x"), null,
    "a corrupt counter must not become a licence to speak");
  console.log("ok 2c the hour survives a reload");
}

/* 3. S71/S72: chips validate verb+object, cap 3, junk falls to Clarify */
{
  const ctx = fresh();
  assert.strictEqual(
    JSON.stringify(ctx.validChips(["Review the brief", "Stop mission",
                                   "Open thread", "Retry now"])),
    JSON.stringify(["Review the brief", "Stop mission", "Open thread"]),
    "max 3");
  assert.strictEqual(JSON.stringify(ctx.validChips(["ok", "", "1234 do it"])),
    "[]", "junk chips rejected");
  const card = (ctx.S.shadowThread = [], ctx.S.shadowChips = ["??", "!"],
                ctx.shadowCardHtml());
  assert(/Clarify/.test(card), "junk chips fall back to Clarify");
  console.log("ok 3 chips");
}

/* 4. S75: own turns are filtered before they can loop */
{
  const ctx = fresh();
  assert(ctx.isOwnTurn("[Shadow \u00b7 mission m-1] do the thing"));
  assert(!ctx.isOwnTurn("founder text about [Shadow] in passing"));
  console.log("ok 4 own-turn filter");
}

/* 5. S78: dot states incl. down */
{
  const ctx = fresh();
  assert.strictEqual(ctx.dotState(null).cls, "shdot-down");
  assert.strictEqual(ctx.dotState({ watching: true }).cls, "shdot-live");
  assert.strictEqual(ctx.dotState({ watching: false }).cls, "shdot-idle");
  console.log("ok 5 dot states");
}

/* 6. OFF-STATE: status 403 -> NOTHING mounts (the P5 off-invariant) */
{
  let fetched = [];
  const ctx = fresh({ fetch: (url) => { fetched.push(url);
    return Promise.resolve({ ok: false }); } });
  ctx.bootShadowOverlay();
  return_after_microtasks(() => {
    assert.strictEqual(ctx._appended.length, 0,
      "403 status must mount zero shadow DOM");
    console.log("ok 6 dark = no mount");
    part2();
  });
}

function return_after_microtasks(fn){ setTimeout(fn, 10); }

function part2(){
  /* 7. flag on -> dot mounts with a11y attributes (S65/S66) */
  const ctx = fresh({ fetch: () => Promise.resolve({
    ok: true, json: () => Promise.resolve({ watching: true }) }) });
  ctx.bootShadowOverlay();
  return_after_microtasks(() => {
    assert.strictEqual(ctx._appended.length, 1, "dot mounts on 200");
    const dot = ctx._appended[0];
    assert(/shdot-live/.test(dot.className));
    assert.strictEqual(dot._attrs["role"], "button");
    assert(dot._attrs["aria-label"], "a11y label present");
    console.log("ok 7 mount + a11y");
    part3();
  });
}

function part3(){
  /* 8. S77 keyboard toggle + Esc; S73 quiet suppresses pills */
  const ctx = fresh();
  ctx.S.shadowCardOpen = false;
  assert(ctx.shadowKeyHandler({ metaKey: true, shiftKey: true, key: "S" }));
  assert.strictEqual(ctx.S.shadowCardOpen, true, "cmd-shift-S opens");
  assert(ctx.shadowKeyHandler({ key: "Escape" }));
  assert.strictEqual(ctx.S.shadowCardOpen, false, "Esc closes");
  ctx.S.shadowQuiet = true;
  ctx.S.shadowNudgeRate = 3;   /* the founder's rate, as the settings GET seeds it */
  assert.strictEqual(ctx.showPill("psst"), null, "quiet switch silences");
  ctx.S.shadowQuiet = false;
  const el = ctx.showPill("hello");
  assert(el && el.className === "shpill");
  console.log("ok 8 keyboard + quiet + pill");

  /* 8b. dot click toggles + MOUNTS the card; Esc unmounts */
  {
    const c2 = fresh();
    const removed = [];
    let mounted = null;
    c2.document.querySelector = (sel) =>
      sel === "[data-shcardwrap]" ? mounted : null;
    const mkEl = c2.document.createElement;
    c2.document.createElement = (tag) => {
      const el = mkEl(tag);
      el.innerHTML = "";
      el.addEventListener = () => {};
      el.remove = () => { removed.push(el); if (mounted === el) mounted = null; };
      return el;
    };
    const baseAppend = c2.document.body.appendChild.bind(c2.document.body);
    c2.document.body.appendChild = (el) => {
      if (el.dataset && el.dataset.shcardwrap) mounted = el;
      baseAppend(el);
    };
    c2.S.shadowThread = [];
    c2.toggleShadowCard();
    assert(mounted, "click path must mount the card");
    assert(/shcard/.test(mounted.innerHTML), "mounted card carries the shell");
    c2.shadowKeyHandler({ key: "Escape" });
    assert(!mounted, "Esc must unmount");
    console.log("ok 8b card mounts");
  }

  /* 9. ONE thread: the card renders S.shadowThread (shared with the home) */
  ctx.S.shadowThread = [{ who: "founder", text: "hi" },
                        { who: "shadow", text: "watching 4 sessions" }];
  const cardHtml = ctx.shadowCardHtml();
  assert(/watching 4 sessions/.test(cardHtml), "card renders the ONE thread");
  console.log("ok 9 one thread");

  /* 10. S70: mission card in-thread; Start gated by state chip */
  assert(/data-shstart="m-1"/.test(
    ctx.missionCardHtml({ id: "m-1", objective: "x", state: "brief_confirm" })),
    "confirmed brief can Start");
  assert(!/data-shstart/.test(
    ctx.missionCardHtml({ id: "m-1", objective: "x", state: "running" })),
    "a running mission has no Start");
  assert(/shstate-paused/.test(
    ctx.missionCardHtml({ id: "m-2", objective: "y", state: "paused" })),
    "state chip carries the state");
  console.log("ok 10 mission card");
  /* 11. reply blocks land: mission renders in-thread; finishers pinned */
{
  const c3 = fresh();
  c3.S.shadowThread = [{ who: "shadow",
    mission: { id: "m-9", objective: "x", state: "brief_confirm" } }];
  assert(/data-shstart="m-9"/.test(c3.shadowCardHtml()),
    "a mission entry renders as a card in the thread");
  assert(/shadowMissionAct/.test(src), "Start must act");
  assert(/active_missions/.test(src), "badge reads the status count");
  assert(/data-shquiet/.test(src) && /data-shhidesess/.test(src),
    "quiet + hide controls exist (R12)");
  assert(/tabindex", "-1"/.test(src), "dot is click-only (R3)");
  console.log("ok 11 reply blocks + finishers");
}
/* 12. the CSRF lesson: every mutating fetch carries the panel token */
{
  const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
  for (const [nm, code] of [["overlay", src], ["home", home]]){
    const posts = code.split("method: \"POST\"").length - 1;
    const tokened = code.split("X-Sutra-Panel").length - 1;
    assert(posts > 0 && tokened >= posts,
      nm + ": every POST must carry X-Sutra-Panel (" + tokened + "/" + posts + ")");
  }
  console.log("ok 12 panel token on every POST");
}

/* gap-closure: the alert pill wins the dot face; clears when alerts drop */
{
  const ctx = fresh();
  const dot = { className: "", textContent: "", setAttribute(){} };
  ctx.applyDotState(dot, { watching: true, active_missions: 2, alerts: 3 });
  assert(/shdot-alert/.test(dot.className), "alert class applied");
  /* mock v5: the S-mark is ALWAYS the face; the count rides a badge */
  assert(/S/.test(dot.textContent), "face keeps the S-mark");
  assert(/3/.test(dot.textContent), "alert count present as badge");
  ctx.applyDotState(dot, { watching: true, active_missions: 2, alerts: 0 });
  assert(!/shdot-alert/.test(dot.className), "alert class cleared");
  assert(/S/.test(dot.textContent) && /2/.test(dot.textContent),
    "badge falls back to mission count, S stays");
  console.log("ok 13 alert pill (S-mark + badge)");
}

/* the deep-link router: every sutra:// link lands somewhere real */
{
  const ctx = fresh();
  const calls = [];
  ctx.goDest = (d) => calls.push("dest:" + d);
  ctx.openScreen = (sc) => calls.push("screen:" + sc);
  ctx.render = () => calls.push("render");
  assert.strictEqual(
    ctx.shadowRouteDeepLink("sutra://shadow/mission/m-abc123"), true);
  assert(calls.includes("dest:focus") && calls.includes("screen:shadow"),
    "mission link lands on Focus > Shadow");
  assert.strictEqual(ctx.S.shadowTab, "working", "working tab selected");
  assert.strictEqual(ctx.S.shadowFocusMission, "m-abc123", "mission focused");
  calls.length = 0;
  assert.strictEqual(ctx.shadowRouteDeepLink("sutra://shadow/m-short99"), true,
    "short legacy form routes too");
  assert.strictEqual(ctx.S.shadowFocusMission, "m-short99");
  calls.length = 0;
  ctx.pushPane = () => {};
  ctx.shadowRouteDeepLink("sutra://session/sess-77");
  assert(calls.includes("dest:chats"), "session link lands on Chats");
  console.log("ok 14 deep-link router");
}

/* the founder's wrong-chat bug: a session link stored a hint nobody read, so
   Chats kept whichever pane was already open -- the PREVIOUS delegated task's
   chat. The link must open the session it names. */
{
  const ctx = fresh();
  const opened = [], read = [], loaded = [];
  ctx.goDest = () => {}; ctx.render = () => {};
  ctx.pushPane = (id) => opened.push(id);
  ctx.markRead = (id) => read.push(id);
  ctx.ensureTranscript = (row) => loaded.push(row && row.id);
  ctx.S.sessions = [{ id: "8811d058", title: "Shadow Task \u2014 Fibonacci" },
                    { id: "2d66f533", title: "Shadow Task \u2014 22/7" }];
  ctx.S.openPanes = ["2d66f533"];
  assert.strictEqual(ctx.shadowRouteDeepLink("sutra://session/8811d058"), true);
  assert.deepStrictEqual(opened, ["8811d058"],
    "the link opens the session it names, not the pane already on screen");
  assert.deepStrictEqual(read, ["8811d058"], "opening marks it read");
  assert.deepStrictEqual(loaded, ["8811d058"],
    "the transcript is read, like the rail's own open");
  assert.strictEqual(ctx.S.pendingSessionHint, undefined,
    "the dead hint is gone");
  console.log("ok 14b session link opens that session");
}

/* a chat published seconds ago has no row yet: load the list, THEN open */
{
  const ctx = fresh();
  const opened = [];
  let loads = 0;
  ctx.goDest = () => {}; ctx.render = () => {};
  ctx.pushPane = (id) => opened.push(id);
  ctx.S.sessions = [{ id: "2d66f533" }];
  ctx.loadSessions = () => { loads++;
    ctx.S.sessions.push({ id: "fresh-sid" });
    return Promise.resolve(); };
  ctx.shadowRouteDeepLink("sutra://session/fresh-sid");
  assert.strictEqual(opened.length, 0, "an unknown session is not opened blind");
  /* NOT `return`: the module wrapper would swallow every test below it.
     setTimeout(0) drains the whole microtask chain (loadSessions is awaited
     through two adoptions), where a fixed number of .then hops does not. */
  setTimeout(() => {
    assert.strictEqual(loads, 1, "exactly one list refresh");
    assert.deepStrictEqual(opened, ["fresh-sid"],
      "the just-published chat opens once its row exists");
    console.log("ok 14c unknown session loads then opens");
  }, 0);
}

/* v10: the active tab rides the turn as scope_id */
{
  const ctx = fresh();
  const posts = [];
  ctx.shadowPost = (path, body) => { posts.push({ path, body });
    return Promise.resolve({ ok: true, json: async () => ({ reply: "ok" }) }); };
  ctx.S.shadowChat = "sess-paisa";
  ctx.S.shadowBusy = false;
  ctx.fetch = () => Promise.resolve({ ok: true, json: async () => ({}) });
  ctx.sendToShadow("do the thing");
  assert(posts.length >= 1, "the turn posted (guards clear)");
  assert.strictEqual(posts[0].path, "/api/shadow/chat");
  assert.strictEqual(posts[0].body.scope_id, "sess-paisa",
    "the open tab scopes the turn");
  posts.length = 0;
  ctx.S.shadowBusy = false;
  ctx.S.shadowChat = "global";
  ctx.sendToShadow("general question");
  assert.strictEqual(posts[0].body.scope_id, undefined,
    "the new tab sends no scope");
  console.log("ok 15 scope rides the turn");
}
/* start_now/retry answer BEFORE the mission moves, so one immediate reload
   reads READY and the row lies until something else loads. A bounded ladder
   of re-reads follows, on those two actions only, each skipped once it has
   moved.

   THE FIRST VALUE IS PART OF THE BEHAVIOUR, which is why it is asserted and
   not just counted: the chat is published at ~394ms (measured on the live
   server), so a first step of 1000ms meant the row lied for 713ms about a
   chat that already existed.

   THE REST IS ASSERTED AS A SHAPE, not as a list (2026-09-16). This block
   pinned the literal `[250, 750, 2000, 5000]`, and the product ladder is now
   geometric out to 90s (SH_START_BACKOFF, 15-shadow-overlay.js) because the
   old tail gave up long before the slowest measured start finished
   provisioning. Re-pinning sixteen literals would buy one more release of
   accuracy and then go stale exactly as the four did; the claims that
   actually matter -- starts soon, only climbs, reaches the slow tail, and
   every step is free once the row has landed -- survive a re-tune. The
   constant is script-scoped inside the vm and cannot be read from here, so
   the ladder is measured through the timers it schedules.

   WHAT "MOVED" MEANS ALSO CHANGED. The guard waits on the state AND on
   target_chat now, so a fixture that only flips state keeps the watcher
   polling -- correctly, because the founder is waiting to see the chat. The
   fixtures below land both. */
{
  const ctx = fresh();
  const timers = [];
  ctx.setTimeout = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
  ctx.fetch = () => Promise.resolve({ ok: true, json: async () => ({}) });
  let homeLoads = 0;
  ctx.loadShadowHome = () => { homeLoads++; };
  ctx.shadowPost = () => Promise.resolve({ ok: true,
    json: async () => ({ accepted: true, mission_id: "m-fib" }) });
  ctx.S.shadowMissions = [{ id: "m-fib", state: "brief_confirm" }];

  ctx.shadowMissionAct("m-fib", "start_now").then(() => {
    assert.strictEqual(homeLoads, 1, "the immediate reload still happens");
    const ms = timers.map(t => t.ms);
    assert(ms.length > 1, "a ladder, not a single re-read");
    assert.strictEqual(ms[0], 250,
      "the first step still beats the ~394ms chat publish");
    assert.deepStrictEqual(ms, ms.slice().sort((a, b) => a - b),
      "the ladder only ever climbs");
    assert(ms[ms.length - 1] >= 60000,
      "and it reaches the slow tail a real provisioning start needs");
    timers[0].fn();
    assert.strictEqual(homeLoads, 2, "still brief_confirm -> re-read");
    /* the mission moved -- state AND chat, which is what the guard waits on.
       EVERY remaining timer must cost nothing, not merely the next three. */
    ctx.S.shadowMissions = [{ id: "m-fib", state: "running",
                              target_chat: "c-fib" }];
    timers.slice(1).forEach(t => t.fn());
    assert.strictEqual(homeLoads, 2, "no re-read once the mission has moved");

    /* every OTHER action is untouched */
    timers.length = 0;
    return ctx.shadowMissionAct("m-fib", "stop");
  }).then(() => {
    assert.strictEqual(timers.length, 0,
      "stop/resume/drop schedule nothing");
    console.log("ok 16 start/retry re-read until the mission moves");
  });
}

/* retry starts a CLONE: the watched id is the one the server named */
{
  const ctx = fresh();
  const timers = [];
  ctx.setTimeout = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
  ctx.fetch = () => Promise.resolve({ ok: true, json: async () => ({}) });
  let homeLoads = 0;
  ctx.loadShadowHome = () => { homeLoads++; };
  ctx.shadowPost = () => Promise.resolve({ ok: true,
    json: async () => ({ accepted: true, mission_id: "m-clone" }) });
  /* the ORIGINAL is terminal and will never move; the clone has no row yet */
  ctx.S.shadowMissions = [{ id: "m-old", state: "failed" }];
  ctx.shadowMissionAct("m-old", "retry").then(() => {
    assert(timers.length > 1, "retry re-reads too");
    homeLoads = 0;
    timers[0].fn();
    assert.strictEqual(homeLoads, 1,
      "a clone with no row yet is exactly what we are waiting for");
    /* m-old is `failed` and would end the watch immediately if the watcher
       were reading it -- so a silent remaining ladder proves the id watched
       is the clone's, which is the whole claim of this block. */
    ctx.S.shadowMissions.push({ id: "m-clone", state: "running",
                                target_chat: "c-clone" });
    timers.slice(1).forEach(t => t.fn());
    assert.strictEqual(homeLoads, 1, "the CLONE's state ends it, not m-old's");
    console.log("ok 17 retry watches the clone the server named");
  });
}

/* A REFUSAL THAT CAME WITH A SENTENCE SAYS THE SENTENCE (run-limit slice).

   Resume at the run limit answers 409 with copy written for the founder --
   the two numbers and both ways out. "That did not stick (409) -- try again"
   would send them back to the same button against the same limit. */
{
  const bare = { ok: false, status: 409,
    json: async () => ({ detail: "Shadow is already running 2 of 2 tasks. "
      + "Stop one, or raise Running at once." }) };
  const nested = { ok: false, status: 409,
    json: async () => ({ detail: { at_capacity: true, running_now: 2,
      running_at_once: 2,
      detail: "Shadow is already running 2 of 2 tasks. Stop one, or raise "
        + "Running at once." } }) };
  /* a proxy error, an html page, a body that will not parse */
  const opaque = { ok: false, status: 500,
    json: async () => { throw new Error("not json"); } };

  const run = (reply) => {
    const ctx = fresh();
    const said = [];
    ctx.showNudge = (t) => said.push(t);
    ctx.loadShadowHome = () => {};
    /* shadowMissionAct's own first line is a `typeof fetch` guard */
    ctx.fetch = () => Promise.resolve({ ok: true, json: async () => ({}) });
    ctx.shadowPost = () => Promise.resolve(reply);
    ctx.S.shadowMissions = [{ id: "m-cap", state: "paused" }];
    return ctx.shadowMissionAct("m-cap", "resume").then(() => said);
  };

  Promise.all([run(bare), run(nested), run(opaque)]).then(([b, n, o]) => {
    for (const [name, said] of [["a bare string detail", b],
                                ["an object detail", n]]){
      assert.strictEqual(said.length, 1, name + ": exactly one nudge");
      assert(/already running 2 of 2/.test(said[0]),
        name + ": the server's own sentence reaches the founder, not "
        + "a status code (" + said[0] + ")");
      assert(/Running at once/.test(said[0]),
        name + ": the refusal must name the way out");
    }
    assert.strictEqual(o.length, 1, "an unreadable refusal still nudges");
    assert(/did not stick \(500\)/.test(o[0]),
      "with nothing to quote, the status line that shipped is the fallback");
    console.log("ok 18 a refusal with a sentence says the sentence");
  });
}

/* 19. "CORNER CARD ON EVERY SCREEN" -- the durable Presence setting.

   The claim is not "a flag gates the mount"; it is that the founder's SAVED
   answer decides, and decides BEFORE the card could appear. So every case
   below boots a context that knows nothing except what the server hands it,
   which is exactly the state a reload or a relaunched app starts from.

   A FRESH vm CONTEXT IS THE RESTART. Nothing carries across it -- no S, no
   module state, no closure -- so a context that mounts nothing when the
   server says false has proven the only thing the client can prove about
   persistence. That the server still SAYS false after a restart is a
   different claim, proven where it lives: test_shadow_presence.py reads the
   store back in a separate interpreter. */
{
  /* the two GETs boot now awaits, answered per URL */
  const serve = (presence, statusOk) => (url) => {
    if (String(url).indexOf("/api/shadow/settings") === 0)
      return Promise.resolve({ ok: true,
        json: () => Promise.resolve(presence === undefined
          ? {} : { presence: { corner_card: presence } }) });
    return Promise.resolve({ ok: statusOk !== false,
      json: () => Promise.resolve({ watching: true }) });
  };

  const boot = (presence, statusOk) => {
    const ctx = fresh({ fetch: serve(presence, statusOk) });
    ctx.bootShadowOverlay();
    return new Promise(res => setTimeout(() => res(ctx), 20));
  };

  Promise.all([boot(true), boot(false), boot(undefined), boot(false, false)])
    .then(([on, off, unset, dark]) => {
    /* ON: the card is there */
    assert.strictEqual(on._appended.length, 1,
      "setting ON must mount the dot");
    assert.strictEqual(on.S.shadowCardEvery, true,
      "the saved answer must reach the flag the mount reads");

    /* OFF: nothing mounts, and nothing mounted first and was taken away --
       _appended records every append that ever happened, so a flash would
       show up here as a length of 1 even though the dot was later removed */
    assert.strictEqual(off._appended.length, 0,
      "setting OFF must mount NOTHING -- not even briefly");
    assert.strictEqual(off.S.shadowCardEvery, false,
      "the saved answer must be applied before the mount decision");
    assert.strictEqual(off.shadowCornerCardOn(), false,
      "and the gate must agree with it");

    /* an install nobody has configured still has a way to reach Shadow */
    assert.strictEqual(unset._appended.length, 1,
      "an absent setting means SHOWN -- the default is not neutral");

    /* the server gate still wins: OFF status mounts nothing regardless */
    assert.strictEqual(dark._appended.length, 0,
      "a dark status mounts nothing whatever presence says");
    console.log("ok 19 corner card: ON mounts, OFF never paints, unset shows");

    /* 20. RESTORED AFTER RESTART. Same saved answer, brand-new context. */
    return Promise.all([boot(false), boot(false), boot(true)]);
  }).then(([restart1, restart2, backOn]) => {
    for (const [n, ctx] of [[1, restart1], [2, restart2]])
      assert.strictEqual(ctx._appended.length, 0,
        "restart " + n + ": a saved OFF must survive into a fresh context "
        + "with no memory of the last one");
    assert.strictEqual(backOn._appended.length, 1,
      "and turning it back on is restored the same way");
    console.log("ok 20 the saved answer survives a restart, both ways");

    /* 21. the setting moves the card WITHOUT a reload, both directions, and
       is kept apart from the card's own hide control. */
    const ctx = fresh();
    let mounted = null;
    const removed = [];
    ctx.document.querySelector = (sel) =>
      sel === ".shdot" ? mounted : null;
    ctx.document.createElement = (tag) => {
      const el = { tagName: tag, className: "", textContent: "", dataset: {},
        _attrs: {}, setAttribute(k, v){ el._attrs[k] = v; },
        addEventListener(){}, remove(){ removed.push(el); mounted = null; } };
      return el;
    };
    const origAppend = ctx.document.body.appendChild;
    ctx.document.body.appendChild = (el) => {
      if (el.className && /shdot/.test(el.className)) mounted = el;
      return origAppend.call(ctx.document.body, el);
    };
    ctx.applyCornerCardPref(true);
    assert(mounted, "turning it ON must mount without a reload");
    ctx.applyCornerCardPref(false);
    assert.strictEqual(removed.length, 1,
      "turning it OFF must remove the dot without a reload");
    assert.strictEqual(mounted, null, "and leave nothing behind");

    /* the two flags mean different things and must not be conflated: the
       setting is the standing choice, hide-for-session is "not right now" */
    ctx.S.shadowHideSession = true;
    ctx.applyCornerCardPref(true);
    assert.strictEqual(ctx.S.shadowHideSession, false,
      "turning the setting ON clears a session dismissal -- 'on every "
      + "screen' that leaves the card hidden is not on");
    ctx.S.shadowCardEvery = true;
    ctx.S.shadowHideSession = true;
    assert.strictEqual(ctx.mountShadowOverlay(), undefined,
      "a session dismissal still suppresses the mount while the setting is ON");
    console.log("ok 21 the setting moves the card live, and is not the "
      + "session flag");
  }).catch(e => {
    console.error("FAIL 19-21:", e && e.message ? e.message : e);
    process.exitCode = 1;
  });
}

/* the setting is applied before the mount, structurally: pin the await so a
   later refactor cannot quietly re-introduce the flash by mounting on status
   and correcting afterwards. */
assert(/Promise\.all\(\[[\s\S]{0,400}\/api\/shadow\/status[\s\S]{0,400}\/api\/shadow\/settings/
  .test(src), "boot must await status AND settings together, not in sequence");
assert(/applyShadowPresence\(settings\);[\s\S]{0,120}mountShadowOverlay\(\)/
  .test(src), "presence must be applied BEFORE the mount, not after");

/* the no-poller pin, restated for the new timers */
assert(!/setInterval/.test(src), "the bounded re-read must not become a poller");

console.log("test_shadow_overlay.js: all green");
}

/* THE FALLBACK HALF OF THE TURN DISPLAY (founder, 2026-09-16).

   missionCardHtml reads the turn through shadowTurnNow, which lives in
   16-shadow-home.js -- and THIS harness loads the overlay module alone, by
   design ("real module under vm, minimal stubs"). So it is exactly the
   context the `typeof shadowTurnNow === "function"` guard exists for, and
   what it proves here is that a partial shell still renders the historical
   number instead of throwing. The reader's own half is pinned in
   test_shadow_home.js, where both modules are loaded. */
{
  const ctx = fresh();
  assert.strictEqual(typeof ctx.shadowTurnNow, "undefined",
    "precondition: this harness does not load the reader");
  const card = ctx.missionCardHtml({ id: "m-1", objective: "o",
    state: "running", turns_used: 3, turn_open: 4, max_turns: 12 });
  const turns = (card.match(/shturns">([^<]*)</) || [])[1];
  assert.strictEqual(turns, "3/12",
    "without the reader the card falls back to the completed count");
  const bare = ctx.missionCardHtml({ id: "m-2", objective: "o",
    state: "running", turns_used: 1, max_turns: 9 });
  assert.strictEqual((bare.match(/shturns">([^<]*)</) || [])[1], "1/9",
    "a record with no turn_open is unchanged");
  console.log("ok turn display falls back when the reader is not loaded");
}
