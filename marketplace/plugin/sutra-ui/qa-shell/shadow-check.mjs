/* qa-shell/shadow-check.mjs — the SHADOW UI parity lane of the publish check.
 *
 * Drives the Shadow surfaces inside the real Sutra.app (or the repo backend
 * via QA_BACKEND=repo) and asserts STRUCTURAL parity invariants against the
 * decided design (website/preview/shadow.html, mock v5) — never pixels:
 *   G1 no raw enum leaks in rendered text (NEEDS_DECISION, app_restart, ...)
 *   G2 no duplicate card titles in the Now feed
 *   G3 every Now card carries at least one action pill (empty feed = SKIP)
 *   G4 the dot face is "S" with a separate numeric badge, never a bare number
 *   G5 mission-row objective width >= 140px (kills one-word-per-line collapse)
 *   G6 Focus > Shadow reachable: tabs + composer render
 *   G7 corner card opens: sees-line + open-home affordance present
 *   G8 zero uncaught page errors during the drive
 *   G15 the task card's turn-budget meter: the things only a browser knows —
 *       real track geometry, fill length tracking used/max, a distinct painted
 *       colour per threshold, no overflow, and a card width the meter did not
 *       move. NUMBERED 15, NOT 9: G9 above is already the deep-link gate, and
 *       two gates sharing an id makes a red line ambiguous at 2am.
 *
 * DEPENDENCY-FREE like nav-check.mjs: raw CDP over Node's WebSocket. Run via
 * run.sh (QA_SCRIPT=$PWD/shadow-check.mjs bash run.sh), never directly.
 * Screenshots land in qa-shell/out/shadow-*.png every run — the visual trail
 * founder direction 2026-08-25 asked for ("keep on checking it").
 *
 * QA_PANEL_PORT picks which served panel to attach to; default 8330 is the
 * app's fixed port, which is what run.sh sets up. Set it to drive a repo
 * backend on a free port instead, and the founder's Sutra.app is never
 * stopped, debug-flagged or restarted to run this lane.
 */
import fs from "fs";

const PORT = process.env.SHELL_DEBUG_PORT || "9223";
const PANEL_PORT = process.env.QA_PANEL_PORT || "8330";
const OUT = new URL("./out/", import.meta.url).pathname;
const ART = new URL("./artifacts/", import.meta.url).pathname;
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(ART, { recursive: true });

let page = null;
const PANEL_RE = new RegExp("127\\.0\\.0\\.1:" + PANEL_PORT + "(/|$)");
for (let i = 0; i < 40 && !page; i++){
  try {
    const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    page = targets.find(t => t.type === "page" && PANEL_RE.test(t.url || ""));
  } catch {}
  if (!page) await new Promise(r => setTimeout(r, 500));
}
if (!page){
  console.error(`no panel page target on CDP after 20s (looked for 127.0.0.1:${PANEL_PORT})`);
  process.exit(1);
}

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pend = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pend.has(m.id)){ pend.get(m.id)(m); pend.delete(m.id); } };

/* A DEAD SESSION MUST FAIL, NOT HANG. Every reply above is matched by id, so
   if the page goes away -- renderer crash, tab closed, browser exited -- the
   pending entries are never called and every `await` below waits forever. A
   publish check that hangs is strictly worse than one that fails: CI kills it
   with no verdict, and a human reads "still running" as "still fine". Seen
   live 2026-09-15: Chrome exited mid-drive and the lane sat on one `until`
   until the harness timed the whole job out, printing no failure at all.

   Two guards, because the two deaths look different. `onclose` catches the
   clean one -- the socket goes, and everything outstanding is rejected at
   once. The deadline catches the rest: a renderer alive enough to hold a
   socket open but not to answer. Both raise, and a raise is what the gates
   already know how to report. */
let dead = null;
function die(why){
  if (!dead) dead = why;
  for (const [, settle] of pend) settle({ error: { message: why } });
  pend.clear();
}
ws.onclose = () => die("CDP session closed: the page or the browser went away mid-drive");
ws.onerror = () => die("CDP socket error mid-drive");

/* and whatever gets past the guards still leaves a VERDICT and an exit code.
   Node's own answer to a rejected top-level await is a warning about an
   "unsettled" promise, which names a line number and not a reason. */
