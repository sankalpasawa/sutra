/* qa-shell/apps-a11y-check.mjs — keyboard + current-marker checks for the Apps
 * screen (program step 84; APPS-DESIGN.md §5). DEPENDENCY-FREE raw CDP, same
 * envs as apps-check.mjs.
 */
const PORT = process.env.SHELL_DEBUG_PORT || "9223";
const URL_RE = new RegExp(process.env.QA_URL_RE || "127\\.0\\.0\\.1:8330");

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
async function check(name, expr, expect){
  try { const got = await evql(expr); const ok = expect === undefined ? !!got : JSON.stringify(got) === JSON.stringify(expect);
    if (ok){ passed++; console.log("ok   - " + name); } else { failed++; console.log("FAIL - " + name + "\n       got " + JSON.stringify(got) + " want " + JSON.stringify(expect)); } }
  catch (e){ failed++; console.log("FAIL - " + name + "\n       " + e.message); }
}
for (let i = 0; i < 60; i++){ if (await evql(`typeof openScreen === 'function'`)) break; await new Promise(r => setTimeout(r, 250)); }
await evql(`(S.openPanes = [], openScreen('modules'), S.ui.railOpen = 'org', render(), true)`);
for (let i = 0; i < 40; i++){ if (await evql(`!!document.querySelector('.mod .dpage nav')`)) break; await new Promise(r => setTimeout(r, 250)); }

await check("exactly one aria-current=true in the rail", `document.querySelectorAll('.mod .dpage nav [aria-current="true"]').length`, 1);
await check("the rail is a labelled landmark", `(document.querySelector('.mod .dpage nav')||{}).getAttribute('aria-label')`, "Departments");
await check("every department link and app row is reachable by Tab (anchors with href)", `[...document.querySelectorAll('.mod .dpage nav a[data-moddept], .mod .dpage nav a[data-modapp]')].every(a => a.getAttribute('href') !== null && a.tabIndex >= 0)`);
await check("the search field precedes the tree in document order", `(function(){ const n = document.querySelector('.mod .dpage nav'); return n && n.firstElementChild && n.firstElementChild.matches('input[data-modq]'); })()`);
await check("tree groups are native details/summary (Space toggles)", `document.querySelectorAll('.mod .dpage nav details.navgrp > summary').length > 0`);
const first = await evql(`(function(){ const a = [...document.querySelectorAll('[data-modapp]')].find(a => !a.dataset.modapp.startsWith('sys-')); return a ? a.dataset.modapp : null; })()`);
if (first){
  await evql(`(modOpenApp(${JSON.stringify(first)}), render(), true)`);
  await new Promise(r => setTimeout(r, 300));
  await check("the Edit in chat control is a real button with a title", `(function(){ const b = document.querySelector('.mod-hd [data-modedit]'); return !!b && b.tagName === 'BUTTON' && !!b.getAttribute('title'); })()`);
  await check("the open app is the single current element in the rail", `document.querySelectorAll('.mod .dpage nav [aria-current="true"]').length`, 1);
  await evql(`(S.modSel = null, render(), true)`);
} else console.log("skip - no user app rows in this registry");
console.log(`\napps a11y lane: ${passed} passed, ${failed} failed`);
ws.close();
process.exit(failed ? 1 : 0);
