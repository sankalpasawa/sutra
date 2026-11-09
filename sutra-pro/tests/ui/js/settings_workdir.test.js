"use strict";
// SettingsView, the Working folder group (sutra_app/ui/static/js/settings_view.js; GAP3-workdir, D125): a text field, "Choose folder..." (only with the desktop
// bridge), Save, Clear, the access choice, the instructions line, the top of the folder under "What the model can see", the plain words (a team works in the
// folder like a Claude session, what is read goes to your own CLI), and the calls GET, PUT ({path} and {access}) and DELETE on /api/connectors/workdir.
// Everything from the wire is escaped.
// Run with: node --test tests/ui/js/settings_workdir.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SV = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/settings_view.js"));
const {workdirHtml, loadWorkdir, saveWorkdir, saveWorkdirAccess, chooseWorkdir, canChooseFolder, clearWorkdir, WORKDIR_PATH, WORKDIR_WORDS} = SV;
const withBridge = (bridge, fn) => {                       // window.sutraDesktop exists only in the desktop app: set it for one test, never leave it
  globalThis.sutraDesktop = bridge;
  try { return fn(); } finally { delete globalThis.sutraDesktop; }
};

const entries = (...names) => names.map(n => ({name: n, kind: n.endsWith("/") ? "dir" : "file"})).map(e => ({name: e.name.replace(/\/$/, ""), kind: e.kind}));
const data = (over) => Object.assign({path: "/work/proj", usable: true, problem: null, access: "edit", instructions: null,
  preview: {entries: entries("src/", "docs/", "app.py", "README.md"), total: 4, shown: 4, capped: false, readable: true}}, over || {});
const NONE = {path: null, usable: false, problem: null, access: null, instructions: null, preview: null};

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
class ApiError extends Error {
  constructor(message, code, status) { super(message); this.name = "ApiError"; this.code = code || "error"; this.status = status || 500; this.details = {}; }
}

/* ---------------------------------------------------------------- the group */
test("the group is its own section with the heading, the plain words and the field with Save and Clear", () => {
  const html = workdirHtml({data: NONE, value: ""});
  assert.match(html, /^<section class="setgrp" data-group="workdir" aria-labelledby="set-workdir-h"><h3 id="set-workdir-h">Working folder<\/h3>/);
  assert.match(html, /Teams you tell to work on a project \(not a document or a website\) work in this folder like a Claude session: they read its files, follow its CLAUDE\.md and, if you allow it, change files\./);
  assert.match(html, /They never run commands other than git status\/diff\/log\/show, and never leave the folder\./);
  assert.doesNotMatch(html, /read-only chats|chats only|department runs are unchanged|cannot create, change or delete/);
  assert.match(html, /goes to your own Claude or Codex/);
  assert.match(html, /<input type="text" id="setwd" data-workdir-input[^>]*placeholder="~\/Documents\/my-project"/);
  assert.match(html, /data-act="workdir-save"/);
  assert.match(html, /data-act="workdir-clear"/);
  assert.match(html, /<h4 class="setsub">What the model can see<\/h4>/);
});

test("with no folder the status says so, Clear is off and the list is a hint, not a list", () => {
  const html = workdirHtml({data: NONE, value: ""});
  assert.match(html, /data-state="none">No folder is set\. Chats run in a private empty folder/);
  assert.match(html, /data-act="workdir-clear" disabled/);
  assert.doesNotMatch(html, /wdlist/);
  assert.match(html, /Nothing yet: choose a folder/);
});

test("a folder in use is named and its top level is listed, folders first as the server sent them, with a slash on a folder", () => {
  const html = workdirHtml({data: data(), value: "/work/proj"});
  assert.match(html, /data-state="set">In use: \/work\/proj</);
  assert.match(html, /value="\/work\/proj"/);
  assert.match(html, /<ul class="wdlist" aria-label="What the model can see"><li data-kind="dir">src\/<\/li><li data-kind="dir">docs\/<\/li><li data-kind="file">app\.py<\/li><li data-kind="file">README\.md<\/li><\/ul>/);
  assert.match(html, /4 entries\./);
  assert.doesNotMatch(html, /data-act="workdir-clear" disabled/);
});

