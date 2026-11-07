'use strict';
/* The updater (src/updater.js): versions and channels, hostile answers, the download rules, the checks before anything is installed, the two helpers'
   commands and the timer. The network, the programs it runs and the dialogs are fakes; the files are real, in a temporary folder, so it runs the same on
   Linux, macOS and Windows (a macOS or Windows flow is driven through fakes whatever the system running the test is). */
const assert = require('node:assert/strict');
const childProcess = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { Readable } = require('node:stream');
const { test } = require('node:test');
const u = require('../src/updater');

const VERSION = '0.3.0';
const TEAM = 'ABCDE12345';
const norm = (p) => String(p).replace(/\\/g, '/');
const sha = (buffer) => crypto.createHash('sha256').update(buffer).digest('hex');
const ASSET_BYTES = Buffer.from('a pretend disk image, long enough to hash'.repeat(20));

function tmp() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'sutra-updater-test-'));
}

/* what POST /api/ops/update-plan answers for `platform`/`arch` (the shape the Python route builds) */
function answerFor({ platform = 'darwin', arch = 'arm64', latest = VERSION, size = ASSET_BYTES.length, ...changes } = {}) {
  const name = u.assetFor(platform, arch);
  const url = name ? u.downloadUrl(latest, name) : null;
  return {
    current: '0.2.0', latest, newer: true, url: `https://github.com/sankalpasawa/sutra/releases/tag/sutra-pro-v${latest}`,
    notes_url: `https://github.com/sankalpasawa/sutra/releases/tag/sutra-pro-v${latest}`, how: 'x', kind: 'mac-app', error: null, tag: `sutra-pro-v${latest}`,
    channel: 'stable', asset: name ? { name, url, size, sha256_url: `${url}.sha256` } : null, said: 'x', ...changes,
  };
}

function response(status, body, headers = {}) {
  return { status, headers, stream: Readable.from(body === null || body === undefined ? [] : [Buffer.isBuffer(body) ? body : Buffer.from(body)]) };
}

/* A transport over a table of urls. `seen` is every url asked, in order. */
function transport(routes) {
  const seen = [];
  const get = async (url) => {
    seen.push(url);
    const route = routes[url];
    if (!route) return response(404, 'no');
    return typeof route === 'function' ? route() : response(route.status || 200, route.body, route.headers);
  };
  get.seen = seen;
  return get;
}

/* A whole fake world for one flow. `world.mac` / `world.win` steer the fake programs; `world.calls` records what was run and started. */
function harness({ platform = 'darwin', arch = 'arm64', packaged = true, env = {}, answer, files = {}, mac = {}, win = {}, choices = [], writable = true } = {}) {
  const root = tmp();
  const data = path.join(root, 'data');
  fs.mkdirSync(data, { recursive: true });
  const installDir = path.join(root, 'Applications');
  const bundle = path.join(installDir, 'Sutra Pro.app');
  fs.mkdirSync(path.join(bundle, 'Contents', 'MacOS'), { recursive: true });
  const execPath = platform === 'darwin' ? path.join(bundle, 'Contents', 'MacOS', 'Sutra Pro') : path.join(root, 'Sutra Pro.exe');
  const world = {
    root, data, bundle, installDir, execPath, logs: [], asked: [], infos: [], reports: [], runs: [], spawned: [], revealed: [], opened: [], quits: 0, settingCalls: 0, planCalls: [],
    mac: { runningTeam: TEAM, runningId: 'os.sutra.pro', teamId: TEAM, bundleId: 'os.sutra.pro', version: VERSION, verify: 0, spctl: 0, apps: 1, attach: 0, ditto: 0, ...mac },
    win: { runningSubject: 'CN=Sutra', runningValid: true, subject: 'CN=Sutra', valid: true, ...win },
    setting: true, choices: [...choices], answer: answer === undefined ? answerFor({ platform, arch }) : answer, planError: null,
  };
  const asset = u.assetFor(platform, arch) || 'Sutra-Pro-arm64.dmg';
  const url = u.downloadUrl(VERSION, asset);
  const routes = {
    [url]: { body: ASSET_BYTES, headers: { 'content-length': String(ASSET_BYTES.length) } },
    [`${url}.sha256`]: { body: `${sha(ASSET_BYTES)}  ${asset}\n` },
    ...files,
  };
  world.get = transport(routes);
  world.run = async (file, args, opts = {}) => {
    world.runs.push({ file, args, opts });
    const done = (code = 0, stdout = '', stderr = '') => ({ code, stdout, stderr });
    const f = norm(file);
    if (f.endsWith('/hdiutil')) {
      if (args[0] === 'attach') {
        if (world.mac.attach) return done(world.mac.attach);
        const mountpoint = args[args.indexOf('-mountpoint') + 1];
        if (world.mac.apps === 'file') fs.writeFileSync(path.join(mountpoint, 'Sutra Pro.app'), 'not a bundle');
        else if (world.mac.apps === 'other') fs.mkdirSync(path.join(mountpoint, 'Sutra Pro 2.app'), { recursive: true });
        else if (world.mac.apps === 1) fs.mkdirSync(path.join(mountpoint, 'Sutra Pro.app'), { recursive: true });
      }
      return done();
    }
    if (f.endsWith('/ditto')) {
      if (world.mac.ditto) return done(world.mac.ditto);
      fs.mkdirSync(path.join(args[1], 'Contents'), { recursive: true });
      return done();
    }
    if (f.endsWith('/spctl')) return done(world.mac.spctl);
    if (f.endsWith('/plutil')) {
      const running = norm(args[args.length - 1]) === norm(path.join(bundle, 'Contents', 'Info.plist'));
      const key = args[1];
      if (key === 'CFBundleIdentifier') return done(0, `${running ? world.mac.runningId : world.mac.bundleId}\n`);
      return done(0, `${running ? '0.2.0' : world.mac.version}\n`);
    }
    if (f.endsWith('/codesign')) {
      if (args[0] === '--verify') return done(world.mac.verify);
      const running = norm(args[args.length - 1]) === norm(bundle);
      const team = running ? world.mac.runningTeam : world.mac.teamId;
      return done(0, '', `Identifier=os.sutra.pro\nTeamIdentifier=${team}\nSignature=Developer ID\n`);
    }
    if (f.endsWith('powershell.exe')) {
      const target = opts.envValue;
      const running = norm(target) === norm(execPath);
      const valid = running ? world.win.runningValid : world.win.valid;
      return done(0, `${JSON.stringify({ status: valid ? 'Valid' : 'NotSigned', subject: valid ? (running ? world.win.runningSubject : world.win.subject) : '' })}\n`);
    }
    return done(1, '', 'unexpected');
  };
  const timers = { calls: [], setTimeout(fn, ms) { const h = { fn, ms, kind: 'timeout', cleared: false, unref() {} }; this.calls.push(h); return h; },
    setInterval(fn, ms) { const h = { fn, ms, kind: 'interval', cleared: false, unref() {} }; this.calls.push(h); return h; },
    clearTimeout(h) { h.cleared = true; }, clearInterval(h) { h.cleared = true; } };
  world.timers = timers;
  world.updater = u.createUpdater({
    platform, arch, version: '0.2.0', packaged, env, execPath, pid: 4242, dataDir: data, tmpDir: root,
    log: (line) => world.logs.push(line), timers, isWritable: () => writable,
    api: { plan: async (body) => { world.planCalls.push(body); if (world.planError) throw world.planError; return world.answer; } },
    setting: async () => { world.settingCalls += 1; return world.setting; },
    report: async (state, version, message) => { world.reports.push({ state, version, message }); },
    get: world.get, run: world.run,
    spawnDetached: (file, args) => world.spawned.push({ file, args }),
    ask: async (question) => { world.asked.push(question); return world.choices.length ? world.choices.shift() : 2; },
    info: async (message) => { world.infos.push(message); },
    reveal: (p) => world.revealed.push(p), openExternal: (link) => world.opened.push(link), quit: () => { world.quits += 1; },
  });
  world.staged = path.join(data, 'updates', VERSION, asset);
  return world;
}

