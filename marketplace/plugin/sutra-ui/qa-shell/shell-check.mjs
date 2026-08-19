/* qa-shell/shell-check.mjs — the PRODUCTION-SHELL lane of the publish check.
 *
 * Verifies a feature inside the real Sutra.app (the Electron shell the founder
 * actually uses), not a headless stand-in. Two lanes, in order:
 *
 *   LANE 1 · STATE   — attach over CDP, read the page's own S, call its own
 *                      pure functions (gvBody/gvLog/turnResponse), assert.
 *                      This answers WHY. It is the primary lane.
 *   LANE 2 · PIXELS  — screenshot the same attached session and sanity-check
 *                      brightness per theme. This answers "what will a human
 *                      perceive". It is confirmatory, never primary.
 *
 * Run it via run.sh (which owns the relaunch/restore choreography), not
 * directly: the shell must be in debug mode only while this runs.
 *
 * HARD-LEARNED RULES (each observed, then codex-confirmed):
 *   - NEVER browser.close() on a connectOverCDP session: it terminates the
 *     app. Detach = disconnect if the binding has it, else just exit.
 *   - Backend OWNERSHIP, not just port-open: the python child on 8330 can
 *     outlive a dead shell, and the next launch silently attaches to the
 *     stale server. run.sh asserts the pid tree before this script runs.
 */
import fs from "fs";

let pw = null;
for (const spec of ["playwright", process.env.PLAYWRIGHT].filter(Boolean)) {
  try { const m = await import(spec); pw = m.default ?? m; break; } catch {}
}
if (!pw) {
  console.error("playwright not found — set PLAYWRIGHT=/abs/path/to/playwright/index.js");
  process.exit(2);
}

const PORT = process.env.SHELL_DEBUG_PORT || "9223";
const OUT = process.env.SHELL_QA_OUT || new URL("./out/", import.meta.url).pathname;
fs.mkdirSync(OUT, { recursive: true });

let pass = 0, fail = 0;
const check = (name, ok, detail = "") => {
  if (ok) { pass++; console.log("  ok   " + name); }
  else    { fail++; console.log("  FAIL " + name + (detail ? " — " + detail : "")); }
};

const browser = await pw.chromium.connectOverCDP("http://127.0.0.1:" + PORT);
const ctx = browser.contexts()[0];
const page = ctx.pages().find(p => p.url().includes("127.0.0.1:8330")) || ctx.pages()[0];
console.log("attached to shell page: " + page.url());
await page.waitForTimeout(1500);

/* ── LANE 1 · STATE ────────────────────────────────────────────────────────── */
console.log("\nLANE 1 · state (the app testifies about itself)");

