/* qa-shell/kindtag-shots.mjs -- the PICTURE of the removed kind badge.
 *
 * kindtag-head-check.mjs proves the geometry in numbers. This lane produces
 * what a founder can sign off by looking: the live Shadow view at :7681 with
 * the task list on screen, one card per state a card can be in, and a
 * BEFORE/AFTER pair on the same card in the same pixels.
 *
 * THE "BEFORE" IS A RECONSTRUCTION, AND IS LABELLED AS ONE. No screenshot of
 * the pre-edit build exists -- the change was made before any picture was
 * taken. So "before" here re-inserts a badge of the deleted rule's exact box
 * into the LIVE DOM at the position the old markup put it, shoots, and
 * removes it. That is honest evidence of what the founder used to see and is
 * NOT a capture of the old build; the filename and this comment both say so.
 *
 * Same backend rules as the sibling lane: :7681 only, and it refuses to run
 * if the served CSS still defines .shcard2tag (which would mean a stale tree).
 *
 * Run:  node qa-shell/kindtag-shots.mjs
 * Env:  KT_PORT (default 7681)  KT_CDP (default 9352)
 * Out:  qa-shell/artifacts/shot-*.png  +  shot-manifest.json
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const PORT = process.env.KT_PORT || "7681";
const CDP_PORT = process.env.KT_CDP || "9352";
const APP = `http://127.0.0.1:${PORT}/`;
const ART = path.join(path.dirname(fileURLToPath(import.meta.url)), "artifacts");
fs.mkdirSync(ART, { recursive: true });

const css = await (await fetch(APP + "static/panel.css")).text();
if (/\.shcard2tag\s*\{/.test(css)){
  console.error("FATAL: :" + PORT + " still serves .shcard2tag -- stale tree, refusing to shoot");
  process.exit(2);
}
console.log("gate: :" + PORT + " serves a panel.css with no .shcard2tag rule");

const apiRaw = await (await fetch(APP + "api/shadow/missions")).json();
const missions = apiRaw.missions || apiRaw;
console.log("missions: " + missions.length
  + "  templates: " + JSON.stringify(missions.reduce((a, m) => {
      a[m.template || "(none)"] = (a[m.template || "(none)"] || 0) + 1; return a; }, {})));

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
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)){ pend.get(m.id)(m); pend.delete(m.id); return; }
  if (m.method === "Network.requestWillBeSent"){ inflight++; lastNet = Date.now(); }
  if (m.method === "Network.loadingFinished" || m.method === "Network.loadingFailed"){
    inflight = Math.max(0, inflight - 1); lastNet = Date.now(); }
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
    throw new Error(r.exceptionDetails.exception?.description || "eval failed");
  return r.result.value;
}
async function until(expr, ms, what){
  for (let t = 0; t < ms; t += 200){
    try { if (await evql(expr)) return true; } catch {}
    await new Promise(r => setTimeout(r, 200));
  }
  throw new Error("never satisfied: " + (what || expr));
}
const netIdle = async (ms = 6000) => {
  const d = Date.now() + ms;
  while (Date.now() < d && (inflight > 0 || Date.now() - lastNet < 400))
    await new Promise(r => setTimeout(r, 100));
};
await cdp("Page.enable"); await cdp("Runtime.enable"); await cdp("Network.enable");
await cdp("Network.setCacheDisabled", { cacheDisabled: true });
await cdp("Page.reload", { ignoreCache: true });
await netIdle();
await until('typeof loadShadowHome === "function" && typeof openScreen === "function"',
  45000, "panel booted");
await evql(`(async () => { await loadShadowHome(true); openScreen("shadow"); })()`);
await netIdle();
await until(`document.querySelectorAll("[data-shtask]").length > 0`, 45000, "task rows");
console.log("shadow view open, "
  + await evql(`document.querySelectorAll("[data-shtask]").length`) + " rows in the list");

/* THE BADGE, RECONSTRUCTED. The deleted rule's own box, resolved against the
   page's live custom properties so the colour is the one the founder saw and
   not a guess -- var(--acc) on var(--acc-bg), the accent pair the rule used. */
