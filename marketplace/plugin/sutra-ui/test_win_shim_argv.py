"""The Windows provider spawn must run node.exe against a shim's .js entry.

THE BUG THIS GUARDS. The provider CLIs (claude, codex, deepseek) are node
programs. On Windows npm installs each as a `.cmd` batch shim (plus a `.ps1` and
an extensionless POSIX-sh shim), and create_subprocess_exec -- CreateProcess
with no shell -- CANNOT exec a .cmd: WinError 193 "%1 is not a valid Win32
application". Routing through `cmd.exe /c` reintroduces the classic batch-quoting
bug. proc_group.win_shim_argv instead does what the shim does: spawn
`node.exe <entry.js>`, two real tokens CreateProcess runs directly.

parse_node_shim_target is pure (no filesystem, no OS branch), so the shim
families npm/pnpm/yarn emit are pinned here on ANY host against fixture text --
this suite is the Windows spawn's proof on a machine that is not Windows. The
POSIX no-op is asserted too: on macOS the rewrite must not touch argv, or the
spawn-group guarantee (test_provider_spawn_group.py) would shift underneath it.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from proc_group import parse_node_shim_target, win_shim_argv  # noqa: E402

# The .bin directory a Windows managed install puts the shims in. Backslashes on
# purpose -- this is what os.path.dirname hands the parser on real Windows.
BIN_DIR = r"C:\Users\dev\.sutra-ui\providers\deepseek\node_modules\.bin"
BIN_DIR_FWD = "C:/Users/dev/.sutra-ui/providers/deepseek/node_modules/.bin"

# npm 7+ .cmd shim (the %dp0% form). node.exe line comes FIRST and must not be
# mistaken for the entry; PATHEXT carries an uppercase .JS that must not match.
NPM_CMD = r'''@ECHO off
GOTO start
:find_dp0
SET dp0=%~dp0
EXIT /b
:start
SETLOCAL
CALL :find_dp0
IF EXIST "%dp0%\node.exe" (
  SET "_prog=%dp0%\node.exe"
) ELSE (
  SET "_prog=node"
  SET PATHEXT=%PATHEXT:;.JS;=;%
)
endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  "%dp0%\node_modules\@sluisr\deepseek-cli\dist\cli.js" %*
'''

# Older npm .cmd shim (the bare %~dp0 form).
NPM_CMD_OLD = r'''@IF EXIST "%~dp0\node.exe" (
  "%~dp0\node.exe"  "%~dp0\node_modules\@sluisr\deepseek-cli\dist\cli.js" %*
) ELSE (
  node  "%~dp0\node_modules\@sluisr\deepseek-cli\dist\cli.js" %*
)
'''

# npm extensionless POSIX-sh shim (used from Git Bash; $basedir + ../ climb).
NPM_SH = r'''#!/bin/sh
basedir=$(dirname "$(echo "$0" | sed -e 's,\\,/,g')")
case `uname` in
    *CYGWIN*|*MINGW*|*MSYS*) basedir=`cygpath -w "$basedir"`;;
esac
if [ -x "$basedir/node" ]; then
  exec "$basedir/node"  "$basedir/../@sluisr/deepseek-cli/dist/cli.js" "$@"
else
  exec node  "$basedir/../@sluisr/deepseek-cli/dist/cli.js" "$@"
fi
'''

# pnpm .cmd shim (${dp0}-style with escaped path, single entry).
PNPM_CMD = r'''@SETLOCAL
@SET "_prog=%~dp0node.exe"
@IF NOT EXIST "%_prog%" SET "_prog=node"
"%_prog%" "%~dp0..\.pnpm\@sluisr+deepseek-cli@1.3.2\node_modules\@sluisr\deepseek-cli\dist\cli.js" %*
'''


class TestParseNodeShimTarget(unittest.TestCase):
    def test_npm_cmd_modern(self):
        got = parse_node_shim_target(NPM_CMD, BIN_DIR)
        self.assertEqual(
            got, BIN_DIR_FWD + "/node_modules/@sluisr/deepseek-cli/dist/cli.js")

    def test_npm_cmd_old(self):
        got = parse_node_shim_target(NPM_CMD_OLD, BIN_DIR)
        self.assertEqual(
            got, BIN_DIR_FWD + "/node_modules/@sluisr/deepseek-cli/dist/cli.js")

    def test_npm_sh_climbs_out_of_dotbin(self):
        # $basedir/../ must resolve away the .bin level via normpath.
        got = parse_node_shim_target(NPM_SH, BIN_DIR)
        self.assertEqual(
            got,
            "C:/Users/dev/.sutra-ui/providers/deepseek/node_modules"
            "/@sluisr/deepseek-cli/dist/cli.js")

    def test_pnpm_cmd(self):
        got = parse_node_shim_target(PNPM_CMD, BIN_DIR)
        self.assertEqual(
            got,
            "C:/Users/dev/.sutra-ui/providers/deepseek/node_modules"
            "/.pnpm/@sluisr+deepseek-cli@1.3.2/node_modules/@sluisr/"
            "deepseek-cli/dist/cli.js")

    def test_node_exe_line_is_not_the_entry(self):
        # The shim's own `"%dp0%\node.exe"` is .exe, never .js -- so the entry we
        # return is always the script, never the interpreter.
        got = parse_node_shim_target(NPM_CMD, BIN_DIR)
        self.assertTrue(got.endswith("cli.js"))
        self.assertNotIn("node.exe", got)

    def test_no_js_is_none(self):
        self.assertIsNone(parse_node_shim_target("@echo just a batch file\n", BIN_DIR))
        self.assertIsNone(parse_node_shim_target("", BIN_DIR))


class TestWinShimArgvPosixNoop(unittest.TestCase):
    """On POSIX win_shim_argv must return argv untouched -- the os.name guard
    short-circuits before any file read, so even a .cmd argv[0] passes through."""

    @unittest.skipIf(os.name == "nt", "POSIX-only no-op guarantee")
    def test_noop_on_posix(self):
        argv = [os.path.join(BIN_DIR, "deepseek.cmd"), "--acp"]
        self.assertIs(win_shim_argv(argv), argv)         # same object, untouched

    @unittest.skipIf(os.name == "nt", "POSIX-only no-op guarantee")
    def test_noop_on_posix_real_provider_path(self):
        argv = ["/usr/local/bin/deepseek", "--acp", "--model", "deepseek-chat"]
        self.assertIs(win_shim_argv(argv), argv)

    def test_empty_argv_is_returned(self):
        self.assertEqual(win_shim_argv([]), [])


if __name__ == "__main__":
    unittest.main()
