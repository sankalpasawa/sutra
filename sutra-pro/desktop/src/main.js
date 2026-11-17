'use strict';
/* Sutra Pro, the desktop app (D116, D118): a window around the local server. The server is the Python app that ships inside this one (or, from a
   checkout, the checkout's). The app finds the server that is running for the data folder or starts its own, shows its page, and stops its own when
   the window closes. src/server.js has the rules, src/runtime.js where everything is. */
const { app, BrowserWindow, Menu, dialog, ipcMain, nativeImage, nativeTheme, session, shell } = require('electron');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const runtime = require('./runtime');
const { channelOf, versionLabel, inertUpdates } = require('./channel');
const { Supervisor } = require('./server');
const { createLog } = require('./log');
const { isInternal, isSafeExternal } = require('./urls');
const { permissionHandlers } = require('./permissions');
const { splashPage, errorPage, dataUrl, THEMES } = require('./pages');
const { menuTemplate } = require('./menu');
const { runSelftest, record } = require('./selftest');
const { createDesktopUpdates } = require('./update_main');
const { registerFolderPicker } = require('./folder');

// the stable app, or a beta built from a working tree to try a change beside it (src/channel.js): the name, the id, the data folder and the icon follow
const channel = channelOf(require('../package.json'));
const APP_NAME = channel.appName;
const APP_ID = channel.appId;
const RELEASES_URL = 'https://github.com/sankalpasawa/sutra/releases?q=sutra-pro';
const PROJECT_ROOT = path.resolve(__dirname, '..', '..');         // sutra-pro/ when the app runs from a checkout
const ICON_NAME = process.platform === 'win32' ? channel.windowsIconName : channel.iconName;   // the Windows app has its own icon (D243)
const SELFTEST = process.env.SUTRA_PRO_SELFTEST === '1';

const folder = runtime.dataDir(process.env, os.homedir(), channel.dataDirName);
// a test's or a developer's own data folder carries its own Chromium state too, and its own single-instance lock. Chromium reports a lock it could not
// create (a missing drive, a file where the folder should be, a read-only folder) as it reports one another app holds, and the app would end as a
// "second instance" without a word: so the folder is made and checked first (runtime.windowState). When it cannot be used the window keeps its state in a
// folder of its own, not the system's (the app of every day holds the lock there), and says so (boot).
const windowState = runtime.windowState({ named: process.env.SUTRA_DATA_DIR, folder, systemUserData: app.getPath('userData') });
const folderProblem = windowState.problem;
if (windowState.userData) app.setPath('userData', windowState.userData);
// a beta keeps Chromium's state, and with it the single-instance lock, in a folder of its own, so it opens beside the stable app instead of being turned away as its
// second instance (the packager already names the app after the channel, which does the same; this does not depend on that)
else if (channel.id !== 'stable') app.setPath('userData', path.join(app.getPath('appData'), channel.appName));

const log = createLog(folderProblem ? app.getPath('userData') : folder);
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

// the app updating itself (src/updater.js): a check a minute after launch and every 6 hours, a dialog when a verified update is ready, never in the self-test
const updates = channel.updates
  ? createDesktopUpdates({ app, dialog, shell, supervisor, log, folder, getWindow: () => win, isQuitting: () => quitting })
  : inertUpdates({ channel, info: (options) => infoBox({ message: options.message, detail: options.detail }) });

function infoBox(options) {
  const full = { type: 'info', title: APP_NAME, buttons: ['OK'], defaultId: 0, noLink: true, ...options };
  return win && !win.isDestroyed() ? dialog.showMessageBox(win, full) : dialog.showMessageBox(full);
}

/* What the build says about itself (Contents/Resources/build-info.json, written by scripts/build_desktop_app.py); null from a checkout. */
function buildInfo() {
  if (!app.isPackaged) return null;
  try {
    return JSON.parse(fs.readFileSync(path.join(process.resourcesPath, 'build-info.json'), 'utf8'));
  } catch {
    return null;
  }
}

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
    // the page is the server's own and needs no Node: a page that cannot reach the file system cannot be made to. The preload hands it one function, the
    // folder dialog (src/folder.js)
    webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false, webviewTag: false, preload: path.join(__dirname, 'preload.js') },
  });
  win.once('ready-to-show', () => win.show());
  win.on('page-title-updated', (event) => event.preventDefault());       // the title is the app's: the pages say "Sutra", this app is Sutra Pro
  win.on('closed', () => {
    win = null;
  });
}

function show(html) {
  if (win) win.loadURL(dataUrl(html)).catch((error) => log.write(`could not show a page: ${error.message}`));
}

/* The window shows the server and nothing else. Whatever else a link asks for goes to the browser, and only if it is a web address.
   Permissions are refused except the clipboard write of the server's own page (src/permissions.js). */
