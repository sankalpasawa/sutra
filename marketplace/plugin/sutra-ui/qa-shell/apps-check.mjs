/* qa-shell/apps-check.mjs — the Apps lane of the publish check (program step 81).
 *
 * Lane 1 (STATE): the page's own S + renderers, no doubles. Lane 2 is the
 * screenshot the caller takes afterwards. DEPENDENCY-FREE: raw CDP over Node's
 * built-in WebSocket (>=22), the nav-check.mjs pattern. Run via run.sh
 * (QA_SCRIPTS=$PWD/apps-check.mjs QA_BACKEND=repo bash run.sh) against the
 * real shell, or headless against a panel on another port:
 *   SHELL_DEBUG_PORT=9224 QA_URL_RE='127\.0\.0\.1:8331' node apps-check.mjs
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
async function evql(expr){ const r = await cdp("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || "eval failed: " + expr.slice(0, 80)); return r.result.value; }
await cdp("Runtime.enable"); await cdp("Network.enable"); await cdp("Page.enable");

let passed = 0, failed = 0;
async function check(name, expr, expect){
  try {
    const got = await evql(expr);
    const ok = expect === undefined ? !!got : JSON.stringify(got) === JSON.stringify(expect);
    if (ok){ passed++; console.log("ok   - " + name); } else { failed++; console.log("FAIL - " + name + "\n       got " + JSON.stringify(got) + " want " + JSON.stringify(expect)); }
  } catch (e){ failed++; console.log("FAIL - " + name + "\n       " + e.message); }
}

for (let i = 0; i < 60; i++){ if (await evql(`typeof openScreen === 'function' && document.querySelectorAll('#railnav [data-dest]').length === 6`)) break; await new Promise(r => setTimeout(r, 250)); }
await evql(`(S.openPanes = [], openScreen('modules'), S.ui.railOpen = 'org', render(), true)`);
for (let i = 0; i < 40; i++){ if (await evql(`!!document.querySelector('.mod .dpage')`)) break; await new Promise(r => setTimeout(r, 250)); }

await check("the Org accordion row reads Apps", `/>\\s*Apps\\s*</.test(document.getElementById('acc-org') ? document.getElementById('acc-org').innerHTML : '')`);
await check("the pane title reads Apps", `(document.querySelector('.pane.browse .ph h3')||{}).textContent`, "Apps");
await check("facets: Live · Draft · Directory · Apps, Apps pressed", `[...document.querySelectorAll('.mod .facets .seg button')].map(b => b.textContent + ':' + b.getAttribute('aria-pressed'))`, ["Live:false", "Draft:false", "Directory:false", "Apps:true"]);
await check("+ New app on the facets bar", `(document.querySelector('.mod [data-modnew]')||{}).textContent`, "+ New app");
await check("the rail is the shared dirRail (.dpage nav with D-chips)", `!!document.querySelector('.mod .dpage nav .chip')`);
await check("no Departments-handler attributes inside the Apps screen", `!document.querySelector('.mod [data-view], .mod [data-ref], .mod #dirQ')`);
await check("System apps listed at the root", `[...document.querySelectorAll('.mod main [data-modapp]')].map(a => a.dataset.modapp).filter(x => x.startsWith('sys-')).length`, 3);
await check("the word module never reaches the operator", `!/\\bmodules?\\b/i.test(document.querySelector('.mod').innerText.replace(/module\\.json|\\.sutra-ui\\/modules/g, ''))`);
const first = await evql(`(function(){ const a = [...document.querySelectorAll('[data-modapp]')].find(a => !a.dataset.modapp.startsWith('sys-')) || document.querySelector('[data-modapp]'); return a ? a.dataset.modapp : null; })()`);
if (first){
  await evql(`(modOpenApp(${JSON.stringify(first)}), render(), true)`);
  await new Promise(r => setTimeout(r, 300));
  await check("app view: a header with chip, crumb, name", `!!document.querySelector('.mod-hd .chip') && !!document.querySelector('.mod-hd .crumb') && !!document.querySelector('.mod-hd h1')`);
  await check("app view: nothing below the header but the app body", `(function(){ const m = document.querySelector('.mod main'); return m.children.length === 2 && m.children[0].classList.contains('mod-hd') && m.children[1].classList.contains('mod-body'); })()`);
  await check("no action row (Move / Archive / Open full width)", `!/Move…|Archive|Open full width/.test(document.querySelector('.mod main').innerText)`);
  const sys = first.startsWith("sys-");
  await check(sys ? "a System app carries no Edit in chat" : "one Edit in chat button on a user app", `document.querySelectorAll('.mod-hd [data-modedit]').length`, sys ? 0 : 1);
  await check("the open app is current in the rail", `document.querySelectorAll('.mod .dpage nav [aria-current="true"]').length`, 1);
  await evql(`(S.modSel = null, render(), true)`);
} else {
  console.log("skip - no app rows in this registry; app-view checks not exercised");
}
await check("state: the query key is the root subtree read", `S.modKey`, "?subtree=1");

console.log(`\napps lane: ${passed} passed, ${failed} failed`);
ws.close();
process.exit(failed ? 1 : 0);
