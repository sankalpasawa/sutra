/* Sutra preload -- the ONLY bridge between the panel and the shell.
 *
 * It exists for one capability the panel cannot have any other way: ending this
 * process so a staged update can replace the bundle. Everything else the panel
 * needs it already gets over HTTP.
 *
 * WHY THE PANEL CANNOT JUST CALL THE BACKEND FOR THIS. The same FastAPI app is
 * served by the CLI to an ordinary browser, where there is no app to restart.
 * A countdown that cannot restart anything is worse than no countdown -- it
 * promises something it cannot do. `window.sutra` is absent in a browser, and
 * the panel keys the whole mandatory-restart UI off its presence. That check is
 * trustworthy in the direction that matters: a page cannot conjure a preload.
 *
 * The token never reaches here. Arming happens in the main process, which owns
 * it; the renderer can only ASK, and only for these two verbs.
 */
"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("sutra", {
  // Presence is the capability signal. Read by the panel before it is willing
  // to draw a countdown.
  desktop: true,

  /* Arm the staged update and quit; the helper swaps the bundle and reopens.
     Resolves {ok:true} or {ok:false, error} -- the panel must be able to say
     why a mandatory restart did not happen. */
  applyUpdate: () => ipcRenderer.invoke("sutra:update-apply"),
  /* Tell the shell the panel's effective theme so nativeTheme can follow.
     This is what makes prefers-color-scheme — and therefore the SilverBullet
     iframe, which keys its own dark mode off that scheme — agree with the
     panel toggle. Cross-origin, so no other bridge exists. */
  setTheme: (t) => ipcRenderer.invoke("sutra:theme", t),


  /* Defer. Deliberately NOT "decline": the staged build stays on disk and is
     applied when the app next exits, so the next launch is updated either way.
     This call exists to tell the shell to stop counting, nothing more. */
  deferUpdate: () => ipcRenderer.invoke("sutra:update-defer"),

  /* Shell-side update state, for windows attached to a backend the shell did
     not start -- that backend knows nothing about shell staging, so the panel
     asks the SHELL. capable:false is a real answer (dev checkout); the panel
     keeps its honesty message on it rather than drawing a fake row. */
  updateState: () => ipcRenderer.invoke("sutra:update-state"),

  /* Staged push: fired when a background stage completes, so the countdown
     appears without the renderer polling a backend that cannot know. */
  onUpdateStaged: (cb) => {
    ipcRenderer.on("sutra:update-staged", (_e, s) => { try { cb(s); } catch (e) {} });
  },

  /* Download + verify a newer build into staging, in the background. The panel
     calls this when its own "Check for updates" finds one, because the staging
     route is token-authenticated and the token is not here. Resolves
     {ok, staged, version} -- the panel reports what actually happened rather
     than claiming a download it did not observe. Arms nothing: the staged build
     applies through the existing countdown/quit path. */
  stageUpdate: () => ipcRenderer.invoke("sutra:update-stage"),

  /* Open a native Finder folder chooser and resolve the chosen absolute path,
     or null if the user cancels. Backs the working-directory fields; absent in a
     browser, where the panel keeps its text inputs as the only way in. */
  pickDirectory: (defaultPath) => ipcRenderer.invoke("sutra:pick-directory", defaultPath),

  /* Mark a Balance actionable (done | movement). The write endpoint is
     desktop-token-gated and the token NEVER reaches the renderer — the main
     process attaches it. Absent in a browser, where Balance is read-only;
     the panel keys the checkbox UI off this verb's presence. */
  markActionable: (id, op, note, reason) =>
    ipcRenderer.invoke("sutra:balance-actionable", { id, op, note, reason }),
  teamsutraAction: (id, op) =>
    ipcRenderer.invoke("sutra:teamsutra-action", { id, op }),

  /* Run `claude auth login` (the CLI's own OAuth browser flow) in the main
     process. Resolves {ok} or {ok:false, error}; CLI output never crosses
     this bridge. Invoking it again while a sign-in runs CANCELS that one —
     the panel's button doubles as Cancel. Absent in a browser, where the
     Account card shows the CLI command instead. */
  authLogin: () => ipcRenderer.invoke("sutra:auth-login"),
});
