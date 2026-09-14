/* qa-shell/shadow-copy-check.mjs — Copy result, END TO END, in a real DOM.
 *
 * WHY THIS LANE EXISTS (founder, 2026-09-15). test_shadow_completion_ui.js
 * calls the real renderers, but it never PARSES what they return: the markup
 * stays a string, the delegated click listener is invoked as a function, and
 * no node is ever queried. That proves the handler behaves when a test drives
 * it. It does not prove the control reaches a real completed task through the
 * real render path, in a document, on a real event.
 *
 * So this drives the shipped 16-shadow-home.js inside Chromium:
 *   1. the REAL renderer  shadowTaskCardHtml(record) -> document -> the node
 *                         is found by querySelector, and its outerHTML is
 *                         read back off the live DOM
 *   2. state-gated        present for a done record, absent for a running one
 *                         and for one waiting on the founder
 *   3. a REAL click       new MouseEvent(bubbles) dispatched on the queried
 *                         node, reaching the module's own document-level
 *                         listener. The string handed to the clipboard is
 *                         captured and printed verbatim.
 *   4. no clipboard       navigator.clipboard undefined AND execCommand
 *                         refusing: the button must show and ANNOUNCE the
 *                         failure, and nothing may reach the console.
 *
 * THE SYSTEM CLIPBOARD IS NEVER TOUCHED. navigator.clipboard.writeText is
 * replaced in-page by a capture stub before any click, and the execCommand
 * fallback is forced to refuse — founder direction 2026-09-15, after a real
 * clipboard write clobbered what they had copied.
 *
 * DEPENDENCY-FREE, like nav-check.mjs: node's own http server, node's own
 * WebSocket, raw CDP. Serves the two real JS files off disk, so what runs is
 * what ships. Self-driving -- it starts and stops both the server and the
 * browser:
 *
 *   node qa-shell/shadow-copy-check.mjs          # exits non-zero on failure
 *   CHROME=/path/to/Chromium node qa-shell/shadow-copy-check.mjs
 */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const UI = path.join(HERE, "..");
const PORT = 8479;
const CDP_PORT = 9334;
const CHROME = process.env.CHROME
  || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

/* ── the record under test: the shape mission_engine stamps on a done
      mission, kept in step with test_shadow_completion_summary.py ───────── */
const DONE = {
  id: "m-done", objective: "get the EMI check green", template: "fix",
  state: "done", target_mode: "new", target_session: "sess-1",
  turns_used: 5, max_turns: 20,
  done_when: [{ tier: "contains_artifact", check: "EMI-OK" }],
  completion: {
    objective: "get the EMI check green", headline: "3 of 3 checks passed",
    /* the worker's own closing message, as shadow_runner.last_worker_message
       hands it over: quoted, whitespace collapsed, already trimmed */
    outcome: "Added the per-tenant loop to emi.py, fixed the stale cache "
      + "read it depended on, and ran the suite: 42 passed, 0 failed.",
    checks_met: 3, checks_total: 3, turns_used: 5, max_turns: 20,
    chat: "sess-1", at: "2026-09-15T01:20:00Z",
    checks: [
      { check: "EMI-OK", tier: "contains_artifact", met: true,
        how: "found in the chat",
        evidence: "…the suite reports EMI-OK for every tenant…" },
      { check: "pytest test_emi.py passes", tier: "verify", met: true,
        how: "Shadow ran this check and it passed" },
      { check: "the copy reads right", tier: "founder_confirm", met: true,
        how: "you confirmed it", by: "founder", at: "2026-09-15T01:19:00Z" },
    ],
  },
};
const RUNNING = {
  id: "m-run", objective: "still working", template: "fix", state: "running",
  target_mode: "new", target_session: "sess-2", turns_used: 3, max_turns: 20,
  done_when: [{ tier: "contains_artifact", check: "EMI-OK" }],
};
/* "needs you" is paused + a founder pause reason (shadowMissionNeedsFounder),
   NOT blocked -- blocked is a stall Shadow is reporting, not a sign-off */
const NEEDS_YOU = {
  id: "m-ask", objective: "sign this off", template: "fix", state: "paused",
  pause_reason: "founder_confirm", target_mode: "new", target_session: "sess-3",
  turns_used: 4, max_turns: 20,
  done_when: [{ tier: "founder_confirm", check: "the copy reads right",
                met: false }],
};
const BLOCKED = {
  id: "m-blk", objective: "stalled on something", template: "fix",
  state: "blocked", block_reason: "ping_pong", target_mode: "new",
  target_session: "sess-4", turns_used: 6, max_turns: 20,
  done_when: [{ tier: "contains_artifact", check: "EMI-OK" }],
};

