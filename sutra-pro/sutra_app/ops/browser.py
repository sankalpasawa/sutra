"""Which browser opens the app (D92, gaps G10).

    result = open_url("http://127.0.0.1:8780/", prefer="auto")        # auto | chrome | default

Only Chrome is measured (hash CSP, EventSource reconnect, sandboxed frames, color-mix), so the app opens Chrome when it is installed.
On macOS that is `open -a "Google Chrome" <url>`; everywhere else, and whenever Chrome is missing or the call fails, the system's
`webbrowser`. `prefer="default"` (`--browser default`) always uses the system default. `SUTRA_BROWSER_APP` names another application
(macOS: an app name for `open -a`; elsewhere: an executable) and beats `auto` and `chrome`, but not `default`. Nothing here raises for
a missing browser: the result says what happened and the caller prints the URL.
"""
import os
import plistlib
import shutil
import subprocess
import sys
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["open_url", "OpenResult", "find_chrome", "chrome_app_installed", "default_browser", "DefaultBrowser", "PREFER", "BROWSER_APP_ENV",
           "MAC_CHROME_PATHS", "MAC_CHROME_APPS"]

PREFER = ("auto", "chrome", "default")
BROWSER_APP_ENV = "SUTRA_BROWSER_APP"
MAC_CHROME_APPS = ("/Applications/Google Chrome.app", "~/Applications/Google Chrome.app")
MAC_CHROME_PATHS = tuple(app + "/Contents/MacOS/Google Chrome" for app in MAC_CHROME_APPS) + (
    "/Applications/Chromium.app/Contents/MacOS/Chromium", "~/Applications/Chromium.app/Contents/MacOS/Chromium")
LINUX_CHROME_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
# LaunchServices bundle ids of browsers built on Chromium (they behave like the measured Chrome)
CHROMIUM_BUNDLES = ("com.google.chrome", "org.chromium.chromium", "com.brave.browser", "com.microsoft.edgemac", "com.vivaldi.vivaldi",
                    "company.thebrowser.browser", "com.operasoftware.opera")
LAUNCH_SERVICES_PLIST = "~/Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"
OPEN_TIMEOUT_S = 10


@dataclass(frozen=True)
class OpenResult:
    opened: bool
    how: str              # chrome | app | default | none
    detail: str = ""


def find_chrome(environ: Mapping[str, str] | None = None, *, platform: str | None = None,
                exists: Callable[[str], bool] = os.path.exists, which: Callable[[str], str | None] = shutil.which) -> str | None:
    """A Chrome executable: `J2_CHROME` when it exists, then the standard macOS paths (or `google-chrome` and friends on PATH)."""
    env = os.environ if environ is None else environ
    named = (env.get("J2_CHROME") or "").strip()
    if named and exists(os.path.expanduser(named)):
        return os.path.expanduser(named)
    for path in MAC_CHROME_PATHS:
        if exists(os.path.expanduser(path)):
            return os.path.expanduser(path)
    for name in LINUX_CHROME_NAMES:
        found = which(name)
        if found:
            return found
    return None


def chrome_app_installed(*, exists: Callable[[str], bool] = os.path.exists) -> bool:
    """True when `Google Chrome.app` is installed (what `open -a "Google Chrome"` needs)."""
    return any(exists(os.path.expanduser(app)) for app in MAC_CHROME_APPS)


def open_url(url: str, prefer: str = "auto", *, environ: Mapping[str, str] | None = None, platform: str | None = None,
             run: Callable[..., Any] = subprocess.run, web_open: Callable[[str], Any] = webbrowser.open,
             exists: Callable[[str], bool] = os.path.exists) -> OpenResult:
    if prefer not in PREFER:
        raise ValueError(f"browser must be one of {', '.join(PREFER)}, not {prefer!r}")
    env = os.environ if environ is None else environ
    mac = (sys.platform if platform is None else platform) == "darwin"
    app = (env.get(BROWSER_APP_ENV) or "").strip()
    notes = ""
    if prefer != "default":
        if app:
            ok, why = _launch(run, ["open", "-a", app, url] if mac else [app, url])
            if ok:
                return OpenResult(True, "app", app)
            notes = f"{BROWSER_APP_ENV}={app} did not open ({why}); "
        elif mac and chrome_app_installed(exists=exists):
            ok, why = _launch(run, ["open", "-a", "Google Chrome", url])
            if ok:
                return OpenResult(True, "chrome", "Google Chrome")
            notes = f"Chrome did not open ({why}); "
        elif prefer == "chrome":
            notes = "Chrome was not found; "
    try:
        opened = bool(web_open(url))
    except Exception as exc:                                              # noqa: BLE001  (no browser is not a failure)
        return OpenResult(False, "none", f"{notes}the system browser failed: {exc}")
    return OpenResult(opened, "default" if opened else "none", notes + ("the system default browser" if opened else "no browser could be opened"))


def _launch(run: Callable[..., Any], argv: list[str]) -> tuple[bool, str]:
    try:
        done = run(argv, capture_output=True, text=True, timeout=OPEN_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, type(exc).__name__
    code = getattr(done, "returncode", 1)
    return code == 0, f"exit {code}"


@dataclass(frozen=True)
class DefaultBrowser:
    bundle_id: str
    chromium: bool

    @property
    def name(self) -> str:
        return {"com.apple.safari": "Safari", "com.google.chrome": "Google Chrome", "org.mozilla.firefox": "Firefox",
                "com.microsoft.edgemac": "Microsoft Edge", "com.brave.browser": "Brave", "company.thebrowser.browser": "Arc"
                }.get(self.bundle_id.lower(), self.bundle_id)


def default_browser(*, platform: str | None = None, plist_path: str | os.PathLike[str] | None = None) -> DefaultBrowser | None:
    """The system's default web browser on macOS (the LaunchServices handler of `https`; Safari when none is recorded). None on other
    systems, or when the preferences cannot be read."""
    if (sys.platform if platform is None else platform) != "darwin":
        return None
    path = Path(plist_path if plist_path is not None else os.path.expanduser(LAUNCH_SERVICES_PLIST))
    bundle = "com.apple.safari"
    try:
        with path.open("rb") as fh:
            data = plistlib.load(fh)
    except FileNotFoundError:
        data = {}
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None
    for handler in data.get("LSHandlers", []) if isinstance(data, dict) else []:
        if isinstance(handler, dict) and handler.get("LSHandlerURLScheme") == "https":
            role = handler.get("LSHandlerRoleAll") or handler.get("LSHandlerRoleViewer")
            if isinstance(role, str) and role:
                bundle = role.lower()
    return DefaultBrowser(bundle_id=bundle, chromium=any(bundle == b or bundle.startswith(b + ".") for b in CHROMIUM_BUNDLES))
