"use strict";
// SettingsView, the Engine group (sutra_app/ui/static/js/settings_view.js): the editable fields as toggles and number fields, the locked fields read-only,
// the {set, unset} body, the scope (all teams, or one team with `dept` in the query), and what a 422 names.
// docs/design/ui.md sections 6.6, 7, 8 and 10; S1-contracts-03; D18.
// Run with: node --test tests/ui/js/settings_engine.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SettingsView = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/settings_view.js"));
const {engineHtml, engineBody, engineErrors, loadEngine, saveEngine, appearanceHtml, enginePath} = SettingsView;
const fixture = name => JSON.parse(fs.readFileSync(path.resolve(__dirname, "../fixtures", name), "utf8"));
const clone = value => JSON.parse(JSON.stringify(value));

// The fixture answers GET /api/engine/settings?dept=web: defaults, global (budget 120, slim off), department (max_cycles 4).
const FOR_TEAM = fixture("engine-settings.json");
// The same answer for all teams: no `department`, and the effective values are the defaults under the all-teams file.
const FOR_ALL = (() => {
  const all = clone(FOR_TEAM);
  delete all.department;
  all.effective = Object.assign({}, all.defaults, all.global);
  return all;
})();
const DEPARTMENTS = [{id: "web", name: "Web"}, {id: "content", name: "Content"}];

// The markup of one field's row: from its opening tag to the next row, so a test can look at one field.
function rows(html) {
  const out = {};
  const parts = html.split('<div class="setfield"').slice(1);
  parts.forEach(part => {
    const field = /data-field="([^"]+)"/.exec(part)[1];
    out[field] = '<div class="setfield"' + part.split("</section>")[0];
  });
  return out;
}
const inputOf = row => /<(input|select)\b[^>]*>/.exec(row);

/* ---------------------------------------------------------------- what the group shows */
test("the group is the engine group, with its title and the line that changes apply to the next run", () => {
  const html = engineHtml(FOR_ALL, {scope: "", departments: DEPARTMENTS});
  assert.match(html, /<section class="setgrp" data-group="engine"/);
  assert.match(html, /<h3[^>]*>Engine<\/h3>/);
  assert.match(html, /changes apply to the next run/i);
});

test("the line about the next run is there before the settings have loaded", () => {
  const html = engineHtml(null, {});
  assert.match(html, /data-group="engine"/);
  assert.match(html, /changes apply to the next run/i);
  assert.match(html, /not loaded yet/);
});

test("every editable field has a control and no locked field has one", () => {
  const html = engineHtml(FOR_ALL, {scope: "", departments: DEPARTMENTS});
  const found = rows(html);
  FOR_ALL.editable.forEach(field => {
    assert.equal(found[field].includes('data-locked="false"'), true, field);
    assert.ok(inputOf(found[field]), `${field} has a control`);
  });
  FOR_ALL.locked.forEach(field => {
    assert.equal(found[field].includes('data-locked="true"'), true, field);
    assert.equal(/<(input|select|textarea)\b/.test(found[field]), false, `${field} is read-only`);
  });
  assert.equal(Object.keys(found).length, FOR_ALL.editable.length + FOR_ALL.locked.length);
});

test("a boolean setting is a toggle that shows the effective value", () => {
  const found = rows(engineHtml(FOR_TEAM, {scope: "web", departments: DEPARTMENTS}));
  assert.match(inputOf(found.slim)[0], /type="checkbox"/);
  assert.equal(/\bchecked\b/.test(inputOf(found.slim)[0]), false);          // the all-teams file turned it off
  assert.equal(/\bchecked\b/.test(inputOf(found.rates)[0]), true);          // the default is on
  assert.equal(/\bchecked\b/.test(inputOf(found.change)[0]), false);        // the default is off
});

test("fixes is a toggle too, although it travels as 0 or 1", () => {
  const found = rows(engineHtml(FOR_ALL, {}));
  assert.match(inputOf(found.fixes)[0], /type="checkbox"/);
  assert.equal(/\bchecked\b/.test(inputOf(found.fixes)[0]), false);
  const on = clone(FOR_ALL);
  on.effective.fixes = 1;
  assert.equal(/\bchecked\b/.test(inputOf(rows(engineHtml(on, {})).fixes)[0]), true);
});

