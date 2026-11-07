'use strict';
/* What scripts/package.mjs hands the packager: the app's identity, its icons, and the short list of what ships in the app archive. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const load = () => import('../scripts/package.mjs');

test('the Mac app is Sutra Pro, os.sutra.pro, with the old Sutra\'s icon', async () => {
  const { packagerOptions } = await load();
  const options = packagerOptions({ platform: 'darwin', arch: 'arm64', out: 'out', version: '0.2.0' });
  assert.equal(options.name, 'Sutra Pro');
  assert.equal(options.appBundleId, 'os.sutra.pro');
  assert.equal(options.appVersion, '0.2.0');
  assert.equal(options.buildVersion, '0.2.0');
  assert.ok(options.icon.endsWith(path.join('assets', 'icon', 'sutra-pro.icns')) && fs.existsSync(options.icon), options.icon);
  assert.ok(options.extraResource.every((file) => fs.existsSync(file)), 'the PNG the window draws its pages with exists');
  assert.equal(options.asar, true);
  assert.equal('win32metadata' in options, false);
});

test('the Windows app is x64, with the same name and the .ico of the same logo', async () => {
  const { packagerOptions } = await load();
  const options = packagerOptions({ platform: 'win32', arch: 'x64', out: 'out', version: '1.2.3' });
  assert.ok(options.icon.endsWith(path.join('assets', 'icon', 'sutra-pro.ico')) && fs.existsSync(options.icon));
  assert.equal(options.win32metadata.ProductName, 'Sutra Pro');
  assert.equal(options.win32metadata.OriginalFilename, 'Sutra Pro.exe');
  assert.equal('appBundleId' in options, false);
});

test('a platform, an architecture or a version it cannot build is refused', async () => {
  const { packagerOptions } = await load();
  const ok = { platform: 'darwin', arch: 'x64', out: 'o', version: '0.2.0' };
  assert.throws(() => packagerOptions({ ...ok, platform: 'linux' }), /darwin or win32/);
  assert.throws(() => packagerOptions({ ...ok, arch: 'ia32' }), /arm64 or x64/);
  assert.throws(() => packagerOptions({ ...ok, platform: 'win32', arch: 'arm64' }), /x64 only/);
  for (const version of ['', '0.2', '0.2.0-beta.1', 'v0.2.0', '01.2.3']) {
    assert.throws(() => packagerOptions({ ...ok, version }), /X\.Y\.Z/, version);
  }
});

test('only package.json and src/ go into the app archive', async () => {
  const { ignored } = await load();
  for (const kept of ['', '/package.json', '/src', '/src/main.js', '/src/deep/er.js']) assert.equal(ignored(kept), false, kept);
  for (const dropped of ['/test', '/test/server.test.js', '/scripts/package.mjs', '/package-lock.json', '/node_modules', '/node_modules/electron/x', '/out',
    '/.gitignore', '/srcx', '/src-old/main.js']) {
    assert.equal(ignored(dropped), true, dropped);
  }
});

test('the versions are exact, so a build is the same build tomorrow', () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));
  for (const [name, range] of Object.entries(pkg.devDependencies)) {
    assert.match(range, /^\d+\.\d+\.\d+$/, `${name} is pinned to ${range}`);
  }
  assert.equal(pkg.productName, 'Sutra Pro');
  assert.equal(pkg.main, 'src/main.js');
  assert.ok(fs.existsSync(path.join(__dirname, '..', 'package-lock.json')), 'the lock file is committed: the release installs with npm ci');
});
