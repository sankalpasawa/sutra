"use strict";
// Run with: node --test tests/ui/js/create_project.test.js
// The Create project box (named projects, task 6): a required name, an optional source folder with the trust question, and where the
// work is saved when no folder is chosen. Strings in, strings out.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const CreateProject = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/create_project.js"));

const text = html => html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

test("the box has a title, a Project name field and a source folder", () => {
  const html = CreateProject.html({desktop: true});
  assert.match(html, /role="dialog" aria-modal="true" aria-labelledby="cptitle"/);
  assert.match(html, /<h2 id="cptitle">Create project<\/h2>/);
  assert.match(html, /<label for="cpname">Project name<\/label>/);
  assert.match(html, /id="cpname"[^>]*maxlength="80"/);
  assert.match(text(html), /Source folder/);
});

test("Create stays disabled until a name is typed", () => {
  assert.equal(CreateProject.canCreate({name: "  "}), false);
  assert.equal(CreateProject.canCreate({name: ""}), false);
  assert.equal(CreateProject.canCreate({name: "Pulse"}), true);
  assert.equal(CreateProject.canCreate({name: "x".repeat(81)}), false);
  assert.equal(CreateProject.canCreate({name: "Pulse", busy: true}), false);
  assert.match(CreateProject.html({name: ""}), /data-act="cp-create"[^>]* disabled/);
  assert.doesNotMatch(CreateProject.html({name: "Pulse"}), /data-act="cp-create"[^>]* disabled/);
});

test("no folder says where it is saved", () => {
  assert.equal(CreateProject.savedIn("Pulse", true), "Saved in Documents\\Sutra Pro\\Pulse");
  assert.equal(CreateProject.savedIn("Pulse", false), "Saved in Documents/Sutra Pro/Pulse");
  assert.equal(CreateProject.savedIn("  ", false), "Saved in Documents/Sutra Pro/<project name>");
  assert.match(text(CreateProject.html({name: "Pulse", win: true, desktop: true})), /Saved in Documents\\Sutra Pro\\Pulse/);
});

test("a picked folder asks the trust question, and Create waits for the answer", () => {
  const state = {name: "Pulse", folder: "C:\\x", access: null, desktop: true};
  const html = CreateProject.html(state);
  assert.match(html, /Allow Sutra Pro's team to read and edit files in <code>C:\\x<\/code>\?/);
  assert.match(html, /data-act="cp-access" data-access="edit"[^>]*>Read and edit</);
  assert.match(html, /data-act="cp-access" data-access="read"[^>]*>Read only</);
  assert.match(html, /data-act="cp-unfolder"[^>]*>Cancel</);
  assert.equal(CreateProject.canCreate(state), false);
  assert.equal(CreateProject.canCreate({...state, access: "edit"}), true);
});

test("an answered folder shows the path and the access chosen", () => {
  const html = CreateProject.html({name: "Pulse", folder: "/work/pulse", access: "read", desktop: true});
  assert.match(text(html), /\/work\/pulse · Read only/);
  assert.doesNotMatch(text(html), /Allow Sutra Pro/);
});

test("Add shows only in the desktop app; a browser gets a path field", () => {
  assert.match(CreateProject.html({desktop: true}), /data-act="cp-add"[^>]*>Add</);
  const browser = CreateProject.html({desktop: false});
  assert.doesNotMatch(browser, /data-act="cp-add"/);
  assert.match(browser, /<input[^>]*id="cpfolder"/);
});

test("an error shows under its field", () => {
  const byName = CreateProject.html({name: "Pulse", error: "A project called Pulse already exists", errorField: "name"});
  assert.match(byName, /id="cpname"[^]*<p class="cperr" role="alert">A project called Pulse already exists<\/p>[^]*Source folder/);
  const byFolder = CreateProject.html({name: "Pulse", error: "There is no folder at /x", errorField: "folder", desktop: true});
  assert.match(byFolder, /Source folder[^]*<p class="cperr" role="alert">There is no folder at \/x<\/p>/);
});

test("a suggested name fills the field", () => {
  const html = CreateProject.html({name: "Cafe site", suggest: true});
  assert.match(html, /id="cpname"[^>]*value="Cafe site"/);
  assert.match(text(html), /Sutra suggests this name/);
});

test("wire strings are escaped", () => {
  const html = CreateProject.html({name: '<b>"x"</b>', folder: "<i>", access: null, desktop: true, error: "<script>", errorField: "name"});
  assert.doesNotMatch(html, /<b>"x"|<i>|<script>/);
  assert.match(html, /&lt;b&gt;&quot;x&quot;&lt;\/b&gt;/);
});

test("the request body: name trimmed, folder and access only when a folder is set", () => {
  assert.deepEqual(CreateProject.body({name: "  Pulse  ", folder: "", access: null}), {name: "Pulse"});
  assert.deepEqual(CreateProject.body({name: "Pulse", folder: "/w", access: "read"}), {name: "Pulse", folder: "/w", access: "read"});
});

test("the module is a classic script with one global", () => {
  const fs = require("node:fs");
  const src = fs.readFileSync(path.resolve(__dirname, "../../../sutra_app/ui/static/js/create_project.js"), "utf8");
  assert.match(src, /root\.CreateProject = CreateProject/);
  assert.doesNotMatch(src, /\bimport\b|\bexport\b/);
});