const sample = { running: '0.2.0', platform: 'darwin', arch: 'arm64' };


/* Where `$name` is used outside double quotes in a shell text (command substitutions inside quotes count as quoted when their own uses are). */
function unquotedUses(text, name) {
  const stack = [];
  const bad = [];
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const top = stack[stack.length - 1];
    if (ch === "'" && top !== 'dq') {
      i = text.indexOf("'", i + 1);
      continue;
    }
    if (ch === '\\') {
      i += 1;
      continue;
    }
    if (ch === '"') {
      if (top === 'dq') stack.pop();
      else stack.push('dq');
    } else if (ch === '$' && text[i + 1] === '(') {
      stack.push('cmd');
      i += 1;
    } else if (ch === '(' && (top === 'cmd' || top === 'paren')) {
      stack.push('paren');
    } else if (ch === ')' && (top === 'cmd' || top === 'paren')) {
      stack.pop();
    } else if (ch === '$' && text.startsWith(name, i + 1) && !/\w/.test(text[i + 1 + name.length] || '') && top !== 'dq') {
      bad.push(text.slice(Math.max(0, i - 20), i + 20));
    }
  }
  return bad;
}

// ================================================================ versions and channels

test('versions are strict: nine digits at most, no leading zeros, a beta only as -beta.N', () => {
  assert.equal(u.parseVersion('0.2.0').text, '0.2.0');
  assert.equal(u.parseVersion('10.20.30-beta.4').beta, 4);
  for (const bad of ['', '0.2', '01.2.3', '0.2.0-rc.1', 'v0.2.0', '0.2.0 ', '1234567890.0.0', '9'.repeat(5000) + '.0.0', null, 7, {}, '0.2.0b1']) assert.equal(u.parseVersion(bad), null, String(bad));
  assert.equal(u.parseVersion('0.2.0b1', { loose: true }).text, '0.2.0-beta.1', 'the running app may spell a beta the PEP 440 way');
});

test('numbers compare as numbers, and a beta is older than its own stable release', () => {
  const v = (text) => u.parseVersion(text);
  assert.equal(u.compareVersions(v('0.10.0'), v('0.9.0')), 1);
  assert.equal(u.compareVersions(v('0.2.0'), v('0.2.0')), 0);
  assert.equal(u.compareVersions(v('0.2.0-beta.9'), v('0.2.0')), -1);
  assert.equal(u.compareVersions(v('0.2.0-beta.2'), v('0.2.0-beta.1')), 1);
  assert.equal(u.compareVersions(v('0.1.99'), v('0.2.0')), -1);
});

test('a stable install is offered stables only; a beta install is offered betas and stables', () => {
  const v = (text) => u.parseVersion(text);
  assert.equal(u.channelAllows(v('0.2.0'), v('0.3.0-beta.1')), false);
  assert.equal(u.channelAllows(v('0.2.0'), v('0.3.0')), true);
  assert.equal(u.channelAllows(v('0.2.0-beta.1'), v('0.3.0-beta.1')), true);
  assert.equal(u.channelAllows(v('0.2.0-beta.1'), v('0.3.0')), true);
  const beta = u.planFromAnswer(answerFor({ latest: '0.3.0-beta.1' }), sample);
  assert.equal(beta.kind, 'error', 'the server should not offer a beta to a stable install, and if it does it is not taken');
  assert.equal(u.planFromAnswer(answerFor({ latest: '0.3.0-beta.1' }), { ...sample, running: '0.2.0-beta.1' }).ok, true);
});

// ================================================================ the answer of the server

test('a good answer becomes a plan with the address built here', () => {
  const plan = u.planFromAnswer(answerFor(), sample);
  assert.equal(plan.ok, true);
  assert.equal(plan.version, VERSION);
  assert.equal(plan.asset.name, 'Sutra-Pro-arm64.dmg');
  assert.equal(plan.asset.url, 'https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-v0.3.0/Sutra-Pro-arm64.dmg');
  assert.equal(plan.asset.sha256Url, `${plan.asset.url}.sha256`);
  assert.equal(u.planFromAnswer(answerFor({ platform: 'darwin', arch: 'x64' }), { ...sample, arch: 'x64' }).asset.name, 'Sutra-Pro-x86_64.dmg');
  assert.equal(u.planFromAnswer(answerFor({ platform: 'win32', arch: 'x64' }), { ...sample, platform: 'win32', arch: 'x64' }).asset.name, 'Sutra-Pro-Setup-x64.exe');
});

