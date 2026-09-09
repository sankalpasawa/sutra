#!/usr/bin/env node
/*
 * test_install_move.js -- the first-install path, asserted.
 *
 * main.js::copyIntoApplications() is the fallback Electron's own mover falls
 * back TO, and because that mover refuses a read-only source and the source is
 * always a DMG, it is the path nearly every first install actually takes.
 *
 * THE BUG THIS FILE EXISTS FOR (2026-09-09). It was one line -- ditto the
 * running bundle straight onto /Applications/<same basename> -- and while
 * opening the shipped app to verify a release it silently overwrote a real,
 * notarized install with a differently-identified copy that merely shared the
 * name. Three separate guards were missing: ditto merges rather than replaces,
 * so a new bundle laid over an old one keeps every file the new version
 * deleted and no longer matches its own sealed signature; the destination was
 * never checked for being the SAME app; and it was written over while
 * processes were still mapped out of it.
 *
 * updates.py has done this correctly all along -- stage beside, verify, swap
 * with two renames, refuse while anything is running -- so these assertions
 * are really "the install path agrees with the update path".
 *
 * These read electron/main.js as TEXT, the test_update_attach.js pattern.
 * They cannot execute it: the function moves an app bundle into /Applications
 * on the machine running the suite, which is exactly what must not happen in a
 * test. So they assert the guards, which is the layer that was wrong.
 *
 * Run: node test_install_move.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const main = fs.readFileSync(path.join(__dirname, "electron/main.js"), "utf8");

let pass = 0, fail = 0;
const test = (n, f) => { try { f(); console.log("ok   - " + n); pass++; }
                         catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; } };
const assert = (c, m) => { if (!c) throw new Error(m); };

/* The function's body, so an assertion cannot be satisfied by an unrelated
   part of a 2,000-line file. */
function copyFn() {
  const i = main.indexOf("function copyIntoApplications()");
  assert(i > 0, "copyIntoApplications is gone from main.js");
  const j = main.indexOf("\nasync function ensureInstalled()", i);
  assert(j > i, "could not find the end of copyIntoApplications");
  return main.slice(i, j);
}

test("copyIntoApplications is still the fallback installer", () => {
  const fn = copyFn();
  assert(fn.includes("/usr/bin/ditto"), "it no longer uses ditto");
  assert(fn.includes("/usr/bin/open"), "it no longer opens the installed copy");
});

test("it never dittos straight onto the destination", () => {
  const fn = copyFn();
  const ditto = fn.match(/execFileSync\("\/usr\/bin\/ditto",\s*\[([^\]]*)\]/);
  assert(ditto, "no ditto call found");
  const args = ditto[1];
  assert(!/\bdst\b/.test(args),
    "ditto still writes to dst; it merges onto the old bundle instead of replacing it");
  assert(/\bstage\b/.test(args), "ditto does not copy to a staging path");
});

test("it stages beside the target and swaps by rename, like updates.py", () => {
  const fn = copyFn();
  assert(/const stage\s*=\s*dst\s*\+/.test(fn), "the staging path is not derived from dst");
  assert(/const backup\s*=\s*dst\s*\+/.test(fn), "there is no backup path to move the old bundle to");
  assert(fn.includes("fs.renameSync(dst, backup)"), "the old bundle is not moved aside");
  assert(fn.includes("fs.renameSync(stage, dst)"), "the new bundle is not renamed into place");
});

test("a failed swap puts the old bundle back", () => {
  const fn = copyFn();
  assert(fn.includes("fs.renameSync(backup, dst)"),
    "nothing restores the old bundle when the second rename fails");
});

test("a bundle at the destination with a different identity is refused, not overwritten", () => {
  const fn = copyFn();
  assert(fn.includes("bundleIdOf(src)") && fn.includes("bundleIdOf(dst)"),
    "the two bundle identifiers are not compared");
  assert(/mine\s*!==\s*theirs/.test(fn), "a mismatched bundle id does not stop the install");
  assert(/throw new Error\(/.test(fn), "a refusal is not reported to the caller");
  assert(fn.includes("left exactly as it was"),
    "the refusal does not tell the user their app was untouched");
});

test("an unreadable identity counts as a mismatch, so it fails closed", () => {
  const fn = copyFn();
  assert(/!mine\s*\|\|/.test(fn),
    "an unreadable bundle id is not treated as a reason to stop");
});

test("it refuses to write over a bundle that is still running", () => {
  const fn = copyFn();
  assert(fn.includes("/usr/bin/pgrep"), "nothing checks for live processes");
  assert(fn.includes("Contents", "MacOS"), "the process check does not look under the bundle");
  assert(/still running/.test(fn), "there is no message naming the running app");
});

test("bundleIdOf reads Info.plist and never throws into the launch path", () => {
  const i = main.indexOf("function bundleIdOf(");
  assert(i > 0, "bundleIdOf is missing");
  const fn = main.slice(i, main.indexOf("\n}", i));
  assert(fn.includes("CFBundleIdentifier"), "it does not read CFBundleIdentifier");
  assert(fn.includes("Info.plist"), "it does not read Info.plist");
  assert(/catch\s*{\s*return ""/.test(fn), "it can throw instead of returning an empty id");
});

console.log("\n" + "-".repeat(60));
console.log(`install to Applications: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
