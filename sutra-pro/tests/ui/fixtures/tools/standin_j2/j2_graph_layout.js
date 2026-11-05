// Stand-in for J2's j2_graph_layout.js: node j2_graph_layout.js <j2_ui.html> <maps.json>
const fs = require("fs");
const maps = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
console.log(JSON.stringify(Object.entries(maps).map(([run, m]) => ({ run, nodes: (m.nodes || []).length }))));
