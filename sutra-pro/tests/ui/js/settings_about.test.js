"use strict";
// SettingsView, the About group (welcome-settings, item 2): version, data folder, Check for updates and its answer in words.
// The check is a POST the owner starts; it downloads and installs nothing. Run with: node --test tests/ui/js/settings_about.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const {aboutHtml, checkUpdate, updateWords, setAutoUpdate} = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/settings_view.js"));

const INFO = {version: "0.1.0", data_dir: "/data/sutra-pro"};
const PAGE = "https://github.com/sankalpasawa/sutra/releases/tag/sutra-pro-v0.2.0";
const NEWER = {current: "0.1.0", latest: "0.2.0", newer: true, url: PAGE, notes_url: PAGE, how: "Download the new Sutra-Pro .dmg and drag it over the app.", error: null,
  said: "You have 0.1.0; 0.2.0 is out."};
const SAME = {current: "0.1.0", latest: "0.1.0", newer: false, url: "https://github.com/sankalpasawa/sutra/releases?q=sutra-pro", notes_url: null, how: "x", error: null,
  said: "You have 0.1.0: up to date."};

test("the group shows the version, the data folder and a button, and says the app asks only when pressed", () => {
  const html = aboutHtml(INFO, {step: "idle"});
  assert.match(html, /<section class="setgrp" data-group="about"/);
  assert.match(html, /<h3 id="set-about-h">About<\/h3>/);
  assert.match(html, /<span class="setlabel">Version<\/span><span class="setvalue">0\.1\.0<\/span>/);
  assert.match(html, /<span class="setvalue setpathv">\/data\/sutra-pro<\/span>/);
  assert.match(html, /<button type="button" class="ghost" data-act="check-update">Check for updates<\/button>/);
  assert.match(html, /contacts the internet when you press Check for updates and, in the desktop app, for the automatic check you can turn off below\. It never installs an update without your choice\./);
  assert.doesNotMatch(html, /<a /);
  assert.doesNotMatch(html, /toggle-auto-update/);                         // two arguments (or the setting not loaded yet): the group is as it was, no switch
});

test("before the answer there is no line; while it asks the button is disabled and says so", () => {
  assert.match(aboutHtml(INFO, {step: "idle"}), /<span class="settest" data-step="idle" role="status"><\/span>/);
  const running = aboutHtml(INFO, {step: "running"});
  assert.match(running, /data-act="check-update" disabled>/);
  assert.match(running, /role="status">Checking…<\/span>/);
});

test("a newer release says what is out, links the release page and gives the line for this install", () => {
  const html = aboutHtml(INFO, {step: "ok", answer: NEWER});
  assert.match(html, /data-step="new" role="status">You have 0\.1\.0; 0\.2\.0 is out\.<\/span>/);
  assert.match(html, /<a class="sulink" href="https:\/\/github\.com\/sankalpasawa\/sutra\/releases\/tag\/sutra-pro-v0\.2\.0" target="_blank" rel="noopener noreferrer">Release notes and download<\/a>/);
  assert.match(html, /Download the new Sutra-Pro \.dmg and drag it over the app\./);
});

test("up to date has the sentence and no link", () => {
  const html = aboutHtml(INFO, {step: "ok", answer: SAME});
  assert.match(html, /data-step="ok" role="status">You have 0\.1\.0: up to date\.<\/span>/);
  assert.doesNotMatch(html, /<a /);
});

test("could not reach GitHub is a sentence in the line, not an error page", () => {
  const answer = {...SAME, latest: null, error: "Could not reach GitHub. Check your connection and try again.", said: "Could not reach GitHub. Check your connection and try again."};
  const html = aboutHtml(INFO, {step: "ok", answer});
  assert.match(html, /data-step="error" role="status">Could not reach GitHub/);
  assert.doesNotMatch(html, /<a /);
  const refused = aboutHtml(INFO, {step: "error", message: "Update check is not available while the app runs offline: it would need the internet."});
  assert.match(refused, /data-step="error" role="status">Update check is not available while the app runs offline/);
});