test("a numeric setting is a number field holding the effective value; whole numbers step by 1 and the others by any", () => {
  const found = rows(engineHtml(FOR_TEAM, {scope: "web"}));
  assert.match(inputOf(found.budget)[0], /type="number"/);
  assert.match(inputOf(found.budget)[0], /value="120"/);                      // from the all-teams file
  assert.match(inputOf(found.budget)[0], /step="1"/);
  assert.match(inputOf(found.max_cycles)[0], /value="4"/);                    // from the team's file
  assert.match(inputOf(found.delay)[0], /step="any"/);
  assert.match(inputOf(found.bargain_minutes)[0], /step="any"/);
});

test("budget_cap, which is not set by default, is an empty number field", () => {
  const found = rows(engineHtml(FOR_ALL, {}));
  assert.match(inputOf(found.budget_cap)[0], /type="number"/);
  assert.match(inputOf(found.budget_cap)[0], /value=""/);
});

test("the kind of build is a choice among the six the engine accepts, and the engine decides by default", () => {
  const row = rows(engineHtml(FOR_ALL, {})).output;
  assert.match(row, /<select\b/);
  ["auto", "website", "prd", "hld", "lld", "project"].forEach(v => assert.match(row, new RegExp(`<option value="${v}"`)));
  assert.match(row, /<option value="auto" selected>Let the team decide</);
  assert.match(row, /<option value="project">Project work</);
});

