#!/usr/bin/env node
/* test_shadow_completion_ui.js -- a finished task must SHOW what was done.
 *
 * THE GAP (founder, 2026-09-15). When a Shadow task completed, the founder
 * got a Now row reading "done - result inside" and then could not get
 * inside: shadowTaskIsActive rule 4 drops a done mission from the list, and
 * shadowSelectedTask picked its replacement from that same filtered list --
 * so the card being read was swapped out in the same tick the task
 * finished. The only rendering of a result anywhere was missionCardHtml's
 * `result_excerpt`, which is 150 characters off the head of the evidence
 * blob plus 250 off its tail.
 *
 * WHAT IS PINNED HERE:
 *   1. shadowCompletionHtml renders the server's summary and nothing else
 *   2. the card shows it, and drops the now-redundant flat "done when" row
 *   3. a record without the field renders exactly as it did before
 *   4. the task the founder is READING survives its own completion...
 *   5. ...while the LIST still drops it (rule 4 is unchanged)
 *   6. the result can LEAVE the pane: Copy result puts the same summary on
 *      the clipboard as text, says so on the button, and says when it could
 *      not (tests 10-14)
 *
 * WHAT THIS SUITE DOES NOT DO, so nobody reads more into it than is here:
 * it calls the REAL renderers (shadowCompletionHtml / shadowTaskCardHtml)
 * and the REAL delegated listener, but the markup it gets back is never
 * PARSED -- there is no document, no queried node, no dispatched event.
 * qa-shell/shadow-copy-check.mjs is the lane that does that end to end, in
 * Chromium, with the clipboard stubbed so no system clipboard is touched.
 *
 * Run: node test_shadow_completion_ui.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

function fresh(){
  const ctx = {
    console, Date,
    /* FAKE TIMERS, and they honour clearTimeout. The copy feedback clears
       itself on one, and a second click cancels the first click's timer --
       a harness that cannot cancel would let a stale timer fire and would
       prove the opposite of what happens in a browser. */
    timers: [], cleared: [], renders: 0, nodes: [],
    setTimeout: (fn, ms) => {
      const t = { fn, ms, id: ctx.timers.length + 1, cancelled: false, fired: 0 };
      ctx.timers.push(t);
      return t.id;
    },
    clearTimeout: (id) => {
      ctx.cleared.push(id);
      const t = ctx.timers.find(x => x.id === id);
      if (t) t.cancelled = true;
    },
    scheduleRender: () => { ctx.renders++; },
    S: {}, SCREENS: {}, TITLES: {},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    listeners: {},
    /* enough DOM to hold a live region: it is created once, looked up by id
       on every later copy, and read back by the announcement tests */
    document: {
      addEventListener(t, fn){ ctx.listeners[t] = fn; },
      body: { appendChild(n){ ctx.nodes.push(n); } },
      getElementById(id){ return ctx.nodes.find(n => n && n.id === id) || null; },
      createElement(tag){
        return { tag, value: "", textContent: "", attrs: {}, style: {},
          dataset: {},
          setAttribute(k, v){ this.attrs[k] = v; },
          select(){}, remove(){} };
      },
      querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(
    path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8"), ctx);
  vm.runInContext(fs.readFileSync(
    path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8"), ctx);
  return ctx;
}

/* the shape mission_engine.completion_summary stamps -- kept in sync with
   test_shadow_completion_summary.py, which pins the producer */
const SUMMARY = {
  objective: "get the EMI check green",
  headline: "3 of 3 checks passed",
  checks_met: 3, checks_total: 3,
  turns_used: 5, max_turns: 20, chat: "sess-1",
  at: "2026-09-15T01:20:00Z",
  checks: [
    { check: "EMI-OK", tier: "contains_artifact", met: true,
      how: "found in the chat",
      evidence: "…the suite reports EMI-OK for every tenant…" },
    { check: "pytest test_emi.py passes", tier: "verify", met: true,
      how: "Shadow ran this check and it passed" },
    { check: "the copy reads right", tier: "founder_confirm", met: true,
      how: "you confirmed it", by: "founder",
      at: "2026-09-15T01:19:00Z" },
  ],
};

const DONE = { id: "m-done", objective: "get the EMI check green",
  template: "fix", state: "done", target_mode: "new",
  target_session: "sess-1", turns_used: 5, max_turns: 20,
  done_when: [{ tier: "contains_artifact", check: "EMI-OK" }],
  result_excerpt: '{"role": "assistant", "text": "..."} ... tail',
  completion: SUMMARY };

/* 1. the block renders every fact the server stamped, and no other */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml(DONE);
  assert(/3 of 3 checks passed/.test(h), "the headline leads");
  assert(/get the EMI check green/.test(h), "the objective is named");
  assert(/5 of 20 turns/.test(h), "the budget it spent is shown");
  SUMMARY.checks.forEach(k =>
    assert(h.indexOf(k.check) !== -1, "check missing: " + k.check));
  assert(/found in the chat/.test(h)
    && /Shadow ran this check and it passed/.test(h)
    && /you confirmed it/.test(h), "every tier says who satisfied it");
  assert(/you confirmed it · founder/.test(h),
    "a confirmation names who signed it off");
  assert(/the suite reports EMI-OK for every tenant/.test(h),
    "the artifact is quoted in the chat's own words");
  assert(/shcheckev/.test(h), "the quote has its own class");
  /* three met rows, three ticks -- a satisfied check looks satisfied */
  assert.strictEqual((h.match(/shcheckmet/g) || []).length, 3,
    "every met check draws as met");
  assert.strictEqual((h.match(/✓/g) || []).length, 3, "three ticks");
  console.log("ok 1 the summary renders");
}

/* 2. no summary -> no block. The panel must not invent one. */
{
  const ctx = fresh();
  assert.strictEqual(ctx.shadowCompletionHtml({ id: "m-1" }), "",
    "a mission without the field renders nothing");
  assert.strictEqual(ctx.shadowCompletionHtml(null), "", "null is safe");
  assert.strictEqual(
    ctx.shadowCompletionHtml({ id: "m-1", completion: null }), "",
    "an explicit null field renders nothing");
  console.log("ok 2 nothing is invented");
}

/* 3. it comes from the SERVER. Nothing here recomputes a verdict: an unmet
      row must render unmet even on a mission the server called done. */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml({ id: "m-x", completion: {
    headline: "1 of 2 checks passed", objective: "o",
    turns_used: 1, max_turns: 4,
    checks: [{ check: "found it", tier: "contains_artifact", met: true,
               how: "found in the chat" },
             { check: "not yet", tier: "verify", met: false,
               how: "still outstanding" }] } });
  assert(/1 of 2 checks passed/.test(h), "the server's count is the count");
  assert.strictEqual((h.match(/shcheckmet/g) || []).length, 1,
    "only the met row draws as met");
  assert(/still outstanding/.test(h), "the unmet row says so");
  console.log("ok 3 the verdict is the server's");
}

/* 4. the card shows it, and the flat "done when" row steps aside */
{
  const ctx = fresh();
  const card = ctx.shadowTaskCardHtml(DONE);
  assert(/3 of 3 checks passed/.test(card), "the card carries the summary");
  assert(/data-shdone="m-done"/.test(card), "the block has its own hook");
  assert(!/done when/.test(card),
    "the criteria without verdicts do not print twice");
  assert(/data-shtakeover="sess-1"/.test(card),
    "Open the chat still reaches the work");
  /* a task that has NOT finished is untouched */
  const live = Object.assign({}, DONE, { state: "running" });
  delete live.completion;
  const lh = ctx.shadowTaskCardHtml(live);
  assert(/done when/.test(lh), "a live task keeps its criteria row");
  assert(!/shdonesum/.test(lh), "and gets no completion block");
  console.log("ok 4 the card shows it, once");
}

/* 5. a mission completed BEFORE this field existed renders as it always did */
{
  const ctx = fresh();
  const old = Object.assign({}, DONE);
  delete old.completion;
  const card = ctx.shadowTaskCardHtml(old);
  assert(!/shdonesum/.test(card), "no block without the field");
  assert(/done when/.test(card), "the old flat row is still its row");
  assert(/EMI-OK/.test(card), "and it still names the criteria");
  console.log("ok 5 records written before the field are unchanged");
}

/* 6. THE TASK YOU ARE READING SURVIVES ITS OWN COMPLETION.
      Rule 4 drops it from the LIST -- that is right and is pinned below --
      but the pane must not swap the card out from under the founder in the
      same tick, or the summary has no surface at all. */
{
  const ctx = fresh();
  ctx.S.goals = [];
  ctx.S.shadowMissions = [
    DONE,
    { id: "m-other", objective: "something else", state: "running",
      turns_used: 1, max_turns: 20, done_when: [] },
  ];
  ctx.S.shadowTaskSel = "m-done";
  const sel = ctx.shadowSelectedTask();
  assert(sel && sel.id === "m-done",
    "the task the founder picked stayed in the pane");
  assert(/3 of 3 checks passed/.test(ctx.shadowTaskCardHtml(sel)),
    "and it is showing the summary");

  /* 5b. the LIST still drops it -- the workspace is not a mission database */
  const ids = ctx.shadowTasks().map(m => m.id);
  assert(!ids.includes("m-done"), "a conclusion still leaves the list");
  assert(ids.includes("m-other"), "live work is still listed");

  /* and picking something else lets go of it */
  ctx.S.shadowTaskSel = "m-other";
  assert.strictEqual(ctx.shadowSelectedTask().id, "m-other",
    "the founder's next pick wins");
  console.log("ok 6 held task survives completion; the list does not grow");
}

/* 7. nothing selected -> the existing fallback ranking is untouched */
{
  const ctx = fresh();
  ctx.S.goals = [];
  ctx.S.shadowMissions = [
    DONE,
    { id: "m-run", objective: "live", state: "running", done_when: [] },
    { id: "m-blk", objective: "asks", state: "blocked",
      block_reason: "ping_pong", done_when: [] },
  ];
  assert.strictEqual(ctx.shadowSelectedTask().id, "m-blk",
    "with no pick, what needs the founder still ranks first");
  ctx.S.shadowTaskSel = "m-gone";      /* a deleted id selects nothing */
  assert.strictEqual(ctx.shadowSelectedTask().id, "m-blk",
    "a stale id falls through to the ranking, never to null");
  console.log("ok 7 the fallback ranking is unchanged");
}

/* 8. it is escaped. The check text is founder- and model-authored. */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml({ id: "m-e", completion: {
    headline: "1 of 1 checks passed", objective: "<b>obj</b>",
    turns_used: 1, max_turns: 2,
    checks: [{ check: "<script>alert(1)</script>", tier: "contains_artifact",
               met: true, how: "found in the chat",
               evidence: "<img onerror=x>" }] } });
  assert(!/<script>/.test(h), "the criterion is escaped");
  assert(!/<img /.test(h), "the quote is escaped");
  assert(!/<b>obj<\/b>/.test(h), "the objective is escaped");
  assert(/&lt;script&gt;/.test(h), "and it is still readable");
  console.log("ok 8 escaped");
}

