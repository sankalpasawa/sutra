#!/usr/bin/env node
/* test_shadow_hi_trace.js -- WHERE THE "Hi" MISSION ACTUALLY COMES FROM.
 *
 * (founder, 2026-09-21, pass 17.) The greeting fix landed on the CHAT path
 * and the screenshot still showed a "Hi" task at NEEDS YOU. This lane
 * established, on the real client code, which door the Shadow tab composer
 * goes through: the answer was that it depends on whether + Delegate is
 * open, and that ONE OF THE TWO DOORS TOOK NO SHADOW TURN AT ALL -- the
 * new-task box posted straight to the create endpoint and then to
 * `start_now`, so "Hi" became a running task nobody had judged.
 *
 * Blocks 2 and 3 now pin the FIX, not the bug: both doors ask Shadow, and
 * a task exists only because Shadow said there was work. Block 1 still
 * pins which box is live, and block 4 the door that was already right.
 *
 * THE SHAPE, SETTLED (founder, 2026-09-23). Two halves that must stay
 * independent: the screen changes on Enter for ANY non-empty line, and
 * Shadow reads the line only after the founder has arrived. Two passes put
 * the reading first and stranded a greeting on the composer; one removed
 * the reading and gave a greeting a worker. Blocks 2-5 pin both halves
 * separately, so neither can be folded back into the other.
 *
 * Run: node test_shadow_hi_trace.js
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

function fresh(){
  const ctx = {
    console, Date, setTimeout: () => ({}), clearTimeout(){},
    scheduleRender(){},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {},
    /* both create paths guard on `typeof fetch` before doing anything */
    fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
    /* every network call this file makes, recorded rather than sent */
    posted: [],
    document: {
      addEventListener(t, fn){ (ctx.listeners[t] = ctx.listeners[t] || []).push(fn); },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  /* what Shadow answers this test's /api/shadow/chat with. The default is
     the greeting answer -- words and NO fence -- because that is the case
     the whole lane exists for; a block that wants a task sets it. */
  ctx.chatDoc = { reply: "Hi. What would you like done?" };
  ctx.shadowPost = async (url, body) => {
    ctx.posted.push({ url, body });
    const doc = (url === "/api/shadow/chat")
      ? ctx.chatDoc
      : { id: "m-new", objective: (body || {}).objective,
          state: "brief_confirm", done_when: [] };
    return { ok: true, status: 200, json: async () => doc };
  };
  /* THE START IS RECORDED, NOT SENT. shadowMissionAct is the one door every
     Shadow control uses for an action, so stubbing it here is what lets a
     block assert "the worker started" without a server. `actResult` is what
     it answers with -- null is a start that did not land. */
  ctx.acted = [];
  ctx.actResult = { id: "m-new", state: "running" };
  ctx.shadowMissionAct = async (mid, action) => {
    ctx.acted.push({ mid, action });
    return ctx.actResult;
  };
  ctx.nudges = [];
  ctx.showNudge = (msg) => { ctx.nudges.push(String(msg)); };
  /* the REAL scope machinery: S.shadowThread is a getter over
     S.shadowThreads[S.shadowChat], installed by the overlay's own seeder.
     A bare array would hide the very boundary block 9 is about. */
  ctx.S.shadowThreads = {};
  ctx.S.shadowChat = "global";
  Object.defineProperty(ctx.S, "shadowThread", {
    configurable: true, enumerable: true,
    get(){ const k = ctx.S.shadowChat || "global";
      if (!ctx.S.shadowThreads[k]) ctx.S.shadowThreads[k] = [];
      return ctx.S.shadowThreads[k]; },
    set(v){ ctx.S.shadowThreads[ctx.S.shadowChat || "global"] = v || []; },
  });
  ctx.loadGoalTranscript = () => {};
  ctx.goalMessages = () => [];
  ctx.goalTranscriptHtml = () => "";
  ctx.loadShadowHome = () => {};
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  ctx.S.shadowMissions = [];
  return ctx;
}

let ok = 0;
const pass = (s) => console.log("ok " + (++ok) + " " + s);