test('nothing newer, an error and a computer without a download are told apart', () => {
  assert.equal(u.planFromAnswer({ ...answerFor(), newer: false }, sample).kind, 'current');
  assert.deepEqual(u.planFromAnswer({ ...answerFor(), error: 'Could not reach GitHub.\u0007' }, sample), { ok: false, kind: 'error', sentence: 'Could not reach GitHub.' });
  const linux = u.planFromAnswer(answerFor({ platform: 'darwin', arch: 'arm64' }), { ...sample, platform: 'linux', arch: 'x64' });
  assert.equal(linux.kind, 'tell');
  assert.equal(linux.version, VERSION);
  assert.equal(u.planFromAnswer(answerFor(), { ...sample, platform: 'win32', arch: 'arm64' }).kind, 'tell');
});

test('hostile answers are refused: wrong types, huge numbers, another host, a path in a name, a version that is not newer', () => {
  const refuse = (changes, why) => {
    const plan = u.planFromAnswer({ ...answerFor(), ...changes }, sample);
    assert.equal(plan.ok, false, why);
    assert.equal(plan.kind === 'error' || plan.kind === 'current', true, why);
  };
  for (const answer of [null, undefined, 'text', 7, [], [answerFor()]]) assert.equal(u.planFromAnswer(answer, sample).ok, false);
  refuse({ latest: '99999999999.0.0' }, 'ten digits');
  refuse({ latest: '9'.repeat(5000) + '.0.0' }, 'five thousand digits');
  refuse({ latest: 7 }, 'a number for a version');
  refuse({ latest: '0.2.0' }, 'not newer than the running 0.2.0');
  refuse({ latest: '0.1.0' }, 'older');
  refuse({ tag: 'sutra-pro-v9.9.9' }, 'a tag that is not the version');
  refuse({ tag: undefined }, 'no tag');
  const asset = answerFor().asset;
  for (const [what, bad] of Object.entries({
    other_host: { ...asset, url: 'https://evil.example/Sutra-Pro-arm64.dmg', sha256_url: 'https://evil.example/Sutra-Pro-arm64.dmg.sha256' },
    look_alike: { ...asset, url: 'https://github.com.evil.example/x', sha256_url: 'https://github.com.evil.example/x.sha256' },
    http: { ...asset, url: asset.url.replace('https', 'http'), sha256_url: asset.sha256_url.replace('https', 'http') },
    userinfo: { ...asset, url: 'https://github.com@evil.example/sankalpasawa/sutra/releases/download/sutra-pro-v0.3.0/Sutra-Pro-arm64.dmg' },
    traversal_name: { ...asset, name: '../../../../etc/passwd' },
    other_name: { ...asset, name: 'Sutra-Pro-x86_64.dmg' },
    traversal_url: { ...asset, url: `${asset.url}/../../x` },
    checksum_elsewhere: { ...asset, sha256_url: 'https://github.com/other/repo/releases/download/x/Sutra-Pro-arm64.dmg.sha256' },
    size_string: { ...asset, size: '5000' }, size_bool: { ...asset, size: true }, size_float: { ...asset, size: 1.5 }, size_zero: { ...asset, size: 0 },
    size_negative: { ...asset, size: -1 }, size_huge: { ...asset, size: 2 ** 40 }, size_unsafe: { ...asset, size: 1e300 }, size_nan: { ...asset, size: NaN },
    asset_array: [asset], asset_text: 'x', asset_missing: null,
  })) {
    refuse({ asset: bad }, what);
  }
});

test('the release page that is shown is a github.com link made of plain URL characters, else the list', () => {
  assert.equal(u.safeReleasePage('https://github.com/sankalpasawa/sutra/releases/tag/sutra-pro-v0.3.0'), 'https://github.com/sankalpasawa/sutra/releases/tag/sutra-pro-v0.3.0');
  for (const bad of ['http://github.com/x', 'https://evil.example/x', 'https://github.com/x y', 'https://github.com/<b>', 'https://github.com/\n', 42, null, 'https://github.com/' + 'a'.repeat(400)]) {
    assert.equal(u.safeReleasePage(bad), u.RELEASES_PAGE, String(bad));
  }
});

test('only https on github.com and githubusercontent.com hosts is allowed, with no credentials and no odd port', () => {
  for (const ok of ['https://github.com/a/b', 'https://objects.githubusercontent.com/x', 'https://release-assets.githubusercontent.com/x?y=1', 'https://githubusercontent.com/x', 'https://github.com:443/a']) {
    assert.equal(u.isAllowedUrl(ok), true, ok);
  }
  for (const bad of ['http://github.com/a', 'https://evilgithub.com/a', 'https://github.com.evil.example/a', 'https://evilgithubusercontent.com/a', 'https://user:pw@github.com/a', 'https://github.com:8443/a',
    'https://127.0.0.1/a', 'file:///etc/passwd', 'ftp://github.com/a', 'not a url', '', 'https://github.com@evil.example/a']) {
    assert.equal(u.isAllowedUrl(bad), false, bad);
  }
});

test('the checksum file is one published line for exactly this asset', () => {
  const hex = 'a'.repeat(64);
  assert.equal(u.parseChecksum(`${hex}  Sutra-Pro-arm64.dmg\n`, 'Sutra-Pro-arm64.dmg'), hex);
  assert.equal(u.parseChecksum(`${hex.toUpperCase()} *Sutra-Pro-arm64.dmg`, 'Sutra-Pro-arm64.dmg'), hex);
  for (const bad of [`${hex}  Other.dmg`, `${hex}`, `${'g'.repeat(64)}  Sutra-Pro-arm64.dmg`, `${hex}  ../Sutra-Pro-arm64.dmg`, '', 'x'.repeat(5000), null, `${'a'.repeat(63)}  Sutra-Pro-arm64.dmg`]) {
    assert.equal(u.parseChecksum(bad, 'Sutra-Pro-arm64.dmg'), null, String(bad).slice(0, 40));
  }
});

// ================================================================ where things go

