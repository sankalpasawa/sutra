'use strict';
/* Sutra Pro, the desktop app (D105, D107): a window around the local server. The server is the Python app that ships inside this one (or, from a
   checkout, the checkout's). The app finds the server that is running for the data folder or starts its own, shows its page, and stops its own when
   the window closes. src/server.js has the rules, src/runtime.js where everything is. */
const { app, BrowserWindow, Menu, dialog, nativeImage, nativeTheme, session, shell } = require('electron');
const path = require('node:path');
const runtime = require('./runtime');
const { Supervisor } = require('./server');
const { createLog } = require('./log');
const { isInternal, isSafeExternal } = require('./urls');
const { splashPage, errorPage, dataUrl, THEMES } = require('./pages');
const { menuTemplate } = require('./menu');
const { runSelftest, record } = require('./selftest');

const APP_NAME = 'Sutra Pro';
const APP_ID = 'os.sutra.pro';
const RELEASES_URL = 'https://github.com/sankalpasawa/sutra/releases?q=sutra-pro';
const PROJECT_ROOT = path.resolve(__dirname, '..', '..');         // sutra-pro/ when the app runs from a checkout
const ICON_NAME = 'sutra-pro-1024.png';
const SELFTEST = process.env.SUTRA_PRO_SELFTEST === '1';

const folder = runtime.dataDir();
// a test's or a developer's own data folder carries its own Chromium state too, and its own single-instance lock
if (process.env.SUTRA_DATA_DIR) app.setPath('userData', path.join(folder, 'electron'));

const log = createLog(folder);
const supervisor = new Supervisor({
  dataDir: folder,
  command: runtime.pythonPath({ packaged: app.isPackaged, resourcesPath: process.resourcesPath, projectRoot: PROJECT_ROOT }),
  args: runtime.serverArgs({ dataDir: folder }),
  env: runtime.childEnv(process.env, { dataDir: folder }),
  timeouts: { start: runtime.startTimeoutMs() },
  strictPid: app.isPackaged || process.platform !== 'win32',          // a venv's python.exe on Windows is a launcher: the server is its child
  log: (line) => log.write(line),
});

let win = null;
let quitting = false;
let stopped = false;
let exitCode = 0;

function selftestDir() {
  return process.env.SUTRA_PRO_SELFTEST_DIR || path.join(folder, 'selftest');
}

function iconPath() {
  return app.isPackaged ? path.join(process.resourcesPath, ICON_NAME) : path.join(PROJECT_ROOT, 'assets', 'icon', ICON_NAME);
}

function appIcon() {
  const image = nativeImage.createFromPath(iconPath());
  return image.isEmpty() ? null : image;
}

function logoDataUri() {
  const image = appIcon();
  return image ? `data:image/png;base64,${image.resize({ width: 192, height: 192 }).toPNG().toString('base64')}` : '';
}

function createWindow() {
  const dark = nativeTheme.shouldUseDarkColors;
  const icon = process.platform === 'darwin' ? null : appIcon();
  win = new BrowserWindow({
    width: 1440, height: 940, minWidth: 900, minHeight: 600, title: APP_NAME, show: false,
    backgroundColor: THEMES[dark ? 'dark' : 'light'].bg, ...(icon ? { icon } : {}),
    // the page is the server's own and needs no Node: a page that cannot reach the file system cannot be made to
    webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false, webviewTag: false },
  });
  win.once('ready-to-show', () => win.show());
  win.on('closed', () => {
    win = null;
  });
}

function show(html) {
  if (win) win.loadURL(dataUrl(html)).catch((error) => log.write(`could not show a page: ${error.message}`));
}

/* The window shows the server and nothing else. Whatever else a link asks for goes to the browser, and only if it is a web address. */
function guardNavigation() {
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  app.on('web-contents-created', (_event, contents) => {
    contents.setWindowOpenHandler(({ url }) => {
      if (isSafeExternal(url)) shell.openExternal(url);
      return { action: 'deny' };
    });
    const leave = (event, url) => {
      if (isInternal(url, supervisor.origin)) return;
      event.preventDefault();
      if (isSafeExternal(url)) shell.openExternal(url);
    };
    contents.on('will-navigate', leave);
    contents.on('will-redirect', leave);
    contents.on('will-attach-webview', (event) => event.preventDefault());
  });
}

