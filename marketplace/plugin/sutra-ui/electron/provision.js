/* provision.js -- what the DMG has to do that a checkout never needs.
 *
 * Two jobs, both first-launch:
 *
 *   1. RESOLVE THE RUNTIME. A DMG install runs the panel straight out of
 *      Sutra.app/Contents/Resources/payload -- a relocatable CPython with the
 *      dependencies already installed into it (bundle-runtime.sh). A checkout
 *      install still uses install.sh's staged copy under Application Support.
 *      Both are supported; the bundle wins when present, so an operator who has
 *      both does not silently run whichever is older.
 *
 *   2. INSTALL THE CLAUDE CODE PLUGIN. The DMG carries the plugin as well as
 *      the desktop app, and installs it on first launch so one double-click
 *      gets both the panel and the governance hooks.
 *
 * RULES this file does not break:
 *   - It NEVER throws into the launch path. A failed plugin install is
 *     reported, not fatal: the panel is the product, the plugin is a bonus.
 *   - It never removes or downgrades an existing install. A newer plugin
 *     already on disk is left exactly alone and said so.
 *   - Every JSON file it edits is backed up beside itself first, and written
 *     atomically (tmp + rename), because these are Claude Code's own config
 *     files and a half-written one breaks the CLI, not just Sutra.
 *   - It reports every path it wrote, so the first-run screen can show the
 *     user what landed on their machine rather than asking them to trust it.
 *
 * Exported for tests; main.js consumes resolveRuntime() + installPlugin().
 */
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

const MARKETPLACE = "sutra";      // matches .claude-plugin/marketplace.json "name"
const PLUGIN_NAME = "core";       // matches marketplace/plugin/.claude-plugin/plugin.json
const SOURCE_REPO = "sankalpasawa/sutra";

/* ------------------------------------------------------------------ util -- */

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

/* tmp + rename, so a crash mid-write can never leave a truncated config that
   Claude Code then fails to parse. The backup is taken once per file per run. */
function writeJsonAtomic(file, obj, backups) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  if (fs.existsSync(file) && backups && !backups.has(file)) {
    const bak = `${file}.sutra-backup`;
    try { fs.copyFileSync(file, bak); backups.set(file, bak); } catch { /* best effort */ }
  }
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", "utf8");
  fs.renameSync(tmp, file);
}

/* "2.64.0" > "2.9.0" is false as strings and true as versions. Compares the
   numeric prefix of each dotted field; anything unparseable sorts low. */
function cmpVersion(a, b) {
  const pa = String(a || "").split(".");
  const pb = String(b || "").split(".");
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = parseInt(pa[i], 10) || 0;
    const y = parseInt(pb[i], 10) || 0;
    if (x !== y) return x < y ? -1 : 1;
  }
  return 0;
}

function copyTree(src, dst) {
  // dereference:false keeps the Python framework's internal symlinks as
  // symlinks -- resolving them doubles the size and breaks sys.prefix.
  fs.cpSync(src, dst, { recursive: true, dereference: false, force: true });
}

/* --------------------------------------------------------------- runtime -- */

/* Where the app should run the panel from.
 *
 * `resourcesPath` is process.resourcesPath in Electron; tests pass their own.
 * Returns {kind, appDir, python, payload, stamp} or {kind:"none", why}. */
function resolveRuntime(resourcesPath, appDataDir) {
  const bundled = path.join(resourcesPath || "", "payload");
  const bPy = path.join(bundled, "python", "bin", "python3");
  const bApp = path.join(bundled, "plugin", "sutra-ui");
  if (fs.existsSync(bPy) && fs.existsSync(path.join(bApp, "app.py"))) {
    return {
      kind: "bundled",
      appDir: bApp,
      python: bPy,
      payload: bundled,
      stamp: readJson(path.join(bundled, "STAMP"), null),
    };
  }
  // install.sh's layout: Application Support/Sutra/{plugin/sutra-ui,venv}
  const stage = path.join(appDataDir || "", "Sutra");
  const sApp = path.join(stage, "plugin", "sutra-ui");
  const sPy = path.join(stage, "venv", "bin", "python");
  if (fs.existsSync(sPy) && fs.existsSync(path.join(sApp, "app.py"))) {
    return { kind: "staged", appDir: sApp, python: sPy, payload: null, stamp: null };
  }
  return {
    kind: "none",
    why: `No runtime found.\n\nLooked for a bundled one at:\n  ${bPy}\n` +
         `and a staged one at:\n  ${sPy}\n\n` +
         "If you installed from the DMG, the app bundle is incomplete -- " +
         "re-download it. If you are running from a checkout, run install.sh.",
  };
}

/* ---------------------------------------------------------------- plugin -- */

/* Where a previous run recorded what it installed. Outside ~/.claude on
   purpose: this is Sutra's own bookkeeping, not Claude Code's. */
function receiptPath(home) {
  return path.join(home || os.homedir(), ".sutra-ui", "plugin-install.json");
}

