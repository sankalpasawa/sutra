'use strict';
/* A stand-in for `python -m sutra_app`, run by the supervisor tests with node. It does what the real server does where the app can see it: serves
   /api/health on a free port, writes "<pid> <port>" to <data>/app.pid, prints where it runs, and stops when its standard input ends.
   FAKE_MODE chooses how it misbehaves:
     normal         follows its input and SIGTERM
     ignore-stdin   ignores the end of its input (an old server without --exit-when-stdin-closes); SIGTERM still stops it
     stubborn       ignores the end of its input and SIGTERM: only a kill ends it
     crash          prints "boom" and exits 3 at once
     already        prints that another server runs and exits 0 at once
     slow           waits FAKE_DELAY_MS before it listens
   FAKE_CONFIG chooses what /api/config says about the data folder (the real server answers its --data-dir as it was given):
     normal         {data_dir: <the --data-dir argument>}
     relative       {data_dir: <the folder's name only>}
     none           404, as an old server that has no such route */
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const mode = process.env.FAKE_MODE || 'normal';
const dataDir = process.argv[process.argv.indexOf('--data-dir') + 1];
const pidFile = path.join(dataDir, 'app.pid');

if (mode === 'crash') {
  process.stderr.write('boom\n');
  process.exit(3);
}
if (mode === 'already') {
  process.stdout.write('Sutra Pro is already running on http://127.0.0.1:1/\n');
  process.exit(0);
}

const configMode = process.env.FAKE_CONFIG || 'normal';

const server = http.createServer((request, response) => {
  if (request.url === '/api/health') {
    response.setHeader('content-type', 'application/json');
    response.end(JSON.stringify({ ok: true, version: '0.0.0-test' }));
  } else if (request.url === '/api/config' && configMode !== 'none') {
    response.setHeader('content-type', 'application/json');
    response.end(JSON.stringify({ data_dir: configMode === 'relative' ? path.basename(dataDir) : dataDir, offline: true }));
  } else {
    response.statusCode = 404;
    response.end('{}');
  }
});

function stop() {
  try {
    fs.unlinkSync(pidFile);
  } catch {
    // already gone
  }
  server.close();
  process.exit(0);
}

if (mode !== 'stubborn') process.on('SIGTERM', stop);
else process.on('SIGTERM', () => {});
if (mode === 'normal' || mode === 'slow') process.stdin.on('end', stop);
process.stdin.resume();                      // keep reading, so the end of the input is noticed

const start = () => server.listen(0, '127.0.0.1', () => {
  const { port } = server.address();
  fs.writeFileSync(pidFile, `${process.pid} ${port}\n${JSON.stringify({ pid: process.pid, port })}\n`);
  process.stdout.write(`Sutra Pro is running at http://127.0.0.1:${port}/  (Ctrl+C to stop)\n`);
});
if (mode === 'slow') setTimeout(start, Number(process.env.FAKE_DELAY_MS || 3000));
else start();
