'use strict';
/* What the window's page may call (D125): one function, `window.sutraDesktop.chooseFolder()`, which asks the main process for the system's folder dialog
   (src/folder.js) and resolves to the chosen path or null. The page stays without Node; the preload runs in the sandbox and has only these two modules. */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('sutraDesktop', {
  chooseFolder: () => ipcRenderer.invoke('sutra:choose-folder'),
});
