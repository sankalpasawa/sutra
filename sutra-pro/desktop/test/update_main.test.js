'use strict';
/* The Electron side of the updater that is not Electron: how the app talks to the local server (token from the boot block, a refusal's code), the menu item,
   and the server's environment. A throw-away server on 127.0.0.1 stands in for Sutra Pro's own. */
const assert = require('node:assert/strict');
const http = require('node:http');
const { test } = require('node:test');
const { localApi, refusal, run } = require('../src/update_main');
const { menuTemplate } = require('../src/menu');
const runtime = require('../src/runtime');

const TOKEN = 'token-0123456789abcdef-token';

/* A server that behaves like the parts of Sutra Pro the updater uses. `seen` lists every request; `behave` steers it. */
async function fakeServer(behave = {}) {
  const seen = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
      seen.push({ method: req.method, url: req.url, token: req.headers['x-sutra-token'] || null, body: body ? JSON.parse(body) : null, host: req.headers.host });
      const send = (status, json) => {
        res.writeHead(status, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(json));
      };
      if (req.url === '/') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(`<html><script type="application/json" id="sutra-boot">${JSON.stringify({ page: 'home', token: behave.token || TOKEN })}</script></html>`);
        return;
      }
      if (req.url === '/api/ops/update-setting') return send(200, { auto: behave.auto !== false });
      if (req.url === '/api/ops/update-plan') {
        if (behave.stale && req.headers['x-sutra-token'] !== TOKEN) return send(401, { error: { code: 'bad_token', message: 'A valid X-Sutra-Token header is required' } });
        if (behave.refuse) return send(409, { error: { code: behave.refuse, message: 'Update check is not available while the app runs offline.' } });
        return send(200, { newer: false, latest: '0.2.0' });
      }
      if (req.url === '/api/ops/update-status') return send(200, { ok: true });
      return send(404, { error: { code: 'not_found', message: 'no' } });
    });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}/`;
  return { origin, seen, behave, close: () => new Promise((resolve) => server.close(resolve)) };
}

test('the plan is asked of the local server with the token read from its own page, once', async () => {
  const server = await fakeServer();
  try {
    const api = localApi({ origin: () => server.origin });
    assert.deepEqual(await api.plan({ auto: true, platform: 'darwin', arch: 'arm64' }), { newer: false, latest: '0.2.0' });
    await api.report('ready', '0.3.0', 'Sutra Pro 0.3.0 is ready.');
    assert.deepEqual(server.seen.map((r) => `${r.method} ${r.url}`), ['GET /', 'POST /api/ops/update-plan', 'POST /api/ops/update-status']);
    assert.equal(server.seen[1].token, TOKEN);
    assert.equal(server.seen[2].token, TOKEN, 'the token is kept: the page is not read again');
    assert.deepEqual(server.seen[1].body, { auto: true, platform: 'darwin', arch: 'arm64' });
    assert.deepEqual(server.seen[2].body, { state: 'ready', version: '0.3.0', message: 'Sutra Pro 0.3.0 is ready.' });
    assert.match(server.seen[1].host, /^127\.0\.0\.1:\d+$/, 'a loopback Host, which the server requires');
  } finally {
    await server.close();
  }
});

test('a server that restarted has a new token: a 401 reads the page again, once', async () => {
  const server = await fakeServer({ stale: true, token: 'other-token-0123456789abcdef' });
  try {
    const api = localApi({ origin: () => server.origin });
    await assert.rejects(api.plan({ auto: false }), (error) => error.code === 'bad_token' && error.status === 401);
    assert.equal(server.seen.filter((r) => r.url === '/').length, 2, 'the page was read again, and no more than once more');
  } finally {
    await server.close();
  }
});

test('the server\'s refusals keep their code and sentence', async () => {
  for (const code of ['offline', 'update_off']) {
    const server = await fakeServer({ refuse: code });
    try {
      await assert.rejects(localApi({ origin: () => server.origin }).plan({ auto: true }), (error) => error.code === code && error.status === 409 && /offline/.test(error.message));
    } finally {
      await server.close();
    }
  }
  const odd = refusal(500, '<html>boom</html>');
  assert.equal(odd.code, '');
  assert.match(odd.message, /answered 500/);
});

test('the switch is read from the server, and a server that cannot say is not asked to check', async () => {
  const on = await fakeServer();
  const off = await fakeServer({ auto: false });
  try {
    assert.equal(await localApi({ origin: () => on.origin }).setting(), true);
    assert.equal(await localApi({ origin: () => off.origin }).setting(), false);
    assert.equal(await localApi({ origin: () => '' }).setting(), false, 'no server at all');
    assert.equal(await localApi({ origin: () => 'http://127.0.0.1:9/' }).setting(), false, 'nothing listens there');
  } finally {
    await on.close();
    await off.close();
  }
});

test('a page without a token is not a Sutra Pro page', async () => {
  const server = http.createServer((req, res) => res.end('<html>nothing here</html>'));
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  try {
    const api = localApi({ origin: () => `http://127.0.0.1:${server.address().port}/` });
    await assert.rejects(api.report('failed', null, 'x'));
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('programs run with an argument list and their output comes back whatever the exit status', async () => {
  const ok = await run(process.execPath, ['-e', 'process.stdout.write("out"); process.stderr.write("err")']);
  assert.deepEqual(ok, { code: 0, stdout: 'out', stderr: 'err' });
  const failing = await run(process.execPath, ['-e', 'process.exit(3)']);
  assert.equal(failing.code, 3);
  const missing = await run('/no/such/program', []);
  assert.equal(missing.code, -1);
  const withEnv = await run(process.execPath, ['-e', 'process.stdout.write(process.env.SUTRA_PRO_VERIFY_PATH)'], { envName: 'SUTRA_PRO_VERIFY_PATH', envValue: 'a path with spaces & "quotes"' });
  assert.equal(withEnv.stdout, 'a path with spaces & "quotes"', 'a value reaches the program as it is, with no shell in between');
});

test('the menu has Check for Updates where each system looks for it, and not when nothing handles it', () => {
  const handlers = { openDataFolder() {}, showLog() {}, openReleases() {}, checkForUpdates() {} };
  const labels = (template, which) => template.find((menu) => (which.role ? menu.role === which.role : menu.label === which.label)).submenu.map((item) => item.label).filter(Boolean);
  const mac = menuTemplate({ appName: 'Sutra Pro', isMac: true, devTools: false, handlers });
  assert.deepEqual(labels(mac, { label: 'Sutra Pro' }), ['Check for Updates...']);
  assert.equal(labels(mac, { role: 'help' }).includes('Check for Updates...'), false);
  const win = menuTemplate({ appName: 'Sutra Pro', isMac: false, devTools: false, handlers });
  assert.deepEqual(labels(win, { role: 'help' }), ['Show the Data Folder', 'Show the Log', 'Check for Updates...', 'Releases']);
  const item = win.find((menu) => menu.role === 'help').submenu.find((entry) => entry.label === 'Check for Updates...');
  assert.equal(item.click, handlers.checkForUpdates);
  const bare = menuTemplate({ appName: 'Sutra Pro', isMac: true, devTools: false, handlers: { ...handlers, checkForUpdates: undefined } });
  assert.deepEqual(labels(bare, { label: 'Sutra Pro' }), []);
});

test('the server is told it is the desktop app that runs it', () => {
  const env = runtime.childEnv({ PATH: '/usr/bin' }, { platform: 'darwin', home: '/home/u', dataDir: '/data' });
  assert.equal(env.SUTRA_PRO_DESKTOP, '1');
});