test("the template library flag says what the catalog's By run list shows while it is off (D142)", () => {
  const html = engineHtml(FOR_ALL, {scope: "", departments: DEPARTMENTS});
  const row = rows(html).template_library;
  assert.match(row, /<label class="setlabel" for="setf-template_library">Template library<\/label>/);
  assert.match(row, /<span class="sethint">Builders use the template library\. While this is off, the catalog&#39;s &quot;By run&quot; list shows J2&#39;s eight development runs only\.<\/span>/);
});

test("the working-folder switch for agents is a choice between auto and off", () => {
  const row = rows(engineHtml(FOR_ALL, {})).workspace;
  assert.match(row, /<select\b/);
  assert.match(row, /<option value="auto" selected>/);
  assert.match(row, /<option value="off">/);
});

test("a row says which layer set its value", () => {
  const found = rows(engineHtml(FOR_TEAM, {scope: "web"}));
  assert.match(found.max_cycles, /data-source="team"/);
  assert.match(found.max_cycles, /set for this team/);
  assert.match(found.budget, /data-source="all"/);
  assert.match(found.budget, /set for all teams/);
  assert.match(found.limit_add, /data-source="default"/);
});

test("every locked field is read-only, shows its value and says where engine.json is", () => {
  const found = rows(engineHtml(FOR_ALL, {}));
  FOR_ALL.locked.forEach(field => assert.match(found[field], /edit engine\.json in your data folder \(About shows where it is\)/, field));
  FOR_ALL.locked.forEach(field => assert.equal(found[field].includes("data/engine.json"), false, field));              // the installed apps have no data/ folder
  assert.match(found.send_mode, /dry-run/);
  assert.match(found.test_email, /\(empty\)/);
  assert.match(found.milestone_emails, />off</);
  assert.match(found.send_cap, />10</);
});

// QA firstrun-settings: every locked row said "edit data/engine.json", a folder that does not exist in the installed apps (they use ~/.sutra-pro).
test("the locked rows name the real file when the data folder is known, with the separator of its system, and escape it", () => {
  const note = (dataDir) => rows(engineHtml(FOR_ALL, {dataDir}))[FOR_ALL.locked[0]].match(/<span class="setlock">([^<]*)<\/span>/)[1];
  assert.equal(note("/home/x/.sutra-pro"), "edit /home/x/.sutra-pro/engine.json");
  assert.equal(note("/home/x/.sutra-pro/"), "edit /home/x/.sutra-pro/engine.json");                                      // no doubled slash
  assert.equal(note("C:\\Users\\x\\.sutra-pro"), "edit C:\\Users\\x\\.sutra-pro\\engine.json");                          // Windows keeps its backslashes
  assert.equal(note("C:\\Users\\x\\.sutra-pro\\"), "edit C:\\Users\\x\\.sutra-pro\\engine.json");
  assert.equal(note(""), SettingsView.NOTE_LOCKED);                                                                       // not known yet (or the read failed): where to look
  assert.equal(note(undefined), SettingsView.NOTE_LOCKED);
  const hostile = engineHtml(FOR_ALL, {dataDir: '/x/<img src=x onerror="alert(1)">'});
  assert.equal(hostile.includes("<img"), false);
  assert.match(hostile, /edit \/x\/&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;\/engine\.json/);
});

test("the scope select offers all teams, then each team, and marks the one in use", () => {
  const all = engineHtml(FOR_ALL, {scope: "", departments: DEPARTMENTS});
  assert.match(all, /<option value="" selected>All teams<\/option>/);
  assert.match(all, /<option value="web">Web<\/option>/);
  assert.match(all, /<option value="content">Content<\/option>/);
  const team = engineHtml(FOR_TEAM, {scope: "content", departments: DEPARTMENTS});
  assert.match(team, /<option value="content" selected>Content<\/option>/);
  assert.match(engineHtml(FOR_TEAM, {scope: "gone", departments: DEPARTMENTS}), /<option value="gone" selected>gone<\/option>/);
});

test("a team name is written as text, never as markup", () => {
  const html = engineHtml(FOR_ALL, {departments: [{id: "x", name: '<img src=x onerror="alert(1)">'}]});
  assert.equal(html.includes("<img"), false);
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
});

test("a refused value is named beside its field, and a general sentence stands at the top", () => {
  const html = engineHtml(FOR_ALL, {errors: {budget: "budget must be a whole number of at least 1", "": "Not saved."}});
  const found = rows(html);
  assert.match(found.budget, /<span class="seterr" role="alert">budget must be a whole number of at least 1<\/span>/);
  assert.equal(found.max_cycles.includes("seterr"), false);
  assert.match(html, /<p class="seterr setgen" role="alert">Not saved\.<\/p>/);
});

test("what the owner typed stays in the fields beside a refusal", () => {
  const html = engineHtml(FOR_ALL, {values: {budget: "0", rates: false, output: "prd", fixes: true}, errors: {budget: "no"}});
  const found = rows(html);
  assert.match(inputOf(found.budget)[0], /value="0"/);
  assert.equal(/\bchecked\b/.test(inputOf(found.rates)[0]), false);        // the default is on; the owner turned it off
  assert.equal(/\bchecked\b/.test(inputOf(found.fixes)[0]), true);
  assert.match(found.output, /<option value="prd" selected>/);
  assert.match(inputOf(rows(engineHtml(FOR_ALL, {})).budget)[0], /value="120"/);   // without values the server's own are shown
});

test("the Save button, the saved line and the busy state", () => {
  assert.match(engineHtml(FOR_ALL, {}), /<button type="button" class="ghost" data-act="save-engine">Save<\/button>/);
  assert.match(engineHtml(FOR_ALL, {busy: true}), /data-act="save-engine" disabled>/);
  assert.match(engineHtml(FOR_ALL, {saved: true}), /Saved\. Changes apply to the next run\./);
  assert.equal(engineHtml(FOR_ALL, {}).includes("Saved."), false);
});

test("the Appearance group has Light, Dark and System, and the chosen one is pressed", () => {
  const html = appearanceHtml("light");
  assert.match(html, /data-group="appearance"/);
  assert.match(html, /data-themepick="light" aria-pressed="true"/);
  assert.match(html, /data-themepick="dark" aria-pressed="false"/);
  assert.match(html, /data-themepick="system" aria-pressed="false"/);
  assert.match(appearanceHtml("nonsense"), /data-themepick="light" aria-pressed="true"/);   // light is the default (the studio look, as the team pages)
});

/* ---------------------------------------------------------------- the PUT body */
test("a form that changed nothing makes an empty body", () => {
  const form = {budget: "120", slim: false, rates: true, output: "auto", fixes: false, budget_cap: "", max_cycles: "4", delay: "0"};
  assert.deepEqual(engineBody(FOR_TEAM, form), {set: {}, unset: []});
  assert.deepEqual(engineBody(FOR_TEAM, {}), {set: {}, unset: []});
});

test("only the changed fields are sent, each as the type its field has", () => {
  const body = engineBody(FOR_ALL, {budget: "200", rates: false, delay: "2.5", output: "prd", fixes: true, max_turns: "30", budget_cap: "500"});
  assert.deepEqual(body, {set: {budget: 200, rates: false, delay: 2.5, output: "prd", fixes: 1, budget_cap: 500}, unset: []});
});

test("a field that goes back to its default is unset, not set", () => {
  // For all teams the default is the layer below the all-teams file: budget 100 and slim on, which the file had overridden.
  const body = engineBody(FOR_ALL, {budget: "100", slim: true, rates: true});
  assert.deepEqual(body, {set: {}, unset: ["budget", "slim"]});
});

test("for one team the layer below is the defaults and the all-teams file", () => {
  // slim: the all-teams file says off, the default on. Back to "on" must be written for the team (it overrides the file); back to "off" unsets it.
  assert.deepEqual(engineBody(FOR_TEAM, {slim: true}), {set: {slim: true}, unset: []});
  // max_cycles 4 is the team's own; 6 is the default and the file does not set it, so the team's value is removed.
  assert.deepEqual(engineBody(FOR_TEAM, {max_cycles: "6"}), {set: {}, unset: ["max_cycles"]});
  // budget 120 comes from the all-teams file: the team may set another value, and writing 120 changes nothing.
  assert.deepEqual(engineBody(FOR_TEAM, {budget: "300"}), {set: {budget: 300}, unset: []});
  assert.deepEqual(engineBody(FOR_TEAM, {budget: "120"}), {set: {}, unset: []});
});

test("a team's own value that goes back to what all teams have is unset, not pinned", () => {
  const settings = clone(FOR_TEAM);
  settings.department.budget = 500;                    // the team overrides the all-teams 120
  settings.effective.budget = 500;
  assert.deepEqual(engineBody(settings, {budget: "120"}), {set: {}, unset: ["budget"]});
  assert.deepEqual(engineBody(settings, {budget: "100"}), {set: {budget: 100}, unset: []});   // the default differs from what all teams say: it must be written
});

test("a value equal to the layer below is still set when this layer does not hold the field", () => {
  const settings = clone(FOR_ALL);
  settings.effective.limit_add = 99;            // something else (the process environment) made it differ from the default
  assert.deepEqual(engineBody(settings, {limit_add: "30"}), {set: {limit_add: 30}, unset: []});
});

test("a field that was set can be emptied back to not set", () => {
  const settings = clone(FOR_ALL);
  settings.global.budget_cap = 500;
  settings.effective.budget_cap = 500;
  assert.deepEqual(engineBody(settings, {budget_cap: ""}), {set: {}, unset: ["budget_cap"]});
  const unpinned = clone(FOR_ALL);
  unpinned.effective.budget_cap = 700;
  assert.deepEqual(engineBody(unpinned, {budget_cap: ""}), {set: {budget_cap: null}, unset: []});
});

test("a locked or unknown field in the form is never sent", () => {
  assert.deepEqual(engineBody(FOR_ALL, {send_mode: "live", chrome: "/x", nothing: 1, test_email: "a@b.c"}), {set: {}, unset: []});
});

test("a value that cannot be read is left out of the body, and the form problems name it", () => {
  const form = {budget: "abc", max_cycles: "2.5", delay: "", output: "pdf", rates: "maybe", limit_add: "7"};
  assert.deepEqual(engineBody(FOR_ALL, form), {set: {limit_add: 7}, unset: []});
  const problems = SettingsView.formProblems(FOR_ALL, form);
  assert.deepEqual(Object.keys(problems).sort(), ["budget", "delay", "max_cycles", "output", "rates"]);
  assert.match(problems.budget, /whole number/);
  assert.match(problems.delay, /number/);
});

/* ---------------------------------------------------------------- what a 422 names */
test("a validation error names each field of its violations", () => {
  const error = {code: "validation", message: "Not saved: budget must be a whole number of at least 1",
    details: {violations: [{path: "set.budget", code: "invalid_value", message: "budget must be a whole number of at least 1"},
      {path: "unset.send_mode", code: "locked_field", message: "send_mode can only be changed by hand in engine.json"},
      {path: "set.budget", code: "invalid_value", message: "second sentence for the same field"}]}};
  assert.deepEqual(engineErrors(error), {budget: "budget must be a whole number of at least 1", send_mode: "send_mode can only be changed by hand in engine.json"});
});

test("an error without violations is one sentence for the whole form", () => {
  assert.deepEqual(engineErrors({code: "bad_token", message: "This page was opened without its access token. Reload it from the app.", details: {}}),
    {"": "This page was opened without its access token. Reload it from the app."});
  assert.deepEqual(engineErrors(null), {"": "The settings could not be saved."});
  assert.deepEqual(engineErrors({message: "x", details: {violations: [{path: "", message: "no field"}]}}), {"": "x"});
});

/* ---------------------------------------------------------------- the calls */
function fakeApi(answers) {
  const calls = [];
  const run = (method, p, body) => {
    calls.push({method, path: p, body});
    const answer = answers[method + " " + p];
    if (answer instanceof Error) return Promise.reject(answer);
    return Promise.resolve(typeof answer === "function" ? answer(body) : answer);
  };
  return {calls, get: p => run("GET", p), post: (p, b) => run("POST", p, b), put: (p, b) => run("PUT", p, b), del: p => run("DELETE", p)};
}
class Refused extends Error {
  constructor(message, details) { super(message); this.name = "ApiError"; this.status = 422; this.code = "validation"; this.details = details || {}; }
}

test("dept is put in the query for one team and left out for all teams", async () => {
  assert.equal(enginePath(""), "/api/engine/settings");
  assert.equal(enginePath(undefined), "/api/engine/settings");
  assert.equal(enginePath("web"), "/api/engine/settings?dept=web");
  assert.equal(enginePath("a b&c"), "/api/engine/settings?dept=a%20b%26c");
  const api = fakeApi({"GET /api/engine/settings": FOR_ALL, "GET /api/engine/settings?dept=web": FOR_TEAM});
  assert.equal(await loadEngine(api, ""), FOR_ALL);
  assert.equal(await loadEngine(api, "web"), FOR_TEAM);
  assert.deepEqual(api.calls.map(c => c.path), ["/api/engine/settings", "/api/engine/settings?dept=web"]);
});

test("saving sends only the {set, unset} body, to the scope's path, and returns the server's answer", async () => {
  const saved = clone(FOR_TEAM);
  saved.department.slim = true;
  const api = fakeApi({"PUT /api/engine/settings?dept=web": saved});
  const out = await saveEngine(api, FOR_TEAM, "web", {slim: true, max_cycles: "6", budget: "120"});
  assert.deepEqual(api.calls, [{method: "PUT", path: "/api/engine/settings?dept=web", body: {set: {slim: true}, unset: ["max_cycles"]}}]);
  assert.equal(out.ok, true);
  assert.equal(out.unchanged, false);
  assert.equal(out.settings, saved);
});

test("saving for all teams leaves dept out of the path", async () => {
  const api = fakeApi({"PUT /api/engine/settings": FOR_ALL});
  await saveEngine(api, FOR_ALL, "", {budget: "250"});
  assert.deepEqual(api.calls, [{method: "PUT", path: "/api/engine/settings", body: {set: {budget: 250}, unset: []}}]);
});

test("saving nothing changed makes no request", async () => {
  const api = fakeApi({});
  const out = await saveEngine(api, FOR_ALL, "", {budget: "120"});
  assert.deepEqual(api.calls, []);
  assert.deepEqual([out.ok, out.unchanged], [true, true]);
});

test("a value that cannot be read is refused on the page, with no request", async () => {
  const api = fakeApi({});
  const out = await saveEngine(api, FOR_ALL, "", {budget: "lots"});
  assert.deepEqual(api.calls, []);
  assert.equal(out.ok, false);
  assert.deepEqual(Object.keys(out.errors), ["budget"]);
});

test("a 422 comes back naming the field it refused", async () => {
  const refusal = new Refused("Not saved: budget must be a whole number of at least 1",
    {violations: [{path: "set.budget", code: "invalid_value", message: "budget must be a whole number of at least 1"}]});
  const api = fakeApi({"PUT /api/engine/settings": refusal});
  const out = await saveEngine(api, FOR_ALL, "", {budget: "0"});
  assert.equal(out.ok, false);
  assert.equal(out.settings, FOR_ALL);
  assert.deepEqual(out.errors, {budget: "budget must be a whole number of at least 1"});
});

test("any other failure of the save is one sentence for the form", async () => {
  const api = fakeApi({"PUT /api/engine/settings": Object.assign(new Error("The app is not responding. Try again in a moment."), {code: "network", status: 0})});
  const out = await saveEngine(api, FOR_ALL, "", {budget: "250"});
  assert.deepEqual([out.ok, out.errors], [false, {"": "The app is not responding. Try again in a moment."}]);
});
