#!/usr/bin/env node
/* THE CONFIRMATION CARRIES ITS OWN EVIDENCE (founder, 2026-09-21).
 *
 * THE FAILURE. Shadow asked "does this ten-line ranking work as the greatest
 * premier-class riders ever?" and the ten riders existed only in the worker's
 * chat. The founder was asked to approve a list they could not see.
 *
 * WHAT THIS PINS is the render half: `m.decision` -- the packet the engine
 * stamps -- is drawn on the same surface as the Confirm button, above the
 * check rows, with nothing composed client-side.
 *
 * Run: node test_shadow_decision_ui.js
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const overlay = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn)=>({fn}),
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    escAttr: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"),
    SCREENS: {}, TITLES: {}, S: {},
    listeners: {},
    document: { addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; } },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  return ctx;
}

const RIDERS = ["Giacomo Agostini", "Valentino Rossi", "Marc Marquez",
                "Mike Hailwood", "Eddie Lawson", "Mick Doohan", "Geoff Duke",
                "Casey Stoner", "Kenny Roberts", "Jorge Lorenzo"];
const ASK = "Does this ten-line ranking work as the greatest "
          + "premier-class riders ever?";

function rankingMission(){
  return {
    id: "m-r", objective: "ten greatest riders", state: "paused",
    pause_reason: "founder_confirm",
    done_when: [
      { tier: "verify", check: "the doc holds exactly 10 lines", met: true },
      { tier: "founder_confirm", check: ASK },
    ],
    decision: {
      at: "2026-09-21T10:00:00Z",
      asks: [{ index: 1, check: ASK }],
      established: [{ check: "the doc holds exactly 10 lines", met: true,
                      how: "10 lines" }],
      artifacts: [{ path: "riders.txt", kind: "text",
                    text: RIDERS.join("\n") + "\n", truncated: false,
                    facts: { lines: 10, distinct_non_empty_lines: 10 } }],
      missing: "",
    },
  };
}

/* 1. the ranking is READABLE where the question is asked */
{
  const ctx = fresh();
  const h = ctx.shadowCheckRowsHtml(rankingMission());
  RIDERS.forEach(r => assert(h.indexOf(r) !== -1,
    r + " is not on the confirmation surface"));
  assert(/riders\.txt/.test(h), "the artifact names itself");
  assert(/10 lines/.test(h), "the measured facts ride along");
  console.log("ok 1 the ten riders are visible in the confirmation");
}

/* 2. ORDER SURVIVES. A ranking is an order; a set is not an answer. */
{
  const ctx = fresh();
  const h = ctx.shadowCheckRowsHtml(rankingMission());
  const at = RIDERS.map(r => h.indexOf(r));
  assert.deepStrictEqual(at, at.slice().sort((a, b) => a - b),
    "the riders must render in the file's own order");
  console.log("ok 2 the order is preserved, not just the names");
}

/* 3. THE EVIDENCE PRECEDES THE CONTROL that acts on it. Asking before
      showing the subject is the bug this whole change is about. */
{
  const ctx = fresh();
  const h = ctx.shadowCheckRowsHtml(rankingMission());
  const art = h.indexOf("Giacomo Agostini");
  const btn = h.indexOf('data-shcheckix="1"');
  assert(art > -1 && btn > -1 && art < btn,
    "the artifact must be readable BEFORE the Confirm button");
  console.log("ok 3 the evidence comes before the button");
}

/* 4. a record with NO packet renders exactly what it used to */
{
  const ctx = fresh();
  const m = rankingMission();
  delete m.decision;
  const h = ctx.shadowCheckRowsHtml(m);
  assert(/data-shcheckix="1"/.test(h), "the sign-off still renders");
  assert(!/shdec\b/.test(h), "and no empty evidence block is drawn");
  assert.strictEqual(ctx.shadowDecisionHtml(m), "");
  assert.strictEqual(ctx.shadowDecisionHtml(null), "");
  console.log("ok 4 no packet, no change");
}

/* 5. THE VISUAL CASE: the image is provided, not described */
{
  const ctx = fresh();
  const m = rankingMission();
  m.decision.artifacts = [{ path: "shot.png", kind: "image", too_big: false,
                            bytes: 120, data_uri: "data:image/png;base64,AAA" }];
  const h = ctx.shadowDecisionHtml(m);
  assert(/<img/.test(h), "a visual decision needs the visual");
  assert(/data:image\/png;base64,AAA/.test(h), "the preview is inlined");
  /* ...and one too large states the fact rather than drawing a broken img */
  m.decision.artifacts = [{ path: "big.png", kind: "image", too_big: true,
                            bytes: 9000000, data_uri: "" }];
  const big = ctx.shadowDecisionHtml(m);
  assert(!/<img/.test(big), "no broken image is drawn");
  assert(/too large to preview/.test(big), "and it says why");
  console.log("ok 5 the visual case shows the visual");
}

