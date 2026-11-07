'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const runtime = require('../src/runtime');

test('the data folder is SUTRA_DATA_DIR, else ~/.sutra-pro, with ~ expanded', () => {
  assert.equal(runtime.dataDir({}, '/home/u'), path.join('/home/u', '.sutra-pro'));
  assert.equal(runtime.dataDir({ SUTRA_DATA_DIR: '   ' }, '/home/u'), path.join('/home/u', '.sutra-pro'));
  assert.equal(runtime.dataDir({ SUTRA_DATA_DIR: '~' }, '/home/u'), '/home/u');
  assert.equal(runtime.dataDir({ SUTRA_DATA_DIR: '~/work/sutra' }, '/home/u'), path.join('/home/u', 'work', 'sutra'));
  assert.equal(runtime.dataDir({ SUTRA_DATA_DIR: '/srv/data' }, '/home/u'), path.resolve('/srv/data'));
});

test('the installed app runs the Python inside it and ignores what the environment names', () => {
  const env = { SUTRA_PRO_PYTHON: '/usr/bin/python3' };
  assert.equal(runtime.pythonPath({ packaged: true, resourcesPath: '/Applications/Sutra Pro.app/Contents/Resources', platform: 'darwin', env }),
    path.join('/Applications/Sutra Pro.app/Contents/Resources', 'python', 'bin', 'python3'));
  assert.equal(runtime.pythonPath({ packaged: true, resourcesPath: 'C:\\Users\\u\\AppData\\Local\\Programs\\Sutra Pro\\resources', platform: 'win32', env }),
    'C:\\Users\\u\\AppData\\Local\\Programs\\Sutra Pro\\resources\\python\\python.exe');
});

test('from a checkout: SUTRA_PRO_PYTHON, else the virtual environment, else the python on PATH', () => {
  const root = '/code/sutra-pro';
  const none = () => false;
  assert.equal(runtime.pythonPath({ packaged: false, platform: 'linux', env: { SUTRA_PRO_PYTHON: '/opt/py' }, projectRoot: root, exists: none }), '/opt/py');
  assert.equal(runtime.pythonPath({ packaged: false, platform: 'linux', env: {}, projectRoot: root, exists: (p) => p === path.join(root, '.venv', 'bin', 'python') }),
    path.join(root, '.venv', 'bin', 'python'));
  assert.equal(runtime.pythonPath({ packaged: false, platform: 'linux', env: {}, projectRoot: root, exists: none }), 'python3');
  assert.equal(runtime.pythonPath({ packaged: false, platform: 'win32', env: {}, projectRoot: root, exists: none }), 'python');
});

test('the server is started isolated, writing no bytecode, headless, tied to our input, on the data folder we name', () => {
  assert.deepEqual(runtime.serverArgs({ platform: 'darwin', dataDir: '/d' }),
    ['-I', '-B', '-m', 'sutra_app', '--no-browser', '--exit-when-stdin-closes', '--data-dir', '/d']);
  assert.deepEqual(runtime.serverArgs({ platform: 'win32', dataDir: 'C:\\d', extra: ['--offline'] }),
    ['-I', '-B', '-X', 'utf8', '-m', 'sutra_app', '--no-browser', '--exit-when-stdin-closes', '--data-dir', 'C:\\d', '--offline']);
});

test('the wait for the server is 60 seconds unless SUTRA_PRO_START_TIMEOUT says 1 to 600', () => {
  assert.equal(runtime.startTimeoutMs({}), 60000);
  assert.equal(runtime.startTimeoutMs({ SUTRA_PRO_START_TIMEOUT: '170' }), 170000);
  assert.equal(runtime.startTimeoutMs({ SUTRA_PRO_START_TIMEOUT: ' 5 ' }), 5000);
  for (const odd of ['0', '-3', '601', 'soon', '', '1.5e3', '12s', '0x20']) {
    assert.equal(runtime.startTimeoutMs({ SUTRA_PRO_START_TIMEOUT: odd }), 60000, odd);
  }
});

test('the server\'s environment drops what reaches into Python or Electron and keeps the rest', () => {
  const env = runtime.childEnv({
    PATH: '/usr/bin', HOME: '/home/u', PYTHONPATH: '/x', PYTHONHOME: '/y', PIP_INDEX_URL: 'z', VIRTUAL_ENV: '/v', UV_CACHE_DIR: '/c',
    ELECTRON_RUN_AS_NODE: '1', ELECTRON_NO_ATTACH_CONSOLE: '1', ANTHROPIC_MODEL: 'keep', SUTRA_OFFLINE: '1',
  }, { platform: 'darwin', home: '/home/u', dataDir: '/data' });
  for (const gone of ['PYTHONPATH', 'PYTHONHOME', 'PIP_INDEX_URL', 'VIRTUAL_ENV', 'UV_CACHE_DIR', 'ELECTRON_RUN_AS_NODE', 'ELECTRON_NO_ATTACH_CONSOLE']) {
    assert.equal(gone in env, false, gone);
  }
  assert.equal(env.ANTHROPIC_MODEL, 'keep');
  assert.equal(env.SUTRA_OFFLINE, '1');
  assert.equal(env.SUTRA_DATA_DIR, '/data');
  assert.equal(env.PYTHONNOUSERSITE, '1');
  assert.equal(env.PYTHONDONTWRITEBYTECODE, '1', 'nothing may be written into the signed app');
  assert.equal(env.PYTHONUNBUFFERED, '1');
  assert.equal('PYTHONUTF8' in env, false, 'only Windows needs it');
});

