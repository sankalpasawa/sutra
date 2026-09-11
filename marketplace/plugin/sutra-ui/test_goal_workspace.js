#!/usr/bin/env node
/* test_goal_workspace.js -- V5 slice 7: the Goal workspace UI.
   Run: node test_goal_workspace.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const html = fs.readFileSync(
  path.join(__dirname, "static", "panel.html"), "utf8");
assert(/18-goal-workspace\.js/.test(html),
       "panel.html loads the goal workspace module");

const css = fs.readFileSync(
  path.join(__dirname, "static", "panel.css"), "utf8");
const overlay = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(
  path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "18-goal-workspace.js"), "utf8");

function fresh(opts){
  opts = opts || {};
  const fetches = [];
  const posts = [];
  const submits = [];
  const nudges = [];
  const ctx = {
    console, Date,
    setTimeout: (fn) => ({ fn }),
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    SCREENS: {}, TITLES: {}, S: {},
    scheduleRender(){ ctx.renders = (ctx.renders || 0) + 1; },
    render(){ ctx.renders = (ctx.renders || 0) + 1; },
    openScreen(id){ ctx.opened = id; ctx.S.screen = id; },
    goDest(d){ ctx.dest = d; },
    showNudge(t){ nudges.push(t); },
    submitTurn(text, sid){ submits.push({ text, sid }); return null; },
    fetch(url){
      fetches.push(url);
      const body = (opts.responses || {})[url];
      if (body === undefined)
        return Promise.resolve({ ok: false, status: 404,
                                 json: () => Promise.resolve({}) });
      return Promise.resolve({ ok: true, status: 200,
                               json: () => Promise.resolve(body) });
    },
    requestAnimationFrame(fn){ (ctx.rafs = ctx.rafs || []).push(fn); },
    document: {
      addEventListener(t, fn){ (ctx.handlers[t] = ctx.handlers[t] || [])
        .push(fn); },
      createElement(){ return { setAttribute(){}, remove(){},
                                dataset: {}, classList: { add(){} } }; },
      body: { appendChild(){}, classList: { add(){} } },
      /* a stand-in .gwturns scroller, so the pin/park logic is driven for
         real rather than mocked away */
      querySelector(sel){
        if (sel === ".gwturns") return ctx.scroller || null;
        return null;
      },
    },
    handlers: {}, fetches, posts, submits, nudges,
  };
  ctx.window = ctx;
  ctx.globalThis = ctx;
  ctx.__SHADOW_NO_AUTOBOOT = true;
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);       /* isOwnTurn, shadowRouteDeepLink */
  vm.runInContext(home, ctx);          /* shadowChatLabel, shadowPlaneHtml */
  /* record posts instead of firing them */
  ctx.shadowPost = (url, body) => {
    posts.push({ url, body });
    return Promise.resolve({ ok: true, status: 200,
                             json: () => Promise.resolve({}) });
  };
  vm.runInContext(src, ctx);
  return ctx;
}

const ROW_BLOCKED = {
  id: "g-aaa111", outcome: "ship the connector retry fix", state: "blocked",
  target_session: "01a081", checks_met: 2, checks_total: 3,
  checks_label: "2 of 3 checks", turns_used: 20, max_turns: 20,
  turn_label: "turn 20/20", block_reason: "budget_exhausted", attempt: 2,
  current_mission_id: null, updated_at: "2026-09-11T09:00:00Z",
};
const ROW_WORKING = {
  id: "g-bbb222", outcome: "wire the webhook", state: "working",
  target_session: "01a082", checks_met: 0, checks_total: 2,
  checks_label: "0 of 2 checks", turn_label: "turn 3/20",
  block_reason: null, attempt: 1, updated_at: "2026-09-11T09:05:00Z",
};

const DETAIL_BLOCKED = Object.assign({}, ROW_BLOCKED, {
  checks: [
    { index: 0, tier: "contains_artifact", check: "Integration configured",
      met: true },
    { index: 1, tier: "contains_artifact", check: "Tests passing",
      met: true },
    { index: 2, tier: "verify", check: "Production deployment verified",
      met: false },
  ],
  unmet: ["Production deployment verified"],
  attempts: [
    { attempt: 1, mission_id: "m-1", ended_state: "blocked",
      note: "budget_exhausted" },
    { attempt: 2, mission_id: "m-2", ended_state: "blocked",
      note: "budget_exhausted" },
  ],
  learned: [
    { id: "l-1", kind: "blocker", text: "attempt 1 stopped on budget" },
    { id: "l-2", kind: "founder_guidance",
      text: "the retry path needs the mock server up first" },
  ],
  founder_guidance: [{ id: "l-2", kind: "founder_guidance",
                       text: "the retry path needs the mock server up first" }],
});

let n = 0;
function ok(msg){ console.log("ok " + (++n) + " " + msg); }

