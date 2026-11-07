"""`sutra-pro doctor`: fourteen checks of the machine, the data folder and the setup, each with a fix hint (gaps G08, D34, D92, D94).

    report = run(settings, offline=False)          # starts no server, makes no model call, writes nothing but a probe file
    print("\\n".join(report.lines()));  exit(0 if report.ok else 1)

A check is `ok`, `warn` (the app runs, something is worth fixing), `fail` (the app cannot do its job) or `skip` (not looked at: offline,
or optional). The report is `ok` when nothing failed. The checks, in order:

    python, data_dir, disk, database, env_file, claude, codex, gh, chrome, port, instance, library, browser, settings

`claude` and `codex` are judged together: when one of them is unusable the other still lets the app work, so the broken one is a
warning; when neither works both fail. The CLI checks reuse the connector layer's own status probes (`build_router(...).status()`:
`<cli> --version`, `claude auth status`, `codex login status`; no model call). An API-key login is refused (D34).
`offline` skips the three CLI checks and the two browser checks.
"""
import json
import os
from sutra_app import oslayer
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sutra_app.config import Settings, read_env_file
from sutra_app.ops import browser, lock
from sutra_app.ops.envfile import SMTP_VARS, mode_problem

__all__ = ["Check", "Report", "run", "CHECK_IDS", "MIN_FREE_BYTES", "PORT_RANGE", "seed_dir", "missing_seed_templates", "sync_seed_library"]

MIN_FREE_BYTES = 1024 ** 3
MIN_PYTHON = (3, 11)
PORT_RANGE = range(8780, 8800)
GH_TIMEOUT_S = 10
CHECK_IDS = ("python", "data_dir", "disk", "database", "env_file", "claude", "codex", "gh", "chrome", "port", "instance", "library",
             "browser", "settings")
_LOGIN = {"claude": "claude auth login", "codex": "codex login"}


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    status: str                 # ok | warn | fail | skip
    detail: str
    fix: str = ""

    def line(self) -> str:
        tag = {"ok": "[ ok ]", "warn": "[WARN]", "fail": "[FAIL]", "skip": "[skip]"}[self.status]
        text = f"{tag} {self.title}: {self.detail}"
        return text + (f"  -> fix: {self.fix}" if self.fix and self.status in ("warn", "fail") else "")

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "title": self.title, "status": self.status, "detail": self.detail, "fix": self.fix}


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures()

    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == "fail"]

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for c in self.checks if c.status == s) for s in ("ok", "warn", "fail", "skip")}

    def lines(self) -> list[str]:
        counts = self.counts()
        return [c.line() for c in self.checks] + [
            f"{counts['ok']} ok, {counts['warn']} warning(s), {counts['fail']} failed, {counts['skip']} skipped"]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "summary": self.counts(), "checks": [c.to_dict() for c in self.checks]}


# ---- the seed library ---------------------------------------------------------------------------------------------------------

def seed_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "engine" / "seed" / "library"


def _entries(index_path: Path) -> list[dict[str, Any]]:
    try:
        doc = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = doc.get("templates") if isinstance(doc, dict) else None
    return [t for t in items if isinstance(t, dict)] if isinstance(items, list) else []


def _key(entry: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(entry.get("artifact")), str(entry.get("section_slug")), str(entry.get("slug")))


def missing_seed_templates(data_dir: str | os.PathLike[str], seed: Path | None = None) -> list[str] | None:
    """The seed templates (`artifact/section/slug`) that `<data>/library` lacks, as folder or as index entry. None when there is no
    library folder yet (the engine seeds it whole at the first run)."""
    library = Path(data_dir) / "library"
    if not library.is_dir():
        return None
    have = {_key(e) for e in _entries(library / "index.json")}
    wanted = sorted(_key(e) for e in _entries((seed or seed_dir()) / "index.json"))
    return ["/".join(key) for key in wanted if key not in have or not library.joinpath(*key).is_dir()]