/* 6. TRUNCATION IS ANNOUNCED. Nobody approves a list believing they saw
      all of it. */
{
  const ctx = fresh();
  const m = rankingMission();
  m.decision.artifacts[0].truncated = true;
  const h = ctx.shadowDecisionHtml(m);
  /* PASS 8 (founder, 2026-09-21): the CLAIM is unchanged -- a cut preview
     must still say it is cut -- and the renderer's instruction ("shown in
     part -- open the task's chat for the whole file") is gone with the rest
     of the internal note vocabulary. What remains is the ordinary
     typographic mark for "there is more". */
  assert(/class="shdeccut"/.test(h), "a cut artifact says so");
  assert(!/shown in part/.test(h), "and not in the renderer's words");
  console.log("ok 6 a bounded preview announces itself");
}

/* 7. THE NO-CONTEXT CASE says what is missing */
{
  const ctx = fresh();
  const m = rankingMission();
  m.decision.artifacts = [];
  m.decision.established = [];
  m.decision.missing = "Shadow could not gather the artifact this question "
                     + "is about — no file it checked is readable.";
  const h = ctx.shadowCheckRowsHtml(m);
  assert(/could not gather/.test(h),
    "an impossible question must state its own gap");
  assert(/data-shcheckix="1"/.test(h), "and the question is still asked");
  console.log("ok 7 the no-context case is honest");
}

/* 8. THE ARTIFACT IS NOT RE-RENDERED AS MARKDOWN. A founder approving a
      ranking must see the literal lines, and a file that happens to contain
      markdown must not be reformatted on the one surface where its exact
      shape is what is being judged. */
{
  const ctx = fresh();
  const m = rankingMission();
  m.decision.artifacts[0].text = "# Heading\n- one\n- two\n";
  const h = ctx.shadowDecisionHtml(m);
  assert(/<pre class="shdectext">/.test(h), "it is drawn as preformatted");
  assert(/# Heading/.test(h), "the hash is literal, not a heading");
  assert(!/<h1/.test(h), "nothing promoted it to markup");
  console.log("ok 8 the artifact is shown as it is");
}

/* 9. ESCAPING. Artifact content is a FILE -- it is whatever the work wrote,
      including angle brackets, and it must never become markup. */
{
  const ctx = fresh();
  const m = rankingMission();
  m.decision.artifacts[0].text = "<script>alert(1)</script>\n";
  m.decision.artifacts[0].path = "<img src=x>";
  const h = ctx.shadowDecisionHtml(m);
  assert(!/<script>/.test(h), "file content is never live markup");
  assert(/&lt;script&gt;/.test(h), "it is escaped and shown");
  console.log("ok 9 artifact content cannot become markup");
}

/* 10. ONLY THE HUMAN PART IS ASKED, and the settled rows stay folded --
       the 2026-09-20 rule still holds with the packet present. */
{
  const ctx = fresh();
  const h = ctx.shadowCheckRowsHtml(rankingMission());
  assert.strictEqual((h.match(/data-shcheckix=/g) || []).length, 1,
    "exactly one row is offered: the founder's own");
  assert(/shcheckfold/.test(h), "Shadow's settled row stays folded");
  console.log("ok 10 the packet did not reopen the fold");
}

/* ══ 11-16. INTERNAL VERIFICATION IS NOT THE USER-FACING RESULT ═════════
   founder, 2026-09-21: "do not show the user internal verification
   machinery ... those checks must continue to run internally exactly as
   before ... keep them available in the mission state/log/debug surfaces".
   So: nothing is removed, everything moves behind one disclosure. */

function doneMission(over){
  return Object.assign({
    id: "m-done", objective: "ten MotoGP stories", state: "done",
    target_mode: "new", target_session: "sess-1",
    completion: {
      headline: "3 of 3 checks passed", objective: "ten MotoGP stories",
      turns_used: 2, max_turns: 20,
      artifacts: ["motogp-top-10-news.md"],
      outcome: "Created motogp-top-10-news.md with 10 sourced MotoGP "
             + "stories from 15-21 September 2026.",
      checks: [
        { check: "the file exists", tier: "verify", met: true,
          how: "Shadow verified this" },
        { check: "it holds 10 lines", tier: "verify", met: true,
          how: "Shadow verified this" },
        { check: "every item is sourced", tier: "judge", met: true,
          how: "Shadow read the change and confirmed it" }],
    },
  }, over || {});
}

/* 11. the headline is a result, not a score */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml(doneMission());
  const above = h.split("shdoneverif")[0];
  /* PASS 7: a clean finish is a Shadow message, not a card -- so the
     heading it used to say Done in is gone with it. The claim below (no
     internal verification vocabulary above the fold) is unchanged and is
     now made of the message. */
  assert(/<div class="shsaidtext">Done/.test(above), "it says Done");
  assert(/shdonesay/.test(above), "as a message from Shadow");
  for (const banned of ["3 of 3", "checks passed", "Shadow settled itself",
                        "DONE-CHECK", "probe", "tier", "founder_confirm"]){
    assert(above.indexOf(banned) === -1,
      "internal verification language on the founder surface: " + banned);
  }
  console.log("ok 11 DONE leads with a result, not a check count");
}

