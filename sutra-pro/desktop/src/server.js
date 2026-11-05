'use strict';
/* The server the window shows (D107): find the one that is running or start our own, wait until it answers, stop it when the app ends.

   ONE SERVER PER DATA FOLDER. The server holds a lock on <data>/app.lock and writes "<pid> <port>" to <data>/app.pid. When that file names a live
   server that answers /api/health (the command line's, a browser launcher's, an earlier run of this app that crashed), the app ATTACHES to it and
   leaves it running when the app quits. Otherwise it starts its own and stops it on the way out.

   HOW OUR OWN ENDS. The app holds the write end of the server's standard input and starts it with --exit-when-stdin-closes. Closing the pipe is
   the normal stop, the same on every system, and it is also what happens when the app is killed, so a crash leaves nothing running.
   The ladder when the server does not follow: close the input, wait; ask the system's way (SIGTERM, or on Windows the app.stop file, because a
   process with no console cannot be signalled); wait; kill (SIGKILL, or taskkill /T /F for the tree on Windows). */
const { EventEmitter } = require('node:events');
const childProcess = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const DEFAULT_TIMEOUTS = { start: 60000, poll: 150, stdinGrace: 8000, hardKill: 15000, afterKill: 3000 };
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

/* GET /api/health on loopback: the parsed answer when it is a Sutra Pro server that says ok, else null. Never rejects, never uses a proxy. */
function checkHealth(port, { timeoutMs = 2000, get = http.get } = {}) {
  return new Promise((resolve) => {
    const request = get({ host: '127.0.0.1', port, path: '/api/health', timeout: timeoutMs, agent: false }, (response) => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => {
        body += chunk;
        if (body.length > 1 << 20) response.destroy();
      });
      response.on('error', () => resolve(null));
      response.on('end', () => {
        try {
          const parsed = JSON.parse(body);
          resolve(response.statusCode === 200 && parsed && parsed.ok === true ? parsed : null);
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

function describeExit(state) {
  if (state.signal) return `signal ${state.signal}`;
  return `exit status ${state.code}`;
}

class Supervisor extends EventEmitter {
  /* options: dataDir, command, args, env (the server's); log(line); platform; strictPid (the pid in app.pid must be the child's: true for the
     bundled interpreter, false for a venv launcher on Windows); timeouts; and for tests spawn, health, readHolder, pidAlive, sleep, now. */
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
    const attached = await this._attach();
    if (attached) {
      this.log(`attached to the server that is running at ${attached}`);
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
            return { url, owned: false };
          }
        }
        throw new StartError(`The server stopped while starting (${describeExit(state)})`, { output: this.recent.slice(), code: state.code });
      }
      const holder = this.readHolder(this.dataDir);
      if (holder && holder.port && (!this.strictPid || holder.pid === child.pid) && (await this.health(holder.port))) {
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

  /* The URL of a live server that app.pid names and that answers, else null. */
  async _attach() {
    const holder = this.readHolder(this.dataDir);
    if (!holder || !holder.port || !this.pidAlive(holder.pid)) return null;
    if (!(await this.health(holder.port))) return null;
    this.url = `http://127.0.0.1:${holder.port}/`;
    this.owned = false;
    return this.url;
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

module.exports = { Supervisor, StartError, parseHolder, readHolder, pidAlive, checkHealth, DEFAULT_TIMEOUTS };
