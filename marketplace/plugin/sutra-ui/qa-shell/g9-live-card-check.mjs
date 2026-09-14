/* qa-shell/g9-live-card-check.mjs -- G9 through the APP'S OWN DATA PATH.
 *
 * The sibling check (g9-budget-check.mjs) calls shadowTaskCardHtml() with a
 * hand-built object. That proves the renderer and the stylesheet agree; it
 * does NOT prove the app ever hands the renderer a record of that shape.
 * This lane closes that gap end to end:
 *
 *     real mission files on disk
 *       -> GET /api/shadow/missions           (the real endpoint)
 *       -> loadShadowHome()                   (the real loader)
 *       -> openScreen("shadow")               (the real navigation)
 *       -> a real click on a real task row    (the real delegated handler)
 *       -> the card the founder actually sees
 *
 * Nothing is injected. The only thing arranged is WHICH missions exist, via
 * SUTRA_SHADOW_HOME pointing at a throwaway store -- the founder's live
 * Shadow home is never read or written.
 *
 * THE FOUR STATES, and what each is really guarding:
 *   low     3 / 20   calm, a short bar
 *   high   19 / 20   critical, a nearly full bar
 *   over   26 / 20   turns_used > max_turns -- MUST CLAMP. The failure is a
 *                    fill wider than its track, spilling across the card.
 *   nomax   4 / --   max_turns ABSENT from the record. The failure is a
 *                    NaN width, a zero-length stub, or the literal string
 *                    "NaN"/"undefined" on screen. Correct is NO BAR.
 *
 * Readiness is polled, never slept, and every state carries a hard timeout
 * that names itself.
 *
 * Setup:
 *   SUTRA_UI_REPO=$PWD SUTRA_SHADOW_HOME=/tmp/g9-shadow-home \
 *     .venv/bin/python qa-shell/g9-seed-missions.py
 *   SUTRA_SHADOW_HOME=/tmp/g9-shadow-home .venv/bin/python -m uvicorn \
 *     app:app --host 127.0.0.1 --port 8343
 *   node qa-shell/g9-live-card-check.mjs
 *
 * Env: G9_PORT (default 8343)  G9_CDP (default 9343)  G9_IDS (ids json)
 * Out: qa-shell/artifacts/g9-live-{low,high,over,nomax}.png
 */
import fs from "fs";
import path from "path";
/* fileURLToPath, NOT new URL(...).pathname -- this checkout lives under a
   directory with a space in it, and .pathname hands back the percent-encoded
   form, which would silently write artifacts into a decoy tree. */
import { fileURLToPath } from "url";

const PORT = process.env.G9_PORT || "8343";
const CDP_PORT = process.env.G9_CDP || "9343";
const IDS_FILE = process.env.G9_IDS || "/tmp/g9-shadow-home/g9-ids.json";
const APP = `http://127.0.0.1:${PORT}/`;
const ART = path.join(path.dirname(fileURLToPath(import.meta.url)), "artifacts");
fs.mkdirSync(ART, { recursive: true });
if (/%[0-9A-Fa-f]{2}/.test(ART)){
  console.error("FATAL: artifact dir is percent-encoded: " + ART); process.exit(2);
}
const IDS = JSON.parse(fs.readFileSync(IDS_FILE, "utf8"));
console.log("artifacts -> " + ART);
console.log("mission ids -> " + JSON.stringify(IDS));

const STATE_TIMEOUT_MS = 20000, READY_TIMEOUT_MS = 45000;
let pass = 0, fail = 0;
const ok  = (n, d) => { pass++; console.log("ok   - " + n + (d ? "  [" + d + "]" : "")); };
const bad = (n, d) => { fail++; console.log("FAIL - " + n + (d ? "\n       " + d : "")); };
const is  = (n, got, want) => (JSON.stringify(got) === JSON.stringify(want))
  ? ok(n, JSON.stringify(got)) : bad(n, "got " + JSON.stringify(got) + " want " + JSON.stringify(want));
function withTimeout(label, ms, p){
  let t;
  return Promise.race([p.finally(() => clearTimeout(t)),
    new Promise((_, rej) => { t = setTimeout(() =>
      rej(new Error("TIMEOUT after " + ms + "ms in state: " + label)), ms); })]);
}