test("a link is drawn only for https on github.com, and every word from the wire is escaped", () => {
  const evil = '<img src=x onerror="1">';
  assert.doesNotMatch(aboutHtml(INFO, {step: "ok", answer: {...NEWER, notes_url: "https://evil.example/x", url: "https://evil.example/x"}}), /<a /);
  assert.doesNotMatch(aboutHtml(INFO, {step: "ok", answer: {...NEWER, notes_url: "javascript:alert(1)", url: "javascript:alert(1)"}}), /<a /);
  const html = aboutHtml({version: evil, data_dir: evil}, {step: "ok", answer: {...NEWER, said: evil, how: evil}});
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=&quot;1&quot;&gt;/);
});

test("without the info answer the group still draws, with unknown values", () => {
  const html = aboutHtml(null, null);
  assert.match(html, /<span class="setvalue">unknown<\/span>/);
  assert.match(html, /data-act="check-update">/);
});

test("updateWords prefers the server's sentence and builds one otherwise", () => {
  assert.equal(updateWords(NEWER), "You have 0.1.0; 0.2.0 is out.");
  assert.equal(updateWords({current: "0.1.0", latest: "0.2.0", newer: true}), "You have 0.1.0; 0.2.0 is out.");
  assert.equal(updateWords({current: "0.1.0", newer: false}), "You have 0.1.0: up to date.");
  assert.equal(updateWords({error: "nope"}), "nope");
  assert.equal(updateWords(null), "");
});

function fakeApi(answer) {
  const calls = [];
  return {calls, post: (p, b) => { calls.push({method: "POST", path: p, body: b}); return answer instanceof Error ? Promise.reject(answer) : Promise.resolve(answer); },
    get: () => assert.fail("the check is a POST: nothing is fetched")};
}

test("checkUpdate is one POST and nothing else, and its answer is handed back whole", async () => {
  const api = fakeApi(NEWER);
  const out = await checkUpdate(api);
  assert.deepEqual(api.calls, [{method: "POST", path: "/api/ops/update-check", body: {}}]);
  assert.deepEqual([out.step, out.answer.latest], ["ok", "0.2.0"]);
});

test("a refusal or a network failure is the owner's sentence, never a throw", async () => {
  const offline = Object.assign(new Error("Update check is not available while the app runs offline."), {status: 409, code: "offline"});
  assert.deepEqual(await checkUpdate(fakeApi(offline)), {step: "error", answer: null, message: "Update check is not available while the app runs offline."});
  assert.equal((await checkUpdate(fakeApi(new Error("")))).message, "The check did not work.");
  assert.equal((await checkUpdate(fakeApi("garbage"))).step, "error");
});

// ---------------------------------------------------------------- the automatic check (gap package autoupdate)
const AUTO = {auto: true, chosen: false, default: true, desktop: true, offline: false, last: null};
const LAST = {at: 1700000000, state: "up_to_date", version: null, message: "You have 0.2.0: up to date."};

test("with the setting loaded there is a labelled switch, what is sent, and no last check yet", () => {
  const html = aboutHtml(INFO, {step: "idle"}, AUTO);
  assert.match(html, /<label class="setswitch"><input type="checkbox" role="switch" data-act="toggle-auto-update" aria-checked="true" checked> Check for updates automatically<\/label>/);
  assert.match(html, /asks GitHub for the list of releases about a minute after it opens and every 6 hours\. It sends one request and nothing about you or your files\./);
  assert.match(html, /installed only when you choose Restart\. The command line and a browser-only start never check by themselves\./);
  assert.match(html, /Last check: none yet\./);
  assert.doesNotMatch(html, /Offline mode/);
  assert.match(html, /data-act="check-update">/);                           // the owner's button is still there, unchanged
});

test("off is an unchecked switch with aria-checked false, and a save in flight disables it", () => {
  const off = aboutHtml(INFO, {step: "idle"}, {...AUTO, auto: false, chosen: true});
  assert.match(off, /aria-checked="false"> Check for updates automatically/);
  assert.doesNotMatch(off, /aria-checked="false" checked/);
  assert.match(aboutHtml(INFO, {step: "idle"}, {...AUTO, busy: true}), /data-act="toggle-auto-update" aria-checked="true" checked disabled>/);
  assert.match(aboutHtml(INFO, {step: "idle"}, {...AUTO, message: "The setting could not be saved."}), /<span class="seterr" role="alert">The setting could not be saved\.<\/span>/);
});