/* THE TWO KINDS OF CALL, KEPT APART. Since 2026-09-23 a submission also
   writes its own durable conversation record (POST /api/shadow/conversations
   ...), fire-and-forget, on a path that never touches the screen. Those are
   PERSISTENCE; the turn itself and the start are BEHAVIOUR. A test that
   counted all POSTs together would break every time persistence changed and
   would stop saying anything about the flow. */
const isConv = (u) => /^\/api\/shadow\/conversations/.test(u || "");
const acts = (ctx) => ctx.posted.filter(p => !isConv(p.url));
const convs = (ctx) => ctx.posted.filter(p => isConv(p.url));

/* ══ 1. THE TWO DOORS, AND WHICH ONE IS LIVE ═══════════════════════════ */
{
  const ctx = fresh();
  ctx.S.shadowNewOpen = false;
  const closed = ctx.shadowHomeHtml();
  assert(/data-shhomecompose/.test(closed),
    "with + Delegate CLOSED the stage composer is the box");
  assert(!/data-shnewtalk/.test(closed) || /data-shnewhost/.test(closed),
    "and the new-task chat is not mounted inline");

  ctx.S.shadowNewOpen = true;
  const open = ctx.shadowHomeHtml();
  assert(!/data-shhomecompose/.test(open),
    "with + Delegate OPEN the stage composer is NOT rendered");
  assert(/data-shnewhost|data-shnewtalk/.test(open),
    "the new-task panel is the box instead");
  pass("+ Delegate swaps which composer the founder is typing into");
}

