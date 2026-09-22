# wincompat — Windows import shims for the Sutra backend (BETA)

The FastAPI backend imports POSIX-only stdlib modules (`fcntl`, `termios`,
`pty`, `tty`) at module load across ~11 files. On Windows those imports abort
the whole backend before it can serve the panel. Rather than edit every call
site, this directory is put FIRST on PYTHONPATH on Windows (main.js startBackend,
win32 branch), so `import fcntl` etc. resolve to these shims and the backend
boots and serves the UI.

SCOPE / HONESTY: these are BETA shims.
- `fcntl.flock`/`lockf` are NO-OPS: file locking does not actually happen on
  Windows yet. Safe enough for a single-user desktop beta; real locking
  (msvcrt.locking / portalocker) is Stage B.
- `termios`/`pty`/`tty` make imports succeed; the terminal pane does not work
  on Windows yet (Stage B).
Never placed on PYTHONPATH on macOS/Linux, where the real modules are used.
