"use strict";
// TeamFind (sutra_app/ui/static/js/team_find.js): the rail's search box (gap package chart-insight): when a query is a search, the results in words (the
// team's address, why it matched), the second group of chat messages, which boxes of the Org chart stay lit, the debounced box, and every word escaped.
// Run with: node --test tests/ui/js/team_find.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const TeamFind = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/team_find.js"));
const {request, html, hits, dimming, dimCss, mount, DEBOUNCE_MS} = TeamFind;

const ROW = (over = {}) => Object.assign({team_id: "bakery-site", team_name: "Bakery site", node_id: "menu", kind: "division", address: "Bakery site > Menu",
  matched_on: ["purpose"], snippet: "Cakes and bread we bake"}, over);
const MSG = (over = {}) => Object.assign({session_id: "cs_0123456789ab", message_id: 7, title: "Menu", snippet: "send the cake list", at: "2026-11-04T10:00:00Z", archived: false}, over);
const wait = () => new Promise(resolve => setImmediate(resolve));

test("a query is a search from two characters in one word, and is trimmed and cut", () => {
  ["", " ", "a", " a ", "a b", null, undefined, 5].forEach(q => assert.equal(request(q), null, JSON.stringify(q)));
  assert.deepEqual(request("  pricing   page "), {path: "/api/find", query: {q: "pricing page"}});
  assert.deepEqual(request("a bc"), {path: "/api/find", query: {q: "a bc"}});
  assert.equal(request("x".repeat(500)).query.q.length, 200);
});

test("the results name each team by its address, say why it matched and link to its page", () => {
  const out = html({teams: [ROW(), ROW({team_id: "florist", team_name: "Florist", node_id: "florist", kind: "department", address: "Florist", matched_on: ["name", "task"], snippet: ""})], messages: []});
  assert.match(out, /^<p class="rfhead">Found in teams<\/p>/);
  assert.match(out, /<a class="railteam rfound" href="\/d\/bakery-site\/" data-dept="bakery-site" data-node="menu"><span class="rtname">Bakery site &gt; Menu<\/span><span class="rtstat">matched on purpose · Cakes and bread we bake<\/span><\/a>/);
  assert.match(out, /<span class="rtstat">matched on name, a task<\/span>/);
  assert.doesNotMatch(out, /Found in chats/);
});

test("the second group is the chat search's messages, a button each", () => {
  const out = html({teams: [], messages: [MSG(), MSG({session_id: "cs_ba9876543210", title: "Old", archived: true})]});
  assert.doesNotMatch(out, /Found in teams/);
  assert.match(out, /<p class="rfhead">Found in chats<\/p><button type="button" class="railteam rfmsg" data-act="find-chat" data-sid="cs_0123456789ab"><span class="rtname">Menu<\/span><span class="rtstat">send the cake list<\/span><\/button>/);
  assert.match(out, /send the cake list · older chat|<span class="rtstat"> · older chat|older chat/);
});

test("nothing found says so once, a cut list says to narrow it, and a non-answer draws nothing", () => {
  assert.equal(html({teams: [], messages: []}), '<p class="railnone">Nothing found.</p>');
  assert.equal(html({}), '<p class="railnone">Nothing found.</p>');
  assert.match(html({teams: [ROW()], messages: [], truncated: true}), /<p class="railnone">More match: add a word to narrow it\.<\/p>/);
  [null, undefined, "x", 3, []].forEach(v => assert.equal(html(v), ""));
});