/* 9. THE ROW'S PROMISE IS KEPT. "done - result inside" links to
      sutra://shadow/mission/<id>; the workspace picks its card from
      shadowTaskSel, so the link must set it or it opens someone else's
      task. shadowFocusMission (the Watching plane's highlight) is still
      set too -- this adds, it does not rename. */
{
  const ctx = fresh();
  const calls = [];
  ctx.goDest = (d) => calls.push("dest:" + d);
  ctx.openScreen = (s) => calls.push("screen:" + s);
  ctx.render = () => {};
  assert.strictEqual(
    ctx.shadowRouteDeepLink("sutra://shadow/mission/m-done"), true,
    "the mission link routes");
  assert(calls.includes("screen:shadow"), "it lands on Focus > Shadow");
  assert.strictEqual(ctx.S.shadowFocusMission, "m-done",
    "the plane highlight is still set");
  assert.strictEqual(ctx.S.shadowTaskSel, "m-done",
    "and the workspace opens the task the row named");

  /* end to end: the linked task is the one whose summary is drawn */
  ctx.S.goals = [];
  ctx.S.shadowMissions = [
    { id: "m-other", objective: "unrelated", state: "running",
      done_when: [] },
    DONE,
  ];
  assert(/3 of 3 checks passed/.test(ctx.shadowHomeHtml()),
    "the summary is on screen after following the link");
  console.log("ok 9 the Now row opens the task it is about");
}