/* 1. the list renders, blocked pinned first */
{
  const ctx = fresh();
  const out = ctx.goalsListHtml([ROW_WORKING, ROW_BLOCKED]);
  assert(/ship the connector retry fix/.test(out), "outcome rendered");
  assert(/wire the webhook/.test(out), "both goals rendered");
  assert(/2 of 3 checks/.test(out), "progress rendered");
  assert(/turn 20\/20/.test(out), "turn usage rendered");
  assert(out.indexOf("g-aaa111") < out.indexOf("g-bbb222"),
         "blocked is pinned to the top");
  assert(/needs you: the turn budget ran out/.test(out),
         "blocker in human words");
  assert(/2026-09-11T09:00:00Z/.test(out), "updated time rendered");
  assert(!/%/.test(out), "no percentage anywhere");
  ok("goal list renders");
}

/* 2. empty state in the existing voice */
{
  const ctx = fresh();
  assert(/No goals yet/.test(ctx.goalsListHtml([])), "honest empty state");
  ok("empty list state");
}

/* 3. screens + titles registered, under the existing registry */
{
  const ctx = fresh();
  assert(typeof ctx.SCREENS.goals === "function", "SCREENS.goals");
  assert(typeof ctx.SCREENS.goal === "function", "SCREENS.goal");
  assert(ctx.TITLES.goals[0] === "Goals", "TITLES.goals");
  assert(ctx.TITLES.goal[0] === "Goal", "TITLES.goal");
  ok("screens registered");
}

/* 4. selecting a goal opens the workspace, under Focus */
{
  const ctx = fresh({ responses: {
    "/api/shadow/goals/g-aaa111": DETAIL_BLOCKED } });
  ctx.DESTS = ["now", "focus", "chats"];
  ctx.S.ui = { dest: "now" };
  ctx.openGoal("g-aaa111");
  assert.strictEqual(ctx.S.goalSel, "g-aaa111", "selection recorded");
  assert.strictEqual(ctx.opened, "goal", "the goal screen was opened");
  assert.strictEqual(ctx.S.ui.dest, "focus",
                     "the rail says Focus, not whatever came before");
  ctx.closeGoal();
  assert.strictEqual(ctx.S.ui.dest, "focus", "and still does on the list");
  assert.strictEqual(ctx.opened, "goals", "back to the list");
  ok("selecting a goal opens the workspace under Focus");
}

/* 5. a card click routes through the delegated handler */
{
  const ctx = fresh({ responses: {
    "/api/shadow/goals/g-aaa111": DETAIL_BLOCKED } });
  const target = { dataset: { goalopen: "g-aaa111" },
                   closest: (sel) => sel === "[data-goalopen]"
                     ? { dataset: { goalopen: "g-aaa111" } } : null };
  ctx.handlers.click.forEach(fn => fn({ target }));
  assert.strictEqual(ctx.S.goalSel, "g-aaa111", "card click opened it");
  ok("card click opens the goal");
}

/* 6. outcome / state / progress render from API data */
{
  const ctx = fresh();
  ctx.S.goalSel = "g-aaa111";
  ctx.S.goalDetail = { "g-aaa111": DETAIL_BLOCKED };
  ctx.S.goalTranscript = { "01a081": [] };
  const out = ctx.goalWorkspaceHtml();
  assert(/ship the connector retry fix/.test(out), "outcome");
  assert(/gwst-blocked/.test(out), "state class");
  assert(/2 of 3 checks · turn 20\/20/.test(out), "both facts, unblended");
  assert(!/%/.test(out), "still no percentage");
  ok("outcome/state/progress from API");
}

/* 7. individual checks render with tick / ring */
{
  const ctx = fresh();
  const out = ctx.goalChecksHtml(DETAIL_BLOCKED.checks);
  assert(/✓/.test(out) && /○/.test(out), "both markers used");
  assert(/Integration configured/.test(out), "check 1");
  assert(/Tests passing/.test(out), "check 2");
  assert(/Production deployment verified/.test(out), "check 3");
  const met = (out.match(/gwcheck-met/g) || []).length;
  assert.strictEqual(met, 2, "exactly the two satisfied checks are marked");
  ok("checks render individually");
}

/* 8. blocked renders the blocker, and does not read as failed */
{
  const ctx = fresh();
  ctx.S.goalSel = "g-aaa111";
  ctx.S.goalDetail = { "g-aaa111": DETAIL_BLOCKED };
  ctx.S.goalTranscript = { "01a081": [] };
  const out = ctx.goalWorkspaceHtml();
  assert(/Shadow needs you/.test(out),
         "blocked is named in the founder's words (slice 9)");
  assert(/the turn budget ran out/.test(out), "reason in human words");
  assert(/Still unmet: Production deployment verified/.test(out),
         "the unmet check is named");
  assert(/still alive/.test(out), "the chat is not dead");
  assert(!/failed/i.test(out), "never reads as failed");
  /* the label's ampersand is correctly escaped in the HTML */
  assert(/Answer &amp; resume/.test(out) && /Extend budget/.test(out),
         "the founder actions are offered");
  ok("blocked renders its blocker");
}