const INJECT = (id) => `(() => {
  const card = document.querySelector('[data-shtaskcard="${id}"]');
  if (!card) return false;
  const head = card.querySelector(".shcard2head");
  if (head.querySelector("#kt-shot-tag")) return true;
  const cs = getComputedStyle(document.documentElement);
  const tag = document.createElement("span");
  tag.id = "kt-shot-tag";
  tag.textContent = (window.__ktTemplate || "fix");
  tag.style.cssText = "font:600 9px/1 ui-monospace,SFMono-Regular,monospace;"
    + "letter-spacing:.07em;text-transform:uppercase;"
    + "color:" + (cs.getPropertyValue("--acc") || "#8a5a2b").trim() + ";"
    + "background:" + (cs.getPropertyValue("--acc-bg") || "#f3e6d6").trim() + ";"
    + "border-radius:5px;padding:4px 7px;flex:none";
  head.insertBefore(tag, head.firstChild);
  return true;
})()`;
const REMOVE = `(() => { const t = document.querySelector("#kt-shot-tag");
  if (t) t.remove(); return !document.querySelector("#kt-shot-tag"); })()`;

/* one card per STATE, so the set covers what a card can be showing */
const byState = {};
for (const m of missions) if (!byState[m.state]) byState[m.state] = m;
const PICKS = Object.entries(byState).map(([state, m]) => ({ state, m }));
console.log("states on this backend: " + PICKS.map(p => p.state).join(", "));

const manifest = [];
const shoot = async (name, note) => {
  const s = await cdp("Page.captureScreenshot", { format: "png" });
  const file = "shot-" + name + ".png";
  fs.writeFileSync(path.join(ART, file), Buffer.from(s.data, "base64"));
  manifest.push({ file, note });
  console.log("  wrote " + file + "  -- " + note);
};

/* ── the per-state set (all AFTER, the real current build) ──────────────── */
for (const p of PICKS){
  await evql(`(() => { const r = document.querySelector('[data-shtask="${p.m.id}"]');
    if (r) r.click(); return !!r; })()`);
  await netIdle(2500);
  await until(`!!document.querySelector('[data-shtaskcard="${p.m.id}"]')`, 20000,
    "card for " + p.m.id);
  await shoot("after-" + p.state,
    `AFTER (real build) — state=${p.state} id=${p.m.id} template=${p.m.template}`);
}

/* ── the BEFORE/AFTER pair, same card, same pixels ──────────────────────── */
const pair = PICKS.find(p => p.state === "done") || PICKS[0];
await evql(`(() => { const r = document.querySelector('[data-shtask="${pair.m.id}"]');
  if (r) r.click(); return !!r; })()`);
await netIdle(2500);
await until(`!!document.querySelector('[data-shtaskcard="${pair.m.id}"]')`, 20000, "pair card");
await evql(`window.__ktTemplate = ${JSON.stringify(pair.m.template || "task")}`);

if (!(await evql(INJECT(pair.m.id)))) throw new Error("could not inject the badge");
await shoot("pair-before-RECONSTRUCTED",
  `BEFORE — RECONSTRUCTION, not a capture of the old build. Badge re-inserted `
  + `into the live DOM. state=${pair.state} id=${pair.m.id} template=${pair.m.template}`);
if (!(await evql(REMOVE))) throw new Error("could not remove the injected badge");
await shoot("pair-after",
  `AFTER (real build) — same card, same pixels. state=${pair.state} id=${pair.m.id}`);

/* the DOM is back to the shipped state -- asserted, not assumed */
const clean = await evql(`!document.querySelector("#kt-shot-tag")
  && !document.querySelector(".shcard2tag")`);
console.log("DOM restored to the shipped state: " + clean);
if (!clean){ console.error("FATAL: injected badge survived"); process.exit(2); }

fs.writeFileSync(path.join(ART, "shot-manifest.json"),
  JSON.stringify({ backend: APP, taken: new Date().toISOString(),
    missions: missions.length,
    templates: missions.reduce((a, m) => {
      a[m.template || "(none)"] = (a[m.template || "(none)"] || 0) + 1; return a; }, {}),
    shots: manifest }, null, 2));
console.log("\nartifacts -> " + ART);
ws.close();
process.exit(0);