const state = await page.evaluate(() => {
  const r = { errors: [] };
  try {
    r.core = ["gvBody", "gvLog", "gvAgents", "turnResponse", "turnControlClick", "agentMatch"]
      .filter(f => typeof globalThis[f] !== "function");
    r.sessions = S.sessions.length;

    /* the loader must be a real, delegated-handled button even mid-stream */
    const t = { uid: "qadbg", streaming: true, response: "", tools: [], toolRuns: [] };
    r.thinkIsButton = /<button class="gv-thinkbtn"/.test(turnResponse(t));

    /* the roster renders from the committed real fixture shape */
    const runs = [
      { id: "toolu_qa1", name: "Agent", summary: "Explore: qa state lane",
        running: false, ok: true, startedAt: Date.now() - 9000, endedAt: Date.now() - 2000 },
      { id: "toolu_qa2", name: "Agent", summary: "Explore: qa pixel lane",
        running: true, ok: null, startedAt: Date.now() - 5000 },
    ];
    const t2 = { uid: "qadbg2", streaming: true, response: "checking",
                 tools: runs.map(x => x.name), toolRuns: runs };
    const html = turnResponse(t2);
    r.rosterRows = (html.match(/<button class="trow /g) || []).length;
    r.rosterInsideAnchor = html.indexOf("data-aturn") < html.indexOf("gv-agents");

    /* design-qa 20260819-004318-adf0df: button.trow computed UA buttontext
       (rgb(0,0,0)) in all 8 states — a <button> does not inherit colour and the
       reset omitted it. Prove the SHIPPED stylesheet in the RUNNING app now
       resolves the row to the token ink: mount the row the page itself just
       rendered, off-screen for one frame, and read the computed colour. */
    const probe = document.createElement("div");
    probe.style.cssText = "position:absolute;left:-9999px;top:0";
    probe.innerHTML = html;
    document.body.appendChild(probe);
    const rowEl = probe.querySelector("button.trow");
    r.rowColor  = rowEl ? getComputedStyle(rowEl).color : "no row mounted";
    r.inkColor  = getComputedStyle(document.body).color;  /* body IS var(--ink) */
    probe.remove();

    /* design-qa 20260819-004318-adf0df rows 9-12: button.gv-chip had no focus
       ring of its own. getComputedStyle cannot force :focus-visible, so
       interrogate the parsed CSSOM of the SHIPPED stylesheet in the RUNNING
       app: the rule must have survived parsing, paint through the token, and
       the token must resolve to a real colour on this page. */
    const walk = rules => [...rules].flatMap(rl =>
      rl.cssRules ? walk(rl.cssRules) : (rl.selectorText === ".gv-chip:focus-visible" ? [rl] : []));
    let chipRules = [];
    for (const sheet of document.styleSheets) {
      try { chipRules = chipRules.concat(walk(sheet.cssRules)); } catch (e) {}
    }
    r.chipFocusOutline = chipRules.length
      ? chipRules[0].style.outline : "rule missing from CSSOM";
    r.accToken = getComputedStyle(document.documentElement).getPropertyValue("--acc").trim();

    /* wire-text hygiene the projections promise */
    r.controlCharsStripped = !/[\x00-\x1F]/.test(
      gvAgents({ toolRuns: [{ id: "a", name: "Agent", summary: "Explore: a\x07b\x1bc",
                              running: true, ok: null }] })[0].desc);
    r.headerStripped = gvBody("[INBOUND·QUERY · TIMING:now · CHANNEL:x · REV:none · RISK:low]\nreal text") === "real text";
    /* the unfenced-block leak this lane found (2026-08-19): a bare INPUT:/TYPE:
       run must strip in the RUNNING app, and only the answer survives */
    r.unfencedStripped = gvBody("Answer.\nINPUT: x\nTYPE: task") === "Answer.";
  } catch (e) { r.errors.push(String(e)); }
  return r;
});

check("no page errors during interrogation", state.errors.length === 0, state.errors.join("; "));
check("every core function is live in the shell", (state.core || []).length === 0,
  "missing: " + (state.core || []).join(","));
check("sessions loaded from the real backend", state.sessions > 0, String(state.sessions));
check("thinking loader is a button", state.thinkIsButton === true);
check("agent roster renders (2 rows from 2 Agent runs)", state.rosterRows === 2, String(state.rosterRows));
check("roster sits inside the patch anchor", state.rosterInsideAnchor === true);
check("control characters stripped from wire text", state.controlCharsStripped === true);
check("H-Sutra header stripped from bodies", state.headerStripped === true);
check("unfenced governance run stripped from bodies", state.unfencedStripped === true);
check("roster button carries the token ink, never UA buttontext",
  state.rowColor === state.inkColor && state.rowColor !== "no row mounted",
  "row=" + state.rowColor + " ink=" + state.inkColor);
check("governance chip focus ring shipped, token-painted, and resolvable",
  /2px solid/.test(state.chipFocusOutline || "")
    && (state.chipFocusOutline || "").includes("var(--acc)")
    && (state.accToken || "").length > 0,
  "outline=" + state.chipFocusOutline + " --acc=" + state.accToken);

/* ── LANE 2 · PIXELS ───────────────────────────────────────────────────────── */
console.log("\nLANE 2 · pixels (what a human will perceive)");

async function shoot(theme) {
  await page.evaluate(t => document.documentElement.setAttribute("data-theme", t), theme);
  await page.waitForTimeout(250);
  const path = OUT + "/shell-" + theme + ".png";
  await page.screenshot({ path });
  /* brightness sanity from the saved bytes — a "light" file that is dark is a
     mislabeled artifact, which this session has produced once already */
  const b64 = fs.readFileSync(path).toString("base64");
  const mean = await page.evaluate(async d => {
    const img = new Image(); img.src = "data:image/png;base64," + d; await img.decode();
    const c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
    const x = c.getContext("2d"); x.drawImage(img, 0, 0);
    const px = x.getImageData(Math.floor(img.width/2), Math.floor(img.height/2), 200, 150).data;
    let s = 0; for (let i = 0; i < px.length; i += 4) s += (px[i]+px[i+1]+px[i+2])/3;
    return Math.round(s / (px.length/4));
  }, b64);
  return { path, mean };
}

const dark = await shoot("dark");
check("dark screenshot is dark (mean < 90)", dark.mean < 90, "mean=" + dark.mean);
const light = await shoot("light");
check("light screenshot is light (mean > 170)", light.mean > 170, "mean=" + light.mean);
await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
console.log("  shots: " + dark.path + " · " + light.path);

/* ── DETACH — the one hard rule ────────────────────────────────────────────── */
/* No browser.close(): on a CDP attachment it kills the target app (observed
   2026-08-18; the founder found the app gone). disconnect-only if the binding
   offers it, else plain exit — the dropped WebSocket is a normal CDP event. */
if (typeof browser.disconnect === "function") { try { browser.disconnect(); } catch {} }

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
