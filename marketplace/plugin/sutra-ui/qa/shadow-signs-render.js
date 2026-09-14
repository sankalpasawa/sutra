#!/usr/bin/env node
/* shadow-signs-render.js -- render a REAL mission record with the REAL panel.
 *
 * WHY THIS EXISTS. The node suites build their own fixtures, so they can only
 * prove the renderer is self-consistent: a hand-written `intervention` that
 * the server would never emit still renders. This driver closes that gap from
 * the other side -- it takes a record exactly as GET /api/shadow/missions
 * returned it and runs the shipped renderer over it, so the Python end-to-end
 * test can assert on what a browser would actually paint.
 *
 * Usage: node qa/shadow-signs-render.js <mission.json>   # card HTML -> stdout
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JS = path.join(__dirname, "..", "static", "js");

/* THE SHIPPED esc, TAKEN FROM THE SHIPPED FILE. 02-helpers.js cannot be
   loaded whole outside a browser (it reaches for PLANS and the DOM), and a
   re-implementation here could pass a test the real panel would fail -- an
   escaping stub that is merely similar is exactly the wrong thing to verify
   escaping against. So the one definition this renderer needs is lifted from
   its own source line, and the driver refuses to run if it is not there. */
const helpers = fs.readFileSync(path.join(JS, "02-helpers.js"), "utf8");
const escSrc = (helpers.match(/^const esc\s*=.*$/m) || [])[0];
if (!escSrc){
  console.error("shadow-signs-render: no `const esc =` in 02-helpers.js");
  process.exit(2);
}

const ctx = {
  console, Date, setTimeout: () => ({}),
  S: {}, SCREENS: {}, TITLES: {},
  showNudge(){}, scheduleRender(){},
  document: {
    addEventListener(){},
    createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
    body: { appendChild(){} }, querySelector(){ return null; },
  },
};
vm.createContext(ctx);
vm.runInContext(escSrc, ctx);
["15-shadow-overlay.js", "16-shadow-home.js"].forEach((f) =>
  vm.runInContext(fs.readFileSync(path.join(JS, f), "utf8"), ctx));

const record = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
ctx.S.shadowMissions = [record];
process.stdout.write(ctx.shadowTaskCardHtml(record));
