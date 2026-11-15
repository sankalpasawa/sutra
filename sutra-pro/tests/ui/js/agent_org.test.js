"use strict";
// Agent Org's team cards (OrgChartView.teamCardsHtml, sutra_app/ui/static/js/orgchart_view.js): per team what it does, its five function agents and
// their state, and what it is doing now; each card opens the team's agent view. The page itself is proved by tests/ui/test_home_front.py.
// Run with: node --test tests/ui/js/agent_org.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const OrgChartView = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/orgchart_view.js"));
const cards = OrgChartView.teamCardsHtml;
const fns = status => ["audit", "identity", "priority", "adaptation", "coordination"].map(fn => ({id: "web." + fn, fn, status: fn === "audit" ? status : "idle"}));

test("one card per team: its name, what it does, its state in plain words, and a link to its agent view", () => {
  const html = cards([{id: "web", name: "Bakery site", purpose: "A site for the bakery", node_status: "running", functions: fns("running")},
    {id: "docs", name: "Docs", purpose: "", node_status: "idle", last_status: "done"}]);
  assert.deepEqual([...html.matchAll(/<a class="orgcard" href="([^"]+)"/g)].map(m => m[1]), ["/d/web/?view=detail", "/d/docs/?view=detail"]);
  assert.match(html, /<b class="orgname">Bakery site<\/b><span class="orgstate oc-making"><i aria-hidden="true"><\/i>Working<\/span>/);
  assert.match(html, /<span class="orgpurpose">A site for the bakery<\/span>/);
  assert.match(html, /<span class="orgstate oc-done"><i aria-hidden="true"><\/i>Done<\/span>/);          // idle again after a finished run
  assert.equal((html.match(/Open agent view/g) || []).length, 2);
});

test("the five function agents, in the studio's order, each with its state", () => {
  const html = cards([{id: "web", name: "Web", node_status: "waiting_on_you", functions: fns("waiting_on_you")}]);
  const agents = [...html.matchAll(/<\/i>([^<]+)<small>([^<]+)<\/small>/g)].map(m => [m[1], m[2]]);
  assert.deepEqual(agents, [["Asha, talks to you", "Resting"], ["Planner, plans the work", "Resting"], ["Budget lead, picks what comes first", "Resting"],
    ["Scheduler, hands out the work", "Resting"], ["Nora, checks the work", "Needs your answer"]]);
});

test("no team yet says where teams come from; bad rows are skipped and every word is escaped", () => {
  assert.match(cards([]), /No teams yet\. Start a project on Attention/);
  const html = cards([null, {id: "../x"}, {id: "ok", name: "<b>x</b>", purpose: "<img src=x>", node_status: "nonsense"}]);
  assert.equal((html.match(/class="orgcard"/g) || []).length, 1);
  assert.ok(!html.includes("<b>x") && !html.includes("<img"));
  assert.match(html, /Resting/);
});
