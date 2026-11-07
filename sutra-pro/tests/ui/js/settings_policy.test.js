"use strict";
// SettingsView, the Default model group (sutra_app/ui/static/js/settings_view.js; welcome-settings, item 3): per provider Make first, On or Off and the model,
// as a read-modify-write of GET and PUT /api/connectors/policy. Run with: node --test tests/ui/js/settings_policy.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SV = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/settings_view.js"));
const {policyHtml, policyBody, policyProblem, policyErrors, loadPolicy, savePolicy, answering} = SV;
const clone = v => JSON.parse(JSON.stringify(v));
// the policy file the app ships: rules, rates, timeouts and a sandbox the page must carry through untouched
const POLICY = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../../../sutra_app/connectors/policy.default.json"), "utf8"));
const READY = {connectors: {claude: {installed: true, signed_in: true, health: {state: "ok"}}, codex: {installed: true, signed_in: true, health: {state: "ok"}}}};
const FIVE = ["low", "medium", "high", "xhigh", "max"];
const MODELS = {
  claude: [{slug: "best", label: "Best available", group: "main", provider: "claude"}, {slug: "opus", label: "Opus", group: "main", provider: "claude"},
    {slug: "sonnet", label: "Sonnet", group: "main", provider: "claude"}, {slug: "opus[1m]", label: "Opus, 1M context", group: "more", provider: "claude"}],
  codex: [{slug: "gpt-5.6-luna", label: "GPT-5.6 Luna", group: "main", provider: "codex", efforts: FIVE}],
};

function row(html, name) {
  const start = html.indexOf(`<div class="setmodel" data-provider="${name}"`);
  assert.ok(start >= 0, `no row for ${name}`);
  const next = html.indexOf('<div class="setmodel"', start + 10);
  return html.slice(start, next < 0 ? html.length : next);
}

/* ---------------------------------------------------------------- the PUT body */
test("policyBody keeps every key that was not edited byte for byte equal, and never changes its input", () => {
  const before = clone(POLICY);
  const body = policyBody(POLICY, {model: {claude: "opus"}});
  assert.deepEqual(POLICY, before);
  const expected = clone(POLICY);
  expected.providers.claude.model = "opus";
  assert.deepEqual(body, expected);
  assert.equal(JSON.stringify(body.rules), JSON.stringify(POLICY.rules));
  assert.equal(JSON.stringify(body.rates), JSON.stringify(POLICY.rates));
  assert.equal(body.providers.codex.sandbox, "read-only");
  assert.equal(body.defaults.timeout_s, 900);
  assert.deepEqual(Object.keys(body), Object.keys(POLICY));                          // the same keys in the same order
});

test("Make first moves a provider to the front of defaults.order and keeps the rest in their order", () => {
  assert.deepEqual(policyBody(POLICY, {first: "codex"}).defaults.order, ["codex", "claude"]);
  assert.deepEqual(policyBody(POLICY, {first: "claude"}).defaults.order, ["claude", "codex"]);
  const three = clone(POLICY);
  three.providers.stub = {enabled: true, model: "scripted"};
  three.defaults.order = ["claude", "codex", "stub"];
  assert.deepEqual(policyBody(three, {first: "stub"}).defaults.order, ["stub", "claude", "codex"]);
  assert.deepEqual(policyBody(POLICY, {first: "gemini"}).defaults.order, ["claude", "codex"]);       // a name the policy does not hold changes nothing
  const rules = policyBody(POLICY, {first: "codex"}).rules;
  assert.deepEqual(rules[2].order, ["claude", "codex"]);                                            // the Audit image rule keeps its own order
});

