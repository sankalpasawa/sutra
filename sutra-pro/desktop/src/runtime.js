'use strict';
/* What the desktop app needs to know about its surroundings, as pure functions (D118). Nothing here touches Electron, so
   `node --test` covers all of it on every system. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const DATA_DIR_NAME = '.sutra-pro';
const ASIDE_NAME = 'data-folder-error';          // inside the system's user-data folder: where the window that reports an unusable data folder keeps its state
const DEFAULT_START_TIMEOUT_S = 60;
const MAX_START_TIMEOUT_S = 600;

/* The data folder: SUTRA_DATA_DIR, else ~/.sutra-pro. The server's own default is the same folder, and the app passes it with --data-dir
   anyway, so the app and the server cannot disagree about where app.pid is. */
function dataDir(env = process.env, home = os.homedir()) {
  const named = String(env.SUTRA_DATA_DIR || '').trim();
  if (!named) return path.join(home, DATA_DIR_NAME);
  if (named === '~') return home;
  if (/^~[\\/]/.test(named)) return path.join(home, named.slice(2));
  return path.resolve(named);
}

/* Make `dir` (and what is above it) when it is missing and say why when the app cannot use it: null when it is a folder the app can write in, else
   one line with the reason. Chromium keeps its single-instance lock in the user-data folder and reports a lock it could not create exactly like
   a lock another app holds, so the app asks first instead of taking "no lock" for "already running". */
function folderProblem(dir) {
  try {
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
    if (!fs.statSync(dir).isDirectory()) return `${dir} is not a folder`;
    fs.accessSync(dir, fs.constants.R_OK | fs.constants.W_OK | fs.constants.X_OK);
    return null;
  } catch (error) {
    if (error && error.code === 'EEXIST') return `${dir} exists and is not a folder`;                     // a file (or a link to one) where the folder should be
    return error && error.code === 'EACCES' && fs.existsSync(dir) ? `${dir} is not writable (${error.code})` : String(error && error.message ? error.message : error);
  }
}

/* Where Chromium keeps the window's own state (its cache and its single-instance lock), as { userData, problem }. `userData` is the folder to set, or null to
   keep the system's own. Without SUTRA_DATA_DIR (`named` empty) it is the system's, as for an installed app. With it, the state lives in <data>/electron so a
   test never meets the app a person uses every day; when that folder cannot be made or written (`problem` says why) the window must still open to say so, and
   it must not use the system's folder for that: the app of every day holds the lock there, and a window that asked for another folder would be turned away as a
   "second instance" without a word. It gets a folder of its own below the system's instead (null when even that cannot be made). */
function windowState({ named, folder, systemUserData, check = folderProblem }) {
  if (!named) return { userData: null, problem: null };
  const own = path.join(folder, 'electron');
  const problem = check(own);
  if (!problem) return { userData: own, problem: null };
  const aside = path.join(systemUserData, ASIDE_NAME);
  return { userData: check(aside) ? null : aside, problem };
}

/* The interpreter that runs the server. Installed: the one inside the app (Contents/Resources/python on a Mac, resources\python on Windows), never
   one the environment names. From a checkout (`npm start`): SUTRA_PRO_PYTHON, else the checkout's virtual environment, else the python on PATH. */
function pythonPath({ packaged, resourcesPath, platform = process.platform, env = process.env, projectRoot, exists = fs.existsSync }) {
  const win = platform === 'win32';
  if (packaged) {
    return win ? path.win32.join(resourcesPath, 'python', 'python.exe') : path.join(resourcesPath, 'python', 'bin', 'python3');
  }
  const named = String(env.SUTRA_PRO_PYTHON || '').trim();
  if (named) return named;
  const venv = win ? path.join(projectRoot, '.venv', 'Scripts', 'python.exe') : path.join(projectRoot, '.venv', 'bin', 'python');
  return exists(venv) ? venv : (win ? 'python' : 'python3');
}

