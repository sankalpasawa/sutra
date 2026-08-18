/* Step 20 + 25 — verify the feature in the REAL running panel, not the mockup.
   Loads http://127.0.0.1:7011/ (the actual FastAPI app serving the actual
   panel.html + modules), then calls the page's OWN turnResponse() with the
   captured fan-out fixture and mounts the result inside a real .pane/.pb.
   Nothing here reimplements the app: the markup, the CSS and the code are all
   the shipped ones. What it does NOT prove is the websocket path; that is what
   the 152 unit assertions cover. */
import pw from "/Users/asawa/sutra-ui-workspace/app/node_modules/playwright/index.js";
import fs from "fs";
const { chromium } = pw;

const ROOT = "/Users/asawa/Claude/asawa-holding/sutra/marketplace/plugin/sutra-ui";
const OUT = "/private/tmp/claude-501/-Users-asawa-sutra-ui-workspace/16e424dd-41c2-468d-a6a4-f757a0972f96/scratchpad";
const FIX = JSON.parse(fs.readFileSync(ROOT + "/tests/fixtures/toolruns-fanout.json", "utf8"));

let pass = 0, fail = 0;
const check = (n, ok, d = "") => {
  if (ok) { pass++; console.log("  ok   " + n); } else { fail++; console.log("  FAIL " + n + " " + d); }
};

const b = await chromium.launch({ channel: "chrome" });

