# QA-desktop-shell: three bugs of the Electron window, found on 2ae63d11 and fixed

QA ran the packaged app (Electron 45.2.1) against scratch data folders and reported three P2 bugs. Each was reproduced first on the unfixed sources (the same Electron
binary, started from a checkout through a stub that `require`s `desktop/src/main.js` of the base commit and then of this branch, with its own settings folder so a
real installed app is never met), fixed at its root, and given a test that fails before and passes after. Nothing outside `sutra-pro/desktop/` and three doc
paragraphs (`RELEASE-macos.md`, D118 in `DECISIONS.md`, this note) changed; no J2 file, prompt, route or golden is touched, and no Python file changed.

## 1. The Copy buttons said "Copy failed" (P2): fixed

- Reproduced: a real click (CDP mouse events) on a button whose handler is the artifacts pane's (`try { await navigator.clipboard.writeText(...) } catch { 'Copy failed' }`)
  gave "Copy failed"; `writeText` threw `NotAllowedError: Write permission denied`; `permissions.query({name:'clipboard-write'})` answered `denied`.
- Root cause: `guardNavigation()` installed `setPermissionRequestHandler(() => false)` and `setPermissionCheckHandler(() => false)`. A browser grants the plain-text
  clipboard write to a page that was clicked on; Electron grants nothing unless a handler says so, and `clipboard-sanitized-write` is one of the refused names.
  The docs promised only camera, location and notifications as refused.
- Fix: `src/permissions.js` (pure, no Electron). `permissionAllowed(permission, url, origin)` is true only for `clipboard-sanitized-write` and only when `url` is on
  the server's own origin (`isInternal`, so no prefix test, no other port, no `data:` page). `permissionHandlers(getOrigin)` builds the two handlers in the shape
  Electron calls them; the origin is asked each time because the port is known only after the server started. `main.js` installs them. Reading the clipboard, the
  camera, the microphone, the location and notifications stay refused. `docs/RELEASE-macos.md` and `desktop/README.md` say so.
- Tests (`desktop/test/permissions.test.js`, 4): the one permission and origin; every other permission refused even for the own page; look-alike origins, other
  ports, schemes, `data:`/`file:`/`about:` and missing addresses refused; the handlers as Electron calls them (request with a callback, check with an origin, with
  and without a trailing slash, with no details, before the server is up). Before the fix the module did not exist, so the file failed to load.
- Live, after the fix, same click: the button reads "Copied" and the system clipboard holds the text; `permissions.query` answers `granted`; geolocation,
  `Notification.requestPermission()` and `clipboard.readText()` are still refused. (Repro A of the report, `writeText` with a CDP gesture, needs the window to
  have focus: with an unfocused window Chromium throws "Document is not focused" before any permission is asked, with or without the fix.)

## 2. An unusable SUTRA_DATA_DIR ended the app silently, exit status 0 (P2): fixed

- Reproduced three ways on the base: a path under a missing drive, a regular file, a read-only (0500) folder. Each exits 0 in about 0.25 s with no window and no log;
  only Chromium's stderr says `Failed to create <data>/electron/SingletonLock` and `Could not open singleton lock`.
- Root cause: with `SUTRA_DATA_DIR` set, `main.js` pointed `userData` at `<data>/electron` (which `app.setPath` does not create) and then took
  `requestSingleInstanceLock() === false` for "a running instance has the focus". Chromium returns false both when another process holds the lock and when it
  cannot create the lock file, so a folder it could not write made the app exit as if it were a second instance. The log could not be written either (the log
  folder is inside the same unusable folder).
- Fix: `runtime.folderProblem(dir)` makes the folder (recursively, 0700) and checks it is a folder the app can read, write and enter; it returns `null` or one line
  with the reason. `main.js` checks `<data>/electron` first. When it is usable the behaviour is unchanged. When it is not, the app keeps its state and its log in `data-folder-error` inside the system's user-data
  folder (a folder of its own: see "Found in review" below), opens the window, and shows the existing could-not-start page and dialog with the message "Sutra Pro cannot use
  its data folder <folder>: <reason>" (the dialog says "cannot use its data folder" instead of "could not start its server"; Try Again looks at the folder again and starts the
  server in it when it is usable by now, Show the Log reveals the fallback log, Quit quits). In the self-test mode the same failure is recorded and the exit status is 1.
  As a safety net for the same ambiguity, a refused lock while the settings folder is itself unusable now shows an error box and exits 1; a refused lock with a usable
  folder is still a second instance and exits 0.
- Tests (`desktop/test/runtime.test.js`, 1): nested folders are made and a present folder is fine; a regular file where the folder should be, and a folder below a
  file, are reported with the path named; a read-only parent (`EACCES`) and a present-but-not-writable folder are reported (those two are skipped on Windows and
  for root, which ignore permission bits). Before the fix `runtime.folderProblem` did not exist.
- Live, after the fix: the three cases in self-test mode give exit 1 with the failure text in the verdict (the base: exit 0); a normal run keeps the window open on the
  error page, which names the folder and the reason, and the log line is in the fallback folder. The safety net was seen only as "the process stays up in the error
  box instead of exiting 0" (a screenshot of the box could not be taken here).

