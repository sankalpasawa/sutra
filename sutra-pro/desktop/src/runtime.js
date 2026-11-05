'use strict';
/* What the desktop app needs to know about its surroundings, as pure functions (D107). Nothing here touches Electron, so
   `node --test` covers all of it on every system. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const DATA_DIR_NAME = '.sutra-pro';

/* The data folder: SUTRA_DATA_DIR, else ~/.sutra-pro. The server's own default is the same folder, and the app passes it with --data-dir
   anyway, so the app and the server cannot disagree about where app.pid is. */
function dataDir(env = process.env, home = os.homedir()) {
  const named = String(env.SUTRA_DATA_DIR || '').trim();
  if (!named) return path.join(home, DATA_DIR_NAME);
  if (named === '~') return home;
  if (/^~[\\/]/.test(named)) return path.join(home, named.slice(2));
  return path.resolve(named);
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

/* The server's command line. -I: no PYTHON* variables and no user site, so a user's own Python setup cannot break the app. -X utf8 on Windows:
   a file opened without an encoding is UTF-8, not the console's code page. --exit-when-stdin-closes: the server ends with this program, however
   this program ends. No --port: the server takes the first free port from 8780 to 8799 (or SUTRA_PORT) and writes it to app.pid. */
function serverArgs({ platform = process.platform, dataDir: folder, extra = [] }) {
  return ['-I', ...(platform === 'win32' ? ['-X', 'utf8'] : []), '-m', 'sutra_app', '--no-browser', '--exit-when-stdin-closes',
    '--data-dir', folder, ...extra];
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
  out.PYTHONDONTWRITEBYTECODE = '1';   // nothing is written into the signed app
  out.PYTHONUNBUFFERED = '1';          // the server's lines reach the log as they happen
  if (platform === 'win32') out.PYTHONUTF8 = '1';
  out.SUTRA_DATA_DIR = folder;
  return out;
}

module.exports = { dataDir, pythonPath, serverArgs, childEnv, pathExtras, DATA_DIR_NAME };