/* 9. done renders verified completion */
{
  const ctx = fresh();
  const done = Object.assign({}, DETAIL_BLOCKED, {
    state: "done", block_reason: null, checks_label: "3 of 3 checks",
    unmet: [], checks: DETAIL_BLOCKED.checks.map(
      c => Object.assign({}, c, { met: true })) });
  ctx.S.goalSel = "g-aaa111";
  ctx.S.goalDetail = { "g-aaa111": done };
  ctx.S.goalTranscript = { "01a081": [] };
  const out = ctx.goalWorkspaceHtml();
  assert(/✓ Verified/.test(out), "verified badge");
  assert(/3 of 3 checks/.test(out), "final checks preserved");
  assert(/not claimed/.test(out), "verified, not claimed");
  assert(/gwattempt/.test(out), "attempt history preserved");
  assert(/gwchat/.test(out), "the target chat is still shown");
  assert.strictEqual(ctx.goalActions("done", done).length, 0,
                     "no nonsensical actions on a terminal goal");
  assert(/No execution controls/.test(out),
         "and the panel says why the controls are absent (slice 9)");
  ok("done renders verified completion");
}

/* 10. stopped preserves progress and history */
{
  const ctx = fresh();
  const stopped = Object.assign({}, DETAIL_BLOCKED,
                                { state: "stopped", block_reason: null });
  ctx.S.goalSel = "g-aaa111";
  ctx.S.goalDetail = { "g-aaa111": stopped };
  ctx.S.goalTranscript = { "01a081": [] };
  const out = ctx.goalWorkspaceHtml();
  assert(/Stopped/.test(out), "stopped named");
  assert(/2 of 3 checks/.test(out), "last known progress kept");
  assert(/gwattempt/.test(out), "history kept");
  assert(/gwchat/.test(out), "chat still accessible");
  ok("stopped preserves progress");
}

/* 11. attempts render compactly */
{
  const ctx = fresh();
  const out = ctx.goalAttemptsHtml(DETAIL_BLOCKED.attempts);
  assert(/Attempts/.test(out), "section head");
  assert(/blocked/.test(out), "how each ended");
  assert.strictEqual((out.match(/gwattempt/g) || []).length, 2,
                     "one row per attempt");
  ok("attempt history renders");
}

/* 12. learned renders, without implementation metadata */
{
  const ctx = fresh();
  const out = ctx.goalLearnedHtml(DETAIL_BLOCKED.learned);
  assert(/What I learned/.test(out), "section head");
  assert(/mock server up first/.test(out), "the guidance text");
  assert(/founder guidance/.test(out), "kind humanised");
  assert(!/dedupe/.test(out), "no dedupe keys leak");
  assert(!/l-1/.test(out), "no internal ids leak");
  ok("learned items render");
}

/* 13. state-appropriate actions only */
{
  const ctx = fresh();
  /* joined, not deepStrictEqual: arrays built inside the vm context have a
     different Array prototype than the host's, which deepStrictEqual
     rejects on identity even when the contents match. */
  const acts = (s, d) => ctx.goalActions(s, d).map(a => a.act).join(",");
  assert.strictEqual(acts("draft"), "start");
  /* slice 9: working can also hand the chat over; verifying can confirm the
     outstanding founder check when there IS one */
  assert.strictEqual(acts("working"), "stop,takeover");
  assert.strictEqual(acts("verifying"), "stop", "nothing to confirm");
  assert.strictEqual(acts("verifying", { checks: [
    { index: 1, tier: "founder_confirm", met: false }] }), "confirm,stop");
  /* blocked depends on WHY: more turns is only an answer when turns were
     what ran out (2026-09-11 fold -- a no_live_runtime block dies at turn
     0/20, so a budget button would point at the wrong problem) */
  assert.strictEqual(acts("blocked", { block_reason: "budget_exhausted" }),
                     "resume,extend,stop");
  assert.strictEqual(acts("blocked", { block_reason: "no_live_runtime" }),
                     "resume,stop");
  assert.strictEqual(acts("blocked"), "resume,stop",
                     "and an unstated reason never assumes the budget");
  assert.strictEqual(acts("done"), "");
  assert.strictEqual(acts("stopped"), "");
  ok("actions match the state");
}

/* 14. YOU -> SHADOW posts founder guidance, and never touches the chat */
{
  const ctx = fresh({ responses: {
    "/api/shadow/goals/g-aaa111": DETAIL_BLOCKED,
    "/api/shadow/goals": { goals: [ROW_BLOCKED] } } });
  ctx.goalTellShadow("g-aaa111", "you are missing the eligibility check");
  assert.strictEqual(ctx.posts.length, 1, "exactly one post");
  assert.strictEqual(ctx.posts[0].url,
                     "/api/shadow/goals/g-aaa111/act", "the goal act route");
  assert.strictEqual(ctx.posts[0].body.action, "guidance",
                     "the existing guidance action");
  assert(/eligibility/.test(ctx.posts[0].body.text), "the text rides along");
  assert.strictEqual(ctx.submits.length, 0,
                     "YOU -> SHADOW must never reach the target chat");
  ok("YOU → SHADOW sends founder guidance");
}

