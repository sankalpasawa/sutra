'use strict';
/* The server the window shows (D118): find the one that is running or start our own, wait until it answers, stop it when the app ends.

   A SERVER WE ONLY ATTACHED TO has no process of ours to watch, so it is watched through its health: when it has not answered for `watchMisses` checks in a
   row (3 s apart: 12 s, longer than any answer the server is slow to give) the supervisor reports it as it reports one of its own that died, and the window
   offers Try Again, which attaches to whatever runs by then or starts a server of its own.

   ONE SERVER PER DATA FOLDER. The server holds a lock on <data>/app.lock and writes "<pid> <port>" to <data>/app.pid. When that file names a live
   server that answers /api/health (the command line's, a browser launcher's, an earlier run of this app that crashed), the app ATTACHES to it and
   leaves it running when the app quits. Otherwise it starts its own and stops it on the way out. A pid file is only a claim (a crash leaves one behind, and
   the pid may be reused by any process while the port is another Sutra server's, of another data folder): /api/health does not say which folder
   answers, so the server on the port is asked (/api/config) and turned away when it names another one.

   HOW OUR OWN ENDS. The app holds the write end of the server's standard input and starts it with --exit-when-stdin-closes. Closing the pipe is
   the normal stop, the same on every system, and it is also what happens when the app is killed, so a crash leaves nothing running.
   The ladder when the server does not follow: close the input, wait; ask the system's way (SIGTERM, or on Windows the app.stop file, because a
   process with no console cannot be signalled); wait; kill (SIGKILL, or taskkill /T /F for the tree on Windows). */
const { EventEmitter } = require('node:events');
const childProcess = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const DEFAULT_TIMEOUTS = { start: 60000, poll: 150, stdinGrace: 8000, hardKill: 15000, afterKill: 3000, watchPoll: 3000, watchMisses: 4 };
const RECENT_LINES = 80;

class StartError extends Error {
  constructor(message, { output = [], code = null } = {}) {
    super(message);
    this.name = 'StartError';
    this.output = output;
    this.code = code;
  }
}

/* app.pid: the first line is "<pid> <port>" (a second line of JSON follows; the launcher's file has only the first). */
function parseHolder(text) {
  const words = String(text || '').split(/\r?\n/, 1)[0].trim().split(/\s+/);
  const pid = Number.parseInt(words[0], 10);
  const port = Number.parseInt(words[1] || '0', 10);
  if (!Number.isInteger(pid) || pid <= 0) return null;
  return { pid, port: Number.isInteger(port) && port > 0 && port < 65536 ? port : null };
}

function readHolder(folder) {
  try {
    return parseHolder(fs.readFileSync(path.join(folder, 'app.pid'), 'utf8'));
  } catch {
    return null;
  }
}

/* signal 0 only asks whether the process exists (on Windows too: libuv answers it without terminating anything) */
function pidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === 'EPERM';
  }
}

/* GET `urlPath` on loopback: { status, json } with the parsed body, or null when nothing answered or the body is no JSON. Never rejects, never uses a proxy. */
function getJson(port, urlPath, { timeoutMs = 2000, get = http.get } = {}) {
  return new Promise((resolve) => {
    const request = get({ host: '127.0.0.1', port, path: urlPath, timeout: timeoutMs, agent: false }, (response) => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => {
        body += chunk;
        if (body.length > 1 << 20) response.destroy();
      });
      response.on('error', () => resolve(null));
      response.on('end', () => {
        try {
          resolve({ status: response.statusCode, json: JSON.parse(body) });
        } catch {
          resolve(null);
        }
      });
    });
    request.on('timeout', () => {
      request.destroy();
      resolve(null);
    });
    request.on('error', () => resolve(null));
  });
}

/* GET /api/health on loopback: the parsed answer when it is a Sutra Pro server that says ok, else null. */
async function checkHealth(port, options) {
  const answer = await getJson(port, '/api/health', options);
  return answer && answer.status === 200 && answer.json && answer.json.ok === true ? answer.json : null;
}

/* GET /api/config on loopback: the data folder the server says it serves (as it was told it: absolute when the app or a launcher started it), else null. */
async function fetchDataDir(port, options) {
  const answer = await getJson(port, '/api/config', options);
  const named = answer && answer.status === 200 && answer.json ? answer.json.data_dir : null;
  return typeof named === 'string' && named.trim() ? named : null;
}

/* Is the folder a server names the folder this app means? 'same' or 'other' when the server names an absolute path (spelled any way: a link, a trailing
   slash, another letter case on Windows). 'unknown' when it names nothing or a relative path, which is relative to a folder only that server knows
   (a command line started elsewhere): that is not held against it, so a server that cannot say is taken as every server was before. */
