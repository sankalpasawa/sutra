/* qa-shell/apps-electron-check.mjs — page-app containment (program step 83;
 * APPS-THREATS.md Information disclosure / Elevation rows).
 *
 * Asserts, against the live panel: every page-app iframe is
 * sandbox="allow-scripts" and never allow-same-origin; the served page carries
 * the CSP with no connect-src and frame-ancestors 'self'; and nothing named
 * openExternal / require / process is reachable from the panel window (a page
 * runs inside an opaque-origin iframe below that). DEPENDENCY-FREE raw CDP,
 * same envs as apps-check.mjs plus QA_ORIGIN for the fetch.
 */
const PORT = process.env.SHELL_DEBUG_PORT || "9223";
const URL_RE = new RegExp(process.env.QA_URL_RE || "127\\.0\\.0\\.1:8330");
const ORIGIN = process.env.QA_ORIGIN || "http://127.0.0.1:8330";

let page = null;
for (let i = 0; i < 40 && !page; i++){
  try { const t = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); page = t.find(x => x.type === "page" && URL_RE.test(x.url || "")); } catch {}
  if (!page) await new Promise(r => setTimeout(r, 500));
}
if (!page){ console.error("no shell page target on CDP after 20s"); process.exit(1); }
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pend = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pend.has(m.id)){ pend.get(m.id)(m); pend.delete(m.id); } };
const cdp = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pend.set(id, m => m.error ? rej(new Error(method + ": " + JSON.stringify(m.error))) : res(m.result)); ws.send(JSON.stringify({ id, method, params })); });
async function evql(expr){ const r = await cdp("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || "eval failed"); return r.result.value; }
await cdp("Runtime.enable"); await cdp("Network.enable"); await cdp("Page.enable");
let passed = 0, failed = 0;
function report(name, ok, detail){ if (ok){ passed++; console.log("ok   - " + name); } else { failed++; console.log("FAIL - " + name + (detail ? "\n       " + detail : "")); } }

for (let i = 0; i < 60; i++){ if (await evql(`typeof openScreen === 'function'`)) break; await new Promise(r => setTimeout(r, 250)); }
await evql(`(S.openPanes = [], openScreen('modules'), render(), true)`);
await new Promise(r => setTimeout(r, 400));

/* 1. every page app opened renders a sandboxed iframe with no same-origin */
const pages = await evql(`JSON.stringify((S.modules && S.modules.modules || []).filter(m => m.kind === 'page' && m.has_page).map(m => m.id))`);
for (const id of JSON.parse(pages || "[]")){
  await evql(`(modOpenApp(${JSON.stringify(id)}), render(), true)`);
  await new Promise(r => setTimeout(r, 300));
  const sb = await evql(`(function(){ const f = document.querySelector('.mod-body iframe.mod-frame'); return f ? f.getAttribute('sandbox') : null; })()`);
  report(`page app ${id}: iframe sandbox is exactly allow-scripts`, sb === "allow-scripts", "sandbox=" + sb);
}
if (!JSON.parse(pages || "[]").length) console.log("skip - no page apps in this registry; iframe checks not exercised");

/* 2. the served page carries the containment CSP */
const probeId = JSON.parse(pages || "[]")[0] || "sys-balance";
const csp = await evql(`fetch(${JSON.stringify(ORIGIN + "/api/modules/" + probeId + "/page")}).then(r => JSON.stringify({ status: r.status, csp: r.headers.get('content-security-policy') || '' }))`);
const c = JSON.parse(csp);
if (c.status === 200){
  report("page CSP has default-src 'none'", /default-src 'none'/.test(c.csp), c.csp);
  report("page CSP has frame-ancestors 'self'", /frame-ancestors 'self'/.test(c.csp), c.csp);
  report("page CSP has no connect-src (no network reach)", !/connect-src/.test(c.csp), c.csp);
} else console.log("skip - no page app to fetch (" + c.status + "); CSP asserted by test_modules_api test_11 instead");

/* 3. the panel window exposes no Electron bridge a page could climb to */
report("no openExternal / require / process on the panel window", await evql(`typeof window.openExternal === 'undefined' && typeof window.require === 'undefined' && typeof window.process === 'undefined'`));

console.log(`\napps electron lane: ${passed} passed, ${failed} failed`);
ws.close();
process.exit(failed ? 1 : 0);