test('staging paths are built from a version and an asset name of ours, and nothing else', () => {
  const p = u.stagingPaths('/data', '0.3.0', 'Sutra-Pro-arm64.dmg');
  assert.equal(norm(p.file), '/data/updates/0.3.0/Sutra-Pro-arm64.dmg');
  assert.equal(norm(p.part), '/data/updates/0.3.0/Sutra-Pro-arm64.dmg.part');
  for (const [version, name] of [['../0.3.0', 'Sutra-Pro-arm64.dmg'], ['0.3.0', '../x.dmg'], ['0.3.0', 'evil.exe'], ['0.3.0/..', 'Sutra-Pro-arm64.dmg'], ['x', 'Sutra-Pro-arm64.dmg']]) {
    assert.throws(() => u.stagingPaths('/data', version, name), /not a staging name/, `${version} ${name}`);
  }
});

test('the app bundle is found from the executable, and only a bundle named Sutra Pro.app', () => {
  assert.equal(u.bundleOf('/Applications/Sutra Pro.app/Contents/MacOS/Sutra Pro'), '/Applications/Sutra Pro.app');
  assert.equal(u.bundleOf('/Users/x y/Apps/Sutra Pro.app/Contents/MacOS/Sutra Pro'), '/Users/x y/Apps/Sutra Pro.app');
  for (const bad of ['/usr/bin/node', '/Applications/Other.app/Contents/MacOS/Sutra Pro', '/Applications/Sutra Pro.app/Contents/MacOS/a/b', '', null, '/Applications/Sutra Pro.app']) {
    assert.equal(u.bundleOf(bad), null, String(bad));
  }
  const paths = u.installPaths('/Applications/Sutra Pro.app');
  assert.deepEqual([paths.newApp, paths.oldApp, paths.badApp], ['/Applications/Sutra Pro.app.new', '/Applications/Sutra Pro.app.old', '/Applications/Sutra Pro.app.bad']);
});

// ================================================================ the download

test('the download follows a redirect to a GitHub host, lands in a part file and counts every byte', async () => {
  const dir = tmp();
  const dest = path.join(dir, 'x.part');
  const get = transport({
    'https://github.com/a/b': { status: 302, headers: { location: 'https://release-assets.githubusercontent.com/blob?sig=1' } },
    'https://release-assets.githubusercontent.com/blob?sig=1': { body: ASSET_BYTES, headers: { 'content-length': String(ASSET_BYTES.length) } },
  });
  const done = await u.downloadTo({ get, url: 'https://github.com/a/b', dest, expectBytes: ASSET_BYTES.length });
  assert.equal(done.bytes, ASSET_BYTES.length);
  assert.deepEqual(fs.readFileSync(dest), ASSET_BYTES);
  assert.deepEqual(get.seen, ['https://github.com/a/b', 'https://release-assets.githubusercontent.com/blob?sig=1']);
});

test('a redirect to another host, to http, or in a loop is refused, and nothing is left behind', async () => {
  const dir = tmp();
  for (const [name, location] of [['elsewhere', 'https://evil.example/x'], ['plain http', 'http://github.com/x'], ['userinfo', 'https://github.com@evil.example/x'], ['not a url', 'http://']]) {
    const dest = path.join(dir, `${name}.part`);
    const get = transport({ 'https://github.com/a': { status: 302, headers: { location } } });
    await assert.rejects(u.downloadTo({ get, url: 'https://github.com/a', dest }), /not GitHub|could not be read/, name);
    assert.equal(fs.existsSync(dest), false);
    assert.equal(get.seen.length, 1, 'the other host is never asked');
  }
  const loop = transport({ 'https://github.com/a': { status: 302, headers: { location: '/a' } } });
  await assert.rejects(u.downloadTo({ get: loop, url: 'https://github.com/a', dest: path.join(dir, 'loop.part') }), /too many times/);
  assert.equal(loop.seen.length, u.MAX_DOWNLOAD_BYTES > 0 ? 6 : 0, 'five redirects are followed, the sixth is refused');
  const missing = transport({ 'https://github.com/a': { status: 404, body: 'no' } });
  await assert.rejects(u.downloadTo({ get: missing, url: 'https://github.com/a', dest: path.join(dir, 'm.part') }), /answered 404/);
  const first = transport({});
  await assert.rejects(u.downloadTo({ get: first, url: 'https://evil.example/a', dest: path.join(dir, 'e.part') }), /not GitHub/);
  assert.equal(first.seen.length, 0, 'a first address on another host is not even asked');
});

test('a download larger than promised, or cut short, is deleted', async () => {
  const dir = tmp();
  const big = transport({ 'https://github.com/a': { body: Buffer.alloc(100, 1) } });
  const dest = path.join(dir, 'big.part');
  await assert.rejects(u.downloadTo({ get: big, url: 'https://github.com/a', dest, expectBytes: 50 }), /larger than it should be/);
  assert.equal(fs.existsSync(dest), false, 'the part file is removed');
  const announced = transport({ 'https://github.com/a': { body: Buffer.alloc(10), headers: { 'content-length': '999999' } } });
  await assert.rejects(u.downloadTo({ get: announced, url: 'https://github.com/a', dest: path.join(dir, 'a.part'), expectBytes: 50 }), /larger than it should be/);
  const short = transport({ 'https://github.com/a': { body: Buffer.alloc(10) } });
  await assert.rejects(u.downloadTo({ get: short, url: 'https://github.com/a', dest: path.join(dir, 's.part'), expectBytes: 50 }), /ended early/);
  assert.equal(fs.existsSync(path.join(dir, 's.part')), false);
  const capped = transport({ 'https://github.com/a': { body: Buffer.alloc(100) } });
  await assert.rejects(u.downloadTo({ get: capped, url: 'https://github.com/a', dest: path.join(dir, 'c.part'), maxBytes: 10 }), /larger than it should be/, 'the cap holds with no promised size too');
  assert.equal(u.MAX_DOWNLOAD_BYTES, 1024 ** 3, 'one GiB');
  await assert.rejects(u.fetchSmall(transport({ 'https://github.com/a': { body: Buffer.alloc(9000) } }), 'https://github.com/a'), /larger than expected/);
});

// ================================================================ the commands