## 3. The window could attach to another data folder's server (P2): fixed

- Reproduced on the base: server Y for `dataY` on a port P; `dataX/app.pid` containing `<a live pid> P`; the app with `SUTRA_DATA_DIR=dataX` logs "attached to the
  server that is running at http://127.0.0.1:P/" and `GET /api/config` on that server says `data_dir=.../dataY`.
- Root cause: `Supervisor._attach()` trusted `pidAlive(holder.pid)` plus `/api/health`, and `/api/health` does not say which data folder answers. A pid file is only a
  claim (a crash or `kill -9` leaves one behind, any process may reuse the pid, and the port may be another Sutra server's). The same trust sat in the start loop
  when `strictPid` is off (a venv launcher on Windows: the pid in `app.pid` is not the child's, so the loop adopted any answering port in the file as "ours").
- Fix (kept in `desktop/`; no server change): the server on the port is asked `GET /api/config` and its `data_dir` is compared with this app's data folder as real
  paths (`folderVerdict`: links resolved, trailing slashes and `..` normalised, letter case ignored on Windows). A server that names another folder is turned away
  (one log line per port) and a server of our own is started instead; the same question guards the adoption of "our" server while it starts when `strictPid` is
  off, and the attach after "our server exited 0 because another won the lock". A server that names nothing comparable is taken as before: an old server with no
  such route, or one started by hand with a relative `--data-dir` (relative to a folder only that server knows). `README.md` says so.
- Tests (`desktop/test/server.test.js`, 6; `fake-server.js` gained `/api/config` and a `FAKE_CONFIG` mode): `folderVerdict` (same folder in other spellings, a link,
  another folder, a missing folder, relative/empty/odd answers, Windows letter case and drive, case-sensitive elsewhere); `fetchDataDir` (only a 200 that names a text
  folder); the bug itself with two real fake servers (a stale file naming this process's pid and the other server's port: the other server is not attached to,
  ours starts, the other keeps running); a server of the same folder is attached to when it says the folder another way (a link), says a relative name, or has no
  route; our exit 0 with a stale winner of another folder is an error, not an attach; the non-strict adoption. The stubbed-server tests got `folderOf: async () => null`
  so they stay off the network. Before the fix five of the six fail (the sixth pins what must not change).
- Live, after the fix: the same set-up (live pid in the stale file, port of server Y) starts a server of its own, the window shows `dataX`, and Y is untouched.
  Legitimate attaches still work (a server started by the command line with an absolute `--data-dir`, and one with a relative `--data-dir`).

## Found in review (two changes to bug 2's fix)

- The first fix fell back to the system's own user-data folder. The app a person uses every day holds its single-instance lock there, so with an unusable
  `SUTRA_DATA_DIR` and the everyday app open, the new instance was still refused the lock, signalled the everyday app and exited 0 without a word: the original
  bug again, in the environment QA and the owner actually work in. Seen live (a stub holding the lock of the same user-data folder, then a data folder that is a
  file): exit 0, no window, and the holder got the second-instance signal. Now `runtime.windowState` gives the window `data-folder-error` inside the system folder,
  so its lock is its own; the window opens, shows the reason, and the holder is not disturbed. Test: `windowState` in `desktop/test/runtime.test.js`.
- Try Again went straight to the supervisor, whose child process cannot start in a missing or file "data folder": the page changed from the reason to
  "could not start its server: spawn ENOTDIR". `startServer` now looks at the data folder again first (while the window opened for a folder problem) and
  reports the folder again when it is still unusable; `folderProblem` says "exists and is not a folder" for a file in the way instead of the raw `EEXIST`.

## Skipped

None: all three reproduced and were fixed.

## Seen and not changed

- `/api/health` still carries no folder identity. A `data_dir` (or an id) in the health answer would let one request ask both questions; it was left alone because the
  health shape is pinned by contract tests and the UI's fake backend, and this fix had to stay in `desktop/`.
- A server we attached to is watched through `/api/health` only. If it dies and a server of another folder takes the same port within the four missed checks, the watch
  does not notice. Narrower than the reported case; not addressed.
- After "cannot use its data folder", Try Again can start the server (the folder may be mounted by then) but the window's own state stays in `data-folder-error` for that
  session.
- With `SUTRA_DATA_DIR` unset and `~/.sutra-pro` unusable, nothing changed: the server prints its reason and the existing error page shows it.
- Notifications are refused by design (the docs say so), so the chat attention feature (`chat_attention.js`) cannot show system notifications in the desktop window.
- The four packager tests (`test/package.test.js`) need `npm ci` in `desktop/` (they import `@electron/packager`); in a fresh worktree they fail the same way on the base.

## Commands run

- `cd desktop && ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm ci --ignore-scripts && node --test "test/*.test.js"`: 57 tests, 57 pass (46 before: 11 added).
- `node --test tests/ui/js/*.test.js`: 965 tests, 963 pass, 2 skipped, 0 fail.
- `scripts/py -m pytest tests/release tests/library tests/test_docs.py tests/test_traceability.py tests/test_ownership.py tests/test_layout.py -q -p no:warnings`:
  3045 tests collected, exit status 0 (the repository's `addopts = "-q"` plus `-q` hides the summary line).
