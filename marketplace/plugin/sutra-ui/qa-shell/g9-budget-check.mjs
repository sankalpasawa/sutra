/* qa-shell/g9-budget-check.mjs -- G9: the threshold-state invariant on the
 * Shadow task card.
 *
 * The card's budget row draws `turns_used / max_turns` as a length with a
 * threshold treatment (founder G9, 2026-09-15):
 *
 *     calm      pct <  60      .p-ok
 *     warning   60 <= pct <= 85 .p-warn
 *     critical  pct >  85      .p-block
 *     fallback  no ceiling     NO BAR AT ALL (not an empty one, not a full one)
 *
 * WHY A BROWSER AND NOT A STRING TEST. test_shadow_home.js already asserts the
 * markup and every boundary. What it cannot see is whether the bar has a
 * width, whether the three severities are three DIFFERENT colours once the
 * stylesheet has had its say, and whether the thing sits inside its card. That
 * is this lane's entire job: rendered geometry and rendered colour.
 *
 * READINESS IS POLLED, NEVER SLEPT. Three gates in order -- HTTP 200, then the
 * card selector present in the DOM, then network idle -- because a fixed sleep
 * is the bug it pretends to fix: too short and the check attaches to a blank
 * page, too long and every run pays for it. Each state additionally carries a
 * HARD TIMEOUT, so one stuck state fails fast and NAMES ITSELF instead of
 * hanging the run.
 *
 * Dependency-free raw CDP, same shape as nav-check.mjs / shadow-check.mjs.
 *
 * Run:  node qa-shell/g9-budget-check.mjs
 * Env:  G9_PORT (backend, default 8340)  G9_CDP (default 9343)
 * Out:  qa-shell/artifacts/g9-{low,mid,high,nomax}.png
 */
import fs from "fs";
import path from "path";
/* fileURLToPath, NOT new URL(...).pathname: this checkout lives under a
   directory with a space in it ("Joy Stephen"), and .pathname hands back the
   PERCENT-ENCODED form. Writing to that string silently creates a decoy
   "Joy%20Stephen" tree next to the real one and every artifact lands there --
   which a size check cannot catch, because it reads back the same wrong path. */
import { fileURLToPath } from "url";

const PORT = process.env.G9_PORT || "8340";
const CDP_PORT = process.env.G9_CDP || "9343";
const APP = `http://127.0.0.1:${PORT}/`;
const ART = path.join(path.dirname(fileURLToPath(import.meta.url)), "artifacts");
fs.mkdirSync(ART, { recursive: true });
/* prove the destination decodes to a real path before writing four files into
   it -- a wrong-but-consistent directory passes every downstream size check */
if (/%[0-9A-Fa-f]{2}/.test(ART)){
  console.error("FATAL: artifact dir is still percent-encoded: " + ART);
  process.exit(2);
}
console.log("artifacts -> " + ART);

const STATE_TIMEOUT_MS = 15000;   /* hard per-state cap */
const READY_TIMEOUT_MS = 45000;

let pass = 0, fail = 0;
const ok  = (n, d) => { pass++; console.log("ok   - " + n + (d ? "  [" + d + "]" : "")); };
const bad = (n, d) => { fail++; console.log("FAIL - " + n + (d ? "\n       " + d : "")); };
const is  = (n, got, want) => (JSON.stringify(got) === JSON.stringify(want))
  ? ok(n, JSON.stringify(got))
  : bad(n, "got " + JSON.stringify(got) + " want " + JSON.stringify(want));

/* a hard cap that says WHICH state it was guarding when it fired */
function withTimeout(label, ms, promise){
  let t;
  return Promise.race([
    promise.finally(() => clearTimeout(t)),
    new Promise((_, rej) => { t = setTimeout(
      () => rej(new Error("TIMEOUT after " + ms + "ms in state: " + label)), ms); }),
  ]);
}

/* ── GATE 1: the backend answers 200 ────────────────────────────────────── */
console.log("gate 1: polling " + APP + " for HTTP 200");
let httpOk = false;
for (let t = 0; t < READY_TIMEOUT_MS && !httpOk; t += 250){
  try { httpOk = (await fetch(APP, { redirect: "manual" })).status === 200; } catch {}
  if (!httpOk) await new Promise(r => setTimeout(r, 250));
}
if (!httpOk){ console.error("FATAL: backend never returned 200 on " + APP); process.exit(2); }
ok("gate 1: backend serving 200 on :" + PORT);

/* ── attach to the page target ──────────────────────────────────────────── */
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
    inflight = Math.max(0, inflight - 1); lastNet = Date.now();
  }
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
await cdp("Page.enable"); await cdp("Runtime.enable"); await cdp("Network.enable");

/* the renderer has to exist before any selector can */
await withTimeout("boot", READY_TIMEOUT_MS,
  until('typeof shadowTaskCardHtml === "function"', READY_TIMEOUT_MS, "panel JS loaded"));
ok("panel booted, shadowTaskCardHtml live");
is("the served bundle is the edited checkout",
  await evql('typeof shadowBudgetBarHtml === "function" && typeof shadowBudgetSev === "function"'),
  true);

/* ── the four G9 states, injected as props -- never reached organically ──
   Driving a real run to 85% of its budget would take a real worker and real
   turns. The renderer takes a mission object, so the state IS the prop. */
