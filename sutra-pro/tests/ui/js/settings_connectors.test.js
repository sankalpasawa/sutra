"use strict";
// SettingsView, the Connectors group (sutra_app/ui/static/js/settings_view.js): a row per provider from GET /api/health with Test, Codex's Sign in
// (the link and the one-time code, polled until signed_in, failed or expired, Cancel sends DELETE), no control to pin a chat, and the rows that
// follow connector.health, connector.switch and connector.mode.
// docs/design/ui.md sections 6.6, 8 and 10; S1-contracts-08; S3-web-06.
// Run with: node --test tests/ui/js/settings_connectors.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SettingsView = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/settings_view.js"));
const {connectorsHtml, signInState, testConnector, signIn, watchHealth, testLine, HEALTH_EVENTS} = SettingsView;
const fixture = name => JSON.parse(fs.readFileSync(path.resolve(__dirname, "../fixtures", name), "utf8"));
const clone = value => JSON.parse(JSON.stringify(value));

const HEALTH = fixture("health.json");        // Claude ready, Codex not signed in
const CONNECTORS = fixture("connectors.json");
const START = CONNECTORS.sign_in.start;       // {id, url, code, expires_in}
const SEQUENCES = CONNECTORS.sign_in.sequences;

// The markup of one provider's row.
function row(html, provider) {
  const start = html.indexOf(`<div class="setconn" data-provider="${provider}"`);
  assert.ok(start >= 0, `no row for ${provider}`);
  const next = html.indexOf('<div class="setconn"', start + 10);
  return html.slice(start, next < 0 ? html.length : next);
}

function fakeApi(answers) {
  const calls = [];
  const run = (method, p, body) => {
    calls.push({method, path: p, body});
    if (calls.length > 300) return Promise.reject(new Error("runaway: more than 300 calls"));
    let answer = answers[method + " " + p];
    if (Array.isArray(answer)) answer = answer.length > 1 ? answer.shift() : answer[0];     // a sequence of answers, the last one repeats
    if (answer instanceof Error) return Promise.reject(answer);
    return Promise.resolve(typeof answer === "function" ? answer(body) : answer);
  };
  return {calls, get: p => run("GET", p), post: (p, b) => run("POST", p, b), put: (p, b) => run("PUT", p, b), del: p => run("DELETE", p)};
}
class ApiError extends Error {
  constructor(message, code, status) { super(message); this.name = "ApiError"; this.code = code || "error"; this.status = status || 500; this.details = {}; }
}
const POLL = `/api/connectors/codex/sign-in/${START.id}`;
// A wait that lets the event loop breathe, so a flow that never stops fails the test (by its guard below) instead of hanging the run.
const instantly = () => new Promise(resolve => setImmediate(resolve));

/* ---------------------------------------------------------------- the rows */
test("there is a row for Claude and then one for Codex, each with its state in words", () => {
  const html = connectorsHtml(HEALTH, {});
  assert.match(html, /<section class="setgrp" data-group="connectors"/);
  assert.ok(html.indexOf('data-provider="claude"') < html.indexOf('data-provider="codex"'));
  assert.match(row(html, "claude"), /<b>Claude<\/b><span class="setchip st-ok">Ready<\/span>/);
  assert.match(row(html, "claude"), /Signed in with claude\.ai/);
  assert.match(row(html, "claude"), /version 2\.1\.308/);
  assert.match(row(html, "codex"), /<b>Codex<\/b><span class="setchip st-signed_out">Not signed in<\/span>/);
  assert.match(row(html, "codex"), /Not signed in\. Use Sign in\./);
});

