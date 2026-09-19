/* qa-shell/kindtag-head-check.mjs -- LAYOUT evidence for the removed kind badge.
 *
 * The JS suites assert on markup: `shcard2tag` is not in the string. A string
 * says nothing about whether the head still carries the nine pixels the badge
 * used to occupy. This lane measures the rendered box in a real browser.
 *
 * AGAINST THE REPO-LIVE BACKEND ON :7681, never :8330 -- 8330 serves the
 * INSTALLED app bundle, which carries an older copy of panel.css and
 * 16-shadow-home.js and would happily report the badge still there (or still
 * gone) for reasons that have nothing to do with the working tree.
 *
 * HARD RELOAD IS Page.reload({ignoreCache:true}). The panel's JS and CSS are
 * served with cache headers; a plain navigation re-runs a cached bundle and
 * would measure the PREVIOUS build.
 *
 * WHAT IS MEASURED, and what each number is guarding:
 *   head children      exactly 2 -- objective, state pill. A leftover empty
 *                      <span> is invisible but still eats one flex `gap`.
 *   obj.left - head.left  MUST be 0. This is the whole "no dead whitespace
 *                      where the span was" claim: the head is flex with a
 *                      gap, so a surviving zero-width child pushes the
 *                      objective right by exactly one gap and nothing else
 *                      on screen shows why.
 *   BEFORE/AFTER delta the same measurement taken with the badge injected
 *                      back into the live DOM, so the shift is a measured
 *                      number rather than an assertion that it is zero.
 *   head height        vs the objective's own line box -- catches a collapsed
 *                      row (head shorter than its text) and a head that grew.
 *   pill.right         flush to head.right: the pill is still pushed to the
 *                      far end by shcard2obj's flex:1, not dragged left.
 *   rows below         where it runs / turn still render at their own left
 *                      edge -- catches a reflow that only shows further down.
 *
 * FOUR CELLS: {short, long} objective x {normal 1440px, compact <900px}.
 * The <900px branch is the panel's own responsive layout (panel.css @media
 * max-width:900px), which is the only second geometry the card has.
 *
 * Read-only against the founder's store: it GETs /api/shadow/missions and
 * clicks task rows (selection is client state). Nothing is written.
 *
 * Run:  node qa-shell/kindtag-head-check.mjs
 * Env:  KT_PORT (default 7681)  KT_CDP (default 9351)
 * Out:  qa-shell/artifacts/kindtag-{short,long}-{normal,compact}.png
 */
import fs from "fs";
import path from "path";
/* fileURLToPath, NOT new URL(...).pathname -- this checkout lives under a
   directory with a space in it ("Joy Stephen"), and .pathname hands back the
   percent-encoded form, which writes artifacts into a decoy tree. */
import { fileURLToPath } from "url";

const PORT = process.env.KT_PORT || "7681";
const CDP_PORT = process.env.KT_CDP || "9351";
const APP = `http://127.0.0.1:${PORT}/`;
const ART = path.join(path.dirname(fileURLToPath(import.meta.url)), "artifacts");
fs.mkdirSync(ART, { recursive: true });
if (/%[0-9A-Fa-f]{2}/.test(ART)){
  console.error("FATAL: artifact dir is percent-encoded: " + ART); process.exit(2);
}

let pass = 0, fail = 0;
const ok  = (n, d) => { pass++; console.log("ok   - " + n + (d ? "  [" + d + "]" : "")); };
const bad = (n, d) => { fail++; console.log("FAIL - " + n + (d ? "\n       " + d : "")); };
const is  = (n, got, want) => (JSON.stringify(got) === JSON.stringify(want))
  ? ok(n, JSON.stringify(got)) : bad(n, "got " + JSON.stringify(got) + " want " + JSON.stringify(want));

/* ── gate 1: the RIGHT backend is answering ─────────────────────────────── */
let httpOk = false;
for (let t = 0; t < 20000 && !httpOk; t += 250){
  try { httpOk = (await fetch(APP, { redirect: "manual" })).status === 200; } catch {}
  if (!httpOk) await new Promise(r => setTimeout(r, 250));
}
if (!httpOk){ console.error("FATAL: no 200 from " + APP); process.exit(2); }
ok("gate 1: backend 200 on :" + PORT);