/* ── COPY RESULT ─────────────────────────────────────────────────────────
   THE GAP (founder, 2026-09-15). The summary is the one legible account of
   what a finished task did, and it could not leave the pane: telling anyone
   else meant retyping it or drag-selecting across three nested divs. What
   is pinned below is that the text is the SAME summary (never a second
   rendering that could drift from it), that the clipboard is actually
   written, and that the founder is told either way. */

/* a click as the delegated listener really receives one. `closest` is
   selector-aware because the handler asks it three different questions on
   the way past ([data-shscreen], [data-shsend], [data-shcopydone]) and a
   stub that answers yes to all of them proves nothing. */
function clickCopy(ctx, mid, opts){
  const el = { dataset: { shcopydone: mid } };
  el.closest = (sel) => sel === "[data-shcopydone]" ? el : null;
  const target = (opts && opts.viaChild)
    /* the label text node inside the button: no dataset of its own, which
       is exactly the bug closest() exists to prevent here */
    ? { dataset: {}, closest: (sel) => sel === "[data-shcopydone]" ? el : null }
    : el;
  return ctx.listeners.click({ target, stopPropagation(){} });
}

function withClipboard(ctx, impl){
  const writes = [];
  ctx.navigator = { clipboard: { writeText: async (t) => {
    if (impl) return impl(t);
    writes.push(t);
  } } };
  return writes;
}