async function shoot(label, opts = {}) {
  const ctx = await b.newContext({ viewport: { width: 1280, height: 860 }, ...opts });
  const p = await ctx.newPage();
  const errs = [];
  p.on("pageerror", e => errs.push(String(e)));
  await p.goto("http://127.0.0.1:7011/", { waitUntil: "networkidle" });
  await p.waitForTimeout(1200);
  /* The app picks its theme from [data-theme] on <html> (07-loaders.js:1067),
     NOT from prefers-color-scheme -- so a light context alone leaves it dark and
     a file called app-light.png would be a dark screenshot. Set it the way the
     theme button does, then prove the paint actually changed. */
  if (opts.theme){
    await p.evaluate(t => document.documentElement.setAttribute("data-theme", t), opts.theme);
    await p.waitForTimeout(150);
    const bg = await p.evaluate(() => getComputedStyle(document.body).backgroundColor);
    check(label + ": the " + opts.theme + " theme is actually applied",
      opts.theme === "light" ? /2[0-9][0-9]|1[89][0-9]/.test(bg) : /^rgb\(1?[0-9], /.test(bg), bg);
  }

  const res = await p.evaluate(runs => {
    /* the page's own functions — if these are missing, the modules did not load */
    if (typeof turnResponse !== "function") return { err: "turnResponse is not defined" };
    if (typeof gvAgents !== "function") return { err: "gvAgents is not defined" };
    S.thinkOpen = { demo: true };
    /* The captured fan-out happens to contain no FAILURE, so one is appended
       here -- clearly marked as part of this demo composition -- because the
       failure state is the one worth looking at and the one worth proving is
       coloured. Everything else in this turn is the captured data. */
    /* The fixture's timestamps are fixed constants from 2023, so a RUNNING row
       measured against the live clock reads "24179H 30M". That is an artifact of
       a frozen fixture, not of the code -- in the app startedAt is stamped by the
       client as the frame arrives. Rebase onto now so the screenshot shows what
       an operator actually sees. */
    const t0 = Date.now() - 9 * 60 * 1000;
    const base = runs[0].startedAt;
    runs = runs.map(r => Object.assign({}, r, {
      startedAt: t0 + (r.startedAt - base),
      endedAt: r.endedAt == null ? undefined : t0 + (r.endedAt - base),
    }));
    const demoRuns = runs.concat([{ id: "toolu_demo_fail", name: "Bash",
      summary: "bats cynefin.bats", running: false, ok: false,
      startedAt: t0 + 9000, endedAt: t0 + 80000 }]);
    const t = { uid: "demo", streaming: true, response:
      "Placement is migrated; lens is mid-rewrite; cynefin hit a golden-test drift.",
      tools: demoRuns.map(r => r.name), toolRuns: demoRuns };
    const html = turnResponse(t);
    /* mount it inside a REAL pane body so it inherits the real layout */
    const pb = document.querySelector(".pane .pb") || document.querySelector(".pb");
    if (!pb) return { err: "no .pb in the running panel" };
    const wrap = document.createElement("div");
    wrap.className = "turn";
    wrap.innerHTML = '<div class="u md">Migrate all twelve engines to ledger schema v2.</div>' + html;
    pb.innerHTML = "";
    pb.appendChild(wrap);
    const row = pb.querySelector(".gv-agents button.trow");
    const toolDiv = pb.querySelector(".toolRow div.trow");
    const dot = pb.querySelector(".gv-agents .trow.run .tstate");
    /* THE claim being tested: a roster row is a .trow, so a <button> row must be
       indistinguishable from the <div> tool row above it. Compare them directly
       rather than guessing what the value should be. */
    const sig = el => {
      if (!el) return null;
      const c = getComputedStyle(el);
      return [c.fontFamily, c.fontSize, c.backgroundColor, c.borderTopWidth,
              c.borderTopStyle, c.borderRadius, c.paddingTop, c.paddingLeft].join(" | ");
    };
    const nameSig = el => {
      const n = el && el.querySelector(".tname");
      if (!n) return null;
      const c = getComputedStyle(n);
      return [c.fontFamily, c.fontSize, c.fontWeight, c.color].join(" | ");
    };
    return {
      agents: gvAgents(t).length,
      rows: pb.querySelectorAll(".gv-agents button.trow").length,
      logLines: pb.querySelectorAll(".gv-log .gv-ln").length,
      rowSig: sig(row), toolSig: sig(toolDiv),
      rowName: nameSig(row), toolName: nameSig(toolDiv),
      rowBg: row && getComputedStyle(row).backgroundColor,
      spin: dot && getComputedStyle(dot).animationName,
      runRing: dot && getComputedStyle(dot).borderLeftColor,
      logColor: (l => l && getComputedStyle(l).color)(pb.querySelector(".gv-log .gv-ln.bad")),
    };
  }, FIX.toolRuns);

  check(label + ": no page errors", errs.length === 0, errs.join(" | "));
  check(label + ": the page's own turnResponse rendered the roster", !res.err, res.err || "");
  if (!res.err) {
    check(label + ": 4 agent rows from the real fixture", res.rows === 4, "got " + res.rows);
    check(label + ": the log renders one line per run", res.logLines === 7, "got " + res.logLines);
    check(label + ": a button row is pixel-identical to a tool row",
      res.rowSig && res.rowSig === res.toolSig,
      "\n        button: " + res.rowSig + "\n        div:    " + res.toolSig);
    check(label + ": and so is its name column",
      res.rowName && res.rowName === res.toolName,
      "\n        button: " + res.rowName + "\n        div:    " + res.toolName);
    check(label + ": rows are painted by the app's tokens, not transparent",
      res.rowBg && res.rowBg !== "rgba(0, 0, 0, 0)", res.rowBg);
    check(label + ": a failed step is coloured as a failure in the log",
      res.logColor && res.logColor !== "rgba(0, 0, 0, 0)", res.logColor);
  }
  await p.screenshot({ path: `${OUT}/app-${label}.png`, fullPage: false });
  fs.copyFileSync(`${OUT}/app-${label}.png`, `${ROOT}/design/app-${label}.png`);
  await ctx.close();
  return res;
}

console.log("\ndark");
const dark = await shoot("dark", { theme: "dark" });
check("dark: the running dot animates", dark.spin && dark.spin !== "none", dark.spin);

console.log("\nlight");
await shoot("light", { colorScheme: "light", theme: "light" });

console.log("\nreduced motion");
const rm = await shoot("reduced-motion", { reducedMotion: "reduce", theme: "dark" });
check("reduced motion: the spinner stops — colour still carries the state",
  rm.spin === "none", "animation-name=" + rm.spin);
/* the run dot is a RING: border-top is transparent on purpose, that is the gap
   the spin shows through. With motion off, the ring itself must still be there. */
check("reduced motion: the state survives without the motion",
  rm.runRing && rm.runRing !== "rgba(0, 0, 0, 0)", "border-left-color=" + rm.runRing);

await b.close();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