const PAGE = `<!doctype html>
<meta charset="utf-8"><title>shadow copy-result e2e</title>
<link rel="stylesheet" href="/static/panel.css">
<body>
<div id="pane"></div>
<script>
/* the two globals the module expects from files this lane does not load */
const esc = s => String(s==null?"":s).replace(/[&<>"]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[m]));
const S = { shadowTaskSel: "m-done", shadowMissions: ${JSON.stringify([DONE, RUNNING, NEEDS_YOU, BLOCKED])} };
window.__writes = [];
window.__console = [];
/* NOTHING REACHES THE SYSTEM CLIPBOARD. Both paths are intercepted before
   any click: the async API is a capture stub, and the deprecated fallback is
   forced to refuse so it can never select-and-copy for real. */
const MODE = new URLSearchParams(location.search).get("mode") || "ok";
Object.defineProperty(navigator, "clipboard", { configurable: true,
  value: MODE === "noclip" ? undefined
    : { writeText: async (t) => { window.__writes.push(t); } } });
document.execCommand = () => false;
for (const k of ["error", "warn"])
  console[k] = (...a) => window.__console.push(k + ": " + a.join(" "));
addEventListener("unhandledrejection", e =>
  window.__console.push("unhandledrejection: " + (e.reason && e.reason.message)));
/* the pane repaints by replacing innerHTML, exactly as render() does */
function draw(id){
  const m = S.shadowMissions.find(x => x.id === (id || S.shadowTaskSel));
  document.getElementById("pane").innerHTML = shadowTaskCardHtml(m);
}
function scheduleRender(){ draw(); }
function render(){ draw(); }
<\/script>
<script src="/static/js/15-shadow-overlay.js"><\/script>
<script src="/static/js/16-shadow-home.js"><\/script>
<script>draw();<\/script>
</body>`;

/* ── a server that hands out the page and the files that really ship ────── */
const TYPES = { ".js": "text/javascript", ".css": "text/css" };
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  if (url.pathname === "/" ) {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    return res.end(PAGE);
  }
  const rel = url.pathname.replace(/^\/+/, "");
  const file = path.join(UI, rel);
  /* never serve outside the ui directory */
  if (!file.startsWith(UI) || !fs.existsSync(file)) {
    res.writeHead(404); return res.end("no");
  }
  res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "text/plain" });
  res.end(fs.readFileSync(file));
});
await new Promise(r => server.listen(PORT, "127.0.0.1", r));

if (!fs.existsSync(CHROME)) {
  console.error("no Chromium at " + CHROME + " -- set CHROME=<path>");
  server.close(); process.exit(2);
}
const profile = fs.mkdtempSync("/tmp/shadow-copy-");
const chrome = spawn(CHROME, ["--headless=new",
  "--remote-debugging-port=" + CDP_PORT, "--user-data-dir=" + profile,
  "--no-first-run", "--disable-gpu", "about:blank"],
  { stdio: "ignore" });

let failed = 0;
const ok = (cond, what) => {
  console.log((cond ? "  ok   " : "  FAIL ") + what);
  if (!cond) failed++;
};

function connect(target){
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let seq = 0; const pend = new Map();
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
  };
  const cdp = (method, params = {}) => new Promise((res, rej) => {
    const id = ++seq;
    pend.set(id, m => m.error ? rej(new Error(method + ": " + JSON.stringify(m.error))) : res(m.result));
    ws.send(JSON.stringify({ id, method, params }));
  });
  return new Promise((res, rej) => { ws.onopen = () => res({ ws, cdp }); ws.onerror = rej; });
}

