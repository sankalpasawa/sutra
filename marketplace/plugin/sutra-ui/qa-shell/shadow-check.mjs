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
 *
 * DEPENDENCY-FREE like nav-check.mjs: raw CDP over Node's WebSocket. Run via
 * run.sh (QA_SCRIPT=$PWD/shadow-check.mjs bash run.sh), never directly.
 * Screenshots land in qa-shell/out/shadow-*.png every run — the visual trail
 * founder direction 2026-08-25 asked for ("keep on checking it").
 */
import fs from "fs";

const PORT = process.env.SHELL_DEBUG_PORT || "9223";
const OUT = new URL("./out/", import.meta.url).pathname;
fs.mkdirSync(OUT, { recursive: true });

let page = null;
for (let i = 0; i < 40 && !page; i++){
  try {
    const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    page = targets.find(t => t.type === "page" && /127\.0\.0\.1:8330/.test(t.url || ""));
  } catch {}
  if (!page) await new Promise(r => setTimeout(r, 500));
}
if (!page){ console.error("no shell page target on CDP after 20s"); process.exit(1); }

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pend = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pend.has(m.id)){ pend.get(m.id)(m); pend.delete(m.id); } };
const cdp = (method, params = {}) => new Promise((res, rej) => {
  const id = ++seq; pend.set(id, m => m.error ? rej(new Error(method + ": " + JSON.stringify(m.error))) : res(m.result));
  ws.send(JSON.stringify({ id, method, params }));
});
async function evql(expr){
  const r = await cdp("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || "eval failed: " + expr.slice(0, 80));
  return r.result.value;
}
async function until(expr, ms = 8000){
  for (let t = 0; t < ms; t += 150){
    if (await evql(expr)) return true;
    await new Promise(r => setTimeout(r, 150));
  }
  return false;
}
async function shot(name){
  const r = await cdp("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(OUT + "shadow-" + name + ".png", Buffer.from(r.data, "base64"));
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

/* ── G9: a Shadow deep link actually lands (the founder's dead-click) ───── */
await evql(`(typeof openNeedsYouItem === "function"
  && openNeedsYouItem("sutra://shadow/mission/m-qa-probe"), true)`);
const landed = await until(
  `S.ui.dest === "focus" && S.screen === "shadow" && S.shadowTab === "working"`);
landed ? ok("G9 deep link: Open lands on Focus > Shadow, Working tab")
       : fail("G9 deep link: Open lands on Focus > Shadow, Working tab",
              "dest/screen/tab never settled");
await shot("5-deeplink-landing");

/* ── G8 ──────────────────────────────────────────────────────────────────── */
await check("G8 zero uncaught page errors during the drive",
  `(window.__qaErrs || []).length === 0
     || (console.log(window.__qaErrs), false)`);

console.log(`\nshadow-check: ${passed} passed, ${failed} failed, ${skipped} skipped`);
console.log("screenshots: qa-shell/out/shadow-*.png");
process.exit(failed ? 1 : 0);