test('the macOS swap script is a constant: nothing is interpolated, every path comes in as an argument and is quoted', () => {
  const text = u.macSwapScript();
  assert.equal(text, u.macSwapScript(), 'the same text every time');
  assert.equal(u.macSwapScript.length, 0, 'it takes no argument, so nothing can be put into it');
  assert.ok(text.startsWith('#!/bin/sh\n'));
  assert.equal(text.includes('${'), false, 'no parameter expansion that could carry text');
  for (const name of ['app', 'new', 'old', 'bad', 'data', 'log', 'pid', 'limit', 'spid', 'port', 'p', 'c']) {
    assert.deepEqual(unquotedUses(text, name), [], `$${name} is always inside double quotes`);
  }
  assert.ok(text.includes('"$app.new"') && text.includes('"$app.old"') && text.includes('"$app.bad"'), 'only the three neighbours of the installed app are ever removed');
  assert.ok(text.includes('Sutra Pro.app'), 'it refuses anything that is not named Sutra Pro.app');
  assert.ok(text.includes('/api/health'), 'the old app goes only after the new one answered');
  assert.equal(/\beval\b|`/.test(text), false);
  assert.ok(text.indexOf('rm -rf "$old"\n    say "the new app answered') > text.indexOf('healthy'), 'the old app is removed only inside the healthy branch');
});

test('the macOS swap script parses as a shell script', { skip: process.platform === 'win32' && 'no /bin/sh here' }, () => {
  const dir = tmp();
  const script = path.join(dir, 'apply-update.sh');
  fs.writeFileSync(script, u.macSwapScript(), { mode: 0o700 });
  const checked = childProcess.spawnSync('/bin/sh', ['-n', script], { encoding: 'utf8' });
  assert.equal(checked.status, 0, checked.stderr);
});

test('the helper gets each path as one argument, spaces and all, and a made-up path never reaches the script text', () => {
  const args = u.macHelperArgs({
    script: '/Users/a b/.sutra-pro/updates/apply-update.sh', pid: 4242, app: '/Applications/My Apps/Sutra Pro.app', newApp: '/Applications/My Apps/Sutra Pro.app.new',
    oldApp: '/Applications/My Apps/Sutra Pro.app.old', badApp: '/Applications/My Apps/Sutra Pro.app.bad', dataDir: '/Users/a b/.sutra-pro', logFile: '/Users/a b/.sutra-pro/logs/desktop.log',
  });
  assert.deepEqual(args, ['/Users/a b/.sutra-pro/updates/apply-update.sh', '4242', '/Applications/My Apps/Sutra Pro.app', '/Applications/My Apps/Sutra Pro.app.new',
    '/Applications/My Apps/Sutra Pro.app.old', '/Applications/My Apps/Sutra Pro.app.bad', '/Users/a b/.sutra-pro', '/Users/a b/.sutra-pro/logs/desktop.log', '90']);
  for (const arg of args.filter((a) => a.includes('/'))) assert.equal(u.macSwapScript().includes(arg), false, arg);
});

test('every macOS command is a file and an argument list, the mount is read-only and private', () => {
  assert.deepEqual(u.macAttachArgs('/d/x.dmg', '/m'), ['attach', '-nobrowse', '-readonly', '-noverify', '-noautoopen', '-mountpoint', '/m', '/d/x.dmg']);
  assert.deepEqual(u.macDetachArgs('/m', false), ['detach', '/m']);
  assert.deepEqual(u.macDetachArgs('/m', true), ['detach', '/m', '-force']);
  assert.deepEqual(u.codesignVerifyArgs('/a'), ['--verify', '--deep', '--strict', '/a']);
  assert.deepEqual(u.spctlArgs('/a'), ['--assess', '--type', 'execute', '/a']);
  assert.deepEqual(u.dittoArgs('/a', '/b'), ['/a', '/b']);
});

test('the Windows installer is run with the real switches and the signature is read by a constant PowerShell script', () => {
  assert.deepEqual(u.winInstallerArgs(), ['/SILENT', '/CLOSEAPPLICATIONS', '/RESTARTAPPLICATIONS', '/NORESTART', '/SP-', '/SutraRelaunch=1']);
  const command = u.winSignatureCommand({ SystemRoot: 'C:\\Windows' });
  assert.equal(command.file, 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe');
  assert.deepEqual(command.args.slice(0, 3), ['-NoProfile', '-NonInteractive', '-Command']);
  assert.equal(command.args[3], u.WIN_SIGNATURE_SCRIPT);
  assert.ok(command.args[3].includes('$env:SUTRA_PRO_VERIFY_PATH') && command.args[3].includes('-LiteralPath'), 'the path comes through the environment, not the command line');
  assert.equal(command.envName, 'SUTRA_PRO_VERIFY_PATH');
  assert.equal(u.winSignatureCommand({}).file, 'powershell.exe');
  assert.deepEqual(u.parseWinSignature('{"status":"Valid","subject":"CN=Sutra"}\r\n'), { valid: true, subject: 'CN=Sutra' });
  assert.equal(u.parseWinSignature('{"status":"NotSigned","subject":""}').valid, false);
  assert.equal(u.parseWinSignature('{"status":"Valid","subject":""}').valid, false, 'a valid signature with no publisher proves nothing');
  assert.equal(u.parseWinSignature('garbage').valid, false);
});

test('the signature display of codesign is read for the team, and ad hoc is told from a developer id', () => {
  const dev = 'Identifier=os.sutra.pro\nFormat=app bundle\nAuthority=Developer ID Application: X (ABCDE12345)\nTeamIdentifier=ABCDE12345\n';
  assert.deepEqual(u.parseCodesignDisplay(dev), { identifier: 'os.sutra.pro', teamId: 'ABCDE12345', adhoc: false });
  const adhoc = 'Identifier=os.sutra.pro\nCodeDirectory v=20400 size=293 flags=0x2(adhoc) hashes=3+3\nSignature=adhoc\nTeamIdentifier=not set\n';
  assert.deepEqual(u.parseCodesignDisplay(adhoc), { identifier: 'os.sutra.pro', teamId: null, adhoc: true });
  assert.equal(u.parseCodesignDisplay('TeamIdentifier=short').teamId, null);
});

test('a file is hashed through one open handle, and a missing one is an error', async () => {
  const dir = tmp();
  const file = path.join(dir, 'a.bin');
  fs.writeFileSync(file, ASSET_BYTES);
  assert.deepEqual(await u.hashFile(file), { sha256: sha(ASSET_BYTES), size: ASSET_BYTES.length });
  await assert.rejects(u.hashFile(path.join(dir, 'none')));
});

test('only the newest two staged versions are kept', () => {
  const root = tmp();
  for (const v of ['0.2.1', '0.2.2', '0.3.0', '0.10.0', '0.9.0']) fs.mkdirSync(path.join(root, v));
  fs.writeFileSync(path.join(root, 'apply-update.sh'), 'x');
  fs.mkdirSync(path.join(root, 'not-a-version'));
  const gone = u.pruneStaged(root);
  assert.deepEqual(gone.sort(), ['0.2.1', '0.2.2', '0.3.0']);
  assert.deepEqual(fs.readdirSync(root).sort(), ['0.10.0', '0.9.0', 'apply-update.sh', 'not-a-version']);
  assert.deepEqual(u.pruneStaged(root, { keep: 1, protect: ['0.9.0'] }), []);
  assert.deepEqual(u.pruneStaged(path.join(root, 'none')), []);
});

// ================================================================ macOS, the whole flow through fakes

test('macOS: a newer signed app is downloaded, verified, offered, and Restart Now stops the app first and starts the helper only when it has quit', async () => {
  const w = harness({ choices: [0] });
  const result = await w.updater.checkNow({ manual: false });
  assert.equal(result.state, 'restarting');
  assert.deepEqual(w.planCalls, [{ auto: true, platform: 'darwin', arch: 'arm64' }]);
  assert.equal(w.asked.length, 1);
  assert.equal(w.asked[0].message, 'Sutra Pro 0.3.0 is ready.');
  assert.deepEqual(w.asked[0].buttons, ['Restart Now', 'Install on Quit', 'Later']);
  assert.equal(w.quits, 1, 'the app quits through its own path');
  assert.equal(w.spawned.length, 0, 'nothing is swapped before the quit path has run');
  assert.deepEqual(fs.readFileSync(w.staged), ASSET_BYTES);
  assert.equal(fs.existsSync(`${w.bundle}.new`), true, 'the verified copy waits beside the installed app');
  assert.equal(w.updater.pending(), true);
  assert.equal(await w.updater.applyOnQuit(), true);
  assert.equal(w.spawned.length, 1);
  const [{ file, args }] = w.spawned;
  assert.equal(file, '/bin/sh');
  assert.deepEqual(args.slice(1), ['4242', w.bundle, `${w.bundle}.new`, `${w.bundle}.old`, `${w.bundle}.bad`, w.data, path.join(w.data, 'logs', 'desktop.log'), '90']);
  const script = path.join(w.data, 'updates', 'apply-update.sh');
  assert.equal(args[0], script);
  assert.equal(fs.readFileSync(script, 'utf8'), u.macSwapScript());
  if (process.platform !== 'win32') assert.equal(fs.statSync(script).mode & 0o777, 0o700);
  assert.deepEqual(w.reports.map((r) => r.state), ['downloading', 'ready', 'installing']);
  assert.ok(w.logs.some((line) => line.includes('0.3.0 is downloaded and verified')));
  const ran = w.runs.map((r) => `${path.basename(r.file)} ${r.args[0]}`);
  for (const wanted of ['hdiutil attach', 'codesign --verify', 'spctl --assess', 'ditto', 'hdiutil detach']) assert.ok(ran.some((line) => line.startsWith(wanted)) || ran.some((line) => line.startsWith(wanted.split(' ')[0])), wanted);
  assert.equal(w.runs.filter((r) => r.args[0] === 'attach').every((r) => r.args.includes('-readonly') && r.args.includes('-nobrowse')), true);
});

test('macOS: Install on Quit prepares now, quits nothing, and starts the helper when the app quits', async () => {
  const w = harness({ choices: [1] });
  assert.equal((await w.updater.checkNow()).state, 'on_quit');
  assert.equal(w.quits, 0);
  assert.equal(w.updater.pending(), true);
  assert.equal(w.spawned.length, 0);
  assert.equal(await w.updater.applyOnQuit(), true);
  assert.equal(w.spawned.length, 1);
});

test('macOS: Later installs nothing now and nothing at quit, and is not asked again in this session', async () => {
  const w = harness({ choices: [2, 0] });
  assert.equal((await w.updater.checkNow()).state, 'later');
  assert.equal(w.updater.pending(), false);
  assert.equal(await w.updater.applyOnQuit(), false);
  assert.equal(w.spawned.length, 0);
  assert.equal(fs.existsSync(`${w.bundle}.new`), false, 'nothing was copied next to the installed app');
  assert.equal((await w.updater.checkNow()).state, 'ready', 'the 6-hour check does not nag');
  assert.equal(w.asked.length, 1);
  assert.equal(fs.existsSync(w.staged), true, 'the verified download stays for the next launch');
  assert.equal((await w.updater.checkNow({ manual: true })).state, 'restarting', 'a menu click asks again');
  assert.equal(w.asked.length, 2);
});

test('macOS: a checksum that does not match deletes the download and installs nothing', async () => {
  const w = harness({ files: { [`${u.downloadUrl(VERSION, 'Sutra-Pro-arm64.dmg')}.sha256`]: { body: `${'0'.repeat(64)}  Sutra-Pro-arm64.dmg\n` } } });
  const result = await w.updater.checkNow({ manual: true });
  assert.equal(result.state, 'failed');
  assert.equal(fs.existsSync(path.join(w.data, 'updates', VERSION)), false, 'the staged folder is gone');
  assert.equal(w.asked.length, 0, 'the owner is never offered it');
  assert.equal(w.spawned.length, 0);
  assert.equal(w.runs.length === 0 || w.runs.every((r) => r.args[0] === '-dv' || r.args[0] === '-extract'), true, 'nothing was even mounted');
  assert.equal(w.reports.at(-1).state, 'failed');
  assert.match(w.reports.at(-1).message, /did not match its published checksum, so it was deleted and nothing was installed/);
  assert.match(w.infos[0].detail, /nothing was installed/);
  assert.ok(w.logs.some((line) => line.includes('was not used')));
  assert.equal(await w.updater.applyOnQuit(), false);
});

test('macOS: a different Team Identifier, bundle id, a version that is not newer, a failing seal or Gatekeeper each stop the update', async () => {
  const cases = {
    'team': { teamId: 'ZZZZZ99999' }, 'bundle id': { bundleId: 'os.other.app' }, 'same version': { version: '0.2.0' }, 'older version': { version: '0.1.0' },
    'a different version than announced': { version: '0.9.0' }, 'seal': { verify: 1 }, 'gatekeeper': { spctl: 3 }, 'no team at all': { teamId: 'not set' },
    'a file where the app should be': { apps: 'file' }, 'another app, not this one': { apps: 'other' }, 'no app in the image': { apps: 0 }, 'the image will not open': { attach: 1 },
  };
  for (const [name, mac] of Object.entries(cases)) {
    const w = harness({ mac });
    const result = await w.updater.checkNow({ manual: true });
    assert.equal(result.state, 'failed', name);
    assert.equal(fs.existsSync(path.join(w.data, 'updates', VERSION)), false, `${name}: deleted`);
    assert.equal(w.asked.length, 0, name);
    assert.equal(w.spawned.length, 0, name);
    assert.equal(fs.existsSync(`${w.bundle}.new`), false, name);
    const attached = w.runs.filter((r) => r.args[0] === 'attach').length;
    const detached = w.runs.filter((r) => r.args[0] === 'detach').length;
    assert.equal(detached >= (name === 'the image will not open' ? 0 : 1) && (attached === 0 || name === 'the image will not open' || detached >= attached), true, `${name}: the image is always unmounted`);
  }
});

test('macOS: a folder the owner cannot write to is not elevated: the verified app is revealed and the owner is told where to drag it', async () => {
  const w = harness({ choices: [0], writable: false });
  const result = await w.updater.checkNow();
  assert.equal(result.state, 'not_installed');
  assert.equal(w.quits, 0);
  assert.equal(w.updater.pending(), false);
  assert.equal(w.revealed.length, 1);
  assert.equal(path.basename(w.revealed[0]), 'Sutra Pro.app');
  assert.ok(norm(w.revealed[0]).includes('/updates/0.3.0/'), 'the verified copy lives in the staging folder');
  assert.match(w.infos[0].detail, /not writable by you/);
  assert.match(w.infos[0].detail, /Drag the Sutra Pro that just opened/);
  assert.equal(w.spawned.length, 0);
  assert.equal(fs.existsSync(`${w.bundle}.new`), false);
});

test('macOS: a copy that cannot be made, or one that fails its check after copying, leaves the installed app untouched', async () => {
  const w = harness({ choices: [0], mac: { ditto: 1 } });
  assert.equal((await w.updater.checkNow()).state, 'not_installed');
  assert.equal(w.quits, 0);
  assert.equal(fs.existsSync(`${w.bundle}.new`), false);
  assert.match(w.infos[0].detail, /nothing was changed/);
  assert.equal(fs.existsSync(path.join(w.bundle, 'Contents', 'MacOS')), true, 'the installed app is where it was');
});

test('a copy that cannot tell who signed it (ad hoc, a checkout) only tells, downloads nothing and never installs', async () => {
  for (const [name, options, wanted] of [
    ['ad hoc', { mac: { runningTeam: 'not set' } }, /not signed with a developer certificate/],
    ['a checkout', { packaged: false }, /source checkout/],
  ]) {
    const w = harness({ choices: [0], ...options });
    const result = await w.updater.checkNow({ manual: true });
    assert.equal(result.state, 'tell_only', name);
    assert.equal(w.get.seen.length, 0, `${name}: nothing downloaded`);
    assert.match(w.asked[0].detail, wanted, name);
    assert.deepEqual(w.asked[0].buttons, ['Open the Release Page', 'Later']);
    assert.deepEqual(w.opened, ['https://github.com/sankalpasawa/sutra/releases/tag/sutra-pro-v0.3.0'], name);
    assert.equal(w.reports.at(-1).state, 'tell_only', name);
    assert.match(w.reports.at(-1).message, /Download it from the release page/);
    assert.equal(w.quits, 0);
    assert.equal(w.spawned.length, 0);
    assert.equal(await w.updater.applyOnQuit(), false);
  }
});

test('a version already downloaded and still valid is checked again, not downloaded again', async () => {
  const w = harness({ choices: [2] });
  await w.updater.checkNow();
  const downloads = w.get.seen.length;
  assert.equal(downloads, 2, 'the checksum and the file');
  const again = harness({ choices: [2] });
  fs.cpSync(path.join(w.data, 'updates'), path.join(again.data, 'updates'), { recursive: true });
  const result = await again.updater.checkNow();
  assert.equal(result.state, 'later');
  assert.equal(again.get.seen.length, 0, 'a launch later, the staged file is verified again and offered with no download');
  assert.equal(again.asked.length, 1);
  assert.ok(again.runs.some((r) => r.args[0] === 'attach'), 'and verified again');
});

test('a tampered staged file is deleted and downloaded fresh', async () => {
  const w = harness({ choices: [2] });
  await w.updater.checkNow();
  fs.appendFileSync(w.staged, 'tampered');
  const again = harness({ choices: [2] });
  fs.cpSync(path.join(w.data, 'updates'), path.join(again.data, 'updates'), { recursive: true });
  assert.equal((await again.updater.checkNow()).state, 'later');
  assert.equal(again.get.seen.length, 2, 'fresh download');
  assert.deepEqual(fs.readFileSync(again.staged), ASSET_BYTES);
  assert.ok(again.logs.some((line) => line.includes('no longer checks out')));
});

// ================================================================ Windows, through fakes

test('Windows: a signed installer from the same publisher is offered and, at quit, run detached with the real switches', async () => {
  const w = harness({ platform: 'win32', arch: 'x64', choices: [0] });
  assert.equal((await w.updater.checkNow()).state, 'restarting');
  assert.equal(w.quits, 1);
  assert.equal(w.spawned.length, 0, 'not before the quit path');
  assert.equal(await w.updater.applyOnQuit(), true);
  assert.deepEqual(w.spawned, [{ file: w.staged, args: u.winInstallerArgs() }]);
  assert.equal(path.basename(w.spawned[0].file), 'Sutra-Pro-Setup-x64.exe');
  const checks = w.runs.filter((r) => r.file.endsWith('powershell.exe'));
  assert.ok(checks.length >= 3, 'the running exe, the download, and again just before it is run');
  assert.ok(checks.every((r) => r.args[3] === u.WIN_SIGNATURE_SCRIPT && r.opts.envName === 'SUTRA_PRO_VERIFY_PATH'));
});

test('Windows: another publisher, an invalid signature or a changed file stops the installer', async () => {
  for (const [name, win] of [['publisher', { subject: 'CN=Someone Else' }], ['invalid', { valid: false }]]) {
    const w = harness({ platform: 'win32', arch: 'x64', win });
    assert.equal((await w.updater.checkNow({ manual: true })).state, 'failed', name);
    assert.equal(fs.existsSync(path.join(w.data, 'updates', VERSION)), false, name);
    assert.equal(w.spawned.length, 0, name);
    assert.equal(w.asked.length, 0, name);
  }
  const w = harness({ platform: 'win32', arch: 'x64', choices: [1] });
  await w.updater.checkNow();
  fs.appendFileSync(w.staged, 'changed after it was checked');
  assert.equal(await w.updater.applyOnQuit(), false, 'the file is hashed again before it is run');
  assert.equal(w.spawned.length, 0);
});

test('Windows: an unsigned running app (today\'s builds) only tells', async () => {
  const w = harness({ platform: 'win32', arch: 'x64', win: { runningValid: false } });
  assert.equal((await w.updater.checkNow({ manual: true })).state, 'tell_only');
  assert.equal(w.get.seen.length, 0);
  assert.match(w.asked[0].detail, /not signed with a developer certificate/);
});

// ================================================================ when it asks, and when it does not

test('the timer: a minute after launch, then every six hours, never keeping the app alive, and cleared at quit', async () => {
  const w = harness();
  assert.equal(w.updater.start(), true);
  assert.equal(w.updater.start(), false, 'once');
  const [first] = w.timers.calls;
  assert.equal(first.kind, 'timeout');
  assert.equal(first.ms, 60 * 1000);
  first.fn();
  const every = w.timers.calls.find((c) => c.kind === 'interval');
  assert.equal(every.ms, 6 * 60 * 60 * 1000);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(w.settingCalls, 1, 'the first check read the switch');
  w.updater.stop();
  assert.equal(every.cleared, true, 'the interval is cleared on quit');
  assert.equal(w.updater.start(), false, 'and does not start again');
  assert.deepEqual((await w.updater.checkNow({ manual: true })).state, 'quitting', 'no dialog during the quit');
  const early = harness();
  early.updater.start();
  early.updater.stop();
  assert.equal(early.timers.calls[0].cleared, true, 'a quit before the first check clears the one-shot too');
});

test('no automatic check in offline mode, with the stub connector, in the self-test, unpackaged, or on a computer with no download', async () => {
  const none = [{ SUTRA_OFFLINE: '1' }, { SUTRA_OFFLINE: 'true' }, { SUTRA_CONNECTOR: 'stub' }, { SUTRA_CONNECTOR: 'STUB' }, { SUTRA_PRO_SELFTEST: '1' }];
  for (const env of none) {
    const w = harness({ env });
    assert.equal(w.updater.start(), false, JSON.stringify(env));
    assert.equal(w.timers.calls.length, 0, JSON.stringify(env));
    assert.equal((await w.updater.checkNow({ manual: false })).state, 'skipped', JSON.stringify(env));
    assert.equal(w.planCalls.length, 0, 'no request is made');
    assert.equal(w.settingCalls, 0);
  }
  const unpackaged = harness({ packaged: false });
  assert.equal(unpackaged.updater.start(), false);
  const linux = harness({ platform: 'linux', arch: 'x64' });
  assert.equal(linux.updater.start(), false);
  assert.equal(harness({ env: { SUTRA_OFFLINE: '0' } }).updater.start(), true, 'a false value does not count');
});

test('with the setting off the timer asks nothing; a menu click still asks', async () => {
  const w = harness({ choices: [2] });
  w.setting = false;
  assert.equal((await w.updater.checkNow({ manual: false })).state, 'skipped');
  assert.equal(w.settingCalls, 1);
  assert.equal(w.planCalls.length, 0, 'no request to the server, so none to GitHub');
  assert.ok(w.logs.some((line) => line.includes('switched off')));
  assert.equal((await w.updater.checkNow({ manual: true })).state, 'later');
  assert.deepEqual(w.planCalls, [{ auto: false, platform: 'darwin', arch: 'arm64' }]);
});

test('a menu click says so offline and when the server declines, and the timer stays silent', async () => {
  const w = harness({ env: { SUTRA_OFFLINE: '1' } });
  assert.equal((await w.updater.checkNow({ manual: true })).state, 'offline');
  assert.match(w.infos[0].message, /not available offline/);
  assert.equal(w.planCalls.length, 0);
  for (const code of ['offline', 'update_off']) {
    const declined = harness();
    declined.planError = Object.assign(new Error('refused'), { code });
    assert.equal((await declined.updater.checkNow({ manual: false })).state, 'skipped', code);
    assert.equal(declined.infos.length, 0, 'no dialog from the timer');
  }
});

test('up to date, a failed question and a hostile answer', async () => {
  const w = harness({ answer: { ...answerFor(), newer: false } });
  assert.equal((await w.updater.checkNow({ manual: true })).state, 'current');
  assert.equal(w.infos[0].message, 'You are up to date.');
  assert.equal((await w.updater.checkNow({ manual: false })).state, 'current');
  assert.equal(w.infos.length, 1, 'the timer says nothing when there is nothing to say');
  const failing = harness();
  failing.planError = new Error('connect ECONNREFUSED');
  assert.equal((await failing.updater.checkNow({ manual: true })).state, 'error');
  assert.match(failing.infos[0].detail, /ECONNREFUSED/);
  const hostile = harness({ answer: answerFor({ asset: { ...answerFor().asset, url: 'https://evil.example/x' } }) });
  assert.equal((await hostile.updater.checkNow({ manual: true })).state, 'error');
  assert.equal(hostile.get.seen.length, 0, 'the other host is never asked');
  assert.equal(hostile.runs.length, 0);
});

test('a second check while one runs is not started', async () => {
  const w = harness({ choices: [2] });
  const [a, b] = await Promise.all([w.updater.checkNow(), w.updater.checkNow()]);
  assert.deepEqual([a.state, b.state].sort(), ['busy', 'later']);
});