test("the last check is the browser's own time and the server's words, and a time that is not a number is left out", () => {
  const html = aboutHtml(INFO, {step: "idle"}, {...AUTO, last: LAST});
  const when = new Date(1700000000 * 1000).toLocaleString();
  assert.ok(html.includes("Last check: " + when + ': <span class="settest" data-step="ok">You have 0.2.0: up to date.</span>'), html);
  for (const at of [NaN, Infinity, null, "soon", undefined, 1e30]) {
    const odd = aboutHtml(INFO, {step: "idle"}, {...AUTO, last: {...LAST, at}});
    assert.doesNotMatch(odd, /NaN|Invalid Date|undefined|null/, String(at));
    assert.match(odd, /Last check: <span class="settest" data-step="ok">You have 0\.2\.0: up to date\.<\/span>/, String(at));
  }
});

test("a failed or available state is coloured by its step and every word of the last check is escaped", () => {
  const evil = '<img src=x onerror="1"> and \u0007 bell';
  const bad = aboutHtml(INFO, {step: "idle"}, {...AUTO, last: {at: 1700000000, state: "failed", version: "0.3.0", message: evil}});
  assert.doesNotMatch(bad, /<img/);
  assert.match(bad, /data-step="error">&lt;img src=x onerror=&quot;1&quot;&gt; and bell<\/span>/);
  assert.match(aboutHtml(INFO, {step: "idle"}, {...AUTO, last: {...LAST, state: "ready", message: "Sutra Pro 0.3.0 is ready."}}), /data-step="new">Sutra Pro 0\.3\.0 is ready\./);
  assert.match(aboutHtml(INFO, {step: "idle"}, {...AUTO, last: {...LAST, state: "error", message: "Could not reach GitHub."}}), /data-step="error">Could not reach GitHub\./);
  assert.match(aboutHtml(INFO, {step: "idle"}, {...AUTO, last: {...LAST, message: ""}}), /Last check: none yet\./);
  assert.match(aboutHtml(INFO, {step: "idle"}, {...AUTO, last: "junk"}), /Last check: none yet\./);
  assert.doesNotMatch(aboutHtml({version: evil, data_dir: evil}, {step: "idle"}, {...AUTO, message: evil}), /<img/);
});

test("offline mode says that no automatic check is made", () => {
  const html = aboutHtml(INFO, {step: "idle"}, {...AUTO, offline: true});
  assert.match(html, /Offline mode is on, so no automatic check is made whatever this switch says\./);
});

test("a setting that is not an object draws nothing about the switch", () => {
  for (const odd of [null, undefined, "x", 5, [], true]) assert.doesNotMatch(aboutHtml(INFO, {step: "idle"}, odd), /toggle-auto-update|Last check/, String(odd));
});

function putApi(answer) {
  const calls = [];
  return {calls, put: (p, b) => { calls.push({method: "PUT", path: p, body: b}); return answer instanceof Error ? Promise.reject(answer) : Promise.resolve(answer); },
    get: () => assert.fail("saving the switch reads nothing"), post: () => assert.fail("saving the switch asks GitHub nothing")};
}

test("setAutoUpdate is one PUT of the owner's choice and hands back what the server stored", async () => {
  const api = putApi({...AUTO, auto: false, chosen: true});
  const out = await setAutoUpdate(api, false);
  assert.deepEqual(api.calls, [{method: "PUT", path: "/api/ops/update-setting", body: {auto: false}}]);
  assert.equal(out.ok, true);
  assert.equal(out.auto.auto, false);
  assert.equal(out.message, "");
  const on = putApi({...AUTO, chosen: true});
  await setAutoUpdate(on, true);
  assert.deepEqual(on.calls[0].body, {auto: true});
  await setAutoUpdate(on, "yes");                                                               // only a real true switches it on
  assert.deepEqual(on.calls[1].body, {auto: false});
});

test("a refused or failed save is the owner's sentence and no setting, never a throw", async () => {
  const refused = Object.assign(new Error("auto must be true or false."), {status: 422, code: "validation"});
  assert.deepEqual(await setAutoUpdate(putApi(refused), true), {ok: false, auto: null, message: "auto must be true or false."});
  assert.equal((await setAutoUpdate(putApi(new Error("")), true)).message, "The setting could not be saved.");
  assert.equal((await setAutoUpdate(putApi("garbage"), true)).ok, false);
  assert.equal((await setAutoUpdate(putApi({auto: "yes"}), true)).ok, false);
  assert.equal((await setAutoUpdate(putApi(null), true)).ok, false);
});