/* 15. YOU -> CHAT uses the ordinary /ws/chat operator path */
{
  const ctx = fresh();
  ctx.goalTakeOver("01a081", "I brought the mock server up");
  assert.strictEqual(ctx.submits.length, 1, "submitTurn was used");
  assert.strictEqual(ctx.submits[0].sid, "01a081", "into the target session");
  assert(/mock server/.test(ctx.submits[0].text), "the founder's words");
  assert.strictEqual(ctx.posts.length, 0,
                     "no second chat route, no shadow post");
  ok("YOU → CHAT uses /ws/chat via submitTurn");
}

/* 16. the two composers are separate, labelled, and warn before typing */
{
  const ctx = fresh();
  ctx.S.goalSel = "g-aaa111";
  ctx.S.goalDetail = { "g-aaa111": DETAIL_BLOCKED };
  ctx.S.goalTranscript = { "01a081": [] };
  const out = ctx.goalWorkspaceHtml();
  assert(/YOU → SHADOW/.test(out), "shadow composer labelled");
  assert(/YOU → CHAT/.test(out), "chat composer labelled");
  assert(/Tell Shadow what it is missing/.test(out), "the placeholder");
  assert(/you take over — Shadow pauses in this/.test(out),
         "the warning is stated before you type");
  assert(/data-goalshadow/.test(out) && /data-goalchat/.test(out),
         "two distinct fields");
  ok("two composers, two audiences");
}

/* 17. keydown routes each composer to its own audience */
{
  const ctx = fresh({ responses: {
    "/api/shadow/goals/g-aaa111": DETAIL_BLOCKED,
    "/api/shadow/goals": { goals: [] } } });
  const ev = (dataset, value) => ({ key: "Enter", shiftKey: false,
    preventDefault(){}, target: { dataset, value } });
  ctx.handlers.keydown.forEach(fn =>
    fn(ev({ goalshadow: "g-aaa111" }, "missing the check")));
  assert.strictEqual(ctx.posts.length, 1, "guidance posted");
  assert.strictEqual(ctx.submits.length, 0, "nothing sent to the chat");
  ctx.handlers.keydown.forEach(fn =>
    fn(ev({ goalchat: "01a081" }, "taking over")));
  assert.strictEqual(ctx.submits.length, 1, "chat send happened");
  assert.strictEqual(ctx.posts.length, 1, "and no extra goal post");
  ok("composers route to their own audience");
}

/* 18. start/resume RE-FETCH rather than trusting the fire-and-forget echo */
{
  const ctx = fresh({ responses: {
    "/api/shadow/goals/g-aaa111": DETAIL_BLOCKED,
    "/api/shadow/goals": { goals: [ROW_BLOCKED] } } });
  return_check(ctx);
  function return_check(c){
    c.goalAct("g-aaa111", "start");
  }
  /* the act posts, then reconciles by reading the goal and the list back */
  setImmediate(() => {});
  assert.strictEqual(ctx.posts[0].body.action, "start", "start posted");
  ok("start posts through the goal act route");
}

/* 19. goalAct reconciles state from the server (async settle) */
{
  const ctx = fresh({ responses: {
    "/api/shadow/goals/g-aaa111": DETAIL_BLOCKED,
    "/api/shadow/goals": { goals: [ROW_BLOCKED] } } });
  ctx.goalAct("g-aaa111", "resume").then(() => {
    assert(ctx.fetches.includes("/api/shadow/goals/g-aaa111"),
           "the goal was re-read after the action");
    assert(ctx.fetches.includes("/api/shadow/goals"),
           "the list was re-read after the action");
    assert.strictEqual(ctx.S.goalDetail["g-aaa111"].state, "blocked",
                       "renders the ACTUAL returned state, not an assumed one");
    ok("start/resume reconcile actual state");
  }).catch(e => { throw e; });
}

/* 20. stop uses the existing goal stop action */
{
  const ctx = fresh({ responses: {
    "/api/shadow/goals/g-aaa111": DETAIL_BLOCKED,
    "/api/shadow/goals": { goals: [] } } });
  ctx.goalAct("g-aaa111", "stop");
  assert.strictEqual(ctx.posts[0].body.action, "stop", "the stop action");
  assert.strictEqual(ctx.posts[0].url, "/api/shadow/goals/g-aaa111/act");
  ok("stop uses the goal stop action");
}

