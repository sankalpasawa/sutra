"use strict";
// The state of the project page (MAN-13, D326): a snapshot replaces whole and a bad one is refused with the last good one kept; messages continue the numbering or are not applied (a gap), a
// replay changes nothing; audit rows are appended once; "Sutra decided for you" is exactly the rows the rule table answered.
// Run with: node --test tests/ui/js/project_store.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ProjectStore = require(path.join(path.resolve(__dirname, "../../../sutra_app/ui/static/js"), "project_store.js"));
const snap = (over = {}) => Object.assign({project: {id: "prj_0123456789ab", title: "A page", status: "running"}, nodes: [], edges: [], last_message_seq: 0}, over);
const msg = seq => ({seq, from: {node_id: "nd_1"}, body: "x" + seq});

test("a snapshot is kept whole and a body that is not a project is refused, the last good one stays", () => {
  const s = ProjectStore.create();
  assert.equal(s.setSnapshot(snap()), true);
  assert.equal(s.state().loaded, true);
  for (const bad of [null, [], {}, {project: {}, nodes: []}, {project: {id: "p"}, nodes: "no"}]) {
    assert.equal(s.setSnapshot(bad), false);
    assert.match(s.state().error, /could not be read/);
    assert.equal(s.state().snapshot.project.id, "prj_0123456789ab");
  }
  assert.equal(s.setSnapshot(snap()), true);
  assert.equal(s.state().error, "");
});

test("messages are applied only when they continue the numbering; a gap is reported and nothing is applied", () => {
  const s = ProjectStore.create();
  assert.deepEqual(s.addMessages([msg(1), msg(2), msg(3)]), {applied: 3, gap: false});
  assert.deepEqual(s.addMessages([msg(5), msg(6)]), {applied: 0, gap: true});
  assert.equal(s.state().seq, 3);
  assert.deepEqual(s.addMessages([msg(4), msg(5)]), {applied: 2, gap: false});
  assert.deepEqual(s.state().messages.map(m => m.seq), [1, 2, 3, 4, 5]);
});

test("the same batch twice, or one in the wrong order, changes nothing it should not", () => {
  const s = ProjectStore.create();
  s.addMessages([msg(2), msg(1)]);
  assert.deepEqual(s.state().messages.map(m => m.seq), [1, 2]);
  assert.deepEqual(s.addMessages([msg(1), msg(2)]), {applied: 0, gap: false});
  assert.equal(s.state().seq, 2);
  assert.deepEqual(s.addMessages([{seq: "3"}, null, {}, msg(3)]), {applied: 1, gap: false});
});

test("a message the snapshot knows and the page has not read is 'behind'", () => {
  const s = ProjectStore.create();
  assert.equal(s.behind(), false);
  s.setSnapshot(snap({last_message_seq: 2}));
  assert.equal(s.behind(), true);
  s.addMessages([msg(1), msg(2)]);
  assert.equal(s.behind(), false);
});

test("audit rows are appended once, in order, and the newest are kept", () => {
  const s = ProjectStore.create();
  assert.equal(s.addAudit([{seq: 2, action: "b"}, {seq: 1, action: "a"}]), 2);
  assert.equal(s.addAudit([{seq: 2, action: "b"}, {seq: 3, action: "c"}]), 1);
  assert.deepEqual(s.state().audit.map(r => r.seq), [1, 2, 3]);
  assert.equal(s.state().auditAfter, 3);
  const many = Array.from({length: ProjectStore.KEEP + 20}, (_, i) => ({seq: 10 + i, action: "x"}));
  s.addAudit(many);
  assert.equal(s.state().audit.length, ProjectStore.KEEP);
  assert.equal(s.state().audit.at(-1).seq, 10 + ProjectStore.KEEP + 19);
});

test("what Sutra decided for the owner is exactly the rows the rule answered, with the answer and the reason", () => {
  const rows = [
    {seq: 1, at: "2026-11-20T10:00:00Z", action: "gate.decided", decision: "allow", node_id: "nd_1", reason: "decided_by rule:decide_for_me: tiers_0_3: reads the team folder"},
    {seq: 2, at: "2026-11-20T10:01:00Z", action: "gate.decided", decision: "allow", node_id: "nd_2", reason: "decided_by owner: yes"},
    {seq: 3, at: "2026-11-20T10:02:00Z", action: "gate.decided", decision: "deny", node_id: "nd_3", reason: "decided_by rule:decide_for_me: scope_violation: set the work aside"},
    {seq: 4, action: "grant.issued", decision: "allow", reason: "decided_by rule:decide_for_me"},
  ];
  const list = ProjectStore.decidedList(rows);
  assert.deepEqual(list.map(r => [r.seq, r.decision]), [[1, "yes"], [3, "no"]]);
  assert.equal(list[0].why, "reads the team folder");                                                // the rule's own name is not shown
  assert.deepEqual(ProjectStore.decidedList(null), []);
});

test("depths put a step after everything before it and a cycle cannot loop", () => {
  const nodes = [{id: "a"}, {id: "b"}, {id: "c"}, {id: "d"}];
  const edges = [{from: "a", to: "b", kind: "depends_on"}, {from: "b", to: "c", kind: "depends_on"}, {from: "a", to: "c", kind: "conflict"}];
  assert.deepEqual(ProjectStore.depths(nodes, edges), {a: 0, b: 1, c: 2, d: 0});
  const loop = ProjectStore.depths([{id: "x"}, {id: "y"}], [{from: "x", to: "y"}, {from: "y", to: "x"}]);
  assert.ok(Number.isInteger(loop.x) && Number.isInteger(loop.y));
  assert.deepEqual(ProjectStore.depths([{id: "a"}], [{from: "ghost", to: "a"}, null]), {a: 0});
});

test("a step is named in the owner's words", () => {
  assert.equal(ProjectStore.nodeName({role: "worker", plan_ref: "a1"}), "Step a1");
  assert.equal(ProjectStore.nodeName({role: "reviewer"}), "The reviewer");
  assert.equal(ProjectStore.nodeName({role: "planner"}), "The planner");
  assert.equal(ProjectStore.nodeName({role: "worker"}), "A step");
  assert.equal(ProjectStore.nodeName(null), "A step");
});
