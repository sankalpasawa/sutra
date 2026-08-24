/* qa-shell/nav-check.mjs — the v3.3 SHELL lane of the publish check.
 *
 * Verifies the six-destination shell inside the real Sutra.app: destinations,
 * the second plane, the identity footer, the accent row, and the 2.118.1/2
 * hotfixes (loaders fire from the rail; the terminal cannot cover the detail).
 *
 * DEPENDENCY-FREE by design: raw CDP over Node's built-in WebSocket (>=22),
 * so it runs on a machine where playwright was never installed. Run it via
 * run.sh (QA_SCRIPT=$PWD/nav-check.mjs QA_BACKEND=repo bash run.sh), never
 * directly — run.sh owns the debug-mode/restore choreography.
 */
import fs from "fs";

const PORT = process.env.SHELL_DEBUG_PORT || "9223";
const OUT = new URL("./out/", import.meta.url).pathname;

const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const page = targets.find(t => t.type === "page" && /127\.0\.0\.1:8330/.test(t.url || ""));
if (!page){ console.error("no shell page target on CDP", targets.map(t=>t.url)); process.exit(1); }

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pend = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pend.has(m.id)){ pend.get(m.id)(m); pend.delete(m.id); } };
const cdp = (method, params={}) => new Promise((res, rej) => {
  const id = ++seq; pend.set(id, m => m.error ? rej(new Error(method+": "+JSON.stringify(m.error))) : res(m.result));
  ws.send(JSON.stringify({ id, method, params }));
});
async function evql(expr){
  const r = await cdp("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || "eval failed: " + expr.slice(0,80));
  return r.result.value;
}

let passed = 0, failed = 0;
async function check(name, expr, expect){
  try {
    const got = await evql(expr);
    const ok = expect === undefined ? !!got : JSON.stringify(got) === JSON.stringify(expect);
    if (ok){ passed++; console.log("ok   - " + name); }
    else { failed++; console.log("FAIL - " + name + "\n       got " + JSON.stringify(got) + " want " + JSON.stringify(expect)); }
  } catch (e){ failed++; console.log("FAIL - " + name + "\n       " + e.message); }
}

/* ── lane 1: STATE — the page's own functions, no doubles ─────────────────── */
/* boot() paints the rail only after the registry answers; give it its moment
   rather than asserting against a page that is still loading. */
for (let i = 0; i < 40; i++){
  if (await evql(`document.querySelectorAll('#railnav [data-dest]').length`) === 6) break;
  await new Promise(r => setTimeout(r, 250));
}
await check("six destinations in the rail DOM (after boot)",
  `document.querySelectorAll('#railnav [data-dest]').length`, 6);
await check("entering Focus from the rail loads Balance (the shipped bug)",
  `(()=>{ let hit=false; const orig=loadBalance; loadBalance=()=>{hit=true};
     try { goDest('focus'); } finally { loadBalance=orig; }
     return hit && S.screen==='balance'; })()`);
await check("entering Team Sutra from the rail loads its tasks",
  `(()=>{ let hit=false; const orig=loadTeamsutra; loadTeamsutra=()=>{hit=true};
     try { goDest('team'); } finally { loadTeamsutra=orig; }
     return hit && S.screen==='teamsutra'; })()`);
await check("org plane lists Files",
  `(goDest('org'), /Files/.test(document.getElementById('planeBody').innerHTML))`);
await check("terminal clamp leaves the detail its floor (plane visible)",
  `(()=>{ goDest('settings'); const w = clampTermW(10000);
     return w <= innerWidth - 224 - 240 - 27 - 320 || w === 280; })()`);
await check("terminal open: the panes column stays visible",
  `(()=>{ if(!S.termOpen) termToggle(true);
     const w = document.getElementById('panes').getBoundingClientRect().width;
     termToggle(false);
     return w >= 300 ? true : 'panes width ' + Math.round(w); })()`, true);
await check("identity footer: role painted, menu is Act as + theme only",
  `(()=>{ const role = document.getElementById('idRole');
     const menu = document.getElementById('idMenu');
     return !!role && role.textContent.length > 0 && !!menu
       && menu.querySelectorAll('[data-role]').length >= 2
       && !!menu.querySelector('#themeBtn')
       && !/Sign out|Account/.test(menu.textContent); })()`);
await check("accent row offers reset + swatches and applies live",
  `(()=>{ buildAccentRow();
     const n = document.querySelectorAll('#accentRow [data-accent]').length;
     const ok = applyAccent('#4A6B8B');
     const set = document.documentElement.getAttribute('data-accent') === '#4A6B8B';
     applyAccent(null);
     return n === 7 && ok && set; })()`);
await check("chats destination keeps the session surface",
  `(goDest('chats'), S.ui.browseClosed === true
     && !!document.getElementById('newSession') && !!document.getElementById('sessions'))`);
await check("back on Now: full-bleed, plane gone",
  `(goDest('now'), document.getElementById('app').classList.contains('noplane')
     && document.getElementById('plane').hidden)`);

/* ── lane 2: PIXELS — light and dark, saved for the founder's own eyes ────── */
async function snap(name){
  const shot = await cdp("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(OUT + name, Buffer.from(shot.data, "base64"));
  console.log("shot - " + name);
}
await evql(`document.documentElement.setAttribute('data-theme','light')`);
await evql(`goDest('settings')`);
await snap("nav-light.png");
await evql(`document.documentElement.setAttribute('data-theme','dark')`);
await snap("nav-dark.png");
await evql(`document.documentElement.removeAttribute('data-theme'); goDest('now')`);

console.log("-".repeat(60));
console.log(`v3.3 shell e2e: ${passed} passed, ${failed} failed`);
ws.close();
process.exit(failed ? 1 : 0);
