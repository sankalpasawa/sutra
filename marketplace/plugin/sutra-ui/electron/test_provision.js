/* test_provision.js -- the DMG's first-launch behaviour, asserted.
 *
 * PROTO-000: every shipped change carries a test. This one matters more than
 * most, because provision.js writes into ~/.claude -- Claude Code's own config
 * -- on someone else's machine, unattended, on first launch. The assertions
 * below are the promises that makes acceptable:
 *
 *   never downgrade · never clobber another plugin · never leave a half-written
 *   config · never throw into the launch path · report every path written.
 *
 * Every case runs against a throwaway HOME under os.tmpdir(). No test touches
 * the real ~/.claude; _assertSandboxed() aborts if a path ever escapes.
 *
 * Run: node test_provision.js
 */
"use strict";

const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const P = require("./provision.js");

const checks = [];
const t = (name, fn) => {
  try { fn(); checks.push([name, true, null]); }
  catch (e) { checks.push([name, false, e.message]); }
};

const TMPROOT = fs.mkdtempSync(path.join(os.tmpdir(), "sutra-provision-"));
function sandbox() {
  const home = fs.mkdtempSync(path.join(TMPROOT, "home-"));
  assert.ok(home.startsWith(os.tmpdir()), "sandbox escaped tmpdir");
  return home;
}

/* A fake payload: the smallest tree installPlugin() accepts as a plugin. */
function fakePayload(version, extraFile) {
  const p = fs.mkdtempSync(path.join(TMPROOT, "payload-"));
  const plug = path.join(p, "plugin");
  fs.mkdirSync(path.join(plug, ".claude-plugin"), { recursive: true });
  fs.writeFileSync(path.join(plug, ".claude-plugin", "plugin.json"),
    JSON.stringify({ name: "core", version }));
  fs.mkdirSync(path.join(plug, "hooks"), { recursive: true });
  fs.writeFileSync(path.join(plug, "hooks", "a.sh"), extraFile || "#!/bin/sh\n");
  return p;
}

function installedFile(home) {
  return path.join(home, ".claude", "plugins", "installed_plugins.json");
}
function readInstalled(home) {
  return JSON.parse(fs.readFileSync(installedFile(home), "utf8"));
}

/* ── version comparison ─────────────────────────────────────────────────── */
t("cmpVersion orders numerically, not lexically (2.64.0 > 2.9.0)", () => {
  assert.strictEqual(P.cmpVersion("2.64.0", "2.9.0"), 1);
  assert.strictEqual(P.cmpVersion("2.9.0", "2.64.0"), -1);
  assert.strictEqual(P.cmpVersion("2.64.0", "2.64.0"), 0);
  assert.strictEqual(P.cmpVersion("2.64", "2.64.0"), 0);
});

/* ── runtime resolution ─────────────────────────────────────────────────── */
t("missingDeps names every library the runtime cannot import, with what it is for", () => {
  const py = (bin, args) => JSON.stringify(["bs4"]);
  const m = P.missingDeps("python3", py);
  assert(m.length === 1 && m[0][0] === "bs4", "just the missing one");
  assert(/beautifulsoup4/.test(m[0][1]), "and says what it is for: " + m[0][1]);
  assert(P.missingDeps("python3", () => "[]").length === 0, "nothing missing, nothing reported");
});

t("a python that cannot even be asked is not reported as missing libraries", () => {
  const boom = () => { throw new Error("no such file"); };
  assert(P.missingDeps("nope", boom).length === 0, "that is a different failure");
});

t("repairDeps installs requirements into a STAGED runtime and never into a bundled one", () => {
  const root = fs.mkdtempSync(path.join(TMPROOT, "repair-"));
  const appDir = path.join(root, "plugin", "sutra-ui");
  fs.mkdirSync(appDir, { recursive: true });
  fs.writeFileSync(path.join(appDir, "requirements.txt"), "beautifulsoup4==4.15.0\n");
  const calls = [];
  let installed = false;
  const run = (bin, args) => {
    if (args[0] === "-c") return installed ? "[]" : JSON.stringify(["bs4"]);
    installed = true; calls.push(args.join(" ")); return "";
  };
  const staged = { kind: "staged", appDir, python: "py" };
  const okr = P.repairDeps(staged, { execFileSync: run });
  assert(okr.ok, "a staged runtime is repaired: " + okr.why);
  assert(/pip install .*requirements.txt/.test(calls[0]), "from its own requirements: " + calls[0]);

  const bundled = { kind: "bundled", appDir, python: "py" };
  const no = P.repairDeps(bundled, { execFileSync: run });
  assert(!no.ok && /staged/.test(no.why), "a bundled payload is never written to: " + no.why);
});

t("depsMessage tells a person what is missing and what to do, in plain words", () => {
  const msg = P.depsMessage([["bs4", "reading the HTML of a page (beautifulsoup4)"]]);
  assert(msg.indexOf("bs4") !== -1 && msg.indexOf("reading the HTML") !== -1, "names it and its job");
  assert(/latest Sutra DMG/.test(msg), "and the fix");
  assert(msg.indexOf("Traceback") === -1 && msg.indexOf("ModuleNotFound") === -1, "no stack trace");
});