for (const sig of ["unhandledRejection", "uncaughtException"])
  process.on(sig, e => {
    console.error("\nFATAL - shadow-check could not finish: "
      + ((e && e.message) || e));
    /* the counters are declared below this point, so a death during setup
       would otherwise trade the real reason for a TDZ ReferenceError */
    let tally = "no gates had run yet";
    try { tally = `${passed} passed, ${failed} failed`; } catch {}
    console.error(`(${tally} before this point)`);
    process.exit(1);
  });

const CDP_TIMEOUT_MS = Number(process.env.QA_CDP_TIMEOUT_MS || 20000);
const cdp = (method, params = {}) => new Promise((res, rej) => {
  if (dead) return rej(new Error(dead));
  const id = ++seq;
  const timer = setTimeout(() => {
    if (pend.delete(id))
      rej(new Error(method + ": no reply in " + CDP_TIMEOUT_MS + "ms (page wedged?)"));
  }, CDP_TIMEOUT_MS);
  pend.set(id, m => { clearTimeout(timer);
    m.error ? rej(new Error(method + ": " + JSON.stringify(m.error))) : res(m.result); });
  try { ws.send(JSON.stringify({ id, method, params })); }
  catch (e){ clearTimeout(timer); pend.delete(id); rej(e); }
});
async function evql(expr){
  const r = await cdp("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || "eval failed: " + expr.slice(0, 80));
  return r.result.value;
}
/* `until` answers "did this become true in time", so a page that cannot be
   asked is a NO, not a throw that skips the gate that was about to run. The
   one exception is a dead session: there is nothing left to wait for, and
   every later gate would poll a corpse for its full timeout. */
async function until(expr, ms = 8000){
  for (let t = 0; t < ms; t += 150){
    try { if (await evql(expr)) return true; }
    catch (e){ if (dead) throw new Error(dead); }
    await new Promise(r => setTimeout(r, 150));
  }
  return false;
}
async function shot(name){
  const r = await cdp("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(OUT + "shadow-" + name + ".png", Buffer.from(r.data, "base64"));
}
/* out/ is the rolling trail -- every run overwrites it and it is gitignored.
   artifacts/ is the EVIDENCE a gate points at: committed, named for the gate
   that produced it, so the picture lives beside the assertion it backs rather
   than in a screenshot folder nobody can date. Cropped to the card, because a
   full-window shot of a 152px meter is evidence of nothing. */
async function artifact(name, selector){
  const p = ART + name + ".png";
  let clip = null;
  if (selector){
    const box = await evql(`(() => { const e = document.querySelector(${
      JSON.stringify(selector)}); if (!e) return null;
      const r = e.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height }; })()`);
    if (box && box.width > 0 && box.height > 0)
      clip = { x: Math.max(0, box.x - 8), y: Math.max(0, box.y - 8),
               width: box.width + 16, height: box.height + 16, scale: 2 };
  }
  const r = await cdp("Page.captureScreenshot",
    clip ? { format: "png", clip, captureBeyondViewport: true } : { format: "png" });
  fs.writeFileSync(p, Buffer.from(r.data, "base64"));
  console.log("       evidence -> qa-shell/artifacts/" + name + ".png");
  return p;
}

let passed = 0, failed = 0, skipped = 0;
function ok(n){ passed++; console.log("ok   - " + n); }
function fail(n, d){ failed++; console.log("FAIL - " + n + (d ? "\n       " + d : "")); }
function skip(n, why){ skipped++; console.log("SKIP - " + n + " (" + why + ")"); }
async function check(name, expr, expect){
  try {
    const got = await evql(expr);
    const pass = expect === undefined ? !!got : JSON.stringify(got) === JSON.stringify(expect);
    pass ? ok(name) : fail(name, "got " + JSON.stringify(got) + " want " + JSON.stringify(expect));
  } catch (e){ fail(name, e.message); }
}

/* wait for the rail FIRST: the shell reloads its page once after the
   backend attaches, which wipes anything installed earlier (learned live:
   an early hook made G8 read undefined). Boot-window errors are therefore
   out of scope for G8 -- the drive itself is what it guards. */
for (let i = 0; i < 40; i++){
  if (await evql(`document.querySelectorAll('#railnav [data-dest]').length`) === 6) break;
  await new Promise(r => setTimeout(r, 250));
}
await evql(`(window.__qaErrs = window.__qaErrs || [],
  window.__qaErrsHooked || (window.__qaErrsHooked = true,
    window.addEventListener("error",
      e => window.__qaErrs.push(String(e.message).slice(0,120)))), true)`);

const RAW = "NEEDS_DECISION|APP_RESTART|D_LEDGER|BRIEF_CONFIRM|FOUNDER_CONFIRM";

/* ── Now ─────────────────────────────────────────────────────────────────── */
await evql(`(goDest("now"), typeof render === "function" && render(), true)`);
/* the .zero placeholder matches instantly -- wait for the FETCH to settle
   (S.needsYou defined) before counting cards (race caught live 2026-08-26) */
await until(`typeof S !== "undefined" && S.needsYou !== undefined`);
await evql(`(typeof render === "function" && render(), true)`);
await until(`document.querySelector(".nyfeed, .zero")`);
await shot("1-now");
const cardCount = await evql(`document.querySelectorAll(".nycard").length`);
if (cardCount === 0) skip("G1 Now: no raw enums in the feed chrome", "feed empty");
else await check("G1 Now: no raw enums in the feed chrome (codex fold: scoped to .nyfeed, founder data exempt)",
  `!new RegExp("${RAW}", "i").test([...document.querySelectorAll(".nyfeed .nyhead, .nyfeed .nywhy, .nygreet, .nysub")].map(e => e.innerText).join(" "))`);
if (cardCount === 0){
  skip("G2 Now: no duplicate card titles", "feed empty on this machine");
  skip("G3 Now: every card has an action pill", "feed empty on this machine");
} else {
  await check("G2 Now: every rendered card is a distinct item (unique data-itemid)",
    `(() => { const t = [...document.querySelectorAll(".nycard")].map(c =>
         (c.dataset && c.dataset.itemid) || "");
       return new Set(t).size === t.length; })()`);
  await check("G3 Now: every card has an action pill",
    `[...document.querySelectorAll(".nycard")].every(c => c.querySelector(".nyact, .nyactrow button"))`);
}

/* ── the dot (G4) ────────────────────────────────────────────────────────── */
const hasDot = await evql(`!!document.querySelector(".shdot")`);
if (!hasDot) skip("G4 dot face", "no dot mounted (shadow off or hidden)");
else await check("G4 dot: S-mark face + a real .shbadge element for the count",
  `(() => { const d = document.querySelector(".shdot");
     const face = (d.innerText || d.textContent || "").trim();
     if (!/S/.test(face) || /^\\d+$/.test(face)) return false;
     const n = (face.match(/\\d+/) || [null])[0];
     return n === null || !!d.querySelector(".shbadge"); })()`);

/* ── Focus > Shadow home ─────────────────────────────────────────────────── */
await evql(`(goDest("focus"), typeof openScreen === "function" ? openScreen("shadow") : (S.screen = "shadow"),
  typeof render === "function" && render(), true)`);
await until(`document.querySelectorAll(".shtab").length >= 2`);
await shot("2-home-watching");
await until(`S.shadowHomeDark === false`);
await check("G10 home: data loaded honestly (no silent-empty, no error strip)",
  `S.shadowHomeErr !== true`);
if (process.env.QA_SHADOW_HOME){
  await check("G10f fixture: the seeded missions actually render",
    `(S.shadowMissions || []).length >= 2`);
}
await check("G6 home: Watching/Working tabs render",
  `document.querySelectorAll(".shtab").length >= 2`);
await check("G6 home: composer present",
  `!!document.querySelector("[data-shhomecompose], .shcompose, textarea")`);
await check("G1 home: no raw enums (memory labels humanized)",
  `!new RegExp("${RAW}", "i").test(document.querySelector(".pb") ? document.querySelector(".pb").innerText : document.body.innerText)`);
await evql(`(S.shadowTab = "working", typeof render === "function" && render(), true)`);
await until(`document.querySelector(".shmissionrow, .shempty")`);
await shot("3-home-working");
const rows = await evql(`document.querySelectorAll(".shmission .shobj").length`);
if (rows === 0) skip("G5 mission-row geometry", "no mission rows to measure");
else await check("G5 mission rows: objective gets real width (offenders listed on fail)",
  `[...document.querySelectorAll(".shmission .shobj")]
     .filter(o => o.offsetParent && o.clientWidth < 140)
     .map(o => o.innerText.slice(0, 30) + "@" + o.clientWidth + "px")`, []);

/* ── the corner card (G7) ────────────────────────────────────────────────── */
await evql(`(goDest("chats"), typeof render === "function" && render(),
  S.shadowCardOpen = true, typeof renderShadowCard === "function" && renderShadowCard(), true)`);
await until(`document.querySelector("[data-shcardwrap]")`);
await shot("4-card");
await check("G7 card: mounts with sees-line",
  `!!document.querySelector("[data-shcardwrap] .shperm")`);
await check("G7 card: open-home affordance present",
  `!!document.querySelector("[data-shcardwrap] [data-shopenhome]")`);
await evql(`(S.shadowCardOpen = false, typeof renderShadowCard === "function" && renderShadowCard(), true)`);

/* ── G11/G12: per-chat tabs + settings (v10) ─────────────────────────────── */
/* the card checks navigated to Chats — come back to the home first
   (learned live: the tab check skipped because nothing was mounted) */
await evql(`(goDest("focus"), typeof openScreen === "function"
  && openScreen("shadow"), typeof render === "function" && render(), true)`);
await until(`document.querySelector("[data-shchat], .shchattabs")`, 6000);
const tabCount = await evql(`document.querySelectorAll("[data-shchat]").length`);
if (tabCount === 0) skip("G11 per-chat tabs render", "no tabs on this machine");
else {
  await check("G11 tabs: the new tab exists and uses its own namespace",
    `!!document.querySelector('[data-shchat="global"]')
       && document.querySelectorAll('[data-shtab]').length <= 2`);
  await check("G14 tabs wear names, not raw ids (known chats)",
    `(() => {
       const bad = [...document.querySelectorAll("[data-shchat]")]
         .filter(t => { const k = t.dataset.shchat;
           if (!k || k === "global") return false;
           const known = (S.sessions || []).some(x => x && x.id === k);
           if (!known) return false;      /* unknown -> honest fallback ok */
           return (t.innerText || "").indexOf(k.slice(0, 6)) === 0; })
         .map(t => t.innerText.slice(0, 20));
       return bad; })()`, []);
  await check("G12 tab click switches the thread (no page churn)",
    `(() => { const t = document.querySelector('[data-shchat]:not(.on)');
       if (!t) return true; t.click();
       return S.shadowChat === t.dataset.shchat; })()`);
}
await evql(`(typeof loadShadowSettings === "function" && loadShadowSettings(), true)`);
await until(`typeof S !== "undefined" && S.shadowSettings !== undefined`, 6000);
await check("G13 settings read: the codified rules load (floors present)",
  `!!(S.shadowSettings && (S.shadowSettings.floors || []).length >= 3)`);

/* ── G9: a Shadow deep link actually lands (the founder's dead-click) ───── */
await evql(`(typeof openNeedsYouItem === "function"
  && openNeedsYouItem("sutra://shadow/mission/m-qa-probe"), true)`);
const landed = await until(
  `S.ui.dest === "focus" && S.screen === "shadow" && S.shadowTab === "working"`);
landed ? ok("G9 deep link: Open lands on Focus > Shadow, Working tab")
       : fail("G9 deep link: Open lands on Focus > Shadow, Working tab",
              "dest/screen/tab never settled");
await shot("5-deeplink-landing");

/* ── G15: the task card's turn-budget meter ──────────────────────────────────
   THE ONLY GATE HERE THAT MEASURES RATHER THAN MATCHES. Every assertion below
   is one the render tests in test_shadow_home.js structurally cannot make:
   they read a string, and a string does not have a width, a painted colour,
   or a box it can overflow. The bug this exists to catch is the one that
   already bit this card once -- a row that passed every string assertion and
   wrapped to two lines in a real browser (see the .shcard2stamp note in
   panel.css). A meter is worse: a track that collapses to 0px, a fill that
   never paints, or an overrun that spills past its own border all leave the
   markup the string tests assert on completely intact.

   THE RECORDS ARE SYNTHETIC, THE RENDER IS NOT. They go through
   S.shadowMissions -> render(), so this is the shipped markup against the
   shipped stylesheet in the shipped browser; only the numbers are chosen,
   because no real mission sits conveniently at 95% of its budget on the
   machine running the publish check. S.shadowMissions is restored afterwards
   so nothing downstream inherits the fixtures.

   IT NEVER SKIPS. A missing card or a missing meter is the failure this gate
   is for, so it fails by name and takes the exit code with it -- a gate that
   goes quiet when the thing it guards has vanished is worse than no gate. */
const BUDGET_FIX = [
  { id: "qa-bud-ok",    objective: "QA budget: a quarter spent", turns_used: 5,  max_turns: 20 },
  { id: "qa-bud-warn",  objective: "QA budget: getting close",   turns_used: 15, max_turns: 20 },
  { id: "qa-bud-block", objective: "QA budget: one turn left",   turns_used: 19, max_turns: 20 },
  { id: "qa-bud-over",  objective: "QA budget: past its ceiling", turns_used: 23, max_turns: 20 },
  { id: "qa-bud-none",  objective: "QA budget: no stated ceiling", turns_used: 4, max_turns: 0 },
  { id: "qa-bud-zero",  objective: "QA budget: not started",     turns_used: 0,  max_turns: 20 },
].map(f => Object.assign({ template: "fix", state: "running", target_mode: "new",
  target_session: null, done_when: [],
  updated_at: new Date(Date.now() - 120000).toISOString() }, f));

await evql(`(() => {
  window.__qaBudSaved = S.shadowMissions;
  window.__qaBudFix = ${JSON.stringify(BUDGET_FIX)};
  /* ONE RECORD IN THE LIST AT A TIME, deliberately. Loading all six at once
     put the gate at the mercy of the Working tab's own list rules -- which
     task counts as active, and what the pane falls back to when the selected
     id is filtered out of it. One fixture duly stopped rendering when those
     rules moved underneath it (caught 2026-09-15), which reported a meter
     bug that did not exist: the same record drew a correct 0%-wide track the
     moment it was the only one in the list. None of that is what this gate
     measures. A single-record list makes every assertion below depend on
     exactly one record and the stylesheet, which is the whole claim. */
  window.__qaBudGo = (id) => {
    const rec = (window.__qaBudFix || []).find(f => f.id === id);
    S.shadowMissions = rec ? [rec] : [];
    if (S.ui) S.ui.dest = "focus";
    S.screen = "shadow"; S.shadowTab = "working"; S.shadowTaskSel = id;
    if (typeof render === "function") render();
    return true;
  };
  window.__qaBudRead = (id) => {
    const card = document.querySelector('[data-shtaskcard="' + id + '"]');
    if (!card) return { card: false };
    const cardW = Math.round(card.getBoundingClientRect().width);
    const text = (card.innerText || "").replace(/\\s+/g, " ");
    const bar = card.querySelector(".shcard2bar");
    if (!bar) return { card: true, bar: false, cardW, text };
    const fill = bar.querySelector("i");
    if (!fill) return { card: true, bar: true, fill: false, cardW, text };
    const br = bar.getBoundingClientRect(), fr = fill.getBoundingClientRect();
    /* the track carries a 1px border, so "full" is the CONTENT width -- the
       ratio is measured against the box the fill actually lives in */
    const inner = bar.clientWidth || br.width;
    return { card: true, bar: true, fill: true,
      barW: Math.round(br.width), barH: Math.round(br.height),
      fillW: Math.round(fr.width), pct: Math.round(fr.width / inner * 100),
      sev: fill.className, colour: getComputedStyle(fill).backgroundColor,
      overflows: fr.right > br.right + 1,
      label: bar.getAttribute("aria-label"), title: bar.getAttribute("title"),
      role: bar.getAttribute("role"), cardW, text };
  };
  return true;
})()`);

/* READ THE SETTLED WIDTH, NEVER A SLEPT-THROUGH ONE. `.ubar i` carries
   `transition:width .25s ease` (panel.css, inherited with the track), so the
   fill is an ANIMATING box for a quarter of a second after it mounts. Measure
   it on the wrong frame and this gate reports 62% for a meter that is on its
   way to 75% -- green on a fast machine, red on a loaded one, which is the
   exact shape of a flaky gate nobody trusts and everybody reruns.

   The fix is to wait on the THING, not on the clock: poll until two
   consecutive reads agree on the fill width. A fixed sleep would only move
   the flake to a slower machine. Cases with nothing to animate (no track at
   all, or a 0-width fill) fall straight out on the first read. */
async function budRead(id){
  await evql(`window.__qaBudGo(${JSON.stringify(id)})`);
  const there = await until(`!!document.querySelector('[data-shtaskcard="${id}"]')`, 6000);
  if (!there) return { card: false };
  let prev = null, r = null;
  for (let i = 0; i < 40; i++){
    r = await evql(`window.__qaBudRead(${JSON.stringify(id)})`);
    if (!r.card || r.bar === false || r.fill === false) return r;
    if (prev !== null && r.fillW === prev) return r;      /* settled */
    prev = r.fillW;
    await new Promise(res => setTimeout(res, 50));
  }
  return r;
}
function eq(name, got, want){
  JSON.stringify(got) === JSON.stringify(want)
    ? ok(name)
    : fail(name, "got " + JSON.stringify(got) + " want " + JSON.stringify(want));
}

const B = {};
for (const f of BUDGET_FIX) B[f.id] = await budRead(f.id);
/* the card has to exist before anything can be measured on it -- said out
   loud, once, so a vanished card reads as one clear red line and not as six */
for (const f of BUDGET_FIX)
  eq(`G15 the task card renders at all (${f.id})`, B[f.id].card, true);

const bOk = B["qa-bud-ok"], bWarn = B["qa-bud-warn"], bBlk = B["qa-bud-block"];
const bOver = B["qa-bud-over"], bNone = B["qa-bud-none"], bZero = B["qa-bud-zero"];

eq("G15 meter: the track is drawn and has real height", bOk.barH > 0 && bOk.barH <= 10, true);
eq("G15 meter: the track has real width", bOk.barW > 40, true);
eq("G15 meter: 5 of 20 fills about a quarter", Math.abs(bOk.pct - 25) <= 2, true);
eq("G15 meter: 15 of 20 fills about three quarters", Math.abs(bWarn.pct - 75) <= 2, true);
eq("G15 meter: 19 of 20 fills about 95%", Math.abs(bBlk.pct - 95) <= 2, true);

eq("G15 threshold: a quarter spent is p-ok", bOk.sev, "p-ok");
eq("G15 threshold: three quarters spent is p-warn", bWarn.sev, "p-warn");
eq("G15 threshold: one turn left is p-block", bBlk.sev, "p-block");
eq("G15 threshold: each band paints a DIFFERENT colour on screen",
   bOk.colour !== bWarn.colour && bWarn.colour !== bBlk.colour, true);
eq("G15 threshold: the fill paints a real colour, not transparent",
   /^rgba?\(/.test(String(bOk.colour)) && !/,\s*0\)$/.test(String(bOk.colour)), true);

eq("G15 overrun: past the ceiling fills the track completely",
   bOver.fillW >= bOver.barW - 2, true);
eq("G15 overrun: and never spills past its own border", bOver.overflows, false);
eq("G15 empty: 0 of 20 draws an EMPTY track, not a missing one",
   bZero.bar === true && bZero.fillW === 0, true);

eq("G15 honesty: no stated ceiling draws NO track", bNone.bar, false);
eq("G15 honesty: and the budget row keeps its text", /turn 4 of 0/.test(bNone.text), true);
eq("G15 honesty: the numbers stay beside the bar", /turn 5 of 20/.test(bOk.text), true);
eq("G15 a11y: the meter is announced, with the arithmetic in words",
   bOk.role === "img" && bOk.label === "5 of 20 turns used, 15 turns left", true);
eq("G15 a11y: one is singular on hover", bBlk.title, "1 turn left");

eq("G15 layout: the meter does not stretch the card", bOk.barW < bOk.cardW, true);
eq("G15 layout: the card is exactly as wide with the meter as without",
   bOk.cardW === bNone.cardW, true);

/* VISUAL EVIDENCE, one per state the gate asserts on (founder direction
   2026-09-15: "a check that only exists in /tmp is a check that doesn't
   exist" -- and a colour assertion nobody can look at is the same thing).
   Re-read before each shot so the capture happens on a SETTLED fill, for the
   same reason the measurements do. */
for (const [id, name] of [
  ["qa-bud-ok",    "g15-budget-low-5of20"],
  ["qa-bud-warn",  "g15-budget-mid-15of20"],
  ["qa-bud-block", "g15-budget-high-19of20"],
  ["qa-bud-none",  "g15-budget-no-ceiling"],
]){
  await budRead(id);
  await artifact(name, `[data-shtaskcard="${id}"]`);
}
await evql(`window.__qaBudGo("qa-bud-warn")`);
await shot("6-budget-warn");
await evql(`window.__qaBudGo("qa-bud-none")`);
await shot("7-budget-no-ceiling");
/* put the machine's own missions back: no later gate inherits the fixtures */
await evql(`(S.shadowMissions = window.__qaBudSaved, S.shadowTaskSel = null,
  typeof render === "function" && render(), true)`);

/* ── G8 ──────────────────────────────────────────────────────────────────── */
await check("G8 zero uncaught page errors during the drive",
  `(window.__qaErrs || []).length === 0
     || (console.log(window.__qaErrs), false)`);

console.log(`\nshadow-check: ${passed} passed, ${failed} failed, ${skipped} skipped`);
console.log("screenshots: qa-shell/out/shadow-*.png");
process.exit(failed ? 1 : 0);