async function startServer() {
  show(splashPage({ logo: logoDataUri(), dark: nativeTheme.shouldUseDarkColors }));
  try {
    const { url } = await supervisor.start();
    if (!win || quitting) return;
    await win.loadURL(url);
  } catch (error) {
    if (quitting) return;
    await failed(error);
    return;
  }
  if (SELFTEST) {
    const result = await runSelftest({
      win, supervisor, log: (line) => log.write(line), expectVersion: process.env.SUTRA_PRO_EXPECT_VERSION || '', outDir: selftestDir(),
    });
    exitCode = result.ok ? 0 : 1;
    app.quit();
  }
}

/* A start that failed, or a server that died: say what happened, with the last lines it printed, and offer the three things a person can do. */
async function failed(error) {
  const output = error && error.output ? error.output.slice(-12) : [];
  log.write(`failed: ${error && error.message}`);
  if (SELFTEST) {
    record({ outDir: selftestDir(), log: (line) => log.write(line), result: { ok: false, failures: [String(error && error.message), ...output] } });
    exitCode = 1;
    app.quit();
    return;
  }
  show(errorPage({ message: String(error && error.message), output, logFile: log.file, logo: logoDataUri(), dark: nativeTheme.shouldUseDarkColors }));
  const question = {
    type: 'error', title: APP_NAME, message: `${APP_NAME} could not start its server.`, detail: String(error && error.message),
    buttons: ['Try Again', 'Show the Log', 'Quit'], defaultId: 0, cancelId: 2,
  };
  for (;;) {
    const { response } = await (win ? dialog.showMessageBox(win, question) : dialog.showMessageBox(question));
    if (response === 0) {
      await startServer();
      return;
    }
    if (response === 1) {
      shell.showItemInFolder(log.file);
    } else {
      app.quit();
      return;
    }
  }
}

function onServerExit({ code, signal, expected }) {
  if (expected || quitting) return;
  failed(new Error(`The server stopped unexpectedly (${signal ? `signal ${signal}` : `exit status ${code}`}).`));
}

function installMenu() {
  const handlers = {
    openDataFolder: () => shell.openPath(folder),
    showLog: () => shell.showItemInFolder(log.file),
    openReleases: () => shell.openExternal(RELEASES_URL),
  };
  const devTools = !app.isPackaged || process.env.SUTRA_PRO_DEVTOOLS === '1';
  Menu.setApplicationMenu(Menu.buildFromTemplate(menuTemplate({ appName: APP_NAME, isMac: process.platform === 'darwin', devTools, handlers })));
}

async function boot() {
  log.write(`Sutra Pro ${app.getVersion()} on ${process.platform} ${process.arch}, electron ${process.versions.electron}, `
    + `${app.isPackaged ? 'installed' : 'from a checkout'}; data folder ${folder}`);
  if (process.platform === 'win32') app.setAppUserModelId(APP_ID);
  if (process.platform === 'darwin' && !app.isPackaged && app.dock) {
    const icon = appIcon();
    if (icon) app.dock.setIcon(icon);                  // an installed app has the icon of its bundle
  }
  app.setAboutPanelOptions({ applicationName: APP_NAME, applicationVersion: app.getVersion(), copyright: 'Sutra' });
  guardNavigation();
  installMenu();
  createWindow();
  supervisor.on('exit', onServerExit);
  await startServer();
}

// the server we started ends with the app: hold the quit until it has stopped (the ladder in src/server.js is bounded)
app.on('before-quit', (event) => {
  if (stopped) return;
  event.preventDefault();
  if (quitting) return;
  quitting = true;
  if (win && !win.isDestroyed()) win.hide();
  supervisor.stop().catch((error) => log.write(`stopping the server failed: ${error.message}`)).finally(() => {
    stopped = true;
    log.write('bye');
    if (SELFTEST) app.exit(exitCode);
    else app.quit();
  });
});

app.on('window-all-closed', () => app.quit());

process.on('uncaughtException', (error) => log.write(`uncaught: ${error && error.stack ? error.stack : error}`));

if (!app.requestSingleInstanceLock()) {
  app.exit(0);                                          // the running app takes the focus (its second-instance handler below)
} else {
  app.on('second-instance', () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(boot).catch((error) => {
    log.write(`could not start: ${error && error.stack ? error.stack : error}`);
    app.exit(1);
  });
}