t("resolveRuntime finds the BUNDLED runtime and prefers it over a staged one", () => {
  const root = fs.mkdtempSync(path.join(TMPROOT, "res-"));
  const res = path.join(root, "Resources");
  fs.mkdirSync(path.join(res, "payload", "python", "bin"), { recursive: true });
  fs.mkdirSync(path.join(res, "payload", "plugin", "sutra-ui"), { recursive: true });
  fs.writeFileSync(path.join(res, "payload", "python", "bin", "python3"), "");
  fs.writeFileSync(path.join(res, "payload", "plugin", "sutra-ui", "app.py"), "");
  fs.writeFileSync(path.join(res, "payload", "STAMP"), JSON.stringify({ arch: "arm64" }));
  // a staged runtime exists too -- the bundle must still win
  const appData = path.join(root, "AppSupport");
  fs.mkdirSync(path.join(appData, "Sutra", "plugin", "sutra-ui"), { recursive: true });
  fs.mkdirSync(path.join(appData, "Sutra", "venv", "bin"), { recursive: true });
  fs.writeFileSync(path.join(appData, "Sutra", "plugin", "sutra-ui", "app.py"), "");
  fs.writeFileSync(path.join(appData, "Sutra", "venv", "bin", "python"), "");

  const r = P.resolveRuntime(res, appData);
  assert.strictEqual(r.kind, "bundled");
  assert.strictEqual(r.stamp.arch, "arm64");
});

t("resolveRuntime falls back to install.sh's staged runtime", () => {
  const root = fs.mkdtempSync(path.join(TMPROOT, "res2-"));
  const appData = path.join(root, "AppSupport");
  fs.mkdirSync(path.join(appData, "Sutra", "plugin", "sutra-ui"), { recursive: true });
  fs.mkdirSync(path.join(appData, "Sutra", "venv", "bin"), { recursive: true });
  fs.writeFileSync(path.join(appData, "Sutra", "plugin", "sutra-ui", "app.py"), "");
  fs.writeFileSync(path.join(appData, "Sutra", "venv", "bin", "python"), "");
  const r = P.resolveRuntime(path.join(root, "NoResources"), appData);
  assert.strictEqual(r.kind, "staged");
});

t("resolveRuntime with neither says WHERE it looked", () => {
  const root = fs.mkdtempSync(path.join(TMPROOT, "res3-"));
  const r = P.resolveRuntime(path.join(root, "a"), path.join(root, "b"));
  assert.strictEqual(r.kind, "none");
  assert.ok(r.why.includes("payload"), "message should name the bundled path");
  assert.ok(r.why.includes("install.sh"), "message should name the checkout fix");
});

/* ── plugin install ─────────────────────────────────────────────────────── */
t("a clean machine gets the plugin, the marketplace and the install record", () => {
  const home = sandbox();
  const r = P.installPlugin({ payload: fakePayload("2.64.0"), home });
  assert.strictEqual(r.status, "installed", r.error || "");
  const dest = path.join(home, ".claude", "plugins", "cache", "sutra", "core", "2.64.0");
  assert.ok(fs.existsSync(path.join(dest, "hooks", "a.sh")), "plugin files not copied");
  const inst = readInstalled(home);
  assert.strictEqual(inst.plugins["core@sutra"].length, 1);
  assert.strictEqual(inst.plugins["core@sutra"][0].version, "2.64.0");
  assert.strictEqual(inst.plugins["core@sutra"][0].scope, "user");
  const km = JSON.parse(fs.readFileSync(
    path.join(home, ".claude", "plugins", "known_marketplaces.json"), "utf8"));
  assert.ok(km.sutra, "marketplace not registered");
  assert.ok(r.wrote.length >= 3, "every written path should be reported");
});

t("running twice changes nothing the second time", () => {
  const home = sandbox();
  const payload = fakePayload("2.64.0");
  P.installPlugin({ payload, home });
  const before = fs.readFileSync(installedFile(home), "utf8");
  const r2 = P.installPlugin({ payload, home });
  assert.strictEqual(r2.status, "already-current");
  assert.strictEqual(r2.wrote.length, 0);
  assert.strictEqual(fs.readFileSync(installedFile(home), "utf8"), before);
});

t("a NEWER plugin already installed is never downgraded", () => {
  const home = sandbox();
  P.installPlugin({ payload: fakePayload("2.99.0"), home });
  const r = P.installPlugin({ payload: fakePayload("2.64.0"), home });
  assert.strictEqual(r.status, "newer-present");
  assert.strictEqual(r.version, "2.99.0");
  assert.strictEqual(r.wrote.length, 0);
  const inst = readInstalled(home);
  assert.deepStrictEqual(inst.plugins["core@sutra"].map((x) => x.version), ["2.99.0"]);
});

t("an OLDER plugin installed is upgraded, and the old record is kept", () => {
  const home = sandbox();
  P.installPlugin({ payload: fakePayload("2.60.0"), home });
  const r = P.installPlugin({ payload: fakePayload("2.64.0"), home });
  assert.strictEqual(r.status, "installed");
  const versions = readInstalled(home).plugins["core@sutra"].map((x) => x.version);
  assert.deepStrictEqual(versions, ["2.60.0", "2.64.0"]);
});

