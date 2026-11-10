"use strict";
// OutputPick (sutra_app/ui/static/js/output_pick.js): "What should we make?" on the start page of a team (J2 sync 4, D139). The page's own
// start select is gone; the port leaves a placeholder (#soutpick) and this module fills it. The api and the host are fakes.
// Run with: node --test tests/ui/js/output_pick.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = path.resolve(__dirname, "../../../sutra_app/ui/static/js/output_pick.js");
const OP = require(SOURCE);

const flush = () => new Promise(r => setImmediate(r));
const settings = (nextOutput, effective = "auto") => ({schema: "engine-settings/1", global: {}, effective: {output: effective}, next_run: nextOutput === undefined ? undefined : {output: nextOutput}});
const refused = (status, message = "") => Object.assign(new Error(message || "The app answered " + status + "."), {status, code: "http_" + status});

function fakeApi({get = settings("auto"), post = null} = {}) {
  const calls = [];
  return {calls,
    async get(p, query) { calls.push({method: "GET", path: p, query}); if (get instanceof Error) throw get; return get; },
    async post(p, body) { calls.push({method: "POST", path: p, body}); if (post instanceof Error) throw post; return post === null ? {ok: true, output: body.type} : post; }};
}

// A host that behaves like the element: writing its markup makes the select hold the option marked selected (and disabled when it says so), and the
// status line hold its words.
function fakeHost() {
  let markup = "";
  let held = "";
  const select = {id: "outsel", disabled: false};
  // a select holds only a value its list offers: any other value leaves it with none, as in a browser
  Object.defineProperty(select, "value", {get: () => held, set: v => { held = markup.includes('<option value="' + String(v) + '"') ? String(v) : ""; }});
  const note = {id: "soutnote", textContent: "", hidden: true};
  const listeners = {};
  const decode = s => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
  const host = {listeners, select, note, addEventListener(type, fn) { listeners[type] = fn; },
    querySelector(sel) { return markup === "" ? null : (sel === "#outsel" ? select : (sel === "#soutnote" ? note : null)); }};
  Object.defineProperty(host, "innerHTML", {get: () => markup, set: v => {
    markup = v;
    const chosen = /<option value="([^"]*)" selected>/.exec(v);
    held = chosen ? decode(chosen[1]) : "";
    select.disabled = /<select[^>]* disabled>/.test(v);
    const status = /<span class="soutnote"[^>]*?( hidden)?>([^<]*)<\/span>/.exec(v);
    note.hidden = !!(status && status[1]);
    note.textContent = status ? decode(status[2]) : "";
  }});
  return host;
}
const pick = async (host, value) => { host.select.value = value; host.listeners.change({target: host.select}); await flush(); };

// ---- pure parts --------------------------------------------------------------------------------------------------------------------------

test("the four things a team can make, in the order of the start page", () => {
  assert.deepEqual(OP.optionsFor("auto"), [["auto", "Let the team decide"], ["website", "Website"], ["prd", "PRD document"], ["project", "Project work"]]);
  assert.deepEqual(OP.optionsFor("").map(o => o[0]), ["auto", "website", "prd", "project"]);
  assert.deepEqual(OP.optionsFor(null).map(o => o[0]), ["auto", "website", "prd", "project"]);
  assert.equal(OP.QUESTION, "What should we make?");
});

test("a choice outside the four is added after them, so it is shown and not lost", () => {
  assert.deepEqual(OP.optionsFor("hld").slice(4), [["hld", "HLD document"]]);
  assert.deepEqual(OP.optionsFor("lld").slice(4), [["lld", "LLD document"]]);
  assert.deepEqual(OP.optionsFor("slides").slice(4), [["slides", "slides"]]);
  assert.equal(OP.optionsFor("hld").length, 5);
  assert.equal(OP.optionsFor("prd").length, 4);
  OP.optionsFor("x").push(["y", "y"]);
  assert.equal(OP.optionsFor("x").length, 5);                                      // the list is a copy: nothing a caller does changes the four
});

test("what the next run would make comes from next_run, else from the team's default, else it is auto", () => {
  assert.equal(OP.outputOf(settings("prd", "website")), "prd");
  assert.equal(OP.outputOf(settings(undefined, "website")), "website");
  assert.equal(OP.outputOf({next_run: {output: ""}, effective: {output: "project"}}), "project");
  assert.equal(OP.outputOf({effective: {}}), "auto");
  assert.equal(OP.outputOf({}), "auto");
  assert.equal(OP.outputOf(null), "auto");
  assert.equal(OP.outputOf({next_run: {output: "  hld "}}), "hld");
});

