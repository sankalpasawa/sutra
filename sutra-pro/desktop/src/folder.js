'use strict';
/* The folder chooser the page can ask for (D125). The Settings page has a text field for the working folder; in the app it also gets a "Choose folder…"
   button, which needs the system's folder dialog. The page has no Node (src/main.js), so the one thing it gets is `window.sutraDesktop.chooseFolder()`,
   bridged by src/preload.js to the IPC channel below. The main process answers only the server's own page (src/urls.js), shows the dialog, and gives back
   the chosen path or null. */
const { isInternal } = require('./urls');

const CHANNEL = 'sutra:choose-folder';
const TITLE = 'Choose the folder your team works in';

/* The path the owner chose, or null when they closed the dialog. `win` is the window to hang the dialog on, when there is one. */
async function chooseFolder({ dialog, win }) {
  const options = { title: TITLE, properties: ['openDirectory', 'createDirectory'] };
  const answer = win ? await dialog.showOpenDialog(win, options) : await dialog.showOpenDialog(options);
  const chosen = answer && !answer.canceled && Array.isArray(answer.filePaths) ? answer.filePaths[0] : null;
  return typeof chosen === 'string' && chosen !== '' ? chosen : null;
}

/* The handler of the channel: a request from any page that is not on the server's own origin gets null and no dialog. `getOrigin` is asked each time (the
   port is known only once the server has started). */
function folderHandler({ dialog, getWindow, getOrigin }) {
  return async (event) => {
    const url = (event && event.senderFrame && event.senderFrame.url) || (event && event.sender && event.sender.getURL && event.sender.getURL());
    if (!isInternal(url, getOrigin())) return null;
    const win = getWindow();
    return chooseFolder({ dialog, win: win && !win.isDestroyed() ? win : undefined });
  };
}

function registerFolderPicker({ ipcMain, dialog, getWindow, getOrigin }) {
  ipcMain.handle(CHANNEL, folderHandler({ dialog, getWindow, getOrigin }));
}

module.exports = { CHANNEL, TITLE, chooseFolder, folderHandler, registerFolderPicker };