/* THE PORT IS NOT ENOUGH. :7681 is only the repo-live server if it is
   serving the WORKING TREE's panel.css -- so ask it for the stylesheet and
   look for the rule this change deleted. If `.shcard2tag` is still in the
   served CSS, we are pointed at a stale bundle and every measurement below
   would be measuring the wrong build. */
const css = await (await fetch(APP + "static/panel.css")).text();
is("gate 1b: the SERVED panel.css no longer defines .shcard2tag",
  /\.shcard2tag\s*\{/.test(css), false);
const js = await (await fetch(APP + "static/js/16-shadow-home.js")).text();
is("gate 1c: the SERVED shadow JS no longer emits class=\"shcard2tag\"",
  /class="shcard2tag"/.test(js), false);

/* the real records, and the spread of kinds across them */
const apiRaw = await (await fetch(APP + "api/shadow/missions")).json();
const missions = apiRaw.missions || apiRaw;
const kinds = {};
for (const m of missions) kinds[m.template || "(none)"] = (kinds[m.template || "(none)"] || 0) + 1;
console.log("     missions on this backend: " + missions.length
  + "  kinds: " + JSON.stringify(kinds));

/* SHORT and LONG are picked from what is actually there, by objective length,
   rather than hard-coded ids -- the founder's store changes between runs. */
const byLen = [...missions].sort(
  (a, b) => (a.objective || "").length - (b.objective || "").length);
const SHORT = byLen[0], LONG = byLen[byLen.length - 1];
if (!SHORT || !LONG || SHORT.id === LONG.id){
  console.error("FATAL: need two missions with different objective lengths");
  process.exit(2);
}
console.log(`     short -> ${SHORT.id} (${(SHORT.objective || "").length} chars)`);
console.log(`     long  -> ${LONG.id} (${(LONG.objective || "").length} chars)`);

/* ── attach ─────────────────────────────────────────────────────────────── */
let target = null;
for (let t = 0; t < 20000 && !target; t += 250){
  try {
    const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
    target = list.find(x => x.type === "page" && x.url && x.url.includes(":" + PORT));
  } catch {}
  if (!target) await new Promise(r => setTimeout(r, 250));
}
if (!target){ console.error("FATAL: no page target on CDP :" + CDP_PORT); process.exit(2); }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pend = new Map();
let inflight = 0, lastNet = Date.now();
const pageErrors = [];
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)){ pend.get(m.id)(m); pend.delete(m.id); return; }
  if (m.method === "Network.requestWillBeSent"){ inflight++; lastNet = Date.now(); }
  if (m.method === "Network.loadingFinished" || m.method === "Network.loadingFailed"){
    inflight = Math.max(0, inflight - 1); lastNet = Date.now(); }
  if (m.method === "Runtime.exceptionThrown")
    pageErrors.push(m.params?.exceptionDetails?.exception?.description || "unknown");
};
const cdp = (method, params = {}) => new Promise((res, rej) => {
  const id = ++seq;
  pend.set(id, m => m.error ? rej(new Error(method + ": " + JSON.stringify(m.error))) : res(m.result));
  ws.send(JSON.stringify({ id, method, params }));
});
async function evql(expr){
  const r = await cdp("Runtime.evaluate",
    { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails)
    throw new Error(r.exceptionDetails.exception?.description
      || ("eval failed: " + expr.slice(0, 160)));
  return r.result.value;
}
async function until(expr, ms, what){
  for (let t = 0; t < ms; t += 200){
    try { if (await evql(expr)) return true; } catch {}
    await new Promise(r => setTimeout(r, 200));
  }
  throw new Error("readiness gate never satisfied: " + (what || expr));
}
const netIdle = async (ms = 6000) => {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline && (inflight > 0 || Date.now() - lastNet < 400))
    await new Promise(r => setTimeout(r, 100));
};
await cdp("Page.enable"); await cdp("Runtime.enable"); await cdp("Network.enable");

