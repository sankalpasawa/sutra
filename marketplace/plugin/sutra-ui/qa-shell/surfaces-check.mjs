/* qa-shell/surfaces-check.mjs — the floor-level ALL-SURFACES smoke lane.
 *
 * Observations pass 2026-08-26: the dead-wire disease is app-wide, so every
 * screen gets at least this floor: it opens through the shell's own
 * openScreen() (loaders fire), renders NON-EMPTY, and the whole sweep ends
 * with zero uncaught page errors. Run beside the deep lanes via QA_SCRIPTS.
 * Dependency-free CDP like nav-check.mjs; run via run.sh only.
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
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || "eval failed");
  return r.result.value;
}
for (let i = 0; i < 40; i++){
  if (await evql(`document.querySelectorAll('#railnav [data-dest]').length`) === 6) break;
  await new Promise(r => setTimeout(r, 250));
}
await evql(`(window.__qaErrs = [], window.addEventListener("error",
  e => window.__qaErrs.push(String(e.message).slice(0,120))), true)`);
const keys = await evql(`Object.keys(SCREENS)`);
let passed = 0, failed = 0;
for (const k of keys){
  try {
    await evql(`(typeof openScreen === "function" ? openScreen(${JSON.stringify(k)})
      : (S.screen = ${JSON.stringify(k)}), typeof render === "function" && render(), true)`);
    let body = "";
    for (let t = 0; t < 4000; t += 200){
      body = await evql(`(document.getElementById("scBody") || {}).innerHTML || ""`);
      if (body.length > 40) break;
      await new Promise(r => setTimeout(r, 200));
    }
    if (body.length > 40){ passed++; console.log("ok   - screen renders: " + k); }
    else { failed++; console.log("FAIL - screen renders: " + k + " (empty body)"); }
  } catch (e){ failed++; console.log("FAIL - screen renders: " + k + " " + e.message.slice(0, 80)); }
}
const errs = await evql(`window.__qaErrs`);
if ((errs || []).length){ failed++; console.log("FAIL - sweep page errors: " + JSON.stringify(errs)); }
else { passed++; console.log("ok   - zero page errors across the sweep"); }
console.log(`\nsurfaces-check: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
