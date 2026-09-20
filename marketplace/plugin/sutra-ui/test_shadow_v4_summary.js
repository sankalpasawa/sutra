#!/usr/bin/env node
/* test_shadow_v4_summary.js -- THE DONE CARD SHOWS THE ANSWER, NOT JUST THE
 * VERDICT.
 *
 * THE GAP THIS CLOSES (founder, 2026-09-17). A finished research task --
 * "Pull the very latest information about Valentino Rossi" -- reached
 *
 *     Done — 3 of 3 checks passed
 *     4 of 12 turns used.
 *     "Good coverage on the racing side …"        <- one sentence of gist
 *     ✓ ✓ ✓
 *
 * Every line true, and none of it the thing that was asked for. To read the
 * research the founder had to open the worker chat and hunt back through the
 * turns for the last message. For a research task that message IS the
 * deliverable; the card was showing a receipt for it.
 *
 * SO THE FIELD THAT ALREADY HELD IT IS DRAWN. `completion.outcome` is
 * stamped once, by mission_engine._complete, off
 * shadow_runner.last_worker_message -- the worker's own closing message,
 * verbatim. No new pipeline, no transcript re-read in JS, and in particular
 * NO message selection here: the safety property that makes this field safe
 * to display (evidence_messages drops Shadow's injected user turns, then a
 * role check keeps only assistant) lives upstream, and picking a message in
 * JavaScript would have thrown both guards away.
 *
 * WHAT MUST NOT MOVE. The one-line gist, the check rows and Copy result are
 * all pinned below, because the backend change this shipped alongside --
 * last_worker_message keeps newlines now, so the block can be markdown --
 * feeds the same field to all four.
 *
 * Run: node test_shadow_v4_summary.js
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
const helpers = fs.readFileSync(
  path.join(__dirname, "static", "js", "02-helpers.js"), "utf8");
const css = fs.readFileSync(
  path.join(__dirname, "static", "panel.css"), "utf8");

/* THE REAL RENDERER, NOT A STUB. 02-helpers.js will not run whole in a bare
   context -- it has an init chain that reaches PLANS.base -- so the mdHtml
   block is sliced out of the real file and run as itself. A stub would prove
   that this lane can render markdown, which is not the claim; the claim is
   that the DONE card renders markdown through the renderer the page ships.
   Sliced by its own delimiters, so the slice cannot silently drift to the
   wrong region: it starts at MD_URL_OK and ends at mdHtml's closing brace. */
function mdBlock(){
  const from = helpers.indexOf("const MD_URL_OK");
  assert(from !== -1, "MD_URL_OK marks the start of the markdown block");
  const at = helpers.indexOf("function mdHtml(src){", from);
  assert(at !== -1, "mdHtml is where the slice expects it");
  const end = helpers.indexOf("\n}\n", at);
  assert(end !== -1, "mdHtml's closing brace");
  return helpers.slice(from, end + 3);
}

