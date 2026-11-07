'use strict';
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const { Supervisor, StartError, parseHolder, checkHealth, pidAlive } = require('../src/server');

const FIXTURE = path.join(__dirname, 'fixtures', 'fake-server.js');
const POSIX = process.platform !== 'win32';
const FAST = { start: 6000, poll: 20, stdinGrace: 600, hardKill: 1500, afterKill: 1500 };

function tempData() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'sutra-desktop-'));
}

function supervisor(dataDir, mode = 'normal', extra = {}) {
  return new Supervisor({
    dataDir, command: process.execPath, args: [FIXTURE, '--data-dir', dataDir], timeouts: FAST,
    env: { ...process.env, FAKE_MODE: mode, FAKE_DELAY_MS: '3000' }, ...extra,
  });
}

const lines = [];
const noisy = (line) => lines.push(line);

async function eventually(predicate, ms = 4000) {
  const end = Date.now() + ms;
  while (!predicate()) {
    assert.ok(Date.now() < end, 'the condition was not met in time');
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

// ---------------------------------------------------------------- the pieces

test('app.pid: the first line is "<pid> <port>"; a missing or odd file is no holder', () => {
  assert.deepEqual(parseHolder('123 8781\n{"pid":123}\n'), { pid: 123, port: 8781 });
  assert.deepEqual(parseHolder('123\n'), { pid: 123, port: null });             // the lock is held, the port is not bound yet
  assert.deepEqual(parseHolder('123 0\n'), { pid: 123, port: null });
  assert.deepEqual(parseHolder('123 70000\n'), { pid: 123, port: null });
  assert.equal(parseHolder(''), null);
  assert.equal(parseHolder('abc 99\n'), null);
  assert.equal(parseHolder('-5 99\n'), null);
});

test('this process is alive and a process that never existed is not', () => {
  assert.equal(pidAlive(process.pid), true);
  assert.equal(pidAlive(2 ** 22 - 3), false);
});

test('health: only a 200 with ok:true from /api/health counts, and a closed port is null, not an error', async () => {
  const answers = { '/api/health': [200, '{"ok":true,"version":"1"}'] };
  const server = http.createServer((request, response) => {
    const [status, body] = answers[request.url] || [404, '{}'];
    response.statusCode = status;
    response.end(body);
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  assert.deepEqual(await checkHealth(port), { ok: true, version: '1' });
  answers['/api/health'] = [200, '{"ok":false}'];
  assert.equal(await checkHealth(port), null);
  answers['/api/health'] = [503, '{"ok":true}'];
  assert.equal(await checkHealth(port), null);
  answers['/api/health'] = [200, 'not json'];
  assert.equal(await checkHealth(port), null);
  await new Promise((resolve) => server.close(resolve));
  assert.equal(await checkHealth(port), null);
});

// ---------------------------------------------------------------- starting and stopping our own

test('it starts its own server, waits until it answers, and stops it by closing its input', async () => {
  const dir = tempData();
  const s = supervisor(dir, 'normal', { log: noisy });
  const { url, owned } = await s.start();
  assert.match(url, /^http:\/\/127\.0\.0\.1:\d+\/$/);
  assert.equal(owned, true);
  assert.equal(s.owned, true);
  assert.equal(s.origin, new URL(url).origin);
  assert.equal(pidAlive(s.child.pid), true);
  await s.stop();
  assert.equal(s.state.exited, true);
  assert.equal(s.state.code, 0, 'the fake follows its input and exits cleanly');
  assert.equal(fs.existsSync(path.join(dir, 'app.pid')), false, 'the server removed its own pid file');
  await s.stop();                                           // a second stop is harmless
});

test('the server\'s printed lines are kept for an error message and written to the log', async () => {
  const seen = [];
  const dir = tempData();
  const s = supervisor(dir, 'normal', { log: (line) => seen.push(line) });
  await s.start();
  assert.ok(s.recent.some((line) => line.startsWith('Sutra Pro is running at http://127.0.0.1:')));
  assert.ok(seen.some((line) => line.startsWith('server out: Sutra Pro is running at')));
  await s.stop();
});

test('it can start again after it was stopped', async () => {
  const dir = tempData();
  const s = supervisor(dir);
  const first = await s.start();
  await s.stop();
  const second = await s.start();
  assert.equal(second.owned, true);
  assert.notEqual(first.url, undefined);
  await s.stop();
});

test('a server that dies while starting is an error with what it printed and its exit status', async () => {
  const s = supervisor(tempData(), 'crash');
  await assert.rejects(s.start(), (error) => {
    assert.ok(error instanceof StartError);
    assert.match(error.message, /stopped while starting \(exit status 3\)/);
    assert.deepEqual(error.output, ['boom']);
    assert.equal(error.code, 3);
    return true;
  });
  assert.equal(s.owned, false);
});

test('a missing interpreter is an error that names it', async () => {
  const dir = tempData();
  const s = new Supervisor({ dataDir: dir, command: path.join(dir, 'no-such-python'), args: [], env: process.env, timeouts: FAST });
  await assert.rejects(s.start(), (error) => {
    assert.ok(error instanceof StartError);
    assert.ok(error.output.some((line) => line.includes('no-such-python')), error.output.join('|'));
    return true;
  });
});

test('a server that does not answer in time is stopped and reported', async () => {
  const s = supervisor(tempData(), 'slow', { timeouts: { ...FAST, start: 400 } });
  await assert.rejects(s.start(), /did not answer within/);
  assert.equal(s.state.exited, true, 'the slow server was stopped, not left running');
});

test('stopping while the server is still starting cancels the start and stops it', async () => {
  const s = supervisor(tempData(), 'slow', { timeouts: { ...FAST, start: 5000 } });
  const starting = s.start();
  const refused = assert.rejects(starting, /cancelled/);
  await new Promise((resolve) => setTimeout(resolve, 150));
  await s.stop();
  await refused;
  assert.equal(s.state.exited, true);
});

test('a server that dies after it was ready is reported once, as unexpected; one we stop is reported as expected', async (t) => {
  if (!POSIX) return t.skip('a signal that kills the process from outside is a POSIX thing');
  const s = supervisor(tempData());
  const events = [];
  s.on('exit', (event) => events.push(event));
  await s.start();
  process.kill(s.child.pid, 'SIGKILL');
  await eventually(() => events.length === 1);
  assert.equal(events[0].expected, false);
  assert.equal(events[0].signal, 'SIGKILL');
  assert.equal(s.owned, false);

  const t2 = supervisor(tempData());
  const quiet = [];
  t2.on('exit', (event) => quiet.push(event));
  await t2.start();
  await t2.stop();
  assert.deepEqual(quiet, [{ code: 0, signal: null, expected: true }], 'every exit is reported; the one the app asked for says so');
});

// ---------------------------------------------------------------- the ladder

test('a server that ignores its closed input is asked to stop with SIGTERM', async (t) => {
  if (!POSIX) return t.skip('Windows has no SIGTERM: it uses the app.stop file (see the next test)');
  const s = supervisor(tempData(), 'ignore-stdin', { log: noisy });
  await s.start();
  await s.stop();
  assert.equal(s.state.exited, true);
  assert.equal(s.state.code, 0, 'the fake stops itself on SIGTERM');
});

test('a server that ignores everything is killed', async (t) => {
  if (!POSIX) return t.skip('the Windows kill is taskkill, which needs a Windows machine');
  const s = supervisor(tempData(), 'stubborn');
  await s.start();
  await s.stop();
  assert.equal(s.state.exited, true);
  assert.equal(s.state.signal, 'SIGKILL');
});

test('on Windows the second step is the app.stop file, and the last is taskkill for the whole tree', async () => {
  const dir = tempData();
  const spawned = [];
  const killed = [];
  const child = new EventEmitter();
  child.pid = 4242;
  child.stdout = Object.assign(new EventEmitter(), { setEncoding() {} });
  child.stderr = Object.assign(new EventEmitter(), { setEncoding() {} });
  child.stdin = Object.assign(new EventEmitter(), { end() { spawned.push('stdin.end'); } });
  child.kill = (signal) => killed.push(signal);
  fs.writeFileSync(path.join(dir, 'app.pid'), '4242 9\n');
  const s = new Supervisor({
    dataDir: dir, command: 'python', args: [], env: {}, platform: 'win32', timeouts: { start: 1000, poll: 5, stdinGrace: 60, hardKill: 150, afterKill: 80 },
    spawn: (command, args) => {
      if (command === 'taskkill') {
        spawned.push([command, ...args].join(' '));
        return new EventEmitter();
      }
      return child;
    },
    health: async () => ({ ok: true }), readHolder: () => ({ pid: 4242, port: 9 }), pidAlive: () => false,
  });
  await s.start();
  assert.equal(s.owned, true);
  await s.stop();
  assert.ok(fs.existsSync(path.join(dir, 'app.stop')), 'the stop request is a file, because a process with no console cannot be signalled');
  assert.deepEqual(spawned, ['stdin.end', 'taskkill /pid 4242 /T /F']);
  assert.deepEqual(killed, ['SIGKILL']);
});

// ---------------------------------------------------------------- attaching

test('it attaches to a server that is already running, and leaves it running when it stops', async (t) => {
  const dir = tempData();
  const running = supervisor(dir);                          // another program's server, as the command line would have started it
  const { url: theirs } = await running.start();
  const mine = supervisor(dir, 'normal', { spawn: () => assert.fail('a running server must not be started again') });
  const { url, owned } = await mine.start();
  assert.equal(owned, false);
  assert.equal(url, theirs);
  assert.equal(mine.child, null);
  await mine.stop();
  assert.ok(await checkHealth(Number(new URL(theirs).port)), 'the app did not stop a server it did not start');
  await running.stop();
  t.diagnostic('attach works');
});

test('a server we attached to is watched: when it stops answering the app is told, once, as unexpected', async () => {
  const dir = tempData();
  let answering = true;
  const s = new Supervisor({
    dataDir: dir, command: 'python', args: [], env: {}, timeouts: { ...FAST, watchPoll: 15, watchMisses: 3 },
    readHolder: () => ({ pid: process.pid, port: 8789 }), pidAlive: () => true, health: async () => (answering ? { ok: true } : null),
  });
  const events = [];
  s.on('exit', (event) => events.push(event));
  assert.deepEqual(await s.start(), { url: 'http://127.0.0.1:8789/', owned: false });
  await new Promise((resolve) => setTimeout(resolve, 80));
  assert.deepEqual(events, [], 'a server that answers is left alone');
  answering = false;
  await eventually(() => events.length === 1);
  assert.deepEqual(events[0], { code: null, signal: null, expected: false, attached: true });
  await new Promise((resolve) => setTimeout(resolve, 80));
  assert.equal(events.length, 1, 'reported once: the watch ends with the report');
});

test('a slow answer or two is not a death, and stopping ends the watch', async () => {
  const dir = tempData();
  let calls = 0;
  const s = new Supervisor({
    dataDir: dir, command: 'python', args: [], env: {}, timeouts: { ...FAST, watchPoll: 10, watchMisses: 3 },
    readHolder: () => ({ pid: process.pid, port: 8788 }), pidAlive: () => true,
    health: async () => ((++calls % 3 === 0) ? null : { ok: true }),          // every third answer is missing, never three in a row
  });
  const events = [];
  s.on('exit', (event) => events.push(event));
  await s.start();
  await new Promise((resolve) => setTimeout(resolve, 150));
  assert.deepEqual(events, []);
  await s.stop();
  const seen = calls;
  await new Promise((resolve) => setTimeout(resolve, 80));
  assert.equal(calls, seen, 'no check is made after stop');
});

test('a pid file whose process is gone is stale: it is ignored and a new server is started', async () => {
  const dir = tempData();
  fs.writeFileSync(path.join(dir, 'app.pid'), `${2 ** 22 - 3} 9\n`);
  const s = supervisor(dir);
  const { owned } = await s.start();
  assert.equal(owned, true);
  await s.stop();
});

test('a pid file whose process is alive but silent on that port is not a server to attach to', async () => {
  const dir = tempData();
  fs.writeFileSync(path.join(dir, 'app.pid'), `${process.pid} 9\n`);     // alive (this test), but nothing answers on port 9
  const s = supervisor(dir);
  const { owned } = await s.start();
  assert.equal(owned, true);
  await s.stop();
});

test('when another server wins the data folder\'s lock our server exits 0 and the app attaches to the winner', async () => {
  const calls = { holder: 0 };
  const child = new EventEmitter();
  child.pid = 77;
  child.stdout = Object.assign(new EventEmitter(), { setEncoding() {} });
  child.stderr = Object.assign(new EventEmitter(), { setEncoding() {} });
  child.stdin = Object.assign(new EventEmitter(), { end() {} });
  const s = new Supervisor({
    dataDir: tempData(), command: 'python', args: [], env: {}, timeouts: { ...FAST, poll: 5 },
    spawn: () => {
      setTimeout(() => child.emit('exit', 0, null), 30);                  // "Sutra Pro is already running on ..."
      return child;
    },
    readHolder: () => (++calls.holder > 1 ? { pid: 500, port: 8785 } : null),   // nothing at first; the winner's file afterwards
    pidAlive: (pid) => pid === 500,
    health: async (port) => (port === 8785 ? { ok: true } : null),
  });
  assert.deepEqual(await s.start(), { url: 'http://127.0.0.1:8785/', owned: false });
});

test('with strictPid the pid in app.pid must be the child\'s: a foreign holder is not adopted while ours starts', async () => {
  const child = new EventEmitter();
  child.pid = 11;
  child.stdout = Object.assign(new EventEmitter(), { setEncoding() {} });
  child.stderr = Object.assign(new EventEmitter(), { setEncoding() {} });
  child.stdin = Object.assign(new EventEmitter(), { end() { child.emit('exit', 0, null); } });
  let holder = { pid: 999, port: 8790 };                                   // somebody else's file, and a port that answers
  const s = new Supervisor({
    dataDir: tempData(), command: 'python', args: [], env: {}, timeouts: { ...FAST, start: 200, poll: 5 },
    spawn: () => child, readHolder: () => holder, pidAlive: () => false, health: async () => ({ ok: true }),
  });
  await assert.rejects(s.start(), /did not answer/);
  holder = { pid: 11, port: 8791 };
  const t = new Supervisor({
    dataDir: tempData(), command: 'python', args: [], env: {}, timeouts: { ...FAST, poll: 5 },
    spawn: () => child, readHolder: () => holder, pidAlive: () => false, health: async () => ({ ok: true }),
  });
  assert.equal((await t.start()).url, 'http://127.0.0.1:8791/');
  await t.stop();
});
