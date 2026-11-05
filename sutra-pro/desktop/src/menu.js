'use strict';
/* The application menu as data (D107), so a test can read it. On a Mac the Edit menu is not decoration: without its copy, paste and select-all roles
   the shortcuts do nothing in a text field. */

function menuTemplate({ appName, isMac, devTools, handlers }) {
  const edit = {
    label: 'Edit',
    submenu: [{ role: 'undo' }, { role: 'redo' }, { type: 'separator' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' },
      { role: 'selectAll' }],
  };
  const view = {
    label: 'View',
    submenu: [{ role: 'reload' }, { role: 'forceReload' }, { type: 'separator' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' },
      { type: 'separator' }, { role: 'togglefullscreen' }, ...(devTools ? [{ type: 'separator' }, { role: 'toggleDevTools' }] : [])],
  };
  const help = {
    role: 'help',
    submenu: [
      { label: 'Show the Data Folder', click: handlers.openDataFolder },
      { label: 'Show the Log', click: handlers.showLog },
      { type: 'separator' },
      { label: 'Releases', click: handlers.openReleases },
    ],
  };
  if (isMac) {
    return [
      { label: appName, submenu: [{ role: 'about' }, { type: 'separator' }, { role: 'services' }, { type: 'separator' }, { role: 'hide' },
        { role: 'hideOthers' }, { role: 'unhide' }, { type: 'separator' }, { role: 'quit' }] },
      { label: 'File', submenu: [{ role: 'close' }] },
      edit,
      view,
      { label: 'Window', submenu: [{ role: 'minimize' }, { role: 'zoom' }, { type: 'separator' }, { role: 'front' }] },
      help,
    ];
  }
  return [
    { label: 'File', submenu: [{ role: 'quit', label: `Exit ${appName}` }] },
    edit,
    view,
    { label: 'Window', submenu: [{ role: 'minimize' }, { role: 'close' }] },
    help,
  ];
}

module.exports = { menuTemplate };