const STATES = [
  { name: "low",   file: "g9-low.png",   used: 5,  max: 20, pct: 25,  sev: "p-ok",
    objective: "Refactor the CSV importer" },
  { name: "mid",   file: "g9-mid.png",   used: 15, max: 20, pct: 75,  sev: "p-warn",
    objective: "Migrate the settings store" },
  { name: "high",  file: "g9-high.png",  used: 19, max: 20, pct: 95,  sev: "p-block",
    objective: "Chase the flaky overlay test" },
  { name: "nomax", file: "g9-nomax.png", used: 4,  max: 0,  pct: null, sev: null,
    objective: "Watch the deploy" },
];

const MOUNT = (s) => `(() => {
  const host = document.getElementById("g9-host") || document.createElement("div");
  host.id = "g9-host";
  host.setAttribute("style",
    "position:fixed;inset:0;z-index:99999;overflow:auto;padding:26px;"
    + "background:var(--bg,#111);display:block");
  host.innerHTML = shadowTaskCardHtml({
    id: "g9-${s.name}", objective: ${JSON.stringify(s.objective)},
    template: "fix", state: "running",
    turns_used: ${s.used}, max_turns: ${s.max},
    target_mode: "existing",
    done_when: [{ check: "the suite is green" }],
    updated_at: new Date(Date.now() - 4 * 60000).toISOString()
  });
  if (!host.isConnected) document.body.appendChild(host);
  return !!document.querySelector('#g9-host [data-shtaskcard="g9-${s.name}"]');
})()`;

const MEASURE = (s) => `(() => {
  const card = document.querySelector('#g9-host [data-shtaskcard="g9-${s.name}"]');
  if (!card) return { error: "card missing" };
  const track = card.querySelector(".shcard2bar");
  const row = card.querySelector(".shcard2row .shcard2k");
  const budgetRow = [...card.querySelectorAll(".shcard2row")]
    .find(r => r.querySelector(".shcard2k")?.textContent.trim() === "budget");
  const text = budgetRow ? budgetRow.querySelector(".shcard2v").textContent.trim().split("\\n")[0].trim() : null;
  if (!track) return { hasBar: false, text };
  const fill = track.querySelector("i");
  const tr = track.getBoundingClientRect(), fr = fill.getBoundingClientRect();
  return {
    hasBar: true, text,
    sev: fill.className,
    colour: getComputedStyle(fill).backgroundColor,
    /* against the CONTENT box: .ubar has a 1px border and the fill sits inside */
    ratio: track.clientWidth ? Math.round((fr.width / track.clientWidth) * 100) : null,
    trackH: Math.round(tr.height),
    visible: tr.width > 0 && tr.height > 0,
    insideCard: card.getBoundingClientRect().bottom >= tr.bottom
  };
})()`;

const colours = {};
for (const s of STATES){
  try {
    await withTimeout(s.name, STATE_TIMEOUT_MS, (async () => {
      /* GATE 2: the card selector actually exists in the DOM */
      is(`[${s.name}] card mounted`, await evql(MOUNT(s)), true);
      await until(`!!document.querySelector('#g9-host [data-shtaskcard="g9-${s.name}"]')`,
        STATE_TIMEOUT_MS, `card g9-${s.name} in DOM`);
      /* GATE 3: network idle -- nothing in flight for 400ms */
      const deadline = Date.now() + 5000;
      while (Date.now() < deadline && (inflight > 0 || Date.now() - lastNet < 400))
        await new Promise(r => setTimeout(r, 100));

      const m = await evql(MEASURE(s));
      console.log(`     [${s.name}] ` + JSON.stringify(m));

      if (s.sev === null){
        is(`[${s.name}] no ceiling draws NO bar`, m.hasBar, false);
        is(`[${s.name}] but keeps its budget text`, /turn 4 of 0/.test(m.text || ""), true);
      } else {
        is(`[${s.name}] bar is rendered and visible`, m.visible, true);
        is(`[${s.name}] fills ${s.pct}%`, m.ratio, s.pct);
        is(`[${s.name}] severity is ${s.sev}`, m.sev, s.sev);
        is(`[${s.name}] bar stays inside the card`, m.insideCard, true);
        is(`[${s.name}] count still printed`,
          new RegExp("turn " + s.used + " of " + s.max).test(m.text || ""), true);
        colours[s.name] = m.colour;
      }

      const shot = await cdp("Page.captureScreenshot", { format: "png" });
      fs.writeFileSync(path.join(ART, s.file), Buffer.from(shot.data, "base64"));
    })());
  } catch (e){
    bad(`[${s.name}] state failed`, e.message);
    console.log("     ^^ the state that hung/failed is: " + s.name);
  }
}

/* three severities must be three DIFFERENT rendered colours, or the threshold
   treatment is decoration -- a class-name assertion cannot catch this */
const cs = ["low", "mid", "high"].map(k => colours[k]);
is("calm / warning / critical are three distinct rendered colours",
  new Set(cs.filter(Boolean)).size, 3);
console.log("     colours: " + cs.join("  |  "));

/* every artifact exists on disk and is non-empty */
for (const s of STATES){
  const p = path.join(ART, s.file);
  const sz = fs.existsSync(p) ? fs.statSync(p).size : 0;
  is(`artifact ${s.file} written, non-zero`, sz > 0, true);
  console.log("     " + p + "  (" + sz + " bytes)");
}

is("zero uncaught page errors during the drive", pageErrors, []);

console.log("\n=== G9: " + pass + " passed, " + fail + " failed ===");
process.exit(fail ? 1 : 0);
