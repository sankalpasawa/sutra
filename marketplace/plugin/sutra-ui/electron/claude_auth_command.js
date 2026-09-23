"use strict";

/* Return the command Electron should spawn for Claude's OAuth flow.
 *
 * npm installs command shims as `claude.cmd` on Windows. Node's spawn() uses
 * CreateProcess directly there, so spawning bare `claude` does not apply
 * PATHEXT and fails with ENOENT even though a terminal can run it. cmd.exe is
 * the supported launcher for those shims. The command passed to /c is fixed --
 * no renderer or user-controlled value is interpolated into it. */
function claudeAuthCommand(platform, env) {
  if (platform === "win32") {
    const command = (env && (env.ComSpec || env.COMSPEC)) || "cmd.exe";
    return { command, args: ["/d", "/s", "/c", "claude auth login"] };
  }
  return { command: "claude", args: ["auth", "login"] };
}

module.exports = { claudeAuthCommand };