test('PATH gets the folders of the claude and codex CLIs appended, once, never in front', () => {
  const env = runtime.childEnv({ PATH: '/opt/homebrew/bin:/usr/bin', SUTRA_EXTRA_PATH: '/extra/bin' }, { platform: 'darwin', home: '/home/u', dataDir: '/d' });
  const parts = env.PATH.split(':');
  assert.deepEqual(parts.slice(0, 2), ['/opt/homebrew/bin', '/usr/bin'], 'what the user\'s PATH finds first stays first');
  assert.equal(parts.filter((p) => p === '/opt/homebrew/bin').length, 1, 'no duplicates');
  for (const dir of ['/usr/local/bin', '/home/u/.local/bin', '/home/u/.claude/local', '/home/u/.npm-global/bin', '/home/u/.bun/bin', '/extra/bin']) {
    assert.ok(parts.includes(dir), dir);
  }
  const bare = runtime.childEnv({}, { platform: 'linux', home: '/home/u', dataDir: '/d' });
  assert.ok(bare.PATH.startsWith('/usr/bin:/bin:/usr/sbin:/sbin:'), bare.PATH);
});

test('on Windows the PATH variable keeps its own spelling, folders are joined with ;, and Python is told to use UTF-8', () => {
  const env = runtime.childEnv({ Path: 'C:\\Windows', APPDATA: 'C:\\Users\\u\\AppData\\Roaming' }, { platform: 'win32', home: 'C:\\Users\\u', dataDir: 'C:\\d' });
  assert.equal('PATH' in env, false);
  assert.equal(env.Path, 'C:\\Windows;C:\\Users\\u\\AppData\\Roaming\\npm;C:\\Users\\u\\.local\\bin');
  assert.equal(env.PYTHONUTF8, '1');
});

test('a folder the app needs is made, and one it cannot make or write to is reported with the reason', (t) => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'sutra-folder-'));
  t.after(() => {
    for (const name of ['read-only', 'locked']) {
      try {
        fs.chmodSync(path.join(base, name), 0o700);
      } catch {
        // never made: Windows and root return before they are
      }
    }
    fs.rmSync(base, { recursive: true, force: true });
  });
  const nested = path.join(base, 'a', 'b', 'electron');
  assert.equal(runtime.folderProblem(nested), null);
  assert.ok(fs.statSync(nested).isDirectory());
  assert.equal(runtime.folderProblem(nested), null, 'a folder that is already there is fine');

  const file = path.join(base, 'a-file');
  fs.writeFileSync(file, 'not a folder');
  assert.match(runtime.folderProblem(file) || '', /\S/, 'a regular file where the folder should be');
  const underFile = runtime.folderProblem(path.join(file, 'electron')) || '';
  assert.match(underFile, /\S/, 'a folder below a regular file cannot be made');
  assert.ok(underFile.includes(file), 'the answer names the path');

  if (process.platform === 'win32' || (typeof process.getuid === 'function' && process.getuid() === 0)) {
    return t.diagnostic('a read-only folder is refused by permission bits: not on Windows, not for root');
  }
  const readOnly = path.join(base, 'read-only');
  fs.mkdirSync(readOnly, { mode: 0o500 });
  assert.match(runtime.folderProblem(path.join(readOnly, 'electron')) || '', /EACCES/);
  fs.mkdirSync(path.join(base, 'locked'), { mode: 0o500 });
  assert.match(runtime.folderProblem(path.join(base, 'locked')) || '', /not writable/, 'it exists but nothing can be written in it');
});

test('the window\'s own state lives in <data>/electron; when that is unusable it moves to a folder of its own, never to the system\'s one the everyday app locks', (t) => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'sutra-state-'));
  t.after(() => fs.rmSync(base, { recursive: true, force: true }));
  const system = path.join(base, 'system', 'Sutra Pro');
  // no SUTRA_DATA_DIR: the system's folder, untouched
  assert.deepEqual(runtime.windowState({ named: '', folder: path.join(base, 'data'), systemUserData: system }), { userData: null, problem: null });
  assert.equal(fs.existsSync(path.join(base, 'data')), false, 'nothing is made when the system folder is used');
  // a usable folder: its own state, as before
  const data = path.join(base, 'data');
  assert.deepEqual(runtime.windowState({ named: data, folder: data, systemUserData: system }), { userData: path.join(data, 'electron'), problem: null });
  // a regular file where the folder should be: the reason, and a folder beside the system's own state, not the system folder itself
  const file = path.join(base, 'a-file');
  fs.writeFileSync(file, 'not a folder');
  const state = runtime.windowState({ named: file, folder: file, systemUserData: system });
  assert.match(state.problem || '', /\S/);
  assert.equal(state.userData, path.join(system, runtime.ASIDE_NAME));
  assert.notEqual(state.userData, system, 'the system folder holds the lock of the app of every day');
  assert.ok(fs.statSync(state.userData).isDirectory(), 'it was made');
  // even that folder cannot be made: the reason is still given, and the system folder is kept (the lock check then decides)
  const stuck = runtime.windowState({ named: file, folder: file, systemUserData: path.join(file, 'Sutra Pro') });
  assert.match(stuck.problem || '', /\S/);
  assert.equal(stuck.userData, null);
});
