'use strict';
/* The two kinds of build (D242): a stable app and a beta that is installed beside it. What matters is that nothing a second copy could collide on is shared,
   that a build's channel comes from one place only, and that the packager gives a beta every name it needs. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const channels = require('../src/channels.json');
const { CHANNELS, channelOf, packageFields, versionLabel, inertUpdates } = require('../src/channel');
const runtime = require('../src/runtime');
const { splashPage, errorPage } = require('../src/pages');
const { judge } = require('../src/selftest');

const load = () => import('../scripts/package.mjs');
const icons = path.resolve(__dirname, '..', '..', 'assets', 'icon');

test('there are two channels, and the stable one is what every release has always been', () => {
  assert.deepEqual(Object.keys(channels), ['stable', 'beta']);
  assert.equal(CHANNELS.stable.appName, 'Sutra Pro');
  assert.equal(CHANNELS.stable.appId, 'os.sutra.pro');
  assert.equal(CHANNELS.stable.dataDirName, '.sutra-pro');
  assert.equal(CHANNELS.stable.updates, true);
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));
  assert.equal(pkg.productName, CHANNELS.stable.appName);
  assert.equal(pkg.name, CHANNELS.stable.packageName);
  assert.equal('sutraChannel' in pkg, false, 'a checkout and a release are stable because package.json names no channel');
});

test('the beta shares no name with the stable app, so both can be installed and open together', () => {
  for (const field of ['appName', 'appId', 'packageName', 'dataDirName', 'iconName', 'icns']) {   // the Windows files (ico, windowsIconName) may be shared: a beta is never built for Windows
    assert.notEqual(CHANNELS.beta[field], CHANNELS.stable[field], field);
  }
  assert.equal(CHANNELS.beta.updates, false, 'a beta never updates itself');
  assert.ok(CHANNELS.beta.appName.endsWith('Beta') && CHANNELS.beta.appId.startsWith(`${CHANNELS.stable.appId}.`));
  assert.ok(!CHANNELS.beta.dataDirName.startsWith(`${CHANNELS.stable.dataDirName}/`) && !`${CHANNELS.stable.dataDirName}`.startsWith(CHANNELS.beta.dataDirName),
    'neither data folder is inside the other');
  for (const channel of Object.values(CHANNELS)) {
    assert.ok(fs.existsSync(path.join(icons, channel.iconName)) && fs.existsSync(path.join(icons, channel.icns)), `${channel.id} has its icons`);
    if (channel.id === 'stable') {                     // the Windows files exist for the app that is built for Windows (a beta is a Mac app)
      assert.ok(fs.existsSync(path.join(icons, channel.windowsIconName)) && fs.existsSync(path.join(icons, channel.ico)), 'the stable app has its Windows icons');
    }
  }
});

test('a build is the channel its package.json names, and a name that does not exist is an error, not the stable app', () => {
  assert.equal(channelOf({}), CHANNELS.stable);
  assert.equal(channelOf({ sutraChannel: '' }), CHANNELS.stable);
  assert.equal(channelOf(null), CHANNELS.stable);
  assert.equal(channelOf({ sutraChannel: 'beta' }), CHANNELS.beta);
  for (const bad of ['Beta', 'nightly', 'toString', '__proto__', 3, true, {}]) {
    assert.throws(() => channelOf({ sutraChannel: bad }), /channel/, String(bad));
  }
});

test('the environment cannot turn a stable app into a beta one, or the other way round', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'src', 'channel.js'), 'utf8');
  assert.equal(/process\.env/.test(source), false, 'channel.js never reads the environment');
  const main = fs.readFileSync(path.join(__dirname, '..', 'src', 'main.js'), 'utf8');
  assert.match(main, /channelOf\(require\('\.\.\/package\.json'\)\)/, 'the app asks the package.json inside it, nothing else');
});

test('the data folder follows the channel, and SUTRA_DATA_DIR still wins for tests', () => {
  assert.equal(runtime.dataDir({}, '/home/u'), path.join('/home/u', '.sutra-pro'));
  assert.equal(runtime.dataDir({}, '/home/u', CHANNELS.beta.dataDirName), path.join('/home/u', '.sutra-pro-beta'));
  assert.equal(runtime.dataDir({ SUTRA_DATA_DIR: '/srv/x' }, '/home/u', CHANNELS.beta.dataDirName), path.resolve('/srv/x'));
});

test('the packager writes the channel and the names Electron derives its own state from into the package.json inside the app', () => {
  assert.deepEqual(packageFields(CHANNELS.beta), { name: 'sutra-pro-desktop-beta', productName: 'Sutra Pro Beta', sutraChannel: 'beta' });
  assert.equal(packageFields(CHANNELS.stable).productName, 'Sutra Pro');
});

test('a beta says which commit it was built from, a release says its version', () => {
  assert.equal(versionLabel(CHANNELS.stable, '0.6.1', { build: 'abc1234' }), '0.6.1');
  assert.equal(versionLabel(CHANNELS.beta, '0.6.1', { build: 'abc1234+changes' }), '0.6.1 beta abc1234+changes');
  assert.equal(versionLabel(CHANNELS.beta, '0.6.1', null), '0.6.1 beta');
  assert.equal(versionLabel(CHANNELS.beta, '0.6.1', { build: 7 }), '0.6.1 beta');
});

test('a build that does not update itself does nothing on a timer and explains itself when asked', async () => {
  const shown = [];
  const updates = inertUpdates({ channel: CHANNELS.beta, info: async (options) => { shown.push(options); } });
  updates.start();
  updates.announce();
  updates.stop();
  assert.equal(updates.autoEligible(), false);
  await updates.applyOnQuit();
  await updates.checkNow({ manual: true });
  assert.equal(shown.length, 1);
  assert.match(shown[0].message, /Sutra Pro Beta does not update itself/);
  assert.match(shown[0].detail, /install_app\.py beta/);
});

test('the pages and the self-test say the build\'s own name', () => {
  assert.match(splashPage({ logo: '', dark: false }), /<h1>Sutra Pro<\/h1>/);
  assert.match(splashPage({ logo: '', dark: false, appName: 'Sutra Pro Beta' }), /<h1>Sutra Pro Beta<\/h1>/);
  assert.match(errorPage({ message: 'x', output: [], logo: '', dark: true, appName: 'Sutra Pro Beta' }), /Sutra Pro Beta could not start/);
  const probe = { readyState: 'complete', href: 'http://127.0.0.1:8781/', title: 't', hasBoot: true, elements: 80, textLength: 90, health: { ok: true, version: '1' } };
  const base = { probe, owned: true, origin: 'http://127.0.0.1:8781', expectVersion: '1' };
  assert.equal(judge({ ...base, windowTitle: 'Sutra Pro Beta', appName: 'Sutra Pro Beta' }).ok, true);
  assert.equal(judge({ ...base, windowTitle: 'Sutra Pro' }).ok, true, 'the stable app is the default');
  assert.equal(judge({ ...base, windowTitle: 'Sutra Pro', appName: 'Sutra Pro Beta' }).ok, false, 'a beta that opened under the stable title is wrong');
});

test('the packager builds the beta as its own app: name, id, icons, and a package.json that names the channel', async () => {
  const { packagerOptions } = await load();
  const stable = packagerOptions({ platform: 'darwin', arch: 'arm64', out: 'out', version: '1.2.3' });
  const beta = packagerOptions({ platform: 'darwin', arch: 'arm64', out: 'out', version: '1.2.3', channel: 'beta' });
  assert.equal(beta.name, 'Sutra Pro Beta');
  assert.equal(beta.appBundleId, 'os.sutra.pro.beta');
  assert.ok(beta.icon.endsWith('sutra-pro-beta.icns') && fs.existsSync(beta.icon));
  assert.deepEqual(beta.extraResource.map((file) => path.basename(file)), ['sutra-pro-beta-1024.png']);
  assert.equal(beta.extraResource.every((file) => fs.existsSync(file)), true);
  assert.equal(beta.sanitizePackageJson.length, 2, 'the default sanitizer is kept and the channel is added after it');
  const sanitized = beta.sanitizePackageJson.reduce((pkg, fn) => fn(pkg), { name: 'sutra-pro-desktop', productName: 'Sutra Pro', main: 'src/main.js', devDependencies: { electron: '1' }, scripts: {} });
  assert.deepEqual(sanitized, { name: 'sutra-pro-desktop-beta', productName: 'Sutra Pro Beta', main: 'src/main.js', sutraChannel: 'beta' });
  assert.equal('sanitizePackageJson' in stable, false, 'what a release ships is what it always was');
  assert.equal(stable.name, 'Sutra Pro');
  assert.equal(stable.appBundleId, 'os.sutra.pro');
  assert.equal(packagerOptions({ platform: 'darwin', arch: 'x64', out: 'o', version: '1.2.3', channel: 'stable' }).name, 'Sutra Pro');
});

test('only a Mac gets a beta, and only a channel that exists', async () => {
  const { packagerOptions } = await load();
  const ok = { platform: 'darwin', arch: 'arm64', out: 'o', version: '1.2.3' };
  assert.throws(() => packagerOptions({ ...ok, platform: 'win32', arch: 'x64', channel: 'beta' }), /Mac app/);
  assert.throws(() => packagerOptions({ ...ok, channel: 'nightly' }), /stable or beta/);
  assert.throws(() => packagerOptions({ ...ok, channel: 'toString' }), /stable or beta/);
});