function folderVerdict(reported, ours, { platform = process.platform, realpath = fs.realpathSync.native } = {}) {
  const flavor = platform === 'win32' ? path.win32 : path.posix;
  const named = typeof reported === 'string' ? reported.trim() : '';
  if (!named || !flavor.isAbsolute(named)) return 'unknown';
  const key = (folder) => {
    let resolved = flavor.resolve(folder);
    try {
      resolved = realpath(resolved);
    } catch {
      // not there (yet): its name is all there is
    }
    return platform === 'win32' ? resolved.toLowerCase() : resolved;
  };
  return key(named) === key(ours) ? 'same' : 'other';
}

function describeExit(state) {
  if (state.signal) return `signal ${state.signal}`;
  return `exit status ${state.code}`;
}

class Supervisor extends EventEmitter {
  /* options: dataDir, command, args, env (the server's); log(line); platform; strictPid (the pid in app.pid must be the child's: true for the
     bundled interpreter, false for a venv launcher on Windows); timeouts; and for tests spawn, health, folderOf, readHolder, pidAlive, sleep, now. */
  constructor(options) {
    super();
    this.dataDir = options.dataDir;
    this.command = options.command;
    this.args = options.args;
    this.env = options.env;
    this.platform = options.platform || process.platform;
    this.strictPid = options.strictPid !== false;
    this.log = options.log || (() => {});
    this.timeouts = { ...DEFAULT_TIMEOUTS, ...(options.timeouts || {}) };
    this.spawn = options.spawn || childProcess.spawn;
    this.health = options.health || ((port) => checkHealth(port));
    this.folderOf = options.folderOf || ((port) => fetchDataDir(port));
    this.readHolder = options.readHolder || readHolder;
    this.pidAlive = options.pidAlive || pidAlive;
    this.sleep = options.sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
    this.now = options.now || Date.now;
    this.child = null;                 // the process WE started (null while attached to someone else's)
    this.state = null;                 // { exited, code, signal } of that process
    this.url = null;
    this.owned = false;                // true once our own server answers
    this.recent = [];                  // the last lines it printed
    this.expected = false;             // set when the app asks it to stop, so its exit is not reported as a crash
    this._starting = null;
    this._stopping = null;
    this._cancelled = false;
    this._watcher = null;              // the interval that watches an attached server
    this._turnedAway = new Set();      // "<port> <folder>" of the servers of other folders already logged
  }

  get origin() {
    return this.url ? new URL(this.url).origin : null;
  }

  start() {
    if (!this._starting) {
      this._starting = this._start().finally(() => {
        this._starting = null;
      });
    }
    return this._starting;
  }

  async _start() {
    this._stopping = null;
    this._cancelled = false;
    this.expected = false;
    this.url = null;
    this.owned = false;
    this._turnedAway.clear();
    this._unwatch();
    const attached = await this._attach();
    if (attached) {
      this.log(`attached to the server that is running at ${attached}`);
      this._watch(attached);
      return { url: attached, owned: false };
    }
    const child = this._launch();
    const state = this.state;
    const deadline = this.now() + this.timeouts.start;
    for (;;) {
      if (this._cancelled) {
        await this._stopOurs();
        throw new StartError('The start was cancelled', { output: this.recent.slice() });
      }
      if (state.exited) {
        if (state.code === 0) {                       // another server won the data folder's lock: that one is the one to show
          const url = await this._attach();
          if (url) {
            this.log(`another server was already running: attached to ${url}`);
            this._watch(url);
            return { url, owned: false };
          }
        }
        throw new StartError(`The server stopped while starting (${describeExit(state)})`, { output: this.recent.slice(), code: state.code });
      }
      const holder = this.readHolder(this.dataDir);
      // with strictPid the file is ours by its pid; without it (a launcher's child is the server) only the folder the port serves says so
      if (holder && holder.port && (!this.strictPid || holder.pid === child.pid) && (await this.health(holder.port))
        && (this.strictPid || (await this._servesOurFolder(holder.port)))) {
        this.url = `http://127.0.0.1:${holder.port}/`;
        this.owned = true;
        this.log(`the server is ready at ${this.url} (pid ${child.pid})`);
        return { url: this.url, owned: true };
      }
      if (this.now() >= deadline) {
        await this._stopOurs();
        throw new StartError(`The server did not answer within ${Math.round(this.timeouts.start / 1000)} seconds`, { output: this.recent.slice() });
      }
      await this.sleep(this.timeouts.poll);
    }
  }

  /* Watch an attached server through its health; see the head of this file. The timer never keeps the program alive. */
  _watch(url) {
    this._unwatch();
    const port = Number(new URL(url).port);
    let misses = 0;
    let busy = false;
    const timer = setInterval(async () => {
      if (busy || this.expected) return;
      busy = true;
      try {
        misses = (await this.health(port)) ? 0 : misses + 1;
      } finally {
        busy = false;
      }
      if (misses >= this.timeouts.watchMisses && this._watcher === timer) {
        this._unwatch();
        this.log(`the server at ${url} that this window attached to stopped answering`);
        this.emit('exit', { code: null, signal: null, expected: this.expected, attached: true });
      }
    }, this.timeouts.watchPoll);
    if (typeof timer.unref === 'function') timer.unref();
    this._watcher = timer;
  }