test("On and Off change one flag, a model one string, and several edits at once change just those keys", () => {
  assert.equal(policyBody(POLICY, {enabled: {codex: false}}).providers.codex.enabled, false);
  assert.equal(policyBody(POLICY, {enabled: {codex: false}}).providers.claude.enabled, true);
  assert.equal(policyBody(POLICY, {model: {codex: " gpt-x "}}).providers.codex.model, "gpt-x");
  const both = policyBody(POLICY, {first: "codex", enabled: {claude: false}, model: {codex: "m"}});
  assert.deepEqual([both.defaults.order, both.providers.claude.enabled, both.providers.codex.model], [["codex", "claude"], false, "m"]);
  assert.deepEqual(policyBody(POLICY, {}), POLICY);
  assert.deepEqual(policyBody(POLICY, null), POLICY);
  assert.deepEqual(policyBody(POLICY, {enabled: {claude: "no"}, model: {claude: 5}}), POLICY);         // a value of the wrong kind is ignored
});

/* ---------------------------------------------------------------- what the page refuses */
test("turning off the last provider that is on is refused with the sentence, and sends nothing", () => {
  assert.equal(policyProblem(POLICY, {enabled: {codex: false}}), "");
  const oneOn = policyBody(POLICY, {enabled: {codex: false}});
  assert.match(policyProblem(oneOn, {enabled: {claude: false}}), /At least one model must stay on/);
  assert.match(policyProblem(POLICY, {enabled: {claude: false, codex: false}}), /At least one model must stay on/);
});

test("making an Off provider first is refused: it would never be tried", () => {
  const off = policyBody(POLICY, {enabled: {codex: false}});
  assert.equal(policyProblem(off, {first: "codex"}), "Turn Codex on before making it first.");
  assert.equal(policyProblem(off, {first: "codex", enabled: {codex: true}}), "");
});

test("an empty model is refused, and a policy that is not loaded is too", () => {
  assert.equal(policyProblem(POLICY, {model: {claude: "   "}}), "Choose a model for Claude.");
  assert.equal(policyProblem(null, {}), "The routing policy is not loaded yet.");
});

/* ---------------------------------------------------------------- the group */
test("a row per provider in the order they are tried, with its place in words", () => {
  const html = policyHtml(POLICY, READY, {models: MODELS});
  assert.match(html, /<section class="setgrp" data-group="models"/);
  assert.ok(html.indexOf('data-provider="claude"') < html.indexOf('data-provider="codex"'));
  assert.match(row(html, "claude"), /<b>Claude<\/b><span class="setchip st-ok">First<\/span>/);
  assert.match(row(html, "codex"), /<b>Codex<\/b><span class="setchip ">Second<\/span>/);
  const moved = policyHtml(policyBody(POLICY, {first: "codex"}), READY, {models: MODELS});
  assert.ok(moved.indexOf('data-provider="codex"') < moved.indexOf('data-provider="claude"'));
  assert.match(row(moved, "codex"), /First/);
  const off = policyHtml(policyBody(POLICY, {enabled: {codex: false}}), READY, {models: MODELS});
  assert.match(row(off, "codex"), /<span class="setchip ">Off<\/span>/);
});

test("Make first is there for the second provider only; the first and an Off one have it disabled", () => {
  const html = policyHtml(POLICY, READY, {models: MODELS});
  assert.match(row(html, "claude"), /data-act="make-first" data-provider="claude" disabled>/);
  assert.match(row(html, "codex"), /data-act="make-first" data-provider="codex">Make first/);
  const off = policyHtml(policyBody(POLICY, {enabled: {codex: false}}), READY, {models: MODELS});
  assert.match(row(off, "codex"), /data-act="make-first" data-provider="codex" disabled>/);
  assert.match(row(off, "codex"), /<input type="checkbox" data-policy-on="codex"> On/);              // unchecked
  assert.match(row(html, "codex"), /<input type="checkbox" data-policy-on="codex" checked> On/);
});