/* ── GATE 1: HTTP 200 ───────────────────────────────────────────────────── */
let httpOk = false;
for (let t = 0; t < READY_TIMEOUT_MS && !httpOk; t += 250){
  try { httpOk = (await fetch(APP, { redirect: "manual" })).status === 200; } catch {}
  if (!httpOk) await new Promise(r => setTimeout(r, 250));
}
if (!httpOk){ console.error("FATAL: no 200 from " + APP); process.exit(2); }
ok("gate 1: backend 200 on :" + PORT);

/* the API really is serving the seeded records, including the ceiling-less
   one -- if this is wrong the browser assertions below are meaningless */
const apiMissions = await (await fetch(APP + "api/shadow/missions")).json();
const apiList = apiMissions.missions || apiMissions;
is("gate 1b: the real API serves all four seeded missions", apiList.length, 4);
const apiNomax = apiList.find(m => m.id === IDS.nomax);
is("gate 1c: the ceiling-less record reaches the API with NO max_turns key",
  Object.prototype.hasOwnProperty.call(apiNomax, "max_turns"), false);

/* ── attach ─────────────────────────────────────────────────────────────── */
let target = null;
for (let t = 0; t < READY_TIMEOUT_MS && !target; t += 250){
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
    throw new Error(r.exceptionDetails.exception?.description || ("eval failed: " + expr.slice(0, 120)));
  return r.result.value;
}
async function until(expr, ms, what){
  for (let t = 0; t < ms; t += 200){
    try { if (await evql(expr)) return true; } catch {}
    await new Promise(r => setTimeout(r, 200));
  }
  throw new Error("readiness gate never satisfied: " + (what || expr));
}
const netIdle = async (ms = 5000) => {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline && (inflight > 0 || Date.now() - lastNet < 400))
    await new Promise(r => setTimeout(r, 100));
};
await cdp("Page.enable"); await cdp("Runtime.enable"); await cdp("Network.enable");

/* ── GATE 2: the real loader + real navigation ──────────────────────────── */
await withTimeout("boot", READY_TIMEOUT_MS,
  until('typeof loadShadowHome === "function" && typeof openScreen === "function"',
    READY_TIMEOUT_MS, "panel JS loaded"));
ok("gate 2: panel booted (loadShadowHome + openScreen live)");

await evql(`(async () => { await loadShadowHome(true); openScreen("shadow"); })()`);
await netIdle();
await withTimeout("shadow-screen", READY_TIMEOUT_MS,
  until(`document.querySelectorAll("[data-shtask]").length >= 4`,
    READY_TIMEOUT_MS, "four task rows on the Shadow screen"));
ok("gate 3: Shadow home rendered four real task rows",
  await evql(`document.querySelectorAll("[data-shtask]").length`));

/* ── the four states, each reached by a REAL CLICK on a REAL ROW ────────── */
const STATES = [
  { name: "low",   id: IDS.low,   file: "g9-live-low.png",
    used: 3,  max: 20, pct: 15,  sev: "p-ok" },
  { name: "high",  id: IDS.high,  file: "g9-live-high.png",
    used: 19, max: 20, pct: 95,  sev: "p-block" },
  { name: "over",  id: IDS.over,  file: "g9-live-over.png",
    used: 26, max: 20, pct: 100, sev: "p-block" },
  { name: "nomax", id: IDS.nomax, file: "g9-live-nomax.png",
    used: 4,  max: null, pct: null, sev: null },
];