try {
  /* wait for the browser's CDP endpoint */
  let list = null;
  for (let i = 0; i < 40 && !list; i++) {
    try { list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json(); }
    catch { await new Promise(r => setTimeout(r, 250)); }
  }
  if (!list) throw new Error("browser never came up on CDP");
  const target = list.find(t => t.type === "page");
  const { ws, cdp } = await connect(target);
  await cdp("Runtime.enable"); await cdp("Page.enable");
  const evq = async (expression) => {
    const r = await cdp("Runtime.evaluate",
      { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails)
      throw new Error(r.exceptionDetails.exception?.description || expression);
    return r.result.value;
  };
  const load = async (mode) => {
    await cdp("Page.navigate", { url: `http://127.0.0.1:${PORT}/${mode ? "?mode=" + mode : ""}` });
    for (let i = 0; i < 60; i++) {
      try { if (await evq(`!!document.querySelector("[data-shtaskcard]")`)) return; }
      catch {}
      await new Promise(r => setTimeout(r, 100));
    }
    throw new Error("the card never rendered");
  };

  /* 1. THE REAL RENDERER, THEN THE REAL DOM ─────────────────────────────── */
  console.log("\n1. the control, queried off the live DOM after shadowTaskCardHtml");
  await load();
  const outer = await evq(`document.querySelector("[data-shcopydone]").outerHTML`);
  console.log(JSON.stringify(outer, null, 0).slice(0, 0) + outer);
  ok(/data-shcopydone="m-done"/.test(outer), "it names the finished mission");
  ok(/data-shcopystate="idle"/.test(outer), "it starts idle");
  ok(!/disabled/.test(outer), "and is not disabled");
  ok(await evq(`document.querySelector("[data-shdone='m-done']")
      .contains(document.querySelector("[data-shcopydone]"))`),
    "it is inside the completion summary the server stamped");

  /* 2. STATE-GATED ──────────────────────────────────────────────────────── */
  console.log("\n2. present for a completed task, absent for the others");
  ok(await evq(`(draw("m-done"), !!document.querySelector("[data-shcopydone]"))`),
    "done      -> the copy control is present");
  ok(await evq(`(draw("m-run"), document.querySelector("[data-shcopydone]") === null)`),
    "running   -> absent");
  ok(await evq(`(draw("m-ask"), document.querySelector("[data-shcopydone]") === null)`),
    "needs you -> absent");
  ok(await evq(`(draw("m-ask"), !!document.querySelector(".shconfirm .shcheck"))`),
    "          (the sign-off list is what renders there instead)");
  ok(await evq(`(draw("m-blk"), document.querySelector("[data-shcopydone]") === null)`),
    "blocked   -> absent");
  ok(await evq(`(draw("m-run"), !!document.querySelector("[data-shtaskcard='m-run']"))`),
    "          (the card itself still renders in every one of those states)");

  /* 2b. WHAT WAS DONE, ON THE LIVE CARD ─────────────────────────────────── */
  console.log("\n2b. the worker's own account, read back off the DOM");
  await load();
  const work = await evq(`(() => { const n =
    document.querySelector("[data-shdone='m-done'] .shdonework");
    return n ? n.textContent : null; })()`);
  console.log(work);
  ok(work === DONE.completion.outcome,
    "the account on the card is the server's string, verbatim");
  ok(await evq(`(() => { const s = document.querySelector("[data-shdone='m-done']");
      const w = s.querySelector(".shdonework"), c = s.querySelector(".shchecks");
      return !!(w && c) && (w.compareDocumentPosition(c) & 4) !== 0; })()`),
    "…and it sits ABOVE the verdicts, so it is read first");
  ok(await evq(`(draw("m-run"), document.querySelector(".shdonework") === null)`),
    "a task that has not finished has no account to show");

  /* 3. A REAL CLICK, AND THE PAYLOAD IT HANDS OVER ──────────────────────── */
  console.log("\n3. a dispatched MouseEvent, through the module's own listener");
  await load();
  await evq(`document.querySelector("[data-shcopydone]")
    .dispatchEvent(new MouseEvent("click", { bubbles: true }))`);
  await new Promise(r => setTimeout(r, 300));
  const writes = await evq(`window.__writes`);
  ok(writes.length === 1, "exactly one clipboard write");
  console.log("\n---- the string handed to clipboard.writeText, verbatim ----");
  console.log(writes[0]);
  console.log("---- end ----");
  ok(!/[<>]/.test(writes[0]), "it is the plain-text render, never the markup");
  ok(writes[0].includes(DONE.completion.outcome),
    "and it carries what the worker said it did, not only the verdicts");
  const after = await evq(`document.querySelector("[data-shcopydone]").outerHTML`);
  console.log(after);
  ok(/data-shcopystate="copied"/.test(after) && />Copied</.test(after),
    "the button says Copied");
  const live = await evq(`(() => { const n = document.getElementById("shdoneannounce");
    return n ? n.outerHTML : null; })()`);
  console.log(live);
  ok(/role="status"/.test(live || "") && /aria-live="polite"/.test(live || "")
    && /Result copied to the clipboard\./.test(live || ""),
    "and it is announced");
  ok((await evq(`window.__console`)).length === 0, "nothing reached the console");

  /* 4. NO CLIPBOARD AT ALL ──────────────────────────────────────────────── */
  console.log("\n4. navigator.clipboard undefined, fallback refusing");
  await load("noclip");
  ok(await evq(`navigator.clipboard === undefined`), "the API really is gone");
  await evq(`document.querySelector("[data-shcopydone]")
    .dispatchEvent(new MouseEvent("click", { bubbles: true }))`);
  await new Promise(r => setTimeout(r, 300));
  const bad = await evq(`document.querySelector("[data-shcopydone]").outerHTML`);
  console.log(bad);
  ok(/data-shcopystate="failed"/.test(bad) && />Copy failed</.test(bad),
    "the failure is visible");
  ok(!/disabled/.test(bad), "and the control is still clickable");
  const badLive = await evq(`document.getElementById("shdoneannounce").outerHTML`);
  console.log(badLive);
  ok(/could not be copied/.test(badLive), "the failure is announced too");
  const noise = await evq(`window.__console`);
  ok(noise.length === 0, "and nothing was thrown into the console");
  if (noise.length) console.log("  console said: " + JSON.stringify(noise));

  ws.close();
} catch (e) {
  console.error("\nlane error: " + (e && e.message));
  failed++;
} finally {
  chrome.kill();
  server.close();
  fs.rmSync(profile, { recursive: true, force: true });
}

console.log(failed
  ? `\nshadow-copy-check: ${failed} FAILED`
  : "\nshadow-copy-check: all green");
process.exit(failed ? 1 : 0);