def sync_seed_library(data_dir: str | os.PathLike[str], seed: Path | None = None) -> list[str]:
    """Copy the seed templates the data library lacks and add their index entries. Nothing that exists is changed. Returns the
    templates added (`artifact/section/slug`). A data folder without a library gets the whole seed."""
    seed = seed or seed_dir()
    library = Path(data_dir) / "library"
    wanted = _entries(seed / "index.json")
    if not library.exists():
        library.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copytree(seed, library)
        return ["/".join(_key(e)) for e in wanted]
    index_path = library / "index.json"
    try:
        doc = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = None
    if not isinstance(doc, dict) or not isinstance(doc.get("templates"), list):
        doc = {"schema": "template-library/1", "templates": []}
    have = {_key(e) for e in doc["templates"] if isinstance(e, dict)}
    added: list[str] = []
    for entry in wanted:
        key = _key(entry)
        folder, source = library.joinpath(*key), seed.joinpath(*key)
        changed = False
        if not folder.exists() and source.is_dir():
            shutil.copytree(source, folder)
            changed = True
        if key not in have:
            doc["templates"].append(entry)
            have.add(key)
            changed = True
        if changed:
            added.append("/".join(key))
    if added:
        tmp = index_path.with_name(f".index.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        oslayer.replace(tmp, index_path)
    return added


# ---- the checks ---------------------------------------------------------------------------------------------------------------

def _nearest_existing(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return Path("/")


def _check_python(version: Sequence[int]) -> Check:
    text = ".".join(str(n) for n in tuple(version)[:3])
    if tuple(version)[:2] >= MIN_PYTHON:
        return Check("python", "Python", "ok", text)
    return Check("python", "Python", "fail", f"{text} is older than {MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
                 f"install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer (for example `uv venv --python 3.11`)")


def _check_data_dir(data_dir: Path) -> Check:
    title = "Data folder"
    if data_dir.exists() and not data_dir.is_dir():
        return Check("data_dir", title, "fail", f"{data_dir} exists and is not a folder", "move it away or set SUTRA_DATA_DIR")
    anchor = data_dir if data_dir.exists() else _nearest_existing(data_dir)
    try:
        with tempfile.NamedTemporaryFile(dir=anchor, prefix=".sutra-doctor-"):
            pass
    except OSError as exc:
        return Check("data_dir", title, "fail", f"{anchor} is not writable ({exc.strerror or exc})",
                     f"fix the permissions (`chmod u+rwx {anchor}`) or set SUTRA_DATA_DIR to another folder")
    if not data_dir.exists():
        return Check("data_dir", title, "ok", f"{data_dir} will be created at the first start")
    if oslayer.IS_WINDOWS:
        return Check("data_dir", title, "ok", f"{data_dir} (writable; Windows keeps a profile folder private to its user)")
    mode = data_dir.stat().st_mode & 0o777
    if mode & 0o077:
        return Check("data_dir", title, "warn", f"{data_dir} is mode {mode:03o}; it holds your work and should be private",
                     f"chmod 700 {data_dir}")
    return Check("data_dir", title, "ok", f"{data_dir} (writable, mode {mode:03o})")


def _check_disk(data_dir: Path, minimum: int) -> Check:
    anchor = _nearest_existing(data_dir)
    try:
        free = shutil.disk_usage(anchor).free
    except OSError as exc:
        return Check("disk", "Free space", "warn", f"could not read the free space of {anchor}: {exc}", "check the disk by hand")
    gb = free / 1024 ** 3
    if free < minimum:
        return Check("disk", "Free space", "fail", f"{gb:.2f} GB free on the disk of {anchor}; at least {minimum / 1024 ** 3:.0f} GB is needed",
                     "free some space (runs write screenshots and logs)")
    return Check("disk", "Free space", "ok", f"{gb:.1f} GB free")


def _check_database(settings: Settings) -> Check:
    from sutra_app.orchestrator.schema import SCHEMA_VERSION
    path = settings.db_path
    if not path.exists():
        return Check("database", "Database", "ok", "none yet; it is created at the first start")
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        try:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return Check("database", "Database", "fail", f"{path.name} cannot be opened ({exc})",
                     "if it is not a Sutra database move it away; otherwise restore a backup")
    if version > SCHEMA_VERSION:
        return Check("database", "Database", "fail", f"schema version {version} is newer than this app's {SCHEMA_VERSION}",
                     "update the app (a newer version wrote this file); do not open it with an older one")
    note = "" if version == SCHEMA_VERSION else f"; it will be upgraded to {SCHEMA_VERSION} at the next start"
    return Check("database", "Database", "ok", f"schema version {version}{note}")


def _check_env_file(settings: Settings) -> Check:
    path = settings.env_file
    if not path.exists():
        return Check("env_file", ".env file", "ok",
                     f"none at {path} (optional: the owner override key and live email need one; `sutra-pro config init` writes a template)")
    problem = mode_problem(path)
    if problem:
        return Check("env_file", ".env file", "warn", f"{path}: {problem}", f"chmod 600 {path}")
    return Check("env_file", ".env file", "ok", f"{path} (mode 600)")


def _provider_statuses(settings: Settings, cfg: Any) -> dict[str, Any]:
    from sutra_app.connectors.factory import build_router
    router = build_router(settings.model_copy(update={"connector": "auto", "offline": False}), config=cfg)
    try:
        return {p.name: p for p in router.status().providers}
    finally:
        router.close()


def _judge(name: str, status: Any, desktop: bool = False) -> tuple[str, str, str]:
    """('ok' | 'warn' | 'bad', detail, fix) for one CLI. `desktop`: Claude Desktop is installed, which is not Claude Code (GAP-providers)."""
    from sutra_app.connectors.factory import TESTED_VERSIONS
    login = _LOGIN[name]
    if (status is None or not status.installed) and name == "claude" and desktop:
        return "bad", "Claude Desktop is installed, but Sutra needs Claude Code, a separate command-line tool", \
            f"install Claude Code (claude.com/claude-code), or choose its file in Settings, Connectors; then run `{login}`"
    if status is None or not status.installed:
        return "bad", "not found on PATH or in the usual install folders", \
            f"install the {name} CLI (or choose its file in Settings, Connectors), then run `{login}`"
    version = status.version or "unknown version"
    if status.billing == "api_key":
        return "bad", f"{version}: signed in with an API key, which is refused", f"sign out, then `{login}` with your subscription account"
    if status.signed_in is False:
        return "bad", f"{version}: not signed in", f"run `{login}`"
    if status.signed_in is None:
        return "bad", f"{version}: could not tell whether it is signed in ({(status.detail or '')[:120]})", f"run `{name} --version` and `{login}` by hand"
    how = f", {status.method}" if status.method else ""
    tested = TESTED_VERSIONS.get(name)
    if tested and status.version and status.version != tested:
        return "warn", f"{version} signed in{how}; the app was tested with {tested}", f"if calls fail, install {name} {tested}"
    return "ok", f"{version} signed in{how}", ""


def _cli_checks(settings: Settings, cfg: Any, offline: bool) -> list[Check]:
    if offline:
        return [Check(n, n, "skip", "not checked (offline)") for n in ("claude", "codex")]
    try:
        statuses = _provider_statuses(settings, cfg)
    except Exception as exc:                                                # noqa: BLE001
        return [Check(n, n, "fail", f"could not probe the CLI ({type(exc).__name__}: {str(exc)[:150]})", "run `sutra-pro doctor --offline` and report this")
                for n in ("claude", "codex")]
    judged = {name: _judge(name, statuses.get(name), bool(getattr(cfg, "claude_desktop", False))) for name in ("claude", "codex")}
    any_usable = any(level in ("ok", "warn") for level, _, _ in judged.values())
    out = []
    for name, (level, detail, fix) in judged.items():
        if level == "bad":
            level = "warn" if any_usable else "fail"
            if level == "warn":
                detail += " (the other CLI can serve)"
        out.append(Check(name, name, {"ok": "ok", "warn": "warn", "fail": "fail"}[level], detail, fix))
    return out


def _check_gh(cfg: Any, offline: bool, env: Mapping[str, str], which: Callable[[str], str | None]) -> Check:
    if offline:
        return Check("gh", "gh", "skip", "not checked (offline)")
    exe = cfg.gh_exe
    if not which(exe):
        return Check("gh", "gh", "skip", "not installed (optional: only the GitHub tool uses it)")
    child_env = {**env, **dict(cfg.extra_env)}
    try:
        done = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=GH_TIMEOUT_S, env=child_env,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return Check("gh", "gh", "warn", f"installed, `gh auth status` did not run ({type(exc).__name__})", "run `gh auth status` by hand")
    if done.returncode == 0:
        return Check("gh", "gh", "ok", "installed and signed in")
    return Check("gh", "gh", "warn", "installed, not signed in (optional)", "run `gh auth login` if you want the GitHub tool")


def _check_chrome(effective_chrome: str, offline: bool, which: Callable[[str], str | None], exists: Callable[[str], bool]) -> Check:
    if offline:
        return Check("chrome", "Chrome", "skip", "not checked (offline)")
    named = os.path.expanduser((effective_chrome or "").strip())
    if named and exists(named):
        return Check("chrome", "Chrome", "ok", named)
    found = browser.find_chrome({}, exists=exists, which=which)          # the standard places (the named one was tried above)
    if found and not named:
        return Check("chrome", "Chrome", "ok", found)
    if found:
        return Check("chrome", "Chrome", "warn", f"J2_CHROME points to {named}, which does not exist (Chrome is at {found})",
                     f"`sutra-pro config set chrome '{found}'`, or unset J2_CHROME")
    why = f"J2_CHROME points to {named}, which does not exist; " if named else "not found; "
    return Check("chrome", "Chrome", "warn", why + "Audit will judge from code only (no screenshots)",
                 "install Google Chrome, or set its path: `sutra-pro config set chrome /path/to/chrome`")


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _check_port(env: Mapping[str, str], ports: Sequence[int]) -> Check:
    explicit = (env.get("SUTRA_PORT") or "").strip()
    if explicit:
        if explicit.isdigit() and _port_free(int(explicit)):
            return Check("port", "Port", "ok", f"{explicit} (SUTRA_PORT) is free")
        return Check("port", "Port", "warn", f"SUTRA_PORT={explicit} is busy or not a port; the server will refuse to start on it",
                     "unset SUTRA_PORT, or stop whatever uses it")
    free = [p for p in ports if _port_free(p)]
    if free:
        return Check("port", "Port", "ok", f"{free[0]} is free (range {ports[0]} to {ports[-1]})")
    return Check("port", "Port", "fail", f"every port from {ports[0]} to {ports[-1]} is busy", "stop the programs that use them, or set SUTRA_PORT")


def _check_instance(data_dir: Path) -> Check:
    if not lock.is_locked(data_dir):
        return Check("instance", "Second instance", "ok", "no other Sutra Pro runs on this data folder")
    holder = lock.read_holder(data_dir)
    if holder is not None and holder.pid == os.getpid():
        return Check("instance", "Second instance", "ok", "this process holds the data folder")
    where = f" on {holder.url} (pid {holder.pid})" if holder is not None and holder.url else ""
    return Check("instance", "Second instance", "warn", f"Sutra Pro already runs{where}; a second launch only opens it",
                 "`sutra-pro stop` to stop it, or use `sutra-pro open`")


def _check_library(data_dir: Path, seed: Path | None) -> Check:
    missing = missing_seed_templates(data_dir, seed)
    if missing is None:
        return Check("library", "Template library", "ok", "not created yet; the first run seeds it")
    if missing:
        return Check("library", "Template library", "warn", f"{len(missing)} seed template(s) are missing from {data_dir / 'library'}: "
                     + ", ".join(missing[:3]) + (" ..." if len(missing) > 3 else ""), "run `sutra-pro config sync-library` (adds only what is missing)")
    return Check("library", "Template library", "ok", "all seed templates are present")


def _check_browser(offline: bool, platform: str | None, plist_path: Any, chrome_known: bool) -> Check:
    if offline:
        return Check("browser", "Default browser", "skip", "not checked (offline)")
    found = browser.default_browser(platform=platform, plist_path=plist_path)
    if found is None:
        return Check("browser", "Default browser", "skip", "not checked on this system")
    if found.chromium:
        return Check("browser", "Default browser", "ok", f"{found.name} (Chrome-based)")
    if chrome_known:
        return Check("browser", "Default browser", "ok", f"{found.name}; Sutra Pro opens Chrome instead (D92)")
    return Check("browser", "Default browser", "warn", f"{found.name}; only Chrome is measured, other browsers are not verified",
                 "install Google Chrome (Sutra Pro opens it), or open the page in Chrome yourself")


def _check_settings(settings: Settings, env: Mapping[str, str]) -> tuple[Check, str]:
    """The engine's setting layers must be valid, and `send_mode=live` needs the SMTP login. Returns the check and the effective `chrome`."""
    from sutra_app.engine.spec import EngineSettings, SettingsError, read_settings_file
    title = "Locked settings"
    effective = ""
    try:
        global_file = read_settings_file(settings.data_dir / "engine.json")
        layers = {"engine.json": EngineSettings.layered(env, global_file, None, {})}
        effective = layers["engine.json"].chrome
        departments = settings.departments_dir
        for path in sorted(departments.glob("*/engine.json")) if departments.is_dir() else []:
            layers[f"departments/{path.parent.name}/engine.json"] = EngineSettings.layered(env, global_file, read_settings_file(path), {})
    except (SettingsError, OSError) as exc:
        return Check("settings", title, "fail", str(exc)[:300], "correct the file, or set the field again with `sutra-pro config set <field> <value>`"), effective
    live = [name for name, eff in layers.items() if eff.send_mode == "live"]
    if live:
        have = {**read_env_file(settings.env_file), **{k: v for k, v in env.items() if k in SMTP_VARS}}
        missing = [v for v in SMTP_VARS if not (have.get(v) or "").strip()]
        if missing:
            return Check("settings", title, "fail", f"send_mode is live ({', '.join(live)}) but {', '.join(missing)} is not set",
                         f"put the J2_SMTP_* lines in {settings.env_file} (`sutra-pro config init` writes a template), or `sutra-pro config set send_mode dry-run`"), effective
        return Check("settings", title, "ok", "send_mode is live and the SMTP login is present"), effective
    return Check("settings", title, "ok", "valid (send_mode is not live)"), effective


# ---- the run ------------------------------------------------------------------------------------------------------------------

def run(settings: Settings, *, offline: bool = False, environ: Mapping[str, str] | None = None, config: Any = None,
        platform: str | None = None, ports: Sequence[int] = PORT_RANGE, python_version: Sequence[int] | None = None,
        plist_path: Any = None, seed: Path | None = None, min_free: int = MIN_FREE_BYTES,
        which: Callable[[str], str | None] = shutil.which, exists: Callable[[str], bool] = os.path.exists) -> Report:
    """All fourteen checks, in `CHECK_IDS` order. A check that raises becomes a failed check, never an exception."""
    env = os.environ if environ is None else environ
    version = tuple(python_version) if python_version is not None else tuple(sys.version_info[:3])
    data_dir = settings.data_dir
    if config is None:
        from sutra_app.connectors.discover import connector_config         # the CLIs where installers put them, as the app finds them
        config = connector_config(data_dir, environ=env)
    try:
        settings_check, chrome_path = _check_settings(settings, env)
    except Exception as exc:                                                # noqa: BLE001
        settings_check, chrome_path = Check("settings", "Locked settings", "fail", f"the check crashed: {type(exc).__name__}: {str(exc)[:200]}",
                                            "report this"), ""
    chrome = _check_chrome(chrome_path, offline, which, exists)
    claude_codex = _cli_checks(settings, config, offline)
    steps: list[tuple[str, Callable[[], Check]]] = [
        ("python", lambda: _check_python(version)),
        ("data_dir", lambda: _check_data_dir(data_dir)),
        ("disk", lambda: _check_disk(data_dir, min_free)),
        ("database", lambda: _check_database(settings)),
        ("env_file", lambda: _check_env_file(settings)),
        ("claude", lambda: claude_codex[0]),
        ("codex", lambda: claude_codex[1]),
        ("gh", lambda: _check_gh(config, offline, env, which)),
        ("chrome", lambda: chrome),
        ("port", lambda: _check_port(env, ports)),
        ("instance", lambda: _check_instance(data_dir)),
        ("library", lambda: _check_library(data_dir, seed)),
        ("browser", lambda: _check_browser(offline, platform, plist_path, chrome.status == "ok")),
        ("settings", lambda: settings_check),
    ]
    report = Report()
    for check_id, step in steps:
        try:
            report.checks.append(step())
        except Exception as exc:                                            # noqa: BLE001
            report.checks.append(Check(check_id, check_id, "fail", f"the check crashed: {type(exc).__name__}: {str(exc)[:200]}",
                                       "report this; the rest of the report is still valid"))
    return report