const flush = () => new Promise(r => setTimeout(r, 0));

/* advance the fake clock: run every timer that is still due, once */
function fireTimers(ctx){
  let n = 0;
  for (const t of ctx.timers) if (!t.cancelled && !t.fired){ t.fired = 1; t.fn(); n++; }
  return n;
}
/* the live region, if the code has made one yet */
const announcer = (ctx) => ctx.nodes.find(n => n && n.id === "shdoneannounce");
/* the copy control as rendered, pulled straight out of the pane's markup */
function copyBtn(ctx, m){
  const h = ctx.shadowCompletionHtml(m || DONE);
  const i = h.indexOf("<button");
  return h.slice(i, h.indexOf("</button>", i) + 9);
}

(async () => {

/* 10. the text IS the summary -- same source, same order, no markup */
{
  const ctx = fresh();
  const t = ctx.shadowCompletionText(DONE);
  assert.strictEqual(t.split("\n")[0], "Done — 3 of 3 checks passed",
    "the headline leads, as it does on screen");
  assert(t.indexOf("get the EMI check green") !== -1, "the objective is named");
  assert(t.indexOf("5 of 20 turns used.") !== -1, "the budget it spent");
  SUMMARY.checks.forEach(k =>
    assert(t.indexOf(k.check) !== -1, "check missing: " + k.check));
  assert(t.indexOf("✓ EMI-OK — found in the chat") !== -1,
    "a check carries its verdict and the server's HOW copy");
  assert(t.indexOf("you confirmed it · founder") !== -1,
    "a confirmation still names who signed it off");
  assert(t.indexOf("\n    …the suite reports EMI-OK for every tenant…") !== -1,
    "the quoted artifact is indented under its check");
  assert(!/[<>]/.test(t), "it is text, not markup");
  assert.strictEqual((t.match(/✓/g) || []).length, 3, "three ticks");
  /* the order on the clipboard is the order on screen */
  assert(t.indexOf("EMI-OK") < t.indexOf("pytest test_emi.py passes")
    && t.indexOf("pytest test_emi.py passes") < t.indexOf("the copy reads right"),
    "checks keep the server's order");
  console.log("ok 10 the result renders as text");
}

/* 11. nothing to copy -> no text, and an unmet check is marked unmet */
{
  const ctx = fresh();
  assert.strictEqual(ctx.shadowCompletionText({ id: "m-1" }), "",
    "a mission without the field has no result text");
  assert.strictEqual(ctx.shadowCompletionText(null), "", "null is safe");
  const t = ctx.shadowCompletionText({ id: "m-x", completion: {
    headline: "1 of 2 checks passed", objective: "o",
    turns_used: 1, max_turns: 4,
    checks: [{ check: "found it", met: true, how: "found in the chat" },
             { check: "not yet", met: false, how: "still outstanding" }] } });
  assert(t.indexOf("✓ found it") !== -1, "the met check ticks");
  assert(t.indexOf("✗ not yet — still outstanding") !== -1,
    "the unmet one says so without the CSS");
  console.log("ok 11 the text never invents a verdict");
}

/* 12. the control is THERE, on the block and on the card */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml(DONE);
  assert(/data-shcopydone="m-done"/.test(h), "the button names its mission");
  assert(/Copy result/.test(h), "and says what it does");
  assert(/3 of 3 checks passed/.test(h), "the headline is still there");
  const card = ctx.shadowTaskCardHtml(DONE);
  assert(/data-shcopydone="m-done"/.test(card), "the card carries it");
  /* a task that has not finished has no result to copy */
  const live = Object.assign({}, DONE, { state: "running" });
  delete live.completion;
  assert(!/data-shcopydone/.test(ctx.shadowTaskCardHtml(live)),
    "a live task offers no copy");
  console.log("ok 12 the copy action is on a finished card, and only there");
}

/* 13. CLICKING IT COPIES -- through the real delegated listener */
{
  for (const viaChild of [false, true]){
    const ctx = fresh();
    ctx.S.shadowMissions = [DONE];
    const writes = withClipboard(ctx);
    clickCopy(ctx, "m-done", { viaChild });
    await flush();
    assert.strictEqual(writes.length, 1, "exactly one write per click");
    assert.strictEqual(writes[0], ctx.shadowCompletionText(DONE),
      "what lands on the clipboard is the summary that is on screen");
    /* ...and the founder is TOLD */
    assert.strictEqual(ctx.S.shadowResultCopied.ok, true, "it worked");
    assert.strictEqual(ctx.S.shadowResultCopied.id, "m-done", "on this task");
    assert(ctx.renders > 0, "and a repaint was asked for");
    const h = ctx.shadowCompletionHtml(DONE);
    assert(/Copied/.test(h) && /shdonecopy ok/.test(h),
      "the button says Copied" + (viaChild ? " (clicked on the label)" : ""));
    assert(!/>Copy result</.test(h), "and is not still offering the action");

    /* the feedback belongs to ONE record: another finished task on screen
       still offers the action */
    const other = Object.assign({}, DONE, { id: "m-two" });
    assert(/Copy result/.test(ctx.shadowCompletionHtml(other)),
      "another task's button is untouched");

    /* and it goes back, on the timer it set */
    assert.strictEqual(ctx.timers.length, 1, "one timer, not one per render");
    ctx.timers[0].fn();
    assert.strictEqual(ctx.S.shadowResultCopied, null, "the flag clears");
    assert(/Copy result/.test(ctx.shadowCompletionHtml(DONE)),
      "the button offers the action again");
  }
  console.log("ok 13 clicking copies the result, and says so");
}

/* 14. A REFUSED CLIPBOARD IS SHOWN, NOT SWALLOWED. A button that says
       nothing after a click is the disease this pane keeps curing. */
{
  const ctx = fresh();
  ctx.S.shadowMissions = [DONE];
  withClipboard(ctx, async () => { throw new Error("denied"); });
  assert.strictEqual(await ctx.shadowCopyResult("m-done"), false,
    "the failure is reported");
  assert.strictEqual(ctx.S.shadowResultCopied.ok, false, "and recorded");
  const h = ctx.shadowCompletionHtml(DONE);
  assert(/Copy failed/.test(h) && /shdonecopy bad/.test(h),
    "the button says it failed");

  /* NEITHER api -- no navigator.clipboard and no execCommand -- reads the
     same way. This is the only case that may still say "Copy failed". */
  const ctx2 = fresh();
  ctx2.S.shadowMissions = [DONE];
  assert.strictEqual(await ctx2.shadowCopyResult("m-done"), false,
    "no clipboard and no fallback is a failure, not a throw");
  assert(/Copy failed/.test(ctx2.shadowCompletionHtml(DONE)),
    "and it is still said out loud");

  /* a mission with nothing to copy writes nothing and claims nothing */
  const ctx3 = fresh();
  ctx3.S.shadowMissions = [{ id: "m-old", objective: "no summary" }];
  const writes = withClipboard(ctx3);
  assert.strictEqual(await ctx3.shadowCopyResult("m-old"), false,
    "an unfinished record copies nothing");
  assert.strictEqual(await ctx3.shadowCopyResult("m-gone"), false,
    "and an id that is not there is safe");
  assert.strictEqual(writes.length, 0, "the clipboard was never touched");
  assert(!ctx3.S.shadowResultCopied, "and nothing was claimed");
  console.log("ok 14 a copy that could not happen says so");
}

/* 15. THE FALLBACK ACTUALLY COPIES. navigator.clipboard is undefined on an
       insecure origin and refused on an unfocused page -- both reachable
       whenever the panel is opened outside the Electron shell. On that path
       the founder must still get the text, not an apology. */
{
  /* a document whose execCommand("copy") really copies the selected node,
     which is what a browser without the async API gives us */
  function withExecCommand(ctx, succeeds){
    const seen = { made: 0, mounted: 0, removed: 0, selected: 0, copied: [] };
    let live = null;
    ctx.document.createElement = (tag) => {
      seen.made++;
      const node = { tag, value: "", attrs: {}, style: {},
        setAttribute(k, v){ node.attrs[k] = v; },
        select(){ seen.selected++; },
        remove(){ seen.removed++; live = null; } };
      live = node;
      return node;
    };
    /* tag-aware: the live region mounts a <div> on this same body, and
       "mounted exactly once" is a claim about the copy TEXTAREA */
    ctx.document.body.appendChild = (n) => {
      ctx.nodes.push(n);
      if (n && n.tag === "textarea") seen.mounted++;
    };
    ctx.document.execCommand = (cmd) => {
      if (cmd !== "copy" || !succeeds) return false;
      seen.copied.push(live ? live.value : null);
      return true;
    };
    return seen;
  }

  /* no async clipboard at all -> the old API carries it */
  const ctx = fresh();
  ctx.S.shadowMissions = [DONE];
  const seen = withExecCommand(ctx, true);
  assert.strictEqual(await ctx.shadowCopyResult("m-done"), true,
    "the fallback reports success");
  assert.strictEqual(seen.copied.length, 1, "exactly one copy");
  assert.strictEqual(seen.copied[0], ctx.shadowCompletionText(DONE),
    "and it copied the SAME summary the async path would have");
  assert.strictEqual(seen.selected, 1, "the node was selected first");
  assert.strictEqual(seen.removed, 1, "and taken back out of the document");
  assert.strictEqual(seen.mounted, 1, "having been mounted exactly once");
  assert.strictEqual(ctx.S.shadowResultCopied.ok, true, "the founder is told");
  assert(/Copied/.test(ctx.shadowCompletionHtml(DONE)),
    "the button says Copied on the fallback path too");

  /* an async clipboard that THROWS (a refused page) falls back as well */
  const ctx2 = fresh();
  ctx2.S.shadowMissions = [DONE];
  withClipboard(ctx2, async () => { throw new Error("denied"); });
  const seen2 = withExecCommand(ctx2, true);
  assert.strictEqual(await ctx2.shadowCopyResult("m-done"), true,
    "a refusal is retried on the old API, not surfaced as a failure");
  assert.strictEqual(seen2.copied[0], ctx2.shadowCompletionText(DONE),
    "with the same text");

  /* execCommand that REFUSES is still reported honestly, and still cleans up */
  const ctx3 = fresh();
  ctx3.S.shadowMissions = [DONE];
  const seen3 = withExecCommand(ctx3, false);
  assert.strictEqual(await ctx3.shadowCopyResult("m-done"), false,
    "a refused fallback is a failure");
  assert.strictEqual(seen3.copied.length, 0, "nothing was copied");
  assert.strictEqual(seen3.removed, 1, "and no stray node was left behind");
  assert(/Copy failed/.test(ctx3.shadowCompletionHtml(DONE)),
    "which is said out loud");

  /* and a fallback that THROWS mid-way still removes its node */
  const ctx4 = fresh();
  ctx4.S.shadowMissions = [DONE];
  const seen4 = withExecCommand(ctx4, true);
  ctx4.document.execCommand = () => { throw new Error("boom"); };
  assert.strictEqual(await ctx4.shadowCopyResult("m-done"), false,
    "a throwing fallback is caught");
  assert.strictEqual(seen4.removed, 1, "the finally still ran");
  console.log("ok 15 the fallback copies when the clipboard API is missing");
}

/* 16. THE NEWS REACHES SOMEBODY WHO CANNOT SEE THE BUTTON.
       The label change is the sighted feedback and was the only feedback:
       `aria-live` sat on the button itself, and this pane repaints by
       replacing innerHTML, so that node was destroyed and rebuilt on every
       render -- a live region that did not exist before the text changed
       announces nothing. The region is outside the markup now, made once. */
{
  const ctx = fresh();
  ctx.S.shadowMissions = [DONE];

  /* idle: the control offers the action, is not disabled, and says what it
     is to a screen reader as well as to an eye */
  const idle = copyBtn(ctx);
  assert(/data-shcopystate="idle"/.test(idle), "idle state is declared");
  assert(/aria-label="Copy result — this summary as text"/.test(idle),
    "and named for a screen reader");
  assert(/>Copy result</.test(idle), "with the visible label inside the name");
  assert(!/disabled/.test(idle), "a control that can be used is never disabled");
  assert(!announcer(ctx), "nothing is announced before anything happens");

  /* copied */
  const writes = withClipboard(ctx);
  clickCopy(ctx, "m-done");
  await flush();
  const okBtn = copyBtn(ctx);
  assert(/data-shcopystate="copied"/.test(okBtn), "the state is on the node");
  assert(/class="btn shdonecopy ok"/.test(okBtn), "and in its class");
  assert(/>Copied</.test(okBtn), "the label says it");
  assert(/aria-label="Copied — the result is on your clipboard"/.test(okBtn),
    "the accessible name says it too");
  assert(!/disabled/.test(okBtn), "and the control stays usable");
  const live = announcer(ctx);
  assert(live, "a live region was created");
  assert.strictEqual(live.attrs.role, "status", 'role="status"');
  assert.strictEqual(live.attrs["aria-live"], "polite", 'aria-live="polite"');
  assert.strictEqual(live.textContent, "Result copied to the clipboard.",
    "and it carries the news");
  assert.strictEqual(writes.length, 1, "one copy, one announcement");

  /* IT IS NOT INSIDE THE REPAINTED MARKUP -- the whole reason it works */
  assert(!/shdoneannounce/.test(ctx.shadowCompletionHtml(DONE)),
    "the region must not be rebuilt by the pane's own render");

  /* failed */
  const ctx2 = fresh();
  ctx2.S.shadowMissions = [DONE];
  withClipboard(ctx2, async () => { throw new Error("denied"); });
  await ctx2.shadowCopyResult("m-done");
  const bad = copyBtn(ctx2);
  assert(/data-shcopystate="failed"/.test(bad), "the failure is a state");
  assert(/class="btn shdonecopy bad"/.test(bad), "with its own class");
  assert(/>Copy failed</.test(bad), "and its own label");
  assert(/aria-label="Copy failed — the result is not on your clipboard"/.test(bad),
    "which does not lie to a screen reader about where the text is");
  assert(!/disabled/.test(bad), "a failed copy leaves the button clickable");
  assert.strictEqual(announcer(ctx2).textContent,
    "The result could not be copied to the clipboard.", "and is announced");

  /* one region, however many copies */
  fireTimers(ctx2);
  await ctx2.shadowCopyResult("m-done");
  assert.strictEqual(ctx2.nodes.filter(n => n && n.id === "shdoneannounce").length,
    1, "the live region is made once and written to after that");
  console.log("ok 16 the copy is announced, not just drawn");
}

/* 17. THE FEEDBACK IS TRANSIENT AND SELF-HEALING. Fake timers, no sleeps. */
{
  /* success reverts */
  const ctx = fresh();
  ctx.S.shadowMissions = [DONE];
  withClipboard(ctx);
  clickCopy(ctx, "m-done");
  await flush();
  assert(/>Copied</.test(copyBtn(ctx)), "…Copied…");
  assert.strictEqual(fireTimers(ctx), 1, "one timer was due");
  const back = copyBtn(ctx);
  assert(/>Copy result</.test(back), "…and back to Copy result");
  assert(/data-shcopystate="idle"/.test(back), "the state went with it");
  assert(!/shdonecopy ok/.test(back), "the green is gone");
  assert(!/disabled/.test(back), "and it is clickable again");
  assert.strictEqual(announcer(ctx).textContent, "",
    "the announcement is cleared, so the next copy is a change and speaks");

  /* clickable again really means it COPIES again */
  clickCopy(ctx, "m-done");
  await flush();
  assert(/>Copied</.test(copyBtn(ctx)), "a second click copies again");
  assert.strictEqual(announcer(ctx).textContent, "Result copied to the clipboard.",
    "and is announced again");

  /* failure reverts the same way -- it must not be a dead end */
  const ctx2 = fresh();
  ctx2.S.shadowMissions = [DONE];
  withClipboard(ctx2, async () => { throw new Error("denied"); });
  clickCopy(ctx2, "m-done");
  await flush();
  assert(/>Copy failed</.test(copyBtn(ctx2)), "…Copy failed…");
  assert.strictEqual(fireTimers(ctx2), 1, "the failure is on a timer too");
  assert(/>Copy result</.test(copyBtn(ctx2)), "…and it heals");

  /* A SECOND CLICK AFTER A FAILURE CAN STILL SUCCEED, and the failure's own
     timer must not survive to wipe the success early. */
  const ctx3 = fresh();
  ctx3.S.shadowMissions = [DONE];
  withClipboard(ctx3, async () => { throw new Error("denied"); });
  clickCopy(ctx3, "m-done");
  await flush();
  assert.strictEqual(ctx3.S.shadowResultCopied.ok, false, "the first click failed");
  const writes = withClipboard(ctx3);           /* the clipboard comes back */
  clickCopy(ctx3, "m-done");
  await flush();
  assert.strictEqual(writes.length, 1, "the retry wrote");
  assert.strictEqual(writes[0], ctx3.shadowCompletionText(DONE),
    "the same text the first click could not write");
  assert.strictEqual(ctx3.S.shadowResultCopied.ok, true, "and it says so");
  assert(/>Copied</.test(copyBtn(ctx3)), "the button recovered");
  assert.strictEqual(ctx3.timers[0].cancelled, true,
    "the failure's timer was cancelled by the retry");
  assert(ctx3.cleared.includes(ctx3.timers[0].id), "explicitly, by id");
  assert.strictEqual(fireTimers(ctx3), 1, "only the retry's timer is live");
  assert(/>Copy result</.test(copyBtn(ctx3)), "which then heals as normal");
  console.log("ok 17 the feedback clears itself, and the control comes back");
}

console.log("test_shadow_completion_ui.js: all green");

})().catch(e => { console.error(e); process.exit(1); });