test("every word of the wire is escaped and an id that is not an id never reaches a link or a button", () => {
  const bad = `<script>alert("x")</script> & 'q'`;
  const out = html({teams: [ROW({team_id: '"><img src=x>', address: bad, snippet: bad, matched_on: [bad, "purpose"]}), ROW({address: bad, snippet: bad})],
    messages: [MSG({session_id: '"><img src=x>', title: bad, snippet: bad}), MSG({title: bad, snippet: bad})]});
  assert.equal(out.includes("<script"), false);
  assert.equal(out.includes("<img"), false);
  assert.doesNotMatch(out, /href="\/d\/%22/);
  assert.equal((out.match(/data-act="find-chat"/g) || []).length, 1, "only the real session id is a button");
});

const NODES = [{id: "root", parent: null}, {id: "bakery", parent: "root"}, {id: "menu", parent: "bakery"}, {id: "cakes", parent: "menu"}, {id: "florist", parent: "root"}];

test("the hits stay lit and the boxes above them stay in view", () => {
  assert.deepEqual(hits([ROW({node_id: "cakes"}), ROW({node_id: "cakes"}), ROW({node_id: "florist"}), ROW({node_id: "bad id"})]), ["cakes", "florist"]);
  assert.deepEqual(dimming([ROW({node_id: "cakes"}), ROW({node_id: "florist"})], NODES), {hits: ["cakes", "florist"], ancestors: ["menu", "bakery", "root"]});
  assert.deepEqual(dimming([ROW({node_id: "menu"}), ROW({node_id: "cakes"})], NODES).ancestors, ["bakery", "root"]);       // a hit is never also an ancestor
  assert.deepEqual(dimming([], NODES), {hits: [], ancestors: []});
  assert.deepEqual(dimming([ROW({node_id: "a"})], [{id: "a", parent: "b"}, {id: "b", parent: "a"}]), {hits: ["a"], ancestors: ["b"]});          // a loop ends
});

test("a hit the chart no longer holds (merged away since the search) lights nothing and so never dims the whole chart", () => {
  const gone = dimming([ROW({node_id: "leads"})], NODES);
  assert.deepEqual(gone, {hits: [], ancestors: []});
  assert.equal(dimCss(".ocpane[data-find]", gone.hits, gone.ancestors), "", "no hit, no rule: every box keeps its own look");
  assert.deepEqual(dimming([ROW({node_id: "leads"}), ROW({node_id: "cakes"})], NODES), {hits: ["cakes"], ancestors: ["menu", "bakery", "root"]});
  assert.deepEqual(dimming([ROW({node_id: "cakes"})], null), {hits: [], ancestors: []});
});

test("the style keeps hits lit, ancestors in view and dims the rest; nothing is written for a bad scope or no hit", () => {
  const css = dimCss(".ocpane[data-find]", ["cakes"], ["menu", "bakery"]);
  assert.match(css, /^\.ocpane\[data-find\] g\.wnode\{opacity:\.22\}\.ocpane\[data-find\] path\.wedge\{opacity:\.15\}/);
  assert.match(css, /\.ocpane\[data-find\] g\.wnode\[data-id="menu"\],\.ocpane\[data-find\] g\.wnode\[data-id="bakery"\]\{opacity:\.7\}/);
  assert.ok(css.endsWith('.ocpane[data-find] g.wnode[data-id="cakes"]{opacity:1}.ocpane[data-find] path.wedge[data-to="cakes"]{opacity:.9}'), "the hits come last so they win");
  assert.equal(dimCss(".ocpane[data-find]", [], ["menu"]), "");
  assert.equal(dimCss("body{x", ["cakes"], []), "");
  assert.equal(dimCss(".a", ['x"] , *{display:none} [y="'], []), "");
  assert.doesNotMatch(dimCss(".a", ["ok", 'x"]{}'], ['y"]{}']), /\{\}|display/);
});

/* ---------------------------------------------------------------- the box */
function rig(answer, extra = {}) {
  const handlers = {input: [], keydown: [], click: []};
  const input = {value: "", addEventListener: (type, fn) => handlers.input && (handlers[type] = (handlers[type] || []).concat(fn))};
  const out = {innerHTML: "", hidden: true, addEventListener: (type, fn) => (handlers["out:" + type] = (handlers["out:" + type] || []).concat(fn))};
  const calls = [];
  const queue = [];
  const timers = {setTimeout: (fn, ms) => { queue.push({fn, ms}); return queue.length; }, clearTimeout: id => { if (queue[id - 1]) queue[id - 1].fn = null; }};
  const told = [];
  const opened = [];
  const api = {get: (p, q) => { calls.push([p, q]); return typeof answer === "function" ? answer(q) : Promise.resolve(answer); }};
  const box = mount(Object.assign({input, out, api, timers, onChange: rows => told.push(rows), onOpenChat: sid => opened.push(sid)}, extra));
  const type = value => { input.value = value; handlers.input.forEach(fn => fn()); };
  const key = (k, extraEvent = {}) => { const e = Object.assign({key: k, preventDefault() {}, stopPropagation() { e.stopped = true; }}, extraEvent); handlers.keydown.forEach(fn => fn(e)); return e; };
  const flush = () => { queue.splice(0).forEach(t => t.fn && t.fn()); return wait(); };
  return {box, input, out, calls, queue, told, opened, type, key, flush, handlers};
}

test("typing waits 220 ms, then one read answers and the rows go to onChange", async () => {
  const r = rig({teams: [ROW()], messages: [], counts: {}, truncated: false});
  r.type("ca");
  r.type("cak");
  r.type("cake");
  assert.equal(DEBOUNCE_MS, 220);
  assert.deepEqual(r.queue.filter(t => t.fn).map(t => t.ms), [220], "a burst of keys leaves one timer");
  assert.equal(r.calls.length, 0);
  await r.flush();
  assert.deepEqual(r.calls, [["/api/find", {q: "cake"}]]);
  assert.match(r.out.innerHTML, /Found in teams/);
  assert.equal(r.out.hidden, false);
  assert.deepEqual(r.told, [[ROW()]]);
});

test("a query that is not a search clears the box and tells onChange null, at once", async () => {
  const r = rig({teams: [ROW()], messages: []});
  r.type("cake");
  await r.flush();
  r.type("c");
  assert.equal(r.out.innerHTML, "");
  assert.equal(r.out.hidden, true);
  assert.deepEqual(r.told.at(-1), null);
  assert.equal(r.queue.filter(t => t.fn).length, 0, "no read is waiting for it");
});

test("an older answer never replaces a newer one", async () => {
  const pending = [];
  const r = rig(q => new Promise(resolve => pending.push(() => resolve({teams: [ROW({address: q.q})], messages: []}))));
  r.box.run("first");
  r.box.run("second");
  await wait();
  pending[1]();
  await wait();
  pending[0]();
  await wait();
  assert.match(r.out.innerHTML, /second/);
  assert.doesNotMatch(r.out.innerHTML, /first/);
});

test("a failed read says the search is not available and clears the lit boxes", async () => {
  const r = rig(() => Promise.reject(new Error("down")));
  await r.box.run("cake");
  assert.equal(r.out.innerHTML, '<p class="railnone">Search is not available right now.</p>');
  assert.deepEqual(r.told, [null]);
});

test("Enter reads at once, Escape clears the box and does not travel on, and Escape in an empty box is left alone", async () => {
  const r = rig({teams: [ROW()], messages: []});
  r.input.value = "cake";
  r.key("Enter");
  await wait();
  assert.equal(r.calls.length, 1);
  const esc = r.key("Escape");
  assert.equal(esc.stopped, true);
  assert.equal(r.input.value, "");
  assert.equal(r.out.innerHTML, "");
  assert.equal(r.key("Escape").stopped, undefined);
});

test("a click on a chat result hands its session to onOpenChat", () => {
  const r = rig({teams: [], messages: [MSG()]});
  const button = {getAttribute: name => (name === "data-sid" ? "cs_0123456789ab" : null)};
  r.handlers["out:click"].forEach(fn => fn({target: {closest: sel => (sel === "[data-act='find-chat']" ? button : null)}}));
  r.handlers["out:click"].forEach(fn => fn({target: {closest: () => null}}));
  assert.deepEqual(r.opened, ["cs_0123456789ab"]);
});

test("destroy drops a waiting read and a late answer", async () => {
  const r = rig({teams: [ROW()], messages: []});
  r.type("cake");
  r.box.destroy();
  await r.flush();
  assert.equal(r.calls.length, 0);
  const late = rig({teams: [ROW()], messages: []});
  const running = late.box.run("cake");
  late.box.destroy();
  await running;
  assert.equal(late.out.innerHTML, "");
  assert.throws(() => mount({}), TypeError);
});
