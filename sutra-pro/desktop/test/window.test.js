'use strict';
/* The parts of the window that are data: which addresses it may show, the two pages, the menu, the log and the self-test's verdict. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const { isInternal, isSafeExternal } = require('../src/urls');
const { splashPage, errorPage, dataUrl, escapeHtml } = require('../src/pages');
const { menuTemplate } = require('../src/menu');
const { createLog, MAX_BYTES } = require('../src/log');
const { judge } = require('../src/selftest');

// ---------------------------------------------------------------- addresses

test('the window shows its own origin and nothing that merely starts like it', () => {
  const origin = 'http://127.0.0.1:8781';
  assert.equal(isInternal('http://127.0.0.1:8781/d/web/', origin), true);
  assert.equal(isInternal('http://127.0.0.1:8781', origin), true);
  assert.equal(isInternal('http://127.0.0.1:8781.evil.example/', origin), false, 'a prefix test would let this in');
  assert.equal(isInternal('http://127.0.0.1:87810/', origin), false);
  assert.equal(isInternal('http://localhost:8781/', origin), false, 'another host name is another origin');
  assert.equal(isInternal('https://127.0.0.1:8781/', origin), false);
  assert.equal(isInternal('data:text/html,hi', origin), false);
  assert.equal(isInternal('not a url', origin), false);
  assert.equal(isInternal('http://127.0.0.1:8781/', null), false, 'with no server there is no own origin');
});

test('only web addresses go to the browser', () => {
  assert.equal(isSafeExternal('https://example.org/a?b=c'), true);
  assert.equal(isSafeExternal('http://example.org'), true);
  for (const unsafe of ['file:///etc/passwd', 'smb://host/share', 'javascript:alert(1)', 'vscode://x', 'data:text/html,hi', 'ftp://h/f', '', 'nope']) {
    assert.equal(isSafeExternal(unsafe), false, unsafe);
  }
});

// ---------------------------------------------------------------- pages

test('text from outside is escaped, and the pages carry no script and a policy that allows none', () => {
  assert.equal(escapeHtml('<b>"x" & \'y\'</b>'), '&lt;b&gt;&quot;x&quot; &amp; &#39;y&#39;&lt;/b&gt;');
  const page = errorPage({
    message: 'It said <script>alert(1)</script>', output: ['line <img src=x onerror=alert(1)>', 'ok'], logFile: '/home/u/.sutra-pro/logs/desktop.log',
    logo: 'data:image/png;base64,AAAA', dark: true,
  });
  assert.equal(/<script/i.test(page), false);
  assert.equal(page.includes('<img src=x'), false);
  assert.ok(page.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(page.includes("default-src 'none'"));
  assert.ok(page.includes('/home/u/.sutra-pro/logs/desktop.log'));
  assert.ok(page.includes('#161513'), 'the dark theme has the app\'s own background');
});

test('the starting page says what is happening and the light theme has its own colours', () => {
  const page = splashPage({ logo: '', dark: false });
  assert.ok(page.includes('Starting the local server'));
  assert.ok(page.includes('#f6f2ec'));
  assert.ok(page.includes('class="spin"'));
});

test('a page becomes a data address that decodes back to the same page', () => {
  const html = '<p>é — “quoted” 100%</p>';
  const url = dataUrl(html);
  assert.ok(url.startsWith('data:text/html;charset=utf-8,'));
  assert.equal(decodeURIComponent(url.slice(url.indexOf(',') + 1)), html);
});

// ---------------------------------------------------------------- menu

const handlers = { openDataFolder() {}, showLog() {}, openReleases() {} };

test('on a Mac the first menu is the app\'s, and Edit has the roles that make copy and paste work', () => {
  const template = menuTemplate({ appName: 'Sutra Pro', isMac: true, devTools: false, handlers });
  assert.equal(template[0].label, 'Sutra Pro');
  assert.ok(template[0].submenu.some((item) => item.role === 'quit'));
  const edit = template.find((menu) => menu.label === 'Edit');
  const roles = edit.submenu.map((item) => item.role).filter(Boolean);
  for (const role of ['undo', 'redo', 'cut', 'copy', 'paste', 'selectAll']) assert.ok(roles.includes(role), role);
});

test('on Windows the file menu leaves the app, and developer tools appear only when asked for', () => {
  const plain = menuTemplate({ appName: 'Sutra Pro', isMac: false, devTools: false, handlers });
  assert.equal(plain[0].label, 'File');
  assert.deepEqual(plain[0].submenu, [{ role: 'quit', label: 'Exit Sutra Pro' }]);
  const flat = (template) => template.flatMap((menu) => menu.submenu.map((item) => item.role));
  assert.equal(flat(plain).includes('toggleDevTools'), false);
  const dev = menuTemplate({ appName: 'Sutra Pro', isMac: false, devTools: true, handlers });
  assert.equal(flat(dev).includes('toggleDevTools'), true);
  const help = plain.find((menu) => menu.role === 'help');
  assert.deepEqual(help.submenu.filter((item) => item.label).map((item) => item.label), ['Show the Data Folder', 'Show the Log', 'Releases']);
});

// ---------------------------------------------------------------- log

test('the log folder is private and lines carry a time; an old big log is kept as .1', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sutra-log-'));
  const log = createLog(dir, { now: () => new Date('2026-11-05T10:00:00Z') });
  log.write('hello');
  assert.equal(fs.readFileSync(log.file, 'utf8'), '2026-11-05T10:00:00.000Z desktop: hello\n');
  if (process.platform !== 'win32') {
    assert.equal(fs.statSync(dir).mode & 0o777, 0o700);
    assert.equal(fs.statSync(path.join(dir, 'logs')).mode & 0o777, 0o700);
  } else {
    t.diagnostic('POSIX permission bits do not exist on Windows');
  }
  fs.truncateSync(log.file, MAX_BYTES + 1);
  createLog(dir).write('after the rotation');
  assert.ok(fs.existsSync(`${log.file}.1`));
  assert.match(fs.readFileSync(log.file, 'utf8'), /^\S+ desktop: after the rotation\n$/);
});

test('a log that cannot be written is not an error', () => {
  const log = createLog(path.join(os.tmpdir(), 'sutra-no-such', 'a', 'b'));
  log.write('nowhere');                                       // the folder is created when it can be; either way nothing throws
});

// ---------------------------------------------------------------- the self-test's verdict

const GOOD = {
  href: 'http://127.0.0.1:8781/', title: 'Sutra', readyState: 'complete', elements: 400, textLength: 900, hasBoot: true, health: { ok: true, version: '0.2.0' },
};

test('a page that loaded, is the server\'s, drew something and answers health passes', () => {
  assert.deepEqual(judge({ probe: GOOD, owned: true, origin: 'http://127.0.0.1:8781', expectVersion: '0.2.0' }), { ok: true, failures: [] });
});

test('each way the page can be wrong is named', () => {
  const ask = (probe, extra = {}) => judge({ probe: { ...GOOD, ...probe }, owned: true, origin: 'http://127.0.0.1:8781', ...extra }).failures.join('|');
  assert.match(ask({ readyState: 'loading' }), /loading, not complete/);
  assert.match(ask({ href: 'http://127.0.0.1:9/' }), /not the server/);
  assert.match(ask({ title: '' }), /no title/);
  assert.match(ask({ hasBoot: false }), /no boot block/);
  assert.match(ask({ elements: 3 }), /drew 3 elements/);
  assert.match(ask({ textLength: 2 }), /2 characters/);
  assert.match(ask({ health: null }), /health does not say ok/);
  assert.match(ask({ health: { ok: true, version: '0.1.0' } }, { expectVersion: '0.2.0' }), /server is 0\.1\.0, the build is 0\.2\.0/);
  assert.match(judge({ probe: GOOD, owned: false, origin: 'http://127.0.0.1:8781' }).failures.join('|'), /did not start its own server/);
  assert.deepEqual(judge({ probe: null, owned: true, origin: 'x' }), { ok: false, failures: ['the page did not answer the probe'] });
});