function guardNavigation() {
  const permissions = permissionHandlers(() => supervisor.origin);
  session.defaultSession.setPermissionRequestHandler(permissions.request);
  session.defaultSession.setPermissionCheckHandler(permissions.check);
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

function dataFolderError(problem) {
  const error = new Error(`${APP_NAME} cannot use its data folder ${folder}: ${problem}`);
  error.dataFolder = true;
  return error;
}

let folderBlocked = Boolean(folderProblem);             // the window opened because the data folder was unusable: look at it again before any start

async function startServer() {
  show(splashPage({ logo: logoDataUri(), dark: nativeTheme.shouldUseDarkColors, appName: APP_NAME }));
  try {
    if (folderBlocked) {                                // Try Again: a server started in a folder that is still unusable would only say "spawn ENOTDIR"
      const problem = runtime.folderProblem(folder);
      if (problem) throw dataFolderError(problem);
      folderBlocked = false;
    }
    const { url } = await supervisor.start();
    if (!win || quitting) return;
    await win.loadURL(url);
    if (!SELFTEST) {
      updates.start();
      updates.announce();
    }
  } catch (error) {
    if (quitting) return;
    await failed(error);
    return;
  }
  if (SELFTEST) {
    const result = await runSelftest({
      win, supervisor, log: (line) => log.write(line), expectVersion: process.env.SUTRA_PRO_EXPECT_VERSION || '', outDir: selftestDir(), appName: APP_NAME,
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
  show(errorPage({ message: String(error && error.message), output, logFile: log.file, logo: logoDataUri(), dark: nativeTheme.shouldUseDarkColors, appName: APP_NAME }));
  const question = {
    type: 'error', title: APP_NAME, message: error && error.dataFolder ? `${APP_NAME} cannot use its data folder.` : `${APP_NAME} could not start its server.`,
    detail: String(error && error.message),
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

function onServerExit({ code, signal, expected, attached }) {
  if (expected || quitting) return;
  failed(new Error(attached
    ? 'The server this window was showing is no longer answering (it was started by something else, so this app did not stop it).'
    : `The server stopped unexpectedly (${signal ? `signal ${signal}` : `exit status ${code}`}).`));
}

function installMenu() {
  const handlers = {
    openDataFolder: () => shell.openPath(folder),
    showLog: () => shell.showItemInFolder(log.file),
    openReleases: () => shell.openExternal(RELEASES_URL),
    checkForUpdates: () => updates.checkNow({ manual: true }),
  };
  const devTools = !app.isPackaged || process.env.SUTRA_PRO_DEVTOOLS === '1';
  Menu.setApplicationMenu(Menu.buildFromTemplate(menuTemplate({ appName: APP_NAME, isMac: process.platform === 'darwin', devTools, handlers })));
}

async function boot() {
  const label = versionLabel(channel, app.getVersion(), buildInfo());
  log.write(`${APP_NAME} ${label} on ${process.platform} ${process.arch}, electron ${process.versions.electron}, `
    + `${app.isPackaged ? 'installed' : 'from a checkout'}; data folder ${folder}`);
  if (process.platform === 'win32') app.setAppUserModelId(APP_ID);
  if (process.platform === 'darwin' && !app.isPackaged && app.dock) {
    const icon = appIcon();
    if (icon) app.dock.setIcon(icon);                  // an installed app has the icon of its bundle
  }
  app.setAboutPanelOptions({ applicationName: APP_NAME, applicationVersion: label, copyright: 'Sutra' });
  guardNavigation();
  registerFolderPicker({ ipcMain, dialog, getWindow: () => win, getOrigin: () => supervisor.origin });
  installMenu();
  createWindow();
  supervisor.on('exit', onServerExit);
  if (folderProblem) {
    await failed(dataFolderError(folderProblem));       // Try Again looks at the folder again and starts the server in it when it is usable by now
    return;
  }
  await startServer();
}

// the server we started ends with the app: hold the quit until it has stopped (the ladder in src/server.js is bounded)
app.on('before-quit', (event) => {
  if (stopped) return;
  event.preventDefault();
  if (quitting) return;
  quitting = true;
  updates.stop();                                       // no timer and no dialog from here on
  if (win && !win.isDestroyed()) win.hide();
  supervisor.stop().catch((error) => log.write(`stopping the server failed: ${error.message}`)).finally(async () => {
    stopped = true;
    // the server is stopped: only now may an update the owner chose replace the app (the helper waits for this process to end as well)
    await updates.applyOnQuit().catch((error) => log.write(`the update was not applied: ${error.message}`));
    log.write('bye');
    if (SELFTEST) app.exit(exitCode);
    else app.quit();
  });
});

app.on('window-all-closed', () => app.quit());

process.on('uncaughtException', (error) => log.write(`uncaught: ${error && error.stack ? error.stack : error}`));

if (!app.requestSingleInstanceLock()) {
  // not taken: another instance holds it (it takes the focus, see its second-instance handler below), or Chromium could not make the lock
  const problem = runtime.folderProblem(app.getPath('userData'));
  if (problem) {
    log.write(`could not start: ${problem}`);
    dialog.showErrorBox(APP_NAME, `${APP_NAME} cannot use its settings folder.\n\n${problem}`);
  }
  app.exit(problem ? 1 : 0);
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
