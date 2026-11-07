'use strict';
/* The Electron side of the updater (src/updater.js has the rules): the local server as the updater's one source of feed facts, GitHub's download as its
   transport, the system programs it runs, and the native dialogs. The page has no part in any of it.

   THE SERVER. The desktop talks to the server it shows, like the window does. The token of a write is read from the boot block of the server's own page
   (the same place the page reads it; there is no token file), kept in memory, and read again when the server says it is stale. */
const childProcess = require('node:child_process');
const http = require('node:http');
const https = require('node:https');
const { createUpdater, USER_AGENT, cleanSentence } = require('./updater');

const BOOT_BLOCK = /<script type="application\/json" id="sutra-boot">([\s\S]*?)<\/script>/;
const MAX_PAGE_BYTES = 8 * 1024 * 1024;
const PLAN_TIMEOUT_MS = 90 * 1000;                       // the server pages through GitHub's list: up to six requests of 8 seconds
const IDLE_TIMEOUT_MS = 30 * 1000;

/* One request to the local server on loopback. Resolves { status, text }; never uses a proxy. */
function loopback({ port, method, path, headers = {}, body = null, timeoutMs = 20000, limit = MAX_PAGE_BYTES, request = http.request }) {
  return new Promise((resolve, reject) => {
    const payload = body === null ? null : Buffer.from(JSON.stringify(body));
    const req = request({
      host: '127.0.0.1', port, method, path, agent: false, timeout: timeoutMs,
      headers: { ...headers, ...(payload ? { 'Content-Type': 'application/json', 'Content-Length': payload.length } : {}) },
    }, (res) => {
      const chunks = [];
      let total = 0;
      res.on('data', (chunk) => {
        total += chunk.length;
        if (total > limit) {
          res.destroy(new Error('the server answered more than expected'));
          return;
        }
        chunks.push(chunk);
      });
      res.on('error', reject);
      res.on('end', () => resolve({ status: res.statusCode, text: Buffer.concat(chunks).toString('utf8') }));
    });
    req.on('timeout', () => req.destroy(new Error('the server did not answer in time')));
    req.on('error', reject);
    req.end(payload || undefined);
  });
}

/* The server's own sentence for a refusal: { error: { code, message } } -> an Error with .code and .message. */
function refusal(status, text) {
  let code = '';
  let message = `the server answered ${status}`;
  try {
    const parsed = JSON.parse(text);
    if (parsed && parsed.error && typeof parsed.error === 'object') {
      code = typeof parsed.error.code === 'string' ? parsed.error.code : '';
      message = cleanSentence(parsed.error.message) || message;
    }
  } catch {
    // not JSON: the status is all there is
  }
  return Object.assign(new Error(message), { code, status });
}

function localApi({ origin, request = http.request }) {
  const port = () => {
    const found = Number(new URL(origin()).port);
    if (!Number.isInteger(found) || found < 1) throw new Error('the server is not running');
    return found;
  };
  let token = null;
  const readToken = async () => {
    const page = await loopback({ port: port(), method: 'GET', path: '/', request });
    const block = BOOT_BLOCK.exec(page.text);
    const found = block ? JSON.parse(block[1]).token : null;
    if (page.status !== 200 || typeof found !== 'string' || found.length < 16) throw new Error('the server page carries no token');
    token = found;
    return token;
  };
  const send = async (method, path, body, timeoutMs) => {
    for (let attempt = 0; ; attempt += 1) {
      const headers = method === 'GET' ? {} : { 'X-Sutra-Token': token || (await readToken()) };
      const answer = await loopback({ port: port(), method, path, headers, body, timeoutMs, request });
      if (answer.status === 401 && attempt === 0 && method !== 'GET') {            // a server that restarted has a new token
        token = null;
        continue;
      }
      if (answer.status < 200 || answer.status >= 300) throw refusal(answer.status, answer.text);
      return JSON.parse(answer.text);
    }
  };
  return {
    plan: (body) => send('POST', '/api/ops/update-plan', body, PLAN_TIMEOUT_MS),
    setting: async () => {
      try {
        return (await send('GET', '/api/ops/update-setting', null, 10000)).auto !== false;
      } catch {
        return false;                                  // a server that cannot say is not asked to check
      }
    },
    report: (state, version, message) => send('POST', '/api/ops/update-status', { state, version, message }, 10000),
  };
}

/* GET for the download: the transport the updater follows redirects over. A socket idle for 30 seconds is an error. */
function httpsGet(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': USER_AGENT, Accept: 'application/octet-stream' } }, (res) => {
      resolve({ status: res.statusCode, headers: res.headers, stream: res });
    });
    req.setTimeout(IDLE_TIMEOUT_MS, () => req.destroy(new Error('GitHub did not answer in time')));
    req.on('error', reject);
  });
}

/* Run a program with an argument list (no shell). Resolves { code, stdout, stderr } whatever the exit status; a program that cannot start has code -1. */
function run(file, args, { envName, envValue } = {}) {
  return new Promise((resolve) => {
    const env = envName ? { ...process.env, [envName]: envValue } : process.env;
    childProcess.execFile(file, args, { timeout: 5 * 60 * 1000, maxBuffer: 4 * 1024 * 1024, windowsHide: true, env, encoding: 'utf8' }, (error, stdout, stderr) => {
      resolve({ code: error ? (typeof error.code === 'number' ? error.code : -1) : 0, stdout: stdout || '', stderr: stderr || (error && typeof error.code !== 'number' ? error.message : '') });
    });
  });
}

function spawnDetached(file, args, log) {
  const child = childProcess.spawn(file, args, { detached: true, stdio: 'ignore', windowsHide: false });
  child.on('error', (error) => log(`update: could not start ${file}: ${error.message}`));
  child.unref();
}

/* Everything main.js needs: start the timer once the server is up, a check on demand (the menu), the quit hooks. */
function createDesktopUpdates({ app, dialog, shell, supervisor, log, folder, getWindow, isQuitting }) {
  const api = localApi({ origin: () => supervisor.url || '' });
  const frame = () => {
    const win = getWindow();
    return win && !win.isDestroyed() ? win : undefined;
  };
  const box = (options) => {
    const win = frame();
    const full = { type: 'info', title: 'Sutra Pro', noLink: true, ...options };
    return win ? dialog.showMessageBox(win, full) : dialog.showMessageBox(full);
  };
  return createUpdater({
    platform: process.platform, arch: process.arch, version: app.getVersion(), packaged: app.isPackaged, env: process.env, execPath: process.execPath, pid: process.pid,
    dataDir: folder, log: (line) => log.write(line), isQuitting,
    api: { plan: api.plan }, setting: api.setting, report: api.report,
    get: httpsGet, run, spawnDetached: (file, args) => spawnDetached(file, args, (line) => log.write(line)),
    ask: async (question) => (await box(question)).response,
    info: async ({ message, detail }) => {
      await box({ message, detail: detail || '', buttons: ['OK'], defaultId: 0 });
    },
    reveal: (target) => shell.showItemInFolder(target),
    openExternal: (url) => shell.openExternal(url),
    quit: () => app.quit(),
  });
}

module.exports = { createDesktopUpdates, localApi, loopback, refusal, httpsGet, run, spawnDetached, BOOT_BLOCK };