/* ── gate 2: HARD RELOAD, past the static cache ─────────────────────────── */
await cdp("Network.setCacheDisabled", { cacheDisabled: true });
await cdp("Page.reload", { ignoreCache: true });
await netIdle();
await until('typeof loadShadowHome === "function" && typeof openScreen === "function"',
  45000, "panel JS booted after the hard reload");
ok("gate 2: hard-reloaded (ignoreCache) and the panel booted");

/* the reloaded DOCUMENT is running the working tree -- asserted in the page,
   not in the fetch above, because a service worker or a memory cache could
   still hand the PAGE something the fetch never saw */
const liveCssHasTag = await evql(`(() => {
  for (const s of document.styleSheets){
    let rules; try { rules = s.cssRules; } catch { continue; }
    for (const r of rules || []) if ((r.selectorText || "").includes("shcard2tag")) return true;
  }
  return false;
})()`);
is("gate 2b: no .shcard2tag rule in any stylesheet the PAGE actually loaded",
  liveCssHasTag, false);

await evql(`(async () => { await loadShadowHome(true); openScreen("shadow"); })()`);
await netIdle();
await until(`document.querySelectorAll("[data-shtask]").length > 0`,
  45000, "task rows on the Shadow screen");
ok("gate 3: Shadow home rendered real task rows",
  await evql(`document.querySelectorAll("[data-shtask]").length`));

/* ── the measurement ────────────────────────────────────────────────────── */
/* Everything is read off getBoundingClientRect / getComputedStyle after a
   forced layout. `gap` is read from the head's computed style rather than
   assumed, so the BEFORE/AFTER delta is checked against what CSS actually
   says rather than against a number copied out of the stylesheet by hand. */
const MEASURE = (id) => `(() => {
  const card = document.querySelector('[data-shtaskcard="${id}"]');
  if (!card) return { error: "card not rendered for ${id}" };
  const head = card.querySelector(".shcard2head");
  if (!head) return { error: "no .shcard2head" };
  const r = (el) => { const b = el.getBoundingClientRect();
    return { x: +b.x.toFixed(1), y: +b.y.toFixed(1),
             w: +b.width.toFixed(1), h: +b.height.toFixed(1),
             right: +b.right.toFixed(1), bottom: +b.bottom.toFixed(1) }; };
  const cs = getComputedStyle(head);
  const obj = head.querySelector(".shcard2obj");
  const pill = head.querySelector(".shtpill") || head.lastElementChild;
  const kids = [...head.children].map(e => ({
    cls: e.className || e.tagName, w: +e.getBoundingClientRect().width.toFixed(1) }));
  /* the objective's OWN line box, to tell a collapsed head from a tall one */
  const rng = document.createRange(); rng.selectNodeContents(obj);
  const lines = [...rng.getClientRects()].map(b => +b.height.toFixed(1));
  const rowOf = (label) => {
    const row = [...card.querySelectorAll(".shcard2row")].find(x =>
      x.querySelector(".shcard2k")
      && x.querySelector(".shcard2k").textContent.trim() === label);
    return row ? r(row) : null;
  };
  const out = {
    cardW: +card.getBoundingClientRect().width.toFixed(1),
    head: r(head), obj: r(obj), pill: pill ? r(pill) : null,
    headGap: cs.gap || cs.columnGap, headPadLeft: cs.paddingLeft,
    kidCount: head.children.length, kids,
    objText: (obj.textContent || "").trim().slice(0, 48),
    objLines: lines.length, objLineHeights: lines,
    objTextH: +lines.reduce((a, b) => a + b, 0).toFixed(1),
    hasTagEl: !!card.querySelector(".shcard2tag"),
    tagWordInHead: /\\b(fix|feature|research|watch)\\b/i.test(head.textContent)
      && !/\\b(fix|feature|research|watch)\\b/i.test(obj.textContent),
    rowWhere: rowOf("where it runs"), rowTurn: rowOf("turn"),
  };
  out.objInsetFromHead = +(out.obj.x - out.head.x).toFixed(1);
  out.pillFlushRight = +(out.head.right - out.pill.right).toFixed(1);
  out.objToPillGap = +(out.pill.x - out.obj.right).toFixed(1);
  out.headMinusText = +(out.head.h - out.objTextH).toFixed(1);
  return out;
})()`;

