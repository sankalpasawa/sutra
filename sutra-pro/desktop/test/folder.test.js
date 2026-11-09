'use strict';
/* The folder chooser the page can ask for (src/folder.js; D125): the dialog's options, the answer for a chosen folder and a closed dialog, and that only the
   server's own page is answered. Electron is stood in for by a fake dialog and a fake ipcMain, like the other tests here. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { CHANNEL, TITLE, chooseFolder, folderHandler, registerFolderPicker } = require('../src/folder');

const ORIGIN = 'http://127.0.0.1:8781';
const fakeDialog = (answer) => {
  const calls = [];
  return { calls, showOpenDialog: async (...args) => { calls.push(args); return answer; } };
};
const fromPage = (url) => ({ senderFrame: { url } });

test('the dialog asks for a folder, may create one, and is titled in the owner\'s words', async () => {
  const dialog = fakeDialog({ canceled: false, filePaths: ['/Users/me/proj'] });
  assert.equal(await chooseFolder({ dialog, win: undefined }), '/Users/me/proj');
  assert.deepEqual(dialog.calls, [[{ title: 'Choose the folder your team works in', properties: ['openDirectory', 'createDirectory'] }]]);
  assert.equal(TITLE, 'Choose the folder your team works in');
});

test('with a window the dialog hangs on it', async () => {
  const dialog = fakeDialog({ canceled: false, filePaths: ['/a'] });
  const win = { isDestroyed: () => false };
  await folderHandler({ dialog, getWindow: () => win, getOrigin: () => ORIGIN })(fromPage(`${ORIGIN}/d/web/`));
  assert.equal(dialog.calls[0][0], win);
});

test('a closed dialog, an empty answer and an odd one are null', async () => {
  for (const answer of [{ canceled: true, filePaths: [] }, { canceled: true, filePaths: ['/x'] }, { canceled: false, filePaths: [] }, { canceled: false, filePaths: [''] },
    { canceled: false }, undefined, null]) {
    assert.equal(await chooseFolder({ dialog: fakeDialog(answer) }), null, JSON.stringify(answer));
  }
});

test('only the server\'s own page is answered: another origin, a look-alike, a data page and an unknown sender get null and no dialog', async () => {
  const dialog = fakeDialog({ canceled: false, filePaths: ['/a'] });
  const handler = folderHandler({ dialog, getWindow: () => null, getOrigin: () => ORIGIN });
  for (const event of [fromPage('http://127.0.0.1:8782/'), fromPage('http://127.0.0.1:8781.evil.example/'), fromPage('https://example.org/'), fromPage('data:text/html,hi'),
    fromPage(''), {}, undefined]) {
    assert.equal(await handler(event), null);
  }
  assert.equal(dialog.calls.length, 0);
  const noServer = folderHandler({ dialog, getWindow: () => null, getOrigin: () => null });
  assert.equal(await noServer(fromPage(`${ORIGIN}/`)), null, 'with no server there is no own origin');
  assert.equal(await handler(fromPage(`${ORIGIN}/`)), '/a');
});

test('a destroyed window is not used and the channel is registered once under its name', async () => {
  const dialog = fakeDialog({ canceled: false, filePaths: ['/a'] });
  const handlers = {};
  registerFolderPicker({ ipcMain: { handle: (channel, fn) => { handlers[channel] = fn; } }, dialog, getWindow: () => ({ isDestroyed: () => true }), getOrigin: () => ORIGIN });
  assert.deepEqual(Object.keys(handlers), ['sutra:choose-folder']);
  assert.equal(CHANNEL, 'sutra:choose-folder');
  assert.equal(await handlers[CHANNEL](fromPage(`${ORIGIN}/`)), '/a');
  assert.equal(dialog.calls[0].length, 1, 'no window argument');
});

test('the preload bridges exactly the one function, over the same channel, and main.js loads it', () => {
  const preload = fs.readFileSync(path.join(__dirname, '../src/preload.js'), 'utf8');
  assert.match(preload, /exposeInMainWorld\('sutraDesktop', \{\s*chooseFolder: \(\) => ipcRenderer\.invoke\('sutra:choose-folder'\),\s*\}\)/);
  const main = fs.readFileSync(path.join(__dirname, '../src/main.js'), 'utf8');
  assert.match(main, /preload: path\.join\(__dirname, 'preload\.js'\)/);
  assert.match(main, /registerFolderPicker\(/);
});