const MEASURE = (id) => `(() => {
  const card = document.querySelector('[data-shtaskcard="${id}"]');
  if (!card) return { error: "card not rendered" };
  const cr = card.getBoundingClientRect();
  const budgetRow = [...card.querySelectorAll(".shcard2row")]
    .find(r => r.querySelector(".shcard2k") &&
               r.querySelector(".shcard2k").textContent.trim() === "budget");
  const text = budgetRow
    ? budgetRow.querySelector(".shcard2v").textContent.replace(/\\s+/g, " ").trim() : null;
  const cardText = card.textContent;
  const out = {
    text,
    /* the degradation failures, checked as literal rendered text */
    saysNaN: /NaN/.test(cardText),
    saysUndefined: /undefined/.test(cardText),
    cardW: Math.round(cr.width)
  };
  const track = card.querySelector(".shcard2bar");
  if (!track){ out.hasBar = false; return out; }
  const fill = track.querySelector("i");
  const tr = track.getBoundingClientRect(), fr = fill.getBoundingClientRect();
  out.hasBar = true;
  out.sev = fill.className;
  out.colour = getComputedStyle(fill).backgroundColor;
  out.inlineWidth = fill.style.width;
  out.trackContentW = track.clientWidth;
  out.fillW = Math.round(fr.width);
  out.ratio = track.clientWidth ? Math.round((fr.width / track.clientWidth) * 100) : null;
  /* OVERFLOW, measured three ways -- this is the assertion the "over" state
     exists for: a fill wider than its track, a track wider than its card, or
     either one spilling past the card's right edge */
  out.fillWithinTrack = fr.right <= tr.right + 0.5;
  out.trackWithinCard = tr.right <= cr.right + 0.5 && tr.left >= cr.left - 0.5;
  out.noHorizontalSpill = card.scrollWidth <= card.clientWidth + 1;
  out.visible = tr.width > 0 && tr.height > 0;
  return out;
})()`;

const seen = {};
for (const s of STATES){
  try {
    await withTimeout(s.name, STATE_TIMEOUT_MS, (async () => {
      /* a REAL click on the row, through the delegated handler */
      const clicked = await evql(`(() => {
        const row = document.querySelector('[data-shtask="${s.id}"]');
        if (!row) return false;
        row.scrollIntoView({ block: "center" });
        row.click();
        return true;
      })()`);
      is(`[${s.name}] clicked its real task row`, clicked, true);
      await until(`!!document.querySelector('[data-shtaskcard="${s.id}"]')`,
        STATE_TIMEOUT_MS, `card ${s.id} rendered after click`);
      await netIdle(3000);

      const m = await evql(MEASURE(s.id));
      seen[s.name] = m;
      console.log(`     [${s.name}] ` + JSON.stringify(m));

      /* degradation is checked on EVERY state, not just nomax */
      is(`[${s.name}] no "NaN" anywhere on the card`, m.saysNaN, false);
      is(`[${s.name}] no "undefined" anywhere on the card`, m.saysUndefined, false);

      if (s.sev === null){
        is(`[${s.name}] a record with NO max_turns draws NO bar`, m.hasBar, false);
        is(`[${s.name}] and still prints its budget row`,
          /turn 4 of 0/.test(m.text || ""), true);
      } else {
        is(`[${s.name}] bar rendered and visible`, m.visible, true);
        is(`[${s.name}] fill is ${s.pct}% of its track`, m.ratio, s.pct);
        is(`[${s.name}] severity ${s.sev}`, m.sev, s.sev);
        is(`[${s.name}] fill does not overflow the track`, m.fillWithinTrack, true);
        is(`[${s.name}] track sits inside the card`, m.trackWithinCard, true);
        is(`[${s.name}] the card does not scroll sideways`, m.noHorizontalSpill, true);
      }

      const shot = await cdp("Page.captureScreenshot", { format: "png" });
      fs.writeFileSync(path.join(ART, s.file), Buffer.from(shot.data, "base64"));
    })());
  } catch (e){
    bad(`[${s.name}] state failed`, e.message);
    console.log("     ^^ the state that hung/failed is: " + s.name);
  }
}

/* the clamp, stated as its own fact: 26 of 20 must render exactly as wide as
   19 of 20 does not -- it must be the FULL track and no wider */
if (seen.over && seen.over.hasBar){
  is("over-budget clamps to exactly the track width",
    seen.over.fillW <= seen.over.trackContentW, true);
  is("over-budget inline width is capped at 100%", seen.over.inlineWidth, "100%");
  console.log("     over: fill " + seen.over.fillW + "px in a "
    + seen.over.trackContentW + "px track (inline " + seen.over.inlineWidth + ")");
}

for (const s of STATES){
  const p = path.join(ART, s.file);
  const sz = fs.existsSync(p) ? fs.statSync(p).size : 0;
  is(`artifact ${s.file} written, non-zero`, sz > 0, true);
}
is("zero uncaught page errors during the drive", pageErrors, []);

console.log("\n=== G9 LIVE: " + pass + " passed, " + fail + " failed ===");
process.exit(fail ? 1 : 0);