/* 21. extend reuses resume with added budget -- never a reset */
{
  const ctx = fresh({ responses: {
    "/api/shadow/goals/g-aaa111": DETAIL_BLOCKED,
    "/api/shadow/goals": { goals: [] } } });
  ctx.handlers.click.forEach(fn => fn({ target: {
    dataset: { goalact: "extend", goalid: "g-aaa111" },
    closest: () => null } }));
  assert.strictEqual(ctx.posts[0].body.action, "resume", "extend = resume");
  assert(ctx.posts[0].body.extra_turns > 0, "with ADDED turns");
  ok("extend adds budget via resume");
}

/* 22. the target chat renders the ACTUAL session messages, in order */
{
  const ctx = fresh();
  const msgs = [
    { role: "user", text: "[Shadow · mission m-2] Continue toward: ship it." },
    { role: "assistant", text: "Running pytest — 2 passed, 1 failed." },
    { role: "user", text: "the mock server is up now" },
  ];
  const out = ctx.goalTranscriptHtml(msgs, DETAIL_BLOCKED);
  assert(/Continue toward: ship it/.test(out), "shadow turn present");
  assert(/2 passed, 1 failed/.test(out), "chat output present");
  assert(/the mock server is up now/.test(out), "founder turn present");
  assert(out.indexOf("Continue toward") < out.indexOf("2 passed"),
         "chronological order");
  ok("target chat renders real session messages");
}