function fresh(){
  const ctx = {
    console, Date,
    setTimeout: () => ({}), clearTimeout(){}, setInterval: () => ({}),
    scheduleRender(){},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    SCREENS: {}, TITLES: {}, S: {},
    listeners: {},
    document: {
      addEventListener(t, fn){ (ctx.listeners[t] = ctx.listeners[t] || []).push(fn); },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(mdBlock(), ctx);          /* mdHtml, as the page has it */
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  ctx.loadGoalTranscript = () => {};
  ctx.goalMessages = () => undefined;
  ctx.goalTranscriptHtml = () => "";
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  return ctx;
}

/* A real research answer, in the shape a worker actually writes one. */
const ROSSI = [
  "## Valentino Rossi — current status",
  "",
  "Rossi retired from MotoGP at the end of the **2021** season and now races",
  "cars full time.",
  "",
  "- Team: WRT, competing in GT3 machinery",
  "- Series: Fanatec GT World Challenge Europe",
  "- Source: [motorsport.com](https://www.motorsport.com/rossi)",
  "",
  "| Year | Series | Result |",
  "|---|---|---|",
  "| 2022 | GTWC | 4th |",
  "| 2023 | GTWC | 2nd |",
  "",
  "Three gaps remain before this is a complete picture.",
].join("\n");

const DONE = (over) => Object.assign({
  id: "m-1", objective: "Pull the very latest information about Valentino Rossi",
  state: "done", target_session: "sess-1", turns_used: 4, max_turns: 12,
  completion: {
    objective: "Pull the very latest information about Valentino Rossi",
    outcome: ROSSI,
    headline: "3 of 3 checks passed",
    checks_met: 3, checks_total: 3,
    checks: [
      { check: "the latest race result is quoted", tier: "verify",
        met: true, how: "Shadow checked this" },
      { check: "a source link is given", tier: "contains_artifact",
        met: true, how: "found in the reply", evidence: "motorsport.com" },
      { check: "you confirmed it", tier: "founder_confirm", met: true,
        how: "you confirmed it", by: "founder" },
    ],
    turns_used: 4, max_turns: 12, chat: "sess-1",
  },
}, over);

let ok = 0;
const pass = (s) => console.log("ok " + (++ok) + " " + s);

/* ══ 1. A DONE RESEARCH TASK RENDERS A SUMMARY BLOCK ════════════════════ */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml(DONE());
  assert(/class="shdonesummary"/.test(h), "the Summary block is drawn");
  assert(/class="shdonesumhead"[^>]*>Summary</.test(h),
    "and it is labelled Summary");
  assert(/class="shdonesumbody md"/.test(h),
    "the body carries .md so mdHtml's own rules style it");
  /* ABOVE the verdicts as of 2026-09-21, because the verdicts moved INTO a
     closed "Verification" fold: internal verification is no longer what a
     founder reads first. The Summary is the result and now leads. The rows
     themselves are unchanged and still rendered -- inside the fold. */
  assert(h.indexOf('class="shdonesummary"') < h.indexOf('shdoneverif'),
    "Summary sits ABOVE the verification fold, which is where the founder "
    + "reads the result");
  assert(/shdoneverif/.test(h), "and the verdicts are still rendered");
  pass("1: a DONE research task leads with the Summary, verdicts folded");
}

/* ══ 2. IT IS THE OUTCOME, NOT THE ONE-LINE GIST ════════════════════════ */
{
  const ctx = fresh();
  const m = DONE();
  const h = ctx.shadowCompletionHtml(m);
  const sum = h.slice(h.indexOf('class="shdonesummary"'));
  /* content from the MIDDLE and the END of the answer -- a gist would carry
     neither, because a gist is the first surviving sentence and nothing else */
  assert(/Fanatec GT World Challenge Europe/.test(sum),
    "a line from the middle of the answer is present");
  assert(/Three gaps remain before this is a complete picture/.test(sum),
    "and the last line of the answer too");
  /* and it really is longer than the gist, by a wide margin */
  const gist = ctx.shadowResultGist(ctx.shadowOutcomeFlat(m.completion.outcome));
  assert(sum.length > gist.length * 3,
    "the Summary is the answer, not a sentence of it");
  pass("2: the Summary carries completion.outcome, not the gist");
}

/* ══ 3. MARKDOWN IS RENDERED, NOT SHOWN AS SOURCE ═══════════════════════ */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml(DONE());
  const sum = h.slice(h.indexOf('class="shdonesummary"'));
  assert(/<h2 class="md-h">Valentino Rossi/.test(sum), "the heading is an h2");
  assert(/<li[^>]*>Team: WRT/.test(sum), "the list is a list");
  assert(/<table class="md-t">/.test(sum), "the table is a table");
  assert(/<th>Year<\/th>/.test(sum) && /<td>2nd<\/td>/.test(sum),
    "with its header and its cells");
  assert(/<strong>2021<\/strong>/.test(sum), "inline emphasis is applied");
  assert(/<a class="md-a" href="https:\/\/www\.motorsport\.com\/rossi"/.test(sum),
    "and the link is a link");
  /* the source markers are GONE -- this is rendered, not escaped source */
  assert(!/## Valentino/.test(sum), "no raw heading marker survives");
  assert(!/\|---\|/.test(sum), "no raw table separator survives");
  /* the CSS the block relies on really ships */
  assert(/\.shdonesummary\{/.test(css), "the block has its stylesheet rule");
  assert(/\.shdonesumbody\{/.test(css), "and so does its body");
  pass("3: the answer renders as markdown through the page's own mdHtml");
}

/* ══ 4. CONTROL-PLANE TEXT CANNOT BECOME THE SUMMARY ════════════════════ */
{
  const CONTROL = "Go get the current state of the WRT seat and report back.";
  const ctx = fresh();
  /* a record carrying Shadow's own control-plane fields, all populated */
  const m = DONE({
    pending_say: CONTROL,
    last_instruction: CONTROL,
    approval: { id: "ap-1", used: false },
    founder_says: [{ text: "don't touch the API", at: "2026-09-17T10:00:00Z" }],
  });
  const h = ctx.shadowCompletionHtml(m);
  const sum = h.slice(h.indexOf('class="shdonesummary"'));
  assert(!new RegExp(CONTROL.slice(0, 30)).test(sum),
    "Shadow's next instruction is not in the Summary");
  assert(!/don't touch the API/.test(sum), "nor a founder aside");
  assert(/Fanatec GT World Challenge Europe/.test(sum),
    "the worker's answer still is");
  /* THE STRUCTURAL GUARANTEE, not just this fixture: the renderer reads ONE
     field. A source check, because a future edit that reached for a
     transcript would pass every assertion above on this record and still
     re-open the hole the upstream guards exist to close. */
  const fn = /function shadowSummaryHtml\(m\)\{[\s\S]*?\n\}/.exec(src);
  assert(fn, "shadowSummaryHtml is where the guard expects it");
  assert(/c\.outcome/.test(fn[0]), "it reads completion.outcome");
  for (const forbidden of ["shadowTaskTranscript", "goalMessages",
                           "pending_say", "last_instruction", "founder_says",
                           "target_session", "goalTranscript"]){
    assert(fn[0].indexOf(forbidden) === -1,
      "the Summary must not reach for " + forbidden);
  }
  pass("4: control-plane text cannot reach the Summary — one field, no transcript");
}

/* ══ 5. THE ONE-LINE GIST IS STILL THERE, AND UNMOVED ═══════════════════ */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml(DONE());
  assert(/class="shdonework"/.test(h), "the gist block still renders");
  /* still ABOVE the checks, where it always was */
  assert(h.indexOf('class="shdonework"') < h.indexOf('class="shchecks"'),
    "and it is still above the verdicts");
  /* ONE SENTENCE, still: the backend keeps newlines now, and the gist is fed
     a flattened copy precisely so this line cannot move (shadowOutcomeFlat) */
  const flat = ctx.shadowOutcomeFlat(ROSSI);
  assert.strictEqual(ctx.shadowResultGist(ROSSI.replace(/\s+/g, " ")),
                     ctx.shadowResultGist(flat),
    "the gist reads the same string it always received");
  assert(flat.indexOf("\n") === -1, "which carries no newlines at all");
  pass("5: the existing gist is present, above the checks, and unchanged");
}

/* ══ 6. THE CHECK ROWS ARE UNTOUCHED ════════════════════════════════════ */
{
  const ctx = fresh();
  const h = ctx.shadowCompletionHtml(DONE());
  /* the rows live inside the Verification fold as of 2026-09-21; the row
     TEMPLATE is unchanged, which is what this test is about */
  const rows = h.slice(h.indexOf('class="shchecks"'));
  assert.strictEqual((rows.match(/class="shcheck shcheckmet"/g) || []).length,
    3, "three rows, each drawn by the unchanged row template");
  assert.strictEqual((rows.match(/shcheckmet/g) || []).length, 3,
    "all three checks still render as met");
  assert(/the latest race result is quoted/.test(rows), "check 1 text");
  assert(/a source link is given/.test(rows), "check 2 text");
  assert(/class="shcheckev">motorsport\.com</.test(rows),
    "its quoted evidence still rides under it");
  assert(/you confirmed it · founder/.test(rows),
    "and the founder confirmation still names who");
  /* the headline is "Done" now; the count moved into the fold with the
     rows it counts (founder, 2026-09-21) */
  assert(/class="shconfirmq">Done</.test(h), "the headline is unchanged");
  assert(/4 of 12 turns used\./.test(h), "and the budget line");
  pass("6: the check rows, headline and budget line are unchanged");
}

/* ══ 7. A TASK THAT IS NOT DONE SHOWS NO SUMMARY ════════════════════════ */
{
  const ctx = fresh();
  for (const st of ["running", "paused", "blocked", "queued",
                    "failed", "stopped"]){
    const h = ctx.shadowCompletionHtml(DONE({ state: st }));
    assert(!/shdonesummary/.test(h),
      "no Summary for a " + st + " task");
  }
  /* and a done task with nothing to quote draws no empty block */
  const empty = ctx.shadowCompletionHtml(
    DONE({ completion: Object.assign({}, DONE().completion, { outcome: "" }) }));
  assert(!/shdonesummary/.test(empty),
    "a done task with no outcome draws no empty Summary");
  /* ...while the card itself still renders, as it did before */
  assert(/class="shchecks"/.test(empty), "the verdicts are still drawn");
  pass("7: Summary is DONE-only, and never an empty block");
}

/* ══ 8. COPY RESULT IS UNTOUCHED ════════════════════════════════════════ */
{
  const ctx = fresh();
  const m = DONE();
  const h = ctx.shadowCompletionHtml(m);
  assert(/data-shcopydone="m-1"/.test(h), "the Copy result button still renders");
  assert(/>Copy result</.test(h), "with its idle label");
  const txt = ctx.shadowCompletionText(m);
  assert(/^Done — 3 of 3 checks passed/.test(txt), "headline leads the copy");
  assert(/Pull the very latest information about Valentino Rossi/.test(txt),
    "the objective rides along");
  assert(/4 of 12 turns used\./.test(txt), "and the budget");
  assert(txt.indexOf("Fanatec GT World Challenge Europe") !== -1,
    "the worker's account is copied in FULL, as it always was");
  assert(/the latest race result is quoted/.test(txt), "and every check");
  /* it is text, not the markup the pane draws */
  assert(txt.indexOf("<") === -1, "and it is still plain text");
  pass("8: Copy result behaviour is intact");
}

/* ══ 9. THE CARD STILL REFUSES PURE WORKING ═════════════════════════════
 * The 2026-09-15 ruling this must not undo: `outcome` is the worker's LAST
 * message, which is not always its CONCLUSION. When that message is the
 * working -- a permissions listing, a grep invocation, a table of hits --
 * the card draws nothing and the working stays behind Open the chat and in
 * Copy result. A big SUMMARY heading over a grep dump would be a louder
 * version of exactly what that ruling removed, so the block is gated on the
 * admissibility verdict that already existed. (test_shadow_rhs 8l pins the
 * same property from the pane side.)
 */
{
  const ctx = fresh();
  const WORKING = "**(1) Path and existing references** ``` -rw-r--r--@ 1 "
    + "joytadanki staff 7474 Sep 15 10:17 release-checklist.md ``` "
    + "`grep -rn 'release-checklist' .` returned four hits: "
    + "| Hit | What it actually is | |---|---| | SKILL.md:203 | An example |";
  const m = DONE({ completion: Object.assign({}, DONE().completion,
                                             { outcome: WORKING }) });
  const h = ctx.shadowCompletionHtml(m);
  assert(!/shdonesummary/.test(h),
    "a pure-working outcome draws no Summary block");
  for (const leak of ["-rw-r--r--", "grep -rn", "7474", "| Hit |"]){
    assert(h.indexOf(leak) === -1, "evidence on the card: " + leak);
  }
  /* and it is still reachable where the ruling said it stays */
  assert(ctx.shadowCompletionText(m).indexOf("-rw-r--r--") !== -1,
    "Copy result still carries the untrimmed outcome");
  /* the record is untouched -- this is a render gate, nothing else */
  assert.strictEqual(m.completion.outcome, WORKING,
    "completion.outcome is byte-identical after rendering");
  pass("9: pure working draws no Summary; Copy result still has it");
}

/* ══ 10. ESCAPED, NEVER INJECTED ════════════════════════════════════════
 * mdHtml escapes the ENTIRE input before it wraps anything, and checks link
 * schemes against http/https. The worker writes this field, so that property
 * is the one that makes rendering it safe.
 */
{
  const ctx = fresh();
  const EVIL = "Done. <img src=x onerror=alert(1)> and "
    + "[click](javascript:alert(2)) and <script>alert(3)</script>";
  const h = ctx.shadowCompletionHtml(DONE({
    completion: Object.assign({}, DONE().completion, { outcome: EVIL }) }));
  const sum = h.slice(h.indexOf('class="shdonesummary"'));
  assert(sum.indexOf("<img") === -1, "no img element is created");
  assert(sum.indexOf("<script") === -1, "no script element is created");
  assert(/&lt;img/.test(sum), "…and the text is still shown, escaped");
  assert(!/href="javascript:/.test(sum), "a javascript: link is not a link");
  pass("10: the Summary is escaped, never injected");
}

/* ══ THE UNIVERSAL AUDIT LANES (founder, 2026-09-17) ════════════════════
 *
 * WHAT THE AUDIT FOUND. The Summary decided WHETHER it had a result from one
 * representation of `completion.outcome` and rendered a DIFFERENT one: the
 * gate read shadowResultGist(shadowOutcomeFlat(o)), the body rendered raw o.
 * Flattening collapses the message to one line, and SH_CONTROL_HEAD matches
 * that line whenever the message merely BEGINS with a governance token -- so
 * a real 1686-character report opening "PLACEMENT: …" was judged empty.
 * Measured on the live store: 2 of 6 completed missions suppressed, both
 * holding a good answer. The discriminator was never the task type; it was
 * whether the worker emitted a Sutra governance preamble, which every
 * governed worker does.
 *
 * The lanes below pin the MECHANISM, not the symptom: one representation
 * (shadowOutcomeBody) feeds both the gate and the body, so existence and
 * presentation can never disagree again.
 */

/* the four real shapes the live store holds, transcribed as fixtures so this
   lane is deterministic on any machine. A live sweep runs too, when a store
   is present -- see U2. */
const GOVERNED = [
  'PLACEMENT: D0 Joy Tadanki | "Joy Tadanki Charter"', "",
  "```", "INPUT ROUTING", "TYPE: task (delegate objective via Shadow)",
  "HOME: sutra/marketplace/plugin/sutra-ui", "ROUTE: direct execution",
  "ACTION: verify existence → confirm 10 lines → report", "```", "",
  "```", 'TASK: "Create a file called `Joy Stefan`"', "DEPTH: 1/5 (surface)",
  "EFFORT: <1 min, 1 file", "COST: ~$0.01", "IMPACT: one scratch file", "```", "",
  "**Finding: the file already exists and already satisfies the objective.**",
  "",
  "| Item | Value |", "|---|---|", "| Line count | 10 |", "| Size | 594 bytes |",
  "", "I did not rewrite it.", "",
  "```", "TRIAGE: depth_selected=1, depth_correct=1, class=correct", "```",
].join("\n");

const WORKING = "**(1) Path and existing references** ``` -rw-r--r--@ 1 "
  + "joytadanki staff 7474 Sep 15 10:17 release-checklist.md ``` "
  + "`grep -rn 'release-checklist' .` returned four hits: "
  + "| Hit | What it actually is | |---|---| | SKILL.md:203 | An example |";

/* a mission completed BEFORE shadow_runner kept newlines: one flat line */
const LEGACY_FLAT = 'PLACEMENT: D0 Joy Tadanki | "Joy Tadanki Charter" ``` '
  + 'TYPE: task HOME: sutra-ui ROUTE: direct file write ``` **What I did** '
  + "| Step | Result | |---|---| | Located working dir | sutra-ui |";

const M = (outcome, over) => Object.assign({
  id: "m-u", state: "done",
  completion: { headline: "1 of 1 checks passed", outcome: outcome,
                turns_used: 1, max_turns: 5, checks: [] },
}, over);

/* ── U1. THE GATE AND THE BODY ARE THE SAME STRING ───────────────────── */
{
  const ctx = fresh();
  /* the invariant, stated as an invariant: for ANY input, the block renders
     exactly when the shared representation survives BOTH filters. This is
     the test that makes the audited defect unrepeatable -- a future edit
     that reintroduces a second representation fails here. */
  const inputs = [ROSSI, GOVERNED, WORKING, LEGACY_FLAT, "", "   \n\n  ",
                  "Done.", "# H\n\n- a\n- b", "```js\nconst a=1;\n```",
                  "PLACEMENT: x", "TASK: y\n\nReal conclusion here."];
  for (const t of inputs){
    const body = ctx.shadowOutcomeBody(t);
    const expect = !!(body && ctx.shadowResultGist(body));
    assert.strictEqual(!!ctx.shadowSummaryHtml(M(t)), expect,
      "gate and body disagree for: " + JSON.stringify(String(t).slice(0, 40)));
    /* and what is DRAWN is that same body, never the raw field */
    if (expect){
      const h = ctx.shadowSummaryHtml(M(t));
      assert(h.indexOf(ctx.mdHtml(body)) !== -1,
        "the rendered body is not the gated body");
    }
  }
  pass("U1: gate and rendering use one representation, for every input");
}

/* ── U2. CORPUS SWEEP ─────────────────────────────────────────────────── */
{
  const ctx = fresh();
  /* the bundled fixtures always; the LIVE store too when this machine has
     one, because the defect was found in real records and not in fixtures.
     The live pass asserts the INVARIANT only -- never a per-record verdict --
     so it cannot break on a machine whose store holds different missions. */
  let swept = 0;
  const check = (m) => {
    const o = (m.completion || {}).outcome || "";
    const body = ctx.shadowOutcomeBody(o);
    assert.strictEqual(!!ctx.shadowSummaryHtml(m),
      !!(body && ctx.shadowResultGist(body) && m.state === "done"),
      "invariant broken on " + (m.id || "?"));
    swept++;
  };
  for (const t of [ROSSI, GOVERNED, WORKING, LEGACY_FLAT]) check(M(t));
  const dir = path.join(require("os").homedir(), ".sutra-ui/shadow/missions");
  let live = 0;
  try {
    for (const f of fs.readdirSync(dir)){
      if (!f.endsWith(".json")) continue;
      let m; try { m = JSON.parse(fs.readFileSync(path.join(dir, f), "utf8")); }
      catch (e){ continue; }
      if (!m || !m.completion) continue;
      check(m); live++;
    }
  } catch (e){ /* no store on this machine: the fixtures above still ran */ }
  assert(swept >= 4, "the bundled corpus must always sweep");
  pass("U2: corpus sweep holds the invariant (" + swept + " records, "
       + live + " live)");
}

/* ── U3. A GOVERNED WORKER'S ANSWER LEADS, NOT ITS PREAMBLE ──────────── */
{
  const ctx = fresh();
  const h = ctx.shadowSummaryHtml(M(GOVERNED));
  assert(h, "a governance-prefixed outcome must render at all");
  const body = ctx.shadowOutcomeBody(GOVERNED);
  /* the preamble is gone -- every token of it */
  for (const gone of ["PLACEMENT", "INPUT ROUTING", "DEPTH:", "EFFORT:",
                      "COST:", "IMPACT:", "TRIAGE:", "ROUTE:", "HOME:"]){
    assert(body.indexOf(gone) === -1, "control-plane survived: " + gone);
  }
  /* and the ANSWER is the first thing drawn */
  assert(/^\*\*Finding: the file already exists/.test(body),
    "the answer must lead: " + JSON.stringify(body.slice(0, 60)));
  const sum = h.slice(h.indexOf('class="shdonesumbody'));
  assert(sum.indexOf("Finding: the file already exists") <
         (sum.indexOf("Line count") === -1 ? 1e9 : sum.indexOf("Line count")),
    "the finding precedes its own table");
  /* the worker's real content survived whole */
  assert(/<table class="md-t">/.test(sum), "its table is still drawn");
  assert(/I did not rewrite it\./.test(sum), "and its closing line");
  pass("U3: the governance preamble is gone; the answer leads");
}

/* ── U4. LEGITIMATE MARKDOWN SURVIVES ────────────────────────────────── */
{
  const ctx = fresh();
  const DOC = ["# Title", "", "Intro **bold** text.", "",
               "## Section", "", "- one", "- two", "",
               "| A | B |", "|---|---|", "| 1 | 2 |", "",
               "```js", "const a = 1;", "```", "",
               "See [docs](https://example.com/x)."].join("\n");
  const h = ctx.shadowSummaryHtml(M(DOC));
  assert(h, "an ordinary markdown document renders");
  assert(/<h1 class="md-h">Title<\/h1>/.test(h), "h1");
  assert(/<h2 class="md-h">Section<\/h2>/.test(h), "h2");
  assert(/<li[^>]*>one<\/li>/.test(h), "list items");
  assert(/<table class="md-t">/.test(h) && /<th>A<\/th>/.test(h), "table");
  assert(/<pre class="md-pre"><code>const a = 1;/.test(h),
    "an ORDINARY fenced block is NOT dropped");
  assert(/<a class="md-a" href="https:\/\/example\.com\/x"/.test(h), "link");
  assert(/<strong>bold<\/strong>/.test(h), "inline emphasis");
  /* the cleaner is a filter over lines, never a rewriter of them */
  assert.strictEqual(ctx.shadowOutcomeBody(DOC), DOC,
    "a document with no control-plane lines passes through unchanged");
  pass("U4: headings, lists, tables, ordinary code, links and emphasis survive");
}

/* ── U5. PURE WORKING IS STILL REFUSED ───────────────────────────────── */
{
  const ctx = fresh();
  assert(!ctx.shadowSummaryHtml(M(WORKING)),
    "the 2026-09-15 evidence ruling must still hold");
  /* AND THE COMPOSITION IS WHY. The body filter alone does NOT suppress it --
     a grep dump has no control-plane LINES to remove, so ~200 characters
     survive cleaning. It is the gist's working-vs-conclusion test, asked of
     that body, that refuses it. Pinning this stops a future simplification
     from dropping the second half and quietly reopening the ruling. */
  const body = ctx.shadowOutcomeBody(WORKING);
  assert(body.length > 100, "cleaning alone leaves the dump intact: "
    + body.length);
  assert.strictEqual(ctx.shadowResultGist(body), "",
    "…and the conclusion test is what refuses it");
  pass("U5: pure working refused, and by the half that must keep refusing it");
}

/* ── U6. A LEGACY FLAT RECORD HAS PINNED BEHAVIOUR ───────────────────── */
{
  const ctx = fresh();
  /* Missions completed before shadow_runner kept newlines hold ONE flat line.
     If that line opens with a control head the whole record reads as
     control-plane and nothing survives -- the structure is gone from the
     STORED DATA, not discarded here, and no renderer can recover it.
     Pinned so the limitation is a decision on the record rather than a
     surprise rediscovered later. 4 of 6 live records were this shape. */
  assert.strictEqual(ctx.shadowOutcomeBody(LEGACY_FLAT), "",
    "a flattened governance record cleans to nothing");
  assert(!ctx.shadowSummaryHtml(M(LEGACY_FLAT)),
    "so it draws no Summary, and says so by drawing nothing");
  /* a legacy record WITHOUT a control-plane opener is unaffected */
  const plain = "`shadow-ui-pass.txt` exists at marketplace/plugin/sutra-ui "
    + "and contains exactly shadow-ui-pass. Verified by reading it back.";
  assert(ctx.shadowSummaryHtml(M(plain)),
    "a flat record that is not control-plane still renders");
  pass("U6: legacy zero-newline behaviour is pinned, both ways");
}

/* ── U7. NOTHING, AND WHITESPACE, STAY NOTHING ───────────────────────── */
{
  const ctx = fresh();
  for (const empty of ["", "   ", "\n\n", "  \n \t \n ", null, undefined]){
    assert(!ctx.shadowSummaryHtml(M(empty)),
      "empty outcome must draw nothing: " + JSON.stringify(empty));
    assert.strictEqual(ctx.shadowOutcomeBody(empty), "",
      "and clean to nothing");
  }
  /* a document that is ONLY control-plane is empty in the same sense */
  assert(!ctx.shadowSummaryHtml(M("PLACEMENT: x\nTASK: y\nDEPTH: 1/5")),
    "an outcome that is only preamble draws nothing");
  pass("U7: empty, whitespace and preamble-only all draw nothing");
}

/* ── U8. STATE GATING IS UNCHANGED ───────────────────────────────────── */
{
  const ctx = fresh();
  for (const st of ["running", "paused", "blocked", "queued", "failed",
                    "stopped", "brief_confirm", undefined]){
    assert(!ctx.shadowSummaryHtml(M(GOVERNED, { state: st })),
      "no Summary for state " + st);
  }
  assert(ctx.shadowSummaryHtml(M(GOVERNED, { state: "done" })),
    "…and done still renders");
  pass("U8: only DONE shows a Summary");
}

/* ── U9. PROVENANCE IS UNCHANGED ─────────────────────────────────────── */
{
  const ctx = fresh();
  /* the source guard from lane 4, restated against the NEW function: the
     representation is derived from completion.outcome and nothing else, so
     the upstream guarantee (evidence_messages drops Shadow's injected user
     turns; a role check keeps only the worker's) still fully owns which
     message this is. */
  const fn = /function shadowOutcomeBody\(text\)\{[\s\S]*?\n\}/.exec(src);
  assert(fn, "shadowOutcomeBody is where the guard expects it");
  for (const forbidden of ["shadowTaskTranscript", "goalMessages",
                           "pending_say", "last_instruction", "founder_says",
                           "target_session", "goalTranscript", "completion"]){
    assert(fn[0].indexOf(forbidden) === -1,
      "the representation must not reach for " + forbidden);
  }
  /* and the whole record's control-plane fields still cannot surface */
  const CONTROL = "Go get the current state of the WRT seat and report back.";
  const h = ctx.shadowSummaryHtml(M(GOVERNED, {
    pending_say: CONTROL, last_instruction: CONTROL,
    founder_says: [{ text: "don't touch the API" }] }));
  assert(h.indexOf(CONTROL.slice(0, 30)) === -1, "Shadow's instruction");
  assert(h.indexOf("don't touch the API") === -1, "a founder aside");
  pass("U9: provenance and the source guard are unchanged");
}

/* ── U10. THE MUTATION GUARD ─────────────────────────────────────────── */
{
  /* Put the flattened representation BACK in the gate, in a sandboxed copy
     of the source, and the audited defect must return. A guard that cannot
     fail proves nothing. */
  const back = (mutate) => {
    const c = { console, Date, setTimeout: () => ({}), clearTimeout(){},
      setInterval: () => ({}), scheduleRender(){},
      esc: (x) => String(x == null ? "" : x), SCREENS: {}, TITLES: {}, S: {},
      document: { addEventListener(){},
        createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
        body: { appendChild(){} }, querySelector(){ return null; } } };
    vm.createContext(c);
    vm.runInContext(mdBlock(), c);
    vm.runInContext(overlay, c);
    vm.runInContext(mutate(src), c);
    return c;
  };
  const GATE = "  const body = shadowOutcomeBody(text);\n"
             + "  if (!body || !shadowResultGist(body)) return \"\";";
  assert(src.indexOf(GATE) !== -1, "the gate is where the mutation expects it");
  const flat = back(t => t.replace(GATE,
    "  const body = text;\n"
    + "  if (!shadowResultGist(shadowOutcomeFlat(text))) return \"\";"));
  /* the governed record -- a real answer -- goes dark again */
  assert.strictEqual(flat.shadowSummaryHtml(M(GOVERNED)), "",
    "restoring the flattened gate must reproduce the suppression");
  /* while the un-mutated module shows it */
  assert(fresh().shadowSummaryHtml(M(GOVERNED)),
    "…and the shipped module must not");
  pass("U10: the flattened representation really does suppress it — guard bites");
}

console.log("\nall DONE-summary tests passed");
