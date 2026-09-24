"use strict";

/* Return the command Electron should spawn for Claude's OAuth flow.
 *
 * npm installs command shims as `claude.cmd` on Windows. Node's spawn() uses
 * CreateProcess directly there, so spawning bare `claude` does not apply
 * PATHEXT and fails with ENOENT even though a terminal can run it. Claude's
 * Windows OAuth flow may also ask the user to paste a code after opening the
 * browser. `start /wait` gives that flow a real, visible console and keeps the
 * outer child alive until sign-in finishes. The command passed to /c is fixed
 * -- no renderer or user-controlled value is interpolated into it. */
function claudeAuthCommand(platform, env) {
  if (platform === "win32") {
    const command = (env && (env.ComSpec || env.COMSPEC)) || "cmd.exe";
    /* Use cmd.exe by its executable name inside `start`. Expanding a quoted
       %ComSpec% path here adds nested quote layers that Windows `start` can
       misparse as the target to open (seen as a `\\` dialog). */
    const login = 'start "" /wait cmd.exe /d /s /c "claude auth login"' +
      ' & claude auth status >nul 2>&1';
    return { command, args: ["/d", "/s", "/c", login] };
  }
  return { command: "claude", args: ["auth", "login"] };
}

module.exports = { claudeAuthCommand };
