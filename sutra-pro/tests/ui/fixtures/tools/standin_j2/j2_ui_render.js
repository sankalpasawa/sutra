// Stand-in for J2's j2_ui_render.js: node j2_ui_render.js <j2_ui.html> <state.json> [previews.json] [docs.json]
// Prints the keys J2's harness prints, each computed from its inputs, so a test can tell what the capture script fed it.
const fs = require("fs");
const [html, statePath, previewPath, docsPath] = process.argv.slice(2);
const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
const previews = previewPath ? JSON.parse(fs.readFileSync(previewPath, "utf8")) : {};
const docs = docsPath ? JSON.parse(fs.readFileSync(docsPath, "utf8")) : {};
const page = fs.readFileSync(html, "utf8");
const parts = (state.studio || {}).parts || [];
const events = (docs.activity || {}).events || [];
const out = {
  simple: "chat:" + state.chat.length,
  sprog: "status:" + state.status,
  finish: state.status === "done" ? "finish card" : "",
  journey: {stops: (docs.changes || []).length},
  journeyhtml: docs.journey ? "journey:" + (docs.changes || []).length : "",
  sframe: "/site/v" + (state.versions || 0) + "?t=" + Date.now(),      // J2's page puts the time in it: the capture freezes node's clock
  teamwork: "teamwork:" + state.chat.length,
  plan: "plan:" + parts.length,
  team: "team:" + parts.length,
  status: "status:" + state.status,
  views: "views:" + Object.keys(docs.arts || {}).sort().join(","),
  files: "",
  parts: parts.map(p => p.sec),
  tabs: ["site", "team"],
  inline: "",
  needids: (state.needs || []).map(String),
  workflows: state.workflows.map(w => w.id + ":" + w.atoms.length).join(","),
  rail: docs.railtabs || [],
  railst: {tabs: (docs.railtabs || []).length},
  needs: "",
  map: "nodes:" + ((docs.map || {}).nodes || []).length,
  planmap: "planmap:" + String((docs.planmap || {}).found),
  msgfns: (docs.msgs || []).map(m => [m.who]),
  feed: "feed:" + ((docs.activity || {}).who || "") + ":" + events.length,
  agent: (docs.agent || {}).who || "",
  cards: Object.keys(previews).sort(),
  page: page.length,
};
if (process.env.STANDIN_RENDER === "random") out.simple = String(Math.random());
if (process.env.STANDIN_RENDER === "nokey") delete out.rail;
if (process.env.STANDIN_RENDER === "fail") { console.error("render failed on purpose"); process.exit(3); }
console.log(JSON.stringify(out));