  _unwatch() {
    if (this._watcher) clearInterval(this._watcher);
    this._watcher = null;
  }

  /* The URL of a live server that app.pid names, that answers and that serves this data folder, else null. */
  async _attach() {
    const holder = this.readHolder(this.dataDir);
    if (!holder || !holder.port || !this.pidAlive(holder.pid)) return null;
    if (!(await this.health(holder.port))) return null;
    if (!(await this._servesOurFolder(holder.port))) return null;
    this.url = `http://127.0.0.1:${holder.port}/`;
    this.owned = false;
    return this.url;
  }

  /* Does the server on `port` serve this data folder? Only one that names ANOTHER folder is turned away; see folderVerdict. */
  async _servesOurFolder(port) {
    const reported = await this.folderOf(port);
    if (folderVerdict(reported, this.dataDir) !== 'other') return true;
    const seen = `${port} ${reported}`;
    if (!this._turnedAway.has(seen)) {
      this._turnedAway.add(seen);
      this.log(`the server on port ${port} serves another data folder (${reported}), not ${this.dataDir}: it is not the one to attach to`);
    }
    return false;
  }

  _launch() {
    const child = this.spawn(this.command, this.args, { cwd: this.dataDir, env: this.env, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
    const state = { exited: false, code: null, signal: null };
    this.child = child;
    this.state = state;
    this.recent = [];
    this.log(`starting the server: ${this.command} ${this.args.join(' ')}`);
    const reader = (tag) => {
      let pending = '';
      return (chunk) => {
        pending += chunk;
        let index = pending.indexOf('\n');
        while (index >= 0) {
          this._line(tag, pending.slice(0, index).replace(/\r$/, ''));
          pending = pending.slice(index + 1);
          index = pending.indexOf('\n');
        }
        if (pending.length > 65536) pending = pending.slice(-4096);
      };
    };
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', reader('out'));
    child.stderr.on('data', reader('err'));
    child.stdin.on('error', () => {});                // writing to a server that is already gone
    child.on('error', (error) => {                    // the program could not be started at all (a missing interpreter)
      this._line('err', `could not start ${this.command}: ${error.message}`);
      state.exited = true;
      state.code = -1;
    });
    child.once('exit', (code, signal) => {
      state.exited = true;
      state.code = code;
      state.signal = signal;
      this.log(`the server exited (${describeExit(state)})`);
      if (this.child === child && this.owned) {
        this.owned = false;
        this.emit('exit', { code, signal, expected: this.expected });
      }
    });
    return child;
  }

  _line(tag, text) {
    this.recent.push(text);
    if (this.recent.length > RECENT_LINES) this.recent.shift();
    this.log(`server ${tag}: ${text}`);
  }

  /* Stop what we started. A server we only attached to is left running, as it was found. Safe to call twice and while a start is in flight. */
  stop() {
    if (!this._stopping) this._stopping = this._stop();
    return this._stopping;
  }

  async _stop() {
    this.expected = true;
    this._cancelled = true;
    this._unwatch();
    if (this._starting) await this._starting.catch(() => {});
    await this._stopOurs();
  }

  async _stopOurs() {
    const child = this.child;
    const state = this.state;
    if (!child || state.exited) return;
    this.expected = true;
    const gone = () => state.exited;
    this.log('stopping the server: closing its input');
    try {
      child.stdin.end();
    } catch {
      // the pipe is already closed
    }
    if (await this._waitFor(gone, this.timeouts.stdinGrace)) return;
    this.log('the server did not follow its input: asking it to stop');
    if (this.platform === 'win32') {
      try {
        fs.writeFileSync(path.join(this.dataDir, 'app.stop'), `${process.pid}\n`);
      } catch {
        // the data folder is gone; the kill below still ends it
      }
    } else {
      try {
        child.kill('SIGTERM');
      } catch {
        // already gone
      }
    }
    if (await this._waitFor(gone, Math.max(0, this.timeouts.hardKill - this.timeouts.stdinGrace))) return;
    this.log('the server did not stop: killing it');
    if (this.platform === 'win32' && child.pid) {
      try {
        this.spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true });
      } catch {
        // taskkill is missing: the plain kill below is all there is
      }
    }
    try {
      child.kill('SIGKILL');
    } catch {
      // already gone
    }
    await this._waitFor(gone, this.timeouts.afterKill);
  }

  async _waitFor(predicate, ms) {
    const end = this.now() + ms;
    while (!predicate()) {
      if (this.now() >= end) return false;
      await this.sleep(50);
    }
    return true;
  }
}

module.exports = { Supervisor, StartError, parseHolder, readHolder, pidAlive, checkHealth, fetchDataDir, folderVerdict, DEFAULT_TIMEOUTS };
