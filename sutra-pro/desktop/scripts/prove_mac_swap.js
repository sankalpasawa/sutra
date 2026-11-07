#!/usr/bin/env node
'use strict';
/* Proof that the macOS swap helper (src/updater.js macSwapScript) really swaps and really rolls back, on a Mac, with throwaway fake apps.

     node scripts/prove_mac_swap.js [--keep]

   It builds two tiny Sutra Pro.app bundles in a temporary folder whose path has spaces (never /Applications), "installs" the old one, starts it for real
   (through `open`, like the helper does), then runs THE REAL HELPER TEXT with the arguments the updater builds:
     1. success   the new app answers /api/health: the old app is replaced and its backup removed
     2. failure   the new app never answers: the helper kills it, moves the old app back, starts it again, and it answers
     3. refusal   names that do not belong together: the helper exits 2 and touches nothing
   Each fake app is a bundle whose executable is a shell script that execs node under the bundle's own name, so `ps` shows the bundle path like Electron's.
   Exit status 0 only when every check held. Nothing here touches the user's installed Sutra Pro or its data. */
const assert = require('node:assert/strict');
const childProcess = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { macSwapScript, macHelperArgs } = require('../src/updater');

if (process.platform !== 'darwin') {
  console.log('prove_mac_swap: this proof needs a Mac');
  process.exit(0);
}

const KEEP = process.argv.includes('--keep');
const NODE = process.execPath;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const lines = [];
const say = (text) => {
  lines.push(text);
  console.log(text);
};

const SERVER = `
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const [data, label, mode] = process.argv.slice(2);
const server = http.createServer((req, res) => {
  if (req.url === '/api/health' && mode === 'ok') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true, version: label }));
  } else {
    res.writeHead(503, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: false }));
  }
});
server.listen(0, '127.0.0.1', () => {
  fs.mkdirSync(data, { recursive: true });
  fs.writeFileSync(path.join(data, 'app.pid'), process.pid + ' ' + server.address().port + '\\n');
});
const bye = () => { try { fs.rmSync(path.join(data, 'app.pid')); } catch {} process.exit(0); };
process.on('SIGTERM', bye);
process.on('SIGINT', bye);
`;

/* Build `<dir>/Sutra Pro.app` that, when started, serves /api/health as `label` (mode ok) or never says ok (mode silent). */
function buildApp(dir, serverFile, data, label, mode) {
  const app = path.join(dir, 'Sutra Pro.app');
  fs.rmSync(app, { recursive: true, force: true });
  fs.mkdirSync(path.join(app, 'Contents', 'MacOS'), { recursive: true });
  const exe = path.join(app, 'Contents', 'MacOS', 'Sutra Pro');
  fs.writeFileSync(path.join(app, 'Contents', 'Info.plist'), `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>Sutra Pro</string>
<key>CFBundleIdentifier</key><string>os.sutra.pro.swapproof</string>
<key>CFBundleName</key><string>Sutra Pro Swap Proof</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>${label}</string>
<key>CFBundleVersion</key><string>${label}</string>
<key>LSUIElement</key><true/>
</dict></plist>
`);
  // the process shows up as the bundle's own executable, as Electron's does; the path of the exe is spelled by this script itself
  fs.writeFileSync(exe, `#!/bin/bash\nexec -a "$0" '${NODE}' '${serverFile}' '${data}' '${label}' '${mode}'\n`, { mode: 0o755 });
  childProcess.execFileSync('/usr/bin/codesign', ['--force', '--sign', '-', app], { stdio: 'ignore' });
  return app;
}

const versionOf = (app) => childProcess.execFileSync('/usr/bin/plutil', ['-extract', 'CFBundleShortVersionString', 'raw', '-o', '-', path.join(app, 'Contents', 'Info.plist')], { encoding: 'utf8' }).trim();

function health(port) {
  return new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port, path: '/api/health', timeout: 1500, agent: false }, (res) => {
      let body = '';
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch {
          resolve(null);
        }
      });
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
  });
}

function holder(data) {
  try {
    const [pid, port] = fs.readFileSync(path.join(data, 'app.pid'), 'utf8').trim().split(/\s+/).map(Number);
    return { pid, port };
  } catch {
    return null;
  }
}

async function until(check, ms) {
  const end = Date.now() + ms;
  for (;;) {
    const value = await check();
    if (value) return value;
    if (Date.now() > end) return null;
    await sleep(200);
  }
}

const alive = (pid) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

