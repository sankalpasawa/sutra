/* render_check.mjs -- C36: render a page fragment in headless Chrome over raw
 * CDP (the qa-shell/apps-check.mjs pattern; Node >= 22 WebSocket, no deps).
 *   node render_check.mjs <file-or-http url> <chrome binary>
 * Prints one JSON line: {ok, errors:[...], text_len}. ok = no exceptions, no
 * console errors, no failed loads, non-empty body text. */
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
const [url, chrome] = process.argv.slice(2);
if (!url || !chrome){ console.log(JSON.stringify({ ok: false, errors: ["usage: render_check.mjs <url> <chrome>"] })); process.exit(2); }
const port = 9400 + Math.floor(Math.random() * 400);
/* a real temp profile dir (codex R2 P2): mkdtemp under os.tmpdir(), removed on exit */
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "kit-chrome-"));
const proc = spawn(chrome, ["--headless=new", "--remote-debugging-port=" + port, "--no-first-run", "--no-default-browser-check",
  "--disable-gpu", "--user-data-dir=" + profile, "about:blank"], { stdio: "ignore" });
const done = (out) => { try { proc.kill(); } catch {} try { fs.rmSync(profile, { recursive: true, force: true }); } catch {} console.log(JSON.stringify(out)); process.exit(0); };
let list = null;
for (let i = 0; i < 40 && !list; i++){
  try { list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); } catch {}
  if (!list) await new Promise(r => setTimeout(r, 250));
}
list = (list || []).filter(t => t.type === "page" && t.webSocketDebuggerUrl);
if (!list.length) done({ ok: false, errors: ["chrome did not expose a page target"] });
const ws = new WebSocket(list[0].webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pend = new Map(); const errors = []; let loadedRes = null;
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)){ pend.get(m.id)(m); pend.delete(m.id); return; }
  if (m.method === "Page.loadEventFired" && loadedRes) loadedRes();
  if (m.method === "Runtime.exceptionThrown") errors.push("exception: " + (m.params.exceptionDetails?.exception?.description || m.params.exceptionDetails?.text || "").slice(0, 160));
  if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") errors.push("console.error: " + (m.params.args || []).map(a => a.value || a.description || "").join(" ").slice(0, 160));
  if (m.method === "Log.entryAdded" && m.params.entry?.level === "error") errors.push("log: " + String(m.params.entry.text).slice(0, 160));
  /* an aborted request is a navigation Chrome replaced (the about:blank it started on), not a failed load (kit 1.1.0) */
  if (m.method === "Network.loadingFailed" && !m.params.canceled && m.params.errorText !== "net::ERR_ABORTED") errors.push("load failed: " + (m.params.errorText || ""));
};
const cdp = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pend.set(id, m => m.error ? rej(new Error(method + ": " + JSON.stringify(m.error))) : res(m.result)); ws.send(JSON.stringify({ id, method, params })); });
try {
  await cdp("Runtime.enable"); await cdp("Log.enable"); await cdp("Network.enable"); await cdp("Page.enable");
  errors.length = 0;                                       /* nothing from before our navigation counts */
  let nav = null;
  for (let attempt = 0; attempt < 4; attempt++){
    nav = await cdp("Page.navigate", { url });
    if (!nav || nav.errorText !== "net::ERR_ABORTED") break;
    /* on a warm start the initial about:blank commit can abort a navigation issued too early; try again */
    await new Promise(r => setTimeout(r, 300));
  }
  if (nav && nav.errorText) errors.push("navigate: " + nav.errorText);
  /* armed only after the navigation was accepted, so about:blank's own load event cannot satisfy it */
  const loaded = new Promise(r => { loadedRes = r; });
  /* wait for the load event: a cold headless start takes well over the fixed 700 ms this used to sleep (kit 1.1.0) */
  const inTime = await Promise.race([loaded.then(() => true), new Promise(r => setTimeout(() => r(false), 10000))]);
  if (!inTime) errors.push("load event did not fire within 10 s");
  await new Promise(r => setTimeout(r, 250));              /* let load-time scripts settle */
  const r = await cdp("Runtime.evaluate", { expression: "document.body ? document.body.innerText.trim().length : 0", returnByValue: true });
  const textLen = r.result?.value || 0;
  if (!textLen) errors.push("empty body");
  done({ ok: errors.length === 0, errors, text_len: textLen });
} catch (e) {
  done({ ok: false, errors: [String(e.message || e)] });
}