t("other people's plugins are untouched", () => {
  const home = sandbox();
  const f = installedFile(home);
  fs.mkdirSync(path.dirname(f), { recursive: true });
  fs.writeFileSync(f, JSON.stringify({
    version: 2,
    plugins: { "rust-analyzer-lsp@claude-plugins-official": [{ scope: "user", version: "1.0.0" }] },
  }));
  P.installPlugin({ payload: fakePayload("2.64.0"), home });
  const inst = readInstalled(home);
  assert.ok(inst.plugins["rust-analyzer-lsp@claude-plugins-official"], "other plugin was dropped");
  assert.strictEqual(
    inst.plugins["rust-analyzer-lsp@claude-plugins-official"][0].version, "1.0.0");
});

t("an existing marketplace entry is left exactly as it was", () => {
  const home = sandbox();
  const kmFile = path.join(home, ".claude", "plugins", "known_marketplaces.json");
  fs.mkdirSync(path.dirname(kmFile), { recursive: true });
  const mine = { sutra: { source: { source: "github", repo: "someone/else" },
                          installLocation: "/somewhere", lastUpdated: "2020-01-01T00:00:00Z" } };
  fs.writeFileSync(kmFile, JSON.stringify(mine));
  const r = P.installPlugin({ payload: fakePayload("2.64.0"), home });
  assert.strictEqual(JSON.parse(fs.readFileSync(kmFile, "utf8")).sutra.source.repo, "someone/else");
  assert.ok(r.notes.some((n) => /already known/.test(n)), "the no-op should be reported");
});

t("edited config files are backed up before being rewritten", () => {
  const home = sandbox();
  const f = installedFile(home);
  fs.mkdirSync(path.dirname(f), { recursive: true });
  fs.writeFileSync(f, JSON.stringify({ version: 2, plugins: {} }));
  P.installPlugin({ payload: fakePayload("2.64.0"), home });
  assert.ok(fs.existsSync(f + ".sutra-backup"), "no backup taken before the edit");
});

t("a corrupt installed_plugins.json does not lose the install", () => {
  const home = sandbox();
  const f = installedFile(home);
  fs.mkdirSync(path.dirname(f), { recursive: true });
  fs.writeFileSync(f, "{ this is not json");
  const r = P.installPlugin({ payload: fakePayload("2.64.0"), home });
  assert.strictEqual(r.status, "installed", r.error || "");
  assert.strictEqual(readInstalled(home).plugins["core@sutra"][0].version, "2.64.0");
});

t("a payload with no manifest fails cleanly instead of throwing", () => {
  const home = sandbox();
  const empty = fs.mkdtempSync(path.join(TMPROOT, "bad-"));
  fs.mkdirSync(path.join(empty, "plugin"), { recursive: true });
  const r = P.installPlugin({ payload: empty, home });
  assert.strictEqual(r.status, "failed");
  assert.ok(r.error && r.error.includes("plugin.json"));
});

t("an unwritable ~/.claude is reported, never thrown", () => {
  const home = sandbox();
  const dir = path.join(home, ".claude");
  fs.mkdirSync(dir, { recursive: true });
  fs.chmodSync(dir, 0o500);                       // r-x: cannot create plugins/
  let r;
  try { r = P.installPlugin({ payload: fakePayload("2.64.0"), home }); }
  finally { fs.chmodSync(dir, 0o700); }
  assert.strictEqual(r.status, "failed");
  assert.ok(r.error, "a failure must carry its reason");
});

t("a checkout install (no payload) is skipped, not failed", () => {
  const home = sandbox();
  const r = P.installPlugin({ payload: null, home });
  assert.strictEqual(r.status, "skipped");
});

t("dryRun writes nothing", () => {
  const home = sandbox();
  const r = P.installPlugin({ payload: fakePayload("2.64.0"), home, dryRun: true });
  assert.strictEqual(r.status, "installed");
  assert.ok(!fs.existsSync(path.join(home, ".claude", "plugins", "cache")),
    "dryRun must not create anything");
});

t("alreadyProvisioned flips only after a real install", () => {
  const home = sandbox();
  assert.strictEqual(P.alreadyProvisioned(home), false);
  P.installPlugin({ payload: fakePayload("2.64.0"), home });
  assert.strictEqual(P.alreadyProvisioned(home), true);
});

/* ── report ─────────────────────────────────────────────────────────────── */
let bad = 0;
for (const [name, ok, why] of checks) {
  if (!ok) bad++;
  console.log((ok ? "ok   " : "FAIL ") + "- " + name + (why ? "\n       " + why : ""));
}
fs.rmSync(TMPROOT, { recursive: true, force: true });
console.log("-".repeat(64));
console.log(bad === 0
  ? `provision: ${checks.length} passed, 0 failed`
  : `provision: ${bad} FAILED of ${checks.length}`);
process.exit(bad === 0 ? 0 : 1);
