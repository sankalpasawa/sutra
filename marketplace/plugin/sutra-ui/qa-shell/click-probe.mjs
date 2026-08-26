/* qa-shell/click-probe.mjs — REAL synthetic mouse clicks on Shadow controls.
 * Diagnoses the founder's dead-button report 2026-08-26: function-level
 * drives pass while physical clicks die. Dispatches CDP Input mouse events
 * at the actual element coordinates and reports which layer saw the click.
 */
const PORT = process.env.SHELL_DEBUG_PORT || "9223";
let page = null;
for (let i = 0; i < 40 && !page; i++){
  try {
    const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    page = targets.find(t => t.type === "page" && /127\.0\.0\.1:8330/.test(t.url || ""));
  } catch {}
  if (!page) await new Promise(r => setTimeout(r, 500));
}
if (!page){ console.error("no page target"); process.exit(1); }
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
async function realClick(selector){
  const box = await evql(`(() => { const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) return null;
    el.scrollIntoView({ block: "center" });
    const r = el.getBoundingClientRect();
    const x = r.x + r.width/2, y = r.y + r.height/2;
    const hit = document.elementFromPoint(x, y);
    return { x, y, w: r.width, h: r.height,
      hitIsTarget: hit === el || (el.contains && el.contains(hit)),
      hitDesc: hit ? hit.tagName + "." + (hit.className || "") + " " +
        JSON.stringify(hit.dataset || {}) : "none" }; })()`);
  if (!box) return { found: false };
  if (!box.hitIsTarget)
    console.log("       COVERED: point hits " + box.hitDesc);
  for (const type of ["mousePressed", "mouseReleased"]){
    await cdp("Input.dispatchMouseEvent", { type, x: box.x, y: box.y,
      button: "left", clickCount: 1 });
  }
  await new Promise(r => setTimeout(r, 400));
  return { found: true, box };
}
for (let i = 0; i < 40; i++){
  if (await evql(`document.querySelectorAll('#railnav [data-dest]').length`) === 6) break;
  await new Promise(r => setTimeout(r, 250));
}
/* capture-phase probes at document root + the app element: which layers see it */
await evql(`(window.__probe = { docCapture: 0, docBubble: 0, lastTarget: "" },
  document.addEventListener("click", e => { window.__probe.docCapture++;
    window.__probe.lastTarget = (e.target.tagName || "") + "." + (e.target.className || "") } , true),
  document.addEventListener("click", e => { window.__probe.docBubble++; }),
  true)`);
/* open the shadow home */
await evql(`(goDest("focus"), typeof openScreen === "function" && openScreen("shadow"),
  typeof render === "function" && render(), true)`);
for (let i = 0; i < 40; i++){
  if (await evql(`document.querySelectorAll(".shtab").length >= 2`)) break;
  await new Promise(r => setTimeout(r, 250));
}
let passed = 0, failed = 0;
function report(name, ok, detail){
  if (ok){ passed++; console.log("ok   - " + name); }
  else { failed++; console.log("FAIL - " + name + (detail ? "\n       " + detail : "")); }
}
/* T1: the Working tab via REAL mouse */
await evql(`S.shadowTab = "watching"`);
const t1 = await realClick('[data-shtab="working"]');
const probe1 = await evql(`window.__probe`);
const tab = await evql(`S.shadowTab`);
report("T1 real click on the Working tab switches the tab",
  t1.found && tab === "working",
  JSON.stringify({ found: t1.found, tab, probe: probe1 }));
/* T2: memory action button via REAL mouse (probe counter, not the API) */
await evql(`(window.__shPostLog = [], window.__origShadowPost = shadowPost,
  window.shadowPost = (p, b) => { window.__shPostLog.push(p);
    return Promise.resolve({ ok: true, json: async () => ({}) }); }, true)`);
const memBtn = await evql(`!!document.querySelector("[data-shconfirm], [data-shrevoke]")`);
if (memBtn){
  const t2 = await realClick('[data-shconfirm], [data-shrevoke]');
  const posts = await evql(`window.__shPostLog`);
  report("T2 real click on a memory action reaches shadowPost",
    t2.found && posts.length >= 1, JSON.stringify({ posts }));
} else { console.log("SKIP - T2 no memory buttons rendered"); }
/* T3: a mission action button via REAL mouse */
const actBtn = await evql(`!!document.querySelector("[data-shact][data-shmid]")`);
if (actBtn){
  const before = await evql(`window.__shPostLog.length`);
  const t3 = await realClick('[data-shact][data-shmid]');
  const after = await evql(`window.__shPostLog.length`);
  report("T3 real click on a mission action reaches shadowPost",
    t3.found && after > before, JSON.stringify({ before, after }));
} else { console.log("SKIP - T3 no mission action buttons rendered"); }
/* restore */
await evql(`(window.shadowPost = window.__origShadowPost, true)`);
const probeEnd = await evql(`window.__probe`);
console.log("probe totals: " + JSON.stringify(probeEnd));
console.log(`\nclick-probe: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
