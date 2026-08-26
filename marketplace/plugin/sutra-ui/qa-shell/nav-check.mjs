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

/* The CDP port answers before the shell's PAGE target exists — one immediate
   /json/list is a race (it lost on 2026-08-24). Poll for the target. */
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
await check("entering Focus from the rail fires the selected screen's loader (2.118.1 pin, state-independent)",
  `(()=>{ /* destSel persists across sessions (e.g. Shadow) -- pin the
       LOADER-FIRES contract, not the ambient selection */
     S.ui.destSel.focus = 'balance';
     let hit=false; const orig=loadBalance; loadBalance=()=>{hit=true};
     try { goDest('focus'); } finally { loadBalance=orig; }
     return hit && S.screen==='balance'; })()`);
await check("entering Help from the rail loads its tasks, full-bleed (no plane)",
  `(()=>{ let hit=false; const orig=loadTeamsutra; loadTeamsutra=()=>{hit=true};
     try { goDest('team'); } finally { loadTeamsutra=orig; }
     return hit && S.screen==='teamsutra'
       && document.getElementById('app').classList.contains('noplane')
       && />\\s*Help\\s*</.test(document.getElementById('railnav').innerHTML); })()`);
await check("org dest lands on a real screen (accordion + workspace-cutover aware)",
  `(()=>{ /* 2.226.0: Org is an inline rail accordion, no second plane;
       S92: the flag-on default surface is the Workspace. State-independent:
       clear the stored pick, then the dest must land on a REAL screen and
       open its accordion. */
     S.ui.destSel.org = null;
     goDest('org');
     return !!SCREENS[S.screen]
       && (S.screen === 'workspace' || S.screen === 'departments')
       && (typeof destInline !== 'function' || !destInline('org')
           || S.ui.railOpen === 'org'); })()`);
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

/* ── v3.4: the lane collapse and the functional Act-as ────────────────────── */
await check("v3.4: one toggle collapses BOTH lanes and the detail takes the width",
  `(async ()=>{ goDest('settings');
     const panes = document.getElementById('panes');
     const before = panes.getBoundingClientRect().width;
     document.getElementById('railToggle').onclick();
     await new Promise(r=>setTimeout(r,80));
     const app = document.getElementById('app');
     const railGone = getComputedStyle(document.querySelector('.rail')).display === 'none';
     const planeGone = getComputedStyle(document.getElementById('plane')).display === 'none';
     const after = panes.getBoundingClientRect().width;
     const ok = app.classList.contains('railcol') && railGone && planeGone && after > before + 300;
     document.getElementById('railToggle').onclick();
     await new Promise(r=>setTimeout(r,80));
     return ok || ('before '+Math.round(before)+' after '+Math.round(after)); })()`, true);
await check("v3.4: acting as CEO of Sutra scopes the org; Asawa restores it",
  `(async ()=>{ localStorage.setItem('sutra.panel.role','CEO of Sutra');
     await loadOrg();
     const scoped = DOMAINS.length > 0 && DOMAINS.every(d => d.ref !== undefined)
       && DOMAINS.some(d => /sutra/i.test(d.name)) && !DOMAINS.some(d => d.name === 'Holding Departments')
       && S.orgScope && !!S.orgScope.ref;
     localStorage.setItem('sutra.panel.role','CEO of Asawa Inc.');
     await loadOrg();
     const restored = DOMAINS.some(d => d.name === 'Holding Departments') && S.orgScope && S.orgScope.ref === null;
     return (scoped && restored) || ('scoped '+scoped+' restored '+restored); })()`, true);

/* ── lane 2: PIXELS — light and dark, saved for the founder's own eyes ────── */
async function snap(name){
  const shot = await cdp("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(OUT + name, Buffer.from(shot.data, "base64"));
  console.log("shot - " + name);
}
await evql(`document.documentElement.setAttribute('data-theme','light')`);
await evql(`goDest('settings')`);
await snap("nav-light.png");
/* v3.4 F2 verification: departments in BOTH lane states (the shipped overlap) */
await evql(`goDest('org'); openScreen('departments'); render()`);
await new Promise(r => setTimeout(r, 900));
await snap("nav-dept.png");
await evql(`document.getElementById('railToggle').onclick()`);
await new Promise(r => setTimeout(r, 300));
await snap("nav-dept-collapsed.png");
await evql(`document.getElementById('railToggle').onclick()`);
await new Promise(r => setTimeout(r, 300));
await evql(`document.documentElement.setAttribute('data-theme','dark')`);
await snap("nav-dark.png");
await evql(`document.documentElement.removeAttribute('data-theme'); goDest('now')`);

console.log("-".repeat(60));
console.log(`v3.3 shell e2e: ${passed} passed, ${failed} failed`);
ws.close();
process.exit(failed ? 1 : 0);
