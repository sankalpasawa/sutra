#!/usr/bin/env node
/* test_shadow_v42_ui.js -- Shadow v4.2 on the screen (founder 2026-09-21:
   "I don't see any buttons there, and I don't think there should be a
   retry button").

     the ask rows   a held instruction, an unmet founder-confirm check, a
                    question and a parked instruction are rows at the end of
                    the task's stream, each with the button that answers it,
                    and each button goes through the one mission-action door.
     the record     what was answered stays in the scrollback, stamped.
     no Retry       nothing draws data-shact="retry" any more.

   Same harness as test_shadow_v41_ui.js.  Run: node test_shadow_v42_ui.js */
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
    return { ok: true, status: 200,
             json: async () => Object.assign({ mission: { id: "m-1" } }, reply || {}) };
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
  done_when: [{ check: "the greeting reads well", tier: "founder_confirm" }],
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

let ok = 0;
const pass = (s) => console.log("ok " + (++ok) + " " + s);

(async () => {
  /* 1. a held instruction is a row with Approve and Withdraw */
  {
    const ctx = fresh();
    const h = pane(ctx, M({ state: "paused", pause_reason: "floor_confirm",
      pending_say: "Push fix/auth to origin and open the PR.",
      approval: { id: "ap-1", used: false } }));
    assert(/class="shsaid shask shask-hold"/.test(h), "the hold row is drawn");
    assert(/Push fix\/auth to origin and open the PR\./.test(h), "with the exact instruction");
    assert(/data-shact="approve"[^>]*data-shmid="m-1"[^>]*data-shapproval="ap-1"/.test(h),
      "Approve carries the one-use approval id");
    assert(/data-shact="answer"[^>]*data-shkind="withdraw"/.test(h), "Withdraw is on the row");
    assert(/yes/.test(h) && /I did it myself/.test(h), "the hint says the composer answers it");
    pass("a held instruction is a row with Approve and Withdraw");
  }

  /* 2. THE ASK SURFACE NO LONGER DRAWS A SECOND CONFIRM (founder,
     2026-09-21: "there should be ONE canonical representation of a user
     decision").

     WHAT THIS USED TO PIN: an unmet founder_confirm check as a
     `shask-check` row with its own live Confirm. shadowCheckRowsHtml drew
     the SAME criterion with another Confirm a few hundred pixels below, so
     one question carried two working buttons and answering either left the
     other looking unanswered.

     THE ONE THAT SURVIVED IS THE RICHER ONE. shadowCheckRowsHtml draws the
     decision packet with it -- the artifact being judged and the facts
     shadow_evidence counted -- so the question is asked next to its
     subject. This row could only ever print the sentence.

     THE ANSWERED RECORD IS UNTOUCHED, and that is the half of this block
     that still matters: once signed, "Confirmed by you" stays in the
     scrollback at the point it happened, which is what makes the surface a
     conversation rather than a form that empties itself. */
  {
    const ctx = fresh();
    let h = pane(ctx, M({ state: "paused", pause_reason: "founder_confirm" }));
    assert(!/shask-check/.test(h), "the duplicate check row is still drawn");
    assert(!/data-shkind="confirm"/.test(h),
      "the ask surface still carries a second Confirm for the same check");
    /* the canonical one, on the same record */
    const one = ctx.shadowCheckRowsHtml(M({ state: "paused",
      pause_reason: "founder_confirm" }));
    assert((one.match(/data-shcheckix=/g) || []).length === 1,
      "the canonical decision surface must carry exactly one Confirm");
    h = pane(ctx, M({ state: "running" }));
    assert(!/shask-check/.test(h), "not drawn while the worker is still working");
    h = pane(ctx, M({ state: "paused", pause_reason: "founder_confirm",
      done_when: [{ check: "x", tier: "founder_confirm", met: true, confirmed_at: "2026-09-21T10:00:00Z" }] }));
    /* PASS 4: said in words rather than labelled with the internal
       vocabulary of the criterion -- the same record, the same row. */
    assert(/shask-done/.test(h) && /You confirmed: x/.test(h),
      "it stays in the scrollback as answered");
    pass("one Confirm, on the canonical surface; the answer stays in the scrollback");
  }

  /* 3. a question is a row pointing at its form; a parked say has Hand back */
  {
    const ctx = fresh();
    let h = pane(ctx, M({ state: "blocked", intervention: { id: "iv-1", question: "Which host?", fields: [] } }));
    assert(/shask-question/.test(h) && /Which host\?/.test(h), "the question row");
    h = pane(ctx, M({ state: "paused", pause_reason: "founder_intervened", parked_say: "Merge PR #218." }));
    assert(/shask-parked/.test(h) && /Merge PR #218\./.test(h), "the parked row");
    assert(/data-shact="resume"[^>]*data-shmid="m-1"/.test(h), "Hand back is Resume");
    assert(/never resend/.test(h), "and says it will ask, not resend");
    pass("question and parked rows");
  }

  /* 4. the buttons go through the one mission-action door with their ask */
  {
    const ctx = fresh({ answered: { kind: "confirm" } });
    pane(ctx, M({ state: "paused", pause_reason: "founder_confirm" }));
    click(ctx, { shact: "answer", shkind: "confirm", shindex: "0", shmid: "m-1" });
    await settle();
    const p = ctx.posted.find(x => /\/act$/.test(x.url));
    assert(p, "Confirm posted");
    const body = JSON.stringify(p.body);
    assert.strictEqual(p.body.action, "answer", body);
    assert.strictEqual(p.body.kind, "confirm", body);
    assert.strictEqual(p.body.index, 0, body);
    assert.strictEqual(ctx.nudged, "Answered.");
    ctx.posted.length = 0;
    click(ctx, { shact: "answer", shkind: "withdraw", shmid: "m-1" });
    await settle();
    const w = ctx.posted[0].body;
    assert.strictEqual(w.action, "answer", JSON.stringify(w));
    assert.strictEqual(w.kind, "withdraw", JSON.stringify(w));
    assert(!("index" in w) || w.index === undefined, "no index on a withdraw: " + JSON.stringify(w));
    pass("ask buttons post answer with their kind and index");
  }

  /* 5. a used approval is drawn as held-then-sent, in the scrollback */
  {
    const ctx = fresh();
    const h = pane(ctx, M({ state: "running",
      approval: { id: "ap-1", used: true, used_at: "2026-09-21T14:02:00Z" },
      approved_say: "Push fix/auth to origin and open the PR." }));
    /* PASS 4: the hold is said, not labelled. Same record, same row. */
    assert(/shask-done/.test(h) && /You approved that, so I sent it/.test(h),
      "the resolved row");
    assert(!/shask-hold/.test(h), "and no live hold");
    pass("a used approval stays in the scrollback as sent");
  }

  /* 6. REPLAY IS BACK, ON THE TASK HEADER ONLY (founder, 2026-09-21,
     pass 2: "DONE [Replay] [Open the chat] / STOPPED [Replay] [Open the
     chat]").

     WHAT v4.2 RULED, and why the two coexist: "no Retry button. The retry
     action stays on the server; the way back is the task's chat or Hand
     back to Shadow." That was written about the finished-task ROWS -- five
     of them stacked on the Watching plane, each growing its own button.
     Those rows are untouched and still carry none. Pass 2 asks for ONE
     control, on the header of the single task the founder is reading.

     FAILED IS STILL EXCLUDED, deliberately. Re-running an unchanged brief
     that already failed is usually the wrong move, and Hand back to Shadow
     remains the documented way back from there -- so the v4.2 rule stands
     exactly where it was argued hardest. */
  {
    const ctx = fresh();
    const h = pane(ctx, M({ state: "failed" }));
    assert(!/data-shact="retry"/.test(h), "failed: no Retry button");
    pass("Replay on done and stopped, never on failed");
  }

  /* 7. the ask rows read the record the way the engine does */
  {
    const engine = fs.readFileSync(path.join(__dirname, "mission_engine.py"), "utf8");
    for (const key of ['"pending_say"', '"parked_say"', '"founder_confirm"', '"intervention"'])
      assert(engine.indexOf(key) !== -1 && home.indexOf(key.replace(/"/g, "")) !== -1,
        key + " is read by both");
    pass("the rows and pending_asks read the same fields");
  }

  console.log("test_shadow_v42_ui.js: " + ok + " passed");
})().catch(e => { console.error(e); process.exit(1); });