test("a long folder says how many are shown of how many, and that the model can see all of them", () => {
  const preview = {entries: entries(...Array.from({length: 60}, (_, i) => `f${i}.txt`)), total: 213, shown: 60, capped: false, readable: true};
  const html = workdirHtml({data: data({preview}), value: ""});
  assert.equal((html.match(/<li /g) || []).length, 60);
  assert.match(html, /Showing 60 of 213 entries\. The model can see all of them\./);
  const capped = workdirHtml({data: data({preview: Object.assign({}, preview, {total: 20000, capped: true})}), value: ""});
  assert.match(capped, /Showing 60 of at least 20000 entries/);
  const one = workdirHtml({data: data({preview: {entries: entries("a.txt"), total: 1, shown: 1, capped: false, readable: true}}), value: ""});
  assert.match(one, /1 entry\./);
  const empty = workdirHtml({data: data({preview: {entries: [], total: 0, shown: 0, capped: false, readable: true}}), value: ""});
  assert.match(empty, /The folder is empty\./);
  assert.doesNotMatch(empty, /<ul/);
});

test("a folder that cannot be used now says why and lists nothing", () => {
  const html = workdirHtml({data: data({usable: false, problem: "There is no folder at /work/proj", preview: null}), value: "/work/proj"});
  assert.match(html, /data-state="broken">The folder you chose cannot be used now, so chats run without it: There is no folder at \/work\/proj</);
  assert.doesNotMatch(html, /wdlist/);
  assert.match(workdirHtml({data: data({preview: {entries: [], total: 0, shown: 0, capped: false, readable: false}}), value: ""}), /This folder cannot be listed\./);
});

test("every word from the wire is escaped: a path, a name, a problem, a message and the typed value", () => {
  const evil = '<img src=x onerror="alert(1)">';
  const html = workdirHtml({data: data({path: "/p/" + evil, problem: evil, usable: true,
    preview: {entries: [{name: evil, kind: "file"}, {name: evil, kind: "dir"}], total: 2, shown: 2, capped: false, readable: true}}),
    value: '"><script>x</script>', step: "error", message: evil});
  assert.doesNotMatch(html, /<img|<script/);
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  assert.match(html, /value="&quot;&gt;&lt;script&gt;x&lt;\/script&gt;"/);
});

test("names with control characters are shown as one clean line", () => {
  const html = workdirHtml({data: data({preview: {entries: [{name: "a\nb\tc", kind: "file"}], total: 1, shown: 1, capped: false, readable: true}}), value: ""});
  assert.match(html, /<li data-kind="file">a b c<\/li>/);
});

test("saving disables both buttons; a refusal is a red sentence beside the field; a pass is a calm one", () => {
  const saving = workdirHtml({data: data(), value: "/x", step: "saving"});
  assert.match(saving, /data-act="workdir-save" disabled/);
  assert.match(saving, /data-act="workdir-clear" disabled/);
  const refused = workdirHtml({data: NONE, value: "/x", step: "error", message: "That folder belongs to Sutra itself"});
  assert.match(refused, /<span class="seterr" role="alert">That folder belongs to Sutra itself<\/span>/);
  const ok = workdirHtml({data: data(), value: "/work/proj", step: "ok", message: WORKDIR_WORDS.saved});
  assert.match(ok, /<span class="settest" data-step="ok" role="status">Saved\. The next message in any chat can read this folder\.<\/span>/);
});

test("before the setting is read the group says so, and a failed read says why", () => {
  assert.match(workdirHtml({data: null}), /Reading the setting/);
  assert.match(workdirHtml(undefined), /Reading the setting/);
  assert.match(workdirHtml({data: null, step: "error", message: "The app is not answering"}), /The app is not answering/);
  assert.doesNotMatch(workdirHtml({data: null}), /<input/);
});

test("the stylesheet and the page have what the group needs, and only J2's tokens", () => {
  const css = fs.readFileSync(path.resolve(__dirname, "../../../sutra_app/ui/static/css/sutra-shell.css"), "utf8");
  const block = css.slice(css.indexOf(".wdstatus"), css.indexOf(".setpathd {"));
  assert.match(block, /\.wdlist/);
  const used = [...block.matchAll(/var\((--[a-z0-9-]+)\)/g)].map(m => m[1]);
  assert.ok(used.length > 0 && used.every(t => ["--ink", "--muted", "--ok", "--bad", "--accent", "--bg", "--panel", "--panel2", "--line", "--mono"].includes(t)), used.join(","));
  const html = fs.readFileSync(path.resolve(__dirname, "../../../sutra_app/ui/pages/home.html"), "utf8");
  assert.ok(html.indexOf('id="set-connectors"') < html.indexOf('id="set-workdir"') && html.indexOf('id="set-workdir"') < html.indexOf('id="set-limits"'));
});