/* Install the bundled Claude Code plugin, idempotently.
 *
 * opts: {payload, home, dryRun}
 * Returns a REPORT -- never throws. { status, version, wrote[], notes[], error }
 *   status: "installed" | "already-current" | "newer-present" | "skipped" | "failed"
 */
function installPlugin(opts) {
  const payload = opts.payload;
  const home = opts.home || os.homedir();
  const wrote = [];
  const notes = [];
  const backups = new Map();

  try {
    if (!payload) {
      return { status: "skipped", wrote, notes: ["no bundled payload (checkout install)"] };
    }
    const src = path.join(payload, "plugin");
    const manifest = readJson(path.join(src, ".claude-plugin", "plugin.json"), null);
    if (!manifest || !manifest.version) {
      return { status: "failed", wrote, notes,
               error: `no readable plugin manifest at ${src}/.claude-plugin/plugin.json` };
    }
    const version = String(manifest.version);
    const claude = path.join(home, ".claude");
    const dest = path.join(claude, "plugins", "cache", MARKETPLACE, PLUGIN_NAME, version);
    const key = `${PLUGIN_NAME}@${MARKETPLACE}`;

    // Never downgrade. An operator running a newer plugin from a checkout must
    // not be quietly pushed back to whatever this DMG happened to carry.
    const installedFile = path.join(claude, "plugins", "installed_plugins.json");
    const installed = readJson(installedFile, { version: 2, plugins: {} });
    if (!installed.plugins || typeof installed.plugins !== "object") installed.plugins = {};
    const existing = Array.isArray(installed.plugins[key]) ? installed.plugins[key] : [];
    const newest = existing.reduce(
      (acc, r) => (acc === null || cmpVersion(r.version, acc) > 0 ? r.version : acc), null);
    if (newest !== null && cmpVersion(newest, version) > 0) {
      notes.push(`left alone: ${key} ${newest} is newer than the bundled ${version}`);
      return { status: "newer-present", version: newest, wrote, notes };
    }

    const alreadyOnDisk = fs.existsSync(path.join(dest, ".claude-plugin", "plugin.json"));
    const alreadyRegistered = existing.some((r) => r.version === version);
    if (alreadyOnDisk && alreadyRegistered) {
      return { status: "already-current", version, wrote, notes };
    }
    if (opts.dryRun) {
      notes.push(`would write ${dest}`);
      return { status: "installed", version, wrote: [dest], notes };
    }

    // 1. the plugin files. Staged next door and renamed, so an interrupted copy
    //    never leaves a half-tree that looks like a complete install.
    if (!alreadyOnDisk) {
      const tmp = `${dest}.incoming-${process.pid}`;
      fs.rmSync(tmp, { recursive: true, force: true });
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      copyTree(src, tmp);
      fs.rmSync(dest, { recursive: true, force: true });
      fs.renameSync(tmp, dest);
      wrote.push(dest);
    }

    // 2. the marketplace entry, if Claude Code does not know this one yet.
    const kmFile = path.join(claude, "plugins", "known_marketplaces.json");
    const km = readJson(kmFile, {});
    if (!km[MARKETPLACE]) {
      km[MARKETPLACE] = {
        source: { source: "github", repo: SOURCE_REPO },
        installLocation: path.join(claude, "plugins", "marketplaces", MARKETPLACE),
        lastUpdated: new Date().toISOString(),
      };
      writeJsonAtomic(kmFile, km, backups);
      wrote.push(kmFile);
    } else {
      notes.push(`marketplace "${MARKETPLACE}" was already known -- left as it was`);
    }

    // 3. the install record. Appended to whatever is there; other plugins and
    //    other versions of this one are preserved.
    if (!alreadyRegistered) {
      const now = new Date().toISOString();
      installed.version = installed.version || 2;
      installed.plugins[key] = existing.concat([{
        scope: "user",
        installPath: dest,
        version,
        installedAt: now,
        lastUpdated: now,
        installedBy: "sutra-desktop",
      }]);
      writeJsonAtomic(installedFile, installed, backups);
      wrote.push(installedFile);
    }

    // 4. our own receipt, so the first-run screen can show what happened and a
    //    later run knows it does not need to ask again.
    const receipt = {
      version, installedAt: new Date().toISOString(), wrote,
      backups: Array.from(backups.values()),
    };
    writeJsonAtomic(receiptPath(home), receipt, null);

    return { status: "installed", version, wrote, notes };
  } catch (e) {
    // Deliberately swallowed: the panel must open even when ~/.claude is
    // read-only, on a different volume, or managed by something else.
    return { status: "failed", wrote, notes, error: String((e && e.message) || e) };
  }
}

/* Has the user already been shown the first-run report? */
function alreadyProvisioned(home) {
  return fs.existsSync(receiptPath(home || os.homedir()));
}

module.exports = {
  resolveRuntime, installPlugin, alreadyProvisioned, receiptPath,
  cmpVersion, MARKETPLACE, PLUGIN_NAME,
};