/* THE BEFORE NUMBER, TAKEN FOR REAL. Re-inserts a badge of exactly the old
   shape at the old position, measures, then removes it and restores the head.
   Without this, "there is no leftover gap" is a claim about a number nobody
   has anything to compare against. The injected element carries the deleted
   rule's own box (flex:none + the padding it had) so the delta is the badge's
   true former footprint, not a bare unstyled span. */
const PROBE_BEFORE = (id) => `(() => {
  const card = document.querySelector('[data-shtaskcard="${id}"]');
  const head = card.querySelector(".shcard2head");
  const obj = head.querySelector(".shcard2obj");
  const before = obj.getBoundingClientRect().x;
  const tag = document.createElement("span");
  tag.id = "kt-injected-tag";
  tag.textContent = "fix";
  tag.style.cssText = "font:600 9px/1 ui-monospace,monospace;letter-spacing:.07em;"
    + "text-transform:uppercase;border-radius:5px;padding:4px 7px;flex:none";
  head.insertBefore(tag, head.firstChild);
  void head.offsetHeight;
  const withTag = {
    objX: +obj.getBoundingClientRect().x.toFixed(1),
    headH: +head.getBoundingClientRect().height.toFixed(1),
    tagW: +tag.getBoundingClientRect().width.toFixed(1),
    objW: +obj.getBoundingClientRect().width.toFixed(1),
  };
  tag.remove();
  void head.offsetHeight;
  const after = {
    objX: +obj.getBoundingClientRect().x.toFixed(1),
    headH: +head.getBoundingClientRect().height.toFixed(1),
    objW: +obj.getBoundingClientRect().width.toFixed(1),
  };
  return { restoredExactly: Math.abs(after.objX - before) < 0.5,
           withTag, after,
           objXShift: +(withTag.objX - after.objX).toFixed(1),
           objWGain: +(after.objW - withTag.objW).toFixed(1) };
})()`;

const CELLS = [
  { vw: 1440, vh: 900, layout: "normal"  },
  { vw: 820,  vh: 900, layout: "compact" },
];
const SUBJECTS = [{ tag: "short", m: SHORT }, { tag: "long", m: LONG }];
const results = {};

for (const cell of CELLS){
  await cdp("Emulation.setDeviceMetricsOverride",
    { width: cell.vw, height: cell.vh, deviceScaleFactor: 1, mobile: false });
  for (const s of SUBJECTS){
    /* a REAL CLICK on the REAL row, through the app's own delegated handler */
    await evql(`(() => { const r = document.querySelector('[data-shtask="${s.m.id}"]');
      if (r) r.click(); return !!r; })()`);
    await netIdle(2500);
    await until(`!!document.querySelector('[data-shtaskcard="${s.m.id}"]')`,
      20000, `card for ${s.m.id} at ${cell.vw}px`);
    const key = s.tag + "-" + cell.layout;
    const mm = await evql(MEASURE(s.m.id));
    const bb = await evql(PROBE_BEFORE(s.m.id));
    results[key] = { measure: mm, delta: bb, viewport: cell.vw + "x" + cell.vh };
    const shot = await cdp("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(ART, `kindtag-${key}.png`),
      Buffer.from(shot.data, "base64"));
  }
}
await cdp("Emulation.clearDeviceMetricsOverride");