test("the markup is a label tied to a select, with the choice in force marked and the status line empty", () => {
  const html = OP.html({output: "prd"});
  assert.match(html, /^<label for="outsel">What should we make\?<\/label><select id="outsel" class="outsel" aria-describedby="soutnote">/);
  assert.match(html, /<option value="auto">Let the team decide<\/option>/);
  assert.match(html, /<option value="prd" selected>PRD document<\/option>/);
  assert.equal((html.match(/ selected>/g) || []).length, 1);
  assert.match(html, /<span class="soutnote" id="soutnote" role="status" hidden><\/span>$/);
  assert.match(OP.html({}), /<option value="auto" selected>/);
  assert.match(OP.html({output: "hld"}), /<option value="hld" selected>HLD document<\/option>/);
});

test("a locked select is disabled and a note is said in the status line", () => {
  const html = OP.html({output: "auto", locked: true, note: OP.STARTED});
  assert.match(html, /<select id="outsel" class="outsel" aria-describedby="soutnote" disabled>/);
  assert.match(html, /<span class="soutnote" id="soutnote" role="status">The team has started; choose before the first message\.<\/span>/);
  assert.equal(OP.STARTED, "The team has started; choose before the first message.");
});

test("every word from the wire is escaped", () => {
  const evil = '<img src=x onerror="alert(1)">';
  const html = OP.html({output: evil, note: evil});
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /value="&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;"/);
});

// ---- the placeholder ----------------------------------------------------------------------------------------------------------------------

test("it reads the team's settings and shows what the next run would make, so a reload shows the pick", async () => {
  const api = fakeApi({get: settings("prd", "auto")});
  const host = fakeHost();
  const handle = OP.mount(host, {api, dept: "web"});
  assert.equal(await handle.first, true);
  assert.deepEqual(api.calls, [{method: "GET", path: "/api/engine/settings", query: {dept: "web"}}]);
  assert.equal(host.select.value, "prd");
  assert.match(host.innerHTML, /<label for="outsel">What should we make\?<\/label>/);
  assert.deepEqual(handle.state(), {output: "prd", locked: false, note: "", busy: false, loaded: true});
});

test("a server that does not say what the next run makes shows the team's default", async () => {
  const host = fakeHost();
  await OP.mount(host, {api: fakeApi({get: settings(undefined, "website")}), dept: "web"}).first;
  assert.equal(host.select.value, "website");
  const unnamed = fakeHost();
  await OP.mount(unnamed, {api: fakeApi({get: {}}), dept: "web"}).first;
  assert.equal(unnamed.select.value, "auto");
});

test("settings that cannot be read leave the placeholder empty, and nothing is thrown", async () => {
  const quiet = console.error;
  console.error = () => {};
  try {
    const host = fakeHost();
    const handle = OP.mount(host, {api: fakeApi({get: refused(500)}), dept: "web"});
    assert.equal(await handle.first, false);
    assert.equal(host.innerHTML, "");
    assert.equal(handle.state().loaded, false);
  } finally {
    console.error = quiet;
  }
});

test("a change is one POST /api/output with the type and the team, and the answer's output is what is shown", async () => {
  const api = fakeApi();
  const host = fakeHost();
  const handle = OP.mount(host, {api, dept: "web"});
  await handle.first;
  await pick(host, "prd");
  assert.deepEqual(api.calls[1], {method: "POST", path: "/api/output?dept=web", body: {type: "prd"}});
  assert.equal(host.select.value, "prd");
  assert.equal(host.select.disabled, false);
  assert.equal(host.note.hidden, true);
  assert.deepEqual(handle.state(), {output: "prd", locked: false, note: "", busy: false, loaded: true});
  const normalised = fakeApi({post: {ok: true, output: "website"}});
  const h2 = fakeHost();
  const m2 = OP.mount(h2, {api: normalised, dept: "web"});
  await m2.first;
  await pick(h2, "prd");                                                          // the engine answers with the output it will make, and the select says so
  assert.equal(m2.state().output, "website");
  assert.equal(h2.select.value, "website");
});

test("the team's name is encoded in the request", async () => {
  const api = fakeApi();
  const host = fakeHost();
  const handle = OP.mount(host, {api, dept: "we b/1"});
  await handle.first;
  await pick(host, "project");
  assert.equal(api.calls[1].path, "/api/output?dept=we%20b%2F1");
  assert.deepEqual(api.calls[0].query, {dept: "we b/1"});
});

test("a team that has started refuses the choice: the old one is back, the select is locked and the sentence says why", async () => {
  const api = fakeApi({get: settings("website"), post: refused(409)});
  const host = fakeHost();
  const handle = OP.mount(host, {api, dept: "web"});
  await handle.first;
  await pick(host, "prd");
  assert.equal(host.select.value, "website");
  assert.equal(host.select.disabled, true);
  assert.equal(host.note.hidden, false);
  assert.equal(host.note.textContent, "The team has started; choose before the first message.");
  assert.deepEqual(handle.state(), {output: "website", locked: true, note: OP.STARTED, busy: false, loaded: true});
  await pick(host, "project");
  assert.equal(api.calls.filter(c => c.method === "POST").length, 1);              // a locked select sends nothing more
});

