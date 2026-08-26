/* qa-shell/path-probe.mjs — walk the founder's EXACT path with a real mouse:
 * Now card -> router landing on Focus > Shadow -> tab, action, composer.
 * Instruments render() to catch re-render storms that eat clicks. */
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
async function until(expr, ms = 8000){
  for (let t = 0; t < ms; t += 150){
    if (await evql(expr)) return true;
    await new Promise(r => setTimeout(r, 150));
  }
  return false;
}
async function realClick(selector){
  const box = await evql(`(() => { const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) return null; el.scrollIntoView({ block: "center" });
    const r = el.getBoundingClientRect();
    const x = r.x + r.width/2, y = r.y + r.height/2;
    const hit = document.elementFromPoint(x, y);
    return { x, y, hitOk: hit === el || (el.contains && el.contains(hit)) }; })()`);
  if (!box) return { found: false };
  for (const type of ["mousePressed", "mouseReleased"])
    await cdp("Input.dispatchMouseEvent", { type, x: box.x, y: box.y, button: "left", clickCount: 1 });
  await new Promise(r => setTimeout(r, 350));
  return { found: true, hitOk: box.hitOk };
}
let passed = 0, failed = 0;
function report(name, ok, detail){
  if (ok){ passed++; console.log("ok   - " + name); }
  else { failed++; console.log("FAIL - " + name + (detail ? "\n       " + detail : "")); }
}
for (let i = 0; i < 40; i++){
  if (await evql(`document.querySelectorAll('#railnav [data-dest]').length`) === 6) break;
  await new Promise(r => setTimeout(r, 250));
}
/* instrument render(): count calls; detect storms */
await evql(`(window.__renders = 0, window.__origRender = render,
  window.render = function(){ window.__renders++; return window.__origRender.apply(this, arguments); }, true)`);
/* P1: Now, wait for feed settle */
await evql(`(goDest("now"), render(), true)`);
await until(`typeof S !== "undefined" && S.needsYou !== undefined`);
await evql(`render()`);
const hasCard = await evql(`!!document.querySelector(".nycard .nyact")`);
if (!hasCard){ console.log("SKIP - P1 no Now cards (feed empty on this machine)");
  await evql(`(typeof openNeedsYouItem === "function" && openNeedsYouItem("sutra://shadow/home"), true)`);
} else {
  const c = await realClick(".nycard .nyact");
  report("P1 real click on a Now card's action", c.found && c.hitOk);
}
/* P2: landed? */
report("P2 landing: Focus > Shadow",
  await until(`S.ui.dest === "focus" && S.screen === "shadow"`));
await until(`S.shadowHomeDark === false`);
/* P3: the DOM must hold still — count actual scBody child replacements
   (render() may fire freely; REBUILDS are what eat clicks) */
await evql(`(window.__domChurn = 0, window.__mo = new MutationObserver(
    ms => { window.__domChurn += ms.length; }),
  window.__mo.observe(document.getElementById("scBody"), { childList: true }),
  true)`);
await new Promise(r => setTimeout(r, 2000));
const churn = await evql(`(window.__mo.disconnect(), window.__domChurn)`);
report("P3 landed home DOM holds still (childList mutations in 2s <= 3)",
  churn <= 3, "mutations=" + churn);
/* P4: real-mouse tab flip on the landed home */
await evql(`S.shadowTab = "working"; render()`);
const t = await realClick('[data-shtab="watching"]');
report("P4 real click flips to Watching on the landed home",
  t.found && await until(`S.shadowTab === "watching"`, 3000));
/* P5: composer — real click to focus, type, Enter (sendToShadow stubbed) */
await evql(`(window.__sends = [], window.__origSend = window.sendToShadow,
  window.sendToShadow = t => (window.__sends.push(t), Promise.resolve({})), true)`);
const comp = await realClick("[data-shhomecompose]");
if (comp.found){
  await cdp("Input.insertText", { text: "probe message" });
  for (const type of ["keyDown", "keyUp"])
    await cdp("Input.dispatchKeyEvent", { type, key: "Enter", code: "Enter",
      windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
  await new Promise(r => setTimeout(r, 400));
  const sends = await evql(`window.__sends`);
  report("P5 composer: type + Enter reaches sendToShadow",
    sends.length === 1 && /probe message/.test(sends[0] || ""),
    JSON.stringify({ sends }));
} else report("P5 composer present on the landed home", false);
await evql(`(window.sendToShadow = window.__origSend,
  window.render = window.__origRender, true)`);
console.log(`\npath-probe: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