test("a provider the CLI is not installed for says so", () => {
  const health = clone(HEALTH);
  health.connectors.codex.installed = false;
  assert.match(row(connectorsHtml(health, {}), "codex"), /st-missing">Not installed</);
});

test("any other state is shown in words, and an extra provider comes after the two", () => {
  const health = clone(HEALTH);
  health.connectors.claude.health = {state: "cooling_down", until: 1793748600, reason: "quota"};
  health.connectors.zeta = {installed: true, signed_in: true, detail: "Stub", health: {state: "ok"}};
  const html = connectorsHtml(health, {});
  assert.match(row(html, "claude"), /st-cooling_down">cooling down</);
  assert.match(row(html, "claude"), /quota/);
  assert.ok(html.indexOf('data-provider="codex"') < html.indexOf('data-provider="zeta"'));
  assert.match(row(html, "zeta"), /<b>zeta<\/b>/);
});

test("a provider out of quota, cooling down or paused is never shown as Ready (the server's health object)", () => {
  const cases = [["quota", "Out of quota"], ["cooldown", "Cooling down"], ["breaker", "Paused after errors"]];
  for (const [state, word] of cases) {
    const health = clone(HEALTH);
    health.connectors.claude.health = {state, until: 1793748600, reason: "usage limit reached"};
    const html = row(connectorsHtml(health, {}), "claude");
    assert.match(html, new RegExp(`<span class="setchip st-${state}">${word}</span>`), state);
    assert.equal(html.includes(">Ready<"), false, state);
  }
});

// a clock that does not depend on the machine's zone: UTC fields (plan_meter.js `when`)
const utc = ms => { const d = new Date(ms); return {day: d.getUTCDay(), date: d.getUTCDate(), month: d.getUTCMonth(), hh: d.getUTCHours(), mm: d.getUTCMinutes()}; };

test("a signed-in row names the plan and how it is billed, and draws a meter per usage window (GAP-providers)", () => {
  const nowMs = Date.UTC(2026, 10, 6, 12, 0, 0);
  const claude = row(connectorsHtml(HEALTH, {nowMs, when: utc}), "claude");
  assert.match(claude, /<p class="setplan">Claude Max, counted against your plan, not billed per call<\/p><div class="pmeter"/);
  assert.match(claude, /data-key="five_hour" data-sev="ok"><span class="pml">5-hour<\/span><span class="pmp">62%<\/span>/);
  assert.match(claude, /data-key="seven_day" data-sev="warn"><span class="pml">Weekly<\/span><span class="pmp">81%<\/span>/);
  assert.match(claude, /<p class="pmasof">as of /);
  const codex = row(connectorsHtml(HEALTH, {nowMs, when: utc}), "codex");
  assert.equal(codex.includes("pmeter"), false);                                         // no quota signal: no meter, never an empty bar
  assert.equal(codex.includes("setplan"), false);
});

test("a window whose reset passed reads reset, and a blocked provider says until when", () => {
  const health = clone(HEALTH);
  const nowMs = health.connectors.claude.quota.windows[0].resets_at * 1000 + 60000;
  health.connectors.claude.health = {state: "quota", until: nowMs / 1000 + 3600, reason: "usage limit reached"};
  const html = row(connectorsHtml(health, {nowMs, when: utc}), "claude");
  assert.match(html, /data-key="five_hour" data-sev="reset"><span class="pml">5-hour<\/span><span class="pmp">reset<\/span>/);
  assert.equal(/5-hour<\/span><span class="pmp">62%/.test(html), false);
  assert.match(html, /usage limit reached, until \d\d:\d\d/);
  assert.match(html, /st-quota">Out of quota</);
});

test("a provider that is not installed has no plan line and no meter", () => {
  const health = clone(HEALTH);
  health.connectors.claude.installed = false;
  const html = row(connectorsHtml(health, {}), "claude");
  assert.equal(html.includes("pmeter") || html.includes("setplan"), false);
});

test("both rows have Test and only the Codex row has Sign in", () => {
  const html = connectorsHtml(HEALTH, {});
  assert.match(row(html, "claude"), /data-act="test" data-provider="claude"/);
  assert.match(row(html, "codex"), /data-act="test" data-provider="codex"/);
  assert.equal(row(html, "claude").includes('data-act="signin"'), false);
  assert.match(row(html, "codex"), /data-act="signin"/);
  assert.equal((html.match(/data-act="signin"/g) || []).length, 1);
});

test("there is no control to pin a chat to a provider", () => {
  const html = connectorsHtml(HEALTH, {signin: signInState(null, START)});
  assert.equal(/\bpin\b|data-act="pin"|<select/i.test(html), false);
});

test("before the health has loaded the group says so, and still has its title", () => {
  const html = connectorsHtml(null, {});
  assert.match(html, /data-group="connectors"/);
  assert.match(html, /not loaded yet/);
  assert.equal(html.includes("data-act"), false);
});

test("words from the server are written as text, never as markup", () => {
  const health = clone(HEALTH);
  health.connectors.claude.detail = '<img src=x onerror="alert(1)">';
  const html = connectorsHtml(health, {test: {claude: {step: "error", message: "<b>no</b>"}}});
  assert.equal(html.includes("<img"), false);
  assert.equal(html.includes("<b>no</b>"), false);
  assert.match(html, /&lt;b&gt;no&lt;\/b&gt;/);
});

/* ---------------------------------------------------------------- Test */
test("a running test disables its button; a pass shows the seconds; a failure shows the server's sentence", () => {
  const running = row(connectorsHtml(HEALTH, {test: {claude: {step: "running"}}}), "claude");
  assert.match(running, /data-act="test" data-provider="claude" disabled>/);
  assert.match(running, /Testing/);
  const passed = row(connectorsHtml(HEALTH, {test: {claude: {step: "ok", seconds: 3.2}}}), "claude");
  assert.match(passed, /Worked in 3\.2 s/);
  assert.equal(passed.includes("disabled"), false);
  const failed = row(connectorsHtml(HEALTH, {test: {codex: {step: "error", message: "Codex is not signed in. Use Sign in on the Codex row."}}}), "codex");
  assert.match(failed, /Codex is not signed in\. Use Sign in on the Codex row\./);
  assert.equal(row(connectorsHtml(HEALTH, {test: {codex: {step: "error", message: "x"}}}), "claude").includes(">x<"), false);   // only its own row
});

test("testLine words", () => {
  assert.equal(testLine({step: "ok", seconds: 4.8}), "Worked in 4.8 s");
  assert.equal(testLine({step: "ok", seconds: 12}), "Worked in 12.0 s");
  assert.equal(testLine({step: "ok"}), "Worked");
  assert.equal(testLine({step: "error", message: ""}), "The test did not pass.");
  assert.equal(testLine({step: "idle"}), "");
  assert.equal(testLine(null), "");
});

test("Test posts to the provider's test path and gives the seconds", async () => {
  const api = fakeApi({"POST /api/connectors/claude/test": CONNECTORS.test.claude, "POST /api/connectors/codex/test": CONNECTORS.test.codex});
  const claude = await testConnector(api, "claude");
  assert.deepEqual(api.calls, [{method: "POST", path: "/api/connectors/claude/test", body: undefined}]);
  assert.deepEqual([claude.ok, claude.seconds, claude.line], [true, 3.2, "Worked in 3.2 s"]);
  const codex = await testConnector(api, "codex");
  assert.equal(api.calls[1].path, "/api/connectors/codex/test");
  assert.equal(codex.line, "Worked in 4.8 s");
});

test("Test shows the error's message when the server refuses", async () => {
  const sentence = CONNECTORS.test_error.error.message;
  const api = fakeApi({"POST /api/connectors/codex/test": new ApiError(sentence, "provider_unavailable", 503)});
  const result = await testConnector(api, "codex");
  assert.deepEqual([result.ok, result.seconds, result.message, result.line], [false, null, sentence, sentence]);
});

test("Test with a failure that has no sentence, or an answer that says ok: false, still says why", async () => {
  const none = await testConnector(fakeApi({"POST /api/connectors/claude/test": Object.assign(new Error(""), {code: "network"})}), "claude");
  assert.equal(none.message, "The test could not run.");
  const no = await testConnector(fakeApi({"POST /api/connectors/claude/test": {ok: false, message: "It answered nothing."}}), "claude");
  assert.deepEqual([no.ok, no.message], [false, "It answered nothing."]);
  const bare = await testConnector(fakeApi({"POST /api/connectors/claude/test": {ok: false}}), "claude");
  assert.equal(bare.message, "The test did not pass.");
});

test("a provider name is encoded into the path", async () => {
  const api = fakeApi({});
  await testConnector(api, "a/b");
  assert.equal(api.calls[0].path, "/api/connectors/a%2Fb/test");
});

/* ---------------------------------------------------------------- the sign-in box */
test("a pending sign-in shows the link, the one-time code and Cancel, and Sign in waits", () => {
  const html = connectorsHtml(HEALTH, {signin: signInState(null, START)});
  const codex = row(html, "codex");
  assert.match(codex, /<a class="sulink" href="https:\/\/auth\.openai\.com\/codex\/device" target="_blank" rel="noopener noreferrer">/);
  assert.match(codex, /<code class="sicode">WXYZ-1234<\/code>/);
  assert.match(codex, /about 15 minutes/);
  assert.match(codex, /data-act="cancel" data-provider="codex">Cancel</);
  assert.match(codex, /data-act="signin" data-provider="codex" disabled>/);
  assert.equal(row(html, "claude").includes("signin"), false);
});

test("a sign-in link that is not https is shown as text, not as a link", () => {
  const html = connectorsHtml(HEALTH, {signin: signInState(null, {id: "x", url: "javascript:alert(1)", code: "AB-12", expires_in: 900})});
  assert.equal(html.includes("<a "), false);
  assert.equal(html.includes("href="), false);
  assert.match(html, /javascript:alert\(1\)/);
});

test("a finished sign-in shows its sentence, without a code or Cancel, and Sign in is back", () => {
  ["signed_in", "failed", "expired"].forEach(step => {
    const state = signInState(signInState(null, START), {state: step});
    const codex = row(connectorsHtml(HEALTH, {signin: state}), "codex");
    assert.match(codex, new RegExp(`<div class="signin" data-step="${step}"`));
    assert.equal(codex.includes("sicode"), false, step);
    assert.equal(codex.includes('data-act="cancel"'), false, step);
    assert.equal(/data-act="signin"[^>]*disabled/.test(codex), false, step);
  });
});

test("an idle sign-in draws no box", () => {
  assert.equal(connectorsHtml(HEALTH, {signin: signInState(null, null)}).includes('class="signin"'), false);
  assert.equal(connectorsHtml(HEALTH).includes('class="signin"'), false);
});

/* ---------------------------------------------------------------- the sign-in reducer */
test("the start answer gives pending, with the link, the code and how long it lasts", () => {
  assert.deepEqual(signInState(null, START), {step: "pending", url: START.url, code: START.code, expires_in: 900, message: "Open the link and type the code."});
});

test("a pending poll keeps the link and the code", () => {
  const pending = signInState(null, START);
  assert.deepEqual(signInState(pending, {state: "pending"}), pending);
});

test("signed_in, failed, expired and cancelled end it and clear the code", () => {
  const pending = signInState(null, START);
  const words = {signed_in: "Signed in.", failed: "Sign in did not work. Try again.", expired: "The code ran out. Press Sign in for a new one.", cancelled: "Sign in cancelled."};
  Object.keys(words).forEach(step => {
    assert.deepEqual(signInState(pending, {state: step}), {step, url: "", code: "", expires_in: 0, message: words[step]});
  });
});

test("an error becomes the error step with the server's sentence", () => {
  const out = signInState(signInState(null, START), new ApiError("Codex is not installed on this Mac.", "cli_missing", 503));
  assert.deepEqual(out, {step: "error", url: "", code: "", expires_in: 0, message: "Codex is not installed on this Mac."});
  assert.equal(signInState(null, {message: ""}).message, "Sign in could not start.");
});

test("a state the page does not know is an error, and something that is not an answer changes nothing", () => {
  assert.equal(signInState(signInState(null, START), {state: "teapot"}).step, "error");
  const pending = signInState(null, START);
  assert.equal(signInState(pending, null), pending);
  assert.equal(signInState(pending, "pending"), pending);
  assert.deepEqual(signInState(undefined, undefined), {step: "idle", url: "", code: "", expires_in: 0, message: ""});
});

/* ---------------------------------------------------------------- the sign-in flow */
test("Sign in posts, shows the link and code, polls until signed_in, and never deletes", async () => {
  const api = fakeApi({"POST /api/connectors/codex/sign-in": START, ["GET " + POLL]: SEQUENCES.success.map(state => ({state}))});
  const seen = [];
  const sleeps = [];
  const flow = signIn(api, {onState: s => seen.push(s), sleep: ms => { sleeps.push(ms); return Promise.resolve(); }, pollMs: 1500});
  const last = await flow.done;
  assert.deepEqual(api.calls.map(c => `${c.method} ${c.path}`), ["POST /api/connectors/codex/sign-in", "GET " + POLL, "GET " + POLL, "GET " + POLL]);
  assert.deepEqual(seen.map(s => s.step), ["pending", "pending", "pending", "signed_in"]);
  assert.deepEqual([seen[0].url, seen[0].code], [START.url, START.code]);
  assert.deepEqual([seen[1].url, seen[1].code], [START.url, START.code]);        // the link and the code stay while it waits
  assert.deepEqual(sleeps, [1500, 1500, 1500]);
  assert.equal(last.step, "signed_in");
});

test("Sign in stops at failed and at expired", async () => {
  for (const [name, expected] of [["failed", ["pending", "failed"]], ["expired", ["pending", "expired"]]]) {
    const api = fakeApi({"POST /api/connectors/codex/sign-in": START, ["GET " + POLL]: SEQUENCES[name].map(state => ({state}))});
    const seen = [];
    await signIn(api, {onState: s => seen.push(s.step), sleep: instantly}).done;
    // the start answer is "pending", then one entry for every poll answer; the first pending poll adds a second "pending"
    assert.equal(seen[seen.length - 1], name);
    assert.equal(api.calls.filter(c => c.method === "GET").length, SEQUENCES[name].length);
    assert.equal(api.calls.some(c => c.method === "DELETE"), false);
    assert.deepEqual(seen.filter((s, i) => i === 0 || s !== seen[i - 1]), expected);
  }
});

test("Sign in asks again after the wait, not before", async () => {
  const order = [];
  const api = fakeApi({"POST /api/connectors/codex/sign-in": START, ["GET " + POLL]: [{state: "pending"}, {state: "signed_in"}]});
  const original = api.get;
  api.get = p => { order.push("get"); return original(p); };
  await signIn(api, {sleep: () => { order.push("wait"); return Promise.resolve(); }}).done;
  assert.deepEqual(order, ["wait", "get", "wait", "get"]);
});

test("Cancel sends DELETE for the sign-in and the polling stops", async () => {
  let release;
  const api = fakeApi({"POST /api/connectors/codex/sign-in": START, ["GET " + POLL]: {state: "pending"}, ["DELETE " + POLL]: null});
  const seen = [];
  const flow = signIn(api, {onState: s => seen.push(s.step), sleep: () => new Promise(resolve => { release = resolve; })});
  while (!release) await Promise.resolve();                  // the first wait has begun
  const after = await flow.cancel();
  release();
  const last = await flow.done;
  assert.equal(after.step, "cancelled");
  assert.equal(last.step, "cancelled");
  assert.deepEqual(api.calls.map(c => `${c.method} ${c.path}`), ["POST /api/connectors/codex/sign-in", "DELETE " + POLL]);
  assert.deepEqual(seen, ["pending", "cancelled"]);
});

test("Cancel while the start request is still on its way deletes the sign-in once it has an id", async () => {
  let answerStart;
  const api = fakeApi({["DELETE " + POLL]: null, ["GET " + POLL]: {state: "pending"}});
  const post = api.post;
  api.post = (p, b) => { api.calls.push({method: "POST", path: p, body: b}); return new Promise(resolve => { answerStart = () => resolve(START); }); };
  const flow = signIn(api, {sleep: instantly});
  while (!answerStart) await Promise.resolve();
  const early = flow.cancel();
  answerStart();
  await early;
  const last = await flow.done;
  assert.equal(last.step, "cancelled");
  assert.deepEqual(api.calls.map(c => `${c.method} ${c.path}`), ["POST /api/connectors/codex/sign-in", "DELETE " + POLL]);
  void post;
});

test("Cancel after the sign-in is over does nothing", async () => {
  const api = fakeApi({"POST /api/connectors/codex/sign-in": START, ["GET " + POLL]: {state: "signed_in"}});
  const flow = signIn(api, {sleep: instantly});
  await flow.done;
  const out = await flow.cancel();
  assert.equal(out.step, "signed_in");
  assert.equal(api.calls.some(c => c.method === "DELETE"), false);
});

test("a sign-in that cannot start ends with the server's sentence and asks nothing more", async () => {
  const api = fakeApi({"POST /api/connectors/codex/sign-in": new ApiError("Codex is not installed on this Mac.", "cli_missing", 503)});
  const seen = [];
  const last = await signIn(api, {onState: s => seen.push(s), sleep: instantly}).done;
  assert.deepEqual([last.step, last.message], ["error", "Codex is not installed on this Mac."]);
  assert.equal(seen.length, 1);
  assert.equal(api.calls.length, 1);
});

test("a start answer without an id is an error", async () => {
  const api = fakeApi({"POST /api/connectors/codex/sign-in": {url: START.url, code: START.code, expires_in: 900}});
  const last = await signIn(api, {sleep: instantly}).done;
  assert.equal(last.step, "error");
  assert.equal(api.calls.length, 1);
});

test("a poll that fails ends the sign-in with its sentence", async () => {
  const api = fakeApi({"POST /api/connectors/codex/sign-in": START, ["GET " + POLL]: new ApiError("No such sign-in.", "not_found", 404)});
  const last = await signIn(api, {sleep: instantly}).done;
  assert.deepEqual([last.step, last.message], ["error", "No such sign-in."]);
  assert.equal(api.calls.filter(c => c.method === "GET").length, 1);
});

test("a sign-in the server never ends is called expired once its time has passed", async () => {
  const api = fakeApi({"POST /api/connectors/codex/sign-in": START, ["GET " + POLL]: {state: "pending"}});
  const last = await signIn(api, {sleep: instantly, pollMs: 300000}).done;       // 5 minutes a time: 900 s + 30 s of grace is 4 polls
  assert.equal(last.step, "expired");
  assert.equal(api.calls.filter(c => c.method === "GET").length, 4);
});

test("a listener that throws does not stop the sign-in", async () => {
  const api = fakeApi({"POST /api/connectors/codex/sign-in": START, ["GET " + POLL]: {state: "signed_in"}});
  const last = await signIn(api, {onState: () => { throw new Error("listener"); }, sleep: instantly}).done;
  assert.equal(last.step, "signed_in");
});

/* ---------------------------------------------------------------- the rows follow the connector events */
test("the three connector events are the ones that refetch the health", () => {
  assert.deepEqual([...HEALTH_EVENTS], ["connector.health", "connector.switch", "connector.mode"]);
});

test("one connector event is one GET /api/health, and the rows get the answer", async () => {
  for (const type of HEALTH_EVENTS) {
    const api = fakeApi({"GET /api/health": HEALTH});
    const got = [];
    const watch = watchHealth(api, h => got.push(h));
    await watch.onEvent(type);
    assert.deepEqual(api.calls, [{method: "GET", path: "/api/health", body: undefined}], type);
    assert.deepEqual(got, [HEALTH], type);
  }
});

test("other events do not touch the health", async () => {
  const api = fakeApi({"GET /api/health": HEALTH});
  const watch = watchHealth(api, () => {});
  for (const type of ["graph.updated", "chat.turn", "chart.changed", "usage.recorded", "server.resync", "connectors"]) {
    assert.equal(await watch.onEvent(type), undefined);
  }
  assert.deepEqual(api.calls, []);
});

test("a health refetch that fails is reported and leaves the rows as they were", async () => {
  const api = fakeApi({"GET /api/health": new ApiError("The app answered 500.", "http_500", 500)});
  const shown = [];
  const failures = [];
  const watch = watchHealth(api, h => shown.push(h), e => failures.push(e.message));
  assert.equal(await watch.refetch(), null);
  assert.deepEqual([shown, failures], [[], ["The app answered 500."]]);
});
