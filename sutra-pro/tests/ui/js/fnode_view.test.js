"use strict";
// FnodeView (sutra_app/ui/static/js/fnode_view.js): the function drawer of the node panel, its work-atom cards with the five states, the tries of
// Verification and the plain-words pills, the stats and usage lines, the "Functions of <Department>" chips of a division, and the adapter that reads the
// wire. docs/design/ui.md sections 6.4, 7 and 10; S3-web-05, S4-fnodes-02, -03, -05, -08, -10, -14.
// Run with: node --test tests/ui/js/fnode_view.test.js
//
// The markup is parsed by a small XML reader below (balanced tags, quoted attributes, no raw "<", no stray "&"), so "well formed" is proved and the
// tests can ask for elements instead of matching text.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const FILE = path.join(JS, "fnode_view.js");
const FnodeView = require(FILE);
const {normalize, render, atomHtml, verifySentence, stateWord, functionsOf, normalizeAtom, nodeHtml, nodeWord, usageText, statsText} = FnodeView;
const DETAIL = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../fixtures/node-identity.json"), "utf8"));
const GRAPH = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../fixtures/graph-full.json"), "utf8"));

const DOT = " \u00b7 ";
const clone = value => JSON.parse(JSON.stringify(value));

/* ---------------------------------------------------------------- a small XML reader */
const ENTITY = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"};
function decode(text, where) {
  assert.equal(/&(?!(?:amp|lt|gt|quot|#39);)/.test(text), false, `a stray & in ${where}: ${text.slice(0, 80)}`);
  return text.replace(/&(?:amp|lt|gt|quot|#39);/g, m => ENTITY[m]);
}
function parse(markup) {
  const root = {tag: "#root", attrs: {}, children: [], text: "", content: []};
  const stack = [root];
  const TOKEN = /<(\/?)([A-Za-z][\w:-]*)((?:\s+[\w:.-]+="[^"<]*")*)\s*(\/?)>|<[^>]*>|[^<]+/y;
  let pos = 0;
  while (pos < markup.length) {
    TOKEN.lastIndex = pos;
    const m = TOKEN.exec(markup);
    assert.ok(m && m.index === pos, `not well formed at ${pos}: ${markup.slice(pos, pos + 80)}`);
    pos = TOKEN.lastIndex;
    const top = stack[stack.length - 1];
    if (m[2] === undefined) {
      assert.equal(m[0].startsWith("<"), false, `a malformed tag: ${m[0].slice(0, 80)}`);
      const piece = decode(m[0], "text");
      top.text += piece;
      top.content.push(piece);
      continue;
    }
    if (m[1] === "/") {
      assert.equal(top.tag, m[2], `</${m[2]}> closes <${top.tag}>`);
      stack.pop();
      continue;
    }
    const attrs = {};
    for (const a of m[3].matchAll(/([\w:.-]+)="([^"<]*)"/g)) {
      assert.equal(a[1] in attrs, false, `attribute ${a[1]} twice on <${m[2]}>`);
      attrs[a[1]] = decode(a[2], "attribute " + a[1]);
    }
    const node = {tag: m[2], attrs, children: [], text: "", content: []};
    top.children.push(node);
    top.content.push(node);
    if (m[4] !== "/") stack.push(node);
  }
  assert.equal(stack.length, 1, "unclosed tags: " + stack.slice(1).map(n => n.tag).join(" "));
  return root;
}
const walk = (node, fn) => { fn(node); node.children.forEach(c => walk(c, fn)); };
function selectOne(node, selector) {          // tag.class.class[attr][attr=value], one compound
  const m = /^([a-zA-Z0-9]*)((?:\.[\w-]+)*)((?:\[[\w:.-]+(?:=[^\]]*)?\])*)$/.exec(selector);
  assert.ok(m, "selector " + selector);
  const classes = m[2].split(".").filter(Boolean);
  const attrs = [...m[3].matchAll(/\[([\w:.-]+)(?:=([^\]]*))?\]/g)].map(a => [a[1], a[2]]);
  const out = [];
  walk(node, n => {
    if (n === node || n.tag === "#root") return;
    if (m[1] !== "" && n.tag !== m[1]) return;
    const have = (n.attrs.class || "").split(/\s+/);
    if (!classes.every(c => have.includes(c))) return;
    if (!attrs.every(([k, v]) => (v === undefined ? k in n.attrs : n.attrs[k] === v))) return;
    out.push(n);
  });
  return out;
}
// compounds separated by spaces are descendants: "section.fnfuncs h4"
function select(node, selector) {
  let found = [node];
  selector.trim().split(/\s+/).forEach(part => {
    const next = [];
    found.forEach(f => selectOne(f, part).forEach(n => { if (!next.includes(n)) next.push(n); }));
    found = next;
  });
  return found;
}
const one = (node, selector) => { const found = select(node, selector); assert.equal(found.length, 1, `${selector}: ${found.length} found`); return found[0]; };
const textOf = node => node.content.map(c => (typeof c === "string" ? c : textOf(c))).join("");
const dom = html => parse(html);

/* ---------------------------------------------------------------- data */
const atomById = id => DETAIL.atoms.find(a => a.id === id);
const OPEN = atomById("a-a810960e61-05");
const ABANDONED = atomById("a-a810960e61-04");
const FAILED = atomById("a-a810960e61-03");
const CLOSED = atomById("a-a810960e61-02");
const REFUSED = atomById("a-a810960e61-01");
const card = atom => one(dom(atomHtml(atom)), "details.atomcard");
const block = (c, name) => one(c, `div.ablock[data-block=${name}]`);

/* ================================================================ normalize: the adapter that reads the wire */
test("normalize reads a NodeDetail: the node, the seven meta keys, the live task, the usage and the atoms", () => {
  const v = normalize(DETAIL);
  assert.equal(v.id, "web.identity");
  assert.equal(v.fn, "identity");
  assert.equal(v.kind, "function");
  assert.equal(v.label, "Identity");
  assert.equal(v.status, "waiting_on_you");
  assert.equal(v.detail, "last seen: asked about the menu");
  assert.equal(v.deptId, "web");
  assert.equal(v.sessionId, "cs_77aa10c2e9b4");
  assert.equal(v.goal, DETAIL.node.meta.goal);
  assert.equal(v.task, "J2.a charter, J2.d rulings, J2.h workable?");
  assert.deepEqual(v.context, ["charter", "proposals", "findings", "alarms", "recorded rules"]);
  assert.equal(v.constraints.length, 6);
  assert.equal(v.waitOn, "you");
  assert.deepEqual(v.handsTo, ["adaptation", "priority", "coordination", "audit"]);
  assert.deepEqual(v.stats, {seconds: 52, calls: 16, tokens_in: 9600, tokens_out: 2880, atoms_open: 1, atoms_closed: 1, atoms_failed: 1, atoms_total: 5});
  assert.deepEqual(v.usage, {calls: 16, usd: 0.56, tokens_in: 9600, tokens_out: 2880});
  assert.deepEqual(v.workingFor, {id: "tsk_a1b2c3d4e5f6", title: "Coffee shop landing page", status: "waiting_user"});
  assert.equal(v.atoms.length, 5);
  assert.equal(v.atomsTotal, 5);
  assert.deepEqual(v.archivedChats, []);
});

test("normalize also reads just the meta of a function node", () => {
  const v = normalize(DETAIL.node.meta);
  assert.equal(v.goal, DETAIL.node.meta.goal);
  assert.equal(v.stats.atoms_total, 5);
  assert.equal(v.id, "");
  assert.deepEqual(v.atoms, []);
  assert.equal(v.workingFor, null);
  assert.equal(v.usage, null);
});

test("task is a string, or an object with summary; anything else is empty", () => {
  assert.equal(normalize({task: "J2.c prices, checks run limits"}).task, "J2.c prices, checks run limits");
  assert.equal(normalize({task: {summary: "J2.c prices"}}).task, "J2.c prices");
  assert.equal(normalize({task: {summary: 5}}).task, "");
  assert.equal(normalize({task: {title: "no summary"}}).task, "");
  assert.equal(normalize({task: 7}).task, "");
});

test("missing stats keys count as 0, in the view and in the lines", () => {
  const v = normalize({goal: "g", stats: {calls: 3}});
  assert.deepEqual(v.stats, {seconds: 0, calls: 3, tokens_in: 0, tokens_out: 0, atoms_open: 0, atoms_closed: 0, atoms_failed: 0, atoms_total: 0});
  assert.deepEqual(normalize({goal: "g"}).stats, {seconds: 0, calls: 0, tokens_in: 0, tokens_out: 0, atoms_open: 0, atoms_closed: 0, atoms_failed: 0, atoms_total: 0});
  assert.deepEqual(normalize({stats: {calls: -4, atoms_total: "7", atoms_open: NaN, seconds: -2}}).stats.atoms_total, 0);
  assert.equal(normalize({stats: {calls: -4}}).stats.calls, 0);
  assert.equal(normalize({stats: {seconds: -2}}).stats.seconds, 0);
  assert.equal(normalize({stats: {seconds: 12.5}}).stats.seconds, 12.5);
});

test("normalize ignores atom_count and every key it does not name", () => {
  const meta = {...DETAIL.node.meta, atom_count: 99, last_seen: "yesterday", bogus: {a: 1}, stats: {...DETAIL.node.meta.stats, atom_count: 5, extra: 1}};
  const v = normalize({...DETAIL, node: {...DETAIL.node, meta, secret: "x"}, surprise: 1});
  const dump = JSON.stringify(v);
  ["atom_count", "last_seen", "bogus", "surprise", "secret", "extra"].forEach(k => assert.equal(dump.includes(k), false, k));
  assert.equal(v.atomsTotal, 5);
});

test("normalize never throws on garbage and gives an empty view", () => {
  [undefined, null, 5, "text", [], {}, {node: 5}, {node: {}, atoms: "no", task: "no", usage_total: 3}, {atoms: [null, 4, "x"]}].forEach(raw => {
    const v = normalize(raw);
    assert.equal(v.view, "fnode");
    assert.deepEqual(v.atoms, []);
    assert.equal(v.goal, "");
    assert.equal(render(v).includes("undefined"), false);
  });
});

test("the atoms come open first, then the newest, and the server's order stands where those keys tie", () => {
  const a = (id, state, ts) => ({id, state, ts_open: ts});
  const v = normalize({node: {id: "n"}, atoms: [a("old", "closed", "2026-11-04T10:00:01Z"), a("new", "closed", "2026-11-04T10:00:09Z"), a("live", "open", "2026-11-04T10:00:05Z"),
    a("tie1", "closed", "2026-11-04T10:00:03Z"), a("tie2", "closed", "2026-11-04T10:00:03Z")]});
  assert.deepEqual(v.atoms.map(x => x.id), ["live", "new", "tie1", "tie2", "old"]);
  assert.deepEqual(normalize(DETAIL).atoms.map(x => x.id), DETAIL.atoms.map(x => x.id));
});

test("the number of work atoms is the server's total, and never less than the list", () => {
  const atoms = [{id: "a"}, {id: "b"}, {id: "c"}];
  assert.equal(normalize({node: {meta: {stats: {atoms_total: 30}}}, atoms}).atomsTotal, 30);
  assert.equal(normalize({node: {}, atoms}).atomsTotal, 3);
  assert.equal(normalize({node: {meta: {stats: {atoms_total: 1}}}, atoms}).atomsTotal, 3);
});

test("wait_on is null, 'you', a function key or a builder id", () => {
  assert.equal(normalize({wait_on: null}).waitOn, null);
  assert.equal(normalize({wait_on: ""}).waitOn, null);
  assert.equal(normalize({wait_on: "priority"}).waitOn, "priority");
  assert.equal(normalize({wait_on: 7}).waitOn, "7");
});

/* ================================================================ render: the function drawer */
test("the sections come in the order of the design: head, goal, task, context, atoms, constraints, hands to", () => {
  const doc = dom(render(DETAIL, {withAgent: true}));
  assert.deepEqual(doc.children.filter(c => c.tag === "section").map(c => c.attrs["data-sec"]), ["head", "goal", "task", "context", "atoms", "constraints", "hands"]);
  assert.equal(doc.children[doc.children.length - 1].attrs.class, "fntail");
  const headings = ["Goal", "Task", "What this function is given", "Work atoms (5)", "Constraints", "Hands to"];
  assert.deepEqual(["goal", "task", "context", "atoms", "constraints", "hands"].map(s => textOf(one(one(doc, `section.fnsec[data-sec=${s}]`), "h4"))), headings);
});

test("the strip's legend sits under the work atoms heading", () => {
  const atoms = one(dom(render(DETAIL)), "section[data-sec=atoms]");
  assert.equal(textOf(one(atoms, "p.atomlegend")), "open > work > verify, close; exits: refuse, abandon");
  assert.equal(FnodeView.LEGEND, "open > work > verify, close; exits: refuse, abandon");
  assert.equal(atoms.children[0].tag, "h4");
  assert.equal(atoms.children[1].attrs.class, "atomlegend");
});

test("the head names the persona and the function, the status, what it is doing, the usage and the counts", () => {
  const head = one(dom(render(DETAIL)), "section[data-sec=head]");
  assert.equal(textOf(one(head, "h4.fntitle")), "Client Lead" + DOT + "Identity");
  assert.equal(textOf(one(head, "span.nstatus")), "waiting on you");
  assert.equal(one(head, "span.nstatus").attrs.class, "nstatus st-waiting_on_you");
  assert.equal(textOf(one(head, "p.fnnow")), "last seen: asked about the menu");
  assert.equal(textOf(one(head, "p.fnusage")), "16 calls" + DOT + "$0.56" + DOT + "9,600 in / 2,880 out tokens");
  assert.equal(textOf(one(head, "p.fncounts")), "16 calls, 52 s, 1 atom open, 1 closed, 1 failed");
  assert.equal(one(head, "button.fnchat").attrs["data-act"], "chat");
  assert.equal(textOf(one(head, "button.fnchat")), "Chat");
});

test("the stats line, with and without failures", () => {
  assert.equal(statsText({calls: 12, seconds: 41.0, atoms_open: 1, atoms_closed: 5}), "12 calls, 41 s, 1 atom open, 5 closed");
  assert.equal(statsText({calls: 12, seconds: 41.0, atoms_open: 1, atoms_closed: 5, atoms_failed: 1}), "12 calls, 41 s, 1 atom open, 5 closed, 1 failed");
  assert.equal(statsText({calls: 12, seconds: 41.0, atoms_open: 1, atoms_closed: 5, atoms_failed: 0}).includes("failed"), false);
  assert.equal(statsText({calls: 1, seconds: 2.34, atoms_open: 2, atoms_closed: 0, atoms_failed: 3}), "1 call, 2.3 s, 2 atoms open, 0 closed, 3 failed");
  assert.equal(statsText({calls: 1234, seconds: 4100.4, atoms_open: 0}), "1,234 calls, 4,100 s, 0 atoms open, 0 closed");
  assert.equal(statsText(null), "0 calls, 0 s, 0 atoms open, 0 closed");
  assert.equal(textOf(one(dom(render({goal: "g", stats: {calls: 4, atoms_open: 1, atoms_closed: 2}})), "p.fncounts")), "4 calls, 0 s, 1 atom open, 2 closed");
});

test("the usage line leaves out every part that is null, and is empty when all are", () => {
  assert.equal(usageText({calls: 12, usd: 0.42, tokens_in: 7000, tokens_out: 2120}), "12 calls" + DOT + "$0.42" + DOT + "7,000 in / 2,120 out tokens");
  assert.equal(usageText({calls: 12, usd: null, tokens_in: 7000, tokens_out: 2120}), "12 calls" + DOT + "7,000 in / 2,120 out tokens");
  assert.equal(usageText({calls: 1, usd: 0.0004, tokens_in: null, tokens_out: 90}), "1 call" + DOT + "under $0.01" + DOT + "90 tokens out");
  assert.equal(usageText({calls: null, usd: 0, tokens_in: 5, tokens_out: null}), "$0.00" + DOT + "5 tokens in");
  assert.equal(usageText({calls: 0, usd: null, tokens_in: null, tokens_out: null}), "0 calls");
  assert.equal(usageText({calls: null, usd: null, tokens_in: null, tokens_out: null}), "");
  assert.equal(usageText(null), "");
  assert.equal(usageText({calls: -1, usd: "0.4"}), "");
  const head = one(dom(render({node: {id: "x.identity", kind: "function", fn: "identity"}, usage_total: {calls: null, usd: null, tokens_in: null, tokens_out: null}})), "section[data-sec=head]");
  assert.equal(select(head, "p.fnusage").length, 0);
});

test("the task shows its J2 step code small and grey, what it works for, and whom it waits on", () => {
  const task = one(dom(render(DETAIL)), "section[data-sec=task]");
  assert.equal(textOf(one(task, "p.fntask")), "J2.a charter, J2.d rulings, J2.h workable?");
  assert.equal(textOf(one(task, "span.code")), "J2.a");
  assert.equal(textOf(one(task, "p.fnwork")), "Working for: Coffee shop landing page (waiting for you)");
  assert.equal(textOf(one(task, "p.fnwait")), "Waiting on you");
  const priced = one(dom(render({task: "J2.c prices, checks run limits", wait_on: "priority"})), "section[data-sec=task]");
  assert.equal(textOf(one(priced, "span.code")), "J2.c");
  assert.equal(textOf(one(priced, "p.fnwait")), "Waiting on Prioritiser");
  assert.equal(select(priced, "p.fnwork").length, 0);
  const plain = one(dom(render({task: "Reads the finished site"})), "section[data-sec=task]");
  assert.equal(select(plain, "span.code").length, 0);
  assert.equal(textOf(one(plain, "p.fntask")), "Reads the finished site");
  assert.equal(select(plain, "p.fnwait").length, 0);
  assert.equal(textOf(one(dom(render({wait_on: "W-3"})), "p.fnwait")), "Waiting on W-3 Builder");
  assert.equal(textOf(one(dom(render({task: {summary: "J2.f schedules"}})), "span.code")), "J2.f");
});

test("what the task is working for names its status in words", () => {
  const work = status => textOf(one(dom(render({node: {id: "a.audit", kind: "function"}, task: {id: "t", title: "Menu", status}})), "p.fnwork"));
  assert.equal(work("running"), "Working for: Menu (running)");
  assert.equal(work("waiting_user"), "Working for: Menu (waiting for you)");
  assert.equal(work("done_with_open_items"), "Working for: Menu (done, with open items)");
  assert.equal(work("some_new_state"), "Working for: Menu (some new state)");
  assert.equal(textOf(one(dom(render({node: {id: "a.audit", kind: "function"}, task: {id: "t", title: "Menu", status: ""}})), "p.fnwork")), "Working for: Menu");
  assert.equal(select(dom(render({node: {id: "a.audit", kind: "function"}, task: {id: "t", title: "", status: "running"}})), "p.fnwork").length, 0);
});

test("the context is worded with J2's names for what a call is given", () => {
  const ctx = one(dom(render(DETAIL)), "section[data-sec=context]");
  assert.deepEqual(select(ctx, "li").map(textOf), ["the charter", "proposals", "Audit's findings", "alarms", "recorded rules"]);
  const names = select(one(dom(render({context: ["ledger", "workflows", "workflow", "chat", "task", "lessons", "proposal", "playbook", "capability_catalogue"]})), "section[data-sec=context]"), "li").map(textOf);
  assert.deepEqual(names, ["the budget", "the workflow list", "its own workflow", "the chat", "its task", "lessons from earlier work", "the proposal", "a saved playbook", "capability catalogue"]);
  const empty = one(dom(render({context: []})), "section[data-sec=context]");
  assert.equal(textOf(one(empty, "span.empty")), "nothing on record");
  assert.equal(select(empty, "li").length, 0);
});

test("the constraints are J2's 'You may not' lines, and the plugin word Limits is nowhere", () => {
  const sec = one(dom(render(DETAIL)), "section[data-sec=constraints]");
  assert.equal(textOf(one(sec, "p.adsmall")), "You may not:");
  assert.deepEqual(select(sec, "li").map(textOf), DETAIL.node.meta.constraints);
  const empty = one(dom(render({constraints: []})), "section[data-sec=constraints]");
  assert.equal(textOf(one(empty, "span.empty")), "none");
  assert.equal(select(empty, "p.adsmall").length, 0);
  assert.equal(render(DETAIL, {withAgent: true}).includes("Limits"), false);
});

test("hands to: a chip for each function that can be handed to; Identity also shows 'you'; 'Handed from' is the inverse", () => {
  const idn = one(dom(render(DETAIL)), "section[data-sec=hands]");
  assert.deepEqual(select(one(idn, "div.fnchips.fnto"), "button.fnchip").map(b => b.attrs["data-fn"]), ["adaptation", "priority", "coordination", "audit"]);
  assert.equal(textOf(one(one(idn, "div.fnchips.fnto"), "span.fnyou")), "you");
  assert.equal(textOf(select(one(idn, "div.fnchips.fnto"), "button.fnchip")[0]), "Strategist Adaptation");
  assert.deepEqual(select(one(idn, "div.fnchips.fnfrom"), "button.fnchip").map(b => b.attrs["data-fn"]), ["adaptation", "priority", "coordination", "audit"]);
  assert.equal(select(one(idn, "div.fnchips.fnfrom"), "span.fnyou").length, 1);
  assert.equal(textOf(one(idn, "p.fnfromlab")), "Handed from");
  const audit = one(dom(render({node: {id: "web.audit", kind: "function", fn: "audit", meta: {hands_to: ["identity"]}}})), "section[data-sec=hands]");
  assert.deepEqual(select(one(audit, "div.fnchips.fnto"), "button").map(b => b.attrs["data-fn"]), ["identity"]);
  assert.equal(select(audit, "span.fnyou").length, 0);
  assert.deepEqual(select(one(audit, "div.fnchips.fnfrom"), "button").map(b => b.attrs["data-fn"]), ["identity", "adaptation", "coordination"]);
  const priority = one(dom(render({node: {id: "web.priority", kind: "function", fn: "priority", meta: {hands_to: ["adaptation", "identity", "coordination"]}}})), "section[data-sec=hands]");
  assert.deepEqual(select(one(priority, "div.fnchips.fnfrom"), "button").map(b => b.attrs["data-fn"]), ["identity", "adaptation", "coordination"]);
  const bare = one(dom(render({hands_to: []})), "section[data-sec=hands]");
  assert.equal(textOf(one(one(bare, "div.fnchips.fnto"), "span.empty")), "none");
});

test("on the department page the drawer ends with Go to the <function> tab and the place for J2's block", () => {
  const FN_TAB = {identity: "charter", adaptation: "workflows", priority: "conflicts", coordination: "timeline", audit: "audit"};
  const names = {identity: "Identity", adaptation: "Adaptation", priority: "Priority", coordination: "Coordination", audit: "Audit"};
  Object.keys(FN_TAB).forEach(fn => {
    const doc = dom(render({node: {id: "web." + fn, kind: "function", fn}, goal: "g"}, {withAgent: true}));
    const go = one(doc, "button.fngo");
    assert.equal(textOf(go), `Go to the ${names[fn]} tab`);
    assert.equal(go.attrs["data-act"], "go-tab");
    assert.equal(go.attrs["data-tab"], FN_TAB[fn]);
    assert.equal(one(doc, "div.fnagent").attrs["data-fnagent"], fn);
    assert.equal(select(doc, "p.fnfull").length, 0);
  });
  assert.deepEqual(FnodeView.FN_TAB, FN_TAB);
});

test("J2's own data-agent attribute is never used in the drawer (a click on it would reopen the Agent drawer)", () => {
  const html = render(DETAIL, {withAgent: true});
  assert.equal(/data-agent(?!=)/.test(html.replace(/data-fnagent/g, "")), false);
  assert.equal(html.includes("data-agentclose"), false);
});

test("on Home the drawer has no Go-to-tab button and a line that sends the owner to the team page", () => {
  const doc = dom(render(DETAIL, {withAgent: false}));
  assert.equal(select(doc, "button.fngo").length, 0);
  assert.equal(select(doc, "div.fnagent").length, 0);
  const line = one(doc, "p.fnfull");
  assert.equal(textOf(line), "Full conversations and thinking: open the team page.");
  assert.equal(one(line, "button").attrs["data-href"], "/d/web/?view=detail");
  assert.equal(select(dom(render(DETAIL)), "button.fngo").length, 0);
  assert.equal(one(dom(render({goal: "g"})), "p.fnfull").children[0].attrs["data-href"], undefined);
});

test("a function that is not one of the five has no tab to go to", () => {
  const doc = dom(render({node: {id: "x.other", kind: "function", label: "Other"}, goal: "g"}, {withAgent: true}));
  assert.equal(select(doc, "button.fngo").length, 0);
  assert.equal(textOf(one(doc, "h4.fntitle")), "Other");
});

test("Show all appears only when the server holds more atoms than it sent", () => {
  const some = clone(DETAIL);
  some.node.meta.stats.atoms_total = 27;
  const doc = dom(render(some));
  assert.equal(textOf(one(doc, "button.fnmore")), "Show all (27)");
  assert.equal(one(doc, "button.fnmore").attrs["data-act"], "show-all");
  assert.equal(textOf(one(doc, "section[data-sec=atoms] h4")), "Work atoms (27)");
  assert.equal(select(dom(render(DETAIL)), "button.fnmore").length, 0);
});

test("no atoms yet says so", () => {
  const doc = dom(render({node: {id: "web.audit", kind: "function", fn: "audit"}, atoms: []}));
  assert.equal(textOf(one(doc, "section[data-sec=atoms] p.empty")), "No work atoms yet.");
  assert.equal(textOf(one(doc, "section[data-sec=atoms] h4")), "Work atoms (0)");
});

test("render takes a view or the raw answer and draws the same", () => {
  assert.equal(render(normalize(DETAIL), {withAgent: true}), render(DETAIL, {withAgent: true}));
  assert.equal(render(normalize(DETAIL)), render(DETAIL, {}));
});

test("the atoms named in openIds are drawn unfolded, the others folded", () => {
  const html = render(DETAIL, {openIds: [OPEN.id]});
  const cards = select(dom(html), "details.atomcard");
  assert.deepEqual(cards.filter(c => "open" in c.attrs).map(c => c.attrs["data-atom"]), [OPEN.id]);
  assert.equal(select(dom(render(DETAIL)), "details.atomcard").some(c => "open" in c.attrs), false);
});

test("every word from the wire is escaped and the whole drawer is well formed", () => {
  const evil = clone(DETAIL);
  const bad = `<script>alert("x")</script> & 'q'`;
  evil.node.meta.goal = bad;
  evil.node.meta.task = "J2.a " + bad;
  evil.node.meta.context = [bad];
  evil.node.meta.constraints = [bad];
  evil.node.detail = bad;
  evil.task.title = bad;
  evil.atoms[0].goal = bad;
  evil.atoms[0].body.constraints = [{text: bad}];
  evil.atoms[0].body.verify.checks[0].text = bad;
  evil.atoms[0].body.verify.checks[0].results[0].evidence = bad;
  const html = render(evil, {withAgent: true});
  assert.equal(html.includes("<script"), false);
  assert.equal(html.includes('alert("x")'), false);
  const doc = dom(html);
  assert.equal(textOf(one(one(doc, "section[data-sec=goal]"), "p")), bad);
  assert.equal(select(doc, "script").length, 0);
});

/* ================================================================ atom cards: the five states */
test("an atom card is a details element with the status line, then J2's labels in J2's order", () => {
  const c = card(CLOSED);
  assert.equal(c.attrs["data-state"], "closed");
  assert.equal(c.attrs["data-atom"], "a-a810960e61-02");
  assert.equal(c.attrs["data-key"], "atom-a-a810960e61-02");
  assert.deepEqual(select(c, "div.ablock").map(b => textOf(b.children[0])), ["Goal", "Constraints", "Context", "How", "Expected output", "Verification", "Result"]);
  assert.deepEqual(select(c, "div.ablock").map(b => b.children[0].tag), ["b", "b", "b", "b", "b", "b", "b"]);
  assert.deepEqual(select(c, "div.ablock").map(b => b.attrs["data-block"]), ["goal", "constraints", "context", "how", "expected_output", "verification", "result"]);
  assert.equal(atomHtml(CLOSED).includes("Limits"), false);
  assert.equal(c.children[0].tag, "summary");
});

test("an open atom: OPEN, attempt 2 of 3, in progress, and the next try is pending", () => {
  const c = card(OPEN);
  assert.equal(c.attrs["data-state"], "open");
  const line = one(c, "span.astate");
  assert.equal(textOf(line), "OPEN");
  assert.equal(line.attrs.class, "astate st-open");
  assert.equal(line.attrs.title, "in progress, attempt 2");
  assert.equal(textOf(one(c, "span.aattempt")), "attempt 2 of 3");
  assert.equal(textOf(one(c, "span.agoal")), OPEN.goal);
  assert.equal(textOf(one(c, "span.code")), "a-a810960e61-05");
  assert.equal(textOf(one(block(c, "result"), "span.apill")), "in progress, attempt 2");
  const verification = block(c, "verification");
  assert.equal(select(verification, "li.try-pending").length, 4);
  assert.equal(textOf(select(verification, "li.try-pending")[0]), "attempt 3: pending");
});

test("an open atom after one failed try says so: in progress, attempt 1, and the second try is pending", () => {
  const first = clone(OPEN);
  first.attempt = 1;
  first.body.verify.checks.forEach(ch => { ch.results = ch.results.slice(0, 1); });
  const c = card(first);
  assert.equal(textOf(one(c, "span.aattempt")), "attempt 1 of 3");
  assert.equal(one(c, "span.astate").attrs.title, "in progress, attempt 1");
  assert.equal(textOf(one(block(c, "result"), "span.apill")), "in progress, attempt 1");
  assert.equal(textOf(select(block(c, "verification"), "li.try-pending")[0]), "attempt 2: pending");
});

test("an open atom with no try yet has attempt 1 pending, says in progress, and shows no 'attempt of 3'", () => {
  const fresh = clone(OPEN);
  fresh.attempt = 0;
  fresh.body.verify.checks.forEach(ch => { ch.results = []; });
  const c = card(fresh);
  assert.equal(select(c, "span.aattempt").length, 0);
  assert.equal(one(c, "span.astate").attrs.title, "in progress");
  assert.equal(textOf(one(block(c, "result"), "span.apill")), "in progress");
  assert.equal(textOf(select(block(c, "verification"), "li.try-pending")[0]), "attempt 1: pending");
});

test("an open atom on its last attempt has no pending try", () => {
  const last = clone(OPEN);
  last.attempt = 3;
  last.body.verify.checks.forEach(ch => ch.results.push({attempt: 3, exit_code: 1, evidence: "still not"}));
  assert.equal(select(card(last), "li.try-pending").length, 0);
});

test("a try that failed reads 'attempt 1: failed, <evidence>', one that passed 'passed'", () => {
  const verification = block(card(FAILED), "verification");
  const checks = select(verification, "div.acheck");
  assert.equal(checks.length, 4);
  assert.equal(textOf(one(checks[0], "p.asent")), "the reply has the shape this function must send");
  assert.deepEqual(select(checks[0], "li.try").map(textOf), ["attempt 1: failed, enough: field required", "attempt 2: passed, ok"]);
  assert.deepEqual(select(checks[2], "li.try").map(textOf), ["attempt 1: deferred, judged when the turn ends", "attempt 2: failed, Charter rejected: fewer than 3 'done when' criteria."]);
  assert.deepEqual(select(checks[2], "li.try").map(li => li.attrs.class), ["try try-deferred", "try try-failed"]);
  assert.deepEqual(select(checks[2], "li.try").map(li => li.attrs["data-attempt"]), ["1", "2"]);
  assert.equal(checks[2].attrs["data-template"], "charter-stamp");
});

test("a verify_failed atom: VERIFY FAILED, the check did not pass, the reason is kept, nothing is pending", () => {
  const c = card(FAILED);
  assert.equal(c.attrs["data-state"], "verify_failed");
  assert.equal(textOf(one(c, "span.astate")), "VERIFY FAILED");
  assert.equal(textOf(one(c, "span.aattempt")), "attempt 2 of 3");
  const result = block(c, "result");
  assert.equal(textOf(one(result, "span.apill")), "the check did not pass, so nothing is marked done");
  assert.equal(one(c, "span.astate").attrs.title, "the check did not pass, so nothing is marked done");
  assert.equal(textOf(one(result, "div.areason")), "Reason verify failed: charter-stamp: Charter rejected: fewer than 3 'done when' criteria.");
  assert.equal(select(c, "li.try-pending").length, 0);
  assert.equal(select(result, "div.aconcern").length, 0);
});

test("a closed atom: CLOSED, goal reached and checked, and a Concern on record for RECOVERED", () => {
  const c = card(CLOSED);
  assert.equal(textOf(one(c, "span.astate")), "CLOSED");
  const result = block(c, "result");
  assert.equal(textOf(one(result, "span.apill")), "goal reached, and checked");
  const concern = one(result, "div.aconcern");
  assert.equal(textOf(one(concern, "b")), "Concern on record");
  assert.equal(textOf(concern), "Concern on record RECOVERED: template, the bad part became the default text");
  assert.equal(select(result, "div.areason").length, 0);
  assert.equal(select(c, "li.try-pending").length, 0);
});

test("a closed atom that J2 let through with a concern on record says WAIVED", () => {
  const waived = clone(CLOSED);
  waived.body.verify.checks[2].results[1].evidence = "WAIVED: Charter accepted after two attempts";
  const result = block(card(waived), "result");
  assert.equal(textOf(one(result, "div.aconcern")), "Concern on record WAIVED: Charter accepted after two attempts");
  const clean = clone(CLOSED);
  clean.body.verify.checks[2].results[1].evidence = "to_requester is plain";
  assert.equal(select(block(card(clean), "result"), "div.aconcern").length, 0);
});

test("an abandoned atom: ABANDONED, stopped on purpose, and the reason is kept", () => {
  const c = card(ABANDONED);
  assert.equal(c.attrs["data-state"], "abandoned");
  assert.equal(textOf(one(c, "span.astate")), "ABANDONED");
  const result = block(c, "result");
  assert.equal(textOf(one(result, "span.apill")), "stopped on purpose, reason kept");
  assert.equal(textOf(one(result, "div.areason")), "Reason replaced: a newer turn opened on this node");
});

test("a refused atom: REFUSED, not started, with only a Goal and a Result", () => {
  const c = card(REFUSED);
  assert.equal(c.attrs["data-state"], "refused");
  assert.equal(textOf(one(c, "span.astate")), "REFUSED");
  assert.equal(select(c, "span.aattempt").length, 0);
  assert.deepEqual(select(c, "div.ablock").map(b => b.attrs["data-block"]), ["goal", "result"]);
  assert.equal(textOf(one(block(c, "result"), "span.apill")), "not started: goal is banal ('done'): state the observable outcome");
  assert.equal(one(c, "span.astate").attrs.title, "not started: goal is banal ('done'): state the observable outcome");
  assert.equal(select(c, "div.areason").length, 0);
  const noMessage = clone(REFUSED);
  delete noMessage.body.refusal;
  assert.equal(textOf(one(block(card(noMessage), "result"), "span.apill")), "not started: refused");
});

test("stateWord gives the status line word of the five display words and shows any other word as it came", () => {
  assert.deepEqual(["open", "closed", "verify_failed", "abandoned", "refused"].map(stateWord), ["OPEN", "CLOSED", "VERIFY FAILED", "ABANDONED", "REFUSED"]);
  assert.equal(stateWord("passed"), "PASSED");
  assert.equal(stateWord("half_done"), "HALF DONE");
  assert.equal(stateWord(""), "UNKNOWN");
  assert.equal(stateWord(undefined), "UNKNOWN");
  const odd = card({id: "x", state: "half_done", goal: "g"});
  assert.equal(odd.attrs["data-state"], "unknown");
  assert.equal(textOf(one(odd, "span.astate")), "HALF DONE");
  assert.equal(textOf(one(block(odd, "result"), "span.apill")), "");
});

test("the lifecycle is read from state; status is only a fallback for old fixtures", () => {
  assert.equal(card({id: "x", state: "closed", status: "open", goal: "g"}).attrs["data-state"], "closed");
  assert.equal(card({id: "x", status: "verify_failed", goal: "g"}).attrs["data-state"], "verify_failed");
});

/* ================================================================ atom cards: the rows */
test("Goal, Constraints, Context and Expected output come from the library Atom's names", () => {
  const c = card(OPEN);
  assert.equal(textOf(one(block(c, "goal"), "div")), OPEN.goal);
  assert.deepEqual(select(block(c, "constraints"), "li").map(textOf), ["invent a new goal or rule", "choose tools or implementation steps"]);
  assert.deepEqual(select(block(c, "context"), "li").map(textOf), ["brief: A website for my cafe", "charter: none yet"]);
  assert.deepEqual(select(block(c, "expected_output"), "li").map(textOf), ["goal.json"]);
  const two = clone(OPEN);
  two.body.outputs = ["goal.json", "notes.md"];
  assert.deepEqual(select(block(card(two), "expected_output"), "li").map(textOf), ["goal.json"]);
  const bare = card({id: "x", state: "open", goal: "g", body: {}});
  ["constraints", "context", "expected_output"].forEach(name => assert.equal(textOf(one(block(bare, name), "span.empty")), "none"));
  assert.equal(textOf(one(block(bare, "verification"), "span.empty")), "no check declared");
});

test("How: the model for an AI turn, code with no AI call for bash, you for the owner's question", () => {
  const how = atom => textOf(one(block(card(atom), "how"), "div"));
  assert.equal(how(OPEN), "Claude (sonnet)");
  const llm = model => ({id: "x", state: "closed", goal: "g", body: {work: {dispatch_kind: "llm"}, model}});
  assert.equal(how(llm("opus")), "Claude (opus)");
  assert.equal(how(llm("claude-sonnet-4")), "Claude (claude-sonnet-4)");
  assert.equal(how(llm("gpt-5")), "Codex (gpt-5)");
  assert.equal(how(llm("o3")), "Codex (o3)");
  assert.equal(how(llm("mystery")), "mystery");
  assert.equal(how(llm(null)), "an AI model");
  assert.equal(how({id: "x", state: "closed", goal: "g", body: {work: {dispatch_kind: "bash"}}}), "code, no AI call");
  assert.equal(how({id: "x", state: "closed", goal: "g", body: {work: {dispatch_kind: "manual", agent: "owner"}}}), "you");
  assert.equal(how({id: "x", state: "closed", goal: "g", body: {work: {dispatch_kind: "skill"}}}), "a Sutra skill");
});

test("How prefers the models that usage names over body.model", () => {
  const how = usage => textOf(one(block(card({id: "x", state: "closed", goal: "g", body: {work: {dispatch_kind: "llm"}, model: "sonnet"}, usage}), "how"), "div"));
  assert.equal(how({calls: 3, models: [{provider: "codex", model: "gpt-5"}, "sonnet"]}), "Codex (gpt-5), Claude (sonnet)");
  assert.equal(how({calls: 3, model: "opus", provider: "claude"}), "Claude (opus)");
  assert.equal(how({calls: 3, models: []}), "Claude (sonnet)");
  assert.equal(how({calls: 3}), "Claude (sonnet)");
  assert.equal(how({calls: 3, models: [{provider: "claude"}]}), "Claude");
});

test("the cost line leaves out the parts that are null, and says nothing when all are", () => {
  const cost = atom => select(block(card(atom), "result"), "div.acost").map(textOf);
  assert.deepEqual(cost(OPEN), ["7 calls" + DOT + "$0.25" + DOT + "4,200 in / 1,300 out tokens"]);
  assert.deepEqual(cost({...CLOSED, usage: {calls: 2, usd: null, tokens_in: 100, tokens_out: 20}}), ["2 calls" + DOT + "100 in / 20 out tokens"]);
  assert.deepEqual(cost(REFUSED), ["0 calls"]);
  assert.deepEqual(cost({...REFUSED, usage: {calls: null, usd: null, tokens_in: null, tokens_out: null}}), []);
  assert.deepEqual(cost({...REFUSED, usage: null}), []);
});

test("Verification starts with each check's sentence, then every try, and spells the plugin templates", () => {
  const checks = [
    {template: "file-exists", args: ["site/index.html"], results: [{attempt: 1, exit_code: 0, evidence: "ok"}]},
    {template: "grep-count", args: ["Menu", "site/index.html", "1"], results: []},
    {template: "named-test", args: ["tests/menu.sh"], text: "", results: []},
    {template: "audience-split", args: [], results: []},
    {template: "charter-stamp", args: [], text: "the charter has a statement", results: []},
  ];
  const v = block(card({id: "x", state: "closed", goal: "g", attempt: 1, body: {verify: {checks}}}), "verification");
  assert.deepEqual(select(v, "p.asent").map(textOf), ["the file site/index.html exists and is not empty", 'the text "Menu" appears in site/index.html',
    "the test tests/menu.sh passes", "audience-split", "the charter has a statement"]);
  assert.equal(textOf(select(v, "li.try")[0]), "attempt 1: passed, ok");
});

test("verifySentence: Check.text first, then the plugin's sentences, then the template's name", () => {
  assert.equal(verifySentence({template: "file-exists", args: ["a.txt"], text: "the file is there"}), "the file is there");
  assert.equal(verifySentence({template: "file-exists", args: ["a.txt"]}), "the file a.txt exists and is not empty");
  assert.equal(verifySentence({template: "grep-count", args: ["Menu", "index.html", "1"]}), 'the text "Menu" appears in index.html');
  assert.equal(verifySentence({template: "named-test", args: ["t.sh"]}), "the test t.sh passes");
  assert.equal(verifySentence({template: "turn-posted"}), "turn-posted");
  assert.equal(verifySentence({template: "file-exists", args: []}), "the file ? exists and is not empty");
  assert.equal(verifySentence({template: "grep-count"}), 'the text "?" appears in ?');
  assert.equal(verifySentence({template: "", text: "  "}), "a check");
  assert.equal(verifySentence(null), "a check");
  assert.equal(verifySentence({template: "named-test", args: [5]}), "the test 5 passes");
});

test("a try with no verdict reads 'not run', and a try with no evidence says only the verdict", () => {
  const checks = [{template: "t", text: "a check", results: [{attempt: 1}, {attempt: 2, exit_code: 1}, {attempt: 3, exit_code: 0}]}];
  const tries = select(block(card({id: "x", state: "abandoned", goal: "g", attempt: 3, body: {verify: {checks}}}), "verification"), "li.try").map(textOf);
  assert.deepEqual(tries, ["attempt 1: not run", "attempt 2: failed", "attempt 3: passed"]);
});

test("a try without an attempt number is numbered by its place", () => {
  const checks = [{template: "t", text: "a check", results: [{exit_code: 1, evidence: "no"}, {exit_code: 0, evidence: "yes"}]}];
  const tries = select(block(card({id: "x", state: "closed", goal: "g", attempt: 2, body: {verify: {checks}}}), "verification"), "li.try").map(textOf);
  assert.deepEqual(tries, ["attempt 1: failed, no", "attempt 2: passed, yes"]);
});

/* ================================================================ atom cards: J2's builders (atom/1) */
const BUILDER = {
  id: "j2-20261104-100004-7f3a:W-1.a1", schema: "atom/1", node_id: "s-1a2d9a66b0", task_id: "tsk_a1b2c3d4e5f6", state: "verify_failed", goal: "The hero section names the cafe",
  attempt: 2, ts_open: "2026-11-04T10:05:00Z", ts_closed: "2026-11-04T10:06:00Z", usage: {calls: 3, usd: 0.1, tokens_in: 900, tokens_out: 300},
  body: {schema: "atom/1", id: "W-1.a1", status: "failed", how: {kind: "ai", agent: "W-1 Hero builder"}, constraints: ["No stock photos", {text: "Keep it short"}],
    context: ["charter item 2", {text: "From workflow W-0"}], defined_output: ["The hero names the cafe", {kind: "heading", target: "Hero"}],
    verification: [{check: "heading-present", applies_to: "Hero", method: "heading-present: Hero", met: true, evidence: "found"},
      {check: "element-count", applies_to: "Hero", method: "element-count: h1", met: false, evidence: "0 found"},
      {check: "render", applies_to: "Hero", method: "render: browser", met: null, evidence: "no browser"}]},
};

test("an atom/1 body is read through its own names and its id is shown after the last colon", () => {
  const c = card(BUILDER);
  assert.equal(c.attrs["data-atom"], "j2-20261104-100004-7f3a:W-1.a1");
  assert.equal(textOf(one(c, "span.code")), "W-1.a1");
  assert.equal(textOf(one(c, "span.astate")), "VERIFY FAILED");
  assert.deepEqual(select(block(c, "constraints"), "li").map(textOf), ["No stock photos", "Keep it short"]);
  assert.deepEqual(select(block(c, "context"), "li").map(textOf), ["charter item 2", "From workflow W-0"]);
  assert.deepEqual(select(block(c, "expected_output"), "li").map(textOf), ["The hero names the cafe", "Hero"]);
  assert.equal(textOf(one(block(c, "how"), "div")), "AI builds it: W-1 Hero builder");
  const tries = select(block(c, "verification"), "li.try");
  assert.deepEqual(tries.map(textOf), ["attempt 2: passed, found", "attempt 2: failed, 0 found", "attempt 2: not run, no browser"]);
  assert.deepEqual(select(block(c, "verification"), "p.asent").map(textOf), ["heading-present", "element-count", "render"]);
});

test("an atom/1 builder done by code says so, and one with no agent says only AI builds it", () => {
  const how = body => textOf(one(block(card({...BUILDER, body: {...BUILDER.body, ...body}}), "how"), "div"));
  assert.equal(how({how: {kind: "code"}}), "code, no AI call");
  assert.equal(how({how: {kind: "ai"}}), "AI builds it");
  assert.equal(how({how: null}), "AI builds it");
});

test("a work-atom/0.3 body and an atom/1 body give the same card shape", () => {
  const shape = c => select(c, "div.ablock").map(b => b.attrs["data-block"]).join();
  assert.equal(shape(card(BUILDER)), shape(card(CLOSED)));
});

test("atomHtml takes the atom as the server sent it or as normalizeAtom made it", () => {
  assert.equal(atomHtml(normalizeAtom(FAILED)), atomHtml(FAILED));
  assert.equal(normalizeAtom(FAILED).view, "atom");
  const open = atomHtml(OPEN, {open: true});
  assert.equal("open" in one(dom(open), "details.atomcard").attrs, true);
  assert.equal("open" in one(dom(atomHtml(OPEN, {open: false})), "details.atomcard").attrs, false);
  assert.equal("open" in one(dom(atomHtml(OPEN)), "details.atomcard").attrs, false);
});

test("an atom of garbage still draws a well formed card", () => {
  [null, undefined, 4, "x", [], {}, {body: 5, usage: 5}, {id: null, state: null, body: {verify: {checks: [null, 5, {results: "no"}]}}}].forEach(raw => {
    const c = card(raw);
    assert.equal(c.tag, "details");
    assert.equal(c.attrs["data-state"], "unknown");
  });
});

test("atom words from the wire are escaped", () => {
  const bad = `<img src=x onerror="y"> & "q"`;
  const html = atomHtml({id: bad, state: "open", goal: bad, attempt: 1, body: {constraints: [{text: bad}], context: [bad], outputs: [bad], reason: bad, refusal: {message: bad},
    verify: {checks: [{template: bad, text: bad, results: [{attempt: 1, exit_code: 1, evidence: bad}]}]}}});
  assert.equal(html.includes("<img"), false);
  const c = one(dom(html), "details.atomcard");
  assert.equal(c.attrs["data-atom"], bad);
  assert.equal(textOf(one(c, "span.agoal")), bad);
});

/* ================================================================ atom cards: what the atom produced (D157) */
const resultOf = atom => block(card(atom), "result");
const inner = atom => resultOf(atom).children[1];                                       // the div inside the labelled block: the pill and the rows
const kinds = node => node.children.map(c => c.tag + (c.attrs.class ? "." + c.attrs.class.split(" ").join(".") : ""));
const withBody = (atom, body) => ({...atom, body: {...atom.body, ...body}});
const REPLY_TEXT = '{\n  "say": "hello",\n  "next": "Adaptation"\n}';
const DONE = [{verb: "do", name: "read your answer: carry on", form: "decision", ref: "chat"}, {verb: "do", name: "posted 1 message to you", form: "message", ref: "chat"}];

test("a closed atom's Result block says what the turn made, then offers the reply, above everything else", () => {
  const result = resultOf(CLOSED);
  const output = one(result, "div.aoutput");
  assert.equal(output.attrs["data-row"], "output");
  assert.equal(textOf(one(output, "b")), "Output");
  assert.deepEqual(select(output, "li").map(textOf), ["read your answer: carry on", "posted 1 message to you"]);
  assert.deepEqual(kinds(inner(CLOSED)), ["span.apill.st-closed", "div.arow.aoutput", "details.areply", "div.arow.aconcern", "div.arow.acost"]);
});

test("the reply is a fold, closed until the owner opens it, holding the text as it was printed", () => {
  const fold = one(resultOf(CLOSED), "details.areply");
  assert.equal("open" in fold.attrs, false);
  assert.equal(fold.attrs["data-row"], "reply");
  assert.equal(fold.attrs["data-key"], "reply-a-a810960e61-02");                         // so that SutraCtx.paint keeps it open across a redraw
  assert.equal(textOf(one(fold, "summary")), "The reply");
  const pre = one(fold, "pre.areplytext");
  assert.equal(textOf(pre), atomById("a-a810960e61-02").body.reply.text);
  assert.equal(textOf(pre).includes('\n  "clause"'), true);                              // new lines and indents stay
  assert.equal(select(fold, "span.empty").length, 0);                                    // not shortened: no note
});

test("a failed atom shows its reply behind the fold, above the Reason, and the reply says why the check failed", () => {
  const result = resultOf(FAILED);
  assert.deepEqual(kinds(inner(FAILED)), ["span.apill.st-verify_failed", "div.arow.aoutput", "details.areply", "div.arow.areason", "div.arow.acost"]);
  assert.deepEqual(select(one(result, "div.aoutput"), "li").map(textOf), ["the charter: Coffee shop landing page, 2 done-when items", "posted 1 message to Adaptation"]);
  const reply = JSON.parse(textOf(one(result, "pre.areplytext")));
  assert.equal(reply.goal.done_when.length, 2);                                          // the check said: fewer than 3 'done when' criteria
  assert.equal(textOf(one(result, "div.areason")), "Reason verify failed: charter-stamp: Charter rejected: fewer than 3 'done when' criteria.");
});

test("an open atom shows what its last failed try said", () => {
  const result = resultOf(OPEN);
  assert.deepEqual(select(one(result, "div.aoutput"), "li").map(textOf), ["said: I need one more answer."]);
  assert.equal(JSON.parse(textOf(one(result, "pre.areplytext"))).enough, false);
});

test("an atom with nothing recorded says so instead of showing nothing, and an atom that has only just opened says nothing yet", () => {
  const old = resultOf(ABANDONED);                                                       // stored before the layer recorded anything
  assert.equal(textOf(one(old, "div.aoutput")), "Output not recorded for this atom");
  assert.equal(select(old, "details.areply").length, 0);
  assert.equal(textOf(one(old, "div.areason")), "Reason replaced: a newer turn opened on this node");
  const fresh = clone(OPEN);
  fresh.attempt = 0;
  fresh.body = {...fresh.body, produced: [], reply: null};
  assert.equal(textOf(one(resultOf(fresh), "div.aoutput")), "Output nothing yet");
  assert.equal(textOf(one(resultOf({id: "x", state: "closed", goal: "g", body: {}}), "div.aoutput")), "Output not recorded for this atom");
  assert.equal(textOf(one(resultOf({id: "x", state: "open", attempt: 1, goal: "g", body: {}}), "div.aoutput")), "Output not recorded for this atom");
});

test("a refused atom never ran: it has no Output row and no reply", () => {
  const refused = resultOf(withBody(REFUSED, {produced: DONE, reply: {text: REPLY_TEXT, clipped: false}}));
  assert.equal(select(refused, "div.aoutput").length, 0);
  assert.equal(select(refused, "details.areply").length, 0);
  assert.deepEqual(kinds(refused.children[1]), ["span.apill.st-refused", "div.arow.acost"]);
});

test("a reply that was cut says how much of it is shown", () => {
  const cut = withBody(CLOSED, {reply: {text: "x".repeat(4000), clipped: true}});
  assert.equal(textOf(one(one(resultOf(cut), "details.areply"), "summary")), "The reply (shortened to its first 4,000 characters)");
  const odd = withBody(CLOSED, {reply: {text: "short", clipped: true}});
  assert.equal(textOf(one(one(resultOf(odd), "details.areply"), "summary")), "The reply (shortened to its first 5 characters)");
  assert.equal(textOf(one(one(resultOf(withBody(CLOSED, {reply: {text: "short", clipped: "yes"}})), "details.areply"), "summary")), "The reply");
});

test("the reply is read as printed: new lines kept, other control characters dropped, and never more than 20,000 characters", () => {
  const normalized = normalizeAtom(withBody(CLOSED, {reply: {text: "a\r\nb\rc\u0000d\u0007e\tf\u007f", clipped: false}}));
  assert.equal(normalized.reply.text, "a\nb\ncde\tf");
  const huge = normalizeAtom(withBody(CLOSED, {reply: {text: "y".repeat(30000), clipped: false}}));
  assert.equal(huge.reply.text.length, 20000);
  assert.equal(huge.reply.clipped, true);
  assert.equal(textOf(one(one(resultOf(withBody(CLOSED, {reply: {text: "y".repeat(30000)}})), "details.areply"), "summary")), "The reply (shortened to its first 20,000 characters)");
});

test("every word of the output and the reply is escaped, and the card stays well formed", () => {
  const bad = `<script>alert("x")</script> & 'q' </pre></details>`;
  const html = atomHtml(withBody(CLOSED, {produced: [{verb: "do", name: bad, form: bad, ref: bad}], reply: {text: bad + "\n  " + bad, clipped: true}}), {open: true});
  assert.equal(html.includes("<script"), false);
  assert.equal(html.includes("</pre></details>\n"), false);
  const c = one(dom(html), "details.atomcard");
  assert.equal(textOf(one(c, "div.aoutput li")), bad);                                   // a function turn's item shows its name only
  assert.equal(textOf(one(c, "pre.areplytext")), bad + "\n  " + bad);
  assert.equal(select(c, "details.areply").length, 1);
});

test("the output and the reply of malformed data are left out, never an error", () => {
  const draw = body => resultOf({id: "x", state: "closed", goal: "g", attempt: 1, body});
  assert.equal(textOf(one(draw({produced: "x", reply: 5}), "div.aoutput")), "Output not recorded for this atom");
  assert.equal(textOf(one(draw({produced: [null, 4, [], {}, {name: ""}, {name: {}}, {name: null}], reply: {text: 5}}), "div.aoutput")), "Output not recorded for this atom");
  assert.deepEqual(select(draw({produced: [{name: 7}, {name: "  two   words\n"}]}), "li").map(textOf), ["7", "two words"]);       // a number is its digits, words are on one line
  assert.equal(select(draw({reply: {text: 5}}), "details.areply").length, 0);
  assert.equal(select(draw({reply: "text"}), "details.areply").length, 0);
  assert.deepEqual(select(draw({produced: ["plain words", {name: "an object"}, null]}), "li").map(textOf), ["plain words", "an object"]);
  assert.equal(textOf(one(draw({reply: {text: ""}}), "pre.areplytext")), "");               // a reply with no text is still a reply
  [{}, {produced: {}, reply: []}].forEach(body => assert.equal(draw(body).tag, "div"));
});

test("a function atom's notes are the layer's own trace text and are not drawn", () => {
  assert.equal(select(resultOf(withBody(CLOSED, {notes: "declared bash, did llm"})), "div.anotes").length, 0);
});

const BUILT = {
  id: "j2-20261104-100004-7f3a:W-1.a1", schema: "atom/1", node_id: "s-1a2d9a66b0", state: "closed", goal: "The hero section names the cafe", attempt: 1,
  ts_open: "2026-11-04T10:05:00Z", ts_closed: "2026-11-04T10:06:00Z", usage: {calls: 2, usd: 0.04, tokens_in: 500, tokens_out: 200},
  body: {schema: "atom/1", id: "W-1.a1", status: "closed", how: {kind: "AI", agent: "W-1 Hero builder"}, verification: [{check: "exists", method: "heading-present: Hero", met: true, evidence: "found"}],
    output: [{verb: "make", name: "Hero section", form: "page", ref: "site/index.html#hero"}, {verb: "make", name: "Style sheet", form: "code", ref: "site/style.css"},
      {verb: "do", name: "Sent the booking", form: "send", ref: "W-3.a1:1"}], notes: "Built the hero section from the charter facts."},
};

test("a builder's Result block draws its output as name, form and where it lives in plain words, and its notes", () => {
  const result = resultOf(BUILT);
  assert.deepEqual(select(one(result, "div.aoutput"), "li").map(textOf), [
    "Hero section (page, site/index.html, section hero)", "Style sheet (code, site/style.css)", "Sent the booking (send, W-3.a1:1)"]);
  assert.equal(textOf(one(result, "div.anotes")), "Notes Built the hero section from the charter facts.");
  assert.equal(one(result, "div.anotes").attrs["data-row"], "notes");
  assert.deepEqual(kinds(inner(BUILT)), ["span.apill.st-closed", "div.arow.aoutput", "div.arow.anotes", "div.arow.acost"]);
  assert.equal(select(result, "details.areply").length, 0);                                // a builder has no turn reply
  assert.equal(select(resultOf(withBody(BUILT, {reply: {text: "x"}})), "details.areply").length, 0);
});

test("a builder with no output says so, and notes are shown without an output", () => {
  const none = withBody(BUILT, {output: [], notes: ""});
  assert.equal(textOf(one(resultOf(none), "div.aoutput")), "Output not recorded for this atom");
  assert.equal(select(resultOf(none), "div.anotes").length, 0);
  assert.equal(textOf(one(resultOf({...none, state: "open", attempt: 0}), "div.aoutput")), "Output nothing yet");
  assert.equal(textOf(one(resultOf(withBody(BUILT, {output: [], notes: "Nothing to build"})), "div.anotes")), "Notes Nothing to build");
  assert.equal(select(resultOf(withBody(BUILT, {output: [{verb: "make", name: "A", form: "", ref: ""}]})), "li span.empty").length, 0);   // no form and no ref: no brackets
});

test("every word of a builder's output and notes is escaped", () => {
  const bad = `<img src=x onerror="y"> & "q"`;
  const html = atomHtml(withBody(BUILT, {output: [{verb: "make", name: bad, form: bad, ref: bad + "#" + bad}], notes: bad}));
  assert.equal(html.includes("<img"), false);
  const c = one(dom(html), "details.atomcard");
  assert.equal(textOf(one(c, "div.aoutput li")), bad + " (" + bad + ", " + bad + ", section " + bad + ")");
  assert.equal(textOf(one(c, "div.anotes")), "Notes " + bad);
});

test("normalizeAtom reads what an atom produced, and the cards drawn from a read atom and a raw atom are the same", () => {
  const n = normalizeAtom(CLOSED);
  assert.deepEqual(n.made.map(m => [m.verb, m.name, m.form, m.ref]), [["do", "read your answer: carry on", "decision", "chat"], ["do", "posted 1 message to you", "message", "chat"]]);
  assert.equal(n.reply.clipped, false);
  assert.equal(n.notes, "");
  [CLOSED, FAILED, OPEN, ABANDONED, REFUSED, BUILT].forEach(atom => assert.equal(atomHtml(normalizeAtom(atom)), atomHtml(atom)));
  const bare = normalizeAtom({id: "x", state: "closed", body: {}});
  assert.deepEqual([bare.made, bare.reply, bare.notes], [[], null, ""]);
  const before = normalizeAtom(CLOSED);                                                   // an atom read by a copy of the view from before D157
  delete before.made;
  delete before.reply;
  delete before.notes;
  assert.equal(textOf(one(block(one(dom(atomHtml(before)), "details.atomcard"), "result"), "div.aoutput")), "Output not recorded for this atom");
});

/* ================================================================ the five functions of a team */
const WEB = GRAPH.nodes.find(n => n.id === "web");
const FAQ = GRAPH.nodes.find(n => n.id === "faq");

test("Functions of <Department>: five chips in the order of the design, each with the node it opens", () => {
  const doc = dom(functionsOf(WEB, GRAPH.nodes));
  const sec = one(doc, "section.fnfuncs");
  assert.equal(textOf(one(sec, "h4")), "Functions of Web");
  const chips = select(sec, "button.fnchip");
  assert.deepEqual(chips.map(c => c.attrs["data-fn"]), ["identity", "adaptation", "priority", "coordination", "audit"]);
  assert.deepEqual(chips.map(c => c.attrs["data-node"]), ["web.identity", "web.adaptation", "web.priority", "web.coordination", "web.audit"]);
  assert.deepEqual(chips.map(c => c.attrs["data-dept"]), ["web", "web", "web", "web", "web"]);
  assert.deepEqual(chips.map(c => c.attrs["data-act"]), ["fn", "fn", "fn", "fn", "fn"]);
  assert.equal(textOf(chips[0]), "Client Lead Identity waiting on you");
  assert.equal(textOf(chips[1]), "Strategist Adaptation running now");
  assert.equal(textOf(chips[2]), "Prioritiser Priority waiting on Strategist");
  assert.equal(textOf(chips[4]), "Quality Reviewer Audit blocked");
  assert.equal(chips[4].attrs.class, "fnchip st-fault");
});

test("the chips are found by team and function, never by reading an id", () => {
  const nodes = [
    {id: "x1", kind: "function", fn: "audit", dept_id: "web", status: "fault", meta: {}},
    {id: "x2", kind: "function", fn: "audit", dept_id: "content", status: "idle", meta: {}},
    {id: "Priority", kind: "function", label: "Priority", dept_id: "web", status: "running", meta: {}},
  ];
  const chips = select(dom(functionsOf({id: "web", label: "Web"}, nodes)), "button.fnchip");
  assert.equal(chips[4].attrs["data-node"], "x1");
  assert.equal(chips[2].attrs["data-node"], "Priority");
  assert.equal("data-node" in chips[0].attrs, false);
  assert.equal(chips[0].attrs.class, "fnchip");
});

test("a team whose function nodes are not in the graph still gets five chips", () => {
  const sec = one(dom(functionsOf(WEB, [])), "section.fnfuncs");
  assert.equal(select(sec, "button.fnchip").length, 5);
  select(sec, "button.fnchip").forEach(c => { assert.equal("data-node" in c.attrs, false); assert.equal(c.attrs["data-dept"], "web"); });
  assert.equal(select(dom(functionsOf(WEB)), "button.fnchip").length, 5);
});

test("the department may be given as an id, and its name is escaped", () => {
  assert.equal(textOf(one(dom(functionsOf("sales", [])), "h4")), "Functions of sales");
  assert.equal(textOf(one(dom(functionsOf({id: "a", label: "<b>Hi</b> & Co"}, [])), "h4")), "Functions of <b>Hi</b> & Co");
  assert.equal(textOf(one(dom(functionsOf(null, [])), "h4")), "Functions of this team");
});

/* ================================================================ the Details tab of the other kinds of node */
const detailOf = (node, extra = {}) => ({node, session: {}, atoms: [], usage_total: {calls: 0, usd: null, tokens_in: null, tokens_out: null}, task: null, archived_chats: [], ...extra});

test("a division's Details tab lists the five functions of its team and nothing of a function", () => {
  const doc = dom(nodeHtml(detailOf(FAQ), {nodes: GRAPH.nodes}));
  assert.equal(textOf(one(doc, "section.fnfuncs h4")), "Functions of Web");
  assert.equal(select(doc, "button.fnchip").length, 5);
  assert.equal(textOf(one(doc, "p.fnpart")), "FAQ is a division of Web.");
  ["goal", "task", "atoms", "constraints", "hands"].forEach(s => assert.equal(select(doc, `section[data-sec=${s}]`).length, 0, s));
  assert.equal(textOf(one(doc, "h4.fntitle")), "FAQ");
  assert.equal(textOf(one(doc, "span.nkind")), "division");
});

test("a team's Details tab has its head, what it works for, its functions and a link to the team page", () => {
  const live = detailOf(WEB, {task: {id: "tsk_1", title: "Coffee shop landing page", status: "running"}, usage_total: {calls: 3, usd: null, tokens_in: null, tokens_out: null}});
  const doc = dom(nodeHtml(live, {nodes: GRAPH.nodes}));
  assert.equal(textOf(one(doc, "span.nkind")), "team");
  assert.equal(textOf(one(doc, "p.fnwork")), "Working for: Coffee shop landing page (running)");
  assert.equal(textOf(one(doc, "p.fnusage")), "3 calls");
  assert.equal(select(doc, "button.fnchip").length, 5);
  const link = one(doc, "p.fnlinks button");
  assert.equal(link.attrs["data-href"], "/d/web/?view=simple");
  assert.equal(textOf(link), "Open the team page");
});

test("a step's Details tab links to its run once the run has ended", () => {
  const step = (status) => detailOf({id: "s-1a2d9a66b0", kind: "step", label: "Hero", status, dept_id: "web", meta: {run_id: "j2-20261104-100004-7f3a"}});
  const done = one(dom(nodeHtml(step("filed"), {nodes: []})), "p.fnlinks button");
  assert.equal(done.attrs["data-href"], "/d/web/?view=detail&run=j2-20261104-100004-7f3a");
  assert.equal(textOf(done), "Open the run");
  const live = one(dom(nodeHtml(step("running"), {nodes: []})), "p.fnlinks button");
  assert.equal(live.attrs["data-href"], "/d/web/?view=detail");
  assert.equal(textOf(live), "Open the team page");
});

test("a step that holds J2's builders lists them as work atoms", () => {
  const doc = dom(nodeHtml(detailOf({id: "s-1", kind: "step", label: "Hero", status: "done_unchecked", dept_id: "web", meta: {stats: {atoms_total: 1}}}, {atoms: [BUILDER]}), {nodes: []}));
  assert.equal(select(doc, "details.atomcard").length, 1);
  assert.equal(textOf(one(doc, "section[data-sec=atoms] h4")), "Work atoms (1)");
});

test("the root has a head and a sentence", () => {
  const doc = dom(nodeHtml(detailOf({id: "root", kind: "root", label: "Root", status: "running"}), {nodes: []}));
  assert.equal(textOf(one(doc, "span.nkind")), "root");
  assert.equal(textOf(one(doc, "p.empty")), "The root of the org chart. Teams and their work hang from it.");
});

test("a function node's Details tab is the drawer", () => {
  assert.equal(nodeHtml(DETAIL, {withAgent: true}), render(DETAIL, {withAgent: true}));
  assert.equal(nodeHtml(normalize(DETAIL), {}), render(DETAIL, {}));
});

test("a node the UI does not know is drawn as a step, never an error", () => {
  const doc = dom(nodeHtml(detailOf({id: "z", kind: "strange", label: "Z", status: "wat"}), {}));
  assert.equal(textOf(one(doc, "span.nkind")), "step");
  assert.equal(textOf(one(doc, "span.nstatus")), "idle");
  assert.equal(one(doc, "span.nstatus").attrs.class, "nstatus st-idle");
  assert.equal(nodeHtml(null, null).includes("undefined"), false);
});

/* ================================================================ words */
test("nodeWord is J2's wording: a function is 'blocked', a team has a 'fault'; a waiting function names who it waits on", () => {
  assert.equal(nodeWord("fault", "function"), "blocked");
  assert.equal(nodeWord("fault", "department"), "fault");
  assert.equal(nodeWord("waiting", "function", "priority"), "waiting on Prioritiser");
  assert.equal(nodeWord("waiting", "function", "you"), "waiting on you");
  assert.equal(nodeWord("waiting", "function", "W-3"), "waiting on W-3 Builder");
  assert.equal(nodeWord("waiting", "function", null), "waiting on someone");
  assert.equal(nodeWord("waiting", "department"), "waiting");
  assert.equal(nodeWord("filed", "function"), "filed and checked");
  assert.equal(nodeWord("filed", "step"), "filed");
  assert.equal(nodeWord("nonsense", "function"), "idle");
  assert.equal(nodeWord(undefined, "step"), "idle");
});

/* ================================================================ how the file loads */
test("the script loads as a classic script with one global and no other name, and as a module", () => {
  const sandbox = {};
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(FILE, "utf8"), sandbox);
  assert.deepEqual(Object.keys(sandbox), ["globalThis", "FnodeView"]);
  assert.equal(typeof sandbox.FnodeView.render, "function");
  assert.equal(sandbox.FnodeView.atomHtml(OPEN).includes("OPEN"), true);
  assert.deepEqual(Object.keys(FnodeView).sort(), Object.keys(sandbox.FnodeView).sort());
});

test("the source and the markup it writes are plain ASCII (the dot and the ellipsis are escapes)", () => {
  assert.equal(/[^\x00-\x7f]/.test(fs.readFileSync(FILE, "utf8")), false);
});
