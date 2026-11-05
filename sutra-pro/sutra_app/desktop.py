"""The desktop entry of the Windows app: `SutraPro.exe -X utf8 -m sutra_app.desktop` (D101, D102).

What `scripts/macos/launcher.sh` is to the Mac app, this is to the Windows app, and it follows the same rules (D12: there is no
window of its own, the browser is the window):

  1. no console: the app runs as a copy of `pythonw.exe`, whose standard streams are None. They are pointed at
     `<data folder>/logs/desktop.log` before anything can print, because uvicorn asks its stream whether it is a terminal
  2. one instance per data folder: `sutra_app.main.run` takes the instance lock; when it is held it opens the browser on the running
     app and returns, so a second launch (the Start menu entry again) just brings the app up
  3. the server runs in a thread, the notification-area icon (pystray, installed with the app) in the main thread: "Open Sutra Pro"
     and "Quit Sutra Pro". Without pystray or Pillow, or with `SUTRA_NO_TRAY=1`, the server runs in the main thread and the app is
     stopped with the Start menu's "Quit Sutra Pro" (`sutra-pro stop`)
  4. a start failure shows one message box that names the log, as the Mac app's dialog does

Anything after the module's own flags goes to the server (`--port 9000`, `--no-browser`, `--offline`).
"""
from __future__ import annotations

import contextlib
import ctypes
import os
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from sutra_app import oslayer

__all__ = ["main", "log_path", "attach_streams", "tray_wanted", "data_dir_of"]

LOG_NAME = "desktop.log"
QUIT_WAIT_S = 30.0
ICON = Path(__file__).resolve().parent / "assets" / "icon.png"


def log_path(environ: dict[str, str] | None = None) -> Path:
    """`<data folder>/logs/desktop.log`: the data folder is SUTRA_DATA_DIR when set, else `~/.sutra-pro` (an installed app)."""
    from sutra_app.config import default_data_dir
    return default_data_dir(environ) / "logs" / LOG_NAME


def attach_streams(path: Path | None = None) -> bool:
    """Give stdout and stderr a file when they are None (no console). True when a file was attached. Never raises."""
    if sys.stdout is not None and sys.stderr is not None:
        return False
    try:
        target = path or log_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        stream = open(target, "a", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    return True


def data_dir_of(args: Sequence[str], environ: dict[str, str] | None = None) -> Path:
    """The data folder the server will use: `--data-dir D` (or `--data-dir=D`) in its arguments, else SUTRA_DATA_DIR, else `~/.sutra-pro`."""
    from sutra_app.config import default_data_dir
    for index, arg in enumerate(args):
        if arg == "--data-dir" and index + 1 < len(args):
            return Path(args[index + 1]).expanduser()
        if arg.startswith("--data-dir="):
            return Path(arg.split("=", 1)[1]).expanduser()
    return default_data_dir(environ)


def tray_wanted(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return oslayer.IS_WINDOWS and not (env.get("SUTRA_NO_TRAY") or "").strip()


def _message_box(text: str) -> None:
    """One error box (Windows only), as the Mac app shows one. Printed when there is no desktop to show it on."""
    print(text, flush=True)
    if os.environ.get("SUTRA_NO_DIALOG") == "1" or not oslayer.IS_WINDOWS:
        return
    with contextlib.suppress(Exception):
        ctypes.windll.user32.MessageBoxW(None, text, "Sutra Pro", 0x10)          # type: ignore[attr-defined]  (MB_ICONERROR)


def _serve(argv: list[str], result: dict[str, int]) -> None:
    from sutra_app.main import run
    try:
        result["code"] = run(argv)
    except SystemExit as stop:
        result["code"] = stop.code if isinstance(stop.code, int) else 1
    except BaseException as exc:                                                    # noqa: BLE001  (the box says what happened)
        print(f"sutra-pro: the server stopped with an error: {type(exc).__name__}: {exc}", flush=True)
        result["code"] = 1


def _run_with_tray(argv: list[str], data_dir: Path) -> int:
    """The server in a thread and the tray icon here. Returns the server's exit status; None-safe when the tray cannot start."""
    try:
        import pystray
        from PIL import Image
        image = Image.open(ICON)
    except Exception:                                                                # noqa: BLE001  (no tray is not a failure)
        return -1
    from sutra_app.ops import browser, lock

    result: dict[str, int] = {}
    worker = threading.Thread(target=_serve, args=(argv, result), name="sutra-server", daemon=False)
    worker.start()

    def open_app(icon: object = None, item: object = None) -> None:
        holder = lock.read_holder(data_dir)
        if holder is not None and holder.url:
            browser.open_url(holder.url)

    def quit_app(icon: "pystray.Icon", item: object = None) -> None:
        with contextlib.suppress(OSError):
            lock.request_stop(data_dir)
        threading.Thread(target=lambda: (worker.join(QUIT_WAIT_S), icon.stop()), daemon=True).start()

    menu = pystray.Menu(pystray.MenuItem("Open Sutra Pro", open_app, default=True), pystray.MenuItem("Quit Sutra Pro", quit_app))
    icon = pystray.Icon("sutra-pro", image, "Sutra Pro", menu)

    def end_with_the_server() -> None:
        worker.join()
        icon.stop()                                    # the server ended by itself (an error, or `sutra-pro stop`): the icon goes too

    threading.Thread(target=end_with_the_server, name="sutra-tray-watch", daemon=True).start()
    try:
        icon.run()
    except Exception as exc:                                                         # noqa: BLE001
        print(f"sutra-pro: the tray icon failed ({type(exc).__name__}: {exc}); the app keeps running without it", flush=True)
        worker.join()
    worker.join(QUIT_WAIT_S)
    return result.get("code", 0)


def main(argv: Sequence[str] | None = None) -> int:
    attach_streams()
    oslayer.setup_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    if "--browser" not in args:
        args = ["--browser", "auto", *args]
    started = time.monotonic()
    data_dir = data_dir_of(args)
    code = -1
    from sutra_app.ops import lock
    if tray_wanted() and not lock.is_locked(data_dir):          # a second launch only opens the running app: no second icon
        code = _run_with_tray(args, data_dir)
    if code == -1:                                     # no tray: the server owns the main thread
        result: dict[str, int] = {}
        _serve(args, result)
        code = result.get("code", 0)
    if code != 0 and time.monotonic() - started < 60:
        _message_box(f"Sutra Pro could not start (exit {code}).\n\nDetails: {log_path()}")
    return code


if __name__ == "__main__":
    sys.exit(main())