/* ---------------------------------------------------------------- the three calls */
test("loadWorkdir is one GET and gives the answer; a failure gives the sentence", async () => {
  const api = fakeApi({["GET " + WORKDIR_PATH]: data()});
  const r = await loadWorkdir(api);
  assert.deepEqual(api.calls, [{method: "GET", path: "/api/connectors/workdir", body: undefined}]);
  assert.equal(r.ok, true);
  assert.equal(r.data.path, "/work/proj");
  const failed = await loadWorkdir(fakeApi({["GET " + WORKDIR_PATH]: new ApiError("The app is not answering", "network", 0)}));
  assert.deepEqual([failed.ok, failed.data, failed.message], [false, null, "The app is not answering"]);
  const odd = await loadWorkdir(fakeApi({["GET " + WORKDIR_PATH]: "nonsense"}));
  assert.equal(odd.ok, false);
});

test("saveWorkdir sends the trimmed path in a PUT and says it applies from the next message", async () => {
  const api = fakeApi({["PUT " + WORKDIR_PATH]: body => data({path: body.path})});
  const r = await saveWorkdir(api, "  ~/Documents/my-project \n");
  assert.deepEqual(api.calls, [{method: "PUT", path: "/api/connectors/workdir", body: {path: "~/Documents/my-project"}}]);
  assert.equal(r.ok, true);
  assert.equal(r.message, "Saved. The next message in any chat can read this folder.");
  assert.equal(r.data.path, "~/Documents/my-project");
});

test("saveWorkdir sends nothing for an empty field, and shows the server's reason for a refusal", async () => {
  const api = fakeApi({});
  for (const empty of ["", "   ", undefined, null]) {
    const r = await saveWorkdir(api, empty);
    assert.equal(r.ok, false);
    assert.match(r.message, /Write the full path/);
  }
  assert.equal(api.calls.length, 0);
  const refused = await saveWorkdir(fakeApi({["PUT " + WORKDIR_PATH]: new ApiError("That folder belongs to Sutra itself (its data and chat state). Choose a folder of your own", "invalid_request", 422)}), "/data");
  assert.deepEqual([refused.ok, refused.data], [false, null]);
  assert.match(refused.message, /belongs to Sutra itself/);
});

test("clearWorkdir is one DELETE and the group then reads as no folder", async () => {
  const api = fakeApi({["DELETE " + WORKDIR_PATH]: NONE});
  const r = await clearWorkdir(api);
  assert.deepEqual(api.calls, [{method: "DELETE", path: "/api/connectors/workdir", body: undefined}]);
  assert.equal(r.ok, true);
  assert.equal(r.message, "Cleared. Chats go back to a private empty folder.");
  assert.match(workdirHtml({data: r.data, value: ""}), /No folder is set/);
  const failed = await clearWorkdir(fakeApi({["DELETE " + WORKDIR_PATH]: new ApiError("Not allowed", "bad_token", 401)}));
  assert.deepEqual([failed.ok, failed.message], [false, "Not allowed"]);
});

/* ---------------------------------------------------------------- the folder dialog, the access choice, the instructions line (D125) */
test("Choose folder is drawn only where the desktop app bridges its dialog", () => {
  assert.equal(canChooseFolder(), false);
  assert.doesNotMatch(workdirHtml({data: NONE, value: ""}), /workdir-choose/);
  withBridge({}, () => assert.doesNotMatch(workdirHtml({data: NONE, value: ""}), /workdir-choose/));           // a bridge without the function is no bridge
  withBridge({chooseFolder: async () => null}, () => {
    assert.equal(canChooseFolder(), true);
    const html = workdirHtml({data: NONE, value: ""});
    assert.match(html, /<button type="button" class="ghost" data-act="workdir-choose">Choose folder\u2026<\/button><button type="button" class="ghost" data-act="workdir-save"/);
    assert.match(html, /<input type="text" id="setwd"/);                                                       // the text field stays beside it
    assert.match(workdirHtml({data: NONE, value: "", step: "saving"}), /data-act="workdir-choose" disabled/);
  });
});