/* The server's command line. -I: no PYTHON* variables and no user site, so a user's own Python setup cannot break the app. -B: write no bytecode
   (-I ignores PYTHONDONTWRITEBYTECODE, so the flag is the only way): a .pyc written into the signed app would break its seal. -X utf8 on Windows:
   a file opened without an encoding is UTF-8, not the console's code page. --exit-when-stdin-closes: the server ends with this program, however
   this program ends. No --port: the server takes the first free port from 8780 to 8799 (or SUTRA_PORT) and writes it to app.pid. */
function serverArgs({ platform = process.platform, dataDir: folder, extra = [] }) {
  return ['-I', '-B', ...(platform === 'win32' ? ['-X', 'utf8'] : []), '-m', 'sutra_app', '--no-browser', '--exit-when-stdin-closes',
    '--data-dir', folder, ...extra];
}

/* How long the app waits for the server to answer before it gives up: SUTRA_PRO_START_TIMEOUT seconds (1 to 600), default 60. A cold machine that is
   scanning a fresh install for viruses is slow to start Python, and the release proofs ask for more. */
function startTimeoutMs(env = process.env) {
  const text = String(env.SUTRA_PRO_START_TIMEOUT || '').trim();
  const seconds = /^\d+$/.test(text) ? Number.parseInt(text, 10) : 0;       // digits only: parseInt would read '1.5e3' as 1
  return (seconds >= 1 && seconds <= MAX_START_TIMEOUT_S ? seconds : DEFAULT_START_TIMEOUT_S) * 1000;
}

const DROPPED = /^(PYTHON|PIP_|VIRTUAL_ENV$|UV_|ELECTRON_)/i;

function pathKey(env) {
  return Object.keys(env).find((key) => key.toUpperCase() === 'PATH') || 'PATH';
}

/* A program started from the Dock or the Start menu gets a bare PATH, and the claude and codex command lines the connectors run live outside it.
   The folders that usually hold them are appended (never prepended: what the user's PATH finds first stays first). */
function pathExtras({ platform, home, env }) {
  if (platform === 'win32') {
    return [env.APPDATA ? path.win32.join(env.APPDATA, 'npm') : '', path.win32.join(home, '.local', 'bin')];
  }
  return ['/opt/homebrew/bin', '/usr/local/bin', `${home}/.local/bin`, `${home}/.claude/local`, `${home}/.npm-global/bin`, `${home}/.bun/bin`];
}

/* The environment of the server: the app's own, minus what would reach into the bundled Python (PYTHON*, PIP_*, VIRTUAL_ENV, UV_*) or turn the
   server into an Electron process (ELECTRON_*), plus a PATH that finds the CLIs, and the settings that keep the signed bundle unchanged. */
function childEnv(env, { platform = process.platform, home = os.homedir(), dataDir: folder }) {
  const out = {};
  for (const [key, value] of Object.entries(env)) {
    if (value !== undefined && !DROPPED.test(key)) out[key] = value;
  }
  const key = pathKey(out);
  const separator = platform === 'win32' ? ';' : ':';
  const current = out[key] || (platform === 'win32' ? '' : '/usr/bin:/bin:/usr/sbin:/sbin');
  const extra = String(env.SUTRA_EXTRA_PATH || '').trim();
  const seen = new Set(current.split(separator).filter(Boolean));
  const added = [...pathExtras({ platform, home, env }), ...(extra ? [extra] : [])].filter((dir) => dir && !seen.has(dir));
  out[key] = [current, ...added].filter(Boolean).join(separator);
  out.PYTHONNOUSERSITE = '1';          // the user's site-packages is not the bundle's
  out.PYTHONDONTWRITEBYTECODE = '1';   // nothing is written into the signed app (the engine's own Python processes get this one; -I would ignore it)
  out.PYTHONUNBUFFERED = '1';          // the server's lines reach the log as they happen
  if (platform === 'win32') out.PYTHONUTF8 = '1';
  out.SUTRA_DATA_DIR = folder;
  return out;
}

module.exports = { dataDir, folderProblem, windowState, pythonPath, serverArgs, childEnv, pathExtras, startTimeoutMs, DATA_DIR_NAME, ASIDE_NAME };