/* The processes whose command starts with the bundle's executable folder, by the path as given and the path the system resolved (a temp folder is behind a link). */
function processesOf(app) {
  const out = childProcess.execFileSync('/bin/ps', ['-axww', '-o', 'pid=,command='], { encoding: 'utf8' });
  const names = [`${app}/Contents/MacOS/`];
  try { names.push(`${fs.realpathSync(app)}/Contents/MacOS/`); } catch { /* the bundle is not there now */ }
  return out.split('\n').filter((line) => names.some((n) => line.trim().slice(line.trim().indexOf(' ') + 1).startsWith(n))).map((line) => Number(line.trim().split(/\s+/)[0]));
}

function startHelper(root, data, app, pid, limit, over = {}) {
  const script = path.join(root, 'apply-update.sh');
  fs.writeFileSync(script, macSwapScript(), { mode: 0o700 });
  const args = macHelperArgs({
    script, pid, app, newApp: `${app}.new`, oldApp: `${app}.old`, badApp: `${app}.bad`, dataDir: data, logFile: path.join(data, 'logs', 'desktop.log'), waitSeconds: limit, ...over,
  });
  fs.mkdirSync(path.join(data, 'logs'), { recursive: true });
  const child = childProcess.spawn('/bin/sh', args, { detached: true, stdio: 'ignore' });
  child.unref();
  return child;
}

function logOf(data) {
  try {
    return fs.readFileSync(path.join(data, 'logs', 'desktop.log'), 'utf8').split('\n').filter((l) => l.includes('update helper')).map((l) => l.replace(/^\S+ desktop: /, ''));
  } catch {
    return [];
  }
}

async function scenario(name, newMode, expectLabel) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'sutra swap proof '));
  const dir = path.join(root, 'My Apps');
  const data = path.join(root, 'data folder');
  fs.mkdirSync(dir, { recursive: true });
  fs.mkdirSync(data, { recursive: true });
  const serverFile = path.join(root, 'fake-server.js');
  fs.writeFileSync(serverFile, SERVER);
  const staging = path.join(root, 'staging');
  fs.mkdirSync(staging);
  const oldBundle = buildApp(dir, serverFile, data, '0.2.0', 'ok');
  const newBundle = buildApp(staging, serverFile, data, '0.3.0', newMode);
  say(`--- ${name}: installed app ${oldBundle}`);
  childProcess.execFileSync('/usr/bin/ditto', [newBundle, `${oldBundle}.new`]);             // what the updater does while the app still runs
  assert.equal(versionOf(oldBundle), '0.2.0');
  childProcess.execFileSync('/usr/bin/open', ['-g', oldBundle]);                           // the "running app": started for real, like the owner's
  const first = await until(async () => { const h = holder(data); return h && (await health(h.port)) ? h : null; }, 20000);
  assert.ok(first, 'the old fake app did not start');
  say(`old app running as pid ${first.pid}, answering ${JSON.stringify(await health(first.port))}`);
  return { root, dir, data, oldBundle, first, newBundle };
}

async function cleanup(ctx) {
  for (const app of [ctx.oldBundle, `${ctx.oldBundle}.new`, `${ctx.oldBundle}.old`, `${ctx.oldBundle}.bad`]) {
    for (const pid of processesOf(app)) {
      try { process.kill(pid, 'SIGKILL'); } catch { /* gone */ }
    }
  }
  if (!KEEP) fs.rmSync(ctx.root, { recursive: true, force: true });
}

async function success() {
  const ctx = await scenario('1. success', 'ok', '0.3.0');
  try {
    const helper = startHelper(ctx.root, ctx.data, ctx.oldBundle, ctx.first.pid, 30);
    await sleep(1500);
    assert.equal(versionOf(ctx.oldBundle), '0.2.0', 'the helper must wait while the app is still running');
    assert.ok(fs.existsSync(`${ctx.oldBundle}.new`), 'the new copy waits beside it');
    say('helper started and is waiting: the installed app is still 0.2.0 while the old app runs');
    process.kill(ctx.first.pid, 'SIGTERM');                                                // the app quits
    assert.ok(await until(() => !alive(ctx.first.pid), 5000));
    const swapped = await until(() => { const h = holder(ctx.data); return h && h.pid !== ctx.first.pid ? h : null; }, 30000);
    assert.ok(swapped, 'the new app did not start');
    const answer = await until(() => health(swapped.port).then((a) => a && a.ok ? a : null), 20000);
    say(`new app running as pid ${swapped.pid}, answering ${JSON.stringify(answer)}`);
    assert.equal(answer.version, '0.3.0');
    const gone = await until(() => !fs.existsSync(`${ctx.oldBundle}.old`) && !fs.existsSync(`${ctx.oldBundle}.new`) && !alive(helper.pid), 30000);
    assert.ok(gone, 'the backup and the staged copy are removed, the helper has ended');
    assert.equal(versionOf(ctx.oldBundle), '0.3.0', 'the installed app is the new one');
    assert.deepEqual(fs.readdirSync(ctx.dir).sort(), ['Sutra Pro.app'], 'nothing is left beside it');
    say(`installed app is now ${versionOf(ctx.oldBundle)}; ${ctx.dir} holds only: ${fs.readdirSync(ctx.dir).join(', ')}`);
    for (const line of logOf(ctx.data)) say(`  log: ${line}`);
    assert.ok(logOf(ctx.data).some((l) => l.includes('the update is done')));
  } finally {
    await cleanup(ctx);
  }
}

