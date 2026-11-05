// Stand-in for J2's j2_ui_render.js: node j2_ui_render.js <j2_ui.html> <state.json> [previews.json] [docs.json]
// Prints seven keys computed from its inputs, so a test can tell what the capture script fed it.
const fs = require("fs");
const [html, statePath, previewPath, docsPath] = process.argv.slice(2);
const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
const previews = previewPath ? JSON.parse(fs.readFileSync(previewPath, "utf8")) : {};
const docs = docsPath ? JSON.parse(fs.readFileSync(docsPath, "utf8")) : {};
const page = fs.readFileSync(html, "utf8");
const out = {
  simple: "chat:" + state.chat.length,
  sprog: "status:" + state.status,
  workflows: state.workflows.map(w => w.id + ":" + w.atoms.length).join(","),
  rail: docs.railtabs || [],
  needs: "",
  map: "nodes:" + ((docs.map || {}).nodes || []).length,
  agent: (docs.agent || {}).who || "",
  cards: Object.keys(previews).sort(),
  page: page.length,
};
if (process.env.STANDIN_RENDER === "random") out.simple = String(Math.random());
if (process.env.STANDIN_RENDER === "nokey") delete out.rail;
if (process.env.STANDIN_RENDER === "fail") { console.error("render failed on purpose"); process.exit(3); }
console.log(JSON.stringify(out));