test("any other refusal puts the old choice back and says what went wrong; the select stays open for another try", async () => {
  const api = fakeApi({post: refused(500)});
  const host = fakeHost();
  const handle = OP.mount(host, {api, dept: "web"});
  await handle.first;
  await pick(host, "prd");
  assert.equal(host.select.value, "auto");
  assert.equal(host.select.disabled, false);
  assert.equal(host.note.textContent, "The app answered 500.");
  assert.equal(handle.state().locked, false);
  const silent = fakeApi({post: Object.assign(new Error(""), {status: 0})});
  const h2 = fakeHost();
  const m2 = OP.mount(h2, {api: silent, dept: "web"});
  await m2.first;
  await pick(h2, "prd");
  assert.equal(h2.note.textContent, "That did not work. Try again.");
});

test("a pick that is already the choice, or one made while a request is out, sends nothing", async () => {
  const api = fakeApi();
  const host = fakeHost();
  const handle = OP.mount(host, {api, dept: "web"});
  await handle.first;
  await pick(host, "auto");
  assert.equal(api.calls.length, 1);
  let release;
  const slow = fakeApi();
  slow.post = (p, body) => { slow.calls.push({method: "POST", path: p, body}); return new Promise(r => { release = () => r({ok: true, output: body.type}); }); };
  const h2 = fakeHost();
  const m2 = OP.mount(h2, {api: slow, dept: "web"});
  await m2.first;
  const first = m2.choose("prd");
  assert.equal(h2.select.disabled, true);                                          // the select waits for the answer
  assert.equal(await m2.choose("website"), false);
  release();
  assert.equal(await first, true);
  assert.equal(slow.calls.filter(c => c.method === "POST").length, 1);
  assert.equal(h2.select.disabled, false);
});

test("a choice outside the four that the engine answers with is shown, not lost", async () => {
  const host = fakeHost();
  const handle = OP.mount(host, {api: fakeApi({post: {ok: true, output: "hld"}}), dept: "web"});
  await handle.first;
  await pick(host, "prd");
  assert.equal(host.select.value, "hld");
  assert.match(host.innerHTML, /<option value="hld" selected>HLD document<\/option>/);
});

test("a destroyed placeholder paints nothing more", async () => {
  const host = fakeHost();
  const handle = OP.mount(host, {api: fakeApi(), dept: "web"});
  handle.destroy();
  assert.equal(await handle.first, false);
  assert.equal(host.innerHTML, "");
});

// ---- start --------------------------------------------------------------------------------------------------------------------------------

function withPage({boot, host, api}, fn) {
  const savedDoc = globalThis.document;
  const savedCtx = globalThis.SutraCtx;
  globalThis.document = host === undefined ? undefined : {getElementById: id => (id === "soutpick" ? host : null)};
  globalThis.SutraCtx = {boot, api: api || fakeApi(), dept: "web"};
  try {
    return fn();
  } finally {
    if (savedDoc === undefined) delete globalThis.document; else globalThis.document = savedDoc;
    if (savedCtx === undefined) delete globalThis.SutraCtx; else globalThis.SutraCtx = savedCtx;
  }
}

test("start builds nothing for Home, for an archived team, or without the placeholder", () => {
  assert.equal(withPage({boot: {page: "home"}, host: fakeHost()}, () => OP.start()), null);
  assert.equal(withPage({boot: {page: "dept", archived: true}, host: fakeHost()}, () => OP.start()), null);
  assert.equal(withPage({boot: {page: "dept"}, host: null}, () => OP.start()), null);
  assert.equal(withPage({boot: {page: "dept"}, host: undefined}, () => OP.start()), null);
  assert.equal(withPage({boot: null, host: fakeHost()}, () => OP.start()), null);
});

test("start mounts the placeholder of a team page once", async () => {
  const host = fakeHost();
  const api = fakeApi({get: settings("project")});
  const handle = withPage({boot: {page: "dept", archived: false}, host, api}, () => OP.start());
  assert.ok(handle);
  await handle.first;
  assert.equal(host.select.value, "project");
  assert.equal(withPage({boot: {page: "dept"}, host: fakeHost()}, () => OP.start()), handle);          // a second start is the same mount
});

test("the page wiring: a classic script with one global that starts itself on a team page and uses no forbidden API", () => {
  const source = fs.readFileSync(SOURCE, "utf8");
  assert.match(source, /root\.OutputPick = OutputPick/);
  assert.match(source, /page === "dept"/);
  assert.match(source, /ctx\.boot\.archived === true/);
  assert.doesNotMatch(source, /\beval\(|new Function|document\.cookie|XMLHttpRequest|EventSource|localStorage|setInterval/);
});