/* ══ 2. "Hi" -- SHADOW CHAT, A REPLY, NO WORKER ══════════════════════ */
{
  const ctx = fresh();
  ctx.S.shadowMissions = [{ id: "m-old", state: "running", target_mode: "new",
                            target_session: "sess-old",
                            objective: "an older task, still running",
                            turns_used: 1, max_turns: 12, done_when: [] }];
  ctx.S.shadowNewOpen = true;
  ctx.chatDoc = { reply: "Hi. Tell me what you want done." };
  ctx.shadowNewChat().text = "Hi";
  return (async () => {
    assert(ctx.shadowSelectedTask(), "before: the fallback picks the old task");
    const made = await ctx.shadowNewTalk();

    assert.strictEqual(acts(ctx).length, 1, "one turn: "
      + JSON.stringify(acts(ctx).map(p => p.url)));
    assert.strictEqual(acts(ctx)[0].url, "/api/shadow/chat");
    /* and it was written down, so a reload can find it */
    assert(convs(ctx).some(p => p.url === "/api/shadow/conversations"
                                && p.body && p.body.prompt === "Hi"),
      "the conversation was opened durably: "
      + JSON.stringify(convs(ctx).map(p => p.url)));
    assert(!ctx.posted.some(p => p.url === "/api/shadow/missions"),
      "NO WORKER: nothing is created");
    assert.strictEqual(ctx.acted.length, 0, "NO WORKER: nothing is started");
    assert.strictEqual(made, null, "and no task is returned");
    assert.strictEqual(ctx.S.shadowMissions.length, 1, "the rail is unchanged");

    assert.strictEqual(ctx.S.shadowNewOpen, false, "New task screen is gone");
    assert.strictEqual(ctx.S.shadowNewChat, null, "and forgotten");
    /* SINCE 2026-09-23 A CONVERSATION HAS A ROW OF ITS OWN, so what they
       are looking at is that -- never the task that was selected before. */
    const looking = ctx.shadowSelectedTask();
    assert(looking && looking.conversation,
      "they are looking at the conversation, not a task: "
      + JSON.stringify(looking && looking.id));
    assert.strictEqual(looking.id, ctx.S.shadowChat, "the one just opened");
    assert.notStrictEqual(looking.id, "m-old", "and not the old task");
    assert.strictEqual(ctx.S.shadowThread.map(t => t.text).join(" | "),
      "Hi | Hi. Tell me what you want done.",
      "the exchange is in the fresh conversation, and it holds nothing else");
    pass("Hi -> Shadow chat -> a reply -> no worker");

    /* ══ 3. ACTIONABLE WORK -- A WORKER STARTS, AND THEY STAY WITH IT ═══ */
    const two = fresh();
    two.S.shadowNewOpen = true;
    two.chatDoc = { reply: "On it.",
                    mission: { id: "m-news", state: "brief_confirm",
                               target_mode: "new",
                               objective: "Get me the top 10 international news stories" } };
    two.shadowNewChat().text = "Get me the top 10 international news stories";
    const m = await two.shadowNewTalk();

    assert(m && m.id === "m-news", "the task from Shadow's reply is returned");
    assert.strictEqual(two.acted.length, 1, "one start: " + JSON.stringify(two.acted));
    assert.strictEqual(two.acted[0].action, "start_now", "the worker starts");
    assert.strictEqual(two.S.shadowTaskSel, "m-news",
      "and they remain in that task's Shadow conversation");
    assert.strictEqual(two.S.shadowNewOpen, false, "New task screen is gone");
    assert.strictEqual((two.S.shadowThread || []).length, 0,
      "the exchange is not duplicated into the general thread");
    pass("actionable work -> a worker starts -> they stay in its conversation");

    /* ══ 4. THE TRANSITION DOES NOT WAIT FOR THE ANSWER ═════════════════
       The half that must never depend on the other. Checked WHILE THE
       REQUEST IS STILL IN FLIGHT: the transport does not resolve until
       this block releases it. Run for BOTH kinds of prompt. */
    for (const [label, doc] of [
      ["a greeting",  { reply: "Hi there." }],
      ["a real task", { reply: "On it.", mission: { id: "m-x",
                        state: "brief_confirm", target_mode: "new",
                        objective: "do a thing" } }],
    ]){
      const mid = fresh();
      mid.S.shadowNewOpen = true;
      let release;
      const gate = new Promise(r => { release = r; });
      mid.shadowPost = async (url, body) => { mid.posted.push({ url, body });
        await gate;
        return { ok: true, status: 200, json: async () => doc }; };
      mid.shadowNewChat().text = "do a thing";
      const inFlight = mid.shadowNewTalk();
      await new Promise(r => setImmediate(() => setImmediate(r)));

      assert.strictEqual(mid.S.shadowNewOpen, false,
        "IN FLIGHT (" + label + "): Screen 1 is already gone");
      assert(!/data-shnewhost/.test(mid.shadowHomeHtml()),
        "IN FLIGHT (" + label + "): and not in the rendered pane");
      assert(/do a thing/.test(mid.shadowHomeHtml()),
        "IN FLIGHT (" + label + "): their words are on screen");
      assert(/thinking/.test(mid.shadowHomeHtml()),
        "IN FLIGHT (" + label + "): under a waiting row");
      assert.strictEqual(mid.acted.length, 0,
        "IN FLIGHT (" + label + "): nothing decided yet");
      release(); await inFlight;
      assert.strictEqual(mid.S.shadowNewOpen, false,
        "AFTER (" + label + "): Screen 1 never comes back");
    }
    pass("Screen 1 disappears on Enter, for every prompt, before any answer");

    /* ══ 5. A TURN THAT FAILS IS SAID, NOT BOUNCED BACK ═════════════════ */
    const bad = fresh();
    bad.S.shadowNewOpen = true;
    bad.shadowPost = async (url, body) => { bad.posted.push({ url, body });
      return { ok: false, status: 503, json: async () => ({}) }; };
    bad.shadowNewChat().text = "Get me the top 10 international news stories";
    await bad.shadowNewTalk();
    assert.strictEqual(bad.S.shadowNewOpen, false, "the composer does not return");
    const said = bad.S.shadowThread.map(t => t.text).join(" | ");
    assert(/top 10 international news/.test(said), "their line is kept: " + said);
    assert(/503/.test(said), "and the reason is beside it: " + said);
    assert(!/thinking/.test(said), "the waiting row is retracted");
    pass("a failed turn is said on the screen they are now on");

    /* ══ 8b. TWO SUBMISSIONS IN FLIGHT AT ONCE STAY APART ═══════════════
       THE RACE THIS PINS. S.shadowThread is a getter that resolves against
       S.shadowChat AT READ TIME. Everything after the await used to read
       it, so a second submission moved S.shadowChat and the FIRST call's
       reply was appended to the SECOND call's conversation -- measured in
       the browser as B holding ["PROMPT B","ANSWER TO B","ANSWER TO A"]
       while A sat on "thinking..." for ever. Each call now owns its thread
       by the key it minted. */
    {
      const par = fresh();
      const gates = {};
      par.shadowPost = (url, body) => new Promise(resolve => {
        gates[body.message] = (doc) => resolve(
          { ok: true, status: 200, json: async () => doc });
      });

      par.S.shadowNewOpen = true;
      par.shadowNewChat().text = "PROMPT A";
      const flightA = par.shadowNewTalk();          /* left in flight */
      await new Promise(r => setImmediate(r));
      const scopeA = par.S.shadowChat;

      par.S.shadowNewOpen = true;
      par.shadowNewChat().text = "PROMPT B";
      const flightB = par.shadowNewTalk();
      await new Promise(r => setImmediate(r));
      const scopeB = par.S.shadowChat;
      assert.notStrictEqual(scopeA, scopeB, "two submissions, two scopes");

      gates["PROMPT B"]({ reply: "ANSWER TO B" });  /* B answers FIRST */
      await flightB;
      gates["PROMPT A"]({ reply: "ANSWER TO A" });  /* then A, out of order */
      await flightA;

      const rows = (k) => (par.S.shadowThreads[k] || []).map(t => t.text).join(" | ");
      assert.strictEqual(rows(scopeA), "PROMPT A | ANSWER TO A",
        "A holds exactly its own exchange, got: " + rows(scopeA));
      assert.strictEqual(rows(scopeB), "PROMPT B | ANSWER TO B",
        "B holds exactly its own exchange, got: " + rows(scopeB));
      pass("two submissions in flight at once never cross-contaminate");
    }

    /* ══ 8c. A SLOW ANSWER DOES NOT STEAL A VIEW THE FOUNDER MOVED ══════
       The rail's click handler writes shadowTaskSel and leaves shadowChat
       alone; a second + Delegate writes shadowChat. They move
       independently, so both are checked before an in-flight answer is
       allowed to take the pane. The task is still created and still
       started -- only the focus is declined. */
    {
      const moved = fresh();
      let release;
      const gate = new Promise(r => { release = r; });
      moved.shadowPost = async () => { await gate;
        return { ok: true, status: 200, json: async () => ({ reply: "On it.",
          mission: { id: "m-slow", state: "brief_confirm", target_mode: "new",
                     objective: "something slow" } }) }; };
      moved.S.shadowMissions = [{ id: "m-open", state: "running",
        target_mode: "new", target_session: "sess-open", objective: "already open",
        turns_used: 1, max_turns: 12, done_when: [] }];
      moved.S.shadowNewOpen = true;
      moved.shadowNewChat().text = "something slow";
      const flight = moved.shadowNewTalk();
      await new Promise(r => setImmediate(r));

      /* the founder clicks a row in the rail while it is in flight */
      moved.S.shadowTaskSel = "m-open";
      release(); await flight;

      assert.strictEqual(moved.S.shadowTaskSel, "m-open",
        "the pane stayed where the founder put it, got " + moved.S.shadowTaskSel);
      assert(moved.S.shadowMissions.some(x => x.id === "m-slow"),
        "the task was still created");
      assert.strictEqual(moved.acted.length, 1, "and still started");
      assert.strictEqual(moved.acted[0].mid, "m-slow");
      pass("a slow answer creates and starts its task without stealing the view");
    }

    /* ══ 8d. THE NEW TASK PANE READS AN EMPTY SCOPE, ALWAYS ═════════════
       THE BUG (founder, 2026-09-23, screenshot). The pane's transcript is
       S.shadowThread, a getter over S.shadowThreads[S.shadowChat]. Opening
       + Delegate set shadowNewOpen and NOTHING ELSE, so shadowChat still
       named the last conversation and the New task pane rendered ITS
       messages under a "New task" header -- "Draw a diagram in a file about
       motorcycles." sitting under a box that had been opened to type
       something new. Reproduced in a real browser, fixed by having the door
       mint the scope rather than by filtering anything out of the render. */
    {
      const door = fresh();
      /* a conversation that already has words in it */
      door.S.shadowChat = "shc-earlier1";
      door.S.shadowThreads["shc-earlier1"] = [
        { who: "founder", text: "Draw a diagram in a file about motorcycles." },
        { who: "shadow", text: "On it." }];
      const beforeKey = door.S.shadowChat;

      /* the founder opens + Delegate -- the real handler, through the DOM */
      (door.listeners.click || []).forEach(fn => fn({
        target: { dataset: { shdelegate: "1" }, closest: () => null } }));

      assert.strictEqual(door.S.shadowNewOpen, true, "the pane opened");
      assert.notStrictEqual(door.S.shadowChat, beforeKey,
        "and it is NOT still pointing at the previous conversation");
      assert.strictEqual((door.S.shadowThread || []).length, 0,
        "the pane's transcript is empty: "
        + JSON.stringify((door.S.shadowThread || []).map(t => t.text)));
      const html = door.shadowHomeHtml();
      assert(!/motorcycles/.test(html),
        "and no earlier message is rendered anywhere in the pane");
      assert.strictEqual(door.S.shadowThreads[beforeKey].length, 2,
        "the earlier conversation is untouched, not cleared");

      /* and the submit adopts THAT scope rather than minting a second */
      const opened = door.S.shadowChat;
      door.chatDoc = { reply: "Hi there." };
      door.shadowNewChat().text = "Hi";
      await door.shadowNewTalk();
      assert.strictEqual(door.S.shadowChat, opened,
        "the line lands in the conversation the founder was looking at");
      assert.strictEqual(door.S.shadowThreads[opened].map(t => t.text).join(" | "),
        "Hi | Hi there.", "and it holds only that exchange");
      assert.strictEqual(door.S.shadowThreads[beforeKey].length, 2,
        "the earlier conversation is STILL untouched");
      pass("+ Delegate opens an empty scope, and the submit lands in it");
    }

    /* ══ 9. + DELEGATE IS THE NEW-INSTANCE DOOR ════════════════════════
       THE FOUNDER'S ACCEPTANCE TEST, VERBATIM (2026-09-23): "with an
       existing task running, open New Task, type Hi, press Enter. A new
       Shadow conversation must open and Hi must appear there -- not inside
       the existing running task. Then repeat with a real task request and
       verify it creates a separate new task." */
    {
      const inst = fresh();
      /* a task that is running, and the conversation it already owns */
      inst.S.shadowMissions = [{ id: "m-running", state: "running",
        target_mode: "new", target_session: "sess-running",
        objective: "an existing task, mid-flight",
        turns_used: 4, max_turns: 12, done_when: [] }];
      inst.S.shadowChat = "sess-running";
      inst.S.shadowThread.push({ who: "founder", ts: 1, text: "work on the existing task" });
      const before = inst.S.shadowThread.length;
      const beforeKey = inst.S.shadowChat;

      /* --- part one: Hi --- */
      inst.S.shadowNewOpen = true;
      inst.chatDoc = { reply: "Hi there." };
      inst.shadowNewChat().text = "Hi";
      await inst.shadowNewTalk();

      assert.notStrictEqual(inst.S.shadowChat, beforeKey,
        "Hi opened a NEW instance, not the running task's conversation");
      assert(/^shc-/.test(inst.S.shadowChat),
        "and it is a DURABLE conversation id: " + inst.S.shadowChat);
      assert.strictEqual(inst.S.shadowThreads[beforeKey].length, before,
        "the running task's own conversation is untouched");
      assert(!inst.S.shadowThreads[beforeKey].some(t => t && t.text === "Hi"),
        "and Hi is NOT in it");
      assert.strictEqual(
        inst.S.shadowThread.map(t => t.text).join(" | "),
        "Hi | Hi there.",
        "Hi and the answer are in the new instance, and it holds nothing else");
      const look = inst.shadowSelectedTask();
      assert(look && look.conversation && look.id === inst.S.shadowChat,
        "what is in focus is the new conversation's own row, not a task "
        + "from the rail: " + JSON.stringify(look && look.id));
      assert.strictEqual(inst.S.shadowMissions.length, 1,
        "and the rail still holds exactly the one task it had");

      /* --- part two: a real task request, from the same door --- */
      const firstKey = inst.S.shadowChat;
      inst.S.shadowNewOpen = true;
      inst.chatDoc = { reply: "Opening that now.",
                       mission: { id: "m-new", state: "brief_confirm",
                                  target_mode: "new",
                                  objective: "Make me a 10-day Africa plan" } };
      inst.shadowNewChat().text = "Make me a 10-day Africa plan";
      const made = await inst.shadowNewTalk();

      assert(made && made.id === "m-new", "a task was created");
      assert.notStrictEqual(inst.S.shadowChat, firstKey,
        "and it opened its OWN instance, not the greeting's");
      assert.strictEqual(inst.S.shadowThreads[firstKey].map(t => t.text).join(" | "),
        "Hi | Hi there.", "the greeting's conversation is left as it was");
      assert.strictEqual(inst.S.shadowMissions.length, 2,
        "the rail now has TWO tasks -- the old one and the new one");
      assert(inst.S.shadowMissions.some(x => x.id === "m-running"),
        "the already-running task is still there");
      assert.strictEqual(inst.S.shadowTaskSel, "m-new",
        "and the new one is what is on screen");
      assert.strictEqual(inst.acted.length, 1, "one start, for the new task only");
      assert.strictEqual(inst.acted[0].mid, "m-new",
        "nothing was done to m-running: " + JSON.stringify(inst.acted));
      pass("+ Delegate opens a new instance every time, and never joins a running task");
    }

    /* ══ 9b. THE INSTANCE KEY IS THE CLIENT'S, AND STAYS THERE ══════════
       scope_id is not decoration on the server: it writes "[Context] You
       are now talking about the chat <id>" into the preamble, and an
       existing-target mission fence with no target of its own is bound to
       it. An instance key names no session, so sending it would make the
       backend act on a chat that does not exist. shadowChatKnown is the
       gate; a REAL chat scope is unaffected. */
    {
      const g = fresh();
      g.S.sessions = [{ id: "sess-real", title: "A real chat" }];
      const sent = [];
      g.shadowPost = async (url, body) => { sent.push(body || {});
        return { ok: true, status: 200, json: async () => ({ reply: "ok" }) }; };

      g.S.shadowChat = "new-abc123-def456";          /* an instance key */
      await g.sendToShadow("hello from a new instance");
      assert.strictEqual(sent[0].scope_id, undefined,
        "an instance key is NOT sent as scope_id: " + JSON.stringify(sent[0]));

      /* AND NOTHING ELSE IS AFFECTED. An earlier attempt gated this on
         shadowChatKnown -- "is it one of the chats the app lists?" -- which
         also dropped a real scope whenever S.sessions had not loaded. Both
         of these ride, as they always have. */
      g.S.shadowChat = "sess-real";                  /* a chat the app lists */
      await g.sendToShadow("hello from a real chat");
      assert.strictEqual(sent[1].scope_id, "sess-real",
        "a real chat scope still rides, exactly as before");

      g.S.sessions = [];                             /* sessions not loaded */
      g.S.shadowChat = "sess-notlisted";
      await g.sendToShadow("hello before the list arrives");
      assert.strictEqual(sent[2].scope_id, "sess-notlisted",
        "and so does a scope the app has simply not listed yet");
      pass("a client-minted instance key never reaches the server as a chat id");
    }

    console.log("\nall Hi-trace checks passed");
  })();
}