/* ── assertions, per cell ───────────────────────────────────────────────── */
for (const [key, r] of Object.entries(results)){
  const m = r.measure, d = r.delta;
  if (m.error){ bad(key + ": " + m.error); continue; }
  console.log("\n--- " + key + " @ " + r.viewport + " ---");
  console.log("    " + JSON.stringify(m, null, 2).replace(/\n/g, "\n    "));
  console.log("    BEFORE/AFTER " + JSON.stringify(d));

  is(key + ": no .shcard2tag element in the card", m.hasTagEl, false);
  is(key + ": no kind word rendered in the head", m.tagWordInHead, false);
  is(key + ": the head holds exactly two children (objective, pill)",
    m.kidCount, 2);
  /* THE DEAD-WHITESPACE CHECK. flex + gap means a surviving zero-width child
     would push the objective right by one gap and show as nothing on screen. */
  is(key + ": objective starts flush at the head's content edge (0px inset)",
    m.objInsetFromHead, 0);
  if (m.kids.every(k => k.w > 0)) ok(key + ": no zero-width leftover child",
    JSON.stringify(m.kids.map(k => k.w)));
  else bad(key + ": a zero-width child survives in the head",
    JSON.stringify(m.kids));
  /* the pill is still pushed to the far end by shcard2obj's flex:1 */
  if (Math.abs(m.pillFlushRight) <= 0.5)
    ok(key + ": state pill flush to the head's right edge",
      m.pillFlushRight + "px");
  else bad(key + ": the pill drifted off the right edge",
    m.pillFlushRight + "px");
  /* the objective and the pill are one CSS gap apart -- not two (a leftover
     child), not zero (a collapsed row) */
  const want = parseFloat(m.headGap);
  if (Math.abs(m.objToPillGap - want) <= 0.5)
    ok(key + ": objective-to-pill gap is exactly the CSS gap",
      m.objToPillGap + "px vs css " + m.headGap);
  else bad(key + ": gap between objective and pill is not the CSS gap",
    "measured " + m.objToPillGap + "px, css says " + m.headGap);
  /* NOT COLLAPSED: the head is at least as tall as the text it contains */
  if (m.head.h >= m.objTextH - 0.5)
    ok(key + ": head not collapsed (h " + m.head.h + " >= text " + m.objTextH + ")");
  else bad(key + ": head collapsed below its own text",
    "head " + m.head.h + " < text " + m.objTextH);
  /* the rows below still start at the card's own left edge -- a reflow that
     only shows further down would land here */
  if (m.rowWhere && m.rowTurn && Math.abs(m.rowWhere.x - m.rowTurn.x) <= 0.5)
    ok(key + ": rows below the head share one left edge",
      m.rowWhere.x + " / " + m.rowTurn.x);
  else bad(key + ": the rows below the head disagree on their left edge",
    JSON.stringify([m.rowWhere && m.rowWhere.x, m.rowTurn && m.rowTurn.x]));
  /* the measured former footprint of the badge */
  if (d.restoredExactly) ok(key + ": DOM restored exactly after the before/after probe");
  else bad(key + ": the before/after probe did not restore the head");
  if (d.objXShift > 0)
    ok(key + ": the badge USED to push the objective right by "
      + d.objXShift + "px (tag " + d.withTag.tagW + "px + gap "
      + m.headGap + "); the objective gained " + d.objWGain + "px of width");
  else bad(key + ": injecting the old badge moved nothing -- the probe is not measuring the head");
}

/* the two objectives really are short vs wrapping, or the "long" cell proved
   nothing about wrapping */
const longLines = Object.entries(results)
  .filter(([k]) => k.startsWith("long")).map(([k, r]) => k + "=" + r.measure.objLines);
const shortLines = Object.entries(results)
  .filter(([k]) => k.startsWith("short")).map(([k, r]) => k + "=" + r.measure.objLines);
console.log("\nline counts -> short: " + shortLines.join(" ") + "  long: " + longLines.join(" "));
if (Object.entries(results).some(([k, r]) => k.startsWith("long") && r.measure.objLines > 1))
  ok("the long objective really does wrap in at least one layout");
else bad("neither long cell wrapped -- the wrapping case was never exercised",
  longLines.join(" "));

is("no uncaught page errors during the drive", pageErrors, []);

console.log("\nartifacts -> " + ART);
console.log(`\n${pass} passed, ${fail} failed`);
ws.close();
process.exit(fail ? 1 : 0);
