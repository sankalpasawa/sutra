/* one-shot: what covers the home composer? */
const PORT = process.env.SHELL_DEBUG_PORT || "9223";
let page = null;
for (let i = 0; i < 40 && !page; i++){
  try { const t = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    page = t.find(x => x.type === "page" && /127\.0\.0\.1:8330/.test(x.url || "")); } catch {}
  if (!page) await new Promise(r => setTimeout(r, 500));
}
if (!page){ console.error("no page"); process.exit(1); }
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pend = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pend.has(m.id)){ pend.get(m.id)(m); pend.delete(m.id); } };
const cdp = (method, params={}) => new Promise((res, rej) => {
  const id = ++seq; pend.set(id, m => m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result));
  ws.send(JSON.stringify({ id, method, params })); });
const ev = async (e) => { const r = await cdp("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || "eval fail");
  return r.result.value; };
for (let i = 0; i < 40; i++){
  if (await ev(`document.querySelectorAll('#railnav [data-dest]').length`) === 6) break;
  await new Promise(r => setTimeout(r, 250));
}
await ev(`(goDest("focus"), typeof openScreen === "function" && openScreen("shadow"),
  typeof render === "function" && render(), true)`);
await new Promise(r => setTimeout(r, 1500));
console.log(await ev(`(() => {
  const el = document.querySelector("[data-shhomecompose]");
  if (!el) return "NO COMPOSER";
  el.scrollIntoView({block:"center"});
  const r = el.getBoundingClientRect();
  const cx = r.x + r.width/2, cy = r.y + r.height/2;
  const hit = document.elementFromPoint(cx, cy);
  const col = el.closest(".shchatcol");
  const cr = col ? col.getBoundingClientRect() : null;
  return JSON.stringify({
    composer: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
    point: [Math.round(cx), Math.round(cy)],
    viewport: [innerWidth, innerHeight],
    hit: hit ? hit.tagName + "." + (hit.className || "") : "none",
    hitZ: hit ? getComputedStyle(hit).zIndex + "/" + getComputedStyle(hit).position : "-",
    column: cr ? {y: Math.round(cr.y), h: Math.round(cr.height), overflow: getComputedStyle(col).overflow} : null,
    tabs: document.querySelectorAll("[data-shchat]").length,
  }, null, 1); })()`));
process.exit(0);