async function failure() {
  const ctx = await scenario('2. forced failure (the new app never answers)', 'silent', '0.2.0');
  try {
    startHelper(ctx.root, ctx.data, ctx.oldBundle, ctx.first.pid, 6);
    process.kill(ctx.first.pid, 'SIGTERM');
    await until(() => !alive(ctx.first.pid), 5000);
    const sawNew = await until(() => versionOf(ctx.oldBundle) === '0.3.0' && processesOf(ctx.oldBundle).length > 0, 20000);
    assert.ok(sawNew, 'the new (broken) app was moved in and started');
    const broken = processesOf(ctx.oldBundle);
    say(`the broken new app is in place and running as pid ${broken.join(', ')}; waiting for the helper to give up (6 seconds)`);
    const back = await until(() => { const h = holder(ctx.data); return versionOf(ctx.oldBundle) === '0.2.0' && h && h.pid !== ctx.first.pid ? h : null; }, 60000);
    assert.ok(back, 'the old app was not put back');
    const answer = await until(() => health(back.port).then((a) => a && a.ok ? a : null), 20000);
    say(`rolled back: installed app is ${versionOf(ctx.oldBundle)}, running as pid ${back.pid}, answering ${JSON.stringify(answer)}`);
    assert.equal(answer.version, '0.2.0');
    await until(() => fs.readdirSync(ctx.dir).length === 1, 20000);
    assert.deepEqual(fs.readdirSync(ctx.dir).sort(), ['Sutra Pro.app'], 'the failed copy and the backup are cleaned up');
    assert.ok(await until(() => broken.every((pid) => !alive(pid)), 10000), 'the broken new app was stopped');
    say(`the broken new app (pid ${broken.join(', ')}) is no longer running`);
    for (const line of logOf(ctx.data)) say(`  log: ${line}`);
    assert.ok(logOf(ctx.data).some((l) => l.includes('did not answer')) && logOf(ctx.data).some((l) => l.includes('the old app is back')));
  } finally {
    await cleanup(ctx);
  }
}

async function refusal() {
  const ctx = await scenario('3. refusal (names that do not belong together)', 'ok', '0.3.0');
  try {
    process.kill(ctx.first.pid, 'SIGTERM');
    await until(() => !alive(ctx.first.pid), 5000);
    const helper = startHelper(ctx.root, ctx.data, ctx.oldBundle, ctx.first.pid, 5, { newApp: path.join(ctx.dir, 'Something Else.app') });
    await sleep(2500);
    assert.equal(versionOf(ctx.oldBundle), '0.2.0', 'nothing was swapped');
    assert.ok(fs.existsSync(`${ctx.oldBundle}.new`), 'and the staged copy was not touched');
    say(`refused: installed app still ${versionOf(ctx.oldBundle)}; log: ${logOf(ctx.data).join(' | ')}`);
    assert.ok(logOf(ctx.data).some((l) => l.includes('staging names do not belong')));
    void helper;
  } finally {
    await cleanup(ctx);
  }
}

const ONLY = (process.argv.find((a) => a.startsWith('--only=')) || '').slice(7);
(async () => {
  if (!ONLY || ONLY === 'success') await success();
  if (!ONLY || ONLY === 'failure') await failure();
  if (!ONLY || ONLY === 'refusal') await refusal();
  say('PROOF OK: the swap, the rollback and the refusal all behaved as designed');
})().catch((error) => {
  console.error(`PROOF FAILED: ${error && error.stack ? error.stack : error}`);
  process.exit(1);
});