/* 23. Shadow's injected turns are visually distinguishable */
{
  const ctx = fresh();
  const msgs = [
    { role: "user", text: "[Shadow · mission m-2] do the thing" },
    { role: "assistant", text: "done the thing" },
    { role: "user", text: "founder speaking" },
  ];
  const out = ctx.goalTranscriptHtml(msgs, DETAIL_BLOCKED);
  assert(/gwturn-shadow/.test(out), "shadow class applied");
  assert(/gwturn-chat/.test(out), "chat class applied");
  assert(/gwturn-founder/.test(out), "founder class applied");
  assert.strictEqual((out.match(/gwturn-shadow/g) || []).length, 1,
                     "only the tagged turn is Shadow's");
  assert(/Shadow · mission<\/span>/.test(out), "and it is labelled");
  /* the CSS must actually distinguish them */
  assert(/\.gwturn-shadow\{/.test(css), "shadow turn styled");
  assert(/\.gwturn-chat\{/.test(css), "chat turn styled");
  ok("shadow turns are distinguishable");
}

/* 23b. the tag is not said twice: the row label carries it */
{
  const ctx = fresh();
  const out = ctx.goalTranscriptHtml(
    [{ role: "user", text: "[Shadow · mission m-2] do the thing" }],
    DETAIL_BLOCKED);
  assert(/Shadow · mission<\/span>/.test(out), "the label says it once");
  assert(/do the thing/.test(out), "the instruction survives");
  assert(!/\[Shadow · mission m-2\]/.test(out),
         "the redundant prefix is stripped from the DISPLAY");
  assert.strictEqual(ctx.goalStripTag("[Shadow · mission m-9] go"), "go",
                     "stripping is prefix-anchored");
  assert.strictEqual(ctx.goalStripTag("plain text"), "plain text",
                     "untagged text is untouched");
  ok("the tag is shown once");
}

/* 24. an assistant turn quoting the tag is NOT mistaken for Shadow's */
{
  const ctx = fresh();
  const out = ctx.goalTranscriptHtml(
    [{ role: "assistant", text: "[Shadow · mission m-2] was my brief" }],
    DETAIL_BLOCKED);
  assert(/gwturn-chat/.test(out), "still the chat's own output");
  assert(!/gwturn-shadow/.test(out), "role asymmetry respected");
  ok("only user turns can be Shadow's");
}

/* 25. the blocked stop point is marked IN the transcript */
{
  const ctx = fresh();
  const out = ctx.goalTranscriptHtml(
    [{ role: "assistant", text: "still failing" }], DETAIL_BLOCKED);
  assert(/Shadow stopped here/.test(out), "the stop is explained in place");
  assert(/turn 20\/20/.test(out), "with the turns used");
  assert(/turn budget ran out/.test(out), "and the reason");
  ok("stop point marked in the transcript");
}

/* 26. an OPEN pane's turns are preferred; a CLOSED pane's are not.
   CORRECTED 2026-09-11. This used to assert that the pane array always
   won, with no pane open -- and that premise is what made a running
   Assignment's RHS look static: `turns` is live only while the pane's
   socket is writing into it, and an Assignment's target has no pane open
   because Shadow drives it headlessly. Both directions are pinned now. */
{
  const ctx = fresh();
  const paneTurns = [{ text: "[Shadow · mission m-9] go", response: "went" }];
  const disk = [{ role: "assistant", text: "NEWER DISK COPY" }];

  ctx.S.openPanes = ["01a081"];                 /* the founder has it open */
  ctx.S.sessions = [{ id: "01a081", turns: paneTurns }];
  ctx.S.goalTranscript = { "01a081": disk };
  let msgs = ctx.goalMessages("01a081");
  assert(/go/.test(JSON.stringify(msgs)), "the open pane's live turns win");
  assert(!/NEWER DISK COPY/.test(JSON.stringify(msgs)),
         "the file lags a streaming turn, so it must not replace it");

  ctx.S.openPanes = [];                         /* Shadow drives it headless */
  msgs = ctx.goalMessages("01a081");
  assert(/NEWER DISK COPY/.test(JSON.stringify(msgs)),
         "with no pane, the refetched transcript is the live one");
  assert(!/go/.test(JSON.stringify(msgs)), "one source, never merged");
  ok("the live source is chosen by whether the pane is actually open");
}

/* 27. transcript states are honest: reading vs empty */
{
  const ctx = fresh();
  assert(/Reading the chat/.test(ctx.goalTranscriptHtml(undefined, {})),
         "not-yet-read says so");
  assert(/Nothing in this chat yet/.test(ctx.goalTranscriptHtml([], {})),
         "genuinely empty says so");
  ok("honest transcript states");
}

/* 28. one workspace bar, one way back */
{
  const ctx = fresh();
  const bar = ctx.goalBarHtml(DETAIL_BLOCKED);
  assert(/‹ All\s+goals/.test(bar), "the back affordance");
  assert.strictEqual((bar.match(/data-goalback/g) || []).length, 1,
                     "exactly one back button");
  assert(/ship the connector retry fix/.test(bar), "bar carries the outcome");
  assert(/gwst-blocked/.test(bar), "and the state");
  ok("one workspace bar");
}

/* 29. back returns to the list */
{
  const ctx = fresh({ responses: { "/api/shadow/goals": { goals: [] } } });
  ctx.S.goalSel = "g-aaa111";
  ctx.handlers.click.forEach(fn => fn({ target: {
    dataset: { goalback: "1" }, closest: () => null } }));
  assert.strictEqual(ctx.S.goalSel, null, "selection cleared");
  assert.strictEqual(ctx.opened, "goals", "landed on the list");
  ok("back returns to the list");
}

/* 30. deep link addresses a goal directly */
{
  const ctx = fresh({ responses: {
    "/api/shadow/goals/g-aaa111": DETAIL_BLOCKED } });
  const handled = ctx.shadowRouteDeepLink("sutra://shadow/goal/g-aaa111");
  assert.strictEqual(handled, true, "the router handled it");
  assert.strictEqual(ctx.S.goalSel, "g-aaa111", "selection set");
  assert.strictEqual(ctx.dest, "focus", "no new top-level destination");
  ok("goal deep link lands in the workspace");
}

/* 31. an existing mission deep link still works */
{
  const ctx = fresh();
  assert.strictEqual(
    ctx.shadowRouteDeepLink("sutra://shadow/mission/m-abc123"), true,
    "mission links unaffected");
  assert.strictEqual(ctx.S.shadowFocusMission, "m-abc123", "still focused");
  ok("existing deep links unaffected");
}

/* 32. Shadow Home keeps Watching and Working, and gains a Goals tab */
{
  const ctx = fresh();
  ctx.S.goals = [ROW_BLOCKED, ROW_WORKING];
  const plane = ctx.shadowPlaneHtml(["s-1"], [], "watching");
  assert(/Watching · 1/.test(plane), "Watching kept");
  assert(/Working · 0/.test(plane), "Working kept");
  assert(/Goals · 2/.test(plane), "Goals tab added with a live count");
  const goalsPlane = ctx.shadowPlaneHtml([], [], "goals");
  assert(/ship the connector retry fix/.test(goalsPlane),
         "the goals tab lists goals");
  ok("Shadow Home gains a Goals tab without losing the others");
}

/* 33. the workspace is ~30/70, height-bounded, and stacks when narrow.
   Measured live at 34/66 with the transcript scrolling and the composer
   on screen; these assertions pin the rules that produce that. */
{
  assert(/\.gwpanel\{ flex:1 1 30%/.test(css), "panel basis is 30%");
  assert(/\.gwchat\{ flex:1 1 62%/.test(css), "chat basis is the larger");
  /* the pane claims the row, exactly as Agents does */
  assert(/\.pane\.gwwide\{/.test(css), "the pane goes wide for a goal");
  /* NOWRAP + min-height:0 are what bound the columns to the row; without
     them the chat grew to its content and the composer left the window */
  assert(/\.pane\.gwwide \.gwcols\{[^}]*flex-wrap:nowrap/.test(css),
         "one line, so the row can bound it");
  assert(/\.pane\.gwwide \.gwpanel, \.pane\.gwwide \.gwchat\{ min-height:0/
    .test(css), "flex items may shrink below their content");
  assert(/\.gwturns\{[^}]*overflow-y:auto/.test(css),
         "the transcript is the scroller");
  assert(/@media \(max-width:900px\)/.test(css), "a stacking breakpoint");
  assert(/flex-direction:column/.test(css), "stacks rather than scrolling");
  ok("30/70 layout, bounded, stacks when narrow");
}

/* 33b. render() gives the goal screen the row, the way Agents already does */
{
  const renderSrc = fs.readFileSync(
    path.join(__dirname, "static", "js", "06-render.js"), "utf8");
  assert(/S\.screen === "agents" \|\| S\.screen === "goal"/.test(renderSrc),
         "the goal screen is solo, so no session pane squeezes it");
  assert(/classList\.toggle\("gwwide", gww\)/.test(renderSrc),
         "and the pane is widened for it");
  ok("the goal screen claims the row");
}

/* 34. the visual language is v10's, expressed in existing tokens */
{
  assert(/#B8945F/.test(css), "the Shadow accent");
  assert(/rgba\(184,148,95,\.12\)/.test(css), "the accent wash");
  assert(/#8B4A6B/.test(css), "alert mulberry for blocked");
  assert(/#2D5A3E/.test(css), "deep green for done");
  assert(/#4A6B8B/.test(css), "slate for verifying");
  assert(/#8B6B4A/.test(css), "brown for working");
  assert(/border-radius:12px/.test(css), "12px cards");
  assert(/border-radius:99px/.test(css), "99px pills");
  assert(!/#e5484d/.test(css.split("v5 slice 7")[1] || ""),
         "no new persistent red alert treatment");
  ok("v10 visual language");
}

/* 35. the dark/off state is honest, like every other Shadow surface */
{
  const ctx = fresh();
  ctx.S.goalDark = true;
  assert(/not enabled/.test(ctx.goalWorkspaceHtml()), "workspace honest");
  assert(/not enabled/.test(ctx.SCREENS.goals()), "list honest");
  ok("honest dark state");
}

/* 36. escaping: a hostile outcome cannot break out */
{
  const ctx = fresh();
  const nasty = Object.assign({}, ROW_BLOCKED,
    { outcome: '<img src=x onerror=alert(1)>' });
  const out = ctx.goalsListHtml([nasty]);
  assert(!/<img/.test(out), "markup escaped");
  assert(/&lt;img/.test(out), "and rendered as text");
  ok("output is escaped");
}

/* ---- autoscroll: follow the tail, but never yank a reader ------------- */

/* a minimal scroller with real geometry */
function scroller(ctx, opts){
  opts = opts || {};
  const el = {
    scrollHeight: opts.scrollHeight == null ? 1000 : opts.scrollHeight,
    clientHeight: opts.clientHeight == null ? 300 : opts.clientHeight,
    scrollTop: opts.scrollTop == null ? 700 : opts.scrollTop,
    dataset: { gwsid: opts.sid || "01a081" },
    listeners: {},
    addEventListener(t, fn){ el.listeners[t] = fn; },
  };
  ctx.scroller = el;
  return el;
}
function flushRafs(ctx){
  const q = ctx.rafs || []; ctx.rafs = [];
  q.forEach(fn => fn());
}

/* 38. at the bottom -> pinned; the rebuild follows the tail */
{
  const ctx = fresh();
  scroller(ctx, { scrollTop: 700 });          /* 1000-300 = exactly bottom */
  const prior = ctx.goalScrollState();
  assert.strictEqual(prior.pinned, true, "at the bottom reads as pinned");
  assert.strictEqual(prior.sid, "01a081", "keyed by the target session");
  /* the rebuild grew the transcript */
  ctx.scroller.scrollHeight = 1400; ctx.scroller.scrollTop = 0;
  ctx.goalRestoreScroll(prior);
  assert.strictEqual(ctx.scroller.scrollTop, 1400,
                     "followed the tail after new turns landed");
  ok("pinned transcript follows new turns");
}

/* 39. scrolled up -> parked; the exact offset is kept, not the tail */
{
  const ctx = fresh();
  scroller(ctx, { scrollTop: 120 });
  const prior = ctx.goalScrollState();
  assert.strictEqual(prior.pinned, false, "away from the bottom = parked");
  ctx.scroller.scrollHeight = 1400; ctx.scroller.scrollTop = 0;
  ctx.goalRestoreScroll(prior);
  assert.strictEqual(ctx.scroller.scrollTop, 120,
                     "the reader's own offset is preserved");
  ok("parked transcript keeps its offset");
}

/* 40. a manual scroll away records intent and stops the forcing */
{
  const ctx = fresh();
  const el = scroller(ctx, { scrollTop: 700 });
  ctx.goalBindScroll();
  assert(typeof el.listeners.scroll === "function", "scroll bound");
  el.scrollTop = 100;                      /* the founder scrolls up */
  el.listeners.scroll();
  assert.strictEqual(ctx.S.goalUserScrolled["01a081"], true,
                     "intent recorded");
  const prior = ctx.goalScrollState();
  assert.strictEqual(prior.pinned, false,
                     "recorded intent outranks any measurement");
  ok("manual scroll stops autoscroll");
}

/* 41. returning to the bottom lets autoscroll resume naturally */
{
  const ctx = fresh();
  const el = scroller(ctx, { scrollTop: 100 });
  ctx.goalBindScroll();
  el.listeners.scroll();
  assert.strictEqual(ctx.S.goalUserScrolled["01a081"], true, "parked");
  el.scrollTop = 700;                      /* back to the bottom */
  el.listeners.scroll();
  assert.strictEqual(ctx.S.goalUserScrolled["01a081"], undefined,
                     "the flag clears -- following resumes on its own");
  assert.strictEqual(ctx.goalScrollState().pinned, true, "pinned again");
  ok("returning to the bottom resumes autoscroll");
}

/* 42. our own pin is not mistaken for the founder scrolling */
{
  const ctx = fresh();
  const el = scroller(ctx, { scrollTop: 700 });
  ctx.goalBindScroll();
  const prior = ctx.goalScrollState();
  ctx.scroller.scrollHeight = 1400;
  ctx.goalRestoreScroll(prior);            /* sets __pinning while scrolling */
  el.listeners.scroll();                   /* the browser fires scroll */
  assert.strictEqual((ctx.S.goalUserScrolled || {})["01a081"], undefined,
                     "a pin we caused must not unpin itself");
  /* two frames: the queue holds the first pass's release AND the second
     late-layout pass, which re-arms the guard before releasing it again */
  flushRafs(ctx);
  flushRafs(ctx);
  assert.strictEqual(el.__pinning, false, "the guard is released after raf");
  ok("__pinning guard prevents self-unpinning");
}

/* 43. the slop tolerates subpixel layout without unpinning */
{
  const ctx = fresh();
  scroller(ctx, { scrollTop: 700 - 12 });   /* 12px shy of the bottom */
  assert.strictEqual(ctx.goalScrollState().pinned, true,
                     "within the 24px slop still counts as the bottom");
  scroller(ctx, { scrollTop: 700 - 40 });
  assert.strictEqual(ctx.goalScrollState().pinned, false,
                     "beyond the slop is a real scroll away");
  ok("pin slop matches the session panes");
}

/* 44. no scroller, no crash -- and the polling CONTRACT (revised) */
{
  const ctx = fresh();
  ctx.scroller = null;
  assert.strictEqual(ctx.goalScrollState(), null, "nothing to capture");
  ctx.goalRestoreScroll(null);
  ctx.goalRestoreScroll({ pinned: true, top: 0, sid: "x" });
  ctx.goalBindScroll();
  ok("absent transcript is handled");
  /* SLICE 7 PINNED "no polling at all" here. The founder reversed that on
     2026-09-11 after a live run: the mission ran two turns and blocked in
     107s while this screen kept showing its opening snapshot. What is
     pinned now is the SHAPE of the refresh, not its absence -- chained
     setTimeout, screen-scoped, state-gated, reusing loadGoal. The full
     behaviour lives in test_goal_live.js. Comments are stripped first: the
     poll's own doc-comment names setInterval while explaining why it does
     not use one. */
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "")
                  .replace(/^\s*\/\/.*$/gm, "");
  assert(!/setInterval/.test(code), "still no setInterval -- chained only");
  assert(!/setTimeout\([^)]*\d{3,}/.test(code), "no literal timer ladder");
  assert(/GOAL_LIVE_STATES\s*=\s*\["working", "verifying"\]/.test(code),
         "and it only runs while the mission loop can move something");
  ok("the refresh is chained, screen-scoped and state-gated");
}

/* 45. render() drives the capture/restore pair at the existing hook points */
{
  const renderSrc = fs.readFileSync(
    path.join(__dirname, "static", "js", "06-render.js"), "utf8");
  assert(/const priorGoal = \(typeof goalScrollState === "function"\)/
    .test(renderSrc), "captured before the rebuild");
  assert(/goalRestoreScroll\(priorGoal\)/.test(renderSrc),
         "restored after the rebuild");
  assert(/goalBindScroll\(\)/.test(renderSrc), "listener bound after render");
  /* beside the session pair, i.e. the SAME lifecycle */
  assert(renderSrc.indexOf("_sessScrollState()")
         < renderSrc.indexOf("goalScrollState()"),
         "capture sits with the existing session capture");
  assert(renderSrc.indexOf("_restoreSessScroll(priorSess)")
         < renderSrc.indexOf("goalRestoreScroll(priorGoal)"),
         "restore sits with the existing session restore");
  ok("hooked into the existing render lifecycle");
}

/* 46. the transcript element carries its session id for keying */
{
  const ctx = fresh();
  const out = ctx.goalTranscriptHtml(
    [{ role: "assistant", text: "hi" }], DETAIL_BLOCKED);
  assert(/data-gwsid="01a081"/.test(out), "keyed by target session");
  ok("transcript element is keyed");
}

setTimeout(() => {
  console.log("test_goal_workspace.js: all green");
}, 30);