test("chooseWorkdir gives the trimmed path, and null for a closed dialog, an odd answer or a failure", async () => {
  assert.equal(await chooseWorkdir({chooseFolder: async () => "  /Users/me/proj \n"}), "/Users/me/proj");
  for (const answer of [null, undefined, "", "   ", 7, {}]) assert.equal(await chooseWorkdir({chooseFolder: async () => answer}), null);
  assert.equal(await chooseWorkdir({chooseFolder: async () => { throw new Error("boom"); }}), null);
  assert.equal(await chooseWorkdir(null), null);                                                              // no bridge on the page
  assert.equal(await withBridge({chooseFolder: async () => "/b"}, () => chooseWorkdir()), "/b");              // the page's own bridge by default
});

test("with a folder set the access choice shows, one option is on, and it is off while saving; with none it is not drawn", () => {
  const html = workdirHtml({data: data(), value: "/work/proj"});
  assert.match(html, /<div class="wdaccessrow" role="radiogroup" aria-label="What a team may do in this folder">/);
  assert.match(html, /<button type="button" class="ghost wdaccess" role="radio" data-act="workdir-access" data-access="edit" aria-checked="true" data-on="true">Read and change files<\/button>/);
  assert.match(html, /<button type="button" class="ghost wdaccess" role="radio" data-act="workdir-access" data-access="read" aria-checked="false">Read only<\/button>/);
  const read = workdirHtml({data: data({access: "read"}), value: ""});
  assert.match(read, /data-access="read" aria-checked="true" data-on="true"/);
  assert.match(read, /data-access="edit" aria-checked="false">/);
  assert.equal((workdirHtml({data: data(), value: "", step: "saving"}).match(/data-act="workdir-access"[^>]* disabled/g) || []).length, 2);
  assert.doesNotMatch(workdirHtml({data: NONE, value: ""}), /workdir-access|radiogroup/);
});

test("the instructions line names the file the team follows, escaped, and is absent without one", () => {
  const html = workdirHtml({data: data({instructions: {file: "CLAUDE.md", chars: 812}}), value: ""});
  assert.match(html, /<p class="sethint wdinstr">The team follows this folder&#39;s CLAUDE\.md\.<\/p>/);
  assert.match(workdirHtml({data: data({instructions: {file: "AGENTS.md", chars: 5}}), value: ""}), /follows this folder&#39;s AGENTS\.md\./);
  assert.doesNotMatch(workdirHtml({data: data(), value: ""}), /The team follows/);
  const evil = workdirHtml({data: data({instructions: {file: "<img src=x>", chars: 1}}), value: ""});
  assert.doesNotMatch(evil, /<img/);
  assert.match(evil, /&lt;img src=x&gt;/);
});

test("saveWorkdirAccess is one PUT with the access alone, and says what it now allows", async () => {
  const api = fakeApi({["PUT " + WORKDIR_PATH]: body => data({access: body.access})});
  const r = await saveWorkdirAccess(api, "read");
  assert.deepEqual(api.calls, [{method: "PUT", path: "/api/connectors/workdir", body: {access: "read"}}]);
  assert.equal(r.ok, true);
  assert.equal(r.data.access, "read");
  assert.equal(r.message, "Saved. Teams only read this folder.");
  assert.equal((await saveWorkdirAccess(api, "edit")).message, "Saved. Teams may change files in this folder.");
  assert.deepEqual(api.calls[1].body, {access: "edit"});
});

test("saveWorkdirAccess sends nothing for another word, and shows the server's reason for a refusal", async () => {
  const api = fakeApi({});
  for (const bad of ["", "write", undefined, null, "EDIT"]) assert.equal((await saveWorkdirAccess(api, bad)).ok, false);
  assert.equal(api.calls.length, 0);
  const refused = await saveWorkdirAccess(fakeApi({["PUT " + WORKDIR_PATH]: new ApiError("Set a folder first", "invalid_request", 422)}), "read");
  assert.deepEqual([refused.ok, refused.data, refused.message], [false, null, "Set a folder first"]);
});

test("saveWorkdir keeps sending the path alone: the server keeps the access of the same folder and gives a new one edit", async () => {
  const api = fakeApi({["PUT " + WORKDIR_PATH]: data()});
  await saveWorkdir(api, "/work/proj");
  assert.deepEqual(api.calls[0].body, {path: "/work/proj"});
});