test("the model select lists the models the answer holds, the saved one chosen, More models folded", () => {
  const html = row(policyHtml(POLICY, READY, {models: MODELS}), "claude");
  assert.match(html, /<select data-policy-model="claude" aria-label="Model for Claude">/);
  assert.match(html, /<option value="sonnet" selected>Sonnet<\/option>/);
  assert.deepEqual([...html.matchAll(/<option value="([^"]+)"/g)].map(m => m[1]), ["best", "opus", "sonnet", "opus[1m]"]);
  assert.match(html, /<optgroup label="More models"><option value="opus\[1m\]">Opus, 1M context<\/option><\/optgroup>/);
});

test("a saved model the list does not name is still shown, and with no list the select holds the saved model alone", () => {
  const html = policyHtml(policyBody(POLICY, {model: {claude: "claude-legacy-9"}}), READY, {models: MODELS});
  assert.match(row(html, "claude"), /<option value="claude-legacy-9" selected>claude-legacy-9<\/option>/);
  const none = row(policyHtml(POLICY, READY, {models: {}}), "codex");
  assert.deepEqual([...none.matchAll(/<option value="([^"]+)"/g)].map(m => m[1]), ["gpt-5.6-luna"]);
  assert.deepEqual([...row(policyHtml(POLICY, READY, {}), "claude").matchAll(/<option value="([^"]+)"/g)].map(m => m[1]), ["sonnet"]);
});

test("the group says what the choice does and what it does not change", () => {
  const html = policyHtml(POLICY, READY, {models: MODELS});
  assert.match(html, /New chats and the chat agent try the first model first/);
  assert.match(html, /A chat you pinned with its pill keeps its pill/);
  assert.match(html, /the image checks of Audit keep their own order/);
});

test("a saved choice that cannot run is said, with the model that is answering instead of a silent fallback", () => {
  const out = {connectors: {claude: {installed: true, signed_in: false, health: {state: "signed_out"}}, codex: READY.connectors.codex}};
  const html = policyHtml(POLICY, out, {models: MODELS});
  assert.match(row(html, "claude"), /Your saved choice could not be used; Codex is answering\./);
  assert.doesNotMatch(row(html, "codex"), /saved choice/);
  assert.equal(answering(POLICY, out), "codex");
  const quota = {connectors: {claude: {installed: true, signed_in: true, health: {state: "quota"}}, codex: READY.connectors.codex}};
  assert.match(policyHtml(POLICY, quota, {models: MODELS}), /Your saved choice could not be used; Codex is answering/);
  const none = {connectors: {claude: {installed: false}, codex: {installed: true, signed_in: false}}};
  assert.match(policyHtml(POLICY, none, {models: MODELS}), /Your saved choice could not be used; no other model is ready either\./);
  assert.equal(answering(POLICY, none), null);
});

test("no note while everything can run, and none without a health answer", () => {
  assert.doesNotMatch(policyHtml(POLICY, READY, {models: MODELS}), /saved choice/);
  assert.doesNotMatch(policyHtml(POLICY, null, {models: MODELS}), /saved choice/);
  assert.equal(answering(POLICY, READY), "claude");
  assert.equal(answering(policyBody(POLICY, {first: "codex"}), READY), "codex");
  assert.equal(answering(policyBody(POLICY, {enabled: {claude: false}}), READY), "codex");
});

test("busy disables every control, saved says so, errors show under the provider and for the group", () => {
  const busy = policyHtml(POLICY, READY, {models: MODELS, busy: true});
  assert.equal((busy.match(/disabled/g) || []).length, 6);          // two Make first, two switches, two selects
  const html = policyHtml(POLICY, READY, {models: MODELS, saved: true, errors: {codex: "model: too short", "": "At least one model must stay on."}});
  assert.match(html, /Saved\. New chats use this from now on\./);
  assert.match(row(html, "codex"), /<span class="seterr" role="alert">model: too short<\/span>/);
  assert.match(html, /<p class="seterr setgen" role="alert">At least one model must stay on\.<\/p>/);
});

test("nothing is drawn but a note while the policy is not loaded", () => {
  assert.match(policyHtml(null, READY, {}), /The routing policy is not loaded yet\./);
  assert.match(policyHtml({providers: {}}, READY, {}), /not loaded yet/);
});

test("every word from the wire is escaped", () => {
  const evil = '<img src=x onerror="1">';
  const p = clone(POLICY);
  p.providers.claude.model = evil;
  const html = policyHtml(p, READY, {models: {claude: [{slug: evil, label: evil, group: "more"}]}, errors: {claude: evil, "": evil}});
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=&quot;1&quot;&gt;/);
});

/* ---------------------------------------------------------------- errors and the calls */
test("a 422 policy_invalid names the provider a line belongs to, and anything else is one sentence for the group", () => {
  assert.deepEqual(policyErrors({message: "x", details: {errors: ["providers.codex.model: String should have at least 1 character", "defaults.order: bad"]}}),
    {codex: "model: String should have at least 1 character", "": "defaults.order: bad"});
  assert.deepEqual(policyErrors({message: "The routing policy is not valid", details: {}}), {"": "The routing policy is not valid"});
  assert.deepEqual(policyErrors(null), {"": "The choice could not be saved."});
});

function fakeApi(answers) {
  const calls = [];
  const run = (method, p, body) => {
    calls.push({method, path: p, body});
    const a = answers[method + " " + p];
    return a instanceof Error ? Promise.reject(a) : Promise.resolve(typeof a === "function" ? a(body) : a);
  };
  return {calls, get: p => run("GET", p), put: (p, b) => run("PUT", p, b), post: (p, b) => run("POST", p, b)};
}

test("loadPolicy reads the policy and the models by provider; a models failure leaves the page working", async () => {
  const list = [...MODELS.claude, ...MODELS.codex];
  const ok = await loadPolicy(fakeApi({"GET /api/connectors/policy": POLICY, "GET /api/connectors/models": {models: list}}));
  assert.deepEqual(ok.policy, POLICY);
  assert.deepEqual(Object.keys(ok.models), ["claude", "codex"]);
  assert.equal(ok.models.claude.length, 4);
  const bad = await loadPolicy(fakeApi({"GET /api/connectors/policy": POLICY, "GET /api/connectors/models": new Error("503")}));
  assert.deepEqual(bad.models, {});
  await assert.rejects(loadPolicy(fakeApi({"GET /api/connectors/policy": new Error("down")})));
});

test("savePolicy is one PUT of the whole policy with only the edit changed, and the answer is the new policy", async () => {
  const api = fakeApi({"PUT /api/connectors/policy": body => body});
  const out = await savePolicy(api, POLICY, {first: "codex"});
  assert.equal(out.ok, true);
  assert.deepEqual(api.calls.map(c => [c.method, c.path]), [["PUT", "/api/connectors/policy"]]);
  assert.deepEqual(api.calls[0].body.defaults.order, ["codex", "claude"]);
  assert.deepEqual(out.policy.defaults.order, ["codex", "claude"]);
  assert.deepEqual(api.calls[0].body.rules, POLICY.rules);
});

test("savePolicy refuses what the page refuses without a request, and maps the server's 422 to the provider", async () => {
  const one = policyBody(POLICY, {enabled: {codex: false}});
  const api = fakeApi({});
  const refused = await savePolicy(api, one, {enabled: {claude: false}});
  assert.equal(refused.ok, false);
  assert.match(refused.errors[""], /At least one model must stay on/);
  assert.deepEqual(api.calls, []);
  const err = Object.assign(new Error("not valid"), {details: {errors: ["providers.claude.model: too short"]}});
  const failed = await savePolicy(fakeApi({"PUT /api/connectors/policy": err}), POLICY, {model: {claude: "x"}});
  assert.deepEqual([failed.ok, failed.errors, failed.policy], [false, {claude: "model: too short"}, POLICY]);
});