/* 12. ...and the verification is still all there, one click away */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml(doneMission());
  assert(/shdoneverif/.test(h), "the fold exists");
  assert(/<summary>Verification<\/summary>/.test(h), "and is labelled plainly");
  const inside = h.slice(h.indexOf("shdoneverif"));
  for (const row of ["the file exists", "it holds 10 lines",
                     "every item is sourced"]){
    assert(inside.indexOf(row) !== -1, "verdict dropped: " + row);
  }
  assert(/2 of 20 turns used/.test(inside), "the turn cost is kept, inside");
  console.log("ok 12 every verdict is preserved behind the fold");
}

/* 13. what was produced is on the surface */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml(doneMission());
  assert(/motogp-top-10-news\.md/.test(h.split("shdoneverif")[0]),
    "the founder is told where the result landed");
  /* a mission whose server recorded none simply has no file line */
  const none = doneMission();
  delete none.completion.artifacts;
  assert(!/shdonefiles/.test(ctx.shadowCompletionHtml(none)),
    "and nothing is invented when there is no artifact");
  console.log("ok 13 the artifact is named on the DONE surface");
}

/* 14. A CAVEAT IS PART OF THE ANSWER. A check that did NOT pass qualifies
   the result, so it stays outside the fold -- this is the one piece of
   verification a founder genuinely needs on the surface. */
{
  const ctx = fresh();
  const m = doneMission();
  m.completion.checks[2].met = false;
  m.completion.checks[2].how = "still outstanding";
  const h = ctx.shadowCompletionHtml(m);
  const above = h.split("shdoneverif")[0];
  /* PASS 3 (founder, 2026-09-21): "even in summary -- don't show user stuff
     he doesn't care about (Done checks and all)." The surface says that
     something did not pass and where to look; the criterion itself is in
     the Verification fold, whole, one click away. */
  assert(/did not pass/.test(above), "an unmet check is surfaced");
  assert(above.indexOf("every item is sourced") === -1,
    "the criterion itself must stay in Verification");
  assert(h.split("shdoneverif")[1].indexOf("every item is sourced") !== -1,
    "...and it must still be there, whole");
  console.log("ok 14 a failed check is a caveat, not hidden bookkeeping");
}

/* 15. THE CONFIRMATION LEADS WITH THE DECISION, not with Shadow's state */
{
  const ctx = fresh();
  const h = ctx.shadowCheckRowsHtml(rankingMission());
  assert(/Shadow needs your decision/.test(h), "it leads with the ask");
  for (const banned of ["Shadow's own checks have passed", "sign these off",
                        "founder_confirm", "probe", "tier", "evidence blob",
                        "still running", "you confirmed"]){
    assert(h.indexOf(banned) === -1,
      "implementation vocabulary on the confirmation: " + banned);
  }
  console.log("ok 15 the confirmation is plain English");
}

/* 16. THE SEMANTIC QUESTION IS NOT REWRITTEN. Presentation changed; the
   criterion the founder signs is still the server's own string. */
{
  const ctx = fresh();
  const h = ctx.shadowCheckRowsHtml(rankingMission());
  assert(h.indexOf(ASK) !== -1,
    "the criterion is rendered verbatim -- rewording it would change what "
    + "was agreed to");
  console.log("ok 16 the question itself is untouched");
}

/* 17. THE WORKER'S TRANSCRIPT IS NOT DUMPED INTO THE CONFIRMATION. Only
   what the packet carries reaches this surface, and the packet is built
   from files (see test_shadow_decision_packet.py). */
{
  const ctx = fresh();
  const m = rankingMission();
  m.result_excerpt = "I searched six sites and then decided the order.";
  m.last_instruction = "Continue toward: ten greatest riders.";
  m.pending_say = "Go on then.";
  const h = ctx.shadowCheckRowsHtml(m);
  for (const chatter of ["I searched six sites", "Continue toward",
                         "Go on then"]){
    assert(h.indexOf(chatter) === -1,
      "worker/control-plane text leaked into the confirmation: " + chatter);
  }
  console.log("ok 17 no worker chatter on the confirmation surface");
}

console.log("\nall decision-packet UI checks passed");
